import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getToken } from "../lib/api";

interface SSEEvent {
  type: string;
  payload: Record<string, unknown>;
}

function handleEvent(event: SSEEvent, queryClient: ReturnType<typeof useQueryClient>) {
  const { type, payload } = event;

  switch (type) {
    case "ticket_created":
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
      queryClient.invalidateQueries({ queryKey: ["user-dash"] });
      break;

    case "ticket_followup":
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
      if (payload.ticket_id) {
        queryClient.invalidateQueries({ queryKey: ["ticket", payload.ticket_id] });
      }
      break;

    case "ticket_answered":
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
      queryClient.invalidateQueries({ queryKey: ["mes-tickets"] });
      queryClient.invalidateQueries({ queryKey: ["user-dash"] });
      if (payload.ticket_id) {
        queryClient.invalidateQueries({ queryKey: ["ticket", payload.ticket_id] });
      }
      break;

    case "ticket_locked":
    case "ticket_unlocked":
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
      if (payload.ticket_id) {
        queryClient.invalidateQueries({ queryKey: ["ticket", payload.ticket_id] });
      }
      break;

    case "ticket_assigned":
    case "ticket_unassigned":
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
      queryClient.invalidateQueries({ queryKey: ["mes-assignations"] });
      if (payload.ticket_id) {
        queryClient.invalidateQueries({ queryKey: ["ticket", payload.ticket_id] });
      }
      break;

    case "ticket_closed":
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
      queryClient.invalidateQueries({ queryKey: ["mes-tickets"] });
      queryClient.invalidateQueries({ queryKey: ["user-dash"] });
      if (payload.ticket_id) {
        queryClient.invalidateQueries({ queryKey: ["ticket", payload.ticket_id] });
      }
      break;

    case "reponse_validated":
    case "reponse_rejected":
    case "reponse_corrected":
      queryClient.invalidateQueries({ queryKey: ["user-dash"] });
      if (payload.ticket_id) {
        queryClient.invalidateQueries({ queryKey: ["ticket", payload.ticket_id] });
      }
      queryClient.invalidateQueries({ queryKey: ["reponses-canoniques"] });
      break;

    case "notification_created":
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
      queryClient.invalidateQueries({ queryKey: ["mes-assignations"] });
      queryClient.invalidateQueries({ queryKey: ["mes-tickets"] });
      if (payload.ticket_id) {
        queryClient.invalidateQueries({ queryKey: ["ticket", payload.ticket_id] });
      }
      break;

    case "banner_updated":
      queryClient.invalidateQueries({ queryKey: ["site-config"] });
      break;

    case "group_updated":
      queryClient.invalidateQueries({ queryKey: ["admin"] });
      break;

    case "saved_answers_updated":
      queryClient.invalidateQueries({ queryKey: ["reponses-canoniques"] });
      // Restauration et suppression font passer une réponse d'une liste à l'autre.
      queryClient.invalidateQueries({ queryKey: ["reponses-obsoletes"] });
      // Confirmer, corriger ou retirer lève le drapeau : le badge doit tomber
      // chez les autres validateurs du domaine, pas seulement chez l'auteur.
      queryClient.invalidateQueries({ queryKey: ["reponses-a-relire"] });
      break;

    // Fin du job de mise à jour : la version, les chunks et éventuellement des
    // réponses enregistrées ont bougé en même temps.
    case "document_updated":
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["reponses-canoniques"] });
      queryClient.invalidateQueries({ queryKey: ["reponses-obsoletes"] });
      // C'est ici que la liste « À relire » se remplit : le job vient de flaguer
      // les réponses du document, l'onglet doit le montrer sans rechargement.
      queryClient.invalidateQueries({ queryKey: ["reponses-a-relire"] });
      if (payload.doc_id) {
        queryClient.invalidateQueries({ queryKey: ["doc-versions", payload.doc_id] });
      }
      break;

    case "job_completed":
      if (payload.job_id) {
        queryClient.invalidateQueries({ queryKey: ["job-tracker", payload.job_id] });
      }
      break;

    default:
      break;
  }
}

export function useSSE() {
  const queryClient = useQueryClient();
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let stopped = false;
    let retryDelay = 1000;
    let hasConnectedOnce = false;

    async function connect() {
      const token = getToken();
      if (!token) return;

      abortRef.current = new AbortController();
      const { signal } = abortRef.current;

      try {
        const response = await fetch("/api/v1/sse/stream", {
          headers: { Authorization: `Bearer ${token}` },
          signal,
        });

        if (!response.ok || !response.body) {
          throw new Error(`SSE ${response.status}`);
        }

        retryDelay = 1000;

        // Après une reconnexion, invalider toutes les queries potentiellement
        // périmées pendant la coupure (les events manqués sont perdus avec pub/sub)
        if (hasConnectedOnce) {
          for (const key of ["tickets", "ticket", "mes-tickets", "mes-assignations", "notifications", "user-dash"]) {
            queryClient.invalidateQueries({ queryKey: [key] });
          }
        }
        hasConnectedOnce = true;

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            try {
              const event: SSEEvent = JSON.parse(line.slice(6));
              handleEvent(event, queryClient);
            } catch {
              // ignore malformed events
            }
          }
        }
      } catch {
        if (signal.aborted) return;
        console.warn("[SSE] Disconnected, retrying in", retryDelay, "ms");
      }

      if (!stopped && !abortRef.current?.signal.aborted) {
        setTimeout(() => {
          retryDelay = Math.min(retryDelay * 2, 30_000);
          connect();
        }, retryDelay);
      }
    }

    connect();

    return () => {
      stopped = true;
      abortRef.current?.abort();
    };
  }, [queryClient]);
}
