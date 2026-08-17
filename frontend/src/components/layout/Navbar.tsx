import { useNavigate, useMatch } from "react-router-dom";
import { Sun, Moon, Plus, LogOut } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../../lib/auth";
import { useTheme } from "../../hooks/useTheme";
import { unlockTicket, getSiteConfig } from "../../lib/api";
import { getValidatorId } from "../../lib/currentUser";
import MarqueeBanner from "../ui/MarqueeBanner";
import NotificationBell from "../ui/NotificationBell";
import UserAvatar from "../ui/UserAvatar";

function displayName(user: { prenom: string | null; nom: string | null; email: string }): string {
  const full = [user.prenom, user.nom].filter(Boolean).join(" ").trim();
  return full || user.email;
}

export default function Navbar() {
  const { theme, toggle } = useTheme();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const ticketMatch = useMatch("/tickets/:id");
  const ticketId = ticketMatch?.params.id;

  const { data: siteConfig } = useQuery({
    queryKey: ["site-config"],
    queryFn: getSiteConfig,
    staleTime: 60_000,
  });
  const banner = siteConfig?.banner;

  async function handleLogout() {
    if (ticketId) {
      try {
        await unlockTicket(ticketId, getValidatorId());
      } catch { /* ignore */ }
    }
    logout();
    navigate("/login");
  }

  return (
    <div
      className="absolute top-0 left-0 right-0 z-20 flex items-center h-14
        bg-white dark:bg-[#111113]
        border-b border-gray-200 dark:border-[#1f1f1f]
        px-4 gap-2"
    >
      {/* Banner or spacer */}
      {banner?.active && banner.message ? (
        <MarqueeBanner message={banner.message} url={banner.url || undefined} />
      ) : (
        <div className="flex-1" />
      )}

      {/* Theme toggle */}
      <button
        onClick={toggle}
        className="p-1.5 rounded-md text-gray-500 dark:text-gray-400
          hover:bg-gray-100 dark:hover:bg-white/[0.06] hover:text-gray-800 dark:hover:text-gray-200
          transition-colors duration-150 shrink-0
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
        title={theme === "dark" ? "Passer en thème clair" : "Passer en thème sombre"}
        aria-label={theme === "dark" ? "Passer en thème clair" : "Passer en thème sombre"}
      >
        {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
      </button>

      <NotificationBell />

      {/* Divider */}
      <div className="w-px h-5 bg-gray-200 dark:bg-white/[0.08] shrink-0" />

      {/* Nouveau ticket */}
      <button
        onClick={() => navigate("/nouveau-ticket")}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-md
          bg-emerald-600 hover:bg-emerald-700
          text-white text-sm font-medium
          transition-colors duration-150 shrink-0
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1"
      >
        <Plus size={14} strokeWidth={2.2} aria-hidden="true" />
        <span className="hidden sm:inline">Ticket</span>
      </button>

      {/* Utilisateur connecté */}
      <div className="flex items-center gap-2 pl-1 shrink-0">
        <UserAvatar name={user ? displayName(user) : "?"} size={28} />
        <p className="hidden md:block text-sm font-medium text-gray-800 dark:text-gray-200 leading-tight whitespace-nowrap">
          {user ? displayName(user) : ""}
        </p>
      </div>

      {/* Déconnexion */}
      <button
        onClick={handleLogout}
        className="p-1.5 rounded-md text-gray-500 dark:text-gray-400
          hover:bg-gray-100 dark:hover:bg-white/[0.06] hover:text-gray-800 dark:hover:text-gray-200
          transition-colors duration-150 shrink-0
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
        title="Se déconnecter"
        aria-label="Se déconnecter"
      >
        <LogOut size={17} />
      </button>
    </div>
  );
}
