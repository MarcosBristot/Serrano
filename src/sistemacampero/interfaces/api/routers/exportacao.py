"""Exportação (CSV em streaming, CSV/XLSX assíncrono) e relatório de qualidade."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from sistemacampero.application.exportacao import ServicoExportacao
from sistemacampero.domain.tenancy import ContextoOrganizacao, Permissao
from sistemacampero.interfaces.api.deps import ContainerDep, exigir

router = APIRouter(tags=["exportação e qualidade"])

ExportarDep = Annotated[ContextoOrganizacao, Depends(exigir(Permissao.EXPORTAR))]
LerDep = Annotated[ContextoOrganizacao, Depends(exigir(Permissao.LER))]
Tipo = Literal["sessoes", "diarias", "alertas", "telemetria"]


def _servico(c: ContainerDep) -> ServicoExportacao:
    assert c.exportacao is not None
    return c.exportacao


ServicoDep = Annotated[ServicoExportacao, Depends(_servico)]


class ExportacaoIn(BaseModel):
    tipo: Tipo = "sessoes"
    formato: Literal["csv", "xlsx"] = "xlsx"
    inicio: date | None = None
    fim: date | None = None
    maquina_id: UUID | None = None
    talhao_id: UUID | None = None


class ExportacaoOut(BaseModel):
    id: UUID
    formato: str
    tipo: str
    filtros: dict[str, Any]
    status: str
    linhas: int | None
    expira_em: datetime | None
    erro: str | None
    criado_em: datetime
    url: str | None = None


def _f(
    inicio: date | None, fim: date | None, maquina_id: UUID | None, talhao_id: UUID | None
) -> dict[str, Any]:
    return {"inicio": inicio, "fim": fim, "maquina_id": maquina_id, "talhao_id": talhao_id}


@router.get("/exportacoes/csv", summary="CSV em streaming (volume pequeno/médio)")
def csv_direto(
    s: ServicoDep,
    ctx: ExportarDep,
    tipo: Tipo = "sessoes",
    inicio: date | None = None,
    fim: date | None = None,
    maquina_id: UUID | None = None,
    talhao_id: UUID | None = None,
    padrao: Literal["excel_br", "rfc4180"] = "excel_br",
) -> StreamingResponse:
    """``excel_br``: separador ';', vírgula decimal e BOM (abre direto no Excel em português)."""
    corpo = s.csv(
        ctx.organizacao_id, tipo, _f(inicio, fim, maquina_id, talhao_id), padrao == "excel_br"
    )
    nome = f"campero_{tipo}_{date.today().isoformat()}.csv"
    return StreamingResponse(
        corpo,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.post("/exportacoes", response_model=ExportacaoOut, status_code=202)
def solicitar(s: ServicoDep, ctx: ExportarDep, corpo: ExportacaoIn) -> dict[str, Any]:
    """Gera no worker e guarda por 7 dias; ``GET /exportacoes/{id}`` traz o link assinado."""
    ident = s.solicitar(
        ctx.organizacao_id,
        ctx.usuario_id,
        corpo.tipo,
        corpo.formato,
        _f(corpo.inicio, corpo.fim, corpo.maquina_id, corpo.talhao_id),
    )
    return s.situacao(ctx.organizacao_id, ident)


@router.get("/exportacoes/{ident}", response_model=ExportacaoOut)
def situacao(s: ServicoDep, ctx: ExportarDep, ident: UUID) -> dict[str, Any]:
    return s.situacao(ctx.organizacao_id, ident)


@router.get("/exportacoes", response_model=list[ExportacaoOut])
def listar(c: ContainerDep, ctx: ExportarDep) -> list[dict[str, Any]]:
    assert c.repo_exportacao is not None
    return c.repo_exportacao.listar(ctx.organizacao_id)


@router.get("/qualidade/relatorio", summary="Arquivos vazios, sem GPS, problemas, por máquina")
def relatorio(
    s: ServicoDep, ctx: LerDep, inicio: date | None = None, fim: date | None = None
) -> dict[str, Any]:
    return s.relatorio_qualidade(ctx.organizacao_id, inicio, fim)
