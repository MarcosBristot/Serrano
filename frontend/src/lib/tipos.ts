/** Tipos das respostas da API (subconjunto usado pelo frontend). */
export type Papel = "owner" | "gestor" | "leitor";

export interface Me {
  usuario_id: string;
  email: string | null;
  organizacoes: { organizacao_id: string; nome: string; slug: string; papel: Papel }[];
}

export interface Indicadores {
  motor_h: number;
  trabalho_h: number;
  ocioso_h: number;
  ociosidade_pct: number | null;
  litros: number;
  litros_trabalho: number;
  litros_ocioso: number;
  area_ha: number;
  distancia_km: number;
  l_ha: number | null;
  ha_h: number | null;
  lph_trabalho: number | null;
  lph_ocioso: number | null;
  custo_rs: number | null;
  custo_ocioso_rs: number | null;
  rs_ha: number | null;
  rs_h: number | null;
}

export interface Resumo extends Indicadores {
  sessoes: number;
  maquinas: number;
  primeiro_dia: string | null;
  ultimo_dia: string | null;
  dias_sem_preco: number;
}

export interface PontoSerie extends Indicadores {
  periodo: string;
}

export interface ItemRanking extends Indicadores {
  id: string | null;
  nome: string;
  sessoes: number;
}

export interface Sessao {
  id: string;
  arquivo_bruto_id: string;
  maquina_id: string;
  serial: string;
  apelido: string | null;
  implemento_id: string | null;
  operador_id: string | null;
  talhao_id: string | null;
  talhao_nome: string | null;
  talhao_origem: "gps" | "monitor" | "manual" | "nenhum";
  talhao_confianca: number | null;
  operacao: string | null;
  inicio: string;
  fim: string;
  n_amostras: number;
  qualidade_score: number | null;
  motor_h: number | null;
  trabalho_h: number | null;
  ocioso_h: number | null;
  litros_integral: number | null;
  area_cobertura_ha: number | null;
  area_estimada_ha: number | null;
  l_ha: number | null;
  ha_h: number | null;
  cobertura_gps: number | null;
}

export interface Problema {
  codigo: string;
  severidade: "info" | "atencao" | "alto";
  mensagem: string;
  valor: number | null;
}

export interface SessaoDetalhe extends Sessao {
  qualidade: { score: number; problemas: Problema[]; detalhes: Record<string, unknown> } | null;
  adapter: string;
  adapter_versao: string;
  firmware: string | null;
  sobreposicao_pct: number | null;
  area_metodo: string | null;
  delta_horimetro_h: number | null;
  litros_contador: number | null;
  distancia_trabalho_km: number | null;
  velocidade_media: number | null;
  lph_trabalho: number | null;
  lph_ocioso: number | null;
}

export interface Pagina<T> {
  itens: T[];
  next_cursor: string | null;
}

export interface Alerta {
  id: string;
  sessao_id: string | null;
  serial: string | null;
  apelido: string | null;
  talhao_nome: string | null;
  tipo: string;
  severidade: "info" | "atencao" | "alto";
  status: "aberto" | "reconhecido" | "resolvido" | "invalidado";
  inicio: string | null;
  fim: string | null;
  valor: number | null;
  limiar: number | null;
  mensagem: string;
  criado_em: string;
  comentarios?: { id: string; texto: string; criado_em: string }[];
}

export interface Talhao {
  id: string;
  fazenda_id: string | null;
  nome: string;
  area_ha: number | null;
  origem_contorno: string | null;
  ativo: boolean;
  tem_contorno: boolean;
  geometria?: GeoJSON.MultiPolygon | null;
}

export interface Job {
  id: string;
  tipo: string;
  status: "pendente" | "executando" | "concluido" | "erro" | "morto" | "cancelado";
  progresso: { resultado?: Record<string, unknown> } & Record<string, unknown>;
  erro: string | null;
}

export interface Preco {
  id: string;
  tipo: string;
  preco_rs_l: number;
  valido_de: string;
  valido_ate: string | null;
  fonte: string;
}

export interface Membro {
  usuario_id: string;
  email: string | null;
  papel: Papel;
}
