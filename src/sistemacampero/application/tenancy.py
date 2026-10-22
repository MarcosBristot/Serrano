"""Casos de uso de conta e organização."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from uuid import UUID

from sistemacampero.domain.errors import Conflito, Invalido, Proibido
from sistemacampero.domain.ports import RepositorioOrganizacoes
from sistemacampero.domain.tenancy import (
    ContextoOrganizacao,
    Organizacao,
    Principal,
    Vinculo,
    gerar_slug,
    validar_slug,
)

PLANO_PADRAO = "basico"
DIAS_TRIAL = 30


@dataclass(frozen=True, slots=True)
class Perfil:
    principal: Principal
    vinculos: list[Vinculo]


class ServicoTenancy:
    """Resolve a organização ativa e cria a primeira organização do usuário."""

    def __init__(self, repo: RepositorioOrganizacoes) -> None:
        self._repo = repo

    def perfil(self, principal: Principal) -> Perfil:
        return Perfil(principal, self._repo.vinculos_do_usuario(principal.usuario_id))

    def resolver_organizacao(
        self, principal: Principal, organizacao_id: UUID | None
    ) -> ContextoOrganizacao:
        """Org do header ``X-Organizacao-Id``; opcional quando o usuário tem só uma."""
        vinculos = self._repo.vinculos_do_usuario(principal.usuario_id)
        if organizacao_id is not None:
            for v in vinculos:
                if v.organizacao_id == organizacao_id:
                    return ContextoOrganizacao(v.organizacao_id, v.papel)
            # Mesma resposta para "não existe" e "não é membro": não revela existência.
            raise Proibido("Você não participa desta organização.", codigo="ORGANIZACAO_PROIBIDA")
        if not vinculos:
            raise Proibido(
                "Usuário ainda não participa de nenhuma organização.",
                codigo="SEM_ORGANIZACAO",
            )
        if len(vinculos) > 1:
            raise Invalido(
                "Usuário participa de mais de uma organização: envie X-Organizacao-Id.",
                codigo="ORGANIZACAO_AMBIGUA",
            )
        v = vinculos[0]
        return ContextoOrganizacao(v.organizacao_id, v.papel)

    def criar_primeira_organizacao(
        self, principal: Principal, nome: str, slug: str | None = None
    ) -> Organizacao:
        nome = nome.strip()
        if not (2 <= len(nome) <= 120):
            raise Invalido("Nome deve ter de 2 a 120 caracteres.", codigo="NOME_INVALIDO")
        if self._repo.vinculos_do_usuario(principal.usuario_id):
            raise Conflito("Usuário já participa de uma organização.", codigo="JA_TEM_ORGANIZACAO")
        org = Organizacao(id=uuid.uuid4(), nome=nome, slug=validar_slug(slug or gerar_slug(nome)))
        self._repo.criar_organizacao(org, principal.usuario_id, PLANO_PADRAO, DIAS_TRIAL)
        return org
