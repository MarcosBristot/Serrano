"""Pasta TASKDATA (ISOBUS) de outra marca no mesmo pendrive do trator John Deere."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from sistemacampero.interfaces.worker import Worker
from tests.integracao.apoio import Conn, drenar, upload, zipar
from tests.sinteticos import isoxml
from tests.sinteticos.jdl_builder import Cenario
from tests.sinteticos.jdl_builder import construir as construir_jdl

pytestmark = pytest.mark.integracao


def test_pulverizador_isobus_e_trator_jd_no_mesmo_pendrive(
    client: TestClient, worker: Worker, org: dict[str, Any], admin: Conn
) -> None:
    h = org["auth"]
    pacote = {
        "Pulverizador/TASKDATA/TASKDATA.XML": isoxml.taskdata(),
        "Pulverizador/TASKDATA/TLG00001.XML": isoxml.tlg_xml(),
        "Pulverizador/TASKDATA/TLG00001.BIN": isoxml.tlg_bin(isoxml.CenarioIso(minutos=20)),
        "Pulverizador/TASKDATA/TLG00002.XML": isoxml.tlg_xml(),  # sem o .BIN: ignorado
        "Trator/JD-Data/log/sessao.jdl": construir_jdl(Cenario(minutos=10)),
    }
    upload(client, org, zipar(pacote), nome="pendrive.zip")
    drenar(worker)

    visao = {m["tipo"]: m for m in client.get("/api/v1/maquinas/visao", headers=h).json()}
    assert set(visao) == {"trator", "pulverizador"}
    pulv = visao["pulverizador"]
    assert (pulv["serial"], pulv["fabricante"]) == ("STR3000123", "Stara Imperador 3.0")
    assert pulv["motor_h"] == pytest.approx(20 / 60, abs=0.02)
    assert pulv["litros"] == pytest.approx(22 * 20 / 60, rel=0.05)
    # 8 km/h x 20 min x 24 m de barra
    assert pulv["area_ha"] == pytest.approx(8 / 3.6 * 20 * 60 * 24 / 10_000, rel=0.05)
    talhoes = [
        t["nome"] for t in client.get("/api/v1/talhoes", params={"ativo": True}, headers=h).json()
    ]
    assert "Lavoura Norte" in talhoes
    arquivo = admin.execute(
        "select marca, tecnologia from public.arquivos_brutos where organizacao_id = %s"
        " and tipo = 'isoxml'",
        (org["id"],),
    ).fetchall()
    assert [(a["marca"], a["tecnologia"]) for a in arquivo] == [("isobus", "isoxml")]
