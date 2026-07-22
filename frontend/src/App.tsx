import { useState } from "react";
import { BrowserRouter, Routes, Route, Outlet } from "react-router-dom";
import Sidebar from "./components/layout/Sidebar";
import Navbar from "./components/layout/Navbar";
import Aurora from "./components/ui/Aurora";
import Dashboard from "./pages/backoffice/Dashboard";
import TicketsList from "./pages/backoffice/TicketsList";
import TicketDetail from "./pages/backoffice/TicketDetail";
import NewTicket from "./pages/user/NewTicket";
import UserTicketHistory from "./pages/user/UserTicketHistory";
import UserTicketDetail from "./pages/user/UserTicketDetail";

function Layout() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="relative flex min-h-screen">
      {/* Fond animé Aurora — fixe derrière toute l'interface.
          Clair : dégradé blanc → menthe. Sombre : quasi-noir. */}
      <div className="pointer-events-none fixed inset-0 -z-10 bg-gradient-to-br from-emerald-50/70 via-white to-slate-50 dark:from-[#05070f] dark:via-[#05070f] dark:to-[#05070f]">
        <Aurora
          colorStops={["#10b981", "#34d399", "#059669"]}
          amplitude={1.0}
          blend={0.55}
          speed={0.6}
        />
        {/* Voile clair : dégradé qui laisse l'aurora briller en haut puis
            redevient opaque pour garder le contenu lisible en bas. */}
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-white/45 to-white/80 dark:hidden" />
        {/* Voile sombre : uniforme, plus marqué. */}
        <div className="absolute inset-0 hidden dark:block bg-[#05070f]/50" />
      </div>

      <Sidebar collapsed={collapsed} />
      <div className="flex flex-col flex-1 overflow-hidden">
        <Navbar collapsed={collapsed} onToggle={() => setCollapsed((v) => !v)} />
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
        </Route>
        <Route element={<Layout />}>
          <Route path="/tickets" element={<TicketsList />} />
          <Route path="/tickets/:id" element={<TicketDetail />} />
          <Route path="/nouveau-ticket" element={<NewTicket />} />
          <Route path="/historique" element={<UserTicketHistory />} />
          <Route path="/historique/:id" element={<UserTicketDetail />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
