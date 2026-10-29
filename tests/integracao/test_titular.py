"""LGPD art. 18 (exportar e excluir a conta) e Marco Civil art. 15 no PostGIS real."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sistemacampero.infrastructure.container import Container
from tests.conftest import emitir_token
from tests.integracao.apoio import Conn, criar_usuario, um, upload
from tests.sinteticos.jdl_builder import Cenario
from tests.sinteticos.jdl_builder import construir as construir_jdl

pytestmark = pytest.mark.integracao


def test_exportar_meus_dados(client: TestClient, org: dict[str, Any], admin: Conn) -> None:
    admin.execute(
        "insert into interno.aceites (usuario_id, documento, versao) values (%s, 'termos', 'v1')",
        (org["user"],),
    )
    r = client.get("/api/v1/eu/dados", headers=org["auth"])
    assert r.status_code == 200, r.text
    assert "attachment" in r.headers["content-disposition"]
    dados = r.json()
    assert dados["conta"]["usuario_id"] == str(org["user"])
    assert [o["papel"] for o in dados["organizacoes"]] == ["owner"]
    assert dados["aceites"][0]["versao"] == "v1"


def test_registro_de_acesso_guarda_ip_usuario_e_rota(
    client: TestClient, org: dict[str, Any], admin: Conn, container: Container
) -> None:
    assert container.acessos is not None
    client.get("/api/v1/me", headers=org["auth"])
    container.acessos.gravar_pendentes()
    linha = admin.execute(
        "select ip, metodo, rota, status from interno.registros_acesso"
        " where usuario_id = %s order by id desc limit 1",
        (org["user"],),
    ).fetchone()
    assert linha is not None
    assert (linha["metodo"], linha["rota"], linha["status"]) == ("GET", "/api/v1/me", 200)
    assert container.acessos.expurgar(6) >= 0


def test_exclusao_com_carencia_cancela_e_executa(
    client: TestClient, org: dict[str, Any], admin: Conn, container: Container
) -> None:
    h = org["auth"]
    upload(client, org, construir_jdl(Cenario()))
    caminho = um(
        admin,
        "select caminho_storage from public.arquivos_brutos where organizacao_id = %s",
        org["id"],
    )
    arquivo = Path(container.settings.storage_dir) / "brutos" / caminho
    assert arquivo.exists()

    situacao = client.get("/api/v1/eu/exclusao", headers=h).json()
    assert situacao["pedido"] is None
    assert [o["acao"] for o in situacao["organizacoes"]] == ["excluida"]

    errado = client.post("/api/v1/eu/exclusao", json={"confirmacao": "sim"}, headers=h)
    assert errado.json()["code"] == "CONFIRMACAO_INVALIDA"
    assert (
        client.post("/api/v1/eu/exclusao", json={"confirmacao": "EXCLUIR"}, headers=h).status_code
        == 202
    )
    duplicado = client.post("/api/v1/eu/exclusao", json={"confirmacao": "excluir"}, headers=h)
    assert duplicado.json()["code"] == "EXCLUSAO_JA_AGENDADA"

    # cancelar e pedir de novo
    assert client.delete("/api/v1/eu/exclusao", headers=h).status_code == 204
    assert client.get("/api/v1/eu/exclusao", headers=h).json()["pedido"] is None
    assert (
        client.post("/api/v1/eu/exclusao", json={"confirmacao": "EXCLUIR"}, headers=h).status_code
        == 202
    )

    # carência vencida: o worker apaga organização, arquivos e conta
    admin.execute(
        "update interno.solicitacoes_exclusao set agendada_para = now() - interval '1 minute'"
        " where usuario_id = %s and status = 'agendada'",
        (org["user"],),
    )
    assert container.titular is not None
    assert container.titular.executar_vencidas() >= 1
    assert um(admin, "select count(*) from public.organizacoes where id = %s", org["id"]) == 0
    assert um(admin, "select count(*) from auth.users where id = %s", org["user"]) == 0
    assert not arquivo.exists()
    assert (
        um(
            admin,
            "select status from interno.solicitacoes_exclusao where usuario_id = %s"
            " order by criado_em desc limit 1",
            org["user"],
        )
        == "concluida"
    )


def test_dono_unico_com_equipe_precisa_transferir(
    client: TestClient, org: dict[str, Any], admin: Conn
) -> None:
    outro = criar_usuario(admin)
    admin.execute(
        "insert into public.membros (organizacao_id, usuario_id, papel) values (%s, %s, 'leitor')",
        (org["id"], outro),
    )
    r = client.post("/api/v1/eu/exclusao", json={"confirmacao": "EXCLUIR"}, headers=org["auth"])
    assert r.status_code == 409 and r.json()["code"] == "TRANSFIRA_A_PROPRIEDADE"

    # o leitor pode sair: a organização continua
    h = {"Authorization": f"Bearer {emitir_token(outro)}"}
    situacao = client.get("/api/v1/eu/exclusao", headers=h).json()
    assert [o["acao"] for o in situacao["organizacoes"]] == ["sai"]
