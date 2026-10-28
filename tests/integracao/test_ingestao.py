"""M3 ponta a ponta no PostGIS real: upload -> Storage -> fila -> worker -> banco."""

from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sistemacampero.domain.ingestao import Job, TipoJob
from sistemacampero.infrastructure.container import Container
from sistemacampero.infrastructure.storage.local import ArmazenamentoLocal
from sistemacampero.interfaces.worker import Worker
from tests.conftest import ACEITE, emitir_token
from tests.integracao.apoio import Conn, criar_usuario, drenar, um, upload, zipar
from tests.sinteticos.jdl_builder import Cenario
from tests.sinteticos.jdl_builder import construir as construir_jdl

pytestmark = pytest.mark.integracao


# ------------------------------------------------------------------- fluxo feliz
def test_upload_processa_e_grava_tudo(
    client: TestClient, worker: Worker, org: dict[str, Any], admin: Conn, container: Container
) -> None:
    r = upload(client, org, construir_jdl(Cenario(minutos=30, plantio=True)))
    assert r["duplicado"] is False and r["status"] == "recebido" and r["job_id"]

    assert drenar(worker) == 1
    job = client.get(f"/api/v1/jobs/{r['job_id']}", headers=org["auth"]).json()
    assert job["status"] == "concluido"
    assert job["progresso"]["resultado"]["status"] == "processado"

    arq = admin.execute(
        "select * from public.arquivos_brutos where id = %s", (r["arquivo_id"],)
    ).fetchone()
    assert arq and arq["status"] == "processado"
    assert arq["caminho_storage"] == f"{org['id']}/{r['sha256']}.jdl"

    sessao = admin.execute(
        "select * from public.sessoes_trabalho where arquivo_bruto_id = %s", (r["arquivo_id"],)
    ).fetchone()
    assert sessao and sessao["operacao"] == "plantio" and sessao["qualidade_score"] == 100
    assert sessao["talhao_origem"] == "monitor"  # talhão do cabeçalho do .jdl
    assert (
        um(admin, "select count(*) from public.telemetria where sessao_id = %s", sessao["id"])
        == sessao["n_amostras"]
    )
    assert (
        um(
            admin,
            "select count(*) from public.telemetria where sessao_id = %s and geom is not null",
            sessao["id"],
        )
        == sessao["n_amostras"]
    )
    m = admin.execute(
        "select * from public.metricas_sessao where sessao_id = %s and vigente", (sessao["id"],)
    ).fetchone()
    assert m and m["litros_integral"] == pytest.approx(11.0, rel=0.01)
    assert m["area_estimada_ha"] == pytest.approx(1.98, rel=0.01)
    assert (
        um(admin, "select serial from public.maquinas where organizacao_id = %s", org["id"])
        == "SINTETICO0001"
    )
    assert um(
        admin,
        "select largura_m::float from public.implementos where organizacao_id = %s",
        org["id"],
    ) == pytest.approx(4.95)

    storage = container.executor._storage  # type: ignore[union-attr]
    assert storage.existe("brutos", arq["caminho_storage"])
    assert storage.existe("limpos", sessao["caminho_limpo"])


def test_reenvio_e_duplicado_por_organizacao(
    client: TestClient, worker: Worker, org: dict[str, Any], admin: Conn
) -> None:
    dados = construir_jdl(Cenario(minutos=2))
    a = upload(client, org, dados)
    b = upload(client, org, dados, nome="outro_nome.jdl")
    assert b["duplicado"] is True
    assert (b["arquivo_id"], b["job_id"]) == (a["arquivo_id"], a["job_id"])
    assert um(admin, "select count(*) from interno.jobs where organizacao_id = %s", org["id"]) == 1

    # Outra organização com o mesmo arquivo não é "duplicado" (isolamento).
    uid = criar_usuario(admin)
    outra = {"auth": {"Authorization": f"Bearer {emitir_token(uid)}"}}
    resp = client.post(
        "/api/v1/organizacoes",
        json={"nome": f"Outra {uuid.uuid4().hex[:6]}", **ACEITE},
        headers=outra["auth"],
    )
    assert resp.status_code == 201
    assert upload(client, outra, dados)["duplicado"] is False
    # ... e não enxerga o job da primeira.
    assert client.get(f"/api/v1/jobs/{a['job_id']}", headers=outra["auth"]).status_code == 404


def test_reprocessar_nao_duplica_e_preserva_alerta_reconhecido(
    client: TestClient, worker: Worker, org: dict[str, Any], admin: Conn, container: Container
) -> None:
    parado = Cenario(
        minutos=25,
        velocidade_kmh=lambda _t: 0.0,
        vazao_lph=lambda _t: 3.2,
        rpm=lambda _t: 900,
        gps="nenhum",
    )
    r = upload(client, org, construir_jdl(parado))
    drenar(worker)
    sessao = um(
        admin, "select id from public.sessoes_trabalho where arquivo_bruto_id = %s", r["arquivo_id"]
    )
    alertas = admin.execute(
        "select tipo, status from public.alertas where sessao_id = %s order by tipo", (sessao,)
    ).fetchall()
    assert [a["tipo"] for a in alertas] == ["ociosidade", "sem_gps"]
    admin.execute(
        "update public.alertas set status = 'reconhecido' where sessao_id = %s and tipo = 'ociosidade'",
        (sessao,),
    )
    n_tel = um(admin, "select count(*) from public.telemetria where sessao_id = %s", sessao)

    assert container.repo_ingestao is not None
    container.repo_ingestao.enfileirar(
        org["id"], TipoJob.PROCESSAR_ARQUIVO, {"arquivo_id": r["arquivo_id"]}
    )
    assert drenar(worker) == 1

    assert (
        um(
            admin,
            "select count(*) from public.sessoes_trabalho where arquivo_bruto_id = %s",
            r["arquivo_id"],
        )
        == 1
    )
    assert um(admin, "select count(*) from public.telemetria where sessao_id = %s", sessao) == n_tel
    depois = admin.execute(
        "select tipo, status from public.alertas where sessao_id = %s order by tipo", (sessao,)
    ).fetchall()
    assert [(a["tipo"], a["status"]) for a in depois] == [
        ("ociosidade", "reconhecido"),
        ("sem_gps", "aberto"),
    ]
    assert (
        um(admin, "select count(*) from public.metricas_sessao where sessao_id = %s", sessao) == 1
    )


# ------------------------------------------------------------------- zip
def test_zip_do_pendrive(
    client: TestClient, worker: Worker, org: dict[str, Any], admin: Conn
) -> None:
    a, b = (
        construir_jdl(Cenario(minutos=3)),
        construir_jdl(Cenario(minutos=4, so_cabecalho=False, lat0=-28.2)),
    )
    vazio = construir_jdl(Cenario(minutos=1, so_cabecalho=True))
    dados = zipar(
        {
            "Trator JD/JD-Data/log/Talhao/a.jdl": a,
            "Trator JD/JD-Data/log/Talhao/b.jdl": b,
            "Trator JD/JD-Data/log/Talhao/copia_de_a.jdl": a,
            "Trator JD/JD-Data/log/Talhao/vazio.jdl": vazio,
            "Trator JD/Gen4/MasterData.xml": b"<Root/>",
            "Trator JD/Run_Pages/x.png": b"png",
        }
    )
    lote = client.post("/api/v1/batches", headers=org["auth"]).json()["lote_id"]
    r = upload(client, org, dados, nome="Trator JD.zip", lote_id=lote)
    assert drenar(worker) == 5  # zip + importar_gen4 + a + b + vazio

    filhos = admin.execute(
        "select nome_original, tipo, status, motivo from public.arquivos_brutos"
        ' where arquivo_pai_id = %s order by nome_original collate "C"',
        (r["arquivo_id"],),
    ).fetchall()
    assert [(f["nome_original"], f["status"]) for f in filhos] == [
        ("MasterData.xml", "processado"),  # importado pelo job importar_gen4
        ("a.jdl", "processado"),
        ("b.jdl", "processado"),
        ("vazio.jdl", "vazio"),
    ]
    assert filhos[3]["motivo"].startswith("sem_blocos_de_dados")
    status = client.get(f"/api/v1/batches/{lote}", headers=org["auth"]).json()
    assert status["arquivos"] == 5 and status["processados"] == 4 and status["vazios"] == 1
    job_zip = client.get(f"/api/v1/jobs/{r['job_id']}", headers=org["auth"]).json()
    assert job_zip["progresso"]["resultado"] == {
        "status": "processado",
        "jdl": 4,
        "masterdata": 1,
        "gjson": 0,
        "duplicados": 1,
    }


def test_zip_slip_rejeitado(
    client: TestClient, worker: Worker, org: dict[str, Any], admin: Conn
) -> None:
    r = upload(client, org, zipar({"../../fora.jdl": b"\x0dx"}), nome="mal.zip")
    drenar(worker)
    arq = admin.execute(
        "select status, motivo from public.arquivos_brutos where id = %s", (r["arquivo_id"],)
    ).fetchone()
    assert arq == {
        "status": "rejeitado",
        "motivo": "ZIP_CAMINHO_INSEGURO: O .zip contém caminho perigoso (fora da pasta).",
    }


def test_upload_recusa_formato_e_tamanho(client: TestClient, org: dict[str, Any]) -> None:
    resp = client.post(
        "/api/v1/telemetry/upload", files={"arquivo": ("x.exe", b"MZ", "x")}, headers=org["auth"]
    )
    assert resp.status_code == 422 and resp.json()["code"] == "FORMATO_NAO_SUPORTADO"
    resp = client.post(
        "/api/v1/telemetry/upload",
        files={"arquivo": ("x.jdl", b"PK\x03\x04", "x")},
        headers=org["auth"],
    )
    assert resp.status_code == 422 and resp.json()["code"] == "FORMATO_NAO_CONFERE"


def test_corrompido_e_rejeitado_sem_retentativa(
    client: TestClient, worker: Worker, org: dict[str, Any], admin: Conn
) -> None:
    r = upload(client, org, construir_jdl(Cenario(minutos=2))[:-500])
    drenar(worker)
    job = admin.execute(
        "select status, tentativas from interno.jobs where id = %s", (r["job_id"],)
    ).fetchone()
    assert job == {"status": "concluido", "tentativas": 1}
    assert (
        um(admin, "select status from public.arquivos_brutos where id = %s", r["arquivo_id"])
        == "rejeitado"
    )


# ------------------------------------------------------------------- plano
def test_limite_de_maquinas_do_plano(
    client: TestClient, worker: Worker, org: dict[str, Any], admin: Conn
) -> None:
    admin.execute(
        "update public.assinaturas set max_maquinas_override = 1 where organizacao_id = %s",
        (org["id"],),
    )
    upload(client, org, construir_jdl(Cenario(minutos=2, serial="SERIAL-A")))
    b = upload(client, org, construir_jdl(Cenario(minutos=2, serial="SERIAL-B")))
    drenar(worker)
    arq = admin.execute(
        "select status, motivo from public.arquivos_brutos where id = %s", (b["arquivo_id"],)
    ).fetchone()
    assert arq == {"status": "bloqueado_plano", "motivo": "PLANO_LIMITE_MAQUINAS"}
    assert (
        um(admin, "select count(*) from public.maquinas where organizacao_id = %s", org["id"]) == 1
    )

    admin.execute(
        "update public.assinaturas set max_maquinas_override = 2 where organizacao_id = %s",
        (org["id"],),
    )
    resp = client.post("/api/v1/admin/reabrir-bloqueados", headers=org["auth"])
    assert resp.json() == {"reenfileirados": 1}
    drenar(worker)
    assert (
        um(admin, "select status from public.arquivos_brutos where id = %s", b["arquivo_id"])
        == "processado"
    )


def test_leitor_nao_fazupload(client: TestClient, org: dict[str, Any], admin: Conn) -> None:
    uid = criar_usuario(admin)
    admin.execute(
        "insert into public.membros (organizacao_id, usuario_id, papel) values (%s, %s, 'leitor')",
        (org["id"], uid),
    )
    resp = client.post(
        "/api/v1/telemetry/upload",
        files={"arquivo": ("s.jdl", construir_jdl(Cenario(minutos=1)), "x")},
        headers={"Authorization": f"Bearer {emitir_token(uid)}"},
    )
    assert resp.status_code == 403 and resp.json()["code"] == "PAPEL_SEM_PERMISSAO"


# ------------------------------------------------------------------- fila
class _Falha:
    def __init__(self, vezes: int) -> None:
        self.vezes, self.chamadas, self.desistiu = vezes, 0, False

    def executar(self, job: Job, controle: Any) -> dict[str, Any]:
        self.chamadas += 1
        if self.chamadas <= self.vezes:
            raise ConnectionError("Storage fora do ar")
        return {"ok": True}

    def ao_desistir(self, job: Job, erro: str) -> None:
        self.desistiu = True


def _job_isolado(container: Container, org: dict[str, Any]) -> uuid.UUID:
    assert container.repo_ingestao is not None
    return container.repo_ingestao.enfileirar(
        org["id"],
        TipoJob.PROCESSAR_ARQUIVO,
        {"arquivo_id": str(uuid.uuid4())},
        chave=uuid.uuid4().hex,
    )


def test_retentativa_com_backoff_e_dead_letter(
    container: Container, org: dict[str, Any], admin: Conn, client: TestClient
) -> None:
    assert container.fila is not None
    job_id = _job_isolado(container, org)
    admin.execute("update interno.jobs set max_tentativas = 2 where id = %s", (job_id,))
    falha = _Falha(vezes=10)
    w = Worker(container.fila, falha, lease_s=60, reaper_s=0)  # type: ignore[arg-type]

    assert w.rodar_uma_vez()
    j = admin.execute(
        "select status, tentativas, erro, proxima_tentativa > now() + interval '20 s' as adiada"
        " from interno.jobs where id = %s",
        (job_id,),
    ).fetchone()
    assert j == {
        "status": "pendente",
        "tentativas": 1,
        "erro": "ConnectionError: Storage fora do ar",
        "adiada": True,
    }
    assert not w.rodar_uma_vez()  # ainda no backoff

    admin.execute("update interno.jobs set proxima_tentativa = now() where id = %s", (job_id,))
    assert w.rodar_uma_vez()
    assert um(admin, "select status from interno.jobs where id = %s", job_id) == "morto"
    assert falha.desistiu

    mortos = client.get(
        "/api/v1/admin/jobs", params={"status": "morto"}, headers=org["auth"]
    ).json()
    assert [m["id"] for m in mortos] == [str(job_id)]
    assert (
        client.post(f"/api/v1/admin/jobs/{job_id}/reenfileirar", headers=org["auth"]).status_code
        == 200
    )
    w.executor = _Falha(vezes=0)  # type: ignore[assignment]
    assert w.rodar_uma_vez()
    assert um(admin, "select status from interno.jobs where id = %s", job_id) == "concluido"


def test_worker_morto_no_meio_do_job_e_retomado(
    client: TestClient, container: Container, worker: Worker, org: dict[str, Any], admin: Conn
) -> None:
    """kill -9 simulado: o job fica 'executando' com lease; vencido, outro worker retoma."""
    assert container.fila is not None
    r = upload(client, org, construir_jdl(Cenario(minutos=3)))
    morto = container.fila.reivindicar("worker-que-morreu", lease_s=600)
    assert morto is not None and str(morto.id) == r["job_id"]
    container.fila.recolher_vencidos()  # lease ainda válido: o reaper não mexe
    assert (
        um(admin, "select locked_by from interno.jobs where id = %s", r["job_id"])
        == "worker-que-morreu"
    )

    admin.execute(
        "update interno.jobs set lease_ate = now() - interval '1 s' where id = %s", (r["job_id"],)
    )
    assert drenar(worker) == 1  # reaper devolve, worker processa
    j = admin.execute(
        "select status, tentativas, locked_by from interno.jobs where id = %s", (r["job_id"],)
    ).fetchone()
    assert j == {"status": "concluido", "tentativas": 2, "locked_by": None}
    assert (
        um(
            admin,
            "select count(*) from public.sessoes_trabalho where arquivo_bruto_id = %s",
            r["arquivo_id"],
        )
        == 1
    )

    # O worker "ressuscitado" não consegue mais concluir nem renovar o job.
    assert not container.fila.renovar(morto.id, "worker-que-morreu", 60)


def test_cancelamento(
    container: Container, org: dict[str, Any], admin: Conn, client: TestClient
) -> None:
    assert container.fila is not None
    pendente = _job_isolado(container, org)
    resp = client.post(f"/api/v1/jobs/{pendente}/cancelar", headers=org["auth"]).json()
    assert resp["status"] == "cancelado"

    executando = _job_isolado(container, org)

    class _PedeCancelamentoNoMeio:
        def executar(self, job: Job, controle: Any) -> dict[str, Any]:
            client.post(f"/api/v1/jobs/{job.id}/cancelar", headers=org["auth"])
            controle.verificar()  # entre etapas
            raise AssertionError("não deveria chegar aqui")

        def ao_desistir(self, job: Job, erro: str) -> None: ...

    w = Worker(container.fila, _PedeCancelamentoNoMeio(), reaper_s=0)  # type: ignore[arg-type]
    assert w.rodar_uma_vez()
    assert um(admin, "select status from interno.jobs where id = %s", executando) == "cancelado"
    assert um(admin, "select status from interno.jobs where id = %s", pendente) == "cancelado"


def test_skip_locked_nenhum_job_pego_duas_vezes(container: Container, org: dict[str, Any]) -> None:
    assert container.fila is not None
    ids = {_job_isolado(container, org) for _ in range(20)}
    pegos: list[uuid.UUID] = []
    trava = threading.Lock()

    def consumir(nome: str) -> None:
        assert container.fila is not None
        while (job := container.fila.reivindicar(nome, 60)) is not None:
            with trava:
                pegos.append(job.id)

    threads = [threading.Thread(target=consumir, args=(f"w{i}",)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(pegos) == len(set(pegos))
    assert ids <= set(pegos)


def test_listagem_paginada_por_cursor(
    client: TestClient, worker: Worker, org: dict[str, Any]
) -> None:
    for i in range(5):
        upload(client, org, construir_jdl(Cenario(minutos=1, lat0=-28.0 - i / 100)))
    vistos, cursor = [], None
    while True:
        params: dict[str, Any] = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        pagina = client.get("/api/v1/arquivos", params=params, headers=org["auth"]).json()
        vistos += [a["id"] for a in pagina["itens"]]
        cursor = pagina["next_cursor"]
        if not cursor:
            break
    assert len(vistos) == len(set(vistos)) == 5
    assert (
        client.get("/api/v1/arquivos", params={"cursor": "lixo"}, headers=org["auth"]).status_code
        == 422
    )


def test_ready_checa_banco_e_storage(client: TestClient) -> None:
    corpo = client.get("/ready").json()
    assert corpo == {"status": "ok", "checks": {"banco": "ok", "storage": "ok"}}


def test_storage_fora_do_caminho(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ArmazenamentoLocal(tmp_path).ler("brutos", "../../segredo")
