import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCheck, Circle, Loader2, Trash2 } from "lucide-react";
import { getSuggestions, supprimerSuggestion, toggleSuggestionLu } from "../../../lib/api";
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

  const supprimer = useMutation({
    mutationFn: () => supprimerSuggestion(s.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-suggestions"] }),
  });

  return (
    <div
      className={`glass-card rounded-xl overflow-hidden border ${
        s.lu
          ? "border-gray-100 dark:border-white/[0.04]"
          : "border-gray-100 dark:border-white/[0.06]"
      }`}
    >
      <div className="px-4 pt-4 pb-3.5 space-y-2.5">
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-2 min-w-0">
            {!s.lu && (
              <span
                className="mt-[0.375rem] w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0"
                aria-hidden="true"
              />
            )}
            <div className="min-w-0">
              <p className={`text-sm font-medium truncate ${s.lu ? "text-muted-foreground" : "text-gray-800 dark:text-gray-100"}`}>
                {s.user_nom || s.user_email || "Utilisateur supprimé"}
              </p>
              {s.user_nom && s.user_email && (
                <p className="text-xs text-muted-foreground truncate mt-0.5">
                  {s.user_email}
                </p>
              )}
            </div>
          </div>
          <div className={`flex items-center gap-1.5 shrink-0 ${s.lu ? "opacity-50" : ""}`}>
            <span className="text-xs text-muted-foreground whitespace-nowrap tabular-nums mr-1">
              {formatDate(s.created_at)}
            </span>
            <button
              onClick={() => toggle.mutate()}
              disabled={toggle.isPending || supprimer.isPending}
              aria-label={s.lu ? "Marquer comme non lu" : "Marquer comme lu"}
              className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-white/[0.06] text-muted-foreground hover:text-emerald-500 dark:hover:text-emerald-400 transition-colors disabled:opacity-40"
            >
              {toggle.isPending ? (
                <Loader2 size={13} className="animate-spin" aria-hidden="true" />
              ) : s.lu ? (
                <Circle size={13} aria-hidden="true" />
              ) : (
                <CheckCheck size={13} aria-hidden="true" />
              )}
            </button>
            {s.lu && (
              <button
                onClick={() => supprimer.mutate()}
                disabled={supprimer.isPending || toggle.isPending}
                aria-label="Supprimer cette suggestion"
                className="p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-500/10 text-muted-foreground hover:text-red-500 dark:hover:text-red-400 transition-colors disabled:opacity-40"
              >
                {supprimer.isPending ? (
                  <Loader2 size={13} className="animate-spin" aria-hidden="true" />
                ) : (
                  <Trash2 size={13} aria-hidden="true" />
                )}
              </button>
            )}
          </div>
        </div>

        {/* Content */}
        <p className={`text-sm whitespace-pre-wrap leading-relaxed break-words ${s.lu ? "text-muted-foreground" : "text-gray-700 dark:text-gray-300"}`}>
          {s.contenu}
        </p>
      </div>
    </div>
  );
}

export default function AdminSuggestions() {
  const qc = useQueryClient();
  const { data: suggestions, isLoading } = useQuery({
    queryKey: ["admin-suggestions"],
    queryFn: getSuggestions,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
  });

  const total = suggestions?.length ?? 0;
  const nonLues = suggestions?.filter((s) => !s.lu).length ?? 0;

  const marquerToutLu = useMutation({
    mutationFn: () =>
      Promise.all(
        (suggestions ?? []).filter((s) => !s.lu).map((s) => toggleSuggestionLu(s.id))
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-suggestions"] }),
  });

  return (
    <div className="space-y-4 max-w-3xl">
      {/* Counter + bulk action */}
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground">
          {isLoading
            ? "Chargement…"
            : nonLues > 0
            ? `${nonLues} non lue${nonLues > 1 ? "s" : ""} sur ${total}`
            : total > 0
            ? `${total} suggestion${total > 1 ? "s" : ""} — toutes lues`
            : "Aucune suggestion"}
        </p>
        {nonLues > 0 && !isLoading && (
          <button
            onClick={() => marquerToutLu.mutate()}
            disabled={marquerToutLu.isPending}
            className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-gray-800 dark:hover:text-gray-200 disabled:opacity-40 transition-colors"
          >
            {marquerToutLu.isPending ? (
              <Loader2 size={12} className="animate-spin" aria-hidden="true" />
            ) : (
              <CheckCheck size={12} aria-hidden="true" />
            )}
            Tout marquer comme lu
          </button>
        )}
      </div>

      {isLoading && (
        <div className="flex justify-center py-16 text-muted-foreground">
          <Loader2 size={20} className="animate-spin" aria-hidden="true" />
        </div>
      )}

      {!isLoading && total === 0 && (
        <div className="glass-card rounded-2xl px-6 py-16 text-center">
          <p className="text-sm text-muted-foreground">
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
