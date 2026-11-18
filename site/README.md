# Serrano — site

Página de apresentação da Serrano: herói com um painel de telemetria de exemplo (números de uma operação real), o problema, como funciona, recursos, calculadora de economia de diesel e o formulário "Solicitar demonstração". Leve: sem 3D nem imagens de terceiros.

## Rodar

```bash
cp .env.example .env.local   # VITE_API_URL e VITE_APP_URL
npm install
npm run dev                  # http://localhost:5174
```

O formulário envia para `POST {VITE_API_URL}/contatos` (público, limitado por IP, com campo-armadilha contra robôs). Os pedidos ficam em `interno.contatos` no Supabase. O `CORS_ORIGENS` da API precisa incluir a origem do site.

## Onde mexer

- `index.html`: todos os textos.
- `src/inicio.css`: visual da página inicial (cores em `.inicio`); `src/estilo.css`: base comum, rodapé, cookies e páginas legais.
- `src/main.ts`: mapa de calor e gráfico do painel de exemplo, calculadora de economia, menu e formulário.
- `public/serrano-marca.svg` e o `<svg>` do topo: a marca vetorizada a partir do logo. Se houver o SVG original, troque o `path`.

`npm run build` gera `dist/` estático (publicado no Worker `www` da Cloudflare, ver `wrangler.jsonc`).
