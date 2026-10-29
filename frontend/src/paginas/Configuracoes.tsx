import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fuel, SlidersHorizontal, Users } from "lucide-react";
import { useEffect, useState } from "react";

import { Cabecalho, Carregando, Erro, Selo } from "../componentes/ui";
import { MeusDados } from "../componentes/MeusDados";
import { useSessao } from "../contextos/Sessao";
import { api } from "../lib/api";
import { data, rs } from "../lib/formato";
import type { Membro, Preco } from "../lib/tipos";

export default function Configuracoes() {
  const { papel } = useSessao();
  return (
    <>
      <Cabecalho titulo="Configurações" sub="Preço do diesel, limites dos alertas, equipe e privacidade." />
      <div className="grid gap-6 xl:grid-cols-2">
        <PrecoDiesel podeEditar={papel !== "leitor"} />
        <Regras podeEditar={papel !== "leitor"} />
        <Equipe podeAdministrar={papel === "owner"} />
        <MeusDados />
      </div>
    </>
  );
}

function Secao({ titulo, icone: Icone, children }: { titulo: string; icone: typeof Fuel; children: React.ReactNode }) {
  return (
    <section className="cartao p-6">
      <h2 className="mb-4 flex items-center gap-2 text-lg font-bold"><Icone size={20} className="text-folha-600" /> {titulo}</h2>
      {children}
    </section>
  );
}

function PrecoDiesel({ podeEditar }: { podeEditar: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["precos"], queryFn: () => api<Preco[]>("/precos-combustivel") });
  const [preco, setPreco] = useState("");
  const [desde, setDesde] = useState(new Date().toISOString().slice(0, 10));
  const salvar = useMutation({
    mutationFn: () => api("/precos-combustivel", { metodo: "POST", corpo: { preco_rs_l: Number(preco.replace(",", ".")), valido_de: desde } }),
    onSuccess: () => { setPreco(""); qc.invalidateQueries(); },
  });
  return (
    <Secao titulo="Preço do diesel (S10)" icone={Fuel}>
      <p className="mb-4 text-sm text-folha-900/60">Usado no custo e no R$/ha. Prefira o preço da nota fiscal; o padrão é a média ANP do RS.</p>
      {q.isLoading ? <Carregando /> : (
        <ul className="mb-4 divide-y divide-folha-900/5 text-sm">
          {q.data?.map((p) => (
            <li key={p.id} className="flex items-center justify-between py-2">
              <span>{data(p.valido_de)} → {p.valido_ate ? data(p.valido_ate) : "hoje"}</span>
              <span className="flex items-center gap-2 font-semibold">{rs(p.preco_rs_l)}/L <Selo>{p.fonte}</Selo></span>
            </li>
          ))}
        </ul>
      )}
      {podeEditar && (
        <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); salvar.mutate(); }}>
          <div><label className="rotulo">R$/L</label><input className="campo w-28" inputMode="decimal" value={preco} onChange={(e) => setPreco(e.target.value)} placeholder="6,20" required /></div>
          <div><label className="rotulo">A partir de</label><input type="date" className="campo" value={desde} onChange={(e) => setDesde(e.target.value)} required /></div>
          <button className="btn-primario" disabled={salvar.isPending}>Salvar</button>
        </form>
      )}
      {salvar.error && <div className="mt-3"><Erro erro={salvar.error} /></div>}
    </Secao>
  );
}

type RegrasT = Record<string, number | string>;
const CAMPOS: { k: string; rotulo: string; ajuda: string }[] = [
  { k: "ociosidade_min_minutos", rotulo: "Ociosidade (min)", ajuda: "motor ligado e parado por mais que isso" },
  { k: "vazao_desvio", rotulo: "Consumo acima do normal (fração)", ajuda: "0,30 = 30% acima da média da máquina" },
  { k: "l_ha_desvio", rotulo: "L/ha acima do normal (fração)", ajuda: "comparado ao histórico do mesmo implemento" },
  { k: "gps_velocidade_max_kmh", rotulo: "Salto de GPS (km/h)", ajuda: "velocidade impossível entre posições" },
];

function Regras({ podeEditar }: { podeEditar: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["regras"], queryFn: () => api<RegrasT>("/config/regras") });
  const [form, setForm] = useState<RegrasT>({});
  useEffect(() => { if (q.data) setForm(q.data); }, [q.data]);
  const salvar = useMutation({
    mutationFn: () => {
      const { versao: _v, ...corpo } = form;
      return api("/config/regras", { metodo: "PUT", corpo });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["regras"] }),
  });
  const reanalisar = useMutation({ mutationFn: () => api<{ sessoes_reenfileiradas: number }>("/analysis/run", { metodo: "POST" }) });
  return (
    <Secao titulo="Limites dos alertas" icone={SlidersHorizontal}>
      {q.isLoading ? <Carregando /> : (
        <form onSubmit={(e) => { e.preventDefault(); salvar.mutate(); }} className="space-y-4">
          {CAMPOS.map((c) => (
            <div key={c.k}>
              <label className="rotulo">{c.rotulo}</label>
              <input className="campo" type="number" step="any" disabled={!podeEditar} value={form[c.k] ?? ""}
                onChange={(e) => setForm({ ...form, [c.k]: Number(e.target.value) })} />
              <p className="mt-1 text-xs text-folha-900/50">{c.ajuda}</p>
            </div>
          ))}
          {podeEditar && (
            <div className="flex flex-wrap gap-2">
              <button className="btn-primario" disabled={salvar.isPending}>Salvar limites</button>
              <button type="button" className="btn-secundario" disabled={reanalisar.isPending} onClick={() => reanalisar.mutate()}>Reaplicar ao histórico</button>
            </div>
          )}
          {salvar.isSuccess && <p className="text-xs text-folha-700">Salvo. Vale para os próximos arquivos.</p>}
          {reanalisar.data && <p className="text-xs text-folha-700">{reanalisar.data.sessoes_reenfileiradas} operações sendo reprocessadas.</p>}
          {(salvar.error || reanalisar.error) && <Erro erro={salvar.error ?? reanalisar.error} />}
        </form>
      )}
    </Secao>
  );
}

function Equipe({ podeAdministrar }: { podeAdministrar: boolean }) {
  const qc = useQueryClient();
  const membros = useQuery({ queryKey: ["membros"], queryFn: () => api<Membro[]>("/membros") });
  const [email, setEmail] = useState("");
  const [papel, setPapel] = useState("leitor");
  const convidar = useMutation({
    mutationFn: () => api<{ token: string; email_enviado: boolean }>("/convites", { metodo: "POST", corpo: { email, papel } }),
    onSuccess: () => { setEmail(""); qc.invalidateQueries({ queryKey: ["membros"] }); },
  });
  const link = convidar.data ? `${window.location.origin}/convite?token=${convidar.data.token}` : null;
  return (
    <Secao titulo="Equipe" icone={Users}>
      <ul className="mb-4 divide-y divide-folha-900/5 text-sm">
        {membros.data?.map((m) => (
          <li key={m.usuario_id} className="flex items-center justify-between py-2">
            <span>{m.email ?? m.usuario_id}</span>
            <Selo tom={m.papel === "owner" ? "ok" : "neutro"}>{{ owner: "dono", gestor: "gestor", leitor: "leitura" }[m.papel]}</Selo>
          </li>
        ))}
      </ul>
      {podeAdministrar && (
        <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); convidar.mutate(); }}>
          <div className="min-w-[200px] flex-1"><label className="rotulo">Convidar e-mail</label><input className="campo" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></div>
          <div><label className="rotulo">Papel</label>
            <select className="campo" value={papel} onChange={(e) => setPapel(e.target.value)}>
              <option value="leitor">Leitura</option><option value="gestor">Gestor</option>
            </select>
          </div>
          <button className="btn-primario" disabled={convidar.isPending}>Convidar</button>
        </form>
      )}
      {link && (
        <div className="mt-4 rounded-xl bg-folha-50 p-3 text-xs">
          {convidar.data?.email_enviado ? "Convite enviado por e-mail." : "Envie este link para a pessoa (vale 7 dias):"}
          <div className="mt-1 break-all font-mono">{link}</div>
        </div>
      )}
      {convidar.error && <div className="mt-3"><Erro erro={convidar.error} /></div>}
    </Secao>
  );
}
