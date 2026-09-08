import { useEffect, useRef, useState } from "react";
import { lockTicket, unlockTicket, heartbeatTicket, LockConflictError } from "../lib/api";
import { getValidatorId } from "../lib/currentUser";

// File d'attente par ticket : garantit que lock / unlock s'exécutent dans l'ordre
// d'émission, même sous le double-montage de React StrictMode (dev) ou lors de
// navigations rapides. Sans ça, un `unlock` peut doubler un `lock` concurrent.
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
  isAssigned: boolean;
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
  const [isAssigned, setIsAssigned] = useState(false);
  const [checking, setChecking] = useState(true);
  const cancelUnlockRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!ticketId) return;

    // Annule un unlock différé issu du cleanup précédent (double-mount StrictMode)
    if (cancelUnlockRef.current) {
      cancelUnlockRef.current();
      cancelUnlockRef.current = null;
    }

    const validatorId = getValidatorId();
    let active = true;
    let acquired = false;

    setChecking(true);
    enqueue(ticketId, () => lockTicket(ticketId, validatorId))
      .then(() => {
        if (active) {
          acquired = true;
          setIsMine(true);
          setLockedByEmail(null);
        }
      })
      .catch((e: unknown) => {
        if (active) {
          setIsMine(false);
          if (e instanceof LockConflictError) {
            setLockedByEmail(e.lockedByEmail);
            setIsAssigned(e.isAssigned);
          } else {
            setLockedByEmail(null);
            setIsAssigned(false);
          }
        }
      })
      .finally(() => {
        if (active) setChecking(false);
      });

    // Renouvelle le verrou toutes les 2 minutes tant que la page est ouverte
    const heartbeatInterval = setInterval(() => {
      if (acquired) void heartbeatTicket(ticketId, validatorId);
    }, 2 * 60 * 1000);

    return () => {
      active = false;
      clearInterval(heartbeatInterval);
      if (!acquired) return;
      // Différé de 50 ms : si le composant se remonte immédiatement (StrictMode),
      // le prochain effet annule ce timer avant qu'il parte.
      let cancelled = false;
      cancelUnlockRef.current = () => { cancelled = true; };
      setTimeout(() => {
        if (!cancelled) void enqueue(ticketId, () => unlockTicket(ticketId, validatorId));
      }, 50);
    };
  }, [ticketId]);

  return { isMine, lockedByEmail, isAssigned, checking };
}
