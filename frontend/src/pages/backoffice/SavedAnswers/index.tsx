import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CheckCircle2, ChevronLeft, ChevronRight } from "lucide-react";
import type { ReponseCanonique, ReponseSignalee } from "../../../types";
import { useAuth } from "../../../lib/auth";
import DeleteModal from "./DeleteModal";
import RetraitModal from "./RetraitModal";
import UnsavedDraftModal from "./UnsavedDraftModal";
import SavedAnswersHeader from "./SavedAnswersHeader";
import TabARelire from "./TabARelire";
import TabCanoniques from "./TabCanoniques";
import TabObsoletes from "./TabObsoletes";
import { useSavedAnswersMutations } from "./useSavedAnswersMutations";
import { useSavedAnswersData } from "./useSavedAnswersData";
import { contenuServi, grouper, LIMIT, type CibleSuppression, type Onglet } from "./utils";

export default function SavedAnswers() {
  const { userDomaines } = useAuth();
  const [searchParams] = useSearchParams();
  const [onglet, setOnglet] = useState<Onglet>(
    (searchParams.get("onglet") as Onglet | null) ?? "canoniques"
  );
  const [domaine, setDomaine] = useState<string | undefined>(undefined);
  const [tag, setTag] = useState<string | undefined>(undefined);
  const [page, setPage] = useState(1);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<CibleSuppression | null>(null);
  const [retraitTarget, setRetraitTarget] = useState<ReponseSignalee | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [groupesReplies, setGroupesReplies] = useState<Set<string>>(new Set());
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [editingOriginal, setEditingOriginal] = useState("");
  const [pendingEdit, setPendingEdit] = useState<ReponseCanonique | ReponseSignalee | null>(null);

  const showSuccess = useCallback((msg: string) => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setSuccessMsg(msg);
    toastTimer.current = setTimeout(() => setSuccessMsg(null), 3000);
  }, []);

  const { canoniques, obsoletes, aRelire, nbObsoletes, nbDocsARelire, requete, tagsDisponibles } =
    useSavedAnswersData(onglet, page, searchQuery, domaine, tag);

  const { editMutation, confirmMutation, confirmLotMutation, retirerMutation, deleteMutation, restoreMutation } =
    useSavedAnswersMutations({
      onEditSuccess: () => { setEditingId(null); setDraft(""); setEditingOriginal(""); showSuccess("Réponse modifiée."); },
      onRetirerSuccess: () => { setRetraitTarget(null); showSuccess("Réponse retirée du service."); },
      onDeleteSuccess: () => { setDeleteTarget(null); showSuccess("Réponse supprimée."); },
      onConfirmSuccess: () => showSuccess("Réponse confirmée."),
      onConfirmLotSuccess: () => showSuccess("Toutes les réponses confirmées."),
      onRestoreSuccess: () => showSuccess("Réponse restaurée."),
    });

  const loading = requete.isLoading;
  const isFetching = requete.isFetching && !requete.isLoading;
  const error = requete.error;
  const total = requete.data?.total ?? 0;
  const totalPages = Math.ceil(total / LIMIT);
  useEffect(() => { if (totalPages > 0 && page > totalPages) setPage(totalPages); }, [totalPages, page]);
  const groupes = useMemo(() => grouper(aRelire.data?.items ?? []), [aRelire.data]);

  const canoniquesItems = canoniques.data?.items ?? [];
  const obsoletesItems = obsoletes.data?.items ?? [];

  function changerOnglet(cible: Onglet) {
    setOnglet(cible);
    setPage(1);
    setSearchQuery("");
    setTag(undefined);
    setEditingId(null);
    setDraft("");
    setEditingOriginal("");
  }

  function changerDomaine(d: string | undefined) {
    setDomaine(d);
    setTag(undefined);
    setPage(1);
  }

  function changerTag(t: string | undefined) {
    setTag(t);
    setPage(1);
  }

  function changerSearch(q: string) {
    setSearchQuery(q);
    setPage(1);
  }

  function commitEdit(r: ReponseCanonique | ReponseSignalee) {
    const content = contenuServi(r);
    setEditingId(r.reponse_id);
    setDraft(content);
    setEditingOriginal(content);
    setPendingEdit(null);
  }

  function startEdit(r: ReponseCanonique | ReponseSignalee) {
    if (editingId !== null && draft !== editingOriginal) {
      setPendingEdit(r);
      return;
    }
    commitEdit(r);
  }

  function cancelEdit() { setEditingId(null); setDraft(""); setEditingOriginal(""); }
  function saveEdit(id: string) { if (draft.trim()) editMutation.mutate({ id, contenu: draft }); }
  function toggleGroupe(cle: string) {
    setGroupesReplies((prev) => {
      const next = new Set(prev);
      if (next.has(cle)) next.delete(cle); else next.add(cle);
      return next;
    });
  }
  function collapseAll() { setGroupesReplies(new Set(groupes.map((g) => g.cle))); }
  function expandAll() { setGroupesReplies(new Set()); }

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

      {/* Persistent live region — toujours dans le DOM pour compatibilité SR legacy */}
      <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
        {loading && !successMsg ? "Chargement en cours…" : (successMsg ?? "")}
      </div>

      <div className="glass-card rounded-2xl overflow-hidden">
        <SavedAnswersHeader
          onglet={onglet}
          nbDocsARelire={nbDocsARelire}
          nbObsoletes={nbObsoletes}
          searchQuery={searchQuery}
          loading={loading}
          isFetching={isFetching}
          error={error}
          total={total}
          canoniquesCount={canoniquesItems.length}
          domaines={userDomaines}
          domaine={domaine}
          tag={tag}
          tagsDisponibles={tagsDisponibles}
          onOngletChange={changerOnglet}
          onSearchChange={changerSearch}
          onDomaine={changerDomaine}
          onTag={changerTag}
        />

        <div
          id="panel-canoniques"
          role="tabpanel"
          aria-labelledby="tab-canoniques"
          tabIndex={onglet === "canoniques" ? 0 : -1}
          hidden={onglet !== "canoniques"}
          className="focus-visible:outline-none"
        >
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
            onRetry={() => requete.refetch()}
          />
        </div>

        <div
          id="panel-a_relire"
          role="tabpanel"
          aria-labelledby="tab-a_relire"
          tabIndex={onglet === "a_relire" ? 0 : -1}
          hidden={onglet !== "a_relire"}
          className="focus-visible:outline-none"
        >
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
            onCollapseAll={collapseAll}
            onExpandAll={expandAll}
            onRetry={() => requete.refetch()}
            onEdit={startEdit}
            onSave={saveEdit}
            onCancel={cancelEdit}
            onDraftChange={setDraft}
            onRetrait={setRetraitTarget}
          />
        </div>

        <div
          id="panel-obsoletes"
          role="tabpanel"
          aria-labelledby="tab-obsoletes"
          tabIndex={onglet === "obsoletes" ? 0 : -1}
          hidden={onglet !== "obsoletes"}
          className="focus-visible:outline-none"
        >
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
            onRetry={() => requete.refetch()}
          />
        </div>

        {!loading && total > 0 && onglet !== "a_relire" && (
          <nav aria-label="Pagination des réponses" className="flex items-center justify-between px-6 py-3.5 border-t border-gray-100 dark:border-white/8">
            <span className="text-xs text-gray-500 dark:text-gray-400 tabular-nums">
              {(page - 1) * LIMIT + 1}–{Math.min(page * LIMIT, total)} sur {total}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                aria-label="Page précédente"
                className="min-w-[44px] min-h-[44px] flex items-center justify-center rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 dark:hover:text-gray-200 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60"
              >
                <ChevronLeft size={15} aria-hidden="true" />
              </button>
              <span className="px-2 text-xs text-gray-500 dark:text-gray-400 tabular-nums">
                {page} / {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                aria-label="Page suivante"
                className="min-w-[44px] min-h-[44px] flex items-center justify-center rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 dark:hover:text-gray-200 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60"
              >
                <ChevronRight size={15} aria-hidden="true" />
              </button>
            </div>
          </nav>
        )}
      </div>

      {pendingEdit && (
        <UnsavedDraftModal
          onConfirm={() => commitEdit(pendingEdit)}
          onCancel={() => setPendingEdit(null)}
        />
      )}
      {retraitTarget && (
        <RetraitModal target={retraitTarget} mutation={retirerMutation} onClose={() => setRetraitTarget(null)} />
      )}
      {deleteTarget && (
        <DeleteModal target={deleteTarget} mutation={deleteMutation} onClose={() => setDeleteTarget(null)} />
      )}

      {successMsg && (
        <div
          aria-hidden="true"
          className="fixed bottom-5 right-5 z-50 flex items-center gap-2.5 px-4 py-3 rounded-xl bg-emerald-600 text-white text-sm font-medium shadow-[0_4px_24px_0_rgba(0,0,0,0.18)]"
        >
          <CheckCircle2 size={15} aria-hidden="true" />
          {successMsg}
        </div>
      )}
    </div>
  );
}
