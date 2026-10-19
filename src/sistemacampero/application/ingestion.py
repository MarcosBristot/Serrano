"""Caso de uso: etapas 1–3 (arquivo bruto -> sessão limpa no schema universal)."""

from __future__ import annotations

import logging
import traceback
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from sistemacampero.domain.ports import ManufacturerAdapter, SessionStore
from sistemacampero.domain.services import sanitization

logger = logging.getLogger(__name__)


class UnsupportedSourceError(ValueError):
    """Não há adapter para a marca/tecnologia informada (ou formato não reconhecido)."""


@dataclass(frozen=True)
class IngestResult:
    """Resultado da ingestão de um arquivo."""

    file: str
    status: str  # ok | ja_processado | vazio | ignorado | erro
    sha256: str | None = None
    rows: int = 0
    reason: str | None = None


class IngestionService:
    """Escolhe o adapter, converte, sanitiza e persiste (bruto + limpo)."""

    def __init__(self, adapters: Sequence[ManufacturerAdapter], store: SessionStore) -> None:
        self._adapters = list(adapters)
        self._store = store

    def select_adapter(
        self, path: Path, manufacturer: str | None = None, technology: str | None = None
    ) -> ManufacturerAdapter:
        """Adapter por (marca, tecnologia) quando informados; senão, por reconhecimento."""
        if manufacturer:
            wanted = (manufacturer.strip().lower(), (technology or "").strip().lower())
            for adapter in self._adapters:
                same_brand = adapter.manufacturer.lower() == wanted[0]
                same_tech = not wanted[1] or adapter.technology.lower() == wanted[1]
                if same_brand and same_tech:
                    return adapter
            label = f"{manufacturer} {technology or ''}".strip()
            raise UnsupportedSourceError(f"adapter para '{label}' ainda não implementado")
        for adapter in self._adapters:
            if adapter.can_parse(path):
                return adapter
        raise UnsupportedSourceError(f"formato não reconhecido: {path.name}")

    def ingest_file(
        self,
        path: str | Path,
        manufacturer: str | None = None,
        technology: str | None = None,
    ) -> IngestResult:
        """Etapas 1–3 para um arquivo (idempotente: mesmo conteúdo + mesmas versões)."""
        path = Path(path)
        try:
            adapter = self.select_adapter(path, manufacturer, technology)
            session = adapter.parse(path)
            sha = session.source_sha256
            if self._store.is_current(sha, adapter.version, sanitization.CLEAN_VERSION):
                return IngestResult(path.name, "ja_processado", sha)
            self._store.save_raw(path, sha)  # etapa 1: bruto preservado
            if session.samples.empty:
                return IngestResult(path.name, "vazio", sha, reason="sem amostras de dados")
            cleaned, quality = sanitization.sanitize(session.samples)  # etapa 2
            self._store.save_clean(  # etapa 3
                session, cleaned, quality, sanitization.CLEAN_VERSION
            )
            return IngestResult(path.name, "ok", sha, rows=len(cleaned))
        except UnsupportedSourceError as exc:
            return IngestResult(path.name, "ignorado", reason=str(exc))
        except Exception as exc:  # um arquivo ruim não derruba o lote
            logger.exception("falha ao ingerir %s", path.name)
            reason = f"{type(exc).__name__}: {exc}"
            return IngestResult(path.name, "erro", reason=reason + "\n" + traceback.format_exc(3))

    def ingest_many(self, paths: Sequence[Path], workers: int = 1) -> list[IngestResult]:
        """Ingestão em lote (``workers > 1`` usa processos)."""
        if workers <= 1 or len(paths) <= 1:
            return [self.ingest_file(p) for p in paths]
        with ProcessPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(self.ingest_file, paths, chunksize=4))
