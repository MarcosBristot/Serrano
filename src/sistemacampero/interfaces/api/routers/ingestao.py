"""Ingestão: upload (contrato preservado), lotes, jobs e arquivos."""

from __future__ import annotations

import base64
import shutil
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

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
    arquivo: str  # contrato antigo
    marca: str | None
    tecnologia: str | None


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
    arquivo: Annotated[
        UploadFile | None, File(description=".jdl ou .zip da pasta do monitor")
    ] = None,
    file: Annotated[UploadFile | None, File(description="nome antigo do campo")] = None,
    marca: Annotated[str | None, Query(examples=["john_deere"])] = None,
    tecnologia: Annotated[str | None, Query(examples=["gen4"])] = None,
    lote_id: UUID | None = None,
) -> UploadOut:
    assert c.ingestao is not None
    enviado = arquivo or file
    if enviado is None:
        raise Invalido("Envie o arquivo no campo 'arquivo' (ou 'file').", codigo="SEM_ARQUIVO")
    if (
        lote_id is not None
        and c.repo_ingestao is not None
        and c.repo_ingestao.obter_lote(ctx.organizacao_id, lote_id) is None
    ):
        raise NaoEncontrado("Lote não encontrado.", codigo="LOTE_NAO_ENCONTRADO")
    r = c.ingestao.receber(
        ctx.organizacao_id,
        enviado.filename or "arquivo",
        enviado.file,
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
        arquivo=enviado.filename or "arquivo",
        marca=marca,
        tecnologia=tecnologia,
    )


# ----------------------------------------------------------------- upload em partes
# A Cloudflare (plano grátis) recusa corpo acima de 100 MB por requisição. Pendrive grande
# vai em partes de até TAMANHO_PARTE: inicia, envia cada parte em ordem e conclui; a API
# junta as partes num arquivo temporário e segue o mesmo caminho do upload simples.

TAMANHO_PARTE = 64 * 1024**2  # o painel manda 32 MB; folga para outros clientes
_VALIDADE_PARTES = timedelta(hours=24)
_PASTA_PARTES = Path(tempfile.gettempdir()) / "serrano-partes"


class InicioPartesIn(BaseModel):
    nome: str = Field(min_length=1, max_length=255)
    tamanho: int = Field(gt=0)


class InicioPartesOut(BaseModel):
    upload_id: UUID
    tamanho_parte: int


class ParteOut(BaseModel):
    recebido: int


def _pasta_upload(organizacao_id: UUID, upload_id: UUID) -> Path:
    pasta = _PASTA_PARTES / str(organizacao_id) / str(upload_id)
    if not pasta.is_dir():
        raise NaoEncontrado(
            "Envio não encontrado ou expirado. Comece de novo.", codigo="ENVIO_NAO_ENCONTRADO"
        )
    return pasta


def _limpar_antigos() -> None:
    """Envios abandonados há mais de 24 h (aba fechada no meio, internet caiu)."""
    limite = (datetime.now(UTC) - _VALIDADE_PARTES).timestamp()
    for pasta in _PASTA_PARTES.glob("*/*"):
        try:
            if pasta.stat().st_mtime < limite:
                shutil.rmtree(pasta, ignore_errors=True)
        except OSError:
            pass


@router.post(
    "/telemetry/upload/partes",
    response_model=InicioPartesOut,
    status_code=status.HTTP_201_CREATED,
    summary="Inicia um envio em partes (arquivos grandes)",
)
def iniciar_partes(c: ContainerDep, ctx: OperarDep, corpo: InicioPartesIn) -> InicioPartesOut:
    maximo = c.settings.max_upload_mb * 1024**2
    if corpo.tamanho > maximo:
        raise Invalido(
            f"Arquivo maior que o limite de {c.settings.max_upload_mb} MB.", codigo="ARQUIVO_GRANDE"
        )
    _limpar_antigos()
    upload_id = uuid4()
    pasta = _PASTA_PARTES / str(ctx.organizacao_id) / str(upload_id)
    pasta.mkdir(parents=True)
    (pasta / "nome").write_text(corpo.nome, encoding="utf-8")
    (pasta / "tamanho").write_text(str(corpo.tamanho), encoding="ascii")
    (pasta / "arquivo").touch()
    return InicioPartesOut(upload_id=upload_id, tamanho_parte=TAMANHO_PARTE)


@router.put(
    "/telemetry/upload/partes/{upload_id}/{indice}",
    response_model=ParteOut,
    summary="Envia a parte `indice` (0, 1, 2…) em ordem; reenviar a última é aceito",
)
async def enviar_parte(
    c: ContainerDep, ctx: OperarDep, upload_id: UUID, indice: int, request: Request
) -> ParteOut:
    pasta = _pasta_upload(ctx.organizacao_id, upload_id)
    destino = pasta / "arquivo"
    marcas = pasta / "partes"
    recebidas = int(marcas.read_text()) if marcas.exists() else 0
    tamanho_total = int((pasta / "tamanho").read_text())
    if indice < recebidas:  # reenvio de uma parte já gravada (a resposta se perdeu)
        return ParteOut(recebido=destino.stat().st_size)
    if indice != recebidas:
        raise Invalido(
            f"Parte fora de ordem: esperava a {recebidas}.", codigo="PARTE_FORA_DE_ORDEM"
        )

    inicio = destino.stat().st_size
    escritos = 0
    with destino.open("ab") as f:
        async for bloco in request.stream():
            escritos += len(bloco)
            if escritos > TAMANHO_PARTE or inicio + escritos > tamanho_total:
                f.truncate(inicio)
                raise Invalido("Parte maior que o permitido.", codigo="PARTE_GRANDE")
            await run_in_threadpool(f.write, bloco)
    if escritos == 0:
        raise Invalido("Parte vazia.", codigo="PARTE_VAZIA")
    marcas.write_text(str(recebidas + 1))
    return ParteOut(recebido=inicio + escritos)


@router.post(
    "/telemetry/upload/partes/{upload_id}/concluir",
    response_model=UploadOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Junta as partes e processa como um upload comum",
)
def concluir_partes(
    c: ContainerDep,
    ctx: OperarDep,
    upload_id: UUID,
    marca: Annotated[str | None, Query(examples=["john_deere"])] = None,
    tecnologia: Annotated[str | None, Query(examples=["gen4"])] = None,
    lote_id: UUID | None = None,
) -> UploadOut:
    assert c.ingestao is not None
    pasta = _pasta_upload(ctx.organizacao_id, upload_id)
    nome = (pasta / "nome").read_text(encoding="utf-8")
    esperado = int((pasta / "tamanho").read_text())
    if (pasta / "arquivo").stat().st_size != esperado:
        raise Invalido("Faltam partes do arquivo. Envie de novo.", codigo="ENVIO_INCOMPLETO")
    if (
        lote_id is not None
        and c.repo_ingestao is not None
        and c.repo_ingestao.obter_lote(ctx.organizacao_id, lote_id) is None
    ):
        raise NaoEncontrado("Lote não encontrado.", codigo="LOTE_NAO_ENCONTRADO")
    try:
        with (pasta / "arquivo").open("rb") as f:
            r = c.ingestao.receber(
                ctx.organizacao_id, nome, f, marca=marca, tecnologia=tecnologia, lote_id=lote_id
            )
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    return UploadOut(
        job_id=r.job_id,
        arquivo_id=r.arquivo_id,
        duplicado=r.duplicado,
        status=r.status.value,
        sha256=r.sha256,
        tipo=r.tipo.value,
        arquivo=nome,
        marca=marca,
        tecnologia=tecnologia,
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
