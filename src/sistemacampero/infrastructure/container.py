"""Raiz de composição: o único módulo que conhece as classes concretas."""

from __future__ import annotations

from dataclasses import dataclass

from sistemacampero.application.tenancy import ServicoTenancy
from sistemacampero.domain.ports import VerificadorDeProntidao, VerificadorDeToken
from sistemacampero.infrastructure.config import Settings
from sistemacampero.infrastructure.persistence.db import Database
from sistemacampero.infrastructure.persistence.organizacoes import (
    PostgresRepositorioOrganizacoes,
)
from sistemacampero.infrastructure.security.jwt import (
    CacheJwks,
    VerificadorJwtSupabase,
    buscar_jwks_http,
)


class ProntidaoBanco:
    def __init__(self, db: Database) -> None:
        self._db = db

    def verificar(self) -> dict[str, str]:
        try:
            self._db.ping()
            return {"banco": "ok"}
        except Exception as exc:  # o /ready só reporta
            return {"banco": f"erro: {type(exc).__name__}"}


@dataclass
class Container:
    settings: Settings
    tenancy: ServicoTenancy
    verificador_token: VerificadorDeToken
    prontidao: VerificadorDeProntidao
    db: Database | None = None

    def fechar(self) -> None:
        if self.db is not None:
            self.db.fechar()


def construir(settings: Settings) -> Container:
    db = Database(
        settings.database_url.get_secret_value(),
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
        modo_pooler=settings.db_modo_pooler,
    )
    jwks = (
        CacheJwks(buscar_jwks_http(settings.jwks_url), ttl_s=settings.jwks_cache_s)
        if settings.jwks_url
        else None
    )
    segredo = settings.supabase_jwt_secret
    verificador = VerificadorJwtSupabase(
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
        jwks=jwks,
        segredo_hs256=segredo.get_secret_value() if segredo else None,
    )
    return Container(
        settings=settings,
        tenancy=ServicoTenancy(PostgresRepositorioOrganizacoes(db)),
        verificador_token=verificador,
        prontidao=ProntidaoBanco(db),
        db=db,
    )
