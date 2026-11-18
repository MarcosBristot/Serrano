"""Upload em partes: pendrive acima do limite de 100 MB por requisição da Cloudflare (plano grátis)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from sistemacampero.interfaces.worker import Worker
from tests.integracao.apoio import drenar, upload, zipar
from tests.sinteticos import gs3

pytestmark = pytest.mark.integracao
PASTA = "GS3_2630/Cliente/RCD/EIC/Documentation/a1"
BASE = "/api/v1/telemetry/upload/partes"


def _pacote() -> bytes:
    return zipar(
        {
            f"{PASTA}/6363bd9a.fdl": gs3.construir_fdl(),
            f"{PASTA}/6363bd9a.fdd": gs3.construir_fdd(gs3.CenarioGs3(minutos=20)),
        }
    )


def _iniciar(
    client: TestClient, org: dict[str, Any], dados: bytes, nome: str = "pendrive.zip"
) -> str:
    r = client.post(BASE, json={"nome": nome, "tamanho": len(dados)}, headers=org["auth"])
    assert r.status_code == 201, r.text
    return str(r.json()["upload_id"])


def _parte(client: TestClient, org: dict[str, Any], uid: str, i: int, dados: bytes) -> Any:
    h = {**org["auth"], "Content-Type": "application/octet-stream"}
    return client.put(f"{BASE}/{uid}/{i}", content=dados, headers=h)


def test_partes_juntas_viram_o_mesmo_arquivo_do_upload_simples(
    client: TestClient, worker: Worker, org: dict[str, Any]
) -> None:
    dados = _pacote()
    uid = _iniciar(client, org, dados)
    terco = len(dados) // 3 + 1
    pedacos = [dados[i : i + terco] for i in range(0, len(dados), terco)]
    for i, p in enumerate(pedacos):
        assert _parte(client, org, uid, i, p).status_code == 200
    # a resposta da última parte se perdeu e o painel reenviou: aceito sem duplicar bytes
    assert _parte(client, org, uid, len(pedacos) - 1, pedacos[-1]).json()["recebido"] == len(dados)

    r = client.post(f"{BASE}/{uid}/concluir", headers=org["auth"])
    assert r.status_code == 202, r.text
    corpo = r.json()
    assert corpo["tipo"] == "zip" and corpo["arquivo"] == "pendrive.zip" and not corpo["duplicado"]
    drenar(worker)
    assert len(client.get("/api/v1/sessions", headers=org["auth"]).json()["itens"]) == 1

    # mesmo conteúdo pelo upload simples: reconhecido como o mesmo arquivo (mesmo sha256)
    assert upload(client, org, dados, nome="pendrive.zip")["duplicado"] is True
    # a pasta temporária foi apagada
    assert client.post(f"{BASE}/{uid}/concluir", headers=org["auth"]).status_code == 404


def test_parte_fora_de_ordem_e_envio_incompleto_sao_recusados(
    client: TestClient, org: dict[str, Any]
) -> None:
    dados = _pacote()
    uid = _iniciar(client, org, dados)
    r = _parte(client, org, uid, 1, dados[:10])
    assert r.status_code == 422 and r.json()["code"] == "PARTE_FORA_DE_ORDEM"
    assert _parte(client, org, uid, 0, dados[:10]).status_code == 200
    r = client.post(f"{BASE}/{uid}/concluir", headers=org["auth"])
    assert r.status_code == 422 and r.json()["code"] == "ENVIO_INCOMPLETO"
    # mais bytes que o anunciado no início
    r = _parte(client, org, uid, 1, dados + b"x")
    assert r.status_code == 422 and r.json()["code"] == "PARTE_GRANDE"


def test_arquivo_acima_do_limite_e_recusado_no_inicio(
    client: TestClient, org: dict[str, Any]
) -> None:
    r = client.post(BASE, json={"nome": "enorme.zip", "tamanho": 10 * 1024**4}, headers=org["auth"])
    assert r.status_code == 422 and r.json()["code"] == "ARQUIVO_GRANDE"


def test_envio_de_outra_organizacao_nao_e_encontrado(
    client: TestClient, org: dict[str, Any]
) -> None:
    r = client.put(
        f"{BASE}/00000000-0000-0000-0000-000000000000/0",
        content=b"x",
        headers={**org["auth"], "Content-Type": "application/octet-stream"},
    )
    assert r.status_code == 404 and r.json()["code"] == "ENVIO_NAO_ENCONTRADO"
