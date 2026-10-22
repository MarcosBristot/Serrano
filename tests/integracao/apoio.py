"""Fixtures e utilitários dos testes de integração de API + worker."""

from __future__ import annotations

import io
import uuid
import zipfile
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from sistemacampero.domain.tenancy import Organizacao
from sistemacampero.infrastructure.config import Settings
from sistemacampero.infrastructure.container import Container, construir
from sistemacampero.infrastructure.persistence.organizacoes import (
    PostgresRepositorioOrganizacoes,
)
from sistemacampero.infrastructure.storage.local import ArmazenamentoLocal
from sistemacampero.interfaces.api.app import create_app
from sistemacampero.interfaces.worker import Worker
from tests.conftest import SEGREDO, emitir_token

Conn = psycopg.Connection[dict[str, Any]]


def criar_usuario(admin: psycopg.Connection[Any]) -> uuid.UUID:
    uid = uuid.uuid4()
    admin.execute("insert into auth.users (id, email) values (%s, %s)", (uid, f"{uid}@teste.dev"))
    return uid


@pytest.fixture(scope="session")
def container(
    bancos: dict[str, str], tmp_path_factory: pytest.TempPathFactory
) -> Iterator[Container]:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        ambiente="test",
        database_url=bancos["backend"],
        supabase_url="https://projeto-teste.supabase.co",
        supabase_jwt_secret=SEGREDO,
        storage_dir=tmp_path_factory.mktemp("storage"),
        db_pool_max=6,
        chave_cifragem="x9Yp4n1bQm0yX1rD0H8q3jzK8lQ2b0nY7mV5cH6tW1E=",
    )
    c = construir(settings, storage=ArmazenamentoLocal(settings.storage_dir))
    assert c.db is not None
    c.db.pool.wait(timeout=10)
    yield c
    c.fechar()


@pytest.fixture(scope="session")
def client(container: Container) -> TestClient:
    return TestClient(create_app(container))


@pytest.fixture
def worker(container: Container) -> Worker:
    assert container.fila is not None and container.executor is not None
    w = Worker(container.fila, container.executor, lease_s=60, heartbeat_s=5, reaper_s=0)
    drenar(w, 500)  # sobras de testes anteriores não entram nas contagens
    return w


@pytest.fixture
def org(admin: Conn, container: Container) -> dict[str, Any]:
    """Organização nova por teste (isolamento) com dono e token."""
    assert container.db is not None
    uid = criar_usuario(admin)
    o = Organizacao(id=uuid.uuid4(), nome="Org Teste", slug=f"org-{uuid.uuid4().hex[:10]}")
    PostgresRepositorioOrganizacoes(container.db).criar_organizacao(o, uid, "basico", 30)
    return {"id": o.id, "user": uid, "auth": {"Authorization": f"Bearer {emitir_token(uid)}"}}


def drenar(worker: Worker, maximo: int = 50) -> int:
    n = 0
    while n < maximo and worker.rodar_uma_vez():
        n += 1
    return n


def upload(
    client: TestClient, org: dict[str, Any], dados: bytes, nome: str = "s.jdl", **params: str
) -> dict[str, Any]:
    resp = client.post(
        "/api/v1/telemetry/upload",
        params={"marca": "john_deere", "tecnologia": "gen4", **params},
        files={"arquivo": (nome, dados, "application/octet-stream")},
        headers=org["auth"],
    )
    assert resp.status_code == 202, resp.text
    return resp.json()  # type: ignore[no-any-return]


def um(admin: Conn, sql: str, *params: Any) -> Any:
    linha = admin.execute(sql, params).fetchone()
    return None if linha is None else next(iter(linha.values()))


def zipar(entradas: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for nome, dados in entradas.items():
            zf.writestr(nome, dados)
    return buf.getvalue()
