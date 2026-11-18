import { lazy } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { Layout } from "./componentes/Layout";
import { Carregando } from "./componentes/ui";
import { useSessao } from "./contextos/Sessao";
import BoasVindas from "./paginas/BoasVindas";
import Convite from "./paginas/Convite";
import Inicio from "./paginas/Inicio";
import Login from "./paginas/Login";

// Telas carregadas sob demanda: o mapa (maplibre) e os gráficos (recharts) só baixam quando usados.
const Painel = lazy(() => import("./paginas/Painel"));
const MapaPagina = lazy(() => import("./paginas/MapaPagina"));
const Talhoes = lazy(() => import("./paginas/Talhoes"));
const Safras = lazy(() => import("./paginas/Safras"));
const MaquinaDetalhe = lazy(() => import("./paginas/MaquinaDetalhe"));
const JornadaDetalhe = lazy(() => import("./paginas/JornadaDetalhe"));
const SessaoDetalhe = lazy(() => import("./paginas/SessaoDetalhe"));
const Integracoes = lazy(() => import("./paginas/Integracoes"));
const Qualidade = lazy(() => import("./paginas/Qualidade"));
const PlanoPagina = lazy(() => import("./paginas/Plano"));
const Configuracoes = lazy(() => import("./paginas/Configuracoes"));
const Alertas = lazy(() => import("./paginas/Alertas"));
const Jornadas = lazy(() => import("./paginas/Jornadas"));
const Sessoes = lazy(() => import("./paginas/Sessoes"));
const Enviar = lazy(() => import("./paginas/Enviar"));
const Maquinas = lazy(() => import("./paginas/Maquinas"));

export default function App() {
  const { sessao, carregando, org } = useSessao();
  const { pathname } = useLocation();

  if (carregando) return <div className="grid min-h-screen place-items-center"><Carregando /></div>;
  if (!sessao) return <Login />;
  if (pathname === "/convite") return <Convite />;
  if (!org) return <BoasVindas />;

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Inicio />} />
        <Route path="safras" element={<Safras />} />
        <Route path="maquinas" element={<Maquinas />} />
        <Route path="maquinas/:id" element={<MaquinaDetalhe />} />
        <Route path="analise" element={<Painel />} />
        <Route path="jornadas" element={<Jornadas />} />
        <Route path="jornadas/:id" element={<JornadaDetalhe />} />
        <Route path="mapa" element={<MapaPagina />} />
        <Route path="sessoes" element={<Sessoes />} />
        <Route path="sessoes/:id" element={<SessaoDetalhe />} />
        <Route path="alertas" element={<Alertas />} />
        <Route path="talhoes" element={<Talhoes />} />
        <Route path="enviar" element={<Enviar />} />
        <Route path="integracoes" element={<Integracoes />} />
        <Route path="qualidade" element={<Qualidade />} />
        <Route path="plano" element={<PlanoPagina />} />
        <Route path="configuracoes" element={<Configuracoes />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
