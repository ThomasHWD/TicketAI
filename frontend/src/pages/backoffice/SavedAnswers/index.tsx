import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { ReponseCanonique, ReponseSignalee } from "../../../types";
import DeleteModal from "./DeleteModal";
import RetraitModal from "./RetraitModal";
import SavedAnswersHeader from "./SavedAnswersHeader";
import TabARelire from "./TabARelire";
import TabCanoniques from "./TabCanoniques";
import TabObsoletes from "./TabObsoletes";
import { useSavedAnswersMutations } from "./useSavedAnswersMutations";
import { useSavedAnswersData } from "./useSavedAnswersData";
import { contenuServi, grouper, LIMIT, type CibleSuppression, type Onglet } from "./utils";

export default function SavedAnswers() {
  const [searchParams] = useSearchParams();
  const [onglet, setOnglet] = useState<Onglet>(
    (searchParams.get("onglet") as Onglet | null) ?? "canoniques"
  );
  const [page, setPage] = useState(1);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<CibleSuppression | null>(null);
  const [retraitTarget, setRetraitTarget] = useState<ReponseSignalee | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [groupesReplies, setGroupesReplies] = useState<Set<string>>(new Set());

  const { canoniques, obsoletes, aRelire, nbObsoletes, nbDocsARelire, requete } =
    useSavedAnswersData(onglet, page);

  const { editMutation, confirmMutation, confirmLotMutation, retirerMutation, deleteMutation, restoreMutation } =
    useSavedAnswersMutations({
      onEditSuccess: () => { setEditingId(null); setDraft(""); },
      onRetirerSuccess: () => setRetraitTarget(null),
      onDeleteSuccess: () => setDeleteTarget(null),
    });

  const loading = requete.isLoading;
  const error = requete.error;
  const total = requete.data?.total ?? 0;
  const totalPages = Math.ceil(total / LIMIT);
  const groupes = useMemo(() => grouper(aRelire.data?.items ?? []), [aRelire.data]);

  const q = searchQuery.trim().toLowerCase();
  const canoniquesItems = (canoniques.data?.items ?? []).filter(
    (r) => !q || r.question.toLowerCase().includes(q)
  );
  const obsoletesItems = (obsoletes.data?.items ?? []).filter(
    (r) => !q || r.question.toLowerCase().includes(q)
  );

  function changerOnglet(cible: Onglet) {
    setOnglet(cible);
    setPage(1);
    setSearchQuery("");
    setEditingId(null);
    setDraft("");
  }

  function startEdit(r: ReponseCanonique | ReponseSignalee) {
    setEditingId(r.reponse_id);
    setDraft(contenuServi(r));
  }

  function cancelEdit() { setEditingId(null); setDraft(""); }
  function saveEdit(id: string) { if (draft.trim()) editMutation.mutate({ id, contenu: draft }); }
  function toggleGroupe(cle: string) {
    setGroupesReplies((prev) => {
      const next = new Set(prev);
      if (next.has(cle)) next.delete(cle); else next.add(cle);
      return next;
    });
  }

  return (
    <div className="p-6 space-y-5">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-50 tracking-tight">
          Réponses enregistrées
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Base de connaissances validée — gère les réponses validées, les conflits de mise à jour et les retraits de service.
        </p>
      </div>

      <div className="glass-card rounded-2xl overflow-hidden">
        <SavedAnswersHeader
          onglet={onglet}
          nbDocsARelire={nbDocsARelire}
          nbObsoletes={nbObsoletes}
          searchQuery={searchQuery}
          loading={loading}
          error={error}
          total={total}
          canoniquesCount={canoniquesItems.length}
          onOngletChange={changerOnglet}
          onSearchChange={setSearchQuery}
        />

        {onglet === "canoniques" && (
          <TabCanoniques
            items={canoniquesItems}
            loading={loading}
            error={error}
            total={total}
            searchQuery={searchQuery}
            editingId={editingId}
            draft={draft}
            isPendingEdit={editMutation.isPending}
            onEdit={startEdit}
            onSave={saveEdit}
            onCancel={cancelEdit}
            onDraftChange={setDraft}
            onDeleteTarget={setDeleteTarget}
            onTabARelire={() => changerOnglet("a_relire")}
          />
        )}

        {onglet === "obsoletes" && (
          <TabObsoletes
            items={obsoletesItems}
            loading={loading}
            error={error}
            total={total}
            searchQuery={searchQuery}
            isPendingRestore={restoreMutation.isPending}
            restoreError={restoreMutation.isError ? restoreMutation.error : null}
            onRestore={(id) => restoreMutation.mutate(id)}
            onDeleteTarget={setDeleteTarget}
          />
        )}

        {onglet === "a_relire" && (
          <TabARelire
            groupes={groupes}
            loading={loading}
            error={error}
            total={total}
            groupesReplies={groupesReplies}
            editingId={editingId}
            draft={draft}
            isPendingEdit={editMutation.isPending}
            confirmMutation={confirmMutation}
            confirmLotMutation={confirmLotMutation}
            onToggleGroupe={toggleGroupe}
            onEdit={startEdit}
            onSave={saveEdit}
            onCancel={cancelEdit}
            onDraftChange={setDraft}
            onRetrait={setRetraitTarget}
          />
        )}

        {!loading && total > 0 && (
          <div className="flex items-center justify-between px-6 py-3.5 border-t border-gray-100 dark:border-white/8">
            <span className="text-xs text-gray-400 dark:text-gray-500 tabular-nums">
              {(page - 1) * LIMIT + 1}–{Math.min(page * LIMIT, total)} sur {total}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                aria-label="Page précédente"
                className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 dark:hover:text-gray-200 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft size={15} />
              </button>
              <span className="px-2 text-xs text-gray-500 dark:text-gray-400 tabular-nums">
                {page} / {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                aria-label="Page suivante"
                className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 dark:hover:text-gray-200 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronRight size={15} />
              </button>
            </div>
          </div>
        )}
      </div>

      {retraitTarget && (
        <RetraitModal target={retraitTarget} mutation={retirerMutation} onClose={() => setRetraitTarget(null)} />
      )}
      {deleteTarget && (
        <DeleteModal target={deleteTarget} mutation={deleteMutation} onClose={() => setDeleteTarget(null)} />
      )}
    </div>
  );
}
