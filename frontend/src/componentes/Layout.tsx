import {
  BarChart3, Bell, ChevronDown, FileText, Home, ListChecks, LogOut, Map, Menu, Settings, Sprout, Tractor,
  Upload, X,
} from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { Marca } from "./Marca";

import { type Preset, usePeriodo, useSessao } from "../contextos/Sessao";

// O produtor abre o Resumo e as Máquinas; o resto fica em "Detalhado", para quem quer cavar.
const MENU: { grupo?: string; itens: { para: string; rotulo: string; icone: typeof Home }[] }[] = [
  {
    itens: [
      { para: "/", rotulo: "Resumo", icone: Home },
      { para: "/maquinas", rotulo: "Máquinas", icone: Tractor },
      { para: "/talhoes", rotulo: "Talhões", icone: Sprout },
      { para: "/mapa", rotulo: "Mapa", icone: Map },
    ],
  },
  {
    grupo: "Detalhado",
    itens: [
      { para: "/analise", rotulo: "Painel completo", icone: BarChart3 },
      { para: "/jornadas", rotulo: "Operações", icone: ListChecks },
      { para: "/alertas", rotulo: "Alertas", icone: Bell },
      { para: "/sessoes", rotulo: "Arquivos do monitor", icone: FileText },
    ],
  },
  {
    itens: [
      { para: "/enviar", rotulo: "Enviar pendrive", icone: Upload },
      { para: "/configuracoes", rotulo: "Configurações", icone: Settings },
    ],
  },
];

const PRESETS: { valor: Preset; rotulo: string }[] = [
  { valor: "7d", rotulo: "7 dias" },
  { valor: "30d", rotulo: "30 dias" },
  { valor: "90d", rotulo: "90 dias" },
  { valor: "safra", rotulo: "Safra" },
  { valor: "12m", rotulo: "12 meses" },
  { valor: "tudo", rotulo: "Tudo" },
];

export function SeletorPeriodo({ opcoes }: { opcoes?: Preset[] }) {
  const { periodo, setPreset } = usePeriodo();
  const lista = opcoes ? PRESETS.filter((p) => opcoes.includes(p.valor)) : PRESETS;
  return (
    <div className="flex flex-wrap gap-1 rounded-xl border border-white/10 bg-white/5 p-1 backdrop-blur" role="group" aria-label="Período">
      {lista.map((p) => (
        <button
          key={p.valor}
          onClick={() => setPreset(p.valor)}
          aria-pressed={periodo.preset === p.valor}
          className={`aba !px-2.5 !py-1 text-xs sm:!px-3 ${periodo.preset === p.valor ? "aba-ativa" : ""}`}
        >
          {p.rotulo}
        </button>
      ))}
    </div>
  );
}

function Navegacao({ aoNavegar }: { aoNavegar?: () => void }) {
  const { me, org, sair, trocarOrg } = useSessao();
  return (
    <div className="flex h-full flex-col">
      <div className="px-5 pb-5 pt-6">
        <Marca tamanho={24} className="text-broto-400" />
        <div className="mt-1.5 text-[11px] font-medium uppercase tracking-[0.18em] text-folha-900/50">gestão de frota agrícola</div>
      </div>

      {me && me.organizacoes.length > 1 ? (
        <div className="relative mx-4 mb-5">
          <select
            value={org?.organizacao_id}
            onChange={(e) => trocarOrg(e.target.value)}
            className="campo appearance-none pr-8 font-semibold"
            aria-label="Fazenda"
          >
            {me.organizacoes.map((o) => (
              <option key={o.organizacao_id} value={o.organizacao_id}>{o.nome}</option>
            ))}
          </select>
          <ChevronDown size={16} className="pointer-events-none absolute right-3 top-3 text-folha-900/60" />
        </div>
      ) : (
        <div className="mx-4 mb-5 rounded-xl border border-white/10 bg-white/5 px-3 py-2.5">
          <div className="text-[11px] uppercase tracking-wide text-folha-900/50">Fazenda</div>
          <div className="truncate text-sm font-semibold">{org?.nome ?? "—"}</div>
        </div>
      )}

      <nav className="flex-1 space-y-5 overflow-y-auto px-3" aria-label="Menu principal">
        {MENU.map((secao, i) => (
          <div key={i} className="space-y-1">
            {secao.grupo && (
              <div className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-folha-900/45">{secao.grupo}</div>
            )}
            {secao.itens.map(({ para, rotulo, icone: Icone }) => (
              <NavLink
                key={para}
                to={para}
                end={para === "/"}
                onClick={aoNavegar}
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition ${
                    isActive
                      ? "bg-broto-500/15 text-broto-300 ring-1 ring-broto-400/30"
                      : "text-folha-900/70 hover:bg-white/5 hover:text-folha-950"
                  }`
                }
              >
                <Icone size={18} aria-hidden="true" /> {rotulo}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      <div className="m-4 rounded-xl border border-white/10 bg-black/20 p-3">
        <div className="truncate text-xs text-folha-900/60">{me?.email}</div>
        <button onClick={sair} className="mt-2 flex items-center gap-2 text-xs font-semibold text-trigo-300 hover:text-trigo-200">
          <LogOut size={14} /> Sair
        </button>
      </div>
    </div>
  );
}

const LATERAL = "border-r border-white/10 bg-noite-900/70 backdrop-blur-xl";

export function Layout() {
  const [aberto, setAberto] = useState(false);
  return (
    <div className="min-h-screen lg:pl-64">
      <aside className={`fixed inset-y-0 left-0 z-30 hidden w-64 lg:block ${LATERAL}`}>
        <Navegacao />
      </aside>

      {aberto && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setAberto(false)} />
          <aside className={`absolute inset-y-0 left-0 w-72 ${LATERAL}`}>
            <button onClick={() => setAberto(false)} className="absolute right-3 top-6 text-folha-900/70" aria-label="Fechar menu"><X /></button>
            <Navegacao aoNavegar={() => setAberto(false)} />
          </aside>
        </div>
      )}

      <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-white/10 bg-noite-900/80 px-4 py-3 backdrop-blur lg:hidden">
        <button onClick={() => setAberto(true)} className="rounded-lg p-2 text-folha-950" aria-label="Abrir menu"><Menu /></button>
        <Marca tamanho={18} className="text-broto-400" />
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        <Outlet />
      </main>
    </div>
  );
}
