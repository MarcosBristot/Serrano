"""Raiz de composição: o único módulo que conhece as classes concretas."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from sistemacampero.application.cadastro import ServicoCadastro
from sistemacampero.application.ingestao import ExecutorDeJobs, ServicoIngestao
from sistemacampero.application.processamento import ProcessadorDeArquivo
from sistemacampero.application.tenancy import ServicoTenancy
from sistemacampero.domain.ports import Armazenamento, VerificadorDeProntidao, VerificadorDeToken
from sistemacampero.domain.services.rules import ConfigRegras
from sistemacampero.infrastructure.config import Settings
from sistemacampero.infrastructure.parsers.john_deere_gen4.masterdata import ler_cadastro_gen4
from sistemacampero.infrastructure.parsers.registry import registro_padrao
from sistemacampero.infrastructure.persistence.cadastro import PostgresRepositorioCadastro
from sistemacampero.infrastructure.persistence.db import Database
from sistemacampero.infrastructure.persistence.ingestao import (
    PostgresFilaDeJobs,
    PostgresRepositorioIngestao,
)
from sistemacampero.infrastructure.persistence.organizacoes import (
    PostgresRepositorioOrganizacoes,
)
from sistemacampero.infrastructure.persistence.resultados import PostgresRepositorioResultados
from sistemacampero.infrastructure.security.jwt import (
    CacheJwks,
    VerificadorJwtSupabase,
    buscar_jwks_http,
)
from sistemacampero.infrastructure.storage.local import ArmazenamentoLocal
from sistemacampero.infrastructure.storage.supabase import ArmazenamentoSupabase


class Prontidao:
    def __init__(self, db: Database, storage: Armazenamento) -> None:
        self._db = db
        self._storage = storage

    def verificar(self) -> dict[str, str]:
        checks: dict[str, str] = {}
        for nome, teste in (("banco", self._db.ping), ("storage", self._storage.verificar)):
            try:
                teste()
                checks[nome] = "ok"
            except Exception as exc:  # o /ready só reporta
                checks[nome] = f"erro: {type(exc).__name__}"
        return checks


@dataclass
class Container:
    settings: Settings
    tenancy: ServicoTenancy
    verificador_token: VerificadorDeToken
    prontidao: VerificadorDeProntidao
    ingestao: ServicoIngestao | None = None
    repo_ingestao: PostgresRepositorioIngestao | None = None
    fila: PostgresFilaDeJobs | None = None
    executor: ExecutorDeJobs | None = None
    cadastro: PostgresRepositorioCadastro | None = None
    servico_cadastro: ServicoCadastro | None = None
    db: Database | None = None

    def fechar(self) -> None:
        if self.db is not None:
            self.db.fechar()


def construir_storage(settings: Settings) -> Armazenamento:
    if settings.storage_backend == "supabase":
        assert settings.supabase_url is not None and settings.supabase_secret_key is not None
        return ArmazenamentoSupabase(
            str(settings.supabase_url), settings.supabase_secret_key.get_secret_value()
        )
    return ArmazenamentoLocal(settings.storage_dir)


def construir(settings: Settings, storage: Armazenamento | None = None) -> Container:
    db = Database(
        settings.database_url.get_secret_value(),
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
        modo_pooler=settings.db_modo_pooler,
    )
    storage = storage or construir_storage(settings)
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
    repo_ingestao = PostgresRepositorioIngestao(db)
    cadastro = PostgresRepositorioCadastro(db)
    regras = ConfigRegras()
    executor = ExecutorDeJobs(
        repo=repo_ingestao,
        storage=storage,
        processador=ProcessadorDeArquivo(registro_padrao(), regras),
        resultados=PostgresRepositorioResultados(db),
        versao_regras=regras.versao,
        config_regras=asdict(regras),
        cadastro=cadastro,
        leitor_cadastro=ler_cadastro_gen4,
    )
    return Container(
        settings=settings,
        tenancy=ServicoTenancy(PostgresRepositorioOrganizacoes(db)),
        verificador_token=verificador,
        prontidao=Prontidao(db, storage),
        ingestao=ServicoIngestao(repo_ingestao, storage, settings.max_upload_mb * 1024**2),
        repo_ingestao=repo_ingestao,
        fila=PostgresFilaDeJobs(db),
        executor=executor,
        cadastro=cadastro,
        servico_cadastro=ServicoCadastro(cadastro, repo_ingestao),
        db=db,
    )
