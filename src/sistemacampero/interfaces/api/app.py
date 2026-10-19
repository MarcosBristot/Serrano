"""API REST (FastAPI) do Sistema Campero.

Contrato mantido para o frontend: ``POST /api/v1/telemetry/upload`` (um arquivo por
chamada, com ``marca`` e ``tecnologia``), ``GET /api/v1/telemetry/machine/{serial}`` e
``GET /api/v1/telemetry/stats/{serial}``. O processamento roda em segundo plano.
"""

from __future__ import annotations

import hmac
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import pandas as pd
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Query,
    UploadFile,
)
from pydantic import BaseModel

from sistemacampero.domain.services.metrics import machine_summary
from sistemacampero.infrastructure.config import Settings
from sistemacampero.infrastructure.container import Services, build_services

logger = logging.getLogger(__name__)

_ID = re.compile(r"[0-9a-f]{32}")
_COPY_BLOCK = 1024 * 1024


class TelemetryPoint(BaseModel):
    """Ponto de telemetria para desenhar o trajeto no mapa."""

    timestamp: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    speed_kmh: float | None = None
    fuel_rate_lph: float | None = None
    engine_rpm: float | None = None
    engine_on: bool = False


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    """Fábrica da aplicação (permite injetar configuração/serviços nos testes)."""
    services = services or build_services(settings or Settings.from_env())
    cfg = services.settings
    uploads = cfg.workdir / "uploads"
    jobs = cfg.workdir / "jobs"
    uploads.mkdir(parents=True, exist_ok=True)
    jobs.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="Sistema Campero - API de Telemetria", version="1.2.0")

    def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
        if cfg.api_key and not (x_api_key and hmac.compare_digest(x_api_key, cfg.api_key)):
            raise HTTPException(401, "API key ausente ou inválida")

    auth = [Depends(require_api_key)]

    def job_path(job_id: str) -> Path:
        if not _ID.fullmatch(job_id):
            raise HTTPException(400, "job_id inválido")
        return jobs / f"{job_id}.json"

    def write_job(job_id: str, **data) -> None:
        job_path(job_id).write_text(json.dumps(data, ensure_ascii=False, default=str))

    def run_job(job_id: str, path: Path, filename: str, marca: str, tecnologia: str) -> None:
        """Roda em segundo plano; sempre remove o arquivo temporário."""
        try:
            write_job(job_id, status="processando", arquivo=filename)
            outcome = services.processor.process_file(path, marca, tecnologia)
            ingest = outcome.ingest
            status = "erro" if ingest.status == "erro" else "concluido"
            write_job(
                job_id,
                status=status,
                arquivo=filename,
                resultado=ingest.status,
                sha256=ingest.sha256,
                amostras=ingest.rows,
                alertas=outcome.alerts,
                publicado=outcome.published,
                amostras_publicadas=outcome.published_samples,
                motivo=ingest.reason,
                finalizado_em=datetime.now(UTC).isoformat(),
            )
        except Exception as exc:
            logger.exception("job %s falhou", job_id)
            write_job(
                job_id, status="erro", arquivo=filename, motivo=f"{type(exc).__name__}: {exc}"
            )
        finally:
            path.unlink(missing_ok=True)

    @app.get("/")
    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "supabase": cfg.supabase_enabled,
            "mensagem": "API do Sistema Campero operando. Acesse /docs para testar.",
        }

    @app.post("/api/v1/telemetry/upload", status_code=202, dependencies=auth)
    def upload_telemetry(
        background_tasks: BackgroundTasks,
        file: Annotated[UploadFile, File()],
        marca: Annotated[str, Query(description="Ex.: John Deere")] = "John Deere",
        tecnologia: Annotated[str, Query(description="Ex.: Gen4")] = "Gen4",
    ) -> dict:
        """Recebe um arquivo por vez e processa em segundo plano."""
        original = Path(file.filename or "arquivo").name  # sem caminho (anti path traversal)
        if not original.lower().endswith(".jdl"):
            raise HTTPException(415, "envie um arquivo .jdl")
        job_id = uuid.uuid4().hex
        target = uploads / f"{job_id}.jdl"  # nome físico próprio: sem colisão entre uploads
        limit = cfg.max_upload_mb * 1024 * 1024
        size = 0
        with target.open("wb") as out:
            while block := file.file.read(_COPY_BLOCK):
                size += len(block)
                if size > limit:
                    out.close()
                    target.unlink(missing_ok=True)
                    raise HTTPException(413, f"arquivo maior que {cfg.max_upload_mb} MB")
                out.write(block)
        write_job(job_id, status="na_fila", arquivo=original)
        background_tasks.add_task(run_job, job_id, target, original, marca, tecnologia)
        return {"job_id": job_id, "arquivo": original, "marca": marca, "tecnologia": tecnologia}

    @app.get("/api/v1/jobs/{job_id}", dependencies=auth)
    def get_job(job_id: str) -> dict:
        path = job_path(job_id)
        if not path.exists():
            raise HTTPException(404, "job não encontrado")
        return json.loads(path.read_text())

    @app.get(
        "/api/v1/telemetry/machine/{machine_serial}",
        response_model=list[TelemetryPoint],
        dependencies=auth,
    )
    def machine_telemetry(
        machine_serial: str,
        talhao_id: str | None = None,
        limit: Annotated[int, Query(ge=1, le=20000)] = 1000,
    ) -> list[dict]:
        """Pontos com GPS válido (trajeto no mapa), em ordem cronológica."""
        points = services.queries.track(machine_serial, talhao_id, limit)
        if not points:
            raise HTTPException(404, "Sem dados geográficos para esta máquina.")
        return points

    @app.get("/api/v1/telemetry/stats/{machine_serial}", dependencies=auth)
    def machine_stats(machine_serial: str) -> dict:
        """KPIs consolidados (a partir das métricas por sessão, nunca de amostras truncadas)."""
        rows = services.queries.metric_rows(machine_serial)
        summary = machine_summary(pd.DataFrame(rows)) if rows else None
        if summary is None:
            raise HTTPException(404, "Sem dados para estatísticas.")
        return {"machine_serial": machine_serial, **summary}

    @app.get("/api/v1/sessions", dependencies=auth)
    def sessions(
        machine_serial: str | None = None,
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict:
        return services.queries.sessions(machine_serial, limit, offset)

    @app.get("/api/v1/alerts", dependencies=auth)
    def alerts(
        machine_serial: str | None = None,
        kind: str | None = None,
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict:
        return services.queries.alerts(machine_serial, kind, limit, offset)

    @app.post("/api/v1/analysis/run", status_code=202, dependencies=auth)
    def run_analysis(background_tasks: BackgroundTasks) -> dict:
        """Reprocessa regras sobre todo o dado limpo (inclui regras entre sessões)."""
        background_tasks.add_task(services.analysis.analyze_all)
        return {"status": "na_fila"}

    return app
