import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { defineConfig, type Plugin } from "vite";

const raiz = fileURLToPath(new URL(".", import.meta.url));
const ler = (arq: string) => readFileSync(raiz + arq, "utf8");
const escapar = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);

/**
 * Partes compartilhadas (`<!-- @parte:rodape -->`) e dados da empresa (`{{cnpj}}`) vindos de
 * `empresa.json`: uma única fonte para rodapé e documentos legais.
 */
function partes(): Plugin {
  return {
    name: "serrano-partes",
    transformIndexHtml: {
      order: "pre",
      handler(html) {
        const empresa = JSON.parse(ler("empresa.json")) as Record<string, string>;
        return html
          .replace(/<!-- @parte:([a-z-]+) -->/g, (_, nome: string) => ler(`partes/${nome}.html`))
          .replace(/\{\{(\w+)\}\}/g, (_, k: string) => {
            if (!(k in empresa)) throw new Error(`empresa.json não tem "${k}"`);
            return escapar(empresa[k]);
          });
      },
    },
    buildEnd() {
      const empresa = JSON.parse(ler("empresa.json")) as Record<string, string>;
      const pendentes = Object.keys(empresa).filter((k) => empresa[k].startsWith("["));
      if (pendentes.length) {
        this.warn(`ATENÇÃO: dados da empresa pendentes em empresa.json (não publique assim): ${pendentes.join(", ")}`);
      }
    },
  };
}

export default defineConfig({
  plugins: [partes()],
  server: { port: 5174, strictPort: true },
  preview: { port: 5174 },
  build: {
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      input: {
        inicio: raiz + "index.html",
        privacidade: raiz + "privacidade.html",
        termos: raiz + "termos.html",
        reembolso: raiz + "reembolso.html",
        acessibilidade: raiz + "acessibilidade.html",
      },
    },
  },
});
