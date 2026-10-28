/** Login (Supabase) + organização ativa + filtros globais de período. */
import type { Session } from "@supabase/supabase-js";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, orgAtiva } from "../lib/api";
import { isoDia } from "../lib/formato";
import { supabase } from "../lib/supabase";
import type { Me, Papel } from "../lib/tipos";

interface Ctx {
  sessao: Session | null;
  carregando: boolean;
  me: Me | undefined;
  org: Me["organizacoes"][number] | undefined;
  papel: Papel | undefined;
  trocarOrg: (id: string) => void;
  sair: () => Promise<void>;
}

const Contexto = createContext<Ctx | null>(null);

export function SessaoProvider({ children }: { children: ReactNode }) {
  const [sessao, setSessao] = useState<Session | null>(null);
  const [pronto, setPronto] = useState(false);
  const qc = useQueryClient();

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSessao(data.session);
      setPronto(true);
    });
    const { data } = supabase.auth.onAuthStateChange((_e, s) => setSessao(s));
    return () => data.subscription.unsubscribe();
  }, []);

  const me = useQuery({
    queryKey: ["me", sessao?.user.id],
    queryFn: () => api<Me>("/me"),
    enabled: Boolean(sessao),
  });

  const org = useMemo(() => {
    const lista = me.data?.organizacoes ?? [];
    return lista.find((o) => o.organizacao_id === orgAtiva.get()) ?? lista[0];
  }, [me.data]);

  useEffect(() => {
    if (org) orgAtiva.set(org.organizacao_id);
  }, [org]);

  const valor: Ctx = {
    sessao,
    carregando: !pronto || (Boolean(sessao) && me.isLoading),
    me: me.data,
    org,
    papel: org?.papel,
    trocarOrg: (id) => {
      orgAtiva.set(id);
      qc.invalidateQueries();
    },
    sair: async () => {
      orgAtiva.set(null);
      await supabase.auth.signOut();
      qc.clear();
    },
  };
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useSessao(): Ctx {
  const c = useContext(Contexto);
  if (!c) throw new Error("useSessao fora do SessaoProvider");
  return c;
}

// ------------------------------------------------------------------ filtros de período
export type Preset = "7d" | "30d" | "90d" | "safra" | "12m" | "tudo";
export interface Periodo {
  preset: Preset;
  inicio?: string;
  fim?: string;
}

export function periodoDe(preset: Preset, hoje = new Date()): Periodo {
  const menos = (dias: number) => isoDia(new Date(hoje.getTime() - dias * 86_400_000));
  switch (preset) {
    case "7d":
      return { preset, inicio: menos(6), fim: isoDia(hoje) };
    case "30d":
      return { preset, inicio: menos(29), fim: isoDia(hoje) };
    case "90d":
      return { preset, inicio: menos(89), fim: isoDia(hoje) };
    case "12m":
      return { preset, inicio: menos(364), fim: isoDia(hoje) };
    case "safra": {
      const ano = hoje.getMonth() >= 6 ? hoje.getFullYear() : hoje.getFullYear() - 1;
      return { preset, inicio: `${ano}-07-01`, fim: isoDia(hoje) };
    }
    default:
      return { preset: "tudo" };
  }
}

const CtxPeriodo = createContext<{ periodo: Periodo; setPreset: (p: Preset) => void } | null>(null);

export function PeriodoProvider({ children }: { children: ReactNode }) {
  const [periodo, setPeriodo] = useState<Periodo>(() => periodoDe("tudo"));
  return (
    <CtxPeriodo.Provider value={{ periodo, setPreset: (p) => setPeriodo(periodoDe(p)) }}>
      {children}
    </CtxPeriodo.Provider>
  );
}

export function usePeriodo() {
  const c = useContext(CtxPeriodo);
  if (!c) throw new Error("usePeriodo fora do PeriodoProvider");
  return c;
}
