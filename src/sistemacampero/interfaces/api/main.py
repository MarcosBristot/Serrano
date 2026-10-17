import os
import shutil
from pathlib import Path
from typing import List, Optional

import pandas as pd
from dotenv import load_dotenv
from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    HTTPException,
    Query,
    UploadFile,
)
from pydantic import BaseModel
from supabase import Client, create_client

# Importações do motor matemático e limpeza (Frente B - Claude)
from sistemacampero.adapters.john_deere_gen4 import JohnDeereGen4Adapter

# Importação da infraestrutura espacial (Frente A)
from sistemacampero.infrastructure.repositories import SpatialRepository
from sistemacampero.processing.clean import sanitize

# Carrega as variáveis de ambiente (.env)
load_dotenv()

app = FastAPI(title="Sistema Campero - API de Telemetria")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("As variáveis SUPABASE_URL e SUPABASE_KEY devem estar definidas no ficheiro .env")

# Inicializa o cliente do Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

class TelemetryResponse(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    speed_kmh: Optional[float] = None
    fuel_rate_lph: Optional[float] = None
    engine_rpm: Optional[float] = None
    engine_on: bool

def processar_arquivo_jdl(file_path: str, marca: str, tecnologia: str):
    """
    Lê o JDL selecionando o adaptador correto baseado na marca e tecnologia,
    limpa os dados absurdos, cruza geograficamente no PostGIS e salva no Supabase
    garantindo que não haverá duplicações (upsert).
    """
    # 1. Roteamento de adaptadores
    if marca.lower() == "john deere" and "gen4" in tecnologia.lower():
        adapter = JohnDeereGen4Adapter()
    else:
        print(f"⚠️ Adaptador para {marca} ({tecnologia}) ainda não implementado. Ignorando ficheiro.")
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass
        return

    repo = SpatialRepository(supabase)
    
    try:
        # Extração profunda com o adaptador selecionado
        session = adapter.parse(Path(file_path))
        
        # Sanitização (Transforma valores irreais em NaN)
        cleaned_df, quality = sanitize(session.samples)
        
        if cleaned_df.empty:
            print(f"⚠️ O ficheiro {session.source_file} não possui amostras válidas.")
            return

        print(f"🚀 Extração {marca} {tecnologia} iniciada: {session.source_file} | Amostras a 1Hz: {len(cleaned_df)}")

        leituras_para_inserir = []
        total_inserido = 0
        
        # Função auxiliar para tratar NaNs do Pandas para inserção na base de dados (NULL)
        def get_val(val):
            return float(val) if pd.notna(val) else None

        # Varre o DataFrame gerado
        for index, row in cleaned_df.iterrows():
            lat = get_val(row['lat'])
            lon = get_val(row['lon'])
            
            # Inteligência PostGIS (Apenas se o trator tiver sinal de satélite)
            talhao_id = None
            if lat is not None and lon is not None:
                talhao_id = repo.get_talhao_id_by_coordinates(lat, lon)
                
            # Prepara os dados exatos lidos dos sensores
            leituras_para_inserir.append({
                "machine_serial": session.machine.serial,
                "timestamp": row['ts'].isoformat(),
                "talhao_id": talhao_id,
                "latitude": lat,
                "longitude": lon,
                "speed_kmh": get_val(row['speed_kmh']),
                "speed_alt_kmh": get_val(row['speed_alt_kmh']),
                "engine_rpm": get_val(row['engine_rpm']),
                "engine_load_pct": get_val(row['engine_load_pct']),
                "fuel_rate_lph": get_val(row['fuel_rate_lph']),
                "fuel_total_l": get_val(row['fuel_total_l']),
                "engine_hours": get_val(row['engine_hours']),
                "engine_on": bool(row['engine_on']) if pd.notna(row['engine_on']) else False
            })
            
            # Gravação rápida em lotes de 2000 registos usando UPSERT
            if len(leituras_para_inserir) >= 2000:
                supabase.table("telemetria").upsert(
                    leituras_para_inserir, 
                    on_conflict="machine_serial, timestamp"
                ).execute()
                total_inserido += len(leituras_para_inserir)
                print(f"Progresso: {total_inserido} pontos sincronizados com a nuvem...")
                leituras_para_inserir.clear()
        
        # Grava os últimos remanescentes com UPSERT
        if leituras_para_inserir:
            supabase.table("telemetria").upsert(
                leituras_para_inserir, 
                on_conflict="machine_serial, timestamp"
            ).execute()
            total_inserido += len(leituras_para_inserir)
            
        print(f"✅ Sucesso! {total_inserido} leituras reais inseridas de {session.source_file}.")

    except Exception as e:
        print(f"❌ Erro crítico no ficheiro {file_path}: {e}")
    finally:
        # Resolve a dívida técnica da limpeza do disco
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"🗑️ Ficheiro temporário removido.")
        except Exception as e:
            print(f"Aviso ao remover ficheiro temporário: {e}")

@app.get("/")
async def root():
    return {"message": "API do Sistema Campero operando com sucesso! Aceda a /docs para testar."}

@app.post("/api/v1/telemetry/upload")
async def upload_telemetry(
    background_tasks: BackgroundTasks, 
    marca: str = Query("John Deere", description="Ex: John Deere"),
    tecnologia: str = Query("Gen4", description="Ex: Gen4"),
    file: UploadFile = File(...)
):
    """
    Recebe um arquivo por vez. 
    O frontend oficial fará o envio em lote chamando esta rota várias vezes em paralelo.
    """
    os.makedirs("data/temp", exist_ok=True)
    
    file_path = f"data/temp/{file.filename}"
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Passa a marca e a tecnologia para a função que roda em segundo plano
    background_tasks.add_task(processar_arquivo_jdl, file_path, marca, tecnologia)
        
    return {"message": f"Upload do arquivo {file.filename} ({marca} - {tecnologia}) concluído. Extração em segundo plano iniciada!"}

@app.get("/api/v1/telemetry/machine/{machine_serial}", response_model=List[TelemetryResponse])
async def get_machine_telemetry(
    machine_serial: str,
    limit: int = Query(1000)
):
    query = supabase.table("telemetria").select("latitude, longitude, speed_kmh, fuel_rate_lph, engine_rpm, engine_on")
    query = query.eq("machine_serial", machine_serial)
    
    # Filtra apenas pontos com GPS válido para desenhar no mapa
    query = query.not_.is_("latitude", "null")
    response = query.limit(limit).execute()
    
    if not response.data:
        raise HTTPException(status_code=404, detail="Sem dados geográficos para esta máquina.")
    return response.data

@app.get("/api/v1/telemetry/stats/{machine_serial}")
async def get_machine_statistics(machine_serial: str):
    response = supabase.table("telemetria").select("speed_kmh, fuel_rate_lph, engine_on").eq("machine_serial", machine_serial).execute()
    data = response.data
    if not data:
        raise HTTPException(status_code=404, detail="Sem dados para estatísticas.")

    pontos_motor_ligado = sum(1 for d in data if d['engine_on'])
    pontos_ocioso = sum(1 for d in data if d['engine_on'] and (d.get('speed_kmh') or 0) < 1.0)
    
    consumos_validos = [d['fuel_rate_lph'] for d in data if d.get('fuel_rate_lph') is not None]
    media_consumo = sum(consumos_validos) / len(consumos_validos) if consumos_validos else 0

    return {
        "machine_serial": machine_serial,
        "percentual_ociosidade": round((pontos_ocioso / pontos_motor_ligado * 100), 2) if pontos_motor_ligado else 0,
        "consumo_medio_lph": round(media_consumo, 2)
    }