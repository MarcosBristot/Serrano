"""Consultas de KPIs, métricas diárias, mapas e rotas legadas.

``metricas_diarias`` é recalculada a partir da telemetria (janelas com ``peso_s``) por dia LOCAL (fuso da
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
                coalesce(sum(t.peso_s) filter (where t.engine_on), 0) as motor_s,
                coalesce(sum(t.peso_s) filter (where t.engine_on and t.speed_kmh >= 1), 0) as trabalho_s,
                coalesce(sum(t.peso_s) filter (where t.engine_on and t.speed_kmh < 1), 0) as ocioso_s,
                coalesce(sum(t.fuel_rate_lph * t.peso_s) filter (where t.engine_on), 0) / 3600 as litros,
                coalesce(sum(t.fuel_rate_lph * t.peso_s) filter (where t.engine_on and t.speed_kmh >= 1), 0)
                    / 3600 as litros_trabalho,
                coalesce(sum(t.fuel_rate_lph * t.peso_s) filter (where t.engine_on and t.speed_kmh < 1), 0)
                    / 3600 as litros_ocioso,
                coalesce(sum(t.speed_kmh * t.peso_s) filter (where t.engine_on and t.speed_kmh >= 1), 0)
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


# Jornada "curta": menos de 3 min de motor e nenhuma área (liga/desliga, teste do monitor).
_CURTA = "j.motor_h < 0.05 and j.area_ha < 0.01"

# Arquivos da mesma máquina separados por menos que isto formam uma jornada.
INTERVALO_JORNADA = "15 minutes"


def recalcular_jornadas(
    conn: Conexao, org: UUID, maquina_id: UUID, inicio: datetime, fim: datetime, versao: str
) -> int:
    """Refaz as jornadas da máquina em volta de [inicio, fim].

    Apaga as jornadas que encostam na janela (com folga do intervalo), alarga a janela até as
    bordas delas e reagrupa os arquivos ali dentro ("ilhas" de sessões com folga menor que
    ``INTERVALO_JORNADA``, considerando arquivos sobrepostos). As somas vêm da telemetria,
    como as diárias, para não contar duas vezes arquivos gravados em paralelo.
    """
    borda = conn.execute(
        "with apagadas as (delete from public.jornadas where maquina_id = %(maq)s"
        "   and versao_regras = %(versao)s"
        "   and fim >= %(a)s::timestamptz - %(gap)s::interval"
        "   and inicio <= %(b)s::timestamptz + %(gap)s::interval returning inicio, fim)"
        " select least(min(inicio), %(a)s::timestamptz) as a,"
        "        greatest(max(fim), %(b)s::timestamptz) as b from apagadas",
        {"maq": maquina_id, "versao": versao, "a": inicio, "b": fim, "gap": INTERVALO_JORNADA},
    ).fetchone()
    assert borda is not None
    return conn.execute(
        """
        with s as (
            select s.id, s.inicio, s.fim, s.operacao from public.sessoes_trabalho s
            where s.maquina_id = %(maq)s
              and s.fim >= %(a)s::timestamptz - %(gap)s::interval
              and s.inicio <= %(b)s::timestamptz + %(gap)s::interval
        ), o as (
            select *, max(fim) over (order by inicio, id
                rows between unbounded preceding and 1 preceding) as fim_ant
            from s
        ), g as (
            select *, sum(case when fim_ant is null or inicio > fim_ant + %(gap)s::interval
                then 1 else 0 end) over (order by inicio, id) as grupo
            from o
        ), j as (
            select grupo, min(inicio) as inicio, max(fim) as fim, count(*) as arquivos,
                mode() within group (order by operacao) as operacao
            from g group by grupo
        ), pts as (
            select j.grupo, t.sessao_id,
                case ss.talhao_origem
                    when 'manual' then ss.talhao_id
                    when 'monitor' then coalesce(t.talhao_id, ss.talhao_id)
                    else t.talhao_id
                end as talhao_id,
                coalesce(sum(t.peso_s) filter (where t.engine_on), 0) as motor_s,
                coalesce(sum(t.peso_s) filter (where t.engine_on and t.speed_kmh >= 1), 0)
                    as trabalho_s,
                coalesce(sum(t.peso_s) filter (where t.engine_on and t.speed_kmh < 1), 0)
                    as ocioso_s,
                coalesce(sum(t.fuel_rate_lph * t.peso_s) filter (where t.engine_on), 0) / 3600
                    as litros,
                coalesce(sum(t.fuel_rate_lph * t.peso_s)
                    filter (where t.engine_on and t.speed_kmh >= 1), 0) / 3600 as litros_trabalho,
                coalesce(sum(t.fuel_rate_lph * t.peso_s)
                    filter (where t.engine_on and t.speed_kmh < 1), 0) / 3600 as litros_ocioso,
                coalesce(sum(t.speed_kmh * t.peso_s)
                    filter (where t.engine_on and t.speed_kmh >= 1), 0) / 3600 as distancia_km
            from j
            join public.telemetria t on t.maquina_id = %(maq)s
                and t.ts >= j.inicio and t.ts <= j.fim
                -- limites constantes: o planejador só poda as partições mensais com eles
                and t.ts >= %(a)s::timestamptz - %(gap)s::interval
                and t.ts <= %(b)s::timestamptz + %(gap)s::interval
            join public.sessoes_trabalho ss on ss.id = t.sessao_id
            group by 1, 2, 3
        ), partes as (
            select p.*,
                coalesce(ms.area_cobertura_ha, ms.area_estimada_ha, 0)
                  * case when ms.distancia_trabalho_km > 0
                         then least(p.distancia_km / ms.distancia_trabalho_km, 1) else 0 end
                  as area_ha
            from pts p
            left join public.metricas_sessao ms on ms.sessao_id = p.sessao_id and ms.vigente
        ), somas as (
            select grupo, sum(motor_s) / 3600.0 as motor_h, sum(trabalho_s) / 3600.0 as trabalho_h,
                sum(ocioso_s) / 3600.0 as ocioso_h, sum(litros) as litros,
                sum(litros_trabalho) as litros_trabalho, sum(litros_ocioso) as litros_ocioso,
                sum(area_ha) as area_ha, sum(distancia_km) as distancia_km,
                count(distinct talhao_id) as talhoes
            from partes group by grupo
        ), principal as (
            select distinct on (grupo) grupo, talhao_id from (
                select grupo, talhao_id, sum(trabalho_s) as trab, sum(motor_s) as mot
                from partes where talhao_id is not null group by 1, 2
            ) x order by grupo, trab desc, mot desc
        )
        insert into public.jornadas (organizacao_id, maquina_id, versao_regras, inicio, fim,
            talhao_id, talhoes, operacao, arquivos, motor_h, trabalho_h, ocioso_h, litros,
            litros_trabalho, litros_ocioso, area_ha, distancia_km)
        select %(org)s, %(maq)s, %(versao)s, j.inicio, j.fim, p.talhao_id,
            coalesce(x.talhoes, 0), j.operacao, j.arquivos,
            coalesce(x.motor_h, 0), coalesce(x.trabalho_h, 0), coalesce(x.ocioso_h, 0),
            coalesce(x.litros, 0), coalesce(x.litros_trabalho, 0), coalesce(x.litros_ocioso, 0),
            coalesce(x.area_ha, 0), coalesce(x.distancia_km, 0)
        from j left join somas x using (grupo) left join principal p using (grupo)
        """,
        {
            "maq": maquina_id,
            "versao": versao,
            "org": org,
            "a": borda["a"],
            "b": borda["b"],
            "gap": INTERVALO_JORNADA,
        },
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
                    coalesce(sum(t.peso_s) filter (where t.engine_on), 0) / 3600.0 as motor_h,
                    coalesce(sum(t.peso_s) filter (where t.engine_on and t.speed_kmh >= 1), 0) / 3600.0 as trabalho_h,
                    coalesce(sum(t.peso_s) filter (where t.engine_on and t.speed_kmh < 1), 0) / 3600.0 as ocioso_h,
                    coalesce(sum(t.fuel_rate_lph * t.peso_s) filter (where t.engine_on), 0) / 3600 as litros,
                    coalesce(sum(t.fuel_rate_lph * t.peso_s)
                        filter (where t.engine_on and t.speed_kmh >= 1), 0)
                        / 3600 as litros_trabalho,
                    coalesce(sum(t.fuel_rate_lph * t.peso_s)
                        filter (where t.engine_on and t.speed_kmh < 1), 0) / 3600 as litros_ocioso,
                    coalesce(sum(t.speed_kmh / 3.6 * i.largura_m * t.peso_s)
                        filter (where t.engine_on and t.speed_kmh >= 1), 0) / 10000 as area_ha,
                    coalesce(sum(t.speed_kmh * t.peso_s) filter (where t.engine_on and t.speed_kmh >= 1), 0)
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
                " sum(t.fuel_rate_lph * t.peso_s) / 3600 as litros,"
                " sum(t.speed_kmh / 3.6 * i.largura_m * t.peso_s) / 10000 as area_ha"
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

    # ------------------------------------------------------------- jornadas
    def jornadas(
        self,
        org: UUID,
        f: dict[str, Any],
        versao: str,
        limite: int,
        cursor: tuple[str, UUID] | None,
        curtas: bool,
    ) -> list[dict[str, Any]]:
        where: list[str] = ["j.versao_regras = %s"]
        params: list[Any] = [versao]
        if f.get("id"):
            where.append("j.id = %s")
            params.append(f["id"])
        if f.get("maquina_id"):
            where.append("j.maquina_id = %s")
            params.append(f["maquina_id"])
        if f.get("talhao_id"):
            where.append("j.talhao_id = %s")
            params.append(f["talhao_id"])
        if f.get("inicio"):
            where.append("(j.inicio at time zone o.fuso)::date >= %s")
            params.append(f["inicio"])
        if f.get("fim"):
            where.append("(j.inicio at time zone o.fuso)::date <= %s")
            params.append(f["fim"])
        if not curtas:
            where.append(f"not ({_CURTA})")
        if cursor:
            where.append("(j.inicio, j.id) < (%s::timestamptz, %s)")
            params.extend(cursor)
        with self._db.transacao(org) as conn:
            return conn.execute(
                "select j.id, j.maquina_id, m.serial, m.apelido, j.inicio, j.fim, j.talhao_id,"
                " t.nome as talhao_nome, j.talhoes, j.operacao, j.arquivos, j.motor_h,"
                " j.trabalho_h, j.ocioso_h, j.litros, j.litros_trabalho, j.litros_ocioso,"
                " j.area_ha, j.distancia_km, p.preco_rs_l::float as preco_rs_l,"
                f" ({_CURTA}) as curta"
                " from public.jornadas j"
                " join public.organizacoes o on o.id = j.organizacao_id"
                " join public.maquinas m on m.id = j.maquina_id"
                " left join public.talhoes t on t.id = j.talhao_id"
                " left join lateral (select pc.preco_rs_l from public.preco_combustivel pc"
                "   where pc.tipo = 'S10' and pc.valido_de <= (j.inicio at time zone o.fuso)::date"
                "     and (pc.valido_ate is null"
                "          or pc.valido_ate > (j.inicio at time zone o.fuso)::date)"
                "   order by pc.valido_de desc limit 1) p on true"
                f" where {' and '.join(where)} order by j.inicio desc, j.id desc limit %s",
                (*params, limite),
            ).fetchall()

    def visao_maquinas(self, org: UUID, f: dict[str, Any], versao: str) -> list[dict[str, Any]]:
        """Uma linha por máquina com uso real: tipo pelo que ela faz e somas das jornadas.

        Registros de segundos (liga/desliga) não entram; máquina sem nenhuma hora de motor
        na vida (ex.: o serial do monitor quando o arquivo não traz o da máquina) não aparece.
        """
        periodo = ["not (" + _CURTA + ")"]
        params: list[Any] = []
        if f.get("inicio"):
            periodo.append("(j.inicio at time zone o.fuso)::date >= %s")
            params.append(f["inicio"])
        if f.get("fim"):
            periodo.append("(j.inicio at time zone o.fuso)::date <= %s")
            params.append(f["fim"])
        filtro = " and ".join(periodo)
        with self._db.transacao(org) as conn:
            return conn.execute(
                f"""
                with vida as (
                    select j.maquina_id, sum(j.motor_h) as motor_h,
                        bool_or(j.operacao = 'colheita') as colhe,
                        bool_or(j.operacao like 'pulveriz%%') as pulveriza
                    from public.jornadas j where j.versao_regras = %s group by 1
                ), periodo as (
                    select j.maquina_id, count(*) as jornadas, sum(j.motor_h) as motor_h,
                        sum(j.trabalho_h) as trabalho_h, sum(j.ocioso_h) as ocioso_h,
                        sum(j.litros) as litros, sum(j.litros_ocioso) as litros_ocioso,
                        sum(j.area_ha) as area_ha, sum(j.distancia_km) as distancia_km,
                        sum(j.litros * p.preco_rs_l)::float as custo_rs,
                        sum(j.litros_ocioso * p.preco_rs_l)::float as custo_ocioso_rs,
                        count(distinct j.talhao_id) as talhoes
                    from public.jornadas j
                    join public.organizacoes o on o.id = j.organizacao_id
                    left join lateral (select pc.preco_rs_l from public.preco_combustivel pc
                        where pc.tipo = 'S10'
                          and pc.valido_de <= (j.inicio at time zone o.fuso)::date
                          and (pc.valido_ate is null
                               or pc.valido_ate > (j.inicio at time zone o.fuso)::date)
                        order by pc.valido_de desc limit 1) p on true
                    where j.versao_regras = %s and {filtro}
                    group by 1
                ), colheita as (
                    select s.maquina_id,
                        sum((s.qualidade -> 'diagnostico' -> 'contadores'
                             ->> 'massa_umida_kg')::float) as massa_kg
                    from public.sessoes_trabalho s
                    join public.organizacoes o on o.id = s.organizacao_id
                    where s.operacao = 'colheita'
                      and (%s::date is null or (s.inicio at time zone o.fuso)::date >= %s)
                      and (%s::date is null or (s.inicio at time zone o.fuso)::date <= %s)
                    group by 1
                )
                select m.id, m.serial, m.apelido, m.modelo, m.fabricante,
                    case when v.colhe then 'colheitadeira' when v.pulveriza then 'pulverizador'
                         else 'trator' end as tipo,
                    m.ultima_atividade, coalesce(p.jornadas, 0) as jornadas,
                    coalesce(p.motor_h, 0) as motor_h, coalesce(p.trabalho_h, 0) as trabalho_h,
                    coalesce(p.ocioso_h, 0) as ocioso_h, coalesce(p.litros, 0) as litros,
                    coalesce(p.litros_ocioso, 0) as litros_ocioso,
                    coalesce(p.area_ha, 0) as area_ha,
                    coalesce(p.distancia_km, 0) as distancia_km, p.custo_rs, p.custo_ocioso_rs,
                    coalesce(p.talhoes, 0) as talhoes, c.massa_kg, u.talhao_nome as ultimo_talhao
                from public.maquinas m
                join vida v on v.maquina_id = m.id and v.motor_h >= 0.1
                left join periodo p on p.maquina_id = m.id
                left join colheita c on c.maquina_id = m.id
                left join lateral (select t.nome as talhao_nome from public.jornadas j
                    left join public.talhoes t on t.id = j.talhao_id
                    where j.maquina_id = m.id and j.versao_regras = %s
                      and not ({_CURTA}) order by j.inicio desc limit 1) u on true
                where m.ativa and (%s::uuid is null or m.id = %s)
                order by coalesce(p.motor_h, 0) desc, m.ultima_atividade desc nulls last
                """,
                (
                    versao,
                    versao,
                    *params,
                    f.get("inicio"),
                    f.get("inicio"),
                    f.get("fim"),
                    f.get("fim"),
                    versao,
                    f.get("maquina_id"),
                    f.get("maquina_id"),
                ),
            ).fetchall()

    def arquivos_da_jornada(self, org: UUID, jornada_id: UUID) -> list[dict[str, Any]]:
        with self._db.transacao(org) as conn:
            return conn.execute(
                "select s.id, s.inicio, s.fim, s.n_amostras, s.qualidade_score, ms.motor_h,"
                " ms.litros_integral from public.jornadas j"
                " join public.sessoes_trabalho s on s.maquina_id = j.maquina_id"
                "  and s.inicio >= j.inicio and s.fim <= j.fim"
                " left join public.metricas_sessao ms on ms.sessao_id = s.id and ms.vigente"
                " where j.id = %s order by s.inicio",
                (jornada_id,),
            ).fetchall()

    def pontos_jornada(self, org: UUID, jornada_id: UUID) -> pd.DataFrame | None:
        with self._db.transacao(org) as conn:
            j = conn.execute(
                "select maquina_id, inicio, fim from public.jornadas where id = %s", (jornada_id,)
            ).fetchone()
            if j is None:
                return None
            linhas = conn.execute(
                "select ts, lat, lon, speed_kmh, engine_on, peso_s from public.telemetria"
                " where maquina_id = %s and ts >= %s and ts <= %s and geom is not null"
                " order by ts",
                (j["maquina_id"], j["inicio"], j["fim"]),
            ).fetchall()
        return pd.DataFrame(
            linhas, columns=["ts", "lat", "lon", "speed_kmh", "engine_on", "peso_s"]
        )

    def pontos_sessao(self, org: UUID, sessao_id: UUID) -> pd.DataFrame | None:
        with self._db.transacao(org) as conn:
            existe = conn.execute(
                "select 1 from public.sessoes_trabalho where id = %s", (sessao_id,)
            ).fetchone()
            if existe is None:
                return None
            linhas = conn.execute(
                "select ts, lat, lon, speed_kmh, engine_on, peso_s from public.telemetria"
                " where sessao_id = %s and geom is not null order by ts",
                (sessao_id,),
            ).fetchall()
        return pd.DataFrame(
            linhas, columns=["ts", "lat", "lon", "speed_kmh", "engine_on", "peso_s"]
        )

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
        if passo_s > 1:  # a telemetria já vem em janelas: um ponto por janela de ``passo_s``
            where.append(
                "t.ts = (select min(t2.ts) from public.telemetria t2 where t2.maquina_id ="
                " t.maquina_id and floor(extract(epoch from t2.ts) / %s)"
                " = floor(extract(epoch from t.ts) / %s))"
            )
            params.extend([passo_s, passo_s])
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
