"""Leitor de baixo nível do GreenStar 3 2630 (pasta ``RCD/EIC/Documentation``).

Cada operação gravada é um par ``<uuid>.fdl`` (XML: cadastro, colunas e hora de início de
cada bloco) + ``<uuid>.fdd`` (binário ``EvenByteDelta``). Formato descoberto por engenharia
reversa (ver ``docs/formatos/greenstar3-rcd.md``); aqui não há significado agronômico,
só colunas e valores físicos.

``.fdd``: uma sequência de blocos. Cada bloco tem cabeçalho (UUIDs + definição das colunas)
e registros de ~1 s:

* cabeçalho do registro: ``u16 2``, ``u8 n_controle``, ``u8 omitidas``, ``u32`` (0x70/0xE0);
* máscara ``A`` (u32) e ``B`` (u24) sobre as colunas a partir da 9ª: em ``B`` o valor vem
  absoluto no fim do registro; em ``A`` (só colunas "cruas") repete o anterior;
* campos fixos, na ordem das colunas: delta ``i16`` (tipo 3) ou ``i32`` (tipo 4) e estado
  absoluto ``u16`` (enumerados das 8 primeiras colunas). Os bits de ``omitidas`` tiram as
  primeiras colunas do registro (registro de evento) e o próximo delta parte do valor físico zero;
* ``n_controle`` valores marcados de controle e um valor marcado (``u16 tipo, u16 tamanho``)
  por bit de ``B``.
"""

from __future__ import annotations

import struct
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

_REGISTRO = 2
_PRIMEIRAS = 8  # colunas sem bit nas máscaras (medidas e seções, sempre no bloco fixo)


class RcdFormatError(ValueError):
    pass


@dataclass(slots=True)
class Coluna:
    nome: str
    tipo: int  # 1 enumerado, 3 inteiro de 16 bits, 4 de 32 bits, 5 valor cru
    cru: bool  # vem só como valor marcado (nunca no bloco fixo)
    resolucao: float = 1.0
    base: float = 0.0
    opcoes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Bloco:
    colunas: list[Coluna]
    linhas: list[list[Any]]  # uma por registro, na ordem das colunas (None = ausente)


def _u16(d: bytes, i: int) -> int:
    v: int = struct.unpack_from("<H", d, i)[0]
    return v


def _cabecalho(d: bytes, i: int) -> tuple[list[Coluna], int]:
    """Do início do bloco (``u16 1|4``, UUIDs) até o primeiro registro."""
    # UUIDs em texto (u16 tamanho + texto) até a lista de colunas: "01 00 02 00 <n> 00".
    fim_busca = min(len(d), i + 4096)
    j = d.find(b"\x01\x00\x02\x00", i, fim_busca)
    while j >= 0 and d[j + 6 : j + 8] not in (b"\x01\x00", b"\x03\x00", b"\x04\x00", b"\x05\x00"):
        j = d.find(b"\x01\x00\x02\x00", j + 1, fim_busca)
    if j < 0:
        raise RcdFormatError(f"lista de colunas não encontrada no bloco em {i}")
    n = _u16(d, j + 4)
    i = j + 6
    colunas: list[Coluna] = []
    for _ in range(n):
        tipo, _, tam = struct.unpack_from("<3H", d, i)
        nome = d[i + 6 : i + 6 + tam].decode("latin-1")
        i += 6 + tam
        cru = d[i] == 1
        if tipo == 1:
            qtd = _u16(d, i + 1)
            i += 5
            opcoes = []
            for _ in range(qtd):
                t = _u16(d, i)
                opcoes.append(d[i + 2 : i + 2 + t].decode("latin-1"))
                i += 2 + t
            colunas.append(Coluna(nome, tipo, cru, opcoes=opcoes))
        else:
            tam_vals = _u16(d, i + 1)
            res, _, base = struct.unpack_from("<3d", d, i + 3)
            i += 3 + tam_vals
            colunas.append(Coluna(nome, tipo, cru or tipo == 5, res, base))
    return colunas, i


def _marcado(d: bytes, i: int) -> tuple[Any, int]:
    tipo, tam = struct.unpack_from("<2H", d, i)
    v = d[i + 4 : i + 4 + tam]
    if len(v) != tam:
        raise RcdFormatError("valor marcado truncado")
    if tam == 8:
        return struct.unpack("<d", v)[0], i + 4 + tam
    if tam == 4 and tipo == 3:
        return struct.unpack("<f", v)[0], i + 4 + tam
    return int.from_bytes(v, "little"), i + 4 + tam


def ler_fdd(d: bytes) -> list[Bloco]:
    try:
        return _ler_fdd(d)
    except (struct.error, IndexError, UnicodeDecodeError) as exc:
        raise RcdFormatError(f"arquivo .fdd truncado ou corrompido: {exc}") from exc


def _ler_fdd(d: bytes) -> list[Bloco]:
    blocos: list[Bloco] = []
    i = 0
    while i + 8 <= len(d):
        tipo = _u16(d, i)
        if tipo != _REGISTRO:  # início de bloco (1 no primeiro, 4 nos seguintes)
            colunas, i = _cabecalho(d, i)
            blocos.append(Bloco(colunas, []))
            acum = [0] * len(colunas)
            valores: list[Any] = [None] * len(colunas)
            continue
        if not blocos:
            raise RcdFormatError("registro antes do cabeçalho")
        if i + 15 > len(d):
            break  # cauda incompleta (o monitor desligou gravando)
        n_controle, omitidas = d[i + 2], d[i + 3]  # o u32 seguinte varia (0x70, 0xE0) e não é usado
        bloco = blocos[-1]
        cols = bloco.colunas
        a = int.from_bytes(d[i + 8 : i + 12], "little")
        b = int.from_bytes(d[i + 12 : i + 15], "little")
        i += 15
        nulas: set[int] = set()
        for k, c in enumerate(cols):
            if c.cru or (k >= _PRIMEIRAS and (b >> (k - _PRIMEIRAS)) & 1):
                continue
            if k < _PRIMEIRAS and (omitidas >> k) & 1:
                # Depois do evento o delta recomeça do valor físico zero (não da base do bloco).
                acum[k] = -round(c.base / c.resolucao) if c.tipo != 1 and c.resolucao else 0
                nulas.add(k)
                continue
            if c.tipo == 4:
                v = struct.unpack_from("<i", d, i)[0]
                i += 4
            else:
                v = struct.unpack_from("<h", d, i)[0]
                i += 2
            acum[k] = v if c.tipo == 1 else acum[k] + v
        for _ in range(n_controle):
            _, i = _marcado(d, i)
        for bit in range(len(cols) - _PRIMEIRAS):
            k = _PRIMEIRAS + bit
            c = cols[k]
            if (b >> bit) & 1:
                v, i = _marcado(d, i)
                if c.cru:
                    valores[k] = v
                elif c.tipo == 1:
                    acum[k] = int(v)
                else:
                    acum[k] = round((v - c.base) / c.resolucao) if c.resolucao else 0
            elif c.cru and not (a >> bit) & 1:
                valores[k] = None
        for k, c in enumerate(cols):
            if c.cru:
                continue
            if k in nulas:
                valores[k] = None
            elif c.tipo == 1:
                valores[k] = acum[k] if 0 <= acum[k] < len(c.opcoes) else None
            else:
                valores[k] = c.base + acum[k] * c.resolucao
        bloco.linhas.append(list(valores))
    return blocos


# ------------------------------------------------------------------------- .fdl
@dataclass(slots=True)
class Fdl:
    inicios: list[datetime]  # um por bloco do .fdd, na ordem
    colunas: dict[str, str]  # columnID -> representação (vrHarvestMoisture, ...)
    serial_maquina: str | None = None
    modelo: str | None = None
    cliente: tuple[str | None, str | None] = (None, None)  # (nome, erid)
    fazenda: tuple[str | None, str | None] = (None, None)
    talhao: tuple[str | None, str | None] = (None, None)
    cultura: str | None = None  # da cultura usada na operação (ProductRef -> variedade -> cultura)
    variedade: str | None = None
    ano_safra: int | None = None
    operador: str | None = None
    tarefa: str | None = None
    implemento: str | None = None
    largura_m: float | None = None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def ler_fdl(xml: bytes) -> Fdl:
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise RcdFormatError(f"arquivo .fdl inválido: {exc}") from exc
    fdl = Fdl(inicios=[], colunas={})
    larguras: dict[str, float] = {}
    pais = {filho: pai for pai in raiz.iter() for filho in pai}
    produtos = [
        e.get("eridRef") for e in raiz.iter() if _local(e.tag) == "ProductRef" and e.get("eridRef")
    ]
    for e in raiz.iter():
        if _local(e.tag) == "CropVariety" and e.get("erid") in produtos:
            pai = pais.get(e)
            fdl.variedade = e.get("name")
            fdl.cultura = pai.get("name") if pai is not None else None
            break
    for el in raiz.iter():
        nome = _local(el.tag)
        at = el.attrib
        if nome == "LogTaskRegion" and at.get("timeStamp"):
            ts = datetime.fromisoformat(at["timeStamp"].replace("Z", "+00:00"))
            fdl.inicios.append(ts.astimezone(UTC))
            if at.get("cropYear", "").isdigit() and fdl.ano_safra is None:
                fdl.ano_safra = int(at["cropYear"])
        elif "columnID" in at:
            rep = at.get("variableRepresentation") or at.get("definedTypeRepresentation")
            if rep:
                fdl.colunas.setdefault(at["columnID"], rep)
        elif nome == "Machine" and fdl.serial_maquina is None:
            fdl.serial_maquina = at.get("serialNumber") or None
        elif nome == "MachineModel" and fdl.modelo is None:
            fdl.modelo = at.get("name")
        elif nome == "Client" and fdl.cliente[0] is None:
            fdl.cliente = (at.get("name"), at.get("erid"))
        elif nome == "Farm" and fdl.fazenda[0] is None:
            fdl.fazenda = (at.get("name"), at.get("erid"))
        elif nome == "Field" and fdl.talhao[0] is None:
            fdl.talhao = (at.get("name"), at.get("erid"))
        elif nome == "Operator" and fdl.operador is None:
            fdl.operador = at.get("name")
        elif nome == "Task" and fdl.tarefa is None:
            fdl.tarefa = at.get("name")
        elif nome == "ImplementModel" and fdl.implemento is None:
            fdl.implemento = at.get("name")
        elif nome == "Section" and "id" in at:
            for filho in el:
                if _local(filho.tag) == "vrSectionWidth" and filho.get("value"):
                    larguras[at["id"]] = float(filho.get("value", "0")) / 1000.0
    if larguras:
        fdl.largura_m = round(sum(larguras.values()), 3)
    return fdl
