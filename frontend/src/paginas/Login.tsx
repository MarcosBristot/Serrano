import { useMutation } from "@tanstack/react-query";
import { ArrowRight, Fuel, MailCheck, Map, Sprout } from "lucide-react";
import { useState } from "react";

import { Marca } from "../componentes/Marca";
import { LINKS_LEGAIS } from "../lib/legal";
import { configuracaoOk, supabase } from "../lib/supabase";

type Modo = "entrar" | "criar";

const MENSAGENS: Record<string, string> = {
  "Invalid login credentials": "E-mail ou senha incorretos.",
  "Email not confirmed": "Confirme o seu e-mail pelo link que enviamos antes de entrar.",
  "User already registered": "Este e-mail já tem conta. Use a aba Entrar.",
};

function traduzir(msg: string) {
  return MENSAGENS[msg] ?? msg;
}

/** Entrada e cadastro. ?cadastro na URL (vindo da landing) abre direto em "Criar conta". */
export default function Login() {
  const [modo, setModo] = useState<Modo>(() => (new URLSearchParams(window.location.search).has("cadastro") ? "criar" : "entrar"));
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [aviso, setAviso] = useState<string | null>(null);
  const [confirmar, setConfirmar] = useState(false);

  const enviar = useMutation({
    mutationFn: async () => {
      if (modo === "entrar") {
        const { error } = await supabase.auth.signInWithPassword({ email, password: senha });
        if (error) throw new Error(traduzir(error.message));
        return;
      }
      const { data, error } = await supabase.auth.signUp({
        email,
        password: senha,
        options: { emailRedirectTo: window.location.origin },
      });
      if (error) throw new Error(traduzir(error.message));
      // Com confirmação de e-mail ligada no Supabase não vem sessão: avisa e espera o clique no link.
      if (!data.session) setConfirmar(true);
    },
  });

  const recuperar = async () => {
    if (!email) return setAviso("Digite seu e-mail acima para receber o link.");
    const { error } = await supabase.auth.resetPasswordForEmail(email, { redirectTo: window.location.origin });
    setAviso(error ? error.message : "Enviamos um link de redefinição para o seu e-mail.");
  };

  const trocar = (m: Modo) => {
    setModo(m);
    setAviso(null);
    enviar.reset();
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <section className="fundo-lavoura relative hidden flex-col justify-between overflow-hidden p-12 lg:flex xl:p-16">
        <Marca tamanho={28} className="text-white" />
        <div className="max-w-xl">
          <h1 className="font-display text-5xl font-extrabold leading-[1.05] text-white xl:text-6xl">
            Sua frota no campo,
            <br />
            <span className="text-trigo-300">em números claros.</span>
          </h1>
          <p className="mt-6 max-w-md text-lg leading-relaxed text-white/75">
            Do pendrive do monitor ao painel: horas, diesel, área trabalhada e alertas de cada máquina e talhão.
          </p>
          <div className="mt-10 grid max-w-lg grid-cols-3 gap-3">
            {[
              { i: Fuel, t: "L/ha por talhão" },
              { i: Map, t: "Trajeto e cobertura" },
              { i: Sprout, t: "Safra a safra" },
            ].map(({ i: I, t }) => (
              <div key={t} className="rounded-2xl border border-white/10 bg-black/25 p-4 backdrop-blur">
                <I size={20} className="text-trigo-300" aria-hidden="true" />
                <div className="mt-2 text-sm font-semibold text-white">{t}</div>
              </div>
            ))}
          </div>
        </div>
        <p className="text-xs text-white/50">John Deere, ISOBUS e mais monitores no mesmo painel.</p>
      </section>

      <section className="flex items-center justify-center px-5 py-10 sm:px-8">
        <div className="w-full max-w-sm">
          <div className="mb-8 lg:hidden">
            <Marca tamanho={30} className="text-white" />
            <p className="mt-3 text-sm text-white/70">Sua frota no campo, em números claros.</p>
          </div>

          <div className="cartao p-6 sm:p-7">
            {confirmar ? (
              <div className="text-center">
                <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-broto-500/15 text-broto-300">
                  <MailCheck aria-hidden="true" />
                </div>
                <h2 className="mt-4 text-xl font-extrabold">Confirme o seu e-mail</h2>
                <p className="mt-2 text-sm text-white/70">
                  Enviamos um link para <b className="text-white">{email}</b>. Clique nele para ativar a conta e voltar para cá.
                </p>
                <button className="btn-secundario mt-6 w-full" onClick={() => { setConfirmar(false); trocar("entrar"); }}>
                  Já confirmei, entrar
                </button>
              </div>
            ) : (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  enviar.mutate();
                }}
              >
                <div className="grid grid-cols-2 gap-1 rounded-xl bg-black/25 p-1" role="tablist">
                  {(["entrar", "criar"] as const).map((m) => (
                    <button key={m} type="button" role="tab" aria-selected={modo === m} onClick={() => trocar(m)}
                      className={`rounded-lg py-2 text-sm font-semibold transition ${modo === m ? "bg-broto-500 text-noite-950" : "text-white/70 hover:text-white"}`}>
                      {m === "entrar" ? "Entrar" : "Criar conta"}
                    </button>
                  ))}
                </div>

                <p className="mt-5 text-sm text-white/70">
                  {modo === "entrar" ? "Bem-vindo de volta. Use o e-mail da sua conta." : "Grátis para começar. Depois você cadastra a fazenda e envia o pendrive."}
                </p>

                {!configuracaoOk && (
                  <div className="mt-5 rounded-xl bg-trigo-400/15 p-3 text-sm text-trigo-300">
                    Configure <code>VITE_SUPABASE_URL</code> e <code>VITE_SUPABASE_PUBLISHABLE_KEY</code>.
                  </div>
                )}

                <div className="mt-5 space-y-4">
                  <div>
                    <label className="rotulo" htmlFor="email">E-mail</label>
                    <input id="email" type="email" autoComplete="email" required className="campo" value={email} onChange={(e) => setEmail(e.target.value)} />
                  </div>
                  <div>
                    <label className="rotulo" htmlFor="senha">Senha</label>
                    <input id="senha" type="password" required minLength={modo === "criar" ? 8 : undefined}
                      autoComplete={modo === "entrar" ? "current-password" : "new-password"}
                      className="campo" value={senha} onChange={(e) => setSenha(e.target.value)} />
                    {modo === "criar" && <p className="mt-1.5 text-xs text-white/50">Mínimo de 8 caracteres.</p>}
                  </div>
                </div>

                {enviar.error && <p className="mt-4 text-sm font-medium text-rose-300" role="alert">{(enviar.error as Error).message}</p>}
                {aviso && <p className="mt-4 text-sm text-broto-300">{aviso}</p>}

                <button type="submit" className="btn-primario mt-6 w-full" disabled={enviar.isPending || !configuracaoOk}>
                  {enviar.isPending ? "Aguarde…" : modo === "entrar" ? "Entrar" : "Criar conta"} <ArrowRight size={16} />
                </button>
                {modo === "entrar" && (
                  <button type="button" onClick={recuperar} className="mt-4 w-full text-center text-sm font-medium text-broto-300 hover:underline">
                    Esqueci minha senha
                  </button>
                )}
                {modo === "criar" && (
                  <p className="mt-4 text-center text-xs text-white/50">
                    Ao criar a conta você concorda com os <a className="underline hover:text-white" href={LINKS_LEGAIS.termos}>Termos</a> e
                    a <a className="underline hover:text-white" href={LINKS_LEGAIS.privacidade}>Política de Privacidade</a>.
                  </p>
                )}
              </form>
            )}
          </div>

          <p className="mt-6 text-center text-xs text-white/50">
            <a className="underline hover:text-white" href={LINKS_LEGAIS.termos}>Termos de Serviço</a> ·{" "}
            <a className="underline hover:text-white" href={LINKS_LEGAIS.privacidade}>Política de Privacidade</a>
          </p>
        </div>
      </section>
    </div>
  );
}
