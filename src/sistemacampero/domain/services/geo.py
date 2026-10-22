"""Geografia do domínio: distâncias, contornos de talhão e localização de sessões.

A localização é feita em memória (STRtree) com os talhões da organização carregados uma
vez por job, em vez de uma consulta por ponto.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import numpy as np
import shapely
from pyproj import Geod
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree
from shapely.validation import make_valid

from sistemacampero.domain.errors import Invalido

RAIO_TERRA_M = 6_371_000.0
MAX_VERTICES = 100_000
_GEOD = Geod(ellps="WGS84")


def distancias_m(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Distância (haversine) entre pontos consecutivos, em metros (len - 1 valores)."""
    p = np.radians(np.asarray(lat, dtype=np.float64))
    lam = np.radians(np.asarray(lon, dtype=np.float64))
    dphi, dlam = np.diff(p), np.diff(lam)
    h = np.sin(dphi / 2) ** 2 + np.cos(p[:-1]) * np.cos(p[1:]) * np.sin(dlam / 2) ** 2
    resultado: np.ndarray = 2 * RAIO_TERRA_M * np.arcsin(np.sqrt(np.clip(h, 0.0, 1.0)))
    return resultado


def area_geodesica_ha(geom: BaseGeometry) -> float:
    return abs(_GEOD.geometry_area_perimeter(geom)[0]) / 10_000.0


def normalizar_contorno(geojson: dict[str, Any] | str) -> MultiPolygon:
    """GeoJSON (Polygon, MultiPolygon, Feature ou FeatureCollection) -> MultiPolygon válido.

    De uma FeatureCollection exportada pelo monitor Gen4, usa só ``boundarytype=Exterior``
    (as cabeceiras geradas pelo monitor não são o talhão).
    """
    dados = json.loads(geojson) if isinstance(geojson, str) else geojson
    if not isinstance(dados, dict):
        raise Invalido("GeoJSON inválido.", codigo="GEOMETRIA_INVALIDA")
    tipo = dados.get("type")
    if tipo == "FeatureCollection":
        feats = [f for f in dados.get("features", []) if isinstance(f, dict)]
        exteriores = [
            f for f in feats if (f.get("properties") or {}).get("boundarytype") == "Exterior"
        ]
        escolhidas = exteriores or feats
        geoms = [f.get("geometry") for f in escolhidas if f.get("geometry")]
    elif tipo == "Feature":
        geoms = [dados.get("geometry")]
    else:
        geoms = [dados]
    partes: list[Polygon] = []
    for g in geoms:
        if not isinstance(g, dict):
            raise Invalido("GeoJSON inválido.", codigo="GEOMETRIA_INVALIDA")
        try:
            geom = shape(g)
        except (AttributeError, TypeError, ValueError, shapely.errors.ShapelyError):
            raise Invalido("GeoJSON inválido.", codigo="GEOMETRIA_INVALIDA") from None
        if not geom.is_valid:
            geom = make_valid(geom)
        partes.extend(poligonos(geom))
    if not partes:
        raise Invalido("O contorno precisa ser um polígono.", codigo="GEOMETRIA_INVALIDA")
    multi = MultiPolygon(partes)
    if not multi.is_valid:
        multi = MultiPolygon(poligonos(make_valid(multi)))
    minx, miny, maxx, maxy = multi.bounds
    if not (-180 <= minx <= maxx <= 180 and -90 <= miny <= maxy <= 90):
        raise Invalido(
            "Coordenadas fora de WGS84 (use longitude, latitude em graus).",
            codigo="GEOMETRIA_INVALIDA",
        )
    if shapely.get_num_coordinates(multi) > MAX_VERTICES:
        raise Invalido("Contorno com vértices demais.", codigo="GEOMETRIA_INVALIDA")
    if area_geodesica_ha(multi) < 0.01:
        raise Invalido("Contorno com área desprezível.", codigo="GEOMETRIA_INVALIDA")
    return multi


def poligonos(geom: BaseGeometry) -> list[Polygon]:
    if isinstance(geom, Polygon):
        return [geom] if not geom.is_empty else []
    if hasattr(geom, "geoms"):
        return [p for g in geom.geoms for p in poligonos(g)]
    return []


def como_geojson(geom: BaseGeometry) -> dict[str, Any]:
    resultado: dict[str, Any] = mapping(geom)
    return resultado


@dataclass(frozen=True, slots=True)
class Contorno:
    talhao_id: UUID
    geometria: BaseGeometry  # WGS84 (lon, lat)
    fazenda_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class Localizacao:
    talhao_id: UUID | None
    confianca: float  # fração dos pontos de trabalho dentro do talhão escolhido
    por_ponto: list[UUID | None]  # talhão de cada amostra (None = fora/sem GPS)


class LocalizadorDeTalhoes:
    def __init__(self, contornos: list[Contorno]) -> None:
        self._contornos = [c for c in contornos if c.geometria is not None]
        geoms = [c.geometria for c in self._contornos]
        self._arvore = STRtree(geoms) if geoms else None

    @property
    def vazio(self) -> bool:
        return self._arvore is None

    def contorno(self, talhao_id: UUID) -> BaseGeometry | None:
        return next((c.geometria for c in self._contornos if c.talhao_id == talhao_id), None)

    def indices(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        """Índice do contorno que contém cada ponto (-1 = fora ou sem posição)."""
        lat = np.asarray(lat, dtype=np.float64)
        lon = np.asarray(lon, dtype=np.float64)
        out = np.full(len(lat), -1, dtype=np.int64)
        if self._arvore is None or not len(lat):
            return out
        validos = np.flatnonzero(np.isfinite(lat) & np.isfinite(lon))
        if not len(validos):
            return out
        pontos = shapely.points(lon[validos], lat[validos])
        pares = self._arvore.query(pontos, predicate="within")
        # Talhões sobrepostos: fica o de menor índice (determinístico).
        for i_ponto, i_contorno in sorted(zip(pares[0], pares[1], strict=True), reverse=True):
            out[validos[i_ponto]] = i_contorno
        return out

    def localizar(self, lat: np.ndarray, lon: np.ndarray, trabalho: np.ndarray) -> Localizacao:
        """Talhão da sessão = o que contém a maioria dos pontos DE TRABALHO com posição.

        ``confianca`` = fração desses pontos dentro do talhão escolhido. Sessão sem
        trabalho (só manobra/deslocamento) usa todos os pontos com posição.
        """
        lat = np.asarray(lat, dtype=np.float64)
        idx = self.indices(lat, lon)
        por_ponto = [self._contornos[i].talhao_id if i >= 0 else None for i in idx]
        com_posicao = np.isfinite(lat) & np.isfinite(np.asarray(lon, dtype=np.float64))
        base = idx[np.asarray(trabalho, dtype=bool) & com_posicao]
        if not len(base):
            base = idx[com_posicao]
        dentro = base[base >= 0]
        if not len(dentro):
            return Localizacao(None, 0.0, por_ponto)
        i, n = Counter(dentro.tolist()).most_common(1)[0]
        return Localizacao(self._contornos[i].talhao_id, round(n / len(base), 4), por_ponto)
