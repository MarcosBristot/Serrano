/** Cena 3D guiada pela rolagem: cada seção da página é um quadro-chave da câmera e do dia. */
import * as THREE from "three";
import { Sky } from "three/examples/jsm/objects/Sky.js";

import { aleatorio, balancar, FAIXA, fbm, texturaPlanta, texturaSolo, texturaSulcos, variarSolo } from "./texturas";
import { criarTrator, type Trator } from "./trator";

export interface Quadro {
  dist: number; // quanto o trator andou (m, frente = -Z)
  cam: [number, number, number]; // posição da câmera relativa ao trator
  alvo: [number, number, number]; // para onde olha, relativo ao trator
  elevacao: number; // altura do sol em graus (negativo = noite)
  azimute: number; // direção do sol em graus
  nevoa: number; // cor da névoa (combina com o horizonte)
  exposicao: number;
  noite: number; // 0..1: estrelas, luar e faróis
  calor: number; // 0..1: mapa de calor
  alerta: number; // 0..1: pulso de ociosidade
  trilha: number; // 0..1: camada de cobertura GPS
}

const NUMERICOS = ["dist", "elevacao", "azimute", "exposicao", "noite", "calor", "alerta", "trilha"] as const;
const FIM_PLANTADEIRA = 3.45; // z (relativo ao trator) onde a faixa plantada começa
const lerp = THREE.MathUtils.lerp;
const suave = (t: number) => t * t * (3 - 2 * t);

// ----------------------------------------------------------------- peças do cenário
function cruzado(): THREE.BufferGeometry {
  const a = new THREE.PlaneGeometry(1, 1);
  a.translate(0, 0.5, 0);
  const b = a.clone().rotateY(Math.PI / 2);
  const g = new THREE.BufferGeometry();
  const junta = (k: "position" | "normal" | "uv") => {
    const x = a.getAttribute(k).array as Float32Array;
    const y = b.getAttribute(k).array as Float32Array;
    const z = new Float32Array(x.length + y.length);
    z.set(x);
    z.set(y, x.length);
    return new THREE.BufferAttribute(z, k === "uv" ? 2 : 3);
  };
  g.setAttribute("position", junta("position"));
  g.setAttribute("normal", junta("normal"));
  g.setAttribute("uv", junta("uv"));
  const ia = a.getIndex()!.array;
  const n = a.getAttribute("position").count;
  g.setIndex([...ia, ...Array.from(ia, (i) => i + n)]);
  // normais "para cima": folhas iluminadas como copa, não como placas
  const nn = g.getAttribute("normal");
  for (let i = 0; i < nn.count; i++) nn.setXYZ(i, 0, 1, 0);
  return g;
}

function colinas(): THREE.Mesh {
  const g = new THREE.PlaneGeometry(2600, 2600, 180, 180);
  g.rotateX(-Math.PI / 2);
  const p = g.getAttribute("position");
  const cores: number[] = [];
  const c = new THREE.Color();
  const pasto = [new THREE.Color(0x6f7d39), new THREE.Color(0x8a8a46), new THREE.Color(0x4e6a2e)];
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i);
    const z = p.getZ(i) - 90;
    const borda = Math.max(Math.abs(x) / 175, Math.abs(z + 0) / 225);
    const fora = THREE.MathUtils.smoothstep(borda, 1.0, 1.9);
    const h = fbm(x * 0.0022 + 5, z * 0.0022 + 3, 1e6, 4, 11);
    p.setY(i, -0.06 + fora * (h * 70 - 8));
    const v = fbm(x * 0.01, z * 0.01, 1e6, 3, 3);
    c.copy(pasto[0]).lerp(pasto[1], v).lerp(pasto[2], fbm(x * 0.004, z * 0.004, 1e6, 2, 9) * 0.8);
    cores.push(c.r, c.g, c.b);
  }
  g.setAttribute("color", new THREE.Float32BufferAttribute(cores, 3));
  g.computeVertexNormals();
  const mesh = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1 }));
  mesh.position.z = -90;
  mesh.receiveShadow = true;
  return mesh;
}

/** Cortinas de eucalipto (quebra-vento) nas bordas da lavoura. */
function eucaliptos(): THREE.Group {
  const grupo = new THREE.Group();
  const rnd = aleatorio(19);
  const pontos: THREE.Vector3[] = [];
  // duas fileiras desencontradas, espaçamento irregular e algumas falhas
  const fileira = (x0: number, z0: number, x1: number, z1: number) => {
    const comp = Math.hypot(x1 - x0, z1 - z0);
    for (const desloc of [0, 2.6]) {
      for (let t = rnd() * 2; t < comp; t += 2.2 + rnd() * 2.6) {
        if (rnd() < 0.08) continue;
        const f = t / comp;
        const nx = (z1 - z0) / comp;
        const nz = -(x1 - x0) / comp;
        pontos.push(new THREE.Vector3(
          x0 + (x1 - x0) * f + nx * (desloc + (rnd() - 0.5) * 1.4), 0,
          z0 + (z1 - z0) * f + nz * (desloc + (rnd() - 0.5) * 1.4),
        ));
      }
    }
  };
  fileira(-62, 70, -62, -282);
  fileira(50, -282, 50, 70);
  fileira(50, -285, -62, -285);
  fileira(-150, -150, -66, -150);

  const tronco = new THREE.CylinderGeometry(0.16, 0.3, 1, 6);
  tronco.translate(0, 0.5, 0);
  const copa = new THREE.IcosahedronGeometry(1, 2);
  const pc = copa.getAttribute("position");
  for (let i = 0; i < pc.count; i++) {
    const v = new THREE.Vector3().fromBufferAttribute(pc, i);
    v.multiplyScalar(0.78 + fbm(v.x * 2 + 9, v.y * 2 + v.z, 1e6, 3, 4) * 0.5);
    pc.setXYZ(i, v.x, v.y, v.z);
  }
  copa.computeVertexNormals();
  const troncos = new THREE.InstancedMesh(tronco, new THREE.MeshStandardMaterial({ color: 0x6b6152, roughness: 0.95 }), pontos.length);
  const copas = new THREE.InstancedMesh(
    copa,
    new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.95, flatShading: true }),
    pontos.length * 3,
  );
  const m = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  const cor = new THREE.Color();
  pontos.forEach((p, i) => {
    const alt = 14 + rnd() * 12;
    m.compose(p, q, new THREE.Vector3(1 + rnd() * 0.4, alt, 1 + rnd() * 0.4));
    troncos.setMatrixAt(i, m);
    for (let k = 0; k < 3; k++) {
      const y = alt * (0.34 + k * 0.22) + rnd() * 1.5;
      const s = 2.6 - k * 0.45 + rnd() * 0.9;
      m.compose(
        new THREE.Vector3(p.x + (rnd() - 0.5) * 1.6, y, p.z + (rnd() - 0.5) * 1.6),
        new THREE.Quaternion().setFromEuler(new THREE.Euler(0, rnd() * 6, 0)),
        new THREE.Vector3(s, s * (1.6 + rnd() * 0.6), s),
      );
      copas.setMatrixAt(i * 3 + k, m);
      copas.setColorAt(i * 3 + k, cor.setHSL(0.27 + rnd() * 0.06, 0.28 + rnd() * 0.12, 0.2 + rnd() * 0.08));
    }
  });
  grupo.add(troncos, copas);
  return grupo;
}

function silos(): THREE.Group {
  const g = new THREE.Group();
  const metal = new THREE.MeshStandardMaterial({ color: 0xc4c8cb, roughness: 0.35, metalness: 0.85 });
  for (let i = 0; i < 3; i++) {
    const c = new THREE.Mesh(new THREE.CylinderGeometry(4.2, 4.2, 13, 40), metal);
    c.position.set(i * 9.5, 6.5, 0);
    const t = new THREE.Mesh(new THREE.ConeGeometry(4.4, 3.2, 40), metal);
    t.position.set(i * 9.5, 14.6, 0);
    g.add(c, t);
  }
  const galpao = new THREE.Mesh(new THREE.BoxGeometry(24, 7, 14), new THREE.MeshStandardMaterial({ color: 0xa9a49b, roughness: 0.7 }));
  galpao.position.set(-22, 3.5, 2);
  const telhado = new THREE.Mesh(new THREE.CylinderGeometry(8.5, 8.5, 24.4, 3, 1), metal);
  telhado.rotation.z = Math.PI / 2;
  telhado.scale.set(1, 1, 0.5);
  telhado.position.set(-22, 9.5, 2);
  g.add(galpao, telhado);
  g.position.set(-30, 0, -262);
  return g;
}

function estrelas(): THREE.Points {
  const n = 1800;
  const pos = new Float32Array(n * 3);
  const rnd = aleatorio(5);
  for (let i = 0; i < n; i++) {
    const u = rnd() * Math.PI * 2;
    const v = Math.asin(rnd()) * 0.95;
    pos.set([Math.cos(u) * Math.cos(v) * 900, Math.sin(v) * 900, Math.sin(u) * Math.cos(v) * 900], i * 3);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  return new THREE.Points(
    g,
    new THREE.PointsMaterial({ color: 0xdfe8ff, size: 1.5, sizeAttenuation: false, transparent: true, depthWrite: false, fog: false }),
  );
}

// ----------------------------------------------------------------- poeira
class Poeira {
  readonly pontos: THREE.Points;
  private n = 420;
  private vida = new Float32Array(this.n);
  private vel: THREE.Vector3[] = [];
  private prox = 0;
  private acumulado = 0;

  constructor() {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(this.n * 3), 3));
    g.setAttribute("aVida", new THREE.BufferAttribute(new Float32Array(this.n), 1));
    g.setAttribute("aTam", new THREE.BufferAttribute(new Float32Array(this.n).map(() => 1 + Math.random() * 1.8), 1));
    for (let i = 0; i < this.n; i++) this.vel.push(new THREE.Vector3());
    const mat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      uniforms: { uCor: { value: new THREE.Color(0xa8835f) }, uEscala: { value: 400 } },
      vertexShader: /* glsl */ `
        attribute float aVida; attribute float aTam; uniform float uEscala; varying float vVida;
        void main() {
          vVida = aVida;
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = min(aTam * (1.4 - aVida) * uEscala / -mv.z, 90.0);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: /* glsl */ `
        uniform vec3 uCor; varying float vVida;
        void main() {
          float d = length(gl_PointCoord - 0.5);
          float a = smoothstep(0.5, 0.0, d) * sin(vVida * 3.14159) * 0.12;
          if (a < 0.004) discard;
          gl_FragColor = vec4(uCor, a);
          #include <tonemapping_fragment>
          #include <colorspace_fragment>
        }`,
    });
    this.pontos = new THREE.Points(g, mat);
    this.pontos.frustumCulled = false;
  }

  set escala(px: number) {
    (this.pontos.material as THREE.ShaderMaterial).uniforms.uEscala.value = px;
  }
  set cor(c: THREE.Color) {
    (this.pontos.material as THREE.ShaderMaterial).uniforms.uCor.value.copy(c);
  }

  atualizar(dt: number, velocidade: number, origens: THREE.Vector3[]) {
    const pos = this.pontos.geometry.getAttribute("position") as THREE.BufferAttribute;
    const vida = this.pontos.geometry.getAttribute("aVida") as THREE.BufferAttribute;
    this.acumulado += Math.min(velocidade, 6) * dt * 6;
    while (this.acumulado >= 1) {
      this.acumulado -= 1;
      const o = origens[Math.floor(Math.random() * origens.length)];
      const i = this.prox;
      this.prox = (this.prox + 1) % this.n;
      this.vida[i] = 1;
      pos.setXYZ(i, o.x + (Math.random() - 0.5) * 0.5, o.y, o.z + Math.random() * 0.4);
      this.vel[i].set((Math.random() - 0.5) * 0.9, 0.35 + Math.random() * 0.7, 0.4 + Math.random() * 0.9);
    }
    for (let i = 0; i < this.n; i++) {
      if (this.vida[i] <= 0) continue;
      this.vida[i] = Math.max(0, this.vida[i] - dt / 3.2);
      this.vel[i].multiplyScalar(1 - dt * 0.6);
      pos.setXYZ(i, pos.getX(i) + this.vel[i].x * dt + 0.25 * dt, pos.getY(i) + this.vel[i].y * dt, pos.getZ(i) + this.vel[i].z * dt);
      vida.setX(i, this.vida[i]);
    }
    pos.needsUpdate = true;
    vida.needsUpdate = true;
  }
}

// ----------------------------------------------------------------- mapa de calor
function consumo(x: number, z: number): number {
  const v = Math.sin(x * 0.18 + 1.3) * 0.35 + Math.cos(z * 0.13 - x * 0.07) * 0.35 + Math.sin((x + z) * 0.31) * 0.15;
  return THREE.MathUtils.clamp(0.5 + v, 0, 1);
}
const RAMPA = [new THREE.Color(0x2f8a57), new THREE.Color(0xe9b949), new THREE.Color(0xd9482b)];
function corRampa(v: number, alvo: THREE.Color) {
  return v < 0.5 ? alvo.copy(RAMPA[0]).lerp(RAMPA[1], v * 2) : alvo.copy(RAMPA[1]).lerp(RAMPA[2], (v - 0.5) * 2);
}

// ----------------------------------------------------------------- cena
export class Cena {
  readonly renderer: THREE.WebGLRenderer;
  private cena = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(40, 1, 0.1, 3000);
  private trator: Trator;
  private sol = new THREE.DirectionalLight(0xffffff, 2);
  private lua = new THREE.DirectionalLight(0x9db4ff, 0);
  private hemi = new THREE.HemisphereLight(0xbfd4ff, 0x4a3324, 0.15);
  private ceu = new Sky();
  private ceuAmbiente = new Sky();
  private cenaAmbiente = new THREE.Scene();
  private pmrem: THREE.PMREMGenerator;
  private ambiente: THREE.WebGLRenderTarget | null = null;
  private ultimoSol = new THREE.Vector3(9, 9, 9);
  private ultimoAmbiente = 0;
  private estrelas = estrelas();
  private poeira = new Poeira();
  private tempo = { value: 0 };
  private faixa: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshStandardMaterial>;
  private rastro: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshBasicMaterial>;
  private pulso: THREE.Mesh<THREE.RingGeometry, THREE.MeshBasicMaterial>;
  private hex: THREE.InstancedMesh;
  private hexDados: { x: number; z: number; v: number; d: number }[] = [];
  private calorAtual = -1;
  private quadros: { p: number; q: Quadro }[] = [];
  private estado: Quadro | null = null;
  private distAnterior = 0;
  private velocidade = 0;
  private ponteiro = new THREE.Vector2();
  private alvoCam = new THREE.Vector3();
  private iniciada = false;
  /** com "reduzir movimento" a câmera vai direto ao quadro, sem deslizar */
  semSuavizar = false;
  private v = new THREE.Vector3();
  private m = new THREE.Matrix4();
  private cor = new THREE.Color();

  constructor(canvas: HTMLCanvasElement) {
    const r = (this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" }));
    r.setPixelRatio(Math.min(window.devicePixelRatio, 1.6));
    r.shadowMap.enabled = true;
    r.shadowMap.type = THREE.PCFSoftShadowMap;
    r.toneMapping = THREE.ACESFilmicToneMapping;
    this.pmrem = new THREE.PMREMGenerator(r);

    this.cena.fog = new THREE.FogExp2(0x000000, 0.0024);
    for (const s of [this.ceu, this.ceuAmbiente]) {
      s.scale.setScalar(1800);
      const u = s.material.uniforms;
      u.turbidity.value = 4.5;
      u.rayleigh.value = 1.4;
      u.mieCoefficient.value = 0.004;
      u.mieDirectionalG.value = 0.85;
    }
    this.cenaAmbiente.add(this.ceuAmbiente);
    this.cena.add(this.ceu, this.estrelas, this.hemi, this.lua, this.lua.target);

    this.sol.castShadow = true;
    this.sol.shadow.mapSize.set(2048, 2048);
    Object.assign(this.sol.shadow.camera, { left: -22, right: 22, top: 22, bottom: -22, near: 1, far: 160 });
    this.sol.shadow.bias = -0.0003;
    this.sol.shadow.normalBias = 0.02;
    this.cena.add(this.sol, this.sol.target);

    // solo da lavoura (um ladrilho de textura = 4 m)
    const { mapa, normal } = texturaSolo();
    const L = 360;
    const C = 470;
    mapa.repeat.set(L / 4, C / 4);
    normal.repeat.copy(mapa.repeat);
    const solo = new THREE.Mesh(
      new THREE.PlaneGeometry(L, C),
      variarSolo(new THREE.MeshStandardMaterial({ map: mapa, normalMap: normal, normalScale: new THREE.Vector2(1.4, 1.4), roughness: 0.96 })),
    );
    solo.rotation.x = -Math.PI / 2;
    solo.position.set(-6, 0, -95);
    solo.receiveShadow = true;
    this.cena.add(solo, colinas(), eucaliptos(), silos());

    // soja já emergida na passada anterior (lado esquerdo), linhas de 0,5 m
    const rnd = aleatorio(11);
    const plantas: THREE.Matrix4[] = [];
    for (let k = 0; k < 62; k++) {
      const x = -2.5 - k * FAIXA.espaco;
      for (let z = 60; z > -230; z -= 0.3) {
        const s = 0.2 + rnd() * 0.12;
        this.m.compose(
          new THREE.Vector3(x + (rnd() - 0.5) * 0.06, 0, z + (rnd() - 0.5) * 0.12),
          new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), rnd() * Math.PI),
          new THREE.Vector3(s * 1.2, s, s * 1.2),
        );
        plantas.push(this.m.clone());
      }
    }
    const lavoura = new THREE.InstancedMesh(
      cruzado(),
      balancar(
        new THREE.MeshStandardMaterial({ map: texturaPlanta(), alphaTest: 0.45, side: THREE.DoubleSide, roughness: 0.75 }),
        this.tempo,
      ),
      plantas.length,
    );
    plantas.forEach((mm, i) => {
      lavoura.setMatrixAt(i, mm);
      lavoura.setColorAt(i, this.cor.setHSL(0.2 + rnd() * 0.08, 0.35, 0.72 + rnd() * 0.2));
    });
    lavoura.receiveShadow = true;
    this.cena.add(lavoura);

    // faixa recém-plantada (sulcos + rastro dos pneus), cresce atrás da plantadeira
    const sulcos = texturaSulcos();
    this.faixa = new THREE.Mesh(
      new THREE.PlaneGeometry(FAIXA.largura, 1),
      new THREE.MeshStandardMaterial({ map: sulcos, transparent: true, depthWrite: false, roughness: 1, polygonOffset: true, polygonOffsetFactor: -2 }),
    );
    this.faixa.rotation.x = -Math.PI / 2;
    this.faixa.position.y = 0.01;
    this.faixa.receiveShadow = true;
    this.cena.add(this.faixa);

    // camada de dados: cobertura GPS
    this.rastro = new THREE.Mesh(
      new THREE.PlaneGeometry(FAIXA.largura, 1),
      new THREE.MeshBasicMaterial({ color: 0xe9b949, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending, fog: false }),
    );
    this.rastro.rotation.x = -Math.PI / 2;
    this.rastro.position.y = 0.04;
    this.cena.add(this.rastro);

    // mapa de calor em hexágonos (camada de dados sobre a lavoura)
    const rh = 1.05;
    const geoHex = new THREE.CylinderGeometry(rh * 0.94, rh * 0.94, 1, 6);
    geoHex.translate(0, 0.5, 0);
    const pts: { x: number; z: number }[] = [];
    for (let lin = 0; lin < 34; lin++) {
      for (let col = 0; col < 24; col++) {
        pts.push({ x: -21 + col * rh * Math.sqrt(3) + (lin % 2 ? (rh * Math.sqrt(3)) / 2 : 0), z: -6 - lin * rh * 1.5 });
      }
    }
    this.hex = new THREE.InstancedMesh(
      geoHex,
      new THREE.MeshStandardMaterial({ roughness: 0.45, metalness: 0.05, transparent: true, opacity: 0.9 }),
      pts.length,
    );
    const centro = new THREE.Vector2(0, -32);
    pts.forEach((p, i) => {
      const v = consumo(p.x, p.z);
      this.hexDados.push({ ...p, v, d: centro.distanceTo(new THREE.Vector2(p.x, p.z)) });
      this.hex.setColorAt(i, corRampa(v, this.cor));
    });
    this.hex.castShadow = true;
    this.hex.visible = false;
    this.cena.add(this.hex);

    this.pulso = new THREE.Mesh(
      new THREE.RingGeometry(0.9, 1.05, 64),
      new THREE.MeshBasicMaterial({ color: 0xff5a3c, transparent: true, opacity: 0, depthWrite: false, fog: false }),
    );
    this.pulso.rotation.x = -Math.PI / 2;
    this.cena.add(this.pulso);

    this.trator = criarTrator();
    this.cena.add(this.trator.grupo, this.poeira.pontos);

    window.addEventListener("pointermove", (e) => {
      this.ponteiro.set(e.clientX / window.innerWidth - 0.5, e.clientY / window.innerHeight - 0.5);
    });
  }

  definirQuadros(lista: { p: number; q: Quadro }[]) {
    this.quadros = lista.sort((a, b) => a.p - b.p);
  }

  redimensionar(l: number, a: number) {
    this.renderer.setSize(l, a, false);
    this.camera.aspect = l / a;
    this.camera.fov = l / a < 0.8 ? 56 : 40; // telas estreitas: abre o campo de visão
    this.camera.updateProjectionMatrix();
    this.poeira.escala = a * this.renderer.getPixelRatio() * 0.9;
  }

  private amostrar(p: number): Quadro {
    const qs = this.quadros;
    let i = 0;
    while (i < qs.length - 2 && p > qs[i + 1].p) i++;
    const a = qs[i];
    const b = qs[Math.min(i + 1, qs.length - 1)];
    const t = b.p === a.p ? 0 : suave(THREE.MathUtils.clamp((p - a.p) / (b.p - a.p), 0, 1));
    const out = { ...a.q };
    for (const k of NUMERICOS) out[k] = lerp(a.q[k], b.q[k], t);
    out.cam = a.q.cam.map((x, j) => lerp(x, b.q.cam[j], t)) as Quadro["cam"];
    out.alvo = a.q.alvo.map((x, j) => lerp(x, b.q.alvo[j], t)) as Quadro["alvo"];
    out.nevoa = this.cor.set(a.q.nevoa).lerp(new THREE.Color(b.q.nevoa), t).getHex();
    return out;
  }

  get distancia() {
    return this.estado?.dist ?? 0;
  }

  /** Céu físico + mapa de ambiente (reflexos) quando o sol anda o bastante. */
  private atualizarCeu(dirSol: THREE.Vector3, agora: number) {
    this.ceu.material.uniforms.sunPosition.value.copy(dirSol);
    if (dirSol.distanceTo(this.ultimoSol) > 0.02 && agora - this.ultimoAmbiente > 0.25) {
      this.ceuAmbiente.material.uniforms.sunPosition.value.copy(dirSol);
      const novo = this.pmrem.fromScene(this.cenaAmbiente, 0, 0.1, 4000);
      this.ambiente?.dispose();
      this.ambiente = novo;
      this.cena.environment = novo.texture;
      this.ultimoSol.copy(dirSol);
      this.ultimoAmbiente = agora;
    }
  }

  quadro(p: number, agora: number, dt: number) {
    if (!this.quadros.length) return;
    const q = (this.estado = this.amostrar(p));
    const { trator } = this;
    const z = -q.dist;
    this.tempo.value = agora;

    // movimento: rodas, balanço do motor e da lavoura
    const andou = q.dist - this.distAnterior;
    this.distAnterior = q.dist;
    this.velocidade += (Math.abs(andou) / Math.max(dt, 1e-3) - this.velocidade) * Math.min(1, dt * 4);
    const mov = Math.min(1, this.velocidade / 3);
    trator.grupo.position.set(0, 0, z);
    const c = trator.carroceria;
    c.position.y = Math.sin(agora * 41) * 0.004 + Math.sin(agora * 7.3) * 0.01 * mov;
    c.rotation.z = Math.sin(agora * 2.1) * 0.006 * mov;
    c.rotation.x = Math.sin(agora * 1.7 + 1) * 0.004 * mov;
    for (const r of trator.rodas) r.grupo.rotation.x -= andou / r.raio;

    // faixa plantada e camada GPS
    const L = Math.max(0.01, -z);
    this.faixa.scale.y = L;
    this.faixa.position.z = z + FIM_PLANTADEIRA + L / 2;
    (this.faixa.material.map as THREE.Texture).repeat.set(1, L / FAIXA.ladrilho);
    this.rastro.scale.y = L;
    this.rastro.position.z = this.faixa.position.z;
    this.rastro.material.opacity = 0.2 * q.trilha;

    // mapa de calor: cresce do centro para fora
    const calor = Math.round(q.calor * 200) / 200;
    if (calor !== this.calorAtual) {
      this.calorAtual = calor;
      this.hex.visible = calor > 0.001;
      if (this.hex.visible) {
        const q0 = new THREE.Quaternion();
        this.hexDados.forEach((h, i) => {
          const s = suave(THREE.MathUtils.clamp(calor * 1.8 - h.d / 34, 0, 1));
          this.m.compose(
            this.v.set(h.x, 0.03, h.z),
            q0,
            new THREE.Vector3(Math.max(s, 0.001), Math.max(0.001, s * (0.15 + h.v * 2.4)), Math.max(s, 0.001)),
          );
          this.hex.setMatrixAt(i, this.m);
        });
        this.hex.instanceMatrix.needsUpdate = true;
      }
    }

    // alerta de ociosidade
    const fase = (agora * 0.8) % 1;
    this.pulso.position.set(0, 0.06, z - 0.3);
    this.pulso.scale.setScalar(1 + fase * 6);
    this.pulso.material.opacity = q.alerta * (1 - fase) * 0.9;
    trator.giroflex.emissiveIntensity = q.alerta > 0.05 ? 0.6 + Math.max(0, Math.sin(agora * 9)) * 8 * q.alerta : 0.6;

    // sol, céu, luar e luzes do trator
    const dirSol = new THREE.Vector3().setFromSphericalCoords(
      1,
      THREE.MathUtils.degToRad(90 - q.elevacao),
      THREE.MathUtils.degToRad(q.azimute),
    );
    this.atualizarCeu(dirSol, agora);
    const dia = THREE.MathUtils.clamp(Math.sin(THREE.MathUtils.degToRad(q.elevacao)) * 4, 0, 1);
    this.ceu.position.set(0, 0, z);
    this.sol.intensity = 3.2 * dia;
    this.sol.color.set(0xff8a3d).lerp(this.cor.set(0xfff4e4), THREE.MathUtils.clamp(q.elevacao / 30, 0, 1));
    this.sol.position.set(dirSol.x * 80, Math.max(dirSol.y, 0.05) * 80, z + dirSol.z * 80);
    this.sol.target.position.set(0, 0, z - 4);
    this.lua.intensity = 1.2 * q.noite;
    this.lua.position.set(-40, 60, z - 30);
    this.lua.target.position.set(0, 0, z);
    this.hemi.intensity = 0.08 + 0.25 * q.noite;
    this.cena.environmentIntensity = 0.12 + 0.88 * dia;
    this.renderer.toneMappingExposure = q.exposicao;
    (this.cena.fog as THREE.FogExp2).color.set(q.nevoa);
    this.estrelas.position.set(0, 0, z);
    (this.estrelas.material as THREE.PointsMaterial).opacity = q.noite * 0.9;
    for (const [i, l] of trator.luzes.entries()) l.intensity = q.noite * (i < 2 ? 140 : 90);
    trator.lampadas.emissiveIntensity = 0.4 + q.noite * 5;

    // poeira (mais visível de dia; cor da terra)
    this.poeira.cor = this.cor.set(0xa47d58).multiplyScalar(0.25 + 0.75 * dia);
    const origens = trator.poeira.map((o) => o.clone().add(trator.grupo.position));
    this.poeira.atualizar(dt, this.velocidade, origens);

    // câmera com leve paralaxe do mouse e amortecimento
    this.v.set(q.cam[0] + this.ponteiro.x * 1.2, q.cam[1] - this.ponteiro.y * 0.6, z + q.cam[2]);
    const k = this.iniciada && !this.semSuavizar ? 1 - Math.exp(-dt * 6) : 1;
    this.camera.position.lerp(this.v, k);
    this.alvoCam.lerp(this.v.set(q.alvo[0], q.alvo[1], z + q.alvo[2]), k);
    this.camera.lookAt(this.alvoCam);
    this.iniciada = true;

    this.renderer.render(this.cena, this.camera);
  }
}
