import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Download,
  Eye,
  Files,
  History,
  Loader2,
  RefreshCw,
  Search,
  Trash2,
} from "lucide-react";
import { apiFetch, listDocuments, deleteDocument, downloadDocument } from "../../../lib/api";
import { useAuth } from "../../../lib/auth";
import UpdateDocModal from "../UpdateDocModal";
import DocHistoryModal from "../DocHistoryModal";
import type { Domaine, IndexedDocument, UpdateImpact } from "../../../types";
import ChunksModal from "./ChunksModal";
import DeleteConfirm from "./DeleteConfirm";

const ACTION_BTN =
  "p-2 rounded-lg border border-gray-300 dark:border-white/15 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors";

async function fetchDomaines(): Promise<string[]> {
  const res = await apiFetch("/api/v1/admin/domaines");
  const data = await res.json();
  return Array.isArray(data) ? data : [];
}

export default function AllDocs() {
  const queryClient = useQueryClient();
  const { userDomaines, user } = useAuth();
  const isAdmin = user?.role === "ADMIN";
  const [domaine, setDomaine] = useState<Domaine | undefined>(undefined);
  const [searchParams] = useSearchParams();
  const [search, setSearch] = useState(searchParams.get("q") ?? "");
  const [viewing, setViewing] = useState<IndexedDocument | null>(null);
  const [confirming, setConfirming] = useState<IndexedDocument | null>(null);
  const [updating, setUpdating] = useState<IndexedDocument | null>(null);
  const [historyOf, setHistoryOf] = useState<IndexedDocument | null>(null);
  const [restauration, setRestauration] = useState<{
    doc: IndexedDocument;
    impact: UpdateImpact;
  } | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);

  const { data: adminDomaines = [] } = useQuery({
    queryKey: ["admin", "domaines"],
    queryFn: fetchDomaines,
    staleTime: 5 * 60 * 1000,
    enabled: isAdmin,
  });

  const availableDomaines = isAdmin ? adminDomaines : userDomaines;
  const domainesFiltres = isAdmin ? [] : domaine ? [domaine] : userDomaines;

  const { data, isLoading, isError } = useQuery({
    queryKey: ["documents", domaine, isAdmin ? "admin" : userDomaines],
    queryFn: () => listDocuments(domaine, domainesFiltres.length ? domainesFiltres : undefined),
  });

  const { mutate: doDelete, isPending: isDeleting } = useMutation({
    mutationFn: (doc: IndexedDocument) => deleteDocument(doc.doc_id),
    onSuccess: () => {
      setConfirming(null);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const terms = search.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const docs = (data?.items ?? []).filter((d) => {
    if (terms.length === 0) return true;
    const haystack = `${d.filename ?? ""} ${d.description ?? ""}`.toLowerCase();
    return terms.every((t) => haystack.includes(t));
  });

  return (
    <>
      <div className="p-6 max-w-4xl mx-auto">
        <div className="glass-card rounded-2xl overflow-hidden">
          <div className="px-7 pt-7 pb-6">
            <div className="flex items-center gap-3 mb-1">
              <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-green-100 dark:bg-emerald-400/15">
                <Files size={18} className="text-green-700 dark:text-emerald-400" />
              </div>
              <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
                Documents indexés
              </h1>
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400 ml-12">
              Consultez et gérez les documents importés.
            </p>
          </div>

          <hr className="border-black/[0.06] dark:border-white/10" />

          {(isAdmin || availableDomaines.length > 1) && (
            <>
              <div className="px-7 py-5">
                <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-3">
                  Filtrer par domaine
                </p>
                <div className="flex flex-wrap gap-2">
                  {([undefined, ...availableDomaines] as Array<Domaine | undefined>).map((d) => (
                    <button
                      key={d ?? "tous"}
                      onClick={() => setDomaine(d)}
                      className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${
                        domaine === d
                          ? "bg-green-100 dark:bg-emerald-400/15 text-green-700 dark:text-emerald-300 border-green-300 dark:border-emerald-500/40"
                          : "bg-gray-50 dark:bg-white/5 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-white/10 hover:bg-gray-100 dark:hover:bg-white/10"
                      }`}
                    >
                      {d ?? "Tous"}
                    </button>
                  ))}
                </div>
              </div>
              <hr className="border-black/[0.06] dark:border-white/10" />
            </>
          )}

          <div className="px-7 py-4">
            <div className="relative">
              <Search
                size={15}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500 pointer-events-none"
              />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Rechercher par titre ou description…"
                className="w-full pl-9 pr-3 py-2 rounded-lg text-sm border border-gray-300 dark:border-white/15 bg-white/70 dark:bg-white/5 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-green-400/50 dark:focus:ring-emerald-400/40"
              />
            </div>
          </div>

          <hr className="border-black/[0.06] dark:border-white/10" />

          <div className="px-7 py-5">
            {isLoading ? (
              <div className="flex justify-center py-12">
                <Loader2 size={22} className="animate-spin text-gray-400" />
              </div>
            ) : isError ? (
              <p className="text-sm text-red-600 dark:text-red-400 text-center py-8">
                Impossible de charger les documents.
              </p>
            ) : docs.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-12">
                {terms.length
                  ? "Aucun document ne correspond à la recherche."
                  : `Aucun document indexé${domaine ? ` en ${domaine}` : ""}.`}
              </p>
            ) : (
              <div className="space-y-2">
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                  {docs.length} document{docs.length > 1 ? "s" : ""}
                  {terms.length && data && docs.length !== data.total
                    ? ` sur ${data.total}`
                    : ""}
                </p>
                {docs.map((doc) => {
                  const enMaj = doc.statut === "EN_MAJ";
                  const peutEcrire = userDomaines.includes(doc.domaine ?? "");
                  return (
                    <div
                      key={doc.doc_id}
                      className="flex items-center gap-4 px-4 py-3.5 rounded-xl border border-black/[0.06] dark:border-white/10 bg-white/60 dark:bg-white/[0.03] hover:bg-white/80 dark:hover:bg-white/[0.05] transition-colors"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                          {doc.filename ?? "—"}
                        </p>
                        <p className="text-xs text-gray-500 dark:text-gray-500 mt-0.5 truncate">
                          {doc.description || <span className="italic">Aucune description</span>}
                        </p>
                      </div>
                      <div className="flex items-center gap-3 shrink-0">
                        {enMaj ? (
                          <span className="flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-medium bg-amber-100 dark:bg-amber-400/15 text-amber-700 dark:text-amber-300 whitespace-nowrap">
                            <Loader2 size={12} className="animate-spin" />
                            Mise à jour en cours…
                          </span>
                        ) : (
                          <span className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">
                            v{doc.version} — {doc.nb_chunks} chunk{doc.nb_chunks > 1 ? "s" : ""}
                          </span>
                        )}
                        <div className="flex items-center gap-1.5">
                          <button
                            onClick={() => setViewing(doc)}
                            title="Voir les chunks"
                            className={ACTION_BTN}
                          >
                            <Eye size={14} />
                          </button>
                          <button
                            onClick={async () => {
                              setDownloading(doc.doc_id);
                              try {
                                await downloadDocument(doc.doc_id, doc.filename);
                              } finally {
                                setDownloading(null);
                              }
                            }}
                            disabled={downloading === doc.doc_id}
                            title="Télécharger la version courante"
                            className={ACTION_BTN}
                          >
                            {downloading === doc.doc_id ? (
                              <Loader2 size={14} className="animate-spin" />
                            ) : (
                              <Download size={14} />
                            )}
                          </button>
                          <button
                            onClick={() => setHistoryOf(doc)}
                            title={`Historique des versions (${doc.nb_versions})`}
                            className={ACTION_BTN}
                          >
                            <History size={14} />
                          </button>
                          {peutEcrire && (
                            <button
                              onClick={() => setUpdating(doc)}
                              disabled={enMaj}
                              title="Mettre à jour : remplacer par une nouvelle version"
                              className={ACTION_BTN}
                            >
                              <RefreshCw size={14} />
                            </button>
                          )}
                          {peutEcrire && (
                            <button
                              onClick={() => setConfirming(doc)}
                              disabled={enMaj}
                              title="Supprimer"
                              className="p-2 rounded-lg border border-red-200 dark:border-red-500/25 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                            >
                              <Trash2 size={14} />
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {viewing && <ChunksModal doc={viewing} onClose={() => setViewing(null)} />}
      {updating && <UpdateDocModal doc={updating} onClose={() => setUpdating(null)} />}
      {historyOf && (
        <DocHistoryModal
          doc={historyOf}
          peutRestaurer={
            userDomaines.includes(historyOf.domaine ?? "") && historyOf.statut !== "EN_MAJ"
          }
          onClose={() => setHistoryOf(null)}
          onImpact={(impact) => {
            setRestauration({ doc: historyOf, impact });
            setHistoryOf(null);
          }}
        />
      )}
      {restauration && (
        <UpdateDocModal
          doc={restauration.doc}
          impactInitial={restauration.impact}
          onClose={() => setRestauration(null)}
        />
      )}
      {confirming && (
        <DeleteConfirm
          doc={confirming}
          onConfirm={() => doDelete(confirming)}
          onCancel={() => setConfirming(null)}
          isPending={isDeleting}
        />
      )}
    </>
  );
}
