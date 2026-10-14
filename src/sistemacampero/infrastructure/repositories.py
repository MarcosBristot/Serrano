import logging
from typing import Optional

from supabase import Client

logger = logging.getLogger(__name__)

class SpatialRepository:
    """
    Repositório responsável pelas consultas geoespaciais no PostGIS via Supabase.
    """

    def __init__(self, supabase_client: Client):
        """
        Inicializa o repositório com o cliente Supabase injetado.
        """
        self.supabase = supabase_client

    def get_talhao_id_by_coordinates(self, lat: float, lon: float) -> Optional[str]:
        """
        Verifica em qual polígono (Boundary) a coordenada se encontra.
        
        Args:
            lat (float): Latitude recebida da telemetria.
            lon (float): Longitude recebida da telemetria.
            
        Returns:
            Optional[str]: O UUID do talhão, se a coordenada estiver dentro de um limite.
                           Retorna None se o trator estiver fora dos talhões mapeados.
        """
        try:
            # Invoca a função RPC criada no Supabase
            response = self.supabase.rpc(
                "get_talhao_by_point", 
                {"lat": lat, "lon": lon}
            ).execute()
            
            # response.data conterá o UUID retornado pelo PostgreSQL ou None
            return response.data if response.data else None
            
        except Exception as e:
            logger.error(f"Erro ao consultar talhão para as coordenadas ({lat}, {lon}): {e}")
            return None