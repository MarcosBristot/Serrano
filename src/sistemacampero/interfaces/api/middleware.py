"""Middleware ASGI: ``X-Request-ID``, log de acesso e métricas Prometheus."""

from __future__ import annotations

import ipaddress
import json
import logging
import re
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import anyio
from prometheus_client import CollectorRegistry, Counter, Histogram
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sistemacampero.infrastructure.logging_config import request_id_var

logger = logging.getLogger("sistemacampero.acesso")

_REQUEST_ID_OK = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def _rota_template(scope: Scope) -> str:
    """Caminho com os parâmetros trocados pelo nome (/sessions/{id}): cardinalidade baixa.

    O FastAPI inclui routers sem copiar o prefixo para ``route.path``, então o template é
    reconstruído a partir do caminho real e dos ``path_params``.
    """
    if scope.get("route") is None:
        return "nao_roteada"
    params = {str(v): k for k, v in (scope.get("path_params") or {}).items()}
    partes = str(scope["path"]).split("/")
    return "/".join("{" + params[p] + "}" if p in params else p for p in partes)


class Metricas:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.requisicoes = Counter(
            "http_requests_total",
            "Requisições HTTP",
            ["method", "route", "status"],
            registry=self.registry,
        )
        self.duracao = Histogram(
            "http_request_duration_seconds",
            "Duração das requisições HTTP",
            ["method", "route"],
            registry=self.registry,
        )


_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_MUTACOES = {"POST", "PUT", "PATCH", "DELETE"}


def evento_auditoria(scope: Scope, status: int, rid: str) -> dict[str, Any] | None:
    """Toda mutação bem-sucedida de uma organização vira linha de auditoria (sem PII)."""
    estado = scope.get("state") or {}
    if scope["method"] not in _MUTACOES or status >= 400 or not estado.get("organizacao_id"):
        return None
    partes = [p for p in str(scope["path"]).split("/") if p][2:]  # tira "api/v1"
    recurso_id = next((p for p in partes if _UUID.fullmatch(p)), None)
    cliente = scope.get("client")
    ip = None
    if cliente:
        try:
            ip = str(ipaddress.ip_address(cliente[0]))
        except ValueError:
            ip = None
    return {
        "organizacao_id": estado["organizacao_id"],
        "ator_id": estado.get("ator_id"),
        "ator_tipo": estado.get("ator_tipo", "usuario"),
        "acao": f"{scope['method']} {_rota_template(scope)}",
        "recurso_tipo": partes[0] if partes else None,
        "recurso_id": recurso_id,
        "ip": ip,
        "request_id": rid,
    }


def evento_acesso(scope: Scope, status: int, rid: str) -> dict[str, Any] | None:
    """Registro de acesso (Marco Civil, art. 15): data, hora e IP de cada uso da API."""
    caminho = str(scope["path"])
    if not caminho.startswith("/api/"):
        return None
    estado = scope.get("state") or {}
    cliente = scope.get("client")
    ip = None
    if cliente:
        try:
            ip = str(ipaddress.ip_address(cliente[0]))
        except ValueError:
            ip = None
    return {
        "ocorrido_em": datetime.now(UTC),
        "ip": ip,
        "usuario_id": estado.get("usuario_id")
        or (estado.get("ator_id") if estado.get("ator_tipo", "usuario") == "usuario" else None),
        "organizacao_id": estado.get("organizacao_id"),
        "metodo": scope["method"],
        "rota": _rota_template(scope),
        "status": status,
        "request_id": rid,
    }


class RequestContextMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        metricas: Metricas,
        auditar: Callable[[dict[str, Any]], None] | None = None,
        registrar_acesso: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.app = app
        self.metricas = metricas
        self.auditar = auditar
        self.registrar_acesso = registrar_acesso

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        recebido = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin-1")
        rid = recebido if _REQUEST_ID_OK.fullmatch(recebido) else uuid.uuid4().hex
        token = request_id_var.set(rid)
        inicio = time.perf_counter()
        status = 500
        iniciada = False

        async def enviar(msg: Message) -> None:
            nonlocal status, iniciada
            if msg["type"] == "http.response.start":
                status, iniciada = msg["status"], True
                msg["headers"] = [*msg.get("headers", []), (b"x-request-id", rid.encode())]
            await send(msg)

        try:
            await self.app(scope, receive, enviar)
        except Exception:
            # Tratado aqui (e não no ServerErrorMiddleware, mais externo) para a
            # resposta 500 levar o request_id.
            logger.exception("erro não tratado")
            if iniciada:
                raise
            corpo = {
                "type": "about:blank",
                "title": "Internal Server Error",
                "status": 500,
                "code": "ERRO_INTERNO",
                "detail": "Erro interno. Informe o request_id ao suporte.",
                "request_id": rid,
            }
            await enviar(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [(b"content-type", b"application/problem+json")],
                }
            )
            await enviar({"type": "http.response.body", "body": json.dumps(corpo).encode()})
        finally:
            duracao = time.perf_counter() - inicio
            rota = _rota_template(scope)
            metodo = scope["method"]
            self.metricas.requisicoes.labels(metodo, rota, str(status)).inc()
            self.metricas.duracao.labels(metodo, rota).observe(duracao)
            if self.registrar_acesso is not None:
                acesso = evento_acesso(scope, status, rid)
                if acesso is not None:
                    self.registrar_acesso(acesso)  # só enfileira; a gravação é em lote
            evento = evento_auditoria(scope, status, rid) if self.auditar else None
            if evento is not None and self.auditar is not None:
                try:
                    await anyio.to_thread.run_sync(self.auditar, evento)
                except Exception:
                    logger.exception("falha ao gravar auditoria")
            logger.info(
                "requisição",
                extra={
                    "metodo": metodo,
                    "rota": rota,
                    "status": status,
                    "duracao_ms": round(duracao * 1000, 1),
                },
            )
            request_id_var.reset(token)
