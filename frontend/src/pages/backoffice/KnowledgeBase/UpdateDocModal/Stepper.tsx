import { Check } from "lucide-react";
import type { Etape } from "../../../../hooks/useUpdateDocModal";

/** `submitting` shares the `impact` rank — screen doesn't change, only the button enters a waiting state. */
const RANGS: Record<Etape, number> = {
  pick: 0,
  analyse: 1,
  impact: 2,
  submitting: 2,
  done: 3,
  error: -1,
};

const LIBELLES = ["Fichier", "Analyse", "Impact", "Confirmation"];

export default function Stepper({ etape }: { etape: Etape }) {
  const rang = RANGS[etape];
  if (rang < 0) return null;

  return (
    <ol className="mb-5 flex items-center gap-1.5" aria-label="Progression">
      {LIBELLES.map((libelle, i) => {
        const fait = i < rang || etape === "done";
        const actif = i === rang && etape !== "done";

        return (
          <li key={libelle} className="flex flex-1 items-center gap-1.5">
            <span
              aria-current={actif ? "step" : undefined}
              className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold tabular-nums transition-colors
                ${
                  fait
                    ? "bg-primary text-primary-foreground"
                    : actif
                      ? "bg-gray-900 text-white dark:bg-white dark:text-gray-900"
                      : "bg-gray-100 text-muted-foreground dark:bg-white/8"
                }`}
            >
              {fait ? <Check size={11} strokeWidth={3} /> : i + 1}
            </span>
            <span
              className={`hidden text-[11px] font-medium sm:inline ${
                actif
                  ? "text-gray-900 dark:text-gray-100"
                  : fait
                    ? "text-muted-foreground"
                    : "text-muted-foreground"
              }`}
            >
              {libelle}
            </span>
            {i < LIBELLES.length - 1 && (
              <span
                aria-hidden="true"
                className={`h-px flex-1 ${fait ? "bg-emerald-300 dark:bg-emerald-500/40" : "bg-gray-200 dark:bg-white/10"}`}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
