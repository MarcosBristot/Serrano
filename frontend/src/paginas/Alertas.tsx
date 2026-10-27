import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CheckCheck, MessageSquare, RotateCcw } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Cabecalho, Carregando, Erro, Selo, Vazio } from "../componentes/ui";
import { useSessao } from "../contextos/Sessao";
import { api } from "../lib/api";
import { dataHora, ROTULO_TIPO_ALERTA } from "../lib/formato";
import type { Alerta, Pagina } from "../lib/tipos";

const ABAS = [
  { valor: "aberto", rotulo: "Abertos" },
  { valor: "reconhecido", rotulo: "Reconhecidos" },
  { valor: "resolvido", rotulo: "Resolvidos" },
] as const;

export default function Alertas() {
  const [aba, setAba] = useState<(typeof ABAS)[number]["valor"]>("aberto");
  const { papel } = useSessao();
  const podeAgir = papel === "owner" || papel === "gestor";
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["alertas", aba], queryFn: () => api<Pagina<Alerta>>("/alerts", { params: { status: aba, limit: 200 } }) });
  const acao = useMutation({
    mutationFn: ({ id, a }: { id: string; a: string }) => api(`/alerts/${id}/${a}`, { metodo: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alertas"] }),
  });

  return (
    <>
      <Cabecalho titulo="Alertas" sub="Ociosidade, consumo acima do normal, falhas de GPS e dados inconsistentes." />
      <div className="mb-5 flex gap-2">
        {ABAS.map((a) => (
          <button key={a.valor} onClick={() => setAba(a.valor)}
            className={`rounded-xl px-4 py-2 text-sm font-semibold ${aba === a.valor ? "bg-folha-700 text-white" : "bg-white text-folha-900/70 shadow-cartao"}`}>
            {a.rotulo}
          </button>
        ))}
      </div>
      {acao.error && <div className="mb-4"><Erro erro={acao.error} /></div>}
      {q.isLoading ? <Carregando /> : q.error ? <Erro erro={q.error} /> : !q.data?.itens.length ? (
        <Vazio titulo={aba === "aberto" ? "Nenhum alerta aberto" : "Nada por aqui"} texto="Os alertas aparecem quando uma regra dispara no processamento dos arquivos." />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {q.data.itens.map((a) => <CartaoAlerta key={a.id} a={a} podeAgir={podeAgir} aoAgir={(x) => acao.mutate({ id: a.id, a: x })} />)}
        </div>
      )}
    </>
  );
}

function CartaoAlerta({ a, podeAgir, aoAgir }: { a: Alerta; podeAgir: boolean; aoAgir: (acao: string) => void }) {
  const [comentando, setComentando] = useState(false);
  const [texto, setTexto] = useState("");
  const qc = useQueryClient();
  const comentar = useMutation({
    mutationFn: () => api(`/alerts/${a.id}/comentarios`, { metodo: "POST", corpo: { texto } }),
    onSuccess: () => {
      setTexto("");
      setComentando(false);
      qc.invalidateQueries({ queryKey: ["alerta", a.id] });
    },
  });
  const borda = { info: "border-l-sky-500", atencao: "border-l-trigo-500", alto: "border-l-rose-600" }[a.severidade];
  return (
    <div className={`cartao border-l-4 ${borda} p-5`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Selo tom={a.severidade}>{ROTULO_TIPO_ALERTA[a.tipo] ?? a.tipo}</Selo>
          <span className="text-xs text-folha-900/50">{a.apelido ?? a.serial}{a.talhao_nome ? ` · ${a.talhao_nome}` : ""}</span>
        </div>
        <span className="whitespace-nowrap text-xs text-folha-900/40">{dataHora(a.inicio ?? a.criado_em)}</span>
      </div>
      <p className="mt-3 text-sm">{a.mensagem}</p>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {a.sessao_id && <Link to={`/sessoes/${a.sessao_id}`} className="btn-secundario px-3 py-1.5 text-xs">Ver operação</Link>}
        {podeAgir && a.status === "aberto" && <button className="btn-secundario px-3 py-1.5 text-xs" onClick={() => aoAgir("reconhecer")}><Check size={14} /> Reconhecer</button>}
        {podeAgir && (a.status === "aberto" || a.status === "reconhecido") && <button className="btn-primario px-3 py-1.5 text-xs" onClick={() => aoAgir("resolver")}><CheckCheck size={14} /> Resolver</button>}
        {podeAgir && (a.status === "reconhecido" || a.status === "resolvido") && <button className="btn-secundario px-3 py-1.5 text-xs" onClick={() => aoAgir("reabrir")}><RotateCcw size={14} /> Reabrir</button>}
        {podeAgir && <button className="ml-auto text-xs font-semibold text-folha-700" onClick={() => setComentando(!comentando)}><MessageSquare size={14} className="mr-1 inline" />Comentar</button>}
      </div>
      {comentando && (
        <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); comentar.mutate(); }}>
          <input className="campo" placeholder="Ex.: operador parou para almoço" value={texto} onChange={(e) => setTexto(e.target.value)} required />
          <button className="btn-primario" disabled={comentar.isPending}>Salvar</button>
        </form>
      )}
    </div>
  );
}
