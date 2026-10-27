import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Sprout } from "lucide-react";
import { useState } from "react";

import { Erro } from "../componentes/ui";
import { useSessao } from "../contextos/Sessao";
import { api } from "../lib/api";

/** Primeiro acesso: o usuário ainda não participa de nenhuma organização. */
export default function BoasVindas() {
  const { me, sair } = useSessao();
  const [nome, setNome] = useState("");
  const qc = useQueryClient();
  const criar = useMutation({
    mutationFn: () => api("/organizacoes", { metodo: "POST", corpo: { nome } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });

  return (
    <div className="fundo-lavoura flex min-h-screen items-center justify-center p-6">
      <div className="cartao w-full max-w-md p-8">
        <div className="mb-5 grid h-12 w-12 place-items-center rounded-2xl bg-folha-50 text-folha-700"><Sprout /></div>
        <h1 className="text-2xl font-extrabold">Bem-vindo à Serrano</h1>
        <p className="mt-1 text-sm text-folha-900/60">
          {me?.email}, crie a sua fazenda (organização). Depois você convida a equipe e envia o pendrive do monitor.
        </p>
        <form className="mt-6" onSubmit={(e) => { e.preventDefault(); criar.mutate(); }}>
          <label className="rotulo" htmlFor="nome">Nome da fazenda ou empresa</label>
          <input id="nome" className="campo" required minLength={2} value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Ex.: Agropecuária Serrano" />
          {criar.error && <div className="mt-4"><Erro erro={criar.error} /></div>}
          <button className="btn-primario mt-5 w-full" disabled={criar.isPending}>{criar.isPending ? "Criando…" : "Criar e começar"}</button>
        </form>
        <p className="mt-4 text-center text-xs text-folha-900/50">
          Recebeu um convite? Abra o link do e-mail. <button onClick={sair} className="font-semibold text-folha-700">Sair</button>
        </p>
      </div>
    </div>
  );
}
