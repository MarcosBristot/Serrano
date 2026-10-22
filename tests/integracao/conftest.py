"""PostGIS real num banco vazio: bootstrap do Supabase + todas as migrations.

Defina ``CAMPERO_TEST_DATABASE_URL`` com um superusuário (ex.: o ``db`` do docker-compose:
``postgresql://postgres:postgres@localhost:54322/postgres``). Sem ela, estes testes são pulados.
Cada sessão de testes cria e apaga o próprio banco ``campero_test_<aleatório>``.
"""

from __future__ import annotations

import json
import os
import secrets
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row

from sistemacampero.infrastructure.persistence import migrations
from sistemacampero.infrastructure.persistence.db import Database

pytestmark = pytest.mark.integracao


@pytest.fixture(scope="session")
def admin_base() -> str:
    dsn = os.environ.get("CAMPERO_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("CAMPERO_TEST_DATABASE_URL não definida")
    return dsn


@pytest.fixture(scope="session")
def bancos(admin_base: str) -> Iterator[dict[str, str]]:
    nome = f"campero_test_{secrets.token_hex(4)}"
    senha_backend = secrets.token_urlsafe(24)
    admin_dsn = psycopg.conninfo.make_conninfo(admin_base, dbname=nome)
    migrations.criar_banco_se_preciso(admin_dsn)
    try:
        migrations.aplicar(admin_dsn, bootstrap=True)
        migrations.definir_senha_backend(admin_dsn, senha_backend)
        backend_dsn = psycopg.conninfo.make_conninfo(
            admin_dsn, user="campero_backend", password=senha_backend
        )
        yield {"admin": admin_dsn, "backend": backend_dsn}
    finally:
        manut = psycopg.conninfo.make_conninfo(admin_base, dbname="postgres")
        with psycopg.connect(manut, autocommit=True) as conn:
            conn.execute(
                sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(nome))
            )


@pytest.fixture
def admin(bancos: dict[str, str]) -> Iterator[psycopg.Connection[dict[str, Any]]]:
    with psycopg.connect(bancos["admin"], autocommit=True, row_factory=dict_row) as conn:
        yield conn


@pytest.fixture(scope="session")
def db_backend(bancos: dict[str, str]) -> Iterator[Database]:
    db = Database(bancos["backend"], min_size=1, max_size=4)
    db.pool.wait(timeout=10)
    yield db
    db.fechar()


def criar_usuario(admin: psycopg.Connection[Any]) -> uuid.UUID:
    uid = uuid.uuid4()
    admin.execute("insert into auth.users (id, email) values (%s, %s)", (uid, f"{uid}@teste.dev"))
    return uid


@contextmanager
def como(
    admin: psycopg.Connection[Any], papel: str, *, usuario: uuid.UUID | None = None
) -> Iterator[psycopg.Connection[Any]]:
    """Executa como anon/authenticated/service_role (como o PostgREST faz) e desfaz tudo."""
    with admin.transaction(force_rollback=True):
        claims = {"role": papel}
        if usuario:
            claims["sub"] = str(usuario)
        admin.execute(
            "select set_config('request.jwt.claims', %s, true)",
            (json.dumps(claims),),
        )
        admin.execute(sql.SQL("set local role {}").format(sql.Identifier(papel)))
        yield admin
