import { AlertTriangle, Loader2, SprayCan, Sprout, Tractor, Wheat, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { ErroApi } from "../lib/api";

export function Cabecalho({ titulo, sub, acoes }: { titulo: string; sub?: string; acoes?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-extrabold text-folha-950 sm:text-3xl">{titulo}</h1>
        {sub && <p className="mt-1 text-sm text-folha-900/60">{sub}</p>}
      </div>
      {acoes && <div className="flex flex-wrap items-center gap-2">{acoes}</div>}
    </div>
  );
}

const TONS = {
  folha: "bg-broto-500/15 text-broto-300 ring-1 ring-broto-400/20",
  trigo: "bg-trigo-400/15 text-trigo-300 ring-1 ring-trigo-400/20",
  terra: "bg-terra-500/20 text-terra-700 ring-1 ring-terra-500/25",
  ceu: "bg-sky-400/15 text-sky-300 ring-1 ring-sky-400/20",
  rosa: "bg-rose-400/15 text-rose-300 ring-1 ring-rose-400/20",
};

export function Kpi({
  rotulo, valor, unidade, icone: Icone, tom = "folha", detalhe,
}: {
  rotulo: string; valor: string; unidade?: string; icone: LucideIcon; tom?: keyof typeof TONS; detalhe?: ReactNode;
}) {
  return (
    <div className="cartao p-5">
      <div className="flex items-start justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-folha-900/55">{rotulo}</span>
        <span className={`rounded-xl p-2 ${TONS[tom]}`}><Icone size={18} /></span>
      </div>
      <div className="mt-3 flex items-baseline gap-1.5">
        <span className="font-display text-3xl font-extrabold text-folha-950">{valor}</span>
        {unidade && <span className="text-sm font-medium text-folha-900/50">{unidade}</span>}
      </div>
      {detalhe && <div className="mt-2 text-xs text-folha-900/55">{detalhe}</div>}
    </div>
  );
}

const SELO = {
  info: "bg-sky-400/15 text-sky-300 ring-sky-400/25",
  atencao: "bg-trigo-400/15 text-trigo-300 ring-trigo-400/30",
  alto: "bg-rose-400/15 text-rose-300 ring-rose-400/30",
  ok: "bg-broto-500/15 text-broto-300 ring-broto-400/30",
  neutro: "bg-white/5 text-folha-900/70 ring-white/10",
};

export function Selo({ tom = "neutro", children }: { tom?: keyof typeof SELO; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${SELO[tom]}`}>
      {children}
    </span>
  );
}

export function seloQualidade(score: number | null | undefined) {
  if (score == null) return <Selo>—</Selo>;
  return <Selo tom={score >= 85 ? "ok" : score >= 60 ? "atencao" : "alto"}>{score}</Selo>;
}

export function Carregando({ texto = "Carregando…" }: { texto?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-folha-900/60">
      <Loader2 className="animate-spin" size={18} /> {texto}
    </div>
  );
}

export function Vazio({ titulo, texto, acao }: { titulo: string; texto?: string; acao?: ReactNode }) {
  return (
    <div className="cartao flex flex-col items-center px-6 py-14 text-center">
      <div className="mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-broto-500/15 text-broto-300 ring-1 ring-broto-400/20"><Sprout size={28} /></div>
      <h3 className="text-lg font-bold">{titulo}</h3>
      {texto && <p className="mt-1 max-w-md text-sm text-folha-900/60">{texto}</p>}
      {acao && <div className="mt-5">{acao}</div>}
    </div>
  );
}

export function Erro({ erro }: { erro: unknown }) {
  const e = erro instanceof ErroApi ? erro : null;
  return (
    <div className="cartao flex items-start gap-3 !border-rose-400/30 p-4 text-sm text-rose-200">
      <AlertTriangle size={18} className="mt-0.5 shrink-0" />
      <div>
        <div className="font-semibold">{e?.message ?? (erro instanceof Error ? erro.message : "Algo deu errado")}</div>
        {e?.requestId && <div className="mt-1 text-xs opacity-70">Código para o suporte: {e.requestId}</div>}
      </div>
    </div>
  );
}

/** Tipo da máquina pelo que ela faz (a API classifica). */
export const TIPO_MAQUINA: Record<string, { rotulo: string; icone: LucideIcon; cor: string }> = {
  trator: { rotulo: "Trator", icone: Tractor, cor: "text-broto-300 bg-broto-500/15 ring-broto-400/25" },
  colheitadeira: { rotulo: "Colheitadeira", icone: Wheat, cor: "text-trigo-300 bg-trigo-400/15 ring-trigo-400/25" },
  pulverizador: { rotulo: "Pulverizador", icone: SprayCan, cor: "text-sky-300 bg-sky-400/15 ring-sky-400/25" },
};

export function IconeMaquina({ tipo, tamanho = 22 }: { tipo: string; tamanho?: number }) {
  const t = TIPO_MAQUINA[tipo] ?? TIPO_MAQUINA.trator;
  const Icone = t.icone;
  return (
    <span className={`grid shrink-0 place-items-center rounded-2xl ring-1 ${t.cor}`} style={{ width: tamanho * 2, height: tamanho * 2 }}>
      <Icone size={tamanho} aria-hidden="true" />
    </span>
  );
}

/** Medidor em arco (0-100). Verde = bom; quando ``inverso``, quanto menor melhor. */
export function Medidor({
  valor, rotulo, sub, inverso = false, tamanho = 148,
}: { valor: number | null | undefined; rotulo: string; sub?: string; inverso?: boolean; tamanho?: number }) {
  const v = Math.max(0, Math.min(100, valor ?? 0));
  const bom = inverso ? 100 - v : v;
  const cor = bom >= 75 ? "#8cc63f" : bom >= 50 ? "#e6b034" : "#f87171";
  const r = 52, c = Math.PI * r; // meia-volta
  return (
    <div className="flex flex-col items-center" role="img" aria-label={`${rotulo}: ${valor == null ? "sem dado" : Math.round(v) + "%"}`}>
      <svg width={tamanho} height={tamanho * 0.62} viewBox="0 0 128 80">
        <path d="M12 70 A52 52 0 0 1 116 70" fill="none" stroke="rgba(255,255,255,.08)" strokeWidth="11" strokeLinecap="round" />
        <path d="M12 70 A52 52 0 0 1 116 70" fill="none" stroke={cor} strokeWidth="11" strokeLinecap="round"
          strokeDasharray={`${(c * v) / 100} ${c}`} style={{ filter: `drop-shadow(0 0 6px ${cor}66)` }} />
        <text x="64" y="64" textAnchor="middle" className="fill-folha-950 font-display" fontSize="24" fontWeight="800">
          {valor == null ? "—" : `${Math.round(v)}%`}
        </text>
      </svg>
      <div className="-mt-1 text-sm font-semibold">{rotulo}</div>
      {sub && <div className="text-xs text-folha-900/60">{sub}</div>}
    </div>
  );
}
