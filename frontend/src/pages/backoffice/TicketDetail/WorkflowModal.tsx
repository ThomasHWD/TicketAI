import { useQuery } from "@tanstack/react-query";
import { Bot, History, Loader2, Lock, MessageCircle, Pencil, Plus, ThumbsUp, UserMinus, UserPlus, X } from "lucide-react";
import { getTicketWorkflow } from "../../../lib/api";
import type { WorkflowEvent, WorkflowEventType } from "../../../types.ts";
import { formatDate } from "./utils";

const EVENT_CONFIG: Record<WorkflowEventType, {
  icon: typeof Bot;
  bg: string;
  iconColor: string;
  ring: string;
}> = {
  CREE:            { icon: Plus,          bg: "bg-emerald-100 dark:bg-emerald-500/25", iconColor: "text-emerald-600 dark:text-emerald-400", ring: "ring-emerald-200/60 dark:ring-emerald-500/20" },
  REPONSE_GENEREE: { icon: Bot,           bg: "bg-blue-100 dark:bg-blue-500/25",       iconColor: "text-blue-600 dark:text-blue-400",       ring: "ring-blue-200/60 dark:ring-blue-500/20" },
  SUIVI:           { icon: MessageCircle, bg: "bg-amber-100 dark:bg-amber-500/25",     iconColor: "text-amber-600 dark:text-amber-400",     ring: "ring-amber-200/60 dark:ring-amber-500/20" },
  VALIDE:          { icon: ThumbsUp,      bg: "bg-emerald-100 dark:bg-emerald-500/25", iconColor: "text-emerald-600 dark:text-emerald-400", ring: "ring-emerald-200/60 dark:ring-emerald-500/20" },
  CORRIGE:         { icon: Pencil,        bg: "bg-blue-100 dark:bg-blue-500/25",       iconColor: "text-blue-600 dark:text-blue-400",       ring: "ring-blue-200/60 dark:ring-blue-500/20" },
  REJETE:          { icon: X,             bg: "bg-red-100 dark:bg-red-500/25",         iconColor: "text-red-600 dark:text-red-400",         ring: "ring-red-200/60 dark:ring-red-500/20" },
  ASSIGNE:         { icon: UserPlus,      bg: "bg-violet-100 dark:bg-violet-500/25",   iconColor: "text-violet-600 dark:text-violet-400",   ring: "ring-violet-200/60 dark:ring-violet-500/20" },
  DESASSIGNE:      { icon: UserMinus,     bg: "bg-gray-100 dark:bg-white/10",          iconColor: "text-gray-500 dark:text-gray-400",       ring: "ring-gray-200/60 dark:ring-white/10" },
  CLOTURE:         { icon: Lock,          bg: "bg-gray-100 dark:bg-white/10",          iconColor: "text-gray-500 dark:text-gray-400",       ring: "ring-gray-200/60 dark:ring-white/10" },
};

function eventLabel(event: WorkflowEvent): string {
  switch (event.type) {
    case "CREE": return "Ticket créé";
    case "REPONSE_GENEREE": {
      const src = event.meta?.source;
      if (src === "LLM") return "Réponse générée par IA";
      if (src === "SUGGESTION") return "Suggestion depuis une réponse validée";
      if (src === "CANONIQUE") return "Réponse canonique appliquée";
      if (src === "HORS_DOMAINE") return "Réponse générée — sujet non couvert";
      return "Réponse générée";
    }
    case "SUIVI": return "Précision de l'utilisateur";
    case "VALIDE": return "Réponse validée";
    case "CORRIGE": return "Réponse corrigée";
    case "REJETE": return "Réponse rejetée";
    case "ASSIGNE": {
      const nom = event.meta?.assignee_nom ?? event.meta?.assignee_email;
      return nom ? `Assigné à ${nom}` : "Assigné";
    }
    case "DESASSIGNE": return "Remis dans le pot commun";
    case "CLOTURE": return "Ticket clôturé";
  }
}

function eventActor(event: WorkflowEvent): string | null {
  const name = event.actor_nom_complet ?? event.actor_email;
  switch (event.type) {
    case "CREE":
    case "VALIDE":
    case "CORRIGE":
    case "REJETE":
    case "ASSIGNE":
    case "DESASSIGNE": return name ?? null;
    default: return null;
  }
}

export default function WorkflowModal({ ticketId, onClose }: { ticketId: string; onClose: () => void }) {
  const { data: events = [], isLoading, error } = useQuery({
    queryKey: ["ticket", ticketId, "workflow"],
    queryFn: () => getTicketWorkflow(ticketId),
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div className="absolute inset-0 bg-black/40 dark:bg-black/70 backdrop-blur-md" />

      <div
        className="relative glass-card rounded-2xl w-full max-w-md flex flex-col max-h-[82vh] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-5 py-4 border-b border-gray-200/80 dark:border-white/10 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-gray-100 dark:bg-white/10">
              <History size={14} className="text-gray-500 dark:text-gray-400" aria-hidden="true" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100 leading-none">Historique</h2>
              {events.length > 0 && (
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{events.length} événement{events.length > 1 ? "s" : ""}</p>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="flex items-center justify-center w-7 h-7 rounded-full text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors"
            aria-label="Fermer"
          >
            <X size={14} aria-hidden="true" />
          </button>
        </div>

        {/* Corps */}
        <div className="overflow-y-auto px-5 py-5">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center gap-3 py-14">
              <Loader2 size={20} className="animate-spin text-gray-300 dark:text-gray-600" aria-label="Chargement" />
              <p className="text-xs text-gray-400 dark:text-gray-500">Chargement de l'historique…</p>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center gap-2 py-10">
              <div className="w-8 h-8 rounded-full bg-red-50 dark:bg-red-500/10 flex items-center justify-center">
                <X size={14} className="text-red-500" aria-hidden="true" />
              </div>
              <p className="text-sm text-red-600 dark:text-red-400 text-center" role="alert">
                Impossible de charger l'historique.
              </p>
            </div>
          ) : events.length === 0 ? (
            <p className="text-sm text-gray-400 dark:text-gray-500 text-center py-10">Aucun événement enregistré.</p>
          ) : (
            <ul aria-label="Historique du ticket">
              {events.map((event, i) => {
                const config = EVENT_CONFIG[event.type];
                const Icon = config.icon;
                const actor = eventActor(event);
                const isFirst = i === 0;
                const isLast = i === events.length - 1;

                return (
                  <li
                    key={i}
                    className="flex gap-3.5 animate-in fade-in slide-in-from-bottom-1 duration-300"
                    style={{ animationDelay: `${i * 35}ms`, animationFillMode: "both" }}
                  >
                    {/* Colonne icône + ligne */}
                    <div className="flex flex-col items-center w-9 shrink-0">
                      {/* Ligne au-dessus de l'icône */}
                      <div className={`flex-1 w-0.5 min-h-[10px] ${isFirst ? "" : "bg-gray-300 dark:bg-white/10"}`} aria-hidden="true" />
                      <div
                        className={`relative z-10 flex items-center justify-center w-9 h-9 rounded-xl shrink-0 ${config.bg} ring-1 ${config.ring} shadow-sm`}
                        aria-hidden="true"
                      >
                        <Icon size={15} strokeWidth={2} className={config.iconColor} />
                      </div>
                      {/* Ligne en-dessous de l'icône */}
                      <div className={`flex-1 w-0.5 min-h-[10px] ${isLast ? "" : "bg-gray-300 dark:bg-white/10"}`} aria-hidden="true" />
                    </div>

                    {/* Contenu */}
                    <div className="flex-1 min-w-0 py-2">
                      <div className="rounded-xl px-3 py-2.5 bg-white/60 dark:bg-white/[0.03] border border-gray-100 dark:border-white/[0.06] hover:border-gray-200 dark:hover:border-white/10 hover:bg-white/80 dark:hover:bg-white/[0.05] transition-colors">
                        <p className="text-sm font-semibold text-gray-800 dark:text-gray-100 leading-snug">
                          {eventLabel(event)}
                        </p>

                        <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                          {event.at && (
                            <span className="text-xs text-gray-400 dark:text-gray-500">
                              {formatDate(event.at)}
                            </span>
                          )}
                          {actor && (
                            <>
                              <span className="text-gray-300 dark:text-white/15 select-none">·</span>
                              <span className="text-xs text-gray-500 dark:text-gray-400">par {actor}</span>
                            </>
                          )}
                        </div>

                        {/* Raison du rejet */}
                        {event.type === "REJETE" && event.meta?.raison && (
                          <blockquote className="mt-2 pl-3 border-l-2 border-red-400/70 dark:border-red-500/50">
                            <p className="text-xs text-gray-600 dark:text-gray-300 leading-relaxed line-clamp-3 italic">
                              {event.meta.raison}
                            </p>
                          </blockquote>
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
