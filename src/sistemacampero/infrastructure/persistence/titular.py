"""Direitos do titular (LGPD art. 18) e registros de acesso (Marco Civil art. 15)."""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg.errors

from sistemacampero.domain.errors import Conflito
from sistemacampero.infrastructure.persistence.db import Database


class PostgresTitular:
    def __init__(self, db: Database) -> None:
        self._db = db

    def dados(self, usuario_id: UUID) -> dict[str, Any]:
        with self._db.transacao(None) as conn:
            linha = conn.execute(
                "select interno.dados_do_titular(%s) as d", (usuario_id,)
            ).fetchone()
        assert linha is not None
        return dict(linha["d"])

    def impacto(self, usuario_id: UUID) -> list[dict[str, Any]]:
        with self._db.transacao(None) as conn:
            return conn.execute(
                "select organizacao_id, nome, papel, outros_membros, outros_donos"
                " from interno.impacto_exclusao(%s)",
                (usuario_id,),
            ).fetchall()

    def pedido_ativo(self, usuario_id: UUID) -> dict[str, Any] | None:
        with self._db.transacao(None) as conn:
            return conn.execute(
                "select id, status, agendada_para, criado_em, organizacoes"
                " from interno.solicitacoes_exclusao where usuario_id = %s and status = 'agendada'",
                (usuario_id,),
            ).fetchone()

    def agendar(
        self, usuario_id: UUID, email: str | None, organizacoes: list[UUID], quando: datetime
    ) -> dict[str, Any]:
        try:
            with self._db.transacao(None) as conn:
                linha = conn.execute(
                    "insert into interno.solicitacoes_exclusao"
                    " (usuario_id, email, organizacoes, agendada_para) values (%s, %s, %s, %s)"
                    " returning id, status, agendada_para, criado_em, organizacoes",
                    (usuario_id, email, organizacoes, quando),
                ).fetchone()
        except psycopg.errors.UniqueViolation as exc:
            raise Conflito(
                "Já existe uma exclusão agendada.", codigo="EXCLUSAO_JA_AGENDADA"
            ) from exc
        assert linha is not None
        return linha

    def cancelar(self, usuario_id: UUID) -> bool:
        with self._db.transacao(None) as conn:
            cur = conn.execute(
                "update interno.solicitacoes_exclusao set status = 'cancelada'"
                " where usuario_id = %s and status = 'agendada'",
                (usuario_id,),
            )
        return cur.rowcount > 0

    def vencidas(self, limite: int = 20) -> list[dict[str, Any]]:
        with self._db.transacao(None) as conn:
            return conn.execute(
                "select id, usuario_id, email, organizacoes from interno.solicitacoes_exclusao"
                " where status = 'agendada' and agendada_para <= now()"
                " order by agendada_para limit %s",
                (limite,),
            ).fetchall()

    def excluir_organizacao(self, organizacao_id: UUID) -> list[tuple[str, str]]:
        """Apaga a organização no banco e devolve (bucket, caminho) dos arquivos a remover."""
        with self._db.transacao(None) as conn:
            linhas = conn.execute(
                "select bucket, caminho from interno.excluir_organizacao(%s)", (organizacao_id,)
            ).fetchall()
        return [(str(r["bucket"]), str(r["caminho"])) for r in linhas]

    def excluir_titular(self, usuario_id: UUID, email: str | None) -> None:
        with self._db.transacao(None) as conn:
            conn.execute("select interno.excluir_titular(%s, %s)", (usuario_id, email))

    def concluir(self, pedido_id: UUID, erro: str | None = None) -> None:
        with self._db.transacao(None) as conn:
            conn.execute(
                "update interno.solicitacoes_exclusao"
                " set status = %s, concluida_em = now(), erro = %s where id = %s",
                ("erro" if erro else "concluida", erro, pedido_id),
            )


class RegistrosDeAcesso:
    """Fila em memória gravada em lote: o registro não atrasa a resposta da API."""

    def __init__(self, db: Database, maximo_em_memoria: int = 20_000) -> None:
        self._db = db
        self._fila: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._maximo = maximo_em_memoria

    def registrar(self, evento: dict[str, Any]) -> None:
        with self._lock:
            if len(self._fila) < self._maximo:  # banco fora do ar: não estoura a memória
                self._fila.append(evento)

    def gravar_pendentes(self) -> int:
        with self._lock:
            lote, self._fila = self._fila, []
        if not lote:
            return 0
        try:
            with self._db.transacao(None) as conn, conn.cursor() as cur:
                cur.executemany(
                    "insert into interno.registros_acesso"
                    " (ocorrido_em, ip, usuario_id, organizacao_id, metodo, rota, status, request_id)"
                    " values (%(ocorrido_em)s, %(ip)s, %(usuario_id)s, %(organizacao_id)s,"
                    " %(metodo)s, %(rota)s, %(status)s, %(request_id)s)",
                    lote,
                )
        except Exception:
            with self._lock:  # devolve para a próxima tentativa
                self._fila = (lote + self._fila)[: self._maximo]
            raise
        return len(lote)

    def expurgar(self, meses: int) -> int:
        with self._db.transacao(None) as conn:
            cur = conn.execute(
                "delete from interno.registros_acesso"
                " where ocorrido_em < now() - make_interval(months => %s)",
                (meses,),
            )
        return cur.rowcount
