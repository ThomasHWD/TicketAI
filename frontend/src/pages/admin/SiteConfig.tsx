import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, Lightbulb, Settings, TriangleAlert } from "lucide-react";
import { getIncidents, getSuggestions } from "../../lib/api";
import HealthTab from "./tabs/HealthTab";
import IncidentsTab from "./tabs/incidents";
import BanniereTab from "./tabs/BanniereTab";
import AdminSuggestions from "./tabs/Suggestions";

type Tab = "sante" | "incidents" | "config" | "suggestions";

const TABS: { id: Tab; label: string; icon: typeof Activity }[] = [
  { id: "sante",       label: "Santé",          icon: Activity      },
  { id: "incidents",   label: "Incidents",       icon: TriangleAlert },
  { id: "config",      label: "Configuration",   icon: Settings      },
  { id: "suggestions", label: "Suggestions",     icon: Lightbulb     },
];

const DIRTY_WARNING = "Vous avez des modifications non sauvegardées sur la bannière. Quitter sans enregistrer ?";

export default function SiteConfigPage() {
  const [tab, setTab] = useState<Tab>("sante");
  const [isBannerDirty, setIsBannerDirty] = useState(false);

  const { data: incidents } = useQuery({
    queryKey: ["admin-incidents"],
    queryFn: getIncidents,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: false,
  });
  const hasIncidents =
    (incidents?.tickets_echoues.length ?? 0) +
    (incidents?.tickets_bloques.length ?? 0) +
    (incidents?.documents_echoues.length ?? 0) > 0;

  const { data: suggestions } = useQuery({
    queryKey: ["admin-suggestions"],
    queryFn: getSuggestions,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: false,
  });
  const nbNonLues = suggestions?.filter((s) => !s.lu).length ?? 0;

  const navigateTo = useCallback(
    (id: Tab) => {
      if (tab === "config" && id !== "config" && isBannerDirty) {
        if (!window.confirm(DIRTY_WARNING)) return;
      }
      setTab(id);
    },
    [tab, isBannerDirty],
  );

  const handleTabKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLButtonElement>, id: Tab) => {
      const currentIdx = TABS.findIndex((t) => t.id === id);
      let nextIdx = -1;
      if (e.key === "ArrowRight") { e.preventDefault(); nextIdx = (currentIdx + 1) % TABS.length; }
      else if (e.key === "ArrowLeft") { e.preventDefault(); nextIdx = (currentIdx - 1 + TABS.length) % TABS.length; }
      else if (e.key === "Home") { e.preventDefault(); nextIdx = 0; }
      else if (e.key === "End") { e.preventDefault(); nextIdx = TABS.length - 1; }
      if (nextIdx >= 0) {
        const nextId = TABS[nextIdx].id;
        if (tab === "config" && nextId !== "config" && isBannerDirty) {
          if (!window.confirm(DIRTY_WARNING)) return;
        }
        setTab(nextId);
        (document.getElementById(`tab-${nextId}`) as HTMLElement)?.focus();
      }
    },
    [tab, isBannerDirty],
  );

  return (
    <div className="px-6 py-8 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-gray-900 dark:text-gray-50">
          Administration
        </h1>
      </div>

      <div
        role="tablist"
        aria-label="Navigation administration"
        className="flex items-stretch border-b border-gray-100 dark:border-white/8 mb-6 overflow-x-auto"
      >
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            id={`tab-${id}`}
            role="tab"
            type="button"
            aria-selected={tab === id}
            aria-controls={`panel-${id}`}
            tabIndex={tab === id ? 0 : -1}
            onClick={() => navigateTo(id)}
            onKeyDown={(e) => handleTabKeyDown(e, id)}
            className={`relative flex items-center gap-2 px-0.5 mr-6 py-3 text-sm font-medium transition-colors duration-150 shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 ${
              tab === id
                ? "text-gray-900 dark:text-gray-50"
                : "text-gray-500 dark:text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            }`}
          >
            <Icon size={14} aria-hidden="true" />
            {label}
            {id === "incidents" && hasIncidents && (
              <span className="w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" aria-label="Incidents actifs" />
            )}
            {id === "suggestions" && nbNonLues > 0 && (
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" aria-label={`${nbNonLues} non lue${nbNonLues > 1 ? "s" : ""}`} />
            )}
            {id === "config" && isBannerDirty && (
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" aria-label="Modifications non sauvegardées" />
            )}
            {tab === id && (
              <span
                className="absolute bottom-0 left-0 right-0 h-0.5 bg-emerald-500 rounded-full"
                aria-hidden="true"
              />
            )}
          </button>
        ))}
      </div>

      {tab === "sante" && (
        <div role="tabpanel" id="panel-sante" aria-labelledby="tab-sante">
          <HealthTab onGoIncidents={() => navigateTo("incidents")} />
        </div>
      )}
      {tab === "incidents" && (
        <div role="tabpanel" id="panel-incidents" aria-labelledby="tab-incidents">
          <IncidentsTab />
        </div>
      )}
      {tab === "config" && (
        <div role="tabpanel" id="panel-config" aria-labelledby="tab-config">
          <BanniereTab onDirtyChange={setIsBannerDirty} />
        </div>
      )}
      {tab === "suggestions" && (
        <div role="tabpanel" id="panel-suggestions" aria-labelledby="tab-suggestions">
          <AdminSuggestions />
        </div>
      )}
    </div>
  );
}
