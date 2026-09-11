import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, soumettreQuestion } from "../lib/api";
import { getValidatorId } from "../lib/currentUser";
import type { Domaine } from "../types";

async function fetchDomaines(): Promise<string[]> {
  const res = await apiFetch("/api/v1/tickets/domaines");
  return res.json();
}

export const isMac =
  typeof navigator !== "undefined" && /Macintosh|Mac OS X/.test(navigator.userAgent);
export const isTouchDevice =
  typeof navigator !== "undefined" && navigator.maxTouchPoints > 0;

export function isValidationError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  const msg = error.message;
  return (
    msg.includes("422") ||
    msg.includes("Unprocessable") ||
    msg === "Erreur lors de la soumission de la question"
  );
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    if (isValidationError(error))
      return "Votre question est incomplète. Vérifiez les champs et réessayez.";
    if (error.message.includes("401") || error.message.includes("403"))
      return "Votre session a expiré. Rechargez la page et reconnectez-vous.";
    if (error.message.includes("500") || error.message.includes("502") || error.message.includes("503"))
      return "Une erreur est survenue de notre côté. Réessayez dans quelques instants.";
  }
  return "Votre question n'a pas pu être envoyée. Réessayez ou contactez votre administrateur.";
}

export function useNewTicket() {
  const queryClient = useQueryClient();
  const [objet, setObjet] = useState("");
  // Pré-remplissage depuis la FAQ (`?question=…`, quand aucune réponse validée ne
  // correspondait). Initialisation paresseuse : l'utilisateur reste libre d'éditer.
  const [question, setQuestion] = useState(
    () => new URLSearchParams(window.location.search).get("question") ?? "",
  );
  const [domaine, setDomaine] = useState<Domaine>("");

  const { data: domaines = [], isLoading: domainesLoading, isError: domainesError } = useQuery({
    queryKey: ["admin", "domaines"],
    queryFn: fetchDomaines,
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    if (domaines.length > 0 && !domaine) setDomaine(domaines[0] as Domaine);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [domaines]);

  const submit = useMutation({
    mutationFn: () =>
      soumettreQuestion({ question: question.trim(), objet: objet.trim(), domaine, user_id: getValidatorId() }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["mes-tickets"] }); },
  });

  const submitted = submit.isSuccess;
  const isDirty = (objet.length > 0 || question.length > 0) && !submitted;

  useEffect(() => {
    if (!isDirty) return;
    const handler = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty]);

  const canSubmit =
    objet.trim().length > 0 &&
    question.trim().length >= 10 &&
    domaine.length > 0 &&
    !submit.isPending &&
    !domainesLoading;

  const fieldError = submit.isError && isValidationError(submit.error);
  const fieldBorder = fieldError ? "border-red-300 dark:border-red-500/50" : "border-gray-200 dark:border-white/10";
  const fieldInvalid: true | undefined = fieldError ? true : undefined;

  function resetState() {
    setObjet("");
    setQuestion("");
    setDomaine(domaines[0] ?? "");
    submit.reset();
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (canSubmit) submit.mutate();
  }

  function handleTextareaKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && canSubmit) {
      e.preventDefault();
      submit.mutate();
    }
  }

  return {
    objet, setObjet, question, setQuestion, domaine, setDomaine,
    domaines, domainesLoading, domainesError,
    submit, submitted, canSubmit,
    fieldBorder, fieldInvalid, fieldError,
    resetState, handleSubmit, handleTextareaKeyDown,
  };
}
