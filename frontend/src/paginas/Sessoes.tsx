import { useInfiniteQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { SeletorPeriodo } from "../componentes/Layout";
import { Cabecalho, Carregando, Erro, Selo, seloQualidade, Vazio } from "../componentes/ui";
import { usePeriodo } from "../contextos/Sessao";
import { api, baixar } from "../lib/api";
import { dataHora, horas, num, ROTULO_ORIGEM } from "../lib/formato";
import type { Pagina, Sessao } from "../lib/tipos";

export default function Sessoes() {
  const { periodo } = usePeriodo();
  const navegar = useNavigate();
  const [baixando, setBaixando] = useState(false);
  const f = { inicio: periodo.inicio, fim: periodo.fim };
  const q = useInfiniteQuery({
    queryKey: ["sessoes", f],
    queryFn: ({ pageParam }) =>
      api<Pagina<Sessao>>("/sessions", { params: { ...f, limit: 50, cursor: pageParam as string | undefined } }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (p) => p.next_cursor ?? undefined,
  });
  const itens = q.data?.pages.flatMap((p) => p.itens) ?? [];

  return (
    <>
      <Cabecalho
        titulo="Operações"
        sub="Cada arquivo do monitor vira uma operação (sessão de trabalho)."
        acoes={
          <>
            <SeletorPeriodo />
            <button
              className="btn-secundario"
              disabled={baixando}
              onClick={async () => {
                setBaixando(true);
                try {
                  await baixar("/exportacoes/csv", { tipo: "sessoes", ...f }, "operacoes.csv");
                } finally {
                  setBaixando(false);
                }
              }}
            >
              <Download size={16} /> Planilha
            </button>
          </>
        }
      />
      {q.isLoading ? <Carregando /> : q.error ? <Erro erro={q.error} /> : !itens.length ? (
        <Vazio titulo="Nenhuma operação no período" texto="Troque o período ou envie os arquivos do pendrive." />
      ) : (
        <div className="cartao overflow-x-auto">
          <table className="tabela w-full min-w-[880px]">
            <thead>
              <tr>
                <th>Início</th><th>Máquina</th><th>Talhão</th><th>Operação</th>
                <th className="text-right">Motor</th><th className="text-right">Diesel</th>
                <th className="text-right">Área</th><th className="text-right">L/ha</th><th>Qualidade</th>
              </tr>
            </thead>
            <tbody>
              {itens.map((s) => (
                <tr key={s.id} onClick={() => navegar(`/sessoes/${s.id}`)} className="cursor-pointer hover:bg-folha-50/60">
                  <td className="whitespace-nowrap font-medium">{dataHora(s.inicio)}</td>
                  <td>{s.apelido ?? s.serial}</td>
                  <td>
                    {s.talhao_nome ?? <span className="text-folha-900/40">—</span>}
                    {s.talhao_nome && <span className="ml-1 text-xs text-folha-900/40">{ROTULO_ORIGEM[s.talhao_origem]}</span>}
                  </td>
                  <td>{s.operacao ? <Selo tom="ok">{s.operacao}</Selo> : <span className="text-folha-900/40">—</span>}</td>
                  <td className="text-right">{horas(s.motor_h)}</td>
                  <td className="text-right">{num(s.litros_integral, 1)} L</td>
                  <td className="text-right">{num(s.area_cobertura_ha ?? s.area_estimada_ha, 2)} ha</td>
                  <td className="text-right font-semibold">{num(s.l_ha, 2)}</td>
                  <td>{seloQualidade(s.qualidade_score)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {q.hasNextPage && (
            <div className="border-t border-folha-900/5 p-3 text-center">
              <button className="btn-secundario" onClick={() => q.fetchNextPage()} disabled={q.isFetchingNextPage}>
                {q.isFetchingNextPage ? "Carregando…" : "Carregar mais"}
              </button>
            </div>
          )}
        </div>
      )}
    </>
  );
}
