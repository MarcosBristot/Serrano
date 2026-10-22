"""Middleware ASGI: ``X-Request-ID``, log de acesso e métricas Prometheus."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid

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


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, metricas: Metricas) -> None:
        self.app = app
        self.metricas = metricas

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
