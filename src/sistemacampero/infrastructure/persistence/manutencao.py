"""Planos de manutenção, histórico e o horímetro atual de cada máquina."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sistemacampero.domain.errors import NaoEncontrado
from sistemacampero.infrastructure.persistence.db import Conexao, Database

# Ritmo de uso: horas de motor por dia trabalhado nos últimos 30 dias com operação.
_USO = """
    -- Média de horas de motor nos dias de trabalho de verdade (>= 1 h) do último ano com
    -- operação: na entressafra a máquina só é ligada para manobra, e isso não é o ritmo.
    select avg(h) as uso_h_dia from (
        select inicio::date as dia, sum(motor_h) as h from public.jornadas
        where maquina_id = %(maq)s
          and inicio >= (select max(inicio) from public.jornadas where maquina_id = %(maq)s)
                        - interval '365 days'
        group by 1 having sum(motor_h) >= 1
    ) d
"""


class PostgresManutencao:
    def __init__(self, db: Database) -> None:
        self._db = db

    @staticmethod
    def _horimetro(conn: Conexao, maquina_id: UUID) -> dict[str, Any]:
        """Do monitor (último horímetro gravado) ou o informado + horas registradas depois."""
        m = conn.execute(
            "select horimetro_informado_h, horimetro_informado_em from public.maquinas"
            " where id = %s",
            (maquina_id,),
        ).fetchone()
        if m is None:
            raise NaoEncontrado("Máquina não encontrada.", codigo="MAQUINA_NAO_ENCONTRADA")
        monitor = conn.execute(
            "select engine_hours as h, ts from public.telemetria"
            " where maquina_id = %s and engine_hours > 0 order by ts desc limit 1",
            (maquina_id,),
        ).fetchone()
        informado = None
        if m["horimetro_informado_h"] is not None:
            depois = conn.execute(
                "select coalesce(sum(motor_h), 0) as h from public.jornadas"
                " where maquina_id = %s and inicio >= %s",
                (maquina_id, m["horimetro_informado_em"]),
            ).fetchone()
            informado = float(m["horimetro_informado_h"]) + float(depois["h"] if depois else 0)
        if monitor is not None and (
            m["horimetro_informado_em"] is None or monitor["ts"] >= m["horimetro_informado_em"]
        ):
            return {"horimetro_h": float(monitor["h"]), "fonte": "monitor", "em": monitor["ts"]}
        if informado is not None:
            return {"horimetro_h": informado, "fonte": "informado", "em": None}
        return {"horimetro_h": None, "fonte": None, "em": None}

    def situacao(self, org: UUID, maquina_id: UUID) -> dict[str, Any]:
        with self._db.transacao(org) as conn:
            horimetro = self._horimetro(conn, maquina_id)
            uso = conn.execute(_USO, {"maq": maquina_id}).fetchone()
            planos = conn.execute(
                "select id, nome, intervalo_h, ultima_h, ultima_em from public.planos_manutencao"
                " where maquina_id = %s and ativo order by intervalo_h, nome",
                (maquina_id,),
            ).fetchall()
            historico = conn.execute(
                "select id, nome, horimetro_h, feita_em, custo_rs::float as custo_rs, observacao"
                " from public.manutencoes_feitas where maquina_id = %s"
                " order by feita_em desc, criado_em desc limit 50",
                (maquina_id,),
            ).fetchall()
        return {
            **horimetro,
            "uso_h_dia": float(uso["uso_h_dia"]) if uso and uso["uso_h_dia"] else None,
            "planos": planos,
            "historico": historico,
        }

    def maquinas_com_planos(self, org: UUID) -> list[dict[str, Any]]:
        with self._db.transacao(org) as conn:
            return conn.execute(
                "select distinct m.id, m.serial, m.apelido, m.modelo"
                " from public.planos_manutencao p join public.maquinas m on m.id = p.maquina_id"
                " where p.ativo and m.ativa",
            ).fetchall()

    def criar_plano(
        self, org: UUID, maquina_id: UUID, nome: str, intervalo_h: float, ultima_h: float | None
    ) -> UUID:
        with self._db.transacao(org) as conn:
            linha = conn.execute(
                "insert into public.planos_manutencao"
                " (organizacao_id, maquina_id, nome, intervalo_h, ultima_h, ultima_em)"
                " values (%s, %s, %s, %s, %s, case when %s::float is null then null"
                "   else current_date end) returning id",
                (org, maquina_id, nome, intervalo_h, ultima_h, ultima_h),
            ).fetchone()
        assert linha is not None
        ident: UUID = linha["id"]
        return ident

    def editar_plano(self, org: UUID, plano_id: UUID, campos: dict[str, Any]) -> None:
        if not campos:
            return
        sets = ", ".join(f"{c} = %s" for c in campos)
        with self._db.transacao(org) as conn:
            r = conn.execute(
                f"update public.planos_manutencao set {sets} where id = %s",  # noqa: S608
                (*campos.values(), plano_id),
            )
            if r.rowcount == 0:
                raise NaoEncontrado("Plano não encontrado.", codigo="PLANO_NAO_ENCONTRADO")

    def registrar_feita(
        self,
        org: UUID,
        plano_id: UUID,
        horimetro_h: float,
        feita_em: date,
        custo_rs: float | None,
        observacao: str | None,
    ) -> None:
        """Guarda no histórico e reinicia a contagem do plano a partir desse horímetro."""
        with self._db.transacao(org) as conn:
            plano = conn.execute(
                "update public.planos_manutencao set ultima_h = %s, ultima_em = %s"
                " where id = %s returning maquina_id, nome",
                (horimetro_h, feita_em, plano_id),
            ).fetchone()
            if plano is None:
                raise NaoEncontrado("Plano não encontrado.", codigo="PLANO_NAO_ENCONTRADO")
            conn.execute(
                "insert into public.manutencoes_feitas (organizacao_id, plano_id, maquina_id,"
                " nome, horimetro_h, feita_em, custo_rs, observacao)"
                " values (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    org,
                    plano_id,
                    plano["maquina_id"],
                    plano["nome"],
                    horimetro_h,
                    feita_em,
                    custo_rs,
                    observacao,
                ),
            )

    def informar_horimetro(self, org: UUID, maquina_id: UUID, horimetro_h: float) -> None:
        with self._db.transacao(org) as conn:
            r = conn.execute(
                "update public.maquinas set horimetro_informado_h = %s,"
                " horimetro_informado_em = now() where id = %s",
                (horimetro_h, maquina_id),
            )
            if r.rowcount == 0:
                raise NaoEncontrado("Máquina não encontrada.", codigo="MAQUINA_NAO_ENCONTRADA")
