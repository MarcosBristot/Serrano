"""Métricas por sessão (combustível, horas, distância, área trabalhada, L/ha)."""

from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

import numpy as np
import pandas as pd

from sistemacampero.schema.universal import ParsedSession

MIN_WORK_SPEED_KMH = 1.0   # abaixo disso, com motor ligado = parado (ociosidade)
MIN_AREA_HA = 0.05         # não calcula L/ha com área trabalhada menor que isso


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371000.0
    p1, p2 = radians(a[0]), radians(b[0])
    dphi, dl = p2 - p1, radians(b[1] - a[1])
    h = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * r * asin(sqrt(h))


@dataclass
class SessionMetrics:
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
    l_per_ha: float | None          # todo o combustível com motor ligado / área trabalhada
    l_per_ha_work: float | None     # só combustível em movimento / área trabalhada
    gps_coverage: float             # fração das amostras com posição

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def compute_session_metrics(session: ParsedSession, clean: pd.DataFrame) -> SessionMetrics | None:
    if clean.empty:
        return None
    df = clean
    on = df["engine_on"]
    speed = df["speed_kmh"]
    moving = on & (speed >= MIN_WORK_SPEED_KMH)
    idle = on & (speed < MIN_WORK_SPEED_KMH)
    rate = df["fuel_rate_lph"]

    def _h(mask) -> float:
        return float(mask.sum()) / 3600.0

    def _l(mask) -> float | None:
        v = rate[mask]
        return float(v.fillna(0).sum()) / 3600.0 if len(v) and v.notna().any() else None

    def _first_last(col):
        s = df[col].dropna()
        return (float(s.iloc[-1] - s.iloc[0]) if len(s) >= 2 else None)

    work_h, idle_h = _h(moving), _h(idle)
    fuel_work, fuel_idle = _l(moving), _l(idle)
    fuel_integral = _l(on)
    work_dist = float((speed[moving].fillna(0)).sum()) / 3600.0  # km

    width = session.context.implement_width_m
    area = (work_dist * 1000.0 * width / 10000.0) if (width and work_dist > 0) else None
    have_area = area is not None and area >= MIN_AREA_HA

    return SessionMetrics(
        source_sha256=session.source_sha256,
        source_file=session.source_file,
        machine_serial=session.machine.serial,
        field_name=session.context.field_name,
        field_guid=session.context.field_guid,
        operation=session.context.operation,
        implement_name=session.context.implement_name,
        implement_width_m=width,
        start_utc=df["ts"].iloc[0],
        end_utc=df["ts"].iloc[-1],
        duration_h=len(df) / 3600.0,
        engine_on_h=_h(on),
        work_h=work_h,
        idle_h=idle_h,
        engine_hours_delta=_first_last("engine_hours"),
        fuel_integral_l=fuel_integral,
        fuel_counter_l=_first_last("fuel_total_l"),
        fuel_work_l=fuel_work,
        fuel_idle_l=fuel_idle,
        lph_work=(fuel_work / work_h) if fuel_work is not None and work_h > 0.01 else None,
        lph_idle=(fuel_idle / idle_h) if fuel_idle is not None and idle_h > 0.01 else None,
        work_distance_km=work_dist,
        avg_speed_work_kmh=(work_dist / work_h) if work_h > 0.01 else None,
        worked_area_ha=area if have_area else None,
        ha_per_h=(area / work_h) if have_area and work_h > 0.01 else None,
        l_per_ha=(fuel_integral / area) if have_area and fuel_integral else None,
        l_per_ha_work=(fuel_work / area) if have_area and fuel_work else None,
        gps_coverage=float(df["gps_valid"].mean()),
    )


def daily_field_metrics(sessions: pd.DataFrame) -> pd.DataFrame:
    """Agrega sessões por (máquina, dia local, talhão, operação) — equivalente ao
    ``calcular_metricas_dia_talhao`` do protótipo, mas sobre dado real."""
    if sessions.empty:
        return sessions
    s = sessions.copy()
    s["date_local"] = s["start_utc"].dt.tz_convert("America/Sao_Paulo").dt.date
    keys = ["machine_serial", "date_local", "field_name", "operation"]
    for k in keys:
        s[k] = s[k].fillna("(não informado)") if k in ("field_name", "operation") else s[k]
    agg = s.groupby(keys, dropna=False).agg(
        sessoes=("source_sha256", "count"),
        engine_on_h=("engine_on_h", "sum"),
        work_h=("work_h", "sum"),
        idle_h=("idle_h", "sum"),
        fuel_l=("fuel_integral_l", "sum"),
        fuel_work_l=("fuel_work_l", "sum"),
        fuel_idle_l=("fuel_idle_l", "sum"),
        area_ha=("worked_area_ha", "sum"),
        distance_km=("work_distance_km", "sum"),
    ).reset_index()
    agg["lph_work"] = np.where(agg.work_h > 0.01, agg.fuel_work_l / agg.work_h, np.nan)
    agg["l_per_ha"] = np.where(agg.area_ha >= MIN_AREA_HA, agg.fuel_l / agg.area_ha, np.nan)
    agg["ha_per_h"] = np.where(agg.work_h > 0.01, agg.area_ha / agg.work_h, np.nan)
    agg["idle_pct"] = np.where(agg.engine_on_h > 0, 100 * agg.idle_h / agg.engine_on_h, np.nan)
    return agg
