"""Plano e assinatura, integrações e saúde dos dados, no PostGIS real."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from sistemacampero.interfaces.worker import Worker
from tests.integracao.apoio import Conn, drenar, upload
from tests.sinteticos.jdl_builder import Cenario
from tests.sinteticos.jdl_builder import construir as construir_jdl

pytestmark = pytest.mark.integracao


def test_assinatura_mostra_teste_uso_e_planos(client: TestClient, org: dict[str, Any]) -> None:
    r = client.get("/api/v1/assinatura", headers=org["auth"])
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["situacao"] == "trial" and 28 <= a["dias_restantes"] <= 30
    assert a["uso"]["maquinas"] == 0 and a["uso"]["usuarios"] == 1
    codigos = [p["codigo"] for p in a["planos"]]
    assert codigos == ["fazenda", "grupo"]  # "basico" e "produtor" fora da vitrine
    assert next(p for p in a["planos"] if p["destaque"])["codigo"] == "fazenda"
    assert a["pedido_aberto"] is None


def test_pedido_de_plano_fica_registrado(client: TestClient, org: dict[str, Any]) -> None:
    h = org["auth"]
    r = client.post(
        "/api/v1/assinatura/pedidos",
        json={"plano_codigo": "fazenda", "ciclo": "anual", "telefone": "54 99999-0000"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    pedido = client.get("/api/v1/assinatura", headers=h).json()["pedido_aberto"]
    assert pedido["plano_codigo"] == "fazenda" and pedido["ciclo"] == "anual"
    r = client.post("/api/v1/assinatura/pedidos", json={"plano_codigo": "basico"}, headers=h)
    assert r.status_code == 422 and r.json()["code"] == "PLANO_INVALIDO"


def test_teste_vencido_bloqueia_envio_mas_nao_a_leitura(
    client: TestClient, org: dict[str, Any], admin: Conn
) -> None:
    admin.execute(
        "update public.assinaturas set fim = now() - interval '1 day' where organizacao_id = %s",
        (org["id"],),
    )
    h = org["auth"]
    assert client.get("/api/v1/assinatura", headers=h).json()["situacao"] == "trial_vencido"
    r = client.post(
        "/api/v1/telemetry/upload",
        files={"arquivo": ("s.jdl", construir_jdl(Cenario(minutos=3)), "application/octet-stream")},
        headers=h,
    )
    assert r.status_code == 422 and r.json()["code"] == "ASSINATURA_INATIVA"
    r = client.post(
        "/api/v1/telemetry/upload/partes", json={"nome": "p.zip", "tamanho": 10}, headers=h
    )
    assert r.status_code == 422 and r.json()["code"] == "ASSINATURA_INATIVA"
    assert client.get("/api/v1/sessions", headers=h).status_code == 200


def test_integracoes_mostram_o_que_ja_chegou(
    client: TestClient, worker: Worker, org: dict[str, Any]
) -> None:
    upload(client, org, construir_jdl(Cenario(minutos=5)))
    drenar(worker)
    itens = {i["id"]: i for i in client.get("/api/v1/integracoes", headers=org["auth"]).json()}
    gen4 = itens["john_deere_gen4"]
    assert gen4["em_uso"] and gen4["sessoes"] == 1 and gen4["maquinas"] == 1
    assert not itens["isoxml"]["em_uso"] and itens["isoxml"]["status"] == "ativa"
    assert itens["operations_center"]["status"] == "roteiro"


def test_qualidade_separa_fragmentos_e_lista_os_esconde(
    client: TestClient, worker: Worker, org: dict[str, Any]
) -> None:
    h = org["auth"]
    upload(client, org, construir_jdl(Cenario(minutos=10)), nome="longa.jdl")
    upload(
        client,
        org,
        construir_jdl(Cenario(minutos=1, horimetro0=700.0, contador0=12000.0)),
        nome="curta.jdl",
    )
    drenar(worker)
    q = client.get("/api/v1/qualidade", headers=h).json()
    assert q["sessoes"]["total"] == 2 and q["sessoes"]["fragmentos"] == 1
    assert q["arquivos"]["processados"] == 2
    assert q["confiabilidade_pct"] is not None and 0 <= q["confiabilidade_pct"] <= 100

    todas = client.get("/api/v1/sessions", headers=h).json()["itens"]
    sem = client.get("/api/v1/sessions", params={"incluir_fragmentos": False}, headers=h).json()
    assert len(todas) == 2 and len(sem["itens"]) == 1
