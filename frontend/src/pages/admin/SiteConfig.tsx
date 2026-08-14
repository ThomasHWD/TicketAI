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
      <h1 className="text-xl font-semibold text-white drop-shadow mb-6">
        Administration
      </h1>

      <div className="flex items-center gap-1 border-b border-white/30 mb-6">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === id
                ? "border-white text-white drop-shadow"
                : "border-transparent text-white/60 hover:text-white/90 drop-shadow"
            }`}
          >
            <span className="relative">
              <Icon size={14} />
              {id === "incidents" && hasIncidents && (
                <span className="absolute -top-0.5 -right-1 w-1.5 h-1.5 rounded-full bg-red-500" />
              )}
              {id === "suggestions" && nbNonLues > 0 && (
                <span className="absolute -top-0.5 -right-1 w-1.5 h-1.5 rounded-full bg-amber-400" />
              )}
            </span>
            {label}
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
