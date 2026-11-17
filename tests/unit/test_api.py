from __future__ import annotations

import uuid

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from sistemacampero.domain.tenancy import Papel
from sistemacampero.infrastructure.container import Container
from sistemacampero.interfaces.api.app import create_app
from tests.conftest import ACEITE, RepositorioEmMemoria, emitir_token


@pytest.fixture
def app(container: Container):  # type: ignore[no-untyped-def]
    app = create_app(container)
    boom = APIRouter()

    @boom.get("/api/v1/_eco/{item_id}")
    def _eco(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    @boom.get("/api/v1/_boom")
    def _boom() -> None:
        raise RuntimeError("falha simulada")

    app.include_router(boom)
    return app


@pytest.fixture
def client(app) -> TestClient:  # type: ignore[no-untyped-def]
    return TestClient(app)


def _auth(uid: uuid.UUID, **headers: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {emitir_token(uid)}", **headers}


def _problema(resp, status: int, code: str) -> dict:  # type: ignore[no-untyped-def]
    assert resp.status_code == status, resp.text
    assert resp.headers["content-type"].startswith("application/problem+json")
    corpo = resp.json()
    assert corpo["status"] == status
    assert corpo["code"] == code
    assert corpo["request_id"] == resp.headers["x-request-id"]
    return corpo  # type: ignore[no-any-return]


def test_health_e_ready(client: TestClient, container: Container) -> None:
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/ready").status_code == 200
    container.prontidao.checks["banco"] = "erro: OperationalError"  # type: ignore[attr-defined]
    resp = client.get("/ready")
    assert resp.status_code == 503
    assert resp.json()["checks"]["banco"].startswith("erro")


def test_request_id_gerado_e_propagado(client: TestClient) -> None:
    gerado = client.get("/health").headers["x-request-id"]
    assert len(gerado) == 32
    assert (
        client.get("/health", headers={"X-Request-ID": "abc-12345678"}).headers["x-request-id"]
        == "abc-12345678"
    )
    # Valor estranho (injeção em log) é trocado por um gerado.
    assert client.get("/health", headers={"X-Request-ID": "x\ty"}).headers["x-request-id"] != "x\ty"


def test_sem_token_401(client: TestClient) -> None:
    resp = client.get("/api/v1/me")
    _problema(resp, 401, "NAO_AUTENTICADO")
    assert resp.headers["www-authenticate"] == "Bearer"
    _problema(
        client.get("/api/v1/me", headers={"Authorization": "Bearer lixo"}), 401, "NAO_AUTENTICADO"
    )


def test_me_lista_organizacoes(client: TestClient, repo: RepositorioEmMemoria) -> None:
    uid = uuid.uuid4()
    org = repo.adicionar("Agro Um", uid, Papel.GESTOR)
    corpo = client.get("/api/v1/me", headers=_auth(uid)).json()
    assert corpo["usuario_id"] == str(uid)
    assert corpo["email"] == "gestor@example.com"
    assert corpo["organizacoes"] == [
        {"organizacao_id": str(org), "nome": "Agro Um", "slug": "agro-um", "papel": "gestor"}
    ]


def test_cria_organizacao(client: TestClient) -> None:
    uid = uuid.uuid4()
    resp = client.post(
        "/api/v1/organizacoes", json={"nome": "Fazenda Serrano", **ACEITE}, headers=_auth(uid)
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["slug"] == "fazenda-serrano"
    assert resp.json()["papel"] == "owner"
    ativa = client.get("/api/v1/organizacao-ativa", headers=_auth(uid)).json()
    assert ativa == {"organizacao_id": resp.json()["id"], "papel": "owner"}

    _problema(
        client.post("/api/v1/organizacoes", json={"nome": "Outra", **ACEITE}, headers=_auth(uid)),
        409,
        "JA_TEM_ORGANIZACAO",
    )


def test_validacao_vira_problem_json(client: TestClient) -> None:
    corpo = _problema(
        client.post("/api/v1/organizacoes", json={"nome": "x"}, headers=_auth(uuid.uuid4())),
        422,
        "VALIDACAO",
    )
    assert corpo["errors"][0]["loc"] == ["body", "nome"]


def test_organizacao_ativa(client: TestClient, repo: RepositorioEmMemoria) -> None:
    uid = uuid.uuid4()
    _problema(client.get("/api/v1/organizacao-ativa", headers=_auth(uid)), 403, "SEM_ORGANIZACAO")
    repo.adicionar("Agro Um", uid, Papel.OWNER)
    org2 = repo.adicionar("Agro Dois", uid, Papel.LEITOR)
    _problema(
        client.get("/api/v1/organizacao-ativa", headers=_auth(uid)), 422, "ORGANIZACAO_AMBIGUA"
    )
    resp = client.get(
        "/api/v1/organizacao-ativa", headers=_auth(uid, **{"X-Organizacao-Id": str(org2)})
    )
    assert resp.json()["papel"] == "leitor"
    _problema(
        client.get("/api/v1/organizacao-ativa", headers=_auth(uid, **{"X-Organizacao-Id": "123"})),
        422,
        "ORGANIZACAO_INVALIDA",
    )
    _problema(
        client.get(
            "/api/v1/organizacao-ativa",
            headers=_auth(uid, **{"X-Organizacao-Id": str(uuid.uuid4())}),
        ),
        403,
        "ORGANIZACAO_PROIBIDA",
    )


def test_404_e_500_em_problem_json(client: TestClient) -> None:
    _problema(client.get("/api/v1/nao-existe"), 404, "NAO_ENCONTRADO")
    corpo = _problema(client.get("/api/v1/_boom"), 500, "ERRO_INTERNO")
    assert "falha simulada" not in corpo["detail"]


def test_metrics_usa_template_da_rota(client: TestClient) -> None:
    client.get("/health")
    client.get("/api/v1/_eco/abc123")
    client.get("/api/v1/nao-existe")
    texto = client.get("/metrics").text
    assert 'http_requests_total{method="GET",route="/health",status="200"}' in texto
    assert 'route="/api/v1/_eco/{item_id}",status="200"' in texto
    assert 'route="nao_roteada",status="404"' in texto
    assert "abc123" not in texto


def test_openapi_documenta_rotas(client: TestClient) -> None:
    caminhos = client.get("/openapi.json").json()["paths"]
    assert {"/api/v1/me", "/api/v1/organizacoes", "/health", "/ready"} <= set(caminhos)


def test_cabecalhos_de_seguranca(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"
    assert "strict-transport-security" not in r.headers  # só staging/prod


def test_limite_de_requisicoes() -> None:
    from sistemacampero.interfaces.api.protecao import Balde

    b = Balde(por_minuto=3)
    assert [b.consumir("x", agora=0.0) for _ in range(3)] == [0.0, 0.0, 0.0]
    espera = b.consumir("x", agora=0.0)
    assert espera == pytest.approx(20.0)  # 1 ficha a cada 20 s
    assert b.consumir("outro", agora=0.0) == 0.0
    assert b.consumir("x", agora=21.0) == 0.0


def test_429_em_problem_json(container: Container) -> None:
    from dataclasses import replace

    c = replace(container, settings=container.settings.model_copy(update={"limite_por_minuto": 10}))
    cli = TestClient(create_app(c))
    respostas = [cli.get("/api/v1/me").status_code for _ in range(12)]
    assert respostas.count(429) == 2
    r = cli.get("/api/v1/me")
    assert r.json()["code"] == "LIMITE_DE_REQUISICOES" and int(r.headers["retry-after"]) >= 1
    assert cli.get("/health").status_code == 200  # healthcheck não é limitado


def test_organizacao_exige_aceite_dos_termos(client: TestClient) -> None:
    corpo = _problema(
        client.post(
            "/api/v1/organizacoes", json={"nome": "Sem Aceite"}, headers=_auth(uuid.uuid4())
        ),
        422,
        "VALIDACAO",
    )
    assert ["body", "aceite_termos"] in [e["loc"] for e in corpo["errors"]]
