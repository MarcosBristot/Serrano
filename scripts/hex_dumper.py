import sys
from pathlib import Path

def gerar_hex_dump(file_path: str, num_bytes: int = 512) -> None:
    """
    Gera um Hex Dump dos primeiros bytes do arquivo para identificarmos
    visualmente o padrão exato de empacotamento (framing) da John Deere.
    """
    path = Path(file_path)
    if not path.exists():
        print(f"Arquivo não encontrado: {file_path}")
        return

    try:
        with open(path, "rb") as f:
            data = f.read(num_bytes)
            
        print(f"--- HEX DUMP: {path.name} ---")
        print("Offset(h)  00 01 02 03 04 05 06 07  08 09 0A 0B 0C 0D 0E 0F")
        print("-" * 65)
        
        for i in range(0, len(data), 16):
            chunk = data[i:i+16]
            hex_str = ""
            for j, b in enumerate(chunk):
                hex_str += f"{b:02X} "
                if j == 7:
                    hex_str += " "
            print(f"{i:08X}   {hex_str}")
            
    except Exception as e:
        print(f"Erro ao ler o arquivo: {e}")

if __name__ == "__main__":
    # Substitua pelo caminho do mesmo arquivo .jdl pequeno que você usou antes
    caminho_jdl = "C:\\Users\\Geral\\Desktop\\SistemaCampero\\SistemaCampero\\Trator JD\\JD-Data\\log\\2026_Aristides Klein_Agr. Sarmento-Klein_Sede\\2026_08_22_[10_39]_{a687d685-10cd-43d0-ac03-ef9e5b53e2c9}.jdl"
    gerar_hex_dump(caminho_jdl)