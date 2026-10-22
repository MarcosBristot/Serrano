"""Alertas (ciclo de vida, comentários), configuração de regras, linhas de base,
destinos de notificação e a outbox ``interno.notificacoes``."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from sistemacampero.domain.alertas import AcaoAlerta, transicao
from sistemacampero.domain.errors import NaoEncontrado
from sistemacampero.domain.services.rules import LinhasBase
from sistemacampero.domain.telemetry import MetadadosSessao
from sistemacampero.infrastructure.persistence.db import Database

_ALERTA = (
    "a.id, a.sessao_id, a.maquina_id, m.serial, m.apelido, a.talhao_id, t.nome as talhao_nome,"
    " a.tipo, a.severidade, a.status, a.versao_regras, a.inicio, a.fim, a.valor, a.limiar,"
    " a.mensagem, a.detalhes, a.reconhecido_por, a.reconhecido_em, a.resolvido_por,"
    " a.resolvido_em, a.criado_em, a.atualizado_em"
)
_JUNTAS = (
    " from public.alertas a left join public.maquinas m on m.id = a.maquina_id"
    " left join public.talhoes t on t.id = a.talhao_id"
)


class PostgresRepositorioAlertas:
    def __init__(self, db: Database) -> None:
        self._db = db

    def listar(
        self, org: UUID, f: dict[str, Any], limite: int, cursor: tuple[str, UUID] | None
    ) -> list[dict[str, Any]]:
        where: list[str] = ["true"]
        params: list[Any] = []
        for coluna in ("status", "tipo", "severidade", "maquina_id", "sessao_id", "talhao_id"):
            if f.get(coluna) is not None:
                where.append(f"a.{coluna} = %s")
                params.append(f[coluna])
        if f.get("inicio"):
            where.append("a.criado_em >= %s")
            params.append(f["inicio"])
        if f.get("fim"):
            where.append("a.criado_em < %s")
            params.append(f["fim"])
        if cursor:
            where.append("(a.criado_em, a.id) < (%s::timestamptz, %s)")
            params.extend(cursor)
        with self._db.transacao(org) as conn:
            return conn.execute(
                f"select {_ALERTA}{_JUNTAS} where {' and '.join(where)}"
                " order by a.criado_em desc, a.id desc limit %s",
                (*params, limite),
            ).fetchall()

    def obter(self, org: UUID, alerta_id: UUID) -> dict[str, Any]:
        with self._db.transacao(org) as conn:
            alerta = conn.execute(
                f"select {_ALERTA}{_JUNTAS} where a.id = %s", (alerta_id,)
            ).fetchone()
            if alerta is None:
                raise NaoEncontrado("Alerta não encontrado.", codigo="ALERTA_NAO_ENCONTRADO")
            alerta["comentarios"] = conn.execute(
                "select id, autor_id, texto, criado_em from public.alertas_comentarios"
                " where alerta_id = %s order by criado_em",
                (alerta_id,),
            ).fetchall()
        return alerta

    def mudar_status(
        self, org: UUID, alerta_id: UUID, acao: AcaoAlerta, usuario_id: UUID | None
    ) -> dict[str, Any]:
        with self._db.transacao(org) as conn:
            atual = conn.execute(
                "select status from public.alertas where id = %s for update", (alerta_id,)
            ).fetchone()
            if atual is None:
                raise NaoEncontrado("Alerta não encontrado.", codigo="ALERTA_NAO_ENCONTRADO")
            novo = transicao(atual["status"], acao)
            if acao is AcaoAlerta.REABRIR:
                conn.execute(
                    "update public.alertas set status = %s, resolvido_por = null,"
                    " resolvido_em = null where id = %s",
                    (novo.value, alerta_id),
                )
            else:
                quem = "reconhecido" if acao is AcaoAlerta.RECONHECER else "resolvido"
                conn.execute(
                    f"update public.alertas set status = %s, {quem}_por = %s, {quem}_em = now()"
                    " where id = %s",
                    (novo.value, usuario_id, alerta_id),
                )
        return self.obter(org, alerta_id)

    def comentar(
        self, org: UUID, alerta_id: UUID, autor: UUID | None, texto: str
    ) -> dict[str, Any]:
        with self._db.transacao(org) as conn:
            if (
                conn.execute("select 1 from public.alertas where id = %s", (alerta_id,)).fetchone()
                is None
            ):
                raise NaoEncontrado("Alerta não encontrado.", codigo="ALERTA_NAO_ENCONTRADO")
            linha = conn.execute(
                "insert into public.alertas_comentarios"
                " (alerta_id, organizacao_id, autor_id, texto)"
                " values (%s, %s, %s, %s) returning id, autor_id, texto, criado_em",
                (alerta_id, org, autor, texto),
            ).fetchone()
        assert linha is not None
        return linha

    # ------------------------------------------------------------- config de regras
    def config(self, org: UUID) -> dict[str, Any] | None:
        with self._db.transacao(org) as conn:
            linha = conn.execute(
                "select config from public.config_regras where organizacao_id = %s", (org,)
            ).fetchone()
        return None if linha is None else dict(linha["config"])

    def salvar_config(
        self, org: UUID, versao: str, config: dict[str, Any], usuario: UUID | None
    ) -> None:
        with self._db.transacao(org) as conn:
            conn.execute(
                "insert into public.config_regras (organizacao_id, versao, config, atualizado_por)"
                " values (%s, %s, %s, %s) on conflict (organizacao_id) do update set"
                " versao = excluded.versao, config = excluded.config,"
                " atualizado_por = excluded.atualizado_por, atualizado_em = now()",
                (org, versao, Jsonb(config), usuario),
            )

    def linhas_base(self, org: UUID, meta: MetadadosSessao, sha_atual: str) -> LinhasBase:
        """Medianas das últimas 50 sessões com trabalho (>= 30 min) da mesma combinação."""
        with self._db.transacao(org) as conn:
            linha = conn.execute(
                """
                select count(*) as n,
                    percentile_cont(0.5) within group (order by x.lph_trabalho) as vazao,
                    percentile_cont(0.5) within group (order by x.l_ha) as l_ha
                from (
                    select ms.lph_trabalho, ms.l_ha
                    from public.sessoes_trabalho s
                    join public.maquinas m on m.id = s.maquina_id
                    join public.arquivos_brutos a on a.id = s.arquivo_bruto_id
                    left join public.implementos i on i.id = s.implemento_id
                    join public.metricas_sessao ms on ms.sessao_id = s.id and ms.vigente
                    where m.serial = %s and a.sha256 <> %s
                      and coalesce(lower(i.nome), '') = coalesce(lower(%s), '')
                      and s.operacao is not distinct from %s
                      and ms.trabalho_h >= 0.5
                    order by s.inicio desc limit 50
                ) x
                """,
                (
                    meta.serial_maquina or meta.serial_monitor or "desconhecido",
                    sha_atual,
                    meta.implemento_nome,
                    meta.operacao,
                ),
            ).fetchone()
        if linha is None or not linha["n"]:
            return LinhasBase()
        return LinhasBase(linha["vazao"], linha["l_ha"], int(linha["n"]))

    def arquivos_processados(self, org: UUID) -> list[UUID]:
        with self._db.transacao(org) as conn:
            return [
                x["id"]
                for x in conn.execute(
                    "select id from public.arquivos_brutos where status = 'processado'"
                    " and tipo = 'jdl'"
                ).fetchall()
            ]

    # ------------------------------------------------------------- destinos e outbox
    def destinos(self, org: UUID) -> list[dict[str, Any]]:
        with self._db.transacao(org) as conn:
            return conn.execute(
                "select id, tipo, destino, severidade_minima, ativo,"
                " segredo_cifrado is not null as tem_segredo, criado_em, atualizado_em"
                " from public.destinos_notificacao order by criado_em"
            ).fetchall()

    def criar_destino(self, org: UUID, dados: dict[str, Any]) -> dict[str, Any]:
        with self._db.transacao(org) as conn:
            linha = conn.execute(
                "insert into public.destinos_notificacao (organizacao_id, tipo, destino,"
                " segredo_cifrado, severidade_minima, ativo) values (%s, %s, %s, %s, %s, %s)"
                " returning id",
                (
                    org,
                    dados["tipo"],
                    dados["destino"],
                    dados.get("segredo_cifrado"),
                    dados.get("severidade_minima", "atencao"),
                    dados.get("ativo", True),
                ),
            ).fetchone()
        assert linha is not None
        return next(d for d in self.destinos(org) if d["id"] == linha["id"])

    def atualizar_destino(self, org: UUID, ident: UUID, dados: dict[str, Any]) -> dict[str, Any]:
        campos = {k: v for k, v in dados.items() if k in ("destino", "severidade_minima", "ativo")}
        if campos:
            with self._db.transacao(org) as conn:
                n = conn.execute(
                    "update public.destinos_notificacao set "
                    + ", ".join(f"{c} = %s" for c in campos)
                    + " where id = %s",
                    (*campos.values(), ident),
                ).rowcount
            if not n:
                raise NaoEncontrado("Destino não encontrado.")
        destino = next((d for d in self.destinos(org) if d["id"] == ident), None)
        if destino is None:
            raise NaoEncontrado("Destino não encontrado.")
        return destino

    def apagar_destino(self, org: UUID, ident: UUID) -> None:
        with self._db.transacao(org) as conn:
            if not conn.execute(
                "delete from public.destinos_notificacao where id = %s", (ident,)
            ).rowcount:
                raise NaoEncontrado("Destino não encontrado.")

    def destino_completo(self, org: UUID, ident: UUID) -> dict[str, Any]:
        with self._db.transacao(org) as conn:
            linha = conn.execute(
                "select * from public.destinos_notificacao where id = %s", (ident,)
            ).fetchone()
        if linha is None:
            raise NaoEncontrado("Destino não encontrado.")
        return linha

    def reivindicar_notificacoes(self, limite: int) -> list[dict[str, Any]]:
        """Pendentes de qualquer org (FOR UPDATE SKIP LOCKED); adia 5 min enquanto envia."""
        with self._db.transacao(None) as conn:
            return conn.execute(
                """
                update interno.notificacoes n set proxima_tentativa = now() + interval '5 min',
                    tentativas = n.tentativas + 1
                where n.id in (
                    select id from interno.notificacoes
                    where status in ('pendente', 'erro') and proxima_tentativa <= now()
                    order by proxima_tentativa for update skip locked limit %s)
                returning n.id, n.organizacao_id, n.alerta_id, n.destino_id, n.tentativas
                """,
                (limite,),
            ).fetchall()

    def dados_notificacao(
        self, org: UUID, alerta_id: UUID, destino_id: UUID
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        return self.obter(org, alerta_id), self.destino_completo(org, destino_id)

    def marcar_notificacao(self, ident: UUID, ok: bool, erro: str | None, tentativas: int) -> None:
        status = "enviada" if ok else ("morta" if tentativas >= 5 else "erro")
        with self._db.transacao(None) as conn:
            conn.execute(
                "update interno.notificacoes set status = %s, erro = %s,"
                " enviado_em = case when %s then now() else enviado_em end,"
                " proxima_tentativa = now() + make_interval(secs => %s) where id = %s",
                (status, (erro or "")[:1000] or None, ok, 60 * 2**tentativas, ident),
            )
