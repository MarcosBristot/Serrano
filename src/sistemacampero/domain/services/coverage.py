"""Área trabalhada por cobertura geométrica.

Cada trecho contínuo de trabalho (motor ligado, velocidade de trabalho, com posição e
sem salto) vira uma linha em UTM, com buffer de meia largura do implemento (pontas
retas). A união dá a área efetivamente coberta; sobrepor passadas não conta duas vezes.

A área da sessão é a cobertura TOTAL: um arquivo do monitor costuma atravessar mais de
um talhão (no pendrive de 2026, 22% do trabalho das sessões localizadas ficou fora do
talhão principal). Recortar pelo talhão principal subestimaria a área e inflaria o L/ha.
Com talhão, ``dentro_do_talhao_ha`` informa quanto caiu dentro do contorno.

Comparação com a área estimada (distância x largura): ``sobreposicao_pct`` é quanto da
faixa percorrida caiu em área já coberta (passes repetidos, manobras sobre o já feito).

Limite conhecido: sem o sinal de implemento levantado/abaixado, manobras de cabeceira e
deslocamentos em estrada com motor ligado entram na cobertura (ver ADR 0007).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import shapely
from pyproj import CRS, Transformer
from shapely.geometry import LineString, MultiPolygon
from shapely.geometry.base import BaseGeometry

from sistemacampero.domain.services.geo import distancias_m, poligonos
from sistemacampero.domain.services.metrics import VELOCIDADE_TRABALHO_KMH

LACUNA_MAX_S = 3  # buraco de posição maior que isso quebra o trecho
SALTO_MAX_M = 30.0  # entre amostras de 1 s, mais que isso é salto (108 km/h)
SIMPLIFICACAO_M = 0.25  # simplifica a linha antes do buffer (precisão de GPS RTK ~2 cm)
SIMPLIFICACAO_SAIDA_M = 0.5  # geometria guardada para o mapa
AREA_MINIMA_HA = 0.05


@dataclass(frozen=True, slots=True)
class Cobertura:
    area_ha: float  # área coberta (união das faixas)
    area_bruta_ha: float  # comprimento dos trechos x largura
    sobreposicao_pct: float
    dentro_do_talhao_ha: float | None  # parte da cobertura dentro do talhão da sessão
    geometria: MultiPolygon  # WGS84, simplificada (para o mapa)


def zona_utm(lon: float, lat: float) -> CRS:
    zona = int((lon + 180) // 6) + 1
    return CRS.from_epsg((32700 if lat < 0 else 32600) + zona)


def _reprojetar(geom: BaseGeometry, t: Transformer) -> BaseGeometry:
    def aplicar(coords: np.ndarray) -> np.ndarray:
        x, y = t.transform(coords[:, 0], coords[:, 1])
        resultado: np.ndarray = np.column_stack([x, y])
        return resultado

    return shapely.transform(geom, aplicar)


def _trechos(df: pd.DataFrame) -> list[tuple[int, int]]:
    trabalho = (
        df["engine_on"].astype(bool)
        & (df["speed_kmh"] >= VELOCIDADE_TRABALHO_KMH)
        & df["gps_valid"].astype(bool)
        & df["lat"].notna()
    ).to_numpy()
    idx = np.flatnonzero(trabalho)
    if len(idx) < 2:
        return []
    lat, lon = df["lat"].to_numpy()[idx], df["lon"].to_numpy()[idx]
    quebra = (np.diff(idx) > LACUNA_MAX_S) | (distancias_m(lat, lon) > SALTO_MAX_M)
    inicios = np.r_[0, np.flatnonzero(quebra) + 1]
    fins = np.r_[np.flatnonzero(quebra), len(idx) - 1]
    return [(int(idx[a]), int(idx[b])) for a, b in zip(inicios, fins, strict=True) if b > a]


def calcular_cobertura(
    limpo: pd.DataFrame, largura_m: float | None, contorno: BaseGeometry | None = None
) -> Cobertura | None:
    if not largura_m or largura_m <= 0 or limpo.empty:
        return None
    trechos = _trechos(limpo)
    if not trechos:
        return None
    lat, lon = limpo["lat"].to_numpy(), limpo["lon"].to_numpy()
    crs = zona_utm(float(np.nanmedian(lon)), float(np.nanmedian(lat)))
    para_utm = Transformer.from_crs(4326, crs, always_xy=True)
    para_wgs = Transformer.from_crs(crs, 4326, always_xy=True)

    linhas = []
    comprimento = 0.0
    for a, b in trechos:
        x, y = para_utm.transform(lon[a : b + 1], lat[a : b + 1])
        linha = LineString(np.column_stack([x, y])).simplify(SIMPLIFICACAO_M)
        if linha.length > 0:
            linhas.append(linha)
            comprimento += linha.length
    if not linhas:
        return None
    faixas = shapely.buffer(np.array(linhas), largura_m / 2, cap_style="flat", join_style="round")
    coberto = shapely.union_all(faixas)
    area_total_m2 = coberto.area
    bruta_m2 = comprimento * largura_m
    dentro_ha = None
    if contorno is not None:
        dentro_ha = coberto.intersection(_reprojetar(contorno, para_utm)).area / 10_000
    area_ha = area_total_m2 / 10_000
    if area_ha < AREA_MINIMA_HA:
        return None
    saida = _reprojetar(coberto.simplify(SIMPLIFICACAO_SAIDA_M), para_wgs)
    return Cobertura(
        area_ha=area_ha,
        area_bruta_ha=bruta_m2 / 10_000,
        sobreposicao_pct=max(0.0, 100 * (1 - area_total_m2 / bruta_m2)) if bruta_m2 else 0.0,
        dentro_do_talhao_ha=dentro_ha,
        geometria=MultiPolygon(poligonos(saida)),
    )
