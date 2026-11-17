import { useQuery } from "@tanstack/react-query";

import { SeletorPeriodo } from "../componentes/Layout";
import { Cabecalho, Carregando, Erro, Vazio } from "../componentes/ui";
import { usePeriodo } from "../contextos/Sessao";
import { api } from "../lib/api";
import type { MaquinaVisao } from "../lib/tipos";
import { CartaoMaquina } from "./Inicio";

const ORDEM = ["colheitadeira", "trator", "pulverizador"] as const;

/** Frota ordenada pelo que cada máquina faz (a API classifica e esconde o que não é máquina). */
export default function Maquinas() {
  const { periodo } = usePeriodo();
  const f = { inicio: periodo.inicio, fim: periodo.fim };
  const q = useQuery({ queryKey: ["maquinas-visao", f], queryFn: () => api<MaquinaVisao[]>("/maquinas/visao", { params: f }) });

  return (
    <>
      <Cabecalho titulo="Máquinas" sub="Cada máquina com o trabalho, o diesel e o que produziu no período." acoes={<SeletorPeriodo />} />
      {q.isLoading ? <Carregando /> : q.error ? <Erro erro={q.error} /> : !q.data?.length ? (
        <Vazio titulo="Nenhuma máquina ainda" texto="As máquinas aparecem sozinhas quando o pendrive do monitor é enviado." />
      ) : (
        <div className={`grid gap-5 md:grid-cols-2 ${q.data.length >= 3 ? "2xl:grid-cols-3" : ""}`}>
          {/* Uma grade só: com frota pequena, um grupo por tipo deixava um cartão sozinho na linha. */}
          {ORDEM.flatMap((tipo) => q.data!.filter((m) => m.tipo === tipo)).map((m) => <CartaoMaquina key={m.id} m={m} />)}
        </div>
      )}
    </>
  );
}
