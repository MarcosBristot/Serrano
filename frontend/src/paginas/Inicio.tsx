/** Resumo do produtor: o que aconteceu e o que fazer agora, em linguagem direta. */
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight, CheckCircle2, Clock, Coins, Fuel, LandPlot, Receipt, TriangleAlert, Upload, Wheat,
} from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { SeletorPeriodo } from "../componentes/Layout";
import { Carregando, Erro, IconeMaquina, Medidor, TIPO_MAQUINA, Vazio } from "../componentes/ui";
import { usePeriodo, useSessao } from "../contextos/Sessao";
import { api } from "../lib/api";
import { ROTULO_TIPO_ALERTA, haQuanto, horas, nomeMaquina, nomeTalhao, num, pct, rs } from "../lib/formato";
import type { Alerta, ItemRanking, Jornada, MaquinaVisao, Pagina, Resumo } from "../lib/tipos";

function saudacao(): string {
  const h = new Date().getHours();
  return h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite";
}

const hora = (iso: string) => new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
const dia = (iso: string) => new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });

interface Acao {
  tom: "alto" | "atencao" | "info";
  icone: typeof Coins;
  titulo: string;
  texto: string;
  link: string;
  botao: string;
}

export default function Inicio() {
  const { org } = useSessao();
  const { periodo } = usePeriodo();
  const f = { inicio: periodo.inicio, fim: periodo.fim };
  const resumo = useQuery({ queryKey: ["resumo", f], queryFn: () => api<Resumo>("/kpis/resumo", { params: f }) });
  const maquinas = useQuery({ queryKey: ["maquinas-visao", f], queryFn: () => api<MaquinaVisao[]>("/maquinas/visao", { params: f }) });
  const talhoes = useQuery({
    queryKey: ["ranking", "talhao", f],
    queryFn: () => api<ItemRanking[]>("/kpis/ranking", { params: { ...f, por: "talhao" } }),
  });
  const jornadas = useQuery({
    queryKey: ["jornadas", "ultimas", f],
    queryFn: () => api<Pagina<Jornada>>("/jornadas", { params: { ...f, limit: 40 } }),
  });
  const alertas = useQuery({
    queryKey: ["alertas", "abertos"],
    queryFn: () => api<Pagina<Alerta>>("/alerts", { params: { status: "aberto", limit: 50 } }),
  });

  if (resumo.isLoading) return <Carregando />;
  if (resumo.error) return <Erro erro={resumo.error} />;
  const r = resumo.data!;
  const frota = maquinas.data ?? [];
  const ativas = frota.filter((m) => m.motor_h > 0);
  const massaT = frota.reduce((s, m) => s + (m.massa_kg ?? 0), 0) / 1000;
  const aproveitamento = r.motor_h > 0 ? (100 * r.trabalho_h) / r.motor_h : null;

  // O que fazer agora: cada aviso diz o tamanho do problema e leva para onde resolver.
  const acoes: Acao[] = [];
  for (const m of ativas) {
    if ((m.ociosidade_pct ?? 0) >= 20 && m.motor_h >= 2) {
      acoes.push({
        tom: (m.ociosidade_pct ?? 0) >= 35 ? "alto" : "atencao",
        icone: Clock,
        titulo: `${nomeMaquina(m)} parada com motor ligado`,
        texto: `${pct(m.ociosidade_pct)} do tempo de motor sem andar: ${num(m.litros_ocioso, 0)} L${m.custo_ocioso_rs ? ` (${rs(m.custo_ocioso_rs)})` : ""} gastos à toa.`,
        link: `/maquinas/${m.id}`,
        botao: "Ver máquina",
      });
    }
  }
  const comArea = (talhoes.data ?? []).filter((t) => t.id && t.area_ha > 1 && t.rs_ha != null);
  if (comArea.length >= 2 && r.rs_ha) {
    const pior = [...comArea].sort((a, b) => (b.rs_ha ?? 0) - (a.rs_ha ?? 0))[0];
    const acima = ((pior.rs_ha ?? 0) / r.rs_ha - 1) * 100;
    if (acima >= 15) {
      acoes.push({
        tom: "atencao", icone: Coins,
        titulo: `${nomeTalhao(pior.nome)} está saindo mais caro`,
        texto: `Diesel a ${rs(pior.rs_ha)} por hectare, ${pct(acima)} acima da média da fazenda (${rs(r.rs_ha)}/ha).`,
        link: "/talhoes", botao: "Ver talhões",
      });
    }
  }
  // Alertas iguais da mesma máquina viram um aviso só ("3 vezes"), com o mais recente de exemplo.
  const grupos = new Map<string, Alerta[]>();
  for (const a of alertas.data?.itens ?? []) {
    const chave = `${a.serial}|${a.tipo}`;
    grupos.set(chave, [...(grupos.get(chave) ?? []), a]);
  }
  for (const lista of grupos.values()) {
    const a = lista[0];
    const m = frota.find((x) => x.serial === a.serial);
    const nome = a.apelido ?? (m ? nomeMaquina(m) : a.serial ? `Máquina …${a.serial.slice(-6)}` : "Frota");
    acoes.push({
      tom: lista.some((x) => x.severidade === "alto") ? "alto" : "atencao", icone: TriangleAlert,
      titulo: `${nome}: ${(ROTULO_TIPO_ALERTA[a.tipo] ?? "alerta").toLowerCase()}${lista.length > 1 ? ` (${lista.length} vezes)` : ""}`,
      texto: lista.length > 1 ? `Último: ${a.mensagem}` : a.mensagem, link: "/alertas", botao: "Ver alertas",
    });
  }
  const paradas = frota.filter((m) => m.motor_h === 0 && m.ultima_atividade);
  if (ativas.length && paradas.length) {
    acoes.push({
      tom: "info", icone: Upload,
      titulo: `${paradas.map(nomeMaquina).join(", ")} sem dados no período`,
      texto: "Se a máquina trabalhou, falta enviar o pendrive dela.",
      link: "/enviar", botao: "Enviar pendrive",
    });
  }
  if (r.dias_sem_preco > 0) {
    acoes.push({
      tom: "info", icone: Receipt, titulo: "Preço do diesel faltando",
      texto: `${r.dias_sem_preco} dia(s) com trabalho sem preço cadastrado: o custo fica incompleto.`,
      link: "/configuracoes", botao: "Cadastrar preço",
    });
  }
  const ordem = { alto: 0, atencao: 1, info: 2 };
  acoes.sort((a, b) => ordem[a.tom] - ordem[b.tom]);

  return (
    <>
      <section className="cartao-destaque relative mb-6 overflow-hidden p-6 sm:p-8">
        <div className="pointer-events-none absolute -right-10 -top-16 h-56 w-56 rounded-full bg-broto-500/20 blur-3xl" aria-hidden="true" />
        <div className="relative flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-semibold text-broto-300">{saudacao()} 👋</p>
            <h1 className="mt-1 text-3xl font-extrabold sm:text-4xl">{org?.nome}</h1>
            {r.sessoes > 0 && (
              <p className="mt-3 max-w-2xl text-folha-900/80">
                No período, as máquinas trabalharam <b className="text-folha-950">{horas(r.trabalho_h)}</b>, gastaram{" "}
                <b className="text-folha-950">{rs(r.custo_rs)}</b> em diesel e cobriram{" "}
                <b className="text-folha-950">{num(r.area_ha, 0)} ha</b>
                {massaT > 0 && <>, colhendo <b className="text-folha-950">{num(massaT, 0)} t</b></>}.
              </p>
            )}
          </div>
          <SeletorPeriodo opcoes={["30d", "safra", "12m", "tudo"]} />
        </div>
      </section>

      {r.sessoes === 0 ? (
        <Vazio titulo="Nada registrado neste período" texto="Troque o período ou envie o pendrive do monitor."
          acao={<Link to="/enviar" className="btn-primario">Enviar pendrive</Link>} />
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Numero icone={Fuel} rotulo="Gasto com diesel" valor={rs(r.custo_rs)} detalhe={`${num(r.litros, 0)} litros`} />
            <Numero icone={Clock} rotulo="Horas trabalhando" valor={horas(r.trabalho_h)} detalhe={`+ ${horas(r.ocioso_h)} parado com motor ligado`} />
            <Numero icone={LandPlot} rotulo="Área trabalhada" valor={`${num(r.area_ha, 0)} ha`} detalhe={`${rs(r.rs_ha)} de diesel por hectare`} />
            {massaT > 0 ? (
              <Numero icone={Wheat} rotulo="Colhido" valor={`${num(massaT, 0)} t`} detalhe="massa úmida na colheitadeira" tom="trigo" />
            ) : (
              <Numero icone={Coins} rotulo="Diesel por hectare" valor={`${num(r.l_ha, 1)} L`} detalhe="média de todas as operações" />
            )}
          </div>

          <div className="grid gap-6 xl:grid-cols-[1fr_320px]">
            <section className="cartao p-5" aria-labelledby="t-acoes">
              <h2 id="t-acoes" className="mb-1 text-lg font-bold">O que fazer agora</h2>
              <p className="mb-4 text-sm text-folha-900/60">O que mais pesa no bolso primeiro.</p>
              {acoes.length === 0 ? (
                <p className="flex items-center gap-2 rounded-xl bg-broto-500/10 px-4 py-3 text-broto-300">
                  <CheckCircle2 size={18} aria-hidden="true" /> Nada fora do normal no período. Bom trabalho!
                </p>
              ) : (
                <ul className="space-y-2.5">
                  {acoes.slice(0, 5).map((a, i) => <ItemAcao key={i} acao={a} />)}
                </ul>
              )}
            </section>

            <section className="cartao flex flex-col items-center justify-center gap-4 p-5" aria-label="Aproveitamento do motor">
              <Medidor valor={aproveitamento} rotulo="Aproveitamento do motor" sub="tempo de motor andando e trabalhando" />
              <div className="grid w-full grid-cols-2 gap-2 text-center text-xs">
                <div className="rounded-xl bg-white/5 p-2"><div className="text-folha-900/60">Trabalhando</div><div className="font-display text-base font-bold">{horas(r.trabalho_h)}</div></div>
                <div className="rounded-xl bg-white/5 p-2"><div className="text-folha-900/60">Parado ligado</div><div className="font-display text-base font-bold text-trigo-300">{horas(r.ocioso_h)}</div></div>
              </div>
            </section>
          </div>

          <section aria-labelledby="t-maquinas">
            <div className="mb-3 flex items-baseline justify-between">
              <h2 id="t-maquinas" className="text-lg font-bold">Suas máquinas</h2>
              <Link to="/maquinas" className="text-sm font-semibold text-broto-300 hover:text-broto-200">ver detalhes →</Link>
            </div>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {frota.map((m) => <CartaoMaquina key={m.id} m={m} />)}
            </div>
          </section>

          <div className="grid gap-6 xl:grid-cols-2">
            <section className="cartao p-5" aria-labelledby="t-talhoes">
              <h2 id="t-talhoes" className="mb-1 text-lg font-bold">Diesel por hectare em cada talhão</h2>
              <p className="mb-4 text-sm text-folha-900/60">Quanto custou trabalhar cada hectare.</p>
              <ul className="space-y-3">
                {[...comArea].sort((a, b) => (b.rs_ha ?? 0) - (a.rs_ha ?? 0)).slice(0, 8).map((t) => {
                  const maior = Math.max(...comArea.map((x) => x.rs_ha ?? 0));
                  const acima = r.rs_ha ? (t.rs_ha ?? 0) > r.rs_ha * 1.15 : false;
                  return (
                    <li key={t.id ?? t.nome}>
                      <div className="flex justify-between text-sm">
                        <span className="font-semibold">{nomeTalhao(t.nome)}</span>
                        <span>{rs(t.rs_ha)}/ha <span className="text-folha-900/50">· {num(t.area_ha, 0)} ha</span></span>
                      </div>
                      <div className="mt-1.5 h-2 rounded-full bg-white/5" aria-hidden="true">
                        <div className={`h-2 rounded-full ${acima ? "bg-trigo-400" : "bg-broto-500"}`} style={{ width: `${(100 * (t.rs_ha ?? 0)) / maior}%` }} />
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>

            <section className="cartao p-5" aria-labelledby="t-ultimos">
              <div className="mb-3 flex items-baseline justify-between">
                <h2 id="t-ultimos" className="text-lg font-bold">Últimos trabalhos</h2>
                <Link to="/jornadas" className="text-sm font-semibold text-broto-300 hover:text-broto-200">todos →</Link>
              </div>
              <ul className="divide-y divide-white/5">
                {/* Só o que foi trabalho de verdade; manobras curtas ficam em Detalhado > Operações. */}
                {(jornadas.data?.itens ?? []).filter((j) => j.motor_h >= 0.25 || j.area_ha >= 0.5).slice(0, 6).map((j) => {
                  const m = frota.find((x) => x.id === j.maquina_id);
                  return (
                    <li key={j.id}>
                      <Link to={`/jornadas/${j.id}`} className="flex items-center gap-3 rounded-xl px-1 py-3 hover:bg-white/[0.03]">
                        <IconeMaquina tipo={m?.tipo ?? "trator"} tamanho={16} />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate font-semibold">{m ? nomeMaquina(m) : j.apelido ?? j.serial} · {nomeTalhao(j.talhao_nome)}</span>
                          <span className="text-xs text-folha-900/60">{dia(j.inicio)}, {hora(j.inicio)}–{hora(j.fim)}</span>
                        </span>
                        <span className="text-right text-sm">
                          <span className="block font-semibold">{horas(j.motor_h)}</span>
                          <span className="text-xs text-folha-900/60">{num(j.litros, 0)} L · {num(j.area_ha, 1)} ha</span>
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </section>
          </div>
        </div>
      )}
    </>
  );
}

function Numero({ icone: Icone, rotulo, valor, detalhe, tom = "broto" }: {
  icone: typeof Coins; rotulo: string; valor: string; detalhe: ReactNode; tom?: "broto" | "trigo";
}) {
  const cor = tom === "trigo" ? "bg-trigo-400/15 text-trigo-300 ring-trigo-400/25" : "bg-broto-500/15 text-broto-300 ring-broto-400/25";
  return (
    <div className="cartao p-5">
      <div className="flex items-center gap-2 text-sm font-semibold text-folha-900/70">
        <span className={`grid h-9 w-9 place-items-center rounded-xl ring-1 ${cor}`}><Icone size={18} aria-hidden="true" /></span>
        {rotulo}
      </div>
      <div className="mt-3 font-display text-3xl font-extrabold">{valor}</div>
      <div className="mt-1 text-sm text-folha-900/60">{detalhe}</div>
    </div>
  );
}

const TOM_ACAO = {
  alto: "border-rose-400/30 bg-rose-400/10 text-rose-300",
  atencao: "border-trigo-400/30 bg-trigo-400/10 text-trigo-300",
  info: "border-sky-400/25 bg-sky-400/10 text-sky-300",
};

function ItemAcao({ acao: a }: { acao: Acao }) {
  const Icone = a.icone;
  return (
    <li className="flex flex-wrap items-center gap-3 rounded-xl border border-white/10 bg-white/[0.03] p-3">
      <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl border ${TOM_ACAO[a.tom]}`}><Icone size={18} aria-hidden="true" /></span>
      <div className="min-w-0 flex-1">
        <div className="font-semibold">{a.titulo}</div>
        <div className="text-sm text-folha-900/70">{a.texto}</div>
      </div>
      <Link to={a.link} className="btn-secundario !py-2 text-xs">{a.botao} <ArrowRight size={14} aria-hidden="true" /></Link>
    </li>
  );
}

export function CartaoMaquina({ m }: { m: MaquinaVisao }) {
  const parada = m.motor_h === 0;
  return (
    <Link to={`/maquinas/${m.id}`} className="cartao group block p-5 transition hover:-translate-y-0.5 hover:border-broto-400/30">
      <div className="flex items-start gap-3">
        <IconeMaquina tipo={m.tipo} />
        <div className="min-w-0 flex-1">
          <div className="truncate font-display text-lg font-bold">{nomeMaquina(m)}</div>
          <div className="text-xs text-folha-900/60">
            {TIPO_MAQUINA[m.tipo]?.rotulo} · última vez {haQuanto(m.ultima_atividade)}
            {m.ultimo_talhao ? ` · ${nomeTalhao(m.ultimo_talhao)}` : ""}
          </div>
        </div>
        <ArrowRight size={18} className="mt-1 text-folha-900/40 transition group-hover:translate-x-0.5 group-hover:text-broto-300" aria-hidden="true" />
      </div>
      {parada ? (
        <p className="mt-4 rounded-xl bg-white/5 px-3 py-2 text-sm text-folha-900/60">Sem trabalho no período.</p>
      ) : (
        <>
          <dl className="mt-4 grid grid-cols-3 gap-2 text-center">
            <div className="rounded-xl bg-white/5 p-2"><dt className="text-[11px] text-folha-900/55">Motor</dt><dd className="font-display font-bold">{horas(m.motor_h)}</dd></div>
            <div className="rounded-xl bg-white/5 p-2"><dt className="text-[11px] text-folha-900/55">Diesel</dt><dd className="font-display font-bold">{num(m.litros, 0)} L</dd></div>
            {m.tipo === "colheitadeira" && m.massa_kg ? (
              <div className="rounded-xl bg-white/5 p-2"><dt className="text-[11px] text-folha-900/55">Colhido</dt><dd className="font-display font-bold text-trigo-300">{num(m.massa_kg / 1000, 0)} t</dd></div>
            ) : (
              <div className="rounded-xl bg-white/5 p-2"><dt className="text-[11px] text-folha-900/55">Área</dt><dd className="font-display font-bold">{num(m.area_ha, 0)} ha</dd></div>
            )}
          </dl>
          <div className="mt-3">
            <div className="flex justify-between text-xs text-folha-900/60">
              <span>Parada com motor ligado</span><span className={(m.ociosidade_pct ?? 0) >= 20 ? "font-semibold text-trigo-300" : ""}>{pct(m.ociosidade_pct)}</span>
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-white/5" aria-hidden="true">
              <div className={`h-1.5 rounded-full ${(m.ociosidade_pct ?? 0) >= 20 ? "bg-trigo-400" : "bg-broto-500"}`} style={{ width: `${Math.min(100, m.ociosidade_pct ?? 0)}%` }} />
            </div>
          </div>
        </>
      )}
    </Link>
  );
}
