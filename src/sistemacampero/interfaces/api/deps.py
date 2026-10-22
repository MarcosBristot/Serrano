"""Dependências do FastAPI: container, usuário autenticado e organização ativa."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from sistemacampero.domain.errors import Invalido, NaoAutenticado
from sistemacampero.domain.tenancy import ContextoOrganizacao, Permissao, Principal
from sistemacampero.infrastructure.container import Container

_bearer = HTTPBearer(auto_error=False, description="JWT do Supabase Auth")


def container(request: Request) -> Container:
    c: Container = request.app.state.container
    return c


ContainerDep = Annotated[Container, Depends(container)]


def principal(
    c: ContainerDep,
    credenciais: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    if credenciais is None or credenciais.scheme.lower() != "bearer":
        raise NaoAutenticado("Envie 'Authorization: Bearer <token>'.")
    usuario_id, email = c.verificador_token.verificar(credenciais.credentials)
    return Principal(usuario_id=usuario_id, email=email)


PrincipalDep = Annotated[Principal, Depends(principal)]


def organizacao(
    c: ContainerDep,
    quem: PrincipalDep,
    x_organizacao_id: Annotated[str | None, Header()] = None,
) -> ContextoOrganizacao:
    org_id: UUID | None = None
    if x_organizacao_id:
        try:
            org_id = UUID(x_organizacao_id)
        except ValueError:
            raise Invalido(
                "X-Organizacao-Id deve ser um UUID.", codigo="ORGANIZACAO_INVALIDA"
            ) from None
    return c.tenancy.resolver_organizacao(quem, org_id)


OrganizacaoDep = Annotated[ContextoOrganizacao, Depends(organizacao)]


def exigir(permissao: Permissao):  # type: ignore[no-untyped-def]
    """Uso: ``ctx: Annotated[ContextoOrganizacao, Depends(exigir(Permissao.OPERAR))]``."""

    def _dep(ctx: OrganizacaoDep) -> ContextoOrganizacao:
        ctx.exigir(permissao)
        return ctx

    return _dep
