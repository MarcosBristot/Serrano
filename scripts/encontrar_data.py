import struct
from pathlib import Path

def procurar_timestamp(caminho_arquivo: str):
    with open(caminho_arquivo, "rb") as f:
        data = f.read()

    print("A procurar a Data/Hora (Timestamp UNIX) perto do GPS...")
    
    # Vamos varrer o ficheiro novamente
    for i in range(len(data) - 30):
        try:
            lat = struct.unpack("<d", data[i:i+8])[0]
            if -28.5 < lat < -28.0:
                # O GPS está aqui! Vamos procurar inteiros (4 bytes) ao redor deste ponto
                # que representem datas entre 2020 e 2030 (timestamps entre 1500000000 e 1900000000)
                
                print(f"\n📍 GPS encontrado no offset {i}")
                
                # Procura 20 bytes para trás e 30 bytes para a frente
                for j in range(i - 20, i + 30):
                    try:
                        possivel_tempo = struct.unpack("<I", data[j:j+4])[0]
                        if 1600000000 < possivel_tempo < 1900000000:
                            from datetime import datetime
                            data_real = datetime.fromtimestamp(possivel_tempo)
                            print(f"⏰ POSSÍVEL DATA encontrada no offset {j} (Distância: {j - i} bytes): {data_real}")
                    except Exception:
                        pass
                break # Analisa apenas o primeiro GPS para não poluir o terminal
        except Exception:
            pass

if __name__ == "__main__":
    # Substitua pelo caminho do ficheiro que acabou de testar
    caminho = r"C:\Users\Geral\Desktop\SistemaCampero\SistemaCampero\Trator JD\JD-Data\log\2026_Aristides Klein_Agr. Sarmento-Klein_Coxilha Grande\2026_05_23_[09_13]_{e65367d9-d651-41a8-80c8-441e809defc4}.jdl"
    procurar_timestamp(caminho)