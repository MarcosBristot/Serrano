import numpy as np
import pandas as pd
from fastapi import FastAPI, File, UploadFile

# Importamos as lógicas que o Raul já fez (supondo que o arquivo original se chame testar_dados_trator.py)
from src.testar_dados_trator import (
    DESVIO_ALERTA_HECTARE,
    calcular_metricas_dia_talhao,
    converter_unidades,
    detectar_alerta_hectare,
    detectar_anomalia_combustivel,
    detectar_ociosidade,
    sanitizar_gps,
)

app = FastAPI(title="API Campero Sistemas", version="1.0.0")

@app.post("/api/v1/process-telemetry")
async def process_telemetry(
    leituras_file: UploadFile = File(...), 
    talhoes_file: UploadFile = File(...)
):
    # 1. Lê os arquivos do "pendrive" diretamente para a memória do servidor
    df_leituras = pd.read_csv(leituras_file.file, parse_dates=["timestamp"])
    df_talhoes = pd.read_csv(talhoes_file.file)

    # 2. Prepara os dados (mesma lógica do carregar_dados original)
    df = df_leituras.sort_values(["tractor_id", "timestamp"]).reset_index(drop=True)
    df["data"] = df["timestamp"].dt.date
    df = df.merge(df_talhoes, on="talhao_id", how="left")

    # 3. Roda o motor de sanitização e cálculo
    df = sanitizar_gps(df)
    df = converter_unidades(df)
    metricas = calcular_metricas_dia_talhao(df)

    # 4. Roda as regras de detecção de anomalias
    ociosidade_eventos = detectar_ociosidade(df)
    combustivel_eventos = detectar_anomalia_combustivel(df)
    eventos_hectare, baseline = detectar_alerta_hectare(metricas)

    # Limpeza para serialização JSON (trocando NaN do Pandas por None do Python)
    metricas = metricas.replace({np.nan: None})

    # 5. Monta a resposta JSON formatada
    return {
        "status": "sucesso",
        "resumo_operacional": metricas.to_dict(orient="records"),
        "alertas": {
            "pontos_gps_invalidos": int(df["gps_invalido"].sum()),
            "ociosidade": [
                {
                    "tractor_id": str(tractor_id),
                    "inicio": inicio.isoformat(),
                    "duracao_minutos": round(duracao, 2),
                    "mensagem": f"Motor ligado parado por {round(duracao)} min."
                }
                for tractor_id, inicio, duracao in ociosidade_eventos
            ],
            "queda_combustivel": [
                {
                    "tractor_id": str(tractor_id),
                    "quando": quando.isoformat(),
                    "litros_perdidos": round(queda, 2),
                    "mensagem": f"Queda abrupta de {round(queda, 2)}L detetada."
                }
                for tractor_id, quando, queda in combustivel_eventos
            ],
            "consumo_alto_hectare": [
                {
                    "tractor_id": str(tractor_id),
                    "data": str(data),
                    "talhao_id": talhao_id,
                    "litros_ha": round(valor, 2),
                    "mensagem": f"Consumo {int(DESVIO_ALERTA_HECTARE*100)}% acima do baseline da fazenda ({round(base, 2)} L/ha)."
                }
                for tractor_id, data, talhao_id, valor, base in eventos_hectare
            ] if baseline else []
        }
    }