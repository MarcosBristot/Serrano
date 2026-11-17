import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { Layout } from "./componentes/Layout";
import { Carregando } from "./componentes/ui";
import { useSessao } from "./contextos/Sessao";
import Alertas from "./paginas/Alertas";
import BoasVindas from "./paginas/BoasVindas";
import Configuracoes from "./paginas/Configuracoes";
import Convite from "./paginas/Convite";
import Enviar from "./paginas/Enviar";
import Inicio from "./paginas/Inicio";
import JornadaDetalhe from "./paginas/JornadaDetalhe";
import Jornadas from "./paginas/Jornadas";
import Login from "./paginas/Login";
import MaquinaDetalhe from "./paginas/MaquinaDetalhe";
import Maquinas from "./paginas/Maquinas";
import MapaPagina from "./paginas/MapaPagina";
import Painel from "./paginas/Painel";
import SessaoDetalhe from "./paginas/SessaoDetalhe";
import Safras from "./paginas/Safras";
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
        <Route path="configuracoes" element={<Configuracoes />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
