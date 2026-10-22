"""M8 no PostGIS real: exportação CSV/XLSX e relatório de qualidade."""

from __future__ import annotations

import csv
import io
import zipfile
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sistemacampero.infrastructure.container import Container
from sistemacampero.interfaces.worker import Worker
from tests.integracao.apoio import Conn, drenar, upload
from tests.sinteticos.jdl_builder import Cenario
from tests.sinteticos.jdl_builder import construir as construir_jdl

pytestmark = pytest.mark.integracao
DIA = "2026-04-30"


@pytest.fixture
def com_dados(client: TestClient, worker: Worker, org: dict[str, Any]) -> dict[str, Any]:
    upload(client, org, construir_jdl(Cenario(minutos=30)))
    upload(client, org, construir_jdl(Cenario(minutos=0.5, lat0=-28.3)))  # fragmento
    upload(client, org, construir_jdl(Cenario(minutos=1, so_cabecalho=True)))  # vazio
    drenar(worker)
    return org


def test_csv_em_streaming_para_excel(client: TestClient, com_dados: dict[str, Any]) -> None:
    r = client.get("/api/v1/exportacoes/csv", params={"tipo": "sessoes"}, headers=com_dados["auth"])
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    texto = r.content.decode("utf-8")
    assert texto.startswith("﻿")
    linhas = list(csv.reader(io.StringIO(texto.lstrip("﻿")), delimiter=";"))
    assert linhas[0][:3] == ["sessao_id", "maquina_serial", "maquina_apelido"]
    assert len(linhas) == 3  # cabeçalho + 2 sessões
    idx = linhas[0].index("litros_integral")
    assert any("," in linha[idx] for linha in linhas[1:])  # vírgula decimal

    rfc = client.get(
        "/api/v1/exportacoes/csv",
        params={"tipo": "diarias", "padrao": "rfc4180"},
        headers=com_dados["auth"],
    ).content.decode()
    assert rfc.splitlines()[0].startswith("dia,maquina_serial")
    tel = client.get(
        "/api/v1/exportacoes/csv", params={"tipo": "telemetria"}, headers=com_dados["auth"]
    )
    assert tel.status_code == 422 and tel.json()["code"] == "PERIODO_INVALIDO"
    tel = client.get(
        "/api/v1/exportacoes/csv",
        params={"tipo": "telemetria", "inicio": DIA, "fim": DIA},
        headers=com_dados["auth"],
    )
    assert tel.status_code == 200 and len(tel.content.decode().splitlines()) > 1800


def test_xlsx_assincrono_com_link(
    client: TestClient, worker: Worker, com_dados: dict[str, Any], container: Container, admin: Conn
) -> None:
    h = com_dados["auth"]
    r = client.post("/api/v1/exportacoes", json={"tipo": "sessoes", "formato": "xlsx"}, headers=h)
    assert r.status_code == 202 and r.json()["status"] == "pendente"
    drenar(worker)
    e = client.get(f"/api/v1/exportacoes/{r.json()['id']}", headers=h).json()
    assert (
        e["status"] == "concluida"
        and e["linhas"] == 2
        and e["url"].startswith("local://exportacoes/")
    )
    caminho = e["url"].split("local://exportacoes/")[1].split("?")[0]
    conteudo = container.exportacao._storage.ler("exportacoes", caminho)  # type: ignore[union-attr]
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:  # xlsx = zip OOXML
        assert "xl/worksheets/sheet1.xml" in z.namelist()

    # Vencida: o worker apaga do Storage e marca expirada.
    admin.execute(
        "update public.exportacoes set expira_em = now() - interval '1 day' where id = %s",
        (r.json()["id"],),
    )
    assert container.exportacao is not None and container.exportacao.limpar_vencidas() == 1
    assert (
        client.get(f"/api/v1/exportacoes/{r.json()['id']}", headers=h).json()["status"]
        == "expirada"
    )
    assert not container.exportacao._storage.existe("exportacoes", caminho)


def test_relatorio_de_qualidade(client: TestClient, com_dados: dict[str, Any]) -> None:
    r = client.get("/api/v1/qualidade/relatorio", headers=com_dados["auth"]).json()
    assert r["sessoes"]["total"] == 2 and r["sessoes"]["fragmentos"] == 1
    vazio = next(a for a in r["arquivos"] if a["status"] == "vazio")
    assert vazio["motivo"] == "sem_blocos_de_dados" and vazio["explicacao"]
    curta = next(p for p in r["problemas"] if p["codigo"] == "SESSAO_CURTA")
    assert curta["n"] == 1 and "2 minutos" in curta["explicacao"]
    assert r["maquinas"][0]["serial"] == "SINTETICO0001" and r["maquinas"][0]["sessoes"] == 2
