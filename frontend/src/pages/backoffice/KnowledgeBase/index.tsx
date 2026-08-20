import { useState } from "react";
import { useNavigate, useSearchParams, useLocation } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, FileSearch, FolderOpen, Loader2, Plus, Search, X } from "lucide-react";
import { deleteDocument, listDocuments } from "../../../lib/api";
import { getHorsDomaine, masquerAngleMort } from "../../../lib/api/stats";
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

// ─── Angles morts ────────────────────────────────────────────────────────────

const PERIODES = [
  { value: "semaine", label: "Cette semaine" },
  { value: "mois",    label: "Ce mois" },
  { value: "annee",   label: "Cette année" },
] as const;
type PeriodeId = typeof PERIODES[number]["value"];

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(iso));
}

function AnglesMorts({ periode }: { periode: PeriodeId }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data = [], isLoading } = useQuery({
    queryKey: ["angles-morts", periode],
    queryFn: () => getHorsDomaine(periode),
    staleTime: 60_000,
  });

  const { mutate: masquer } = useMutation({
    mutationFn: masquerAngleMort,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["angles-morts"] }),
  });

  if (isLoading) return <AnglesMortsSkeleton />;
  if (data.length === 0) return <AnglesMortsEmptyState />;

  return (
    <div className="divide-y divide-gray-100 dark:divide-white/[0.06]">
      {data.map((entry) => (
        <div key={entry.domaine}>
          <div className="flex items-center justify-between gap-3 bg-gray-50/60 dark:bg-white/[0.02] px-5 py-2.5 border-b border-gray-100 dark:border-white/[0.06]">
            <span className="text-xs font-semibold uppercase tracking-[0.05em] text-gray-500 dark:text-gray-400">
              {entry.domaine}
            </span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold tabular-nums bg-purple-50 dark:bg-purple-500/15 text-purple-700 dark:text-purple-300 border border-purple-200/60 dark:border-purple-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-purple-500 dark:bg-purple-400" aria-hidden="true" />
              {entry.nb_tickets} ticket{entry.nb_tickets > 1 ? "s" : ""}
            </span>
          </div>
          <ul className="divide-y divide-gray-100 dark:divide-white/[0.04]">
            {entry.questions.map((q) => (
              <li key={q.id} className="group flex items-stretch">
                <button
                  onClick={() => navigate(`/tickets/${q.id}`)}
                  className="flex-1 min-w-0 flex items-center gap-4 pl-5 pr-3 py-3.5 text-left hover:bg-gray-50/70 dark:hover:bg-white/[0.03] transition-colors duration-75"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-800 dark:text-gray-100 truncate leading-snug">
                      {q.objet ?? q.question.slice(0, 100)}
                    </p>
                    {q.objet && (
                      <p className="text-xs text-gray-400 dark:text-gray-500 truncate mt-0.5">
                        {q.question.slice(0, 120)}
                      </p>
                    )}
                  </div>
                  <span className="text-xs text-gray-400 dark:text-gray-500 shrink-0 tabular-nums">
                    {formatDate(q.created_at)}
                  </span>
                  <ArrowRight
                    size={13}
                    className="text-gray-300 dark:text-white/20 shrink-0 group-hover:text-gray-500 dark:group-hover:text-gray-400 group-hover:translate-x-0.5 transition-all duration-75"
                    aria-hidden="true"
                  />
                </button>
                <button
                  onClick={() => masquer(q.id)}
                  title="Marquer comme traité"
                  className="shrink-0 flex items-center justify-center w-10 border-l border-gray-100 dark:border-white/[0.05] text-gray-300 dark:text-white/20 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 opacity-0 group-hover:opacity-100 transition-all duration-100"
                >
                  <X size={13} />
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function AnglesMortsSkeleton() {
  return (
    <div className="animate-pulse divide-y divide-gray-100 dark:divide-white/[0.06]">
      {[
        { rows: 4, widths: [72, 58, 85, 64] },
        { rows: 2, widths: [55, 78, 0, 0] },
      ].map(({ rows, widths }, i) => (
        <div key={i}>
          <div className="bg-gray-50/60 dark:bg-white/[0.02] px-5 py-2.5 border-b border-gray-100 dark:border-white/[0.06] flex items-center justify-between">
            <div className="h-3 w-14 bg-gray-200 dark:bg-white/10 rounded" />
            <div className="h-4 w-20 bg-purple-100 dark:bg-purple-500/10 rounded-full" />
          </div>
          <div className="divide-y divide-gray-100 dark:divide-white/[0.04]">
            {Array.from({ length: rows }).map((_, j) => (
              <div key={j} className="px-5 py-3.5 flex items-center gap-4">
                <div className="flex-1">
                  <div className="h-3.5 bg-gray-100 dark:bg-white/[0.07] rounded" style={{ width: `${widths[j]}%` }} />
                </div>
                <div className="h-3 w-16 bg-gray-100 dark:bg-white/[0.05] rounded shrink-0" />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function AnglesMortsEmptyState() {
  return (
    <div className="flex flex-col items-center gap-3 py-16 text-center px-8">
      <div className="flex items-center justify-center w-11 h-11 rounded-2xl bg-emerald-50 dark:bg-emerald-500/10 mb-1">
        <CheckCircle2 size={20} className="text-emerald-500 dark:text-emerald-400" aria-hidden="true" />
      </div>
      <div>
        <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">Aucun angle mort sur cette période</p>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-1.5 max-w-xs mx-auto leading-relaxed">
          Toutes les questions ont pu être traitées depuis les documents disponibles.
        </p>
      </div>
    </div>
  );
}

// ─── Documents ────────────────────────────────────────────────────────────────

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

// ─── Page principale ──────────────────────────────────────────────────────────

const ONGLETS = [
  { id: "documents",    label: "Documents" },
  { id: "angles-morts", label: "Angles morts" },
] as const;
type OngletId = typeof ONGLETS[number]["id"];

/**
 * Base de connaissances : documents indexés + angles morts.
 * L'onglet « Angles morts » (anciennement /angles-morts) s'active via
 * ?onglet=angles-morts ; la route /angles-morts redirige ici.
 */
export default function KnowledgeBase() {
  const queryClient = useQueryClient();
  const { isAdmin, visibles, inscriptibles } = useDomaines();
  const location = useLocation();
  const highlightDocId = (location.state as { highlight?: string } | null)?.highlight;

  const [searchParams, setSearchParams] = useSearchParams();
  const ongletParam = searchParams.get("onglet") as OngletId | null;
  const onglet: OngletId = ongletParam === "angles-morts" ? "angles-morts" : "documents";

  const [recherche, setRecherche] = useState(searchParams.get("q") ?? "");
  const [domaine, setDomaine] = useState<Domaine | undefined>(undefined);
  const [periode, setPeriode] = useState<PeriodeId>("mois");

  function changerOnglet(id: OngletId) {
    setSearchParams(id === "documents" ? {} : { onglet: id }, { replace: true });
  }

  const [drawerOuvert, setDrawerOuvert] = useState(false);
  const [consultation, setConsultation] = useState<IndexedDocument | null>(null);
  const [historique, setHistorique] = useState<IndexedDocument | null>(null);
  const [suppression, setSuppression] = useState<IndexedDocument | null>(null);
  const [maj, setMaj] = useState<CibleMaj | null>(null);

  const domainesFiltres = isAdmin ? [] : domaine ? [domaine] : inscriptibles;

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["documents", domaine, isAdmin ? "admin" : inscriptibles],
    queryFn: () => listDocuments(domaine, domainesFiltres.length ? domainesFiltres : undefined),
  });

  // Pré-charge angles morts pour le badge (même clé que AnglesMorts → cache partagé)
  const { data: anglesData = [] } = useQuery({
    queryKey: ["angles-morts", periode],
    queryFn: () => getHorsDomaine(periode),
    staleTime: 60_000,
  });
  const totalAngles = anglesData.reduce((sum, e) => sum + e.nb_tickets, 0);

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
      className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 dark:border-white/10 px-2.5 py-1.5 text-xs font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors disabled:cursor-not-allowed disabled:opacity-40"
    >
      <Plus size={13} />
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
            Les documents internes sur lesquels le moteur s'appuie pour répondre. Chaque version est archivée, et toute mise à jour fait relire les réponses concernées.
          </p>
        </div>
      </div>

      <div className="glass-card overflow-hidden rounded-2xl">
        {/* Barre onglets + contrôles */}
        <div className="flex flex-wrap items-stretch border-b border-gray-100 dark:border-white/8 px-4">
          {/* Onglets — underline style */}
          <div className="flex items-stretch">
            {ONGLETS.map((o) => (
              <button
                key={o.id}
                type="button"
                onClick={() => changerOnglet(o.id)}
                className={`relative flex items-center gap-1.5 px-0.5 mr-6 py-3 text-sm font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 ${
                  onglet === o.id
                    ? "text-gray-900 dark:text-gray-50"
                    : "text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
                }`}
              >
                {o.label}
                {o.id === "angles-morts" && totalAngles > 0 && (
                  <span className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-semibold tabular-nums bg-purple-100 dark:bg-purple-500/20 text-purple-700 dark:text-purple-300">
                    {totalAngles > 99 ? "99+" : totalAngles}
                  </span>
                )}
                {onglet === o.id && (
                  <span
                    className="absolute bottom-0 left-0 right-0 h-0.5 bg-emerald-500 rounded-full"
                    aria-hidden="true"
                  />
                )}
              </button>
            ))}
          </div>

          {/* Contrôles contextuels (droite) */}
          <div className="ml-auto flex items-center gap-3 py-2">
            {boutonAjouter}
            <span aria-hidden="true" className="h-4 w-px bg-gray-200 dark:bg-white/10" />
            {onglet === "documents" && (
              <>
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
                    className="w-52 rounded-lg border border-gray-200 bg-white py-1.5 pl-7 pr-7 text-xs text-gray-700 placeholder:text-gray-400 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:border-white/10 dark:bg-white/5 dark:text-gray-200 dark:placeholder:text-gray-500"
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
                    <span aria-hidden="true" className="h-4 w-px bg-gray-200 dark:bg-white/10" />
                    <div className="flex items-center gap-1">
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

                <span className="text-xs tabular-nums text-gray-400 dark:text-gray-500">
                  {isLoading
                    ? "…"
                    : `${docs.length} document${docs.length > 1 ? "s" : ""}${
                        termes.length && docs.length !== total ? ` sur ${total}` : ""
                      }`}
                </span>

              </>
            )}

            {onglet === "angles-morts" && (
              <div className="flex items-center gap-0.5 p-0.5 rounded-lg bg-gray-100/80 dark:bg-white/[0.06] border border-gray-200/50 dark:border-white/[0.06]">
                {PERIODES.map((p) => (
                  <button
                    key={p.value}
                    onClick={() => setPeriode(p.value)}
                    className={`px-2.5 py-1 rounded-md text-xs font-medium transition-all duration-150 ${
                      periode === p.value
                        ? "bg-white dark:bg-white/15 text-gray-900 dark:text-gray-100 shadow-sm"
                        : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Contenu — Documents */}
        {onglet === "documents" && (
          isLoading ? (
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
                detail="Tant que la base est vide, le moteur n'a rien à citer : chaque question devra être rédigée manuellement."
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
              highlightDocId={highlightDocId}
            />
          )
        )}

        {/* Contenu — Angles morts (flat dans le glass-card parent) */}
        {onglet === "angles-morts" && <AnglesMorts periode={periode} />}
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
