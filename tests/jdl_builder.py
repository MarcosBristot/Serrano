"""Gerador de .jdl SINTÉTICO (mesma estrutura do formato real) para testes.

Não usa dados de clientes: nomes e coordenadas são fictícios.
"""

import struct

START_MS = 1_763_208_470_000  # 2025-11-15 12:07:50 UTC


def varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def zz(n: int) -> int:
    return (n << 1) ^ (n >> 63)


def f_varint(no, v):
    return varint(no << 3) + varint(v)


def f_bytes(no, b):
    return varint(no << 3 | 2) + varint(len(b)) + b


def f_double(no, d):
    return varint(no << 3 | 1) + struct.pack("<d", d)


def f_str(no, s):
    return f_bytes(no, s.encode())


def packed(vals):
    return b"".join(varint(v) for v in vals)


def block(msg: bytes) -> bytes:
    return b"\x0d" + struct.pack("<I", len(msg)) + msg


CHANNELS = {  # id: (ddi, offset, scale, unit)
    1: (561, 0.0, 1000.0, "km1hr-1"),
    2: (99, 0.0, 20.0, "l1hr-1"),
    3: (271, 0.0, 8.0, "RPM"),
    4: (247, 0.0, 20.0, "hr"),
    5: (100, 0.0, 2.0, "l"),
}


def build_jdl(
    speed_kmh,
    fuel_lph,
    rpm,
    minutes,
    *,
    width_m=4.95,
    with_gps=True,
    hour0=661.3,
    fuel0=11368.5,
    start_ms=START_MS,
    lat0=-28.10,
    lon0=-52.92,
):
    """Série constante por canal durante ``minutes`` minutos (5 Hz, blocos de 30 s)."""
    chan_defs = b"".join(
        f_bytes(
            5,
            f_varint(1, cid)
            + f_varint(2, ddi)
            + f_double(3, off)
            + f_double(4, sc)
            + f_str(5, unit),
        )
        for cid, (ddi, off, sc, unit) in CHANNELS.items()
    )
    group = f_varint(1, 100) + f_str(9, "Deere Tractor Data") + chan_defs
    dev0 = f_str(4, "SINTETICO0001") + f_bytes(7, group)
    dev1 = f_str(5, "Plantadeira Teste") + f_double(6, width_m)
    root = (
        f_varint(3, start_ms)
        + f_str(5, "PCGUTESTE")
        + f_bytes(10, f_bytes(2, dev0) + f_bytes(2, dev1))
        + f_bytes(11, f_bytes(1, f_str(1, "{c}") + f_str(2, "Cliente Teste")))
        + f_bytes(12, f_bytes(1, f_str(1, "{f}") + f_str(2, "Fazenda Teste")))
        + f_bytes(13, f_bytes(1, f_str(1, "{t}") + f_str(2, "Talhao Teste")))
    )
    out = block(f_varint(1, 3) + f_bytes(3, f_str(4, "10.30.0-test")))
    out += block(f_varint(1, 1) + f_bytes(5, root))

    target = {1: int(speed_kmh * 1000), 2: int(fuel_lph * 20), 3: int(rpm * 8)}
    last = dict.fromkeys(CHANNELS, 0)
    lat, lon = lat0, lon0
    n_chunks = int(minutes * 2)
    for k in range(n_chunks):
        ids, entries = [], b""
        for cid in CHANNELS:
            if cid in target:
                vals, dts = [], []
                for _ in range(150):
                    vals.append(zz(target[cid] - last[cid]))
                    last[cid] = target[cid]
                    dts.append(400)
            else:  # contadores: 1 amostra por bloco
                inc = int(fuel_lph * 20 * 30 / 3600 / 20 * 2) if cid == 5 else int(30 / 3600 * 20)
                base = int(fuel0 * 2) if cid == 5 else int(hour0 * 20)
                new = (
                    base + (k + 1) * max(inc, 0)
                    if cid == 5
                    else base + int((k + 1) * 30 / 3600 * 20)
                )
                vals, dts = [zz(new - last[cid])], [60000]
                last[cid] = new
            ids.append(cid)
            entries += f_bytes(3, f_bytes(2, packed(dts)) + f_bytes(3, packed(vals)))
        cols = f_bytes(2, packed(ids)) + entries
        body = f_varint(5, 30000)
        if with_gps:
            step = speed_kmh / 3.6 * 30 / 111_000
            p0 = f_double(1, lat) + f_double(2, lon)
            lat += step
            p1 = f_double(1, lat) + f_double(2, lon)
            body += f_bytes(6, p0) + f_bytes(7, p1)
        body += f_bytes(9, cols)
        out += block(f_varint(1, 2) + f_bytes(4, body))
    return out
