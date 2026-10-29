"""Configuração por variáveis de ambiente, validada no boot (pydantic-settings).

Nada é lido no import: quem precisa chama ``Settings()`` (feito em ``container``).
Segredos nunca têm valor padrão.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,  # "SUPABASE_JWT_SECRET=" vazio = não definido
        extra="ignore",
        frozen=True,
    )

    ambiente: Literal["dev", "test", "staging", "prod"] = "dev"

    # Banco: em produção, o pooler Supavisor em modo sessão (porta 5432, IPv4).
    database_url: SecretStr
    db_pool_min: int = Field(default=1, ge=0)
    db_pool_max: int = Field(default=10, ge=1)
    db_modo_pooler: Literal["sessao", "transacao"] = "sessao"

    # Auth (Supabase): JWKS em {SUPABASE_URL}/auth/v1/.well-known/jwks.json.
    # SUPABASE_JWT_SECRET só para projetos com a chave HS256 legada.
    supabase_url: AnyHttpUrl | None = None
    supabase_jwt_secret: SecretStr | None = None
    jwt_audience: str = "authenticated"
    jwks_cache_s: int = Field(default=600, ge=30)

    # Storage: "supabase" em staging/produção; "local" (disco) em dev/compose/testes.
    storage_backend: Literal["local", "supabase"] = "local"
    storage_dir: Path = Path("./data_storage")
    supabase_secret_key: SecretStr | None = None  # sb_secret_... (ou service_role legada)
    max_upload_mb: int = Field(default=1024, ge=1)

    # Worker (fila Postgres)
    worker_lease_s: int = Field(default=600, ge=30)
    worker_heartbeat_s: int = Field(default=60, ge=5)
    worker_poll_min_s: float = Field(default=1.0, gt=0)
    worker_poll_max_s: float = Field(default=5.0, gt=0)

    # Notificações e convites
    frontend_url: AnyHttpUrl | None = None  # links nos e-mails
    chave_cifragem: SecretStr | None = None  # Fernet (segredos de webhook)
    smtp_host: str | None = None
    smtp_porta: int = 587
    smtp_usuario: str | None = None
    smtp_senha: SecretStr | None = None
    smtp_remetente: str | None = None
    smtp_tls: bool = True

    # Proteção HTTP (por instância da API)
    limite_por_minuto: int = Field(default=600, ge=10)
    limite_uploads_por_minuto: int = Field(default=120, ge=1)
    limite_contatos_por_minuto: int = Field(default=5, ge=1)
    retencao_contatos_meses: int = Field(default=12, ge=1, le=60)
    # Marco Civil, art. 15: no mínimo 6 meses
    retencao_acessos_meses: int = Field(default=6, ge=6, le=24)
    carencia_exclusao_dias: int = Field(default=7, ge=0, le=30)

    cors_origens: list[str] = Field(default_factory=list)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = True

    @model_validator(mode="after")
    def _exige_auth(self) -> Settings:
        if self.supabase_url is None and self.supabase_jwt_secret is None:
            raise ValueError("Defina SUPABASE_URL (JWKS) ou SUPABASE_JWT_SECRET (HS256).")
        if self.storage_backend == "supabase" and (
            self.supabase_url is None or self.supabase_secret_key is None
        ):
            raise ValueError("STORAGE_BACKEND=supabase exige SUPABASE_URL e SUPABASE_SECRET_KEY.")
        if self.ambiente in ("staging", "prod") and self.storage_backend == "local":
            raise ValueError("Em staging/produção o Storage é o do Supabase (disco é efêmero).")
        if self.ambiente == "prod" and "*" in self.cors_origens:
            raise ValueError("CORS_ORIGENS='*' não é permitido em produção.")
        return self

    @property
    def jwt_issuer(self) -> str | None:
        if self.supabase_url is None:
            return None
        return f"{str(self.supabase_url).rstrip('/')}/auth/v1"

    @property
    def jwks_url(self) -> str | None:
        return f"{self.jwt_issuer}/.well-known/jwks.json" if self.jwt_issuer else None
