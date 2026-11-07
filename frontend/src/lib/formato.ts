/** Formatação pt-BR (vírgula decimal, R$, datas locais). */
const nf = (casas: number) =>
  new Intl.NumberFormat("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });

export const num = (v: number | null | undefined, casas = 1) => (v == null ? "—" : nf(casas).format(v));
export const rs = (v: number | null | undefined) =>
  v == null ? "—" : new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(v);
export const pct = (v: number | null | undefined, casas = 0) => (v == null ? "—" : `${nf(casas).format(v)}%`);

export function horas(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 100) return `${nf(0).format(Math.round(v))} h`; // 1.688 h lê melhor que 1688h11
  const h = Math.floor(v);
  const m = Math.round((v - h) * 60);
  return h ? `${h}h${m ? String(m).padStart(2, "0") : ""}` : `${m} min`;
}

export const data = (iso: string | null | undefined) =>
  iso ? new Date(iso.length === 10 ? `${iso}T12:00:00` : iso).toLocaleDateString("pt-BR") : "—";
export const dataHora = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "—";
export const diaCurto = (iso: string) =>
  new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });

export const isoDia = (d: Date) => d.toISOString().slice(0, 10);

export const ROTULO_TIPO_ALERTA: Record<string, string> = {
  ociosidade: "Ociosidade",
  vazao_alta: "Consumo alto",
  l_ha_alto: "L/ha acima do normal",
  gps_salto: "Salto de GPS",
  sem_gps: "Sem GPS",
  contador_divergente: "Contador divergente",
  qualidade_dado: "Dado inconsistente",
};

export const ROTULO_ORIGEM: Record<string, string> = {
  gps: "por GPS",
  monitor: "do monitor",
  manual: "manual",
  nenhum: "sem talhão",
};

const ROTULO_TIPO: Record<string, string> = {
  trator: "Trator", colheitadeira: "Colheitadeira", pulverizador: "Pulverizador",
};

/** "Trator 6210M", "Colheitadeira S540" ou o apelido; o serial completo fica para o detalhe. */
export function nomeMaquina(m: { apelido?: string | null; modelo?: string | null; tipo?: string; serial: string }): string {
  if (m.apelido) return m.apelido;
  const tipo = ROTULO_TIPO[m.tipo ?? ""] ?? "Máquina";
  return m.modelo ? `${tipo} ${m.modelo}` : `${tipo} …${m.serial.slice(-6)}`;
}

/** Talhão criado pelo controlador sem nome ("Campo_151122-145941") vira algo legível. */
export function nomeTalhao(nome: string | null | undefined): string {
  if (!nome) return "Fora dos talhões";
  const m = /^Campo[ _](\d{2})(\d{2})(\d{2})-\d+$/.exec(nome);
  return m ? `Talhão sem nome (${m[1]}/${m[2]}/${m[3]})` : nome;
}

export function haQuanto(iso: string | null | undefined): string {
  if (!iso) return "sem registro";
  const dias = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (dias <= 0) return "hoje";
  if (dias === 1) return "ontem";
  if (dias < 30) return `há ${dias} dias`;
  if (dias < 365) return `há ${Math.round(dias / 30)} meses`;
  return new Date(iso).toLocaleDateString("pt-BR", { month: "short", year: "numeric" });
}
