import "./estilo.css";

import { Cena, type Quadro } from "./cena";

const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000/api/v1";
const APP_URL = (import.meta.env.VITE_APP_URL as string | undefined) ?? "http://localhost:5173";
const menosMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// ----------------------------------------------------------------- quadros-chave por seção
const BASE: Omit<Quadro, "dist" | "cam" | "alvo"> = {
  elevacao: -6, azimute: 95, nevoa: 0x18202e, exposicao: 0.85, noite: 1, calor: 0, alerta: 0, trilha: 0,
};
const QUADROS: Record<string, Quadro & { segura: number }> = {
  inicio: { ...BASE, dist: 0, cam: [4.6, 2.1, -8.4], alvo: [3.4, 1.5, 0.5], segura: 0 },
  coleta: {
    ...BASE, dist: 14, cam: [-8.5, 5.2, 9.5], alvo: [-3.8, 1.0, -2], elevacao: 9, azimute: 100, nevoa: 0xc9b29e,
    exposicao: 0.72, noite: 0.1, trilha: 1, segura: 4,
  },
  mapa: {
    ...BASE, dist: 30, cam: [0.5, 44, 10], alvo: [0, 0, -2], elevacao: 26, azimute: 115, nevoa: 0xb3c0cc,
    exposicao: 0.5, noite: 0, calor: 1, trilha: 0.6, segura: 1,
  },
  alertas: {
    ...BASE, dist: 35, cam: [7.5, 3.6, 2.2], alvo: [0, 1.3, 3.2], elevacao: 40, azimute: 135, nevoa: 0xbac6d0,
    exposicao: 0.5, noite: 0, calor: 0, alerta: 1, trilha: 0.6, segura: 0,
  },
  resultados: {
    ...BASE, dist: 50, cam: [12, 6.5, 1], alvo: [0, 1, -5.5], elevacao: 52, azimute: 165, nevoa: 0xbfcad3,
    exposicao: 0.48, noite: 0, trilha: 1, segura: 5,
  },
  contato: {
    ...BASE, dist: 72, cam: [-3.5, 2.6, 13], alvo: [0, 1.8, -10], elevacao: 6, azimute: 200, nevoa: 0xd6a582,
    exposicao: 0.72, noite: 0.05, trilha: 0.8, segura: 4,
  },
};

const canvas = document.querySelector<HTMLCanvasElement>("#cena")!;
const secoes = [...document.querySelectorAll<HTMLElement>("[data-cena]")];
let cena: Cena | null = null;
try {
  cena = new Cena(canvas);
} catch {
  // sem WebGL: a página continua legível sobre o fundo escuro
  canvas.remove();
}

function maxRolagem() {
  return Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
}

/** Cada seção vira dois quadros (entrada e saída do centro da tela): a cena "segura" enquanto se lê. */
function calcularQuadros() {
  if (!cena) return;
  const max = maxRolagem();
  const vh = window.innerHeight;
  const lista: { p: number; q: Quadro }[] = [];
  secoes.forEach((el, i) => {
    const q = QUADROS[el.dataset.cena!];
    if (i === 0) {
      lista.push({ p: 0, q });
      return;
    }
    if (i === secoes.length - 1) {
      lista.push({ p: 1, q });
      return;
    }
    const centro = el.offsetTop + el.offsetHeight / 2 - vh / 2;
    const meio = el.offsetHeight * 0.18;
    lista.push({ p: Math.min(1, (centro - meio) / max), q });
    lista.push({ p: Math.min(1, (centro + meio) / max), q: { ...q, dist: q.dist + q.segura } });
  });
  cena.definirQuadros(lista);
}

function redimensionar() {
  cena?.redimensionar(window.innerWidth, window.innerHeight);
  calcularQuadros();
}
window.addEventListener("resize", redimensionar);
redimensionar();
document.fonts?.ready.then(calcularQuadros);

// ----------------------------------------------------------------- laço de animação + HUD
const hud = {
  vel: document.getElementById("hud-vel")!,
  area: document.getElementById("hud-area")!,
  diesel: document.getElementById("hud-diesel")!,
  lha: document.getElementById("hud-lha")!,
};
const fmt = (v: number, casas: number) => v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });

let progresso = 0;
let anterior = performance.now();
let velocidade = 0;
let distHud = 0;
function quadro(agora: number) {
  const dt = Math.min(0.05, (agora - anterior) / 1000);
  anterior = agora;
  const alvo = window.scrollY / maxRolagem();
  progresso = menosMovimento ? alvo : progresso + (alvo - progresso) * (1 - Math.exp(-dt * 3.5));
  if (cena) {
    cena.quadro(progresso, agora / 1000, dt);
    const d = cena.distancia;
    const kmh = dt > 0 ? (Math.abs(d - distHud) / dt) * 0.9 : 0;
    distHud = d;
    velocidade += (Math.min(kmh, 12.4) - velocidade) * 0.08;
    const area = d * 0.52;
    hud.vel.textContent = fmt(velocidade, 1);
    hud.area.textContent = fmt(area, 2);
    hud.diesel.textContent = fmt(area * 4.26 + d * 0.15, 1);
    hud.lha.textContent = area > 0.5 ? fmt((area * 4.26 + d * 0.15) / area, 2) : "—";
  }
  requestAnimationFrame(quadro);
}
requestAnimationFrame(quadro);

// ----------------------------------------------------------------- topo, trilho e revelações
const topo = document.querySelector(".topo")!;
const pontos = [...document.querySelectorAll<HTMLElement>(".trilho li")];
const marcarAtiva = () => {
  topo.classList.toggle("rolado", window.scrollY > 40);
  const meio = window.scrollY + window.innerHeight / 2;
  let ativa = secoes[0].id;
  for (const s of secoes) if (s.offsetTop <= meio) ativa = s.id;
  pontos.forEach((p) => p.classList.toggle("ativo", p.dataset.alvo === ativa));
  document.body.classList.toggle("no-contato", ativa === "contato");
};
window.addEventListener("scroll", marcarAtiva, { passive: true });
marcarAtiva();
pontos.forEach((p) => p.addEventListener("click", () => document.getElementById(p.dataset.alvo!)?.scrollIntoView()));

const observador = new IntersectionObserver(
  (itens) => {
    for (const it of itens) {
      if (!it.isIntersecting) continue;
      const el = it.target as HTMLElement;
      const irmaos = [...(el.parentElement?.querySelectorAll(".revela") ?? [])];
      el.style.transitionDelay = `${Math.max(0, irmaos.indexOf(el)) * 80}ms`;
      el.classList.add("visivel");
      observador.unobserve(el);
    }
  },
  { threshold: 0.15 },
);
document.querySelectorAll(".revela").forEach((el) => observador.observe(el));

document.querySelectorAll<HTMLAnchorElement>("[data-app]").forEach((a) => (a.href = APP_URL));

// ----------------------------------------------------------------- formulário de demonstração
const form = document.querySelector<HTMLFormElement>("#form-contato")!;
const status = document.querySelector<HTMLElement>("#form-status")!;
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  status.className = "";
  if (!form.checkValidity()) {
    form.reportValidity();
    return;
  }
  const dados = new FormData(form);
  const texto = (k: string) => String(dados.get(k) ?? "").trim() || null;
  const inteiro = (k: string) => (texto(k) === null ? null : Number(texto(k)));
  const corpo = {
    nome: texto("nome"),
    email: texto("email"),
    telefone: texto("telefone"),
    fazenda: texto("fazenda"),
    hectares: inteiro("hectares"),
    maquinas: inteiro("maquinas"),
    mensagem: texto("mensagem"),
    website: texto("website"),
    origem: "site",
  };
  const botao = form.querySelector<HTMLButtonElement>("button[type=submit]")!;
  botao.disabled = true;
  status.textContent = "Enviando…";
  try {
    const r = await fetch(`${API_URL}/contatos`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo),
    });
    if (r.status === 429) throw new Error("Muitas tentativas seguidas. Tente de novo em um minuto.");
    if (!r.ok) {
      const p = await r.json().catch(() => null);
      throw new Error(p?.detail && typeof p.detail === "string" ? p.detail : "Confira os campos e tente de novo.");
    }
    form.reset();
    status.className = "ok";
    status.textContent = "Recebido! Entramos em contato em breve.";
  } catch (erro) {
    status.className = "erro";
    status.textContent = erro instanceof TypeError ? "Sem conexão com o servidor. Tente de novo." : (erro as Error).message;
  } finally {
    botao.disabled = false;
  }
});
