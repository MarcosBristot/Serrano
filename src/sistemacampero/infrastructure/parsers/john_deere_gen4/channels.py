"""Mapeia canais do JDL (por DDI + unidade) para as colunas do schema universal.

Validado no dump real de 2026 (trator 6210, monitor Gen4 10.x), já com as âncoras:
  * 561 km/h -> velocidade; bate com a velocidade derivada da trilha GPS (razão 0,996-1,000);
  * 99 L/h   -> vazão; ~3 L/h em marcha lenta, ~20-40 L/h sob carga;
  * 100 L    -> contador acumulado de combustível (resolução 0,5 L);
  * 247 h    -> horímetro;
  * 271 RPM, 2109 % (torque; o offset -125 já vem no cabeçalho).
O DDI 560 aparece duas vezes (km/h no grupo "Deere Tractor Data" e sem unidade no HLC):
a unidade decide.
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

# Contadores ("seguram" o valor entre amostras) vs. grandezas instantâneas.
COUNTER_COLUMNS = {"fuel_total_l", "engine_hours"}

# Sem estas não há métrica de combustível/horas: o diagnóstico avisa.
ESSENCIAIS = ("speed_kmh", "fuel_rate_lph", "engine_rpm", "engine_hours", "fuel_total_l")
