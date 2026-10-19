"""Workspace local (sistema de arquivos): bruto, limpo (Parquet) e resultados.

Layout::

    <workdir>/raw/<sha256>.jdl            etapa 1 — bruto imutável
    <workdir>/clean/<sha256>.parquet      etapa 3 — amostras limpas (schema universal)
    <workdir>/clean/<sha256>.meta.json    metadados da sessão + qualidade + versões
    <workdir>/results/*.parquet|csv|json  etapa 5 — métricas/alertas (reprocessáveis)
    <workdir>/published/                  marcadores de sessões já publicadas no banco
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from sistemacampero.domain.entities import (
    Alert,
    ContextInfo,
    MachineInfo,
    WorkSession,
)


class LocalWorkspace:
    """Implementação de ``SessionStore`` sobre o sistema de arquivos."""

    def __init__(self, workdir: str | Path) -> None:
        self.root = Path(workdir)
        self._raw = self.root / "raw"
        self._clean = self.root / "clean"
        self._results = self.root / "results"
        self._published = self.root / "published"

    # ------------------------------------------------------------ etapas 1–3
    def is_current(self, sha256: str, adapter_version: str, clean_version: str) -> bool:
        meta_path = self._clean / f"{sha256}.meta.json"
        if not meta_path.exists():
            return False
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return (
            meta.get("adapter_version") == adapter_version
            and meta.get("clean_version") == clean_version
        )

    def save_raw(self, path: Path, sha256: str) -> None:
        self._raw.mkdir(parents=True, exist_ok=True)
        target = self._raw / f"{sha256}{Path(path).suffix.lower()}"
        if not target.exists():
            shutil.copy2(path, target)

    def save_clean(
        self,
        session: WorkSession,
        cleaned: pd.DataFrame,
        quality: dict[str, int],
        clean_version: str,
    ) -> None:
        self._clean.mkdir(parents=True, exist_ok=True)
        sha = session.source_sha256
        cleaned.to_parquet(self._clean / f"{sha}.parquet", index=False)
        meta = {
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
            "clean_version": clean_version,
            "ingested_at": datetime.now(UTC).isoformat(),
        }
        (self._clean / f"{sha}.meta.json").write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8"
        )

    # ------------------------------------------------------------ leitura
    def list_sessions(self) -> list[str]:
        if not self._clean.exists():
            return []
        return sorted(p.name.removesuffix(".meta.json") for p in self._clean.glob("*.meta.json"))

    def load_session(self, sha256: str) -> tuple[WorkSession, pd.DataFrame]:
        meta = json.loads((self._clean / f"{sha256}.meta.json").read_text(encoding="utf-8"))
        samples = pd.read_parquet(self._clean / f"{sha256}.parquet")
        started = meta["started_at"]
        session = WorkSession(
            source_file=meta["source_file"],
            source_sha256=sha256,
            adapter=meta["adapter"],
            adapter_version=meta["adapter_version"],
            machine=MachineInfo(**meta["machine"]),
            context=ContextInfo(**meta["context"]),
            started_at=datetime.fromisoformat(started) if started else None,
            samples=samples,
            gps_chunks=[
                (dur, tuple(a) if a else None, tuple(b) if b else None)
                for dur, a, b in meta["gps_chunks"]
            ],
            warnings=meta["warnings"],
        )
        return session, samples

    # ------------------------------------------------------------ etapa 5
    def save_results(
        self,
        sessions: pd.DataFrame,
        daily: pd.DataFrame,
        alerts: list[Alert],
        summary: dict,
    ) -> None:
        self._results.mkdir(parents=True, exist_ok=True)
        sessions.to_parquet(self._results / "sessions.parquet", index=False)
        daily.to_parquet(self._results / "daily.parquet", index=False)
        daily.to_csv(self._results / "consolidado_diario.csv", index=False, encoding="utf-8-sig")
        alert_df = pd.DataFrame([a.to_dict() for a in alerts])
        if not alert_df.empty:
            alert_df["details"] = alert_df["details"].map(
                lambda d: json.dumps(d, ensure_ascii=False)
            )
        alert_df.to_parquet(self._results / "alerts.parquet", index=False)
        (self._results / "run.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load_results(self, name: str) -> pd.DataFrame | None:
        path = self._results / f"{name}.parquet"
        return pd.read_parquet(path) if path.exists() else None

    # ------------------------------------------------------------ publicação
    def is_published(self, sha256: str, rules_version: str) -> bool:
        return (self._published / f"{sha256}.{rules_version}").exists()

    def mark_published(self, sha256: str, rules_version: str) -> None:
        self._published.mkdir(parents=True, exist_ok=True)
        (self._published / f"{sha256}.{rules_version}").touch()
