"""Sanitização, métricas, qualidade e regras (sem I/O)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sistemacampero.application.processamento import ProcessadorDeArquivo, ResultadoSessao
from sistemacampero.domain.errors import Invalido
from sistemacampero.domain.services import rules
from sistemacampero.domain.services.sanitization import sanitizar
from sistemacampero.domain.telemetry import EmptyFile, ParseContext
from sistemacampero.infrastructure.parsers.registry import RegistroAdapters, registro_padrao
from tests.sinteticos.jdl_builder import Cenario, construir


def _processar(c: Cenario) -> ResultadoSessao:
    r = ProcessadorDeArquivo(registro_padrao()).processar(construir(c), ParseContext("s.jdl"))
    assert isinstance(r, ResultadoSessao)
    return r


def test_metricas_de_uma_sessao_de_plantio() -> None:
    r = _processar(Cenario(minutos=30, plantio=True))
    m = r.metricas
    assert m is not None
    assert m.litros_integral == pytest.approx(11.0, rel=0.01)  # 22 L/h x 0,5 h
    assert m.distancia_trabalho_km == pytest.approx(4.0, rel=0.01)  # 8 km/h x 0,5 h
    assert m.area_estimada_ha == pytest.approx(4.0 * 4.95 / 10, rel=0.01)
    # Linha reta sem passadas repetidas: cobertura ~ estimada, sobreposição ~ 0.
    assert m.area_metodo == "cobertura"
    assert m.area_cobertura_ha == pytest.approx(m.area_estimada_ha, rel=0.01)
    assert m.sobreposicao_pct == pytest.approx(0, abs=0.5)
    assert m.l_ha == pytest.approx(m.litros_integral / m.area_cobertura_ha)
    assert m.ocioso_h == 0 and m.cobertura_gps == 1.0
    assert r.sessao.metadados.operacao == "plantio"
    assert r.qualidade.score == 100


def test_sanitizacao_limites_e_contador_zerado() -> None:
    r = _processar(Cenario(minutos=2, velocidade_kmh=lambda _t: 95.0, contador_comeca_zero=True))
    assert r.limpo["speed_kmh"].isna().all()
    assert r.sanitizacao["speed_kmh_fora_do_limite"] > 0
    assert r.sanitizacao["fuel_total_l_zerado_nao_reportado"] > 0
    assert (r.limpo["fuel_total_l"].dropna() > 11000).all()


def test_sentinela_nao_disponivel_vira_nan_e_nao_zero() -> None:
    r = _processar(Cenario(minutos=2, nao_disponivel=frozenset({"engine_load_pct"})))
    assert r.limpo["engine_load_pct"].isna().all()


def test_regra_ociosidade() -> None:
    r = _processar(
        Cenario(
            minutos=25,
            velocidade_kmh=lambda _t: 0.0,
            vazao_lph=lambda _t: 3.2,
            rpm=lambda _t: 900,
            gps="nenhum",
        )
    )
    ocio = [a for a in r.alertas if a.tipo == "ociosidade"]
    assert len(ocio) == 1 and ocio[0].valor == pytest.approx(25, abs=1)
    assert ocio[0].detalhes["litros"] == pytest.approx(3.2 * 25 / 60, rel=0.05)
    assert "sem_gps" in [a.tipo for a in r.alertas]


def test_regra_vazao_alta_contra_linha_de_base() -> None:
    proc = ProcessadorDeArquivo(registro_padrao())
    dados = construir(Cenario(minutos=30, vazao_lph=lambda _t: 30.0))
    r = proc.processar(dados, ParseContext("s.jdl"), linha_base_vazao_lph=20.0)
    assert isinstance(r, ResultadoSessao)
    assert [a.tipo for a in r.alertas] == ["vazao_alta"]
    r2 = proc.processar(dados, ParseContext("s.jdl"), linha_base_vazao_lph=float("nan"))
    assert isinstance(r2, ResultadoSessao) and r2.alertas == []


def test_nenhuma_regra_dispara_com_nan() -> None:
    n = 3600
    df = pd.DataFrame(
        {
            "ts": pd.date_range("2026-01-01", periods=n, freq="s", tz="UTC"),
            "lat": np.nan,
            "lon": np.nan,
            "gps_valid": False,
            "speed_kmh": np.nan,
            "speed_alt_kmh": np.nan,
            "engine_rpm": np.nan,
            "engine_load_pct": np.nan,
            "fuel_rate_lph": np.nan,
            "fuel_total_l": np.nan,
            "fuel_level_l": np.nan,
            "engine_hours": np.nan,
            "engine_on": pd.array([pd.NA] * n, dtype="boolean"),
        }
    )
    limpo, _ = sanitizar(df)
    cfg = rules.ConfigRegras()
    assert rules.ociosidade("x", limpo, cfg) == []
    assert rules.vazao_alta("x", limpo, cfg, 20.0) == []
    assert rules.gps_salto("x", limpo, cfg) == []


def test_l_ha_alto_entre_sessoes() -> None:
    t = pd.Timestamp("2026-04-30", tz="UTC").to_pydatetime()
    comb = ("serial", "plantadeira", "plantio")
    sessoes = [rules.ResumoSessao(f"s{i}", comb, 4.0, t, t) for i in range(5)]
    sessoes.append(rules.ResumoSessao("fora", comb, 6.0, t, t))
    sessoes.append(rules.ResumoSessao("nan", comb, float("nan"), t, t))
    alertas = rules.l_ha_alto(sessoes, rules.ConfigRegras())
    assert [a.chave_sessao for a in alertas] == ["fora"]


def test_impressao_digital_estavel_e_versao_da_config() -> None:
    t = pd.Timestamp("2026-04-30 10:00", tz="UTC").to_pydatetime()
    a = rules.Alerta("ociosidade", "atencao", "sha", "m", inicio=t)
    b = rules.Alerta("ociosidade", "alto", "sha", "outra mensagem", inicio=t, valor=3)
    assert a.impressao_digital == b.impressao_digital
    assert rules.ConfigRegras().versao != rules.ConfigRegras(ociosidade_min_minutos=30).versao


def test_arquivo_so_cabecalho_vira_vazio_explicado() -> None:
    r = ProcessadorDeArquivo(registro_padrao()).processar(
        construir(Cenario(minutos=1, so_cabecalho=True)), ParseContext("s.jdl")
    )
    assert isinstance(r, EmptyFile) and r.motivo == "sem_blocos_de_dados"


def test_gps_zerado_nao_vira_posicao() -> None:
    r = _processar(Cenario(minutos=2, gps="zero"))
    assert not r.limpo["gps_valid"].any()
    assert r.sessao.diagnostico.fonte_posicao == "nenhuma"


def test_registro_escolhe_por_marca_ou_deteccao() -> None:
    reg = registro_padrao()
    head = construir(Cenario(minutos=1))[:64]
    assert reg.escolher(head, ParseContext("a.jdl", "John Deere", "Gen4")).brand == "john_deere"
    assert reg.escolher(head, ParseContext("a.jdl")).technology == "gen4"
    with pytest.raises(Invalido) as exc:
        reg.escolher(head, ParseContext("a.jdl", "case", "afs"))
    assert exc.value.codigo == "FORMATO_NAO_SUPORTADO"
    with pytest.raises(Invalido) as exc:
        reg.escolher(b"PK\x03\x04", ParseContext("a.zip", "john_deere", "gen4"))
    assert exc.value.codigo == "FORMATO_NAO_CONFERE"
    with pytest.raises(ValueError, match="duplicado"):
        RegistroAdapters(reg.todos() + reg.todos())


def test_fragmento_curto_tem_um_problema_so() -> None:
    r = _processar(
        Cenario(minutos=0.5, omitir=frozenset({"engine_rpm"}), contador_comeca_zero=True)
    )
    assert [p.codigo for p in r.qualidade.problemas] == ["SESSAO_CURTA"]
    assert r.qualidade.score == 70
    assert r.sanitizacao["descartadas_por_mil"] == 0  # contador "ainda não reportado" não conta
