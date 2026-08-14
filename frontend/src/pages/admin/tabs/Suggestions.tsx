import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getSuggestions, toggleSuggestionLu } from "../../../lib/api";
import type { SuggestionOut } from "../../../lib/api";
import { CheckCheck, Circle, Loader2, MessageSquare } from "lucide-react";

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
      className={`glass-card rounded-xl p-4 space-y-2 border transition-colors ${
        s.lu
          ? "border-gray-100 dark:border-white/5 opacity-60"
          : "border-emerald-200 dark:border-emerald-500/20"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">
            {s.user_nom || s.user_email || "Utilisateur supprimé"}
          </p>
          {s.user_nom && s.user_email && (
            <p className="text-xs text-gray-400 dark:text-gray-500 truncate">{s.user_email}</p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">
            {formatDate(s.created_at)}
          </span>
          <button
            onClick={() => toggle.mutate()}
            disabled={toggle.isPending}
            title={s.lu ? "Marquer comme non lu" : "Marquer comme lu"}
            className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-white/5 text-gray-400 hover:text-emerald-500 dark:hover:text-emerald-400 transition-colors"
          >
            {toggle.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : s.lu ? (
              <Circle size={14} />
            ) : (
              <CheckCheck size={14} />
            )}
          </button>
        </div>
      </div>

      <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed break-words overflow-hidden">
        {s.contenu}
      </p>
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

  const nonLues = suggestions?.filter((s) => !s.lu).length ?? 0;

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-5">
      {/* Header */}
      <div className="glass-card rounded-2xl px-6 py-5 flex items-start gap-3.5">
        <span className="mt-0.5 flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-xl bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
          <MessageSquare size={16} />
        </span>
        <div>
          <h1 className="text-base font-semibold text-gray-900 dark:text-gray-100 tracking-tight">
            Suggestions utilisateurs
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
            {isLoading
              ? "Chargement…"
              : nonLues > 0
              ? `${nonLues} non lue${nonLues > 1 ? "s" : ""} sur ${suggestions?.length ?? 0}`
              : `${suggestions?.length ?? 0} suggestion${(suggestions?.length ?? 0) > 1 ? "s" : ""}`}
          </p>
        </div>
      </div>

      {isLoading && (
        <div className="flex justify-center py-12 text-gray-400">
          <Loader2 size={22} className="animate-spin" />
        </div>
      )}

      {!isLoading && suggestions?.length === 0 && (
        <div className="glass-card rounded-2xl p-10 text-center text-gray-500 dark:text-gray-400 text-sm">
          Aucune suggestion pour le moment.
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
