"""Par .fdl + .fdd sintético do GreenStar 3, no formato descrito em ``parsers/john_deere_gs3/rcd.py``.

Colheitadeira de 5 seções (7,6 m) andando para o norte: umidade, massa, plataforma e seções
no bloco fixo; consumo e velocidade como valores crus; GPS e distância em delta.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import UTC, datetime

from sistemacampero.domain.ingestao import empacotar_rcd

INICIO = datetime(2026, 3, 26, 18, 14, 58, tzinfo=UTC)
_UUID = b"6363bd9a-0000-1000-5690-e1e1e1464fe0"
# (columnID, tipo, cru, resolução, base, representação no .fdl)
_COLUNAS = [
    ("MeasElement1", 3, False, 0.01, 15.0, "vrHarvestMoisture"),
    ("MeasElement2", 3, False, 0.001, 0.0, "vrYieldWetMass"),
    ("MeasElement3", 1, False, 0, 0, "dtHeaderStatus"),
    *[(f"Section{n}_State", 1, False, 0, 0, "dtRecordingStatus") for n in range(1, 6)],
    ("TgtElement36", 5, True, 0, 0, "vrFuelRatePerHour"),
    ("TgtElement38", 5, True, 0, 0, "vrVehicleSpeed"),
    ("GPSLatitude_5140", 4, False, 1e-9, -28.1, "vrLatitude"),
    ("GPSLongitude_5140", 4, False, 1e-9, -52.9, "vrLongitude"),
    ("DeltaDistance_5140", 3, False, 1.0, 0.0, "vrDistanceTraveled"),
    ("ElapsedTime", 4, False, 1.0, 0.0, "vrElapsedTime"),
]


@dataclass(frozen=True, slots=True)
class CenarioGs3:
    minutos: float = 30
    velocidade_kmh: float = 8.0
    vazao_lph: float = 22.0
    umidade_pct: float = 17.5
    massa_kg_s: float = 4.0
    so_cabecalho: bool = False


def _nome(texto: str) -> bytes:
    b = texto.encode()
    return struct.pack("<H", len(b)) + b


def _cabecalho() -> bytes:
    out = struct.pack("<H", 1) + _nome(_UUID.decode()) + b"\x01\x00\x02\x00"
    out += struct.pack("<H", len(_COLUNAS))
    for nome, tipo, cru, res, base, _ in _COLUNAS:
        n = nome.encode()
        out += struct.pack("<3H", tipo, len(n) + 3, len(n)) + n
        if tipo == 1:
            opcoes = [b"dtiOn", b"dtiOff"]
            corpo = b"".join(struct.pack("<H", len(o)) + o for o in opcoes)
            out += bytes([0]) + struct.pack("<2H", len(opcoes), len(corpo)) + corpo
        else:
            out += bytes([1 if cru else 0]) + struct.pack("<H3d", 24, res, 0.0, base)
    return out


def _marcado_double(v: float) -> bytes:
    return struct.pack("<2Hd", 3, 8, v)


def construir_fdd(c: CenarioGs3) -> bytes:
    out = _cabecalho()
    if c.so_cabecalho:
        return out
    passo_cm = round(c.velocidade_kmh / 0.036)  # cm por segundo
    passo_lat = round(c.velocidade_kmh / 3.6 / 111_320 / 1e-9)  # nano-graus por segundo
    for k in range(int(c.minutos * 60)):
        primeiro = k == 0
        # máscara B: consumo (bit 0) e velocidade (bit 1) só no primeiro registro; depois repetem (A)
        a, b = (0, 0b11) if primeiro else (0b11, 0)
        reg = (
            struct.pack("<HBBI", 2, 1, 0, 0x70) + a.to_bytes(4, "little") + b.to_bytes(3, "little")
        )
        umidade = round((c.umidade_pct - 15.0) / 0.01) if primeiro else 0
        massa = round(c.massa_kg_s / 0.001) if primeiro else 0
        reg += struct.pack("<2h", umidade, massa) + struct.pack("<6H", 0, 0, 0, 0, 0, 0)
        reg += struct.pack("<ii", 0 if primeiro else passo_lat, 0)
        reg += struct.pack("<h", passo_cm if primeiro else 0)
        reg += struct.pack("<i", 0 if primeiro else 1000)
        reg += struct.pack("<2Hf", 3, 4, 2.0)  # valor de controle
        if primeiro:
            reg += _marcado_double(c.vazao_lph) + _marcado_double(c.velocidade_kmh)
        out += reg
    return out + b"\x00\x00"


def construir_fdl() -> bytes:
    colunas = "".join(
        f'<VariableNumberColumn columnID="{n}" variableRepresentation="{r}" />'
        if t != 1
        else f'<DefinedTypeColumn columnID="{n}" definedTypeRepresentation="{r}" />'
        for n, t, _, _, _, r in _COLUNAS
    )
    secoes = "".join(
        f'<Section id="{n}"><vrSectionWidth value="1520.000000" sourceUOM="mm" /></Section>'
        for n in range(1, 6)
    )
    ts = INICIO.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return (
        '<?xml version="1.0" encoding="ISO-8859-1"?>'
        '<RCDLogFile xmlns="urn:schemas-johndeere-com:RCD:LogFile"'
        ' xmlns:rcdsetup="urn:schemas-johndeere-com:RCD:Setup">'
        '<rcdsetup:Client name="Cliente Teste" erid="{641b36bd-0000-1000-59ec-e1e1e1464fe0}" />'
        '<rcdsetup:Field name="Talhao Teste" erid="{6432e28f-0000-1000-786b-e1e1e1464fe0}" />'
        '<rcdsetup:Machine serialNumber="1CQS540ATG0000001" />'
        '<rcdsetup:MachineModel name="S540" />'
        '<rcdsetup:Crop name="Soja"><rcdsetup:CropVariety'
        ' erid="{5bd857bf-0000-1000-403a-e1e1e1464fe0}" name="Zeus" /></rcdsetup:Crop>'
        '<rcdsetup:ImplementModel name="625F" />'
        f'<LogTaskRegion timeStamp="{ts}" timeColumnID="ElapsedTime" logInterval="1000">'
        '<ProductRef eridRef="{5bd857bf-0000-1000-403a-e1e1e1464fe0}" />'
        f"{secoes}{colunas}"
        '<LogDataBlock logDataProcessor="EvenByteDelta" /></LogTaskRegion></RCDLogFile>'
    ).encode("latin-1")


def construir(c: CenarioGs3 | None = None) -> bytes:
    """Pacote pronto para o adapter (o que a expansão do .zip grava)."""
    return empacotar_rcd(construir_fdl(), construir_fdd(c or CenarioGs3()))
