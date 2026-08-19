import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, Lightbulb, Megaphone, TriangleAlert } from "lucide-react";
import { getIncidents, getSuggestions } from "../../lib/api";
import HealthTab from "./tabs/HealthTab";
import IncidentsTab from "./tabs/incidents";
import BanniereTab from "./tabs/BanniereTab";
import AdminSuggestions from "./tabs/Suggestions";

type Tab = "sante" | "incidents" | "config" | "suggestions";

const TABS: { id: Tab; label: string; icon: typeof Activity }[] = [
  { id: "sante",       label: "Santé",       icon: Activity      },
  { id: "incidents",   label: "Incidents",   icon: TriangleAlert },
  { id: "config",      label: "Bannière",    icon: Megaphone     },
  { id: "suggestions", label: "Suggestions", icon: Lightbulb     },
];

export default function SiteConfigPage() {
  const [tab, setTab] = useState<Tab>("sante");

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

  return (
    <div className="px-6 py-8 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-gray-900 dark:text-gray-50">
          Administration
        </h1>
      </div>

      <div className="flex items-stretch border-b border-gray-100 dark:border-white/8 mb-6">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`relative flex items-center gap-2 px-0.5 mr-6 py-3 text-sm font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 ${
              tab === id
                ? "text-gray-900 dark:text-gray-50"
                : "text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
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
            {tab === id && (
              <span
                className="absolute bottom-0 left-0 right-0 h-0.5 bg-emerald-500 rounded-full"
                aria-hidden="true"
              />
            )}
          </button>
        ))}
      </div>

      {tab === "sante"       && <HealthTab onGoIncidents={() => setTab("incidents")} />}
      {tab === "incidents"   && <IncidentsTab />}
      {tab === "config"      && <BanniereTab />}
      {tab === "suggestions" && <AdminSuggestions />}
    </div>
  );
}
