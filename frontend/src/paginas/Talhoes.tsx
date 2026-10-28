import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Upload } from "lucide-react";
import { useState } from "react";

import { Mapa } from "../componentes/Mapa";
import { Cabecalho, Carregando, Erro, Selo, Vazio } from "../componentes/ui";
import { useSessao } from "../contextos/Sessao";
import { api, comParams, orgAtiva } from "../lib/api";
import { useContornos, useTalhoes } from "../lib/consultas";
import { num } from "../lib/formato";
import { supabase } from "../lib/supabase";

const ORIGEM: Record<string, string> = { monitor: "do monitor", upload: "arquivo enviado", desenho: "desenhado" };

export default function Talhoes() {
  const lista = useTalhoes();
  const contornos = useContornos();
  const { papel } = useSessao();
  const podeEditar = papel === "owner" || papel === "gestor";
  const qc = useQueryClient();
  const [novo, setNovo] = useState("");

  const criar = useMutation({
    mutationFn: () => api("/talhoes", { metodo: "POST", corpo: { nome: novo } }),
    onSuccess: () => { setNovo(""); qc.invalidateQueries({ queryKey: ["talhoes"] }); },
  });
  const enviarContorno = useMutation({
    mutationFn: async ({ id, arquivo }: { id: string; arquivo: File }) => {
      const { data } = await supabase.auth.getSession();
      const form = new FormData();
      form.append("arquivo", arquivo);
      const resp = await fetch(comParams(`/talhoes/${id}/contorno/arquivo`), {
        method: "PUT",
        body: form,
        headers: { Authorization: `Bearer ${data.session?.access_token}`, "X-Organizacao-Id": orgAtiva.get() ?? "" },
      });
      if (!resp.ok) throw new Error((await resp.json()).detail ?? "Falha ao enviar contorno");
    },
    onSuccess: () => qc.invalidateQueries(),
  });

  const comContorno = (lista.data ?? []).filter((t) => t.tem_contorno).length;

  return (
    <>
      <Cabecalho
        titulo="Talhões"
        sub={`${lista.data?.length ?? 0} talhões · ${comContorno} com contorno. Sem contorno, a operação não é localizada por GPS.`}
      />
      {podeEditar && (
        <form className="mb-6 flex max-w-md gap-2" onSubmit={(e) => { e.preventDefault(); criar.mutate(); }}>
          <input className="campo" placeholder="Nome do novo talhão" value={novo} onChange={(e) => setNovo(e.target.value)} required />
          <button className="btn-primario whitespace-nowrap" disabled={criar.isPending}><Plus size={16} /> Criar</button>
        </form>
      )}
      {(criar.error || enviarContorno.error) && <div className="mb-4"><Erro erro={criar.error ?? enviarContorno.error} /></div>}

      {lista.isLoading ? <Carregando /> : !lista.data?.length ? (
        <Vazio titulo="Nenhum talhão ainda" texto="Envie o .zip do pendrive com a pasta Gen4: os talhões e contornos do monitor são importados automaticamente." />
      ) : (
        <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
          <div className="cartao overflow-hidden">
            <table className="tabela w-full">
              <thead><tr><th>Talhão</th><th className="text-right">Área</th><th>Contorno</th><th /></tr></thead>
              <tbody>
                {lista.data.map((t) => (
                  <tr key={t.id}>
                    <td className="font-semibold">{t.nome}</td>
                    <td className="text-right">{t.area_ha ? `${num(t.area_ha, 1)} ha` : "—"}</td>
                    <td>{t.tem_contorno ? <Selo tom="ok">{ORIGEM[t.origem_contorno ?? ""] ?? "sim"}</Selo> : <Selo tom="atencao">sem contorno</Selo>}</td>
                    <td className="text-right">
                      {podeEditar && (
                        <label className="btn-secundario cursor-pointer px-3 py-1.5 text-xs" title="Enviar .gjson do monitor ou .geojson">
                          <Upload size={14} /> {t.tem_contorno ? "Trocar" : "Enviar"}
                          <input type="file" accept=".gjson,.geojson,.json" className="hidden"
                            onChange={(e) => e.target.files?.[0] && enviarContorno.mutate({ id: t.id, arquivo: e.target.files[0] })} />
                        </label>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="cartao p-2">
            <Mapa className="h-[60vh] min-h-[360px]" camadas={{ talhoes: contornos.dados }} />
          </div>
        </div>
      )}
    </>
  );
}
