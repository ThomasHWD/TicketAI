import { NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../../lib/auth";
import GlassSurface from "@@/components/GlassSurface";
import TicketAIMark from "../../assets/ticketai_mark_v2.svg";
import {
  LayoutDashboard,
  TicketMinus,
  MessageSquare,
  // Settings,
  BookText,
  History,
  // TicketPlus,
  MessagesSquare,
  ArchiveX,
  File,
  Users,
  SlidersHorizontal,
} from "lucide-react";
import { getIncidents } from "../../lib/api";
import UserAvatar from "../ui/UserAvatar";

const navMain = [
  { to: "/", icon: LayoutDashboard, label: "Tableau de bord" },
  { to: "/tickets", icon: TicketMinus, label: "Tickets" },
  { to: "/tickets-clotures", icon: ArchiveX, label: "Tickets clôturés" },
  { to: "/mon-suivi", icon: MessagesSquare, label: "Mon suivi" },
  {
    to: "/reponses-enregistrees",
    icon: MessageSquare,
    label: "Réponses Enregistrées",
  },
  { to: "/Documentations", icon: BookText, label: "Documentations" },
  { to: "/documents-indexes", icon: File, label: "Documents indexés" },
];

const navSettings = [
  // { to: "/nouveau-ticket", icon: TicketPlus, label: "Nouvelle question" },
  { to: "/historique", icon: History, label: "Mon historique" },
  // { to: "/parametres", icon: Settings, label: "Paramètres" },
];

const navAdmin = [
  { to: "/admin/dashboard", icon: LayoutDashboard, label: "Vue globale" },
  { to: "/admin", icon: Users, label: "Groupes" },
  { to: "/admin/documents", icon: File, label: "Tous les documents" },
  { to: "/admin/config", icon: SlidersHorizontal, label: "Configuration" },
];

function NavItem({
  to,
  icon: Icon,
  label,
  collapsed,
  badge,
}: {
  to: string;
  icon: React.ElementType;
  label: string;
  collapsed: boolean;
  badge?: boolean;
}) {
  return (
    <NavLink
      to={to}
      end
      title={collapsed ? label : undefined}
      className={({ isActive }) =>
        `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors overflow-hidden ${
          collapsed ? "justify-center" : ""
        } ${
          isActive
            ? "bg-green-100 dark:bg-emerald-400/15 text-green-700 dark:text-emerald-300 font-medium"
            : "text-gray-700 dark:text-gray-300 hover:bg-white/60 dark:hover:bg-white/5"
        }`
      }
    >
      <span className="relative shrink-0">
        <Icon size={18} />
        {badge && (
          <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-red-500" />
        )}
      </span>
      <span
        className={`whitespace-nowrap transition-all duration-300 ease-in-out ${
          collapsed
            ? "opacity-0 -translate-x-2 w-0 overflow-hidden"
            : "opacity-100 translate-x-0"
        }`}
      >
        {label}
      </span>
    </NavLink>
  );
}

interface SidebarProps {
  collapsed: boolean;
}

export default function Sidebar({ collapsed }: SidebarProps) {
  const { user, userDomaines } = useAuth();
  const greetingName = user?.prenom || user?.email || "";
  const avatarName = [user?.prenom, user?.nom].filter(Boolean).join(" ") || user?.email || "?";

  const { data: incidents } = useQuery({
    queryKey: ["admin-incidents"],
    queryFn: getIncidents,
    enabled: user?.role === "ADMIN",
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: false,
  });
  const hasIncidents =
    (incidents?.tickets_echoues.length ?? 0) +
    (incidents?.tickets_bloques.length ?? 0) +
    (incidents?.documents_echoues.length ?? 0) > 0;
  return (
    <aside
      className={`relative flex flex-col shrink-0 overflow-hidden
        transition-[width] duration-300 ease-[cubic-bezier(0.4,0,0.2,1)]
        ${collapsed ? "w-16" : "w-60"}`}
    >
      {/* Effet glass — positionné en absolu pour ne pas bloquer la transition de largeur CSS */}
      <div className="pointer-events-none absolute inset-0" aria-hidden="true">
        <GlassSurface
          width="100%"
          height="100%"
          borderRadius={0}
          backgroundOpacity={0.1}
          brightness={52}
          opacity={0.9}
          blur={14}
          distortionScale={-100}
          className="!w-full !h-full border-r border-white/30 dark:border-white/8"
        />
      </div>

      {/* Contenu au-dessus du layer glass */}
      <div className="relative z-10 flex flex-col flex-1 overflow-hidden">

      {/* Logo */}
      <div className={`flex items-center gap-[11px] h-20 overflow-hidden transition-all duration-300 ${collapsed ? "justify-center px-3" : "px-[18px]"}`}>
        <img
          src={TicketAIMark}
          alt="TicketAI"
          className={`shrink-0 [filter:drop-shadow(0_0_6px_rgba(255,255,255,0.8))_drop-shadow(0_1px_3px_rgba(0,0,0,0.15))] dark:[filter:drop-shadow(0_1px_3px_rgba(0,0,0,0.15))] transition-all duration-300 ease-in-out ${
            collapsed ? "h-8 w-8" : "h-[52px] w-[52px]"
          }`}
        />
        <span
          className={`text-[18px] font-semibold tracking-tight text-gray-900 dark:text-gray-100 whitespace-nowrap transition-all duration-300 ease-in-out ${
            collapsed ? "opacity-0 -translate-x-2 w-0 overflow-hidden" : "opacity-100 translate-x-0"
          }`}
        >
          Ticket<span className="text-green-700 dark:text-emerald-300">AI</span>
        </span>
      </div>

      {/* Main nav — visible uniquement si l'utilisateur a au moins un groupe avec un domaine */}
      {userDomaines.length > 0 && (
        <nav className="flex flex-col gap-1 px-2 pt-12 pb-4">
          <p className={`px-3 pb-1 text-xs font-semibold tracking-[0.05em] uppercase text-gray-500 dark:text-gray-400 [text-shadow:0_1px_2px_rgba(255,255,255,0.6)] dark:[text-shadow:none] transition-all duration-300 ease-in-out ${collapsed ? "opacity-0 h-0 overflow-hidden" : "opacity-100"}`}>
            Principal
          </p>
          {navMain.map((item) => (
            <NavItem key={item.to} {...item} collapsed={collapsed} />
          ))}
        </nav>
      )}

      {user?.role === "ADMIN" && (
        <>
          {userDomaines.length > 0 && <hr className="mx-3 border-gray-200 dark:border-white/10" />}
          <nav className="flex flex-col gap-1 px-2 py-4">
            <p className={`px-3 pb-1 text-xs font-semibold tracking-[0.05em] uppercase text-gray-500 dark:text-gray-400 [text-shadow:0_1px_2px_rgba(255,255,255,0.6)] dark:[text-shadow:none] transition-all duration-300 ease-in-out ${collapsed ? "opacity-0 h-0 overflow-hidden" : "opacity-100"}`}>
              Administration
            </p>
            {navAdmin.map((item) => (
              <NavItem
                key={item.to}
                {...item}
                collapsed={collapsed}
                badge={item.to === "/admin/config" && hasIncidents}
              />
            ))}
          </nav>
        </>
      )}

      {(userDomaines.length > 0 || user?.role === "ADMIN") && (
        <hr className="mx-3 border-gray-200 dark:border-white/10" />
      )}

      {/* Settings nav */}
      <nav className="flex flex-col gap-1 px-2 py-4 flex-1">
        <p className={`px-3 pb-1 text-xs font-semibold tracking-[0.05em] uppercase text-gray-500 dark:text-gray-400 [text-shadow:0_1px_2px_rgba(255,255,255,0.6)] dark:[text-shadow:none] transition-all duration-300 ease-in-out ${collapsed ? "opacity-0 h-0 overflow-hidden" : "opacity-100"}`}>
          Espace personnel
        </p>
        <NavItem to="/mon-espace" icon={LayoutDashboard} label="Mon espace" collapsed={collapsed} />
        {navSettings.map((item) => (
          <NavItem key={item.to} {...item} collapsed={collapsed} />
        ))}
      </nav>

      {/* User footer */}
      <div
        className={`flex items-center gap-3 px-3 py-4 border-t border-gray-200 dark:border-white/10 overflow-hidden ${
          collapsed ? "justify-center" : ""
        }`}
      >
        <UserAvatar name={avatarName} size={36} />
        <div
          className={`flex items-center gap-2 flex-1 min-w-0 transition-all duration-300 ease-in-out ${
            collapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100"
          }`}
        >
          <div className="flex-1 min-w-0">
            <p className="text-xs text-gray-600 dark:text-gray-400">Bonjour 👋</p>
            <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">{greetingName}</p>
          </div>
        </div>
      </div>

      </div>{/* fin contenu z-10 */}
    </aside>
  );
}
