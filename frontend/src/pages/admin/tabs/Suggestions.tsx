import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCheck, Circle, Loader2 } from "lucide-react";
import { getSuggestions, toggleSuggestionLu } from "../../../lib/api";
import type { SuggestionOut } from "../../../lib/api";

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("fr-FR", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function SuggestionCard({ s }: { s: SuggestionOut }) {
  const qc = useQueryClient();
  const toggle = useMutation({
    mutationFn: () => toggleSuggestionLu(s.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-suggestions"] }),
  });

  return (
    <div
      className={`glass-card rounded-xl overflow-hidden transition-opacity ${
        s.lu
          ? "opacity-60 border border-gray-100 dark:border-white/[0.04]"
          : "border border-gray-100 dark:border-white/[0.06] border-l-[3px] border-l-emerald-500"
      }`}
    >
      <div className="px-4 pt-4 pb-3.5 space-y-2.5">
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">
              {s.user_nom || s.user_email || "Utilisateur supprimé"}
            </p>
            {s.user_nom && s.user_email && (
              <p className="text-xs text-gray-400 dark:text-gray-500 truncate mt-0.5">
                {s.user_email}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap tabular-nums">
              {formatDate(s.created_at)}
            </span>
            <button
              onClick={() => toggle.mutate()}
              disabled={toggle.isPending}
              title={s.lu ? "Marquer comme non lu" : "Marquer comme lu"}
              className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-white/[0.06] text-gray-400 hover:text-emerald-500 dark:hover:text-emerald-400 transition-colors"
            >
              {toggle.isPending ? (
                <Loader2 size={13} className="animate-spin" aria-hidden="true" />
              ) : s.lu ? (
                <Circle size={13} aria-label="Marquer comme non lu" />
              ) : (
                <CheckCheck size={13} aria-label="Marquer comme lu" />
              )}
            </button>
          </div>
        </div>

        {/* Content */}
        <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed break-words">
          {s.contenu}
        </p>
      </div>
    </div>
  );
}

export default function AdminSuggestions() {
  const { data: suggestions, isLoading } = useQuery({
    queryKey: ["admin-suggestions"],
    queryFn: getSuggestions,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
  });

  const total = suggestions?.length ?? 0;
  const nonLues = suggestions?.filter((s) => !s.lu).length ?? 0;

  return (
    <div className="space-y-4 max-w-3xl">
      {/* Counter */}
      <p className="text-xs text-gray-400 dark:text-gray-500">
        {isLoading
          ? "Chargement…"
          : nonLues > 0
          ? `${nonLues} non lue${nonLues > 1 ? "s" : ""} sur ${total}`
          : total > 0
          ? `${total} suggestion${total > 1 ? "s" : ""} — toutes lues`
          : "Aucune suggestion"}
      </p>

      {isLoading && (
        <div className="flex justify-center py-16 text-gray-400">
          <Loader2 size={20} className="animate-spin" aria-hidden="true" />
        </div>
      )}

      {!isLoading && total === 0 && (
        <div className="glass-card rounded-2xl px-6 py-16 text-center">
          <p className="text-sm text-gray-400 dark:text-gray-500">
            Aucune suggestion pour le moment.
          </p>
        </div>
      )}

      {suggestions && suggestions.length > 0 && (
        <div className="space-y-3">
          {suggestions.map((s) => (
            <SuggestionCard key={s.id} s={s} />
          ))}
        </div>
      )}
    </div>
  );
}
