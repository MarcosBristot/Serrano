import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ruler } from "lucide-react";
import { useState, type FormEvent } from "react";

import { api } from "../lib/api";
import { num } from "../lib/formato";
import { Erro } from "./ui";

type Implemento = { id: string; nome: string; largura_m: number | null };
type Maquina = { id: string; implemento_padrao_id: string | null };
type Resposta = Maquina & { sessoes_recalculadas?: number | null };

const NOVO = "__novo__";

/**
 * Implemento usado quando o arquivo do monitor não diz qual estava engatado (ex.: Trimble da
 * Massey só grava GPS). Com a largura dele a Serrano calcula área, ha/h e L/ha, e refaz as
 * operações da máquina.
 */
export function ImplementoPadrao({ maquinaId, semArea }: { maquinaId: string; semArea: boolean }) {
  const qc = useQueryClient();
  const maquinas = useQuery({ queryKey: ["maquinas-cadastro"], queryFn: () => api<Maquina[]>("/maquinas") });
  const implementos = useQuery({ queryKey: ["implementos"], queryFn: () => api<Implemento[]>("/implementos") });
  const atual = maquinas.data?.find((m) => m.id === maquinaId)?.implemento_padrao_id ?? null;
  const [editando, setEditando] = useState(false);
  const [escolha, setEscolha] = useState<string>("");
  const [nome, setNome] = useState("");
  const [largura, setLargura] = useState("");
  const [recalculadas, setRecalculadas] = useState<number | null>(null);

  const salvar = useMutation({
    mutationFn: async (): Promise<Resposta> => {
      let implementoId: string | null = escolha || null;
      if (escolha === NOVO) {
        const criado = await api<Implemento>("/implementos", {
          metodo: "POST",
          corpo: { nome: nome.trim(), largura_m: Number(largura.replace(",", ".")) },
        });
        implementoId = criado.id;
      }
      return api<Resposta>(`/maquinas/${maquinaId}/implemento-padrao`, { metodo: "PUT", corpo: { implemento_id: implementoId } });
    },
    onSuccess: (r) => {
      setRecalculadas(r.sessoes_recalculadas ?? 0);
      setEditando(false);
      qc.invalidateQueries({ queryKey: ["maquinas-cadastro"] });
      qc.invalidateQueries({ queryKey: ["implementos"] });
      // Os números mudam quando o worker terminar de refazer as operações.
      setTimeout(() => qc.invalidateQueries(), 20_000);
    },
  });

  if (maquinas.isLoading || implementos.isLoading) return null;
  const lista = (implementos.data ?? []).filter((i) => (i.largura_m ?? 0) > 0);
  const escolhido = lista.find((i) => i.id === atual);

  function enviar(e: FormEvent) {
    e.preventDefault();
    salvar.mutate();
  }

  const larguraValida = Number(largura.replace(",", ".")) > 0 && Number(largura.replace(",", ".")) <= 60;
  const podeSalvar = escolha === NOVO ? nome.trim().length > 0 && larguraValida : true;

  return (
    <section className={`cartao mb-6 p-5 ${semArea && !escolhido ? "!border-trigo-300/40" : ""}`}>
      <div className="flex flex-wrap items-start gap-3">
        <Ruler size={20} className="mt-0.5 shrink-0 text-broto-300" />
        <div className="min-w-0 flex-1">
          <h2 className="font-bold">Implemento padrão</h2>
          {escolhido ? (
            <p className="text-sm text-folha-900/70">
              {escolhido.nome} · <b>{num(escolhido.largura_m, 1)} m</b> de largura. Usado quando o arquivo do monitor não informa o implemento.
            </p>
          ) : (
            <p className="text-sm text-folha-900/70">
              {semArea
                ? "O monitor desta máquina não informa o implemento, por isso a área está vazia. Diga a largura do que ela puxa e a Serrano calcula hectares, ha/h e L/ha."
                : "Opcional: usado quando o arquivo do monitor não informa o implemento."}
            </p>
          )}
          {recalculadas !== null && (
            <p className="mt-2 text-sm text-broto-300">
              Salvo. {recalculadas > 0 ? `Recalculando ${recalculadas} arquivo(s); os números atualizam em alguns minutos.` : "Nenhuma operação para recalcular."}
            </p>
          )}
        </div>
        {!editando && (
          <button className="btn-secundario" onClick={() => { setEditando(true); setEscolha(atual ?? (lista.length ? lista[0].id : NOVO)); setRecalculadas(null); }}>
            {escolhido ? "Trocar" : "Informar largura"}
          </button>
        )}
      </div>

      {editando && (
        <form onSubmit={enviar} className="mt-4 grid gap-3 sm:grid-cols-[1fr_1fr_140px_auto] sm:items-end">
          <div>
            <label className="rotulo" htmlFor="impl-escolha">Implemento</label>
            <select id="impl-escolha" className="campo" value={escolha} onChange={(e) => setEscolha(e.target.value)}>
              {lista.map((i) => <option key={i.id} value={i.id}>{i.nome} ({num(i.largura_m, 1)} m)</option>)}
              <option value={NOVO}>+ Novo implemento</option>
              {atual && <option value="">Nenhum (tirar o padrão)</option>}
            </select>
          </div>
          {escolha === NOVO ? (
            <>
              <div>
                <label className="rotulo" htmlFor="impl-nome">Nome</label>
                <input id="impl-nome" className="campo" required maxLength={200} value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Ex.: Plantadeira 9 m" />
              </div>
              <div>
                <label className="rotulo" htmlFor="impl-largura">Largura (m)</label>
                <input id="impl-largura" className="campo" required inputMode="decimal" value={largura} onChange={(e) => setLargura(e.target.value)} placeholder="9" />
              </div>
            </>
          ) : (
            <div className="sm:col-span-2" />
          )}
          <div className="flex gap-2">
            <button className="btn-primario" disabled={salvar.isPending || !podeSalvar}>{salvar.isPending ? "Salvando…" : "Salvar"}</button>
            <button type="button" className="btn-secundario" onClick={() => setEditando(false)}>Cancelar</button>
          </div>
          {salvar.error && <div className="sm:col-span-4"><Erro erro={salvar.error} /></div>}
        </form>
      )}
    </section>
  );
}
