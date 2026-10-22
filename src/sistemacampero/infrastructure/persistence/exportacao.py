"""Exportações (CSV em streaming e arquivos CSV/XLSX gerados pelo worker) e o relatório
de qualidade dos dados."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import xlsxwriter
from psycopg.types.json import Jsonb

from sistemacampero.domain.errors import Invalido, NaoEncontrado
from sistemacampero.infrastructure.persistence.db import Database

LOTE = 5000

# Colunas em português (cabeçalho = nome da coluna). Filtros: inicio/fim (dia local),
# maquina_id, talhao_id.
CONSULTAS: dict[str, tuple[str, str, str]] = {
    # tipo: (select, coluna de data local para o filtro, from/joins)
    "sessoes": (
        "s.id as sessao_id, m.serial as maquina_serial, m.apelido as maquina_apelido,"
        " (s.inicio at time zone o.fuso) as inicio_local, (s.fim at time zone o.fuso) as fim_local,"
        " s.operacao, t.nome as talhao, s.talhao_origem, i.nome as implemento,"
        " i.largura_m as implemento_largura_m, op.nome as operador, s.qualidade_score,"
        " ms.motor_h, ms.trabalho_h, ms.ocioso_h, ms.ociosidade_pct, ms.delta_horimetro_h,"
        " ms.litros_integral, ms.litros_contador, ms.lph_trabalho, ms.lph_ocioso,"
        " ms.distancia_trabalho_km, ms.velocidade_media, ms.area_cobertura_ha,"
        " ms.area_estimada_ha, ms.sobreposicao_pct, ms.area_metodo, ms.ha_h, ms.l_ha,"
        " ms.cobertura_gps",
        "(s.inicio at time zone o.fuso)::date",
        " from public.sessoes_trabalho s join public.organizacoes o on o.id = s.organizacao_id"
        " join public.maquinas m on m.id = s.maquina_id"
        " left join public.talhoes t on t.id = s.talhao_id"
        " left join public.implementos i on i.id = s.implemento_id"
        " left join public.operadores op on op.id = s.operador_id"
        " left join public.metricas_sessao ms on ms.sessao_id = s.id and ms.vigente",
    ),
    "diarias": (
        "d.dia, m.serial as maquina_serial, m.apelido as maquina_apelido, t.nome as talhao,"
        " d.operacao, d.sessoes, d.motor_h, d.trabalho_h, d.ocioso_h, d.litros,"
        " d.litros_trabalho, d.litros_ocioso, d.area_ha, d.distancia_km",
        "d.dia",
        " from public.metricas_diarias d join public.maquinas m on m.id = d.maquina_id"
        " left join public.talhoes t on t.id = d.talhao_id",
    ),
    "alertas": (
        "a.id as alerta_id, a.tipo, a.severidade, a.status, m.serial as maquina_serial,"
        " t.nome as talhao, (a.inicio at time zone o.fuso) as inicio_local,"
        " (a.fim at time zone o.fuso) as fim_local, a.valor, a.limiar, a.mensagem,"
        " (a.criado_em at time zone o.fuso) as criado_local",
        "(a.criado_em at time zone o.fuso)::date",
        " from public.alertas a join public.organizacoes o on o.id = a.organizacao_id"
        " left join public.maquinas m on m.id = a.maquina_id"
        " left join public.talhoes t on t.id = a.talhao_id",
    ),
    "telemetria": (
        "(x.ts at time zone o.fuso) as data_hora_local, m.serial as maquina_serial,"
        " tl.nome as talhao, x.lat, x.lon, x.gps_valid, x.speed_kmh, x.engine_rpm,"
        " x.engine_load_pct, x.fuel_rate_lph, x.fuel_total_l, x.engine_hours, x.engine_on",
        "(x.ts at time zone o.fuso)::date",
        " from public.telemetria x join public.organizacoes o on o.id = x.organizacao_id"
        " join public.maquinas m on m.id = x.maquina_id"
        " left join public.talhoes tl on tl.id = x.talhao_id",
    ),
}
_ALIAS = {"sessoes": "s", "diarias": "d", "alertas": "a", "telemetria": "x"}
MAX_DIAS_TELEMETRIA = 31


def _sql(tipo: str, f: dict[str, Any], versao: str) -> tuple[str, list[Any]]:
    if tipo not in CONSULTAS:
        raise Invalido("Tipo: sessoes, diarias, alertas ou telemetria.", codigo="TIPO_INVALIDO")
    colunas, data, origem = CONSULTAS[tipo]
    a = _ALIAS[tipo]
    where: list[str] = ["true"]
    params: list[Any] = []
    if tipo == "diarias":
        where.append("d.versao_regras = %s")
        params.append(versao)
    if tipo == "telemetria":
        if (
            not (f.get("inicio") and f.get("fim"))
            or (f["fim"] - f["inicio"]).days > MAX_DIAS_TELEMETRIA
        ):
            raise Invalido(
                f"Telemetria exige 'inicio' e 'fim' com até {MAX_DIAS_TELEMETRIA} dias.",
                codigo="PERIODO_INVALIDO",
            )
        # filtro por ts (usa o índice) com folga de um dia, refinado pela data local
        where.append("x.ts >= (%s::date - 1) and x.ts < (%s::date + 2)")
        params += [f["inicio"], f["fim"]]
    if f.get("inicio"):
        where.append(f"{data} >= %s")
        params.append(f["inicio"])
    if f.get("fim"):
        where.append(f"{data} <= %s")
        params.append(f["fim"])
    for coluna in ("maquina_id", "talhao_id"):
        if f.get(coluna):
            where.append(f"{a}.{coluna} = %s")
            params.append(f[coluna])
    ordem = {
        "sessoes": "s.inicio",
        "diarias": "d.dia, m.serial",
        "alertas": "a.criado_em",
        "telemetria": "x.maquina_id, x.ts",
    }[tipo]
    return f"select {colunas}{origem} where {' and '.join(where)} order by {ordem}", params


def _celula(v: Any, excel_br: bool) -> Any:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "sim" if v else "não"
    if isinstance(v, float | Decimal) and excel_br:
        return f"{float(v):.6g}".replace(".", ",")
    if isinstance(v, datetime):
        return v.isoformat(sep=" ")
    if isinstance(v, date):
        return v.isoformat()
    return v


class PostgresExportacoes:
    def __init__(self, db: Database) -> None:
        self._db = db

    def linhas(
        self, org: UUID, tipo: str, f: dict[str, Any], versao: str
    ) -> Iterator[tuple[list[str], list[tuple[Any, ...]]]]:
        """(cabeçalho, lote de linhas) via cursor no servidor: memória constante."""
        sql, params = _sql(tipo, f, versao)
        with self._db.transacao(org) as conn, conn.cursor(name=f"exp_{tipo}") as cur:
            cur.itersize = LOTE
            cur.execute(sql, params)
            cabecalho: list[str] | None = None
            while True:
                lote = cur.fetchmany(LOTE)
                if cabecalho is None:
                    cabecalho = [d.name for d in (cur.description or [])]
                if not lote:
                    if cabecalho is not None:
                        yield cabecalho, []
                    return
                yield cabecalho, [tuple(r.values()) for r in lote]

    def csv_stream(
        self, org: UUID, tipo: str, f: dict[str, Any], versao: str, excel_br: bool = True
    ) -> Iterator[bytes]:
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";" if excel_br else ",", lineterminator="\r\n")
        primeiro = True
        for cabecalho, lote in self.linhas(org, tipo, f, versao):
            if primeiro:
                if excel_br:
                    buf.write("﻿")  # BOM: Excel abre UTF-8 com acentos
                w.writerow(cabecalho)
                primeiro = False
            for linha in lote:
                w.writerow([_celula(v, excel_br) for v in linha])
            yield buf.getvalue().encode("utf-8")
            buf.seek(0)
            buf.truncate()

    def xlsx(self, org: UUID, tipo: str, f: dict[str, Any], versao: str, destino: Any) -> int:
        wb = xlsxwriter.Workbook(
            destino,
            {
                "constant_memory": True,
                "remove_timezone": True,
                "default_date_format": "dd/mm/yyyy hh:mm",
            },
        )
        ws = wb.add_worksheet(tipo)
        negrito = wb.add_format({"bold": True})
        n = 0
        linha_xls = 1
        for cabecalho, lote in self.linhas(org, tipo, f, versao):
            if n == 0 and linha_xls == 1:
                ws.write_row(0, 0, cabecalho, negrito)
                ws.freeze_panes(1, 0)
            for linha in lote:
                if linha_xls >= 1_048_575:
                    raise Invalido(
                        "Mais linhas que o Excel suporta; use CSV.", codigo="EXCEL_LIMITE"
                    )
                ws.write_row(
                    linha_xls,
                    0,
                    [
                        float(v)
                        if isinstance(v, Decimal)
                        else (str(v) if isinstance(v, UUID) else v)
                        for v in linha
                    ],
                )
                linha_xls += 1
                n += 1
        wb.close()
        return n

    # ------------------------------------------------------------- registro
    def criar(
        self, org: UUID, usuario: UUID | None, tipo: str, formato: str, filtros: dict[str, Any]
    ) -> UUID:
        with self._db.transacao(org) as conn:
            linha = conn.execute(
                "insert into public.exportacoes (organizacao_id, solicitado_por, formato, tipo,"
                " filtros) values (%s, %s, %s, %s, %s) returning id",
                (org, usuario, formato, tipo, Jsonb(filtros)),
            ).fetchone()
        assert linha is not None
        ident: UUID = linha["id"]
        return ident

    def obter(self, org: UUID, ident: UUID) -> dict[str, Any]:
        with self._db.transacao(org) as conn:
            linha = conn.execute(
                "select id, formato, tipo, filtros, status, caminho_storage, linhas, expira_em,"
                " erro, criado_em, atualizado_em from public.exportacoes where id = %s",
                (ident,),
            ).fetchone()
        if linha is None:
            raise NaoEncontrado("Exportação não encontrada.", codigo="EXPORTACAO_NAO_ENCONTRADA")
        return linha

    def listar(self, org: UUID) -> list[dict[str, Any]]:
        with self._db.transacao(org) as conn:
            return conn.execute(
                "select id, formato, tipo, filtros, status, caminho_storage, linhas, expira_em,"
                " erro, criado_em, atualizado_em from public.exportacoes"
                " order by criado_em desc limit 100"
            ).fetchall()

    def marcar(self, org: UUID, ident: UUID, **campos: Any) -> None:
        sets = ", ".join(f"{c} = %s" for c in campos)
        with self._db.transacao(org) as conn:
            conn.execute(
                f"update public.exportacoes set {sets} where id = %s", (*campos.values(), ident)
            )

    def vencidas(self, limite: int = 100) -> list[dict[str, Any]]:
        """Exportações vencidas de todas as orgs (via função do worker: sem org ativa)."""
        with self._db.transacao(None) as conn:
            return conn.execute(
                "select e.id, e.organizacao_id, e.caminho_storage from interno.exportacoes_vencidas(%s) e",
                (limite,),
            ).fetchall()

    # ------------------------------------------------------------- qualidade
    def relatorio_qualidade(
        self, org: UUID, inicio: date | None, fim: date | None
    ) -> dict[str, Any]:
        filtro_a, filtro_s, pa, ps = "true", "true", [], []
        if inicio:
            filtro_a += " and (a.criado_em at time zone o.fuso)::date >= %s"
            filtro_s += " and (s.inicio at time zone o.fuso)::date >= %s"
            pa.append(inicio)
            ps.append(inicio)
        if fim:
            filtro_a += " and (a.criado_em at time zone o.fuso)::date <= %s"
            filtro_s += " and (s.inicio at time zone o.fuso)::date <= %s"
            pa.append(fim)
            ps.append(fim)
        with self._db.transacao(org) as conn:
            arquivos = conn.execute(
                "select a.tipo, a.status, split_part(coalesce(a.motivo, ''), ':', 1) as motivo,"
                " count(*) as n from public.arquivos_brutos a"
                " join public.organizacoes o on o.id = a.organizacao_id"
                f" where {filtro_a} group by 1, 2, 3 order by 4 desc",
                pa,
            ).fetchall()
            sessoes = conn.execute(
                "select count(*) as total, avg(s.qualidade_score)::float as score_medio,"
                " count(*) filter (where ms.cobertura_gps > 0) as com_gps,"
                " count(*) filter (where ms.cobertura_gps = 0 or ms.cobertura_gps is null) as sem_gps,"
                " count(*) filter (where s.n_amostras < 120) as fragmentos,"
                " coalesce(sum(ms.motor_h) filter (where ms.cobertura_gps = 0), 0)::float"
                "   as motor_h_sem_gps"
                " from public.sessoes_trabalho s join public.organizacoes o on o.id = s.organizacao_id"
                " left join public.metricas_sessao ms on ms.sessao_id = s.id and ms.vigente"
                f" where {filtro_s}",
                ps,
            ).fetchone()
            problemas = conn.execute(
                "select p->>'codigo' as codigo, p->>'severidade' as severidade, count(*) as n"
                " from public.sessoes_trabalho s join public.organizacoes o on o.id = s.organizacao_id,"
                " jsonb_array_elements(s.qualidade->'problemas') p"
                f" where {filtro_s} group by 1, 2 order by 3 desc",
                ps,
            ).fetchall()
            maquinas = conn.execute(
                "select m.serial, m.apelido, count(*) as sessoes, avg(s.qualidade_score)::float"
                " as score_medio, avg(coalesce(ms.cobertura_gps, 0))::float as cobertura_gps_media"
                " from public.sessoes_trabalho s join public.organizacoes o on o.id = s.organizacao_id"
                " join public.maquinas m on m.id = s.maquina_id"
                " left join public.metricas_sessao ms on ms.sessao_id = s.id and ms.vigente"
                f" where {filtro_s} group by 1, 2 order by 3 desc",
                ps,
            ).fetchall()
        return {
            "arquivos": arquivos,
            "sessoes": sessoes,
            "problemas": problemas,
            "maquinas": maquinas,
        }
