"""Gera configurar_supabase.sql: todas as migrations + senha do campero_backend, para o SQL Editor.

Use quando a rede bloqueia a porta 5432 (o SQL Editor do Supabase funciona pelo navegador).
No SQL Editor, se aparecer "Run and enable RLS", tanto faz: a migration 20261023000000
deixa as tabelas internas com RLS e política explícitas.

    uv run python scripts/gerar_sql_supabase.py
"""

import re
import sys
from pathlib import Path

raiz = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
env = {}
for linha in (raiz / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in linha and not linha.lstrip().startswith("#"):
        k, v = linha.split("=", 1)
        env[k.strip()] = v.strip()
senha = env["CAMPERO_BACKEND_SENHA"]
assert "'" not in senha

partes = [
    "-- Sistema Campero: configuração inicial do banco (rode UMA vez no SQL Editor do Supabase).",
    "-- Gerado a partir de supabase/migrations.",
    "-- Contém a senha do papel campero_backend: não compartilhe.",
    "begin;",
    "create schema if not exists supabase_migrations;",
    "create table if not exists supabase_migrations.schema_migrations "
    "(version text primary key, statements text[], name text);",
]
for arq in sorted((raiz / "supabase" / "migrations").glob("*.sql")):
    versao, nome = re.match(r"(\d{14})_(.+)\.sql", arq.name).groups()
    partes.append(f"\n-- ===== {arq.name} =====")
    partes.append(arq.read_text(encoding="utf-8"))
    partes.append(
        "insert into supabase_migrations.schema_migrations (version, name) "
        f"values ('{versao}', '{nome}') on conflict (version) do nothing;"
    )
partes.append(f"\nalter role campero_backend password '{senha}';")
partes.append("commit;")
partes.append(
    "select 'Campero configurado' as resultado, count(*) as tabelas "
    "from information_schema.tables where table_schema in ('public','interno');"
)
destino = raiz / "configurar_supabase.sql"
destino.write_text("\n".join(partes) + "\n", encoding="utf-8", newline="\n")
print(destino.name, f"{destino.stat().st_size // 1024} KB")
