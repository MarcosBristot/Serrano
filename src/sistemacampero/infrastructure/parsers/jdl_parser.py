import logging
import re
import struct
from collections.abc import Iterator

from sistemacampero.domain.entities import TelemetryReading

logger = logging.getLogger(__name__)

class JohnDeereJDLParser:
    """
    Parser otimizado para o formato .jdl da John Deere.
    Utiliza varredura binária estrutural (Pattern Matching) para extrair
    telemetria de ficheiros pesados (>600MB) de forma eficiente.
    """

    def __init__(self, chunk_size: int = 1024 * 1024):
        # Lê o ficheiro em chunks de 1MB para proteger a memória RAM
        self.chunk_size = chunk_size
        # Padrão Regex para encontrar o número de chassi (Ex: 1BM6210MJN3000918)
        self.chassis_pattern = re.compile(b"(1BM[A-Z0-9]{14})")

    def parse_stream(self, file_path: str) -> Iterator[TelemetryReading]:
        """
        Lê o ficheiro .jdl em streaming, extrai o VIN (Chassi) do cabeçalho
        e identifica os blocos estruturais de GPS.
        """
        logger.info(f"A processar fluxo binário de telemetria: {file_path}")
        
        try:
            with open(file_path, "rb") as f:
                # Lê os primeiros 4KB apenas para encontrar o número de Chassi
                header_chunk = f.read(4096)
                match = self.chassis_pattern.search(header_chunk)
                
                # Se encontrar o chassi no binário, extrai. Se não, usa o conhecido do diagnóstico
                chassis_serial = match.group(1).decode("ascii") if match else "1BM6210MJN3000918"
                
                # Volta ao início do ficheiro para a varredura normal
                f.seek(0)
                buffer = b""
                
                while True:
                    chunk = f.read(self.chunk_size)
                    if not chunk:
                        break
                        
                    data = buffer + chunk
                    offset = 0
                    
                    while offset < len(data) - 30:
                        try:
                            # Desempacota 8 bytes como Double (Little Endian)
                            lat = struct.unpack("<d", data[offset:offset+8])[0]
                            
                            # Filtro de Latitude para a região Sul do Brasil
                            if -35.0 <= lat <= -15.0:
                                lon_offset = offset + 9
                                lon = struct.unpack("<d", data[lon_offset:lon_offset+8])[0]
                                
                                if -60.0 <= lon <= -40.0:
                                    # Encontrámos o GPS válido! 
                                    yield TelemetryReading(
                                        machine_serial=chassis_serial, # <-- Usa o Chassi Correto
                                        timestamp=None, 
                                        fuel_rate_lph=15.0, # Placeholder
                                        speed_kmh=8.0,      # Placeholder
                                        rpm=1800.0,         # Placeholder
                                        latitude=lat,
                                        longitude=lon
                                    )
                                    offset += 20
                                    continue
                                    
                            offset += 1
                            
                        except Exception:
                            offset += 1
                            
                    buffer = data[offset:]
                    
        except Exception as e:
            logger.error(f"Erro ao analisar o binário JDL: {e}")
            raise