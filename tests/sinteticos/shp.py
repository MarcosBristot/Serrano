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


def polilinhas_shp(*linhas: list[tuple[float, float]]) -> bytes:
    """Um registro tipo 3 (PolyLine) por linha, como as cabeceiras e linhas-guia do OMNI."""
    pts = [p for linha in linhas for p in linha]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    bbox = struct.pack("<4d", min(xs), min(ys), max(xs), max(ys))
    registros = b""
    for n, linha in enumerate(linhas, start=1):
        conteudo = (
            struct.pack("<i", 3)
            + bbox
            + struct.pack("<2i", 1, len(linha))
            + struct.pack("<i", 0)
            + b"".join(struct.pack("<2d", *p) for p in linha)
        )
        registros += struct.pack(">2i", n, len(conteudo) // 2) + conteudo
    total = 100 + len(registros)
    cabecalho = (
        struct.pack(">i", 9994)
        + b"\0" * 20
        + struct.pack(">i", total // 2)
        + struct.pack("<2i", 1000, 3)
        + bbox
        + b"\0" * 32
    )
    return cabecalho + registros


def dbf(campos: list[tuple[str, str, int]], linhas: list[list[str]]) -> bytes:
    """dBase III mínimo: campos (nome, tipo C/N, largura) e valores como texto."""
    cab = 32 + 32 * len(campos) + 1
    tam = 1 + sum(c[2] for c in campos)
    saida = struct.pack("<4BIHH20x", 3, 126, 1, 1, len(linhas), cab, tam)
    for nome, tipo, largura in campos:
        saida += nome.encode().ljust(11, b"\0") + tipo.encode() + b"\0" * 4
        saida += bytes([largura, 0]) + b"\0" * 14
    saida += b"\r"
    for valores in linhas:
        saida += b" " + b"".join(
            v.encode("latin-1").ljust(c[2])[: c[2]] for v, c in zip(valores, campos, strict=True)
        )
    return saida + b"\x1a"
