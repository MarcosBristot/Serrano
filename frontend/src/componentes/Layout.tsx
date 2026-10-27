import {
  Bell, ChevronDown, Gauge, LayoutDashboard, LogOut, Map, Menu, Settings, Sprout, Tractor, Upload, X,
} from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { type Preset, usePeriodo, useSessao } from "../contextos/Sessao";

const MENU = [
  { para: "/", rotulo: "Painel", icone: LayoutDashboard },
  { para: "/mapa", rotulo: "Mapa", icone: Map },
  { para: "/sessoes", rotulo: "Operações", icone: Tractor },
  { para: "/alertas", rotulo: "Alertas", icone: Bell },
  { para: "/talhoes", rotulo: "Talhões", icone: Sprout },
  { para: "/enviar", rotulo: "Enviar pendrive", icone: Upload },
  { para: "/configuracoes", rotulo: "Configurações", icone: Settings },
];

const PRESETS: { valor: Preset; rotulo: string }[] = [
  { valor: "7d", rotulo: "7 dias" },
  { valor: "30d", rotulo: "30 dias" },
  { valor: "90d", rotulo: "90 dias" },
  { valor: "safra", rotulo: "Safra atual" },
  { valor: "12m", rotulo: "12 meses" },
  { valor: "tudo", rotulo: "Tudo" },
];

export function SeletorPeriodo() {
  const { periodo, setPreset } = usePeriodo();
  return (
    <div className="flex rounded-xl bg-white p-1 shadow-cartao ring-1 ring-folha-950/5">
      {PRESETS.map((p) => (
        <button
          key={p.valor}
          onClick={() => setPreset(p.valor)}
          className={`rounded-lg px-2.5 py-1.5 text-xs font-semibold transition sm:px-3 ${
            periodo.preset === p.valor ? "bg-folha-700 text-white" : "text-folha-900/60 hover:text-folha-900"
          }`}
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
      <div className="flex items-center gap-3 px-5 py-6">
        <div className="grid h-10 w-10 place-items-center rounded-xl bg-trigo-400 text-folha-950">
          <Gauge size={22} strokeWidth={2.5} />
        </div>
        <div>
          <div className="font-display text-xl font-extrabold tracking-tight text-white">Campero</div>
          <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-folha-200/60">gestão de frota</div>
        </div>
      </div>

      {me && me.organizacoes.length > 1 ? (
        <div className="relative mx-4 mb-4">
          <select
            value={org?.organizacao_id}
            onChange={(e) => trocarOrg(e.target.value)}
            className="w-full appearance-none rounded-xl bg-white/10 px-3 py-2.5 pr-8 text-sm font-semibold text-white outline-none"
          >
            {me.organizacoes.map((o) => (
              <option key={o.organizacao_id} value={o.organizacao_id} className="text-folha-950">{o.nome}</option>
            ))}
          </select>
          <ChevronDown size={16} className="pointer-events-none absolute right-3 top-3 text-white/60" />
        </div>
      ) : (
        <div className="mx-4 mb-4 rounded-xl bg-white/10 px-3 py-2.5">
          <div className="text-[11px] uppercase tracking-wide text-folha-200/60">Fazenda</div>
          <div className="truncate text-sm font-semibold text-white">{org?.nome ?? "—"}</div>
        </div>
      )}

      <nav className="flex-1 space-y-1 px-3">
        {MENU.map(({ para, rotulo, icone: Icone }) => (
          <NavLink
            key={para}
            to={para}
            end={para === "/"}
            onClick={aoNavegar}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition ${
                isActive ? "bg-white text-folha-900 shadow" : "text-folha-100/80 hover:bg-white/10 hover:text-white"
              }`
            }
          >
            <Icone size={18} /> {rotulo}
          </NavLink>
        ))}
      </nav>

      <div className="m-4 rounded-xl bg-black/15 p-3">
        <div className="truncate text-xs text-folha-100/70">{me?.email}</div>
        <button onClick={sair} className="mt-2 flex items-center gap-2 text-xs font-semibold text-trigo-300 hover:text-trigo-200">
          <LogOut size={14} /> Sair
        </button>
      </div>
    </div>
  );
}

export function Layout() {
  const [aberto, setAberto] = useState(false);
  return (
    <div className="min-h-screen lg:pl-64">
      <aside className="fundo-lavoura fixed inset-y-0 left-0 z-30 hidden w-64 lg:block">
        <Navegacao />
      </aside>

      {aberto && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setAberto(false)} />
          <aside className="fundo-lavoura absolute inset-y-0 left-0 w-72">
            <button onClick={() => setAberto(false)} className="absolute right-3 top-6 text-white/70"><X /></button>
            <Navegacao aoNavegar={() => setAberto(false)} />
          </aside>
        </div>
      )}

      <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-folha-950/5 bg-[#f6f7f2]/90 px-4 py-3 backdrop-blur lg:hidden">
        <button onClick={() => setAberto(true)} className="rounded-lg p-2 text-folha-900"><Menu /></button>
        <span className="font-display text-lg font-extrabold">Campero</span>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        <Outlet />
      </main>
    </div>
  );
}
