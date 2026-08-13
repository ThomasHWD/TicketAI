import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Pencil,
  Trash2,
  Check,
  X,
  BadgeCheck,
  Archive,
  RotateCcw,
  AlertTriangle,
  CheckCircle2,
  EyeOff,
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
} from "../../lib/api";
import { formatDate } from "../../lib/ticketStatus";
import type { ReponseObsolete, ReponseSignalee } from "../../types.ts";

/** Contenu effectivement servi : la version corrigée prime sur l'originale. */
function contenuServi(r: { contenu: string; contenu_corrige: string | null }): string {
  return r.contenu_corrige ?? r.contenu;
}

const RELATIF = new Intl.RelativeTimeFormat("fr-FR", { numeric: "auto" });
const SEUILS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 86400],
  ["month", 30 * 86400],
  ["day", 86400],
  ["hour", 3600],
  ["minute", 60],
];

/** « il y a 3 jours ». La date exacte reste accessible en `title`. */
function depuis(iso: string | null): string {
  if (!iso) return "—";
  const secondes = (Date.now() - new Date(iso).getTime()) / 1000;
  for (const [unite, taille] of SEUILS) {
    if (secondes >= taille) return RELATIF.format(-Math.floor(secondes / taille), unite);
  }
  return RELATIF.format(-Math.floor(secondes), "second");
}

const LIMIT = 10;

type Onglet = "canoniques" | "obsoletes" | "a_relire";

/** Cible de la modale de suppression, commune aux deux onglets. */
type CibleSuppression = { reponse_id: string; question: string; obsolete: boolean };

/**
 * Un document et une version, avec les réponses qu'ils ont fait signaler.
 *
 * La clé inclut la version : un document remis à jour entre-temps a reflagué ses
 * réponses sur v(n+1), et les deux lots ne se confirment pas ensemble — ils ne
 * portent pas sur le même diff.
 */
type GroupeARelire = {
  cle: string;
  doc_id: string | null;
  version: number | null;
  filename: string | null;
  document_supprime: boolean;
  raison: ReponseSignalee["a_relire_raison"];
  changements: ReponseSignalee["changements"];
  reponses: ReponseSignalee[];
};

/**
 * Regroupe les réponses signalées par (document, version), dans l'ordre reçu.
 *
 * Le groupement est *tout* l'intérêt de l'écran : une phrase réécrite dans une
 * charte qui porte 40 réponses en signale 39. On lit le diff une fois, on juge
 * les 39 ensuite — une liste plate obligerait à relire le même diff 39 fois, et
 * l'onglet ne serait jamais vidé.
 *
 * Le backend trie déjà par `a_relire_doc_id` : les groupes sortent contigus, et
 * la Map conserve l'ordre d'insertion.
 */
function grouper(items: ReponseSignalee[]): GroupeARelire[] {
  const groupes = new Map<string, GroupeARelire>();
  for (const r of items) {
    const cle = `${r.doc_id ?? "?"}#${r.a_relire_version ?? "?"}`;
    const groupe = groupes.get(cle);
    if (groupe) {
      groupe.reponses.push(r);
    } else {
      groupes.set(cle, {
        cle,
        doc_id: r.doc_id,
        version: r.a_relire_version,
        filename: r.document_filename,
        document_supprime: r.document_supprime,
        raison: r.a_relire_raison,
        changements: r.changements,
        reponses: [r],
      });
    }
  }
  return [...groupes.values()];
}

/**
 * Ce que chaque raison veut dire, en une ligne.
 *
 * L'onglet ne reçoit plus « toutes les réponses du document » mais exactement ce
 * que la machine n'a pas pu trancher — et les cas ne se traitent pas pareil :
 * une contradiction probable se lit tout de suite, une panne d'analyse se relit
 * quand on a le temps. Taire la nuance rendrait la liste aussi indifférenciée
 * qu'avant.
 */
const RAISONS: Record<NonNullable<ReponseSignalee["a_relire_raison"]>, string> = {
  CONTREDITE_PROBABLE:
    "L'analyse juge cette réponse contredite, mais elle ne cite pas ce document : à confirmer avant tout retrait.",
  ANALYSE_EN_COURS: "Analyse en cours — le verdict n'est pas encore rendu.",
  ANALYSE_INDISPONIBLE:
    "Le service d'analyse n'a pas pu se prononcer : cette réponse est signalée par précaution.",
  ANALYSE_PARTIELLE:
    "Le budget d'analyse de cette mise à jour a été épuisé avant d'atteindre cette réponse.",
  REECRITURE_MASSIVE:
    "Le document a été réécrit en profondeur : trop de changements pour juger réponse par réponse.",
  DOC_MODIFIÉ: "L'analyse n'a pas su conclure : à trancher à la main.",
  VERSION_SORTANTE_ILLISIBLE:
    "La version précédente n'a pas pu être relue : impossible de dire ce qui a changé.",
};

/** État transitoire : rien à faire, il se résout tout seul en quelques minutes. */
const EN_ANALYSE = "ANALYSE_EN_COURS";

/**
 * Les raisons qui valent pour tout le document, donc portées par l'en-tête du
 * groupe. Aucune réponse n'a été jugée individuellement dans ces deux cas : les
 * répéter sur chaque carte reviendrait à écrire trente-neuf fois la même phrase.
 */
const RAISONS_DE_GROUPE = ["VERSION_SORTANTE_ILLISIBLE", "REECRITURE_MASSIVE"] as const;

function estRaisonDeGroupe(raison: ReponseSignalee["a_relire_raison"]): boolean {
  return RAISONS_DE_GROUPE.some((r) => r === raison);
}

/**
 * Pourquoi cette réponse-là est en cause, et ce que le modèle en a dit.
 *
 * Le diff est affiché une fois par groupe ; la justification, elle, est propre à
 * chaque réponse. C'est toute la différence entre « ce document a bougé » et
 * « voici ce qui contredit cette réponse » — sans elle, l'écran redemanderait à
 * l'humain le travail que l'analyse vient de faire.
 */
function MotifSignalement({ reponse }: { reponse: ReponseSignalee }) {
  const raison = reponse.a_relire_raison;
  const generique = raison && !estRaisonDeGroupe(raison) ? RAISONS[raison] : null;
  const message = reponse.analyse_justification ?? generique;
  if (!message) return null;

  const attention = raison === "CONTREDITE_PROBABLE";
  return (
    <p
      className={`flex items-start gap-1.5 text-xs ${
        attention
          ? "text-amber-700 dark:text-amber-300"
          : "text-gray-500 dark:text-gray-400"
      }`}
    >
      <AlertTriangle size={13} className="mt-0.5 shrink-0" />
      <span>{message}</span>
    </p>
  );
}

/** Les extraits d'un sens du changement, ou rien. */
function SensDuChangement({ titre, total, extraits }: { titre: string; total: number; extraits: string[] }) {
  if (total === 0) return null;

  return (
    <div className="space-y-1">
      <p className="text-[11px] font-medium uppercase tracking-wider text-amber-900/70 dark:text-amber-200/70">
        {total} passage{total > 1 ? "s" : ""} {titre}
        {total > 1 ? "s" : ""}
      </p>
      <ul className="space-y-1">
        {extraits.map((extrait, i) => (
          <li
            key={i}
            className="text-[11px] text-gray-600 dark:text-gray-400 font-mono leading-relaxed border-l-2 border-amber-300 dark:border-amber-500/40 pl-2"
          >
            {extrait}
          </li>
        ))}
      </ul>
      {total > extraits.length && (
        <p className="text-[11px] text-amber-900/70 dark:text-amber-200/70">
          … et {total - extraits.length} autre{total - extraits.length > 1 ? "s" : ""}.
        </p>
      )}
    </div>
  );
}

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
  // On mémorise les groupes *repliés*, pas les dépliés : un groupe s'ouvre donc
  // tout seul. Le diff est la seule chose qui permette de trancher — le cacher
  // derrière un clic ferait confirmer en lot sans l'avoir lu.
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

  // Compteur de l'onglet : requête distincte (limit 1) pour rester à jour même
  // depuis l'onglet Canoniques. Clé partagée avec le badge de la Sidebar.
  const { data: compteur } = useQuery({
    queryKey: ["reponses-obsoletes", "count"],
    queryFn: () => getReponsesObsoletes({ page: 1, limit: 1 }),
    staleTime: 60_000,
  });
  const nbObsoletes = compteur?.total ?? 0;

  // Le badge compte les **documents**, pas les réponses : « 2 documents à
  // relire » se traite, « 39 réponses » se subit — et c'est bien deux diffs
  // qu'il faut lire, pas trente-neuf.
  const { data: compteurARelire } = useQuery({
    queryKey: ["reponses-a-relire", "count"],
    queryFn: () => getReponsesARelire({ page: 1, limit: 1 }),
    staleTime: 60_000,
  });
  const nbDocsARelire = compteurARelire?.nb_documents ?? 0;

  // Éditer une réponse signalée vaut jugement : le drapeau tombe côté backend,
  // les deux listes bougent.
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

  // Retirer bascule vers les obsolètes, d'où la réponse reste restaurable.
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

  // Une réponse restaurée réapparaît côté canoniques : les deux listes bougent.
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
  const nbColonnes = onglet === "canoniques" ? 4 : 5;
  const groupes = grouper(aRelire.data?.items ?? []);

  function changerOnglet(cible: Onglet) {
    setOnglet(cible);
    setPage(1);
    cancelEdit();
  }

  function startEdit(r: { reponse_id: string; contenu: string; contenu_corrige: string | null }) {
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

  function ongletClasses(cible: Onglet) {
    return `flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 -mb-px transition-colors ${
      onglet === cible
        ? "border-emerald-500 text-gray-800 dark:text-gray-100"
        : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
    }`;
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-800 dark:text-gray-100">
          Réponses Enregistrées
        </h1>
      </div>

      {/* Card */}
      <div className="glass-card rounded-2xl overflow-hidden">
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

        {onglet === "obsoletes" && (
          <p className="px-6 py-3 text-sm text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-white/10">
            Ces réponses ne sont plus servies : le passage du document sur lequel
            elles s'appuyaient a changé. Leurs validations sont conservées — les
            restaurer les remet en service telles quelles.
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
              {" · "}{total} réponse{total > 1 ? "s" : ""} à vérifier
            </p>
          </div>
        )}

        {onglet === "a_relire" && (
          <div className="divide-y divide-gray-200 dark:divide-white/5">
            {loading && (
              <p className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">Chargement…</p>
            )}
            {error && (
              <p className="px-6 py-12 text-center text-red-600 dark:text-red-400">
                {error instanceof Error ? error.message : "Erreur de chargement"}
              </p>
            )}
            {!loading && !error && total === 0 && (
              <p className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">
                Aucune réponse à relire
              </p>
            )}

            {!loading &&
              groupes.map((g) => {
                const ouvert = !groupesReplies.has(g.cle);
                const toggleGroupe = () =>
                  setGroupesReplies((prev) => {
                    const next = new Set(prev);
                    if (next.has(g.cle)) next.delete(g.cle);
                    else next.add(g.cle);
                    return next;
                  });
                return (
                <section key={g.cle} className="px-6 py-5 space-y-4">
                  <div className="rounded-xl border border-amber-200 dark:border-amber-500/30 bg-amber-50/80 dark:bg-amber-400/10 px-4 py-3.5 space-y-2.5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <button
                        onClick={toggleGroupe}
                        className="min-w-0 flex-1 text-left"
                        aria-expanded={ouvert}
                      >
                        <p className="text-sm font-semibold text-amber-900 dark:text-amber-300 truncate flex items-center gap-1.5">
                          {g.filename ?? "Document inconnu"}
                          {g.version !== null && (
                            <span className="font-normal text-amber-900/70 dark:text-amber-200/70">
                              v{g.version}
                            </span>
                          )}
                          {ouvert ? (
                            <ChevronUp size={14} className="shrink-0 text-amber-700/60 dark:text-amber-300/60" />
                          ) : (
                            <ChevronDown size={14} className="shrink-0 text-amber-700/60 dark:text-amber-300/60" />
                          )}
                        </p>
                        <p className="mt-0.5 text-xs text-amber-900/80 dark:text-amber-200/80">
                          {g.reponses.length} réponse{g.reponses.length > 1 ? "s" : ""} sur cette
                          page
                          {g.document_supprime && " — document supprimé depuis"}
                        </p>
                      </button>
                      {g.doc_id !== null && g.version !== null && (
                        <button
                          onClick={() =>
                            confirmLotMutation.mutate({ doc_id: g.doc_id!, version: g.version! })
                          }
                          disabled={confirmLotMutation.isPending}
                          className="shrink-0 inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        >
                          <CheckCircle2 size={15} />
                          Tout confirmer
                        </button>
                      )}
                    </div>

                    {ouvert && (
                      estRaisonDeGroupe(g.raison) ? (
                        // Le signalement dit lui-même pourquoi il est bruyant : sans
                        // ça, un onglet plein sans un seul extrait passerait pour un bug.
                        <p className="text-xs text-amber-900/80 dark:text-amber-200/80">
                          {RAISONS[g.raison!]} Ces réponses sont signalées par précaution.
                        </p>
                      ) : g.changements ? (
                        <>
                          <SensDuChangement
                            titre="ajouté"
                            total={g.changements.nb_ajoutes}
                            extraits={g.changements.extraits_ajoutes}
                          />
                          <SensDuChangement
                            titre="retiré"
                            total={g.changements.nb_retires}
                            extraits={g.changements.extraits_retires}
                          />
                        </>
                      ) : (
                        <p className="text-xs text-amber-900/80 dark:text-amber-200/80">
                          Le détail de cette mise à jour n'a pas été conservé.
                        </p>
                      )
                    )}
                  </div>

                  <ul className="space-y-2">
                    {g.reponses.map((r) => {
                      const isEditing = editingId === r.reponse_id;
                      return (
                        <li
                          key={r.reponse_id}
                          className="rounded-xl border border-gray-200 dark:border-white/10 px-4 py-3 space-y-2"
                        >
                          <div className="flex items-start gap-2">
                            <p className="flex-1 min-w-0 text-sm text-gray-800 dark:text-gray-100">
                              {r.question}
                            </p>
                            {r.canonique && (
                              <span className="shrink-0 px-1.5 py-0.5 rounded-full text-[11px] font-medium bg-emerald-500/10 text-emerald-700 dark:text-emerald-300">
                                canonique
                              </span>
                            )}
                            <span className="shrink-0 text-[11px] text-gray-500 dark:text-gray-400 tabular-nums">
                              {r.nb_validations} val.
                            </span>
                          </div>

                          {isEditing ? (
                            <textarea
                              value={draft}
                              onChange={(e) => setDraft(e.target.value)}
                              rows={6}
                              autoFocus
                              className="w-full rounded-xl border border-gray-200 dark:border-white/15 bg-white/70 dark:bg-white/5 px-3 py-2 text-sm text-gray-800 dark:text-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
                            />
                          ) : (
                            <p className="text-sm text-gray-600 dark:text-gray-300 whitespace-pre-wrap">
                              {contenuServi(r)}
                            </p>
                          )}

                          <MotifSignalement reponse={r} />

                          {/* `ANALYSE_EN_COURS` est transitoire : proposer de trancher
                              maintenant reviendrait à faire juger l'humain avant la
                              machine, et sa décision serait écrasée dans deux minutes. */}
                          {r.a_relire_raison === EN_ANALYSE ? (
                            <p className="text-right text-[11px] text-gray-400 dark:text-gray-500">
                              Résultat dans quelques minutes.
                            </p>
                          ) : (
                          <div className="flex items-center justify-end gap-1.5">
                            {isEditing ? (
                              <>
                                <button
                                  onClick={() => saveEdit(r.reponse_id)}
                                  disabled={!draft.trim() || editMutation.isPending}
                                  title="Enregistrer"
                                  aria-label="Enregistrer"
                                  className="p-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                                >
                                  <Check size={16} />
                                </button>
                                <button
                                  onClick={cancelEdit}
                                  title="Annuler"
                                  aria-label="Annuler"
                                  className="p-1.5 rounded-lg border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 transition-colors"
                                >
                                  <X size={16} />
                                </button>
                              </>
                            ) : (
                              <>
                                <button
                                  onClick={() => confirmMutation.mutate(r.reponse_id)}
                                  disabled={confirmMutation.isPending}
                                  title="Toujours d'actualité : lever le signalement"
                                  aria-label="Toujours d'actualité"
                                  className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-emerald-200 dark:border-emerald-500/20 text-emerald-600 dark:text-emerald-300 text-xs font-medium hover:bg-emerald-50 dark:hover:bg-emerald-500/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                                >
                                  <CheckCircle2 size={15} />
                                  Toujours d'actualité
                                </button>
                                <button
                                  onClick={() => startEdit(r)}
                                  title="Modifier"
                                  aria-label="Modifier la réponse"
                                  className="p-1.5 rounded-lg border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 transition-colors"
                                >
                                  <Pencil size={16} />
                                </button>
                                <button
                                  onClick={() => setRetraitTarget(r)}
                                  title="Retirer du service"
                                  aria-label="Retirer la réponse du service"
                                  className="p-1.5 rounded-lg border border-amber-200 dark:border-amber-500/25 text-amber-700 dark:text-amber-300 hover:bg-amber-50 dark:hover:bg-amber-500/10 transition-colors"
                                >
                                  <EyeOff size={16} />
                                </button>
                              </>
                            )}
                          </div>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </section>
                );
              })}

            {(confirmMutation.isError || confirmLotMutation.isError) && (
              <p className="px-6 py-3 text-sm text-red-600 dark:text-red-400">
                Erreur de confirmation : le signalement n'a pas été levé.
              </p>
            )}
          </div>
        )}

        {onglet !== "a_relire" && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-green-100 dark:bg-emerald-400/10 text-green-700 dark:text-emerald-300 text-left">
                <th className="px-6 py-3 font-medium">Question</th>
                <th className="px-6 py-3 font-medium">Réponse servie</th>
                {onglet === "canoniques" ? (
                  <th className="px-6 py-3 font-medium text-center whitespace-nowrap">Fois posée</th>
                ) : (
                  <>
                    <th className="px-6 py-3 font-medium">Document</th>
                    <th className="px-6 py-3 font-medium whitespace-nowrap">Depuis</th>
                  </>
                )}
                <th className="px-6 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-white/5">
              {loading && (
                <tr>
                  <td colSpan={nbColonnes} className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">
                    Chargement…
                  </td>
                </tr>
              )}
              {error && (
                <tr>
                  <td colSpan={nbColonnes} className="px-6 py-12 text-center text-red-600 dark:text-red-400">
                    {error instanceof Error ? error.message : "Erreur de chargement"}
                  </td>
                </tr>
              )}
              {!loading && !error && total === 0 && (
                <tr>
                  <td colSpan={nbColonnes} className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">
                    {onglet === "canoniques"
                      ? "Aucune réponse enregistrée"
                      : "Aucune réponse obsolète"}
                  </td>
                </tr>
              )}

              {!loading &&
                onglet === "canoniques" &&
                (canoniques.data?.items ?? []).map((r) => {
                  const isEditing = editingId === r.reponse_id;
                  return (
                    <tr
                      key={r.reponse_id}
                      className="align-top hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                    >
                      <td className="px-6 py-4 text-gray-700 dark:text-gray-200">
                        <span className="block max-w-xs" title={r.question}>
                          {r.question}
                        </span>
                        {/* Elle est encore servie, donc encore ici : la pastille est
                            le seul endroit où cet écran dit qu'elle n'est plus acquise. */}
                        {r.a_relire && (
                          <button
                            onClick={() => changerOnglet("a_relire")}
                            className="mt-1 inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-300 hover:bg-amber-200 dark:hover:bg-amber-400/25 transition-colors"
                            title="Le document source a changé — voir l'onglet À relire"
                          >
                            <AlertTriangle size={11} aria-hidden="true" />À relire
                          </button>
                        )}
                      </td>
                      <td className="px-6 py-4 text-gray-600 dark:text-gray-300">
                        {isEditing ? (
                          <textarea
                            value={draft}
                            onChange={(e) => setDraft(e.target.value)}
                            rows={5}
                            autoFocus
                            className="w-full min-w-[18rem] rounded-xl border border-gray-200 dark:border-white/15 bg-white/70 dark:bg-white/5 px-3 py-2 text-sm text-gray-800 dark:text-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
                          />
                        ) : (
                          <span className="block max-w-md whitespace-pre-wrap">
                            {contenuServi(r)}
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-4 text-center whitespace-nowrap">
                        <span
                          className="inline-flex items-center justify-center min-w-[2rem] px-2 py-0.5 rounded-full text-xs font-medium tabular-nums bg-emerald-500/10 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
                          title={`Réponse auto-servie ${r.occurence} fois`}
                        >
                          {r.occurence}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center justify-end gap-1.5">
                          {isEditing ? (
                            <>
                              <button
                                onClick={() => saveEdit(r.reponse_id)}
                                disabled={!draft.trim() || editMutation.isPending}
                                title="Enregistrer"
                                aria-label="Enregistrer"
                                className="p-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                              >
                                <Check size={16} />
                              </button>
                              <button
                                onClick={cancelEdit}
                                title="Annuler"
                                aria-label="Annuler"
                                className="p-1.5 rounded-lg border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 transition-colors"
                              >
                                <X size={16} />
                              </button>
                            </>
                          ) : (
                            <>
                              <button
                                onClick={() => startEdit(r)}
                                title="Modifier"
                                aria-label="Modifier la réponse"
                                className="p-1.5 rounded-lg border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 transition-colors"
                              >
                                <Pencil size={16} />
                              </button>
                              <button
                                onClick={() =>
                                  setDeleteTarget({
                                    reponse_id: r.reponse_id,
                                    question: r.question,
                                    obsolete: false,
                                  })
                                }
                                title="Supprimer"
                                aria-label="Supprimer la réponse"
                                className="p-1.5 rounded-lg border border-red-200 dark:border-red-500/20 text-red-600 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                              >
                                <Trash2 size={16} />
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}

              {!loading &&
                onglet === "obsoletes" &&
                (obsoletes.data?.items ?? []).map((r: ReponseObsolete) => (
                  <tr
                    key={r.reponse_id}
                    className="align-top hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                  >
                    <td className="px-6 py-4 text-gray-700 dark:text-gray-200">
                      <span className="block max-w-xs" title={r.question}>
                        {r.question}
                      </span>
                      <span className="mt-1 flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
                        {r.canonique && (
                          <span className="inline-flex items-center px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-700 dark:text-emerald-300">
                            canonique
                          </span>
                        )}
                        {r.nb_validations} validation{r.nb_validations > 1 ? "s" : ""}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-gray-600 dark:text-gray-300">
                      <span className="block max-w-md whitespace-pre-wrap">{contenuServi(r)}</span>
                      {/* Le retrait est sec — aucune correction n'est rédigée à la
                          place. C'est cette phrase qui le rend défendable : sans
                          elle, on voit une réponse disparue et rien qui dise pourquoi. */}
                      {r.analyse_justification && (
                        <span className="mt-1.5 flex max-w-md items-start gap-1.5 text-xs text-amber-700 dark:text-amber-300">
                          <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                          <span>{r.analyse_justification}</span>
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-gray-600 dark:text-gray-300">
                      <span
                        className="block max-w-[12rem] truncate"
                        title={r.document_filename ?? undefined}
                      >
                        {r.document_filename ?? "Document inconnu"}
                      </span>
                      <span className="mt-1 inline-flex items-center px-1.5 py-0.5 rounded-full text-xs bg-gray-100 text-gray-600 dark:bg-white/10 dark:text-gray-300">
                        {r.document_supprime
                          ? "supprimé"
                          : r.obsolete_version
                            ? `v${r.obsolete_version}`
                            : "mis à jour"}
                      </span>
                    </td>
                    <td
                      className="px-6 py-4 whitespace-nowrap text-gray-500 dark:text-gray-400"
                      title={formatDate(r.obsolete_at)}
                    >
                      {depuis(r.obsolete_at)}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          onClick={() => restoreMutation.mutate(r.reponse_id)}
                          disabled={restoreMutation.isPending}
                          title="Restaurer : remettre cette réponse en service"
                          aria-label="Restaurer la réponse"
                          className="p-1.5 rounded-lg border border-emerald-200 dark:border-emerald-500/20 text-emerald-600 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-500/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        >
                          <RotateCcw size={16} />
                        </button>
                        <button
                          onClick={() =>
                            setDeleteTarget({
                              reponse_id: r.reponse_id,
                              question: r.question,
                              obsolete: true,
                            })
                          }
                          title="Supprimer définitivement"
                          aria-label="Supprimer définitivement la réponse"
                          className="p-1.5 rounded-lg border border-red-200 dark:border-red-500/20 text-red-600 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
        )}

        {restoreMutation.isError && (
          <p className="px-6 py-3 text-sm text-red-600 dark:text-red-400 border-t border-gray-200 dark:border-white/10">
            {restoreMutation.error instanceof Error
              ? restoreMutation.error.message
              : "Erreur de restauration"}
          </p>
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

      {/* Retirer du service : moins qu'une suppression, et réversible — la modale
          doit le dire, sinon on hésitera et l'onglet ne se videra pas. */}
      {retraitTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-label="Confirmer le retrait"
          onClick={() => !retirerMutation.isPending && setRetraitTarget(null)}
        >
          <div
            className="w-full max-w-md rounded-2xl border border-white/60 dark:border-white/10 bg-white dark:bg-[#0b0f1a] p-6 shadow-[0_8px_40px_0_rgba(0,0,0,0.25)]"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100">
              Retirer cette réponse du service ?
            </h3>
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
              La réponse à «&nbsp;{retraitTarget.question}&nbsp;» ne sera plus servie
              automatiquement : les questions similaires repasseront par la génération. Elle rejoint
              l'onglet <span className="font-medium">Obsolètes</span>, d'où elle reste restaurable —
              ses validations sont conservées.
            </p>
            {retirerMutation.isError && (
              <p className="mt-3 text-sm text-red-600 dark:text-red-400">
                {retirerMutation.error instanceof Error
                  ? retirerMutation.error.message
                  : "Erreur de retrait"}
              </p>
            )}
            <div className="mt-6 flex items-center justify-end gap-2">
              <button
                onClick={() => setRetraitTarget(null)}
                disabled={retirerMutation.isPending}
                className="px-4 py-2 rounded-xl border border-gray-200 dark:border-white/15 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 disabled:opacity-40 transition-colors"
              >
                Annuler
              </button>
              <button
                onClick={() => retirerMutation.mutate(retraitTarget.reponse_id)}
                disabled={retirerMutation.isPending}
                className="px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-600 text-white text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {retirerMutation.isPending ? "Retrait…" : "Retirer du service"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modale de confirmation de suppression */}
      {deleteTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-label="Confirmer la suppression"
          onClick={() => !deleteMutation.isPending && setDeleteTarget(null)}
        >
          <div
            className="w-full max-w-md rounded-2xl border border-white/60 dark:border-white/10 bg-white dark:bg-[#0b0f1a] p-6 shadow-[0_8px_40px_0_rgba(0,0,0,0.25)]"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100">
              {deleteTarget.obsolete
                ? "Supprimer définitivement cette réponse ?"
                : "Supprimer cette réponse canonique ?"}
            </h3>
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
              La réponse à «&nbsp;{deleteTarget.question}&nbsp;» sera supprimée
              définitivement.{" "}
              {deleteTarget.obsolete
                ? "Elle ne pourra plus être restaurée."
                : "Les futures questions similaires repasseront par le pipeline de génération normal."}{" "}
              Cette action est irréversible.
            </p>
            {deleteMutation.isError && (
              <p className="mt-3 text-sm text-red-600 dark:text-red-400">
                {deleteMutation.error instanceof Error
                  ? deleteMutation.error.message
                  : "Erreur de suppression"}
              </p>
            )}
            <div className="mt-6 flex items-center justify-end gap-2">
              <button
                onClick={() => setDeleteTarget(null)}
                disabled={deleteMutation.isPending}
                className="px-4 py-2 rounded-xl border border-gray-200 dark:border-white/15 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 disabled:opacity-40 transition-colors"
              >
                Annuler
              </button>
              <button
                onClick={() => deleteMutation.mutate(deleteTarget.reponse_id)}
                disabled={deleteMutation.isPending}
                className="px-4 py-2 rounded-xl bg-red-500 hover:bg-red-600 text-white text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {deleteMutation.isPending ? "Suppression…" : "Supprimer"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
