"""Teste de contrato comum: roda para TODO adapter registrado.

Para uma marca nova, adicione amostras sintéticas em ``AMOSTRAS`` (ver
docs/como-adicionar-marca.md). Nada aqui conhece detalhes de fabricante.
"""

from __future__ import annotations

import io
from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest

from sistemacampero.domain.ports import TelemetryAdapter
from sistemacampero.domain.telemetry import (
    COLUNAS_UNIVERSAIS,
    ArquivoInvalido,
    EmptyFile,
    ParseContext,
    ParsedSession,
)
from sistemacampero.infrastructure.parsers.registry import registro_padrao
from tests.sinteticos import gs3, isoxml, trimble
from tests.sinteticos.jdl_builder import Cenario, construir


class Amostras:
    def __init__(
        self,
        nome_arquivo: str,
        trabalho: Callable[[], bytes],
        sem_canal: Callable[[], bytes],
        so_cabecalho: Callable[[], bytes],
        corrompido: Callable[[], bytes] | None = None,
    ) -> None:
        self.nome_arquivo = nome_arquivo
        self.trabalho = trabalho  # 30 min, 8 km/h, 22 L/h, 1800 RPM, com GPS
        self.sem_canal = sem_canal  # sem o canal de RPM
        self.so_cabecalho = so_cabecalho
        # Padrão: o arquivo cortado ao meio. Formato de fluxo (registro contínuo), em que o corte
        # é normal e legível, diz o que é corrompido de verdade.
        self.corrompido = corrompido or (lambda: (d := trabalho())[: len(d) // 2])


AMOSTRAS: dict[tuple[str, str], Amostras] = {
    ("john_deere", "gen4"): Amostras(
        "sessao.jdl",
        lambda: construir(Cenario(minutos=30)),
        lambda: construir(Cenario(minutos=5, omitir=frozenset({"engine_rpm"}))),
        lambda: construir(Cenario(minutos=1, so_cabecalho=True)),
    ),
    # O GreenStar 3 não grava RPM: a amostra "sem canal" é a mesma operação, mais curta.
    ("john_deere", "gs3"): Amostras(
        "operacao.rcd",
        lambda: gs3.construir(gs3.CenarioGs3(minutos=30)),
        lambda: gs3.construir(gs3.CenarioGs3(minutos=5)),
        lambda: gs3.construir(gs3.CenarioGs3(so_cabecalho=True)),
    ),
    # ISOBUS não tem RPM padronizado no TLG; a amostra é gravada a 5 Hz, como muitos monitores.
    ("isobus", "isoxml"): Amostras(
        "TLG00001.isoxml",
        lambda: isoxml.construir(isoxml.CenarioIso(minutos=30, hz=5)),
        lambda: isoxml.construir(isoxml.CenarioIso(minutos=5)),
        lambda: isoxml.construir(isoxml.CenarioIso(so_cabecalho=True)),
    ),
    # Trimble TMX-2050: registro de GPS (sem diesel nem RPM no formato). Registro cortado no fim é
    # normal (monitor desligado no meio); corrompido = bytes sem estrutura de pacote TSIP.
    ("trimble", "tmx"): Amostras(
        "Massey Ferguson 7725 · TMX_LogAg_6435439113_20261111_1500_001.tsip",
        lambda: trimble.construir(trimble.CenarioTrimble(minutos=30)),
        lambda: trimble.construir(trimble.CenarioTrimble(minutos=5)),
        lambda: trimble.construir(trimble.CenarioTrimble(so_cabecalho=True)),
        lambda: b"" + bytes(range(16, 250)) * 300,
    ),
}

ADAPTERS = registro_padrao().todos()


def _id(a: TelemetryAdapter) -> str:
    return f"{a.brand}/{a.technology}"


def _amostras(a: TelemetryAdapter) -> Amostras:
    chave = (a.brand, a.technology)
    assert chave in AMOSTRAS, f"adapter {chave} sem amostras de contrato"
    return AMOSTRAS[chave]


def _parse(a: TelemetryAdapter, dados: bytes) -> ParsedSession | EmptyFile:
    am = _amostras(a)
    return a.parse(io.BytesIO(dados), ParseContext(am.nome_arquivo, a.brand, a.technology))


@pytest.fixture(params=ADAPTERS, ids=_id)
def adapter(request: pytest.FixtureRequest) -> TelemetryAdapter:
    a: TelemetryAdapter = request.param
    return a


def test_identificacao(adapter: TelemetryAdapter) -> None:
    assert adapter.brand and adapter.technology and adapter.version
    am = _amostras(adapter)
    assert adapter.can_parse(am.trabalho()[:64], am.nome_arquivo)
    assert not adapter.can_parse(b"PK\x03\x04qualquer zip", "x.zip")


def test_schema_tipos_e_unidades(adapter: TelemetryAdapter) -> None:
    s = _parse(adapter, _amostras(adapter).trabalho())
    assert isinstance(s, ParsedSession)
    df = s.amostras
    assert list(df.columns) == list(COLUNAS_UNIVERSAIS)
    assert {c: str(t) for c, t in df.dtypes.items()} == COLUNAS_UNIVERSAIS
    assert len(df) == pytest.approx(30 * 60, abs=2)
    assert df["speed_kmh"].median() == pytest.approx(8.0, rel=0.01)  # km/h
    if "fuel_rate_lph" not in s.diagnostico.canais_fora_do_formato:  # registro só de GPS
        assert df["fuel_rate_lph"].median() == pytest.approx(22.0, rel=0.01)  # L/h
    sem_rpm = s.diagnostico.canais_ausentes + s.diagnostico.canais_fora_do_formato
    if "engine_rpm" not in sem_rpm:  # nem todo monitor grava RPM
        assert df["engine_rpm"].median() == pytest.approx(1800.0, rel=0.01)
    assert df["gps_valid"].mean() > 0.95
    assert df.loc[df["gps_valid"], "lat"].between(-90, 90).all()
    assert s.metadados.inicio <= s.metadados.fim


def test_ts_utc_estritamente_crescente(adapter: TelemetryAdapter) -> None:
    s = _parse(adapter, _amostras(adapter).trabalho())
    assert isinstance(s, ParsedSession)
    ts = s.amostras["ts"]
    assert str(ts.dt.tz) == "UTC"
    assert ts.is_monotonic_increasing and ts.is_unique
    assert (ts.diff().dropna() == pd.Timedelta(seconds=1)).all()


def test_ausencia_e_nan_nunca_zero(adapter: TelemetryAdapter) -> None:
    s = _parse(adapter, _amostras(adapter).sem_canal())
    assert isinstance(s, ParsedSession)
    assert s.amostras["engine_rpm"].isna().all()
    # Ausente no arquivo ou fora do formato (GreenStar 3 nunca grava RPM): nunca vira 0.
    assert "engine_rpm" in s.diagnostico.canais_ausentes + s.diagnostico.canais_fora_do_formato
    # Ninguém inventa 0 para o que não foi medido.
    for col in ("speed_alt_kmh", "fuel_level_l"):
        assert not (s.amostras[col] == 0).any()


def test_idempotente(adapter: TelemetryAdapter) -> None:
    dados = _amostras(adapter).trabalho()
    a, b = _parse(adapter, dados), _parse(adapter, dados)
    assert isinstance(a, ParsedSession) and isinstance(b, ParsedSession)
    assert a.sha256 == b.sha256
    pd.testing.assert_frame_equal(a.amostras, b.amostras)
    assert a.metadados == b.metadados


def test_so_cabecalho_e_arquivo_vazio_com_motivo(adapter: TelemetryAdapter) -> None:
    r = _parse(adapter, _amostras(adapter).so_cabecalho())
    assert isinstance(r, EmptyFile)
    assert r.motivo and r.explicacao
    assert r.adapter_versao == adapter.version


def test_corrompido_levanta_arquivo_invalido(adapter: TelemetryAdapter) -> None:
    with pytest.raises(ArquivoInvalido):
        _parse(adapter, _amostras(adapter).corrompido())


def test_sem_infinito(adapter: TelemetryAdapter) -> None:
    s = _parse(adapter, _amostras(adapter).trabalho())
    assert isinstance(s, ParsedSession)
    numericas = s.amostras.select_dtypes("float64")
    assert not np.isinf(numericas.to_numpy()).any()
