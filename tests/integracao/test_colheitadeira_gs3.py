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
