"""Pasta do GreenStar 3 (colheitadeira) dentro do .zip do pendrive, no PostGIS real."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from sistemacampero.interfaces.worker import Worker
from tests.integracao.apoio import Conn, drenar, upload, zipar
from tests.sinteticos import gs3

pytestmark = pytest.mark.integracao
PASTA = "GS3_2630/Cliente/RCD/EIC/Documentation/a1"


def test_par_fdl_fdd_vira_operacao_de_colheita(
    client: TestClient, worker: Worker, org: dict[str, Any], admin: Conn
) -> None:
    h = org["auth"]
    pacote = {
        f"{PASTA}/6363bd9a.fdl": gs3.construir_fdl(),
        f"{PASTA}/6363bd9a.fdd": gs3.construir_fdd(gs3.CenarioGs3(minutos=20)),
        f"{PASTA}/sozinho.fdd": b"sem o .fdl correspondente",  # metade órfã: ignorada
        "GS3_2630/Cliente/RCD/EIC/Documentation/a1/6363bd9a.fdr": b"ignorado",
    }
    upload(client, org, zipar(pacote), nome="pendrive.zip")
    drenar(worker)

    sessoes = client.get("/api/v1/sessions", headers=h).json()["itens"]
    assert len(sessoes) == 1
    s = sessoes[0]
    assert s["operacao"] == "colheita"
    assert s["motor_h"] == pytest.approx(20 / 60, abs=0.02)
    assert s["litros_integral"] == pytest.approx(22 * 20 / 60, rel=0.05)
    maquina = admin.execute(
        "select serial, modelo from public.maquinas where organizacao_id = %s", (org["id"],)
    ).fetchone()
    assert maquina is not None and maquina["serial"] == "1CQS540ATG0000001"
    arquivo = admin.execute(
        "select tipo, tecnologia from public.arquivos_brutos"
        " where organizacao_id = %s and tipo = 'rcd'",
        (org["id"],),
    ).fetchone()
    assert arquivo is not None and arquivo["tecnologia"] == "gs3"


def test_fdd_avulso_e_recusado_com_orientacao(client: TestClient, org: dict[str, Any]) -> None:
    r = client.post(
        "/api/v1/telemetry/upload",
        files={"arquivo": ("x.fdd", b"\x01\x00", "application/octet-stream")},
        headers=org["auth"],
    )
    assert r.status_code == 422 and "GS3_2630" in r.json()["detail"]


def test_visao_por_maquina_separa_trator_e_colheitadeira(
    client: TestClient, worker: Worker, org: dict[str, Any]
) -> None:
    from tests.sinteticos.jdl_builder import Cenario
    from tests.sinteticos.jdl_builder import construir as construir_jdl

    h = org["auth"]
    pacote = {
        f"{PASTA}/6363bd9a.fdl": gs3.construir_fdl(),
        f"{PASTA}/6363bd9a.fdd": gs3.construir_fdd(gs3.CenarioGs3(minutos=30, massa_kg_s=4.0)),
    }
    upload(client, org, zipar(pacote), nome="colheitadeira.zip")
    upload(client, org, construir_jdl(Cenario(minutos=20)), nome="trator.jdl")
    drenar(worker)

    visao = {m["tipo"]: m for m in client.get("/api/v1/maquinas/visao", headers=h).json()}
    assert set(visao) == {"trator", "colheitadeira"}
    colhe = visao["colheitadeira"]
    assert colhe["modelo"] == "S540"
    # massa seca: 17,5 % de umidade descontada até os 14 % da soja
    assert colhe["massa_kg"] == pytest.approx(4.0 * 30 * 60 * 82.5 / 86, rel=0.01)
    assert colhe["motor_h"] == pytest.approx(0.5, abs=0.02)
    assert colhe["t_ha"] and colhe["t_ha"] > 0
    assert visao["trator"]["massa_kg"] is None


def test_talhao_com_safra_no_nome_cai_na_lavoura_que_ja_existe(
    client: TestClient, worker: Worker, org: dict[str, Any], admin: Conn
) -> None:
    h = org["auth"]
    existente = client.post("/api/v1/talhoes", json={"nome": "Talhão Teste"}, headers=h).json()
    pacote = {
        f"{PASTA}/6363bd9a.fdl": gs3.construir_fdl().replace(
            b"Talhao Teste", b"TalhaoTeste_Soja22"
        ),
        f"{PASTA}/6363bd9a.fdd": gs3.construir_fdd(gs3.CenarioGs3(minutos=5)),
    }
    upload(client, org, zipar(pacote), nome="colheitadeira.zip")
    drenar(worker)

    ativos = client.get("/api/v1/talhoes", params={"ativo": True}, headers=h).json()
    assert [t["nome"] for t in ativos] == ["Talhão Teste"]
    sessao = admin.execute(
        "select talhao_monitor_id from public.sessoes_trabalho where organizacao_id = %s",
        (org["id"],),
    ).fetchone()
    assert sessao is not None and str(sessao["talhao_monitor_id"]) == existente["id"]


def test_agrupar_junta_os_repetidos_sem_apagar(client: TestClient, org: dict[str, Any]) -> None:
    h = org["auth"]
    for nome in ("Mãe", "Mae_Aveia22", "Mae", "Bira", "Coxilha Grande", "CoxilhaGrand_Trigo22"):
        assert client.post("/api/v1/talhoes", json={"nome": nome}, headers=h).status_code == 201
    r = client.post("/api/v1/talhoes/agrupar", headers=h).json()
    assert (r["grupos"], r["talhoes_agrupados"], r["talhoes_ativos"]) == (2, 3, 3)
    ativos = sorted(
        t["nome"] for t in client.get("/api/v1/talhoes", params={"ativo": True}, headers=h).json()
    )
    assert ativos == ["Bira", "Coxilha Grande", "Mãe"]
    assert len(client.get("/api/v1/talhoes", headers=h).json()) == 6  # nada apagado


def test_fechamento_da_safra_por_talhao(
    client: TestClient, worker: Worker, org: dict[str, Any]
) -> None:
    h = org["auth"]
    # Talhão cobrindo a trilha sintética (anda para o norte a partir de -28,1 / -52,9)
    contorno = [
        [-52.91, -28.11],
        [-52.89, -28.11],
        [-52.89, -28.0],
        [-52.91, -28.0],
        [-52.91, -28.11],
    ]
    t = client.post(
        "/api/v1/talhoes",
        json={"nome": "Lavoura Norte", "geometria": {"type": "Polygon", "coordinates": [contorno]}},
        headers=h,
    ).json()
    pacote = {
        f"{PASTA}/6363bd9a.fdl": gs3.construir_fdl(),
        f"{PASTA}/6363bd9a.fdd": gs3.construir_fdd(gs3.CenarioGs3(minutos=30, massa_kg_s=4.0)),
    }
    upload(client, org, zipar(pacote), nome="colheitadeira.zip")
    drenar(worker)

    safras = client.get("/api/v1/safras", headers=h).json()
    assert [(s["safra"], s["cultura"]) for s in safras] == [("2025/26", "soja")]
    f = client.get(
        "/api/v1/safras/fechamento", params={"safra": "2025/26", "cultura": "soja"}, headers=h
    ).json()
    [talhao] = f["talhoes"]
    assert talhao["talhao_id"] == t["id"] and talhao["variedades"] == ["Zeus"]
    area = 8 / 3.6 * 30 * 60 * 7.6 / 10_000  # 8 km/h por 30 min com 7,6 m
    sacas = 4.0 * 30 * 60 * 82.5 / 86 / 60
    assert talhao["area_colhida_ha"] == pytest.approx(area, rel=0.02)
    assert talhao["sc_ha"] == pytest.approx(sacas / area, rel=0.03)
    assert talhao["litros"] == pytest.approx(22 * 0.5, rel=0.05)
    assert talhao["operacoes_maquina"][0]["operacao"] == "colheita"
    assert f["sacas"] == pytest.approx(sacas, rel=0.01)

    nada = client.get("/api/v1/safras/fechamento", params={"safra": "1999/00"}, headers=h)
    assert nada.status_code == 404


def test_reprocessar_inclui_a_colheitadeira(
    client: TestClient, worker: Worker, org: dict[str, Any]
) -> None:
    pacote = {
        f"{PASTA}/x.fdl": gs3.construir_fdl(),
        f"{PASTA}/x.fdd": gs3.construir_fdd(gs3.CenarioGs3(minutos=5)),
    }
    upload(client, org, zipar(pacote), nome="colheitadeira.zip")
    drenar(worker)
    r = client.post("/api/v1/analysis/run", headers=org["auth"]).json()
    assert r["sessoes_reenfileiradas"] == 1
