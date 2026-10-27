import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Clock, Fuel, Gauge, LandPlot } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { Mapa, type FC } from "../componentes/Mapa";
import { Carregando, Erro, Kpi, Selo, seloQualidade } from "../componentes/ui";
import { api } from "../lib/api";
import { useContornos, useTalhoes } from "../lib/consultas";
import { dataHora, horas, num, pct, ROTULO_ORIGEM, ROTULO_TIPO_ALERTA } from "../lib/formato";
import type { Alerta, Pagina, SessaoDetalhe as Detalhe } from "../lib/tipos";

export default function SessaoDetalhe() {
  const { id } = useParams();
  const qc = useQueryClient();
  const s = useQuery({ queryKey: ["sessao", id], queryFn: () => api<Detalhe>(`/sessions/${id}`) });
  const trilha = useQuery({ queryKey: ["trilha", id], queryFn: () => api<FC>(`/sessions/${id}/track`, { params: { max_pontos: 3000 } }) });
  const alertas = useQuery({ queryKey: ["alertas", "sessao", id], queryFn: () => api<Pagina<Alerta>>("/alerts", { params: { sessao_id: id } }) });
  const talhoes = useTalhoes();
  const contornos = useContornos();
  const corrigir = useMutation({
    mutationFn: (talhao_id: string | null) => api(`/sessions/${id}`, { metodo: "PATCH", corpo: { talhao_id } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessao", id] }),
  });

  if (s.isLoading) return <Carregando />;
  if (s.error) return <Erro erro={s.error} />;
  const d = s.data!;

  return (
    <>
      <Link to="/sessoes" className="mb-4 inline-flex items-center gap-1 text-sm font-semibold text-folha-700"><ArrowLeft size={16} /> Operações</Link>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold sm:text-3xl">{d.apelido ?? d.serial}</h1>
          <p className="mt-1 text-sm text-folha-900/60">
            {dataHora(d.inicio)} → {dataHora(d.fim)} · {d.operacao ?? "operação não informada"} · firmware {d.firmware ?? "—"}
          </p>
        </div>
        <div className="flex items-center gap-2">Qualidade {seloQualidade(d.qualidade_score)}</div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi rotulo="Motor" valor={horas(d.motor_h)} icone={Clock} detalhe={<>{horas(d.trabalho_h)} trabalhando · ociosidade {pct(d.ocioso_h && d.motor_h ? (100 * d.ocioso_h) / d.motor_h : null)}</>} />
        <Kpi rotulo="Diesel" valor={num(d.litros_integral, 1)} unidade="L" icone={Fuel} tom="trigo" detalhe={<>contador do motor: {num(d.litros_contador, 1)} L · {num(d.lph_trabalho, 1)} L/h</>} />
        <Kpi rotulo="Área" valor={num(d.area_cobertura_ha ?? d.area_estimada_ha, 2)} unidade="ha" icone={LandPlot}
          detalhe={<>{d.area_metodo === "cobertura" ? `cobertura GPS · sobreposição ${pct(d.sobreposicao_pct, 1)}` : "estimada (sem GPS)"}</>} />
        <Kpi rotulo="Consumo" valor={num(d.l_ha, 2)} unidade="L/ha" icone={Gauge} tom="terra" detalhe={<>{num(d.ha_h, 2)} ha/h · {num(d.velocidade_media, 1)} km/h</>} />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1fr_340px]">
        <div className="cartao p-2">
          {trilha.isLoading ? <Carregando texto="Carregando trajeto…" /> : (
            <Mapa className="h-[56vh] min-h-[380px]" camadas={{ trilha: trilha.data, talhoes: contornos.dados }} />
          )}
          <div className="flex flex-wrap gap-4 px-3 py-2 text-xs text-folha-900/60">
            <span className="flex items-center gap-1.5"><i className="inline-block h-1 w-5 rounded bg-trigo-400" /> trabalhando</span>
            <span className="flex items-center gap-1.5"><i className="inline-block h-0.5 w-5 rounded bg-white ring-1 ring-folha-900/30" /> parado/deslocando</span>
            <span className="flex items-center gap-1.5"><i className="inline-block h-3 w-3 rounded-full bg-rose-700" /> parada longa</span>
          </div>
        </div>

        <div className="space-y-4">
          <div className="cartao p-5">
            <h3 className="font-bold">Talhão</h3>
            <p className="mt-1 text-sm">
              {d.talhao_nome ?? "Não identificado"}{" "}
              <span className="text-folha-900/50">({ROTULO_ORIGEM[d.talhao_origem]}{d.talhao_confianca != null && d.talhao_origem === "gps" ? `, ${pct(100 * d.talhao_confianca)} do trabalho` : ""})</span>
            </p>
            <label className="rotulo mt-4">Corrigir manualmente</label>
            <select
              className="campo"
              value={d.talhao_origem === "manual" ? d.talhao_id ?? "" : ""}
              onChange={(e) => corrigir.mutate(e.target.value || null)}
              disabled={corrigir.isPending}
            >
              <option value="">Automático (GPS/monitor)</option>
              {(talhoes.data ?? []).map((t) => <option key={t.id} value={t.id}>{t.nome}</option>)}
            </select>
            {corrigir.isSuccess && <p className="mt-2 text-xs text-folha-700">Salvo. Área e L/ha são recalculados em instantes.</p>}
            {corrigir.error && <div className="mt-2"><Erro erro={corrigir.error} /></div>}
          </div>

          <div className="cartao p-5">
            <h3 className="mb-3 font-bold">Qualidade do dado</h3>
            {d.qualidade?.problemas.length ? (
              <ul className="space-y-2">
                {d.qualidade.problemas.map((p) => (
                  <li key={p.codigo} className="text-sm">
                    <Selo tom={p.severidade}>{p.codigo.replaceAll("_", " ").toLowerCase()}</Selo>
                    <p className="mt-1 text-folha-900/70">{p.mensagem}</p>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-folha-700">Sem problemas encontrados. ✅</p>}
          </div>

          <div className="cartao p-5">
            <h3 className="mb-3 font-bold">Alertas desta operação</h3>
            {alertas.data?.itens.length ? (
              <ul className="space-y-3">
                {alertas.data.itens.map((a) => (
                  <li key={a.id} className="text-sm">
                    <div className="flex items-center gap-2"><Selo tom={a.severidade}>{ROTULO_TIPO_ALERTA[a.tipo] ?? a.tipo}</Selo><span className="text-xs text-folha-900/50">{a.status}</span></div>
                    <p className="mt-1 text-folha-900/70">{a.mensagem}</p>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-folha-900/50">Nenhum alerta.</p>}
          </div>
        </div>
      </div>
    </>
  );
}
