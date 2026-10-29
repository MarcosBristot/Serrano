/** LGPD art. 18: baixar os próprios dados e excluir a conta (com carência e cancelamento). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, ShieldCheck, Trash2 } from "lucide-react";
import { useState } from "react";

import { api, baixar } from "../lib/api";
import { data } from "../lib/formato";
import { LINKS_LEGAIS } from "../lib/legal";
import { Carregando, Erro, Selo } from "./ui";

interface Situacao {
  pedido: { agendada_para: string } | null;
  organizacoes: { organizacao_id: string; nome: string; papel: string; acao: "excluida" | "sai" | "bloqueia" }[];
  carencia_dias: number;
}

const ACAO = {
  excluida: { tom: "alto", texto: "será apagada (você é o único membro)" },
  sai: { tom: "neutro", texto: "você sai; a organização continua" },
  bloqueia: { tom: "atencao", texto: "torne outra pessoa dona antes" },
} as const;

export function MeusDados() {
  const qc = useQueryClient();
  const s = useQuery({ queryKey: ["exclusao"], queryFn: () => api<Situacao>("/eu/exclusao") });
  const [confirmacao, setConfirmacao] = useState("");
  const exportar = useMutation({
    mutationFn: () => baixar("/eu/dados", {}, `serrano_meus_dados_${new Date().toISOString().slice(0, 10)}.json`),
  });
  const pedir = useMutation({
    mutationFn: () => api("/eu/exclusao", { metodo: "POST", corpo: { confirmacao } }),
    onSuccess: () => { setConfirmacao(""); qc.invalidateQueries({ queryKey: ["exclusao"] }); },
  });
  const cancelar = useMutation({
    mutationFn: () => api("/eu/exclusao", { metodo: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["exclusao"] }),
  });

  const bloqueada = s.data?.organizacoes.some((o) => o.acao === "bloqueia") ?? false;

  return (
    <section className="cartao p-6 xl:col-span-2" aria-labelledby="titulo-meus-dados">
      <h2 id="titulo-meus-dados" className="mb-1 flex items-center gap-2 text-lg font-bold">
        <ShieldCheck size={20} className="text-folha-600" aria-hidden="true" /> Privacidade e meus dados
      </h2>
      <p className="mb-5 text-sm text-folha-900/70">
        Seus direitos pela LGPD. Detalhes na <a className="font-semibold text-folha-700 underline" href={LINKS_LEGAIS.privacidade}>Política de Privacidade</a>.
      </p>

      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <h3 className="font-semibold">Baixar uma cópia</h3>
          <p className="mb-3 mt-1 text-sm text-folha-900/70">
            Conta, organizações, aceites, comentários, ações e acessos dos últimos 6 meses, em JSON. Os dados das
            máquinas ficam em Operações, na exportação em CSV.
          </p>
          <button className="btn-secundario" onClick={() => exportar.mutate()} disabled={exportar.isPending}>
            <Download size={16} aria-hidden="true" /> {exportar.isPending ? "Preparando…" : "Baixar meus dados"}
          </button>
          {exportar.error && <div className="mt-3"><Erro erro={exportar.error} /></div>}
        </div>

        <div>
          <h3 className="font-semibold">Excluir minha conta</h3>
          {s.isLoading ? <Carregando /> : s.error ? <Erro erro={s.error} /> : s.data?.pedido ? (
            <div className="mt-2 rounded-xl bg-rose-50 p-4 text-sm" role="status">
              <p className="font-semibold text-rose-800">Exclusão agendada para {data(s.data.pedido.agendada_para)}.</p>
              <p className="mt-1 text-folha-900/80">Até lá você pode cancelar e tudo continua como está.</p>
              <button className="btn-secundario mt-3" onClick={() => cancelar.mutate()} disabled={cancelar.isPending}>
                Cancelar exclusão
              </button>
            </div>
          ) : (
            <>
              <p className="mt-1 text-sm text-folha-900/70">
                A exclusão acontece {s.data?.carencia_dias} dias depois do pedido; até lá dá para cancelar.
                Aceites e registros de acesso ficam pelo prazo que a lei exige.
              </p>
              <ul className="my-3 space-y-1.5 text-sm">
                {s.data?.organizacoes.map((o) => (
                  <li key={o.organizacao_id} className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{o.nome}</span>
                    <Selo tom={ACAO[o.acao].tom}>{ACAO[o.acao].texto}</Selo>
                  </li>
                ))}
              </ul>
              <form
                className="flex flex-wrap items-end gap-2"
                onSubmit={(e) => { e.preventDefault(); pedir.mutate(); }}
              >
                <div>
                  <label className="rotulo" htmlFor="confirmar-exclusao">Digite EXCLUIR para confirmar</label>
                  <input id="confirmar-exclusao" className="campo w-48" autoComplete="off" value={confirmacao}
                    onChange={(e) => setConfirmacao(e.target.value)} disabled={bloqueada} />
                </div>
                <button
                  className="inline-flex items-center gap-2 rounded-xl bg-rose-700 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
                  disabled={bloqueada || confirmacao.trim().toUpperCase() !== "EXCLUIR" || pedir.isPending}
                >
                  <Trash2 size={16} aria-hidden="true" /> Agendar exclusão
                </button>
              </form>
              {bloqueada && (
                <p className="mt-2 text-sm text-trigo-800">
                  Você é o único dono de uma organização com outros membros. Torne outra pessoa dona ou remova os membros.
                </p>
              )}
              {pedir.error && <div className="mt-3"><Erro erro={pedir.error} /></div>}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
