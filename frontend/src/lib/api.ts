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

export async function cabecalhos(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  // API exposta pelo ngrok (plano grátis): sem este cabeçalho ele devolve a página de aviso em vez do JSON.
  const h: Record<string, string> = { "ngrok-skip-browser-warning": "1" };
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

type ResultadoEnvio = { job_id: string | null; arquivo_id: string; duplicado: boolean; status: string; tipo: string };

/** Uma requisição com progresso de envio (fetch não informa progresso de upload). */
async function xhrComProgresso<T>(
  metodo: string,
  url: string,
  corpo: XMLHttpRequestBodyInit,
  aoProgredir: (enviados: number) => void,
  extras: Record<string, string> = {},
): Promise<T> {
  const h = { ...(await cabecalhos()), ...extras };
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(metodo, url);
    for (const [k, v] of Object.entries(h)) xhr.setRequestHeader(k, v);
    xhr.upload.onprogress = (e) => aoProgredir(e.loaded);
    xhr.onload = () => {
      let resposta: any = {};
      try {
        resposta = JSON.parse(xhr.responseText);
      } catch {
        /* sem corpo */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(resposta);
      else if (xhr.status === 413) reject(new ErroApi(413, "ARQUIVO_GRANDE", "Arquivo grande demais para um envio só."));
      else reject(new ErroApi(xhr.status, resposta.code ?? `HTTP_${xhr.status}`, resposta.detail ?? "Falha no envio", resposta.request_id));
    };
    xhr.onerror = () => reject(new ErroApi(0, "REDE", "Sem conexão com a API"));
    xhr.send(corpo);
  });
}

/** Acima disto o arquivo vai em partes: a Cloudflare recusa corpo acima de 100 MB por requisição. */
const LIMITE_ENVIO_UNICO = 32 * 1024 ** 2;
const TAMANHO_PARTE = 32 * 1024 ** 2;
const TENTATIVAS_POR_PARTE = 4;

/** Upload com progresso. Arquivos grandes vão em partes de 32 MB, com nova tentativa se a rede falhar. */
export async function enviarArquivo(
  arquivo: File,
  params: Params,
  aoProgredir: (fracao: number) => void,
): Promise<ResultadoEnvio> {
  if (arquivo.size <= LIMITE_ENVIO_UNICO) {
    const form = new FormData();
    form.append("arquivo", arquivo, arquivo.name);
    return xhrComProgresso<ResultadoEnvio>("POST", comParams("/telemetry/upload", params), form, (n) =>
      aoProgredir(Math.min(1, n / arquivo.size)),
    );
  }

  const inicio = await api<{ upload_id: string }>("/telemetry/upload/partes", {
    metodo: "POST",
    corpo: { nome: arquivo.name, tamanho: arquivo.size },
  });
  const base = `/telemetry/upload/partes/${inicio.upload_id}`;
  const total = Math.ceil(arquivo.size / TAMANHO_PARTE);
  for (let i = 0; i < total; i++) {
    const de = i * TAMANHO_PARTE;
    const parte = arquivo.slice(de, Math.min(arquivo.size, de + TAMANHO_PARTE));
    for (let tentativa = 1; ; tentativa++) {
      try {
        await xhrComProgresso("PUT", comParams(`${base}/${i}`), parte, (n) => aoProgredir(Math.min(0.99, (de + n) / arquivo.size)), {
          "Content-Type": "application/octet-stream",
        });
        break;
      } catch (erro) {
        const deRede = erro instanceof ErroApi && (erro.status === 0 || erro.status >= 500);
        if (!deRede || tentativa >= TENTATIVAS_POR_PARTE) throw erro;
        await new Promise((r) => setTimeout(r, 2000 * tentativa));
      }
    }
  }
  const r = await api<ResultadoEnvio>(`${base}/concluir`, { metodo: "POST", params });
  aoProgredir(1);
  return r;
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
