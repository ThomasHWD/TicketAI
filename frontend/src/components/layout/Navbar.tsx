import { Link } from "react-router-dom";
import { Search, Bell, Sun, Plus, ChevronDown, LayoutGrid, ChevronLeft, ChevronRight } from "lucide-react";
import { getValidatorId, setValidatorId } from "../../lib/currentUser";

interface NavbarProps {
  breadcrumb?: string;
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

export default function Navbar({ breadcrumb = "Dashboard", collapsed, onToggle }: NavbarProps) {
  return (
    <div className="h-20 bg-white border-b border-gray-100 flex items-center px-5 gap-3 shrink-0">
      {/* Collapse */}
      <button
        onClick={onToggle}
        className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 transition-colors shrink-0"
      >
        {collapsed ? <ChevronRight size={17} /> : <ChevronLeft size={17} />}
      </button>

      {/* Grid */}
      <button className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 transition-colors shrink-0">
        <LayoutGrid size={17} />
      </button>

      {/* Divider */}
      <div className="w-px h-5 bg-gray-200 shrink-0" />

      {/* Breadcrumb */}
      <span className="text-sm text-gray-400 shrink-0">
        <Link to="/" className="hover:text-gray-600 transition-colors">
          Dashboard
        </Link>
        {breadcrumb !== "Dashboard" && (
          <>
            <span className="mx-1.5 text-gray-300">/</span>
            <span className="text-gray-600">{breadcrumb}</span>
          </>
        )}
      </span>

      {/* Search */}
      <div className="flex items-center gap-2.5 bg-gray-50 border border-gray-200 rounded-xl px-3 py-2 text-sm text-gray-400 w-64 ml-1 hover:border-gray-300 transition-colors cursor-text">
        <Search size={14} className="text-gray-400 shrink-0" />
        <span className="flex-1">Search...</span>
        <kbd className="text-xs text-gray-300 bg-gray-100 border border-gray-200 rounded px-1.5 py-0.5 font-sans">⌘/</kbd>
      </div>

      <div className="flex-1" />

      {/* Icon group */}
      <div className="flex items-center gap-0.5">
        <button className="p-2 rounded-lg hover:bg-gray-100 text-gray-400 transition-colors relative">
          <Bell size={18} />
          <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-red-500 rounded-full" />
        </button>
        <button className="p-2 rounded-lg hover:bg-gray-100 text-gray-400 transition-colors">
          <Sun size={18} />
        </button>
      </div>

      {/* Divider */}
      <div className="w-px h-5 bg-gray-200 shrink-0" />

      {/* Sélecteur de validateur (dev uniquement) */}
      {import.meta.env.DEV && <DevValidatorSwitcher />}

      {/* Add Ticket */}
      <button className="flex items-center gap-1.5 bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium px-4 py-2 rounded-xl transition-colors shadow-sm shadow-emerald-200">
        <Plus size={15} />
        Add Ticket
      </button>

      {/* User */}
      <button className="flex items-center gap-2.5 pl-1">
        <img
          src="https://i.pravatar.cc/36"
          alt="avatar"
          className="w-8 h-8 rounded-full object-cover ring-2 ring-gray-100"
        />
        <div className="text-left">
          <p className="text-sm font-medium text-gray-700 leading-tight whitespace-nowrap">
            Thomas HENWOOD
          </p>
        </div>
        <ChevronDown size={14} className="text-gray-400" />
      </button>
    </div>
  );
}
