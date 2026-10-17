"""API (FastAPI) do pipeline: upload em partes + processamento em segundo plano.

Fluxo (suporta dumps de pendrive de centenas de MB, sem estourar memória/limite de body):

    POST /api/v1/uploads                       -> {upload_id}        (declara nome/tamanho/sha256)
    PUT  /api/v1/uploads/{id}/chunks/{n}       -> corpo = bytes da parte n (ordem livre)
    POST /api/v1/uploads/{id}/complete         -> 202 {job_id}       (monta, confere sha256, enfileira)
    GET  /api/v1/jobs/{job_id}                 -> status/resumo do processamento
    GET  /api/v1/sessions | /alerts | /metrics/daily                 -> resultados (etapa 5)

Aceita ``.jdl`` avulso ou ``.zip`` com vários (a pasta inteira do pendrive, zipada).
O armazenamento é o ``workdir`` local; em produção troque por Supabase Storage + Postgres
(ver db/migrations) mantendo as mesmas funções de pipeline.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
import zipfile
from pathlib import Path

import pandas as pd
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from sistemacampero.pipeline.runner import analyze, ingest_paths

MAX_CHUNK_BYTES = 16 * 1024 * 1024
MAX_UPLOAD_BYTES = 4 * 1024**3
SAFE_NAME = re.compile(r"[^A-Za-z0-9._\-]+")


class UploadInit(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0, le=MAX_UPLOAD_BYTES)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")


def create_app(workdir: str | Path = "./data_work") -> FastAPI:
    work = Path(workdir)
    (work / "uploads").mkdir(parents=True, exist_ok=True)
    (work / "jobs").mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="API Campero Sistemas", version="1.1.0")

    def _upload_dir(upload_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", upload_id):
            raise HTTPException(400, "upload_id inválido")
        d = work / "uploads" / upload_id
        if not d.exists():
            raise HTTPException(404, "upload não encontrado")
        return d

    def _job_path(job_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise HTTPException(400, "job_id inválido")
        return work / "jobs" / f"{job_id}.json"

    def _write_job(job_id: str, **data) -> None:
        _job_path(job_id).write_text(json.dumps(data, ensure_ascii=False))

    # ------------------------------------------------------------------ upload
    @app.post("/api/v1/uploads", status_code=201)
    def init_upload(body: UploadInit):
        uid = uuid.uuid4().hex
        d = work / "uploads" / uid
        (d / "parts").mkdir(parents=True)
        (d / "meta.json").write_text(body.model_dump_json())
        return {"upload_id": uid, "max_chunk_bytes": MAX_CHUNK_BYTES}

    @app.put("/api/v1/uploads/{upload_id}/chunks/{n}", status_code=204)
    async def put_chunk(upload_id: str, n: int, request: Request):
        d = _upload_dir(upload_id)
        if not 0 <= n < 100_000:
            raise HTTPException(400, "número de parte inválido")
        data = await request.body()
        if not data or len(data) > MAX_CHUNK_BYTES:
            raise HTTPException(413, f"parte vazia ou maior que {MAX_CHUNK_BYTES} bytes")
        (d / "parts" / f"{n:06d}").write_bytes(data)

    def _run_job(job_id: str, upload_id: str, filename: str) -> None:
        d = work / "uploads" / upload_id
        try:
            _write_job(job_id, status="processando", upload_id=upload_id)
            src = d / "assembled"
            files: list[Path] = []
            if filename.lower().endswith(".zip"):
                out = d / "extracted"
                out.mkdir(exist_ok=True)
                with zipfile.ZipFile(src) as z:
                    for info in z.infolist():
                        if info.is_dir() or not info.filename.lower().endswith(".jdl"):
                            continue
                        target = out / f"{len(files):06d}.jdl"  # nome próprio: sem path traversal
                        with z.open(info) as fi, target.open("wb") as fo:
                            shutil.copyfileobj(fi, fo)
                        files.append(target)
            else:
                files = [src.with_suffix(".jdl")]
                src.rename(files[0])
            results = ingest_paths(files, work, workers=1)
            summary = analyze(work)
            counts: dict[str, int] = {}
            for r in results:
                counts[r["status"]] = counts.get(r["status"], 0) + 1
            _write_job(job_id, status="concluido", upload_id=upload_id, arquivos=counts,
                       erros=[r for r in results if r["status"] == "erro"][:20], resumo=summary)
        except Exception as exc:
            _write_job(job_id, status="erro", upload_id=upload_id, motivo=f"{type(exc).__name__}: {exc}")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    @app.post("/api/v1/uploads/{upload_id}/complete", status_code=202)
    def complete(upload_id: str, tasks: BackgroundTasks):
        d = _upload_dir(upload_id)
        meta = UploadInit.model_validate_json((d / "meta.json").read_text())
        parts = sorted((d / "parts").iterdir())
        if not parts:
            raise HTTPException(400, "nenhuma parte enviada")
        h, total = hashlib.sha256(), 0
        with (d / "assembled").open("wb") as out:
            for p in parts:
                b = p.read_bytes()
                h.update(b)
                total += len(b)
                out.write(b)
        if total != meta.size_bytes:
            raise HTTPException(422, f"tamanho recebido {total} != declarado {meta.size_bytes}")
        if meta.sha256 and h.hexdigest() != meta.sha256.lower():
            raise HTTPException(422, "sha256 não confere: upload corrompido")
        shutil.rmtree(d / "parts")
        job_id = uuid.uuid4().hex
        _write_job(job_id, status="na_fila", upload_id=upload_id)
        tasks.add_task(_run_job, job_id, upload_id, SAFE_NAME.sub("_", meta.filename))
        return {"job_id": job_id}

    @app.get("/api/v1/jobs/{job_id}")
    def job(job_id: str):
        p = _job_path(job_id)
        if not p.exists():
            raise HTTPException(404, "job não encontrado")
        return json.loads(p.read_text())

    # --------------------------------------------------------------- resultados
    def _table(name: str) -> pd.DataFrame:
        p = work / "results" / f"{name}.parquet"
        if not p.exists():
            raise HTTPException(404, "ainda não há resultados; envie arquivos primeiro")
        return pd.read_parquet(p)

    def _records(df: pd.DataFrame, limit: int, offset: int) -> dict:
        page = df.iloc[offset : offset + limit]
        return {"total": len(df), "items": json.loads(page.to_json(orient="records", date_format="iso"))}

    @app.get("/api/v1/sessions")
    def sessions(limit: int = 100, offset: int = 0):
        return _records(_table("sessions").sort_values("start_utc"), min(limit, 1000), offset)

    @app.get("/api/v1/alerts")
    def alerts(kind: str | None = None, severity: str | None = None, limit: int = 100, offset: int = 0):
        df = _table("alerts")
        if kind:
            df = df[df["kind"] == kind]
        if severity:
            df = df[df["severity"] == severity]
        return _records(df.sort_values("start_utc"), min(limit, 1000), offset)

    @app.get("/api/v1/metrics/daily")
    def daily(limit: int = 500, offset: int = 0):
        return _records(_table("daily"), min(limit, 2000), offset)

    return app


app = create_app()
