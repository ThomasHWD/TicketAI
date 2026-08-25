import { Bot } from "lucide-react";

export function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  }).format(new Date(iso));
}

export function BotAvatar({ pulse = false }: { pulse?: boolean }) {
  return (
    <span
      className={`inline-flex items-center justify-center w-9 h-9 rounded-full bg-emerald-500 dark:bg-emerald-600 text-white shrink-0 ring-2 ring-white dark:ring-black/40 shadow-md shadow-emerald-600/40${pulse ? " motion-safe:animate-pulse" : ""}`}
      aria-hidden="true"
    >
      <Bot size={16} strokeWidth={1.75} />
    </span>
  );
}
