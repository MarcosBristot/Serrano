"""Cálculos geográficos simples (a localização de talhão e a cobertura entram no M4)."""

from __future__ import annotations

import numpy as np

RAIO_TERRA_M = 6_371_000.0


def distancias_m(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Distância (haversine) entre pontos consecutivos, em metros (len - 1 valores)."""
    p = np.radians(np.asarray(lat, dtype=np.float64))
    lam = np.radians(np.asarray(lon, dtype=np.float64))
    dphi, dlam = np.diff(p), np.diff(lam)
    h = np.sin(dphi / 2) ** 2 + np.cos(p[:-1]) * np.cos(p[1:]) * np.sin(dlam / 2) ** 2
    resultado: np.ndarray = 2 * RAIO_TERRA_M * np.arcsin(np.sqrt(np.clip(h, 0.0, 1.0)))
    return resultado
