"""Shapefile sintético de polígono (ESRI .shp), no formato que o OMNI grava."""

from __future__ import annotations

import struct

PRJ_WGS84 = (
    b'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137,298.257223563]],'
    b'PRIMEM["Greenwich",0],UNIT["Degree",0.017453292519943295]]'
)
PRJ_UTM = b'PROJCS["SIRGAS_2000_UTM_Zone_22S",GEOGCS["GCS_SIRGAS_2000"]]'


def poligono_shp(*aneis: list[tuple[float, float]]) -> bytes:
    """Um registro tipo 5 (Polygon) com uma parte por anel, na ordem dada."""
    pts = [p for a in aneis for p in a]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    bbox = struct.pack("<4d", min(xs), min(ys), max(xs), max(ys))
    partes, k = [], 0
    for a in aneis:
        partes.append(k)
        k += len(a)
    conteudo = (
        struct.pack("<i", 5)
        + bbox
        + struct.pack("<2i", len(aneis), len(pts))
        + struct.pack(f"<{len(partes)}i", *partes)
        + b"".join(struct.pack("<2d", *p) for p in pts)
    )
    registro = struct.pack(">2i", 1, len(conteudo) // 2) + conteudo
    total = 100 + len(registro)
    cabecalho = (
        struct.pack(">i", 9994)
        + b"\0" * 20
        + struct.pack(">i", total // 2)
        + struct.pack("<2i", 1000, 5)
        + bbox
        + b"\0" * 32
    )
    return cabecalho + registro


def quadrado(
    lon: float, lat: float, lado: float, anti_horario: bool = True
) -> list[tuple[float, float]]:
    anel = [(lon, lat), (lon + lado, lat), (lon + lado, lat + lado), (lon, lat + lado), (lon, lat)]
    return anel if anti_horario else anel[::-1]
