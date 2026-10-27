import "./index.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { PeriodoProvider, SessaoProvider } from "./contextos/Sessao";
import { ErroApi } from "./lib/api";

const qc = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
      // erros 4xx não melhoram com nova tentativa
      retry: (n, e) => !(e instanceof ErroApi && e.status < 500) && n < 2,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <SessaoProvider>
          <PeriodoProvider>
            <App />
          </PeriodoProvider>
        </SessaoProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
