"""Gerador de .jdl SINTÉTICO com a mesma estrutura do formato real (ver ADR 0005).

Reproduz: âncoras de valor (campo 1) e de tempo (campo 12), primeiro bloco já com valor
acumulado (o caso do arquivo 106a770c), trilha GPS de 5 Hz em canal sem definição,
caixa sudoeste/nordeste por bloco, sentinela -2^31, canais ausentes, contador que começa
em 0 e arquivo só de cabeçalho. Nomes e coordenadas são fictícios.
"""

from __future__ import annotations

import math
import struct
from collections.abc import Callable
from dataclasses import dataclass, field

START_MS = 1_777_543_920_000  # 2026-04-30 10:12:00 UTC
NA = -(2**31)
BLOCO_MS = 30_000
HZ = 5
GPS_CANAL = 9001  # sem definição no cabeçalho, como no arquivo real

Funcao = Callable[[float], float]  # t (s desde o início) -> valor físico


def varint(n: int) -> bytes:
    if n < 0:
        n += 1 << 64
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def zz(n: int) -> int:
    return (n << 1) ^ (n >> 63)


def f_varint(no: int, v: int) -> bytes:
    return varint(no << 3) + varint(v)


def f_bytes(no: int, b: bytes) -> bytes:
    return varint(no << 3 | 2) + varint(len(b)) + b


def f_double(no: int, d: float) -> bytes:
    return varint(no << 3 | 1) + struct.pack("<d", d)


def f_str(no: int, s: str) -> bytes:
    return f_bytes(no, s.encode())


def packed(vals: list[int]) -> bytes:
    return b"".join(varint(v) for v in vals)


def bloco(msg: bytes) -> bytes:
    return b"\x0d" + struct.pack("<I", len(msg)) + msg


@dataclass(frozen=True)
class Canal:
    cid: int
    ddi: int
    offset: float
    escala: float
    unidade: str
    grupo: str
    contador: bool = False


CANAIS: dict[str, Canal] = {
    "speed_kmh": Canal(1, 561, 0.0, 1000.0, "km1hr-1", "Deere Tractor Data"),
    "fuel_rate_lph": Canal(2, 99, 0.0, 20.0, "l1hr-1", "Deere Tractor Data"),
    "engine_rpm": Canal(3, 271, 0.0, 8.0, "RPM", "HLC"),
    "engine_hours": Canal(4, 247, 0.0, 100.0, "hr", "HLC", contador=True),
    "fuel_total_l": Canal(5, 100, 0.0, 2.0, "l", "HLC", contador=True),
    "engine_load_pct": Canal(6, 2109, -125.0, 1.0, "prcnt", "HLC"),
}


def constante(v: float) -> Funcao:
    return lambda _t: v


@dataclass
class Cenario:
    minutos: float
    velocidade_kmh: Funcao = field(default_factory=lambda: constante(8.0))
    vazao_lph: Funcao = field(default_factory=lambda: constante(22.0))
    rpm: Funcao = field(default_factory=lambda: constante(1800.0))
    carga_pct: Funcao = field(default_factory=lambda: constante(60.0))
    horimetro0: float = 661.3
    contador0: float = 11368.5
    largura_m: float | None = 4.95
    gps: str = "trilha"  # trilha | caixa | nenhum | zero
    rumo_graus: float = 0.0  # 0 = norte, 225 = sudoeste
    lat0: float = -28.10
    lon0: float = -52.92
    ancora_inicial: bool = True  # 1º bloco já com valor acumulado (caso real 106a770c)
    omitir: frozenset[str] = frozenset()
    nao_disponivel: frozenset[str] = frozenset()  # canais que só mandam -2^31
    contador_comeca_zero: bool = False  # contadores mandam 0 até o 1º valor real
    teleporte_em_s: float | None = None  # desloca a trilha 2 km a partir deste instante
    so_cabecalho: bool = False
    start_ms: int = START_MS
    plantio: bool = False
    serial: str = "SINTETICO0001"


def _bruto(canal: Canal, valor: float) -> int:
    return round((valor - canal.offset) * canal.escala)


def construir(c: Cenario) -> bytes:
    canais = {k: v for k, v in CANAIS.items() if k not in c.omitir}
    defs = b"".join(
        f_bytes(
            5,
            f_varint(1, ch.cid)
            + f_varint(2, ch.ddi)
            + f_double(3, ch.offset)
            + f_double(4, ch.escala)
            + f_str(5, ch.unidade),
        )
        for ch in canais.values()
    )
    grupos = f_bytes(7, f_varint(1, 100) + f_str(9, "Deere Tractor Data") + defs)
    grupos += f_bytes(7, f_varint(1, 101) + f_str(9, "HLC"))
    if c.plantio:
        grupos += f_bytes(7, f_varint(1, 102) + f_str(9, "Plantio"))
    dev0 = f_str(4, c.serial) + grupos
    dev1 = f_str(5, "Plantadeira Teste") + (f_double(6, c.largura_m) if c.largura_m else b"")
    root = (
        f_varint(3, c.start_ms)
        + f_str(5, "PCGUTESTE")
        + f_bytes(10, f_bytes(2, dev0) + f_bytes(2, dev1))
        + f_bytes(11, f_bytes(1, f_str(1, "{cli}") + f_str(2, "Cliente Teste")))
        + f_bytes(12, f_bytes(1, f_str(1, "{faz}") + f_str(2, "Fazenda Teste")))
        + f_bytes(13, f_bytes(1, f_str(1, "{tal}") + f_str(2, "Talhao Teste")))
    )
    out = bloco(f_varint(1, 3) + f_bytes(3, f_str(4, "10.30.0-teste")))
    out += bloco(f_varint(1, 1) + f_bytes(5, root))
    if c.so_cabecalho:
        return out

    funcoes: dict[str, Funcao] = {
        "speed_kmh": c.velocidade_kmh,
        "fuel_rate_lph": c.vazao_lph,
        "engine_rpm": c.rpm,
        "engine_load_pct": c.carga_pct,
    }
    passo_s = 1.0 / HZ
    n_blocos = math.ceil(c.minutos * 60_000 / BLOCO_MS)

    # Integra posição, horímetro e contador amostra a amostra (5 Hz).
    total_amostras = n_blocos * BLOCO_MS // 1000 * HZ
    tempos = [i * passo_s for i in range(total_amostras)]
    lat, lon, horas, litros = [], [], [], []
    la, lo, h, li = c.lat0, c.lon0, c.horimetro0, c.contador0
    rumo = math.radians(c.rumo_graus)
    for t in tempos:
        v = max(c.velocidade_kmh(t), 0.0)
        passo_m = v / 3.6 * passo_s
        la += passo_m * math.cos(rumo) / 111_320
        lo += passo_m * math.sin(rumo) / (111_320 * math.cos(math.radians(la)))
        desloc = 2000 / 111_320 if c.teleporte_em_s is not None and t >= c.teleporte_em_s else 0
        lat.append(la + desloc)
        lon.append(lo)
        if c.rpm(t) > 400:
            h += passo_s / 3600
        li += max(c.vazao_lph(t), 0.0) * passo_s / 3600
        horas.append(h)
        litros.append(li)

    corrente = dict.fromkeys(canais, 0)  # valor bruto acumulado por canal
    gps_corrente = [0, 0, 0]  # t_ms, lat_ng, lon_ng
    for k in range(n_blocos):
        t_bloco_ms = k * BLOCO_MS
        i0, i1 = k * BLOCO_MS // 1000 * HZ, (k + 1) * BLOCO_MS // 1000 * HZ
        ids: list[int] = []
        entradas = b""
        for nome, ch in canais.items():
            if ch.contador:
                # 1 amostra no fim do bloco (como os contadores reais)
                serie = horas if nome == "engine_hours" else litros
                valores_fis = [serie[i1 - 1]]
                dts = [round(BLOCO_MS / 0.5)]
            else:
                valores_fis = [funcoes[nome](tempos[i]) for i in range(i0, i1)]
                dts = [round(passo_s * 1000 / 0.5)] * len(valores_fis)
            if nome in c.nao_disponivel:
                brutos = [NA] * len(valores_fis)
            elif ch.contador and c.contador_comeca_zero and k == 0:
                brutos = [0]
            else:
                brutos = [_bruto(ch, v) for v in valores_fis]
            campos = b""
            primeiro_absoluto = k == 0 and not c.ancora_inicial
            if not primeiro_absoluto:
                if k == 0:
                    corrente[nome] = brutos[0]  # âncora inicial = valor já acumulado
                campos += f_double(1, float(corrente[nome]))
            deltas = []
            for b in brutos:
                deltas.append(zz(b - corrente[nome]))
                corrente[nome] = b
            campos += f_bytes(2, packed(dts)) + f_bytes(3, packed(deltas)) + f_varint(4, 0)
            campos += f_varint(12, t_bloco_ms)
            ids.append(ch.cid)
            entradas += f_bytes(3, campos)

        corpo = f_varint(5, BLOCO_MS)
        if c.gps in ("trilha", "caixa", "zero"):
            la_b = [0.0] * (i1 - i0) if c.gps == "zero" else lat[i0:i1]
            lo_b = [0.0] * (i1 - i0) if c.gps == "zero" else lon[i0:i1]
            sw = f_double(1, min(la_b)) + f_double(2, min(lo_b))
            ne = f_double(1, max(la_b)) + f_double(2, max(lo_b))
            corpo += f_bytes(6, sw) + f_bytes(7, ne)
            if c.gps in ("trilha", "zero"):
                g = b""
                if k > 0:
                    g += f_double(1, float(gps_corrente[1])) + f_double(2, float(gps_corrente[2]))
                    g += f_varint(26, gps_corrente[0])
                dts_g, dla, dlo = [], [], []
                for j in range(i1 - i0):
                    t_ms = round(t_bloco_ms + (j + 1) * passo_s * 1000)
                    a_ng, b_ng = round(la_b[j] * 1e9), round(lo_b[j] * 1e9)
                    dts_g.append(zz(t_ms - gps_corrente[0]))
                    dla.append(zz(a_ng - gps_corrente[1]))
                    dlo.append(zz(b_ng - gps_corrente[2]))
                    gps_corrente = [t_ms, a_ng, b_ng]
                g += (
                    f_bytes(10, packed(dts_g)) + f_bytes(12, packed(dla)) + f_bytes(13, packed(dlo))
                )
                ids.append(GPS_CANAL)
                entradas += f_bytes(3, g)

        colunas = f_bytes(2, packed(ids)) + entradas
        corpo += f_bytes(9, colunas)
        out += bloco(f_varint(1, 2) + f_bytes(4, corpo))
    return out
