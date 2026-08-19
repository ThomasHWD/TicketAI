import { NavLink } from "react-router-dom";
import { useAuth } from "../../lib/auth";
import TicketAIMark from "../../assets/ticketai_mark_v2.svg";
import { LayoutDashboard, Lightbulb } from "lucide-react";
import UserAvatar from "../ui/UserAvatar";
import { navMain, navSettings, navAdmin } from "./nav-items";
import { useSidebarBadges } from "./useSidebarBadges";

function SectionLabel({ label, collapsed }: { label: string; collapsed: boolean }) {
  return (
    <p
      className={`px-2 pt-4 pb-1 text-xs font-semibold tracking-[0.06em] uppercase
        text-gray-400 dark:text-gray-600 select-none
        transition-all duration-200 ease-in-out
        ${collapsed ? "opacity-0 h-0 pt-0 pb-0 overflow-hidden" : "opacity-100"}`}
    >
      {label}
    </p>
  );
}

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
  badge?: boolean | number;
}) {
  const count = typeof badge === "number" ? badge : 0;

  return (
    <NavLink
      to={to}
      end
      title={collapsed ? label : undefined}
      className={({ isActive }) =>
        [
          "flex items-center gap-2.5 text-sm rounded-md",
          "transition-colors duration-150 overflow-hidden",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1",
          collapsed
            ? "w-9 h-9 justify-center mx-auto"
            : "px-2.5 py-[7px] mx-2",
          isActive
            ? "bg-emerald-50 dark:bg-emerald-500/[0.08] text-emerald-700 dark:text-emerald-400 font-medium"
            : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/[0.05] hover:text-gray-900 dark:hover:text-gray-200",
        ].join(" ")
      }
    >
      <span className="relative shrink-0">
        <Icon size={15} strokeWidth={1.7} />
        {badge === true && (
          <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full bg-red-500" />
        )}
        {count > 0 && (
          <span className="absolute -top-1.5 -right-2 min-w-[1rem] px-0.5 rounded-full bg-amber-500 text-white text-[9px] leading-4 font-semibold text-center tabular-nums">
            {count > 99 ? "99+" : count}
          </span>
        )}
      </span>
      <span
        className={`whitespace-nowrap transition-all duration-200 ease-in-out ${
          collapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100"
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
  const { hasIncidents, badge } = useSidebarBadges();

  return (
    <aside
      className={`flex flex-col shrink-0
        bg-white dark:bg-[#111113]
        border-r border-gray-200 dark:border-[#1f1f1f]
        transition-[width] duration-300 ease-[cubic-bezier(0.4,0,0.2,1)]
        ${collapsed ? "w-14" : "w-56"}`}
    >
      {/* Logo */}
      <div
        className={`flex items-center h-14 shrink-0 overflow-hidden
          border-b border-gray-100 dark:border-[#1a1a1a]
          transition-all duration-300
          ${collapsed ? "justify-center px-0" : "px-4 gap-2.5"}`}
      >
        <img
          src={TicketAIMark}
          alt="TicketAI"
          className="shrink-0 w-13 h-13"
        />
        <span
          className={`text-base font-semibold tracking-[-0.01em] text-gray-900 dark:text-gray-100
            whitespace-nowrap transition-all duration-200 ease-in-out
            ${collapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100"}`}
        >
          Ticket<span className="text-emerald-600 dark:text-emerald-400">AI</span>
        </span>
      </div>

      {/* Navigation — scrollable area */}
      <div className="flex flex-col flex-1 overflow-y-auto overflow-x-hidden py-2 min-h-0">

        {/* Backoffice nav */}
        {userDomaines.length > 0 && (
          <nav className="flex flex-col gap-0.5 px-1.5">
            <SectionLabel label="Gestion tickets" collapsed={collapsed} />
            {navMain.map((item) => (
              <NavItem
                key={item.to}
                {...item}
                collapsed={collapsed}
                badge={item.to === "/reponses-enregistrees" ? badge : undefined}
              />
            ))}
          </nav>
        )}

        {/* Admin nav */}
        {user?.role === "ADMIN" && (
          <>
            {userDomaines.length > 0 && (
              <div className="mx-4 my-2 border-t border-gray-100 dark:border-[#1f1f1f]" />
            )}
            <nav className="flex flex-col gap-0.5 px-1.5">
              <SectionLabel label="Administration" collapsed={collapsed} />
              {navAdmin.map((item) => (
                <NavItem
                  key={item.to}
                  {...item}
                  collapsed={collapsed}
                  badge={item.to === "/admin/config" ? hasIncidents : undefined}
                />
              ))}
            </nav>
          </>
        )}

        {/* Personal nav */}
        {(userDomaines.length > 0 || user?.role === "ADMIN") && (
          <div className="mx-4 my-2 border-t border-gray-100 dark:border-[#1f1f1f]" />
        )}
        <nav className="flex flex-col gap-0.5 px-1.5">
          <SectionLabel label="Espace personnel" collapsed={collapsed} />
          <NavItem to="/mon-espace" icon={LayoutDashboard} label="Mon espace" collapsed={collapsed} />
          {navSettings.map((item) => (
            <NavItem key={item.to} {...item} collapsed={collapsed} />
          ))}
          <NavItem to="/suggestion" icon={Lightbulb} label="Faire une suggestion" collapsed={collapsed} />
        </nav>
      </div>

      {/* User footer */}
      <div
        className={`flex items-center shrink-0 overflow-hidden
          border-t border-gray-100 dark:border-[#1a1a1a]
          py-3 transition-all duration-300
          ${collapsed ? "justify-center px-0" : "px-3 gap-2.5"}`}
      >
        <UserAvatar name={avatarName} size={32} />
        <div
          className={`flex flex-col flex-1 min-w-0 transition-all duration-200 ease-in-out
            ${collapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100"}`}
        >
          <p className="text-xs text-gray-400 dark:text-gray-500 leading-none mb-0.5">
            Connecté en tant que
          </p>
          <p className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate leading-none">
            {greetingName}
          </p>
        </div>
      </div>
    </aside>
  );
}
