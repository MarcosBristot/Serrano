import { AlertTriangle, Loader2, type LucideIcon } from "lucide-react";
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
  folha: "bg-folha-50 text-folha-700",
  trigo: "bg-trigo-50 text-trigo-700",
  terra: "bg-terra-50 text-terra-700",
  ceu: "bg-sky-50 text-sky-700",
  rosa: "bg-rose-50 text-rose-700",
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
  info: "bg-sky-50 text-sky-700 ring-sky-600/15",
  atencao: "bg-trigo-50 text-trigo-800 ring-trigo-600/20",
  alto: "bg-rose-50 text-rose-700 ring-rose-600/20",
  ok: "bg-folha-50 text-folha-700 ring-folha-600/20",
  neutro: "bg-folha-900/5 text-folha-900/70 ring-folha-900/10",
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
      <div className="mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-folha-50 text-3xl">🌱</div>
      <h3 className="text-lg font-bold">{titulo}</h3>
      {texto && <p className="mt-1 max-w-md text-sm text-folha-900/60">{texto}</p>}
      {acao && <div className="mt-5">{acao}</div>}
    </div>
  );
}

export function Erro({ erro }: { erro: unknown }) {
  const e = erro instanceof ErroApi ? erro : null;
  return (
    <div className="cartao flex items-start gap-3 border-rose-200 bg-rose-50/60 p-4 text-sm text-rose-800">
      <AlertTriangle size={18} className="mt-0.5 shrink-0" />
      <div>
        <div className="font-semibold">{e?.message ?? (erro instanceof Error ? erro.message : "Algo deu errado")}</div>
        {e?.requestId && <div className="mt-1 text-xs opacity-70">Código para o suporte: {e.requestId}</div>}
      </div>
    </div>
  );
}
