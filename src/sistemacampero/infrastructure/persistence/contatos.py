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
                " (nome, email, telefone, fazenda, hectares, maquinas, mensagem, origem, ip_hash,"
                " politica_versao, aceita_novidades)"
                " values (%(nome)s, %(email)s, %(telefone)s, %(fazenda)s, %(hectares)s,"
                " %(maquinas)s, %(mensagem)s, %(origem)s, %(ip_hash)s,"
                " %(politica_versao)s, %(aceita_novidades)s) returning id",
                {**dados, "ip_hash": ip_hash},
            ).fetchone()
        assert linha is not None
        return UUID(str(linha["id"]))

    def expurgar(self, meses: int) -> int:
        """Apaga pedidos mais antigos que o prazo de retenção (LGPD, art. 15 e 16)."""
        with self._db.transacao(None) as conn:
            cur = conn.execute(
                "delete from interno.contatos where criado_em < now() - make_interval(months => %s)",
                (meses,),
            )
        return cur.rowcount


class PostgresAceites:
    """Registro de aceite dos Termos e da Política (prova do consentimento/contratação)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def registrar(
        self, usuario_id: UUID, documentos: list[str], versao: str, ip_hash: str | None
    ) -> None:
        with self._db.transacao(None) as conn:
            for doc in documentos:
                conn.execute(
                    "insert into interno.aceites (usuario_id, documento, versao, ip_hash)"
                    " values (%s, %s, %s, %s)",
                    (usuario_id, doc, versao, ip_hash),
                )
