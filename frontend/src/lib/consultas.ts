/** Consultas reaproveitadas entre páginas. */
import { useQueries, useQuery } from "@tanstack/react-query";

import type { FC } from "../componentes/Mapa";
import { api } from "./api";
import type { Talhao } from "./tipos";

export function useTalhoes() {
  return useQuery({ queryKey: ["talhoes"], queryFn: () => api<Talhao[]>("/talhoes") });
}

/** Contornos de todos os talhões como FeatureCollection (para o mapa). */
export function useContornos(): { dados: FC | undefined; carregando: boolean } {
  const lista = useTalhoes();
  const comContorno = (lista.data ?? []).filter((t) => t.tem_contorno && t.ativo);
  const detalhes = useQueries({
    queries: comContorno.map((t) => ({
      queryKey: ["talhao", t.id],
      queryFn: () => api<Talhao>(`/talhoes/${t.id}`),
      staleTime: 5 * 60_000,
    })),
  });
  const prontos = detalhes.every((d) => d.data);
  const dados: FC | undefined =
    lista.data && prontos
      ? {
          type: "FeatureCollection",
          features: detalhes
            .map((d) => d.data!)
            .filter((t) => t.geometria)
            .map((t) => ({
              type: "Feature" as const,
              geometry: t.geometria!,
              properties: { id: t.id, nome: t.nome, area_ha: t.area_ha },
            })),
        }
      : undefined;
  return { dados, carregando: lista.isLoading || !prontos };
}
