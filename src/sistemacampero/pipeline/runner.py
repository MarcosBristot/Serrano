"""Pipeline em etapas isoladas (arquitetura de dados do projeto).

    1. raw      -> cópia imutável do arquivo bruto      workdir/raw/<sha256>.jdl
    2. clean    -> sanitização (clean.sanitize)
    3. persist  -> amostras limpas em schema universal  workdir/clean/<sha256>.parquet (+ .meta.json)
    4. analyze  -> métricas + regras sobre o dado limpo
    5. results  -> workdir/results/*.parquet            (separado do bruto e do limpo)

As etapas 4–5 podem ser repetidas com outra ``RuleConfig`` sem reler nem reprocessar o bruto.
O ``workdir`` local é o equivalente de Supabase Storage + tabelas; ver db/migrations.
"""

from __future__ import annotations

import json
import shutil
import traceback
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from sistemacampero.adapters.base import ManufacturerAdapter
from sistemacampero.adapters.john_deere_gen4 import JohnDeereGen4Adapter
from sistemacampero.analytics import rules
from sistemacampero.analytics.rules import Alert, RuleConfig
from sistemacampero.processing import clean as clean_mod
from sistemacampero.processing import metrics as metrics_mod
from sistemacampero.schema.universal import ContextInfo, MachineInfo, ParsedSession

ADAPTERS: list[ManufacturerAdapter] = [JohnDeereGen4Adapter()]


def pick_adapter(path: Path) -> ManufacturerAdapter | None:
    return next((a for a in ADAPTERS if a.can_parse(path)), None)


# ------------------------------------------------------------------ etapas 1–3
def ingest_file(path: str | Path, workdir: str | Path) -> dict:
    """Etapas 1–3 para um arquivo. Idempotente (mesmo conteúdo + mesma versão do adapter)."""
    path, workdir = Path(path), Path(workdir)
    raw_dir, clean_dir = workdir / "raw", workdir / "clean"
    raw_dir.mkdir(parents=True, exist_ok=True)
    clean_dir.mkdir(parents=True, exist_ok=True)
    try:
        adapter = pick_adapter(path)
        if adapter is None:
            return {"file": path.name, "status": "ignorado", "reason": "formato não reconhecido"}

        session = adapter.parse(path)
        sha = session.source_sha256
        meta_path = clean_dir / f"{sha}.meta.json"
        if meta_path.exists():
            old = json.loads(meta_path.read_text())
            if (old["adapter_version"] == adapter.version
                    and old.get("clean_version") == clean_mod.CLEAN_VERSION):
                return {"file": path.name, "sha256": sha, "status": "ja_processado"}

        raw_copy = raw_dir / f"{sha}{path.suffix.lower()}"
        if not raw_copy.exists():
            shutil.copy2(path, raw_copy)  # etapa 1: bruto preservado

        if session.samples.empty:
            return {"file": path.name, "sha256": sha, "status": "vazio",
                    "reason": "sem amostras de dados"}

        cleaned, quality = clean_mod.sanitize(session.samples)  # etapa 2
        cleaned.to_parquet(clean_dir / f"{sha}.parquet", index=False)  # etapa 3
        meta_path.write_text(json.dumps({
            "source_file": session.source_file,
            "source_sha256": sha,
            "adapter": session.adapter,
            "adapter_version": session.adapter_version,
            "machine": asdict(session.machine),
            "context": asdict(session.context),
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "gps_chunks": session.gps_chunks,
            "warnings": session.warnings,
            "quality": quality,
            "clean_version": clean_mod.CLEAN_VERSION,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False))
        return {"file": path.name, "sha256": sha, "status": "ok", "rows": len(cleaned)}
    except Exception as exc:  # um arquivo ruim não derruba o lote
        return {"file": path.name, "status": "erro", "reason": f"{type(exc).__name__}: {exc}",
                "trace": traceback.format_exc(limit=3)}


def ingest_paths(paths: list[Path], workdir: Path, workers: int = 4) -> list[dict]:
    if workers <= 1 or len(paths) == 1:
        return [ingest_file(p, workdir) for p in paths]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(ingest_file, paths, [workdir] * len(paths), chunksize=4))


# ------------------------------------------------------------------ etapas 4–5
def load_session(workdir: Path, sha: str) -> tuple[ParsedSession, pd.DataFrame]:
    meta = json.loads((workdir / "clean" / f"{sha}.meta.json").read_text())
    df = pd.read_parquet(workdir / "clean" / f"{sha}.parquet")
    session = ParsedSession(
        source_file=meta["source_file"], source_sha256=sha, adapter=meta["adapter"],
        adapter_version=meta["adapter_version"], machine=MachineInfo(**meta["machine"]),
        context=ContextInfo(**meta["context"]),
        started_at=datetime.fromisoformat(meta["started_at"]) if meta["started_at"] else None,
        samples=df, gps_chunks=[(d, tuple(a) if a else None, tuple(b) if b else None)
                                for d, a, b in meta["gps_chunks"]],
        warnings=meta["warnings"],
    )
    return session, df


def analyze(workdir: str | Path, cfg: RuleConfig | None = None) -> dict:
    """Etapas 4–5: recalcula métricas e alertas a partir do dado limpo."""
    workdir = Path(workdir)
    cfg = cfg or RuleConfig()
    shas = sorted(p.name.removesuffix(".meta.json") for p in (workdir / "clean").glob("*.meta.json"))

    sessions, rows = [], []
    for sha in shas:
        s, df = load_session(workdir, sha)
        m = metrics_mod.compute_session_metrics(s, df)
        if m is not None:
            rows.append(m.to_dict())
    sess_df = pd.DataFrame(rows)
    if sess_df.empty:
        return {"sessoes": 0, "alertas": 0}

    # baseline de vazão em trabalho por trator (mediana ponderada simples das sessões úteis)
    useful = sess_df[(sess_df.work_h >= 0.25) & sess_df.lph_work.notna()]
    key = ["machine_serial", "operation", "implement_name"]
    baseline = {k: float(v) for k, v in
                useful.groupby(key, dropna=False)["lph_work"].median().items()}

    alerts: list[Alert] = []
    by_sha = sess_df.set_index("source_sha256")
    for sha in shas:
        if sha not in by_sha.index:
            continue
        s, df = load_session(workdir, sha)
        m = metrics_mod.SessionMetrics(**{**by_sha.loc[sha].to_dict(), "source_sha256": sha})
        alerts += rules.detect_idle(s, df, cfg)
        alerts += rules.detect_high_fuel_rate(s, df, cfg, baseline.get(
            (s.machine.serial, s.context.operation, s.context.implement_name)))
        alerts += rules.detect_counter_mismatch(s, m, cfg)
        alerts += rules.detect_gps_jumps(s, cfg)
        alerts += rules.detect_no_gps(s, m, cfg)
    alerts += rules.detect_l_per_ha_outliers(sess_df, cfg)

    daily = metrics_mod.daily_field_metrics(sess_df)
    alert_df = pd.DataFrame([a.to_dict() for a in alerts])

    out = workdir / "results"
    out.mkdir(exist_ok=True)
    sess_df.to_parquet(out / "sessions.parquet", index=False)
    daily.to_parquet(out / "daily.parquet", index=False)
    daily.to_csv(out / "consolidado_diario.csv", index=False, encoding="utf-8-sig")
    if not alert_df.empty:
        alert_df["details"] = alert_df["details"].map(lambda d: json.dumps(d, ensure_ascii=False))
    alert_df.to_parquet(out / "alerts.parquet", index=False)
    summary = {
        "sessoes": len(sess_df), "alertas": len(alert_df),
        "regras_versao": cfg.version, "regras": asdict(cfg),
        "baseline_lph_trabalho": {" | ".join(str(x) for x in k): round(v, 2)
                                  for k, v in baseline.items()},
        "gerado_em": datetime.now(timezone.utc).isoformat(),
    }
    (out / "run.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary
