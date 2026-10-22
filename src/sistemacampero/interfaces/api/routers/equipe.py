"""Equipe: membros e papéis, convites, chaves de API e auditoria."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, EmailStr, Field

from sistemacampero.domain.errors import Invalido
from sistemacampero.domain.tenancy import ContextoOrganizacao, Papel, Permissao
from sistemacampero.infrastructure.persistence.equipe import PostgresRepositorioEquipe
from sistemacampero.interfaces.api.deps import ContainerDep, PrincipalDep, exigir

router = APIRouter(tags=["equipe"])

LerDep = Annotated[ContextoOrganizacao, Depends(exigir(Permissao.LER))]
AdminDep = Annotated[ContextoOrganizacao, Depends(exigir(Permissao.ADMINISTRAR))]


def _repo(c: ContainerDep) -> PostgresRepositorioEquipe:
    assert c.repo_equipe is not None
    return c.repo_equipe


RepoDep = Annotated[PostgresRepositorioEquipe, Depends(_repo)]


class MembroOut(BaseModel):
    usuario_id: UUID
    email: str | None
    papel: str
    criado_em: datetime


class PapelIn(BaseModel):
    papel: Literal["owner", "gestor", "leitor"]


class ConviteIn(BaseModel):
    email: EmailStr
    papel: Literal["gestor", "leitor"] = "leitor"


class ConviteOut(BaseModel):
    id: UUID
    email: str
    papel: str
    expira_em: datetime
    aceito_em: datetime | None
    criado_em: datetime


class ConviteCriadoOut(ConviteOut):
    token: str = Field(description="Mostrado só agora; o link de aceite usa este token")
    email_enviado: bool


class ChaveIn(BaseModel):
    nome: str = Field(min_length=1, max_length=100)
    escopos: list[Literal["ler", "operar"]] = Field(default=["ler"], min_length=1)


class ChaveOut(BaseModel):
    id: UUID
    nome: str
    prefixo: str
    escopos: list[str]
    criado_em: datetime
    ultimo_uso_em: datetime | None
    revogada_em: datetime | None


class ChaveCriadaOut(ChaveOut):
    chave: str = Field(
        description="Mostrada só agora. Use em 'X-API-Key' ou 'Authorization: Bearer'"
    )


class AuditoriaOut(BaseModel):
    id: int
    ator_id: UUID | None
    ator_tipo: str
    acao: str
    recurso_tipo: str | None
    recurso_id: str | None
    dados: dict[str, Any]
    ip: str | None
    request_id: str | None
    criado_em: datetime


@router.get("/membros", response_model=list[MembroOut])
def membros(repo: RepoDep, ctx: LerDep) -> list[dict[str, Any]]:
    return repo.membros(ctx.organizacao_id)


@router.patch("/membros/{usuario_id}", response_model=list[MembroOut])
def mudar_papel(
    repo: RepoDep, ctx: AdminDep, usuario_id: UUID, corpo: PapelIn
) -> list[dict[str, Any]]:
    repo.mudar_papel(ctx.organizacao_id, usuario_id, corpo.papel)
    return repo.membros(ctx.organizacao_id)


@router.delete("/membros/{usuario_id}", status_code=204)
def remover(repo: RepoDep, ctx: AdminDep, usuario_id: UUID) -> Response:
    repo.mudar_papel(ctx.organizacao_id, usuario_id, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/convites", response_model=ConviteCriadoOut, status_code=201)
def convidar(c: ContainerDep, ctx: AdminDep, corpo: ConviteIn) -> dict[str, Any]:
    assert c.equipe is not None
    convite, token, enviado = c.equipe.convidar(ctx, corpo.email, Papel(corpo.papel))
    return {**convite, "token": token, "email_enviado": enviado}


@router.get("/convites", response_model=list[ConviteOut])
def convites(repo: RepoDep, ctx: AdminDep) -> list[dict[str, Any]]:
    return repo.convites(ctx.organizacao_id)


@router.delete("/convites/{convite_id}", status_code=204)
def revogar_convite(repo: RepoDep, ctx: AdminDep, convite_id: UUID) -> Response:
    repo.revogar_convite(ctx.organizacao_id, convite_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/convites/{token}/aceitar")
def aceitar(c: ContainerDep, quem: PrincipalDep, token: str) -> dict[str, str]:
    """O usuário logado (mesmo e-mail do convite) entra na organização."""
    if len(token) > 200:
        raise Invalido("Convite inválido.", codigo="CONVITE_INVALIDO")
    assert c.equipe is not None
    return {"organizacao_id": str(c.equipe.aceitar(quem, token))}


@router.post("/chaves-api", response_model=ChaveCriadaOut, status_code=201)
def criar_chave(c: ContainerDep, ctx: AdminDep, corpo: ChaveIn) -> dict[str, Any]:
    """Para integrações (ex.: upload automático). A chave fica na organização."""
    assert c.equipe is not None
    chave, token = c.equipe.criar_chave(ctx, corpo.nome, list(corpo.escopos))
    return {**chave, "chave": token}


@router.get("/chaves-api", response_model=list[ChaveOut])
def chaves(repo: RepoDep, ctx: AdminDep) -> list[dict[str, Any]]:
    return repo.chaves(ctx.organizacao_id)


@router.delete("/chaves-api/{chave_id}", status_code=204)
def revogar_chave(repo: RepoDep, ctx: AdminDep, chave_id: UUID) -> Response:
    repo.revogar_chave(ctx.organizacao_id, chave_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/auditoria", response_model=list[AuditoriaOut])
def auditoria(
    repo: RepoDep,
    ctx: AdminDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    antes_de: int | None = None,
) -> list[dict[str, Any]]:
    return repo.auditoria(ctx.organizacao_id, limit, antes_de)
