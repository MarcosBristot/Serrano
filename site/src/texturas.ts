/** Texturas procedurais (sem arquivos externos) e ajustes de shader compartilhados. */
import * as THREE from "three";

// ----------------------------------------------------------------- ruído
export function aleatorio(semente: number) {
  let a = semente >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hash(x: number, y: number, s: number) {
  let h = Math.imul(x, 374761393) + Math.imul(y, 668265263) + Math.imul(s, 982451653);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
}

/** Ruído de valor que repete a cada `p` unidades (textura sem emenda). */
function ruido(x: number, y: number, p: number, s: number) {
  const xi = Math.floor(x);
  const yi = Math.floor(y);
  const xf = x - xi;
  const yf = y - yi;
  const u = xf * xf * (3 - 2 * xf);
  const v = yf * yf * (3 - 2 * yf);
  const m = (a: number) => ((a % p) + p) % p;
  const a = hash(m(xi), m(yi), s);
  const b = hash(m(xi + 1), m(yi), s);
  const c = hash(m(xi), m(yi + 1), s);
  const d = hash(m(xi + 1), m(yi + 1), s);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
}

export function fbm(x: number, y: number, periodo: number, oitavas: number, s = 0) {
  let t = 0;
  let amp = 0.5;
  let f = 1;
  let n = 0;
  for (let i = 0; i < oitavas; i++) {
    t += amp * ruido(x * f, y * f, periodo * f, s + i);
    n += amp;
    amp *= 0.5;
    f *= 2;
  }
  return t / n;
}

function tela(l: number, a = l) {
  const c = document.createElement("canvas");
  c.width = l;
  c.height = a;
  return { c, g: c.getContext("2d", { willReadFrequently: true })! };
}

function normalDeAltura(altura: Uint8ClampedArray, n: number, forca: number) {
  const { c, g } = tela(n);
  const img = g.createImageData(n, n);
  const H = (x: number, y: number) => altura[(((y + n) % n) * n + ((x + n) % n)) * 4] / 255;
  for (let y = 0; y < n; y++) {
    for (let x = 0; x < n; x++) {
      const dx = (H(x + 1, y) - H(x - 1, y)) * forca;
      const dy = (H(x, y + 1) - H(x, y - 1)) * forca;
      const inv = 1 / Math.sqrt(dx * dx + dy * dy + 1);
      const k = (y * n + x) * 4;
      img.data[k] = (-dx * inv * 0.5 + 0.5) * 255;
      img.data[k + 1] = (dy * inv * 0.5 + 0.5) * 255;
      img.data[k + 2] = (inv * 0.5 + 0.5) * 255;
      img.data[k + 3] = 255;
    }
  }
  g.putImageData(img, 0, 0);
  return c;
}

// ----------------------------------------------------------------- solo com palha
/** Latossolo vermelho do planalto gaúcho coberto de palha (plantio direto). Um ladrilho = 4 m. */
export function texturaSolo(n = 1024) {
  const cor = tela(n);
  const alt = tela(n);
  const ic = cor.g.createImageData(n, n);
  const ia = alt.g.createImageData(n, n);
  const P = 8;
  for (let y = 0; y < n; y++) {
    for (let x = 0; x < n; x++) {
      const u = (x / n) * P;
      const v = (y / n) * P;
      const mancha = fbm(u, v, P, 4, 1);
      const grumo = fbm(u * 6, v * 6, P * 6, 3, 7);
      const k = (y * n + x) * 4;
      const luz = 0.62 + mancha * 0.5 + (grumo - 0.5) * 0.35;
      ic.data[k] = Math.min(255, 104 * luz);
      ic.data[k + 1] = Math.min(255, 56 * luz);
      ic.data[k + 2] = Math.min(255, 40 * luz);
      ic.data[k + 3] = 255;
      const h = 60 + grumo * 110 + mancha * 30;
      ia.data[k] = ia.data[k + 1] = ia.data[k + 2] = h;
      ia.data[k + 3] = 255;
    }
  }
  cor.g.putImageData(ic, 0, 0);
  alt.g.putImageData(ia, 0, 0);

  const rnd = aleatorio(42);
  cor.g.lineCap = alt.g.lineCap = "round";
  for (let i = 0; i < 6500; i++) {
    const x = rnd() * n;
    const y = rnd() * n;
    const ang = rnd() * Math.PI;
    const len = 10 + rnd() * 46;
    const w = 1 + rnd() * 2.6;
    const tom = rnd();
    const c =
      tom < 0.55 ? [205 + rnd() * 30, 178 + rnd() * 30, 118 + rnd() * 30]
      : tom < 0.85 ? [160 + rnd() * 25, 136 + rnd() * 22, 92 + rnd() * 20]
      : [112 + rnd() * 20, 92 + rnd() * 15, 64];
    const alfa = 0.5 + rnd() * 0.45;
    const dx = (Math.cos(ang) * len) / 2;
    const dy = (Math.sin(ang) * len) / 2;
    for (const ox of [-n, 0, n]) {
      for (const oy of [-n, 0, n]) {
        const px = x + ox;
        const py = y + oy;
        if (px < -len || px > n + len || py < -len || py > n + len) continue;
        cor.g.strokeStyle = `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${alfa})`;
        cor.g.lineWidth = w;
        cor.g.beginPath();
        cor.g.moveTo(px - dx, py - dy);
        cor.g.lineTo(px + dx, py + dy);
        cor.g.stroke();
        alt.g.strokeStyle = `rgba(255,255,255,${alfa * 0.7})`;
        alt.g.lineWidth = w;
        alt.g.beginPath();
        alt.g.moveTo(px - dx, py - dy);
        alt.g.lineTo(px + dx, py + dy);
        alt.g.stroke();
      }
    }
  }

  const altura = alt.g.getImageData(0, 0, n, n).data;
  const mapa = new THREE.CanvasTexture(cor.c);
  mapa.colorSpace = THREE.SRGBColorSpace;
  const normal = new THREE.CanvasTexture(normalDeAltura(altura, n, 4));
  for (const t of [mapa, normal]) {
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.anisotropy = 16;
  }
  return { mapa, normal };
}

// ----------------------------------------------------------------- faixa recém-plantada
export const FAIXA = { largura: 4.8, ladrilho: 2.4, linhas: 9, espaco: 0.5 };

/** Sulcos das 9 linhas e rastro dos pneus traseiros (transparente; vai por cima do solo). */
export function texturaSulcos() {
  const L = 512;
  const A = 256;
  const { c, g } = tela(L, A);
  const pxm = L / FAIXA.largura;
  const X = (m: number) => (m + FAIXA.largura / 2) * pxm;
  const rnd = aleatorio(7);

  for (const cx of [-1.15, 1.15]) {
    const w = 0.62 * pxm;
    g.fillStyle = "rgba(48,26,16,0.32)";
    g.fillRect(X(cx) - w / 2, 0, w, A);
    // marcas das garras em V
    for (let y = 0; y < A; y += 13) {
      g.fillStyle = "rgba(22,12,8,0.38)";
      for (const lado of [-1, 1]) {
        g.save();
        g.translate(X(cx) + (lado * w) / 4, y + (lado > 0 ? 6 : 0));
        g.rotate(lado * 0.5);
        g.fillRect(-w / 4, -2.5, w / 2, 5);
        g.restore();
      }
    }
  }
  for (let i = 0; i < FAIXA.linhas; i++) {
    const cx = X(-2 + i * FAIXA.espaco);
    for (let y = 0; y < A; y += 4) {
      const j = (rnd() - 0.5) * 1.6;
      g.fillStyle = "rgba(120,74,48,0.5)";
      g.fillRect(cx - 9 + j, y, 5, 4);
      g.fillRect(cx + 4 + j, y, 5, 4);
      g.fillStyle = "rgba(30,15,9,0.92)";
      g.fillRect(cx - 4 + j, y, 8, 4);
    }
    for (let y = 0; y < A; y += 7) {
      g.fillStyle = "rgba(0,0,0,0.18)";
      g.fillRect(cx - 5, y, 10, 2);
    }
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.wrapT = THREE.RepeatWrapping;
  t.anisotropy = 16;
  return t;
}

// ----------------------------------------------------------------- planta de soja
/** Soja jovem (V3/V4): caule, cotilédones e trifólios. Fundo transparente. */
export function texturaPlanta() {
  const n = 256;
  const { c, g } = tela(n);
  const rnd = aleatorio(3);
  g.strokeStyle = "#5b6b2c";
  g.lineWidth = 5;
  g.lineCap = "round";
  g.beginPath();
  g.moveTo(128, 256);
  g.quadraticCurveTo(122, 190, 130, 120);
  g.stroke();

  const folha = (x: number, y: number, ang: number, comp: number, larg: number) => {
    g.save();
    g.translate(x, y);
    g.rotate(ang);
    const gr = g.createLinearGradient(0, -larg / 2, 0, larg / 2);
    gr.addColorStop(0, "#7fb648");
    gr.addColorStop(0.5, "#5c9a35");
    gr.addColorStop(1, "#3f7426");
    g.fillStyle = gr;
    g.beginPath();
    g.ellipse(comp / 2, 0, comp / 2, larg / 2, 0, 0, Math.PI * 2);
    g.fill();
    g.strokeStyle = "rgba(220,240,180,0.35)";
    g.lineWidth = 1.5;
    g.beginPath();
    g.moveTo(2, 0);
    g.lineTo(comp - 4, 0);
    g.stroke();
    g.restore();
  };
  const trifolio = (x: number, y: number, ang: number, s: number) => {
    g.strokeStyle = "#5b6b2c";
    g.lineWidth = 3;
    g.beginPath();
    g.moveTo(130, 150);
    g.lineTo(x, y);
    g.stroke();
    for (const d of [-0.75, 0, 0.75]) folha(x, y, ang + d + (rnd() - 0.5) * 0.2, 46 * s, 30 * s);
  };
  // cotilédones
  folha(128, 205, Math.PI + 0.25, 30, 20);
  folha(128, 205, -0.25, 30, 20);
  trifolio(80, 150, Math.PI + 0.5, 1.0);
  trifolio(176, 140, -0.45, 1.05);
  trifolio(128, 92, -Math.PI / 2, 1.15);
  trifolio(98, 70, -Math.PI / 2 - 0.6, 0.85);

  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}

// ----------------------------------------------------------------- trator
/** Adesivo lateral do capô: aberturas de ventilação + marca. */
export function texturaAdesivo() {
  const { c, g } = tela(1024, 160);
  g.fillStyle = "rgba(10,10,10,0.92)";
  for (let i = 0; i < 7; i++) {
    g.beginPath();
    g.roundRect(30 + i * 34, 40, 18, 80, 9);
    g.fill();
  }
  g.strokeStyle = "#e9b949";
  g.lineWidth = 16;
  g.miterLimit = 10;
  g.beginPath();
  const s = 2.1;
  const ox = 330;
  const oy = 34;
  [[3, 41], [17, 15], [27, 32], [39, 7], [61, 41]].forEach(([x, y], i) =>
    i ? g.lineTo(ox + x * s, oy + y * s) : g.moveTo(ox + x * s, oy + y * s),
  );
  g.stroke();
  g.fillStyle = "#e9b949";
  g.font = "900 96px 'Arial Black', 'Helvetica Neue', Arial, sans-serif";
  g.textBaseline = "middle";
  g.fillText("SERRANO", 480, 84);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}

export function texturaGrade() {
  const { c, g } = tela(256);
  g.fillStyle = "#0b0c0d";
  g.fillRect(0, 0, 256, 256);
  for (let y = 10; y < 256; y += 18) {
    const gr = g.createLinearGradient(0, y, 0, y + 10);
    gr.addColorStop(0, "#5a5f63");
    gr.addColorStop(1, "#1d2022");
    g.fillStyle = gr;
    g.fillRect(8, y, 240, 9);
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

// ----------------------------------------------------------------- shaders
const RUIDO_GLSL = /* glsl */ `
  float h2s(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
  float vns(vec2 p) {
    vec2 i = floor(p); vec2 f = fract(p); vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(h2s(i), h2s(i + vec2(1, 0)), u.x), mix(h2s(i + vec2(0, 1)), h2s(i + vec2(1, 1)), u.x), u.y);
  }`;

/** Terra grudada nas partes baixas (ou no pneu inteiro). Funciona com instâncias. */
export function sujar(
  mat: THREE.MeshStandardMaterial,
  { altura = 1.1, intensidade = 0.7, cor = 0x6e4630, uniforme = false } = {},
) {
  mat.onBeforeCompile = (s) => {
    s.uniforms.uSujCor = { value: new THREE.Color(cor) };
    s.vertexShader = s.vertexShader
      .replace("#include <common>", "#include <common>\nvarying vec3 vObjS; varying float vAltS;")
      .replace(
        "#include <begin_vertex>",
        `#include <begin_vertex>
        vObjS = position;
        vec4 wpS = vec4(transformed, 1.0);
        #ifdef USE_INSTANCING
          wpS = instanceMatrix * wpS;
        #endif
        vAltS = (modelMatrix * wpS).y;`,
      );
    s.fragmentShader = s.fragmentShader
      .replace("#include <common>", `#include <common>\nvarying vec3 vObjS; varying float vAltS; uniform vec3 uSujCor;\n${RUIDO_GLSL}`)
      .replace(
        "#include <color_fragment>",
        `#include <color_fragment>
        float suj = ${uniforme ? "1.0" : `1.0 - smoothstep(0.05, ${altura.toFixed(2)}, vAltS)`};
        suj *= ${intensidade.toFixed(2)} * mix(0.3, 1.0, vns(vObjS.xz * 7.0 + vObjS.y * 5.0)) * mix(0.7, 1.0, vns(vObjS.zy * 23.0));
        suj = clamp(suj, 0.0, 1.0);
        diffuseColor.rgb = mix(diffuseColor.rgb, uSujCor, suj);`,
      )
      .replace("#include <roughnessmap_fragment>", "#include <roughnessmap_fragment>\nroughnessFactor = mix(roughnessFactor, 0.95, suj);")
      .replace("#include <metalnessmap_fragment>", "#include <metalnessmap_fragment>\nmetalnessFactor *= 1.0 - suj;");
  };
  mat.customProgramCacheKey = () => `sujo-${altura}-${intensidade}-${uniforme}`;
  return mat;
}

/** Variação em grande escala no solo: quebra a repetição da textura vista de longe. */
export function variarSolo(mat: THREE.MeshStandardMaterial) {
  mat.onBeforeCompile = (s) => {
    s.vertexShader = s.vertexShader
      .replace("#include <common>", "#include <common>\nvarying vec2 vMundoXZ;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvMundoXZ = (modelMatrix * vec4(transformed, 1.0)).xz;");
    s.fragmentShader = s.fragmentShader
      .replace("#include <common>", `#include <common>\nvarying vec2 vMundoXZ;\n${RUIDO_GLSL}`)
      .replace(
        "#include <map_fragment>",
        `#include <map_fragment>
        float macro = vns(vMundoXZ * 0.03) * 0.6 + vns(vMundoXZ * 0.11) * 0.4;
        diffuseColor.rgb *= mix(0.72, 1.18, macro);
        // talhão já plantado à esquerda: palha mais escura e úmida
        diffuseColor.rgb *= mix(1.0, 0.86, 1.0 - smoothstep(-2.9, -2.3, vMundoXZ.x));`,
      );
  };
  mat.customProgramCacheKey = () => "solo-macro";
  return mat;
}

/** Balanço das folhas com o vento (plantas instanciadas). */
export function balancar(mat: THREE.MeshStandardMaterial, tempo: { value: number }) {
  mat.onBeforeCompile = (s) => {
    s.uniforms.uTempo = tempo;
    s.vertexShader = s.vertexShader
      .replace("#include <common>", "#include <common>\nuniform float uTempo;")
      .replace(
        "#include <begin_vertex>",
        `#include <begin_vertex>
        vec4 ipB = instanceMatrix[3];
        float topoB = uv.y * uv.y;
        transformed.x += sin(uTempo * 1.9 + ipB.x * 0.7 + ipB.z * 0.45) * 0.07 * topoB;
        transformed.z += cos(uTempo * 1.4 + ipB.z * 0.6) * 0.05 * topoB;`,
      );
  };
  mat.customProgramCacheKey = () => "planta-vento";
  return mat;
}
