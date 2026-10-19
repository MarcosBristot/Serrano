"""Consultas de leitura sobre o workspace local (modo sem Supabase)."""

from __future__ import annotations

import json

import pandas as pd

from sistemacampero.domain.services.decimation import decimate
from sistemacampero.infrastructure.persistence.workspace import LocalWorkspace


def _records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records", date_format="iso"))


class LocalTelemetryQueries:
    """Implementa ``TelemetryQueries`` lendo os Parquet de resultados."""

    def __init__(self, store: LocalWorkspace) -> None:
        self._store = store

    def _sessions_df(self) -> pd.DataFrame:
        df = self._store.load_results("sessions")
        return df if df is not None else pd.DataFrame()

    def track(self, machine_serial: str, talhao_id: str | None, limit: int) -> list[dict]:
        sessions = self._sessions_df()
        if sessions.empty:
            return []
        sessions = sessions[sessions["machine_serial"] == machine_serial]
        if talhao_id:
            sessions = sessions[sessions["talhao_id"] == talhao_id]
        points: list[pd.DataFrame] = []
        remaining = limit
        for sha in sessions.sort_values("start_utc")["source_sha256"]:
            if remaining <= 0:
                break
            _, df = self._store.load_session(sha)
            df = decimate(df[df["gps_valid"]], 5).head(remaining)
            points.append(df)
            remaining -= len(df)
        if not points:
            return []
        out = pd.concat(points)[
            ["ts", "lat", "lon", "speed_kmh", "fuel_rate_lph", "engine_rpm", "engine_on"]
        ]
        out.columns = [
            "timestamp",
            "latitude",
            "longitude",
            "speed_kmh",
            "fuel_rate_lph",
            "engine_rpm",
            "engine_on",
        ]
        return _records(out)

    def sessions(self, machine_serial: str | None, limit: int, offset: int) -> dict:
        df = self._sessions_df()
        if machine_serial and not df.empty:
            df = df[df["machine_serial"] == machine_serial]
        df = df.sort_values("start_utc", ascending=False) if not df.empty else df
        return {"total": len(df), "items": _records(df.iloc[offset : offset + limit])}

    def alerts(self, machine_serial: str | None, kind: str | None, limit: int, offset: int) -> dict:
        df = self._store.load_results("alerts")
        if df is None or df.empty:
            return {"total": 0, "items": []}
        if machine_serial:
            df = df[df["machine_serial"] == machine_serial]
        if kind:
            df = df[df["kind"] == kind]
        df = df.sort_values("start_utc", ascending=False)
        return {"total": len(df), "items": _records(df.iloc[offset : offset + limit])}

    def metric_rows(self, machine_serial: str) -> list[dict]:
        df = self._sessions_df()
        if df.empty:
            return []
        return _records(df[df["machine_serial"] == machine_serial])
