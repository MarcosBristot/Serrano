/**
 * Aviso de cookies e consentimento (LGPD, art. 7º I e 8º).
 *
 * Hoje o site NÃO usa cookies nem scripts de rastreamento, publicidade ou medição: só guarda,
 * no armazenamento local do navegador, a escolha feita neste aviso (estritamente necessário).
 *
 * Para adotar uma ferramenta opcional no futuro, cadastre-a em CATEGORIAS com seus scripts:
 * ela só é carregada depois do consentimento, pode ser recusada com o mesmo esforço de aceitar
 * e a escolha pode ser revista a qualquer momento em "Preferências de cookies" (rodapé).
 */
interface Categoria {
  nome: string;
  descricao: string;
  scripts: string[]; // URLs carregadas só com consentimento
}

const CATEGORIAS: Record<string, Categoria> = {
  // exemplo (desativado): analiticos: { nome: "Medição de audiência", descricao: "...", scripts: ["https://..."] },
};

const CHAVE = "serrano.consentimento";
const VERSAO = 1;

interface Escolha {
  versao: number;
  data: string;
  permitidas: string[];
}

function ler(): Escolha | null {
  try {
    const e = JSON.parse(localStorage.getItem(CHAVE) ?? "null") as Escolha | null;
    return e && e.versao === VERSAO ? e : null;
  } catch {
    return null;
  }
}

function salvar(permitidas: string[]) {
  try {
    localStorage.setItem(CHAVE, JSON.stringify({ versao: VERSAO, data: new Date().toISOString(), permitidas }));
  } catch {
    // navegação privada ou armazenamento bloqueado: o aviso volta a aparecer, sem prejuízo
  }
}

const carregados = new Set<string>();
function aplicar(permitidas: string[]) {
  for (const id of permitidas) {
    for (const src of CATEGORIAS[id]?.scripts ?? []) {
      if (carregados.has(src)) continue;
      carregados.add(src);
      const s = document.createElement("script");
      s.src = src;
      s.async = true;
      document.head.append(s);
    }
  }
}

const opcionais = () => Object.keys(CATEGORIAS);

function aviso(): HTMLElement {
  const temOpcionais = opcionais().length > 0;
  const el = document.createElement("section");
  el.className = "cookies";
  el.setAttribute("aria-labelledby", "cookies-titulo");
  el.innerHTML = temOpcionais
    ? `<h2 id="cookies-titulo">Cookies</h2>
       <p>Usamos armazenamento essencial para o site funcionar. Ferramentas opcionais só são ativadas se você aceitar.
       <a href="/privacidade.html#cookies">Saiba mais</a>.</p>
       <div class="botoes">
         <button type="button" class="botao primario" data-acao="aceitar">Aceitar</button>
         <button type="button" class="botao secundario" data-acao="recusar">Recusar</button>
         <button type="button" class="link" data-acao="preferencias">Preferências</button>
       </div>`
    : `<h2 id="cookies-titulo">Sem rastreamento</h2>
       <p>Este site não usa cookies de publicidade nem de rastreamento. Guardamos no seu navegador apenas esta escolha.
       <a href="/privacidade.html#cookies">Saiba mais</a>.</p>
       <div class="botoes"><button type="button" class="botao primario" data-acao="recusar">Entendi</button></div>`;
  el.addEventListener("click", (e) => {
    const acao = (e.target as HTMLElement).closest<HTMLElement>("[data-acao]")?.dataset.acao;
    if (!acao) return;
    if (acao === "preferencias") return abrirPreferencias();
    const permitidas = acao === "aceitar" ? opcionais() : [];
    salvar(permitidas);
    aplicar(permitidas);
    el.remove();
  });
  return el;
}

export function abrirPreferencias() {
  const atual = ler()?.permitidas ?? [];
  const d = document.createElement("dialog");
  d.className = "preferencias";
  d.setAttribute("aria-labelledby", "pref-titulo");
  const linhas = opcionais()
    .map(
      (id) => `<label><input type="checkbox" name="${id}" ${atual.includes(id) ? "checked" : ""} />
        <span><b>${CATEGORIAS[id].nome}</b><br />${CATEGORIAS[id].descricao}</span></label>`,
    )
    .join("");
  d.innerHTML = `
    <form method="dialog">
      <h2 id="pref-titulo">Preferências de cookies</h2>
      <fieldset>
        <legend>Essenciais (sempre ativos)</legend>
        <p>Guardam a sua escolha neste aviso e, no painel do cliente, mantêm você conectado. Sem eles o serviço não funciona.</p>
      </fieldset>
      <fieldset>
        <legend>Opcionais</legend>
        ${linhas || "<p>Nenhuma ferramenta opcional está em uso hoje: não há medição de audiência, publicidade nem rastreamento.</p>"}
      </fieldset>
      <div class="botoes">
        <button class="botao primario" value="salvar">Salvar escolha</button>
        <button class="botao secundario" value="cancelar">Cancelar</button>
      </div>
    </form>`;
  d.addEventListener("close", () => {
    if (d.returnValue === "salvar") {
      const permitidas = opcionais().filter((id) => (d.querySelector<HTMLInputElement>(`input[name="${id}"]`)?.checked ?? false));
      salvar(permitidas);
      aplicar(permitidas);
      document.querySelector(".cookies")?.remove();
      if (atual.some((id) => !permitidas.includes(id))) location.reload(); // retira scripts já carregados
    }
    d.remove();
  });
  document.body.append(d);
  d.showModal();
}

export function iniciarConsentimento() {
  const escolha = ler();
  if (escolha) aplicar(escolha.permitidas);
  else document.body.append(aviso());
  document.addEventListener("click", (e) => {
    if ((e.target as HTMLElement).closest("[data-preferencias-cookies]")) abrirPreferencias();
  });
}
