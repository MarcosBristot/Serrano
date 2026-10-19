"""Entidades e objetos de valor do domínio (agnósticos de fabricante e de infraestrutura).

Convenções do schema universal de telemetria:

* tempo em UTC; unidades métricas (km/h, L, L/h, h, graus decimais WGS84);
* campo ausente = ``NaN``/``None`` (nunca 0). Ex.: ``fuel_level_l`` é ``NaN`` para o
  John Deere Gen4, que informa vazão e contador acumulado, mas não nível de tanque;
* ``engine_on`` é derivado (RPM > ``ENGINE_ON_RPM``) quando o fabricante não o fornece.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

ENGINE_ON_RPM = 400.0

#: Colunas do DataFrame de amostras limpas a 1 Hz (ordem = ordem de persistência).
SAMPLE_COLUMNS: dict[str, str] = {
    "ts": "datetime64[ns, UTC]",
    "lat": "float64",
    "lon": "float64",
    "gps_valid": "bool",  # posição real (interpolada entre pontos de ~30 s)
    "speed_kmh": "float64",
    "speed_alt_kmh": "float64",  # segundo sensor de velocidade
    "engine_rpm": "float64",
    "engine_load_pct": "float64",
    "fuel_rate_lph": "float64",  # vazão instantânea
    "fuel_total_l": "float64",  # contador acumulado do motor
    "fuel_level_l": "float64",  # nível do tanque (NaN se o fabricante não informa)
    "engine_hours": "float64",  # horímetro acumulado
    "engine_on": "bool",
}


def empty_samples() -> pd.DataFrame:
    """DataFrame vazio no schema universal."""
    return pd.DataFrame({c: pd.Series(dtype=t) for c, t in SAMPLE_COLUMNS.items()})


@dataclass(frozen=True)
class MachineInfo:
    """Máquina que gerou o arquivo (identificada pelo serial do fabricante)."""

    manufacturer: str
    serial: str
    model_hint: str | None = None
    display_serial: str | None = None


@dataclass(frozen=True)
class ContextInfo:
    """Contexto operacional informado no arquivo (cliente, fazenda, talhão, implemento)."""

    client_name: str | None = None
    farm_name: str | None = None
    field_guid: str | None = None
    field_name: str | None = None
    implement_name: str | None = None
    implement_width_m: float | None = None
    operation: str | None = None  # ex.: "plantio"


@dataclass
class WorkSession:
    """Sessão de trabalho (um arquivo do monitor) já no schema universal."""

    source_file: str
    source_sha256: str
    adapter: str
    adapter_version: str
    machine: MachineInfo
    context: ContextInfo
    started_at: datetime | None
    samples: pd.DataFrame
    gps_chunks: list[tuple[float, tuple | None, tuple | None]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FieldBoundary:
    """Talhão (contorno externo) usado para associar posições GPS a um talhão."""

    id: str
    name: str
    geometry: dict[str, Any]  # GeoJSON Polygon, WGS84
    farm: str | None = None
    client: str | None = None
    area_ha: float | None = None
    external_guid: str | None = None


@dataclass
class SessionMetrics:
    """Métricas calculadas de uma sessão (resultado da etapa 4)."""

    source_sha256: str
    source_file: str
    machine_serial: str
    field_name: str | None
    field_guid: str | None
    operation: str | None
    implement_name: str | None
    implement_width_m: float | None
    start_utc: pd.Timestamp
    end_utc: pd.Timestamp
    duration_h: float
    engine_on_h: float
    work_h: float
    idle_h: float
    engine_hours_delta: float | None
    fuel_integral_l: float | None
    fuel_counter_l: float | None
    fuel_work_l: float | None
    fuel_idle_l: float | None
    lph_work: float | None
    lph_idle: float | None
    work_distance_km: float
    avg_speed_work_kmh: float | None
    worked_area_ha: float | None
    ha_per_h: float | None
    l_per_ha: float | None  # todo o combustível com motor ligado / área trabalhada
    l_per_ha_work: float | None  # só combustível em movimento / área trabalhada
    gps_coverage: float  # fração das amostras com posição
    talhao_id: str | None = None  # talhão por junção espacial (quando há contornos)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class Alert:
    """Alerta gerado por uma regra (resultado da etapa 4)."""

    kind: str  # ociosidade | vazao_alta | contador_divergente | gps_salto | sem_gps | l_ha_alto
    severity: str  # info | atencao | alto
    source_sha256: str
    machine_serial: str
    start_utc: pd.Timestamp | None
    end_utc: pd.Timestamp | None
    value: float | None
    message: str
    field_name: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)
