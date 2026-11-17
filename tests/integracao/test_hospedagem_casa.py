"""Hospedagem em casa: usuário do Supabase Auth copiado para o banco local no primeiro acesso."""

from __future__ import annotations

import uuid
from typing import Any

import psycopg
import pytest

from sistemacampero.infrastructure.persistence.db import Database
from sistemacampero.infrastructure.persistence.usuarios import EspelhoDeUsuarios


def test_espelha_usuario_uma_vez(admin: psycopg.Connection[Any], db_backend: Database) -> None:
    espelho = EspelhoDeUsuarios(db_backend)
    uid = uuid.uuid4()
    email = f"{uid.hex[:8]}@fazenda.test"

    espelho.garantir(uid, email)
    espelho.garantir(uid, email)  # repetido: nada muda

    linhas = admin.execute("select email from auth.users where id = %s", (uid,)).fetchall()
    assert [r["email"] for r in linhas] == [email]


def test_usuario_espelhado_pode_criar_organizacao(
    admin: psycopg.Connection[Any], db_backend: Database
) -> None:
    uid = uuid.uuid4()
    EspelhoDeUsuarios(db_backend).garantir(uid, None)
    org = admin.execute(
        "insert into public.organizacoes (nome, slug) values ('Casa', %s) returning id",
        (f"casa-{uid.hex[:8]}",),
    ).fetchone()
    admin.execute(
        "insert into public.membros (organizacao_id, usuario_id, papel) values (%s, %s, 'owner')",
        (org["id"], uid),
    )


def test_papel_da_aplicacao_nao_escreve_direto_em_auth_users(db_backend: Database) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege), db_backend.transacao(None) as conn:
        conn.execute("insert into auth.users (id) values (%s)", (uuid.uuid4(),))
