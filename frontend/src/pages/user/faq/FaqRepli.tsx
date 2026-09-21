import { Link } from "react-router-dom";
import { ArrowRight, MessageSquarePlus } from "lucide-react";

/** Fallback when FAQ doesn't suffice. Row not button — it's an exit, not the primary action; same visual width as content so it reads as a natural continuation. */
export default function FaqRepli({ question, sousTitre }: { question: string; sousTitre: string }) {
  return (
    <Link
      to={`/nouveau-ticket?question=${encodeURIComponent(question)}`}
      className="group flex items-center gap-3 rounded-xl border border-gray-200 px-4 py-3 transition-colors hover:border-emerald-400/60 hover:bg-emerald-50/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 dark:border-white/10 dark:hover:border-emerald-500/40 dark:hover:bg-emerald-500/[0.06]"
    >
      <MessageSquarePlus
        size={18}
        strokeWidth={1.7}
        aria-hidden="true"
        className="shrink-0 text-gray-400 transition-colors group-hover:text-emerald-600 dark:group-hover:text-emerald-400"
      />
      <span className="flex-1">
        <span className="block text-sm font-medium text-gray-800 dark:text-gray-100">
          Poser la question à un expert
        </span>
        <span className="block text-xs text-gray-500 dark:text-gray-400">{sousTitre}</span>
      </span>
      <ArrowRight
        size={16}
        aria-hidden="true"
        className="shrink-0 text-gray-300 transition-all group-hover:translate-x-0.5 group-hover:text-emerald-600 dark:text-gray-600 dark:group-hover:text-emerald-400"
      />
    </Link>
  );
}
