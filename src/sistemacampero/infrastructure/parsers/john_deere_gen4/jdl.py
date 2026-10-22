"""Leitor de baixo nível dos arquivos .jdl do monitor John Deere Gen4 (software 10.x).

Formato (engenharia reversa, não documentado pela John Deere; ver ADR 0005):

    arquivo  = bloco*
    bloco    = 0x0D  uint32_le(tamanho)  mensagem_protobuf
    mensagem : campo 1 = tipo (3 = versão do software, 1 = cabeçalho/definições,
                              2 = bloco de dados, 4 = rodapé)

    Bloco de dados (tipo 2, campo 4):
        5  = duração do bloco em ms (~30 000)
        6  = canto SUDOESTE (lat mín., lon mín.) das posições do bloco  (double, double)
        7  = canto NORDESTE (lat máx., lon máx.)                          (double, double)
        9  = colunas: 2 = ids dos canais (varints empacotados) | 3* uma entrada por canal

    Entrada de canal definido no cabeçalho:
        1  = ÂNCORA de valor: valor bruto acumulado antes deste bloco (double)
        2  = deltas de tempo entre amostras (varints, unidade = 0,5 ms)
        3  = valores (varints zigzag, DELTA em relação à amostra anterior)
        12 = ÂNCORA de tempo: início do bloco em ms desde o início do arquivo (int64)

    Entrada da trilha GPS (canal SEM definição no cabeçalho, ~5 Hz):
        1, 2 = âncoras de latitude/longitude acumuladas (double, nanograus)
        26   = âncora de tempo (ms)
        10   = deltas de tempo (varints zigzag, ms)
        12   = deltas de latitude, 13 = deltas de longitude (zigzag, nanograus)

    valor_físico = valor_bruto / escala + offset   (escala/offset vêm do cabeçalho)

As âncoras ressincronizam a soma a cada bloco. Sem elas, um primeiro bloco que já
começa com valor acumulado (âncora diferente de zero) desloca a série inteira: era o
"RPM nunca passa de 709" do arquivo 106a770c. Os pontos 6/7 são uma caixa, não início
e fim da trajetória; lê-los como trajetória gerava os falsos "saltos de GPS".

Este módulo não conhece o significado dos canais; isso fica em ``channels.py``.
"""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

DT_UNIT_MS = 0.5  # unidade dos deltas de tempo, validada: 150 amostras/30 s a 5 Hz
GPS_ESCALA = 1e-9  # nanograus

Campo = tuple[int, int, bytes | int]
Ponto = tuple[float, float]


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


def parse_message(buf: bytes) -> list[Campo]:
    """Decodifica uma mensagem protobuf em (campo, wire_type, valor)."""
    i, out = 0, []
    try:
        while i < len(buf):
            key, i = _varint(buf, i)
            field_no, wire = key >> 3, key & 7
            if field_no == 0 or wire in (3, 4) or wire > 5:
                raise JdlFormatError("wire type inválido")
            value: bytes | int
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
    try:
        while i < len(buf):
            value, i = _varint(buf, i)
            out.append(value)
    except IndexError as exc:
        raise JdlFormatError("varints empacotados truncados") from exc
    return out


def _zigzag(n: int) -> int:
    return (n >> 1) ^ -(n & 1)


def _int64(n: int) -> int:
    return n - (1 << 64) if n >= (1 << 63) else n


def _first(fields: list[Campo], number: int) -> bytes | int | None:
    for f, _, v in fields:
        if f == number:
            return v
    return None


def _first_bytes(fields: list[Campo], number: int) -> bytes | None:
    v = _first(fields, number)
    return v if isinstance(v, bytes) else None


def _all_bytes(fields: list[Campo], number: int) -> list[bytes]:
    return [v for f, _, v in fields if f == number and isinstance(v, bytes)]


def _double(raw: bytes) -> float:
    return float(struct.unpack("<d", raw)[0])


def _text(raw: bytes | int | None) -> str | None:
    if not isinstance(raw, bytes):
        return None
    try:
        s = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return s if s and s.isprintable() else None


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
    """Série temporal de um canal dentro de um arquivo (valores brutos já acumulados)."""

    t_ms: list[float] = field(default_factory=list)  # ms desde o início do arquivo
    raw: list[int] = field(default_factory=list)


@dataclass
class GpsTrack:
    """Trilha GPS (~5 Hz); tempo em ms desde o início do arquivo."""

    t_ms: list[float] = field(default_factory=list)
    lat: list[float] = field(default_factory=list)
    lon: list[float] = field(default_factory=list)


@dataclass(frozen=True)
class DataChunk:
    duration_ms: int
    inicio_ms: float  # início do bloco (ms desde o início do arquivo)
    sudoeste: Ponto | None  # (lat mín., lon mín.)
    nordeste: Ponto | None  # (lat máx., lon máx.)

    @property
    def centro(self) -> Ponto | None:
        if self.sudoeste is None or self.nordeste is None:
            return None
        return (
            (self.sudoeste[0] + self.nordeste[0]) / 2,
            (self.sudoeste[1] + self.nordeste[1]) / 2,
        )


@dataclass(frozen=True)
class ImplementInfo:
    name: str
    width_m: float | None


@dataclass
class JdlFile:
    sha256: str
    software_version: str | None
    display_serial: str | None
    machine_serial: str | None
    started_at_ms: int | None  # epoch ms (UTC)
    channels: dict[int, ChannelDef]
    series: dict[int, Series]
    chunks: list[DataChunk]
    device_names: list[str]
    client_guid: str | None = None
    client_name: str | None = None
    farm_guid: str | None = None
    farm_name: str | None = None
    field_guid: str | None = None
    field_name: str | None = None
    implements: list[ImplementInfo] = field(default_factory=list)
    gps: GpsTrack = field(default_factory=GpsTrack)
    # blocos, ancoras_divergentes (ressincronização = sinal de perda de dado),
    # entradas_ignoradas (codificação desconhecida), amostras_gps
    estatisticas: dict[str, int] = field(default_factory=dict)


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


def _named_entity(root: list[Campo], number: int) -> tuple[str | None, str | None]:
    """Cliente/fazenda/talhão: campo N -> {1: {1: guid, 2: nome}}."""
    raw = _first_bytes(root, number)
    if not raw:
        return None, None
    inner = _first_bytes(parse_message(raw), 1)
    if inner is None:
        return None, None
    f = parse_message(inner)
    return _text(_first(f, 1)), _text(_first(f, 2))


@dataclass
class _Header:
    started_at_ms: int | None = None
    display_serial: str | None = None
    machine_serial: str | None = None
    channels: dict[int, ChannelDef] = field(default_factory=dict)
    device_names: list[str] = field(default_factory=list)
    entities: dict[str, str | None] = field(default_factory=dict)
    implements: list[ImplementInfo] = field(default_factory=list)


def _parse_header(header_msg: list[Campo]) -> _Header:
    """Extrai metadados e definições de canal do bloco de cabeçalho (tipo 1)."""
    raw_root = _first_bytes(header_msg, 5)
    if raw_root is None:
        raise JdlFormatError("cabeçalho sem raiz")
    root = parse_message(raw_root)
    h = _Header()
    started = _first(root, 3)
    h.started_at_ms = started if isinstance(started, int) else None
    h.display_serial = _text(_first(root, 5))

    block10 = _first_bytes(root, 10)
    devices = _all_bytes(parse_message(block10), 2) if block10 else []
    for dev_idx, dev in enumerate(devices):
        dev_fields = parse_message(dev)
        if dev_idx == 0:
            h.machine_serial = _text(_first(dev_fields, 4))
        for group_raw in _all_bytes(dev_fields, 7):
            group = parse_message(group_raw)
            group_name = _text(_first(group, 9)) or f"grupo_{_first(group, 1)!r}"
            h.device_names.append(group_name)
            for chan_raw in _all_bytes(group, 5):
                c = parse_message(chan_raw)
                cid = _first(c, 1)
                if not isinstance(cid, int):
                    continue
                ddi, scale, offset = _first(c, 2), _first_bytes(c, 4), _first_bytes(c, 3)
                h.channels[cid] = ChannelDef(
                    channel_id=cid,
                    ddi=ddi if isinstance(ddi, int) else 0,
                    offset=_double(offset) if offset and len(offset) == 8 else 0.0,
                    scale=(_double(scale) if scale and len(scale) == 8 else 1.0) or 1.0,
                    unit=_text(_first(c, 5)) or "",
                    group=group_name,
                    device_index=dev_idx,
                )

    for nome, numero in (("client", 11), ("farm", 12), ("field", 13)):
        guid, nome_ent = _named_entity(root, numero)
        h.entities[f"{nome}_guid"], h.entities[f"{nome}_name"] = guid, nome_ent

    for dev in devices[1:]:
        f = parse_message(dev)
        name, width = _text(_first(f, 5)), _first_bytes(f, 6)
        if name:
            w = _double(width) if width and len(width) == 8 else None
            h.implements.append(ImplementInfo(name, w if w and w > 0 else None))
    return h


def _ponto(raw: bytes | None) -> Ponto | None:
    if raw is None:
        return None
    f = parse_message(raw)
    a, b = _first_bytes(f, 1), _first_bytes(f, 2)
    if a is None or b is None or len(a) != 8 or len(b) != 8:
        return None
    return (_double(a), _double(b))


class _Canal:
    """Estado acumulado de um canal entre blocos."""

    __slots__ = ("bruto", "t_ms")

    def __init__(self) -> None:
        self.bruto: float = 0.0
        self.t_ms: float = 0.0


def _ancora(
    valor: bytes | int | None, atual: float, iniciado: bool, stats: dict[str, int]
) -> float:
    """Aplica a âncora (double) se houver; conta divergências em relação à soma."""
    if not isinstance(valor, bytes) or len(valor) != 8:
        return atual
    ancora = _double(valor)
    if iniciado and abs(ancora - atual) > 1.0:
        stats["ancoras_divergentes"] += 1
    return ancora


def _entrada_canal(
    campos: dict[int, bytes | int],
    estado: _Canal,
    iniciado: bool,
    serie: Series,
    stats: dict[str, int],
) -> None:
    estado.bruto = _ancora(campos.get(1), estado.bruto, iniciado, stats)
    t_anc = campos.get(12)
    if isinstance(t_anc, int):
        estado.t_ms = float(_int64(t_anc))
    raw_dts, raw_vals = campos.get(2), campos.get(3)
    if not isinstance(raw_dts, bytes) or not isinstance(raw_vals, bytes):
        return  # bloco sem amostras deste canal (só âncoras)
    dts, vals = packed_varints(raw_dts), packed_varints(raw_vals)
    if len(dts) != len(vals):
        stats["entradas_ignoradas"] += 1
        return
    t, bruto = estado.t_ms, estado.bruto
    for dt, v in zip(dts, vals, strict=True):
        t += dt * DT_UNIT_MS
        bruto += _zigzag(v)
        serie.t_ms.append(t)
        serie.raw.append(round(bruto))
    estado.t_ms, estado.bruto = t, bruto


def _e_trilha_gps(campos: dict[int, bytes | int]) -> bool:
    return all(isinstance(campos.get(f), bytes) for f in (10, 12, 13))


class _Gps:
    __slots__ = ("iniciado", "lat", "lon", "t_ms")

    def __init__(self) -> None:
        self.lat = self.lon = self.t_ms = 0.0
        self.iniciado = False


def _entrada_gps(
    campos: dict[int, bytes | int], estado: _Gps, trilha: GpsTrack, stats: dict[str, int]
) -> None:
    estado.lat = _ancora(campos.get(1), estado.lat, estado.iniciado, stats)
    estado.lon = _ancora(campos.get(2), estado.lon, estado.iniciado, stats)
    t_anc = campos.get(26)
    if isinstance(t_anc, int):
        estado.t_ms = float(_int64(t_anc))
    dts, dlat, dlon = (packed_varints(_bytes(campos[f])) for f in (10, 12, 13))
    if not (len(dts) == len(dlat) == len(dlon)):
        stats["entradas_ignoradas"] += 1
        return
    t, la, lo = estado.t_ms, estado.lat, estado.lon
    for dt, a, b in zip(dts, dlat, dlon, strict=True):
        t += _zigzag(dt)
        la += _zigzag(a)
        lo += _zigzag(b)
        trilha.t_ms.append(t)
        trilha.lat.append(la * GPS_ESCALA)
        trilha.lon.append(lo * GPS_ESCALA)
    estado.t_ms, estado.lat, estado.lon, estado.iniciado = t, la, lo, True


def _bytes(v: bytes | int) -> bytes:
    return v if isinstance(v, bytes) else b""


def read_jdl(
    data: bytes,
    *,
    channel_filter: set[int] | Callable[[ChannelDef], bool] | None = None,
    ler_gps: bool = True,
) -> JdlFile:
    """Decodifica um .jdl completo.

    ``channel_filter`` limita quais canais definidos são materializados (economiza
    memória): um conjunto de ids ou um predicado sobre ``ChannelDef``. A trilha GPS é
    lida à parte (``ler_gps``).
    """
    wanted: set[int] | None = channel_filter if isinstance(channel_filter, set) else None
    software: str | None = None
    header = _Header()
    series: dict[int, Series] = {}
    estados: dict[int, _Canal] = {}
    chunks: list[DataChunk] = []
    gps, gps_estado = GpsTrack(), _Gps()
    stats = {"blocos": 0, "ancoras_divergentes": 0, "entradas_ignoradas": 0}
    proximo_inicio_ms = 0.0

    for block in iter_blocks(data):
        msg = parse_message(block)
        kind = _first(msg, 1)

        if kind == 3:
            inner = _first_bytes(msg, 3)
            if inner is not None:
                software = _text(_first(parse_message(inner), 4))

        elif kind == 1 and _first(msg, 5) is not None:
            header = _parse_header(msg)
            if callable(channel_filter):
                wanted = {cid for cid, c in header.channels.items() if channel_filter(c)}

        elif kind == 2 and (raw_body := _first_bytes(msg, 4)) is not None:
            stats["blocos"] += 1
            body = parse_message(raw_body)
            duration = _first(body, 5)
            ancoras_tempo: list[float] = []  # de canais com amostras neste bloco
            raw_cols = _first_bytes(body, 9)
            cols = parse_message(raw_cols) if raw_cols else []
            ids_raw = _first_bytes(cols, 2)
            ids = packed_varints(ids_raw) if ids_raw is not None else []
            for cid, entry in zip(ids, _all_bytes(cols, 3), strict=False):
                try:
                    campos = {f: v for f, _, v in parse_message(entry)}
                    if cid not in header.channels:
                        if ler_gps and _e_trilha_gps(campos):
                            _entrada_gps(campos, gps_estado, gps, stats)
                        continue
                    t_anc = campos.get(12)
                    if isinstance(t_anc, int) and isinstance(campos.get(2), bytes):
                        ancoras_tempo.append(float(_int64(t_anc)))
                    if wanted is not None and cid not in wanted:
                        continue
                    iniciado = cid in estados
                    _entrada_canal(
                        campos,
                        estados.setdefault(cid, _Canal()),
                        iniciado,
                        series.setdefault(cid, Series()),
                        stats,
                    )
                except JdlFormatError:
                    stats["entradas_ignoradas"] += 1  # codificação desconhecida neste canal
            dur = duration if isinstance(duration, int) else 0
            # Mediana: um canal sem amostras pode repetir uma âncora antiga.
            inicio = (
                sorted(ancoras_tempo)[len(ancoras_tempo) // 2]
                if ancoras_tempo
                else proximo_inicio_ms
            )
            chunks.append(
                DataChunk(dur, inicio, _ponto(_first_bytes(body, 6)), _ponto(_first_bytes(body, 7)))
            )
            proximo_inicio_ms = inicio + dur

    stats["amostras_gps"] = len(gps.t_ms)
    ent = header.entities
    return JdlFile(
        sha256=hashlib.sha256(data).hexdigest(),
        software_version=software,
        display_serial=header.display_serial,
        machine_serial=header.machine_serial,
        started_at_ms=header.started_at_ms,
        channels=header.channels,
        series={cid: s for cid, s in series.items() if s.t_ms},
        chunks=chunks,
        device_names=header.device_names,
        client_guid=ent.get("client_guid"),
        client_name=ent.get("client_name"),
        farm_guid=ent.get("farm_guid"),
        farm_name=ent.get("farm_name"),
        field_guid=ent.get("field_guid"),
        field_name=ent.get("field_name"),
        implements=header.implements,
        gps=gps,
        estatisticas=stats,
    )
