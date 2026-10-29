"""Fábrica da aplicação FastAPI.

Produção: ``uvicorn --factory sistemacampero.interfaces.api.app:create_app``.
Nos testes, injete um ``Container`` com dublês.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import anyio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sistemacampero import __version__
from sistemacampero.infrastructure.config import Settings
from sistemacampero.infrastructure.container import Container, construir
from sistemacampero.infrastructure.logging_config import configurar_logs
from sistemacampero.infrastructure.persistence.titular import RegistrosDeAcesso
from sistemacampero.interfaces.api import errors
from sistemacampero.interfaces.api.middleware import Metricas, RequestContextMiddleware
from sistemacampero.interfaces.api.protecao import ProtecaoMiddleware
from sistemacampero.interfaces.api.routers import (
    alertas,
    cadastro,
    conta,
    contatos,
    equipe,
    exportacao,
    ingestao,
    kpis,
    saude,
    titular,
)

PREFIXO = "/api/v1"
logger = logging.getLogger(__name__)


async def _gravar_acessos(acessos: RegistrosDeAcesso, intervalo_s: float = 5.0) -> None:
    """Grava em lote os registros de acesso enfileirados pelo middleware."""
    while True:
        await asyncio.sleep(intervalo_s)
        try:
            await anyio.to_thread.run_sync(acessos.gravar_pendentes)
        except Exception:
            logger.exception("falha ao gravar registros de acesso (nova tentativa em seguida)")


def create_app(
    container: Container | None = None,
    construir_container: Callable[[Settings], Container] = construir,
) -> FastAPI:
    if container is None:
        settings = Settings()  # vem do ambiente
        configurar_logs(settings.log_level, settings.log_json)
        container = construir_container(settings)
    cfg = container.settings

    @asynccontextmanager
    async def ciclo_de_vida(_: FastAPI) -> AsyncIterator[None]:
        acessos = container.acessos
        tarefa = asyncio.create_task(_gravar_acessos(acessos)) if acessos else None
        yield
        if tarefa is not None and acessos is not None:
            tarefa.cancel()
            with contextlib.suppress(Exception):
                await anyio.to_thread.run_sync(acessos.gravar_pendentes)
        container.fechar()

    app = FastAPI(
        title="Serrano API",
        version=__version__,
        lifespan=ciclo_de_vida,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    app.state.container = container
    app.state.metricas = Metricas()

    errors.registrar(app)
    app.add_middleware(
        ProtecaoMiddleware,
        por_minuto=cfg.limite_por_minuto,
        uploads_por_minuto=cfg.limite_uploads_por_minuto,
        contatos_por_minuto=cfg.limite_contatos_por_minuto,
        hsts=cfg.ambiente in ("staging", "prod"),
    )
    if cfg.cors_origens:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cfg.cors_origens,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-Organizacao-Id", "X-Request-ID"],
            expose_headers=["X-Request-ID"],
        )
    # Adicionado por último = mais externo: o request_id vale também para o CORS e erros.
    app.add_middleware(
        RequestContextMiddleware,
        metricas=app.state.metricas,
        auditar=container.repo_equipe.auditar if container.repo_equipe else None,
        registrar_acesso=container.acessos.registrar if container.acessos else None,
    )

    app.include_router(saude.router)  # /health, /ready e /metrics na raiz (healthcheck)
    app.include_router(saude.router, prefix=PREFIXO, include_in_schema=False)
    app.include_router(conta.router, prefix=PREFIXO)
    app.include_router(ingestao.router, prefix=PREFIXO)
    app.include_router(ingestao.admin, prefix=PREFIXO)
    app.include_router(cadastro.router, prefix=PREFIXO)
    app.include_router(cadastro.sessoes, prefix=PREFIXO)
    app.include_router(kpis.router, prefix=PREFIXO)
    app.include_router(kpis.legado, prefix=PREFIXO)
    app.include_router(alertas.router, prefix=PREFIXO)
    app.include_router(equipe.router, prefix=PREFIXO)
    app.include_router(exportacao.router, prefix=PREFIXO)
    app.include_router(contatos.router, prefix=PREFIXO)
    app.include_router(titular.router, prefix=PREFIXO)
    return app
