"""Controle do resumo semanal (uma vez por semana por fazenda) e destinos de envio."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sistemacampero.infrastructure.persistence.db import Database


class PostgresResumoSemanal:
    def __init__(self, db: Database) -> None:
        self._db = db

    def orgs_com_destino(self) -> list[dict[str, Any]]:
        with self._db.transacao(None) as conn:
            return conn.execute("select * from interno.orgs_com_destino_ativo()").fetchall()

    def ja_enviado(self, org: UUID, semana: str) -> bool:
        with self._db.transacao(None) as conn:
            return (
                conn.execute(
                    "select 1 from interno.resumos_semanais"
                    " where organizacao_id = %s and semana = %s",
                    (org, semana),
                ).fetchone()
                is not None
            )

    def registrar(self, org: UUID, semana: str, destinos: int, texto: str) -> None:
        with self._db.transacao(None) as conn:
            conn.execute(
                "insert into interno.resumos_semanais (organizacao_id, semana, destinos, texto)"
                " values (%s, %s, %s, %s) on conflict do nothing",
                (org, semana, destinos, texto),
            )

    def destinos(self, org: UUID) -> list[dict[str, Any]]:
        with self._db.transacao(org) as conn:
            return conn.execute(
                "select id, tipo, destino, segredo_cifrado, ativo"
                " from public.destinos_notificacao order by criado_em"
            ).fetchall()

    def nome_org(self, org: UUID) -> str:
        with self._db.transacao(org) as conn:
            linha = conn.execute(
                "select nome from public.organizacoes where id = %s", (org,)
            ).fetchone()
        return str(linha["nome"]) if linha else "Fazenda"
