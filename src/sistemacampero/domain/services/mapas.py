"""Geometrias para o mapa: trajeto da sessão (decimado) e mapa de calor hexagonal de L/ha."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon, mapping

from sistemacampero.domain.services.coverage import zona_utm
from sistemacampero.domain.services.metrics import VELOCIDADE_TRABALHO_KMH

LACUNA_TRAJETO_S = 5
PARADA_MIN_S = 120


def _transformadores(lat: np.ndarray, lon: np.ndarray) -> tuple[Transformer, Transformer]:
    crs = zona_utm(float(np.nanmedian(lon)), float(np.nanmedian(lat)))
    return (
        Transformer.from_crs(4326, crs, always_xy=True),
        Transformer.from_crs(crs, 4326, always_xy=True),
    )


def _estado(df: pd.DataFrame) -> np.ndarray:
    ligado = df["engine_on"].fillna(False).astype(bool).to_numpy()
    andando = (df["speed_kmh"].fillna(0) >= VELOCIDADE_TRABALHO_KMH).to_numpy()
    return np.where(ligado & andando, "trabalho", np.where(ligado, "parado", "desligado"))


def trajeto(df: pd.DataFrame, max_pontos: int = 2000) -> dict[str, Any]:
    """FeatureCollection: linhas por estado (trabalho/parado) e paradas longas como pontos.

    ``df``: ts, lat, lon, speed_kmh, engine_on (1 Hz, só pontos com posição). A linha é
    simplificada (Douglas-Peucker em UTM) até caber em ``max_pontos`` vértices.
    """
    vazio: dict[str, Any] = {"type": "FeatureCollection", "features": []}
    df = df.dropna(subset=["lat", "lon"]).reset_index(drop=True)
    if len(df) < 2:
        return vazio
    lat, lon = df["lat"].to_numpy(), df["lon"].to_numpy()
    ida, volta = _transformadores(lat, lon)
    x, y = ida.transform(lon, lat)
    ts = pd.to_datetime(df["ts"], utc=True)
    segundos = (ts - ts.iloc[0]).dt.total_seconds().to_numpy(dtype=np.float64)
    estado = _estado(df)

    quebra = np.r_[False, (np.diff(segundos) > LACUNA_TRAJETO_S) | (estado[1:] != estado[:-1])]
    grupos = np.cumsum(quebra)
    trechos: list[tuple[str, np.ndarray]] = []
    paradas: list[dict[str, Any]] = []
    for g in np.unique(grupos):
        idx = np.flatnonzero(grupos == g)
        tipo = str(estado[idx[0]])
        duracao = segundos[idx[-1]] - segundos[idx[0]]
        if tipo != "trabalho" and duracao >= PARADA_MIN_S:
            px, py = volta.transform(float(np.mean(x[idx])), float(np.mean(y[idx])))
            paradas.append(
                {
                    "type": "Feature",
                    "geometry": mapping(Point(round(px, 7), round(py, 7))),
                    "properties": {
                        "tipo": "parada",
                        "motor_ligado": tipo == "parado",
                        "inicio": ts.iloc[idx[0]].isoformat(),
                        "fim": ts.iloc[idx[-1]].isoformat(),
                        "minutos": round(duracao / 60, 1),
                    },
                }
            )
        # Mantém continuidade entre trechos: começa no último ponto do anterior.
        if idx[0] > 0 and not (segundos[idx[0]] - segundos[idx[0] - 1] > LACUNA_TRAJETO_S):
            idx = np.r_[idx[0] - 1, idx]
        if len(idx) >= 2:
            trechos.append((tipo, idx))

    tolerancia = 0.5
    while True:
        linhas = [
            (tipo, idx, LineString(np.column_stack([x[idx], y[idx]])).simplify(tolerancia))
            for tipo, idx in trechos
        ]
        total = sum(len(linha.coords) for _, _, linha in linhas)
        if total <= max_pontos or tolerancia > 500:
            break
        tolerancia *= 2

    feats = []
    for tipo, idx, linha in linhas:
        cx, cy = np.asarray(linha.coords).T
        lo, la = volta.transform(cx, cy)
        feats.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [round(a, 7), round(b, 7)] for a, b in zip(lo, la, strict=True)
                    ],
                },
                "properties": {
                    "tipo": tipo,
                    "inicio": ts.iloc[idx[0]].isoformat(),
                    "fim": ts.iloc[idx[-1]].isoformat(),
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "features": feats + paradas,
        "properties": {"pontos_originais": len(df), "tolerancia_m": tolerancia},
    }


def mapa_de_calor(
    df: pd.DataFrame, tamanho_m: float = 50.0, area_minima_ha: float = 0.01
) -> dict[str, Any]:
    """Grade hexagonal de L/ha.

    ``df``: pontos de trabalho a 1 Hz (lat, lon, speed_kmh, fuel_rate_lph, largura_m; área
    do ponto = velocidade x 1 s x largura) OU células já agregadas (lat, lon, litros,
    area_ha). Cada hexágono soma litros e área e devolve L/ha.
    ``tamanho_m`` = distância entre lados opostos do hexágono.
    """
    vazio: dict[str, Any] = {"type": "FeatureCollection", "features": []}
    if "area_ha" not in df:
        df = df.dropna(subset=["lat", "lon", "speed_kmh", "largura_m"])
        df = df[(df["speed_kmh"] >= VELOCIDADE_TRABALHO_KMH) & (df["largura_m"] > 0)]
        df = df.assign(
            litros=df["fuel_rate_lph"].fillna(0) / 3600,
            area_ha=df["speed_kmh"] / 3.6 * df["largura_m"] / 10_000,
        )
    df = df.dropna(subset=["lat", "lon", "area_ha"])
    if df.empty:
        return vazio
    lat, lon = df["lat"].to_numpy(), df["lon"].to_numpy()
    ida, volta = _transformadores(lat, lon)
    x, y = ida.transform(lon, lat)
    raio = tamanho_m / math.sqrt(3)  # do centro ao vértice (hexágono "pointy-top")
    q = (math.sqrt(3) / 3 * x - y / 3) / raio
    r = (2 / 3 * y) / raio
    # arredondamento cúbico
    cx, cz = q, r
    cy = -cx - cz
    rx, ry, rz = np.round(cx), np.round(cy), np.round(cz)
    dx, dy, dz = np.abs(rx - cx), np.abs(ry - cy), np.abs(rz - cz)
    ajusta_x = (dx > dy) & (dx > dz)
    ajusta_y = ~ajusta_x & (dy > dz)
    rx = np.where(ajusta_x, -ry - rz, rx)
    ry = np.where(ajusta_y, -rx - rz, ry)
    rz = np.where(~ajusta_x & ~ajusta_y, -rx - ry, rz)

    agg = (
        pd.DataFrame(
            {
                "q": rx.astype(np.int64),
                "r": rz.astype(np.int64),
                "litros": df["litros"].fillna(0).to_numpy(),
                "area_ha": df["area_ha"].to_numpy(),
            }
        )
        .groupby(["q", "r"], as_index=False)
        .agg(litros=("litros", "sum"), area_ha=("area_ha", "sum"), pontos=("litros", "size"))
    )
    agg = agg[agg["area_ha"] >= area_minima_ha]
    feats: list[dict[str, Any]] = []
    valores: list[float] = []
    angulos = np.radians(np.arange(6) * 60 + 30)
    colunas = (agg[c].to_numpy() for c in ("q", "r", "litros", "area_ha", "pontos"))
    for hq, hr, litros, area, pontos in zip(*colunas, strict=True):
        centro_x = raio * math.sqrt(3) * (float(hq) + float(hr) / 2)
        centro_y = raio * 1.5 * float(hr)
        vx, vy = centro_x + raio * np.cos(angulos), centro_y + raio * np.sin(angulos)
        lo, la = volta.transform(vx, vy)
        anel = [[round(a, 7), round(b, 7)] for a, b in zip(lo, la, strict=True)]
        l_ha = round(float(litros) / float(area), 2)
        valores.append(l_ha)
        feats.append(
            {
                "type": "Feature",
                "geometry": mapping(Polygon([*anel, anel[0]])),
                "properties": {
                    "l_ha": l_ha,
                    "litros": round(float(litros), 3),
                    "area_ha": round(float(area), 4),
                    "pontos": int(pontos),
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "features": feats,
        "properties": {
            "tamanho_m": tamanho_m,
            "l_ha_p10": float(np.percentile(valores, 10)) if valores else None,
            "l_ha_p50": float(np.percentile(valores, 50)) if valores else None,
            "l_ha_p90": float(np.percentile(valores, 90)) if valores else None,
        },
    }
