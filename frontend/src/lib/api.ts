/** Cliente da API do Campero: token do Supabase, organização ativa e erros problem+json. */
import { API_URL, supabase } from "./supabase";

export class ErroApi extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public requestId?: string,
  ) {
    super(message);
  }
}

const CHAVE_ORG = "campero.organizacao";
export const orgAtiva = {
  get: () => localStorage.getItem(CHAVE_ORG),
  set: (id: string | null) => (id ? localStorage.setItem(CHAVE_ORG, id) : localStorage.removeItem(CHAVE_ORG)),
};

async function cabecalhos(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const h: Record<string, string> = {};
  if (data.session) h.Authorization = `Bearer ${data.session.access_token}`;
  const org = orgAtiva.get();
  if (org) h["X-Organizacao-Id"] = org;
  return h;
}

async function erroDe(resp: Response): Promise<ErroApi> {
  try {
    const p = await resp.json();
    return new ErroApi(resp.status, p.code ?? `HTTP_${resp.status}`, p.detail ?? p.title ?? "Erro", p.request_id);
  } catch {
    return new ErroApi(resp.status, `HTTP_${resp.status}`, resp.statusText || "Erro de rede");
  }
}

type Params = Record<string, string | number | boolean | null | undefined>;

export function comParams(caminho: string, params?: Params): string {
  const u = new URL(API_URL + caminho);
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v !== undefined && v !== null && v !== "") u.searchParams.set(k, String(v));
  }
  return u.toString();
}

export async function api<T>(caminho: string, opcoes: { metodo?: string; corpo?: unknown; params?: Params } = {}): Promise<T> {
  const h = await cabecalhos();
  const init: RequestInit = { method: opcoes.metodo ?? "GET", headers: h };
  if (opcoes.corpo !== undefined) {
    h["Content-Type"] = "application/json";
    init.body = JSON.stringify(opcoes.corpo);
  }
  const resp = await fetch(comParams(caminho, opcoes.params), init);
  if (!resp.ok) throw await erroDe(resp);
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

/** Upload com progresso (fetch não informa progresso de envio). */
export async function enviarArquivo(
  arquivo: File,
  params: Params,
  aoProgredir: (fracao: number) => void,
): Promise<{ job_id: string | null; arquivo_id: string; duplicado: boolean; status: string; tipo: string }> {
  const h = await cabecalhos();
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", comParams("/telemetry/upload", params));
    for (const [k, v] of Object.entries(h)) xhr.setRequestHeader(k, v);
    xhr.upload.onprogress = (e) => e.lengthComputable && aoProgredir(e.loaded / e.total);
    xhr.onload = () => {
      let corpo: any = {};
      try {
        corpo = JSON.parse(xhr.responseText);
      } catch {
        /* sem corpo */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(corpo);
      else reject(new ErroApi(xhr.status, corpo.code ?? `HTTP_${xhr.status}`, corpo.detail ?? "Falha no envio", corpo.request_id));
    };
    xhr.onerror = () => reject(new ErroApi(0, "REDE", "Sem conexão com a API"));
    const form = new FormData();
    form.append("arquivo", arquivo, arquivo.name);
    xhr.send(form);
  });
}

/** Download autenticado (link comum não manda o token). */
export async function baixar(caminho: string, params: Params, nome: string): Promise<void> {
  const resp = await fetch(comParams(caminho, params), { headers: await cabecalhos() });
  if (!resp.ok) throw await erroDe(resp);
  const url = URL.createObjectURL(await resp.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: nome });
  a.click();
  URL.revokeObjectURL(url);
}
