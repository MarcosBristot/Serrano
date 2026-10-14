import logging
import struct
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")

def brute_force_scanner(caminho_arquivo: str):
    """
    Ignora qualquer formato ou cabeçalho. Varre a memória bruta do ficheiro
    à procura da representação exata em bytes das coordenadas de GPS.
    """
    path = Path(caminho_arquivo)
    if not path.exists():
        print(f"❌ Ficheiro não encontrado: {caminho_arquivo}")
        return

    with open(path, "rb") as f:
        data = f.read()

    print(f"\n--- A varrer {len(data)} bytes de memória bruta ---")
    encontrou_gps = False
    
    # Varremos o ficheiro byte a byte tentando ler grupos de 8 bytes como 'double'
    for i in range(len(data) - 7):
        try:
            valor = struct.unpack("<d", data[i:i+8])[0]
            
            # Filtro abrangente para a região de Marau, RS (Lat: -28.1, Lon: -52.9)
            if -28.5 < valor < -28.0:
                print(f"📍 [DOUBLE] LATITUDE encontrada no offset global {i}: {valor}")
                encontrou_gps = True
            elif -53.5 < valor < -52.5:
                print(f"📍 [DOUBLE] LONGITUDE encontrada no offset global {i}: {valor}")
                encontrou_gps = True
                
        except Exception:
            pass

    # Se não encontrar como double, vamos tentar como float (4 bytes)
    if not encontrou_gps:
        print("\nNenhum Double encontrado. A tentar como Float de 32 bits...")
        for i in range(len(data) - 3):
            try:
                valor = struct.unpack("<f", data[i:i+4])[0]
                if -28.5 < valor < -28.0:
                    print(f"📍 [FLOAT] LATITUDE encontrada no offset global {i}: {valor}")
                    encontrou_gps = True
                elif -53.5 < valor < -52.5:
                    print(f"📍 [FLOAT] LONGITUDE encontrada no offset global {i}: {valor}")
                    encontrou_gps = True
            except Exception:
                pass

    if not encontrou_gps:
        print("\n❌ Nenhuma coordenada de GPS encontrada em texto claro.")
        print("Possíveis causas:")
        print("1. O ficheiro escolhido não tem GPS (ex: pasta 'Teste').")
        print("2. A telemetria interna está fortemente compactada com Zlib.")

if __name__ == "__main__":
    # COLOQUE O CAMINHO EXATO DE UM FICHEIRO JDL REAL
    # Dica: Escolha um ficheiro maior que 10KB de um talhão real.
    caminho = r"C:\Users\Geral\Desktop\SistemaCampero\SistemaCampero\Trator JD\JD-Data\log\2026_Aristides Klein_Agr. Sarmento-Klein_Precis-o\2026_05_15_[12_20]_{1c21e07e-29a4-482b-8250-ff82c1ba1482}.jdl"
    brute_force_scanner(caminho)