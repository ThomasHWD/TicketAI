import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, ArrowRightLeft, Loader2, X } from "lucide-react";
import { getDomaines, recheminerTicket } from "../../../lib/api";
import type { Ticket } from "../../../types";
import { useDialogFocus } from "../../../hooks/useDialogFocus";

interface RerouteModalProps {
  ticket: Ticket;
  onClose: () => void;
  onSuccess: () => void;
}

export default function RerouteModal({ ticket, onClose, onSuccess }: RerouteModalProps) {
  const [nouveauDomaine, setNouveauDomaine] = useState("");
  const [raison, setRaison] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  const { data: domaines = [], isLoading: domainesLoading } = useQuery<string[]>({
    queryKey: ["domaines"],
    queryFn: getDomaines,
    staleTime: 60_000,
  });

  const autresDomaines = domaines.filter((d) => d !== ticket.domaine);

  useDialogFocus(dialogRef, { onClose, initialFocus: closeRef });

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!nouveauDomaine || !raison.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await recheminerTicket(ticket.id, { nouveau_domaine: nouveauDomaine, raison: raison.trim() });
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur lors du réacheminement. Réessayez.");
    } finally {
      setLoading(false);
    }
  }

  const isRejete = ticket.statut_ticket === "REJETÉ";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40 dark:bg-black/70" />

      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="reroute-modal-title"
        className="relative bg-white dark:bg-[#141416] border border-gray-200 dark:border-white/10 rounded-2xl w-full max-w-md flex flex-col shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-5 py-4 border-b border-gray-200/80 dark:border-white/10 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="flex items-center justify-center w-7 h-7 rounded-md bg-orange-100 dark:bg-orange-500/20">
              <ArrowRightLeft size={14} className="text-orange-600 dark:text-orange-400" aria-hidden="true" />
            </div>
            <div>
              <h2 id="reroute-modal-title" className="text-sm font-semibold text-gray-800 dark:text-gray-100 leading-none">
                Réacheminer ce ticket
              </h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Domaine actuel : <span className="font-medium text-gray-700 dark:text-gray-300">{ticket.domaine}</span>
              </p>
            </div>
          </div>
          <button
            ref={closeRef}
            onClick={onClose}
            className="flex items-center justify-center w-7 h-7 rounded-full text-muted-foreground hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors"
            aria-label="Fermer"
          >
            <X size={14} aria-hidden="true" />
          </button>
        </div>

        {/* Corps */}
        <form onSubmit={handleSubmit} className="px-5 py-5 space-y-4">

          {/* Avertissement contextuel */}
          <div className="flex items-start gap-2.5 px-3 py-2.5 rounded-xl bg-orange-50 dark:bg-orange-500/10 border border-orange-200 dark:border-orange-500/20">
            <AlertCircle size={13} className="text-orange-500 dark:text-orange-400 shrink-0 mt-0.5" aria-hidden="true" />
            <p className="text-xs text-orange-700 dark:text-orange-300 leading-relaxed">
              {isRejete
                ? "Le ticket sera rouvert et la question retraitée par le nouveau service."
                : "La réponse actuelle sera annulée et la question retraitée depuis les documents du nouveau service."}
            </p>
          </div>

          {/* Sélection du domaine */}
          <div className="space-y-1.5">
            <label htmlFor="reroute-domaine" className="text-xs font-semibold text-muted-foreground uppercase tracking-[0.06em]">
              Nouveau service
            </label>
            <select
              id="reroute-domaine"
              value={nouveauDomaine}
              onChange={(e) => setNouveauDomaine(e.target.value)}
              disabled={loading || domainesLoading}
              required
              className="w-full text-xs text-gray-700 dark:text-gray-100 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-md px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-orange-400 disabled:opacity-40"
            >
              <option value="">
                {domainesLoading ? "Chargement…" : autresDomaines.length === 0 ? "Aucun autre service disponible" : "Choisir un service…"}
              </option>
              {autresDomaines.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
          </div>

          {/* Raison */}
          <div className="space-y-1.5">
            <label htmlFor="reroute-raison" className="text-xs font-semibold text-muted-foreground uppercase tracking-[0.06em]">
              Motif du réacheminement
            </label>
            <textarea
              id="reroute-raison"
              value={raison}
              onChange={(e) => setRaison(e.target.value)}
              disabled={loading}
              required
              rows={3}
              placeholder="Ex. : question relevant du service juridique…"
              className="w-full text-xs text-gray-700 dark:text-gray-100 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-400 disabled:opacity-40 resize-none placeholder:text-muted-foreground"
            />
          </div>

          {/* Erreur */}
          {error && (
            <p className="flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400" role="alert">
              <AlertCircle size={12} aria-hidden="true" />
              {error}
            </p>
          )}

          {/* Actions */}
          <div className="flex items-center justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="text-xs px-3 py-2 rounded-md border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 disabled:opacity-40 transition-colors"
            >
              Annuler
            </button>
            <button
              type="submit"
              disabled={loading || !nouveauDomaine || !raison.trim()}
              className="flex items-center gap-1.5 text-xs px-4 py-2 rounded-md bg-orange-500 text-white hover:bg-orange-600 disabled:opacity-40 font-medium transition-colors"
            >
              {loading
                ? <><Loader2 size={12} className="animate-spin" aria-hidden="true" />Réacheminement…</>
                : <><ArrowRightLeft size={12} aria-hidden="true" />Réacheminer</>
              }
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
