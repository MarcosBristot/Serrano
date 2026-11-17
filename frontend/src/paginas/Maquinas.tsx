import { useQuery } from "@tanstack/react-query";

import { SeletorPeriodo } from "../componentes/Layout";
import { Cabecalho, Carregando, Erro, TIPO_MAQUINA, Vazio } from "../componentes/ui";
import { usePeriodo } from "../contextos/Sessao";
import { api } from "../lib/api";
import type { MaquinaVisao } from "../lib/tipos";
import { CartaoMaquina } from "./Inicio";

/** Frota agrupada pelo que cada máquina faz (a API classifica e esconde o que não é máquina). */
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
        <div className="space-y-8">
          {(["colheitadeira", "trator", "pulverizador"] as const).map((tipo) => {
            const lista = q.data!.filter((m) => m.tipo === tipo);
            if (!lista.length) return null;
            const Icone = TIPO_MAQUINA[tipo].icone;
            return (
              <section key={tipo} aria-labelledby={`t-${tipo}`}>
                <h2 id={`t-${tipo}`} className="mb-3 flex items-center gap-2 text-lg font-bold">
                  <Icone size={20} className="text-broto-300" aria-hidden="true" />
                  {TIPO_MAQUINA[tipo].rotulo}{lista.length > 1 ? "s" : ""}
                </h2>
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {lista.map((m) => <CartaoMaquina key={m.id} m={m} />)}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </>
  );
}
