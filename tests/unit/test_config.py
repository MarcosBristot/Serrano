from __future__ import annotations

import pytest
from pydantic import ValidationError

from sistemacampero.infrastructure.config import Settings


def _settings(**kw: object) -> Settings:
    return Settings(_env_file=None, database_url="postgresql://x@h/db", **kw)  # type: ignore[arg-type]


def test_exige_alguma_forma_de_validar_jwt(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("SUPABASE_URL", "SUPABASE_JWT_SECRET"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ValidationError, match="SUPABASE_URL"):
        _settings()


def test_database_url_obrigatoria(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None, supabase_jwt_secret="x")  # type: ignore[call-arg]


def test_urls_derivadas_do_supabase() -> None:
    s = _settings(supabase_url="https://abc.supabase.co/")
    assert s.jwt_issuer == "https://abc.supabase.co/auth/v1"
    assert s.jwks_url == "https://abc.supabase.co/auth/v1/.well-known/jwks.json"


def test_cors_curinga_proibido_em_producao() -> None:
    with pytest.raises(ValidationError, match="CORS"):
        _settings(supabase_url="https://abc.supabase.co", ambiente="prod", cors_origens=["*"])


def test_segredo_nao_aparece_no_repr() -> None:
    s = _settings(supabase_jwt_secret="super-secreto")
    assert "super-secreto" not in repr(s)
    assert "postgresql://x@h/db" not in repr(s)
