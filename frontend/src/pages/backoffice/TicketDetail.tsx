import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Pencil, X, Check, ThumbsUp } from "lucide-react";
import { getTicket, getReponsesByTicket, corrigerReponse, validerReponse } from "../../lib/api";
import type { Ticket, TicketReponse, StatutTicket, StatutReponse } from "../../types.ts";

const VALIDATOR_ID = "00000000-0000-0000-0000-000000000001";

const MOCK_OBJET = "Demande de clarification sur la politique de télétravail";

const MOCK_AUTHOR = {
  name: "Sophie Martin",
  role: "Responsable RH",
  department: "Ressources Humaines",
  avatar: "SM",
  email: "sophie.martin@entreprise.fr",
  phone: "+33 6 12 34 56 78",
};

function ticketStatutLabel(statut: StatutTicket, canonique: boolean) {
  if (canonique) return "Canonique";
  if (statut === "VALIDÉ") return "Validée";
  if (statut === "RÉPONDU") return "Suggestion";
  if (statut === "REJETÉ") return "Rejetée";
  return "Nouvelle";
}

function ticketStatutClass(statut: StatutTicket, canonique: boolean) {
  if (statut === "REJETÉ") return "bg-red-50 text-red-600 border-red-200";
  if (canonique) return "bg-emerald-50 text-emerald-600 border-emerald-200";
  if (statut === "VALIDÉ") return "bg-blue-50 text-blue-600 border-blue-200";
  if (statut === "RÉPONDU") return "bg-yellow-50 text-yellow-600 border-yellow-200";
  return "bg-gray-100 text-gray-500 border-gray-200";
}

function reponseStatutLabel(statut: StatutReponse, canonique: boolean) {
  if (statut === "VALIDÉE" || statut === "CORRIGÉE") return canonique ? "Canonique" : "Validée";
  if (statut === "REJETÉE") return "Rejetée";
  if (statut === "EN_ATTENTE") return "En attente";
  return statut;
}

function reponseStatutClass(statut: StatutReponse, canonique: boolean) {
  if (statut === "REJETÉE") return "bg-red-50 text-red-600 border-red-200";
  if ((statut === "VALIDÉE" || statut === "CORRIGÉE") && canonique)
    return "bg-emerald-50 text-emerald-600 border-emerald-200";
  if (statut === "VALIDÉE" || statut === "CORRIGÉE")
    return "bg-blue-50 text-blue-600 border-blue-200";
  return "bg-yellow-50 text-yellow-600 border-yellow-200";
}

function StatutBadge({ statut, canonique }: { statut: StatutTicket; canonique: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${ticketStatutClass(statut, canonique)}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current" aria-hidden="true" />
      {ticketStatutLabel(statut, canonique)}
    </span>
  );
}

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  }).format(new Date(iso));
}

const DOMAINE_LABEL: Record<string, string> = {
  IT: "Informatique",
  RH: "Ressources humaines",
  JURIDIQUE: "Juridique",
};

const SOURCE_LABEL: Record<string, string> = {
  LLM: "Généré par IA",
  SUGGESTION: "Suggestion",
  CANONIQUE: "Canonique",
};

function ReponseItem({
  reponse,
  onUpdated,
}: {
  reponse: TicketReponse;
  onUpdated: (id: string, patch: Partial<TicketReponse>) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(reponse.contenu);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canAct = reponse.statut === "EN_ATTENTE";

  async function handleValider() {
    setLoading(true);
    setError(null);
    try {
      const res = await validerReponse(reponse.id, { validator_id: VALIDATOR_ID });
      onUpdated(reponse.id, { statut: "VALIDÉE", nb_validations: res.nb_validations, canonique: res.canonique });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erreur");
    } finally {
      setLoading(false);
    }
  }

  async function handleCorriger() {
    if (!draft.trim() || draft === reponse.contenu) { setEditing(false); return; }
    setLoading(true);
    setError(null);
    try {
      await corrigerReponse(reponse.id, { contenu_corrige: draft, validator_id: VALIDATOR_ID });
      onUpdated(reponse.id, { contenu: draft, statut: "CORRIGÉE" });
      setEditing(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erreur");
    } finally {
      setLoading(false);
    }
  }

  function handleCancel() {
    setDraft(reponse.contenu);
    setEditing(false);
    setError(null);
  }

  return (
    <li className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`text-xs px-2.5 py-0.5 rounded-full border font-medium ${reponseStatutClass(reponse.statut, reponse.canonique)}`}>
            {reponseStatutLabel(reponse.statut, reponse.canonique)}
          </span>
          <span className="text-xs text-gray-400">{SOURCE_LABEL[reponse.source] ?? reponse.source}</span>
          {reponse.score_similarite != null && (
            <span className="text-xs text-gray-400">
              · similarité {(reponse.score_similarite * 100).toFixed(0)} %
            </span>
          )}
        </div>
        <span className="text-xs text-gray-400 shrink-0">{formatDate(reponse.created_at)}</span>
      </div>

      {editing ? (
        <div className="space-y-3">
          <textarea
            className="w-full text-sm text-gray-700 bg-gray-50 border border-gray-300 rounded-xl p-4 focus:outline-none focus:ring-2 focus:ring-emerald-500 resize-y leading-relaxed min-h-[420px]"
            rows={18}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            disabled={loading}
            autoFocus
            aria-label="Contenu corrigé"
          />
          {error && <p className="text-xs text-red-500" role="alert">{error}</p>}
          <div className="flex items-center gap-2">
            <button
              onClick={handleCorriger}
              disabled={loading || !draft.trim()}
              className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-xl bg-emerald-500 text-white hover:bg-emerald-600 disabled:opacity-40 font-medium transition-colors"
            >
              <Check size={14} aria-hidden="true" /> Valider la correction
            </button>
            <button
              onClick={handleCancel}
              disabled={loading}
              className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-xl border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors"
            >
              <X size={14} aria-hidden="true" /> Annuler
            </button>
          </div>
        </div>
      ) : (
        <div className="bg-gray-50 rounded-xl p-4">
          <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">{reponse.contenu}</p>
        </div>
      )}

      {canAct && !editing && (
        <div className="flex items-center gap-2 pt-1 flex-wrap">
          <button
            onClick={handleValider}
            disabled={loading}
            className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-xl bg-emerald-500 text-white hover:bg-emerald-600 disabled:opacity-40 font-medium transition-colors"
          >
            <ThumbsUp size={14} aria-hidden="true" /> Valider
          </button>
          <button
            onClick={() => setEditing(true)}
            disabled={loading}
            className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-xl border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-40 transition-colors"
          >
            <Pencil size={14} aria-hidden="true" /> Corriger
          </button>
          {error && <p className="text-xs text-red-500 ml-1" role="alert">{error}</p>}
        </div>
      )}
    </li>
  );
}

export default function TicketDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [reponses, setReponses] = useState<TicketReponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setError(null);
    Promise.all([getTicket(id), getReponsesByTicket(id)])
      .then(([t, r]) => { setTicket(t); setReponses(r); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  function handleUpdated(reponseId: string, patch: Partial<TicketReponse>) {
    setReponses((prev) =>
      prev.map((r) => r.id === reponseId ? { ...r, ...patch } : r)
    );
    if (patch.statut === "VALIDÉE" || patch.statut === "CORRIGÉE") {
      setTicket((prev) => prev ? {
        ...prev,
        statut_ticket: "VALIDÉ" as StatutTicket,
        canonique: prev.canonique || (patch.canonique ?? false),
      } : prev);
    } else if (patch.statut === "REJETÉE") {
      setTicket((prev) => prev ? { ...prev, statut_ticket: "REJETÉ" as StatutTicket } : prev);
    }
  }

  if (loading) return <div className="p-6 text-center text-gray-400" aria-live="polite">Chargement…</div>;

  if (error || !ticket) {
    return (
      <div className="p-6">
        <button onClick={() => navigate(-1)} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 mb-4">
          <ArrowLeft size={16} aria-hidden="true" /> Retour
        </button>
        <p className="text-red-400" role="alert">{error ?? "Ticket introuvable"}</p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-4 max-w-6xl">
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 transition-colors"
        aria-label="Retour à la liste des tickets"
      >
        <ArrowLeft size={16} aria-hidden="true" /> Retour aux tickets
      </button>

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-0.5">Objet</p>
          <h1 className="text-xl font-semibold text-gray-800">{MOCK_OBJET}</h1>
        </div>
        <StatutBadge statut={ticket.statut_ticket} canonique={ticket.canonique} />
      </div>

      {/* Layout 2 colonnes */}
      <div className="flex gap-5 items-start">

        {/* Colonne principale : question + réponses */}
        <div className="flex-1 min-w-0 space-y-4">
          {/* Question */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
            <p className="text-gray-400 text-xs uppercase tracking-wide mb-2">Question</p>
            <p className="text-sm text-gray-700 leading-relaxed">{ticket.question}</p>
          </div>

          {/* Réponses */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100">
              <h2 className="text-sm font-semibold text-gray-800">Réponses</h2>
            </div>
            {reponses.length === 0 ? (
              <p className="px-6 py-10 text-center text-gray-400 text-sm">Aucune réponse pour ce ticket.</p>
            ) : (
              <ul className="divide-y divide-gray-100" aria-label="Réponses au ticket">
                {reponses.map((r) => (
                  <ReponseItem key={r.id} reponse={r} onUpdated={handleUpdated} />
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* Colonne latérale */}
        <div className="w-72 shrink-0 space-y-4">

          {/* Infos ticket */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5 space-y-4">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Informations</p>
            <dl className="space-y-3 text-sm">
              <div>
                <dt className="text-gray-400 text-xs mb-0.5">Domaine</dt>
                <dd className="text-gray-700 font-medium">{DOMAINE_LABEL[ticket.domaine] ?? ticket.domaine}</dd>
              </div>
              <div>
                <dt className="text-gray-400 text-xs mb-0.5">Créé le</dt>
                <dd className="text-gray-700">{formatDate(ticket.created_at)}</dd>
              </div>
              <div>
                <dt className="text-gray-400 text-xs mb-0.5">Référence</dt>
                <dd className="text-gray-500 font-mono text-xs break-all">{ticket.id}</dd>
              </div>
              <div>
                <dt className="text-gray-400 text-xs mb-0.5">Statut traitement</dt>
                <dd className="text-gray-700">{ticket.statut_job}</dd>
              </div>
            </dl>
          </div>

          {/* Demandeur */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5 space-y-4">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Demandeur</p>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-emerald-100 text-emerald-700 font-semibold text-sm flex items-center justify-center shrink-0" aria-hidden="true">
                {MOCK_AUTHOR.avatar}
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">{MOCK_AUTHOR.name}</p>
                <p className="text-xs text-gray-500 truncate">{MOCK_AUTHOR.role}</p>
              </div>
            </div>
            <dl className="space-y-2 text-xs text-gray-500 border-t border-gray-100 pt-3">
              <div>
                <dt className="text-gray-400 mb-0.5">Département</dt>
                <dd className="text-gray-700">{MOCK_AUTHOR.department}</dd>
              </div>
              <div>
                <dt className="text-gray-400 mb-0.5">Email</dt>
                <dd className="text-gray-700 break-all">{MOCK_AUTHOR.email}</dd>
              </div>
              <div>
                <dt className="text-gray-400 mb-0.5">Téléphone</dt>
                <dd className="text-gray-700">{MOCK_AUTHOR.phone}</dd>
              </div>
            </dl>
          </div>

        </div>
      </div>
    </div>
  );
}
