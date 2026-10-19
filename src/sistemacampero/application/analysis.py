"""Caso de uso: etapas 4–5 (métricas + regras) sobre o dado limpo.

Pode ser repetido com outra ``RuleConfig`` sem reler nem reprocessar o bruto.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, replace
from datetime import UTC, datetime

import pandas as pd

from sistemacampero.domain.entities import (
    Alert,
    FieldBoundary,
    SessionMetrics,
    WorkSession,
)
from sistemacampero.domain.ports import FieldSource, SessionStore
from sistemacampero.domain.services import metrics as metrics_svc
from sistemacampero.domain.services import rules
from sistemacampero.domain.services.geo import FieldLocator
from sistemacampero.domain.services.rules import RuleConfig

logger = logging.getLogger(__name__)

BaselineKey = tuple[str, str | None, str | None]
MIN_BASELINE_WORK_H = 0.25


class AnalysisService:
    """Calcula métricas por sessão, alertas e agregados diários."""

    def __init__(
        self,
        store: SessionStore,
        field_source: FieldSource | None = None,
        config: RuleConfig | None = None,
    ) -> None:
        self._store = store
        self._field_source = field_source
        self.config = config or RuleConfig()
        self._locator: FieldLocator | None = None

    # ------------------------------------------------------------------ talhões
    def locator(self, refresh: bool = False) -> FieldLocator | None:
        """Índice espacial dos talhões (carregado uma vez e reutilizado)."""
        if self._field_source is None:
            return None
        if self._locator is None or refresh:
            fields = self._field_source.list_fields()
            self._locator = FieldLocator(fields)
            logger.info("%d talhões carregados para a junção espacial", len(fields))
        return self._locator

    def _locate(self, df: pd.DataFrame) -> FieldBoundary | None:
        locator = self.locator()
        return locator.dominant_field(df) if locator else None

    # ------------------------------------------------------------------ sessão
    def measure(
        self, session: WorkSession, df: pd.DataFrame
    ) -> tuple[SessionMetrics | None, WorkSession]:
        """Métricas de uma sessão (sem alertas). Devolve a sessão enriquecida com o talhão."""
        talhao = self._locate(df)
        if talhao is not None:
            context = replace(session.context, field_name=talhao.name)
            session = replace(session, context=context)
        metrics = metrics_svc.compute_session_metrics(session, df)
        if metrics is not None:
            metrics.talhao_id = talhao.id if talhao else None
        return metrics, session

    def analyze_session(
        self,
        session: WorkSession,
        df: pd.DataFrame,
        baselines: dict[BaselineKey, float] | None = None,
    ) -> tuple[SessionMetrics | None, list[Alert], WorkSession]:
        """Métricas e alertas de uma sessão."""
        metrics, session = self.measure(session, df)
        if metrics is None:
            return None, [], session
        alerts = self._session_alerts(session, df, metrics, baselines or {})
        return metrics, alerts, session

    def _session_alerts(
        self,
        session: WorkSession,
        df: pd.DataFrame,
        metrics: SessionMetrics,
        baselines: dict[BaselineKey, float],
    ) -> list[Alert]:
        cfg = self.config
        key = (session.machine.serial, session.context.operation, session.context.implement_name)
        return [
            *rules.detect_idle(session, df, cfg),
            *rules.detect_high_fuel_rate(session, df, cfg, baselines.get(key)),
            *rules.detect_counter_mismatch(session, metrics, cfg),
            *rules.detect_gps_jumps(session, cfg),
            *rules.detect_no_gps(session, metrics, cfg),
        ]

    def baselines_from_results(self) -> dict[BaselineKey, float]:
        """Baseline de vazão em trabalho por (máquina, operação, implemento), do histórico."""
        sessions = self._store.load_results("sessions")
        return self._baselines(sessions) if sessions is not None else {}

    @staticmethod
    def _baselines(sessions: pd.DataFrame) -> dict[BaselineKey, float]:
        useful = sessions[(sessions.work_h >= MIN_BASELINE_WORK_H) & sessions.lph_work.notna()]
        if useful.empty:
            return {}
        keys = ["machine_serial", "operation", "implement_name"]
        grouped = useful.groupby(keys, dropna=False)["lph_work"].median()
        return {tuple(None if pd.isna(x) else x for x in k): float(v) for k, v in grouped.items()}

    # ------------------------------------------------------------------ lote
    def analyze_all(self) -> dict:
        """Recalcula tudo a partir do dado limpo e grava os resultados (etapa 5)."""
        shas = self._store.list_sessions()
        rows: list[dict] = []
        for sha in shas:
            session, df = self._store.load_session(sha)
            metrics, _ = self.measure(session, df)
            if metrics is not None:
                rows.append(metrics.to_dict())
        if not rows:
            return {"sessoes": 0, "alertas": 0}
        sessions_df = pd.DataFrame(rows)
        baselines = self._baselines(sessions_df)

        alerts: list[Alert] = []
        for sha in sessions_df["source_sha256"]:
            session, df = self._store.load_session(sha)
            _, session_alerts, _ = self.analyze_session(session, df, baselines)
            alerts += session_alerts
        alerts += rules.detect_l_per_ha_outliers(sessions_df, self.config)

        daily = metrics_svc.daily_field_metrics(sessions_df)
        summary = {
            "sessoes": len(sessions_df),
            "alertas": len(alerts),
            "regras_versao": self.config.version,
            "regras": asdict(self.config),
            "baseline_lph_trabalho": {
                " | ".join(str(x) for x in k): round(v, 2) for k, v in baselines.items()
            },
            "gerado_em": datetime.now(UTC).isoformat(),
        }
        self._store.save_results(sessions_df, daily, alerts, summary)
        return summary
