/** Formatação pt-BR (vírgula decimal, R$, datas locais). */
const nf = (casas: number) =>
  new Intl.NumberFormat("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });

export const num = (v: number | null | undefined, casas = 1) => (v == null ? "—" : nf(casas).format(v));
export const rs = (v: number | null | undefined) =>
  v == null ? "—" : new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(v);
export const pct = (v: number | null | undefined, casas = 0) => (v == null ? "—" : `${nf(casas).format(v)}%`);

export function horas(v: number | null | undefined): string {
  if (v == null) return "—";
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
