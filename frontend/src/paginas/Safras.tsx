/**
 * Fechamento da safra por talhão: o que a colheitadeira colheu (sacas secas) e quanto as
 * máquinas custaram em cada talhão desde a colheita anterior. É o relatório que o produtor leva
 * ao banco e usa para decidir onde mexer na próxima safra.
 */
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Coins, Printer, Sprout, TrendingDown, TrendingUp, Wheat } from "lucide-react";
import { Fragment, useEffect, useMemo, useState } from "react";

import { Mapa, type FC } from "../componentes/Mapa";
import { Cabecalho, Carregando, Erro, Selo, Vazio } from "../componentes/ui";
import { useSessao } from "../contextos/Sessao";
import { api } from "../lib/api";
import { useContornos } from "../lib/consultas";
import { horas, nomeTalhao, num, pct, rs } from "../lib/formato";
import type { Fechamento, SafraResumo, TalhaoFechamento } from "../lib/tipos";

const ROTULO_CULTURA: Record<string, string> = {
  soja: "Soja", milho: "Milho", trigo: "Trigo", aveia: "Aveia", cevada: "Cevada", canola: "Canola", feijao: "Feijão",
};
// Preço de referência só para sugerir; o produtor troca pelo dele (fica salvo no navegador).
const PRECO_SACA_PADRAO: Record<string, number> = { soja: 125, milho: 60, trigo: 70, aveia: 45, cevada: 70, canola: 120 };
const ROTULO_OP: Record<string, string> = {
  colheita: "Colheita", plantio: "Plantio", pulverizacao: "Pulverização", outras: "Outras operações",
};

function usePreferencia(chave: string, inicial: number): [number, (v: number) => void] {
  const [v, setV] = useState<number>(() => {
    try { const s = localStorage.getItem(chave); return s ? Number(s) : inicial; } catch { return inicial; }
  });
  useEffect(() => { try { localStorage.setItem(chave, String(v)); } catch { /* sem armazenamento */ } }, [chave, v]);
  return [v, setV];
}

/** Escala de produtividade relativa à média da safra: vermelho (abaixo) -> verde (acima). */
function corRelativa(vs: number | null): string {
  if (vs == null) return "#64748b";
  if (vs <= -20) return "#dc2626";
  if (vs <= -8) return "#f59e0b";
  if (vs < 8) return "#a3c94a";
  if (vs < 20) return "#5fb83a";
  return "#2f9e44";
}

export default function Safras() {
  const { org } = useSessao();
  const safras = useQuery({ queryKey: ["safras"], queryFn: () => api<SafraResumo[]>("/safras") });
  const [escolhida, setEscolhida] = useState<SafraResumo | null>(null);
  const atual = escolhida ?? safras.data?.[0] ?? null;
  const safra = atual?.safra ?? null;
  const fech = useQuery({
    queryKey: ["fechamento", safra, atual?.cultura],
    queryFn: () => api<Fechamento>("/safras/fechamento", { params: { safra: safra!, cultura: atual?.cultura ?? undefined } }),
    enabled: Boolean(safra),
  });
  const contornos = useContornos();
  const [aberto, setAberto] = useState<string | null>(null);

  const culturaPrincipal = atual?.cultura ?? "soja";
  const [precoSaca, setPrecoSaca] = usePreferencia(`serrano:preco-saca:${culturaPrincipal}`, PRECO_SACA_PADRAO[culturaPrincipal] ?? 100);
  const [custoHora, setCustoHora] = usePreferencia("serrano:custo-hora-maquina", 0);

  const mapa: FC | undefined = useMemo(() => {
    if (!contornos.dados || !fech.data) return undefined;
    const porId = new Map(fech.data.talhoes.filter((t) => t.talhao_id).map((t) => [t.talhao_id!, t]));
    return {
      type: "FeatureCollection",
      features: contornos.dados.features
        .filter((f) => porId.has(String(f.properties?.id)))
        .map((f) => {
          const t = porId.get(String(f.properties?.id))!;
          return { ...f, properties: { ...f.properties, cor: corRelativa(t.vs_media_pct), rotulo: `${nomeTalhao(t.talhao_nome)}\n${num(t.sc_ha, 0)} sc/ha` } };
        }),
    };
  }, [contornos.dados, fech.data]);

  if (safras.isLoading) return <Carregando />;
  if (safras.error) return <Erro erro={safras.error} />;
  if (!safras.data?.length) {
    return (
      <>
        <Cabecalho titulo="Safras" />
        <Vazio titulo="Nenhuma colheita ainda" texto="Envie o pendrive da colheitadeira (pasta GS3_2630) para fechar a safra por talhão." />
      </>
    );
  }

  const f = fech.data;
  const custoMaquina = (t: { custo_diesel_rs: number | null; motor_h: number }) => (t.custo_diesel_rs ?? 0) + t.motor_h * custoHora;
  const talhoes = (f?.talhoes ?? []).filter((t) => t.area_colhida_ha >= 1);
  const media = f?.sc_ha ?? null;
  const abaixo = talhoes.filter((t) => t.sc_ha != null && media != null && t.sc_ha < media);
  const sacasPerdidas = abaixo.reduce((s, t) => s + (media! - t.sc_ha!) * t.area_colhida_ha, 0);
  const melhor = talhoes[0];
  const pior = talhoes[talhoes.length - 1];

  return (
    <div className="impressao">
      <Cabecalho
        titulo="Fechamento da safra"
        sub="Produtividade de cada talhão em sacas secas e o custo das máquinas para produzir cada saca."
        acoes={<button className="btn-secundario nao-imprimir" onClick={() => window.print()}><Printer size={16} /> Imprimir / PDF</button>}
      />

      <div className="nao-imprimir mb-6 flex flex-wrap gap-2" role="tablist" aria-label="Safra">
        {safras.data.map((s) => {
          const ativa = s.safra === safra && s.cultura === atual?.cultura;
          return (
          <button key={`${s.safra}-${s.cultura}`} role="tab" aria-selected={ativa} onClick={() => setEscolhida(s)}
            className={`rounded-xl border px-3 py-2 text-left text-sm transition ${ativa ? "border-broto-400/50 bg-broto-500/15" : "border-white/10 bg-white/5 hover:bg-white/10"}`}>
            <div className="font-semibold">{ROTULO_CULTURA[s.cultura ?? ""] ?? s.cultura ?? "Safra"} {s.safra}</div>
            <div className="text-xs text-folha-900/60">{num(s.sc_ha, 1)} sc/ha · {num(s.area_colhida_ha, 0)} ha</div>
          </button>
          );
        })}
      </div>

      {fech.isLoading ? <Carregando /> : fech.error ? <Erro erro={fech.error} /> : f && (
        <div className="space-y-6">
          <section className="cartao-destaque p-6">
            <div className="flex flex-wrap items-center gap-2 text-sm text-broto-300">
              <Wheat size={16} aria-hidden="true" /> {org?.nome} · {ROTULO_CULTURA[culturaPrincipal] ?? culturaPrincipal} {f.safra}
            </div>
            <div className="mt-4 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              <Grande rotulo="Produção" valor={`${num(f.sacas, 0)} sc`} sub={`${num(f.area_colhida_ha, 0)} ha colhidos`} />
              <Grande rotulo="Produtividade média" valor={`${num(f.sc_ha, 1)} sc/ha`} sub="massa seca, umidade de venda" />
              <Grande rotulo="Máquina por saca" valor={rs(f.sacas ? (custoMaquina(f) / f.sacas) : null)}
                sub={custoHora ? `diesel + ${rs(custoHora)}/h de máquina` : `só diesel · ${num(f.litros, 0)} L`} />
              <Grande rotulo="Horas de máquina" valor={`${num(f.horas_ha, 2)} h/ha`} sub={`${horas(f.motor_h)} no total`} />
            </div>
          </section>

          {talhoes.length >= 2 && melhor && pior && media && (
            <section className="grid gap-4 lg:grid-cols-3" aria-label="Destaques">
              <Destaque icone={TrendingUp} tom="broto" titulo={`Melhor: ${nomeTalhao(melhor.talhao_nome)}`}
                texto={`${num(melhor.sc_ha, 1)} sc/ha, ${pct(melhor.vs_media_pct)} acima da média.`} />
              <Destaque icone={TrendingDown} tom="rosa" titulo={`Mais fraco: ${nomeTalhao(pior.talhao_nome)}`}
                texto={`${num(pior.sc_ha, 1)} sc/ha, ${pct(Math.abs(pior.vs_media_pct ?? 0))} abaixo da média${pior.custo_diesel_saca && melhor.custo_diesel_saca ? `; o diesel por saca saiu ${num(pior.custo_diesel_saca / melhor.custo_diesel_saca, 1)}× o do melhor` : ""}.`} />
              <Destaque icone={Coins} tom="trigo" titulo={`${num(sacasPerdidas, 0)} sacas abaixo da média`}
                texto={`Se os talhões fracos rendessem a média da fazenda, seriam cerca de ${rs(sacasPerdidas * precoSaca)} a mais. É aí que vale investigar solo, plantio e manejo.`} />
            </section>
          )}

          <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
            <div className="cartao p-2">
              <div className="flex flex-wrap items-center justify-between gap-2 px-3 pb-2 pt-2">
                <h2 className="font-bold">Mapa de produtividade</h2>
                <div className="flex items-center gap-2 text-xs text-folha-900/70" aria-hidden="true">
                  <span>abaixo</span>
                  {["#dc2626", "#f59e0b", "#a3c94a", "#5fb83a", "#2f9e44"].map((c) => <i key={c} className="inline-block h-2.5 w-6 rounded-sm" style={{ background: c }} />)}
                  <span>acima da média</span>
                </div>
              </div>
              {contornos.carregando ? <Carregando texto="Carregando talhões…" /> : (
                <Mapa className="h-[52vh] min-h-[360px]" camadas={{ produtividade: mapa }} />
              )}
            </div>
            <div className="cartao nao-imprimir space-y-4 p-5">
              <h2 className="font-bold">Seus números</h2>
              <p className="text-sm text-folha-900/60">Para transformar sacas em dinheiro. Ficam salvos neste navegador.</p>
              <label className="block">
                <span className="rotulo">Preço da saca de {ROTULO_CULTURA[culturaPrincipal] ?? culturaPrincipal} (R$)</span>
                <input type="number" min={0} step={1} className="campo" value={precoSaca} onChange={(e) => setPrecoSaca(Number(e.target.value) || 0)} />
              </label>
              <label className="block">
                <span className="rotulo">Custo da hora-máquina além do diesel (R$/h)</span>
                <input type="number" min={0} step={10} className="campo" value={custoHora} onChange={(e) => setCustoHora(Number(e.target.value) || 0)} />
                <span className="mt-1 block text-xs text-folha-900/55">Operador, manutenção e depreciação. Deixe 0 para ver só o diesel.</span>
              </label>
              <div className="rounded-xl bg-white/5 p-3 text-sm">
                <div className="flex justify-between"><span className="text-folha-900/70">Receita estimada</span><b>{rs(f.sacas * precoSaca)}</b></div>
                <div className="mt-1 flex justify-between"><span className="text-folha-900/70">Custo de máquina</span><b>{rs(custoMaquina(f))}</b></div>
                <div className="mt-1 flex justify-between"><span className="text-folha-900/70">Máquina sobre a receita</span>
                  <b>{pct(f.sacas && precoSaca ? (100 * custoMaquina(f)) / (f.sacas * precoSaca) : null, 1)}</b></div>
              </div>
            </div>
          </div>

          <section className="cartao overflow-x-auto" aria-labelledby="t-talhoes">
            <h2 id="t-talhoes" className="px-5 pb-2 pt-5 font-bold">Talhão a talhão</h2>
            <table className="tabela w-full min-w-[920px]">
              <thead>
                <tr>
                  <th>Talhão</th><th className="text-right">Colhido</th><th>Produtividade</th>
                  <th className="text-right">Umidade</th><th className="text-right">Diesel</th>
                  <th className="text-right">Máquina/saca</th><th className="nao-imprimir" aria-label="Detalhe" />
                </tr>
              </thead>
              <tbody>
                {talhoes.map((t) => {
                  const chave = `${t.talhao_id}-${t.cultura}`;
                  const max = Math.max(...talhoes.map((x) => x.sc_ha ?? 0));
                  return (
                    <Fragment key={chave}>
                      <tr>
                        <td>
                          <div className="font-semibold">{nomeTalhao(t.talhao_nome)}</div>
                          <div className="text-xs text-folha-900/60">{ROTULO_CULTURA[t.cultura ?? ""] ?? t.cultura}{t.variedades.length ? ` · ${t.variedades.join(", ")}` : ""}</div>
                        </td>
                        <td className="text-right">{num(t.area_colhida_ha, 1)} ha<div className="text-xs text-folha-900/60">{num(t.sacas, 0)} sc</div></td>
                        <td className="min-w-[220px]">
                          <div className="flex items-center gap-2">
                            <span className="w-16 font-display font-bold">{num(t.sc_ha, 1)}</span>
                            <div className="h-2 flex-1 rounded-full bg-white/5"><div className="h-2 rounded-full" style={{ width: `${(100 * (t.sc_ha ?? 0)) / max}%`, background: corRelativa(t.vs_media_pct) }} /></div>
                            {t.vs_media_pct != null && <Selo tom={t.vs_media_pct >= 0 ? "ok" : t.vs_media_pct <= -15 ? "alto" : "atencao"}>{t.vs_media_pct >= 0 ? "+" : ""}{num(t.vs_media_pct, 0)}%</Selo>}
                          </div>
                        </td>
                        <td className="text-right">{pct(t.umidade_pct, 1)}</td>
                        <td className="text-right">{num(t.l_ha, 1)} L/ha<div className="text-xs text-folha-900/60">{rs(t.custo_diesel_rs)}</div></td>
                        <td className="text-right font-semibold">{rs(t.sacas ? custoMaquina(t) / t.sacas : null)}</td>
                        <td className="nao-imprimir text-right">
                          <button className="rounded-lg p-1.5 text-folha-900/60 hover:bg-white/10" aria-expanded={aberto === chave}
                            aria-label={`Operações em ${nomeTalhao(t.talhao_nome)}`} onClick={() => setAberto(aberto === chave ? null : chave)}>
                            <ChevronDown size={18} className={`transition ${aberto === chave ? "rotate-180" : ""}`} />
                          </button>
                        </td>
                      </tr>
                      {aberto === chave && <DetalheTalhao t={t} custoHora={custoHora} />}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
            <p className="px-5 py-4 text-xs text-folha-900/55">
              Produtividade em massa seca na umidade de venda (soja e milho 14 %, trigo 13 %), sobre a área colhida com a plataforma abaixada.
              O custo de máquina soma todas as operações no talhão desde a colheita anterior (plantio, aplicações e colheita).
            </p>
          </section>
        </div>
      )}
    </div>
  );
}

function DetalheTalhao({ t, custoHora }: { t: TalhaoFechamento; custoHora: number }) {
  return (
    <tr>
      <td colSpan={7} className="!bg-white/[0.03]">
        <div className="flex flex-wrap items-start gap-6 py-1 text-sm">
          <div className="text-folha-900/70">
            <Sprout size={14} className="mr-1 inline" aria-hidden="true" />
            Ciclo considerado: {new Date(`${t.janela_inicio}T12:00:00`).toLocaleDateString("pt-BR")} até{" "}
            {new Date(t.colheita_fim).toLocaleDateString("pt-BR")}
            {t.area_talhao_ha ? ` · talhão de ${num(t.area_talhao_ha, 1)} ha (${pct((100 * t.area_colhida_ha) / t.area_talhao_ha)} colhido)` : ""}
          </div>
          <ul className="flex flex-wrap gap-2">
            {t.operacoes_maquina.map((o) => (
              <li key={o.operacao} className="rounded-xl border border-white/10 bg-white/5 px-3 py-2">
                <div className="font-semibold">{ROTULO_OP[o.operacao] ?? o.operacao}</div>
                <div className="text-xs text-folha-900/65">
                  {horas(o.motor_h)} · {num(o.litros, 0)} L · {rs((o.custo_rs ?? 0) + (o.motor_h ?? 0) * custoHora)}
                  {o.maquinas > 1 ? ` · ${o.maquinas} máquinas` : ""}
                </div>
              </li>
            ))}
            {!t.operacoes_maquina.length && <li className="text-folha-900/60">Sem operação de máquina registrada no talhão.</li>}
          </ul>
        </div>
      </td>
    </tr>
  );
}

function Grande({ rotulo, valor, sub }: { rotulo: string; valor: string; sub: string }) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase tracking-wide text-folha-900/60">{rotulo}</div>
      <div className="mt-1 font-display text-3xl font-extrabold">{valor}</div>
      <div className="text-sm text-folha-900/60">{sub}</div>
    </div>
  );
}

const TOM = {
  broto: "bg-broto-500/15 text-broto-300 ring-broto-400/25",
  rosa: "bg-rose-400/15 text-rose-300 ring-rose-400/25",
  trigo: "bg-trigo-400/15 text-trigo-300 ring-trigo-400/25",
};

function Destaque({ icone: Icone, tom, titulo, texto }: { icone: typeof Coins; tom: keyof typeof TOM; titulo: string; texto: string }) {
  return (
    <div className="cartao flex gap-3 p-4">
      <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ring-1 ${TOM[tom]}`}><Icone size={18} aria-hidden="true" /></span>
      <div>
        <div className="font-semibold">{titulo}</div>
        <p className="text-sm text-folha-900/70">{texto}</p>
      </div>
    </div>
  );
}
