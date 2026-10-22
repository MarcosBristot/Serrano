"""M6 no PostGIS real: ciclo do alerta, regras por organização, linha de base e outbox."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from sistemacampero.application.alertas import ServicoNotificacoes
from sistemacampero.infrastructure.container import Container
from sistemacampero.interfaces.worker import Worker
from tests.integracao.apoio import Conn, drenar, um, upload
from tests.sinteticos.jdl_builder import START_MS, Cenario
from tests.sinteticos.jdl_builder import construir as construir_jdl

pytestmark = pytest.mark.integracao

PARADO = Cenario(
    minutos=25,
    velocidade_kmh=lambda _t: 0.0,
    vazao_lph=lambda _t: 3.2,
    rpm=lambda _t: 900,
    gps="nenhum",
)


def _alertas(client: TestClient, org: dict[str, Any], **p: Any) -> list[dict[str, Any]]:
    r = client.get("/api/v1/alerts", params=p, headers=org["auth"])
    assert r.status_code == 200, r.text
    return r.json()["itens"]  # type: ignore[no-any-return]


def test_ciclo_de_vida_e_comentarios(
    client: TestClient, worker: Worker, org: dict[str, Any]
) -> None:
    upload(client, org, construir_jdl(PARADO))
    drenar(worker)
    ocio = _alertas(client, org, tipo="ociosidade")
    assert len(ocio) == 1 and ocio[0]["status"] == "aberto" and ocio[0]["serial"] == "SINTETICO0001"
    aid, h = ocio[0]["id"], org["auth"]

    r = client.post(f"/api/v1/alerts/{aid}/reconhecer", headers=h).json()
    assert r["status"] == "reconhecido" and r["reconhecido_por"] == str(org["user"])
    errado = client.post(f"/api/v1/alerts/{aid}/reconhecer", headers=h)
    assert errado.status_code == 409 and errado.json()["code"] == "TRANSICAO_INVALIDA"
    assert client.post(f"/api/v1/alerts/{aid}/resolver", headers=h).json()["status"] == "resolvido"
    assert client.post(f"/api/v1/alerts/{aid}/reabrir", headers=h).json()["status"] == "aberto"

    c = client.post(
        f"/api/v1/alerts/{aid}/comentarios", json={"texto": "Operador almoçando."}, headers=h
    )
    assert c.status_code == 201
    detalhe = client.get(f"/api/v1/alerts/{aid}", headers=h).json()
    assert [x["texto"] for x in detalhe["comentarios"]] == ["Operador almoçando."]
    assert _alertas(client, org, status="aberto", tipo="ociosidade")[0]["id"] == aid


def test_regras_da_organizacao_e_reanalise(
    client: TestClient, worker: Worker, org: dict[str, Any]
) -> None:
    upload(client, org, construir_jdl(PARADO))
    drenar(worker)
    h = org["auth"]
    padrao = client.get("/api/v1/config/regras", headers=h).json()
    assert padrao["ociosidade_min_minutos"] == 20

    salvo = client.put(
        "/api/v1/config/regras", json={**padrao, "ociosidade_min_minutos": 30}, headers=h
    )
    assert salvo.status_code == 200 and salvo.json()["versao"] != padrao["versao"]
    ruim = client.put("/api/v1/config/regras", json={**padrao, "vazao_desvio": 50}, headers=h)
    assert ruim.status_code == 422 and ruim.json()["code"] == "CONFIG_REGRAS_INVALIDA"

    assert client.post("/api/v1/analysis/run", headers=h).json() == {"sessoes_reenfileiradas": 1}
    drenar(worker)
    ocio = _alertas(client, org, tipo="ociosidade")
    assert [a["status"] for a in ocio] == ["invalidado"]  # 25 min < 30: deixou de disparar


def test_l_ha_acima_da_linha_de_base(
    client: TestClient, worker: Worker, org: dict[str, Any]
) -> None:
    for i in range(5):
        upload(client, org, construir_jdl(Cenario(minutos=32, start_ms=START_MS + i * 86_400_000)))
    drenar(worker)
    assert _alertas(client, org, tipo="l_ha_alto") == []
    upload(
        client,
        org,
        construir_jdl(
            Cenario(minutos=32, vazao_lph=lambda _t: 33.0, start_ms=START_MS + 9 * 86_400_000)
        ),
    )
    drenar(worker)
    alto = _alertas(client, org, tipo="l_ha_alto")
    assert len(alto) == 1
    assert alto[0]["detalhes"]["sessoes_base"] == 5
    assert alto[0]["valor"] == pytest.approx(alto[0]["detalhes"]["linha_base_l_ha"] * 1.5, rel=0.03)
    # vazão em trabalho 50% acima da mediana: também dispara (janelas de 10 min)
    assert _alertas(client, org, tipo="vazao_alta")


class _Enviador:
    def __init__(self, falhar: bool = False) -> None:
        self.enviados: list[tuple[str, str]] = []
        self.falhar = falhar

    def enviar(self, alerta: dict[str, Any], destino: dict[str, Any]) -> None:
        if self.falhar:
            raise ConnectionError("smtp fora")
        self.enviados.append((alerta["tipo"], destino["destino"]))


def test_outbox_de_notificacoes(
    client: TestClient, worker: Worker, org: dict[str, Any], admin: Conn, container: Container
) -> None:
    h = org["auth"]
    http = client.post(
        "/api/v1/destinos-notificacao",
        json={"tipo": "webhook", "destino": "http://inseguro.example"},
        headers=h,
    )
    assert http.status_code == 422
    wh = client.post(
        "/api/v1/destinos-notificacao",
        json={
            "tipo": "webhook",
            "destino": "https://exemplo.invalid/hook",
            "segredo": "s" * 32,
            "severidade_minima": "atencao",
        },
        headers=h,
    )
    assert wh.status_code == 201 and wh.json()["tem_segredo"] is True
    client.post(
        "/api/v1/destinos-notificacao",
        json={"tipo": "email", "destino": "gestor@example.com", "severidade_minima": "alto"},
        headers=h,
    )
    cifrado = um(
        admin,
        "select segredo_cifrado from public.destinos_notificacao where tipo='webhook'"
        " and organizacao_id = %s",
        org["id"],
    )
    assert cifrado and "s" * 32 not in cifrado

    upload(client, org, construir_jdl(PARADO))  # ociosidade (atencao) + sem_gps (info)
    drenar(worker)
    pend = admin.execute(
        "select n.status, d.tipo from interno.notificacoes n join public.destinos_notificacao d"
        " on d.id = n.destino_id where n.organizacao_id = %s",
        (org["id"],),
    ).fetchall()
    assert [(p["status"], p["tipo"]) for p in pend] == [("pendente", "webhook")]

    assert container.repo_alertas is not None
    falha = ServicoNotificacoes(container.repo_alertas, _Enviador(falhar=True))
    assert falha.enviar_pendentes() == 1
    assert (
        um(admin, "select status from interno.notificacoes where organizacao_id = %s", org["id"])
        == "erro"
    )
    admin.execute(
        "update interno.notificacoes set proxima_tentativa = now() where organizacao_id = %s",
        (org["id"],),
    )
    ok = _Enviador()
    ServicoNotificacoes(container.repo_alertas, ok).enviar_pendentes()
    assert ok.enviados == [("ociosidade", "https://exemplo.invalid/hook")]
    assert (
        um(admin, "select status from interno.notificacoes where organizacao_id = %s", org["id"])
        == "enviada"
    )

    # Reprocessar não renotifica.
    client.post("/api/v1/analysis/run", headers=h)
    drenar(worker)
    assert (
        um(admin, "select count(*) from interno.notificacoes where organizacao_id = %s", org["id"])
        == 1
    )
