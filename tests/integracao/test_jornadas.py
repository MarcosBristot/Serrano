"""Jornadas: arquivos do monitor agrupados como o produtor entende a operação."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from sistemacampero.interfaces.worker import Worker
from tests.integracao.apoio import drenar, upload
from tests.sinteticos.jdl_builder import START_MS, Cenario, constante
from tests.sinteticos.jdl_builder import construir as construir_jdl

pytestmark = pytest.mark.integracao
MIN = 60_000


def test_arquivos_proximos_viram_uma_jornada_sem_contar_duas_vezes(
    client: TestClient, worker: Worker, org: dict[str, Any]
) -> None:
    h = org["auth"]
    arquivos = [
        Cenario(minutos=10, start_ms=START_MS),  # 0-10 min
        Cenario(minutos=3, start_ms=START_MS + 4 * MIN),  # em paralelo com o primeiro
        Cenario(minutos=10, start_ms=START_MS + 12 * MIN),  # 2 min depois: mesma jornada
        Cenario(minutos=10, start_ms=START_MS + 120 * MIN),  # 2 h depois: outra jornada
    ]
    for i, c in enumerate(arquivos):
        upload(client, org, construir_jdl(c), nome=f"a{i}.jdl")
    drenar(worker)

    pagina = client.get("/api/v1/jornadas", headers=h).json()
    jornadas = sorted(pagina["itens"], key=lambda j: j["inicio"])
    assert [j["arquivos"] for j in jornadas] == [3, 1]
    primeira = jornadas[0]
    # Motor das duas metades (0-10 e 12-22 min), sem somar o arquivo paralelo de novo.
    assert primeira["motor_h"] == pytest.approx(20 / 60, abs=0.02)
    assert primeira["litros"] > 0 and primeira["curta"] is False

    detalhe = client.get(f"/api/v1/jornadas/{primeira['id']}", headers=h).json()
    assert len(detalhe["arquivos_detalhe"]) == 3
    trilha = client.get(f"/api/v1/jornadas/{primeira['id']}/track", headers=h).json()
    assert trilha["type"] == "FeatureCollection" and trilha["features"]

    # A soma das jornadas bate com o resumo do painel (mesma telemetria, sem duplicar).
    resumo = client.get("/api/v1/kpis/resumo", headers=h).json()
    assert sum(j["motor_h"] for j in jornadas) == pytest.approx(resumo["motor_h"], rel=1e-6)


def test_jornada_de_segundos_fica_escondida(
    client: TestClient, worker: Worker, org: dict[str, Any]
) -> None:
    upload(client, org, construir_jdl(Cenario(minutos=10, start_ms=START_MS)), nome="longo.jdl")
    # 18 s parado: liga, o monitor abre arquivo, desliga
    curto = Cenario(minutos=0.3, start_ms=START_MS + 300 * MIN, velocidade_kmh=constante(0.0))
    upload(client, org, construir_jdl(curto), nome="curto.jdl")
    drenar(worker)

    padrao = client.get("/api/v1/jornadas", headers=org["auth"]).json()["itens"]
    todas = client.get("/api/v1/jornadas", params={"curtas": True}, headers=org["auth"]).json()
    assert len(padrao) == 1 and len(todas["itens"]) == 2
    assert [j["curta"] for j in sorted(todas["itens"], key=lambda j: j["inicio"])] == [False, True]
