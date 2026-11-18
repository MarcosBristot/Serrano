/** Saúde dos dados: o que chegou, o que foi descartado e por quê, e quanto dá para confiar nos números. */
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, FileX2, Layers, ScissorsLineDashed, ShieldCheck, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { SeletorPeriodo } from "../componentes/Layout";
import { Cabecalho, Carregando, Erro, Medidor, Selo } from "../componentes/ui";
import { usePeriodo } from "../contextos/Sessao";
import { api } from "../lib/api";
import { horas, num } from "../lib/formato";

interface Qualidade {
  fragmento_s: number;
  arquivos: { processados: number; vazios: number; com_erro: number; pacotes: number };
  sessoes: {
    total: number; fragmentos: number; sem_duracao: number; fragmentos_motor_h: number;
    motor_h: number; motor_h_confiavel: number; score_medio: number | null;
  };
  sobreposicao: { pares: number; minutos: number };
  problemas: { codigo: string; severidade: "info" | "atencao" | "alto"; sessoes: number }[];
  motivos_vazios: { motivo: string; arquivos: number }[];
  confiabilidade_pct: number | null;
}

/** O que cada problema quer dizer para o produtor e o que a Serrano fez com ele. */
const PROBLEMA: Record<string, { titulo: string; texto: string }> = {
  CANAIS_AUSENTES: {
    titulo: "Sensor sem leitura",
    texto: "O monitor não gravou algum sinal (vazão, RPM ou horímetro). Os números que dependem dele ficam em branco, nunca inventados.",
  },
  LACUNA_DE_DADOS: {
    titulo: "Buraco na gravação",
    texto: "O monitor parou de gravar por mais de 1 minuto no meio da operação. O trecho vazio não entra nas contas.",
  },
  VARIOS_TALHOES: {
    titulo: "Operação em mais de um talhão",
    texto: "A máquina passou por vários talhões no mesmo arquivo. Horas e diesel são repartidos ponto a ponto pelo GPS.",
  },
  SEM_GPS: { titulo: "Sem GPS", texto: "Sem posição, não há mapa nem talhão. A área vem da largura do implemento × distância." },
  MUITOS_DESCARTES: {
    titulo: "Muitas leituras impossíveis",
    texto: "Valores fora da faixa física (ex.: 300 L/h num trator) foram descartados antes do cálculo.",
  },
  HORIMETRO_DIVERGE: {
    titulo: "Horímetro não bate",
    texto: "O horímetro andou diferente do tempo de motor ligado. As horas e o consumo desse arquivo são marcados como não confiáveis.",
  },
  CONTADOR_DIVERGE: {
    titulo: "Contador de diesel não bate",
    texto: "O total do contador difere da vazão somada. Pode ser sensor ou lacuna: vale conferir no abastecimento.",
  },
};

const VAZIO: Record<string, string> = {
  sem_canais_do_trator: "Arquivo do monitor sem dados do trator (só tela, mapa ou configuração)",
  sem_blocos_de_dados: "Monitor ligado e desligado sem operar (arquivo só com cabeçalho)",
};

function Etapa({ icone, valor, rotulo, tom, children }: {
  icone: ReactNode; valor: string; rotulo: string; tom: "ok" | "info" | "atencao"; children?: ReactNode;
}) {
  const cor = { ok: "text-broto-300 bg-broto-500/15 ring-broto-400/25", info: "text-sky-300 bg-sky-400/15 ring-sky-400/25", atencao: "text-trigo-300 bg-trigo-400/15 ring-trigo-400/25" }[tom];
  return (
    <div className="cartao flex gap-4 p-4">
      <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ring-1 ${cor}`}>{icone}</span>
      <div className="min-w-0">
        <div className="font-display text-2xl font-extrabold text-folha-950">{valor}</div>
        <div className="text-sm font-semibold">{rotulo}</div>
        {children && <div className="mt-1 text-xs text-folha-900/60">{children}</div>}
      </div>
    </div>
  );
}

export default function Qualidade() {
  const { periodo } = usePeriodo();
  const f = { inicio: periodo.inicio, fim: periodo.fim };
  const q = useQuery({ queryKey: ["qualidade", f], queryFn: () => api<Qualidade>("/qualidade", { params: f }) });

  const cabecalho = (
    <Cabecalho
      titulo="Qualidade dos dados"
      sub="Antes de virar número, cada arquivo passa por checagens. Aqui está o que foi aproveitado, descartado ou corrigido."
      acoes={<SeletorPeriodo />}
    />
  );
  if (q.isLoading) return <>{cabecalho}<Carregando /></>;
  if (q.error) return <>{cabecalho}<Erro erro={q.error} /></>;
  const d = q.data!;
  const s = d.sessoes;
  const validas = s.total - s.fragmentos;
  const vazios = d.arquivos.vazios;
  const recebidos = d.arquivos.processados + vazios + d.arquivos.com_erro;

  return (
    <>
      {cabecalho}

      <section className="mb-6 grid gap-4 lg:grid-cols-[280px_1fr]">
        <div className="cartao-destaque flex flex-col items-center justify-center p-6 text-center">
          <Medidor valor={d.confiabilidade_pct} rotulo="Confiabilidade" sub="horas de motor com dado completo" tamanho={180} />
          <p className="mt-3 text-xs text-folha-900/60">
            {d.confiabilidade_pct == null
              ? "Ainda sem operações no período."
              : d.confiabilidade_pct >= 85
                ? "Dá para decidir com estes números."
                : "Parte das horas tem sensor faltando ou divergência: veja abaixo."}
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Etapa icone={<Layers size={20} />} valor={num(recebidos, 0)} rotulo="Arquivos lidos do pendrive" tom="info">
            Todos os arquivos enviados, de todos os pendrives (reenvio do mesmo arquivo é reconhecido e ignorado).
          </Etapa>
          <Etapa icone={<FileX2 size={20} />} valor={num(vazios, 0)} rotulo="Sem dado de operação, ignorados" tom="atencao">
            {d.motivos_vazios.map((m) => `${num(m.arquivos, 0)} · ${VAZIO[m.motivo] ?? m.motivo}`).join(" · ") || "Nenhum."}
          </Etapa>
          <Etapa icone={<ScissorsLineDashed size={20} />} valor={num(s.fragmentos, 0)} rotulo="Fragmentos e arquivos sem motor" tom="atencao">
            Menos de {d.fragmento_s / 60} min de gravação ou menos de 1 min de motor ligado ({num(s.sem_duracao, 0)} com duração zero).
            Ficam guardados, mas fora da lista e das médias.
          </Etapa>
          <Etapa icone={<CheckCircle2 size={20} />} valor={num(validas, 0)} rotulo="Operações aproveitadas" tom="ok">
            {s.score_medio != null ? <>Nota média de qualidade {num(s.score_medio, 0)}/100 · {horas(s.motor_h)} de motor</> : "—"}
          </Etapa>
        </div>
      </section>

      <section className="cartao mb-6 flex flex-wrap items-center gap-4 p-5">
        <span className="grid h-11 w-11 place-items-center rounded-xl bg-sky-400/15 text-sky-300 ring-1 ring-sky-400/25"><ShieldCheck size={20} /></span>
        <div className="min-w-0 flex-1">
          <div className="font-semibold">Duplicidade tratada</div>
          <p className="text-sm text-folha-900/60">
            {d.sobreposicao.pares > 0 ? (
              <>
                {num(d.sobreposicao.pares, 0)} vezes o monitor gravou o mesmo trecho em dois arquivos ({num(d.sobreposicao.minutos, 1)} min no total).
                A Serrano guarda um ponto por segundo por máquina, então esse trecho é somado <b className="text-folha-950">uma vez só</b>.
              </>
            ) : (
              "Nenhum trecho gravado em dois arquivos no período. Reenvio do mesmo pendrive também é reconhecido e não conta em dobro."
            )}
          </p>
        </div>
      </section>

      <h2 className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-folha-900/50">Pontos de atenção nas operações aproveitadas</h2>
      {d.problemas.length === 0 ? (
        <div className="cartao flex items-center gap-3 p-5 text-sm"><CheckCircle2 className="text-broto-400" size={18} /> Nenhum problema encontrado.</div>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {d.problemas.map((p) => {
            const info = PROBLEMA[p.codigo] ?? { titulo: p.codigo, texto: "" };
            return (
              <div key={p.codigo} className="cartao flex gap-4 p-4">
                <TriangleAlert size={18} className={`mt-0.5 shrink-0 ${p.severidade === "alto" ? "text-rose-300" : p.severidade === "atencao" ? "text-trigo-300" : "text-sky-300"}`} />
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold">{info.titulo}</span>
                    <Selo tom={p.severidade}>{num(p.sessoes, 0)} arquivo{p.sessoes === 1 ? "" : "s"}</Selo>
                  </div>
                  <p className="mt-1 text-sm text-folha-900/60">{info.texto}</p>
                </div>
              </div>
            );
          })}
        </div>
      )}
      <p className="mt-6 text-xs text-folha-900/50">
        Quer ver arquivo por arquivo? Abra <Link to="/sessoes" className="font-semibold text-broto-300 underline">Arquivos do monitor</Link>.
      </p>
    </>
  );
}
