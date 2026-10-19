"""Leitura dos talhões do monitor Gen4: ``MasterData.xml`` + ``SpatialFiles/Boundary*.gjson``.

Só o contorno **externo** (``boundarytype == "Exterior"``) vira talhão. Os polígonos de
cabeceira gerados pelo monitor (``OffsetGeneratedExteriorHeadland``) não são talhões.
"""

from __future__ import annotations

import json
import logging
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from pyproj import Geod
from shapely.geometry import shape

from sistemacampero.domain.entities import FieldBoundary

logger = logging.getLogger(__name__)

_GEOD = Geod(ellps="WGS84")
_NAMESPACE = uuid.UUID("6f1d3c2e-5b0a-4c8e-9a47-2d7e1f9b3a10")
_SUFFIX = "-Contorno"


def _strip_namespaces(root: ET.Element) -> None:
    """Remove o namespace das tags (o MasterData.xml real declara ``xmlns``)."""
    for element in root.iter():
        if isinstance(element.tag, str) and "}" in element.tag:
            element.tag = element.tag.split("}", 1)[1]


def _guid(value: str | None) -> str | None:
    return value.strip("{}").lower() if value else None


def polygon_area_ha(geometry: dict) -> float:
    """Área geodésica (ha) de um polígono GeoJSON em WGS84."""
    return abs(_GEOD.geometry_area_perimeter(shape(geometry))[0]) / 10_000.0


def stable_field_id(external_guid: str) -> str:
    """UUID determinístico a partir do GUID do monitor (idempotência em reimportações)."""
    return str(uuid.uuid5(_NAMESPACE, external_guid))


class SpatialFilesFieldSource:
    """Fonte de talhões a partir da pasta ``Gen4`` exportada no pendrive."""

    def __init__(self, gen4_dir: Path) -> None:
        self._dir = Path(gen4_dir)

    def list_fields(self) -> list[FieldBoundary]:
        master = self._dir / "MasterData.xml"
        spatial = self._dir / "SpatialFiles"
        if not master.exists() or not spatial.is_dir():
            raise FileNotFoundError(f"MasterData.xml/SpatialFiles não encontrados em {self._dir}")
        root = ET.parse(master).getroot()
        _strip_namespaces(root)

        clients = {_guid(e.get("StringGuid")): e.get("Name") for e in root.iter("Client")}
        farms = {
            _guid(e.get("StringGuid")): (e.get("Name"), _guid(e.get("Client")))
            for e in root.iter("Farm")
            if e.get("StringGuid")
        }
        fields = {}
        for e in root.iter("Field"):
            guid = _guid(e.get("StringGuid"))
            if guid:
                fields[guid] = (e.get("Name"), _guid((e.findtext("Farm") or "").strip()))

        result: list[FieldBoundary] = []
        for boundary in root.iter("OperationalBoundary"):
            field_guid = _guid(boundary.get("TaggedEntity"))
            filename = boundary.findtext("Geometry/FilenameWithExtension")
            if field_guid not in fields or not filename:
                continue
            geometry = self._exterior_polygon(spatial / filename)
            if geometry is None:
                continue
            name, farm_guid = fields[field_guid]
            farm_name, client_guid = farms.get(farm_guid, (None, None))
            result.append(
                FieldBoundary(
                    id=stable_field_id(field_guid),
                    external_guid=field_guid,
                    name=name or boundary.get("Name", "").removesuffix(_SUFFIX),
                    farm=farm_name,
                    client=clients.get(client_guid),
                    geometry=geometry,
                    area_ha=round(polygon_area_ha(geometry), 3),
                )
            )
        logger.info("%d talhões com contorno em %s", len(result), self._dir)
        return result

    @staticmethod
    def _exterior_polygon(path: Path) -> dict | None:
        if not path.exists():
            logger.warning("arquivo de contorno ausente: %s", path.name)
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            geometry = feature.get("geometry", {})
            if props.get("boundarytype") == "Exterior" and geometry.get("type") == "Polygon":
                return geometry
        return None
