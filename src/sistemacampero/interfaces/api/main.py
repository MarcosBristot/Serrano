import os
import re
import shutil
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from supabase import Client, create_client

from sistemacampero.infrastructure.parsers.jdl_parser import JohnDeereJDLParser
from sistemacampero.infrastructure.repositories import SpatialRepository

# Carrega as variáveis do ficheiro .env
load_dotenv()

# Inicialização do FastAPI
app = FastAPI(title="Sistema Serrano - API de Telemetria")

# Cliente Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("As variáveis SUPABASE_URL e SUPABASE_KEY devem estar definidas no ficheiro .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

class TelemetryResponse(BaseModel):
    latitude: float
    longitude: float
    speed_kmh: float
    fuel_rate_lph: float
    engine_on: bool

def processar_arquivo_jdl(file_path: str):
    """
    Função executada em background: lê o binário, extrai a data real,
    cruza as coordenadas com o PostGIS e insere os dados em lotes no Supabase.
    """
    parser = JohnDeereJDLParser()
    repo = SpatialRepository(supabase)
    
    # Extração da data a partir do nome do ficheiro gerado pelo monitor
    nome_ficheiro = os.path.basename(file_path)
    match_data = re.search(r"(\d{4}_\d{2}_\d{2})_\[(\d{2}_\d{2})\]", nome_ficheiro)
    
    timestamp_operacao = datetime.now(ZoneInfo("America/Sao_Paulo"))
    if match_data:
        data_str = match_data.group(1)
        hora_str = match_data.group(2)
        try:
            timestamp_operacao = datetime.strptime(f"{data_str} {hora_str}", "%Y_%m_%d %H_%M")
            timestamp_operacao = timestamp_operacao.replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
        except Exception as e:
            print(f"Aviso: Não foi possível converter a data do ficheiro: {e}")

    try:
        leituras_para_inserir = []
        total_inserido = 0
        
        print(f"A iniciar extração de {nome_ficheiro} com data {timestamp_operacao}...")
        
        for leitura in parser.parse_stream(file_path):
            talhao_id = repo.get_talhao_id_by_coordinates(leitura.latitude, leitura.longitude)
            
            leituras_para_inserir.append({
                "machine_serial": leitura.machine_serial,
                "timestamp": timestamp_operacao.isoformat(), # Grava a data real do trator!
                "talhao_id": talhao_id,
                "latitude": leitura.latitude,
                "longitude": leitura.longitude,
                "speed_kmh": leitura.speed_kmh,
                "fuel_rate_lph": leitura.fuel_rate_lph,
                "engine_on": True
            })
            
            # Inserção otimizada em lotes
            if len(leituras_para_inserir) >= 2000:
                supabase.table("telemetria").insert(leituras_para_inserir).execute()
                total_inserido += len(leituras_para_inserir)
                print(f"Progresso: {total_inserido} pontos já guardados no Supabase...")
                leituras_para_inserir.clear()
        
        # Insere o remanescente
        if leituras_para_inserir:
            supabase.table("telemetria").insert(leituras_para_inserir).execute()
            total_inserido += len(leituras_para_inserir)
            
        print(f"✅ Processamento concluído! Total: {total_inserido} pontos inseridos para o ficheiro {nome_ficheiro}.")
    except Exception as e:
        print(f"❌ Erro crítico no processamento de {nome_ficheiro}: {e}")

@app.post("/api/v1/telemetry/upload")
async def upload_telemetry(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Recebe o ficheiro .jdl pesado e envia-o para processamento em segundo plano.
    """
    os.makedirs("data/temp", exist_ok=True)
    file_path = f"data/temp/{file.filename}"
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    background_tasks.add_task(processar_arquivo_jdl, file_path)
    
    return {"message": "Upload concluído. Processamento espacial e binário em segundo plano iniciado."}

@app.get("/api/v1/telemetry/machine/{machine_serial}", response_model=List[TelemetryResponse])
async def get_machine_telemetry(
    machine_serial: str,
    talhao_id: Optional[str] = None,
    limit: int = Query(1000, description="Limite de pontos para não travar o frontend")
):
    """
    Retorna os pontos de telemetria para o frontend desenhar a rota no mapa.
    """
    query = supabase.table("telemetria").select("latitude, longitude, speed_kmh, fuel_rate_lph, engine_on")
    query = query.eq("machine_serial", machine_serial)
    
    if talhao_id:
        query = query.eq("talhao_id", talhao_id)
        
    response = query.limit(limit).execute()
    
    if not response.data:
        raise HTTPException(status_code=404, detail="Nenhum dado encontrado para esta máquina.")
        
    return response.data

@app.get("/api/v1/telemetry/stats/{machine_serial}")
async def get_machine_statistics(machine_serial: str):
    """
    Retorna estatísticas consolidadas (KPIs) para os dashboards do frontend.
    """
    response = supabase.table("telemetria").select("speed_kmh, fuel_rate_lph, engine_on").eq("machine_serial", machine_serial).execute()
    
    data = response.data
    if not data:
        raise HTTPException(status_code=404, detail="Sem dados.")

    pontos_motor_ligado = sum(1 for d in data if d['engine_on'])
    pontos_ocioso = sum(1 for d in data if d['engine_on'] and d['speed_kmh'] < 1.0)
    media_consumo = sum(d['fuel_rate_lph'] for d in data) / len(data) if data else 0

    return {
        "machine_serial": machine_serial,
        "total_leituras": len(data),
        "percentual_ociosidade": round((pontos_ocioso / pontos_motor_ligado * 100), 2) if pontos_motor_ligado else 0,
        "consumo_medio_lph": round(media_consumo, 2)
    }