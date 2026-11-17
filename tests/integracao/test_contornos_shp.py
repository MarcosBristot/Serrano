"""Contornos do OMNI (pulverizador) dentro do .zip, no PostGIS real."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from sistemacampero.interfaces.worker import Worker
from tests.integracao.apoio import Conn, drenar, upload, zipar
from tests.sinteticos.shp import PRJ_WGS84, dbf, poligono_shp, polilinhas_shp, quadrado

pytestmark = pytest.mark.integracao


def _omni(talhao: str, lon: float) -> dict[str, bytes]:
    base = f"Pulverizador/OMNI/Data/Agricola Teste/{talhao}"
    return {
        f"{base}/_perimeter.shp": poligono_shp(quadrado(lon, -28.12, 0.01)),
        f"{base}/_perimeter.prj": PRJ_WGS84,
        f"{base}/_headland.shp": polilinhas_shp(
            [(lon, -28.12), (lon + 0.01, -28.12), (lon + 0.01, -28.11), (lon, -28.11)]
        ),
        f"{base}/_headland.dbf": dbf([("Headland", "C", 64)], [["2026/06/16 12:37:29"]]),
        f"{base}/_runline.shp": polilinhas_shp([(lon, -28.12), (lon, -28.11)]),
        f"{base}/_runline.dbf": dbf(
            [("Runline", "C", 64), ("Type", "N", 5)], [["2022/07/21 19:21:59", "1"]]
        ),
    }


def test_zip_com_omni_casa_pelo_nome_e_preserva_contorno(
    client: TestClient, worker: Worker, org: dict[str, Any], admin: Conn
) -> None:
    h = org["auth"]
    client.post("/api/v1/talhoes", json={"nome": "Mãe"}, headers=h)
    precisao = client.post("/api/v1/talhoes", json={"nome": "Precisão"}, headers=h).json()
    desenho = [
        [-52.80, -28.0],
        [-52.79, -28.0],
        [-52.79, -27.99],
        [-52.80, -27.99],
        [-52.80, -28.0],
    ]
    r = client.put(
        f"/api/v1/talhoes/{precisao['id']}/contorno",
        json={"geometria": {"type": "Polygon", "coordinates": [desenho]}, "origem": "desenho"},
        headers=h,
    )
    assert r.status_code == 200

    pacote = {
        **_omni("Mae", -52.93),
        **_omni("Precisao", -52.90),
        **_omni("Campo_151122-145941", -52.87),
    }
    upload(client, org, zipar(pacote), nome="pendrive.zip")
    drenar(worker)

    talhoes = {
        t["nome"]: t
        for t in admin.execute(
            "select nome, origem_contorno, round(area_ha::numeric, 0) as ha,"
            " extensions.st_xmin(geometria) as x from public.talhoes where organizacao_id = %s",
            (org["id"],),
        ).fetchall()
    }
    assert talhoes["Mãe"]["origem_contorno"] == "upload"  # ganhou o contorno do OMNI
    assert talhoes["Mãe"]["ha"] > 100
    assert talhoes["Precisão"]["origem_contorno"] == "desenho"  # o do gestor ficou
    assert float(talhoes["Precisão"]["x"]) == pytest.approx(-52.80)
    assert talhoes["Campo 151122-145941"]["origem_contorno"] == "upload"  # criado

    # Cabeceira e linha-guia de cada talhão viram camada do mapa.
    linhas = client.get("/api/v1/talhoes/linhas", headers=h).json()["features"]
    assert sorted((f["properties"]["talhao"], f["properties"]["tipo"]) for f in linhas) == sorted(
        (t, tipo)
        for t in ("Mãe", "Precisão", "Campo 151122-145941")
        for tipo in ("cabeceira", "linha_guia")
    )

    # Reenviar o mesmo pacote não duplica talhões nem linhas.
    upload(client, org, zipar({**pacote, "leia-me.txt": b"x"}), nome="de-novo.zip")
    drenar(worker)
    n = admin.execute(
        "select count(*) as n from public.talhoes where organizacao_id = %s", (org["id"],)
    ).fetchone()
    assert n is not None and n["n"] == 3
    assert len(client.get("/api/v1/talhoes/linhas", headers=h).json()["features"]) == 6
