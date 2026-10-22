"""Etapa 2 do pipeline: sanitização do dado já no schema universal.

Nunca altera o bruto. Valores fisicamente impossíveis viram NaN e são contados no
relatório (persistido com a sessão, para auditoria). Também deriva ``engine_on`` quando
o fabricante não o informa, cruzando RPM, vazão e horímetro: uma fonte ausente ou
quebrada não zera mais o "motor ligado" (defeito 1 do M0).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SANITIZER_VERSION = "3"  # 3: engine_on por RPM -> vazão -> horímetro

# Limites físicos plausíveis para um trator agrícola.
LIMITES: dict[str, tuple[float, float]] = {
    "speed_kmh": (0.0, 40.0),
    "speed_alt_kmh": (0.0, 40.0),
    "engine_rpm": (0.0, 3500.0),
    "engine_load_pct": (0.0, 125.0),
    "fuel_rate_lph": (0.0, 90.0),
    "fuel_level_l": (0.0, 2000.0),
}
CONTADORES = ("engine_hours", "fuel_total_l")

RPM_MOTOR_LIGADO = 400.0
VAZAO_MOTOR_LIGADO_LPH = 0.5  # motor desligado não consome
JANELA_HORIMETRO_S = 300  # horímetro avançou em ±5 min -> motor ligado nesse trecho
VAZAO_INCOERENTE_LPH = 5.0  # RPM diz desligado, mas vazão acima disto


def derivar_motor_ligado(df: pd.DataFrame) -> tuple[pd.Series, dict[str, int]]:
    """``engine_on`` informado; senão RPM; senão vazão; senão horímetro; senão False."""
    informado = df["engine_on"].astype("boolean")
    rpm, vazao, horas = df["engine_rpm"], df["fuel_rate_lph"], df["engine_hours"]

    por_rpm = (rpm > RPM_MOTOR_LIGADO).astype("boolean").mask(rpm.isna())
    por_vazao = (vazao > VAZAO_MOTOR_LIGADO_LPH).astype("boolean").mask(vazao.isna())
    janela = 2 * JANELA_HORIMETRO_S + 1
    variacao = (
        horas.rolling(janela, center=True, min_periods=1).max()
        - horas.rolling(janela, center=True, min_periods=1).min()
    )
    por_horimetro = (variacao > 0).astype("boolean").mask(variacao.isna())

    resultado = informado.copy()
    fontes: dict[str, int] = {"motor_fonte_informado": int(informado.notna().sum())}
    for nome, serie in (("rpm", por_rpm), ("vazao", por_vazao), ("horimetro", por_horimetro)):
        vaga = resultado.isna() & serie.notna()
        fontes[f"motor_fonte_{nome}"] = int(vaga.sum())
        resultado = resultado.mask(vaga, serie)
    fontes["motor_fonte_nenhuma"] = int(resultado.isna().sum())

    incoerente = (rpm <= RPM_MOTOR_LIGADO) & (vazao > VAZAO_INCOERENTE_LPH)
    fontes["motor_rpm_vazao_incoerente"] = int(incoerente.sum())
    return resultado.fillna(False).astype(bool), fontes


def sanitizar(amostras: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    df = amostras.copy()
    relatorio: dict[str, int] = {}
    total_medidas = 0
    descartadas = 0

    for col, (lo, hi) in LIMITES.items():
        presentes = df[col].notna()
        ruim = presentes & ((df[col] < lo) | (df[col] > hi))
        relatorio[f"{col}_fora_do_limite"] = int(ruim.sum())
        total_medidas += int(presentes.sum())
        descartadas += int(ruim.sum())
        df.loc[ruim, col] = np.nan

    for col in CONTADORES:
        presentes = df[col].notna()
        total_medidas += int(presentes.sum())
        # 0 = contador ainda não reportado pelo barramento (não é "zero litros").
        zerado = presentes & (df[col] <= 0)
        relatorio[f"{col}_zerado_nao_reportado"] = int(zerado.sum())
        df.loc[zerado, col] = np.nan
        # Contador acumulado não diminui: queda = reset/ruído -> invalida o ponto.
        ruim = df[col].notna() & (df[col] < df[col].cummax() - 1e-9)
        relatorio[f"{col}_nao_monotonico"] = int(ruim.sum())
        descartadas += int(ruim.sum())  # "não reportado ainda" não é dado ruim
        df.loc[ruim, col] = np.nan
        df[col] = df[col].ffill()

    df["engine_on"], fontes = derivar_motor_ligado(df)
    relatorio.update(fontes)
    relatorio["amostras"] = int(len(df))
    relatorio["amostras_com_gps"] = int(df["gps_valid"].sum())
    relatorio["amostras_motor_ligado"] = int(df["engine_on"].sum())
    relatorio["descartadas_por_mil"] = (
        round(1000 * descartadas / total_medidas) if total_medidas else 0
    )
    return df, relatorio
