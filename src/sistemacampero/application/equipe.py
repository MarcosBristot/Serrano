"""Equipe: convites (token de uso único), papéis e chaves de API.

Tokens e chaves só existem em claro na resposta de criação; o banco guarda o sha256.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable
from typing import Any, Protocol
from uuid import UUID

from sistemacampero.domain.errors import Invalido, NaoAutenticado, Proibido
from sistemacampero.domain.tenancy import ContextoOrganizacao, Papel, Principal

DIAS_CONVITE = 7
PREFIXO_CHAVE = "cmp_"
ESCOPOS = {"ler": Papel.LEITOR, "operar": Papel.GESTOR}


def _sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode()).hexdigest()


class RepositorioEquipe(Protocol):
    def criar_convite(
        self, org: UUID, email: str, papel: str, token_hash: str, dias: int, criado_por: UUID | None
    ) -> dict[str, Any]: ...
    def convite_por_hash(self, token_hash: str) -> dict[str, Any] | None: ...
    def aceitar_convite(
        self, org: UUID, convite_id: UUID, usuario_id: UUID, papel: str
    ) -> None: ...
    def criar_chave(
        self,
        org: UUID,
        nome: str,
        prefixo: str,
        hash_: str,
        escopos: list[str],
        criado_por: UUID | None,
    ) -> dict[str, Any]: ...
    def chave_por_prefixo(self, prefixo: str) -> dict[str, Any] | None: ...


class ServicoEquipe:
    def __init__(
        self,
        repo: RepositorioEquipe,
        enviar_convite: Callable[[str, str, str], None] | None = None,
    ) -> None:
        self._repo = repo
        self._enviar = enviar_convite  # (email, nome_da_org_ou_papel, token)

    def convidar(
        self, ctx: ContextoOrganizacao, email: str, papel: Papel
    ) -> tuple[dict[str, Any], str, bool]:
        if papel is Papel.OWNER:
            raise Invalido("Convite só para gestor ou leitor.", codigo="PAPEL_INVALIDO")
        token = secrets.token_urlsafe(32)
        convite = self._repo.criar_convite(
            ctx.organizacao_id, email, papel.value, _sha256(token), DIAS_CONVITE, ctx.usuario_id
        )
        enviado = False
        if self._enviar is not None:
            try:
                self._enviar(email, papel.value, token)
                enviado = True
            except Exception:  # sem SMTP: o owner compartilha o link manualmente
                enviado = False
        return convite, token, enviado

    def aceitar(self, quem: Principal, token: str) -> UUID:
        convite = self._repo.convite_por_hash(_sha256(token))
        if convite is None:
            raise Invalido("Convite inválido.", codigo="CONVITE_INVALIDO")
        if not quem.email or quem.email.lower() != str(convite["email"]).lower():
            raise Proibido(
                "Este convite foi enviado para outro e-mail.", codigo="CONVITE_OUTRO_EMAIL"
            )
        self._repo.aceitar_convite(
            convite["organizacao_id"], convite["id"], quem.usuario_id, convite["papel"]
        )
        org: UUID = convite["organizacao_id"]
        return org

    def criar_chave(
        self, ctx: ContextoOrganizacao, nome: str, escopos: list[str]
    ) -> tuple[dict[str, Any], str]:
        if not escopos or set(escopos) - set(ESCOPOS):
            raise Invalido("Escopos: 'ler' e/ou 'operar'.", codigo="ESCOPO_INVALIDO")
        prefixo = secrets.token_hex(4)
        token = f"{PREFIXO_CHAVE}{prefixo}_{secrets.token_urlsafe(32)}"
        chave = self._repo.criar_chave(
            ctx.organizacao_id, nome, prefixo, _sha256(token), sorted(set(escopos)), ctx.usuario_id
        )
        return chave, token

    def autenticar_chave(self, token: str) -> ContextoOrganizacao:
        partes = token.removeprefix(PREFIXO_CHAVE).split("_", 1)
        if not token.startswith(PREFIXO_CHAVE) or len(partes) != 2:
            raise NaoAutenticado("Chave de API malformada.", codigo="CHAVE_INVALIDA")
        linha = self._repo.chave_por_prefixo(partes[0])
        if (
            linha is None
            or linha["revogada_em"] is not None
            or not hmac.compare_digest(str(linha["hash"]), _sha256(token))
        ):
            raise NaoAutenticado("Chave de API inválida ou revogada.", codigo="CHAVE_INVALIDA")
        papel = Papel.GESTOR if "operar" in linha["escopos"] else Papel.LEITOR
        return ContextoOrganizacao(linha["organizacao_id"], papel, chave_api_id=linha["id"])
