import { useMutation } from "@tanstack/react-query";
import { ArrowRight, Fuel, Map, Sprout } from "lucide-react";
import { useState } from "react";

import { Marca } from "../componentes/Marca";
import { configuracaoOk, supabase } from "../lib/supabase";

export default function Login() {
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [aviso, setAviso] = useState<string | null>(null);

  const entrar = useMutation({
    mutationFn: async () => {
      const { error } = await supabase.auth.signInWithPassword({ email, password: senha });
      if (error) throw new Error(error.message === "Invalid login credentials" ? "E-mail ou senha incorretos." : error.message);
    },
  });

  const recuperar = async () => {
    if (!email) return setAviso("Digite seu e-mail acima para receber o link.");
    const { error } = await supabase.auth.resetPasswordForEmail(email, { redirectTo: window.location.origin });
    setAviso(error ? error.message : "Enviamos um link de redefinição para o seu e-mail.");
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <section className="fundo-lavoura relative hidden flex-col justify-between overflow-hidden p-12 text-white lg:flex">
        <div className="flex items-center gap-3">
          <Marca tamanho={28} />
        </div>
        <div className="max-w-lg">
          <h1 className="font-display text-5xl font-extrabold leading-[1.05]">
            Sua frota no campo,<br /><span className="text-trigo-300">em números claros.</span>
          </h1>
          <p className="mt-5 text-lg text-folha-100/80">
            Do pendrive do monitor ao painel: horas, diesel, área trabalhada e alertas de cada máquina e talhão.
          </p>
          <div className="mt-10 grid grid-cols-3 gap-4">
            {[
              { i: Fuel, t: "L/ha por talhão" },
              { i: Map, t: "Trajeto e cobertura" },
              { i: Sprout, t: "Safra a safra" },
            ].map(({ i: I, t }) => (
              <div key={t} className="rounded-2xl bg-white/10 p-4 backdrop-blur">
                <I className="text-trigo-300" />
                <div className="mt-2 text-sm font-semibold">{t}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="text-xs text-folha-100/50">Passo Fundo · RS</div>
      </section>

      <section className="flex items-center justify-center px-6 py-12">
        <form
          className="w-full max-w-sm"
          onSubmit={(e) => {
            e.preventDefault();
            entrar.mutate();
          }}
        >
          <div className="mb-8 lg:hidden">
            <Marca tamanho={30} className="text-folha-950" />
          </div>
          <h2 className="text-2xl font-extrabold">Entrar</h2>
          <p className="mt-1 text-sm text-folha-900/60">Use o e-mail cadastrado pela sua fazenda.</p>

          {!configuracaoOk && (
            <div className="mt-6 rounded-xl bg-trigo-50 p-3 text-sm text-trigo-800">
              Configure <code>VITE_SUPABASE_URL</code> e <code>VITE_SUPABASE_PUBLISHABLE_KEY</code> em <code>frontend/.env.local</code>.
            </div>
          )}

          <div className="mt-8 space-y-4">
            <div>
              <label className="rotulo" htmlFor="email">E-mail</label>
              <input id="email" type="email" autoComplete="email" required className="campo" value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div>
              <label className="rotulo" htmlFor="senha">Senha</label>
              <input id="senha" type="password" autoComplete="current-password" required className="campo" value={senha} onChange={(e) => setSenha(e.target.value)} />
            </div>
          </div>

          {entrar.error && <p className="mt-4 text-sm font-medium text-rose-700">{(entrar.error as Error).message}</p>}
          {aviso && <p className="mt-4 text-sm text-folha-700">{aviso}</p>}

          <button type="submit" className="btn-primario mt-6 w-full" disabled={entrar.isPending || !configuracaoOk}>
            {entrar.isPending ? "Entrando…" : "Entrar"} <ArrowRight size={16} />
          </button>
          <button type="button" onClick={recuperar} className="mt-4 w-full text-center text-sm font-medium text-folha-700 hover:underline">
            Esqueci minha senha
          </button>
        </form>
      </section>
    </div>
  );
}
