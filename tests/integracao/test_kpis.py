"""M5 no PostGIS real: métricas diárias, KPIs, preço, mapas e rotas legadas."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from sistemacampero.interfaces.worker import Worker
from tests.conftest import ACEITE
from tests.integracao.apoio import Conn, drenar, um, upload, zipar
from tests.sinteticos.gen4 import gjson_boundary, masterdata_xml
from tests.sinteticos.jdl_builder import START_MS, Cenario
from tests.sinteticos.jdl_builder import construir as construir_jdl

pytestmark = pytest.mark.integracao

DIA = "2026-04-30"  # START_MS = 30/04/2026 10:12 UTC (07:12 em Brasília)


def _kpi(client: TestClient, org: dict[str, Any], rota: str, **params: Any) -> Any:
    resp = client.get(f"/api/v1/{rota}", params=params, headers=org["auth"])
    assert resp.status_code == 200, resp.text
    return resp.json()


def _diarias(admin: Conn, org: dict[str, Any]) -> list[dict[str, Any]]:
    return admin.execute(
        "select d.dia::text as dia, t.nome as talhao, d.sessoes, d.motor_h, d.litros, d.area_ha,"
        " d.distancia_km from public.metricas_diarias d left join public.talhoes t on t.id = d.talhao_id"
        " where d.organizacao_id = %s order by d.dia, t.nome nulls last",
        (org["id"],),
    ).fetchall()


def test_diarias_batem_com_as_sessoes(
    client: TestClient, worker: Worker, org: dict[str, Any], admin: Conn
) -> None:
    upload(client, org, construir_jdl(Cenario(minutos=30)))
    upload(
        client,
        org,
        construir_jdl(Cenario(minutos=20, start_ms=START_MS + 3 * 3600_000, lat0=-28.2)),
    )
    drenar(worker)
    sessao = admin.execute(
        "select sum(motor_h) as motor_h, sum(litros_integral) as litros,"
        " sum(coalesce(area_cobertura_ha, area_estimada_ha)) as area"
        " from public.metricas_sessao where organizacao_id = %s and vigente",
        (org["id"],),
    ).fetchone()
    d = _diarias(admin, org)
    assert [x["dia"] for x in d] == [DIA]
    assert d[0]["sessoes"] == 2
    assert sum(x["motor_h"] for x in d) == pytest.approx(sessao["motor_h"], rel=1e-6)
    assert sum(x["litros"] for x in d) == pytest.approx(sessao["litros"], rel=1e-6)
    assert sum(x["area_ha"] for x in d) == pytest.approx(sessao["area"], rel=1e-6)


def test_sessao_que_vira_a_meia_noite_local_e_repartida(
    client: TestClient, worker: Worker, org: dict[str, Any], admin: Conn
) -> None:
    # 02:50 UTC = 23:50 em Brasília: 10 min num dia, 10 min no outro.
    inicio = 1_777_517_400_000  # 2026-04-30 02:50:00 UTC
    upload(client, org, construir_jdl(Cenario(minutos=20, start_ms=inicio)))
    drenar(worker)
    d = _diarias(admin, org)
    assert [x["dia"] for x in d] == ["2026-04-29", "2026-04-30"]
    assert d[0]["motor_h"] == pytest.approx(10 / 60, abs=0.01)
    assert d[1]["motor_h"] == pytest.approx(10 / 60, abs=0.01)
    assert d[0]["area_ha"] == pytest.approx(d[1]["area_ha"], rel=0.05)
    assert d[0]["sessoes"] == d[1]["sessoes"] == 1
    assert _kpi(client, org, "kpis/resumo")["sessoes"] == 1  # a sessão conta uma vez


def test_sessao_em_dois_talhoes_reparte_por_talhao_do_ponto(
    client: TestClient, worker: Worker, org: dict[str, Any], admin: Conn
) -> None:
    # Contorno só até -28.095: o trator sai dele depois de ~550 m (4 min de 15).
    curto = [
        [-52.93, -28.11],
        [-52.91, -28.11],
        [-52.91, -28.095],
        [-52.93, -28.095],
        [-52.93, -28.11],
    ]
    upload(
        client,
        org,
        zipar(
            {
                "Gen4/MasterData.xml": masterdata_xml(),
                "Gen4/SpatialFiles/Boundary{b1}.gjson": gjson_boundary(curto),
                "log/s.jdl": construir_jdl(Cenario(minutos=15)),
            }
        ),
        nome="p.zip",
    )
    drenar(worker)
    d = {x["talhao"]: x for x in _diarias(admin, org)}
    assert set(d) == {"Talhao Teste", None}
    total = d["Talhao Teste"]["distancia_km"] + d[None]["distancia_km"]
    assert d["Talhao Teste"]["distancia_km"] / total == pytest.approx(0.55 / 2.0, abs=0.03)
    assert d["Talhao Teste"]["area_ha"] / (
        d["Talhao Teste"]["area_ha"] + d[None]["area_ha"]
    ) == pytest.approx(d["Talhao Teste"]["distancia_km"] / total, rel=1e-6)
    ranking = _kpi(client, org, "kpis/ranking", por="talhao")
    assert {r["nome"] for r in ranking} == {"Talhao Teste", "(sem talhão)"}

    # Correção manual: a operação inteira passa para o talhão escolhido, inclusive no ranking.
    novo = client.post("/api/v1/talhoes", json={"nome": "Corrigido"}, headers=org["auth"]).json()
    sessao = client.get("/api/v1/sessions", headers=org["auth"]).json()["itens"][0]["id"]
    r = client.patch(
        f"/api/v1/sessions/{sessao}", json={"talhao_id": novo["id"]}, headers=org["auth"]
    )
    assert r.status_code == 200, r.text
    drenar(worker)
    assert {x["talhao"] for x in _diarias(admin, org)} == {"Corrigido"}
    assert {r["nome"] for r in _kpi(client, org, "kpis/ranking", por="talhao")} == {"Corrigido"}


def test_resumo_custo_e_preco_do_combustivel(
    client: TestClient, worker: Worker, org: dict[str, Any]
) -> None:
    precos = _kpi(client, org, "precos-combustivel")
    assert [(p["tipo"], p["preco_rs_l"], p["fonte"]) for p in precos] == [("S10", 6.59, "anp")]

    upload(client, org, construir_jdl(Cenario(minutos=30)))
    drenar(worker)
    r = _kpi(client, org, "kpis/resumo")
    assert r["sessoes"] == 1 and r["maquinas"] == 1
    assert r["litros"] == pytest.approx(11.0, rel=0.01)
    assert r["custo_rs"] == pytest.approx(r["litros"] * 6.59, rel=1e-6)
    assert r["rs_ha"] == pytest.approx(r["custo_rs"] / r["area_ha"])
    assert r["l_ha"] == pytest.approx(r["litros"] / r["area_ha"])
    assert (r["primeiro_dia"], r["ultimo_dia"]) == (DIA, DIA)

    # Preço da nota a partir do dia da sessão: o custo passa a usá-lo.
    novo = client.post(
        "/api/v1/precos-combustivel",
        json={"preco_rs_l": 6.0, "valido_de": DIA},
        headers=org["auth"],
    )
    assert novo.status_code == 201
    assert _kpi(client, org, "kpis/resumo")["custo_rs"] == pytest.approx(
        r["litros"] * 6.0, rel=1e-6
    )
    antigo = [p for p in _kpi(client, org, "precos-combustivel") if p["fonte"] == "anp"][0]
    assert antigo["valido_ate"] == DIA
    repetido = client.post(
        "/api/v1/precos-combustivel",
        json={"preco_rs_l": 5.0, "valido_de": "2026-01-01"},
        headers=org["auth"],
    )
    assert repetido.status_code == 409 and repetido.json()["code"] == "PRECO_SOBREPOSTO"


def test_series_ranking_safras(client: TestClient, worker: Worker, org: dict[str, Any]) -> None:
    upload(client, org, construir_jdl(Cenario(minutos=30, plantio=True)))
    upload(
        client,
        org,
        construir_jdl(Cenario(minutos=30, serial="OUTRA", start_ms=START_MS + 86_400_000 * 80)),
    )
    drenar(worker)
    dias = _kpi(client, org, "kpis/series", granularidade="dia")
    assert [x["periodo"] for x in dias] == [DIA, "2026-07-19"]
    meses = _kpi(client, org, "kpis/series", granularidade="mes")
    assert [x["periodo"] for x in meses] == ["2026-04-01", "2026-07-01"]
    horas = _kpi(client, org, "kpis/series", granularidade="hora", inicio=DIA, fim=DIA)
    assert len(horas) == 1  # 07:12-07:42 em Brasília: uma hora só
    assert horas[0]["motor_h"] == pytest.approx(0.5, abs=0.01)
    longe = client.get("/api/v1/kpis/series", params={"granularidade": "hora"}, headers=org["auth"])
    assert longe.status_code == 422 and longe.json()["code"] == "PERIODO_INVALIDO"

    maquinas = _kpi(client, org, "kpis/ranking", por="maquina")
    assert {m["nome"] for m in maquinas} == {"SINTETICO0001", "OUTRA"}
    operacoes = {o["nome"] for o in _kpi(client, org, "kpis/ranking", por="operacao")}
    assert operacoes == {"plantio", "(não informada)"}

    safras = _kpi(client, org, "kpis/safras")
    assert [s["safra"] for s in safras] == ["2025/26", "2026/27"]  # safra começa em julho
    assert _kpi(client, org, "kpis/safras", comparar="2026/27")[0]["inicio"] == "2026-07-01"
    filtrado = _kpi(client, org, "kpis/resumo", inicio="2026-07-01", fim="2026-12-31")
    assert filtrado["sessoes"] == 1 and filtrado["maquinas"] == 1


def test_trajeto_e_mapa_de_calor(
    client: TestClient, worker: Worker, org: dict[str, Any], admin: Conn
) -> None:
    upload(client, org, construir_jdl(Cenario(minutos=30)))
    drenar(worker)
    sessao = um(
        admin, "select id from public.sessoes_trabalho where organizacao_id = %s", org["id"]
    )
    fc = _kpi(client, org, f"sessions/{sessao}/track", max_pontos=200)
    linhas = [f for f in fc["features"] if f["geometry"]["type"] == "LineString"]
    assert linhas and all(f["properties"]["tipo"] == "trabalho" for f in linhas)
    assert sum(len(f["geometry"]["coordinates"]) for f in linhas) <= 200
    assert fc["properties"]["pontos_originais"] > 1700

    calor = _kpi(client, org, "mapas/calor", inicio=DIA, fim=DIA, tamanho_m=100)
    assert calor["features"]
    assert calor["properties"]["l_ha_p50"] == pytest.approx(22 / (8 * 4.95 / 10), rel=0.02)
    sem_periodo = client.get("/api/v1/mapas/calor", headers=org["auth"])
    assert sem_periodo.status_code == 422


# ------------------------------------------------------------------- contrato legado
def test_upload_com_campo_antigo_file(
    client: TestClient, worker: Worker, org: dict[str, Any]
) -> None:
    resp = client.post(
        "/api/v1/telemetry/upload",
        params={"marca": "John Deere", "tecnologia": "Gen4"},
        files={
            "file": ("antigo.jdl", construir_jdl(Cenario(minutos=2)), "application/octet-stream")
        },
        headers=org["auth"],
    )
    assert resp.status_code == 202, resp.text
    corpo = resp.json()
    assert (corpo["arquivo"], corpo["marca"], corpo["tecnologia"]) == (
        "antigo.jdl",
        "John Deere",
        "Gen4",
    )
    assert corpo["job_id"]
    vazio = client.post("/api/v1/telemetry/upload", headers=org["auth"])
    assert vazio.status_code == 422


def test_rotas_legadas_de_telemetria(
    client: TestClient, worker: Worker, org: dict[str, Any]
) -> None:
    upload(client, org, construir_jdl(Cenario(minutos=10)))
    drenar(worker)
    primeira = client.get(
        "/api/v1/telemetry/machine/SINTETICO0001", params={"limit": 300}, headers=org["auth"]
    )
    assert primeira.status_code == 200
    pontos = primeira.json()
    assert len(pontos) == 300 and set(pontos[0]) == {
        "timestamp",
        "latitude",
        "longitude",
        "speed_kmh",
        "fuel_rate_lph",
        "engine_rpm",
        "engine_on",
    }
    vistos = len(pontos)
    cursor = primeira.headers.get("x-next-cursor")
    while cursor:
        r = client.get(
            "/api/v1/telemetry/machine/SINTETICO0001",
            params={"limit": 300, "cursor": cursor},
            headers=org["auth"],
        )
        vistos += len(r.json())
        cursor = r.headers.get("x-next-cursor")
    assert vistos == 601  # 10 min a 1 Hz (inclusive)

    a_cada_10 = client.get(
        "/api/v1/telemetry/machine/SINTETICO0001",
        params={"passo_s": 10, "limit": 5000},
        headers=org["auth"],
    ).json()
    assert 59 <= len(a_cada_10) <= 61
    assert client.get("/api/v1/telemetry/machine/NAOEXISTE", headers=org["auth"]).status_code == 404

    stats = client.get("/api/v1/telemetry/stats/SINTETICO0001", headers=org["auth"]).json()
    assert {
        "machine_serial",
        "sessoes",
        "horas_motor",
        "horas_trabalho",
        "horas_ociosas",
        "percentual_ociosidade",
        "litros_total",
        "consumo_medio_lph",
        "area_trabalhada_ha",
        "litros_por_ha",
    } <= set(stats)
    assert stats["consumo_medio_lph"] == pytest.approx(22.0, abs=0.1)
    assert client.get("/api/v1/telemetry/stats/NAOEXISTE", headers=org["auth"]).status_code == 404


def test_kpis_isolados_por_organizacao(
    client: TestClient, worker: Worker, org: dict[str, Any], admin: Conn
) -> None:
    from tests.conftest import emitir_token
    from tests.integracao.apoio import criar_usuario

    upload(client, org, construir_jdl(Cenario(minutos=10)))
    drenar(worker)
    uid = criar_usuario(admin)
    h = {"Authorization": f"Bearer {emitir_token(uid)}"}
    client.post("/api/v1/organizacoes", json={"nome": "Vizinha Kpi", **ACEITE}, headers=h)
    assert client.get("/api/v1/kpis/resumo", headers=h).json()["sessoes"] == 0
    assert client.get("/api/v1/telemetry/machine/SINTETICO0001", headers=h).status_code == 404
