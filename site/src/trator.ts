/** Trator 4x4 (~200 cv) e plantadeira de 9 linhas, modelados com primitivas. Frente = -Z, chão = y 0. */
import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";

import { sujar, texturaAdesivo, texturaGrade } from "./texturas";

export interface Trator {
  grupo: THREE.Group;
  carroceria: THREE.Group;
  rodas: { grupo: THREE.Group; raio: number }[];
  luzes: THREE.SpotLight[];
  lampadas: THREE.MeshStandardMaterial;
  giroflex: THREE.MeshStandardMaterial;
  /** pontos (no espaço do trator) onde a poeira nasce */
  poeira: THREE.Vector3[];
}

function materiais() {
  const tinta = sujar(
    new THREE.MeshPhysicalMaterial({ color: 0x1b1f22, roughness: 0.45, metalness: 0.15, clearcoat: 0.15, clearcoatRoughness: 0.3, envMapIntensity: 0.35 }),
    { altura: 1.25, intensidade: 0.75 },
  );
  const ouro = sujar(
    new THREE.MeshPhysicalMaterial({ color: 0xd9a53a, roughness: 0.34, metalness: 0.3, clearcoat: 0.4, clearcoatRoughness: 0.25, envMapIntensity: 0.7 }),
    { altura: 1.1, intensidade: 0.8 },
  );
  const ferro = sujar(new THREE.MeshStandardMaterial({ color: 0x2b2d2f, roughness: 0.55, metalness: 0.6 }), { altura: 1.4, intensidade: 0.85 });
  const borracha = sujar(new THREE.MeshStandardMaterial({ color: 0x141414, roughness: 0.93 }), {
    uniforme: true, intensidade: 0.55, cor: 0x5c3d2a,
  });
  const plastico = new THREE.MeshStandardMaterial({ color: 0x0f1011, roughness: 0.55 });
  const cromo = new THREE.MeshStandardMaterial({ color: 0x9aa0a4, roughness: 0.22, metalness: 1 });
  const vidro = new THREE.MeshPhysicalMaterial({
    color: 0x6f8f9c, roughness: 0.04, metalness: 0, transparent: true, opacity: 0.32, envMapIntensity: 2.2, side: THREE.DoubleSide,
  });
  const lampadas = new THREE.MeshStandardMaterial({ color: 0x333333, emissive: 0xfff3d6, emissiveIntensity: 2 });
  const lanterna = new THREE.MeshStandardMaterial({ color: 0x400000, emissive: 0xff2a1a, emissiveIntensity: 0.6 });
  const ambar = new THREE.MeshStandardMaterial({ color: 0x5a3000, emissive: 0xff8a1f, emissiveIntensity: 0.6 });
  const giroflex = new THREE.MeshStandardMaterial({ color: 0x552a00, emissive: 0xff8a1f, emissiveIntensity: 0.6, transparent: true, opacity: 0.9 });
  const banco = new THREE.MeshStandardMaterial({ color: 0x1a1a1a, roughness: 0.8 });
  return { tinta, ouro, ferro, borracha, plastico, cromo, vidro, lampadas, lanterna, ambar, giroflex, banco };
}
type Mats = ReturnType<typeof materiais>;

function peca(g: THREE.BufferGeometry, m: THREE.Material, pos: [number, number, number], pai: THREE.Object3D, rot?: [number, number, number]) {
  const mesh = new THREE.Mesh(g, m);
  mesh.position.set(...pos);
  if (rot) mesh.rotation.set(...rot);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  pai.add(mesh);
  return mesh;
}
const rbox = (l: number, a: number, c: number, r = 0.05, seg = 3) => new RoundedBoxGeometry(l, a, c, seg, Math.min(r, l / 2, a / 2, c / 2));

// ----------------------------------------------------------------- rodas
/** Pneu agrícola com garras em V, aro com disco e parafusos. Eixo = X; `lado` espelha para fora. */
function roda(raio: number, largura: number, lado: number, m: Mats) {
  const g = new THREE.Group();
  const h = largura / 2;
  const ra = raio * 0.62;
  const perfil = [
    [ra, -h * 0.9], [raio * 0.8, -h * 1.0], [raio * 0.93, -h * 0.96], [raio * 0.985, -h * 0.82], [raio, -h * 0.55],
    [raio, h * 0.55], [raio * 0.985, h * 0.82], [raio * 0.93, h * 0.96], [raio * 0.8, h * 1.0], [ra, h * 0.9],
  ].map(([x, y]) => new THREE.Vector2(x, y));
  const pneu = peca(new THREE.LatheGeometry(perfil, 72), m.borracha, [0, 0, 0], g, [0, 0, Math.PI / 2]);
  pneu.geometry.computeVertexNormals();

  // garras: duas metades inclinadas, desencontradas (padrão em V)
  const n = Math.round(raio * 24);
  const alt = raio * 0.07;
  const garra = rbox(h * 0.95, alt, raio * 0.11, 0.015, 2);
  const garras = new THREE.InstancedMesh(garra, m.borracha, n * 2);
  const q = new THREE.Quaternion();
  const qy = new THREE.Quaternion();
  const mat = new THREE.Matrix4();
  const um = new THREE.Vector3(1, 1, 1);
  for (let i = 0; i < n * 2; i++) {
    const metade = i % 2 ? 1 : -1;
    const ang = (Math.floor(i / 2) / n) * Math.PI * 2 + (metade > 0 ? Math.PI / n : 0);
    q.setFromAxisAngle(new THREE.Vector3(1, 0, 0), ang);
    qy.setFromAxisAngle(new THREE.Vector3(0, 1, 0), metade * 0.55);
    q.multiply(qy);
    const r = raio + alt * 0.35;
    mat.compose(new THREE.Vector3(metade * h * 0.45, Math.cos(ang) * r, Math.sin(ang) * r), q, um);
    garras.setMatrixAt(i, mat);
  }
  garras.castShadow = true;
  g.add(garras);

  // aro: tambor + disco abaulado + cubo + parafusos (para o lado de fora)
  const tambor = new THREE.CylinderGeometry(ra, ra, largura * 0.88, 48, 1, true);
  m.ouro.side = THREE.DoubleSide;
  peca(tambor, m.ouro, [0, 0, 0], g, [0, 0, Math.PI / 2]);
  const disco = new THREE.LatheGeometry(
    [[0.001, 0.02], [ra * 0.32, 0.02], [ra * 0.45, -0.03], [ra * 0.8, -0.08], [ra * 0.98, -0.12]].map(([x, y]) => new THREE.Vector2(x, y)),
    48,
  );
  const d = peca(disco, m.ouro, [lado * h * 0.15, 0, 0], g, [0, 0, -lado * Math.PI / 2]);
  d.castShadow = false;
  peca(new THREE.CylinderGeometry(ra * 0.24, ra * 0.3, 0.16, 24), m.ferro, [lado * h * 0.25, 0, 0], g, [0, 0, Math.PI / 2]);
  peca(new THREE.CylinderGeometry(ra * 0.1, ra * 0.12, 0.12, 16), m.cromo, [lado * h * 0.36, 0, 0], g, [0, 0, Math.PI / 2]);
  const parafuso = new THREE.CylinderGeometry(0.018, 0.018, 0.05, 6);
  parafuso.rotateZ(Math.PI / 2);
  const parafusos = new THREE.InstancedMesh(parafuso, m.cromo, 10);
  for (let i = 0; i < 10; i++) {
    const a = (i / 10) * Math.PI * 2;
    mat.compose(new THREE.Vector3(lado * h * 0.27, Math.cos(a) * ra * 0.36, Math.sin(a) * ra * 0.36), new THREE.Quaternion(), um);
    parafusos.setMatrixAt(i, mat);
  }
  g.add(parafusos);
  return g;
}

// ----------------------------------------------------------------- trator
export function criarTrator(): Trator {
  const m = materiais();
  const grupo = new THREE.Group();
  const corpo = new THREE.Group(); // tudo menos as rodas (balança um pouco)
  grupo.add(corpo);

  // bloco do motor / chassi
  peca(rbox(0.86, 0.62, 3.1, 0.06), m.ferro, [0, 0.95, -0.85], corpo);
  peca(rbox(1.7, 0.12, 0.5, 0.03), m.ferro, [0, 0.7, -2.0], corpo); // eixo dianteiro
  peca(new THREE.CylinderGeometry(0.11, 0.11, 2.05, 16), m.ferro, [0, 0.95, 0.9], corpo, [0, 0, Math.PI / 2]); // eixo traseiro
  peca(rbox(1.1, 0.55, 0.9, 0.06), m.ferro, [0, 0.95, 0.9], corpo); // diferencial

  // capô moldado (perfil extrudado)
  const s = new THREE.Shape();
  s.moveTo(0, 1.05);
  s.lineTo(2.28, 1.05);
  s.lineTo(2.42, 1.32);
  s.lineTo(2.46, 1.7);
  s.quadraticCurveTo(2.46, 1.9, 2.26, 1.93);
  s.lineTo(0.18, 2.06);
  s.quadraticCurveTo(0, 2.07, 0, 1.94);
  s.lineTo(0, 1.05);
  const geoCapo = new THREE.ExtrudeGeometry(s, { depth: 0.96, bevelEnabled: true, bevelThickness: 0.06, bevelSize: 0.06, bevelSegments: 5, curveSegments: 18 });
  geoCapo.translate(0, 0, -0.48);
  geoCapo.rotateY(Math.PI / 2);
  peca(geoCapo, m.tinta, [0, 0, -0.18], corpo);
  // friso dourado no topo do capô
  peca(rbox(1.0, 0.02, 2.2, 0.01), m.ouro, [0, 2.0, -1.35], corpo, [-0.055, 0, 0]);

  // grade, faróis e adesivos
  const grade = new THREE.MeshStandardMaterial({ map: texturaGrade(), roughness: 0.5, metalness: 0.4 });
  peca(rbox(0.86, 0.62, 0.05, 0.02), grade, [0, 1.52, -2.71], corpo);
  for (const x of [-0.3, 0.3]) {
    peca(rbox(0.26, 0.11, 0.05, 0.03), m.lampadas, [x, 1.79, -2.66], corpo);
    peca(rbox(0.05, 0.12, 0.3, 0.02), m.lampadas, [x * 1.78, 1.72, -2.3], corpo); // faróis laterais
  }
  const adesivo = new THREE.MeshStandardMaterial({ map: texturaAdesivo(), transparent: true, roughness: 0.4, polygonOffset: true, polygonOffsetFactor: -2 });
  for (const lado of [-1, 1]) {
    const p = peca(new THREE.PlaneGeometry(1.75, 0.27), adesivo, [lado * 0.546, 1.56, -1.38], corpo, [0, lado * Math.PI / 2, 0]);
    p.castShadow = false;
    if (lado > 0) p.scale.x = -1; // texto legível dos dois lados
  }

  // pesos dianteiros (lastro)
  peca(rbox(0.3, 0.5, 0.35, 0.03), m.ferro, [0, 0.95, -2.85], corpo);
  for (let i = 0; i < 8; i++) peca(rbox(0.11, 0.52, 0.4, 0.025), m.tinta, [-0.42 + i * 0.12, 0.98, -3.05], corpo);

  // cabine
  const zc = 0.68;
  peca(rbox(1.7, 0.28, 1.78, 0.05), m.tinta, [0, 1.62, zc], corpo);
  peca(rbox(1.56, 1.3, 1.62, 0.05), m.vidro, [0, 2.42, zc], corpo).castShadow = false;
  for (const [x, z] of [[-0.79, zc - 0.82], [0.79, zc - 0.82], [-0.79, zc + 0.82], [0.79, zc + 0.82]]) {
    peca(rbox(0.08, 1.34, 0.08, 0.02), m.tinta, [x, 2.42, z], corpo);
  }
  peca(rbox(0.06, 0.06, 1.62, 0.02), m.tinta, [-0.79, 2.0, zc], corpo); // travessa da porta
  peca(rbox(1.92, 0.2, 2.0, 0.08), m.tinta, [0, 3.17, zc + 0.04], corpo);
  peca(rbox(1.94, 0.04, 2.02, 0.02), m.ouro, [0, 3.08, zc + 0.04], corpo);
  peca(rbox(1.7, 0.08, 1.7, 0.04), m.plastico, [0, 3.3, zc], corpo); // tampa do ar-condicionado
  const giro = peca(new THREE.CylinderGeometry(0.075, 0.09, 0.15, 16), m.giroflex, [0.62, 3.42, zc + 0.6], corpo);
  giro.castShadow = false;
  for (const x of [-0.6, -0.2, 0.2, 0.6]) peca(rbox(0.18, 0.09, 0.06, 0.02), m.lampadas, [x, 3.15, zc - 1.0], corpo);
  for (const x of [-0.5, 0.5]) peca(rbox(0.18, 0.09, 0.06, 0.02), m.lampadas, [x, 3.15, zc + 1.06], corpo);
  // interior: banco, coluna e volante
  peca(rbox(0.5, 0.55, 0.5, 0.08), m.banco, [0, 2.05, zc + 0.35], corpo);
  peca(rbox(0.5, 0.65, 0.12, 0.05), m.banco, [0, 2.35, zc + 0.62], corpo, [0.15, 0, 0]);
  peca(new THREE.CylinderGeometry(0.04, 0.05, 0.6, 10), m.plastico, [0, 2.0, zc - 0.45], corpo, [-0.5, 0, 0]);
  peca(new THREE.TorusGeometry(0.2, 0.025, 10, 32), m.plastico, [0, 2.3, zc - 0.28], corpo, [-1.0, 0, 0]);
  peca(rbox(0.25, 0.5, 0.6, 0.04), m.plastico, [0.48, 2.0, zc + 0.15], corpo); // console
  // retrovisores
  for (const lado of [-1, 1]) {
    peca(new THREE.CylinderGeometry(0.015, 0.015, 0.42, 8), m.plastico, [lado * 0.98, 2.95, zc - 0.82], corpo, [0, 0, Math.PI / 2]);
    peca(rbox(0.04, 0.32, 0.2, 0.02), m.plastico, [lado * 1.2, 2.82, zc - 0.82], corpo);
  }
  // escada e tanque
  for (let i = 0; i < 3; i++) peca(rbox(0.38, 0.04, 0.26, 0.01), m.ferro, [-0.98, 0.5 + i * 0.36, -0.28], corpo);
  for (const z of [-0.42, -0.14]) peca(rbox(0.04, 1.2, 0.04, 0.01), m.ferro, [-1.16, 0.95, z], corpo);
  peca(rbox(0.42, 0.62, 0.95, 0.12), m.tinta, [0.72, 1.05, -0.55], corpo);
  peca(new THREE.CylinderGeometry(0.06, 0.06, 0.05, 16), m.cromo, [0.72, 1.39, -0.4], corpo);

  // escapamento e pré-filtro de ar
  peca(new THREE.CylinderGeometry(0.11, 0.11, 0.6, 20), m.ferro, [0.4, 2.35, -0.48], corpo);
  peca(new THREE.CylinderGeometry(0.065, 0.07, 1.45, 16), m.ferro, [0.4, 2.65, -0.48], corpo);
  peca(new THREE.CylinderGeometry(0.07, 0.07, 0.06, 16), m.cromo, [0.4, 3.39, -0.47], corpo, [0.35, 0, 0]);
  peca(new THREE.CylinderGeometry(0.12, 0.1, 0.28, 18), m.plastico, [-0.4, 2.2, -0.48], corpo);

  // para-lamas traseiros e dianteiros (com luzes âmbar e lanternas)
  for (const lado of [-1, 1]) {
    const pl = new THREE.Mesh(new THREE.CylinderGeometry(1.08, 1.08, 0.74, 40, 1, true, -0.15, Math.PI * 0.95), m.tinta);
    pl.material.side = THREE.DoubleSide;
    pl.rotation.z = Math.PI / 2;
    pl.position.set(lado * 1.15, 0.95, 0.9);
    pl.castShadow = true;
    corpo.add(pl);
    peca(rbox(0.08, 0.06, 0.16, 0.02), m.ambar, [lado * 1.48, 1.95, 0.6], corpo);
    peca(rbox(0.12, 0.08, 0.05, 0.02), m.lanterna, [lado * 1.3, 1.5, 1.98], corpo);
    const pf = new THREE.Mesh(new THREE.CylinderGeometry(0.8, 0.8, 0.5, 32, 1, true, Math.PI * 0.05, Math.PI * 0.7), m.tinta);
    pf.rotation.z = Math.PI / 2;
    pf.position.set(lado * 1.0, 0.7, -2.0);
    pf.castShadow = true;
    corpo.add(pf);
  }

  // engate de três pontos
  for (const lado of [-1, 1]) {
    peca(rbox(0.07, 0.07, 0.95, 0.02), m.ferro, [lado * 0.42, 0.72, 1.85], corpo, [0.22, 0, 0]);
  }
  peca(rbox(0.07, 0.07, 0.8, 0.02), m.ferro, [0, 1.25, 1.85], corpo, [-0.25, 0, 0]);
  peca(rbox(0.2, 0.08, 0.6, 0.02), m.ferro, [0, 0.55, 1.9], corpo);

  // rodas
  const rodas: Trator["rodas"] = [];
  for (const [x, z, r, w] of [
    [-1.15, 0.9, 0.95, 0.62], [1.15, 0.9, 0.95, 0.62],
    [-1.0, -2.0, 0.7, 0.48], [1.0, -2.0, 0.7, 0.48],
  ]) {
    const g = roda(r, w, Math.sign(x), m);
    g.position.set(x, r, z);
    grupo.add(g);
    rodas.push({ grupo: g, raio: r });
  }

  plantadeira(corpo, m, rodas);

  // luzes de verdade (faróis + luzes de serviço)
  const luzes: THREE.SpotLight[] = [];
  const spot = (pos: [number, number, number], alvo: [number, number, number], ang: number) => {
    const sp = new THREE.SpotLight(0xfff1d6, 0, 60, ang, 0.55, 1.6);
    sp.position.set(...pos);
    sp.target.position.set(...alvo);
    corpo.add(sp, sp.target);
    luzes.push(sp);
  };
  spot([-0.3, 1.8, -2.75], [-1.2, 0, -16], 0.45);
  spot([0.3, 1.8, -2.75], [1.2, 0, -16], 0.45);
  spot([0, 3.15, zc - 1.05], [0, 0, -9], 0.85);
  spot([0, 3.15, zc + 1.1], [0, 0, 5], 0.9);

  return {
    grupo,
    carroceria: corpo,
    rodas,
    luzes,
    lampadas: m.lampadas,
    giroflex: m.giroflex,
    poeira: [
      new THREE.Vector3(-1.15, 0.15, 1.7), new THREE.Vector3(1.15, 0.15, 1.7),
      new THREE.Vector3(-1.5, 0.1, 3.1), new THREE.Vector3(0, 0.1, 3.1), new THREE.Vector3(1.5, 0.1, 3.1),
    ],
  };
}

// ----------------------------------------------------------------- plantadeira
function plantadeira(pai: THREE.Group, m: Mats, rodas: Trator["rodas"]) {
  const z0 = 2.4;
  peca(rbox(4.7, 0.16, 0.16, 0.03), m.tinta, [0, 0.72, z0], pai); // barra porta-ferramentas
  peca(rbox(4.5, 0.12, 0.12, 0.03), m.tinta, [0, 0.95, z0 + 0.45], pai);
  for (const x of [-1.6, 0, 1.6]) peca(rbox(0.1, 0.35, 0.55, 0.02), m.tinta, [x, 0.84, z0 + 0.22], pai);
  // reservatório de adubo
  peca(rbox(3.9, 0.62, 0.78, 0.1), m.tinta, [0, 1.42, z0 + 0.35], pai);
  peca(rbox(3.92, 0.06, 0.8, 0.02), m.ouro, [0, 1.6, z0 + 0.35], pai);
  peca(rbox(3.8, 0.05, 0.7, 0.02), m.plastico, [0, 1.76, z0 + 0.35], pai);

  const caixa = new THREE.CylinderGeometry(0.2, 0.11, 0.36, 4, 1);
  caixa.rotateY(Math.PI / 4);
  for (let i = 0; i < 9; i++) {
    const x = -2 + i * 0.5;
    peca(caixa, m.ouro, [x, 1.0, z0 + 0.95], pai); // caixa de sementes
    peca(rbox(0.05, 0.05, 0.55, 0.01), m.ferro, [x - 0.06, 0.62, z0 + 0.6], pai, [0.5, 0, 0]); // paralelogramo
    peca(rbox(0.05, 0.05, 0.55, 0.01), m.ferro, [x + 0.06, 0.78, z0 + 0.6], pai, [0.5, 0, 0]);
    peca(rbox(0.14, 0.32, 0.5, 0.03), m.tinta, [x, 0.48, z0 + 0.95], pai); // corpo da linha
    for (const l of [-1, 1]) {
      peca(new THREE.CylinderGeometry(0.19, 0.19, 0.012, 28), m.cromo, [x + l * 0.035, 0.2, z0 + 0.95], pai, [0, l * 0.09, Math.PI / 2]);
      peca(new THREE.CylinderGeometry(0.15, 0.15, 0.06, 20), m.borracha, [x + l * 0.11, 0.15, z0 + 1.08], pai, [0, 0, Math.PI / 2]);
    }
    peca(new THREE.CylinderGeometry(0.13, 0.13, 0.05, 18), m.borracha, [x, 0.13, z0 + 1.38], pai, [0, 0, Math.PI / 2]); // compactadora
  }
  // rodas de transporte da plantadeira (giram como as do trator)
  for (const lado of [-1, 1]) {
    const r = roda(0.33, 0.22, lado, m);
    r.position.set(lado * 2.55, 0.33, z0 + 0.4);
    pai.parent?.add(r) ?? pai.add(r);
    rodas.push({ grupo: r, raio: 0.33 });
  }
}
