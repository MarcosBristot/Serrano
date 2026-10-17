import hashlib
import time

from fastapi.testclient import TestClient

from sistemacampero.api.app import create_app
from tests.jdl_builder import build_jdl


def test_upload_em_partes_ate_resultados(tmp_path):
    data = build_jdl(8.0, 22.0, 1800, 30)
    client = TestClient(create_app(tmp_path))
    up = client.post("/api/v1/uploads", json={
        "filename": "sessao.jdl", "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    uid = up.json()["upload_id"]
    size = 40_000
    for i, off in enumerate(range(0, len(data), size)):
        assert client.put(f"/api/v1/uploads/{uid}/chunks/{i}", content=data[off:off + size]).status_code == 204
    job_id = client.post(f"/api/v1/uploads/{uid}/complete").json()["job_id"]
    for _ in range(50):  # TestClient executa a tarefa de fundo ao fim da requisição
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in ("concluido", "erro"):
            break
        time.sleep(0.1)
    assert job["status"] == "concluido", job
    assert job["arquivos"] == {"ok": 1}
    sessions = client.get("/api/v1/sessions").json()
    assert sessions["total"] == 1 and sessions["items"][0]["fuel_integral_l"] > 10
    assert client.get("/api/v1/metrics/daily").json()["total"] == 1


def test_sha_invalido_rejeita(tmp_path):
    data = build_jdl(8.0, 22.0, 1800, 1)
    client = TestClient(create_app(tmp_path))
    uid = client.post("/api/v1/uploads", json={
        "filename": "x.jdl", "size_bytes": len(data), "sha256": "0" * 64}).json()["upload_id"]
    client.put(f"/api/v1/uploads/{uid}/chunks/0", content=data)
    assert client.post(f"/api/v1/uploads/{uid}/complete").status_code == 422
