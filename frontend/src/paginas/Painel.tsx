import { useQuery } from "@tanstack/react-query";
import { Clock, Coins, Fuel, Gauge, Hourglass, LandPlot, Tractor, TriangleAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { Area, Bar, CartesianGrid, ComposedChart, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { SeletorPeriodo } from "../componentes/Layout";
import { Cabecalho, Carregando, Erro, Kpi, Selo, Vazio } from "../componentes/ui";
import { usePeriodo } from "../contextos/Sessao";
import { api } from "../lib/api";
import { diaCurto, horas, num, pct, ROTULO_TIPO_ALERTA, rs } from "../lib/formato";
import type { Alerta, ItemRanking, Pagina, PontoSerie, Resumo } from "../lib/tipos";

export default function Painel() {
  const { periodo } = usePeriodo();
  const f = { inicio: periodo.inicio, fim: periodo.fim };
  const resumo = useQuery({ queryKey: ["resumo", f], queryFn: () => api<Resumo>("/kpis/resumo", { params: f }) });
  const dias = (resumo.data?.primeiro_dia && resumo.data?.ultimo_dia)
    ? (new Date(resumo.data.ultimo_dia).getTime() - new Date(resumo.data.primeiro_dia).getTime()) / 86_400_000
    : 0;
  const granularidade = dias > 120 ? "semana" : "dia";
  const serie = useQuery({
    queryKey: ["serie", f, granularidade],
    queryFn: () => api<PontoSerie[]>("/kpis/series", { params: { ...f, granularidade } }),
  });
  const ranking = useQuery({ queryKey: ["ranking", "talhao", f], queryFn: () => api<ItemRanking[]>("/kpis/ranking", { params: { ...f, por: "talhao" } }) });
  const alertas = useQuery({ queryKey: ["alertas", "abertos"], queryFn: () => api<Pagina<Alerta>>("/alerts", { params: { status: "aberto", limit: 5 } }) });

  if (resumo.isLoading) return <Carregando />;
  if (resumo.error) return <Erro erro={resumo.error} />;
  const r = resumo.data!;

  return (
    <>
      <Cabecalho titulo="Painel da frota" sub="Horas, diesel e área de todas as máquinas no período." acoes={<SeletorPeriodo />} />

      {r.sessoes === 0 ? (
        <Vazio
          titulo="Ainda não há operações neste período"
          texto="Envie o conteúdo do pendrive do monitor (arquivos .jdl ou o .zip inteiro) para ver os indicadores."
          acao={<Link to="/enviar" className="btn-primario">Enviar pendrive</Link>}
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Kpi rotulo="Horas de motor" valor={horas(r.motor_h)} icone={Clock}
              detalhe={<>{horas(r.trabalho_h)} trabalhando · {r.sessoes} operações · {r.maquinas} máq.</>} />
            <Kpi rotulo="Diesel" valor={num(r.litros, 0)} unidade="L" icone={Fuel} tom="trigo"
              detalhe={<>{num(r.lph_trabalho, 1)} L/h em trabalho</>} />
            <Kpi rotulo="Área trabalhada" valor={num(r.area_ha, 1)} unidade="ha" icone={LandPlot}
              detalhe={<>{num(r.ha_h, 2)} ha/h · {num(r.distancia_km, 0)} km</>} />
            <Kpi rotulo="Consumo" valor={num(r.l_ha, 2)} unidade="L/ha" icone={Gauge} tom="terra"
              detalhe="litros por hectare trabalhado" />
            <Kpi rotulo="Custo do diesel" valor={rs(r.custo_rs)} icone={Coins} tom="trigo"
              detalhe={<>{rs(r.rs_ha)} por hectare</>} />
            <Kpi rotulo="Ociosidade" valor={pct(r.ociosidade_pct, 1)} icone={Hourglass} tom="rosa"
              detalhe={<>{horas(r.ocioso_h)} parado com motor ligado · {rs(r.custo_ocioso_rs)}</>} />
            <Kpi rotulo="Máquinas" valor={String(r.maquinas)} icone={Tractor} tom="ceu" detalhe="com operação no período" />
            <Kpi rotulo="Alertas abertos" valor={String(alertas.data?.itens.length ?? 0)} icone={TriangleAlert} tom="rosa"
              detalhe={<Link to="/alertas" className="font-semibold text-folha-700">ver alertas →</Link>} />
          </div>

          <div className="mt-6 grid gap-6 xl:grid-cols-3">
            <div className="cartao p-5 xl:col-span-2">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="font-bold">Horas e diesel por {granularidade}</h3>
                <span className="text-xs text-folha-900/50">trabalho × ocioso (h) · diesel (L)</span>
              </div>
              <div className="h-72">
                <ResponsiveContainer>
                  <ComposedChart data={serie.data ?? []} margin={{ left: -10, right: 0 }}>
                    <CartesianGrid stroke="#0d201110" vertical={false} />
                    <XAxis dataKey="periodo" tickFormatter={diaCurto} tick={{ fontSize: 11 }} />
                    <YAxis yAxisId="h" tick={{ fontSize: 11 }} />
                    <YAxis yAxisId="l" orientation="right" tick={{ fontSize: 11 }} />
                    <Tooltip
                      labelFormatter={(v) => diaCurto(String(v))}
                      formatter={(v: number, n) => [n === "Diesel (L)" ? `${num(v, 0)} L` : horas(v), n]}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar yAxisId="h" dataKey="trabalho_h" stackId="h" name="Trabalho" fill="#3f8c3e" radius={[0, 0, 0, 0]} />
                    <Bar yAxisId="h" dataKey="ocioso_h" stackId="h" name="Ocioso" fill="#ecc55a" radius={[6, 6, 0, 0]} />
                    <Area yAxisId="l" dataKey="litros" name="Diesel (L)" stroke="#945118" fill="#94511820" strokeWidth={2} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="cartao p-5">
              <h3 className="mb-4 font-bold">Por talhão</h3>
              <div className="space-y-3">
                {(ranking.data ?? []).slice(0, 7).map((t) => {
                  const max = Math.max(...(ranking.data ?? []).map((x) => x.area_ha), 1);
                  return (
                    <div key={t.id ?? t.nome}>
                      <div className="flex justify-between text-sm">
                        <span className="font-semibold">{t.nome}</span>
                        <span className="text-folha-900/60">{num(t.area_ha, 1)} ha · {num(t.l_ha, 2)} L/ha</span>
                      </div>
                      <div className="mt-1 h-2 rounded-full bg-folha-50">
                        <div className="h-2 rounded-full bg-gradient-to-r from-folha-500 to-trigo-400" style={{ width: `${(100 * t.area_ha) / max}%` }} />
                      </div>
                    </div>
                  );
                })}
                {!ranking.data?.length && <p className="text-sm text-folha-900/50">Sem dados.</p>}
              </div>
            </div>
          </div>

          <div className="mt-6 cartao p-5">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="font-bold">Alertas abertos</h3>
              <Link to="/alertas" className="text-sm font-semibold text-folha-700">Todos →</Link>
            </div>
            {alertas.data?.itens.length ? (
              <ul className="divide-y divide-folha-900/5">
                {alertas.data.itens.map((a) => (
                  <li key={a.id} className="flex items-start justify-between gap-4 py-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <Selo tom={a.severidade}>{ROTULO_TIPO_ALERTA[a.tipo] ?? a.tipo}</Selo>
                        <span className="text-xs text-folha-900/50">{a.apelido ?? a.serial}</span>
                      </div>
                      <p className="mt-1 text-sm">{a.mensagem}</p>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-folha-900/50">Nenhum alerta aberto. 🌾</p>
            )}
          </div>
        </>
      )}
    </>
  );
}
