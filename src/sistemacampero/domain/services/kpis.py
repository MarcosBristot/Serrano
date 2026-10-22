"""Indicadores derivados (razões) a partir de somas, e safra agrícola.

As somas vêm de ``metricas_diarias``; as razões são calculadas aqui, uma vez, para todo
endpoint (resumo, série, ranking, safra) usar a mesma regra: razão sem base suficiente
é ``None``, nunca 0 nem infinito.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

HORAS_MINIMAS = 0.01
AREA_MINIMA_HA = 0.05


@dataclass(frozen=True, slots=True)
class Somas:
    motor_h: float = 0.0
    trabalho_h: float = 0.0
    ocioso_h: float = 0.0
    litros: float = 0.0
    litros_trabalho: float = 0.0
    litros_ocioso: float = 0.0
    area_ha: float = 0.0
    distancia_km: float = 0.0
    custo_rs: float | None = None  # litros x preço vigente em cada dia (None = sem preço)


@dataclass(frozen=True, slots=True)
class Indicadores:
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
    custo_rs: float | None
    custo_ocioso_rs: float | None
    rs_ha: float | None
    rs_h: float | None

    def como_dict(self) -> dict[str, Any]:
        return asdict(self)


def _div(a: float | None, b: float | None, minimo: float) -> float | None:
    if a is None or b is None or b < minimo:
        return None
    return a / b


def derivar(s: Somas) -> Indicadores:
    preco_medio = _div(s.custo_rs, s.litros, 1e-9)
    return Indicadores(
        motor_h=s.motor_h,
        trabalho_h=s.trabalho_h,
        ocioso_h=s.ocioso_h,
        ociosidade_pct=_div(100 * s.ocioso_h, s.motor_h, HORAS_MINIMAS),
        litros=s.litros,
        litros_trabalho=s.litros_trabalho,
        litros_ocioso=s.litros_ocioso,
        area_ha=s.area_ha,
        distancia_km=s.distancia_km,
        l_ha=_div(s.litros, s.area_ha, AREA_MINIMA_HA),
        ha_h=_div(s.area_ha, s.trabalho_h, HORAS_MINIMAS),
        lph_trabalho=_div(s.litros_trabalho, s.trabalho_h, HORAS_MINIMAS),
        lph_ocioso=_div(s.litros_ocioso, s.ocioso_h, HORAS_MINIMAS),
        custo_rs=s.custo_rs,
        custo_ocioso_rs=s.litros_ocioso * preco_medio if preco_medio is not None else None,
        rs_ha=_div(s.custo_rs, s.area_ha, AREA_MINIMA_HA),
        rs_h=_div(s.custo_rs, s.motor_h, HORAS_MINIMAS),
    )


def safra(dia: date, inicio_safra_mes: int = 7) -> str:
    """Safra agrícola: com início em julho, 15/08/2026 e 10/03/2027 são da safra 2026/27."""
    ano = dia.year if dia.month >= inicio_safra_mes else dia.year - 1
    return f"{ano}/{str(ano + 1)[-2:]}"


def intervalo_da_safra(rotulo: str, inicio_safra_mes: int = 7) -> tuple[date, date]:
    """'2026/27' -> [2026-07-01, 2027-07-01)."""
    try:
        ano = int(rotulo.split("/")[0])
    except (ValueError, IndexError):
        raise ValueError(f"safra inválida: {rotulo!r} (use '2026/27')") from None
    return date(ano, inicio_safra_mes, 1), date(ano + 1, inicio_safra_mes, 1)
