import type { ReponseARelire } from "../../../../types";

/** Response awaiting judgment. Link opens in a new tab — in-place navigation would lose the staging preview and the uploaded file. */
export default function LigneARelire({ reponse }: { reponse: ReponseARelire }) {
  return (
    <li className="rounded-lg border border-gray-200 bg-white px-3 py-2.5 dark:border-white/10 dark:bg-white/[0.03]">
      <div className="flex items-start gap-2">
        <a
          href={`/tickets/${reponse.ticket_id}`}
          target="_blank"
          rel="noreferrer"
          className="line-clamp-2 flex-1 text-xs font-medium text-gray-900 hover:underline dark:text-gray-100"
        >
          {reponse.question || (
            <span className="font-normal italic text-gray-400">Question indisponible</span>
          )}
        </a>
        {reponse.canonique && (
          <span className="shrink-0 rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">
            canonique
          </span>
        )}
        <span className="shrink-0 text-[10px] tabular-nums text-gray-500 dark:text-gray-400">
          {reponse.nb_validations} val.
        </span>
      </div>
      {reponse.contenu && (
        <p className="mt-1.5 line-clamp-2 text-[11px] text-gray-500 dark:text-gray-400">
          {reponse.contenu}
        </p>
      )}
    </li>
  );
}
