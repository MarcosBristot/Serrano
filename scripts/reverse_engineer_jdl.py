import logging
import struct
from pathlib import Path

# Configuração de logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

def extract_protobuf_payloads(file_path: str):
    """
    Lê o ficheiro .jdl, procura a estrutura [Marcador][Tamanho][Mensagem Protobuf]
    e imprime o conteúdo em bruto para mapearmos as tags reais.
    """
    path = Path(file_path)
    if not path.exists():
        logger.error(f"Ficheiro não encontrado: {file_path}")
        return

    with open(path, "rb") as f:
        data = f.read()

    offset = 0
    message_count = 0

    # Lógica de engenharia reversa para saltar o cabeçalho (aprox. os primeiros bytes com versão/serial)
    # Procuramos o padrão do bloco de dados
    while offset < len(data):
        try:
            # Assumimos que o bloco começa com um marcador de 1 byte e um tamanho de 4 bytes (Little Endian)
            # Pode ser necessário ajustar este offset dependendo de como a John Deere empacotou
            marker = data[offset]
            offset += 1

            if marker == 0x00: # Exemplo de byte marcador nulo, avançar
                continue

            # Lê o tamanho do bloco Protobuf (4 bytes)
            msg_size = struct.unpack("<I", data[offset:offset+4])[0]
            offset += 4

            # Se o tamanho for irreal, provavelmente estamos fora de sincronia
            if msg_size > 10000 or msg_size == 0:
                continue

            # Extrai o payload Protobuf
            payload = data[offset:offset+msg_size]
            offset += msg_size
            message_count += 1

            # Guarda do 10º ao 12º payload para saltar os cabeçalhos iniciais
            if 10 <= message_count <= 12:
                filename = f"amostra_limpa_{message_count}.pb"
                with open(filename, "wb") as out:
                    out.write(payload)
                logger.info(f"Payload {message_count} guardado em '{filename}'.")
                
            if message_count > 12:
                logger.info("Processo concluído. Teste os ficheiros no terminal com:")
                logger.info("protoc --decode_raw < amostra_limpa_10.pb")
                logger.info("protoc --decode_raw < amostra_limpa_11.pb")
                break

        except Exception as e:
            offset += 1 # Avança byte a byte se falhar a leitura

    logger.info("Análise concluída.")

if __name__ == "__main__":
    # Substitua pelo caminho de um ficheiro .jdl real e pequeno
    extract_protobuf_payloads("Trator JD\\JD-Data\\log\\2026_Aristides Klein_Agr. Sarmento-Klein_Sede\\2026_08_22_[10_39]_{f4b0c043-83f5-4c18-ad7a-fce57e373c54}.jdl")