/** Aba de manutenção de uma máquina: horímetro, o que vence e o histórico do que foi feito. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Gauge, Plus, Wrench } from "lucide-react";
import { useState } from "react";

import { Carregando, Erro, Selo } from "./ui";
import { useSessao } from "../contextos/Sessao";
import { api } from "../lib/api";
import { num, rs } from "../lib/formato";

interface Plano {
  id: string;
  nome: string;
  intervalo_h: number;
  ultima_h: number | null;
  ultima_em: string | null;
  proxima_h: number | null;
  faltam_h: number | null;
  situacao: "em_dia" | "proxima" | "vencida" | "sem_referencia";
  dias_trabalho: number | null;
}
interface Situacao {
  horimetro_h: number | null;
  fonte: "monitor" | "informado" | null;
  uso_h_dia: number | null;
  planos: Plano[];
  historico: { id: string; nome: string; horimetro_h: number; feita_em: string; custo_rs: number | null; observacao: string | null }[];
}

const SELO = {
  vencida: { tom: "alto", texto: "Vencida" },
  proxima: { tom: "atencao", texto: "Agendar" },
  em_dia: { tom: "ok", texto: "Em dia" },
  sem_referencia: { tom: "neutro", texto: "Sem referência" },
} as const;

const hoje = () => new Date().toISOString().slice(0, 10);

export function AbaManutencao({ maquinaId, tipo }: { maquinaId: string; tipo: string }) {
  const qc = useQueryClient();
  const { papel } = useSessao();
  const pode = papel === "owner" || papel === "gestor";
  const chave = ["manutencao", maquinaId];
  const q = useQuery({ queryKey: chave, queryFn: () => api<Situacao>(`/maquinas/${maquinaId}/manutencao`) });
  const atualizar = () => { qc.invalidateQueries({ queryKey: chave }); qc.invalidateQueries({ queryKey: ["pendencias"] }); };
  const modelo = useMutation({
    mutationFn: () => api(`/maquinas/${maquinaId}/manutencao/modelo`, { metodo: "POST", corpo: { tipo } }),
    onSuccess: atualizar,
  });
  const [leitura, setLeitura] = useState("");
  const horimetro = useMutation({
    mutationFn: () => api(`/maquinas/${maquinaId}/horimetro`, { metodo: "PUT", corpo: { horimetro_h: Number(leitura) } }),
    onSuccess: () => { setLeitura(""); atualizar(); },
  });
  const [novo, setNovo] = useState({ nome: "", intervalo_h: "" });
  const criar = useMutation({
    mutationFn: () => api(`/maquinas/${maquinaId}/manutencao/planos`, {
      metodo: "POST", corpo: { nome: novo.nome, intervalo_h: Number(novo.intervalo_h), ultima_h: q.data?.horimetro_h ?? null },
    }),
    onSuccess: () => { setNovo({ nome: "", intervalo_h: "" }); atualizar(); },
  });
  const [feita, setFeita] = useState<{ plano: Plano; horimetro: string; data: string; custo: string } | null>(null);
  const registrar = useMutation({
    mutationFn: () => api(`/manutencao/planos/${feita!.plano.id}/feita`, {
      metodo: "POST",
      corpo: { horimetro_h: Number(feita!.horimetro), feita_em: feita!.data, custo_rs: feita!.custo ? Number(feita!.custo) : null },
    }),
    onSuccess: () => { setFeita(null); atualizar(); },
  });

  if (q.isLoading) return <Carregando />;
  if (q.error) return <Erro erro={q.error} />;
  const s = q.data!;
  const erro = modelo.error ?? horimetro.error ?? criar.error ?? registrar.error;

  return (
    <div className="space-y-6">
      {erro && <Erro erro={erro} />}
      <div className="grid gap-4 md:grid-cols-[320px_1fr]">
        <section className="cartao p-5">
          <div className="flex items-center gap-2 text-sm font-semibold text-folha-900/70"><Gauge size={18} className="text-broto-300" /> Horímetro</div>
          <div className="mt-2 font-display text-4xl font-extrabold">{s.horimetro_h == null ? "—" : `${num(s.horimetro_h, 0)} h`}</div>
          <p className="mt-1 text-sm text-folha-900/60">
            {s.fonte === "monitor" ? "lido do monitor" : s.fonte === "informado" ? "informado + horas registradas depois" : "o monitor desta máquina não grava o horímetro"}
            {s.uso_h_dia ? ` · ~${num(s.uso_h_dia, 1)} h por dia trabalhado` : ""}
          </p>
          {pode && (
            <form className="mt-4 flex gap-2" onSubmit={(e) => { e.preventDefault(); horimetro.mutate(); }}>
              <input className="campo" type="number" min={0} step={0.1} required placeholder="Leitura do painel (h)" value={leitura}
                onChange={(e) => setLeitura(e.target.value)} aria-label="Leitura do horímetro no painel" />
              <button className="btn-secundario whitespace-nowrap" disabled={horimetro.isPending}>Informar</button>
            </form>
          )}
        </section>

        <section className="cartao p-5">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="flex items-center gap-2 font-bold"><Wrench size={18} className="text-broto-300" /> Plano de manutenção</h2>
            {pode && !s.planos.length && (
              <button className="btn-primario !py-2 text-sm" onClick={() => modelo.mutate()} disabled={modelo.isPending}>
                Usar plano sugerido
              </button>
            )}
          </div>
          {!s.planos.length ? (
            <p className="text-sm text-folha-900/60">
              Nenhum item ainda. O plano sugerido traz os intervalos mais comuns (troca de óleo a cada 250 h, filtros a cada 500 h…);
              ajuste depois pelo manual da sua máquina.
            </p>
          ) : (
            <ul className="space-y-2">
              {s.planos.map((p) => {
                const pctUsado = p.faltam_h == null ? 0 : Math.min(100, Math.max(0, 100 * (1 - p.faltam_h / p.intervalo_h)));
                return (
                  <li key={p.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                    <div className="flex flex-wrap items-center gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2 font-semibold">
                          {p.nome} <Selo tom={SELO[p.situacao].tom}>{SELO[p.situacao].texto}</Selo>
                        </div>
                        <div className="text-xs text-folha-900/60">
                          a cada {num(p.intervalo_h, 0)} h
                          {p.faltam_h != null && (p.faltam_h > 0
                            ? ` · faltam ${num(p.faltam_h, 0)} h${p.dias_trabalho != null ? ` (~${num(Math.max(1, p.dias_trabalho), 0)} dias de trabalho)` : ""}`
                            : ` · passou ${num(-p.faltam_h, 0)} h`)}
                          {p.ultima_em ? ` · última: ${new Date(`${p.ultima_em}T12:00:00`).toLocaleDateString("pt-BR")} com ${num(p.ultima_h, 0)} h` : ""}
                        </div>
                      </div>
                      {pode && (
                        <button className="btn-secundario !py-1.5 text-xs" onClick={() => setFeita({ plano: p, horimetro: String(Math.round(s.horimetro_h ?? 0)), data: hoje(), custo: "" })}>
                          <CheckCircle2 size={14} /> Feito
                        </button>
                      )}
                    </div>
                    <div className="mt-2 h-1.5 rounded-full bg-white/5" aria-hidden="true">
                      <div className={`h-1.5 rounded-full ${p.situacao === "vencida" ? "bg-rose-400" : p.situacao === "proxima" ? "bg-trigo-400" : "bg-broto-500"}`} style={{ width: `${pctUsado}%` }} />
                    </div>
                    {feita?.plano.id === p.id && (
                      <form className="mt-3 grid gap-2 sm:grid-cols-[1fr_1fr_1fr_auto]" onSubmit={(e) => { e.preventDefault(); registrar.mutate(); }}>
                        <label><span className="rotulo">Horímetro</span><input className="campo" type="number" min={0} step={0.1} required value={feita.horimetro} onChange={(e) => setFeita({ ...feita, horimetro: e.target.value })} /></label>
                        <label><span className="rotulo">Data</span><input className="campo" type="date" required value={feita.data} onChange={(e) => setFeita({ ...feita, data: e.target.value })} /></label>
                        <label><span className="rotulo">Custo (R$)</span><input className="campo" type="number" min={0} step={0.01} value={feita.custo} onChange={(e) => setFeita({ ...feita, custo: e.target.value })} /></label>
                        <div className="flex items-end gap-2">
                          <button className="btn-primario" disabled={registrar.isPending}>Salvar</button>
                          <button type="button" className="btn-secundario" onClick={() => setFeita(null)}>Cancelar</button>
                        </div>
                      </form>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          {pode && s.planos.length > 0 && (
            <form className="mt-4 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); criar.mutate(); }}>
              <input className="campo flex-1" placeholder="Outro item (ex.: troca das facas)" required minLength={2} value={novo.nome} onChange={(e) => setNovo({ ...novo, nome: e.target.value })} />
              <input className="campo w-36" type="number" min={1} placeholder="a cada (h)" required value={novo.intervalo_h} onChange={(e) => setNovo({ ...novo, intervalo_h: e.target.value })} />
              <button className="btn-secundario" disabled={criar.isPending}><Plus size={16} /> Adicionar</button>
            </form>
          )}
        </section>
      </div>

      {s.historico.length > 0 && (
        <section className="cartao overflow-x-auto">
          <h2 className="px-5 pb-2 pt-5 font-bold">Histórico</h2>
          <table className="tabela w-full min-w-[560px]">
            <thead><tr><th>Quando</th><th>O quê</th><th className="text-right">Horímetro</th><th className="text-right">Custo</th></tr></thead>
            <tbody>
              {s.historico.map((f) => (
                <tr key={f.id}>
                  <td>{new Date(`${f.feita_em}T12:00:00`).toLocaleDateString("pt-BR")}</td>
                  <td>{f.nome}</td>
                  <td className="text-right">{num(f.horimetro_h, 0)} h</td>
                  <td className="text-right">{rs(f.custo_rs)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
