"""M7 no PostGIS real: convites, papéis, chaves de API e auditoria."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import emitir_token
from tests.integracao.apoio import Conn, criar_usuario, upload
from tests.sinteticos.jdl_builder import Cenario
from tests.sinteticos.jdl_builder import construir as construir_jdl

pytestmark = pytest.mark.integracao


def _usuario(admin: Conn, email: str) -> dict[str, str]:
    uid = criar_usuario(admin)
    admin.execute("update auth.users set email = %s where id = %s", (email, uid))
    return {"Authorization": f"Bearer {emitir_token(uid, email=email)}"}


def test_convite_aceite_e_papeis(client: TestClient, org: dict[str, Any], admin: Conn) -> None:
    h = org["auth"]
    r = client.post(
        "/api/v1/convites", json={"email": "Novo@Fazenda.com", "papel": "gestor"}, headers=h
    )
    assert r.status_code == 201, r.text
    token = r.json()["token"]
    assert r.json()["email"] == "novo@fazenda.com" and r.json()["email_enviado"] is False
    assert [c["email"] for c in client.get("/api/v1/convites", headers=h).json()] == [
        "novo@fazenda.com"
    ]

    intruso = _usuario(admin, "outro@fazenda.com")
    assert (
        client.post(f"/api/v1/convites/{token}/aceitar", headers=intruso).json()["code"]
        == "CONVITE_OUTRO_EMAIL"
    )
    novo = _usuario(admin, "novo@fazenda.com")
    ok = client.post(f"/api/v1/convites/{token}/aceitar", headers=novo)
    assert ok.status_code == 200 and ok.json()["organizacao_id"] == str(org["id"])
    assert client.post(f"/api/v1/convites/{token}/aceitar", headers=novo).status_code == 409
    assert client.get("/api/v1/organizacao-ativa", headers=novo).json()["papel"] == "gestor"

    membros = client.get("/api/v1/membros", headers=h).json()
    assert {(m["email"], m["papel"]) for m in membros} >= {("novo@fazenda.com", "gestor")}
    # gestor não administra a equipe
    assert (
        client.post("/api/v1/convites", json={"email": "x@y.com"}, headers=novo).status_code == 403
    )

    dono = str(org["user"])
    ultimo = client.patch(f"/api/v1/membros/{dono}", json={"papel": "leitor"}, headers=h)
    assert ultimo.status_code == 409 and ultimo.json()["code"] == "ULTIMO_OWNER"
    novo_id = next(m["usuario_id"] for m in membros if m["email"] == "novo@fazenda.com")
    assert client.delete(f"/api/v1/membros/{novo_id}", headers=h).status_code == 204
    assert client.get("/api/v1/organizacao-ativa", headers=novo).json()["code"] == "SEM_ORGANIZACAO"


def test_chaves_de_api(client: TestClient, worker: Any, org: dict[str, Any]) -> None:
    h = org["auth"]
    leitura = client.post("/api/v1/chaves-api", json={"nome": "BI"}, headers=h).json()
    escrita = client.post(
        "/api/v1/chaves-api", json={"nome": "Coletor", "escopos": ["ler", "operar"]}, headers=h
    ).json()
    assert leitura["chave"].startswith("cmp_") and leitura["escopos"] == ["ler"]
    assert "chave" not in client.get("/api/v1/chaves-api", headers=h).json()[0]

    jdl = construir_jdl(Cenario(minutos=2))
    negado = client.post(
        "/api/v1/telemetry/upload",
        files={"arquivo": ("a.jdl", jdl, "x")},
        headers={"X-API-Key": leitura["chave"]},
    )
    assert negado.status_code == 403
    aceito = client.post(
        "/api/v1/telemetry/upload",
        files={"arquivo": ("a.jdl", jdl, "x")},
        headers={"Authorization": f"Bearer {escrita['chave']}"},
    )
    assert aceito.status_code == 202
    assert (
        client.get("/api/v1/kpis/resumo", headers={"X-API-Key": leitura["chave"]}).status_code
        == 200
    )
    assert (
        client.get(
            "/api/v1/me", headers={"Authorization": f"Bearer {leitura['chave']}"}
        ).status_code
        == 401
    )

    assert client.delete(f"/api/v1/chaves-api/{leitura['id']}", headers=h).status_code == 204
    revogada = client.get("/api/v1/kpis/resumo", headers={"X-API-Key": leitura["chave"]})
    assert revogada.status_code == 401 and revogada.json()["code"] == "CHAVE_INVALIDA"
    falsa = client.get("/api/v1/kpis/resumo", headers={"X-API-Key": escrita["chave"][:-3] + "abc"})
    assert falsa.status_code == 401


def test_auditoria_registra_mutacoes_sem_pii(client: TestClient, org: dict[str, Any]) -> None:
    h = org["auth"]
    upload(client, org, construir_jdl(Cenario(minutos=1)))
    t = client.post("/api/v1/talhoes", json={"nome": "Auditado"}, headers=h).json()
    client.get("/api/v1/talhoes", headers=h)  # leitura não é auditada
    client.post("/api/v1/fazendas", json={"nome": ""}, headers=h)  # erro não é auditado
    eventos = client.get("/api/v1/auditoria", headers=h).json()
    acoes = [e["acao"] for e in eventos]
    assert "POST /api/v1/talhoes" in acoes and "POST /api/v1/telemetry/upload" in acoes
    assert not any(a.startswith("GET") for a in acoes) and "POST /api/v1/fazendas" not in acoes
    talhao = next(e for e in eventos if e["acao"] == "POST /api/v1/talhoes")
    assert talhao["ator_id"] == str(org["user"]) and talhao["ator_tipo"] == "usuario"
    assert talhao["recurso_tipo"] == "talhoes" and talhao["dados"] == {}
    patch = client.patch(f"/api/v1/talhoes/{t['id']}", json={"nome": "X"}, headers=h)
    assert patch.status_code == 200
    ultimo = client.get("/api/v1/auditoria", params={"limit": 1}, headers=h).json()[0]
    assert ultimo["recurso_id"] == t["id"] and ultimo["acao"] == "PATCH /api/v1/talhoes/{ident}"
