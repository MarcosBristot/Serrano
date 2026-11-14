"""Pasta TASKDATA sintética (ISO 11783-10): pulverizador ISOBUS andando para o norte."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import UTC, datetime

from sistemacampero.domain.ingestao import empacotar_isoxml

INICIO = datetime(2026, 1, 15, 13, 0, 0, tzinfo=UTC)
EPOCA = datetime(1980, 1, 1, tzinfo=UTC)
# DLVs do cabeçalho, na ordem: vazão (149), total (148), largura (67), taxa (2)
DLVS = [0x95, 0x94, 0x43, 0x02]


@dataclass(frozen=True, slots=True)
class CenarioIso:
    minutos: float = 30
    velocidade_kmh: float = 8.0
    vazao_lph: float = 22.0
    largura_m: float = 24.0
    taxa_l_ha: float = 100.0
    hz: int = 1
    so_cabecalho: bool = False


def taskdata(talhao: str = "Lavoura Norte") -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ISO11783_TaskData VersionMajor="4" VersionMinor="2" DataTransferOrigin="1">'
        '<CTR A="CTR1" B="Cliente Teste"/><FRM A="FRM1" B="Fazenda Teste" I="CTR1"/>'
        f'<PFD A="PFD1" C="{talhao}" D="500000" E="CTR1" F="FRM1"/>'
        '<DVC A="DVC1" B="Stara Imperador 3.0" D="A00084000E2B0000" E="STR3000123" '
        'F="FF000000000000" G="FF000000000000"><DET A="DET1" B="1" D="1"/></DVC>'
        '<TSK A="TSK1" B="Pulverização fungicida" C="CTR1" D="FRM1" E="PFD1" G="4">'
        '<TLG A="TLG00001"/></TSK></ISO11783_TaskData>'
    ).encode()


def tlg_xml() -> bytes:
    dlvs = "".join(f'<DLV A="{d:04X}" B="" C="DET1"/>' for d in DLVS)
    return f'<?xml version="1.0"?><TIM A="" D="4"><PTN A="" B="" D=""/>{dlvs}</TIM>'.encode()


def tlg_bin(c: CenarioIso) -> bytes:
    if c.so_cabecalho:
        return b""
    out = b""
    passos = int(c.minutos * 60 * c.hz)
    passo_graus = c.velocidade_kmh / 3.6 / c.hz / 111_320  # para o norte
    t0 = INICIO - EPOCA
    total_mm3 = 0.0
    for k in range(passos):
        ms = int((t0.seconds + k / c.hz) * 1000)
        norte = round((-28.1 + k * passo_graus) / 1e-7)
        leste = round(-52.9 / 1e-7)
        out += struct.pack("<IH", ms, t0.days) + struct.pack("<iiB", norte, leste, 4)
        vazao_mm3s = c.vazao_lph / 3.6e-3
        total_mm3 += vazao_mm3s / c.hz
        valores = [
            round(vazao_mm3s),
            round(total_mm3 / 1000),  # ml
            round(c.largura_m * 1000),  # mm
            round(c.taxa_l_ha / 0.01),  # mm³/m²
        ]
        out += bytes([len(valores)]) + b"".join(
            struct.pack("<Bi", i, v) for i, v in enumerate(valores)
        )
    return out


def construir(c: CenarioIso | None = None) -> bytes:
    """Pacote pronto para o adapter (o que a expansão do .zip grava)."""
    c = c or CenarioIso()
    return empacotar_isoxml("TLG00001", taskdata(), tlg_xml(), tlg_bin(c))
