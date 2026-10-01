import { useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { X, Frown, AlertTriangle } from "lucide-react";
import { getTickets } from "../../lib/api/tickets";
import { StarRating } from "./SatisfactionCard";
import type { Ticket } from "../../types";
import { useDialogFocus } from "../../hooks/useDialogFocus";

interface Props {
  onClose: () => void;
  periode: string;
  domaine?: string;
}

function NoteCell({ label, value }: { label: string; value: number | null }) {
  if (value === null) return <span className="text-muted-foreground text-xs">—</span>;
  const mauvaise = value <= 2;
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</span>
      <div className="flex items-center gap-1.5">
        <span
          className={`text-sm font-semibold tabular-nums ${
            mauvaise ? "text-rose-500 dark:text-rose-400" : "text-amber-700 dark:text-amber-400"
          }`}
        >
          {value}
        </span>
        <StarRating value={value} size={11} />
      </div>
    </div>
  );
}

export default function TicketsInsatisfaitsModal({ onClose, periode, domaine }: Props) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = "modal-insatisfaits-title";

  const { data, isLoading, isError } = useQuery({
    queryKey: ["tickets-insatisfaits", periode, domaine],
    queryFn: () => getTickets({ noteMax: 2, closed: true, limit: 50, periode, domaine }),
    staleTime: 30_000,
  });

  useDialogFocus(panelRef, { onClose });

  const tickets: Ticket[] = data?.items ?? [];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      {/* Overlay */}
      <div className="absolute inset-0 bg-black/40 dark:bg-black/60 backdrop-blur-sm" />

      {/* Panel */}
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative z-10 w-full max-w-2xl max-h-[80vh] flex flex-col rounded-2xl bg-white dark:bg-[#141416] shadow-2xl border border-gray-100 dark:border-white/8 overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100 dark:border-white/8 shrink-0">
          <div className="flex items-center gap-2">
            <Frown size={16} className="text-rose-500 dark:text-rose-400" />
            <h2 id={titleId} className="text-sm font-semibold text-gray-800 dark:text-gray-200">
              Tickets insatisfaits
            </h2>
            <span className="text-xs text-muted-foreground">
              note &lt; 3 sur au moins un critère
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-white/8 transition-colors"
            aria-label="Fermer"
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto flex-1">
          {isError ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-muted-foreground">
              <AlertTriangle size={28} className="text-red-400 opacity-70" />
              <p className="text-sm">Impossible de charger les tickets</p>
              <button
                onClick={() => queryClient.refetchQueries({ queryKey: ["tickets-insatisfaits", periode, domaine] })}
                className="text-xs font-medium text-emerald-700 dark:text-emerald-400 hover:underline"
              >
                Réessayer
              </button>
            </div>
          ) : isLoading ? (
            <div className="p-5 space-y-3">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="animate-pulse flex gap-4 p-3 rounded-xl bg-gray-50 dark:bg-white/4">
                  <div className="flex-1 space-y-2">
                    <div className="h-3.5 bg-gray-200 dark:bg-white/10 rounded w-3/4" />
                    <div className="h-3 bg-gray-200 dark:bg-white/10 rounded w-1/3" />
                  </div>
                  <div className="w-24 h-8 bg-gray-200 dark:bg-white/10 rounded" />
                </div>
              ))}
            </div>
          ) : tickets.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-muted-foreground">
              <Frown size={32} className="opacity-40" />
              <p className="text-sm">Aucun ticket avec une note inférieure à 3</p>
            </div>
          ) : (
            <ul className="p-3 space-y-1.5">
              {tickets.map((t) => (
                <li key={t.id}>
                  <button
                    onClick={() => { navigate(`/tickets/${t.id}`); onClose(); }}
                    className="w-full text-left flex items-center gap-4 px-4 py-3 rounded-xl hover:bg-gray-50 dark:hover:bg-white/4 transition-colors group"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate group-hover:text-amber-600 dark:group-hover:text-amber-400 transition-colors">
                        {t.objet || "Sans objet"}
                      </p>
                      <p className="text-xs text-muted-foreground truncate mt-0.5">
                        {t.domaine} · {t.closed_at ? new Date(t.closed_at).toLocaleDateString("fr-FR") : ""}
                      </p>
                    </div>
                    <div className="shrink-0 flex gap-4">
                      <NoteCell label="Qualité" value={t.note_qualite} />
                      <NoteCell label="Rapidité" value={t.note_delai} />
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {!isLoading && !isError && tickets.length > 0 && (
          <div className="px-5 py-3 border-t border-gray-100 dark:border-white/8 shrink-0">
            <p className="text-xs text-muted-foreground">
              {tickets.length} ticket{tickets.length > 1 ? "s" : ""} · cliquez pour accéder au détail
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
