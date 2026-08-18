import { useState } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Outlet,
  Navigate,
  useLocation,
} from "react-router-dom";
import { useAuth } from "./lib/auth";
import { useSSE } from "./hooks/useSSE";
import Login from "./pages/auth/Login";
import Sidebar from "./components/layout/Sidebar";
import Navbar from "./components/layout/Navbar";
import SidebarToggle from "./components/layout/SidebarToggle";
import JobTracker from "./components/ui/JobTracker";
import { JobsProvider } from "./context/JobsContext";
import Dashboard from "./pages/backoffice/Dashboard";
import UserDashboard from "./pages/user/UserDashboard";
import TicketsList from "./pages/backoffice/TicketsList";
import ClosedTicketsList from "./pages/backoffice/ClosedTicketsList";
import TicketDetail from "./pages/backoffice/TicketDetail/TicketDetail";
import SavedAnswers from "./pages/backoffice/SavedAnswers";
import NewTicket from "./pages/user/NewTicket";
import UserTicketHistory from "./pages/user/UserTicketHistory";
import UserTicketDetail from "./pages/user/UserTicketDetail/UserTicketDetail";
import Ingestion from "./pages/backoffice/Ingestion";
import AllDocs from "./pages/backoffice/AllDocs";
import TicketTracking from "./pages/backoffice/TicketTracking";
import HorsDomaine from "./pages/backoffice/HorsDomaine";
import AdminPage from "./pages/admin/Groups";
import SiteConfigPage from "./pages/admin/SiteConfig";
import AdminDashboard from "./pages/admin/AdminDashboard";
import NotFound from "./pages/404";
import SuggestionBox from "./pages/user/SuggestionBox";

function Layout() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="relative flex h-screen overflow-hidden bg-gray-50 dark:bg-[#0d0d0d]">
      <Sidebar collapsed={collapsed} />

      <SidebarToggle collapsed={collapsed} onToggle={() => setCollapsed((v) => !v)} />

      <div className="relative flex-1 overflow-hidden">
        <Navbar />
        <main className="absolute inset-0 overflow-auto pt-14">
          <Outlet />
        </main>
      </div>
      <JobTracker />
    </div>
  );
}

/** Barrière d'authentification : redirige vers /login si non connecté. */
function ProtectedRoute() {
  const { isAuthenticated } = useAuth();
  const location = useLocation();
  useSSE();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}

/** Barrière admin : redirige vers / si l'utilisateur n'est pas ADMIN. */
function AdminRoute() {
  const { user } = useAuth();
  if (user?.role !== "ADMIN") {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}

/** Redirige les users lambda vers leur espace personnel, affiche le dashboard backoffice pour les autres. */
function RootPage() {
  const { isBackoffice } = useAuth();
  return isBackoffice ? <Dashboard /> : <Navigate to="/mon-espace" replace />;
}

/** Barrière backoffice : accessible uniquement si l'utilisateur est dans au moins un groupe. */
function BackofficeRoute() {
  const { userDomaines, user } = useAuth();
  if (userDomaines.length === 0 && user?.role !== "ADMIN") {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}

export default function App() {
  return (
    <JobsProvider>
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<Layout />}>
            <Route path="/" element={<RootPage />} />
          </Route>
          <Route element={<BackofficeRoute />}>
            <Route element={<Layout />}>
              <Route path="/tickets" element={<TicketsList />} />
              <Route path="/tickets/:id" element={<TicketDetail />} />
              <Route path="/tickets-clotures" element={<ClosedTicketsList />} />
              <Route path="/reponses-enregistrees" element={<SavedAnswers />} />
              <Route path="/Documentations" element={<Ingestion />} />
              <Route path="/documents-indexes" element={<AllDocs />} />
              <Route path="/mon-suivi" element={<TicketTracking />} />
              <Route path="/angles-morts" element={<HorsDomaine />} />
            </Route>
          </Route>
          <Route element={<Layout />}>
            <Route path="*" element={<NotFound />} />
            <Route path="/mon-espace" element={<UserDashboard />} />
            <Route path="/nouveau-ticket" element={<NewTicket />} />
            <Route path="/historique" element={<UserTicketHistory />} />
            <Route path="/historique/:id" element={<UserTicketDetail />} />
            <Route path="/suggestion" element={<SuggestionBox />} />
          </Route>
          <Route element={<AdminRoute />}>
            <Route element={<Layout />}>
              <Route path="/admin" element={<AdminPage />} />
              <Route path="/admin/documents" element={<AllDocs />} />
              <Route path="/admin/config" element={<SiteConfigPage />} />
              <Route path="/admin/dashboard" element={<AdminDashboard />} />

            </Route>
          </Route>
        </Route>
      </Routes>
    </BrowserRouter>
    </JobsProvider>
  );
}
