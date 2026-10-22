"""Repositório de ingestão (arquivos, lotes) e fila durável de jobs.

A fila é a tabela ``interno.jobs`` (ADR 0004/D2):
* ``reivindicar``: transação curta com ``FOR UPDATE SKIP LOCKED`` + lease;
* o processamento roda FORA dessa transação, renovando o lease (heartbeat);
* ``recolher_vencidos`` devolve à fila o que ficou com lease vencido (worker morreu);
* retentativa com backoff exponencial e jitter; esgotou -> ``morto`` (dead-letter).
"""

from __future__ import annotations

import random
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from sistemacampero.domain.ingestao import (
    PRIORIDADE,
    ArquivoRegistrado,
    Job,
    NovoArquivo,
    SituacaoJob,
    StatusArquivo,
    StatusJob,
    TipoJob,
)
from sistemacampero.infrastructure.persistence.db import Conexao, Database

BACKOFF_BASE_S = 30
BACKOFF_MAX_S = 3600


def backoff_s(tentativa: int, sorteio: float | None = None) -> float:
    """30 s · 2^(n-1), no máximo 1 h, com jitter de ±20%."""
    base = min(BACKOFF_BASE_S * 2 ** max(tentativa - 1, 0), BACKOFF_MAX_S)
    fator = 0.8 + 0.4 * (random.random() if sorteio is None else sorteio)  # noqa: S311
    return float(base * fator)


class PostgresRepositorioIngestao:
    def __init__(self, db: Database) -> None:
        self._db = db

    def _enfileirar(
        self,
        conn: Conexao,
        organizacao_id: UUID,
        tipo: TipoJob,
        payload: dict[str, Any],
        lote_id: UUID | None,
        chave: str | None,
    ) -> UUID:
        linha = conn.execute(
            "insert into interno.jobs (organizacao_id, lote_id, tipo, payload, prioridade,"
            " chave_idempotencia) values (%s, %s, %s, %s, %s, %s)"
            " on conflict (organizacao_id, tipo, chave_idempotencia) do update"
            " set atualizado_em = interno.jobs.atualizado_em"  # no-op para obter o id
            " returning id",
            (organizacao_id, lote_id, tipo.value, Jsonb(payload), PRIORIDADE[tipo], chave),
        ).fetchone()
        assert linha is not None
        job_id: UUID = linha["id"]  # type: ignore[assignment]
        return job_id

    def registrar_arquivo(
        self, novo: NovoArquivo, enfileirar: TipoJob | None, chave_job: str | None = None
    ) -> ArquivoRegistrado:
        with self._db.transacao(novo.organizacao_id) as conn:
            linha = conn.execute(
                "insert into public.arquivos_brutos (organizacao_id, lote_id, arquivo_pai_id,"
                " sha256, nome_original, caminho_storage, tamanho_bytes, tipo, marca, tecnologia)"
                " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                " on conflict (organizacao_id, sha256) do nothing returning id",
                (
                    novo.organizacao_id,
                    novo.lote_id,
                    novo.arquivo_pai_id,
                    novo.sha256,
                    novo.nome_original,
                    novo.caminho_storage,
                    novo.tamanho_bytes,
                    novo.tipo.value,
                    novo.marca,
                    novo.tecnologia,
                ),
            ).fetchone()
            if linha is None:  # já existia: devolve o que há, sem novo job
                existente = conn.execute(
                    "select a.id, a.status,"
                    " (select j.id from interno.jobs j"
                    "   where j.organizacao_id = a.organizacao_id"
                    "     and j.payload->>'arquivo_id' = a.id::text"
                    "   order by j.criado_em desc limit 1)"
                    " as job_id"
                    " from public.arquivos_brutos a where a.organizacao_id = %s and a.sha256 = %s",
                    (novo.organizacao_id, novo.sha256),
                ).fetchone()
                assert existente is not None
                return ArquivoRegistrado(
                    arquivo_id=existente["id"],  # type: ignore[arg-type]
                    job_id=existente["job_id"],  # type: ignore[arg-type]
                    duplicado=True,
                    status=StatusArquivo(str(existente["status"])),
                )
            arquivo_id: UUID = linha["id"]  # type: ignore[assignment]
            job_id = None
            if enfileirar is not None:
                job_id = self._enfileirar(
                    conn,
                    novo.organizacao_id,
                    enfileirar,
                    {"arquivo_id": str(arquivo_id)},
                    novo.lote_id,
                    chave_job or f"{enfileirar.value}:{novo.sha256}",
                )
            return ArquivoRegistrado(arquivo_id, job_id, False, StatusArquivo.RECEBIDO)

    def criar_lote(self, organizacao_id: UUID, usuario_id: UUID | None, origem: str) -> UUID:
        with self._db.transacao(organizacao_id) as conn:
            linha = conn.execute(
                "insert into public.lotes_upload (organizacao_id, criado_por, origem)"
                " values (%s, %s, %s) returning id",
                (organizacao_id, usuario_id, origem),
            ).fetchone()
        assert linha is not None
        lote: UUID = linha["id"]  # type: ignore[assignment]
        return lote

    def obter_lote(self, organizacao_id: UUID, lote_id: UUID) -> dict[str, Any] | None:
        with self._db.transacao(organizacao_id) as conn:
            return conn.execute(
                "select * from public.lotes_upload_status where id = %s", (lote_id,)
            ).fetchone()

    def obter_arquivo(self, organizacao_id: UUID, arquivo_id: UUID) -> dict[str, Any] | None:
        with self._db.transacao(organizacao_id) as conn:
            return conn.execute(
                "select * from public.arquivos_brutos where id = %s", (arquivo_id,)
            ).fetchone()

    def listar_arquivos(
        self,
        organizacao_id: UUID,
        status: str | None,
        limite: int,
        cursor: tuple[str, UUID] | None,
    ) -> list[dict[str, Any]]:
        """Keyset por (criado_em desc, id desc)."""
        filtros: list[str] = ["true"]
        params: list[Any] = []
        if status:
            filtros.append("status = %s")
            params.append(status)
        if cursor:
            filtros.append("(criado_em, id) < (%s::timestamptz, %s)")
            params.extend(cursor)
        sql = (
            "select id, lote_id, arquivo_pai_id, sha256, nome_original, tamanho_bytes, tipo,"
            " marca, tecnologia, status, motivo, criado_em, atualizado_em"
            f" from public.arquivos_brutos where {' and '.join(filtros)}"
            " order by criado_em desc, id desc limit %s"
        )
        with self._db.transacao(organizacao_id) as conn:
            return conn.execute(sql, (*params, limite)).fetchall()

    def marcar_arquivo(
        self, organizacao_id: UUID, arquivo_id: UUID, status: StatusArquivo, motivo: str | None
    ) -> None:
        with self._db.transacao(organizacao_id) as conn:
            conn.execute(
                "update public.arquivos_brutos set status = %s, motivo = %s where id = %s",
                (status.value, motivo, arquivo_id),
            )

    def enfileirar(
        self,
        organizacao_id: UUID,
        tipo: TipoJob,
        payload: dict[str, Any],
        lote_id: UUID | None = None,
        chave: str | None = None,
    ) -> UUID:
        with self._db.transacao(organizacao_id) as conn:
            return self._enfileirar(conn, organizacao_id, tipo, payload, lote_id, chave)

    def reabrir_bloqueados(self, organizacao_id: UUID) -> int:
        """Vaga no plano (upgrade/desativação): reprocessa os arquivos bloqueados."""
        with self._db.transacao(organizacao_id) as conn:
            ids = conn.execute(
                "update public.arquivos_brutos set status = 'recebido', motivo = null"
                " where status = 'bloqueado_plano' returning id, lote_id"
            ).fetchall()
            for linha in ids:
                self._enfileirar(
                    conn,
                    organizacao_id,
                    TipoJob.PROCESSAR_ARQUIVO,
                    {"arquivo_id": str(linha["id"])},
                    linha["lote_id"],  # type: ignore[arg-type]
                    None,
                )
        return len(ids)


class PostgresFilaDeJobs:
    def __init__(self, db: Database) -> None:
        self._db = db

    def reivindicar(self, worker_id: str, lease_s: int) -> Job | None:
        with self._db.transacao(None) as conn:
            linha = conn.execute(
                "update interno.jobs j set status = 'executando', locked_by = %s,"
                " locked_at = now(), lease_ate = now() + make_interval(secs => %s),"
                " tentativas = j.tentativas + 1, erro = null"
                " where j.id = ("
                "   select id from interno.jobs"
                "   where status = 'pendente' and proxima_tentativa <= now()"
                "     and not cancelamento_solicitado"
                "   order by prioridade, proxima_tentativa, criado_em"
                "   for update skip locked limit 1)"
                " returning id, organizacao_id, lote_id, tipo, payload, tentativas, max_tentativas",
                (worker_id, lease_s),
            ).fetchone()
        if linha is None:
            return None
        return Job(
            id=linha["id"],  # type: ignore[arg-type]
            organizacao_id=linha["organizacao_id"],  # type: ignore[arg-type]
            tipo=TipoJob(str(linha["tipo"])),
            payload=dict(linha["payload"]),  # type: ignore[call-overload]
            tentativas=int(linha["tentativas"]),  # type: ignore[call-overload]
            max_tentativas=int(linha["max_tentativas"]),  # type: ignore[call-overload]
            lote_id=linha["lote_id"],  # type: ignore[arg-type]
        )

    def renovar(self, job_id: UUID, worker_id: str, lease_s: int) -> bool:
        with self._db.transacao(None) as conn:
            cur = conn.execute(
                "update interno.jobs set lease_ate = now() + make_interval(secs => %s)"
                " where id = %s and status = 'executando' and locked_by = %s",
                (lease_s, job_id, worker_id),
            )
            return cur.rowcount == 1

    def cancelamento_solicitado(self, job_id: UUID) -> bool:
        with self._db.transacao(None) as conn:
            linha = conn.execute(
                "select cancelamento_solicitado from interno.jobs where id = %s", (job_id,)
            ).fetchone()
        return bool(linha and linha["cancelamento_solicitado"])

    def progresso(self, job_id: UUID, dados: dict[str, Any]) -> None:
        with self._db.transacao(None) as conn:
            conn.execute(
                "update interno.jobs set progresso = progresso || %s where id = %s",
                (Jsonb(dados), job_id),
            )

    def _finalizar(self, sql: str, params: tuple[Any, ...]) -> int:
        with self._db.transacao(None) as conn:
            return conn.execute(sql, params).rowcount

    def concluir(self, job_id: UUID, worker_id: str, resultado: dict[str, Any]) -> None:
        self._finalizar(
            "update interno.jobs set status = 'concluido', locked_by = null, lease_ate = null,"
            " progresso = progresso || %s where id = %s and locked_by = %s",
            (Jsonb({"resultado": resultado}), job_id, worker_id),
        )

    def falhar(self, job_id: UUID, worker_id: str, erro: str, definitivo: bool = False) -> str:
        with self._db.transacao(None) as conn:
            linha = conn.execute(
                "select tentativas, max_tentativas from interno.jobs"
                " where id = %s and locked_by = %s for update",
                (job_id, worker_id),
            ).fetchone()
            if linha is None:
                return "lease_perdido"
            tentativas = int(linha["tentativas"])  # type: ignore[call-overload]
            esgotou = definitivo or tentativas >= int(linha["max_tentativas"])  # type: ignore[call-overload]
            status = StatusJob.MORTO if esgotou else StatusJob.PENDENTE
            conn.execute(
                "update interno.jobs set status = %s, erro = %s, locked_by = null,"
                " lease_ate = null, proxima_tentativa = now() + make_interval(secs => %s)"
                " where id = %s",
                (status.value, erro[:2000], 0 if esgotou else backoff_s(tentativas), job_id),
            )
        return status.value

    def marcar_cancelado(self, job_id: UUID, worker_id: str) -> None:
        self._finalizar(
            "update interno.jobs set status = 'cancelado', locked_by = null, lease_ate = null"
            " where id = %s and locked_by = %s",
            (job_id, worker_id),
        )

    def recolher_vencidos(self) -> int:
        with self._db.transacao(None) as conn:
            return conn.execute(
                "update interno.jobs set"
                " status = case when tentativas >= max_tentativas then 'morto' else 'pendente' end,"
                " erro = 'lease vencido (worker parou durante o processamento)',"
                " locked_by = null, lease_ate = null, proxima_tentativa = now()"
                " where status = 'executando' and lease_ate < now()"
            ).rowcount

    # ------------------------------------------------------------- API/admin
    def situacao(self, organizacao_id: UUID, job_id: UUID) -> SituacaoJob | None:
        with self._db.transacao(organizacao_id) as conn:
            linha = conn.execute(
                "select id, tipo, status, tentativas, max_tentativas, progresso, erro, payload,"
                " lote_id, criado_em, atualizado_em from interno.jobs"
                " where id = %s and organizacao_id = %s",  # interno não tem RLS: filtro explícito
                (job_id, organizacao_id),
            ).fetchone()
        if linha is None:
            return None
        payload: dict[str, Any] = linha["payload"]  # type: ignore[assignment]
        arquivo = payload.get("arquivo_id")
        return SituacaoJob(
            id=linha["id"],  # type: ignore[arg-type]
            tipo=str(linha["tipo"]),
            status=str(linha["status"]),
            tentativas=int(linha["tentativas"]),  # type: ignore[call-overload]
            max_tentativas=int(linha["max_tentativas"]),  # type: ignore[call-overload]
            progresso=dict(linha["progresso"]),  # type: ignore[call-overload]
            erro=linha["erro"],  # type: ignore[arg-type]
            arquivo_id=UUID(arquivo) if arquivo else None,
            lote_id=linha["lote_id"],  # type: ignore[arg-type]
            criado_em=linha["criado_em"],  # type: ignore[arg-type]
            atualizado_em=linha["atualizado_em"],  # type: ignore[arg-type]
        )

    def solicitar_cancelamento(self, organizacao_id: UUID, job_id: UUID) -> str | None:
        """Pendente: cancela já. Executando: o worker para na próxima etapa."""
        with self._db.transacao(organizacao_id) as conn:
            linha = conn.execute(
                "update interno.jobs set cancelamento_solicitado = true,"
                " status = case when status = 'pendente' then 'cancelado' else status end"
                " where id = %s and organizacao_id = %s"
                "   and status in ('pendente', 'executando')"
                " returning status",
                (job_id, organizacao_id),
            ).fetchone()
            if linha is None:
                atual = conn.execute(
                    "select status from interno.jobs where id = %s and organizacao_id = %s",
                    (job_id, organizacao_id),
                ).fetchone()
                return None if atual is None else str(atual["status"])
        return str(linha["status"])

    def listar(self, organizacao_id: UUID, status: str | None, limite: int) -> list[dict[str, Any]]:
        with self._db.transacao(organizacao_id) as conn:
            return conn.execute(
                "select id, tipo, status, tentativas, max_tentativas, erro, payload, criado_em,"
                " atualizado_em from interno.jobs where organizacao_id = %s"
                " and (%s::text is null or status = %s) order by criado_em desc limit %s",
                (organizacao_id, status, status, limite),
            ).fetchall()

    def reenfileirar(self, organizacao_id: UUID, job_id: UUID) -> bool:
        """Admin: tira do dead-letter (ou do erro/cancelado) e zera as tentativas."""
        with self._db.transacao(organizacao_id) as conn:
            return (
                conn.execute(
                    "update interno.jobs set status = 'pendente', tentativas = 0, erro = null,"
                    " cancelamento_solicitado = false, proxima_tentativa = now()"
                    " where id = %s and organizacao_id = %s"
                    "   and status in ('morto', 'erro', 'cancelado')",
                    (job_id, organizacao_id),
                ).rowcount
                == 1
            )
