import { useEffect, useRef, useState } from "react";
import { lockTicket, unlockTicket, heartbeatTicket, LockConflictError } from "../lib/api";
import { getValidatorId } from "../lib/currentUser";

// per-ticket queue: ensures lock/unlock execute in emission order under StrictMode double-mount or fast navigation
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

    const heartbeatInterval = setInterval(() => {
      if (acquired) void heartbeatTicket(ticketId, validatorId);
    }, 2 * 60 * 1000);

    return () => {
      active = false;
      clearInterval(heartbeatInterval);
      if (!acquired) return;
      // 50 ms delay: if the component remounts immediately (StrictMode), the next effect cancels this before it fires
      let cancelled = false;
      cancelUnlockRef.current = () => { cancelled = true; };
      setTimeout(() => {
        if (!cancelled) void enqueue(ticketId, () => unlockTicket(ticketId, validatorId));
      }, 50);
    };
  }, [ticketId]);

  return { isMine, lockedByEmail, isAssigned, checking };
}
