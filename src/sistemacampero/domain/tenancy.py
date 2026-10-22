"""Multiempresa: organizações, membros e papéis."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sistemacampero.domain.errors import Invalido, Proibido


class Papel(StrEnum):
    """Papel de um usuário dentro de uma organização."""

    OWNER = "owner"
    GESTOR = "gestor"
    LEITOR = "leitor"


class Permissao(StrEnum):
    LER = "ler"
    EXPORTAR = "exportar"
    OPERAR = "operar"  # upload, cadastro, ciclo de alertas, limiares, preços
    ADMINISTRAR = "administrar"  # equipe, chaves de API, plano


_PERMISSOES: dict[Papel, frozenset[Permissao]] = {
    Papel.OWNER: frozenset(Permissao),
    Papel.GESTOR: frozenset({Permissao.LER, Permissao.EXPORTAR, Permissao.OPERAR}),
    Papel.LEITOR: frozenset({Permissao.LER, Permissao.EXPORTAR}),
}


def papel_permite(papel: Papel, permissao: Permissao) -> bool:
    return permissao in _PERMISSOES[papel]


@dataclass(frozen=True, slots=True)
class Principal:
    """Quem faz a requisição (hoje só usuário autenticado; chave de API entra no M7)."""

    usuario_id: UUID
    email: str | None = None


@dataclass(frozen=True, slots=True)
class Vinculo:
    """Participação de um usuário numa organização."""

    organizacao_id: UUID
    organizacao_nome: str
    organizacao_slug: str
    papel: Papel


@dataclass(frozen=True, slots=True)
class ContextoOrganizacao:
    """Organização ativa da requisição e o papel do usuário nela."""

    organizacao_id: UUID
    papel: Papel
    usuario_id: UUID | None = None  # None quando o acesso é por chave de API
    chave_api_id: UUID | None = None

    def exigir(self, permissao: Permissao) -> None:
        if not papel_permite(self.papel, permissao):
            raise Proibido(
                f"O papel '{self.papel}' não permite '{permissao}'.",
                codigo="PAPEL_SEM_PERMISSAO",
                permissao=str(permissao),
            )


@dataclass(frozen=True, slots=True)
class Organizacao:
    id: UUID
    nome: str
    slug: str
    fuso: str = "America/Sao_Paulo"
    inicio_safra_mes: int = 7


_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def gerar_slug(nome: str) -> str:
    """'Fazenda São João Ltda.' -> 'fazenda-sao-joao-ltda'."""
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")
    return slug[:60].rstrip("-")


def validar_slug(slug: str) -> str:
    if not (3 <= len(slug) <= 60) or not _SLUG.fullmatch(slug):
        raise Invalido(
            "Slug deve ter de 3 a 60 caracteres: letras minúsculas, números e hífens.",
            codigo="SLUG_INVALIDO",
        )
    return slug
