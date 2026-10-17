"""Schema universal (agnóstico de fabricante) dos dados limpos.

Todo adapter de fabricante deve devolver um ``ParsedSession``. A etapa seguinte do
pipeline (sanitização, métricas, regras) só conhece este schema.

Convenções:
  * tempo em UTC; unidades métricas (km/h, L, L/h, h, graus decimais WGS84);
  * campo ausente = NaN/None (nunca 0). Ex.: ``fuel_level_l`` é NaN para John Deere
    Gen4, que não expõe nível de tanque (só vazão e contador acumulado);
  * ``engine_on`` é derivado (RPM > ``ENGINE_ON_RPM``) quando o fabricante não o fornece.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

ENGINE_ON_RPM = 400.0

# Colunas do DataFrame de amostras limpas a 1 Hz (ordem = ordem da tabela no banco).
SAMPLE_COLUMNS: dict[str, str] = {
    "ts": "datetime64[ns, UTC]",
    "lat": "float64",
    "lon": "float64",
    "gps_valid": "bool",           # há posição real (interpolada entre pontos de 30 s)
    "speed_kmh": "float64",
    "speed_alt_kmh": "float64",    # segundo sensor de velocidade (DDI 560)
    "engine_rpm": "float64",
    "engine_load_pct": "float64",  # torque % (DDI 2109)
    "fuel_rate_lph": "float64",    # vazão instantânea
    "fuel_total_l": "float64",     # contador acumulado do motor (L)
    "fuel_level_l": "float64",     # nível do tanque (NaN se o fabricante não fornece)
    "engine_hours": "float64",     # horímetro acumulado (h)
    "engine_on": "bool",
}


@dataclass
class MachineInfo:
    manufacturer: str
    serial: str
    model_hint: str | None = None
    display_serial: str | None = None


@dataclass
class ContextInfo:
    client_name: str | None = None
    farm_name: str | None = None
    field_guid: str | None = None
    field_name: str | None = None
    implement_name: str | None = None
    implement_width_m: float | None = None
    operation: str | None = None  # ex.: "plantio" (quando o fabricante informa)


@dataclass
class ParsedSession:
    """Uma sessão de trabalho (um arquivo do pendrive) já no schema universal."""

    source_file: str
    source_sha256: str
    adapter: str                 # ex.: "john_deere_gen4"
    adapter_version: str
    machine: MachineInfo
    context: ContextInfo
    started_at: datetime | None
    samples: pd.DataFrame        # colunas = SAMPLE_COLUMNS
    gps_chunks: list[tuple[float, tuple | None, tuple | None]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def empty_samples() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=t) for c, t in SAMPLE_COLUMNS.items()})
