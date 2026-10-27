"""Site: formulário público de demonstração."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.integracao.apoio import Conn, um

pytestmark = pytest.mark.integracao


def test_contato_publico_grava_sem_login(client: TestClient, admin: Conn) -> None:
    r = client.post(
        "/api/v1/contatos",
        json={"nome": "Ana Souza", "email": "Ana@Fazenda.com", "hectares": 1200, "maquinas": 6},
    )
    assert r.status_code == 202, r.text
    assert um(admin, "select email from interno.contatos where nome = 'Ana Souza'") == (
        "ana@fazenda.com"
    )


def test_contato_robo_e_invalido(client: TestClient, admin: Conn) -> None:
    r = client.post(
        "/api/v1/contatos",
        json={"nome": "Robo", "email": "robo@x.com", "website": "http://spam"},
    )
    assert r.status_code == 202
    assert um(admin, "select count(*) from interno.contatos where nome = 'Robo'") == 0
    assert client.post("/api/v1/contatos", json={"nome": "A", "email": "x"}).status_code == 422
