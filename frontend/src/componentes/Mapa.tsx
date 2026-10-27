/** Mapa de satélite (MapLibre + Esri World Imagery) com camadas GeoJSON da Serrano. */
import maplibregl, { type LngLatBoundsLike, type Map as MapaML } from "maplibre-gl";
import { useEffect, useRef } from "react";

export type FC = GeoJSON.FeatureCollection;

export interface Camadas {
  talhoes?: FC; // polígonos com properties.nome
  calor?: FC; // hexágonos com properties.l_ha
  trilha?: FC; // linhas com properties.tipo (trabalho|parado) + pontos de parada
}

const ESTILO: maplibregl.StyleSpecification = {
  version: 8,
  glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
  sources: {
    satelite: {
      type: "raster",
      tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
      tileSize: 256,
      maxzoom: 19,
      attribution: "Imagens © Esri, Maxar, Earthstar Geographics",
    },
  },
  layers: [{ id: "satelite", type: "raster", source: "satelite" }],
};

const VAZIO: FC = { type: "FeatureCollection", features: [] };

function limites(fcs: (FC | undefined)[]): LngLatBoundsLike | null {
  let [x0, y0, x1, y1] = [Infinity, Infinity, -Infinity, -Infinity];
  const visitar = (c: unknown): void => {
    if (Array.isArray(c) && typeof c[0] === "number") {
      const [x, y] = c as number[];
      x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y);
    } else if (Array.isArray(c)) c.forEach(visitar);
  };
  for (const fc of fcs) for (const f of fc?.features ?? []) if (f.geometry && "coordinates" in f.geometry) visitar(f.geometry.coordinates);
  return Number.isFinite(x0) ? [[x0, y0], [x1, y1]] : null;
}

export function Mapa({ camadas, className = "h-[520px]", enquadrar = true }: { camadas: Camadas; className?: string; enquadrar?: boolean }) {
  const div = useRef<HTMLDivElement>(null);
  const mapa = useRef<MapaML | null>(null);
  const pronto = useRef(false);
  const ultimo = useRef<Camadas>(camadas);
  ultimo.current = camadas;

  const aplicar = () => {
    const m = mapa.current;
    if (!m || !pronto.current) return;
    const c = ultimo.current;
    (m.getSource("talhoes") as maplibregl.GeoJSONSource).setData(c.talhoes ?? VAZIO);
    (m.getSource("calor") as maplibregl.GeoJSONSource).setData(c.calor ?? VAZIO);
    (m.getSource("trilha") as maplibregl.GeoJSONSource).setData(c.trilha ?? VAZIO);
    const b = enquadrar ? limites([c.trilha, c.calor, c.talhoes]) : null;
    if (b) m.fitBounds(b, { padding: 48, maxZoom: 16, duration: 600 });
  };

  useEffect(() => {
    if (!div.current) return;
    const m = new maplibregl.Map({
      container: div.current,
      style: ESTILO,
      center: [-52.41, -28.26], // Passo Fundo
      zoom: 10,
      attributionControl: { compact: true },
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.on("load", () => {
      m.addSource("talhoes", { type: "geojson", data: VAZIO });
      m.addSource("calor", { type: "geojson", data: VAZIO });
      m.addSource("trilha", { type: "geojson", data: VAZIO });
      m.addLayer({
        id: "calor", type: "fill", source: "calor",
        paint: {
          "fill-color": ["interpolate", ["linear"], ["get", "l_ha"], 2, "#2f7030", 3.5, "#8fc78d", 4.5, "#ecc55a", 6, "#d6921f", 8, "#b91c1c"],
          "fill-opacity": 0.72,
        },
      });
      m.addLayer({ id: "talhoes-fundo", type: "fill", source: "talhoes", paint: { "fill-color": "#f9eecb", "fill-opacity": 0.08 } });
      m.addLayer({ id: "talhoes-borda", type: "line", source: "talhoes", paint: { "line-color": "#f9eecb", "line-width": 2.5 } });
      m.addLayer({
        id: "talhoes-nome", type: "symbol", source: "talhoes",
        layout: { "text-field": ["get", "nome"], "text-size": 13, "text-font": ["Open Sans Semibold"] },
        paint: { "text-color": "#fff", "text-halo-color": "#1c3b1f", "text-halo-width": 1.6 },
      });
      m.addLayer({
        id: "trilha", type: "line", source: "trilha", filter: ["==", ["geometry-type"], "LineString"],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": ["match", ["get", "tipo"], "trabalho", "#e6b034", "#ffffff"],
          "line-width": ["match", ["get", "tipo"], "trabalho", 3, 1.5],
          "line-opacity": 0.95,
        },
      });
      m.addLayer({
        id: "paradas", type: "circle", source: "trilha", filter: ["==", ["geometry-type"], "Point"],
        paint: { "circle-radius": 6, "circle-color": "#be123c", "circle-stroke-color": "#fff", "circle-stroke-width": 2 },
      });
      const popup = new maplibregl.Popup({ closeButton: false, offset: 8 });
      m.on("mousemove", "calor", (e) => {
        const p = e.features?.[0]?.properties;
        if (!p) return;
        popup.setLngLat(e.lngLat).setHTML(`<b>${Number(p.l_ha).toFixed(2).replace(".", ",")} L/ha</b><br/>${Number(p.area_ha).toFixed(2).replace(".", ",")} ha`).addTo(m);
      });
      m.on("mouseleave", "calor", () => popup.remove());
      m.on("click", "paradas", (e) => {
        const p = e.features?.[0]?.properties;
        if (p) new maplibregl.Popup().setLngLat(e.lngLat).setHTML(`<b>Parada de ${p.minutos} min</b><br/>${p.motor_ligado ? "motor ligado" : "motor desligado"}`).addTo(m);
      });
      pronto.current = true;
      aplicar();
    });
    mapa.current = m;
    return () => {
      pronto.current = false;
      m.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(aplicar, [camadas.talhoes, camadas.calor, camadas.trilha]);

  return <div ref={div} className={`overflow-hidden rounded-2xl ${className}`} />;
}

export function LegendaCalor() {
  return (
    <div className="flex items-center gap-2 text-xs text-folha-900/70">
      <span>L/ha</span>
      <div className="h-2 w-40 rounded-full" style={{ background: "linear-gradient(90deg,#2f7030,#8fc78d,#ecc55a,#d6921f,#b91c1c)" }} />
      <span>2</span><span className="text-folha-900/40">→</span><span>8+</span>
    </div>
  );
}
