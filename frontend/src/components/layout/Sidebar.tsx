import { NavLink } from "react-router-dom";
import Logo from "../../assets/logo.svg";
import SmallLogo from "../../assets/small_logo.svg";
import {
  LayoutDashboard,
  TicketMinus,
  MessageSquare,
  Settings,
  BookText,
  ChevronRight,
  History,
} from "lucide-react";

const navMain = [
  { to: "/", icon: LayoutDashboard, label: "Tableau de bord" },
  { to: "/tickets", icon: TicketMinus, label: "Tickets" },
  {
    to: "/reponses-enregistrees",
    icon: MessageSquare,
    label: "Réponses Enregistrées",
  },
];

const navSettings = [
  { to: "/historique", icon: History, label: "Mon historique" },
  { to: "/Documentations", icon: BookText, label: "Documentations" },
  { to: "/parametres", icon: Settings, label: "Paramètres" },
];

function NavItem({
  to,
  icon: Icon,
  label,
  collapsed,
}: {
  to: string;
  icon: React.ElementType;
  label: string;
  collapsed: boolean;
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
            ? "bg-green-100 text-green-700 font-medium"
            : "text-gray-600 hover:bg-gray-100"
        }`
      }
    >
      <Icon size={18} className="shrink-0" />
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
  return (
    <aside
      className={`flex flex-col bg-white border-r border-gray-200 shrink-0 overflow-hidden
        transition-[width] duration-300 ease-[cubic-bezier(0.4,0,0.2,1)]
        ${collapsed ? "w-16" : "w-60"}`}
    >
      {/* Logo */}
      <div className="relative flex items-center justify-center h-20 px-3 overflow-hidden">
        {/* Full logo */}
        <img
          src={Logo}
          alt="TicketAI"
          className={`absolute w-[80%] h-auto transition-all duration-300 ease-in-out ${
            collapsed ? "opacity-0 scale-90 pointer-events-none" : "opacity-100 scale-100"
          }`}
        />
        {/* Small logo */}
        <img
          src={SmallLogo}
          alt="TicketAI"
          className={`h-8 w-auto transition-all duration-300 ease-in-out ${
            collapsed ? "opacity-100 scale-100" : "opacity-0 scale-90 pointer-events-none"
          }`}
        />
      </div>

      {/* Main nav */}
      <nav className="flex flex-col gap-1 px-2 pt-12 pb-4">
        {navMain.map((item) => (
          <NavItem key={item.to} {...item} collapsed={collapsed} />
        ))}
      </nav>

      <hr className="mx-3 border-gray-200" />

      {/* Settings nav */}
      <nav className="flex flex-col gap-1 px-2 py-4 flex-1">
        {navSettings.map((item) => (
          <NavItem key={item.to} {...item} collapsed={collapsed} />
        ))}
      </nav>

      {/* User footer */}
      <div
        className={`flex items-center gap-3 px-3 py-4 border-t border-gray-200 overflow-hidden ${
          collapsed ? "justify-center" : ""
        }`}
      >
        <div className="w-9 h-9 rounded-full bg-gray-300 overflow-hidden shrink-0">
          <img
            src="https://i.pravatar.cc/36"
            alt="avatar"
            className="w-full h-full object-cover"
          />
        </div>
        <div
          className={`flex items-center gap-2 flex-1 min-w-0 transition-all duration-300 ease-in-out ${
            collapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100"
          }`}
        >
          <div className="flex-1 min-w-0">
            <p className="text-xs text-gray-400">Bonjour 👋</p>
            <p className="text-sm font-semibold text-gray-800 truncate">Thomas</p>
          </div>
          <ChevronRight size={16} className="text-gray-400 shrink-0" />
        </div>
      </div>
    </aside>
  );
}
