import { lazy, Suspense, useState } from "react";
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

const Dashboard = lazy(() => import("./pages/backoffice/Dashboard"));
const UserDashboard = lazy(() => import("./pages/user/UserDashboard"));
const TicketsList = lazy(() => import("./pages/backoffice/TicketsList"));
const TicketDetail = lazy(() => import("./pages/backoffice/TicketDetail/TicketDetail"));
const SavedAnswers = lazy(() => import("./pages/backoffice/SavedAnswers"));
const NewTicket = lazy(() => import("./pages/user/NewTicket"));
const UserTicketHistory = lazy(() => import("./pages/user/UserTicketHistory"));
const UserTicketDetail = lazy(() => import("./pages/user/UserTicketDetail/UserTicketDetail"));
const KnowledgeBase = lazy(() => import("./pages/backoffice/KnowledgeBase"));
const TicketTracking = lazy(() => import("./pages/backoffice/TicketTracking"));
const AdminPage = lazy(() => import("./pages/admin/Groups"));
const SiteConfigPage = lazy(() => import("./pages/admin/SiteConfig"));
const AdminDashboard = lazy(() => import("./pages/admin/AdminDashboard"));
const NotFound = lazy(() => import("./pages/404"));
const SuggestionBox = lazy(() => import("./pages/user/SuggestionBox"));

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

/** Redirection vers la base de connaissances, `?q=` compris. */
function RedirigerVersBase() {
  const { search } = useLocation();
  return <Navigate to={`/base-de-connaissances${search}`} replace />;
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
      <Suspense fallback={
        <div className="fixed inset-0 flex items-center justify-center bg-gray-50 dark:bg-[#0d0d0d]">
          <div className="w-5 h-5 rounded-full border-2 border-emerald-500 border-t-transparent motion-safe:animate-spin" />
        </div>
      }>
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
              <Route path="/reponses-enregistrees" element={<SavedAnswers />} />
              <Route path="/base-de-connaissances" element={<KnowledgeBase />} />
              {/* Anciennes pages « Indexation » et « Documents indexés », désormais fusionnées.
                  Les liens externes (favoris, `?q=` du tableau de bord) doivent continuer à tomber juste. */}
              <Route path="/Documentations" element={<RedirigerVersBase />} />
              <Route path="/documents-indexes" element={<RedirigerVersBase />} />
              <Route path="/mon-suivi" element={<TicketTracking />} />
              {/* /angles-morts est désormais un onglet de la base de connaissances */}
              <Route path="/angles-morts" element={<Navigate to="/base-de-connaissances?onglet=angles-morts" replace />} />
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
              <Route path="/admin/config" element={<SiteConfigPage />} />
              <Route path="/admin/dashboard" element={<AdminDashboard />} />

            </Route>
          </Route>
        </Route>
      </Routes>
      </Suspense>
    </BrowserRouter>
    </JobsProvider>
  );
}
