"""Site: formulário público de demonstração."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sistemacampero.infrastructure.container import Container
from tests.conftest import ACEITE, emitir_token
from tests.integracao.apoio import Conn, criar_usuario, um

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


def test_contato_guarda_consentimento_e_expira(
    client: TestClient, admin: Conn, container: Container
) -> None:
    r = client.post(
        "/api/v1/contatos",
        json={"nome": "Bia Lima", "email": "bia@fazenda.com", "politica_versao": "2026-10-28"},
    )
    assert r.status_code == 202, r.text
    linha = admin.execute(
        "select politica_versao, aceita_novidades from interno.contatos where nome = 'Bia Lima'"
    ).fetchone()
    assert linha == {"politica_versao": "2026-10-28", "aceita_novidades": False}

    admin.execute(
        "update interno.contatos set criado_em = now() - interval '13 months' where nome = 'Bia Lima'"
    )
    assert container.contatos is not None
    assert container.contatos.expurgar(12) >= 1
    assert um(admin, "select count(*) from interno.contatos where nome = 'Bia Lima'") == 0


def test_criar_organizacao_registra_aceite(client: TestClient, admin: Conn) -> None:
    uid = criar_usuario(admin)
    h = {"Authorization": f"Bearer {emitir_token(uid)}"}
    r = client.post("/api/v1/organizacoes", json={"nome": "Fazenda Aceite", **ACEITE}, headers=h)
    assert r.status_code == 201, r.text
    docs = admin.execute(
        "select documento, versao from interno.aceites where usuario_id = %s order by documento",
        (uid,),
    ).fetchall()
    assert docs == [
        {"documento": "privacidade", "versao": "2026-10-28"},
        {"documento": "termos", "versao": "2026-10-28"},
    ]
