"""Contornos de talhão em shapefile (ESRI .shp), como os do controlador OMNI do pulverizador.

O OMNI grava uma pasta por talhão (``Data/<Cliente>/<Talhão>/``) com ``_perimeter.shp``
(polígono do talhão), ``_headland`` (cabeceira), ``_runline`` (linhas-guia) e ``_feature``
(obstáculos). O perímetro vira contorno; cabeceira e linhas-guia viram camadas do mapa.
Leitura sem dependências além do shapely: o formato é público (ESRI Shapefile Technical
Description, 1998) e o polígono é uma lista de anéis.
"""

from __future__ import annotations

import struct
import unicodedata
from datetime import datetime
from typing import Any

import shapely
from shapely.geometry import LineString, MultiPolygon, Polygon

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


_LINHAS = {3, 13, 23}  # PolyLine, PolyLineZ, PolyLineM


def _registros_dbf(dbf: bytes | None) -> list[dict[str, str]]:
    """Tabela do .dbf (dBase III) como texto; registro apagado ('*') vira vazio."""
    if not dbf or len(dbf) < 32:
        return []
    n, cab, tam = struct.unpack("<IHH", dbf[4:12])
    campos: list[tuple[str, int]] = []
    for i in range(32, cab - 1, 32):
        campos.append((dbf[i : i + 11].split(b"\0")[0].decode("latin-1"), dbf[i + 16]))
    linhas = []
    for k in range(n):
        reg = dbf[cab + k * tam : cab + (k + 1) * tam]
        if len(reg) < tam:
            break
        pos, valores = 1, {}
        for nome, largura in campos:
            valores[nome] = reg[pos : pos + largura].decode("latin-1").strip()
            pos += largura
        linhas.append({} if reg[:1] == b"*" else valores)
    return linhas


def _data_omni(texto: str) -> datetime | None:
    try:
        return datetime.strptime(texto, "%Y/%m/%d %H:%M:%S")
    except ValueError:
        return None


def ler_linhas(shp: bytes, dbf: bytes | None, prj: bytes | None, tipo: str) -> list[dict[str, Any]]:
    """Cabeceira (``_headland``) ou linhas-guia (``_runline``) do OMNI, em WGS 84.

    O OMNI acrescenta um registro a cada regravação e o .dbf nem sempre acompanha: da
    cabeceira vale só o último registro com forma (3+ pontos); linhas-guia valem todas
    (``Type`` 1 = reta AB, 0 = curva). A data do .dbf é a hora local do controlador.
    """
    if len(shp) < 100 or struct.unpack(">i", shp[0:4])[0] != 9994:
        raise Invalido("Arquivo .shp inválido.", codigo="SHP_INVALIDO")
    if not _projecao_ok(prj):
        raise Invalido("Linhas em projeção não suportada.", codigo="SHP_PROJECAO")
    if struct.unpack("<i", shp[32:36])[0] not in _LINHAS:
        return []
    atributos = _registros_dbf(dbf)
    linhas: list[dict[str, Any]] = []
    i, k = 100, 0
    while i + 8 <= len(shp):
        tam = struct.unpack(">i", shp[i + 4 : i + 8])[0] * 2
        reg = shp[i + 8 : i + 8 + tam]
        i += 8 + tam
        attr = atributos[k] if k < len(atributos) else {}
        k += 1
        if len(reg) < 44 or struct.unpack("<i", reg[0:4])[0] not in _LINHAS:
            continue
        n_partes, n_pontos = struct.unpack("<2i", reg[36:44])
        partes = list(struct.unpack(f"<{n_partes}i", reg[44 : 44 + 4 * n_partes]))
        base = 44 + 4 * n_partes
        pts = [
            struct.unpack("<2d", reg[base + 16 * j : base + 16 * j + 16]) for j in range(n_pontos)
        ]
        if any(not (-180 <= x <= 180 and -90 <= y <= 90) for x, y in pts):
            raise Invalido("Coordenadas fora de graus WGS 84.", codigo="SHP_PROJECAO")
        for a, b in zip(partes, [*partes[1:], n_pontos], strict=True):
            if b - a < 2:
                continue
            texto = next(iter(attr.values()), "") if attr else ""
            subtipo = attr.get("Type", "")
            linhas.append(
                {
                    "tipo": tipo,
                    "gravado_em": _data_omni(texto),
                    "subtipo": int(subtipo) if subtipo.lstrip("-").isdigit() else None,
                    "geom": LineString(pts[a:b]),
                }
            )
    if tipo == "cabeceira":
        com_forma = [x for x in linhas if len(x["geom"].coords) >= 3][-1:]
        datas = [d for a in atributos if (d := _data_omni(next(iter(a.values()), "")))]
        for x in com_forma:
            x["gravado_em"] = x["gravado_em"] or (max(datas) if datas else None)
        return com_forma
    return linhas


def nome_normalizado(nome: str) -> str:
    """'Mãe', 'Mae' e 'MAE' são o mesmo talhão; 'Paulo 3,7' = 'Paulo3-7'."""
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return "".join(c for c in sem_acento.lower() if c.isalnum())
