"""Proteções HTTP: cabeçalhos de segurança e limite de requisições (por processo).

O limite é em memória (token bucket por chave de cliente): suficiente para o piloto com
uma instância da API. Com várias réplicas, mover para o Postgres ou para o proxy.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

CABECALHOS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"geolocation=(), camera=(), microphone=()"),
    (b"cross-origin-opener-policy", b"same-origin"),
]
SEM_LIMITE = ("/health", "/ready", "/metrics")


class Balde:
    def __init__(self, por_minuto: int) -> None:
        self.capacidade = float(por_minuto)
        self.taxa = por_minuto / 60.0
        self._estado: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def consumir(self, chave: str, agora: float | None = None) -> float:
        """0 = liberado; > 0 = segundos até a próxima ficha."""
        t = time.monotonic() if agora is None else agora
        with self._lock:
            fichas, ultimo = self._estado.get(chave, (self.capacidade, t))
            fichas = min(self.capacidade, fichas + (t - ultimo) * self.taxa)
            if fichas >= 1:
                self._estado[chave] = (fichas - 1, t)
                if len(self._estado) > 50_000:  # evita crescer sem limite
                    self._estado.clear()
                return 0.0
            self._estado[chave] = (fichas, t)
            return (1 - fichas) / self.taxa


def _chave_cliente(scope: Scope) -> str:
    cab = dict(scope.get("headers") or [])
    credencial = cab.get(b"authorization") or cab.get(b"x-api-key")
    if credencial:  # por credencial (hash: nunca guarda o token)
        return "c:" + hashlib.sha256(credencial).hexdigest()[:24]
    cliente = scope.get("client")
    return "ip:" + (cliente[0] if cliente else "?")


class ProtecaoMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        por_minuto: int,
        uploads_por_minuto: int,
        hsts: bool,
        contatos_por_minuto: int = 5,
    ) -> None:
        self.app = app
        self.geral = Balde(por_minuto)
        self.uploads = Balde(uploads_por_minuto)
        self.contatos = Balde(contatos_por_minuto)  # formulário público do site
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        caminho = str(scope["path"])
        if not caminho.startswith(SEM_LIMITE):
            chave = _chave_cliente(scope)
            espera = self.geral.consumir(chave)
            if not espera and caminho.endswith("/upload") and scope["method"] == "POST":
                espera = self.uploads.consumir(chave)
            if not espera and caminho.endswith("/contatos") and scope["method"] == "POST":
                espera = self.contatos.consumir(chave)
            if espera:
                await self._recusar(send, espera)
                return

        async def enviar(msg: Message) -> None:
            if msg["type"] == "http.response.start":
                extras = list(CABECALHOS)
                if self.hsts:
                    extras.append((b"strict-transport-security", b"max-age=31536000"))
                if caminho.startswith("/api/"):
                    extras.append((b"cache-control", b"no-store"))
                msg["headers"] = [*msg.get("headers", []), *extras]
            await send(msg)

        await self.app(scope, receive, enviar)

    @staticmethod
    async def _recusar(send: Send, espera: float) -> None:
        corpo = json.dumps(
            {
                "type": "about:blank",
                "title": "Too Many Requests",
                "status": 429,
                "code": "LIMITE_DE_REQUISICOES",
                "detail": "Muitas requisições; tente de novo em instantes.",
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/problem+json"),
                    (b"retry-after", str(max(1, round(espera))).encode()),
                    *CABECALHOS,
                ],
            }
        )
        await send({"type": "http.response.body", "body": corpo})
