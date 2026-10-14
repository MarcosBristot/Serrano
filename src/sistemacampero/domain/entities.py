from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class TelemetryReading:
    """
    Entidade de domínio que representa uma leitura individual de telemetria do trator.
    """
    machine_serial: str
    timestamp: datetime
    fuel_rate_lph: float  # Alterado de fuel_level para vazão (litros/hora)
    speed_kmh: float
    rpm: Optional[float] = None
    fuel_level: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    @property
    def is_engine_on(self) -> bool:
        """
        Deriva o estado do motor (ligado/desligado) com base no RPM ou velocidade.
        """
        if self.rpm is not None:
            return self.rpm > 0.0
        return self.speed_kmh > 0.0

    @property
    def has_valid_gps(self) -> bool:
        """
        Verifica se a leitura possui coordenadas GPS válidas.
        """
        return self.latitude is not None and self.longitude is not None