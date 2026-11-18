import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
  // Sem manualChunks: as telas são carregadas sob demanda (App.tsx) e o mapa e os gráficos
  // vêm junto só com as telas que os usam.
  build: {
    chunkSizeWarningLimit: 1500,
  },
});
