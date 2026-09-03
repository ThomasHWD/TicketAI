import { CheckCircle2, FileSearch, FolderOpen } from "lucide-react";
import { useKnowledgeBase } from "../../../hooks/useKnowledgeBase";
import AnglesMorts from "./AnglesMorts";
import { EtatVide } from "./EtatVide";
import { KnowledgeBaseToolbar } from "./KnowledgeBaseToolbar";
import ChunksModal from "./ChunksModal";
import DeleteConfirm from "./DeleteConfirm";
import DocHistoryModal from "./DocHistoryModal";
import DocumentsTable from "./DocumentsTable";
import IngestionDrawer from "./IngestionDrawer";
import UpdateDocModal from "./UpdateDocModal";

export default function KnowledgeBase() {
  const kb = useKnowledgeBase();

  return (
    <div className="mx-auto max-w-6xl space-y-5 p-6">
      {/* En-tête */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-gray-900 dark:text-gray-50">
            Base de connaissances
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Les documents internes sur lesquels le moteur s'appuie pour répondre. Chaque version est archivée, et toute mise à jour fait relire les réponses concernées.
          </p>
        </div>
      </div>

      <div className="glass-card overflow-hidden rounded-2xl">
        <KnowledgeBaseToolbar
          onglet={kb.onglet}
          totalAngles={kb.totalAngles}
          onChangeOnglet={kb.changerOnglet}
          recherche={kb.recherche}
          onRecherche={kb.setRecherche}
          peutAjouter={kb.peutAjouter}
          onAjouter={() => kb.setDrawerOuvert(true)}
          visibles={kb.visibles}
          domaine={kb.domaine}
          onDomaine={kb.setDomaine}
          filtreEnMaj={kb.filtreEnMaj}
          onFiltreEnMaj={() => kb.setFiltreEnMaj((v) => !v)}
          hasEnMaj={kb.hasEnMaj}
          docsCount={kb.docs.length}
          total={kb.total}
          termes={kb.termes}
          isLoading={kb.isLoading}
          periode={kb.periode}
          onPeriode={(p) => kb.setPeriode(p as Parameters<typeof kb.setPeriode>[0])}
        />

        {/* Contenu — Documents */}
        {kb.onglet === "documents" && (
          <div role="tabpanel" id="panel-documents" aria-labelledby="tab-documents">
            {kb.isLoading ? (
              <div role="status" aria-label="Chargement des documents…" className="flex justify-center py-20">
                <svg className="animate-spin h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              </div>
            ) : kb.isError ? (
              <EtatVide
                icon={FileSearch}
                titre="Impossible de charger les documents."
                detail="La liste n'a pas pu être récupérée. Vérifiez votre connexion, puis réessayez."
                action={
                  <button type="button" onClick={() => kb.refetch()} className="mt-1 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50 dark:border-white/12 dark:text-gray-300 dark:hover:bg-white/5">
                    Réessayer
                  </button>
                }
              />
            ) : kb.docs.length === 0 ? (
              kb.termes.length ? (
                <EtatVide
                  icon={FileSearch}
                  titre="Aucun document ne correspond à la recherche."
                  detail="La recherche porte sur le nom du fichier et sa description, pas sur le contenu indexé."
                  action={
                    <button type="button" onClick={() => kb.setRecherche("")} className="mt-1 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50 dark:border-white/12 dark:text-gray-300 dark:hover:bg-white/5">
                      Afficher tous les documents
                    </button>
                  }
                />
              ) : (
                <EtatVide
                  icon={FolderOpen}
                  titre={kb.domaine ? `Aucun document indexé en ${kb.domaine}.` : "La base de connaissances est vide."}
                  detail={kb.domaine ? "Aucun document disponible dans ce domaine. Ajoutez-en un pour que l'IA puisse répondre aux questions de ce périmètre." : "Sans documents, l'IA ne peut pas répondre : aucune source citée, aucune réponse automatique possible. Ajoutez votre premier document pour simplifier vos réponses."}
                />
              )
            ) : (
              <DocumentsTable
                docs={kb.docs}
                estInscriptible={(doc) => kb.inscriptibles.includes(doc.domaine ?? "")}
                actions={kb.actions}
                highlightDocId={kb.highlightDocId}
              />
            )}
          </div>
        )}

        {/* Contenu — Angles morts */}
        {kb.onglet === "angles-morts" && (
          <div role="tabpanel" id="panel-angles-morts" aria-labelledby="tab-angles-morts">
            <AnglesMorts periode={kb.periode} />
          </div>
        )}
      </div>

      {/* Modals et drawers */}
      {kb.drawerOuvert && (
        <IngestionDrawer
          domaines={kb.visibles}
          onClose={() => kb.setDrawerOuvert(false)}
          onIndexed={() => kb.queryClient.invalidateQueries({ queryKey: ["documents"] })}
          onVoirDocument={kb.setRecherche}
          onDemanderMaj={(doc, fichier) => {
            kb.setDrawerOuvert(false);
            kb.setMaj({ doc, fichier });
          }}
        />
      )}

      {kb.consultation && (
        <ChunksModal doc={kb.consultation} onClose={() => kb.setConsultation(null)} />
      )}

      {kb.historique && (
        <DocHistoryModal
          doc={kb.historique}
          peutRestaurer={kb.inscriptibles.includes(kb.historique.domaine ?? "") && kb.historique.statut !== "EN_MAJ"}
          onClose={() => kb.setHistorique(null)}
          onImpact={(impact) => {
            kb.setMaj({ doc: kb.historique!, impact });
            kb.setHistorique(null);
          }}
        />
      )}

      {kb.maj && (
        <UpdateDocModal
          doc={kb.maj.doc}
          fichierInitial={kb.maj.fichier}
          impactInitial={kb.maj.impact}
          onClose={() => kb.setMaj(null)}
        />
      )}

      {kb.suppression && (
        <DeleteConfirm
          doc={kb.suppression}
          isPending={kb.supprimer.isPending}
          erreur={kb.supprimer.error instanceof Error ? kb.supprimer.error.message : null}
          onConfirm={() => kb.supprimer.mutate(kb.suppression!)}
          onCancel={() => { kb.supprimer.reset(); kb.setSuppression(null); }}
        />
      )}

      {kb.docSupprime && (
        <div role="status" aria-live="polite" className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-xs font-medium text-gray-700 shadow-md dark:border-white/12 dark:bg-[#1e1e21] dark:text-gray-300">
          <CheckCircle2 size={13} className="text-emerald-500" aria-hidden="true" />
          <span className="max-w-[240px] truncate">{kb.docSupprime}</span> supprimé de la base.
        </div>
      )}
    </div>
  );
}
