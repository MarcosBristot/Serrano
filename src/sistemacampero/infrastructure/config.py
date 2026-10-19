"""Configuração por variáveis de ambiente (12-factor). Nunca há segredo com valor padrão."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Parâmetros de execução do sistema."""

    workdir: Path = Path("./data_work")
    supabase_url: str | None = None
    supabase_key: str | None = None
    api_key: str | None = None
    gen4_dir: Path | None = None  # pasta Gen4 do pendrive (contornos locais, sem Supabase)
    persist_step_s: int = 5  # resolução das amostras gravadas no banco (1 = tudo)
    max_upload_mb: int = 512

    @property
    def supabase_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        gen4 = env.get("CAMPERO_GEN4_DIR")
        return cls(
            workdir=Path(env.get("CAMPERO_WORKDIR", "./data_work")),
            supabase_url=env.get("SUPABASE_URL") or None,
            supabase_key=env.get("SUPABASE_KEY") or None,
            api_key=env.get("CAMPERO_API_KEY") or None,
            gen4_dir=Path(gen4) if gen4 else None,
            persist_step_s=max(1, int(env.get("CAMPERO_PERSIST_STEP_S", "5"))),
            max_upload_mb=max(1, int(env.get("CAMPERO_MAX_UPLOAD_MB", "512"))),
        )
