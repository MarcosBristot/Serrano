"""Cadastro exportado pelo monitor Gen4: ``MasterData.xml`` + ``SpatialFiles/*.gjson``.

Estrutura verificada no pendrive de 2026 (GS4 10.30): ``SetupFile/Setup`` com ``Client``,
``Farm`` (``Client=`` guid), ``Field`` (filho ``<Farm>`` guid), ``OperationalBoundary``
(``TaggedEntity`` = guid do talhão, ``Geometry/FilenameWithExtension``), ``Implement``
(``PhysicalImplementWidth`` em m) e ``Operator``. Máquinas vêm com ``SerialNumber`` vazio
e não são importadas: a máquina nasce pelo serial do ``.jdl``.

Só o contorno ``boundarytype == "Exterior"`` vira talhão; as cabeceiras geradas pelo
monitor (``OffsetGeneratedExteriorHeadland``) não.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from sistemacampero.domain.cadastro import (
    FazendaImportada,
    ImplementoImportado,
    ImportacaoCadastro,
    OperadorImportado,
    TalhaoImportado,
)
from sistemacampero.domain.errors import Invalido
from sistemacampero.domain.services.geo import normalizar_contorno
from sistemacampero.domain.telemetry import normalizar_guid

MAX_XML_BYTES = 50 * 1024**2


def _sem_namespace(root: ET.Element) -> None:
    for e in root.iter():
        if isinstance(e.tag, str) and "}" in e.tag:
            e.tag = e.tag.split("}", 1)[1]


def _parse_seguro(xml: bytes) -> ET.Element:
    if len(xml) > MAX_XML_BYTES:
        raise Invalido("MasterData.xml grande demais.", codigo="MASTERDATA_INVALIDO")
    cabeca = xml[:4096].upper()
    # Sem DTD: bloqueia expansão de entidades (billion laughs) e entidades externas.
    if b"<!DOCTYPE" in cabeca or b"<!ENTITY" in xml.upper():
        raise Invalido("MasterData.xml com DTD não é aceito.", codigo="MASTERDATA_INVALIDO")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise Invalido(f"MasterData.xml inválido: {exc}", codigo="MASTERDATA_INVALIDO") from exc
    _sem_namespace(root)
    return root


def _nome(e: ET.Element) -> str | None:
    n = (e.get("Name") or "").strip()
    return n[:200] or None


def _largura(implemento: ET.Element) -> float | None:
    fisica = implemento.find(".//PhysicalImplementWidth")
    try:
        if fisica is not None and fisica.get("SourceUnit", "m") == "m":
            v = float(fisica.get("Value", ""))
            return v if 0 < v < 100 else None
    except ValueError:
        pass
    largura = implemento.find(".//ImplementWidth/Width")
    linhas = implemento.find(".//ImplementWidth/NumberOfRows")
    try:
        if largura is not None and linhas is not None and largura.get("SourceUnit") == "cm":
            v = float(largura.get("Value", "")) / 100 * float(linhas.get("Value", ""))
            return v if 0 < v < 100 else None
    except ValueError:
        pass
    return None


def ler_cadastro_gen4(xml: bytes, gjson_por_nome: dict[str, bytes]) -> ImportacaoCadastro:
    """``gjson_por_nome``: nome do arquivo (``Boundary{guid}.gjson``) -> conteúdo."""
    root = _parse_seguro(xml)
    out = ImportacaoCadastro()
    clientes = {normalizar_guid(e.get("StringGuid")): _nome(e) for e in root.iter("Client")}
    for e in root.iter("Farm"):
        guid, nome = normalizar_guid(e.get("StringGuid")), _nome(e)
        if guid and nome:  # o <Farm> filho de <Field> não tem StringGuid
            out.fazendas.append(
                FazendaImportada(guid, nome, clientes.get(normalizar_guid(e.get("Client"))))
            )

    arquivos = {nome.lower(): dados for nome, dados in gjson_por_nome.items()}
    contornos: dict[str, bytes] = {}
    for b in root.iter("OperationalBoundary"):
        talhao = normalizar_guid(b.get("TaggedEntity"))
        arquivo = (b.findtext("Geometry/FilenameWithExtension") or "").strip().lower()
        if not talhao or not arquivo:
            continue
        if arquivo in arquivos:
            contornos[talhao] = arquivos[arquivo]
        else:
            out.avisos.append(f"contorno {arquivo} citado no MasterData não veio no pendrive")

    for e in root.iter("Field"):
        guid, nome = normalizar_guid(e.get("StringGuid")), _nome(e)
        if not guid or not nome:
            continue
        geometria = None
        if guid in contornos:
            try:
                geometria = normalizar_contorno(json.loads(contornos[guid]))
            except (Invalido, ValueError) as exc:
                out.avisos.append(f"contorno do talhão {nome} ignorado: {exc}")
        out.talhoes.append(
            TalhaoImportado(guid, nome, normalizar_guid(e.findtext("Farm")), geometria)
        )

    for e in root.iter("Implement"):
        guid, nome = normalizar_guid(e.get("StringGuid")), _nome(e)
        if guid and nome:
            out.implementos.append(ImplementoImportado(guid, nome, _largura(e)))
    for e in root.iter("Operator"):
        guid, nome = normalizar_guid(e.get("StringGuid")), _nome(e)
        if guid and nome:
            out.operadores.append(OperadorImportado(guid, nome))
    return out
