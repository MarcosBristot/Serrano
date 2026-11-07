"""Fechamento da safra por talhão (colheita + custo de máquina)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from sistemacampero.application.fechamento import ServicoFechamento
from sistemacampero.domain.tenancy import ContextoOrganizacao, Permissao
from sistemacampero.interfaces.api.deps import ContainerDep, exigir

router = APIRouter(prefix="/safras", tags=["safras"])
LerDep = Annotated[ContextoOrganizacao, Depends(exigir(Permissao.LER))]


def _servico(c: ContainerDep) -> ServicoFechamento:
    assert c.fechamento is not None
    return c.fechamento


ServicoDep = Annotated[ServicoFechamento, Depends(_servico)]


class SafraOut(BaseModel):
    safra: str
    cultura: str | None
    area_colhida_ha: float
    sacas: float
    sc_ha: float | None
    inicio: datetime
    fim: datetime


class OperacaoMaquina(BaseModel):
    operacao: str
    motor_h: float | None
    litros: float | None
    custo_rs: float | None
    maquinas: int


class TalhaoFechamento(BaseModel):
    talhao_id: UUID | None
    talhao_nome: str | None
    cultura: str | None
    variedades: list[str]
    area_talhao_ha: float | None
    area_colhida_ha: float
    sacas: float
    sc_ha: float | None
    vs_media_pct: float | None
    umidade_pct: float | None
    colheita_inicio: datetime
    colheita_fim: datetime
    janela_inicio: date
    motor_h: float
    litros: float
    custo_diesel_rs: float | None
    l_ha: float | None
    custo_diesel_ha: float | None
    custo_diesel_saca: float | None
    operacoes_maquina: list[OperacaoMaquina]


class FechamentoOut(BaseModel):
    safra: str
    cultura: str | None
    area_colhida_ha: float
    sacas: float
    sc_ha: float | None
    motor_h: float
    litros: float
    custo_diesel_rs: float | None
    custo_diesel_saca: float | None
    horas_ha: float | None
    talhoes: list[TalhaoFechamento]


@router.get("", response_model=list[SafraOut])
def listar(servico: ServicoDep, ctx: LerDep) -> list[dict[str, Any]]:
    """Safras com colheita registrada, da mais recente para a mais antiga."""
    return servico.safras(ctx.organizacao_id)


@router.get("/fechamento", response_model=FechamentoOut)
def fechamento(
    servico: ServicoDep,
    ctx: LerDep,
    safra: Annotated[str, Query(min_length=4, max_length=20)],
    cultura: str | None = None,
) -> dict[str, Any]:
    """Por talhão: sacas/ha secas, área colhida e o custo de máquina desde a colheita anterior."""
    return servico.fechamento(ctx.organizacao_id, safra, cultura)
