# Campero — frontend

Painel web do Sistema Campero: React 18 + Vite + TypeScript + Tailwind, mapas com MapLibre (satélite Esri), gráficos com Recharts, login pelo Supabase.

## Rodar

1. Copie `.env.example` para `.env.local` e preencha:
   - `VITE_SUPABASE_URL`: `https://<ref>.supabase.co`
   - `VITE_SUPABASE_PUBLISHABLE_KEY`: a chave `sb_publishable_…` (Supabase → Project Settings → API Keys). É pública; nunca use a `sb_secret_` aqui.
   - `VITE_API_URL`: a API, por padrão `http://localhost:8000/api/v1`
2. Na raiz do repositório, suba a API e o worker:
   ```bash
   uv run sistemacampero api --port 8000
   uv run sistemacampero worker
   ```
   O `CORS_ORIGENS` do `.env` do backend precisa incluir `http://localhost:5173`.
3. Aqui na pasta `frontend`:
   ```bash
   npm install
   npm run dev
   ```
   e abra http://localhost:5173.

## Telas

| Rota | O quê |
|---|---|
| `/` | Painel: horas, diesel, área, L/ha, R$/ha, ociosidade; série por dia/semana; ranking por talhão; alertas abertos |
| `/mapa` | Talhões + mapa de calor de consumo (L/ha) em hexágonos |
| `/sessoes`, `/sessoes/:id` | Operações (sessões de trabalho), trajeto no mapa, qualidade do dado, correção manual do talhão |
| `/alertas` | Abertos / reconhecidos / resolvidos, com comentários |
| `/talhoes` | Lista, criação e envio de contorno (`.gjson` do monitor ou GeoJSON) |
| `/enviar` | Upload do pendrive (`.jdl` ou `.zip`) com progresso e acompanhamento do processamento |
| `/configuracoes` | Preço do diesel, limites dos alertas, equipe e convites |
| `/convite?token=` | Aceite do convite |

O período (7 dias, 30 dias, safra, …) fica no topo e vale para o painel e o mapa.

## Build

`npm run build` gera `dist/` (estático; sirva com qualquer CDN, configurando fallback de rotas para `index.html`).
