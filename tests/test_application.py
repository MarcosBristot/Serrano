import pytest

from sistemacampero.application.analysis import AnalysisService
from sistemacampero.application.ingestion import IngestionService
from sistemacampero.infrastructure.parsers import default_adapters
from sistemacampero.infrastructure.parsers.john_deere_gen4.spatial import SpatialFilesFieldSource
from sistemacampero.infrastructure.persistence.workspace import LocalWorkspace


@pytest.fixture
def jdl_file(tmp_path, jdl_bytes):
    p = tmp_path / "2025_11_15_[09_07]_{abc}.jdl"
    p.write_bytes(jdl_bytes)
    return p


def test_ingestao_e_idempotente_e_preserva_bruto(tmp_path, jdl_file):
    store = LocalWorkspace(tmp_path / "w")
    svc = IngestionService(default_adapters(), store)
    first = svc.ingest_file(jdl_file, "John Deere", "Gen4")
    again = svc.ingest_file(jdl_file, "John Deere", "Gen4")
    assert first.status == "ok" and first.rows > 1000
    assert again.status == "ja_processado"
    assert (tmp_path / "w" / "raw" / f"{first.sha256}.jdl").exists()


def test_marca_nao_suportada_e_ignorada_sem_erro(tmp_path, jdl_file):
    svc = IngestionService(default_adapters(), LocalWorkspace(tmp_path / "w"))
    r = svc.ingest_file(jdl_file, "Case IH", "AFS")
    assert r.status == "ignorado" and "Case IH" in r.reason


def test_arquivo_corrompido_nao_derruba(tmp_path):
    bad = tmp_path / "x.jdl"
    bad.write_bytes(b"\x0d\x10\x00\x00\x00abc")
    r = IngestionService(default_adapters(), LocalWorkspace(tmp_path / "w")).ingest_file(bad)
    assert r.status == "erro"


def test_analise_associa_talhao_por_juncao_espacial(tmp_path, jdl_file, gen4_dir):
    store = LocalWorkspace(tmp_path / "w")
    IngestionService(default_adapters(), store).ingest_file(jdl_file)
    analysis = AnalysisService(store, SpatialFilesFieldSource(gen4_dir))
    summary = analysis.analyze_all()
    sessions = store.load_results("sessions")
    assert summary["sessoes"] == 1
    assert sessions.loc[0, "field_name"] == "Talhao Teste"
    assert sessions.loc[0, "talhao_id"] is not None
    assert sessions.loc[0, "fuel_integral_l"] == pytest.approx(11.0, rel=0.05)
