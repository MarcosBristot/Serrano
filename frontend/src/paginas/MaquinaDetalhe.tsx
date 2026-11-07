import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Clock, Coins, Fuel, LandPlot, Wheat } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Area, Bar, CartesianGrid, ComposedChart, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { SeletorPeriodo } from "../componentes/Layout";
import { Mapa, type FC } from "../componentes/Mapa";
import { Carregando, Erro, IconeMaquina, Kpi, Medidor, Selo, TIPO_MAQUINA, Vazio } from "../componentes/ui";
import { usePeriodo } from "../contextos/Sessao";
import { api } from "../lib/api";
import { useContornos } from "../lib/consultas";
import { haQuanto, horas, nomeMaquina, nomeTalhao, num, pct, rs } from "../lib/formato";
import type { ItemRanking, Jornada, MaquinaVisao, Pagina } from "../lib/tipos";

type Aba = "geral" | "operacoes" | "talhoes";
const EIXO = { fontSize: 11, fill: "rgba(226,238,220,.6)" };
const mes = (iso: string) => new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString("pt-BR", { month: "short", year: "2-digit" });

export default function MaquinaDetalhe() {
  const { id } = useParams();
  const { periodo } = usePeriodo();
  const [aba, setAba] = useState<Aba>("geral");
  const f = { inicio: periodo.inicio, fim: periodo.fim, maquina_id: id };
  const visao = useQuery({ queryKey: ["maquinas-visao", f], queryFn: () => api<MaquinaVisao[]>("/maquinas/visao", { params: f }) });
  const jornadas = useQuery({
    queryKey: ["jornadas", "maquina", f],
    queryFn: () => api<Pagina<Jornada>>("/jornadas", { params: { ...f, limit: 100 } }),
  });
  const serie = useQuery({
    queryKey: ["serie", "mes", f],
    queryFn: () => api<Record<string, number | string | null>[]>("/kpis/series", { params: { ...f, granularidade: "mes" } }),
  });
  const talhoes = useQuery({
    queryKey: ["ranking", "talhao", f],
    queryFn: () => api<ItemRanking[]>("/kpis/ranking", { params: { ...f, por: "talhao" } }),
  });
  const ultima = jornadas.data?.itens[0];
  const trilha = useQuery({
    queryKey: ["trilha-jornada", ultima?.id],
    queryFn: () => api<FC>(`/jornadas/${ultima!.id}/track`, { params: { max_pontos: 3000 } }),
    enabled: Boolean(ultima),
  });
  const contornos = useContornos();

  if (visao.isLoading) return <Carregando />;
  if (visao.error) return <Erro erro={visao.error} />;
  const m = visao.data?.[0];
  if (!m) return <Vazio titulo="Máquina não encontrada" texto="Ela pode ter sido desativada ou não ter dados úteis." />;
  const colhe = m.tipo === "colheitadeira";
  const aproveitamento = m.motor_h > 0 ? (100 * m.trabalho_h) / m.motor_h : null;

  return (
    <>
      <Link to="/maquinas" className="mb-4 inline-flex items-center gap-1 text-sm font-semibold text-broto-300"><ArrowLeft size={16} /> Máquinas</Link>

      <section className="cartao-destaque mb-6 flex flex-wrap items-center gap-4 p-6">
        <IconeMaquina tipo={m.tipo} tamanho={30} />
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-extrabold sm:text-3xl">{nomeMaquina(m)}</h1>
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            <Selo tom="ok">{TIPO_MAQUINA[m.tipo]?.rotulo}</Selo>
            {m.fabricante && <Selo>{m.fabricante}</Selo>}
            <Selo>série {m.serial}</Selo>
            <Selo tom="info">última vez {haQuanto(m.ultima_atividade)}</Selo>
          </div>
        </div>
        <SeletorPeriodo opcoes={["30d", "safra", "12m", "tudo"]} />
      </section>

      <div className="mb-6 flex gap-1 rounded-xl border border-white/10 bg-white/5 p-1 sm:inline-flex" role="tablist">
        {([["geral", "Visão geral"], ["operacoes", `Operações (${m.jornadas})`], ["talhoes", `Talhões (${m.talhoes})`]] as const).map(([v, r]) => (
          <button key={v} role="tab" aria-selected={aba === v} onClick={() => setAba(v)} className={`aba flex-1 ${aba === v ? "aba-ativa" : ""}`}>{r}</button>
        ))}
      </div>

      {m.motor_h === 0 ? (
        <Vazio titulo="Sem trabalho neste período" texto="Troque o período para ver o histórico desta máquina." />
      ) : aba === "geral" ? (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Kpi rotulo="Motor ligado" valor={horas(m.motor_h)} icone={Clock}
              detalhe={<>{horas(m.trabalho_h)} trabalhando · {horas(m.ocioso_h)} parado</>} />
            <Kpi rotulo="Diesel" valor={num(m.litros, 0)} unidade="L" icone={Fuel} tom="trigo"
              detalhe={<>{rs(m.custo_rs)} · {num(m.motor_h ? m.litros / m.motor_h : null, 1)} L/h</>} />
            <Kpi rotulo="Área" valor={num(m.area_ha, 0)} unidade="ha" icone={LandPlot}
              detalhe={<>{num(m.ha_h, 1)} ha por hora · {num(m.l_ha, 1)} L/ha</>} />
            {colhe && m.massa_kg ? (
              <Kpi rotulo="Colhido" valor={num(m.massa_kg / 1000, 0)} unidade="t" icone={Wheat} tom="trigo"
                detalhe={<>{num(m.t_ha, 1)} t/ha de massa úmida</>} />
            ) : (
              <Kpi rotulo="Custo por hectare" valor={rs(m.rs_ha)} icone={Coins} tom="terra" detalhe={<>só o diesel</>} />
            )}
          </div>

          <div className="grid gap-6 xl:grid-cols-[320px_1fr]">
            <div className="cartao flex flex-col items-center justify-center gap-5 p-5">
              <Medidor valor={aproveitamento} rotulo="Aproveitamento do motor" sub="motor ligado e andando" />
              <div className="w-full space-y-2 text-sm">
                <Linha rotulo="Diesel parado com motor ligado" valor={`${num(m.litros_ocioso, 0)} L`} destaque={(m.ociosidade_pct ?? 0) >= 20} />
                <Linha rotulo="Custo desse diesel" valor={rs(m.custo_ocioso_rs)} destaque={(m.ociosidade_pct ?? 0) >= 20} />
                <Linha rotulo="Distância trabalhando" valor={`${num(m.distancia_km, 0)} km`} />
                <Linha rotulo="Operações" valor={String(m.jornadas)} />
              </div>
            </div>
            <div className="cartao p-5">
              <h2 className="mb-1 font-bold">Mês a mês</h2>
              <p className="mb-3 text-sm text-folha-900/60">Horas trabalhando e paradas, e o diesel gasto.</p>
              <div className="h-72">
                {serie.data && (
                  <ResponsiveContainer>
                    <ComposedChart data={serie.data}>
                      <CartesianGrid stroke="rgba(255,255,255,.07)" vertical={false} />
                      <XAxis dataKey="periodo" tickFormatter={(v) => mes(String(v))} tick={EIXO} stroke="rgba(255,255,255,.15)" />
                      <YAxis yAxisId="h" tick={EIXO} stroke="rgba(255,255,255,.15)" />
                      <YAxis yAxisId="l" orientation="right" tick={EIXO} stroke="rgba(255,255,255,.15)" />
                      <Tooltip labelFormatter={(v) => mes(String(v))} formatter={(v: number, n) => [num(v, 1), n]} />
                      <Legend />
                      <Bar yAxisId="h" dataKey="trabalho_h" stackId="h" name="Trabalhando (h)" fill="#8cc63f" />
                      <Bar yAxisId="h" dataKey="ocioso_h" stackId="h" name="Parado ligado (h)" fill="#e6b034" radius={[6, 6, 0, 0]} />
                      <Area yAxisId="l" dataKey="litros" name="Diesel (L)" stroke="#7dd3fc" fill="#7dd3fc1f" strokeWidth={2} />
                    </ComposedChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>
          </div>

          {ultima && (
            <div className="cartao p-2">
              <div className="flex flex-wrap items-baseline justify-between gap-2 px-3 pb-2 pt-2">
                <h2 className="font-bold">Última operação · {nomeTalhao(ultima.talhao_nome)}</h2>
                <Link to={`/jornadas/${ultima.id}`} className="text-sm font-semibold text-broto-300">abrir →</Link>
              </div>
              {trilha.isLoading ? <Carregando texto="Carregando trajeto…" /> : (
                <Mapa className="h-[46vh] min-h-[320px]" camadas={{ trilha: trilha.data, talhoes: contornos.dados }} />
              )}
            </div>
          )}
        </div>
      ) : aba === "operacoes" ? (
        <div className="cartao overflow-x-auto">
          <table className="tabela w-full min-w-[760px]">
            <thead><tr><th>Quando</th><th>Talhão</th><th className="text-right">Motor</th><th className="text-right">Parado</th><th className="text-right">Diesel</th><th className="text-right">Área</th><th className="text-right">L/ha</th><th className="text-right">Custo</th></tr></thead>
            <tbody>
              {(jornadas.data?.itens ?? []).map((j) => (
                <tr key={j.id}>
                  <td className="whitespace-nowrap"><Link to={`/jornadas/${j.id}`} className="font-semibold text-broto-300 hover:underline">{new Date(j.inicio).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}</Link></td>
                  <td>{nomeTalhao(j.talhao_nome)}</td>
                  <td className="text-right">{horas(j.motor_h)}</td>
                  <td className="text-right">{pct(j.ociosidade_pct)}</td>
                  <td className="text-right">{num(j.litros, 0)} L</td>
                  <td className="text-right">{j.area_ha >= 0.05 ? `${num(j.area_ha, 1)} ha` : "—"}</td>
                  <td className="text-right font-semibold">{num(j.l_ha, 1)}</td>
                  <td className="text-right">{rs(j.custo_rs)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="cartao p-5">
          <h2 className="mb-4 font-bold">Onde esta máquina trabalhou</h2>
          <ul className="space-y-4">
            {(talhoes.data ?? []).filter((t) => t.motor_h > 0.05).map((t) => {
              const maior = Math.max(...(talhoes.data ?? []).map((x) => x.motor_h));
              return (
                <li key={t.id ?? t.nome}>
                  <div className="flex flex-wrap justify-between gap-2 text-sm">
                    <span className="font-semibold">{nomeTalhao(t.id ? t.nome : null)}</span>
                    <span className="text-folha-900/70">{horas(t.motor_h)} · {num(t.litros, 0)} L · {num(t.area_ha, 1)} ha · <b className="text-folha-950">{num(t.l_ha, 1)} L/ha</b></span>
                  </div>
                  <div className="mt-1.5 h-2 rounded-full bg-white/5" aria-hidden="true">
                    <div className="h-2 rounded-full bg-broto-500" style={{ width: `${(100 * t.motor_h) / maior}%` }} />
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </>
  );
}

function Linha({ rotulo, valor, destaque }: { rotulo: string; valor: string; destaque?: boolean }) {
  return (
    <div className="flex justify-between gap-3 rounded-lg bg-white/5 px-3 py-2">
      <span className="text-folha-900/70">{rotulo}</span>
      <span className={`font-semibold ${destaque ? "text-trigo-300" : ""}`}>{valor}</span>
    </div>
  );
}
