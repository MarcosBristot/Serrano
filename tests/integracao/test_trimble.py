"""Pendrive do monitor Trimble TMX-2050 (Massey Ferguson), no PostGIS real."""

from __future__ import annotations

import io
import zipfile
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sistemacampero.interfaces.worker import Worker
from tests.integracao.apoio import Conn, drenar, upload, zipar
from tests.sinteticos import trimble

pytestmark = pytest.mark.integracao
PASTA = "Trator Massey - Irmaos Berwig"


def _agv(nome: str) -> bytes:
    """Perfil de veículo do monitor: zip com manifest.xml aberto e o resto criptografado."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "manifest.xml",
            f'<?xml version="1.0" encoding="UTF-8"?><manifest><name>{nome}</name>'
            "<source><product>TMX</product></source></manifest>",
        )
        z.writestr("b89d28fb.xml.gz.enc", b"\x8f\x02conteudo criptografado")
    return buf.getvalue()


def test_pendrive_trimble_vira_operacao_da_massey(
    client: TestClient, worker: Worker, org: dict[str, Any], admin: Conn
) -> None:
    h = org["auth"]
    pacote = {
        f"{PASTA}/AgData/Vehicles/Massey Ferguson  7725.agv": _agv("Massey Ferguson  7725"),
        f"{PASTA}/AgData/Vehicles/Massey Ferguson 7700 7725.agv": _agv("Massey Ferguson 7700 7725"),
        f"{PASTA}/AgData/Tasks/9d10dd39.agt": b"PK\x03\x04criptografado",
        f"{PASTA}/Diagnostics/TMX_LogAg_6435439113_20261111_1500_001.tsip": trimble.construir(
            trimble.CenarioTrimble(minutos=20)
        ),
        f"{PASTA}/Diagnostics/farmStream.log": b"16Nov26 20:20:09 - Refreshing auth token..",
    }
    r = upload(client, org, zipar(pacote), nome="Trator Massey.zip")
    drenar(worker)
    job = client.get(f"/api/v1/jobs/{r['job_id']}", headers=h).json()
    assert job["progresso"]["resultado"]["tsip"] == 1

    sessoes = client.get("/api/v1/sessions", headers=h).json()["itens"]
    assert len(sessoes) == 1
    s = sessoes[0]
    assert s["motor_h"] == pytest.approx(20 / 60, abs=0.02)
    maquina = admin.execute(
        "select serial, modelo from public.maquinas where organizacao_id = %s", (org["id"],)
    ).fetchone()
    assert maquina is not None
    assert maquina["serial"] == "trimble-6435439113"
    assert maquina["modelo"] == "Massey Ferguson 7725"
    integ = {i["id"]: i for i in client.get("/api/v1/integracoes", headers=h).json()}
    assert integ["trimble_tmx"]["em_uso"] and integ["trimble_tmx"]["maquinas"] == 1


def test_zip_sem_formato_conhecido_explica_o_que_achou(
    client: TestClient, worker: Worker, org: dict[str, Any]
) -> None:
    pacote = {
        "pendrive/IntelliView/dados.cn1": b"\x00\x01binario",
        "pendrive/IntelliView/mapa.vy1": b"\x00\x02binario",
        "pendrive/leia-me.txt": b"oi",
    }
    r = upload(client, org, zipar(pacote), nome="pendrive.zip")
    drenar(worker)
    res = client.get(f"/api/v1/jobs/{r['job_id']}", headers=org["auth"]).json()["progresso"][
        "resultado"
    ]
    assert res["status"] == "rejeitado"
    assert res["motivo"].startswith("formato_ainda_nao_suportado")
    assert "Case IH / New Holland" in res["motivo"]
