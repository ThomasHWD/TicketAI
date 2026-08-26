import { useEffect, useRef, useState } from "react";
import { Check, Crown, Loader2, UserMinus, Users, X } from "lucide-react";
import type { Groupe, MembreSummary } from "../../../types/index.tsx";
import { displayName, initials } from "./utils";

type Props = {
  groupe: Groupe;
  pendingChefId: string | null;
  onChef: (membreId: string, isChef: boolean) => void;
  onRetirer: (membre: MembreSummary) => void;
};

export default function MembresPanel({ groupe, pendingChefId, onChef, onRetirer }: Props) {
  const [confirmCrown, setConfirmCrown] = useState<{ id: string; type: "promote" | "demote-last" } | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  const helpRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!showHelp) return;
    function onOutside(e: MouseEvent) {
      if (helpRef.current && !helpRef.current.contains(e.target as Node)) setShowHelp(false);
    }
    document.addEventListener("mousedown", onOutside);
    return () => document.removeEventListener("mousedown", onOutside);
  }, [showHelp]);

  const chefCount = groupe.membres.filter((m) => m.is_chef).length;

  function handleCrownClick(m: MembreSummary) {
    if (m.is_chef) {
      if (chefCount === 1) {
        setConfirmCrown({ id: m.id, type: "demote-last" });
      } else {
        onChef(m.id, false);
      }
    } else {
      setConfirmCrown({ id: m.id, type: "promote" });
    }
  }

  return (
    <div className="flex flex-col w-full md:w-1/2 min-h-0 overflow-hidden">
      {/* Sub-header */}
      <div className="px-5 py-3 border-b border-gray-100 dark:border-white/5 bg-gray-50/40 dark:bg-white/[0.015] shrink-0">
        <div className="flex items-center justify-between">
          <div className="relative" ref={helpRef}>
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400">
                Membres actuels
              </span>
            </div>
            <p className="text-[10px] text-gray-400 dark:text-gray-600 mt-0.5 leading-snug">
              Le chef valide dispose de statistiques sur les membres de son épuipe.
            </p>
          </div>
          {groupe.membres.length > 0 && (
            <span className="text-[11px] tabular-nums text-gray-500 dark:text-gray-400 self-start mt-0.5">
              {groupe.membres.length}
            </span>
          )}
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {groupe.membres.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-14 px-5 text-center">
            <Users size={20} className="text-gray-300 dark:text-gray-600 mb-3" aria-hidden="true" />
            <p className="text-sm text-gray-500 dark:text-gray-400">Aucun membre</p>
            <p className="text-xs text-gray-400 dark:text-gray-600 mt-1 leading-relaxed">
              Ajoutez des gestionnaires<br />depuis le panneau de droite.
            </p>
          </div>
        ) : (
          groupe.membres.map((m: MembreSummary) => {
            const isPending = pendingChefId === m.id;
            const isConfirming = confirmCrown?.id === m.id;

            return (
              <div
                key={m.id}
                className="flex items-center gap-3 px-5 py-2.5 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors group"
              >
                {/* Avatar */}
                <div
                  aria-hidden="true"
                  className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-xs font-semibold ${
                    m.is_chef
                      ? "bg-amber-100 dark:bg-amber-400/15 text-amber-700 dark:text-amber-400"
                      : "bg-gray-100 dark:bg-white/10 text-gray-600 dark:text-gray-300"
                  }`}
                >
                  {initials(m)}
                </div>

                {/* Name + meta */}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate leading-snug">
                      {displayName(m)}
                    </p>
                    {m.is_chef && (
                      <span
                        title="Le chef valide en priorité les réponses IA de ce domaine."
                        className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full bg-amber-50 dark:bg-amber-400/10 border border-amber-200/60 dark:border-amber-400/20 text-amber-600 dark:text-amber-400 text-[10px] font-semibold shrink-0 leading-none cursor-help"
                      >
                        <Crown size={8} strokeWidth={2.5} aria-hidden="true" />
                        Chef
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 truncate leading-snug mt-0.5">
                    {m.departement ?? m.email}
                  </p>
                  {/* Live region for popconfirm — must be in DOM before content appears */}
                  <div aria-live="polite">
                    {isConfirming && (
                      <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                        <span className="text-[11px] text-gray-600 dark:text-gray-400 leading-tight">
                          {confirmCrown?.type === "demote-last"
                            ? "Retirer le seul chef ? Plus aucun validateur prioritaire ne sera désigné."
                            : "Désigner comme chef d'équipe ?"}
                        </span>
                        <button
                          onClick={() => {
                            onChef(m.id, confirmCrown?.type !== "demote-last");
                            setConfirmCrown(null);
                          }}
                          aria-label={
                            confirmCrown?.type === "demote-last"
                              ? `Confirmer la rétrogradation de ${displayName(m)}`
                              : `Confirmer la promotion de ${displayName(m)}`
                          }
                          className="flex items-center gap-0.5 px-1.5 py-0.5 rounded-md bg-amber-50 dark:bg-amber-400/10 text-amber-700 dark:text-amber-400 hover:bg-amber-100 dark:hover:bg-amber-400/20 text-[11px] font-medium transition-colors"
                        >
                          <Check size={10} aria-hidden="true" />
                          Oui
                        </button>
                        <button
                          onClick={() => setConfirmCrown(null)}
                          aria-label="Annuler"
                          className="flex items-center gap-0.5 px-1.5 py-0.5 rounded-md text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10 text-[11px] font-medium transition-colors"
                        >
                          <X size={10} aria-hidden="true" />
                          Non
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                {/* Actions — muted at rest for touch accessibility */}
                {!isConfirming && (
                  <div className="w-[52px] flex items-center justify-end gap-0.5 shrink-0 opacity-30 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity">
                    {isPending ? (
                      <span className="p-2">
                        <Loader2 size={13} className="animate-spin text-amber-400" aria-hidden="true" />
                      </span>
                    ) : (
                      <button
                        onClick={() => handleCrownClick(m)}
                        aria-label={
                          m.is_chef
                            ? `Retirer le rôle de chef à ${displayName(m)}`
                            : `Désigner ${displayName(m)} comme chef d'équipe`
                        }
                        className={`p-2 rounded-md transition-colors ${
                          m.is_chef
                            ? "text-amber-500 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-400/10"
                            : "text-gray-400 hover:text-amber-500 hover:bg-amber-50 dark:hover:bg-amber-400/10"
                        }`}
                      >
                        <Crown size={13} strokeWidth={m.is_chef ? 2.5 : 1.5} aria-hidden="true" />
                      </button>
                    )}
                    <button
                      onClick={() => onRetirer(m)}
                      aria-label={`Retirer ${displayName(m)} du groupe`}
                      className="p-2 rounded-md text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-400/10 transition-colors"
                    >
                      <UserMinus size={13} aria-hidden="true" />
                    </button>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
