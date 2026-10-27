/** Trator Serrano montado com primitivas (sem modelo externo). Frente = -Z. */
import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";

export const CORES = {
  corpo: 0x24282b,
  corpoClaro: 0x33393d,
  ouro: 0xe9b949,
  pneu: 0x121314,
  vidro: 0x8fb3c4,
  farol: 0xfff1c9,
};

export interface Trator {
  grupo: THREE.Group;
  rodas: { grupo: THREE.Group; raio: number }[];
  farois: THREE.SpotLight[];
  lampadas: THREE.MeshStandardMaterial;
  giroflex: THREE.MeshStandardMaterial;
}

function caixa(l: number, a: number, c: number, mat: THREE.Material, raio = 0.08) {
  const m = new THREE.Mesh(new RoundedBoxGeometry(l, a, c, 3, raio), mat);
  m.castShadow = true;
  m.receiveShadow = true;
  return m;
}

function roda(raio: number, largura: number, mats: { pneu: THREE.Material; aro: THREE.Material }) {
  const g = new THREE.Group();
  const pneu = new THREE.Mesh(new THREE.CylinderGeometry(raio, raio, largura, 48), mats.pneu);
  pneu.rotation.z = Math.PI / 2;
  pneu.castShadow = true;
  g.add(pneu);

  const aro = new THREE.Mesh(new THREE.CylinderGeometry(raio * 0.62, raio * 0.62, largura + 0.04, 32), mats.aro);
  aro.rotation.z = Math.PI / 2;
  g.add(aro);
  const cubo = new THREE.Mesh(new THREE.CylinderGeometry(raio * 0.2, raio * 0.2, largura + 0.12, 16), mats.pneu);
  cubo.rotation.z = Math.PI / 2;
  g.add(cubo);

  // garras da banda de rodagem (em V, alternadas)
  const n = Math.round(raio * 30);
  const garra = new THREE.BoxGeometry(largura * 0.48, raio * 0.09, raio * 0.16);
  const garras = new THREE.InstancedMesh(garra, mats.pneu, n * 2);
  const m = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  const e = new THREE.Euler();
  for (let i = 0; i < n * 2; i++) {
    const lado = i % 2 ? 1 : -1;
    const ang = (i / 2 / n) * Math.PI * 2 + (lado > 0 ? Math.PI / n : 0);
    e.set(ang, lado * 0.45, 0);
    q.setFromEuler(e);
    const pos = new THREE.Vector3(lado * largura * 0.24, Math.cos(ang) * raio, Math.sin(ang) * raio);
    m.compose(pos, q, new THREE.Vector3(1, 1, 1));
    garras.setMatrixAt(i, m);
  }
  garras.castShadow = true;
  g.add(garras);
  return g;
}

export function criarTrator(): Trator {
  const grupo = new THREE.Group();
  const corpo = new THREE.MeshStandardMaterial({ color: CORES.corpo, roughness: 0.42, metalness: 0.35 });
  const corpoClaro = new THREE.MeshStandardMaterial({ color: CORES.corpoClaro, roughness: 0.5, metalness: 0.3 });
  const ouro = new THREE.MeshStandardMaterial({ color: CORES.ouro, roughness: 0.35, metalness: 0.55 });
  const pneu = new THREE.MeshStandardMaterial({ color: CORES.pneu, roughness: 0.92 });
  const vidro = new THREE.MeshPhysicalMaterial({
    color: CORES.vidro, roughness: 0.08, metalness: 0.1, transparent: true, opacity: 0.38,
  });
  const lampadas = new THREE.MeshStandardMaterial({ color: 0x222222, emissive: CORES.farol, emissiveIntensity: 2 });
  const giroflex = new THREE.MeshStandardMaterial({ color: 0x552a00, emissive: 0xff8a1f, emissiveIntensity: 1 });
  const mats = { pneu, aro: ouro };

  // chassi, capô e grade
  const chassi = caixa(1.0, 0.45, 3.9, corpoClaro);
  chassi.position.set(0, 0.95, -0.1);
  grupo.add(chassi);
  const capo = caixa(1.12, 0.92, 2.15, corpo, 0.16);
  capo.position.set(0, 1.42, -1.05);
  grupo.add(capo);
  const faixa = caixa(1.14, 0.08, 2.17, ouro, 0.03);
  faixa.position.set(0, 1.62, -1.05);
  grupo.add(faixa);
  const grade = caixa(1.0, 0.7, 0.08, corpoClaro, 0.03);
  grade.position.set(0, 1.38, -2.13);
  grupo.add(grade);
  for (const x of [-0.32, 0.32]) {
    const farol = new THREE.Mesh(new RoundedBoxGeometry(0.26, 0.12, 0.06, 2, 0.03), lampadas);
    farol.position.set(x, 1.7, -2.14);
    grupo.add(farol);
  }
  const peso = caixa(1.3, 0.42, 0.42, corpoClaro, 0.06);
  peso.position.set(0, 0.78, -2.35);
  grupo.add(peso);

  // cabine
  const vidros = caixa(1.42, 1.25, 1.35, vidro, 0.06);
  vidros.castShadow = false;
  vidros.position.set(0, 2.32, 0.75);
  grupo.add(vidros);
  for (const [x, z] of [[-0.7, 0.08], [0.7, 0.08], [-0.7, 1.42], [0.7, 1.42]]) {
    const coluna = new THREE.Mesh(new THREE.BoxGeometry(0.07, 1.3, 0.07), corpo);
    coluna.position.set(x, 2.32, z);
    coluna.castShadow = true;
    grupo.add(coluna);
  }
  const base = caixa(1.5, 0.3, 1.55, corpo, 0.06);
  base.position.set(0, 1.58, 0.75);
  grupo.add(base);
  const teto = caixa(1.62, 0.16, 1.66, corpo, 0.07);
  teto.position.set(0, 3.03, 0.75);
  grupo.add(teto);
  const tetoFaixa = caixa(1.64, 0.04, 1.68, ouro, 0.02);
  tetoFaixa.position.set(0, 2.95, 0.75);
  grupo.add(tetoFaixa);
  const luz = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.1, 0.14, 16), giroflex);
  luz.position.set(0.55, 3.18, 1.25);
  grupo.add(luz);

  // escapamento
  const escape = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.07, 1.25, 12), corpoClaro);
  escape.position.set(0.42, 2.28, -1.55);
  grupo.add(escape);

  // para-lamas traseiros
  for (const lado of [-1, 1]) {
    const pl = new THREE.Mesh(
      new THREE.CylinderGeometry(1.08, 1.08, 0.66, 32, 1, true, -Math.PI / 2, Math.PI),
      corpo,
    );
    pl.rotation.z = Math.PI / 2;
    pl.position.set(lado * 1.08, 1.0, 0.85);
    (pl.material as THREE.MeshStandardMaterial).side = THREE.DoubleSide;
    pl.castShadow = true;
    grupo.add(pl);
  }

  // rodas
  const rodas: Trator["rodas"] = [];
  for (const [x, z, r, w] of [
    [-1.08, 0.85, 0.98, 0.6], [1.08, 0.85, 0.98, 0.6],
    [-0.9, -1.55, 0.6, 0.4], [0.9, -1.55, 0.6, 0.4],
  ]) {
    const g = roda(r, w, mats);
    g.position.set(x, r, z);
    grupo.add(g);
    rodas.push({ grupo: g, raio: r });
  }

  // plantadeira atrás (barra + linhas)
  const barra = caixa(4.4, 0.18, 0.22, ouro, 0.04);
  barra.position.set(0, 0.62, 2.55);
  grupo.add(barra);
  const engate = caixa(0.2, 0.16, 0.8, corpoClaro, 0.03);
  engate.position.set(0, 0.7, 2.05);
  grupo.add(engate);
  for (let i = 0; i < 7; i++) {
    const linha = caixa(0.16, 0.5, 0.7, corpoClaro, 0.04);
    linha.position.set(-1.95 + i * 0.65, 0.45, 2.85);
    grupo.add(linha);
    const disco = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.2, 0.04, 20), ouro);
    disco.rotation.z = Math.PI / 2;
    disco.position.set(-1.95 + i * 0.65, 0.2, 3.05);
    grupo.add(disco);
  }

  // faróis de verdade (iluminam a lavoura à noite)
  const farois: THREE.SpotLight[] = [];
  for (const x of [-0.32, 0.32]) {
    const s = new THREE.SpotLight(CORES.farol, 0, 40, 0.5, 0.6, 1.4);
    s.position.set(x, 1.7, -2.2);
    s.target.position.set(x * 3, 0, -14);
    grupo.add(s, s.target);
    farois.push(s);
  }

  return { grupo, rodas, farois, lampadas, giroflex };
}
