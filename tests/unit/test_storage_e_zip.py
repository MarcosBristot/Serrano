from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest

from sistemacampero.domain.errors import Invalido
from sistemacampero.domain.ingestao import TipoArquivo, nome_para_exibicao, tipo_do_arquivo
from sistemacampero.domain.services.zip_seguro import LimitesZip, expandir
from sistemacampero.infrastructure.persistence.ingestao import backoff_s
from sistemacampero.infrastructure.storage.local import ArmazenamentoLocal
from sistemacampero.infrastructure.storage.supabase import ArmazenamentoSupabase, ErroStorage


# ------------------------------------------------------------------ local
def test_storage_local_ida_e_volta(tmp_path: Path) -> None:
    s = ArmazenamentoLocal(tmp_path)
    s.gravar("brutos", "org/abc.jdl", io.BytesIO(b"dados"), "application/octet-stream")
    assert s.existe("brutos", "org/abc.jdl")
    assert s.ler("brutos", "org/abc.jdl") == b"dados"
    destino = io.BytesIO()
    s.copiar_para("brutos", "org/abc.jdl", destino)
    assert destino.getvalue() == b"dados"
    assert s.url_assinada("brutos", "org/abc.jdl", 60).startswith("local://brutos/org/abc.jdl?")
    s.apagar("brutos", "org/abc.jdl")
    assert not s.existe("brutos", "org/abc.jdl")
    with pytest.raises(FileNotFoundError):
        s.ler("brutos", "org/abc.jdl")


@pytest.mark.parametrize("caminho", ["../fora", "org/../../x", "/abs", "org/a b", "org\\x"])
def test_storage_local_recusa_caminho_perigoso(tmp_path: Path, caminho: str) -> None:
    with pytest.raises(ValueError):
        ArmazenamentoLocal(tmp_path).gravar("brutos", caminho, io.BytesIO(b"x"), "x")


# ------------------------------------------------------------------ supabase
def _supabase(handler):  # type: ignore[no-untyped-def]
    return ArmazenamentoSupabase(
        "https://proj.supabase.co",
        "sb_secret_teste",
        httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_storage_supabase_rotas_e_cabecalhos() -> None:
    vistos: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        vistos.append(req)
        if req.url.path.endswith("/object/sign/brutos/org/a.jdl"):
            return httpx.Response(200, json={"signedURL": "/object/sign/brutos/org/a.jdl?token=t"})
        if req.method == "HEAD" and "inexistente" in req.url.path:
            return httpx.Response(404)
        return httpx.Response(200, content=b"conteudo")

    s = _supabase(handler)
    s.gravar("brutos", "org/a.jdl", io.BytesIO(b"x" * 10), "application/octet-stream")
    assert s.ler("brutos", "org/a.jdl") == b"conteudo"
    assert s.existe("brutos", "org/a.jdl") and not s.existe("brutos", "org/inexistente.jdl")
    assert s.url_assinada("brutos", "org/a.jdl", 60) == (
        "https://proj.supabase.co/storage/v1/object/sign/brutos/org/a.jdl?token=t"
    )
    s.apagar("brutos", "org/a.jdl")

    up = vistos[0]
    assert up.url.path == "/storage/v1/object/brutos/org/a.jdl"
    assert up.headers["apikey"] == "sb_secret_teste"
    assert "authorization" not in up.headers  # chave nova não é JWT
    assert up.headers["x-upsert"] == "true"
    assert vistos[1].url.path == "/storage/v1/object/authenticated/brutos/org/a.jdl"
    assert json.loads(vistos[-1].content) == {"prefixes": ["org/a.jdl"]}


def test_storage_supabase_erro_nao_vaza_chave() -> None:
    s = _supabase(lambda _r: httpx.Response(500, text="sb_secret_teste eco"))
    with pytest.raises(ErroStorage) as exc:
        s.gravar("brutos", "org/a.jdl", io.BytesIO(b"x"), "x")
    assert "sb_secret" not in str(exc.value)


# ------------------------------------------------------------------ zip
def _zip(entradas: dict[str, bytes], compressao: int = zipfile.ZIP_DEFLATED) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compressao) as zf:
        for nome, dados in entradas.items():
            zf.writestr(nome, dados)
    buf.seek(0)
    return buf


def test_zip_expande_so_o_que_interessa() -> None:
    z = _zip(
        {
            "Trator/JD-Data/log/a.jdl": b"\x0d" + b"1" * 50,
            "Trator/Gen4/MasterData.xml": b"<Root/>",
            "Trator/Gen4/SpatialFiles/Boundary{x}.gjson": b"{}",
            "Trator/Run_Pages/foto.png": b"png",
            "Trator/interno.zip": b"PK",
        }
    )
    entradas = list(expandir(z))
    assert sorted((e.tipo, e.nome) for e in entradas) == [
        (TipoArquivo.GJSON, "Boundary{x}.gjson"),
        (TipoArquivo.JDL, "a.jdl"),
        (TipoArquivo.MASTERDATA, "MasterData.xml"),
    ]


@pytest.mark.parametrize(
    "nome", ["../../etc/passwd.jdl", "/abs/a.jdl", "C:/win/a.jdl", "a/../../b.jdl"]
)
def test_zip_slip_recusado(nome: str) -> None:
    with pytest.raises(Invalido) as exc:
        list(expandir(_zip({nome: b"\x0dx"})))
    assert exc.value.codigo == "ZIP_CAMINHO_INSEGURO"


def test_zip_bomba_recusada() -> None:
    bomba = _zip({"a.jdl": b"\x00" * 5_000_000})
    with pytest.raises(Invalido) as exc:
        list(expandir(bomba))
    assert exc.value.codigo == "ZIP_BOMBA"


def test_zip_limites_de_tamanho_e_quantidade() -> None:
    with pytest.raises(Invalido):
        list(
            expandir(
                _zip({"a.jdl": b"\x0d" * 2000}, zipfile.ZIP_STORED),
                LimitesZip(max_entrada_bytes=1000),
            )
        )
    with pytest.raises(Invalido):
        list(expandir(_zip({f"{i}.jdl": b"\x0d" for i in range(5)}), LimitesZip(max_entradas=3)))


def test_zip_corrompido() -> None:
    with pytest.raises(Invalido) as exc:
        list(expandir(io.BytesIO(b"PK\x03\x04 lixo")))
    assert exc.value.codigo == "ZIP_INVALIDO"


# ------------------------------------------------------------------ nomes e backoff
def test_nome_do_cliente_nunca_vira_caminho() -> None:
    assert nome_para_exibicao("../../etc/passwd") == "passwd"
    assert (
        nome_para_exibicao("C:\\x\\2026_05_22_[09_11]_{106a}.jdl")
        == "2026_05_22_[09_11]_{106a}.jdl"
    )
    assert "\n" not in nome_para_exibicao("a\nb.jdl")
    assert tipo_do_arquivo("x/MASTERDATA.XML") is TipoArquivo.MASTERDATA
    assert tipo_do_arquivo("a.JDL") is TipoArquivo.JDL
    assert tipo_do_arquivo("a.exe") is None


def test_backoff_exponencial_com_teto_e_jitter() -> None:
    assert backoff_s(1, 0.5) == pytest.approx(30)
    assert backoff_s(3, 0.5) == pytest.approx(120)
    assert backoff_s(20, 0.5) == pytest.approx(3600)
    assert backoff_s(1, 0.0) == pytest.approx(24)
    assert backoff_s(1, 1.0) == pytest.approx(36)
