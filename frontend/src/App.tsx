import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { Layout } from "./componentes/Layout";
import { Carregando } from "./componentes/ui";
import { useSessao } from "./contextos/Sessao";
import Alertas from "./paginas/Alertas";
import BoasVindas from "./paginas/BoasVindas";
import Configuracoes from "./paginas/Configuracoes";
import Convite from "./paginas/Convite";
import Enviar from "./paginas/Enviar";
import Login from "./paginas/Login";
import MapaPagina from "./paginas/MapaPagina";
import Painel from "./paginas/Painel";
import SessaoDetalhe from "./paginas/SessaoDetalhe";
import Sessoes from "./paginas/Sessoes";
import Talhoes from "./paginas/Talhoes";

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
        <Route index element={<Painel />} />
        <Route path="mapa" element={<MapaPagina />} />
        <Route path="sessoes" element={<Sessoes />} />
        <Route path="sessoes/:id" element={<SessaoDetalhe />} />
        <Route path="alertas" element={<Alertas />} />
        <Route path="talhoes" element={<Talhoes />} />
        <Route path="enviar" element={<Enviar />} />
        <Route path="configuracoes" element={<Configuracoes />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
