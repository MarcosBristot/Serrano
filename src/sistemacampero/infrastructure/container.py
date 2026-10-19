"""Raiz de composição: monta os serviços concretos a partir das configurações."""

from __future__ import annotations

from dataclasses import dataclass

from sistemacampero.application.analysis import AnalysisService
from sistemacampero.application.ingestion import IngestionService
from sistemacampero.application.processing import TelemetryProcessor
from sistemacampero.application.publishing import PublishingService
from sistemacampero.domain.ports import FieldSource, TelemetryQueries
from sistemacampero.infrastructure.config import Settings
from sistemacampero.infrastructure.parsers import default_adapters
from sistemacampero.infrastructure.parsers.john_deere_gen4.spatial import (
    SpatialFilesFieldSource,
)
from sistemacampero.infrastructure.persistence.local_queries import LocalTelemetryQueries
from sistemacampero.infrastructure.persistence.supabase_repository import (
    SupabaseFieldRepository,
    SupabaseTelemetryPublisher,
    SupabaseTelemetryQueries,
)
from sistemacampero.infrastructure.persistence.workspace import LocalWorkspace


@dataclass
class Services:
    """Serviços prontos para uso pelas interfaces (API e CLI)."""

    settings: Settings
    store: LocalWorkspace
    ingestion: IngestionService
    analysis: AnalysisService
    processor: TelemetryProcessor
    queries: TelemetryQueries
    field_repository: SupabaseFieldRepository | None = None


def create_supabase_client(settings: Settings):
    """Cliente Supabase (import tardio: só é exigido quando o Supabase está habilitado)."""
    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_key)


def build_services(settings: Settings, supabase_client=None) -> Services:
    """Monta o grafo de dependências.

    Sem Supabase, o sistema roda 100% local (workspace em disco); com Supabase, os
    talhões vêm do PostGIS e os resultados são publicados no banco.
    """
    store = LocalWorkspace(settings.workdir)
    ingestion = IngestionService(default_adapters(), store)

    field_repository = None
    publishing = None
    queries: TelemetryQueries = LocalTelemetryQueries(store)
    field_source: FieldSource | None = None

    if settings.supabase_enabled or supabase_client is not None:
        client = supabase_client or create_supabase_client(settings)
        field_repository = SupabaseFieldRepository(client)
        field_source = field_repository
        publishing = PublishingService(
            store, SupabaseTelemetryPublisher(client), settings.persist_step_s
        )
        queries = SupabaseTelemetryQueries(client)
    elif settings.gen4_dir is not None:
        field_source = SpatialFilesFieldSource(settings.gen4_dir)

    analysis = AnalysisService(store, field_source)
    processor = TelemetryProcessor(ingestion, analysis, publishing, store)
    return Services(
        settings=settings,
        store=store,
        ingestion=ingestion,
        analysis=analysis,
        processor=processor,
        queries=queries,
        field_repository=field_repository,
    )
