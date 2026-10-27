import { useQuery } from "@tanstack/react-query";
import { Flame, Layers } from "lucide-react";
import { useState } from "react";

import { SeletorPeriodo } from "../componentes/Layout";
import { LegendaCalor, Mapa, type FC } from "../componentes/Mapa";
import { Cabecalho, Erro } from "../componentes/ui";
import { usePeriodo } from "../contextos/Sessao";
import { api } from "../lib/api";
import { useContornos } from "../lib/consultas";
import { num } from "../lib/formato";
import type { Resumo } from "../lib/tipos";

export default function MapaPagina() {
  const { periodo } = usePeriodo();
  const [verCalor, setVerCalor] = useState(true);
  const [verTalhoes, setVerTalhoes] = useState(true);
  const [tamanho, setTamanho] = useState(50);
  const contornos = useContornos();

  // "Tudo" não tem datas: usa o primeiro e o último dia com operação.
  const resumo = useQuery({
    queryKey: ["resumo", { inicio: periodo.inicio, fim: periodo.fim }],
    queryFn: () => api<Resumo>("/kpis/resumo", { params: { inicio: periodo.inicio, fim: periodo.fim } }),
  });
  const inicio = periodo.inicio ?? resumo.data?.primeiro_dia ?? undefined;
  const fim = periodo.fim ?? resumo.data?.ultimo_dia ?? undefined;
  const calor = useQuery({
    queryKey: ["calor", inicio, fim, tamanho],
    queryFn: () => api<FC & { properties: Record<string, number | null> }>("/mapas/calor", { params: { inicio, fim, tamanho_m: tamanho } }),
    enabled: Boolean(inicio && fim && verCalor),
  });

  return (
    <>
      <Cabecalho titulo="Mapa" sub="Talhões e consumo de diesel por hectare, sobre imagem de satélite." acoes={<SeletorPeriodo />} />
      <div className="grid gap-6 xl:grid-cols-[1fr_300px]">
        <div className="cartao p-2">
          <Mapa className="h-[68vh] min-h-[420px]" camadas={{ talhoes: verTalhoes ? contornos.dados : undefined, calor: verCalor ? calor.data : undefined }} />
        </div>
        <div className="space-y-4">
          <div className="cartao p-5">
            <h3 className="mb-3 flex items-center gap-2 font-bold"><Layers size={18} /> Camadas</h3>
            <label className="flex items-center justify-between py-2 text-sm">
              Talhões <input type="checkbox" checked={verTalhoes} onChange={(e) => setVerTalhoes(e.target.checked)} className="h-4 w-4 accent-folha-700" />
            </label>
            <label className="flex items-center justify-between py-2 text-sm">
              Mapa de calor (L/ha) <input type="checkbox" checked={verCalor} onChange={(e) => setVerCalor(e.target.checked)} className="h-4 w-4 accent-folha-700" />
            </label>
            <div className="mt-3">
              <span className="rotulo">Tamanho do hexágono</span>
              <select className="campo" value={tamanho} onChange={(e) => setTamanho(Number(e.target.value))}>
                {[25, 50, 100, 200].map((t) => <option key={t} value={t}>{t} m</option>)}
              </select>
            </div>
          </div>
          <div className="cartao p-5">
            <h3 className="mb-3 flex items-center gap-2 font-bold"><Flame size={18} className="text-trigo-600" /> Consumo</h3>
            <LegendaCalor />
            {calor.data?.properties && (
              <dl className="mt-4 grid grid-cols-3 gap-2 text-center">
                {(["l_ha_p10", "l_ha_p50", "l_ha_p90"] as const).map((k, i) => (
                  <div key={k} className="rounded-xl bg-folha-50 p-2">
                    <dt className="text-[11px] text-folha-900/50">{["10% menores", "mediana", "10% maiores"][i]}</dt>
                    <dd className="font-display text-lg font-bold">{num(calor.data.properties[k], 2)}</dd>
                  </div>
                ))}
              </dl>
            )}
            {calor.isLoading && verCalor && <p className="mt-3 text-xs text-folha-900/50">Calculando mapa de calor…</p>}
            {calor.error && <div className="mt-3"><Erro erro={calor.error} /></div>}
            <p className="mt-4 text-xs text-folha-900/50">
              Cada hexágono soma os litros e a área trabalhada (velocidade × largura do implemento) dentro dele.
            </p>
          </div>
        </div>
      </div>
    </>
  );
}
