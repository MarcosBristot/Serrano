"""Serviços geoespaciais do domínio: localização de talhão por ponto (junção espacial)."""

from __future__ import annotations

from collections import Counter
from math import asin, cos, radians, sin, sqrt

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape
from shapely.strtree import STRtree

from sistemacampero.domain.entities import FieldBoundary


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distância em metros entre dois pontos (lat, lon)."""
    earth_radius_m = 6_371_000.0
    p1, p2 = radians(a[0]), radians(b[0])
    dphi, dlam = p2 - p1, radians(b[1] - a[1])
    h = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlam / 2) ** 2
    return 2 * earth_radius_m * asin(sqrt(h))


class FieldLocator:
    """Associa coordenadas a talhões em memória (índice espacial STRtree).

    Substitui uma consulta RPC por ponto: os contornos são carregados uma vez por
    processamento e a junção é vetorizada.
    """

    def __init__(self, fields: list[FieldBoundary]) -> None:
        self._fields = fields
        self._geoms = [shape(f.geometry) for f in fields]
        self._tree = STRtree(self._geoms) if self._geoms else None

    @property
    def fields(self) -> list[FieldBoundary]:
        return self._fields

    def locate(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        """Índice do talhão de cada ponto (-1 = fora de todos ou sem posição)."""
        lat = np.asarray(lat, dtype="float64")
        lon = np.asarray(lon, dtype="float64")
        out = np.full(len(lat), -1, dtype=np.int64)
        if self._tree is None or not len(lat):
            return out
        valid = np.isfinite(lat) & np.isfinite(lon)
        if not valid.any():
            return out
        idx = np.flatnonzero(valid)
        points = shapely.points(lon[idx], lat[idx])
        hits = self._tree.query(points, predicate="within")
        # primeiro talhão que contém o ponto
        for point_i, tree_i in zip(hits[0][::-1], hits[1][::-1], strict=True):
            out[idx[point_i]] = tree_i
        return out

    def dominant_field(self, samples: pd.DataFrame) -> FieldBoundary | None:
        """Talhão onde ocorreu a maior parte das amostras com posição."""
        located = self.locate(samples["lat"].to_numpy(), samples["lon"].to_numpy())
        found = located[located >= 0]
        if not len(found):
            return None
        idx, _ = Counter(found.tolist()).most_common(1)[0]
        return self._fields[idx]

    def field_ids(self, lat: np.ndarray, lon: np.ndarray) -> list[str | None]:
        """Id do talhão por ponto (``None`` fora dos talhões)."""
        return [self._fields[i].id if i >= 0 else None for i in self.locate(lat, lon)]
