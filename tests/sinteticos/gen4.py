"""MasterData.xml e Boundary.gjson SINTÉTICOS (estrutura do Gen4 10.30, dados fictícios)."""

from __future__ import annotations

import json

# ~2 km x 2 km ao redor do ponto inicial do gerador de .jdl (-28.10, -52.92).
QUADRADO = [
    [-52.93, -28.11],
    [-52.91, -28.11],
    [-52.91, -28.09],
    [-52.93, -28.09],
    [-52.93, -28.11],
]


def masterdata_xml(guid_talhao: str = "{TAL}", arquivo: str = "Boundary{b1}.gjson") -> bytes:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<SetupFile xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" language="pt">
 <SourceApp major="10" minor="30"/>
 <Setup>
  <Client Name="Cliente Teste" StringGuid="{{C1}}"/>
  <Farm Name="Fazenda Teste" StringGuid="{{F1}}" Client="{{C1}}"/>
  <Field Name="Talhao Teste" StringGuid="{guid_talhao}"><Farm>{{F1}}</Farm></Field>
  <Field Name="Sem Contorno" StringGuid="{{T2}}"><Farm>{{F1}}</Farm></Field>
  <Operator Name="Operador Teste" StringGuid="{{O1}}"><CurrentLicense>---</CurrentLicense></Operator>
  <Implement Name="Plantadeira Teste" StringGuid="{{I1}}" SerialNumber="">
   <ImplementDefinition><ImplementSettings>
    <PhysicalImplementWidth SourceUnit="m" Representation="vrPhysicalImplementWidth" Value="4.95"/>
   </ImplementSettings></ImplementDefinition>
  </Implement>
  <Implement Name="Por Linhas" StringGuid="{{I2}}" SerialNumber="">
   <ImplementDefinition><ImplementSettings>
    <ImplementWidth xsi:type="RowDistance">
     <Width SourceUnit="cm" Value="45.0"/><NumberOfRows SourceUnit="row" Value="10"/>
    </ImplementWidth>
   </ImplementSettings></ImplementDefinition>
  </Implement>
  <Machine Name="Tractor" SerialNumber="" StringGuid="{{M1}}"/>
  <OperationalBoundary TaggedEntity="{guid_talhao}" Name="Talhao Teste-Contorno" StringGuid="{{B1}}">
   <Geometry><FilenameWithExtension>{arquivo}</FilenameWithExtension><Path>./SpatialFiles/</Path></Geometry>
  </OperationalBoundary>
 </Setup>
</SetupFile>""".encode()


def gjson_boundary(anel: list[list[float]]) -> bytes:
    """FeatureCollection como a do monitor: Exterior + cabeceira gerada (que não é talhão)."""
    menor = [
        [x + (0.001 if x < -52.92 else -0.001), y + (0.001 if y < -28.10 else -0.001)]
        for x, y in anel
    ]
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"boundarytype": "OffsetGeneratedExteriorHeadland"},
                    "geometry": {"type": "Polygon", "coordinates": [menor]},
                },
                {
                    "type": "Feature",
                    "properties": {"boundarytype": "Exterior", "name": "Talhao Teste"},
                    "geometry": {"type": "Polygon", "coordinates": [anel]},
                },
            ],
        }
    ).encode()
