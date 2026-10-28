import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MailCheck } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { Erro } from "../componentes/ui";
import { useSessao } from "../contextos/Sessao";
import { api, orgAtiva } from "../lib/api";

/** Link do convite: o usuário logado (mesmo e-mail) entra na organização. */
export default function Convite() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const { me } = useSessao();
  const qc = useQueryClient();
  const ir = useNavigate();
  const aceitar = useMutation({
    mutationFn: () => api<{ organizacao_id: string }>(`/convites/${encodeURIComponent(token)}/aceitar`, { metodo: "POST" }),
    onSuccess: async (r) => {
      orgAtiva.set(r.organizacao_id);
      await qc.invalidateQueries();
      ir("/", { replace: true });
    },
  });

  return (
    <div className="fundo-lavoura flex min-h-screen items-center justify-center p-6">
      <div className="cartao w-full max-w-md p-8">
        <div className="mb-5 grid h-12 w-12 place-items-center rounded-2xl bg-folha-50 text-folha-700"><MailCheck /></div>
        <h1 className="text-2xl font-extrabold">Convite para a equipe</h1>
        <p className="mt-1 text-sm text-folha-900/60">
          Você entrou como <b>{me?.email}</b>. O convite só vale para o e-mail para o qual foi enviado.
        </p>
        {aceitar.error && <div className="mt-4"><Erro erro={aceitar.error} /></div>}
        <button className="btn-primario mt-6 w-full" disabled={!token || aceitar.isPending} onClick={() => aceitar.mutate()}>
          {aceitar.isPending ? "Entrando…" : "Aceitar convite"}
        </button>
        <button className="btn-secundario mt-2 w-full" onClick={() => ir("/", { replace: true })}>Agora não</button>
      </div>
    </div>
  );
}
