"""Repositório de organizações e membros (SQL explícito)."""

from __future__ import annotations

from uuid import UUID

import psycopg.errors

from sistemacampero.domain.errors import Conflito
from sistemacampero.domain.tenancy import Organizacao, Papel, Vinculo
from sistemacampero.infrastructure.persistence.db import Database


class PostgresRepositorioOrganizacoes:
    def __init__(self, db: Database) -> None:
        self._db = db

    def vinculos_do_usuario(self, usuario_id: UUID) -> list[Vinculo]:
        # Antes de conhecer a org ativa a RLS não deixa ver nada: a função
        # SECURITY DEFINER devolve só os vínculos deste usuário.
        with self._db.transacao(None) as conn:
            linhas = conn.execute(
                "select organizacao_id, nome, slug, papel"
                " from interno.vinculos_do_usuario(%s) order by nome",
                (usuario_id,),
            ).fetchall()
        return [
            Vinculo(
                organizacao_id=linha["organizacao_id"],  # type: ignore[arg-type]
                organizacao_nome=str(linha["nome"]),
                organizacao_slug=str(linha["slug"]),
                papel=Papel(str(linha["papel"])),
            )
            for linha in linhas
        ]

    def criar_organizacao(
        self, org: Organizacao, dono_id: UUID, plano_codigo: str, dias_trial: int
    ) -> None:
        try:
            with self._db.transacao(org.id) as conn:
                conn.execute(
                    "insert into public.organizacoes (id, nome, slug, fuso, inicio_safra_mes)"
                    " values (%s, %s, %s, %s, %s)",
                    (org.id, org.nome, org.slug, org.fuso, org.inicio_safra_mes),
                )
                conn.execute(
                    "insert into public.membros (organizacao_id, usuario_id, papel)"
                    " values (%s, %s, 'owner')",
                    (org.id, dono_id),
                )
                conn.execute(
                    "insert into public.assinaturas"
                    " (organizacao_id, plano_codigo, status, inicio, fim)"
                    " values (%s, %s, 'trial', now(), now() + make_interval(days => %s))",
                    (org.id, plano_codigo, dias_trial),
                )
        except psycopg.errors.UniqueViolation as exc:
            if exc.diag.constraint_name == "organizacoes_slug_key":
                raise Conflito("Slug já está em uso.", codigo="SLUG_EM_USO") from exc
            raise
