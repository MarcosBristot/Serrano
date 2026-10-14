import subprocess
import sys
import zlib


def decodificar_payload(arquivo_pb):
    with open(arquivo_pb, "rb") as f:
        data = f.read()

    # Tenta descompactar caso a John Deere tenha comprimido o bloco
    try:
        data = zlib.decompress(data)
        print("✅ Sucesso: O pacote estava compactado com zlib e foi descompactado!\n")
    except zlib.error:
        # Se falhar, significa que já está em formato bruto (não-compactado)
        pass

    # Executa o protoc injetando os bytes diretamente, fugindo do erro do terminal
    process = subprocess.run(
        [sys.executable, "-m", "grpc_tools.protoc", "--decode_raw"],
        input=data,
        capture_output=True
    )

    if process.stdout:
        print("=== ESTRUTURA REVELADA ===")
        print(process.stdout.decode(errors='replace'))
    
    if process.stderr:
        print("=== ERROS/AVISOS ===")
        print(process.stderr.decode(errors='replace'))

if __name__ == "__main__":
    # Testando o arquivo 11 (você pode testar o 10 ou 12 também mudando o nome aqui)
    decodificar_payload("amostra_limpa_11.pb")