"""
Gera arquivos CSV fictícios simulando a exportação via pendrive de duas
marcas diferentes, com "dialetos" (nomes de coluna, unidades) propositalmente
diferentes entre si — para servirem de fixture no desenvolvimento dos
adapters (Etapa 2 do pipeline), sem depender de arquivos reais.

Uso:
    python scripts/gerar_arquivos_brutos_ficticios.py
Gera os arquivos em ./dados_ficticios/brutos/
"""

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

SAIDA = Path(__file__).parent.parent / "dados_ficticios" / "brutos"
SAIDA.mkdir(parents=True, exist_ok=True)

random.seed(42)

# Área aproximada da região de Passo Fundo / Não-Me-Toque (RS)
LAT_BASE, LON_BASE = -28.30, -52.60


def _ponto_aleatorio():
    return (
        round(LAT_BASE + random.uniform(-0.15, 0.15), 6),
        round(LON_BASE + random.uniform(-0.20, 0.20), 6),
    )


def gerar_arquivo_john_deere(maquina_id: str, n_linhas: int = 200) -> Path:
    """Dialeto John Deere: colunas em inglês, combustível em % do tanque,
    horímetro acumulado, timestamp ISO."""
    caminho = SAIDA / f"john_deere_{maquina_id}.csv"
    inicio = datetime(2026, 9, 1, 7, 0, 0)
    horimetro = round(random.uniform(500, 3000), 1)
    fuel_pct = 100.0

    with caminho.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["MachineID", "Timestamp", "Latitude", "Longitude",
             "EngineHours", "FuelLevelPercent", "Speed_kmh"]
        )
        momento = inicio
        for _ in range(n_linhas):
            lat, lon = _ponto_aleatorio()
            horimetro += round(random.uniform(0.01, 0.05), 3)
            fuel_pct = max(0.0, fuel_pct - random.uniform(0.05, 0.4))
            velocidade = round(random.uniform(0, 12), 1)
            writer.writerow(
                [maquina_id, momento.isoformat(), lat, lon,
                 round(horimetro, 2), round(fuel_pct, 1), velocidade]
            )
            momento += timedelta(minutes=1)

    return caminho


def gerar_arquivo_nh(maquina_id: str, n_linhas: int = 200) -> Path:
    """Dialeto nh: colunas diferentes, combustível já em litros consumidos
    (não em %), timestamp separado em data e hora, velocidade em m/s."""
    caminho = SAIDA / f"nh_{maquina_id}.csv"
    inicio = datetime(2026, 9, 1, 7, 0, 0)
    horas_motor = round(random.uniform(500, 3000), 1)
    litros_consumidos_total = 0.0

    with caminho.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["Equipment_ID", "Date", "Time", "GPS_Lat", "GPS_Lon",
             "HourMeter", "FuelConsumption_L", "Velocity_ms"]
        )
        momento = inicio
        for _ in range(n_linhas):
            lat, lon = _ponto_aleatorio()
            horas_motor += round(random.uniform(0.01, 0.05), 3)
            litros_consumidos_total += round(random.uniform(0.02, 0.3), 3)
            velocidade_ms = round(random.uniform(0, 3.3), 2)  # m/s (~0-12 km/h)
            writer.writerow(
                [maquina_id, momento.date().isoformat(), momento.time().isoformat(),
                 lat, lon, round(horas_motor, 2),
                 round(litros_consumidos_total, 2), velocidade_ms]
            )
            momento += timedelta(minutes=1)

    return caminho


if __name__ == "__main__":
    arquivos = [
        gerar_arquivo_john_deere("JD-0001"),
        gerar_arquivo_john_deere("JD-0002"),
        gerar_arquivo_nh("nh-0001"),
        gerar_arquivo_nh("nh-0002"),
    ]
    for caminho in arquivos:
        print(f"Gerado: {caminho}")
