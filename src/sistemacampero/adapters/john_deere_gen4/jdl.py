"""Leitor de baixo nível dos arquivos .jdl do monitor John Deere Gen4 (software 10.x).

Formato (engenharia reversa, não documentado pela John Deere):

    arquivo  = bloco*
    bloco    = 0x0D  uint32_le(tamanho)  mensagem_protobuf
    mensagem : campo 1 = tipo (3 = versão do software, 1 = cabeçalho/definições,
                              2 = bloco de dados, 4 = rodapé)

    Bloco de dados (tipo 2, campo 4):
        5  = duração do bloco em ms (~30 000)
        6  = {lat, lon} (double) no início do bloco
        7  = {lat, lon} (double) no fim do bloco
        9  = colunas:
               1* tipos | 2 = ids dos canais (varints empacotados) | 3* uma série por canal:
                   2 = delta de tempo entre amostras (varints, unidade = 0,5 ms)
                   3 = valores (varints zigzag, codificados como DELTA em relação à
                       amostra anterior; a soma é contínua entre blocos do mesmo canal)

    valor_físico = valor_bruto / escala + offset   (escala/offset vêm do cabeçalho)

Este módulo não conhece o significado dos canais; isso fica em ``channels.py``.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

DT_UNIT_MS = 0.5  # unidade dos deltas de tempo, validada: 150 amostras/30 s a 5 Hz


class JdlFormatError(ValueError):
    """Arquivo .jdl fora do formato esperado."""


# --------------------------------------------------------------------------- protobuf
def _varint(buf: bytes, i: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        byte = buf[i]
        i += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, i
        shift += 7


def parse_message(buf: bytes) -> list[tuple[int, int, bytes | int]]:
    """Decodifica uma mensagem protobuf em (campo, wire_type, valor)."""
    i, out = 0, []
    try:
        while i < len(buf):
            key, i = _varint(buf, i)
            field_no, wire = key >> 3, key & 7
            if field_no == 0 or wire in (3, 4) or wire > 5:
                raise JdlFormatError("wire type inválido")
            if wire == 0:
                value, i = _varint(buf, i)
            elif wire == 1:
                value, i = buf[i : i + 8], i + 8
            elif wire == 5:
                value, i = buf[i : i + 4], i + 4
            else:
                size, i = _varint(buf, i)
                if i + size > len(buf):
                    raise JdlFormatError("tamanho de campo excede o bloco")
                value, i = buf[i : i + size], i + size
            out.append((field_no, wire, value))
    except IndexError as exc:
        raise JdlFormatError("mensagem truncada") from exc
    return out


def packed_varints(buf: bytes) -> list[int]:
    out, i = [], 0
    while i < len(buf):
        value, i = _varint(buf, i)
        out.append(value)
    return out


def _zigzag(n: int) -> int:
    return (n >> 1) ^ -(n & 1)


def _first(fields, number):
    for f, _, v in fields:
        if f == number:
            return v
    return None


def _all(fields, number):
    return [v for f, _, v in fields if f == number]


def _double(raw: bytes) -> float:
    return struct.unpack("<d", raw)[0]


# --------------------------------------------------------------------------- estruturas
@dataclass(frozen=True)
class ChannelDef:
    channel_id: int
    ddi: int
    offset: float
    scale: float
    unit: str
    group: str  # ex.: "Deere Tractor Data", "HLC", "Plantio"
    device_index: int


@dataclass
class Series:
    """Série temporal de um canal dentro de um arquivo (já em valores brutos acumulados)."""

    t_ms: list[float] = field(default_factory=list)  # ms desde o início do arquivo
    raw: list[int] = field(default_factory=list)


@dataclass
class DataChunk:
    duration_ms: int
    start: tuple[float, float] | None  # (lat, lon)
    end: tuple[float, float] | None


@dataclass(frozen=True)
class ImplementInfo:
    name: str
    width_m: float | None


@dataclass
class JdlFile:
    path: Path
    software_version: str | None
    display_serial: str | None
    machine_serial: str | None
    started_at_ms: int | None  # epoch ms (UTC)
    channels: dict[int, ChannelDef]
    series: dict[int, Series]
    chunks: list[DataChunk]
    device_names: list[str]
    client_name: str | None = None
    farm_name: str | None = None
    field_guid: str | None = None
    field_name: str | None = None
    implements: list[ImplementInfo] = field(default_factory=list)
    sha256: str = ""


# --------------------------------------------------------------------------- leitura
def iter_blocks(data: bytes) -> Iterator[bytes]:
    i, n = 0, len(data)
    while i < n:
        if data[i] != 0x0D or i + 5 > n:
            raise JdlFormatError(f"marcador de bloco inesperado em {i}")
        size = struct.unpack_from("<I", data, i + 1)[0]
        if i + 5 + size > n:
            raise JdlFormatError("bloco truncado")
        yield data[i + 5 : i + 5 + size]
        i += 5 + size


def _read_text(raw: bytes) -> str | None:
    try:
        s = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return s if s.isprintable() else None


def _named_entity(root, number) -> tuple[str | None, str | None]:
    """Cliente/fazenda/talhão: campo N -> {1: {1: guid, 2: nome}}."""
    raw = _first(root, number)
    if not isinstance(raw, bytes) or not raw:
        return None, None
    inner = _first(parse_message(raw), 1)
    if not isinstance(inner, bytes):
        return None, None
    f = parse_message(inner)
    g, n = _first(f, 1), _first(f, 2)
    return (
        _read_text(g) if isinstance(g, bytes) else None,
        _read_text(n) if isinstance(n, bytes) else None,
    )


def _parse_header(header_msg: list) -> tuple[dict, dict, list, list]:
    """Extrai metadados e definições de canal do bloco de cabeçalho (tipo 1)."""
    root = parse_message(_first(header_msg, 5))
    meta = {
        "started_at_ms": _first(root, 3),
        "display_serial": None,
    }
    serial = _first(root, 5)
    if isinstance(serial, bytes):
        meta["display_serial"] = _read_text(serial)

    channels: dict[int, ChannelDef] = {}
    device_names: list[str] = []
    machine_serial = None
    block10 = _first(root, 10)
    devices = _all(parse_message(block10), 2) if block10 else []
    for dev_idx, dev in enumerate(devices):
        dev_fields = parse_message(dev)
        if dev_idx == 0:
            s = _first(dev_fields, 4)
            machine_serial = _read_text(s) if isinstance(s, bytes) else None
        for group_raw in _all(dev_fields, 7):
            group = parse_message(group_raw)
            name_raw = _first(group, 9)
            group_name = _read_text(name_raw) if isinstance(name_raw, bytes) else None
            group_name = group_name or f"grupo_{_first(group, 1)}"
            device_names.append(group_name)
            for chan_raw in _all(group, 5):
                c = parse_message(chan_raw)
                cid = _first(c, 1)
                if cid is None:
                    continue
                scale = _first(c, 4)
                offset = _first(c, 3)
                unit = _first(c, 5)
                channels[cid] = ChannelDef(
                    channel_id=cid,
                    ddi=_first(c, 2) or 0,
                    offset=_double(offset) if isinstance(offset, bytes) else 0.0,
                    scale=(_double(scale) if isinstance(scale, bytes) else 1.0) or 1.0,
                    unit=(_read_text(unit) or "") if isinstance(unit, bytes) else "",
                    group=group_name,
                    device_index=dev_idx,
                )
    meta["machine_serial"] = machine_serial

    meta["client_guid"], meta["client_name"] = _named_entity(root, 11)
    meta["farm_guid"], meta["farm_name"] = _named_entity(root, 12)
    meta["field_guid"], meta["field_name"] = _named_entity(root, 13)

    implements: list[ImplementInfo] = []
    for dev in devices[1:]:
        f = parse_message(dev)
        name, width = _first(f, 5), _first(f, 6)
        if isinstance(name, bytes) and _read_text(name):
            w = _double(width) if isinstance(width, bytes) and len(width) == 8 else None
            implements.append(ImplementInfo(_read_text(name), w if w else None))
    meta["implements"] = implements
    return meta, channels, device_names, devices


def read_jdl(
    path: str | Path,
    *,
    channel_filter: set[int] | Callable[[ChannelDef], bool] | None = None,
) -> JdlFile:
    """Lê um .jdl completo.

    ``channel_filter`` limita quais canais são materializados (economiza memória):
    um conjunto de ids ou um predicado sobre ``ChannelDef`` (avaliado após o cabeçalho).
    """
    path = Path(path)
    data = path.read_bytes()
    sha256 = hashlib.sha256(data).hexdigest()
    wanted: set[int] | None = channel_filter if isinstance(channel_filter, set) else None
    software = None
    meta: dict = {}
    channels: dict[int, ChannelDef] = {}
    device_names: list[str] = []
    series: dict[int, Series] = {}
    chunks: list[DataChunk] = []
    last_raw: dict[int, int] = {}
    clock_ms: dict[int, float] = {}

    for block in iter_blocks(data):
        msg = parse_message(block)
        kind = _first(msg, 1)

        if kind == 3:
            inner = _first(msg, 3)
            if isinstance(inner, bytes):
                v = _first(parse_message(inner), 4)
                software = _read_text(v) if isinstance(v, bytes) else None

        elif kind == 1 and _first(msg, 5) is not None:
            meta, channels, device_names, _ = _parse_header(msg)
            if callable(channel_filter):
                wanted = {cid for cid, c in channels.items() if channel_filter(c)}

        elif kind == 2 and _first(msg, 4) is not None:
            body = parse_message(_first(msg, 4))
            duration = _first(body, 5) or 0
            p6, p7 = _first(body, 6), _first(body, 7)

            def _pt(raw):
                if not isinstance(raw, bytes):
                    return None
                f = parse_message(raw)
                try:
                    return (_double(_first(f, 1)), _double(_first(f, 2)))
                except (TypeError, struct.error):
                    return None

            chunks.append(DataChunk(duration, _pt(p6), _pt(p7)))

            cols = _first(body, 9)
            if not cols:
                continue
            cols = parse_message(cols)
            ids_raw = _first(cols, 2)
            if not isinstance(ids_raw, bytes):
                continue
            ids = packed_varints(ids_raw)
            for cid, entry in zip(ids, _all(cols, 3)):
                if wanted is not None and cid not in wanted:
                    continue
                e = parse_message(entry)
                dts = _first(e, 2)
                vals = _first(e, 3)
                if not isinstance(dts, bytes) or not isinstance(vals, bytes):
                    continue
                dts, vals = packed_varints(dts), packed_varints(vals)
                if len(dts) != len(vals):
                    continue
                s = series.setdefault(cid, Series())
                t = clock_ms.get(cid, 0.0)
                run = last_raw.get(cid, 0)
                for dt, v in zip(dts, vals):
                    t += dt * DT_UNIT_MS
                    run += _zigzag(v)
                    s.t_ms.append(t)
                    s.raw.append(run)
                clock_ms[cid], last_raw[cid] = t, run

    return JdlFile(
        path=path,
        software_version=software,
        display_serial=meta.get("display_serial"),
        machine_serial=meta.get("machine_serial"),
        started_at_ms=meta.get("started_at_ms"),
        channels=channels,
        series=series,
        chunks=chunks,
        device_names=device_names,
        client_name=meta.get("client_name"),
        farm_name=meta.get("farm_name"),
        field_guid=meta.get("field_guid"),
        field_name=meta.get("field_name"),
        implements=meta.get("implements", []),
        sha256=sha256,
    )
