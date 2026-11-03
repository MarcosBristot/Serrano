"""Consultas de KPIs, métricas diárias, mapas e rotas legadas.

``metricas_diarias`` é recalculada a partir da telemetria (1 Hz) por dia LOCAL (fuso da
organização), máquina, talhão de CADA PONTO e operação. Assim uma sessão que atravessa
meia-noite ou dois talhões é repartida corretamente. A área da sessão (cobertura, ou
estimada sem GPS) é repartida pela distância trabalhada em cada parte.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

import pandas as pd
import psycopg.errors

from sistemacampero.domain.errors import Conflito
from sistemacampero.domain.services.kpis import Somas
from sistemacampero.infrastructure.persistence.db import Conexao, Database

_SOMAS = (
    "coalesce(sum(d.motor_h), 0) as motor_h, coalesce(sum(d.trabalho_h), 0) as trabalho_h,"
    " coalesce(sum(d.ocioso_h), 0) as ocioso_h, coalesce(sum(d.litros), 0) as litros,"
    " coalesce(sum(d.litros_trabalho), 0) as litros_trabalho,"
    " coalesce(sum(d.litros_ocioso), 0) as litros_ocioso,"
    " coalesce(sum(d.area_ha), 0) as area_ha, coalesce(sum(d.distancia_km), 0) as distancia_km,"
    " sum(d.litros * p.preco_rs_l)::float as custo_rs,"
    " count(*) filter (where p.preco_rs_l is null and d.litros > 0) as dias_sem_preco"
)
# Preço vigente no dia (tipo S10 por enquanto; por máquina entra quando houver o cadastro).
_PRECO = (
    " left join lateral (select pc.preco_rs_l from public.preco_combustivel pc"
    "   where pc.tipo = 'S10' and pc.valido_de <= d.dia"
    "     and (pc.valido_ate is null or pc.valido_ate > d.dia)"
    "   order by pc.valido_de desc limit 1) p on true"
)


def somas(linha: dict[str, Any]) -> Somas:
    return Somas(
        motor_h=float(linha["motor_h"]),
        trabalho_h=float(linha["trabalho_h"]),
        ocioso_h=float(linha["ocioso_h"]),
        litros=float(linha["litros"]),
        litros_trabalho=float(linha["litros_trabalho"]),
        litros_ocioso=float(linha["litros_ocioso"]),
        area_ha=float(linha["area_ha"]),
        distancia_km=float(linha["distancia_km"]),
        custo_rs=None
        if linha["custo_rs"] is None or linha["dias_sem_preco"]
        else float(linha["custo_rs"]),
    )


def _filtros(f: dict[str, Any], alias: str = "d") -> tuple[str, list[Any]]:
    where, params = [f"{alias}.versao_regras = %s"], [f["versao"]]
    if f.get("inicio"):
        where.append(f"{alias}.dia >= %s")
        params.append(f["inicio"])
    if f.get("fim"):
        where.append(f"{alias}.dia <= %s")
        params.append(f["fim"])
    for coluna in ("maquina_id", "talhao_id", "operacao"):
        if f.get(coluna) is not None:
            where.append(f"{alias}.{coluna} = %s")
            params.append(f[coluna])
    return " and ".join(where), params


def recalcular_diarias(
    conn: Conexao, org: UUID, maquina_id: UUID, inicio: datetime, fim: datetime, versao: str
) -> int:
    """Refaz os dias (locais) tocados por [inicio, fim] para a máquina, numa transação."""
    dias = conn.execute(
        "select (%s::timestamptz at time zone o.fuso)::date as d0,"
        " (%s::timestamptz at time zone o.fuso)::date as d1, o.fuso"
        " from public.organizacoes o where o.id = %s",
        (inicio, fim, org),
    ).fetchone()
    assert dias is not None
    d0, d1, fuso = dias["d0"], dias["d1"], dias["fuso"]
    conn.execute(
        "delete from public.metricas_diarias where maquina_id = %s and versao_regras = %s"
        " and dia between %s and %s",
        (maquina_id, versao, d0, d1),
    )
    return conn.execute(
        """
        with pts as (
            select (t.ts at time zone %(fuso)s)::date as dia,
                -- manual vale para tudo; o talhão do monitor cobre pontos fora de contornos
                -- conhecidos; localizado por GPS reparte ponto a ponto.
                case s.talhao_origem
                    when 'manual' then s.talhao_id
                    when 'monitor' then coalesce(t.talhao_id, s.talhao_id)
                    else t.talhao_id
                end as talhao_id,
                s.operacao, t.sessao_id,
                count(*) filter (where t.engine_on) as motor_s,
                count(*) filter (where t.engine_on and t.speed_kmh >= 1) as trabalho_s,
                count(*) filter (where t.engine_on and t.speed_kmh < 1) as ocioso_s,
                coalesce(sum(t.fuel_rate_lph) filter (where t.engine_on), 0) / 3600 as litros,
                coalesce(sum(t.fuel_rate_lph) filter (where t.engine_on and t.speed_kmh >= 1), 0)
                    / 3600 as litros_trabalho,
                coalesce(sum(t.fuel_rate_lph) filter (where t.engine_on and t.speed_kmh < 1), 0)
                    / 3600 as litros_ocioso,
                coalesce(sum(t.speed_kmh) filter (where t.engine_on and t.speed_kmh >= 1), 0)
                    / 3600 as distancia_km
            from public.telemetria t
            join public.sessoes_trabalho s on s.id = t.sessao_id
            where t.maquina_id = %(maq)s
              and t.ts >= (%(d0)s::date)::timestamp at time zone %(fuso)s
              and t.ts < (%(d1)s::date + 1)::timestamp at time zone %(fuso)s
            group by 1, 2, 3, 4
        ), partes as (
            select p.*,
                coalesce(ms.area_cobertura_ha, ms.area_estimada_ha, 0)
                  * case when ms.distancia_trabalho_km > 0
                         then least(p.distancia_km / ms.distancia_trabalho_km, 1) else 0 end
                  as area_ha
            from pts p
            left join public.metricas_sessao ms on ms.sessao_id = p.sessao_id and ms.vigente
        )
        insert into public.metricas_diarias (organizacao_id, dia, maquina_id, talhao_id, operacao,
            versao_regras, sessoes, motor_h, trabalho_h, ocioso_h, litros, litros_trabalho,
            litros_ocioso, area_ha, distancia_km)
        select %(org)s, dia, %(maq)s, talhao_id, operacao, %(versao)s, count(distinct sessao_id),
            sum(motor_s) / 3600.0, sum(trabalho_s) / 3600.0, sum(ocioso_s) / 3600.0,
            sum(litros), sum(litros_trabalho), sum(litros_ocioso), sum(area_ha), sum(distancia_km)
        from partes group by dia, talhao_id, operacao
        """,
        {"fuso": fuso, "maq": maquina_id, "d0": d0, "d1": d1, "org": org, "versao": versao},
    ).rowcount


class PostgresConsultasKpi:
    def __init__(self, db: Database) -> None:
        self._db = db

    def inicio_safra_mes(self, org: UUID) -> int:
        with self._db.transacao(org) as conn:
            linha = conn.execute(
                "select inicio_safra_mes from public.organizacoes where id = %s", (org,)
            ).fetchone()
        return int(linha["inicio_safra_mes"]) if linha else 7

    def resumo(self, org: UUID, f: dict[str, Any]) -> dict[str, Any]:
        where, params = _filtros(f)
        sw, sp = ["true"], []
        if f.get("inicio"):
            sw.append("(s.inicio at time zone o.fuso)::date >= %s")
            sp.append(f["inicio"])
        if f.get("fim"):
            sw.append("(s.inicio at time zone o.fuso)::date <= %s")
            sp.append(f["fim"])
        for coluna in ("maquina_id", "talhao_id", "operacao"):
            if f.get(coluna) is not None:
                sw.append(f"s.{coluna} = %s")
                sp.append(f[coluna])
        with self._db.transacao(org) as conn:
            linha = conn.execute(
                f"select {_SOMAS}, count(distinct d.maquina_id) as maquinas,"
                f" min(d.dia) as primeiro_dia, max(d.dia) as ultimo_dia"
                f" from public.metricas_diarias d {_PRECO} where {where}",
                params,
            ).fetchone()
            sessoes = conn.execute(
                "select count(*) as n from public.sessoes_trabalho s"
                f" join public.organizacoes o on o.id = s.organizacao_id where {' and '.join(sw)}",
                sp,
            ).fetchone()
        assert linha is not None and sessoes is not None
        return {**linha, "sessoes": int(sessoes["n"])}

    def serie(self, org: UUID, f: dict[str, Any], granularidade: str) -> list[dict[str, Any]]:
        where, params = _filtros(f)
        with self._db.transacao(org) as conn:
            return conn.execute(
                f"select date_trunc(%s, d.dia::timestamp)::date as periodo, {_SOMAS}"
                f" from public.metricas_diarias d {_PRECO} where {where}"
                " group by 1 order by 1",
                [granularidade, *params],
            ).fetchall()

    def serie_horaria(self, org: UUID, f: dict[str, Any]) -> list[dict[str, Any]]:
        """Por hora, direto da telemetria (área estimada ponto a ponto; janela curta)."""
        where, params = ["true"], []
        if f.get("maquina_id"):
            where.append("t.maquina_id = %s")
            params.append(f["maquina_id"])
        if f.get("talhao_id"):
            where.append("t.talhao_id = %s")
            params.append(f["talhao_id"])
        if f.get("operacao"):
            where.append("s.operacao = %s")
            params.append(f["operacao"])
        with self._db.transacao(org) as conn:
            return conn.execute(
                f"""
                select date_trunc('hour', t.ts at time zone o.fuso) as periodo,
                    count(*) filter (where t.engine_on) / 3600.0 as motor_h,
                    count(*) filter (where t.engine_on and t.speed_kmh >= 1) / 3600.0 as trabalho_h,
                    count(*) filter (where t.engine_on and t.speed_kmh < 1) / 3600.0 as ocioso_h,
                    coalesce(sum(t.fuel_rate_lph) filter (where t.engine_on), 0) / 3600 as litros,
                    coalesce(sum(t.fuel_rate_lph)
                        filter (where t.engine_on and t.speed_kmh >= 1), 0)
                        / 3600 as litros_trabalho,
                    coalesce(sum(t.fuel_rate_lph)
                        filter (where t.engine_on and t.speed_kmh < 1), 0) / 3600 as litros_ocioso,
                    coalesce(sum(t.speed_kmh / 3.6 * i.largura_m)
                        filter (where t.engine_on and t.speed_kmh >= 1), 0) / 10000 as area_ha,
                    coalesce(sum(t.speed_kmh) filter (where t.engine_on and t.speed_kmh >= 1), 0)
                        / 3600 as distancia_km,
                    null::float as custo_rs, 0 as dias_sem_preco
                from public.telemetria t
                join public.sessoes_trabalho s on s.id = t.sessao_id
                join public.organizacoes o on o.id = t.organizacao_id
                left join public.implementos i on i.id = s.implemento_id
                where t.ts >= (%s::date)::timestamp at time zone o.fuso
                  and t.ts < (%s::date + 1)::timestamp at time zone o.fuso
                  and {" and ".join(where)}
                group by 1 order by 1
                """,
                [f["inicio"], f["fim"], *params],
            ).fetchall()

    def ranking(self, org: UUID, f: dict[str, Any], por: str) -> list[dict[str, Any]]:
        where, params = _filtros(f)
        chave, nome, junta = {
            "maquina": (
                "d.maquina_id",
                "coalesce(m.apelido, m.serial)",
                " join public.maquinas m on m.id = d.maquina_id",
            ),
            "talhao": (
                "d.talhao_id",
                "coalesce(t.nome, '(sem talhão)')",
                " left join public.talhoes t on t.id = d.talhao_id",
            ),
            "operacao": ("d.operacao", "coalesce(d.operacao, '(não informada)')", ""),
        }[por]
        with self._db.transacao(org) as conn:
            return conn.execute(
                f"select {chave}::text as id, {nome} as nome, sum(d.sessoes) as sessoes, {_SOMAS}"
                f" from public.metricas_diarias d {_PRECO}{junta} where {where}"
                " group by 1, 2 order by sum(d.litros) desc",
                params,
            ).fetchall()

    def por_safra(self, org: UUID, f: dict[str, Any], inicio_mes: int) -> list[dict[str, Any]]:
        where, params = _filtros(f)
        with self._db.transacao(org) as conn:
            return conn.execute(
                "select case when extract(month from d.dia) >= %s"
                "   then extract(year from d.dia)::int else extract(year from d.dia)::int - 1 end"
                f" as ano, {_SOMAS} from public.metricas_diarias d {_PRECO} where {where}"
                " group by 1 order by 1",
                [inicio_mes, *params],
            ).fetchall()

    # ------------------------------------------------------------- mapas
    def pontos_mapa(self, org: UUID, f: dict[str, Any], celula_m: float) -> pd.DataFrame:
        """Pré-agrega no banco em células de ``celula_m`` (bem menores que o hexágono):
        254 mil pontos viram poucos milhares de linhas, com litros e área já somados."""
        where, params = ["t.geom is not null", "t.engine_on", "t.speed_kmh >= 1"], []
        for coluna, alias in (("maquina_id", "t"), ("talhao_id", "t"), ("operacao", "s")):
            if f.get(coluna) is not None:
                where.append(f"{alias}.{coluna} = %s")
                params.append(f[coluna])
        grau = celula_m / 111_320.0
        with self._db.transacao(org) as conn:
            linhas = conn.execute(
                "select avg(t.lat) as lat, avg(t.lon) as lon,"
                " sum(t.fuel_rate_lph) / 3600 as litros,"
                " sum(t.speed_kmh / 3.6 * i.largura_m) / 10000 as area_ha"
                " from public.telemetria t"
                " join public.sessoes_trabalho s on s.id = t.sessao_id"
                " join public.organizacoes o on o.id = t.organizacao_id"
                " join public.implementos i on i.id = s.implemento_id and i.largura_m > 0"
                " where t.ts >= (%s::date)::timestamp at time zone o.fuso"
                "   and t.ts < (%s::date + 1)::timestamp at time zone o.fuso"
                f"   and {' and '.join(where)}"
                " group by floor(t.lat / %s), floor(t.lon * cos(radians(t.lat)) / %s)",
                [f["inicio"], f["fim"], *params, grau, grau],
            ).fetchall()
        return pd.DataFrame(linhas, columns=["lat", "lon", "litros", "area_ha"], dtype=float)

    def pontos_sessao(self, org: UUID, sessao_id: UUID) -> pd.DataFrame | None:
        with self._db.transacao(org) as conn:
            existe = conn.execute(
                "select 1 from public.sessoes_trabalho where id = %s", (sessao_id,)
            ).fetchone()
            if existe is None:
                return None
            linhas = conn.execute(
                "select ts, lat, lon, speed_kmh, engine_on from public.telemetria"
                " where sessao_id = %s and geom is not null order by ts",
                (sessao_id,),
            ).fetchall()
        return pd.DataFrame(linhas, columns=["ts", "lat", "lon", "speed_kmh", "engine_on"])

    # ------------------------------------------------------------- legado
    def pontos_maquina(
        self,
        org: UUID,
        serial: str,
        talhao_id: UUID | None,
        inicio: datetime | None,
        fim: datetime | None,
        passo_s: int,
        limite: int,
        apos: datetime | None,
    ) -> list[dict[str, Any]] | None:
        where: list[str] = ["m.serial = %s", "t.geom is not null"]
        params: list[Any] = [serial]
        for cond, valor in (
            ("t.talhao_id = %s", talhao_id),
            ("t.ts >= %s", inicio),
            ("t.ts < %s", fim),
            ("t.ts > %s", apos),
        ):
            if valor is not None:
                where.append(cond)
                params.append(valor)
        if passo_s > 1:
            where.append("mod(extract(epoch from t.ts)::bigint, %s) = 0")
            params.append(passo_s)
        with self._db.transacao(org) as conn:
            if (
                conn.execute(
                    "select 1 from public.maquinas where serial = %s", (serial,)
                ).fetchone()
                is None
            ):
                return None
            return conn.execute(
                "select t.ts, t.lat, t.lon, t.speed_kmh, t.fuel_rate_lph, t.engine_rpm, t.engine_on"
                " from public.telemetria t join public.maquinas m on m.id = t.maquina_id"
                f" where {' and '.join(where)} order by t.ts limit %s",
                (*params, limite),
            ).fetchall()

    def maquina_por_serial(self, org: UUID, serial: str) -> UUID | None:
        with self._db.transacao(org) as conn:
            linha = conn.execute(
                "select id from public.maquinas where serial = %s", (serial,)
            ).fetchone()
        return None if linha is None else linha["id"]

    # ------------------------------------------------------------- preços
    def precos(self, org: UUID) -> list[dict[str, Any]]:
        with self._db.transacao(org) as conn:
            return conn.execute(
                "select id, tipo, preco_rs_l::float as preco_rs_l, valido_de, valido_ate, fonte,"
                " criado_em from public.preco_combustivel order by tipo, valido_de desc"
            ).fetchall()

    def novo_preco(
        self, org: UUID, tipo: str, preco: float, valido_de: date, fonte: str
    ) -> dict[str, Any]:
        """Fecha o preço vigente (valido_ate = valido_de do novo) e insere o novo."""
        try:
            return self._novo_preco(org, tipo, preco, valido_de, fonte)
        except psycopg.errors.ExclusionViolation as exc:
            raise Conflito(
                "Já existe preço cadastrado a partir dessa data; corrija o existente.",
                codigo="PRECO_SOBREPOSTO",
            ) from exc

    def _novo_preco(
        self, org: UUID, tipo: str, preco: float, valido_de: date, fonte: str
    ) -> dict[str, Any]:
        with self._db.transacao(org) as conn:
            conn.execute(
                "update public.preco_combustivel set valido_ate = %s"
                " where tipo = %s and valido_de < %s and (valido_ate is null or valido_ate > %s)",
                (valido_de, tipo, valido_de, valido_de),
            )
            linha = conn.execute(
                "insert into public.preco_combustivel (organizacao_id, tipo, preco_rs_l, valido_de,"
                " fonte) values (%s, %s, %s, %s, %s) returning id, tipo, preco_rs_l::float as"
                " preco_rs_l, valido_de, valido_ate, fonte, criado_em",
                (org, tipo, preco, valido_de, fonte),
            ).fetchone()
        assert linha is not None
        return linha

    def corrigir_preco(self, org: UUID, preco_id: UUID, preco: float) -> dict[str, Any] | None:
        with self._db.transacao(org) as conn:
            return conn.execute(
                "update public.preco_combustivel set preco_rs_l = %s, fonte = 'manual'"
                " where id = %s returning id, tipo, preco_rs_l::float as preco_rs_l, valido_de,"
                " valido_ate, fonte, criado_em",
                (preco, preco_id),
            ).fetchone()

    def datas_de_atividade(self, org: UUID) -> tuple[date | None, date | None]:
        with self._db.transacao(org) as conn:
            linha = conn.execute(
                "select min(dia) as a, max(dia) as b from public.metricas_diarias"
            ).fetchone()
        return (linha["a"], linha["b"]) if linha else (None, None)
