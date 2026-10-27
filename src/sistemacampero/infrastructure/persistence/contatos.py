"""Pedidos de demonstração vindos do site (sem organização)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sistemacampero.infrastructure.persistence.db import Database


class PostgresContatos:
    def __init__(self, db: Database) -> None:
        self._db = db

    def registrar(self, dados: dict[str, Any], ip_hash: str | None) -> UUID:
        with self._db.transacao(None) as conn:
            linha = conn.execute(
                "insert into interno.contatos"
                " (nome, email, telefone, fazenda, hectares, maquinas, mensagem, origem, ip_hash)"
                " values (%(nome)s, %(email)s, %(telefone)s, %(fazenda)s, %(hectares)s,"
                " %(maquinas)s, %(mensagem)s, %(origem)s, %(ip_hash)s) returning id",
                {**dados, "ip_hash": ip_hash},
            ).fetchone()
        assert linha is not None
        return UUID(str(linha["id"]))
