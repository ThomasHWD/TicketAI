import { useNavigate, useMatch } from "react-router-dom";
import { Sun, Moon, Plus, LogOut } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../../lib/auth";
import { useTheme } from "../../hooks/useTheme";
import { unlockTicket, getSiteConfig } from "../../lib/api";
import { getValidatorId } from "../../lib/currentUser";
import GlassSurface from "@@/components/GlassSurface";
import MarqueeBanner from "../ui/MarqueeBanner";
import NotificationBell from "../ui/NotificationBell";
import UserAvatar from "../ui/UserAvatar";

/** Nom affichable de l'utilisateur : « Prénom NOM », sinon email. */
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
    <GlassSurface
      width="100%"
      height={80}
      borderRadius={0}
      backgroundOpacity={0.3}
      brightness={55}
      opacity={0.92}
      blur={14}
      distortionScale={-120}
      className="absolute top-0 left-0 right-0 z-20 border-b border-white/40 dark:border-white/10 !flex-row !justify-start"
      style={{ borderBottom: undefined }}
    >
      <div className="flex items-center w-full px-5 gap-3 h-full">
      {banner?.active && banner.message ? (
        <MarqueeBanner message={banner.message} url={banner.url || undefined} />
      ) : (
        <div className="flex-1" />
      )}

      {/* Theme toggle */}
      <button
        onClick={toggle}
        className="p-2 rounded-lg hover:bg-white/60 dark:hover:bg-white/10 text-gray-600 dark:text-amber-300 transition-colors shrink-0"
        title={theme === "dark" ? "Passer en thème clair" : "Passer en thème sombre"}
        aria-label={theme === "dark" ? "Passer en thème clair" : "Passer en thème sombre"}
      >
        {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
      </button>

      <NotificationBell />

      {/* Divider */}
      <div className="w-px h-5 bg-gray-200 dark:bg-white/10 shrink-0" />

      {/* Nouvelle question */}
      <button
        onClick={() => navigate("/nouveau-ticket")}
        className="flex items-center gap-1.5 bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium px-4 py-2 rounded-xl transition-colors shadow-sm shadow-emerald-200 dark:shadow-none shrink-0"
      >
        <Plus size={15} aria-hidden="true" />
        <span className="hidden sm:inline">Ticket</span>
      </button>

      {/* Utilisateur connecté */}
      <div className="flex items-center gap-2.5 pl-1 shrink-0">
        <UserAvatar name={user ? displayName(user) : "?"} size={32} />
        <p className="hidden md:block text-sm font-medium text-gray-900 dark:text-gray-100 leading-tight whitespace-nowrap">
          {user ? displayName(user) : ""}
        </p>
      </div>

      {/* Déconnexion */}
      <button
        onClick={handleLogout}
        className="p-2 rounded-lg hover:bg-white/60 dark:hover:bg-white/10 text-gray-600 dark:text-gray-400 transition-colors shrink-0"
        title="Se déconnecter"
        aria-label="Se déconnecter"
      >
        <LogOut size={18} />
      </button>
      </div>
    </GlassSurface>
  );
}
