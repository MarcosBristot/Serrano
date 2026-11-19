"""Registro TSIP sintético de monitor Trimble TMX-2050 (pacotes 0x1A com NMEA, 0x5F com texto)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

DLE, ETX = 0x10, 0x03


@dataclass(frozen=True)
class CenarioTrimble:
    minutos: float = 30
    velocidade_kmh: float = 8.0
    lat0: float = -28.5111
    lon0: float = -52.7539
    inicio: datetime = datetime(2026, 11, 11, 15, 0, 0, tzinfo=UTC)
    so_cabecalho: bool = False  # monitor ligado sem sinal de GPS


def _pacote(ident: int, corpo: bytes) -> bytes:
    escapado = corpo.replace(bytes([DLE]), bytes([DLE, DLE]))
    return bytes([DLE, ident]) + escapado + bytes([DLE, ETX])


def _nmea(frase: str) -> bytes:
    soma = 0
    for c in frase:
        soma ^= ord(c)
    return f"${frase}*{soma:02X}\r\n".encode()


def _ddmm(graus: float, eixo: str) -> tuple[str, str]:
    hem = ("S" if graus < 0 else "N") if eixo == "lat" else ("W" if graus < 0 else "E")
    g = abs(graus)
    inteiro = int(g)
    minutos = (g - inteiro) * 60
    largura = 2 if eixo == "lat" else 3
    return f"{inteiro:0{largura}d}{minutos:09.6f}", hem


def construir(c: CenarioTrimble) -> bytes:
    saida = bytearray(
        _pacote(0x5F, b"\x01Created name N:/gpsData/TMX_LogAg_1_20261111_1500_001.tsip")
    )
    # pacote binário com um byte 0x10 dentro (testa o escape do DLE)
    saida += _pacote(0x8F, bytes([0xA2, 0x10, 0x01, 0x10]))
    if c.so_cabecalho:
        saida += _pacote(0x1A, b"\x01&" + _nmea("GPGGA,150000.00,,,,,0,00,99.9,,M,,M,,"))
        return bytes(saida)
    passo_graus = (c.velocidade_kmh / 3.6) / 111_320.0  # para o norte
    for s in range(int(c.minutos * 60)):
        t = c.inicio + timedelta(seconds=s)
        lat = c.lat0 + passo_graus * s
        hora = t.strftime("%H%M%S.00")
        la, hla = _ddmm(lat, "lat")
        lo, hlo = _ddmm(c.lon0, "lon")
        nos = c.velocidade_kmh / 1.852
        saida += _pacote(
            0x1A,
            b"\x01&"
            + _nmea(f"GPRMC,{hora},A,{la},{hla},{lo},{hlo},{nos:05.2f},0.0,{t:%d%m%y},12.0,W,D"),
        )
        saida += _pacote(
            0x1A,
            b"\x01&" + _nmea(f"GPGGA,{hora},{la},{hla},{lo},{hlo},4,27,0.5,423.0,M,5.8,M,6.0,0001"),
        )
        saida += _pacote(
            0x1A, b"\x01&" + _nmea(f"GPVTG,000.0,T,,,{nos:06.2f},N,{c.velocidade_kmh:06.2f},K,D")
        )
        if s % 60 == 0:
            saida += _pacote(
                0x5F, b"\x01GNSS S[27:27] Q[5:5] H[0.5] " + str(math.floor(s / 60)).encode()
            )
    return bytes(saida)
