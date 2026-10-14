import logging

from sistemacampero.infrastructure.parsers.jdl_parser import JohnDeereJDLParser
from sistemacampero.infrastructure.repositories import SpatialRepository

logger = logging.getLogger(__name__)


async def process_telemetry_file(file_path: str) -> None:
    """
    Caso de Uso: Processar ficheiro de telemetria em segundo plano.
    
    Args:
        file_path (str): Caminho absoluto para o ficheiro temporário recebido.
    """
    parser = JohnDeereJDLParser()
    spatial_repo = SpatialRepository()
    
    batch = []
    batch_size = 5000  # Tamanho ideal para inserção em massa na base de dados
    
    logger.info("Processamento de telemetria iniciado.")
    
    for reading in parser.parse_stream(file_path):
        # Regra: Descartar leituras sem GPS válido
        if not reading.has_valid_gps:
            continue
            
        # Regra: Derivar ID do talhão via PostGIS
        talhao_id = spatial_repo.get_talhao_id_by_coordinates(
            lat=reading.latitude,
            lon=reading.longitude
        )
        
        # Preparar registo para a base de dados
        record = {
            "machine_serial": reading.machine_serial,
            "timestamp": reading.timestamp,
            "talhao_id": talhao_id,
            "engine_on": reading.is_engine_on,
            "fuel_rate_lph": reading.fuel_rate_lph,
            "speed_kmh": reading.speed_kmh,
        }
        
        batch.append(record)
        
        # Inserção em lotes para otimização de I/O
        if len(batch) >= batch_size:
            # TODO: db_session.bulk_insert_mappings(TelemetryModel, batch)
            # db_session.commit()
            batch.clear()
            
    # Processar os registos remanescentes
    if batch:
        # TODO: Inserir o restante na base de dados
        pass
        
    logger.info("Processamento de telemetria concluído com sucesso.")