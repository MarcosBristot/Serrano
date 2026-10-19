"""Fixtures compartilhadas (dados 100% sintéticos: nenhum dado de cliente)."""

import json

import pytest

from sistemacampero.infrastructure.config import Settings
from sistemacampero.infrastructure.container import build_services
from tests.jdl_builder import build_jdl

# Talhão de teste que contém a trajetória sintética (lat -28.10.., lon -52.92)
FIELD_GEOJSON = {
    "type": "Polygon",
    "coordinates": [
        [[-52.93, -28.11], [-52.91, -28.11], [-52.91, -28.05], [-52.93, -28.05], [-52.93, -28.11]]
    ],
}


class FakeResponse:
    def __init__(self, data=None, count=None):
        self.data, self.count = data, count


class FakeSupabase:
    """Dublê mínimo do cliente supabase-py: registra upserts e RPCs."""

    def __init__(self, fields=None):
        self.upserts: dict[str, list[dict]] = {}
        self.conflicts: dict[str, str] = {}
        self.rpcs: list[tuple[str, dict]] = []
        self._fields = fields or []

    def table(self, name):
        return _FakeTable(self, name)

    def rpc(self, name, params):
        self.rpcs.append((name, params))
        data = self._fields if name == "listar_talhoes_geojson" else None
        return _FakeExec(FakeResponse(data))


class _FakeExec:
    def __init__(self, response):
        self._response = response

    def execute(self):
        return self._response


class _FakeTable:
    def __init__(self, client, name):
        self._client, self._name = client, name

    def upsert(self, rows, on_conflict=None):
        self._client.upserts.setdefault(self._name, []).extend(rows)
        self._client.conflicts[self._name] = on_conflict
        return _FakeExec(FakeResponse())


@pytest.fixture
def settings(tmp_path):
    return Settings(workdir=tmp_path / "work", persist_step_s=5)


@pytest.fixture
def jdl_bytes():
    return build_jdl(speed_kmh=8.0, fuel_lph=22.0, rpm=1800, minutes=30)


@pytest.fixture
def fake_supabase():
    field = {
        "id": "11111111-1111-1111-1111-111111111111",
        "nome": "Talhao Teste",
        "fazenda": "Fazenda Teste",
        "cliente": "Cliente Teste",
        "area_ha": 100.0,
        "external_guid": "g1",
        "geometry": FIELD_GEOJSON,
    }
    return FakeSupabase([field])


@pytest.fixture
def services(settings, fake_supabase):
    return build_services(settings, supabase_client=fake_supabase)


@pytest.fixture
def gen4_dir(tmp_path):
    """Pasta Gen4 sintética: MasterData.xml + SpatialFiles com contorno externo e cabeceira."""
    root = tmp_path / "Gen4"
    (root / "SpatialFiles").mkdir(parents=True)
    xml = """<?xml version="1.0"?>
<Root xmlns="http://www.example.org/masterdata" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
 <Client Name="Cliente Teste" StringGuid="{c1}"/>
 <Farm Name="Fazenda Teste" StringGuid="{f1}" Client="{c1}"/>
 <Field Name="Talhao Teste" StringGuid="{t1}"><Farm>{f1}</Farm></Field>
 <OperationalBoundary TaggedEntity="{t1}" Name="Talhao Teste-Contorno" StringGuid="{b1}">
  <Geometry><FilenameWithExtension>Boundary{b1}.gjson</FilenameWithExtension></Geometry>
 </OperationalBoundary>
</Root>"""
    (root / "MasterData.xml").write_text(xml, encoding="utf-8")
    headland = {
        "type": "Polygon",
        "coordinates": [
            [
                [-52.925, -28.105],
                [-52.915, -28.105],
                [-52.915, -28.06],
                [-52.925, -28.06],
                [-52.925, -28.105],
            ]
        ],
    }
    gj = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"boundarytype": "OffsetGeneratedExteriorHeadland"},
                "geometry": headland,
            },
            {
                "type": "Feature",
                "properties": {"boundarytype": "Exterior"},
                "geometry": FIELD_GEOJSON,
            },
        ],
    }
    (root / "SpatialFiles" / "Boundary{b1}.gjson").write_text(json.dumps(gj), encoding="utf-8")
    return root
