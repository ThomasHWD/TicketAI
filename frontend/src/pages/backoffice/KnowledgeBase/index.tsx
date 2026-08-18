import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileSearch, FolderOpen, Loader2, Plus, Search, X } from "lucide-react";
import { deleteDocument, listDocuments } from "../../../lib/api";
import type { Domaine, DocumentHomonyme, IndexedDocument, UpdateImpact } from "../../../types";
import ChunksModal from "./ChunksModal";
import DeleteConfirm from "./DeleteConfirm";
import DocHistoryModal from "./DocHistoryModal";
import DocumentsTable from "./DocumentsTable";
import IngestionDrawer from "./IngestionDrawer";
import UpdateDocModal from "./UpdateDocModal";
import { useDomaines } from "./useDomaines";

/** Ce que la mise à jour vise : un document listé, ou l'homonyme d'un fichier qu'on vient de déposer. */
type CibleMaj =
  | { doc: IndexedDocument; fichier?: undefined; impact?: undefined }
  | { doc: DocumentHomonyme; fichier: File; impact?: undefined }
  | { doc: IndexedDocument; fichier?: undefined; impact: UpdateImpact };

function EtatVide({
  icon: Icon,
  titre,
  detail,
  action,
}: {
  icon: typeof FolderOpen;
  titre: string;
  detail: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-20 text-center">
      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gray-100 dark:bg-white/5">
        <Icon size={18} className="text-gray-400 dark:text-gray-500" />
      </div>
      <p className="text-sm font-medium text-gray-700 dark:text-gray-300">{titre}</p>
      <p className="max-w-sm text-xs leading-relaxed text-gray-400 dark:text-gray-500">{detail}</p>
      {action}
    </div>
  );
}

/**
 * Base de connaissances : le catalogue des documents indexés **et** leur point
 * d'entrée. Consulter, ajouter, versionner et retirer se font au même endroit —
 * l'ancienne séparation « Indexation » / « Documents indexés » obligeait à
 * naviguer entre deux pages pour un seul geste.
 */
export default function KnowledgeBase() {
  const queryClient = useQueryClient();
  const { isAdmin, visibles, inscriptibles } = useDomaines();

  const [searchParams] = useSearchParams();
  const [recherche, setRecherche] = useState(searchParams.get("q") ?? "");
  const [domaine, setDomaine] = useState<Domaine | undefined>(undefined);

  const [drawerOuvert, setDrawerOuvert] = useState(false);
  const [consultation, setConsultation] = useState<IndexedDocument | null>(null);
  const [historique, setHistorique] = useState<IndexedDocument | null>(null);
  const [suppression, setSuppression] = useState<IndexedDocument | null>(null);
  const [maj, setMaj] = useState<CibleMaj | null>(null);

  // Un ADMIN sans filtre voit tout le catalogue ; sinon la liste est bornée à
  // ses domaines, même quand aucun filtre n'est actif.
  const domainesFiltres = isAdmin ? [] : domaine ? [domaine] : inscriptibles;

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["documents", domaine, isAdmin ? "admin" : inscriptibles],
    queryFn: () => listDocuments(domaine, domainesFiltres.length ? domainesFiltres : undefined),
  });

  const supprimer = useMutation({
    mutationFn: (doc: IndexedDocument) => deleteDocument(doc.doc_id),
    onSuccess: () => {
      setSuppression(null);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const termes = recherche.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const docs = (data?.items ?? []).filter((d) => {
    if (termes.length === 0) return true;
    const foin = `${d.filename ?? ""} ${d.description ?? ""}`.toLowerCase();
    return termes.every((t) => foin.includes(t));
  });

  const total = data?.total ?? 0;
  const peutAjouter = visibles.length > 0;

  const boutonAjouter = (
    <button
      type="button"
      onClick={() => setDrawerOuvert(true)}
      disabled={!peutAjouter}
      title={peutAjouter ? undefined : "Aucun domaine ne vous est attribué."}
      className="inline-flex items-center gap-1.5 rounded-lg bg-gray-900 px-3.5 py-2 text-sm font-medium text-white transition-colors hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100"
    >
      <Plus size={15} />
      Ajouter un document
    </button>
  );

  return (
    <div className="mx-auto max-w-6xl space-y-5 p-6">
      {/* En-tête */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-gray-900 dark:text-gray-50">
            Base de connaissances
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Les documents internes sur lesquels le moteur s'appuie pour répondre. Chaque version est
            archivée, et toute mise à jour fait relire les réponses concernées.
          </p>
        </div>
        {boutonAjouter}
      </div>

      <div className="glass-card overflow-hidden rounded-2xl">
        {/* Barre d'outils */}
        <div className="flex flex-wrap items-center gap-3 border-b border-gray-100 px-4 py-3 dark:border-white/8">
          <div className="relative">
            <Search
              size={13}
              className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400"
              aria-hidden="true"
            />
            <input
              type="search"
              value={recherche}
              onChange={(e) => setRecherche(e.target.value)}
              placeholder="Rechercher un document…"
              aria-label="Rechercher un document"
              className="w-56 rounded-lg border border-gray-200 bg-white py-1.5 pl-7 pr-7 text-xs text-gray-700 placeholder:text-gray-400 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:border-white/10 dark:bg-white/5 dark:text-gray-200 dark:placeholder:text-gray-500"
            />
            {recherche && (
              <button
                type="button"
                onClick={() => setRecherche("")}
                aria-label="Effacer la recherche"
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 transition-colors hover:text-gray-700 dark:hover:text-gray-200"
              >
                <X size={12} />
              </button>
            )}
          </div>

          {visibles.length > 1 && (
            <>
              <span
                aria-hidden="true"
                className="h-4 w-px bg-gray-200 dark:bg-white/10"
              />
              <div className="flex flex-wrap items-center gap-1">
                {([undefined, ...visibles] as Array<Domaine | undefined>).map((d) => (
                  <button
                    key={d ?? "tous"}
                    type="button"
                    onClick={() => setDomaine(d)}
                    aria-pressed={domaine === d}
                    className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                      domaine === d
                        ? "bg-gray-900 text-white dark:bg-white dark:text-gray-900"
                        : "text-gray-500 hover:bg-gray-100 hover:text-gray-800 dark:text-gray-400 dark:hover:bg-white/5 dark:hover:text-gray-200"
                    }`}
                  >
                    {d ?? "Tous"}
                  </button>
                ))}
              </div>
            </>
          )}

          <span className="ml-auto text-xs tabular-nums text-gray-400 dark:text-gray-500">
            {isLoading
              ? "…"
              : `${docs.length} document${docs.length > 1 ? "s" : ""}${
                  termes.length && docs.length !== total ? ` sur ${total}` : ""
                }`}
          </span>
        </div>

        {/* Contenu */}
        {isLoading ? (
          <div className="flex justify-center py-20">
            <Loader2 size={20} className="animate-spin text-gray-400" />
          </div>
        ) : isError ? (
          <EtatVide
            icon={FileSearch}
            titre="Impossible de charger les documents."
            detail="La liste n'a pas pu être récupérée. Vérifiez votre connexion, puis réessayez."
            action={
              <button
                type="button"
                onClick={() => refetch()}
                className="mt-1 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50 dark:border-white/12 dark:text-gray-300 dark:hover:bg-white/5"
              >
                Réessayer
              </button>
            }
          />
        ) : docs.length === 0 ? (
          termes.length ? (
            <EtatVide
              icon={FileSearch}
              titre="Aucun document ne correspond à la recherche."
              detail="La recherche porte sur le nom du fichier et sa description, pas sur le contenu indexé."
              action={
                <button
                  type="button"
                  onClick={() => setRecherche("")}
                  className="mt-1 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50 dark:border-white/12 dark:text-gray-300 dark:hover:bg-white/5"
                >
                  Afficher tous les documents
                </button>
              }
            />
          ) : (
            <EtatVide
              icon={FolderOpen}
              titre={`Aucun document indexé${domaine ? ` en ${domaine}` : ""}.`}
              detail="Tant que la base est vide, le moteur n'a rien à citer : chaque question partira en génération libre, puis en validation humaine."
              action={peutAjouter ? <div className="mt-1">{boutonAjouter}</div> : undefined}
            />
          )
        ) : (
          <DocumentsTable
            docs={docs}
            estInscriptible={(doc) => inscriptibles.includes(doc.domaine ?? "")}
            actions={{
              onVoir: setConsultation,
              onHistorique: setHistorique,
              onMettreAJour: (doc) => setMaj({ doc }),
              onSupprimer: setSuppression,
            }}
          />
        )}
      </div>

      {drawerOuvert && (
        <IngestionDrawer
          domaines={visibles}
          onClose={() => setDrawerOuvert(false)}
          onIndexed={() => queryClient.invalidateQueries({ queryKey: ["documents"] })}
          onVoirDocument={setRecherche}
          onDemanderMaj={(doc, fichier) => {
            setDrawerOuvert(false);
            setMaj({ doc, fichier });
          }}
        />
      )}

      {consultation && (
        <ChunksModal doc={consultation} onClose={() => setConsultation(null)} />
      )}

      {historique && (
        <DocHistoryModal
          doc={historique}
          peutRestaurer={
            inscriptibles.includes(historique.domaine ?? "") && historique.statut !== "EN_MAJ"
          }
          onClose={() => setHistorique(null)}
          onImpact={(impact) => {
            setMaj({ doc: historique, impact });
            setHistorique(null);
          }}
        />
      )}

      {maj && (
        <UpdateDocModal
          doc={maj.doc}
          fichierInitial={maj.fichier}
          impactInitial={maj.impact}
          onClose={() => setMaj(null)}
        />
      )}

      {suppression && (
        <DeleteConfirm
          doc={suppression}
          isPending={supprimer.isPending}
          erreur={supprimer.error instanceof Error ? supprimer.error.message : null}
          onConfirm={() => supprimer.mutate(suppression)}
          onCancel={() => {
            supprimer.reset();
            setSuppression(null);
          }}
        />
      )}
    </div>
  );
}
