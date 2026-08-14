import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Archive,
  BadgeCheck,
  ChevronLeft,
  ChevronRight,
  Search,
  X,
} from "lucide-react";
import {
  getReponsesCanoniques,
  getReponsesObsoletes,
  getReponsesARelire,
  confirmerActualite,
  confirmerActualiteLot,
  retirerReponse,
  editerReponseCanonique,
  supprimerReponseCanonique,
  restaurerReponse,
} from "../../../lib/api";
import type { ReponseCanonique, ReponseSignalee } from "../../../types.ts";
import DeleteModal from "./DeleteModal";
import RetraitModal from "./RetraitModal";
import TabARelire from "./TabARelire";
import TabCanoniques from "./TabCanoniques";
import TabObsoletes from "./TabObsoletes";
import { contenuServi, grouper, LIMIT, type CibleSuppression, type Onglet } from "./utils";

export default function SavedAnswers() {
  const queryClient = useQueryClient();
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

  const canoniques = useQuery({
    queryKey: ["reponses-canoniques", page],
    queryFn: () => getReponsesCanoniques({ page, limit: LIMIT }),
    placeholderData: (prev) => prev,
    enabled: onglet === "canoniques",
  });

  const obsoletes = useQuery({
    queryKey: ["reponses-obsoletes", "liste", page],
    queryFn: () => getReponsesObsoletes({ page, limit: LIMIT }),
    placeholderData: (prev) => prev,
    enabled: onglet === "obsoletes",
  });

  const aRelire = useQuery({
    queryKey: ["reponses-a-relire", "liste", page],
    queryFn: () => getReponsesARelire({ page, limit: LIMIT }),
    placeholderData: (prev) => prev,
    enabled: onglet === "a_relire",
  });

  const { data: compteur } = useQuery({
    queryKey: ["reponses-obsoletes", "count"],
    queryFn: () => getReponsesObsoletes({ page: 1, limit: 1 }),
    staleTime: 60_000,
  });
  const nbObsoletes = compteur?.total ?? 0;

  const { data: compteurARelire } = useQuery({
    queryKey: ["reponses-a-relire", "count"],
    queryFn: () => getReponsesARelire({ page: 1, limit: 1 }),
    staleTime: 60_000,
  });
  const nbDocsARelire = compteurARelire?.nb_documents ?? 0;

  const editMutation = useMutation({
    mutationFn: ({ id, contenu }: { id: string; contenu: string }) =>
      editerReponseCanonique(id, { contenu }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reponses-canoniques"] });
      queryClient.invalidateQueries({ queryKey: ["reponses-a-relire"] });
      setEditingId(null);
      setDraft("");
    },
  });

  const confirmMutation = useMutation({
    mutationFn: (id: string) => confirmerActualite(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reponses-a-relire"] });
      queryClient.invalidateQueries({ queryKey: ["reponses-canoniques"] });
    },
  });

  const confirmLotMutation = useMutation({
    mutationFn: ({ doc_id, version }: { doc_id: string; version: number }) =>
      confirmerActualiteLot(doc_id, version),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reponses-a-relire"] });
      queryClient.invalidateQueries({ queryKey: ["reponses-canoniques"] });
    },
  });

  const retirerMutation = useMutation({
    mutationFn: (id: string) => retirerReponse(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reponses-a-relire"] });
      queryClient.invalidateQueries({ queryKey: ["reponses-canoniques"] });
      queryClient.invalidateQueries({ queryKey: ["reponses-obsoletes"] });
      setRetraitTarget(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => supprimerReponseCanonique(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reponses-canoniques"] });
      queryClient.invalidateQueries({ queryKey: ["reponses-obsoletes"] });
      setDeleteTarget(null);
    },
  });

  const restoreMutation = useMutation({
    mutationFn: (id: string) => restaurerReponse(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reponses-obsoletes"] });
      queryClient.invalidateQueries({ queryKey: ["reponses-canoniques"] });
    },
  });

  const requete =
    onglet === "canoniques" ? canoniques : onglet === "obsoletes" ? obsoletes : aRelire;
  const loading = requete.isLoading;
  const error = requete.error;
  const total = requete.data?.total ?? 0;
  const totalPages = Math.ceil(total / LIMIT);
  const from = (page - 1) * LIMIT + 1;
  const to = Math.min(page * LIMIT, total);
  const groupes = grouper(aRelire.data?.items ?? []);

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
    cancelEdit();
  }

  function startEdit(r: ReponseCanonique | ReponseSignalee) {
    setEditingId(r.reponse_id);
    setDraft(contenuServi(r));
  }

  function cancelEdit() {
    setEditingId(null);
    setDraft("");
  }

  function saveEdit(id: string) {
    if (!draft.trim()) return;
    editMutation.mutate({ id, contenu: draft });
  }

  function toggleGroupe(cle: string) {
    setGroupesReplies((prev) => {
      const next = new Set(prev);
      if (next.has(cle)) next.delete(cle);
      else next.add(cle);
      return next;
    });
  }

  function ongletClasses(cible: Onglet) {
    return `flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 -mb-px transition-colors ${
      onglet === cible
        ? "border-emerald-500 text-gray-800 dark:text-gray-100"
        : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
    }`;
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-800 dark:text-gray-100">
          Réponses Enregistrées
        </h1>
      </div>

      <div className="glass-card rounded-2xl overflow-hidden">
        {/* Tabs */}
        <div
          className="flex items-center gap-1 px-4 border-b border-gray-200 dark:border-white/10"
          role="tablist"
        >
          <button
            role="tab"
            aria-selected={onglet === "canoniques"}
            onClick={() => changerOnglet("canoniques")}
            className={ongletClasses("canoniques")}
          >
            <BadgeCheck size={16} className="text-emerald-500" aria-hidden="true" />
            Canoniques
          </button>
          <button
            role="tab"
            aria-selected={onglet === "a_relire"}
            onClick={() => changerOnglet("a_relire")}
            className={ongletClasses("a_relire")}
          >
            <AlertTriangle size={16} className="text-amber-500" aria-hidden="true" />
            À relire
            {nbDocsARelire > 0 && (
              <span className="inline-flex items-center justify-center min-w-[1.25rem] px-1.5 py-0.5 rounded-full text-xs font-medium tabular-nums bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-300">
                {nbDocsARelire}
              </span>
            )}
          </button>
          <button
            role="tab"
            aria-selected={onglet === "obsoletes"}
            onClick={() => changerOnglet("obsoletes")}
            className={ongletClasses("obsoletes")}
          >
            <Archive size={16} className="text-gray-400" aria-hidden="true" />
            Obsolètes
            {nbObsoletes > 0 && (
              <span className="inline-flex items-center justify-center min-w-[1.25rem] px-1.5 py-0.5 rounded-full text-xs font-medium tabular-nums bg-gray-200 text-gray-700 dark:bg-white/10 dark:text-gray-300">
                {nbObsoletes}
              </span>
            )}
          </button>
        </div>

        {/* Bandeaux contextuels */}
        {onglet === "obsoletes" && (
          <p className="px-6 py-3 text-sm text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-white/10">
            Ces réponses ne sont plus servies : le passage du document sur lequel elles s'appuyaient
            a changé. Leurs validations sont conservées — les restaurer les remet en service telles
            quelles.
          </p>
        )}

        {onglet === "a_relire" && (
          <p className="px-6 py-3 text-sm text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-white/10">
            Ces réponses <span className="font-medium">continuent d'être servies</span> : le
            document dont elles sont issues a changé ailleurs que dans les passages qui les
            fondaient. Rien ne prouve qu'elles soient fausses — rien ne prouve l'inverse non plus.
            Lisez ce qui a changé, puis tranchez.
          </p>
        )}

        {onglet === "a_relire" && !loading && !error && total > 0 && (
          <div className="px-6 py-3 flex items-center justify-between border-b border-amber-100 dark:border-amber-500/20 bg-amber-50/50 dark:bg-amber-400/5">
            <p className="text-sm font-medium text-amber-900 dark:text-amber-300">
              {nbDocsARelire} document{nbDocsARelire > 1 ? "s" : ""} mis à jour
              {" · "}
              {total} réponse{total > 1 ? "s" : ""} à vérifier
            </p>
          </div>
        )}

        {/* Barre de recherche — Canoniques & Obsolètes */}
        {onglet !== "a_relire" && (
          <div className="px-6 py-3 border-b border-gray-200 dark:border-white/10">
            <div className="relative max-w-sm">
              <Search
                size={14}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none"
                aria-hidden="true"
              />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Chercher par question…"
                aria-label="Chercher par question"
                className="w-full pl-8 pr-8 py-1.5 text-sm rounded-xl border border-gray-200 dark:border-white/15 bg-white/60 dark:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 placeholder:text-gray-400"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  aria-label="Effacer la recherche"
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
                >
                  <X size={14} />
                </button>
              )}
            </div>
          </div>
        )}

        {/* Bandeau de stats — Canoniques */}
        {onglet === "canoniques" && !loading && !error && total > 0 && (
          <div className="px-6 py-2 flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-white/10">
            <span>
              {total} réponse{total > 1 ? "s" : ""} canonique{total > 1 ? "s" : ""} active
              {total > 1 ? "s" : ""}
            </span>
            {q && (
              <span className="text-emerald-600 dark:text-emerald-400">
                · {canoniquesItems.length} résultat{canoniquesItems.length !== 1 ? "s" : ""} sur cette page
              </span>
            )}
          </div>
        )}

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

        {/* Pagination */}
        {!loading && total > 0 && (
          <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 dark:border-white/10 text-sm text-gray-500 dark:text-gray-400">
            <span>
              {from}–{to} sur {total}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft size={16} />
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="p-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}
      </div>

      {retraitTarget && (
        <RetraitModal
          target={retraitTarget}
          mutation={retirerMutation}
          onClose={() => setRetraitTarget(null)}
        />
      )}

      {deleteTarget && (
        <DeleteModal
          target={deleteTarget}
          mutation={deleteMutation}
          onClose={() => setDeleteTarget(null)}
        />
      )}
    </div>
  );
}
