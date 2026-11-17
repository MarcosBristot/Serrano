/** Documentos legais ficam no site; a versão precisa bater com `site/empresa.json` (versaoDocumentos). */
export const SITE_URL = ((import.meta.env.VITE_SITE_URL as string | undefined) ?? "http://localhost:5174").replace(/\/$/, "");
export const VERSAO_DOCUMENTOS = "2026-10-29";
export const LINKS_LEGAIS = {
  termos: `${SITE_URL}/termos.html`,
  privacidade: `${SITE_URL}/privacidade.html`,
};
