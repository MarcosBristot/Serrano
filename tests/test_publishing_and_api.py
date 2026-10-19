import io
import time

import pytest
from fastapi.testclient import TestClient

from sistemacampero.infrastructure.config import Settings
from sistemacampero.infrastructure.container import build_services
from sistemacampero.interfaces.api.app import create_app


def _wait(client, job_id, headers=None):
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
        if job["status"] in ("concluido", "erro"):
            return job
        time.sleep(0.05)
    raise AssertionError(job)


def _upload(client, data, name="2025_11_15_[09_07]_{abc}.jdl", params=None, headers=None):
    return client.post(
        "/api/v1/telemetry/upload",
        params=params or {"marca": "John Deere", "tecnologia": "Gen4"},
        files={"file": (name, io.BytesIO(data), "application/octet-stream")},
        headers=headers,
    )


def test_upload_processa_e_publica_no_supabase(services, fake_supabase, jdl_bytes):
    client = TestClient(create_app(services=services))
    r = _upload(client, jdl_bytes)
    assert r.status_code == 202
    job = _wait(client, r.json()["job_id"])
    assert job["status"] == "concluido" and job["publicado"] is True

    # tabelas e chaves de conflito usadas no upsert (idempotência)
    assert fake_supabase.conflicts["telemetria"] == "machine_serial,timestamp"
    assert fake_supabase.conflicts["sessoes_trabalho"] == "source_sha256"
    assert fake_supabase.conflicts["metricas_sessao"] == "session_sha256,rules_version"

    rows = fake_supabase.upserts["telemetria"]
    assert len(rows) == pytest.approx(360, abs=2)  # 30 min a cada 5 s
    first = rows[0]
    assert first["machine_serial"] == "SINTETICO0001"
    assert first["speed_kmh"] == pytest.approx(8.0)
    assert first["fuel_rate_lph"] == pytest.approx(22.0)
    assert first["talhao_id"] == "11111111-1111-1111-1111-111111111111"  # junção espacial
    # sem RPC por ponto: só a listagem de talhões (1 chamada)
    assert [n for n, _ in fake_supabase.rpcs] == ["listar_talhoes_geojson"]
    sess = fake_supabase.upserts["sessoes_trabalho"][0]
    assert sess["talhao_id"] == first["talhao_id"] and sess["operation"] is None
    assert fake_supabase.upserts["metricas_sessao"][0]["fuel_integral_l"] == pytest.approx(
        11.0, rel=0.05
    )


def test_reenvio_do_mesmo_arquivo_nao_duplica_registros_logicos(services, fake_supabase, jdl_bytes):
    client = TestClient(create_app(services=services))
    ids = []
    for _ in range(2):
        job = _wait(client, _upload(client, jdl_bytes).json()["job_id"])
        ids.append(job["resultado"])
    assert ids == ["ok", "ja_processado"]
    keys = {(r["machine_serial"], r["timestamp"]) for r in fake_supabase.upserts["telemetria"]}
    assert len(keys) == len(set(keys))  # mesma chave => o upsert sobrescreve, não duplica


def test_marca_nao_suportada_vira_job_concluido_ignorado(services, jdl_bytes):
    client = TestClient(create_app(services=services))
    job = _wait(
        client,
        _upload(client, jdl_bytes, params={"marca": "New Holland", "tecnologia": "PLM"}).json()[
            "job_id"
        ],
    )
    assert job["resultado"] == "ignorado" and job["publicado"] is False


def test_nome_malicioso_nao_escapa_do_diretorio_e_temp_e_removido(services, jdl_bytes):
    client = TestClient(create_app(services=services))
    r = _upload(client, jdl_bytes, name="../../etc/passwd.jdl")
    assert r.status_code == 202 and r.json()["arquivo"] == "passwd.jdl"
    _wait(client, r.json()["job_id"])
    assert list((services.settings.workdir / "uploads").iterdir()) == []


def test_extensao_invalida_e_limite_de_tamanho(settings, jdl_bytes):
    small = Settings(workdir=settings.workdir, max_upload_mb=1)
    client = TestClient(create_app(services=build_services(small)))
    assert _upload(client, b"x", name="a.csv").status_code == 415
    assert _upload(client, b"\0" * (2 * 1024 * 1024), name="grande.jdl").status_code == 413


def test_api_key_quando_configurada(settings, jdl_bytes):
    secured = Settings(workdir=settings.workdir, api_key="segredo-de-teste")
    client = TestClient(create_app(services=build_services(secured)))
    assert client.get("/health").status_code == 200
    assert _upload(client, jdl_bytes).status_code == 401
    assert _upload(client, jdl_bytes, headers={"X-API-Key": "errada"}).status_code == 401
    assert _upload(client, jdl_bytes, headers={"X-API-Key": "segredo-de-teste"}).status_code == 202


def test_modo_local_sem_supabase_consulta_resultados(settings, jdl_bytes, gen4_dir):
    local = Settings(workdir=settings.workdir, gen4_dir=gen4_dir)
    services = build_services(local)
    client = TestClient(create_app(services=services))
    job = _wait(client, _upload(client, jdl_bytes).json()["job_id"])
    assert job["status"] == "concluido" and job["publicado"] is False
    services.analysis.analyze_all()

    stats = client.get("/api/v1/telemetry/stats/SINTETICO0001").json()
    assert stats["horas_motor"] == pytest.approx(0.5, abs=0.01)
    assert stats["consumo_medio_lph"] == pytest.approx(22.0, rel=0.03)
    track = client.get("/api/v1/telemetry/machine/SINTETICO0001").json()
    assert track and track[0]["latitude"] < -28.0 and track[0]["engine_on"] is True
    assert client.get("/api/v1/sessions").json()["total"] == 1
    assert client.get("/api/v1/telemetry/stats/NAOEXISTE").status_code == 404


def test_publish_pending_faz_backfill(settings, jdl_bytes, fake_supabase):
    local = build_services(settings)  # ingere sem publicar
    local.ingestion.ingest_file(_write(settings, jdl_bytes))
    with_db = build_services(settings, supabase_client=fake_supabase)
    assert with_db.processor.publish_pending() == {
        "publicadas": 1,
        "ja_publicadas": 0,
        "sem_metricas": 0,
    }
    assert with_db.processor.publish_pending()["ja_publicadas"] == 1


def _write(settings, data):
    settings.workdir.mkdir(parents=True, exist_ok=True)
    p = settings.workdir / "in.jdl"
    p.write_bytes(data)
    return p
