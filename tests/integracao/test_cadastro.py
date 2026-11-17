"""M4 no PostGIS real: importação Gen4, localização por GPS, cobertura, CRUD e correções."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sistemacampero.interfaces.worker import Worker
from tests.conftest import ACEITE, emitir_token
from tests.integracao.apoio import Conn, criar_usuario, drenar, um, upload, zipar
from tests.sinteticos.gen4 import QUADRADO, gjson_boundary, masterdata_xml
from tests.sinteticos.jdl_builder import Cenario
from tests.sinteticos.jdl_builder import construir as construir_jdl

pytestmark = pytest.mark.integracao

DENTRO = Cenario(minutos=6, velocidade_kmh=lambda _t: 8.0)  # 800 m ao norte, dentro do quadrado


def _pendrive(com_jdl: bool = True, contorno: list[list[float]] = QUADRADO) -> bytes:
    arquivos = {
        "Trator/Gen4/MasterData.xml": masterdata_xml(),
        "Trator/Gen4/SpatialFiles/Boundary{b1}.gjson": gjson_boundary(contorno),
    }
    if com_jdl:
        arquivos["Trator/JD-Data/log/Talhao/s.jdl"] = construir_jdl(DENTRO)
    return zipar(arquivos)


def _sessao(admin: Conn, org: dict[str, Any]) -> dict[str, Any]:
    linha = admin.execute(
        "select s.*, t.nome as talhao_nome from public.sessoes_trabalho s"
        " left join public.talhoes t on t.id = s.talhao_id where s.organizacao_id = %s",
        (org["id"],),
    ).fetchone()
    assert linha is not None
    return linha


# ------------------------------------------------------------------- importação + GPS
def test_pendrive_completo_importa_cadastro_e_localiza_por_gps(
    client: TestClient, worker: Worker, org: dict[str, Any], admin: Conn
) -> None:
    upload(client, org, _pendrive(), nome="pendrive.zip")
    assert drenar(worker) == 3  # zip -> importar_gen4 -> .jdl (nessa ordem, por prioridade)

    jobs = admin.execute(
        "select tipo from interno.jobs where organizacao_id = %s order by atualizado_em",
        (org["id"],),
    ).fetchall()
    assert [j["tipo"] for j in jobs] == ["expandir_zip", "importar_gen4", "processar_arquivo"]

    s = _sessao(admin, org)
    assert (s["talhao_nome"], s["talhao_origem"]) == ("Talhao Teste", "gps")
    assert float(s["talhao_confianca"]) == pytest.approx(1.0)
    assert (
        um(admin, "select count(*) from public.talhoes where organizacao_id = %s", org["id"]) == 2
    )
    # O implemento do .jdl é o mesmo do cadastro do monitor (por nome): sem duplicata.
    assert (
        um(admin, "select count(*) from public.implementos where organizacao_id = %s", org["id"])
        == 2
    )
    assert (
        um(admin, "select count(*) from public.operadores where organizacao_id = %s", org["id"])
        == 1
    )
    assert (
        um(
            admin,
            "select count(*) from public.telemetria where sessao_id = %s and talhao_id is null",
            s["id"],
        )
        == 0
    )

    m = admin.execute(
        "select * from public.metricas_sessao where sessao_id = %s and vigente", (s["id"],)
    ).fetchone()
    assert m is not None and m["area_metodo"] == "cobertura"
    # 6 min a 8 km/h = 800 m x 4,95 m = 0,396 ha
    assert m["area_cobertura_ha"] == pytest.approx(0.396, rel=0.02)
    assert m["area_cobertura_ha"] == pytest.approx(m["area_estimada_ha"], rel=0.02)
    assert m["l_ha"] == pytest.approx(m["litros_integral"] / m["area_cobertura_ha"])
    cob = admin.execute(
        "select extensions.st_isvalid(geometria) as ok,"
        " extensions.st_area(geometria::extensions.geography) / 10000 as ha"
        " from public.coberturas_sessao where sessao_id = %s",
        (s["id"],),
    ).fetchone()
    assert cob is not None and cob["ok"] and cob["ha"] == pytest.approx(0.396, rel=0.03)


def test_importar_depois_relocaliza_sessoes_existentes(
    client: TestClient, worker: Worker, org: dict[str, Any], admin: Conn
) -> None:
    upload(client, org, construir_jdl(DENTRO))
    drenar(worker)
    antes = _sessao(admin, org)
    assert antes["talhao_origem"] == "monitor"  # só o nome do cabeçalho, sem contorno ainda

    upload(client, org, _pendrive(com_jdl=False), nome="cadastro.zip")
    assert drenar(worker) == 3  # zip, importar_gen4, relocalização da sessão
    depois = _sessao(admin, org)
    assert depois["id"] == antes["id"]
    assert (depois["talhao_origem"], depois["talhao_nome"]) == ("gps", "Talhao Teste")


def test_reimportar_nao_sobrescreve_contorno_do_gestor(
    client: TestClient, worker: Worker, org: dict[str, Any], admin: Conn
) -> None:
    upload(client, org, _pendrive(com_jdl=False), nome="a.zip")
    drenar(worker)
    talhao = um(
        admin,
        "select id from public.talhoes where organizacao_id = %s and nome = 'Talhao Teste'",
        org["id"],
    )
    menor = [
        [-52.925, -28.105],
        [-52.915, -28.105],
        [-52.915, -28.095],
        [-52.925, -28.095],
        [-52.925, -28.105],
    ]
    resp = client.put(
        f"/api/v1/talhoes/{talhao}/contorno",
        json={"geometria": {"type": "Polygon", "coordinates": [menor]}, "origem": "desenho"},
        headers=org["auth"],
    )
    assert resp.status_code == 200 and resp.json()["origem_contorno"] == "desenho"
    area_desenhada = resp.json()["area_ha"]

    # Pendrive de novo com um contorno diferente: o desenho do gestor prevalece.
    outro = [
        [-52.94, -28.12],
        [-52.90, -28.12],
        [-52.90, -28.08],
        [-52.94, -28.08],
        [-52.94, -28.12],
    ]
    upload(client, org, _pendrive(com_jdl=False, contorno=outro), nome="b.zip")
    drenar(worker)
    t = client.get(f"/api/v1/talhoes/{talhao}", headers=org["auth"]).json()
    assert (t["origem_contorno"], t["area_ha"]) == ("desenho", area_desenhada)
    resultado = admin.execute(
        "select progresso from interno.jobs where organizacao_id = %s and tipo = 'importar_gen4'"
        " order by criado_em desc limit 1",
        (org["id"],),
    ).fetchone()
    assert resultado is not None
    assert resultado["progresso"]["resultado"]["contornos_preservados"] == 1


# ------------------------------------------------------------------- correção manual
def test_talhao_manual_sobrevive_ao_reprocessamento(
    client: TestClient, worker: Worker, org: dict[str, Any], admin: Conn, container: Any
) -> None:
    upload(client, org, _pendrive(), nome="p.zip")
    drenar(worker)
    s = _sessao(admin, org)
    sem_contorno = um(
        admin,
        "select id from public.talhoes where organizacao_id = %s and nome = 'Sem Contorno'",
        org["id"],
    )

    resp = client.patch(
        f"/api/v1/sessions/{s['id']}", json={"talhao_id": str(sem_contorno)}, headers=org["auth"]
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["sessao"]["talhao_origem"] == "manual"
    assert resp.json()["reprocessamento_agendado"] is True
    drenar(worker)

    # Reimportar o cadastro relocaliza só sessões NÃO manuais.
    upload(client, org, _pendrive(com_jdl=False, contorno=QUADRADO[::-1]), nome="de-novo.zip")
    drenar(worker)
    s2 = _sessao(admin, org)
    assert (s2["talhao_origem"], s2["talhao_nome"]) == ("manual", "Sem Contorno")
    area = um(
        admin,
        "select area_metodo from public.metricas_sessao where sessao_id = %s and vigente",
        s2["id"],
    )
    assert area == "cobertura"  # sem contorno no talhão manual: cobertura sem recorte

    # Voltar ao automático.
    client.patch(f"/api/v1/sessions/{s['id']}", json={"talhao_id": None}, headers=org["auth"])
    drenar(worker)
    s3 = _sessao(admin, org)
    assert (s3["talhao_origem"], s3["talhao_nome"]) == ("gps", "Talhao Teste")


def test_sessoes_lista_e_detalhe(client: TestClient, worker: Worker, org: dict[str, Any]) -> None:
    for i in range(3):
        upload(client, org, construir_jdl(Cenario(minutos=2, lat0=-28.10 + i / 1000)))
    drenar(worker)
    pagina = client.get("/api/v1/sessions", params={"limit": 2}, headers=org["auth"]).json()
    assert len(pagina["itens"]) == 2 and pagina["next_cursor"]
    resto = client.get(
        "/api/v1/sessions",
        params={"limit": 2, "cursor": pagina["next_cursor"]},
        headers=org["auth"],
    ).json()
    assert len(resto["itens"]) == 1 and resto["next_cursor"] is None
    detalhe = client.get(f"/api/v1/sessions/{resto['itens'][0]['id']}", headers=org["auth"]).json()
    assert detalhe["qualidade"]["score"] >= 0 and detalhe["adapter"] == "john_deere_gen4"
    assert client.get(f"/api/v1/sessions/{uuid.uuid4()}", headers=org["auth"]).status_code == 404


# ------------------------------------------------------------------- CRUD
def test_crud_do_cadastro(client: TestClient, org: dict[str, Any]) -> None:
    h = org["auth"]
    faz = client.post(
        "/api/v1/fazendas", json={"nome": "Sede", "cliente_nome": "Cliente"}, headers=h
    )
    assert faz.status_code == 201
    fid = faz.json()["id"]
    tal = client.post(
        "/api/v1/talhoes",
        json={
            "nome": "Lavoura 1",
            "fazenda_id": fid,
            "geometria": {"type": "Polygon", "coordinates": [QUADRADO]},
        },
        headers=h,
    )
    assert tal.status_code == 201, tal.text
    t = tal.json()
    assert t["tem_contorno"] and t["origem_contorno"] == "desenho"
    assert t["area_ha"] == pytest.approx(436, rel=0.02)  # ~1,96 km x 2,22 km
    assert t["geometria"]["type"] == "MultiPolygon"

    assert (
        client.patch(
            f"/api/v1/talhoes/{t['id']}", json={"nome": "Lavoura Norte"}, headers=h
        ).json()["nome"]
        == "Lavoura Norte"
    )
    listados = client.get("/api/v1/talhoes", params={"fazenda_id": fid}, headers=h).json()
    assert [x["nome"] for x in listados] == ["Lavoura Norte"]
    assert "geometria" not in listados[0] or listados[0]["geometria"] is None

    sem = client.delete(f"/api/v1/talhoes/{t['id']}/contorno", headers=h).json()
    assert (sem["tem_contorno"], sem["area_ha"], sem["origem_contorno"]) == (False, None, None)

    imp = client.post(
        "/api/v1/implementos", json={"nome": "Semeadora", "largura_m": 9.0}, headers=h
    ).json()
    assert (
        client.patch(f"/api/v1/implementos/{imp['id']}", json={"largura_m": 9.1}, headers=h).json()[
            "largura_m"
        ]
        == 9.1
    )
    op = client.post("/api/v1/operadores", json={"nome": "Fulano"}, headers=h).json()
    assert (
        client.patch(f"/api/v1/operadores/{op['id']}", json={"ativo": False}, headers=h).json()[
            "ativo"
        ]
        is False
    )

    assert client.delete(f"/api/v1/implementos/{imp['id']}", headers=h).status_code == 204
    assert client.delete(f"/api/v1/fazendas/{fid}", headers=h).status_code == 204
    assert client.get(f"/api/v1/talhoes/{t['id']}", headers=h).json()["fazenda_id"] is None


def test_upload_de_gjson_do_monitor_como_contorno(client: TestClient, org: dict[str, Any]) -> None:
    t = client.post("/api/v1/talhoes", json={"nome": "Via Arquivo"}, headers=org["auth"]).json()
    resp = client.put(
        f"/api/v1/talhoes/{t['id']}/contorno/arquivo",
        files={"arquivo": ("Boundary{x}.gjson", gjson_boundary(QUADRADO), "application/geo+json")},
        headers=org["auth"],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["origem_contorno"] == "upload"
    assert resp.json()["area_ha"] == pytest.approx(436, rel=0.02)  # Exterior, não a cabeceira


@pytest.mark.parametrize(
    ("corpo", "status", "code"),
    [
        (
            {"nome": "x", "geometria": {"type": "Point", "coordinates": [0, 0]}},
            422,
            "GEOMETRIA_INVALIDA",
        ),
        ({"nome": "x", "fazenda_id": str(uuid.UUID(int=1))}, 404, "REFERENCIA_INEXISTENTE"),
        ({"nome": ""}, 422, "VALIDACAO"),
    ],
)
def test_cadastro_invalido(
    client: TestClient, org: dict[str, Any], corpo: dict[str, Any], status: int, code: str
) -> None:
    resp = client.post("/api/v1/talhoes", json=corpo, headers=org["auth"])
    assert (resp.status_code, resp.json()["code"]) == (status, code)


def test_leitor_le_mas_nao_edita_e_org_alheia_nao_ve(
    client: TestClient, org: dict[str, Any], admin: Conn
) -> None:
    t = client.post("/api/v1/talhoes", json={"nome": "Privado"}, headers=org["auth"]).json()
    uid = criar_usuario(admin)
    admin.execute(
        "insert into public.membros (organizacao_id, usuario_id, papel) values (%s, %s, 'leitor')",
        (org["id"], uid),
    )
    leitor = {"Authorization": f"Bearer {emitir_token(uid)}"}
    assert client.get("/api/v1/talhoes", headers=leitor).status_code == 200
    assert client.post("/api/v1/fazendas", json={"nome": "x"}, headers=leitor).status_code == 403

    estranho = criar_usuario(admin)
    h = {"Authorization": f"Bearer {emitir_token(estranho)}"}
    client.post(
        "/api/v1/organizacoes", json={"nome": f"Outra {uuid.uuid4().hex[:6]}", **ACEITE}, headers=h
    )
    assert client.get(f"/api/v1/talhoes/{t['id']}", headers=h).status_code == 404
    assert (
        client.patch(f"/api/v1/talhoes/{t['id']}", json={"nome": "invadido"}, headers=h).status_code
        == 404
    )


# ------------------------------------------------------------------- máquinas
def test_desativar_libera_vaga_e_reativar_respeita_plano(
    client: TestClient, worker: Worker, org: dict[str, Any], admin: Conn
) -> None:
    admin.execute(
        "update public.assinaturas set max_maquinas_override = 1 where organizacao_id = %s",
        (org["id"],),
    )
    upload(client, org, construir_jdl(Cenario(minutos=2, serial="A")))
    b = upload(client, org, construir_jdl(Cenario(minutos=2, serial="B")))
    drenar(worker)
    assert (
        um(admin, "select status from public.arquivos_brutos where id = %s", b["arquivo_id"])
        == "bloqueado_plano"
    )

    maquinas = client.get("/api/v1/maquinas", headers=org["auth"]).json()
    assert [m["serial"] for m in maquinas] == ["A"]
    resp = client.patch(
        f"/api/v1/maquinas/{maquinas[0]['id']}",
        json={"ativa": False, "apelido": "Velho"},
        headers=org["auth"],
    ).json()
    assert (resp["ativa"], resp["apelido"], resp["arquivos_reabertos"]) == (False, "Velho", 1)
    drenar(worker)
    assert (
        um(admin, "select status from public.arquivos_brutos where id = %s", b["arquivo_id"])
        == "processado"
    )

    volta = client.patch(
        f"/api/v1/maquinas/{maquinas[0]['id']}", json={"ativa": True}, headers=org["auth"]
    )
    assert volta.status_code == 409 and volta.json()["code"] == "PLANO_LIMITE_MAQUINAS"
    assert json.loads(volta.content)["detalhes"]["limite"] == 1
