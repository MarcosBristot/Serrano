"""Aplica as migrations SQL em ordem (dev, docker-compose e testes).

Em staging/produção quem aplica é a Supabase CLI (``supabase db push``) no CI; este
executor usa a mesma tabela de controle (``supabase_migrations.schema_migrations``).
O ``bootstrap_supabase_local.sql`` cria num PostGIS comum o que o Supabase já traz.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import psycopg
from psycopg import sql

logger = logging.getLogger(__name__)


def _raiz() -> Path:
    """Raiz do repositório (instalação editável) ou o diretório atual (imagem Docker)."""
    candidata = Path(__file__).resolve().parents[4]
    return candidata if (candidata / "supabase").is_dir() else Path.cwd()


RAIZ = _raiz()
MIGRATIONS_DIR = RAIZ / "supabase" / "migrations"
BOOTSTRAP_SQL = RAIZ / "db" / "bootstrap_supabase_local.sql"

_NOME = re.compile(r"^(\d{14})_([a-z0-9_]+)\.sql$")

_CONTROLE = """
create schema if not exists supabase_migrations;
create table if not exists supabase_migrations.schema_migrations (
    version text primary key,
    name text,
    statements text[]
);
"""


def listar_migrations(pasta: Path = MIGRATIONS_DIR) -> list[tuple[str, str, Path]]:
    itens = []
    for arq in sorted(pasta.glob("*.sql")):
        m = _NOME.fullmatch(arq.name)
        if not m:
            raise ValueError(f"Nome de migration fora do padrão: {arq.name}")
        itens.append((m.group(1), m.group(2), arq))
    return itens


def criar_banco_se_preciso(dsn: str) -> None:
    """Cria o banco do DSN (a partir de template0) conectando ao banco 'postgres'."""
    info = psycopg.conninfo.conninfo_to_dict(dsn)
    nome = str(info.get("dbname") or "postgres")
    if nome == "postgres":
        return
    manut = psycopg.conninfo.make_conninfo(dsn, dbname="postgres")
    with psycopg.connect(manut, autocommit=True) as conn:
        existe = conn.execute("select 1 from pg_database where datname = %s", (nome,)).fetchone()
        if not existe:
            conn.execute(
                sql.SQL("create database {} template template0").format(sql.Identifier(nome))
            )
            logger.info("banco criado", extra={"banco": nome})


def aplicar(dsn: str, *, bootstrap: bool = False, pasta: Path = MIGRATIONS_DIR) -> list[str]:
    """Aplica as pendentes; devolve as versões aplicadas agora."""
    aplicadas: list[str] = []
    with psycopg.connect(dsn, autocommit=True) as conn:
        if bootstrap:
            conn.execute(BOOTSTRAP_SQL.read_text(encoding="utf-8"))
        conn.execute(_CONTROLE)
        feitas = {
            r[0] for r in conn.execute("select version from supabase_migrations.schema_migrations")
        }
        for versao, nome, arq in listar_migrations(pasta):
            if versao in feitas:
                continue
            with conn.transaction():
                conn.execute(arq.read_text(encoding="utf-8"))
                conn.execute(
                    "insert into supabase_migrations.schema_migrations (version, name)"
                    " values (%s, %s)",
                    (versao, nome),
                )
            logger.info("migration aplicada", extra={"versao": versao, "nome": nome})
            aplicadas.append(versao)
    return aplicadas


def definir_senha_backend(dsn: str, senha: str) -> None:
    """Só dev/teste. Em Supabase a senha é definida uma vez, à mão, por ambiente."""
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("alter role campero_backend password {}").format(sql.Literal(senha)))
