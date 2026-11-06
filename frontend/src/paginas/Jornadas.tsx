import { useInfiniteQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { SeletorPeriodo } from "../componentes/Layout";
import { Cabecalho, Carregando, Erro, Selo, Vazio } from "../componentes/ui";
import { usePeriodo } from "../contextos/Sessao";
import { api } from "../lib/api";
import { dataHora, horas, num, pct, rs } from "../lib/formato";
import type { Jornada, Pagina } from "../lib/tipos";

/** Jornadas: os arquivos do monitor da mesma máquina agrupados (intervalo < 15 min). */
export default function Jornadas() {
  const { periodo } = usePeriodo();
  const [curtas, setCurtas] = useState(false);
  const f = { inicio: periodo.inicio, fim: periodo.fim, curtas };
  const q = useInfiniteQuery({
    queryKey: ["jornadas", f],
    queryFn: ({ pageParam }) =>
      api<Pagina<Jornada>>("/jornadas", { params: { ...f, limit: 50, cursor: pageParam as string | undefined } }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (p) => p.next_cursor ?? undefined,
  });
  const itens = q.data?.pages.flatMap((p) => p.itens) ?? [];

  return (
    <>
      <Cabecalho
        titulo="Operações"
        sub="Cada operação junta os arquivos do monitor da mesma máquina com menos de 15 min de intervalo."
        acoes={<SeletorPeriodo />}
      />
      <label className="mb-4 inline-flex items-center gap-2 text-sm text-folha-900/80">
        <input type="checkbox" checked={curtas} onChange={(e) => setCurtas(e.target.checked)} className="h-4 w-4 accent-folha-700" />
        Mostrar registros de segundos (ligou e desligou sem trabalhar)
      </label>
      {q.isLoading ? <Carregando /> : q.error ? <Erro erro={q.error} /> : !itens.length ? (
        <Vazio titulo="Nenhuma operação no período" texto="Troque o período ou envie os arquivos do pendrive." />
      ) : (
        <div className="cartao overflow-x-auto">
          <table className="tabela w-full min-w-[900px]">
            <thead>
              <tr>
                <th>Quando</th><th>Máquina</th><th>Talhão</th>
                <th className="text-right">Motor</th><th className="text-right">Parado</th>
                <th className="text-right">Diesel</th><th className="text-right">Área</th>
                <th className="text-right">L/ha</th><th className="text-right">Custo</th>
              </tr>
            </thead>
            <tbody>
              {itens.map((j) => (
                <tr key={j.id} className={j.curta ? "text-folha-900/50" : undefined}>
                  <td className="whitespace-nowrap">
                    <Link to={`/jornadas/${j.id}`} className="font-semibold text-folha-800 underline-offset-2 hover:underline">
                      {dataHora(j.inicio)}
                    </Link>
                    <div className="text-xs text-folha-900/60">até {dataHora(j.fim)} · {j.arquivos} arquivo{j.arquivos > 1 ? "s" : ""}</div>
                  </td>
                  <td>{j.apelido ?? j.serial}</td>
                  <td>
                    {j.talhao_nome ?? <span className="text-folha-900/40">—</span>}
                    {j.talhoes > 1 && <span className="ml-1 text-xs text-folha-900/60">+{j.talhoes - 1}</span>}
                    {j.curta && <span className="ml-2"><Selo>segundos</Selo></span>}
                  </td>
                  <td className="text-right">{horas(j.motor_h)}</td>
                  <td className="text-right">{pct(j.ociosidade_pct)}</td>
                  <td className="text-right">{num(j.litros, 0)} L</td>
                  <td className="text-right">{num(j.area_ha, 1)} ha</td>
                  <td className="text-right font-semibold">{num(j.l_ha, 2)}</td>
                  <td className="text-right">{rs(j.custo_rs)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {q.hasNextPage && (
            <div className="p-3 text-center">
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
