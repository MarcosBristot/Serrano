"""Manutenção pelo horímetro: do monitor (trator) ou informado (colheitadeira)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from sistemacampero.interfaces.worker import Worker
from tests.integracao.apoio import drenar, upload, zipar
from tests.sinteticos import gs3
from tests.sinteticos.jdl_builder import Cenario
from tests.sinteticos.jdl_builder import construir as construir_jdl

pytestmark = pytest.mark.integracao


def _maquinas(client: TestClient, h: dict[str, str]) -> dict[str, dict[str, Any]]:
    return {m["tipo"]: m for m in client.get("/api/v1/maquinas/visao", headers=h).json()}


def test_trator_usa_o_horimetro_do_monitor_e_avisa_o_vencimento(
    client: TestClient, worker: Worker, org: dict[str, Any]
) -> None:
    h = org["auth"]
    upload(client, org, construir_jdl(Cenario(minutos=60, horimetro0=740.0)), nome="s.jdl")
    drenar(worker)
    trator = _maquinas(client, h)["trator"]
    base = f"/api/v1/maquinas/{trator['id']}"

    r = client.post(f"{base}/manutencao/modelo", json={"tipo": "trator"}, headers=h).json()
    assert r["criados"] == 4
    s = client.get(f"{base}/manutencao", headers=h).json()
    assert s["fonte"] == "monitor" and s["horimetro_h"] == pytest.approx(741.0, abs=0.1)
    assert all(p["situacao"] == "em_dia" for p in s["planos"])

    # A troca de óleo foi feita com 500 h: vence em 750 h, 9 h depois do horímetro atual.
    oleo = next(p for p in s["planos"] if p["nome"].startswith("Óleo e filtro do motor"))
    feita = {"horimetro_h": 500, "feita_em": "2026-01-10", "custo_rs": 1850.0}
    assert (
        client.post(
            f"/api/v1/manutencao/planos/{oleo['id']}/feita", json=feita, headers=h
        ).status_code
        == 204
    )
    s = client.get(f"{base}/manutencao", headers=h).json()
    assert s["planos"][0]["nome"] == oleo["nome"] and s["planos"][0]["situacao"] == "proxima"
    assert s["planos"][0]["faltam_h"] == pytest.approx(9.0, abs=0.2)
    assert s["historico"][0]["custo_rs"] == 1850.0

    [pend] = client.get("/api/v1/manutencao/pendencias", headers=h).json()
    assert (pend["maquina_id"], pend["nome"], pend["situacao"]) == (
        trator["id"],
        oleo["nome"],
        "proxima",
    )


def test_colheitadeira_sem_horimetro_soma_as_horas_depois_do_informado(
    client: TestClient, worker: Worker, org: dict[str, Any]
) -> None:
    h = org["auth"]
    colhe_id = None
    pasta = "GS3_2630/Cliente/RCD/EIC/Documentation/a1"
    pacote = {
        f"{pasta}/x.fdl": gs3.construir_fdl(),
        f"{pasta}/x.fdd": gs3.construir_fdd(gs3.CenarioGs3(minutos=30)),
    }
    upload(client, org, zipar(pacote), nome="colheitadeira.zip")
    drenar(worker)
    colhe_id = _maquinas(client, h)["colheitadeira"]["id"]
    base = f"/api/v1/maquinas/{colhe_id}"

    assert client.get(f"{base}/manutencao", headers=h).json()["horimetro_h"] is None
    assert client.put(f"{base}/horimetro", json={"horimetro_h": 2100}, headers=h).status_code == 204
    s = client.get(f"{base}/manutencao", headers=h).json()
    # A operação sintética é de 2026 (antes da leitura): nada a somar ainda.
    assert (s["fonte"], s["horimetro_h"]) == ("informado", 2100)
