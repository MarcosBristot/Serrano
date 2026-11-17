"""Resumo da semana: o texto que vai para o produtor (WhatsApp, e-mail ou webhook)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sistemacampero.interfaces.worker import Worker
from tests.integracao.apoio import drenar, upload
from tests.sinteticos.jdl_builder import START_MS, Cenario
from tests.sinteticos.jdl_builder import construir as construir_jdl

pytestmark = pytest.mark.integracao


def test_texto_da_semana_com_numeros_e_a_acao(
    client: TestClient, worker: Worker, org: dict[str, Any]
) -> None:
    h = org["auth"]
    upload(client, org, construir_jdl(Cenario(minutos=90, horimetro0=740.0)), nome="s.jdl")
    drenar(worker)
    trator = client.get("/api/v1/maquinas/visao", headers=h).json()[0]
    base = f"/api/v1/maquinas/{trator['id']}"
    client.post(f"{base}/manutencao/modelo", json={"tipo": "trator"}, headers=h)
    oleo = next(
        p
        for p in client.get(f"{base}/manutencao", headers=h).json()["planos"]
        if p["nome"].startswith("Óleo e filtro")
    )
    client.post(
        f"/api/v1/manutencao/planos/{oleo['id']}/feita",
        json={"horimetro_h": 480, "feita_em": "2026-01-10"},
        headers=h,
    )

    dia = datetime.fromtimestamp(START_MS / 1000, UTC).date()
    r = client.get("/api/v1/resumo-semanal", params={"fim": dia.isoformat()}, headers=h).json()
    assert r["trabalho_h"] > 1 and r["litros"] > 0
    texto = r["texto"]
    assert texto.startswith("🌾 *Serrano ·") and "h trabalhando" in texto
    assert "Para esta semana" in texto and "óleo e filtro do motor vencida" in texto
