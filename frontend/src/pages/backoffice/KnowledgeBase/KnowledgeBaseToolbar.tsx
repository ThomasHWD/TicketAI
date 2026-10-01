import { Plus, Search, X } from "lucide-react";
import { PERIODES } from "./AnglesMorts";
import { ONGLETS } from "../../../hooks/useKnowledgeBase";
import type { OngletId } from "../../../hooks/useKnowledgeBase";
import type { Domaine } from "../../../types";

interface KnowledgeBaseToolbarProps {
  onglet: OngletId;
  totalAngles: number;
  onChangeOnglet: (id: OngletId) => void;
  recherche: string;
  onRecherche: (v: string) => void;
  peutAjouter: boolean;
  onAjouter: () => void;
  visibles: string[];
  domaine: Domaine | undefined;
  onDomaine: (d: Domaine | undefined) => void;
  filtreEnMaj: boolean;
  onFiltreEnMaj: () => void;
  hasEnMaj: boolean;
  docsCount: number;
  total: number;
  termes: string[];
  isLoading: boolean;
  periode: string;
  onPeriode: (p: string) => void;
}

export function KnowledgeBaseToolbar({
  onglet, totalAngles, onChangeOnglet,
  recherche, onRecherche, peutAjouter, onAjouter,
  visibles, domaine, onDomaine,
  filtreEnMaj, onFiltreEnMaj, hasEnMaj,
  docsCount, total, termes, isLoading,
  periode, onPeriode,
}: KnowledgeBaseToolbarProps) {
  return (
    <div className="flex items-stretch border-b border-gray-100 dark:border-white/8 px-4 overflow-x-auto">
      {/* Onglets — underline style */}
      <div role="tablist" className="flex items-stretch">
        {ONGLETS.map((o) => (
          <button
            key={o.id}
            type="button"
            role="tab"
            id={`tab-${o.id}`}
            aria-selected={onglet === o.id}
            aria-controls={`panel-${o.id}`}
            onClick={() => onChangeOnglet(o.id)}
            className={`relative flex items-center gap-1.5 px-0.5 mr-6 py-3 text-sm font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 ${
              onglet === o.id
                ? "text-gray-900 dark:text-gray-50"
                : "text-muted-foreground hover:text-gray-600 dark:hover:text-gray-300"
            }`}
          >
            {o.id === "angles-morts" ? (
              <span title="Questions restées sans réponse satisfaisante depuis la base actuelle">{o.label}</span>
            ) : o.label}
            {o.id === "angles-morts" && totalAngles > 0 && (
              <span className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-semibold tabular-nums bg-purple-100 dark:bg-purple-500/20 text-purple-700 dark:text-purple-300">
                {totalAngles > 99 ? "99+" : totalAngles}
              </span>
            )}
            {onglet === o.id && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-emerald-500 rounded-full" aria-hidden="true" />
            )}
          </button>
        ))}
      </div>

      {/* Contrôles contextuels (droite) */}
      <div className="ml-auto flex items-center gap-3 py-2">
        {onglet === "documents" && (
          <>
            <div className="relative">
              <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-subtle" aria-hidden="true" />
              <input
                type="search"
                value={recherche}
                onChange={(e) => onRecherche(e.target.value)}
                placeholder="Rechercher un document…"
                aria-label="Rechercher un document"
                className="w-60 rounded-lg border border-gray-200 bg-white py-1.5 pl-7 pr-7 text-xs text-gray-700 placeholder:text-muted-foreground focus:border-transparent focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:border-white/10 dark:bg-white/5 dark:text-gray-200"
              />
              {recherche && (
                <button type="button" onClick={() => onRecherche("")} aria-label="Effacer la recherche" className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-gray-700 dark:hover:text-gray-200">
                  <X size={12} />
                </button>
              )}
            </div>
            <span aria-hidden="true" className="h-4 w-px bg-gray-200 dark:bg-white/10" />
            <button
              type="button"
              onClick={onAjouter}
              disabled={!peutAjouter}
              title={peutAjouter ? undefined : "Aucun domaine ne vous est attribué."}
              className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 transition-colors disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Plus size={13} className="text-emerald-500 dark:text-emerald-400" aria-hidden="true" />
              Ajouter un document
            </button>

            {visibles.length > 1 && (
              <>
                <span aria-hidden="true" className="h-4 w-px bg-gray-200 dark:bg-white/10" />
                <div role="group" aria-label="Filtrer par domaine" className="flex items-center gap-1">
                  {([undefined, ...visibles] as Array<Domaine | undefined>).map((d) => (
                    <button
                      key={d ?? "tous"}
                      type="button"
                      onClick={() => onDomaine(d)}
                      aria-pressed={domaine === d}
                      className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                        domaine === d
                          ? "bg-gray-900 text-white dark:bg-white dark:text-gray-900"
                          : "text-muted-foreground hover:bg-gray-100 hover:text-gray-800 dark:hover:bg-white/5 dark:hover:text-gray-200"
                      }`}
                    >
                      {d ?? "Tous"}
                    </button>
                  ))}
                </div>
              </>
            )}

            {hasEnMaj && (
              <>
                <span aria-hidden="true" className="h-4 w-px bg-gray-200 dark:bg-white/10" />
                <button
                  type="button"
                  aria-pressed={filtreEnMaj}
                  onClick={onFiltreEnMaj}
                  className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                    filtreEnMaj
                      ? "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300"
                      : "text-muted-foreground hover:bg-gray-100 hover:text-gray-800 dark:hover:bg-white/5"
                  }`}
                >
                  En cours de mise à jour
                </button>
              </>
            )}

            <span className="text-xs tabular-nums text-muted-foreground">
              {isLoading
                ? "…"
                : `${docsCount} document${docsCount > 1 ? "s" : ""}${termes.length && docsCount !== total ? ` sur ${total}` : ""}`}
            </span>
          </>
        )}

        {onglet === "angles-morts" && (
          <>
            <button
              type="button"
              onClick={onAjouter}
              disabled={!peutAjouter}
              title={peutAjouter ? undefined : "Aucun domaine ne vous est attribué."}
              className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 transition-colors disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Plus size={13} className="text-emerald-500 dark:text-emerald-400" aria-hidden="true" />
              Ajouter un document
            </button>
            <span aria-hidden="true" className="h-4 w-px bg-gray-200 dark:bg-white/10" />
            <div role="group" aria-label="Période d'analyse" className="flex items-center gap-0.5 p-0.5 rounded-lg bg-gray-100/80 dark:bg-white/[0.06] border border-gray-200/50 dark:border-white/[0.06]">
              {PERIODES.map((p) => (
                <button
                  key={p.value}
                  type="button"
                  aria-pressed={periode === p.value}
                  onClick={() => onPeriode(p.value)}
                  className={`px-2.5 py-2 rounded-md text-xs font-medium transition-all duration-150 ${
                    periode === p.value
                      ? "bg-white dark:bg-white/15 text-gray-900 dark:text-gray-100 shadow-sm"
                      : "text-muted-foreground hover:text-gray-700 dark:hover:text-gray-200"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
