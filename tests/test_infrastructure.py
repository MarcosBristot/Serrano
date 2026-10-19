from sistemacampero.infrastructure.config import Settings
from sistemacampero.infrastructure.parsers.john_deere_gen4.spatial import (
    SpatialFilesFieldSource,
    stable_field_id,
)
from sistemacampero.infrastructure.persistence.supabase_repository import (
    SupabaseFieldRepository,
    json_row,
)


def test_settings_nao_tem_segredo_padrao():
    s = Settings.from_env({})
    assert s.supabase_key is None and s.api_key is None and not s.supabase_enabled
    s = Settings.from_env(
        {"SUPABASE_URL": "https://x", "SUPABASE_KEY": "k", "CAMPERO_PERSIST_STEP_S": "0"}
    )
    assert s.supabase_enabled and s.persist_step_s == 1


def test_contornos_do_monitor_usam_so_o_exterior(gen4_dir):
    fields = SpatialFilesFieldSource(gen4_dir).list_fields()
    assert len(fields) == 1
    f = fields[0]
    assert (f.name, f.farm, f.client) == ("Talhao Teste", "Fazenda Teste", "Cliente Teste")
    assert (
        f.id == stable_field_id("t1") and 1250 < f.area_ha < 1350
    )  # 0,02° x 0,06° em -28° ≈ 1.307 ha
    assert f.geometry["coordinates"][0][0] == [-52.93, -28.11]  # exterior, não a cabeceira


def test_importacao_de_talhoes_usa_rpc_upsert(gen4_dir, fake_supabase):
    repo = SupabaseFieldRepository(fake_supabase)
    n = repo.upsert_fields(SpatialFilesFieldSource(gen4_dir).list_fields())
    name, params = fake_supabase.rpcs[0]
    assert n == 1 and name == "upsert_talhao" and params["p_external_guid"] == "t1"
    assert params["p_geojson"]["type"] == "Polygon"


def test_listar_talhoes_le_geojson_via_rpc(fake_supabase):
    fields = SupabaseFieldRepository(fake_supabase).list_fields()
    assert fields[0].name == "Talhao Teste" and fields[0].geometry["type"] == "Polygon"


def test_json_row_converte_nan_e_numpy():
    import numpy as np
    import pandas as pd

    row = json_row(
        {
            "a": float("nan"),
            "b": np.float64(1.5),
            "c": pd.Timestamp("2025-01-01", tz="UTC"),
            "d": None,
        }
    )
    assert row == {"a": None, "b": 1.5, "c": "2025-01-01T00:00:00+00:00", "d": None}
