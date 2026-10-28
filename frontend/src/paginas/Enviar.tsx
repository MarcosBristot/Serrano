import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CircleAlert, FileArchive, Loader2, UploadCloud } from "lucide-react";
import { useRef, useState } from "react";

import { Cabecalho } from "../componentes/ui";
import { api, enviarArquivo, ErroApi } from "../lib/api";
import type { Job } from "../lib/tipos";

interface Item {
  chave: string;
  nome: string;
  tamanho: number;
  progresso: number;
  estado: "enviando" | "processando" | "pronto" | "duplicado" | "erro";
  mensagem?: string;
}

const MB = 1024 * 1024;

export default function Enviar() {
  const [itens, setItens] = useState<Item[]>([]);
  const [arrastando, setArrastando] = useState(false);
  const entrada = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();

  const atualizar = (chave: string, p: Partial<Item>) =>
    setItens((xs) => xs.map((x) => (x.chave === chave ? { ...x, ...p } : x)));

  async function acompanhar(chave: string, jobId: string) {
    for (let i = 0; i < 600; i++) {
      await new Promise((r) => setTimeout(r, 3000));
      const j = await api<Job>(`/jobs/${jobId}`).catch(() => null);
      if (!j) continue;
      if (j.status === "concluido") {
        const r = j.progresso.resultado ?? {};
        const st = String(r.status ?? "");
        const msg =
          st === "vazio" ? "Arquivo sem dados do trator (normal: o monitor grava muitos arquivos vazios)."
          : st === "rejeitado" ? `Arquivo rejeitado: ${String(r.motivo ?? "")}`
          : st === "bloqueado_plano" ? "Máquina acima do limite do plano."
          : "jdl" in r ? `${r.jdl} arquivos .jdl no zip, processando em seguida.`
          : `Processado · qualidade ${String(r.qualidade ?? "—")} · ${String(r.alertas ?? 0)} alerta(s).`;
        atualizar(chave, { estado: st === "rejeitado" ? "erro" : "pronto", mensagem: msg, progresso: 1 });
        qc.invalidateQueries();
        return;
      }
      if (j.status === "morto" || j.status === "cancelado") {
        atualizar(chave, { estado: "erro", mensagem: j.erro ?? j.status });
        return;
      }
    }
  }

  async function enviar(arquivos: FileList | File[]) {
    for (const arquivo of Array.from(arquivos)) {
      const chave = `${arquivo.name}-${arquivo.size}-${Date.now()}`;
      setItens((xs) => [{ chave, nome: arquivo.name, tamanho: arquivo.size, progresso: 0, estado: "enviando" }, ...xs]);
      try {
        const r = await enviarArquivo(arquivo, {}, (p) => atualizar(chave, { progresso: p }));
        if (r.duplicado) {
          atualizar(chave, { estado: "duplicado", progresso: 1, mensagem: "Este arquivo já tinha sido enviado." });
        } else {
          atualizar(chave, { estado: "processando", progresso: 1, mensagem: "Na fila de processamento…" });
          if (r.job_id) void acompanhar(chave, r.job_id);
        }
      } catch (e) {
        atualizar(chave, { estado: "erro", mensagem: e instanceof ErroApi ? e.message : "Falha no envio" });
      }
    }
  }

  return (
    <>
      <Cabecalho titulo="Enviar pendrive" sub="Arraste os arquivos .jdl da pasta JD-Data/log, ou o .zip do pendrive inteiro (com a pasta Gen4 vêm os talhões)." />
      <div
        onDragOver={(e) => { e.preventDefault(); setArrastando(true); }}
        onDragLeave={() => setArrastando(false)}
        onDrop={(e) => { e.preventDefault(); setArrastando(false); void enviar(e.dataTransfer.files); }}
        onClick={() => entrada.current?.click()}
        className={`cartao flex cursor-pointer flex-col items-center border-2 border-dashed px-6 py-14 text-center transition ${arrastando ? "border-folha-500 bg-folha-50" : "border-folha-900/15 hover:border-folha-400"}`}
      >
        <div className="grid h-16 w-16 place-items-center rounded-2xl bg-folha-700 text-white shadow-lg"><UploadCloud size={30} /></div>
        <h3 className="mt-4 text-lg font-bold">Solte os arquivos aqui</h3>
        <p className="mt-1 text-sm text-folha-900/60">ou clique para escolher · .jdl e .zip · o processamento continua mesmo se você sair da página</p>
        <input ref={entrada} type="file" multiple accept=".jdl,.zip" className="hidden" onChange={(e) => e.target.files && void enviar(e.target.files)} />
      </div>

      {itens.length > 0 && (
        <div className="mt-6 cartao divide-y divide-folha-900/5">
          {itens.map((i) => (
            <div key={i.chave} className="flex items-center gap-4 p-4">
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-folha-50 text-folha-700"><FileArchive size={20} /></div>
              <div className="min-w-0 flex-1">
                <div className="flex justify-between gap-2 text-sm">
                  <span className="truncate font-semibold">{i.nome}</span>
                  <span className="shrink-0 text-folha-900/50">{(i.tamanho / MB).toFixed(1).replace(".", ",")} MB</span>
                </div>
                {i.estado === "enviando" ? (
                  <div className="mt-2 h-2 rounded-full bg-folha-50"><div className="h-2 rounded-full bg-folha-600 transition-all" style={{ width: `${Math.round(i.progresso * 100)}%` }} /></div>
                ) : (
                  <p className={`mt-1 text-xs ${i.estado === "erro" ? "text-rose-700" : "text-folha-900/60"}`}>{i.mensagem}</p>
                )}
              </div>
              <div className="shrink-0">
                {i.estado === "enviando" && <span className="text-xs font-semibold text-folha-700">{Math.round(i.progresso * 100)}%</span>}
                {i.estado === "processando" && <Loader2 className="animate-spin text-trigo-600" size={20} />}
                {(i.estado === "pronto" || i.estado === "duplicado") && <CheckCircle2 className="text-folha-600" size={20} />}
                {i.estado === "erro" && <CircleAlert className="text-rose-600" size={20} />}
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
