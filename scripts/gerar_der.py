# ruff: noqa: E501 - SQL e textos do documento ficam em uma linha para ler melhor
"""Gera docs/entrega/banco-de-dados.md (DER em Mermaid) a partir de um banco já migrado.

Uso:
    uv run sistemacampero db migrar --criar-banco --bootstrap --database-url <dsn>
    uv run python scripts/gerar_der.py <dsn>

Lê tabelas, colunas, chaves primárias e estrangeiras dos schemas ``public`` e ``interno`` (sem as
partições mensais da telemetria) e escreve um diagrama por área do sistema.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import psycopg

SAIDA = Path(__file__).resolve().parents[1] / "docs" / "entrega" / "banco-de-dados.md"

GRUPOS: list[tuple[str, str, list[str]]] = [
    (
        "Organização, acesso, plano e LGPD",
        "Quem usa o sistema, com que papel, em qual plano, e os registros exigidos por lei.",
        [
            "organizacoes",
            "membros",
            "convites",
            "assinaturas",
            "planos",
            "pedidos_assinatura",
            "interno.chaves_api",
            "interno.auditoria",
            "interno.registros_acesso",
            "interno.aceites",
            "interno.solicitacoes_exclusao",
            "interno.contatos",
        ],
    ),
    (
        "Frota, talhões e dados de operação",
        "O que vem dos monitores: arquivos, sessões de trabalho, telemetria e métricas calculadas.",
        [
            "fazendas",
            "talhoes",
            "linhas_talhao",
            "maquinas",
            "implementos",
            "operadores",
            "lotes_upload",
            "arquivos_brutos",
            "sessoes_trabalho",
            "telemetria",
            "metricas_sessao",
            "metricas_diarias",
            "coberturas_sessao",
            "colheitas",
            "jornadas",
            "preco_combustivel",
            "planos_manutencao",
            "manutencoes_feitas",
        ],
    ),
    (
        "Alertas, notificações e processamento",
        "Regras, alertas e o que sai do sistema (e-mail, webhook, exportações), mais a fila de jobs.",
        [
            "alertas",
            "alertas_comentarios",
            "config_regras",
            "execucoes_regras",
            "destinos_notificacao",
            "interno.notificacoes",
            "interno.jobs",
            "exportacoes",
            "interno.resumos_semanais",
        ],
    ),
]

TIPOS = {
    "uuid": "uuid",
    "text": "text",
    "character varying": "text",
    "integer": "int",
    "bigint": "bigint",
    "smallint": "smallint",
    "numeric": "numeric",
    "double precision": "float",
    "real": "float",
    "boolean": "bool",
    "timestamp with time zone": "timestamptz",
    "date": "date",
    "jsonb": "jsonb",
    "json": "json",
    "ARRAY": "array",
    "USER-DEFINED": "geometry",
    "bytea": "bytea",
    "interval": "interval",
    "time without time zone": "time",
}


def nome_entidade(schema: str, tabela: str) -> str:
    return tabela if schema == "public" else f"{schema}_{tabela}"


def chave(schema: str, tabela: str) -> str:
    return tabela if schema == "public" else f"{schema}.{tabela}"


def main(dsn: str) -> None:
    with psycopg.connect(dsn) as conn:
        colunas = conn.execute(
            "select c.table_schema, c.table_name, c.column_name, c.data_type, c.is_nullable"
            " from information_schema.columns c join information_schema.tables t"
            " on t.table_schema = c.table_schema and t.table_name = c.table_name"
            " where c.table_schema in ('public', 'interno') and t.table_type = 'BASE TABLE'"
            " and c.table_name not like 'telemetria\\_y%%' and c.table_name <> 'telemetria_default'"
            " order by c.table_schema, c.table_name, c.ordinal_position"
        ).fetchall()
        pks = conn.execute(
            "select kcu.table_schema, kcu.table_name, kcu.column_name"
            " from information_schema.table_constraints tc join information_schema.key_column_usage kcu"
            " on kcu.constraint_name = tc.constraint_name and kcu.table_schema = tc.table_schema"
            " where tc.constraint_type = 'PRIMARY KEY' and tc.table_schema in ('public', 'interno')"
        ).fetchall()
        fks = conn.execute(
            "select distinct cl.relnamespace::regnamespace::text as s, cl.relname as t,"
            " a.attname as col, rcl.relnamespace::regnamespace::text as rs, rcl.relname as rt"
            " from pg_constraint co join pg_class cl on cl.oid = co.conrelid"
            " join pg_class rcl on rcl.oid = co.confrelid"
            " join pg_attribute a on a.attrelid = co.conrelid and a.attnum = any(co.conkey)"
            " where co.contype = 'f' and cl.relnamespace::regnamespace::text in ('public', 'interno')"
            " and not cl.relispartition"
        ).fetchall()

    cols: dict[str, list[tuple[str, str, bool]]] = defaultdict(list)
    for s, t, c, tipo, nulo in colunas:
        cols[chave(s, t)].append((c, TIPOS.get(tipo, tipo.split()[0]), nulo == "YES"))
    pk = {(chave(s, t), c) for s, t, c in pks}
    fk_col = {(chave(s, t), col) for s, t, col, _, _ in fks}
    nulo = {(k, c): n for k, lista in cols.items() for c, _, n in lista}

    partes = [
        "# Banco de dados (DER)",
        "",
        "PostgreSQL 16 + PostGIS. O esquema é versionado em "
        "[`supabase/migrations`](../../supabase/migrations) e este documento é **gerado a partir "
        "dele** por [`scripts/gerar_der.py`](../../scripts/gerar_der.py).",
        "",
        f"- **{len(cols)} tabelas** (`public`: dados do cliente; `interno`: fila, auditoria, chaves, "
        "LGPD), **{n} chaves estrangeiras**.".format(n=len(fks)),
        "- **Multiempresa:** toda tabela de cliente tem `organizacao_id` e política de Row Level "
        "Security. Para o diagrama ficar legível, a ligação de cada tabela com `organizacoes` só "
        "aparece no primeiro diagrama.",
        "- **Telemetria particionada por mês** (`telemetria_yAAAAmMM`): consultas por período leem só "
        "as partições do intervalo.",
        "- **Geometria:** contornos de talhão, linhas e coberturas em `geometry` (PostGIS, SRID 4326).",
        "- `PK` = chave primária, `FK` = chave estrangeira.",
        "",
    ]
    for titulo, descricao, tabelas in GRUPOS:
        presentes = [t for t in tabelas if t in cols]
        conjunto = set(presentes)
        partes += [f"## {titulo}", "", descricao, "", "```mermaid", "erDiagram"]
        for s, t, col, rs, rt in sorted(fks):
            filho, pai = chave(s, t), chave(rs, rt)
            if filho not in conjunto:
                continue
            if pai == "organizacoes" and titulo != GRUPOS[0][0]:
                continue
            pai_nome = nome_entidade(rs, rt)
            # pai 1 (ou 0..1, se a FK aceita nulo) para filhos 0..n
            card = "|o--o{" if nulo.get((filho, col), True) else "||--o{"
            partes.append(f'    {pai_nome} {card} {nome_entidade(s, t)} : "{col}"')
        for t in presentes:
            s, _, nome = t.rpartition(".")
            partes.append(f"    {nome_entidade(s or 'public', nome)} {{")
            for c, tipo, _ in cols[t]:
                marca = " PK" if (t, c) in pk else (" FK" if (t, c) in fk_col else "")
                partes.append(f"        {tipo} {c}{marca}")
            partes.append("    }")
        partes += ["```", ""]
    SAIDA.write_text("\n".join(partes), encoding="utf-8", newline="\n")
    print(f"{len(cols)} tabelas, {len(fks)} FKs -> {SAIDA}")


if __name__ == "__main__":
    main(sys.argv[1])
