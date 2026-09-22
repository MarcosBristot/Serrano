"""
Script básico para testar os dados fictícios de telemetria do trator.
Reproduz, de forma simples, os passos discutidos na sprint:
  1) Leitura/sanitização de GPS (detectar saltos impossíveis)
  2) Cálculo de combustível/horímetro (litros consumidos, horas trabalhadas, litros/hora)
  3) Métricas por hectare (litros/hectare, horas/hectare) - cruzando com o cadastro de talhões
  4) Alertas de IA (regra simples): ociosidade, queda suspeita de combustível,
     e litros/hectare acima do baseline da fazenda
"""

import sys
from math import atan2, cos, radians, sin, sqrt

import pandas as pd

GALOES_PARA_LITROS = 3.78541

# limites simples (regras, não ML - suficiente para o MVP validar os dados)
VELOCIDADE_MAX_PLAUSIVEL_KMH = 40      # trator não anda mais rápido que isso
OCIOSIDADE_MIN_MINUTOS = 20            # motor ligado e parado por mais que isso = ociosidade a investigar
QUEDA_COMBUSTIVEL_SUSPEITA_L = 15      # queda entre leituras consecutivas maior que isso = suspeita
DESVIO_ALERTA_HECTARE = 0.3            # 30% acima do baseline da fazenda = alerta


def distancia_km(lat1, lon1, lat2, lon2):
    """Distância aproximada entre dois pontos (haversine)."""
    R = 6371
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def carregar_dados(caminho_leituras, caminho_talhoes):
    df = pd.read_csv(caminho_leituras, parse_dates = ["timestamp"])
    df = df.sort_values(["tractor_id", "timestamp"]).reset_index(drop=True)
    df["data"] = df["timestamp"].dt.date

    talhoes = pd.read_csv(caminho_talhoes)
    df = df.merge(talhoes, on = "talhao_id", how="left")
    if df["area_hectares"].isna().any():
        faltando = df[df["area_hectares"].isna()]["talhao_id"].unique()
        print(f"[Aviso] talhão sem área cadastrada, não vai entrar nas métricas por hectare: {list(faltando)}")
    return df


def sanitizar_gps(df):
    """Marca como inválida qualquer leitura que implique velocidade absurda em relação à anterior."""
    df["gps_invalido"] = False
    for tractor_id, grupo in df.groupby("tractor_id"):
        idx_anterior = None
        for idx, linha in grupo.iterrows():
            if idx_anterior is not None:
                anterior = df.loc[idx_anterior]
                dist_km = distancia_km(anterior["latitude"], anterior["longitude"], linha["latitude"], linha["longitude"])
                horas = (linha["timestamp"] - anterior["timestamp"]).total_seconds() / 3600
                velocidade_implicita = dist_km / horas if horas > 0 else 0
                if velocidade_implicita > VELOCIDADE_MAX_PLAUSIVEL_KMH:
                    df.at[idx, "gps_invalido"] = True
            idx_anterior = idx
    return df


def converter_unidades(df):
    df["fuel_level_l"] = (df["fuel_level_gal"] * GALOES_PARA_LITROS).round(2)
    return df


def detectar_ociosidade(df):
    """Agrupa sequências consecutivas de (engine ON, speed == 0) e mede a duração."""
    eventos = []
    for tractor_id, grupo in df.groupby("tractor_id"):
        grupo = grupo.reset_index(drop = True)
        em_ociosidade = False
        inicio = None
        for i, linha in grupo.iterrows():
            parado = linha["engine_status"] == "ON" and linha["speed_kmh"] == 0
            if parado and not em_ociosidade:
                em_ociosidade = True
                inicio = linha["timestamp"]
            elif not parado and em_ociosidade:
                em_ociosidade = False
                duracao_min = (linha["timestamp"] - inicio).total_seconds() / 60
                if duracao_min >= OCIOSIDADE_MIN_MINUTOS:
                    eventos.append((tractor_id, inicio, duracao_min))
        if em_ociosidade:
            duracao_min = (grupo.iloc[-1]["timestamp"] - inicio).total_seconds() / 60
            if duracao_min >= OCIOSIDADE_MIN_MINUTOS:
                eventos.append((tractor_id, inicio, duracao_min))
    return eventos


def detectar_anomalia_combustivel(df):
    eventos = []
    for tractor_id, grupo in df.groupby("tractor_id"):
        grupo = grupo.reset_index(drop = True)
        for i in range(1, len(grupo)):
            anterior = grupo.loc[i - 1, "fuel_level_l"]
            atual = grupo.loc[i, "fuel_level_l"]
            queda = anterior - atual
            if queda >= QUEDA_COMBUSTIVEL_SUSPEITA_L:
                eventos.append((tractor_id, grupo.loc[i, "timestamp"], round(queda, 2)))
    return eventos


def calcular_metricas_dia_talhao(df):
    """
    Para cada (trator, dia, talhão): combustível consumido no dia, horas trabalhadas
    (pelo horímetro), litros/hora e - cruzando com a área do talhão - litros/hectare
    e horas/hectare.
    """
    linhas = []
    for (tractor_id, data, talhao_id), grupo in df.groupby(["tractor_id", "data", "talhao_id"]):
        grupo = grupo.sort_values("timestamp")
        primeira, ultima = grupo.iloc[0], grupo.iloc[-1]

        combustivel_consumido_l = round(primeira["fuel_level_l"] - ultima["fuel_level_l"], 2)
        horas_trabalhadas = round(ultima["engine_hours"] - primeira["engine_hours"], 2)
        area_ha = primeira["area_hectares"]

        litros_por_hora = round(combustivel_consumido_l / horas_trabalhadas, 2) if horas_trabalhadas > 0 else None
        litros_por_hectare = round(combustivel_consumido_l / area_ha, 2) if pd.notna(area_ha) and area_ha > 0 else None
        horas_por_hectare = round(horas_trabalhadas / area_ha, 3) if pd.notna(area_ha) and area_ha > 0 else None

        linhas.append({
            "tractor_id": tractor_id,
            "data": data,
            "talhao_id": talhao_id,
            "area_hectares": area_ha,
            "combustivel_consumido_l": combustivel_consumido_l,
            "horas_trabalhadas": horas_trabalhadas,
            "litros_por_hora": litros_por_hora,
            "litros_por_hectare": litros_por_hectare,
            "horas_por_hectare": horas_por_hectare,
        })
    return pd.DataFrame(linhas)


def detectar_alerta_hectare(metricas):
    """Regra simples: litros/hectare acima de X% da mediana da fazenda (todos os registros) = alerta."""
    validos = metricas["litros_por_hectare"].dropna()
    if validos.empty:
        return [], None
    baseline = validos.median()
    limite = baseline * (1 + DESVIO_ALERTA_HECTARE)
    eventos = []
    for _, linha in metricas.iterrows():
        if pd.notna(linha["litros_por_hectare"]) and linha["litros_por_hectare"] > limite:
            eventos.append((linha["tractor_id"], linha["data"], linha["talhao_id"], linha["litros_por_hectare"], round(baseline, 2)))
    return eventos, baseline


def main():
    caminho_leituras = sys.argv[1] if len(sys.argv) > 1 else "data/dados_ficticios_trator_bruto.csv"
    caminho_talhoes = sys.argv[2] if len(sys.argv) > 2 else "data/talhoes.csv"

    df = carregar_dados(caminho_leituras, caminho_talhoes)
    print(f"Total de leituras carregadas: {len(df)}\n")

    df = sanitizar_gps(df)
    invalidos = df["gps_invalido"].sum()
    print(f"[1. Leitura/GPS] leituras marcadas como inválidas: {invalidos}")
    if invalidos:
        print(df[df["gps_invalido"]][["tractor_id", "timestamp", "latitude", "longitude"]].to_string(index=False))
    print()

    df = converter_unidades(df)
    print("[2. Combustível] amostra da conversão (galões -> litros):")
    print(df[["tractor_id", "timestamp", "fuel_level_gal", "fuel_level_l", "engine_hours"]].head(3).to_string(index=False))
    print()

    metricas = calcular_metricas_dia_talhao(df)
    print("[2/3. Combustível + horímetro + hectare] métricas por trator/dia/talhão:")
    print(metricas.to_string(index=False))
    print()

    print(f"[4. Alertas] ociosidade (>= {OCIOSIDADE_MIN_MINUTOS} min parado com motor ligado):")
    for tractor_id, inicio, duracao in detectar_ociosidade(df):
        print(f"  {tractor_id} | início {inicio} | duração {duracao:.0f} min")
    print()

    print(f"[4. Alertas] combustível (quedas >= {QUEDA_COMBUSTIVEL_SUSPEITA_L} L entre leituras):")
    for tractor_id, quando, queda in detectar_anomalia_combustivel(df):
        print(f"  {tractor_id} | {quando} | queda de {queda} L")
    print()

    eventos_hectare, baseline = detectar_alerta_hectare(metricas)
    if baseline is not None:
        print(f"[4. Alertas] litros/hectare acima de {int(DESVIO_ALERTA_HECTARE*100)}% do baseline da fazenda ({baseline:.2f} L/ha):")
        for tractor_id, data, talhao_id, valor, base in eventos_hectare:
            print(f"  {tractor_id} | {data} | {talhao_id} | {valor} L/ha (baseline {base} L/ha)")


if __name__ == "__main__":
    main()
