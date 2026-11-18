/** Plano e assinatura: situação do teste, uso da conta e contratação de um plano. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Check, CheckCircle2, HardDrive, LandPlot, Send, Tractor, Users } from "lucide-react";
import { useState } from "react";

import { Cabecalho, Carregando, Erro, Selo } from "../componentes/ui";
import { useSessao } from "../contextos/Sessao";
import { api } from "../lib/api";
import { data, num } from "../lib/formato";

export interface Plano {
  codigo: string;
  nome: string;
  descricao: string;
  max_maquinas: number;
  preco_mensal_centavos: number;
  preco_anual_centavos: number | null;
  destaque: boolean;
  sob_consulta: boolean;
  recursos: string[];
}

export interface Assinatura {
  plano_codigo: string;
  plano_nome: string;
  status: string;
  situacao: "trial" | "ativa" | "trial_vencido" | "vencida" | "suspensa" | "cancelada";
  inicio: string;
  fim: string | null;
  dias_restantes: number | null;
  max_maquinas: number;
  uso: { maquinas: number; envios: number; armazenamento_bytes: number; hectares: number; usuarios: number };
  pedido_aberto: { plano_codigo: string; ciclo: string; criado_em: string } | null;
  planos: Plano[];
}

const reais = (centavos: number) =>
  (centavos / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });

const tamanho = (b: number) =>
  b >= 1024 ** 3 ? `${num(b / 1024 ** 3, 1)} GB` : b >= 1024 ** 2 ? `${num(b / 1024 ** 2, 0)} MB` : `${num(b / 1024, 0)} KB`;

const SITUACAO: Record<Assinatura["situacao"], { rotulo: string; tom: "ok" | "info" | "alto" | "atencao" }> = {
  trial: { rotulo: "Teste grátis", tom: "info" },
  ativa: { rotulo: "Ativa", tom: "ok" },
  trial_vencido: { rotulo: "Teste encerrado", tom: "alto" },
  vencida: { rotulo: "Vencida", tom: "alto" },
  suspensa: { rotulo: "Suspensa", tom: "alto" },
  cancelada: { rotulo: "Cancelada", tom: "alto" },
};

export function useAssinatura() {
  return useQuery({ queryKey: ["assinatura"], queryFn: () => api<Assinatura>("/assinatura"), staleTime: 5 * 60_000 });
}

function Uso({ icone, rotulo, valor, limite }: { icone: React.ReactNode; rotulo: string; valor: string; limite?: { usado: number; max: number } }) {
  const pct = limite ? Math.min(100, (100 * limite.usado) / limite.max) : null;
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-folha-900/55">{icone}{rotulo}</div>
      <div className="mt-2 font-display text-2xl font-extrabold">{valor}</div>
      {pct != null && (
        <div className="mt-2 h-1.5 rounded-full bg-white/10">
          <div className={`h-1.5 rounded-full ${pct >= 90 ? "bg-rose-400" : "bg-broto-500"}`} style={{ width: `${pct}%` }} />
        </div>
      )}
    </div>
  );
}

export default function PlanoPagina() {
  const { papel } = useSessao();
  const q = useAssinatura();
  const cliente = useQueryClient();
  const [ciclo, setCiclo] = useState<"mensal" | "anual">("mensal");
  const [escolhido, setEscolhido] = useState<Plano | null>(null);
  const [telefone, setTelefone] = useState("");
  const [mensagem, setMensagem] = useState("");
  const pedir = useMutation({
    mutationFn: () =>
      api("/assinatura/pedidos", {
        metodo: "POST",
        corpo: { plano_codigo: escolhido!.codigo, ciclo, telefone: telefone || null, mensagem: mensagem || null },
      }),
    onSuccess: () => {
      setEscolhido(null);
      cliente.invalidateQueries({ queryKey: ["assinatura"] });
    },
  });

  if (q.isLoading) return <Carregando />;
  if (q.error) return <Erro erro={q.error} />;
  const a = q.data!;
  const sit = SITUACAO[a.situacao];
  const dono = papel === "owner";

  return (
    <>
      <Cabecalho titulo="Plano e assinatura" sub="Mensalidade pelo tamanho da frota. Sem fidelidade, sem taxa de instalação." />

      <section className="cartao-destaque mb-8 grid gap-6 p-6 lg:grid-cols-[1fr_2fr]">
        <div>
          <div className="flex items-center gap-2">
            <Selo tom={sit.tom}>{sit.rotulo}</Selo>
            <span className="text-xs text-folha-900/55">plano {a.plano_nome}</span>
          </div>
          <div className="mt-3 font-display text-3xl font-extrabold text-folha-950">
            {a.situacao === "trial" ? `${a.dias_restantes ?? 0} dias de teste` : a.situacao === "ativa" ? `Até ${data(a.fim)}` : "Envios pausados"}
          </div>
          <p className="mt-2 text-sm text-folha-900/65">
            {a.situacao === "trial"
              ? `Tudo liberado até ${data(a.fim)}. Depois, escolha um plano para continuar enviando pendrives; os dados já enviados ficam com você.`
              : a.situacao === "ativa"
                ? "Obrigado por usar a Serrano. A renovação é combinada com a nossa equipe."
                : "Os dados continuam visíveis. Escolha um plano para voltar a enviar pendrives."}
          </p>
          {a.pedido_aberto && (
            <div className="mt-4 flex items-start gap-2 rounded-xl bg-broto-500/10 p-3 text-sm text-broto-300 ring-1 ring-broto-400/25">
              <CheckCircle2 size={18} className="mt-0.5 shrink-0" />
              Pedido do plano {a.planos.find((p) => p.codigo === a.pedido_aberto!.plano_codigo)?.nome ?? a.pedido_aberto.plano_codigo} ({a.pedido_aberto.ciclo}) recebido em {data(a.pedido_aberto.criado_em)}. Vamos entrar em contato para combinar o pagamento.
            </div>
          )}
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Uso icone={<Tractor size={14} />} rotulo="Máquinas" valor={`${a.uso.maquinas} de ${a.max_maquinas}`} limite={{ usado: a.uso.maquinas, max: a.max_maquinas }} />
          <Uso icone={<LandPlot size={14} />} rotulo="Hectares medidos" valor={num(a.uso.hectares, 0)} />
          <Uso icone={<HardDrive size={14} />} rotulo="Pendrives guardados" valor={tamanho(a.uso.armazenamento_bytes)} />
          <Uso icone={<Users size={14} />} rotulo="Usuários" valor={`${a.uso.usuarios}`} />
        </div>
      </section>

      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-xl font-extrabold">Planos</h2>
        <div className="flex gap-1 rounded-xl border border-white/10 bg-white/5 p-1" role="group" aria-label="Ciclo de cobrança">
          {(["mensal", "anual"] as const).map((c) => (
            <button key={c} onClick={() => setCiclo(c)} aria-pressed={ciclo === c} className={`aba ${ciclo === c ? "aba-ativa" : ""}`}>
              {c === "mensal" ? "Mensal" : "Anual · 2 meses grátis"}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        {a.planos.map((p) => {
          const atual = a.plano_codigo === p.codigo && a.situacao === "ativa";
          const preco = ciclo === "anual" && p.preco_anual_centavos != null ? p.preco_anual_centavos / 12 : p.preco_mensal_centavos;
          return (
            <article
              key={p.codigo}
              className={`cartao relative flex flex-col p-6 ${p.destaque ? "!border-broto-400/50 shadow-[0_0_50px_-18px_rgba(140,198,63,.7)]" : ""}`}
            >
              {p.destaque && (
                <span className="absolute -top-3 left-6 rounded-full bg-broto-500 px-3 py-1 text-xs font-bold text-noite-950">Mais escolhido</span>
              )}
              <h3 className="font-display text-xl font-extrabold">{p.nome}</h3>
              <p className="mt-1 min-h-[2.5rem] text-sm text-folha-900/60">{p.descricao}</p>
              <div className="mt-4 flex items-baseline gap-1">
                {p.sob_consulta ? (
                  <span className="font-display text-3xl font-extrabold">Sob consulta</span>
                ) : (
                  <>
                    <span className="font-display text-4xl font-extrabold">{reais(preco)}</span>
                    <span className="text-sm text-folha-900/55">/mês</span>
                  </>
                )}
              </div>
              <p className="mt-1 h-5 text-xs text-folha-900/50">
                {!p.sob_consulta && ciclo === "anual" && p.preco_anual_centavos != null ? `${reais(p.preco_anual_centavos)} por ano` : ""}
              </p>
              <ul className="mt-5 flex-1 space-y-2.5 text-sm">
                {p.recursos.map((r) => (
                  <li key={r} className="flex gap-2"><Check size={16} className="mt-0.5 shrink-0 text-broto-400" />{r}</li>
                ))}
              </ul>
              <button
                className={`mt-6 ${p.destaque ? "btn-primario" : "btn-secundario"}`}
                disabled={!dono || atual || !!a.pedido_aberto}
                onClick={() => setEscolhido(p)}
              >
                {atual ? "Plano atual" : p.sob_consulta ? "Falar com a equipe" : "Contratar"}
              </button>
            </article>
          );
        })}
      </div>
      {!dono && <p className="mt-4 text-xs text-folha-900/55">Só o dono da conta pode contratar um plano.</p>}

      {escolhido && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4" role="dialog" aria-modal="true" aria-labelledby="titulo-pedido">
          <form
            className="cartao w-full max-w-md p-6"
            onSubmit={(e) => {
              e.preventDefault();
              pedir.mutate();
            }}
          >
            <h2 id="titulo-pedido" className="font-display text-xl font-extrabold">Contratar o plano {escolhido.nome}</h2>
            <p className="mt-1 text-sm text-folha-900/60">
              {escolhido.sob_consulta
                ? "Conte o tamanho da operação e montamos a proposta."
                : `${ciclo === "anual" && escolhido.preco_anual_centavos != null ? `${reais(escolhido.preco_anual_centavos)} por ano` : `${reais(escolhido.preco_mensal_centavos)} por mês`}. A nossa equipe entra em contato para combinar o pagamento (PIX ou boleto).`}
            </p>
            <label className="rotulo mt-5" htmlFor="p-tel">WhatsApp ou telefone</label>
            <input id="p-tel" className="campo" value={telefone} onChange={(e) => setTelefone(e.target.value)} maxLength={40} inputMode="tel" autoComplete="tel" />
            <label className="rotulo mt-4" htmlFor="p-msg">Mensagem (opcional)</label>
            <textarea id="p-msg" className="campo" rows={3} value={mensagem} onChange={(e) => setMensagem(e.target.value)} maxLength={2000} />
            {pedir.error && <div className="mt-3"><Erro erro={pedir.error} /></div>}
            <div className="mt-6 flex justify-end gap-2">
              <button type="button" className="btn-secundario" onClick={() => setEscolhido(null)}>Cancelar</button>
              <button type="submit" className="btn-primario" disabled={pedir.isPending}><Send size={16} /> Enviar pedido</button>
            </div>
          </form>
        </div>
      )}

      <p className="mt-8 flex items-center gap-2 text-xs text-folha-900/50">
        <CalendarClock size={14} /> Valores em reais. Cancelamento a qualquer momento; veja a política de cancelamento e reembolso no site.
      </p>
    </>
  );
}
