"""Caso de uso de ponta a ponta para um arquivo enviado pelo monitor."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sistemacampero.application.analysis import AnalysisService
from sistemacampero.application.ingestion import IngestionService, IngestResult
from sistemacampero.application.publishing import PublishingService

logger = logging.getLogger(__name__)


@dataclass
class ProcessingOutcome:
    """Resumo do processamento de um arquivo."""

    ingest: IngestResult
    alerts: int = 0
    published_samples: int = 0
    published: bool = False


class TelemetryProcessor:
    """Ingere, analisa e (se configurado) publica um arquivo."""

    def __init__(
        self,
        ingestion: IngestionService,
        analysis: AnalysisService,
        publishing: PublishingService | None,
        store,
    ) -> None:
        self._ingestion = ingestion
        self._analysis = analysis
        self._publishing = publishing
        self._store = store

    def process_file(
        self, path, manufacturer: str | None = None, technology: str | None = None
    ) -> ProcessingOutcome:
        result = self._ingestion.ingest_file(path, manufacturer, technology)
        outcome = ProcessingOutcome(ingest=result)
        if result.status not in ("ok", "ja_processado") or result.sha256 is None:
            return outcome

        session, df = self._store.load_session(result.sha256)
        baselines = self._analysis.baselines_from_results()
        metrics, alerts, session = self._analysis.analyze_session(session, df, baselines)
        if metrics is None:
            return outcome
        outcome.alerts = len(alerts)
        if self._publishing is not None:
            outcome.published_samples = self._publishing.publish_session(
                session,
                df,
                metrics,
                alerts,
                self._analysis.config.version,
                self._analysis.locator(),
            )
            outcome.published = True
        return outcome

    def publish_pending(self) -> dict[str, int]:
        """Publica no banco todas as sessões do workspace ainda não publicadas (backfill)."""
        if self._publishing is None:
            raise RuntimeError("Supabase não configurado (defina SUPABASE_URL e SUPABASE_KEY)")
        version = self._analysis.config.version
        baselines = self._analysis.baselines_from_results()
        done = skipped = empty = 0
        for sha in self._store.list_sessions():
            if self._store.is_published(sha, version):
                skipped += 1
                continue
            session, df = self._store.load_session(sha)
            metrics, alerts, session = self._analysis.analyze_session(session, df, baselines)
            if metrics is None:
                empty += 1
                continue
            self._publishing.publish_session(
                session, df, metrics, alerts, version, self._analysis.locator()
            )
            done += 1
        return {"publicadas": done, "ja_publicadas": skipped, "sem_metricas": empty}
