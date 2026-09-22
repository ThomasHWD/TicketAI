import { useState } from "react";
import { corrigerReponse, validerReponse, rejeterReponse, updateTag, LockConflictError } from "../lib/api";
import { getValidatorId } from "../lib/currentUser";
import type { TicketReponse } from "../types";

interface UseReponseActionsOpts {
  onChanged: () => void;
  onLockConflict: (message: string) => void;
}

export function useReponseActions(reponse: TicketReponse, { onChanged, onLockConflict }: UseReponseActionsOpts) {
  const isHorsDomaine = reponse.source === "HORS_DOMAINE";
  const isRag = reponse.source === "LLM";
  const canAct = reponse.statut === "EN_ATTENTE";

  const DRAFT_KEY = `ticketai-draft-${reponse.id}`;

  const [editing, setEditing] = useState(isHorsDomaine && canAct);
  const [draft, setDraft] = useState<string>(() => {
    if (isHorsDomaine) return localStorage.getItem(DRAFT_KEY) ?? "";
    return reponse.contenu;
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tagDraft, setTagDraft] = useState(reponse.tag ?? "");
  const [confirmingValidation, setConfirmingValidation] = useState(false);
  const [faqVisible, setFaqVisible] = useState(false);
  const [justValidated, setJustValidated] = useState(false);
  const [confirmingRejection, setConfirmingRejection] = useState(false);
  const [rejectRaison, setRejectRaison] = useState("");

  function updateDraft(value: string) {
    setDraft(value);
    if (isHorsDomaine) {
      if (value) localStorage.setItem(DRAFT_KEY, value);
      else localStorage.removeItem(DRAFT_KEY);
    }
  }

  function handleError(e: unknown) {
    if (e instanceof LockConflictError) { onLockConflict(e.message); return; }
    setError(e instanceof Error ? e.message : "Une erreur est survenue. Vérifiez votre connexion et réessayez.");
  }

  async function handleValider() {
    if (isRag && !confirmingValidation) { setConfirmingValidation(true); return; }
    setConfirmingValidation(false);
    setLoading(true); setError(null);
    try {
      if (reponse.nb_validations === 0) {
        // Première validation : on fixe le tag (silencieux — ne bloque pas la validation)
        await updateTag(reponse.id, tagDraft.trim() || null).catch(() => null);
      }
      await validerReponse(reponse.id, { validator_id: getValidatorId(), faq_visible: faqVisible });
      setJustValidated(true);
      setTimeout(() => onChanged(), 250);
    } catch (e) { handleError(e); } finally { setLoading(false); }
  }

  async function handleCorriger() {
    if (!draft.trim() || draft.trim() === reponse.contenu.trim()) { setEditing(false); return; }
    setLoading(true); setError(null);
    try {
      await corrigerReponse(reponse.id, {
        contenu_corrige: draft,
        validator_id: getValidatorId(),
        ...(isHorsDomaine && { tag: tagDraft.trim() || null, faq_visible: faqVisible }),
      });
      if (isHorsDomaine) localStorage.removeItem(DRAFT_KEY);
      setEditing(false);
      onChanged();
    } catch (e) { handleError(e); } finally { setLoading(false); }
  }

  async function handleRejeter() {
    if (!rejectRaison.trim()) { setError("Un motif est obligatoire pour rejeter une réponse."); return; }
    setLoading(true); setError(null);
    try {
      await rejeterReponse(reponse.id, { validator_id: getValidatorId(), raison: rejectRaison.trim() });
      setConfirmingRejection(false);
      setRejectRaison("");
      onChanged();
    } catch (e) { handleError(e); } finally { setLoading(false); }
  }

  function handleCancel() {
    setDraft(isHorsDomaine ? (localStorage.getItem(DRAFT_KEY) ?? "") : reponse.contenu);
    setEditing(false);
    setError(null);
  }

  return {
    isHorsDomaine, isRag, canAct,
    editing, setEditing,
    draft, updateDraft,
    tagDraft, setTagDraft,
    loading,
    error, setError,
    confirmingValidation, setConfirmingValidation,
    faqVisible, setFaqVisible,
    justValidated,
    confirmingRejection, setConfirmingRejection,
    rejectRaison, setRejectRaison,
    handleValider, handleCorriger, handleRejeter, handleCancel,
  };
}
