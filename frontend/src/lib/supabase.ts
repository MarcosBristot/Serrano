import { createClient } from "@supabase/supabase-js";

export const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL as string;
export const API_URL = (import.meta.env.VITE_API_URL as string) ?? "http://localhost:8000/api/v1";
const CHAVE_PUBLICA = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string;

export const configuracaoOk = Boolean(SUPABASE_URL && CHAVE_PUBLICA && !CHAVE_PUBLICA.includes("..."));

export const supabase = createClient(SUPABASE_URL || "http://invalido", CHAVE_PUBLICA || "x", {
  auth: { persistSession: true, autoRefreshToken: true },
});
