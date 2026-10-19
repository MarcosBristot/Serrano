"""Caso de uso: publicação dos resultados no banco analítico (Supabase/PostGIS)."""

from __future__ import annotations

import hashlib
import logging

import pandas as pd

from sistemacampero.domain.entities import Alert, SessionMetrics, WorkSession
from sistemacampero.domain.ports import SessionStore, TelemetryPublisher
from sistemacampero.domain.services.decimation import decimate
from sistemacampero.domain.services.geo import FieldLocator

logger = logging.getLogger(__name__)

_SAMPLE_COLUMNS = {
    "lat": "latitude",
    "lon": "longitude",
    "speed_kmh": "speed_kmh",
    "speed_alt_kmh": "speed_alt_kmh",
    "engine_rpm": "engine_rpm",
    "engine_load_pct": "engine_load_pct",
    "fuel_rate_lph": "fuel_rate_lph",
    "fuel_total_l": "fuel_total_l",
    "engine_hours": "engine_hours",
    "engine_on": "engine_on",
}
_METRIC_EXCLUDE = {"source_file", "start_utc", "end_utc"}


def alert_id(alert: Alert, rules_version: str) -> str:
    """Id determinístico do alerta (reprocessar com as mesmas regras não duplica)."""
    raw = f"{alert.source_sha256}|{alert.kind}|{alert.start_utc}|{alert.value}|{rules_version}"
    return hashlib.sha1(raw.encode()).hexdigest()


class PublishingService:
    """Converte sessão/métricas/alertas em linhas e envia ao banco, de forma idempotente."""

    def __init__(
        self,
        store: SessionStore,
        publisher: TelemetryPublisher,
        step_s: int = 5,
    ) -> None:
        self._store = store
        self._publisher = publisher
        self._step = step_s

    def publish_session(
        self,
        session: WorkSession,
        df: pd.DataFrame,
        metrics: SessionMetrics,
        alerts: list[Alert],
        rules_version: str,
        locator: FieldLocator | None = None,
    ) -> int:
        """Publica uma sessão. Devolve quantas amostras foram enviadas."""
        sha = session.source_sha256
        serial = session.machine.serial
        samples_df = decimate(df, self._step)
        talhoes = (
            locator.field_ids(samples_df["lat"].to_numpy(), samples_df["lon"].to_numpy())
            if locator
            else [None] * len(samples_df)
        )
        samples = self._sample_rows(samples_df, serial, sha, talhoes)

        session_row = {
            "source_sha256": sha,
            "source_file": session.source_file,
            "machine_serial": serial,
            "talhao_id": metrics.talhao_id,
            "adapter": session.adapter,
            "adapter_version": session.adapter_version,
            "operation": session.context.operation,
            "implement_name": session.context.implement_name,
            "implement_width_m": session.context.implement_width_m,
            "started_at": metrics.start_utc,
            "ended_at": metrics.end_utc,
        }
        metrics_row = {
            "session_sha256": sha,
            "rules_version": rules_version,
            **{k: v for k, v in metrics.to_dict().items() if k not in _METRIC_EXCLUDE},
        }
        metrics_row.pop("source_sha256", None)
        alert_rows = [
            {
                "id": alert_id(a, rules_version),
                "session_sha256": sha,
                "rules_version": rules_version,
                "kind": a.kind,
                "severity": a.severity,
                "start_utc": a.start_utc,
                "end_utc": a.end_utc,
                "value": a.value,
                "message": a.message,
                "details": a.details,
            }
            for a in alerts
        ]
        self._publisher.publish_session(session_row, samples, metrics_row, alert_rows)
        self._store.mark_published(sha, rules_version)
        logger.info(
            "sessão %s publicada: %d amostras, %d alertas", sha[:8], len(samples), len(alerts)
        )
        return len(samples)

    @staticmethod
    def _sample_rows(
        samples_df: pd.DataFrame, serial: str, sha: str, talhoes: list[str | None]
    ) -> list[dict]:
        out = samples_df[["ts", *_SAMPLE_COLUMNS]].rename(columns=_SAMPLE_COLUMNS)
        out = out.rename(columns={"ts": "timestamp"})
        out.insert(0, "machine_serial", serial)
        out.insert(1, "session_sha256", sha)
        out["talhao_id"] = talhoes
        out["timestamp"] = out["timestamp"].map(lambda t: t.isoformat())
        out = out.astype(object).where(out.notna(), None)
        return out.to_dict(orient="records")
