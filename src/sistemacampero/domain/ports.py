"""Portas (interfaces) que o domínio/aplicação exigem da infraestrutura."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pandas as pd

from sistemacampero.domain.entities import Alert, FieldBoundary, WorkSession


class ManufacturerAdapter(Protocol):
    """Converte o arquivo bruto de um fabricante para o schema universal."""

    name: str
    version: str
    manufacturer: str
    technology: str

    def can_parse(self, path: Path) -> bool:
        """Reconhece (barato, sem ler o arquivo todo) se o arquivo é deste fabricante."""

    def parse(self, path: Path) -> WorkSession:
        """Converte um arquivo bruto em ``WorkSession``."""


class SessionStore(Protocol):
    """Persistência das etapas 1–3 (bruto e limpo) e 5 (resultados)."""

    def is_current(self, sha256: str, adapter_version: str, clean_version: str) -> bool: ...

    def save_raw(self, path: Path, sha256: str) -> None: ...

    def save_clean(
        self,
        session: WorkSession,
        cleaned: pd.DataFrame,
        quality: dict[str, int],
        clean_version: str,
    ) -> None: ...

    def list_sessions(self) -> list[str]: ...

    def load_session(self, sha256: str) -> tuple[WorkSession, pd.DataFrame]: ...

    def save_results(
        self,
        sessions: pd.DataFrame,
        daily: pd.DataFrame,
        alerts: list[Alert],
        summary: dict,
    ) -> None: ...

    def load_results(self, name: str) -> pd.DataFrame | None: ...

    def is_published(self, sha256: str, rules_version: str) -> bool: ...

    def mark_published(self, sha256: str, rules_version: str) -> None: ...


class FieldSource(Protocol):
    """Fonte (somente leitura) de talhões: arquivos do monitor ou banco."""

    def list_fields(self) -> list[FieldBoundary]: ...


class FieldRepository(FieldSource, Protocol):
    """Repositório de talhões no banco geoespacial (PostGIS)."""

    def upsert_fields(self, fields: list[FieldBoundary]) -> int: ...


class TelemetryPublisher(Protocol):
    """Publica resultados no banco analítico (Supabase/PostGIS)."""

    def publish_session(
        self,
        session_row: dict,
        samples: list[dict],
        metrics_row: dict,
        alerts: list[dict],
    ) -> None: ...


class TelemetryQueries(Protocol):
    """Consultas de leitura usadas pela API (dashboards e mapa)."""

    def track(self, machine_serial: str, talhao_id: str | None, limit: int) -> list[dict]: ...

    def sessions(self, machine_serial: str | None, limit: int, offset: int) -> dict: ...

    def alerts(
        self, machine_serial: str | None, kind: str | None, limit: int, offset: int
    ) -> dict: ...

    def metric_rows(self, machine_serial: str) -> list[dict]: ...
