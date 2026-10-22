"""Equipe: membros, convites, chaves de API e auditoria."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import psycopg.errors
from psycopg.types.json import Jsonb

from sistemacampero.domain.errors import Conflito, NaoEncontrado
from sistemacampero.infrastructure.persistence.db import Database


class PostgresRepositorioEquipe:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ------------------------------------------------------------- membros
    def membros(self, org: UUID) -> list[dict[str, Any]]:
        with self._db.transacao(org) as conn:
            return conn.execute(
                "select m.usuario_id, e.email, m.papel, m.criado_em from public.membros m"
                " left join interno.emails_dos_membros() e on e.usuario_id = m.usuario_id"
                " order by m.criado_em"
            ).fetchall()

    def mudar_papel(self, org: UUID, usuario_id: UUID, papel: str | None) -> None:
        """``papel=None`` remove. Nunca deixa a organização sem owner."""
        with self._db.transacao(org) as conn:
            atual = conn.execute(
                "select papel from public.membros where usuario_id = %s for update", (usuario_id,)
            ).fetchone()
            if atual is None:
                raise NaoEncontrado("Membro não encontrado.", codigo="MEMBRO_NAO_ENCONTRADO")
            if atual["papel"] == "owner" and papel != "owner":
                owners = conn.execute(
                    "select count(*) as n from public.membros where papel = 'owner'"
                ).fetchone()
                assert owners is not None
                if owners["n"] <= 1:
                    raise Conflito(
                        "A organização precisa de pelo menos um owner.", codigo="ULTIMO_OWNER"
                    )
            if papel is None:
                conn.execute("delete from public.membros where usuario_id = %s", (usuario_id,))
            else:
                conn.execute(
                    "update public.membros set papel = %s where usuario_id = %s",
                    (papel, usuario_id),
                )

    # ------------------------------------------------------------- convites
    def criar_convite(
        self, org: UUID, email: str, papel: str, token_hash: str, dias: int, criado_por: UUID | None
    ) -> dict[str, Any]:
        with self._db.transacao(org) as conn:
            linha = conn.execute(
                "insert into public.convites (organizacao_id, email, papel, token_hash, expira_em,"
                " criado_por) values (%s, lower(%s), %s, %s, now() + make_interval(days => %s), %s)"
                " returning id, email, papel, expira_em, aceito_em, criado_em",
                (org, email, papel, token_hash, dias, criado_por),
            ).fetchone()
        assert linha is not None
        return linha

    def convites(self, org: UUID) -> list[dict[str, Any]]:
        with self._db.transacao(org) as conn:
            return conn.execute(
                "select id, email, papel, expira_em, aceito_em, criado_em from public.convites"
                " where aceito_em is null and expira_em > now() order by criado_em desc"
            ).fetchall()

    def revogar_convite(self, org: UUID, convite_id: UUID) -> None:
        with self._db.transacao(org) as conn:
            if not conn.execute(
                "delete from public.convites where id = %s and aceito_em is null", (convite_id,)
            ).rowcount:
                raise NaoEncontrado("Convite não encontrado.", codigo="CONVITE_NAO_ENCONTRADO")

    def convite_por_hash(self, token_hash: str) -> dict[str, Any] | None:
        with self._db.transacao(None) as conn:
            return conn.execute(
                "select * from interno.convite_por_hash(%s)", (token_hash,)
            ).fetchone()

    def aceitar_convite(self, org: UUID, convite_id: UUID, usuario_id: UUID, papel: str) -> None:
        try:
            with self._db.transacao(org) as conn:
                n = conn.execute(
                    "update public.convites set aceito_em = now()"
                    " where id = %s and aceito_em is null and expira_em > now()",
                    (convite_id,),
                ).rowcount
                if not n:
                    raise Conflito("Convite expirado ou já usado.", codigo="CONVITE_INVALIDO")
                conn.execute(
                    "insert into public.membros (organizacao_id, usuario_id, papel)"
                    " values (%s, %s, %s)",
                    (org, usuario_id, papel),
                )
        except psycopg.errors.UniqueViolation as exc:
            raise Conflito("Você já participa desta organização.", codigo="JA_E_MEMBRO") from exc

    # ------------------------------------------------------------- chaves de API
    def criar_chave(
        self,
        org: UUID,
        nome: str,
        prefixo: str,
        hash_: str,
        escopos: list[str],
        criado_por: UUID | None,
    ) -> dict[str, Any]:
        with self._db.transacao(org) as conn:
            linha = conn.execute(
                "insert into interno.chaves_api (organizacao_id, nome, prefixo, hash, escopos,"
                " criado_por) values (%s, %s, %s, %s, %s, %s)"
                " returning id, nome, prefixo, escopos, criado_em, ultimo_uso_em, revogada_em",
                (org, nome, prefixo, hash_, escopos, criado_por),
            ).fetchone()
        assert linha is not None
        return linha

    def chaves(self, org: UUID) -> list[dict[str, Any]]:
        with self._db.transacao(org) as conn:
            return conn.execute(
                "select id, nome, prefixo, escopos, criado_em, ultimo_uso_em, revogada_em"
                " from interno.chaves_api where organizacao_id = %s order by criado_em desc",
                (org,),
            ).fetchall()

    def revogar_chave(self, org: UUID, chave_id: UUID) -> None:
        with self._db.transacao(org) as conn:
            if not conn.execute(
                "update interno.chaves_api set revogada_em = now()"
                " where id = %s and organizacao_id = %s and revogada_em is null",
                (chave_id, org),
            ).rowcount:
                raise NaoEncontrado("Chave não encontrada.", codigo="CHAVE_NAO_ENCONTRADA")

    def chave_por_prefixo(self, prefixo: str) -> dict[str, Any] | None:
        with self._db.transacao(None) as conn:
            linha = conn.execute(
                "select id, organizacao_id, hash, escopos, ultimo_uso_em, revogada_em"
                " from interno.chaves_api where prefixo = %s",
                (prefixo,),
            ).fetchone()
            if (
                linha
                and linha["revogada_em"] is None
                and (
                    linha["ultimo_uso_em"] is None
                    or linha["ultimo_uso_em"]
                    < datetime.now(linha["ultimo_uso_em"].tzinfo) - timedelta(minutes=5)
                )
            ):
                conn.execute(
                    "update interno.chaves_api set ultimo_uso_em = now() where id = %s",
                    (linha["id"],),
                )
        return linha

    # ------------------------------------------------------------- auditoria
    def auditar(self, evento: dict[str, Any]) -> None:
        with self._db.transacao(evento.get("organizacao_id")) as conn:
            conn.execute(
                "insert into interno.auditoria (organizacao_id, ator_id, ator_tipo, acao,"
                " recurso_tipo, recurso_id, dados, ip, request_id)"
                " values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    evento.get("organizacao_id"),
                    evento.get("ator_id"),
                    evento.get("ator_tipo", "usuario"),
                    evento["acao"],
                    evento.get("recurso_tipo"),
                    evento.get("recurso_id"),
                    Jsonb(evento.get("dados") or {}),
                    evento.get("ip"),
                    evento.get("request_id"),
                ),
            )

    def auditoria(self, org: UUID, limite: int, antes_de: int | None) -> list[dict[str, Any]]:
        with self._db.transacao(org) as conn:
            return conn.execute(
                "select id, ator_id, ator_tipo, acao, recurso_tipo, recurso_id, dados,"
                " host(ip) as ip, request_id, criado_em from interno.auditoria"
                " where organizacao_id = %s and (%s::bigint is null or id < %s)"
                " order by id desc limit %s",
                (org, antes_de, antes_de, limite),
            ).fetchall()
