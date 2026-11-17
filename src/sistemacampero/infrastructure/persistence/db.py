"""Pool de conexões psycopg 3 e transações com a organização ativa.

Toda transação de negócio executa ``set_config('app.organizacao_id', <org>, true)``:
as policies de RLS do papel ``campero_backend`` filtram por esse valor, então um
``WHERE organizacao_id`` esquecido no código ainda é bloqueado pelo banco.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

Conexao = psycopg.Connection[dict[str, Any]]


class Database:
    def __init__(
        self,
        dsn: str,
        *,
        min_size: int = 1,
        max_size: int = 10,
        modo_pooler: str = "sessao",
        abrir: bool = True,
    ) -> None:
        kwargs: dict[str, object] = {"row_factory": dict_row, "autocommit": False}
        if modo_pooler == "transacao":
            # O pooler em modo transação não suporta prepared statements no servidor.
            kwargs["prepare_threshold"] = None
        self.pool: ConnectionPool[Conexao] = ConnectionPool(
            dsn,
            min_size=min_size,
            max_size=max_size,
            kwargs=kwargs,
            open=False,
            name="campero",
            check=ConnectionPool.check_connection,
            # Padrão do psycopg_pool: desiste de reconectar após 5 min, e o processo fica
            # sem conexões para sempre (PoolTimeout em loop). Queda de rede longa, hibernação
            # ou manutenção do banco não pode matar o worker: continua tentando, com backoff.
            reconnect_timeout=24 * 3600,
        )
        if abrir:
            self.pool.open(wait=False)

    def fechar(self) -> None:
        self.pool.close()

    @contextmanager
    def transacao(self, organizacao_id: UUID | None) -> Iterator[Conexao]:
        """Abre uma transação; com ``organizacao_id``, fixa a org para a RLS."""
        with self.pool.connection() as conn, conn.transaction():
            if organizacao_id is not None:
                conn.execute(
                    "select set_config('app.organizacao_id', %s, true)", (str(organizacao_id),)
                )
            yield conn

    def ping(self) -> None:
        with self.pool.connection(timeout=3) as conn:
            conn.execute("select 1")
