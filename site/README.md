# Serrano — site

Página de apresentação da Serrano: um trator 3D (three.js, modelado em código) planta a lavoura conforme a rolagem; cada seção é um quadro-chave da câmera (noite → amanhecer → dia → pôr do sol), com mapa de calor de L/ha, alerta de ociosidade e o formulário "Solicitar demonstração".

## Rodar

```bash
cp .env.example .env.local   # VITE_API_URL e VITE_APP_URL
npm install
npm run dev                  # http://localhost:5174
```

O formulário envia para `POST {VITE_API_URL}/contatos` (público, limitado por IP, com campo-armadilha contra robôs). Os pedidos ficam em `interno.contatos` no Supabase. O `CORS_ORIGENS` da API precisa incluir a origem do site.

## Onde mexer

- `src/main.ts`: textos são do `index.html`; os quadros-chave da câmera e do céu ficam em `QUADROS`.
- `src/cena.ts`: lavoura, plantio, rastro de cobertura, mapa de calor, céu.
- `src/trator.ts`: o trator e a plantadeira.
- `public/serrano-marca.svg` e o `<svg>` do topo: a marca vetorizada a partir do logo. Se houver o SVG original, troque o `path`.

`npm run build` gera `dist/` estático (Vercel, Netlify, Cloudflare Pages).
