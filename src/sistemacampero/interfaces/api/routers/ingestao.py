"""Ingestão: upload (contrato preservado), lotes, jobs e arquivos."""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from sistemacampero.domain.errors import Invalido, NaoEncontrado
from sistemacampero.domain.tenancy import ContextoOrganizacao, Permissao
from sistemacampero.interfaces.api.deps import ContainerDep, OrganizacaoDep, exigir

router = APIRouter(tags=["ingestão"])

OperarDep = Annotated[ContextoOrganizacao, Depends(exigir(Permissao.OPERAR))]
AdministrarDep = Annotated[ContextoOrganizacao, Depends(exigir(Permissao.ADMINISTRAR))]


class UploadOut(BaseModel):
    job_id: UUID | None
    arquivo_id: UUID
    duplicado: bool
    status: str
    sha256: str
    tipo: str


class LoteOut(BaseModel):
    lote_id: UUID


class LoteStatusOut(BaseModel):
    id: UUID
    origem: str
    criado_em: datetime
    arquivos: int
    processados: int
    vazios: int
    com_erro: int
    bloqueados: int
    pendentes: int


class JobOut(BaseModel):
    id: UUID
    tipo: str
    status: str
    tentativas: int
    max_tentativas: int
    progresso: dict[str, Any]
    erro: str | None
    arquivo_id: UUID | None
    lote_id: UUID | None
    criado_em: datetime | None
    atualizado_em: datetime | None


class ArquivoOut(BaseModel):
    id: UUID
    lote_id: UUID | None
    arquivo_pai_id: UUID | None
    sha256: str
    nome_original: str
    tamanho_bytes: int
    tipo: str
    marca: str | None
    tecnologia: str | None
    status: str
    motivo: str | None
    criado_em: datetime
    atualizado_em: datetime


class PaginaArquivos(BaseModel):
    itens: list[ArquivoOut]
    next_cursor: str | None


class CancelamentoOut(BaseModel):
    job_id: UUID
    status: str


def _cursor(valor: str | None) -> tuple[str, UUID] | None:
    if not valor:
        return None
    try:
        ts, ident = base64.urlsafe_b64decode(valor.encode()).decode().split("|")
        return ts, UUID(ident)
    except (ValueError, UnicodeDecodeError):
        raise Invalido("Cursor inválido.", codigo="CURSOR_INVALIDO") from None


@router.post(
    "/telemetry/upload",
    response_model=UploadOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Envia UM arquivo (.jdl ou .zip do pendrive); o processamento é assíncrono",
)
def upload(
    c: ContainerDep,
    ctx: OperarDep,
    arquivo: Annotated[UploadFile, File(description=".jdl ou .zip da pasta do monitor")],
    marca: Annotated[str | None, Query(examples=["john_deere"])] = None,
    tecnologia: Annotated[str | None, Query(examples=["gen4"])] = None,
    lote_id: UUID | None = None,
) -> UploadOut:
    assert c.ingestao is not None
    if (
        lote_id is not None
        and c.repo_ingestao is not None
        and c.repo_ingestao.obter_lote(ctx.organizacao_id, lote_id) is None
    ):
        raise NaoEncontrado("Lote não encontrado.", codigo="LOTE_NAO_ENCONTRADO")
    r = c.ingestao.receber(
        ctx.organizacao_id,
        arquivo.filename or "arquivo",
        arquivo.file,
        marca=marca,
        tecnologia=tecnologia,
        lote_id=lote_id,
    )
    return UploadOut(
        job_id=r.job_id,
        arquivo_id=r.arquivo_id,
        duplicado=r.duplicado,
        status=r.status.value,
        sha256=r.sha256,
        tipo=r.tipo.value,
    )


@router.post("/batches", response_model=LoteOut, status_code=status.HTTP_201_CREATED)
def criar_lote(c: ContainerDep, ctx: OperarDep) -> LoteOut:
    """Agrupa vários uploads (o frontend envia um arquivo por chamada, em paralelo)."""
    assert c.repo_ingestao is not None
    return LoteOut(lote_id=c.repo_ingestao.criar_lote(ctx.organizacao_id, None, "api"))


@router.get("/batches/{lote_id}", response_model=LoteStatusOut)
def status_lote(c: ContainerDep, ctx: OrganizacaoDep, lote_id: UUID) -> LoteStatusOut:
    assert c.repo_ingestao is not None
    linha = c.repo_ingestao.obter_lote(ctx.organizacao_id, lote_id)
    if linha is None:
        raise NaoEncontrado("Lote não encontrado.", codigo="LOTE_NAO_ENCONTRADO")
    return LoteStatusOut.model_validate(linha)


@router.get("/jobs/{job_id}", response_model=JobOut)
def situacao_job(c: ContainerDep, ctx: OrganizacaoDep, job_id: UUID) -> JobOut:
    assert c.fila is not None
    s = c.fila.situacao(ctx.organizacao_id, job_id)
    if s is None:
        raise NaoEncontrado("Job não encontrado.", codigo="JOB_NAO_ENCONTRADO")
    return JobOut.model_validate(s, from_attributes=True)


@router.post("/jobs/{job_id}/cancelar", response_model=CancelamentoOut)
def cancelar_job(c: ContainerDep, ctx: OperarDep, job_id: UUID) -> CancelamentoOut:
    assert c.fila is not None
    novo = c.fila.solicitar_cancelamento(ctx.organizacao_id, job_id)
    if novo is None:
        raise NaoEncontrado("Job não encontrado.", codigo="JOB_NAO_ENCONTRADO")
    return CancelamentoOut(job_id=job_id, status=novo)


@router.get("/arquivos", response_model=PaginaArquivos)
async def listar_arquivos(
    c: ContainerDep,
    ctx: OrganizacaoDep,
    status_: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    cursor: str | None = None,
) -> PaginaArquivos:
    assert c.repo_ingestao is not None
    linhas = await run_in_threadpool(
        c.repo_ingestao.listar_arquivos, ctx.organizacao_id, status_, limit + 1, _cursor(cursor)
    )
    proximo = None
    if len(linhas) > limit:
        ultimo = linhas[limit - 1]
        bruto = f"{ultimo['criado_em'].isoformat()}|{ultimo['id']}"
        proximo = base64.urlsafe_b64encode(bruto.encode()).decode()
        linhas = linhas[:limit]
    return PaginaArquivos(itens=[ArquivoOut.model_validate(x) for x in linhas], next_cursor=proximo)


# ------------------------------------------------------------------- admin
admin = APIRouter(prefix="/admin", tags=["admin"])


@admin.get("/jobs", response_model=list[JobOut])
def jobs_admin(
    c: ContainerDep,
    ctx: AdministrarDep,
    status_: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[JobOut]:
    assert c.fila is not None
    out = []
    for linha in c.fila.listar(ctx.organizacao_id, status_, limit):
        arquivo = (linha["payload"] or {}).get("arquivo_id")
        out.append(
            JobOut(
                **{
                    k: linha[k]
                    for k in (
                        "id",
                        "tipo",
                        "status",
                        "tentativas",
                        "max_tentativas",
                        "erro",
                        "criado_em",
                        "atualizado_em",
                    )
                },
                progresso={},
                arquivo_id=UUID(arquivo) if arquivo else None,
                lote_id=None,
            )
        )
    return out


@admin.post("/jobs/{job_id}/reenfileirar", response_model=CancelamentoOut)
def reenfileirar(c: ContainerDep, ctx: AdministrarDep, job_id: UUID) -> CancelamentoOut:
    assert c.fila is not None
    if not c.fila.reenfileirar(ctx.organizacao_id, job_id):
        raise Invalido(
            "Só jobs mortos, com erro ou cancelados podem ser reenfileirados.",
            codigo="JOB_NAO_REENFILEIRAVEL",
        )
    return CancelamentoOut(job_id=job_id, status="pendente")


@admin.post("/reabrir-bloqueados")
def reabrir_bloqueados(c: ContainerDep, ctx: AdministrarDep) -> dict[str, int]:
    """Depois de upgrade do plano ou de desativar máquina: reprocessa os bloqueados."""
    assert c.repo_ingestao is not None
    return {"reenfileirados": c.repo_ingestao.reabrir_bloqueados(ctx.organizacao_id)}
