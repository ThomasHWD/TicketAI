import type { ReponseARelire } from "../../../types";

export default function LigneARelire({ reponse }: { reponse: ReponseARelire }) {
  return (
    <li className="rounded-lg border border-amber-200/70 dark:border-amber-500/25 bg-white/70 dark:bg-white/[0.03] px-3 py-2.5 space-y-1.5">
      <div className="flex items-start gap-2">
        <a
          href={`/tickets/${reponse.ticket_id}`}
          target="_blank"
          rel="noreferrer"
          className="flex-1 text-xs font-medium text-gray-900 dark:text-gray-100 line-clamp-2 hover:underline"
        >
          {reponse.question || (
            <span className="italic font-normal text-gray-500">Question indisponible</span>
          )}
        </a>
        {reponse.canonique && (
          <span className="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-100 dark:bg-emerald-400/15 text-green-700 dark:text-emerald-300">
            canonique
          </span>
        )}
        <span className="shrink-0 text-[10px] text-gray-500 dark:text-gray-400 tabular-nums">
          {reponse.nb_validations} val.
        </span>
      </div>
      {reponse.contenu && (
        <p className="text-[11px] text-gray-500 dark:text-gray-400 line-clamp-2">
          {reponse.contenu}
        </p>
      )}
    </li>
  );
}
