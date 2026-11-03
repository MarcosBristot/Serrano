"""Contornos de talhão em shapefile (ESRI .shp), como os do controlador OMNI do pulverizador.

O OMNI grava uma pasta por talhão (``Data/<Cliente>/<Talhão>/``) com ``_perimeter.shp``
(polígono do talhão), ``_headland``, ``_runline`` e ``_feature``. Só o perímetro vira contorno.
Leitura sem dependências além do shapely: o formato é público (ESRI Shapefile Technical
Description, 1998) e o polígono é uma lista de anéis.
"""

from __future__ import annotations

import struct
import unicodedata
from typing import Any

import shapely
from shapely.geometry import MultiPolygon, Polygon

from sistemacampero.domain.errors import Invalido

_POLIGONOS = {5, 15, 25}  # Polygon, PolygonZ, PolygonM (Z/M são ignorados)


def _projecao_ok(prj: bytes | None) -> bool:
    """Aceita só coordenadas geográficas WGS 84 (graus), que é o que o OMNI grava."""
    if prj is None:
        return True  # sem .prj: o formato do OMNI é sempre WGS 84; a faixa de valores é checada
    texto = prj.decode("latin-1").upper()
    return texto.startswith("GEOGCS") and "WGS" in texto and "84" in texto


def ler_perimetro(shp: bytes, prj: bytes | None = None) -> MultiPolygon:
    """Lê todos os polígonos do .shp e devolve um MultiPolygon válido (EPSG:4326)."""
    if len(shp) < 100 or struct.unpack(">i", shp[0:4])[0] != 9994:
        raise Invalido("Arquivo .shp inválido.", codigo="SHP_INVALIDO")
    if not _projecao_ok(prj):
        raise Invalido(
            "Contorno em projeção não suportada (esperado WGS 84 em graus).",
            codigo="SHP_PROJECAO",
        )
    tipo = struct.unpack("<i", shp[32:36])[0]
    if tipo not in _POLIGONOS:
        raise Invalido("O .shp não contém polígonos.", codigo="SHP_SEM_POLIGONO")

    aneis: list[list[tuple[float, float]]] = []
    i = 100
    while i + 8 <= len(shp):
        tam = struct.unpack(">i", shp[i + 4 : i + 8])[0] * 2  # em palavras de 16 bits
        reg = shp[i + 8 : i + 8 + tam]
        i += 8 + tam
        if len(reg) < 44 or struct.unpack("<i", reg[0:4])[0] not in _POLIGONOS:
            continue  # registro nulo
        n_partes, n_pontos = struct.unpack("<2i", reg[36:44])
        partes = list(struct.unpack(f"<{n_partes}i", reg[44 : 44 + 4 * n_partes]))
        base = 44 + 4 * n_partes
        pts = [
            struct.unpack("<2d", reg[base + 16 * k : base + 16 * k + 16]) for k in range(n_pontos)
        ]
        for a, b in zip(partes, [*partes[1:], n_pontos], strict=True):
            if b - a >= 4:
                aneis.append(pts[a:b])

    for anel in aneis:
        for lon, lat in anel:
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise Invalido("Coordenadas fora de graus WGS 84.", codigo="SHP_PROJECAO")

    # A especificação diz "externo horário, furo anti-horário", mas o OMNI grava o contrário e
    # ainda repete o perímetro quando o operador regrava o talhão. Por isso a montagem é por
    # contenção, do maior anel para o menor: dentro de outro e bem menor = furo; dentro e quase
    # do mesmo tamanho = regravação (descartada); fora de todos = outro polígono.
    candidatos = sorted(
        (p for p in (shapely.make_valid(Polygon(a)) for a in aneis) if p.area > 0),
        key=lambda p: p.area,
        reverse=True,
    )
    aceitos: list[Any] = []  # Polygon ou, após um furo, MultiPolygon
    for p in candidatos:
        ponto = p.representative_point()
        dono = next((k for k, q in enumerate(aceitos) if q.contains(ponto)), None)
        if dono is None:
            aceitos.append(p)
        elif p.area < 0.8 * aceitos[dono].area:
            aceitos[dono] = aceitos[dono].difference(p)
    partes = [g for a in aceitos for g in getattr(a, "geoms", [a]) if isinstance(g, Polygon)]
    if not partes or max(p.area for p in partes) <= 0:
        raise Invalido("O .shp não tem polígono válido.", codigo="SHP_SEM_POLIGONO")
    # Regravações parciais deixam fiapos e furinhos: some o que tem menos de 1% da maior parte.
    minimo = max(p.area for p in partes) * 0.01
    limpas = [
        Polygon(p.exterior, [f for f in p.interiors if Polygon(f).area >= minimo])
        for p in partes
        if p.area >= minimo
    ]
    return MultiPolygon(limpas)


def nome_normalizado(nome: str) -> str:
    """'Mãe', 'Mae' e 'MAE' são o mesmo talhão; 'Paulo 3,7' = 'Paulo3-7'."""
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return "".join(c for c in sem_acento.lower() if c.isalnum())
