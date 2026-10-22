"""Erros tipados do domínio, cada um com um código estável para o frontend.

A camada de interface traduz a categoria do erro em status HTTP; o ``codigo`` não muda
entre versões (o frontend trata por ele).
"""

from __future__ import annotations

from typing import Any


class ErroDominio(Exception):  # noqa: N818 - nomes do domínio em português
    """Base de todos os erros esperados (regra de negócio, permissão, conflito)."""

    codigo: str = "ERRO"

    def __init__(self, mensagem: str, *, codigo: str | None = None, **detalhes: Any) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem
        if codigo is not None:
            self.codigo = codigo
        self.detalhes = detalhes


class NaoAutenticado(ErroDominio):
    codigo = "NAO_AUTENTICADO"


class Proibido(ErroDominio):
    codigo = "PROIBIDO"


class NaoEncontrado(ErroDominio):
    codigo = "NAO_ENCONTRADO"


class Conflito(ErroDominio):
    codigo = "CONFLITO"


class Invalido(ErroDominio):
    codigo = "INVALIDO"


class GrandeDemais(ErroDominio):
    codigo = "ARQUIVO_GRANDE_DEMAIS"
