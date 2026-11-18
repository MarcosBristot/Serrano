import "./base";
import "./inicio.css";

import empresa from "../empresa.json";

const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000/api/v1";
const APP_URL = (import.meta.env.VITE_APP_URL as string | undefined) ?? "http://localhost:5173";
const SVG = "http://www.w3.org/2000/svg";

const fmt = (v: number, casas = 0) =>
  v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });

// ----------------------------------------------------------------- links para o painel
document.querySelectorAll<HTMLAnchorElement>("[data-app]").forEach((a) => (a.href = APP_URL));
document
  .querySelectorAll<HTMLAnchorElement>("[data-app-cadastro]")
  .forEach((a) => (a.href = `${APP_URL.replace(/\/$/, "")}/?cadastro`));

// ----------------------------------------------------------------- mapa de calor ilustrativo
/** Ruído suave e determinístico (mesma imagem a cada visita). */
function ruido(x: number, y: number) {
  return (
    0.5 +
    0.28 * Math.sin(x * 0.021 + 1.3) * Math.cos(y * 0.034 - 0.4) +
    0.16 * Math.sin((x + y) * 0.047) +
    0.08 * Math.cos(x * 0.09 - y * 0.06)
  );
}
const CORES = ["#2f8a57", "#5fa84a", "#a9c23f", "#e9b949", "#e8873a", "#d9482b"];

function desenharMapa() {
  const svg = document.getElementById("mapa-calor");
  if (!svg) return;
  // contorno do talhão (irregular, como um talhão de verdade)
  const contorno = "M38 40 L300 22 L372 70 L360 178 L210 204 L60 190 L22 120 Z";
  const defs = document.createElementNS(SVG, "defs");
  defs.innerHTML = `<clipPath id="talhao"><path d="${contorno}"/></clipPath>`;
  svg.append(defs);

  const g = document.createElementNS(SVG, "g");
  g.setAttribute("clip-path", "url(#talhao)");
  const r = 9;
  const w = Math.sqrt(3) * r;
  let i = 0;
  for (let linha = 0, y = 0; y < 240; linha++, y += r * 1.5) {
    for (let x = linha % 2 ? w / 2 : 0; x < 420; x += w) {
      const v = Math.min(0.999, Math.max(0, ruido(x, y)));
      const hex = document.createElementNS(SVG, "polygon");
      const pts = Array.from({ length: 6 }, (_, k) => {
        const a = (Math.PI / 3) * k + Math.PI / 6;
        return `${(x + r * 0.94 * Math.cos(a)).toFixed(1)},${(y + r * 0.94 * Math.sin(a)).toFixed(1)}`;
      }).join(" ");
      hex.setAttribute("points", pts);
      hex.setAttribute("fill", CORES[Math.floor(v * CORES.length)]);
      hex.style.setProperty("--atraso", `${(i++ % 37) * 18 + x * 1.2}ms`);
      g.append(hex);
    }
  }
  svg.append(g);

  // passadas da máquina por cima do mapa
  const passadas = document.createElementNS(SVG, "g");
  passadas.setAttribute("clip-path", "url(#talhao)");
  passadas.setAttribute("class", "passadas");
  for (let y = 30; y < 210; y += 22) {
    const p = document.createElementNS(SVG, "path");
    p.setAttribute("d", `M0 ${y} L420 ${y - 14}`);
    passadas.append(p);
  }
  svg.append(passadas);

  const borda = document.createElementNS(SVG, "path");
  borda.setAttribute("d", contorno);
  borda.setAttribute("class", "borda");
  svg.append(borda);

  // máquina percorrendo a passada
  const maquina = document.createElementNS(SVG, "circle");
  maquina.setAttribute("r", "5");
  maquina.setAttribute("class", "maquina");
  svg.append(maquina);
  const anel = document.createElementNS(SVG, "circle");
  anel.setAttribute("r", "5");
  anel.setAttribute("class", "anel");
  svg.append(anel);

  const reduzir = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let t0 = performance.now();
  const passo = (agora: number) => {
    const t = ((agora - t0) / 9000) % 1;
    const faixa = Math.floor(((agora - t0) / 9000) % 7);
    const ida = faixa % 2 === 0;
    const x = 40 + (ida ? t : 1 - t) * 320;
    const y0 = 52 + faixa * 22;
    const y = y0 - (x / 420) * 14;
    for (const c of [maquina, anel]) {
      c.setAttribute("cx", x.toFixed(1));
      c.setAttribute("cy", y.toFixed(1));
    }
    requestAnimationFrame(passo);
  };
  if (reduzir) {
    for (const c of [maquina, anel]) {
      c.setAttribute("cx", "220");
      c.setAttribute("cy", "110");
    }
  } else {
    t0 = performance.now();
    requestAnimationFrame(passo);
  }
}

function desenharGrafico() {
  const linha = document.getElementById("linha-grafico");
  const area = document.getElementById("area-grafico");
  if (!linha || !area) return;
  const n = 24;
  const pts = Array.from({ length: n }, (_, k) => {
    const x = (k / (n - 1)) * 300;
    const v = 0.5 + 0.22 * Math.sin(k * 0.7) + 0.12 * Math.cos(k * 1.9) + (k === 15 ? 0.3 : 0);
    return [x, 56 - v * 46] as const;
  });
  const d = pts.map(([x, y], k) => `${k ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  linha.setAttribute("d", d);
  area.setAttribute("d", `${d} L300 60 L0 60 Z`);
}

desenharMapa();
desenharGrafico();

// ----------------------------------------------------------------- calculadora de economia
function calculadora() {
  const campo = (id: string) => document.getElementById(id) as HTMLInputElement;
  const saida = (id: string) => document.getElementById(id) as HTMLOutputElement;
  const area = campo("c-area");
  const passadas = campo("c-passadas");
  const reducao = campo("c-reducao");
  const preco = campo("c-preco");
  const reais = document.getElementById("r-reais")!;
  const litros = document.getElementById("r-litros")!;
  if (!area) return;

  const atualizar = () => {
    const a = Number(area.value);
    const p = Number(passadas.value);
    const r = Number(reducao.value);
    const d = Number(preco.value);
    saida("o-area").textContent = `${fmt(a)} ha`;
    saida("o-passadas").textContent = `${p}×`;
    saida("o-reducao").textContent = `${fmt(r, 1)} L/ha`;
    saida("o-preco").textContent = `R$ ${fmt(d, 2)}/L`;
    const l = a * p * r;
    reais.textContent = `R$ ${fmt(l * d)}`;
    litros.textContent = `${fmt(l)} litros de diesel a menos`;
    for (const c of [area, passadas, reducao, preco]) {
      const pct = ((Number(c.value) - Number(c.min)) / (Number(c.max) - Number(c.min))) * 100;
      c.style.setProperty("--pct", `${pct}%`);
    }
  };
  document.getElementById("calculadora")!.addEventListener("input", atualizar);
  atualizar();
}
calculadora();

// ----------------------------------------------------------------- planos: mensal ou anual
const botoesCiclo = [...document.querySelectorAll<HTMLButtonElement>("[data-ciclo]")];
function mostrarCiclo(ciclo: string) {
  botoesCiclo.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.ciclo === ciclo)));
  document.querySelectorAll<HTMLElement>(".preco b[data-mensal]").forEach((b) => {
    b.textContent = (ciclo === "anual" ? b.dataset.anual : b.dataset.mensal) ?? b.textContent;
  });
  document.querySelectorAll<HTMLElement>("[data-anual-total]").forEach((el) => {
    el.textContent = ciclo === "anual" ? (el.dataset.anualTotal ?? "") : "";
  });
}
botoesCiclo.forEach((b) => b.addEventListener("click", () => mostrarCiclo(b.dataset.ciclo!)));

// ----------------------------------------------------------------- topo e menu
const topo = document.querySelector(".topo")!;
const marcarRolado = () => topo.classList.toggle("rolado", window.scrollY > 20);
window.addEventListener("scroll", marcarRolado, { passive: true });
marcarRolado();

// menu em telas pequenas: botão com aria-expanded, fecha com Esc e ao escolher um item
const botaoMenu = document.querySelector<HTMLButtonElement>(".menu-botao")!;
const menu = document.querySelector<HTMLElement>("#menu")!;
const alternarMenu = (abrir: boolean) => {
  menu.classList.toggle("aberto", abrir);
  botaoMenu.setAttribute("aria-expanded", String(abrir));
};
botaoMenu.addEventListener("click", () => alternarMenu(!menu.classList.contains("aberto")));
menu.addEventListener("click", (e) => (e.target as HTMLElement).closest("a") && alternarMenu(false));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && menu.classList.contains("aberto")) {
    alternarMenu(false);
    botaoMenu.focus();
  }
});

// ----------------------------------------------------------------- revelação ao rolar
const observador = new IntersectionObserver(
  (itens) => {
    for (const it of itens) {
      if (!it.isIntersecting) continue;
      const el = it.target as HTMLElement;
      const irmaos = [...(el.parentElement?.querySelectorAll(":scope > .revela") ?? [])];
      el.style.transitionDelay = `${Math.max(0, irmaos.indexOf(el)) * 70}ms`;
      el.classList.add("visivel");
      observador.unobserve(el);
    }
  },
  { threshold: 0.12 },
);
document.querySelectorAll(".revela").forEach((el) => observador.observe(el));

// ----------------------------------------------------------------- formulário de demonstração
const form = document.querySelector<HTMLFormElement>("#form-contato")!;
const status = document.querySelector<HTMLElement>("#form-status")!;

/** Erros em texto ao lado do campo (lidos pelo leitor de tela) e foco no primeiro inválido. */
function validar(): boolean {
  const regras: [string, string, (v: string) => boolean][] = [
    ["f-nome", "Informe seu nome (pelo menos 2 letras).", (v) => v.trim().length >= 2],
    ["f-email", "Informe um e-mail válido, como nome@fazenda.com.br.", (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.trim())],
  ];
  let primeiro: HTMLInputElement | null = null;
  for (const [id, msg, ok] of regras) {
    const campo = document.getElementById(id) as HTMLInputElement;
    const erro = document.getElementById(campo.getAttribute("aria-describedby")!)!;
    const valido = ok(campo.value);
    campo.setAttribute("aria-invalid", String(!valido));
    erro.textContent = valido ? "" : msg;
    if (!valido && !primeiro) primeiro = campo;
  }
  primeiro?.focus();
  return !primeiro;
}
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  status.className = "";
  if (!validar()) return;
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
    aceita_novidades: dados.get("aceita_novidades") === "on",
    politica_versao: empresa.versaoDocumentos,
    origem: "site",
  };
  const botao = form.querySelector<HTMLButtonElement>("button[type=submit]")!;
  botao.disabled = true;
  status.textContent = "Enviando…";
  try {
    const r = await fetch(`${API_URL}/contatos`, {
      method: "POST",
      // ngrok-skip-browser-warning: API exposta pelo ngrok (plano grátis) mostraria a página de aviso.
      headers: { "Content-Type": "application/json", "ngrok-skip-browser-warning": "1" },
      body: JSON.stringify(corpo),
    });
    if (r.status === 429) throw new Error("Muitas tentativas seguidas. Tente de novo em um minuto.");
    if (!r.ok) {
      const p = await r.json().catch(() => null);
      throw new Error(p?.detail && typeof p.detail === "string" ? p.detail : "Confira os campos e tente de novo.");
    }
    form.reset();
    status.className = "ok";
    status.textContent = "Pedido recebido. Vamos responder pelo e-mail informado.";
  } catch (erro) {
    status.className = "erro";
    status.textContent = erro instanceof TypeError ? "Sem conexão com o servidor. Tente de novo." : (erro as Error).message;
  } finally {
    botao.disabled = false;
  }
});
