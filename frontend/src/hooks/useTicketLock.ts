import { useEffect, useRef, useState } from "react";
import { lockTicket, heartbeatTicket, unlockTicket, LockConflictError } from "../lib/api";
import { getValidatorId } from "../lib/currentUser";

// Prolonge le bail bien avant son expiration (TTL backend = 300 s par défaut).
const HEARTBEAT_MS = 120_000;

// File d'attente par ticket : garantit que lock / unlock / heartbeat s'exécutent
// dans l'ordre d'émission, même sous le double-montage de React StrictMode (dev)
// ou lors de navigations rapides. Sans ça, un `unlock` peut doubler un `lock`
// concurrent et laisser un verrou fantôme (ou l'inverse).
const chains = new Map<string, Promise<unknown>>();

function enqueue<T>(ticketId: string, op: () => Promise<T>): Promise<T> {
  const prev = chains.get(ticketId) ?? Promise.resolve();
  const next = prev.catch(() => undefined).then(op);
  chains.set(ticketId, next);
  return next;
}

export interface TicketLock {
  isMine: boolean;
  lockedByEmail: string | null;
  checking: boolean;
}

/**
 * Prend automatiquement le verrou du ticket à l'ouverture, le prolonge par
 * heartbeat tant que la page reste montée, et le libère à la sortie
 * (démontage ou fermeture d'onglet).
 */
export function useTicketLock(ticketId: string | undefined): TicketLock {
  const [isMine, setIsMine] = useState(false);
  const [lockedByEmail, setLockedByEmail] = useState<string | null>(null);
  const [checking, setChecking] = useState(true);

  // Garde la valeur à jour pour le heartbeat sans re-souscrire l'effet.
  const isMineRef = useRef(false);
  useEffect(() => {
    isMineRef.current = isMine;
  }, [isMine]);

  useEffect(() => {
    if (!ticketId) return;
    const validatorId = getValidatorId();
    let active = true;

    setChecking(true);
    enqueue(ticketId, () => lockTicket(ticketId, validatorId))
      .then(() => {
        if (active) {
          setIsMine(true);
          setLockedByEmail(null);
        }
      })
      .catch((e: unknown) => {
        if (active) {
          setIsMine(false);
          setLockedByEmail(e instanceof LockConflictError ? e.lockedByEmail : null);
        }
      })
      .finally(() => {
        if (active) setChecking(false);
      });

    const heartbeat = window.setInterval(() => {
      if (!isMineRef.current) return;
      enqueue(ticketId, () => heartbeatTicket(ticketId, validatorId))
        .then(() => setIsMine(true))
        .catch((e: unknown) => {
          setIsMine(false);
          setLockedByEmail(e instanceof LockConflictError ? e.lockedByEmail : null);
        });
    }, HEARTBEAT_MS);

    // Libération best-effort si l'utilisateur ferme l'onglet (unlock idempotent).
    const releaseOnUnload = () => {
      void unlockTicket(ticketId, validatorId);
    };
    window.addEventListener("beforeunload", releaseOnUnload);

    return () => {
      active = false;
      window.clearInterval(heartbeat);
      window.removeEventListener("beforeunload", releaseOnUnload);
      // Libère à la suite des opérations en cours (unlock ne touche que les
      // tickets dont on est réellement le détenteur).
      void enqueue(ticketId, () => unlockTicket(ticketId, validatorId));
    };
  }, [ticketId]);

  return { isMine, lockedByEmail, checking };
}
