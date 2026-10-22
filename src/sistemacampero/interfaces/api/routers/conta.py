"""Conta: perfil do usuário e criação da primeira organização."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from sistemacampero.domain.tenancy import Papel
from sistemacampero.interfaces.api.deps import ContainerDep, OrganizacaoDep, PrincipalDep

router = APIRouter(tags=["conta"])


class VinculoOut(BaseModel):
    organizacao_id: UUID
    nome: str
    slug: str
    papel: Papel


class MeOut(BaseModel):
    usuario_id: UUID
    email: str | None
    organizacoes: list[VinculoOut]


class OrganizacaoIn(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    slug: str | None = Field(default=None, min_length=3, max_length=60)


class OrganizacaoOut(BaseModel):
    id: UUID
    nome: str
    slug: str
    fuso: str
    papel: Papel


class OrganizacaoAtivaOut(BaseModel):
    organizacao_id: UUID
    papel: Papel


@router.get("/me", response_model=MeOut)
def me(c: ContainerDep, quem: PrincipalDep) -> MeOut:
    perfil = c.tenancy.perfil(quem)
    return MeOut(
        usuario_id=quem.usuario_id,
        email=quem.email,
        organizacoes=[
            VinculoOut(
                organizacao_id=v.organizacao_id,
                nome=v.organizacao_nome,
                slug=v.organizacao_slug,
                papel=v.papel,
            )
            for v in perfil.vinculos
        ],
    )


@router.post("/organizacoes", response_model=OrganizacaoOut, status_code=status.HTTP_201_CREATED)
def criar_organizacao(c: ContainerDep, quem: PrincipalDep, corpo: OrganizacaoIn) -> OrganizacaoOut:
    org = c.tenancy.criar_primeira_organizacao(quem, corpo.nome, corpo.slug)
    return OrganizacaoOut(id=org.id, nome=org.nome, slug=org.slug, fuso=org.fuso, papel=Papel.OWNER)


@router.get("/organizacao-ativa", response_model=OrganizacaoAtivaOut)
def organizacao_ativa(ctx: OrganizacaoDep) -> OrganizacaoAtivaOut:
    """Qual organização e papel valem para esta requisição (útil para o frontend)."""
    return OrganizacaoAtivaOut(organizacao_id=ctx.organizacao_id, papel=ctx.papel)
