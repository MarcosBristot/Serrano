"""Repositórios sobre Supabase (PostgREST + RPC PostGIS).

O cliente é injetado (nunca criado aqui) para permitir teste com dublê. A chave deve ser
a ``service_role`` **apenas no backend** e sempre vir de variável de ambiente.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable, Iterable, Iterator
from typing import Any

from sistemacampero.domain.entities import FieldBoundary

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000
MAX_ATTEMPTS = 3


def _chunks(rows: list[dict], size: int) -> Iterator[list[dict]]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def to_json_value(value: Any) -> Any:
    """Converte NaN/NaT/numpy para tipos aceitos em JSON (NaN vira ``None``)."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return None if str(value) == "NaT" else value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def json_row(row: dict[str, Any]) -> dict[str, Any]:
    return {k: to_json_value(v) for k, v in row.items()}


def _retry(action: Callable[[], Any], what: str) -> Any:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return action()
        except Exception as exc:  # erros de rede/PostgREST: tenta de novo e propaga
            if attempt == MAX_ATTEMPTS:
                logger.error("falha definitiva em %s: %s", what, exc)
                raise
            logger.warning("falha em %s (tentativa %d): %s", what, attempt, exc)
            time.sleep(0.5 * 2**attempt)
    return None  # inalcançável


class SupabaseFieldRepository:
    """Talhões no PostGIS via RPC (``upsert_talhao`` e ``listar_talhoes_geojson``)."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def list_fields(self) -> list[FieldBoundary]:
        response = _retry(
            lambda: self._client.rpc("listar_talhoes_geojson", {}).execute(), "listar talhões"
        )
        return [
            FieldBoundary(
                id=str(row["id"]),
                name=row["nome"],
                farm=row.get("fazenda"),
                client=row.get("cliente"),
                area_ha=row.get("area_ha"),
                external_guid=row.get("external_guid"),
                geometry=row["geometry"],
            )
            for row in (response.data or [])
            if row.get("geometry")
        ]

    def upsert_fields(self, fields: Iterable[FieldBoundary]) -> int:
        count = 0
        for f in fields:
            params = {
                "p_external_guid": f.external_guid,
                "p_nome": f.name,
                "p_fazenda": f.farm,
                "p_cliente": f.client,
                "p_area_ha": f.area_ha,
                "p_geojson": f.geometry,
            }
            _retry(
                lambda p=params: self._client.rpc("upsert_talhao", p).execute(), f"talhão {f.name}"
            )
            count += 1
        return count


class SupabaseTelemetryPublisher:
    """Publica sessões, amostras decimadas, métricas e alertas (upsert idempotente)."""

    def __init__(self, client: Any, batch_size: int = BATCH_SIZE) -> None:
        self._client = client
        self._batch = batch_size

    def _upsert(self, table: str, rows: list[dict], on_conflict: str) -> None:
        for batch in _chunks(rows, self._batch):
            _retry(
                lambda b=batch: (
                    self._client.table(table).upsert(b, on_conflict=on_conflict).execute()
                ),
                f"upsert {table}",
            )

    def publish_session(
        self,
        session_row: dict,
        samples: list[dict],
        metrics_row: dict,
        alerts: list[dict],
    ) -> None:
        # ordem respeita as chaves estrangeiras: sessão -> filhos
        self._upsert("sessoes_trabalho", [json_row(session_row)], "source_sha256")
        self._upsert("telemetria", [json_row(r) for r in samples], "machine_serial,timestamp")
        self._upsert("metricas_sessao", [json_row(metrics_row)], "session_sha256,rules_version")
        if alerts:
            self._upsert("alertas", [json_row(a) for a in alerts], "id")


class SupabaseTelemetryQueries:
    """Consultas de leitura (mapa e KPIs) sobre as tabelas publicadas."""

    PAGE = 1000  # limite padrão do PostgREST: paginamos para nunca truncar em silêncio

    def __init__(self, client: Any) -> None:
        self._client = client

    def _fetch_all(self, build: Callable[[], Any]) -> list[dict]:
        rows: list[dict] = []
        start = 0
        while True:
            page = (
                _retry(
                    lambda s=start: build().range(s, s + self.PAGE - 1).execute(),
                    "consulta paginada",
                ).data
                or []
            )
            rows += page
            if len(page) < self.PAGE:
                return rows
            start += self.PAGE

    def track(self, machine_serial: str, talhao_id: str | None, limit: int) -> list[dict]:
        query = (
            self._client.table("telemetria")
            .select("timestamp,latitude,longitude,speed_kmh,fuel_rate_lph,engine_rpm,engine_on")
            .eq("machine_serial", machine_serial)
            .not_.is_("latitude", "null")
            .order("timestamp")
            .limit(limit)
        )
        if talhao_id:
            query = query.eq("talhao_id", talhao_id)
        return _retry(query.execute, "trajeto").data or []

    def sessions(self, machine_serial: str | None, limit: int, offset: int) -> dict:
        query = self._client.table("sessoes_trabalho").select("*", count="exact")
        if machine_serial:
            query = query.eq("machine_serial", machine_serial)
        response = _retry(
            query.order("started_at", desc=True).range(offset, offset + limit - 1).execute,
            "sessões",
        )
        return {"total": response.count or 0, "items": response.data or []}

    def alerts(self, machine_serial: str | None, kind: str | None, limit: int, offset: int) -> dict:
        query = self._client.table("alertas").select(
            "*, sessoes_trabalho!inner(machine_serial)", count="exact"
        )
        if machine_serial:
            query = query.eq("sessoes_trabalho.machine_serial", machine_serial)
        if kind:
            query = query.eq("kind", kind)
        response = _retry(
            query.order("start_utc", desc=True).range(offset, offset + limit - 1).execute,
            "alertas",
        )
        return {"total": response.count or 0, "items": response.data or []}

    def metric_rows(self, machine_serial: str) -> list[dict]:
        """Todas as métricas por sessão de uma máquina (paginado)."""
        return self._fetch_all(
            lambda: (
                self._client.table("metricas_sessao")
                .select("*")
                .eq("machine_serial", machine_serial)
                .order("session_sha256")
            )
        )
