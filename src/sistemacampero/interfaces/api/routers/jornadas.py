"""Jornadas: a operação como o produtor entende (os arquivos do monitor agrupados)."""

from __future__ import annotations

import base64
from datetime import date, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from sistemacampero.application.kpis import ServicoKpis
from sistemacampero.domain.errors import Invalido
from sistemacampero.domain.tenancy import ContextoOrganizacao, Permissao
from sistemacampero.interfaces.api.deps import ContainerDep, exigir

router = APIRouter(prefix="/jornadas", tags=["jornadas"])
LerDep = Annotated[ContextoOrganizacao, Depends(exigir(Permissao.LER))]


def _servico(c: ContainerDep) -> ServicoKpis:
    assert c.kpis is not None
    return c.kpis


ServicoDep = Annotated[ServicoKpis, Depends(_servico)]


class JornadaOut(BaseModel):
    id: UUID
    maquina_id: UUID
    serial: str
    apelido: str | None
    inicio: datetime
    fim: datetime
    talhao_id: UUID | None
    talhao_nome: str | None
    talhoes: int
    operacao: str | None
    arquivos: int
    motor_h: float
    trabalho_h: float
    ocioso_h: float
    litros: float
    litros_trabalho: float
    litros_ocioso: float
    area_ha: float
    distancia_km: float
    l_ha: float | None
    ha_h: float | None
    ociosidade_pct: float | None
    custo_rs: float | None
    curta: bool


class ArquivoDaJornada(BaseModel):
    id: UUID
    inicio: datetime
    fim: datetime
    n_amostras: int
    qualidade_score: int | None
    motor_h: float | None
    litros_integral: float | None


class JornadaDetalheOut(JornadaOut):
    arquivos_detalhe: list[ArquivoDaJornada]


class PaginaJornadas(BaseModel):
    itens: list[JornadaOut]
    next_cursor: str | None


def _cursor(valor: str | None) -> tuple[str, UUID] | None:
    if not valor:
        return None
    try:
        ts, ident = base64.urlsafe_b64decode(valor.encode()).decode().split("|")
        return ts, UUID(ident)
    except (ValueError, UnicodeDecodeError):
        raise Invalido("Cursor inválido.", codigo="CURSOR_INVALIDO") from None


@router.get("", response_model=PaginaJornadas)
def listar(
    servico: ServicoDep,
    ctx: LerDep,
    inicio: date | None = None,
    fim: date | None = None,
    maquina_id: UUID | None = None,
    talhao_id: UUID | None = None,
    curtas: bool = Query(False, description="incluir jornadas de segundos (liga/desliga)"),
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    cursor: str | None = None,
) -> PaginaJornadas:
    filtros = {"inicio": inicio, "fim": fim, "maquina_id": maquina_id, "talhao_id": talhao_id}
    linhas = servico.jornadas(ctx.organizacao_id, filtros, limit + 1, _cursor(cursor), curtas)
    proximo = None
    if len(linhas) > limit:
        ultimo = linhas[limit - 1]
        proximo = base64.urlsafe_b64encode(
            f"{ultimo['inicio'].isoformat()}|{ultimo['id']}".encode()
        ).decode()
        linhas = linhas[:limit]
    return PaginaJornadas(itens=[JornadaOut.model_validate(x) for x in linhas], next_cursor=proximo)


@router.get("/{jornada_id}", response_model=JornadaDetalheOut)
def obter(servico: ServicoDep, ctx: LerDep, jornada_id: UUID) -> dict[str, Any]:
    return servico.jornada(ctx.organizacao_id, jornada_id)


@router.get("/{jornada_id}/track")
def trajeto(
    servico: ServicoDep,
    ctx: LerDep,
    jornada_id: UUID,
    max_pontos: Annotated[int, Query(ge=50, le=20000)] = 3000,
) -> dict[str, Any]:
    """GeoJSON da jornada inteira (todos os arquivos), como o trajeto de uma sessão."""
    return servico.trajeto_jornada(ctx.organizacao_id, jornada_id, max_pontos)
