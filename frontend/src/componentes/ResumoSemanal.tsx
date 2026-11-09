/** O resumo da semana pronto para mandar no WhatsApp (o mesmo texto que vai por e-mail toda segunda). */
import { useQuery } from "@tanstack/react-query";
import { Check, Copy, MessageCircle } from "lucide-react";
import { useState } from "react";

import { Carregando, Erro } from "./ui";
import { api } from "../lib/api";

interface Resumo {
  inicio: string;
  fim: string;
  texto: string;
  acoes: string[];
}

/** WhatsApp: *negrito*; aqui vira <b> só para a prévia. */
function Previa({ texto }: { texto: string }) {
  return (
    <div className="whitespace-pre-wrap rounded-2xl rounded-tl-sm bg-[#1f3d2a] p-4 text-sm leading-relaxed text-folha-950 shadow-cartao">
      {texto.split("\n").map((linha, i) => (
        <div key={i}>
          {linha.split(/(\*[^*]+\*)/g).map((p, j) => (p.startsWith("*") && p.endsWith("*") ? <b key={j}>{p.slice(1, -1)}</b> : p))}
          {!linha && " "}
        </div>
      ))}
    </div>
  );
}

export function ResumoSemanal({ ultimoDia }: { ultimoDia: string | null }) {
  // Sem trabalho nos últimos 7 dias (entressafra, pendrive não enviado): mostra a última semana com operação.
  const ontem = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
  const fim = ultimoDia && ultimoDia < new Date(Date.now() - 7 * 86_400_000).toISOString().slice(0, 10) ? ultimoDia : ontem;
  const q = useQuery({ queryKey: ["resumo-semanal", fim], queryFn: () => api<Resumo>("/resumo-semanal", { params: { fim } }) });
  const [copiado, setCopiado] = useState(false);

  return (
    <section className="cartao p-5" aria-labelledby="t-resumo-semana">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="t-resumo-semana" className="flex items-center gap-2 text-lg font-bold">
          <MessageCircle size={20} className="text-broto-300" aria-hidden="true" /> Resumo da semana
        </h2>
        <span className="text-xs text-folha-900/60">vai por e-mail toda segunda às 7 h para os destinos cadastrados</span>
      </div>
      {q.isLoading ? <Carregando /> : q.error ? <Erro erro={q.error} /> : q.data && (
        <div className="grid gap-4 lg:grid-cols-[1fr_auto]">
          <Previa texto={q.data.texto} />
          <div className="flex flex-row gap-2 lg:flex-col">
            <a className="btn-primario" target="_blank" rel="noreferrer"
              href={`https://wa.me/?text=${encodeURIComponent(q.data.texto)}`}>
              <MessageCircle size={16} /> Abrir no WhatsApp
            </a>
            <button className="btn-secundario" onClick={async () => {
              try { await navigator.clipboard.writeText(q.data!.texto); setCopiado(true); setTimeout(() => setCopiado(false), 2000); } catch { /* sem permissão */ }
            }}>
              {copiado ? <><Check size={16} /> Copiado</> : <><Copy size={16} /> Copiar</>}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
