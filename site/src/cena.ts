/** Cena 3D guiada pela rolagem: cada seção da página é um quadro-chave da câmera. */
import * as THREE from "three";

import { criarTrator, type Trator } from "./trator";

export interface Quadro {
  dist: number; // quanto o trator andou (unidades de cena, frente = -Z)
  cam: [number, number, number]; // posição da câmera relativa ao trator
  alvo: [number, number, number]; // para onde olha, relativo ao trator
  topo: number; // cor do céu no alto
  horizonte: number; // cor do horizonte e da névoa
  sol: number; // intensidade do sol
  elevacao: number; // altura do sol (0 = horizonte, 1 = a pino)
  noite: number; // 0..1: estrelas e faróis
  calor: number; // 0..1: mapa de calor
  alerta: number; // 0..1: pulso de ociosidade
  trilha: number; // 0..1: rastro de cobertura GPS
}

const INICIO_Z = 0;
const ESPACO_LINHA = 0.65;

const lerp = THREE.MathUtils.lerp;
const suave = (t: number) => t * t * (3 - 2 * t);

// ----------------------------------------------------------------- texturas e peças
function texturaSolo(): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 256;
  c.height = 256;
  const g = c.getContext("2d")!;
  g.fillStyle = "#4a3726";
  g.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 3000; i++) {
    const v = 40 + Math.random() * 50;
    g.fillStyle = `rgba(${v + 30},${v + 12},${v - 8},0.25)`;
    g.fillRect(Math.random() * 256, Math.random() * 256, 2, 2);
  }
  // sulcos ao longo do sentido de plantio (eixo Z)
  for (let x = 0; x < 256; x += 32) {
    const grad = g.createLinearGradient(x, 0, x + 32, 0);
    grad.addColorStop(0, "rgba(0,0,0,0.0)");
    grad.addColorStop(0.5, "rgba(0,0,0,0.28)");
    grad.addColorStop(1, "rgba(0,0,0,0.0)");
    g.fillStyle = grad;
    g.fillRect(x, 0, 32, 256);
  }
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(400 / (ESPACO_LINHA * 8), 400 / 6);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}

function muda(): THREE.BufferGeometry {
  const g = new THREE.ConeGeometry(0.11, 0.32, 5);
  g.translate(0, 0.16, 0);
  return g;
}

function ceu(): THREE.Mesh<THREE.SphereGeometry, THREE.ShaderMaterial> {
  const mat = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    uniforms: {
      topo: { value: new THREE.Color() },
      horizonte: { value: new THREE.Color() },
      sol: { value: new THREE.Vector3(0, 0.2, -1) },
      brilho: { value: 1 },
    },
    vertexShader: /* glsl */ `
      varying vec3 vDir;
      void main() {
        vDir = normalize(position);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: /* glsl */ `
      uniform vec3 topo; uniform vec3 horizonte; uniform vec3 sol; uniform float brilho;
      varying vec3 vDir;
      void main() {
        float h = clamp(vDir.y * 1.6, 0.0, 1.0);
        vec3 cor = mix(horizonte, topo, pow(h, 0.7));
        float s = max(dot(normalize(vDir), normalize(sol)), 0.0);
        cor += vec3(1.0, 0.72, 0.38) * (pow(s, 380.0) * 2.0 + pow(s, 9.0) * 0.32) * brilho;
        gl_FragColor = vec4(cor, 1.0);
      }`,
  });
  return new THREE.Mesh(new THREE.SphereGeometry(500, 32, 16), mat);
}

function estrelas(): THREE.Points {
  const n = 1400;
  const pos = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const u = Math.random() * Math.PI * 2;
    const v = Math.random() * 0.48 * Math.PI;
    pos.set([Math.cos(u) * Math.cos(v) * 420, Math.sin(v) * 420 + 10, Math.sin(u) * Math.cos(v) * 420], i * 3);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  return new THREE.Points(
    g,
    new THREE.PointsMaterial({ color: 0xffffff, size: 1.6, sizeAttenuation: false, transparent: true, depthWrite: false }),
  );
}

// valor "L/ha" sintético e suave para o mapa de calor
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
  private camera = new THREE.PerspectiveCamera(42, 1, 0.1, 1200);
  private trator: Trator;
  private sol = new THREE.DirectionalLight(0xffe2b8, 2);
  private hemi = new THREE.HemisphereLight(0xbfd4ff, 0x3a2a1c, 0.6);
  private ceu = ceu();
  private estrelas = estrelas();
  private plantio: THREE.InstancedMesh;
  private plantioZ: number[] = [];
  private hex: THREE.InstancedMesh;
  private hexDados: { x: number; z: number; v: number; d: number }[] = [];
  private calorAtual = -1;
  private rastro: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshBasicMaterial>;
  private pulso: THREE.Mesh<THREE.RingGeometry, THREE.MeshBasicMaterial>;
  private quadros: { p: number; q: Quadro }[] = [];
  private estado: Quadro | null = null;
  private distAnterior = 0;
  private ponteiro = new THREE.Vector2();
  private tmp = { cor: new THREE.Color(), m: new THREE.Matrix4(), v: new THREE.Vector3(), alvo: new THREE.Vector3() };

  constructor(canvas: HTMLCanvasElement) {
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.2;

    this.cena.fog = new THREE.Fog(0x000000, 40, 230);
    this.cena.add(this.ceu, this.estrelas, this.hemi);

    this.sol.castShadow = true;
    this.sol.shadow.mapSize.set(2048, 2048);
    Object.assign(this.sol.shadow.camera, { left: -26, right: 26, top: 26, bottom: -26, near: 1, far: 120 });
    this.sol.shadow.bias = -0.0004;
    this.cena.add(this.sol, this.sol.target);

    // solo
    const solo = new THREE.Mesh(
      new THREE.PlaneGeometry(400, 400),
      new THREE.MeshStandardMaterial({ map: texturaSolo(), roughness: 1 }),
    );
    solo.rotation.x = -Math.PI / 2;
    solo.position.z = -100;
    solo.receiveShadow = true;
    this.cena.add(solo);

    const geoMuda = muda();
    // passadas anteriores (lado esquerdo já plantado)
    const plantado: THREE.Vector3[] = [];
    for (let k = 0; k < 34; k++) {
      for (let z = 30; z > -170; z -= 0.55) {
        plantado.push(new THREE.Vector3(-2.6 - k * ESPACO_LINHA, 0, z + (Math.random() - 0.5) * 0.2));
      }
    }
    const lavoura = new THREE.InstancedMesh(
      geoMuda,
      new THREE.MeshStandardMaterial({ color: 0x5f9b45, roughness: 0.8 }),
      plantado.length,
    );
    plantado.forEach((p, i) => {
      const s = 0.8 + Math.random() * 0.6;
      this.tmp.m.compose(p, new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.random() * 6), new THREE.Vector3(s, s, s));
      lavoura.setMatrixAt(i, this.tmp.m);
    });
    lavoura.receiveShadow = true;
    this.cena.add(lavoura);

    // linhas que a plantadeira vai deixando (ordenadas pelo Z: o "count" revela)
    const linhas: THREE.Vector3[] = [];
    for (let z = INICIO_Z + 2.5; z > -170; z -= 0.4) {
      for (let i = 0; i < 7; i++) linhas.push(new THREE.Vector3(-1.95 + i * 0.65, 0, z));
    }
    this.plantio = new THREE.InstancedMesh(
      geoMuda,
      new THREE.MeshStandardMaterial({ color: 0x8cc35b, roughness: 0.7, emissive: 0x1d3510 }),
      linhas.length,
    );
    linhas.forEach((p, i) => {
      this.tmp.m.compose(p, new THREE.Quaternion(), new THREE.Vector3(0.55, 0.45, 0.55));
      this.plantio.setMatrixAt(i, this.tmp.m);
      this.plantioZ.push(p.z);
    });
    this.plantio.count = 0;
    this.cena.add(this.plantio);

    // rastro de cobertura GPS
    this.rastro = new THREE.Mesh(
      new THREE.PlaneGeometry(4.6, 1),
      new THREE.MeshBasicMaterial({ color: 0xe9b949, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending }),
    );
    this.rastro.rotation.x = -Math.PI / 2;
    this.rastro.position.y = 0.03;
    this.cena.add(this.rastro);

    // mapa de calor em hexágonos
    const r = 1.05;
    const geoHex = new THREE.CylinderGeometry(r * 0.94, r * 0.94, 1, 6);
    geoHex.translate(0, 0.5, 0);
    const pontos: { x: number; z: number }[] = [];
    for (let lin = 0; lin < 34; lin++) {
      for (let col = 0; col < 24; col++) {
        const x = -21 + col * r * Math.sqrt(3) + (lin % 2 ? (r * Math.sqrt(3)) / 2 : 0);
        const z = -6 - lin * r * 1.5;
        pontos.push({ x, z });
      }
    }
    this.hex = new THREE.InstancedMesh(
      geoHex,
      new THREE.MeshStandardMaterial({ roughness: 0.55, metalness: 0.05, transparent: true, opacity: 0.92 }),
      pontos.length,
    );
    const centro = new THREE.Vector2(0, -32);
    pontos.forEach((p, i) => {
      const v = consumo(p.x, p.z);
      this.hexDados.push({ ...p, v, d: centro.distanceTo(new THREE.Vector2(p.x, p.z)) });
      this.hex.setColorAt(i, corRampa(v, this.tmp.cor));
    });
    this.hex.castShadow = true;
    this.hex.visible = false;
    this.cena.add(this.hex);

    // pulso do alerta
    this.pulso = new THREE.Mesh(
      new THREE.RingGeometry(0.9, 1.05, 64),
      new THREE.MeshBasicMaterial({ color: 0xff5a3c, transparent: true, opacity: 0, depthWrite: false }),
    );
    this.pulso.rotation.x = -Math.PI / 2;
    this.pulso.position.y = 0.05;
    this.cena.add(this.pulso);

    this.trator = criarTrator();
    this.cena.add(this.trator.grupo);

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
    // em telas estreitas, abre o campo de visão para o trator caber
    this.camera.fov = l / a < 0.8 ? 58 : 42;
    this.camera.updateProjectionMatrix();
  }

  /** Interpola os quadros-chave para o progresso p (0..1). */
  private amostrar(p: number): Quadro {
    const qs = this.quadros;
    let i = 0;
    while (i < qs.length - 2 && p > qs[i + 1].p) i++;
    const a = qs[i];
    const b = qs[Math.min(i + 1, qs.length - 1)];
    const t = b.p === a.p ? 0 : suave(THREE.MathUtils.clamp((p - a.p) / (b.p - a.p), 0, 1));
    const n = (k: keyof Quadro) => lerp(a.q[k] as number, b.q[k] as number, t);
    const v3 = (k: "cam" | "alvo") => a.q[k].map((x, j) => lerp(x, b.q[k][j], t)) as [number, number, number];
    const cor = (k: "topo" | "horizonte") => this.tmp.cor.set(a.q[k]).lerp(new THREE.Color(b.q[k]), t).getHex();
    return {
      dist: n("dist"), cam: v3("cam"), alvo: v3("alvo"), topo: cor("topo"), horizonte: cor("horizonte"),
      sol: n("sol"), elevacao: n("elevacao"), noite: n("noite"), calor: n("calor"), alerta: n("alerta"), trilha: n("trilha"),
    };
  }

  /** Telemetria de mentira para o painel flutuante. */
  get distancia() {
    return this.estado?.dist ?? 0;
  }

  quadro(p: number, tempo: number, dt: number) {
    if (!this.quadros.length) return;
    const q = (this.estado = this.amostrar(p));
    const { trator } = this;
    const z = INICIO_Z - q.dist;

    // trator e rodas
    trator.grupo.position.set(0, Math.sin(tempo * 38) * 0.008, z);
    const andou = q.dist - this.distAnterior;
    this.distAnterior = q.dist;
    for (const r of trator.rodas) r.grupo.rotation.x -= andou / r.raio;
    for (const f of trator.farois) f.intensity = q.noite * 60;
    trator.lampadas.emissiveIntensity = 0.3 + q.noite * 3;
    trator.giroflex.emissiveIntensity = q.alerta > 0.05 ? 1 + Math.max(0, Math.sin(tempo * 9)) * 6 * q.alerta : 0.4;

    // plantio revelado atrás da plantadeira
    const limite = z + 3.1;
    let n = 0;
    while (n < this.plantioZ.length && this.plantioZ[n] >= limite) n++;
    this.plantio.count = n;

    // rastro de cobertura
    const comp = Math.max(0.01, INICIO_Z + 2.5 - (z + 2.9));
    this.rastro.scale.y = comp;
    this.rastro.position.z = z + 2.9 + comp / 2;
    this.rastro.material.opacity = 0.22 * q.trilha;

    // mapa de calor: cresce do centro para fora
    const calor = Math.round(q.calor * 200) / 200;
    if (calor !== this.calorAtual) {
      this.calorAtual = calor;
      this.hex.visible = calor > 0.001;
      if (this.hex.visible) {
        this.hexDados.forEach((h, i) => {
          const local = THREE.MathUtils.clamp(calor * 1.8 - h.d / 34, 0, 1);
          const s = suave(local);
          this.tmp.m.compose(
            this.tmp.v.set(h.x, 0.02, h.z),
            new THREE.Quaternion(),
            new THREE.Vector3(Math.max(s, 0.001), Math.max(0.001, s * (0.15 + h.v * 2.4)), Math.max(s, 0.001)),
          );
          this.hex.setMatrixAt(i, this.tmp.m);
        });
        this.hex.instanceMatrix.needsUpdate = true;
      }
    }

    // pulso de alerta em volta do trator
    const fase = (tempo * 0.8) % 1;
    this.pulso.position.set(0, 0.05, z - 0.3);
    this.pulso.scale.setScalar(1 + fase * 6);
    this.pulso.material.opacity = q.alerta * (1 - fase) * 0.9;

    // céu, sol e luz
    const mat = this.ceu.material.uniforms;
    mat.topo.value.set(q.topo);
    mat.horizonte.value.set(q.horizonte);
    (this.cena.fog as THREE.Fog).color.set(q.horizonte);
    const dirSol = this.tmp.v.set(-0.55, Math.max(0.02, q.elevacao), -1).normalize();
    mat.sol.value.copy(dirSol);
    mat.brilho.value = 1 - q.noite * 0.85;
    this.ceu.position.set(0, 0, z);
    this.estrelas.position.set(0, 0, z);
    (this.estrelas.material as THREE.PointsMaterial).opacity = q.noite;
    this.sol.intensity = q.sol;
    this.sol.color.set(q.horizonte).lerp(new THREE.Color(0xfff4e0), 0.6);
    this.sol.position.set(dirSol.x * 60, dirSol.y * 60 + 8, z + dirSol.z * 60);
    this.sol.target.position.set(0, 0, z - 6);
    this.hemi.intensity = 0.45 + q.sol * 0.3;
    this.hemi.color.set(q.topo).lerp(new THREE.Color(0xffffff), 0.5);

    // câmera com leve paralaxe do mouse e amortecimento
    const alvoCam = this.tmp.v.set(q.cam[0] + this.ponteiro.x * 1.2, q.cam[1] - this.ponteiro.y * 0.6, z + q.cam[2]);
    const k = 1 - Math.exp(-dt * 6);
    this.camera.position.lerp(alvoCam, this.camera.position.lengthSq() === 0 ? 1 : k);
    this.tmp.alvo.lerp(new THREE.Vector3(q.alvo[0], q.alvo[1], z + q.alvo[2]), this.tmp.alvo.lengthSq() === 0 ? 1 : k);
    this.camera.lookAt(this.tmp.alvo);

    this.renderer.render(this.cena, this.camera);
  }
}
