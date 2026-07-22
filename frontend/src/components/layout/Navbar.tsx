import { useNavigate } from "react-router-dom";
import { Sun, Moon, Plus, ChevronLeft, ChevronRight } from "lucide-react";
import { getValidatorId, setValidatorId } from "../../lib/currentUser";
import { useTheme } from "../../hooks/useTheme";

interface NavbarProps {
  collapsed: boolean;
  onToggle: () => void;
}

// Validateurs fictifs pour tester le verrouillage à plusieurs — DEV UNIQUEMENT.
// À supprimer quand l'authentification réelle sera en place.
const DEV_VALIDATORS = [
  { id: "00000000-0000-0000-0000-000000000001", label: "Validateur A" },
  { id: "00000000-0000-0000-0000-000000000002", label: "Validateur B" },
];

function DevValidatorSwitcher() {
  return (
    <select
      defaultValue={getValidatorId()}
      onChange={(e) => {
        setValidatorId(e.target.value);
        window.location.reload();
      }}
      className="text-xs border border-amber-200 bg-amber-50 text-amber-700 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-amber-400"
      title="Simuler un validateur (dev)"
      aria-label="Validateur simulé (dev)"
    >
      {DEV_VALIDATORS.map((v) => (
        <option key={v.id} value={v.id}>{v.label}</option>
      ))}
    </select>
  );
}

export default function Navbar({ collapsed, onToggle }: NavbarProps) {
  const { theme, toggle } = useTheme();
  const navigate = useNavigate();
  return (
    <div className="h-20 bg-white/50 dark:bg-white/5 backdrop-blur-2xl border-b border-white/60 dark:border-white/10 shadow-[0_1px_24px_0_rgba(0,0,0,0.06)] flex items-center px-5 gap-3 shrink-0">
      {/* Collapse */}
      <button
        onClick={onToggle}
        className="p-1.5 rounded-lg hover:bg-white/60 dark:hover:bg-white/10 text-gray-600 dark:text-gray-400 transition-colors shrink-0"
        title={collapsed ? "Déplier le menu" : "Replier le menu"}
        aria-label={collapsed ? "Déplier le menu latéral" : "Replier le menu latéral"}
      >
        {collapsed ? <ChevronRight size={17} /> : <ChevronLeft size={17} />}
      </button>

      <div className="flex-1" />

      {/* Theme toggle */}
      <button
        onClick={toggle}
        className="p-2 rounded-lg hover:bg-white/60 dark:hover:bg-white/10 text-gray-600 dark:text-amber-300 transition-colors shrink-0"
        title={theme === "dark" ? "Passer en thème clair" : "Passer en thème sombre"}
        aria-label={theme === "dark" ? "Passer en thème clair" : "Passer en thème sombre"}
      >
        {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
      </button>

      {/* Divider */}
      <div className="w-px h-5 bg-gray-200 dark:bg-white/10 shrink-0" />

      {/* Sélecteur de validateur (dev uniquement) */}
      {import.meta.env.DEV && <DevValidatorSwitcher />}

      {/* Nouvelle question */}
      <button
        onClick={() => navigate("/nouveau-ticket")}
        className="flex items-center gap-1.5 bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium px-4 py-2 rounded-xl transition-colors shadow-sm shadow-emerald-200 dark:shadow-none shrink-0"
      >
        <Plus size={15} aria-hidden="true" />
        <span className="hidden sm:inline">Ticket</span>
      </button>

      {/* User (identité, statique tant qu'il n'y a pas de menu réel) */}
      <div className="flex items-center gap-2.5 pl-1 shrink-0">
        <img
          src="https://i.pravatar.cc/36"
          alt=""
          className="w-8 h-8 rounded-full object-cover ring-2 ring-gray-100 dark:ring-white/10"
        />
        <p className="hidden md:block text-sm font-medium text-gray-900 dark:text-gray-100 leading-tight whitespace-nowrap">
          Thomas HENWOOD
        </p>
      </div>
    </div>
  );
}
