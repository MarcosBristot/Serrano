"""Grava o resultado do processamento de um arquivo (etapas 3 a 5) numa transação.

Idempotente: reprocessar o mesmo arquivo atualiza a sessão (upsert por arquivo), troca
a telemetria da sessão, faz upsert das métricas por versão de regras e dos alertas por
impressão digital. Um alerta que deixa de disparar vira ``invalidado`` (nunca é apagado)
e um alerta reconhecido continua reconhecido.

Telemetria: ``COPY`` direto não é permitido em tabela com RLS, então o ``COPY`` vai para
uma tabela temporária e um ``INSERT ... SELECT`` (que passa pela RLS) copia para o destino.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import numpy as np
import pandas as pd
import shapely
from psycopg.types.json import Jsonb

from sistemacampero.application.processamento import ResultadoSessao
from sistemacampero.domain.ingestao import StatusArquivo
from sistemacampero.infrastructure.persistence.db import Conexao, Database
from sistemacampero.infrastructure.persistence.kpis import recalcular_diarias

COLUNAS_TELEMETRIA = (
    "ts",
    "lat",
    "lon",
    "gps_valid",
    "speed_kmh",
    "speed_alt_kmh",
    "engine_rpm",
    "engine_load_pct",
    "fuel_rate_lph",
    "fuel_total_l",
    "fuel_level_l",
    "engine_hours",
    "engine_on",
)

PLANO_LIMITE = "PLANO_LIMITE_MAQUINAS"
MAQUINA_INATIVA = "MAQUINA_INATIVA"
ASSINATURA_INATIVA = "ASSINATURA_INATIVA"


def _meses(inicio: datetime, fim: datetime) -> list[datetime]:
    atual = datetime(inicio.year, inicio.month, 1, tzinfo=UTC)
    out = []
    while atual <= fim:
        out.append(atual)
        atual = datetime(atual.year + atual.month // 12, atual.month % 12 + 1, 1, tzinfo=UTC)
    return out


def _uuid(linha: dict[str, Any] | None) -> UUID | None:
    if linha is None:
        return None
    valor: UUID = linha["id"]
    return valor


def _sem_nan(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, float) and not np.isfinite(v):
        return None
    return v


class PostgresRepositorioResultados:
    def __init__(self, db: Database) -> None:
        self._db = db

    def gravar_sessao(
        self,
        organizacao_id: UUID,
        arquivo_id: UUID,
        r: ResultadoSessao,
        caminho_limpo: str | None,
        versao_regras: str,
        config_regras: dict[str, Any],
    ) -> tuple[StatusArquivo, str | None]:
        meta = r.sessao.metadados
        with self._db.transacao(organizacao_id) as conn:
            maquina_id, bloqueio = self._maquina(conn, organizacao_id, r)
            if maquina_id is None:
                conn.execute(
                    "update public.arquivos_brutos set status = 'bloqueado_plano', motivo = %s"
                    " where id = %s",
                    (bloqueio, arquivo_id),
                )
                return StatusArquivo.BLOQUEADO_PLANO, bloqueio

            fazenda_id = self._upsert_guid(
                conn,
                "fazendas",
                organizacao_id,
                meta.fazenda_guid,
                {"nome": meta.fazenda_nome, "cliente_nome": meta.cliente_nome},
            )
            talhao_monitor_id = self._upsert_guid(
                conn,
                "talhoes",
                organizacao_id,
                meta.talhao_guid,
                {"nome": meta.talhao_nome, "fazenda_id": fazenda_id},
            )
            implemento_id = self._implemento(conn, organizacao_id, r)
            # GPS (ou manual, que o SQL preserva) > talhão escolhido no monitor.
            talhao_id = r.talhao_id or talhao_monitor_id

            sessao_id = self._sessao(
                conn,
                organizacao_id,
                arquivo_id,
                maquina_id,
                implemento_id,
                talhao_monitor_id,
                caminho_limpo,
                r,
            )
            self._telemetria(conn, organizacao_id, maquina_id, sessao_id, r)
            self._cobertura(conn, organizacao_id, sessao_id, versao_regras, r)
            execucao_id = self._execucao(
                conn, organizacao_id, sessao_id, versao_regras, config_regras
            )
            self._metricas(conn, organizacao_id, sessao_id, versao_regras, execucao_id, r)
            recalcular_diarias(
                conn, organizacao_id, maquina_id, meta.inicio, meta.fim, versao_regras
            )
            self._alertas(
                conn,
                organizacao_id,
                sessao_id,
                maquina_id,
                talhao_id,
                r.regras.versao,  # alertas: versão da config de regras DA ORGANIZAÇÃO
                execucao_id,
                r,
            )
            conn.execute(
                "update public.arquivos_brutos set status = 'processado', motivo = null"
                " where id = %s",
                (arquivo_id,),
            )
        return StatusArquivo.PROCESSADO, None

    # ------------------------------------------------------------------ partes
    def _maquina(
        self, conn: Conexao, org: UUID, r: ResultadoSessao
    ) -> tuple[UUID | None, str | None]:
        """Cria a máquina no 1º arquivo de um serial novo, respeitando o plano.

        O ``FOR UPDATE`` na assinatura serializa uploads paralelos da mesma organização:
        dois arquivos de seriais novos não passam juntos do limite.
        """
        meta = r.sessao.metadados
        serial = meta.serial_maquina or meta.serial_monitor or "desconhecido"
        plano = conn.execute(
            "select a.status, coalesce(a.max_maquinas_override, p.max_maquinas) as limite"
            " from public.assinaturas a join public.planos p on p.codigo = a.plano_codigo"
            " where a.organizacao_id = %s for update of a",
            (org,),
        ).fetchone()
        if plano is None or plano["status"] not in ("trial", "ativa"):
            return None, ASSINATURA_INATIVA
        existente = conn.execute(
            "select id, ativa from public.maquinas where serial = %s", (serial,)
        ).fetchone()
        if existente is not None and not existente["ativa"]:
            return None, MAQUINA_INATIVA
        if existente is None:
            ativas = conn.execute(
                "select count(*) as n from public.maquinas where ativa"
            ).fetchone()
            assert ativas is not None
            if int(ativas["n"]) >= int(plano["limite"]):
                return None, PLANO_LIMITE
            existente = conn.execute(
                "insert into public.maquinas (organizacao_id, serial, fabricante, tecnologia)"
                " values (%s, %s, %s, %s) returning id, ativa",
                (org, serial, meta.fabricante, r.sessao.adapter),
            ).fetchone()
        maquina_id = _uuid(existente)
        conn.execute(
            "update public.maquinas set"
            " primeira_atividade = least(coalesce(primeira_atividade, %s), %s),"
            " ultima_atividade = greatest(coalesce(ultima_atividade, %s), %s)"
            " where id = %s",
            (meta.inicio, meta.inicio, meta.fim, meta.fim, maquina_id),
        )
        return maquina_id, None

    @staticmethod
    def _upsert_guid(
        conn: Conexao, tabela: str, org: UUID, guid: str | None, campos: dict[str, Any]
    ) -> UUID | None:
        if not guid or not campos.get("nome"):
            return None
        nomes = ["organizacao_id", "external_guid", *campos]
        valores = [org, guid, *campos.values()]
        atualiza = ", ".join(f"{c} = coalesce(excluded.{c}, {tabela}.{c})" for c in campos)
        linha = conn.execute(
            f"insert into public.{tabela} ({', '.join(nomes)})"  # noqa: S608 - nomes fixos
            f" values ({', '.join(['%s'] * len(valores))})"
            f" on conflict (organizacao_id, external_guid) do update set {atualiza}"
            " returning id",
            valores,
        ).fetchone()
        return _uuid(linha)

    def _implemento(self, conn: Conexao, org: UUID, r: ResultadoSessao) -> UUID | None:
        """O do cadastro do monitor (mesmo nome) se existir; senão cria um pelo .jdl."""
        meta = r.sessao.metadados
        if not meta.implemento_nome:
            return None
        existente = conn.execute(
            "select id from public.implementos where lower(nome) = lower(%s)"
            " order by (external_guid like 'jdl:%%'), criado_em limit 1",
            (meta.implemento_nome,),
        ).fetchone()
        if existente is not None:
            return _uuid(existente)
        return self._upsert_guid(
            conn,
            "implementos",
            org,
            f"jdl:{meta.implemento_nome}",
            {"nome": meta.implemento_nome, "largura_m": meta.implemento_largura_m},
        )

    @staticmethod
    def _sessao(
        conn: Conexao,
        org: UUID,
        arquivo_id: UUID,
        maquina_id: UUID,
        implemento_id: UUID | None,
        talhao_monitor_id: UUID | None,
        caminho_limpo: str | None,
        r: ResultadoSessao,
    ) -> UUID:
        meta, q = r.sessao.metadados, r.qualidade
        qualidade = {
            "score": q.score,
            "problemas": [
                {
                    "codigo": p.codigo,
                    "severidade": p.severidade,
                    "mensagem": p.mensagem,
                    "valor": p.valor,
                }
                for p in q.problemas
            ],
            "detalhes": q.detalhes,
            "sanitizacao": r.sanitizacao,
            "sanitizador_versao": r.sanitizador_versao,
            "diagnostico": {
                "canais": r.sessao.diagnostico.canais,
                "canais_ausentes": r.sessao.diagnostico.canais_ausentes,
                "fonte_posicao": r.sessao.diagnostico.fonte_posicao,
                "contadores": r.sessao.diagnostico.contadores,
                "avisos": r.sessao.diagnostico.avisos,
            },
        }
        loc = r.localizacao
        if loc is not None and loc.talhao_id is not None:
            talhao_id, origem, confianca = loc.talhao_id, "gps", loc.confianca
        elif talhao_monitor_id is not None:
            talhao_id, origem, confianca = talhao_monitor_id, "monitor", None
        else:
            talhao_id, origem, confianca = None, "nenhum", None
        # Talhão manual (correção do gestor) nunca é sobrescrito.
        linha = conn.execute(
            "insert into public.sessoes_trabalho (organizacao_id, arquivo_bruto_id, maquina_id,"
            " implemento_id, talhao_id, talhao_origem, talhao_monitor_id, operacao, inicio, fim,"
            " n_amostras, adapter, adapter_versao, firmware, caminho_limpo, qualidade_score,"
            " qualidade, talhao_confianca)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " on conflict (arquivo_bruto_id) do update set"
            "  maquina_id = excluded.maquina_id, implemento_id = excluded.implemento_id,"
            "  talhao_monitor_id = excluded.talhao_monitor_id,"
            "  talhao_id = case when sessoes_trabalho.talhao_origem = 'manual'"
            "    then sessoes_trabalho.talhao_id else excluded.talhao_id end,"
            "  talhao_origem = case when sessoes_trabalho.talhao_origem = 'manual'"
            "    then 'manual' else excluded.talhao_origem end,"
            "  talhao_confianca = case when sessoes_trabalho.talhao_origem = 'manual'"
            "    then sessoes_trabalho.talhao_confianca else excluded.talhao_confianca end,"
            "  operacao = excluded.operacao, inicio = excluded.inicio, fim = excluded.fim,"
            "  n_amostras = excluded.n_amostras, adapter = excluded.adapter,"
            "  adapter_versao = excluded.adapter_versao, firmware = excluded.firmware,"
            "  caminho_limpo = excluded.caminho_limpo,"
            "  qualidade_score = excluded.qualidade_score, qualidade = excluded.qualidade"
            " returning id",
            (
                org,
                arquivo_id,
                maquina_id,
                implemento_id,
                talhao_id,
                origem,
                talhao_monitor_id,
                meta.operacao,
                meta.inicio,
                meta.fim,
                len(r.limpo),
                r.sessao.adapter,
                r.sessao.adapter_versao,
                meta.firmware,
                caminho_limpo,
                q.score,
                Jsonb(json.loads(json.dumps(qualidade, default=str))),
                confianca,
            ),
        ).fetchone()
        sessao_id = _uuid(linha)
        assert sessao_id is not None
        return sessao_id

    @staticmethod
    def _telemetria(
        conn: Conexao, org: UUID, maquina_id: UUID, sessao_id: UUID, r: ResultadoSessao
    ) -> None:
        limpo = r.limpo
        conn.execute("delete from public.telemetria where sessao_id = %s", (sessao_id,))
        if limpo.empty:
            return
        inicio, fim = limpo["ts"].iloc[0].to_pydatetime(), limpo["ts"].iloc[-1].to_pydatetime()
        for mes in _meses(inicio, fim):
            conn.execute("select interno.garantir_particao(%s)", (mes,))
        conn.execute(
            "create temp table if not exists _telemetria_carga ("
            " ts timestamptz, lat double precision, lon double precision, gps_valid boolean,"
            " speed_kmh real, speed_alt_kmh real, engine_rpm real, engine_load_pct real,"
            " fuel_rate_lph real, fuel_total_l double precision, fuel_level_l real,"
            " engine_hours double precision, engine_on boolean, talhao_id uuid)"
            " on commit drop"
        )
        df = limpo[list(COLUNAS_TELEMETRIA)].astype(object)
        por_ponto = r.localizacao.por_ponto if r.localizacao else [None] * len(df)
        df["talhao_id"] = pd.Series(por_ponto, index=df.index, dtype=object)
        df = df.where(pd.notna(df), None)
        with conn.cursor().copy(
            f"copy _telemetria_carga ({', '.join(COLUNAS_TELEMETRIA)}, talhao_id) from stdin"
        ) as copia:
            for linha in df.itertuples(index=False, name=None):
                copia.write_row([_sem_nan(v) for v in linha])
        conn.execute(
            f"insert into public.telemetria (organizacao_id, maquina_id, sessao_id,"
            f" {', '.join(COLUNAS_TELEMETRIA)}, talhao_id)"
            f" select %s, %s, %s, {', '.join(COLUNAS_TELEMETRIA)}, talhao_id"
            " from _telemetria_carga"
            " on conflict (maquina_id, ts) do nothing",  # sessões sobrepostas da mesma máquina
            (org, maquina_id, sessao_id),
        )
        conn.execute("truncate _telemetria_carga")

    @staticmethod
    def _cobertura(
        conn: Conexao, org: UUID, sessao_id: UUID, versao: str, r: ResultadoSessao
    ) -> None:
        conn.execute(
            "delete from public.coberturas_sessao where sessao_id = %s and versao_regras = %s",
            (sessao_id, versao),
        )
        if r.cobertura is None:
            return
        conn.execute(
            "insert into public.coberturas_sessao (sessao_id, versao_regras, organizacao_id,"
            " geometria) values (%s, %s, %s,"
            " extensions.st_multi(extensions.st_geomfromwkb(%s, 4326)))",
            (sessao_id, versao, org, shapely.to_wkb(r.cobertura.geometria)),
        )

    @staticmethod
    def _execucao(
        conn: Conexao, org: UUID, sessao_id: UUID, versao: str, config: dict[str, Any]
    ) -> UUID:
        blob = json.dumps(config, sort_keys=True)
        linha = conn.execute(
            "insert into public.execucoes_regras (organizacao_id, versao_regras, config,"
            " config_hash, escopo, concluida_em) values (%s, %s, %s, %s, %s, now()) returning id",
            (
                org,
                versao,
                Jsonb(config),
                hashlib.sha256(blob.encode()).hexdigest(),
                Jsonb({"sessao_id": str(sessao_id)}),
            ),
        ).fetchone()
        execucao_id = _uuid(linha)
        assert execucao_id is not None
        return execucao_id

    @staticmethod
    def _metricas(
        conn: Conexao,
        org: UUID,
        sessao_id: UUID,
        versao: str,
        execucao_id: UUID,
        r: ResultadoSessao,
    ) -> None:
        conn.execute(
            "update public.metricas_sessao set vigente = false"
            " where sessao_id = %s and versao_regras <> %s",
            (sessao_id, versao),
        )
        if r.metricas is None:
            return
        m = {k: _sem_nan(v) for k, v in r.metricas.como_dict().items()}
        colunas = list(m)
        conn.execute(
            f"insert into public.metricas_sessao (sessao_id, versao_regras, organizacao_id,"
            f" execucao_id, vigente, {', '.join(colunas)})"
            f" values (%s, %s, %s, %s, true, {', '.join(['%s'] * len(colunas))})"
            " on conflict (sessao_id, versao_regras) do update set vigente = true,"
            " execucao_id = excluded.execucao_id, "
            + ", ".join(f"{c} = excluded.{c}" for c in colunas),
            (sessao_id, versao, org, execucao_id, *m.values()),
        )

    @staticmethod
    def _alertas(
        conn: Conexao,
        org: UUID,
        sessao_id: UUID,
        maquina_id: UUID,
        talhao_id: UUID | None,
        versao: str,
        execucao_id: UUID,
        r: ResultadoSessao,
    ) -> None:
        digitais = []
        novos: list[tuple[UUID, str]] = []
        for a in r.alertas:
            digitais.append(a.impressao_digital)
            linha = conn.execute(
                "insert into public.alertas (organizacao_id, sessao_id, maquina_id, talhao_id,"
                " tipo, severidade, versao_regras, execucao_id, inicio, fim, valor, limiar,"
                " mensagem, detalhes, impressao_digital)"
                " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                " on conflict (organizacao_id, impressao_digital) do update set"
                "  severidade = excluded.severidade, versao_regras = excluded.versao_regras,"
                "  execucao_id = excluded.execucao_id, fim = excluded.fim,"
                "  valor = excluded.valor, limiar = excluded.limiar,"
                "  mensagem = excluded.mensagem, detalhes = excluded.detalhes,"
                "  status = case when alertas.status = 'invalidado' then 'aberto'"
                "    else alertas.status end"
                " returning id, severidade, (xmax = 0) as novo",
                (
                    org,
                    sessao_id,
                    maquina_id,
                    talhao_id,
                    a.tipo,
                    a.severidade,
                    versao,
                    execucao_id,
                    a.inicio,
                    a.fim,
                    _sem_nan(a.valor),
                    _sem_nan(a.limiar),
                    a.mensagem,
                    Jsonb(json.loads(json.dumps(a.detalhes, default=str))),
                    a.impressao_digital,
                ),
            ).fetchone()
            if linha is not None and linha["novo"]:
                novos.append((linha["id"], linha["severidade"]))
        # Outbox: a notificação nasce na mesma transação do alerta NOVO
        # (reprocessar não renotifica).
        for alerta_id, severidade in novos:
            conn.execute(
                "insert into interno.notificacoes (organizacao_id, alerta_id, destino_id)"
                " select %s, %s, d.id from public.destinos_notificacao d where d.ativo"
                " and array_position(array['info','atencao','alto'], %s)"
                "   >= array_position(array['info','atencao','alto'], d.severidade_minima)"
                " on conflict (alerta_id, destino_id) do nothing",
                (org, alerta_id, severidade),
            )
        conn.execute(
            "update public.alertas set status = 'invalidado'"
            " where sessao_id = %s and status in ('aberto', 'reconhecido')"
            "   and not (impressao_digital = any(%s))",
            (sessao_id, digitais),
        )
