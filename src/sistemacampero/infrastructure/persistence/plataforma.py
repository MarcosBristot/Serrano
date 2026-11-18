"""Assinatura e planos, integrações (de onde vêm os dados) e saúde dos dados da organização."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sistemacampero.domain.errors import Invalido, NaoEncontrado
from sistemacampero.infrastructure.persistence.db import Database

# Sessão abaixo disto é fragmento (liga/desliga do monitor): não entra em razões nem na lista
# padrão. Mesmo corte do serviço de qualidade (SESSAO_CURTA_S).
FRAGMENTO_S = 120

_SITUACAO = (
    "select case"
    " when a2.status = 'trial' and a2.fim < now() then 'trial_vencido'"
    " when a2.status = 'ativa' and a2.fim < now() - interval '7 days' then 'vencida'"
    " else a2.status end as situacao"
    " from public.assinaturas a2"
)


class PostgresPlataforma:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ------------------------------------------------------------------ assinatura
    def planos(self) -> list[dict[str, Any]]:
        with self._db.transacao(None) as conn:
            return conn.execute(
                "select codigo, nome, descricao, max_maquinas, preco_mensal_centavos,"
                " preco_anual_centavos, destaque, sob_consulta, recursos"
                " from public.planos where publico order by ordem"
            ).fetchall()

    def situacao(self, org: UUID) -> str | None:
        """trial | ativa | trial_vencido | vencida | suspensa | cancelada (None: sem assinatura).

        Assinatura paga tem 7 dias de tolerância depois do vencimento (boleto/PIX atrasado).
        """
        with self._db.transacao(org) as conn:
            linha = conn.execute(_SITUACAO + " where a2.organizacao_id = %s", (org,)).fetchone()
        return None if linha is None else str(linha["situacao"])

    def assinatura(self, org: UUID) -> dict[str, Any]:
        with self._db.transacao(org) as conn:
            a = conn.execute(
                "select a.plano_codigo, p.nome as plano_nome, a.status, a.inicio, a.fim,"
                " (" + _SITUACAO + " where a2.organizacao_id = a.organizacao_id)"
                "   as situacao,"
                " coalesce(a.max_maquinas_override, p.max_maquinas) as max_maquinas,"
                " p.preco_mensal_centavos, p.sob_consulta"
                " from public.assinaturas a join public.planos p on p.codigo = a.plano_codigo"
                " where a.organizacao_id = %s",
                (org,),
            ).fetchone()
            if a is None:
                raise NaoEncontrado("Organização sem assinatura.", codigo="SEM_ASSINATURA")
            uso = conn.execute(
                "select (select count(*) from public.maquinas where organizacao_id = %(o)s)"
                "   as maquinas,"
                " (select count(*) from public.arquivos_brutos where organizacao_id = %(o)s"
                "   and arquivo_pai_id is null) as envios,"
                " (select coalesce(sum(tamanho_bytes), 0) from public.arquivos_brutos"
                "   where organizacao_id = %(o)s and arquivo_pai_id is null) as armazenamento_bytes,"
                " (select coalesce(sum(area_ha), 0) from public.jornadas"
                "   where organizacao_id = %(o)s) as hectares,"
                " (select count(*) from public.membros where organizacao_id = %(o)s) as usuarios",
                {"o": org},
            ).fetchone()
            pedido = conn.execute(
                "select plano_codigo, ciclo, criado_em from public.pedidos_assinatura"
                " where organizacao_id = %s and status = 'aberto'"
                " order by criado_em desc limit 1",
                (org,),
            ).fetchone()
        return {**a, "uso": uso, "pedido_aberto": pedido}

    def pedir(
        self,
        org: UUID,
        usuario: UUID | None,
        plano: str,
        ciclo: str,
        mensagem: str | None,
        telefone: str | None,
    ) -> dict[str, Any]:
        with self._db.transacao(org) as conn:
            p = conn.execute(
                "select codigo from public.planos where codigo = %s and publico", (plano,)
            ).fetchone()
            if p is None:
                raise Invalido("Plano inexistente.", codigo="PLANO_INVALIDO")
            linha = conn.execute(
                "insert into public.pedidos_assinatura"
                " (organizacao_id, plano_codigo, ciclo, mensagem, telefone, solicitado_por)"
                " values (%s, %s, %s, %s, %s, %s) returning id, plano_codigo, ciclo, criado_em",
                (org, plano, ciclo, mensagem, telefone, usuario),
            ).fetchone()
            assert linha is not None
            return linha

    # ------------------------------------------------------------------ integrações
    def fontes(self, org: UUID) -> list[dict[str, Any]]:
        """Por formato lido: arquivos, sessões, máquinas e o último envio."""
        with self._db.transacao(org) as conn:
            return conn.execute(
                """
                select s.adapter as fonte, count(*) as sessoes,
                    count(distinct s.maquina_id) as maquinas, max(s.fim) as ultimo_dado,
                    max(s.criado_em) as ultimo_envio
                from public.sessoes_trabalho s group by 1
                union all
                select 'contornos', count(*), 0, null, max(criado_em)
                from public.talhoes where origem_contorno in ('monitor', 'upload')
                having count(*) > 0
                """
            ).fetchall()

    # ------------------------------------------------------------------ saúde dos dados
    def qualidade(self, org: UUID, inicio: datetime | None, fim: datetime | None) -> dict[str, Any]:
        p = {"o": org, "i": inicio, "f": fim, "frag": FRAGMENTO_S}
        janela = (
            " and (%(i)s::timestamptz is null or s.inicio >= %(i)s)"
            " and (%(f)s::timestamptz is null or s.inicio < %(f)s)"
        )
        with self._db.transacao(org) as conn:
            arquivos = conn.execute(
                "select count(*) filter (where status = 'processado' and tipo not in ('zip'))"
                "   as processados,"
                " count(*) filter (where status = 'vazio') as vazios,"
                " count(*) filter (where status in ('erro', 'bloqueado')) as com_erro,"
                " count(*) filter (where tipo = 'zip') as pacotes"
                " from public.arquivos_brutos a where a.organizacao_id = %(o)s",
                p,
            ).fetchone()
            sessoes = conn.execute(
                "select count(*) as total,"
                " count(*) filter (where s.fim - s.inicio < make_interval(secs => %(frag)s))"
                "   as fragmentos,"
                " count(*) filter (where s.fim = s.inicio) as sem_duracao,"
                " coalesce(sum(ms.motor_h) filter"
                "   (where s.fim - s.inicio < make_interval(secs => %(frag)s)), 0) as fragmentos_motor_h,"
                " coalesce(sum(ms.motor_h), 0) as motor_h,"
                " coalesce(sum(ms.motor_h) filter (where s.qualidade_score >= 80), 0)"
                "   as motor_h_confiavel,"
                " round(avg(s.qualidade_score) filter"
                "   (where s.fim - s.inicio >= make_interval(secs => %(frag)s))) as score_medio"
                " from public.sessoes_trabalho s"
                " left join public.metricas_sessao ms on ms.sessao_id = s.id and ms.vigente"
                " where s.organizacao_id = %(o)s" + janela,
                p,
            ).fetchone()
            # Trechos gravados em dois arquivos da mesma máquina: a telemetria guarda um ponto por
            # segundo por máquina, então o trecho repetido já é somado uma vez só.
            sobreposicao = conn.execute(
                "select count(*) as pares, coalesce(sum(extract(epoch from"
                "   least(a.fim, b.fim) - greatest(a.inicio, b.inicio))), 0) / 60.0 as minutos"
                " from public.sessoes_trabalho a"
                " join public.sessoes_trabalho b on b.maquina_id = a.maquina_id and a.id < b.id"
                "   and a.inicio < b.fim and b.inicio < a.fim"
                " where a.organizacao_id = %(o)s"
                " and (%(i)s::timestamptz is null or a.inicio >= %(i)s)"
                " and (%(f)s::timestamptz is null or a.inicio < %(f)s)",
                p,
            ).fetchone()
            problemas = conn.execute(
                "select pr->>'codigo' as codigo, pr->>'severidade' as severidade, count(*) as sessoes"
                " from public.sessoes_trabalho s,"
                "   jsonb_array_elements(coalesce(s.qualidade->'problemas', '[]'::jsonb)) pr"
                " where s.organizacao_id = %(o)s and pr->>'codigo' <> 'SESSAO_CURTA'"
                + janela
                + " group by 1, 2 order by 3 desc",
                p,
            ).fetchall()
            motivos_vazios = conn.execute(
                "select split_part(motivo, ':', 1) as motivo, count(*) as arquivos"
                " from public.arquivos_brutos where organizacao_id = %(o)s and status = 'vazio'"
                " group by 1 order by 2 desc",
                p,
            ).fetchall()
        assert arquivos is not None and sessoes is not None and sobreposicao is not None
        return {
            "arquivos": arquivos,
            "sessoes": sessoes,
            "sobreposicao": sobreposicao,
            "problemas": problemas,
            "motivos_vazios": motivos_vazios,
        }
