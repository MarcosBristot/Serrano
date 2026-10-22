"""KPIs, mapas, preço do combustível e rotas legadas ``/telemetry/*``."""

from __future__ import annotations

import base64
from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from sistemacampero.application.kpis import Filtros, ServicoKpis
from sistemacampero.domain.errors import Invalido, NaoEncontrado
from sistemacampero.domain.tenancy import ContextoOrganizacao, Permissao
from sistemacampero.infrastructure.persistence.kpis import PostgresConsultasKpi
from sistemacampero.interfaces.api.deps import ContainerDep, exigir

router = APIRouter(tags=["kpis"])
legado = APIRouter(prefix="/telemetry", tags=["telemetria (contrato legado)"])

LerDep = Annotated[ContextoOrganizacao, Depends(exigir(Permissao.LER))]
OperarDep = Annotated[ContextoOrganizacao, Depends(exigir(Permissao.OPERAR))]


def _servico(c: ContainerDep) -> ServicoKpis:
    assert c.kpis is not None
    return c.kpis


def _consultas(c: ContainerDep) -> PostgresConsultasKpi:
    assert c.consultas_kpi is not None
    return c.consultas_kpi


KpiDep = Annotated[ServicoKpis, Depends(_servico)]
ConsultasDep = Annotated[PostgresConsultasKpi, Depends(_consultas)]


def filtros(
    inicio: Annotated[date | None, Query(description="dia local, inclusivo")] = None,
    fim: Annotated[date | None, Query(description="dia local, inclusivo")] = None,
    maquina_id: UUID | None = None,
    talhao_id: UUID | None = None,
    operacao: str | None = None,
) -> Filtros:
    return Filtros(inicio, fim, maquina_id, talhao_id, operacao)


FiltrosDep = Annotated[Filtros, Depends(filtros)]


class IndicadoresOut(BaseModel):
    motor_h: float
    trabalho_h: float
    ocioso_h: float
    ociosidade_pct: float | None
    litros: float
    litros_trabalho: float
    litros_ocioso: float
    area_ha: float
    distancia_km: float
    l_ha: float | None
    ha_h: float | None
    lph_trabalho: float | None
    lph_ocioso: float | None
    custo_rs: float | None = Field(description="litros x preço vigente em cada dia")
    custo_ocioso_rs: float | None
    rs_ha: float | None
    rs_h: float | None


class ResumoOut(IndicadoresOut):
    sessoes: int
    maquinas: int
    primeiro_dia: date | None
    ultimo_dia: date | None
    dias_sem_preco: int


class PontoSerieOut(IndicadoresOut):
    periodo: date | datetime


class ItemRankingOut(IndicadoresOut):
    id: str | None
    nome: str
    sessoes: int


class SafraOut(IndicadoresOut):
    safra: str
    inicio: date
    fim: date


@router.get("/kpis/resumo", response_model=ResumoOut)
def resumo(s: KpiDep, ctx: LerDep, f: FiltrosDep) -> dict[str, Any]:
    return s.resumo(ctx.organizacao_id, f)


@router.get("/kpis/series", response_model=list[PontoSerieOut])
def series(
    s: KpiDep,
    ctx: LerDep,
    f: FiltrosDep,
    granularidade: Literal["hora", "dia", "semana", "mes"] = "dia",
) -> list[dict[str, Any]]:
    return s.serie(ctx.organizacao_id, f, granularidade)


@router.get("/kpis/ranking", response_model=list[ItemRankingOut])
def ranking(
    s: KpiDep, ctx: LerDep, f: FiltrosDep, por: Literal["maquina", "talhao", "operacao"] = "maquina"
) -> list[dict[str, Any]]:
    return s.ranking(ctx.organizacao_id, f, por)


@router.get("/kpis/safras", response_model=list[SafraOut])
def safras(
    s: KpiDep,
    ctx: LerDep,
    f: FiltrosDep,
    comparar: Annotated[str | None, Query(examples=["2025/26,2026/27"])] = None,
) -> list[dict[str, Any]]:
    lista = [x.strip() for x in comparar.split(",") if x.strip()] if comparar else None
    return s.safras(ctx.organizacao_id, f, lista)


@router.get("/mapas/calor", summary="Grade hexagonal de L/ha (GeoJSON)")
def mapa_calor(
    s: KpiDep, ctx: LerDep, f: FiltrosDep, tamanho_m: Annotated[float, Query(ge=10, le=2000)] = 50
) -> dict[str, Any]:
    return s.mapa_calor(ctx.organizacao_id, f, tamanho_m)


@router.get("/sessions/{sessao_id}/track", summary="Trajeto decimado da sessão (GeoJSON)")
def trajeto(
    s: KpiDep,
    ctx: LerDep,
    sessao_id: UUID,
    max_pontos: Annotated[int, Query(ge=100, le=20000)] = 2000,
) -> dict[str, Any]:
    return s.trajeto(ctx.organizacao_id, sessao_id, max_pontos)


# ------------------------------------------------------------------ preços
class PrecoIn(BaseModel):
    tipo: Literal["S10", "S500"] = "S10"
    preco_rs_l: float = Field(gt=0, lt=100)
    valido_de: date


class PrecoPatch(BaseModel):
    preco_rs_l: float = Field(gt=0, lt=100)


class PrecoOut(BaseModel):
    id: UUID
    tipo: str
    preco_rs_l: float
    valido_de: date
    valido_ate: date | None
    fonte: str
    criado_em: datetime


@router.get("/precos-combustivel", response_model=list[PrecoOut], tags=["combustível"])
def listar_precos(q: ConsultasDep, ctx: LerDep) -> list[dict[str, Any]]:
    return q.precos(ctx.organizacao_id)


@router.post("/precos-combustivel", response_model=PrecoOut, status_code=201, tags=["combustível"])
def novo_preco(q: ConsultasDep, ctx: OperarDep, corpo: PrecoIn) -> dict[str, Any]:
    """Preço a partir de uma data (o anterior é encerrado nela). Preferir o preço da nota."""
    return q.novo_preco(ctx.organizacao_id, corpo.tipo, corpo.preco_rs_l, corpo.valido_de, "manual")


@router.patch("/precos-combustivel/{preco_id}", response_model=PrecoOut, tags=["combustível"])
def corrigir_preco(
    q: ConsultasDep, ctx: OperarDep, preco_id: UUID, corpo: PrecoPatch
) -> dict[str, Any]:
    linha = q.corrigir_preco(ctx.organizacao_id, preco_id, corpo.preco_rs_l)
    if linha is None:
        raise NaoEncontrado("Preço não encontrado.")
    return linha


# ------------------------------------------------------------------ legado
class TelemetryPoint(BaseModel):
    """Contrato antigo do frontend (ponto do trajeto)."""

    timestamp: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    speed_kmh: float | None = None
    fuel_rate_lph: float | None = None
    engine_rpm: float | None = None
    engine_on: bool = False


@legado.get("/machine/{machine_serial}", response_model=list[TelemetryPoint])
def machine_telemetry(
    q: ConsultasDep,
    ctx: LerDep,
    response: Response,
    machine_serial: str,
    talhao_id: UUID | None = None,
    inicio: datetime | None = None,
    fim: datetime | None = None,
    passo_s: Annotated[int, Query(ge=1, le=3600)] = 1,
    limit: Annotated[int, Query(ge=1, le=20000)] = 1000,
    cursor: str | None = None,
) -> list[dict[str, Any]]:
    """Pontos com GPS em ordem cronológica. Mais páginas: cabeçalho ``X-Next-Cursor``."""
    apos = None
    if cursor:
        try:
            apos = datetime.fromisoformat(base64.urlsafe_b64decode(cursor.encode()).decode())
        except (ValueError, UnicodeDecodeError):
            raise Invalido("Cursor inválido.", codigo="CURSOR_INVALIDO") from None
    linhas = q.pontos_maquina(
        ctx.organizacao_id, machine_serial, talhao_id, inicio, fim, passo_s, limit + 1, apos
    )
    if linhas is None or (not linhas and cursor is None):
        raise NaoEncontrado("Sem dados geográficos para esta máquina.", codigo="SEM_DADOS")
    if len(linhas) > limit:
        linhas = linhas[:limit]
        response.headers["X-Next-Cursor"] = base64.urlsafe_b64encode(
            linhas[-1]["ts"].isoformat().encode()
        ).decode()
    return [
        {
            "timestamp": x["ts"].isoformat(),
            "latitude": x["lat"],
            "longitude": x["lon"],
            "speed_kmh": x["speed_kmh"],
            "fuel_rate_lph": x["fuel_rate_lph"],
            "engine_rpm": x["engine_rpm"],
            "engine_on": bool(x["engine_on"]),
        }
        for x in linhas
    ]


@legado.get("/stats/{machine_serial}")
def machine_stats(
    s: KpiDep, q: ConsultasDep, ctx: LerDep, machine_serial: str, f: FiltrosDep
) -> dict[str, Any]:
    """KPIs consolidados da máquina (chaves do contrato antigo)."""
    maquina = q.maquina_por_serial(ctx.organizacao_id, machine_serial)
    if maquina is None:
        raise NaoEncontrado("Sem dados para estatísticas.", codigo="SEM_DADOS")
    filtro = Filtros(f.inicio, f.fim, maquina, f.talhao_id, f.operacao)
    r = s.resumo(ctx.organizacao_id, filtro)
    if not r["sessoes"]:
        raise NaoEncontrado("Sem dados para estatísticas.", codigo="SEM_DADOS")

    def arred(v: float | None, casas: int) -> float | None:
        return None if v is None else round(v, casas)

    return {
        "machine_serial": machine_serial,
        "sessoes": r["sessoes"],
        "horas_motor": round(r["motor_h"], 2),
        "horas_trabalho": round(r["trabalho_h"], 2),
        "horas_ociosas": round(r["ocioso_h"], 2),
        "percentual_ociosidade": arred(r["ociosidade_pct"], 2) or 0.0,
        "litros_total": round(r["litros"], 1),
        "consumo_medio_lph": arred(r["lph_trabalho"], 2) or 0.0,
        "area_trabalhada_ha": round(r["area_ha"], 1),
        "litros_por_ha": arred(r["l_ha"], 2),
        "custo_rs": arred(r["custo_rs"], 2),
        "rs_por_ha": arred(r["rs_ha"], 2),
    }
