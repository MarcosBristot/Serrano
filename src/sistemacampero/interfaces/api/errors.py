"""Respostas de erro em ``application/problem+json`` (RFC 9457) com ``code`` estável."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from sistemacampero.domain.errors import (
    Conflito,
    ErroDominio,
    Invalido,
    NaoAutenticado,
    NaoEncontrado,
    Proibido,
)
from sistemacampero.infrastructure.logging_config import request_id_var

MEDIA_TYPE = "application/problem+json"

_STATUS: dict[type[ErroDominio], int] = {
    NaoAutenticado: 401,
    Proibido: 403,
    NaoEncontrado: 404,
    Conflito: 409,
    Invalido: 422,
}


def problema(status: int, codigo: str, detalhe: str | None = None, **extras: Any) -> JSONResponse:
    corpo: dict[str, Any] = {
        "type": "about:blank",
        "title": HTTPStatus(status).phrase,
        "status": status,
        "code": codigo,
    }
    if detalhe:
        corpo["detail"] = detalhe
    if rid := request_id_var.get():
        corpo["request_id"] = rid
    corpo.update(extras)
    cabecalhos = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return JSONResponse(corpo, status_code=status, media_type=MEDIA_TYPE, headers=cabecalhos)


def _status_de(exc: ErroDominio) -> int:
    for classe in type(exc).__mro__:
        if classe in _STATUS:
            return _STATUS[classe]
    return 400


def registrar(app: FastAPI) -> None:
    @app.exception_handler(ErroDominio)
    async def _dominio(_: Request, exc: ErroDominio) -> JSONResponse:
        extras = {"detalhes": exc.detalhes} if exc.detalhes else {}
        return problema(_status_de(exc), exc.codigo, exc.mensagem, **extras)

    @app.exception_handler(RequestValidationError)
    async def _validacao(_: Request, exc: RequestValidationError) -> JSONResponse:
        erros = [
            {"loc": list(e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()
        ]
        return problema(422, "VALIDACAO", "Requisição inválida.", errors=erros)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        codigo = "NAO_ENCONTRADO" if exc.status_code == 404 else f"HTTP_{exc.status_code}"
        detalhe = exc.detail if isinstance(exc.detail, str) else None
        return problema(exc.status_code, codigo, detalhe)
