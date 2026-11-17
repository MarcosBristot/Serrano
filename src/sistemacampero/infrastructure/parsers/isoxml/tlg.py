"""ISOXML (ISO 11783-10): TASKDATA.XML + registros de tempo/posição (TLGnnnnn.XML + .BIN).

É o formato aberto que monitores ISOBUS de várias marcas exportam no pendrive. Aqui só a parte
da norma que o Serrano usa:

* ``TASKDATA.XML``: tarefas (``TSK``) com cliente (``CTR``), fazenda (``FRM``), talhão (``PFD``),
  equipamentos (``DVC``/``DET``) e a lista de ``TLG`` gravados;
* ``TLGnnnnn.XML``: cabeçalho ``TIM`` com a posição ``PTN`` e os valores ``DLV`` (DDI em hex).
  Atributo vazio = o valor vem em cada registro do .BIN; preenchido = constante;
* ``TLGnnnnn.BIN``, por registro: hora (``u32`` ms desde a meia-noite + ``u16`` dias desde
  1980-01-01), os campos vazios do ``PTN`` na ordem A..I, ``u8`` quantos DLV vêm e, para cada um,
  ``u8`` índice do DLV + ``i32`` valor.
"""

from __future__ import annotations

import struct
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

EPOCA = datetime(1980, 1, 1, tzinfo=UTC)
# PTN: atributo -> (formato struct, fator para unidade física)
_PTN = {
    "A": ("<i", 1e-7),  # norte (graus)
    "B": ("<i", 1e-7),  # leste (graus)
    "C": ("<i", 1e-3),  # altitude (mm -> m)
    "D": ("<B", 1.0),  # status do GPS
    "E": ("<H", 0.1),  # PDOP
    "F": ("<H", 0.1),  # HDOP
    "G": ("<B", 1.0),  # satélites
    "H": ("<I", 1.0),  # hora GPS (ms)
    "I": ("<H", 1.0),  # data GPS (dias)
}


class IsoxmlFormatError(ValueError):
    pass


@dataclass(slots=True)
class Registro:
    ts: datetime
    posicao: dict[str, float]  # A..I presentes
    valores: dict[int, int]  # DDI -> valor bruto


@dataclass(slots=True)
class Tlg:
    nome: str
    ddis: list[int]  # DDI de cada DLV, na ordem do cabeçalho
    dets: list[str | None]  # DET de cada DLV
    registros: list[Registro] = field(default_factory=list)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def ler_tlg(nome: str, cabecalho: bytes, binario: bytes) -> Tlg:
    try:
        raiz = ET.fromstring(cabecalho)
    except ET.ParseError as exc:
        raise IsoxmlFormatError(f"{nome}.XML inválido: {exc}") from exc
    tim = raiz if _local(raiz.tag) == "TIM" else raiz.find(".//TIM")
    if tim is None:
        raise IsoxmlFormatError(f"{nome}.XML sem TIM")
    if tim.get("A", "") != "":
        raise IsoxmlFormatError(f"{nome}: hora fixa no cabeçalho não é suportada")
    ptn = tim.find("PTN")
    campos = [a for a in _PTN if ptn is not None and ptn.get(a) == ""]
    dlvs = tim.findall("DLV")
    ddis = [int(d.get("A", "0"), 16) for d in dlvs]
    tlg = Tlg(nome, ddis, [d.get("C") for d in dlvs])
    try:
        _ler_bin(binario, campos, tlg)
    except (struct.error, IndexError) as exc:
        raise IsoxmlFormatError(f"{nome}.BIN truncado ou corrompido: {exc}") from exc
    return tlg


def _ler_bin(d: bytes, campos: list[str], tlg: Tlg) -> None:
    i = 0
    n = len(d)
    while i < n:
        ms, dias = struct.unpack_from("<IH", d, i)
        i += 6
        posicao: dict[str, float] = {}
        for a in campos:
            fmt, fator = _PTN[a]
            (v,) = struct.unpack_from(fmt, d, i)
            i += struct.calcsize(fmt)
            posicao[a] = v * fator
        qtd = d[i]
        i += 1
        valores: dict[int, int] = {}
        for _ in range(qtd):
            idx, valor = struct.unpack_from("<Bi", d, i)
            i += 5
            if idx >= len(tlg.ddis):
                raise IsoxmlFormatError(f"{tlg.nome}: DLV {idx} fora do cabeçalho")
            valores[tlg.ddis[idx]] = valor
        ts = EPOCA + timedelta(days=dias, milliseconds=ms)
        tlg.registros.append(Registro(ts, posicao, valores))


# ------------------------------------------------------------------ TASKDATA.XML
@dataclass(slots=True)
class Tarefa:
    nome: str | None
    cliente: str | None
    fazenda: str | None
    talhao: str | None
    dispositivos: dict[str, dict[str, Any]]  # DET -> {"designacao", "serial"} do DVC dono


def ler_taskdata(xml: bytes, tlg: str) -> Tarefa:
    """A tarefa que gravou o TLG, com os nomes já resolvidos."""
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise IsoxmlFormatError(f"TASKDATA.XML inválido: {exc}") from exc
    por_id = {e.get("A"): e for e in raiz.iter() if e.get("A")}
    dispositivos: dict[str, dict[str, Any]] = {}
    for dvc in raiz.iter("DVC"):
        info = {"designacao": dvc.get("B"), "serial": dvc.get("E") or None}
        for det in dvc.iter("DET"):
            if det.get("A"):
                dispositivos[det.get("A", "")] = info
    tsk = next((t for t in raiz.iter("TSK") if any(x.get("A") == tlg for x in t.iter("TLG"))), None)

    def nome(ref: str | None, attr: str) -> str | None:
        el = por_id.get(ref) if ref else None
        return el.get(attr) if el is not None else None

    return Tarefa(
        nome=tsk.get("B") if tsk is not None else None,
        cliente=nome(tsk.get("C") if tsk is not None else None, "B"),
        fazenda=nome(tsk.get("D") if tsk is not None else None, "B"),
        talhao=nome(tsk.get("E") if tsk is not None else None, "C"),
        dispositivos=dispositivos,
    )
