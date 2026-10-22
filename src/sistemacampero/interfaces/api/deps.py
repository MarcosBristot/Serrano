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
    request: Request,
    c: ContainerDep,
    credenciais: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    x_organizacao_id: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> ContextoOrganizacao:
    """JWT do usuário (org pelo header ou única) ou chave de API (org da chave)."""
    chave = x_api_key or (
        credenciais.credentials
        if credenciais and credenciais.credentials.startswith("cmp_")
        else None
    )
    if chave is not None:
        assert c.equipe is not None
        ctx = c.equipe.autenticar_chave(chave)
    else:
        quem = principal(c, credenciais)
        org_id: UUID | None = None
        if x_organizacao_id:
            try:
                org_id = UUID(x_organizacao_id)
            except ValueError:
                raise Invalido(
                    "X-Organizacao-Id deve ser um UUID.", codigo="ORGANIZACAO_INVALIDA"
                ) from None
        resolvido = c.tenancy.resolver_organizacao(quem, org_id)
        ctx = ContextoOrganizacao(
            resolvido.organizacao_id, resolvido.papel, usuario_id=quem.usuario_id
        )
    # Para a auditoria (middleware) saber quem fez o quê.
    request.state.organizacao_id = ctx.organizacao_id
    request.state.ator_id = ctx.usuario_id or ctx.chave_api_id
    request.state.ator_tipo = "chave_api" if ctx.chave_api_id else "usuario"
    return ctx


OrganizacaoDep = Annotated[ContextoOrganizacao, Depends(organizacao)]


def exigir(permissao: Permissao):  # type: ignore[no-untyped-def]
    """Uso: ``ctx: Annotated[ContextoOrganizacao, Depends(exigir(Permissao.OPERAR))]``."""

    def _dep(ctx: OrganizacaoDep) -> ContextoOrganizacao:
        ctx.exigir(permissao)
        return ctx

    return _dep
