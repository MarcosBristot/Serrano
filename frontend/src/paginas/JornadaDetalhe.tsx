import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Clock, Coins, Fuel, LandPlot } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { Mapa, type FC } from "../componentes/Mapa";
import { Carregando, Erro, Kpi, seloQualidade } from "../componentes/ui";
import { api } from "../lib/api";
import { useContornos } from "../lib/consultas";
import { dataHora, horas, num, pct, rs } from "../lib/formato";
import type { JornadaDetalhe as Detalhe } from "../lib/tipos";

// Arquivos de reinício duram segundos; "0 min" pareceria erro.
const duracao = (h: number | null) =>
  h != null && h * 3600 < 60 ? `${Math.round(h * 3600)} s` : horas(h);

export default function JornadaDetalhe() {
  const { id } = useParams();
  const j = useQuery({ queryKey: ["jornada", id], queryFn: () => api<Detalhe>(`/jornadas/${id}`) });
  const trilha = useQuery({ queryKey: ["trilha-jornada", id], queryFn: () => api<FC>(`/jornadas/${id}/track`, { params: { max_pontos: 4000 } }) });
  const contornos = useContornos();

  if (j.isLoading) return <Carregando />;
  if (j.error) return <Erro erro={j.error} />;
  const d = j.data!;

  return (
    <>
      <Link to="/jornadas" className="mb-4 inline-flex items-center gap-1 text-sm font-semibold text-folha-700"><ArrowLeft size={16} /> Operações</Link>
      <div className="mb-6">
        <h1 className="text-2xl font-extrabold sm:text-3xl">{d.apelido ?? d.serial}{d.talhao_nome ? ` · ${d.talhao_nome}` : ""}</h1>
        <p className="mt-1 text-sm text-folha-900/70">
          {dataHora(d.inicio)} até {dataHora(d.fim)} · {d.operacao ?? "operação não informada"} · {d.arquivos} arquivos do monitor
          {d.talhoes > 1 ? ` · passou por ${d.talhoes} talhões` : ""}
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi rotulo="Motor" valor={horas(d.motor_h)} icone={Clock}
          detalhe={<>{horas(d.trabalho_h)} trabalhando · parado {pct(d.ociosidade_pct)}</>} />
        <Kpi rotulo="Diesel" valor={num(d.litros, 0)} unidade="L" icone={Fuel} tom="trigo"
          detalhe={<>{num(d.litros_ocioso, 1)} L com a máquina parada</>} />
        <Kpi rotulo="Área" valor={num(d.area_ha, 1)} unidade="ha" icone={LandPlot}
          detalhe={<>{num(d.ha_h, 2)} ha/h · {num(d.distancia_km, 1)} km</>} />
        <Kpi rotulo="Custo do diesel" valor={rs(d.custo_rs)} icone={Coins} tom="terra"
          detalhe={<>{num(d.l_ha, 2)} L/ha</>} />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1fr_360px]">
        <div className="cartao p-2">
          {trilha.isLoading ? <Carregando texto="Carregando trajeto…" /> : (
            <Mapa className="h-[56vh] min-h-[380px]" camadas={{ trilha: trilha.data, talhoes: contornos.dados }} />
          )}
        </div>
        <div className="cartao p-5">
          <h2 className="mb-1 font-bold">Arquivos do monitor</h2>
          <p className="mb-3 text-sm text-folha-900/70">O monitor abre um arquivo a cada ligada ou reinício.</p>
          <ul className="max-h-[50vh] space-y-2 overflow-y-auto text-sm">
            {d.arquivos_detalhe.map((a) => (
              <li key={a.id}>
                <Link to={`/sessoes/${a.id}`} className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 hover:bg-folha-50">
                  <span>{new Date(a.inicio).toLocaleTimeString("pt-BR")} · {duracao(a.motor_h)}</span>
                  {seloQualidade(a.qualidade_score)}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </>
  );
}
