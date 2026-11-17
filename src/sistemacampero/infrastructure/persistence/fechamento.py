"""Fechamento da safra por talhão: o que a colheitadeira colheu e o que as máquinas gastaram ali.

A janela de custo de um talhão vai do dia seguinte à colheita anterior nele (outra safra) até o
fim desta colheita: entra o plantio, as aplicações e a própria colheita, de qualquer máquina.
Sem colheita anterior conhecida, a janela começa 240 dias antes (um ciclo de verão com folga).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sistemacampero.infrastructure.persistence.db import Database

JANELA_MAX_DIAS = 240
INTERVALO_ENTRE_SAFRAS_DIAS = 20  # colheitas do mesmo talhão mais perto que isso são a mesma safra

_PRECO_DIA = """
    left join lateral (select pc.preco_rs_l from public.preco_combustivel pc
        where pc.tipo = 'S10' and pc.valido_de <= d.dia
          and (pc.valido_ate is null or pc.valido_ate > d.dia)
        order by pc.valido_de desc limit 1) p on true
"""


class PostgresFechamento:
    def __init__(self, db: Database) -> None:
        self._db = db

    def safras(self, org: UUID) -> list[dict[str, Any]]:
        with self._db.transacao(org) as conn:
            return conn.execute(
                # Uma linha por safra e cultura: sc/ha de aveia não se compara com o de trigo.
                "select c.safra, c.cultura, sum(c.area_colhida_ha) as area_colhida_ha,"
                " sum(c.massa_seca_kg) / 60 as sacas, min(s.inicio) as inicio, max(s.fim) as fim"
                " from public.colheitas c join public.sessoes_trabalho s on s.id = c.sessao_id"
                " group by c.safra, c.cultura"
                # colheita sem área (teste do monitor, sensor sem leitura) não é safra
                " having sum(c.area_colhida_ha) >= 1"
                " order by max(s.fim) desc, sum(c.massa_seca_kg) desc",
            ).fetchall()

    def talhoes(
        self, org: UUID, safra: str, cultura: str | None, versao: str
    ) -> list[dict[str, Any]]:
        with self._db.transacao(org) as conn:
            return conn.execute(
                f"""
                with colhido as (
                    select s.talhao_id, c.cultura,
                        array_agg(distinct c.variedade) filter (where c.variedade is not null)
                            as variedades,
                        sum(c.massa_seca_kg) as massa_seca_kg,
                        sum(c.massa_umida_kg) as massa_umida_kg,
                        sum(c.area_colhida_ha) as area_colhida_ha,
                        sum(c.umidade_pct * c.massa_umida_kg)
                            / nullif(sum(c.massa_umida_kg) filter (where c.umidade_pct is not null), 0)
                            as umidade_pct,
                        min(s.inicio) as colheita_inicio, max(s.fim) as colheita_fim,
                        count(*) as operacoes
                    from public.colheitas c
                    join public.sessoes_trabalho s on s.id = c.sessao_id
                    where c.safra = %(safra)s
                      and (%(cultura)s::text is null or c.cultura = %(cultura)s)
                    group by 1, 2
                ), janela as (
                    select k.*,
                        greatest(
                            (k.colheita_fim - make_interval(days => %(max_dias)s))::date,
                            coalesce((
                                select max(s2.fim)::date + 1
                                from public.colheitas c2
                                join public.sessoes_trabalho s2 on s2.id = c2.sessao_id
                                where s2.talhao_id is not distinct from k.talhao_id
                                  and s2.fim < k.colheita_inicio
                                      - make_interval(days => %(intervalo)s)
                            ), '-infinity'::date)
                        ) as janela_inicio
                    from colhido k
                ), gasto as (
                    select j.talhao_id, j.cultura, d.operacao,
                        sum(d.motor_h) as motor_h, sum(d.litros) as litros,
                        sum(d.area_ha) as area_ha, sum(d.litros * p.preco_rs_l)::float as custo_rs,
                        count(distinct d.maquina_id) as maquinas
                    from janela j
                    join public.metricas_diarias d
                      on d.talhao_id is not distinct from j.talhao_id
                     and d.versao_regras = %(versao)s
                     and d.dia between j.janela_inicio and j.colheita_fim::date
                    {_PRECO_DIA}
                    group by 1, 2, 3
                )
                select j.*, t.nome as talhao_nome, t.area_ha as area_talhao_ha,
                    coalesce((
                        select json_agg(json_build_object(
                            'operacao', coalesce(g.operacao, 'outras'), 'motor_h', g.motor_h,
                            'litros', g.litros, 'custo_rs', g.custo_rs, 'maquinas', g.maquinas
                        ) order by g.litros desc)
                        from gasto g
                        where g.talhao_id is not distinct from j.talhao_id
                          and g.cultura is not distinct from j.cultura
                    ), '[]'::json) as operacoes_maquina
                from janela j
                left join public.talhoes t on t.id = j.talhao_id
                order by j.massa_seca_kg / nullif(j.area_colhida_ha, 0) desc nulls last
                """,
                {
                    "safra": safra,
                    "cultura": cultura,
                    "versao": versao,
                    "max_dias": JANELA_MAX_DIAS,
                    "intervalo": INTERVALO_ENTRE_SAFRAS_DIAS,
                },
            ).fetchall()
