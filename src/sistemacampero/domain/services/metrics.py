"""Métricas por sessão (combustível, horas, distância, área estimada, L/ha).

Entrada: amostras LIMPAS (sanitizadas, ``engine_on`` booleano). Os nomes dos campos
são os da tabela ``metricas_sessao``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

VELOCIDADE_TRABALHO_KMH = 1.0  # abaixo disso, com motor ligado = parado (ociosidade)
AREA_MINIMA_HA = 0.05  # não calcula L/ha nem ha/h com área menor que isso
HORAS_MINIMAS = 0.01  # ~36 s: abaixo disso razões (L/h, km/h) não fazem sentido


@dataclass(frozen=True, slots=True)
class MetricasSessao:
    duracao_h: float
    motor_h: float
    trabalho_h: float
    ocioso_h: float
    ociosidade_pct: float | None
    delta_horimetro_h: float | None
    litros_integral: float | None  # integral da vazão com motor ligado
    litros_contador: float | None  # diferença do contador acumulado do motor
    litros_trabalho: float | None
    litros_ocioso: float | None
    lph_trabalho: float | None
    lph_ocioso: float | None
    distancia_trabalho_km: float
    velocidade_media: float | None
    area_estimada_ha: float | None  # distância x largura do implemento
    area_cobertura_ha: float | None  # união das faixas trabalhadas (recortada pelo talhão)
    sobreposicao_pct: float | None
    area_metodo: str | None  # cobertura | estimada (a usada em ha/h e L/ha)
    ha_h: float | None
    l_ha: float | None
    cobertura_gps: float  # fração das amostras com motor ligado que têm posição

    def como_dict(self) -> dict[str, Any]:
        return asdict(self)


def _diferenca(serie: pd.Series) -> float | None:
    s = serie.dropna()
    return float(s.iloc[-1] - s.iloc[0]) if len(s) >= 2 else None


def _razao(a: float | None, b: float | None, minimo: float = HORAS_MINIMAS) -> float | None:
    if a is None or b is None or b < minimo:
        return None
    return a / b


def calcular_metricas(
    limpo: pd.DataFrame,
    largura_m: float | None,
    area_cobertura_ha: float | None = None,
    sobreposicao_pct: float | None = None,
) -> MetricasSessao | None:
    """Com cobertura (trilha GPS), ha/h e L/ha usam a área coberta; senão, a estimada."""
    if limpo.empty:
        return None
    ligado = limpo["engine_on"].astype(bool)
    velocidade = limpo["speed_kmh"]
    vazao = limpo["fuel_rate_lph"]
    andando = ligado & (velocidade >= VELOCIDADE_TRABALHO_KMH)
    parado = ligado & (velocidade < VELOCIDADE_TRABALHO_KMH)

    def horas(mascara: pd.Series) -> float:
        return float(mascara.sum()) / 3600.0

    def litros(mascara: pd.Series) -> float | None:
        v = vazao[mascara]
        return float(v.fillna(0).sum()) / 3600.0 if v.notna().any() else None

    motor_h, trabalho_h, ocioso_h = horas(ligado), horas(andando), horas(parado)
    l_int, l_trab, l_ocio = litros(ligado), litros(andando), litros(parado)
    distancia = float(velocidade[andando].fillna(0).sum()) / 3600.0
    estimada = distancia * largura_m / 10.0 if largura_m and distancia > 0 else None  # ha
    if estimada is not None and estimada < AREA_MINIMA_HA:
        estimada = None
    base_gps = limpo["gps_valid"][ligado] if ligado.any() else limpo["gps_valid"]
    area = area_cobertura_ha if area_cobertura_ha is not None else estimada
    metodo = "cobertura" if area_cobertura_ha is not None else ("estimada" if estimada else None)

    return MetricasSessao(
        duracao_h=len(limpo) / 3600.0,
        motor_h=motor_h,
        trabalho_h=trabalho_h,
        ocioso_h=ocioso_h,
        ociosidade_pct=100 * ocioso_h / motor_h if motor_h >= HORAS_MINIMAS else None,
        delta_horimetro_h=_diferenca(limpo["engine_hours"]),
        litros_integral=l_int,
        litros_contador=_diferenca(limpo["fuel_total_l"]),
        litros_trabalho=l_trab,
        litros_ocioso=l_ocio,
        lph_trabalho=_razao(l_trab, trabalho_h),
        lph_ocioso=_razao(l_ocio, ocioso_h),
        distancia_trabalho_km=distancia,
        velocidade_media=_razao(distancia, trabalho_h),
        area_estimada_ha=estimada,
        area_cobertura_ha=area_cobertura_ha,
        sobreposicao_pct=sobreposicao_pct,
        area_metodo=metodo,
        ha_h=_razao(area, trabalho_h),
        l_ha=_razao(l_int, area, AREA_MINIMA_HA),
        cobertura_gps=float(base_gps.mean()) if len(base_gps) else 0.0,
    )
