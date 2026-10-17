"""Mapeia canais do JDL (por DDI + unidade) para as colunas do schema universal.

Validado nos dados reais (trator 6210 (serial omitido), monitor Gen4 10.30):
  * 561 km/h   -> velocidade; confere com o GPS (~8-9 km/h em plantio);
  * 99 L/h     -> vazão; ~3 L/h em marcha lenta, ~20-40 L/h sob carga;
  * 100 L      -> contador acumulado de combustível; a diferença do contador em uma
                 sessão de 15,3 h (335 L) bate com a integral da vazão (~22 L/h × 15,3 h);
  * 247 h      -> horímetro; 15,35 h numa sessão de 15,3 h;
  * 271 RPM, 2109 % (torque, offset -125 já vem no cabeçalho).
"""

from __future__ import annotations

# DDI -> (coluna do schema universal, unidade esperada no cabeçalho)
DDI_TO_COLUMN: dict[int, tuple[str, str]] = {
    561: ("speed_kmh", "km1hr-1"),
    560: ("speed_alt_kmh", "km1hr-1"),
    99: ("fuel_rate_lph", "l1hr-1"),
    100: ("fuel_total_l", "l"),
    247: ("engine_hours", "hr"),
    271: ("engine_rpm", "RPM"),
    2109: ("engine_load_pct", "prcnt"),
}

# Grupos de canais que carregam o dado do trator (ignora canais de implemento/ISOBUS).
TRACTOR_GROUPS = {"Deere Tractor Data", "HLC"}

# Valor "não disponível" do barramento: inteiro 32 bits com sinal mínimo.
RAW_NA = -(2**31)

# Colunas que são contadores (valor "segura" entre amostras) vs. grandezas instantâneas.
COUNTER_COLUMNS = {"fuel_total_l", "engine_hours"}
