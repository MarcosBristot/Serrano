/** Início do produtor: o essencial em linguagem direta. O detalhe fica em "Análise detalhada". */
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, Coins, Fuel, Hourglass, LandPlot, Tractor, TriangleAlert } from "lucide-react";
import { Link } from "react-router-dom";

import { Carregando, Erro, Vazio } from "../componentes/ui";
import { type Preset, usePeriodo, useSessao } from "../contextos/Sessao";
import { api } from "../lib/api";
import { horas, num, pct, rs } from "../lib/formato";
import type { Alerta, ItemRanking, Jornada, Pagina, Resumo } from "../lib/tipos";

const PERIODOS: { valor: Preset; rotulo: string }[] = [
  { valor: "30d", rotulo: "Últimos 30 dias" },
  { valor: "safra", rotulo: "Safra atual" },
  { valor: "tudo", rotulo: "Tudo" },
];

function quando(iso: string): string {
  const d = new Date(iso);
  const hoje = new Date();
  const dias = Math.floor((new Date(hoje.toDateString()).getTime() - new Date(d.toDateString()).getTime()) / 86_400_000);
  if (dias === 0) return "hoje";
  if (dias === 1) return "ontem";
  if (dias < 7) return `há ${dias} dias`;
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: dias > 300 ? "numeric" : undefined });
}

const maiuscula = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);
const hora = (iso: string) => new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });

export default function Inicio() {
  const { org } = useSessao();
  const { periodo, setPreset } = usePeriodo();
  const f = { inicio: periodo.inicio, fim: periodo.fim };
  const resumo = useQuery({ queryKey: ["resumo", f], queryFn: () => api<Resumo>("/kpis/resumo", { params: f }) });
  const talhoes = useQuery({
    queryKey: ["ranking", "talhao", f],
    queryFn: () => api<ItemRanking[]>("/kpis/ranking", { params: { ...f, por: "talhao" } }),
  });
  const jornadas = useQuery({
    queryKey: ["jornadas", "inicio", f],
    queryFn: () => api<Pagina<Jornada>>("/jornadas", { params: { ...f, limit: 500 } }),
  });
  const alertas = useQuery({
    queryKey: ["alertas", "abertos"],
    queryFn: () => api<Pagina<Alerta>>("/alerts", { params: { status: "aberto", limit: 3 } }),
  });

  if (resumo.isLoading) return <Carregando />;
  if (resumo.error) return <Erro erro={resumo.error} />;
  const r = resumo.data!;
  const lista = jornadas.data?.itens ?? [];

  // Por máquina: total do período e a última jornada.
  const maquinas = new Map<string, { nome: string; ultima: Jornada; horas: number; litros: number; area: number }>();
  for (const j of lista) {
    const m = maquinas.get(j.maquina_id);
    if (!m) maquinas.set(j.maquina_id, { nome: j.apelido ?? j.serial, ultima: j, horas: j.motor_h, litros: j.litros, area: j.area_ha });
    else { m.horas += j.motor_h; m.litros += j.litros; m.area += j.area_ha; }
  }

  // O que merece atenção, em frases curtas.
  const avisos: { texto: string; link: string }[] = [];
  if ((r.ociosidade_pct ?? 0) >= 20) {
    avisos.push({
      texto: `As máquinas ficaram ${pct(r.ociosidade_pct)} do tempo paradas com o motor ligado, o que custou ${rs(r.custo_ocioso_rs)} de diesel.`,
      link: "/analise",
    });
  }
  const comArea = (talhoes.data ?? []).filter((t) => t.id && t.area_ha > 1 && t.rs_ha != null);
  if (comArea.length >= 2 && r.rs_ha) {
    const pior = [...comArea].sort((a, b) => (b.rs_ha ?? 0) - (a.rs_ha ?? 0))[0];
    const acima = ((pior.rs_ha ?? 0) / r.rs_ha - 1) * 100;
    if (acima >= 15) {
      avisos.push({ texto: `No talhão ${pior.nome}, o diesel por hectare ficou ${pct(acima)} acima da média da fazenda.`, link: "/talhoes" });
    }
  }
  for (const a of alertas.data?.itens ?? []) avisos.push({ texto: a.mensagem, link: "/alertas" });

  return (
    <>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold sm:text-3xl">{org?.nome}</h1>
          <p className="mt-1 text-folha-900/70">Como foi o trabalho das máquinas.</p>
        </div>
        <div className="flex flex-wrap gap-1 rounded-xl bg-white p-1 shadow-cartao" role="group" aria-label="Período">
          {PERIODOS.map((p) => (
            <button key={p.valor} onClick={() => setPreset(p.valor)} aria-pressed={periodo.preset === p.valor}
              className={`rounded-lg px-3 py-1.5 text-sm font-semibold ${periodo.preset === p.valor ? "bg-folha-700 text-white" : "text-folha-900/70 hover:bg-folha-50"}`}>
              {p.rotulo}
            </button>
          ))}
        </div>
      </div>

      {r.sessoes === 0 ? (
        <Vazio titulo="Nada registrado neste período" texto="Envie o pendrive do monitor para ver o trabalho das máquinas."
          acao={<Link to="/enviar" className="btn-primario">Enviar pendrive</Link>} />
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 md:grid-cols-3">
            <Grande icone={Coins} rotulo="Gasto com diesel" valor={rs(r.custo_rs)} detalhe={`${num(r.litros, 0)} litros`} />
            <Grande icone={Tractor} rotulo="Horas trabalhando" valor={horas(r.trabalho_h)}
              detalhe={`e ${horas(r.ocioso_h)} parado com motor ligado`} />
            <Grande icone={LandPlot} rotulo="Área trabalhada" valor={`${num(r.area_ha, 1)} ha`}
              detalhe={`${rs(r.rs_ha)} por hectare · ${num(r.l_ha, 1)} L/ha`} />
          </div>

          <section className="cartao p-5" aria-labelledby="t-atencao">
            <h2 id="t-atencao" className="mb-3 flex items-center gap-2 text-lg font-bold">
              <TriangleAlert size={20} className="text-trigo-600" aria-hidden="true" /> Precisa da sua atenção
            </h2>
            {avisos.length === 0 ? (
              <p className="flex items-center gap-2 text-folha-800"><CheckCircle2 size={18} aria-hidden="true" /> Nada fora do normal no período.</p>
            ) : (
              <ul className="space-y-2">
                {avisos.slice(0, 4).map((a, i) => (
                  <li key={i}>
                    <Link to={a.link} className="flex items-start justify-between gap-3 rounded-xl bg-trigo-50 px-4 py-3 text-folha-950 hover:bg-trigo-100">
                      <span>{a.texto}</span><ArrowRight size={18} className="mt-0.5 shrink-0" aria-hidden="true" />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <div className="grid gap-6 xl:grid-cols-2">
            <section className="cartao p-5" aria-labelledby="t-maquinas">
              <h2 id="t-maquinas" className="mb-3 text-lg font-bold">Suas máquinas</h2>
              <ul className="divide-y divide-folha-900/5">
                {[...maquinas.entries()].map(([id, m]) => (
                  <li key={id} className="py-3">
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="font-semibold">{m.nome}</span>
                      <span className="text-sm text-folha-900/70">última vez {quando(m.ultima.inicio)}</span>
                    </div>
                    <p className="mt-0.5 text-sm text-folha-900/70">
                      {horas(m.horas)} de motor · {num(m.litros, 0)} L · {num(m.area, 1)} ha no período
                      {m.ultima.talhao_nome ? ` · último talhão: ${m.ultima.talhao_nome}` : ""}
                    </p>
                  </li>
                ))}
              </ul>
            </section>

            <section className="cartao p-5" aria-labelledby="t-talhoes">
              <h2 id="t-talhoes" className="mb-1 text-lg font-bold">Custo de diesel por talhão</h2>
              <p className="mb-3 text-sm text-folha-900/70">Quanto custou cada hectare trabalhado.</p>
              <ul className="space-y-2.5">
                {comArea.sort((a, b) => (b.rs_ha ?? 0) - (a.rs_ha ?? 0)).slice(0, 8).map((t) => {
                  const maior = Math.max(...comArea.map((x) => x.rs_ha ?? 0));
                  return (
                    <li key={t.id ?? t.nome}>
                      <div className="flex justify-between text-sm">
                        <span className="font-semibold">{t.nome}</span>
                        <span>{rs(t.rs_ha)}/ha <span className="text-folha-900/60">· {num(t.area_ha, 1)} ha</span></span>
                      </div>
                      <div className="mt-1 h-2 rounded-full bg-folha-50" aria-hidden="true">
                        <div className="h-2 rounded-full bg-trigo-400" style={{ width: `${(100 * (t.rs_ha ?? 0)) / maior}%` }} />
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          </div>

          <section className="cartao p-5" aria-labelledby="t-jornadas">
            <div className="mb-3 flex items-baseline justify-between">
              <h2 id="t-jornadas" className="text-lg font-bold">Últimos trabalhos</h2>
              <Link to="/jornadas" className="text-sm font-semibold text-folha-700">ver todos na análise detalhada →</Link>
            </div>
            <ul className="divide-y divide-folha-900/5">
              {lista.slice(0, 6).map((j) => (
                <li key={j.id}>
                  <Link to={`/jornadas/${j.id}`} className="flex flex-wrap items-baseline justify-between gap-2 py-3 hover:bg-folha-50/60">
                    <span>
                      <span className="font-semibold">{maiuscula(quando(j.inicio))}</span>, {hora(j.inicio)}–{hora(j.fim)}
                      <span className="text-folha-900/70"> · {j.apelido ?? j.serial}{j.talhao_nome ? ` · ${j.talhao_nome}` : ""}</span>
                    </span>
                    <span className="text-sm text-folha-900/80">
                      {horas(j.motor_h)} · {num(j.litros, 0)} L · {num(j.area_ha, 1)} ha
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>

          <p className="flex items-center gap-2 text-sm text-folha-900/60">
            <Hourglass size={14} aria-hidden="true" /> <Fuel size={14} aria-hidden="true" />
            Gráficos, mapas e cada arquivo do monitor estão em <Link to="/analise" className="font-semibold text-folha-700 underline">Análise detalhada</Link>.
          </p>
        </div>
      )}
    </>
  );
}

function Grande({ icone: Icone, rotulo, valor, detalhe }: { icone: typeof Coins; rotulo: string; valor: string; detalhe: string }) {
  return (
    <div className="cartao p-5">
      <div className="flex items-center gap-2 text-sm font-semibold text-folha-900/70">
        <Icone size={18} className="text-folha-600" aria-hidden="true" /> {rotulo}
      </div>
      <div className="mt-2 font-display text-3xl font-extrabold text-folha-950 sm:text-4xl">{valor}</div>
      <div className="mt-1 text-sm text-folha-900/70">{detalhe}</div>
    </div>
  );
}
