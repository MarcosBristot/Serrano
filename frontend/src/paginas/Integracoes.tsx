/** Integrações: o diferencial da Serrano, dados de marcas e sistemas diferentes num painel só. */
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight, Braces, CheckCircle2, Clock3, Cloud, FileSpreadsheet, Map, MonitorSmartphone, Send, Sparkles,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router-dom";

import { Cabecalho, Carregando, Erro, Selo } from "../componentes/ui";
import { api } from "../lib/api";
import { data, num } from "../lib/formato";

interface Integracao {
  id: string;
  categoria: "monitor" | "mapa" | "saida" | "nuvem";
  nome: string;
  detalhe: string;
  status: "ativa" | "roteiro";
  em_uso: boolean;
  sessoes: number;
  maquinas: number;
  ultimo_dado: string | null;
  ultimo_envio: string | null;
}

const ICONE: Record<string, LucideIcon> = {
  monitor: MonitorSmartphone,
  mapa: Map,
  nuvem: Cloud,
  planilha: FileSpreadsheet,
  webhook: Send,
  api: Braces,
};

function Cartao({ i }: { i: Integracao }) {
  const Icone = ICONE[i.id] ?? ICONE[i.categoria] ?? MonitorSmartphone;
  const roteiro = i.status === "roteiro";
  return (
    <article
      className={`cartao relative flex flex-col gap-3 p-5 transition ${
        i.em_uso ? "!border-broto-400/40 shadow-[0_0_30px_-12px_rgba(140,198,63,.6)]" : ""
      } ${roteiro ? "opacity-70" : "hover:-translate-y-0.5"}`}
    >
      <div className="flex items-start justify-between gap-3">
        <span
          className={`grid h-11 w-11 place-items-center rounded-xl ring-1 ${
            i.em_uso ? "bg-broto-500/15 text-broto-300 ring-broto-400/30" : "bg-white/5 text-folha-900/70 ring-white/10"
          }`}
        >
          <Icone size={20} aria-hidden="true" />
        </span>
        {i.em_uso ? (
          <Selo tom="ok"><CheckCircle2 size={12} /> Conectado</Selo>
        ) : roteiro ? (
          <Selo><Clock3 size={12} /> Em breve</Selo>
        ) : (
          <Selo tom="info">Disponível</Selo>
        )}
      </div>
      <div>
        <h3 className="font-display text-base font-bold text-folha-950">{i.nome}</h3>
        <p className="mt-1 text-sm text-folha-900/60">{i.detalhe}</p>
      </div>
      {i.em_uso && (
        <dl className="mt-auto grid grid-cols-3 gap-2 border-t border-white/5 pt-3 text-xs">
          <div><dt className="text-folha-900/50">Arquivos</dt><dd className="font-display text-sm font-bold">{num(i.sessoes, 0)}</dd></div>
          <div><dt className="text-folha-900/50">Máquinas</dt><dd className="font-display text-sm font-bold">{num(i.maquinas, 0)}</dd></div>
          <div><dt className="text-folha-900/50">Último dado</dt><dd className="font-display text-sm font-bold">{data(i.ultimo_dado ?? i.ultimo_envio)}</dd></div>
        </dl>
      )}
    </article>
  );
}

/** Desenho do "hub": as fontes chegam por um lado, a Serrano no meio, as saídas do outro. */
function Hub({ entradas, saidas }: { entradas: Integracao[]; saidas: Integracao[] }) {
  const linha = (lista: Integracao[], lado: "e" | "d") =>
    lista.map((i, k) => {
      const y = 30 + (k * 200) / Math.max(1, lista.length - 1);
      const x0 = lado === "e" ? 150 : 450;
      const x1 = lado === "e" ? 255 : 345;
      return (
        <g key={i.id}>
          <path
            d={`M${x0} ${y} C ${(x0 + x1) / 2} ${y}, ${(x0 + x1) / 2} 130, ${x1} 130`}
            fill="none"
            stroke={i.em_uso ? "#8cc63f" : "rgba(226,238,220,.18)"}
            strokeWidth={i.em_uso ? 2 : 1.2}
            strokeDasharray={i.em_uso ? "6 6" : "3 5"}
            className={i.em_uso ? "fluxo" : ""}
          />
          <text
            x={lado === "e" ? x0 - 8 : x0 + 8}
            y={y + 4}
            textAnchor={lado === "e" ? "end" : "start"}
            fontSize="12"
            fontWeight={i.em_uso ? 700 : 500}
            fill={i.em_uso ? "#e2eedc" : "rgba(226,238,220,.5)"}
          >
            {i.nome}
          </text>
          <circle cx={x0} cy={y} r="4" fill={i.em_uso ? "#8cc63f" : "rgba(226,238,220,.3)"} />
        </g>
      );
    });
  return (
    <svg viewBox="0 0 600 260" className="h-auto w-full" role="img" aria-label="Fontes de dados ligadas à Serrano e saídas para outros sistemas">
      {linha(entradas, "e")}
      {linha(saidas, "d")}
      <circle cx="300" cy="130" r="54" fill="rgba(140,198,63,.08)" stroke="rgba(140,198,63,.35)" />
      <circle cx="300" cy="130" r="40" fill="#0c1f11" stroke="#8cc63f" strokeWidth="2" />
      <path d="M279 142 288 125l6 10 8-17 14 24" fill="none" stroke="#8cc63f" strokeWidth="4" strokeLinejoin="round" />
      <text x="300" y="205" textAnchor="middle" fontSize="12" fontWeight="700" fill="#c8ec8a">SERRANO</text>
    </svg>
  );
}

export default function Integracoes() {
  const q = useQuery({ queryKey: ["integracoes"], queryFn: () => api<Integracao[]>("/integracoes") });
  if (q.isLoading) return <Carregando />;
  if (q.error) return <Erro erro={q.error} />;
  const itens = q.data ?? [];
  const ativas = itens.filter((i) => i.status === "ativa");
  const entradas = ativas.filter((i) => i.categoria !== "saida");
  const saidas = ativas.filter((i) => i.categoria === "saida");
  const roteiro = itens.filter((i) => i.status === "roteiro");
  const conectadas = itens.filter((i) => i.em_uso).length;

  return (
    <>
      <Cabecalho
        titulo="Integrações"
        sub="Cada marca grava num formato. A Serrano lê todos e junta num painel só."
        acoes={<Link to="/enviar" className="btn-primario">Enviar pendrive <ArrowRight size={16} /></Link>}
      />

      <section className="cartao-destaque mb-6 grid items-center gap-6 overflow-hidden p-6 lg:grid-cols-[1fr_1.4fr]">
        <div>
          <Selo tom="ok"><Sparkles size={12} /> {conectadas} fonte{conectadas === 1 ? "" : "s"} conectada{conectadas === 1 ? "" : "s"}</Selo>
          <h2 className="mt-3 font-display text-2xl font-extrabold leading-tight text-folha-950">
            Uma central para a frota inteira, <span className="text-broto-400">de qualquer marca.</span>
          </h2>
          <p className="mt-3 text-sm text-folha-900/65">
            Trator John Deere, colheitadeira com GreenStar, pulverizador ISOBUS: cada um fala uma língua e os
            softwares das marcas não conversam entre si. A Serrano traduz tudo para os mesmos números (horas, diesel,
            área, L/ha e R$/ha) e devolve para a sua planilha, o seu ERP ou o seu e-mail.
          </p>
        </div>
        <Hub entradas={entradas} saidas={saidas} />
      </section>

      <h2 className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-folha-900/50">Entrada de dados</h2>
      <div className="mb-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{entradas.map((i) => <Cartao key={i.id} i={i} />)}</div>

      <h2 className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-folha-900/50">Saída para outros sistemas</h2>
      <div className="mb-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{saidas.map((i) => <Cartao key={i.id} i={i} />)}</div>

      <h2 className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-folha-900/50">No roteiro</h2>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{roteiro.map((i) => <Cartao key={i.id} i={i} />)}</div>
      <p className="mt-4 text-xs text-folha-900/50">
        Usa outro monitor ou sistema? Fale com a gente: as próximas integrações seguem o que os clientes mais usam.
      </p>
    </>
  );
}
