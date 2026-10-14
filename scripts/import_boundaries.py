import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List  # noqa: UP035

from supabase import Client, create_client

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Configurações do Supabase (idealmente carregadas de variáveis de ambiente)
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://zfyycybubllaxhqveaid.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpmeXljeWJ1YmxsYXhocXZlYWlkIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc5MDcxMzUwOSwiZXhwIjoyMTA2Mjg5NTA5fQ.FobQUa3qT0XBxR02q6p4OQt3pB5B3b7OyjQRkfVs1dI")

# Diretório onde os arquivos .gjson foram extraídos
SPATIAL_FILES_DIR = Path("Trator JD/Gen4/SpatialFiles")


def get_supabase_client() -> Client:
    """Inicializa e retorna o cliente do Supabase."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("Credenciais do Supabase não encontradas nas variáveis de ambiente.")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def parse_johndeere_geojson(file_path: Path) -> List[Dict[str, Any]]:
    """
    Lê um arquivo .gjson da John Deere e extrai as features que contêm os polígonos.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Os arquivos John Deere geralmente usam o padrão FeatureCollection
    features = data.get("features", [])
    boundaries = []

    for feature in features:
        # Filtra apenas geometrias de área (Boundary)
        geom_type = feature.get("geometry", {}).get("type")
        if geom_type in ("Polygon", "MultiPolygon"):
            boundaries.append(feature)

    return boundaries


def import_boundaries_to_supabase() -> None:
    """
    Varre a pasta de arquivos espaciais, extrai os polígonos e insere no Supabase.
    """
    if not SPATIAL_FILES_DIR.exists():
        logger.error(f"Diretório não encontrado: {SPATIAL_FILES_DIR}")
        return

    supabase = get_supabase_client()
    gjson_files = list(SPATIAL_FILES_DIR.glob("*.gjson"))
    
    logger.info(f"Encontrados {len(gjson_files)} arquivos .gjson para processamento.")

    for file_path in gjson_files:
        logger.info(f"A processar: {file_path.name}")
        
        try:
            boundaries = parse_johndeere_geojson(file_path)
            
            if not boundaries:
                logger.warning(f"Nenhum polígono encontrado em {file_path.name}. A ignorar.")
                continue

            for boundary in boundaries:
                props = boundary.get("properties", {})
                
                # Monta o payload mapeando as propriedades do GeoJSON para as colunas do banco
                payload = {
                    "nome": props.get("Name", file_path.stem),
                    "fazenda": props.get("Farm", "Desconhecida"),
                    "cliente": props.get("Client", "Desconhecido"),
                    # O Supabase converte automaticamente este dict GeoJSON para geometry no PostGIS
                    "geometria": boundary.get("geometry") 
                }

                # Executa o INSERT
                response = supabase.table("talhoes").insert(payload).execute()
                
                if response.data:
                    logger.info(f"Talhão inserido com sucesso: {payload['nome']}")
                    
        except Exception as e:
            logger.error(f"Erro ao importar {file_path.name}: {str(e)}")

    logger.info("Processo de importação finalizado.")


if __name__ == "__main__":
    import_boundaries_to_supabase()