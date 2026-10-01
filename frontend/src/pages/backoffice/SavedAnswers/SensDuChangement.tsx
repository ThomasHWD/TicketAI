export default function SensDuChangement({
  titre,
  total,
  extraits,
}: {
  titre: string;
  total: number;
  extraits: string[];
}) {
  if (total === 0) return null;

  const isAdded = titre === "ajouté";
  return (
    <div className="space-y-1.5">
      <p className={`text-xs font-semibold uppercase tracking-wider ${
        isAdded
          ? "text-emerald-700 dark:text-emerald-300"
          : "text-red-700 dark:text-red-300"
      }`}>
        {total} passage{total > 1 ? "s" : ""} {titre}{total > 1 ? "s" : ""}
      </p>
      <ul className="space-y-1">
        {extraits.map((extrait, i) => (
          <li
            key={i}
            aria-label={`${isAdded ? "Ajouté" : "Retiré"} : ${extrait}`}
            className={`text-xs font-mono leading-relaxed rounded px-2.5 py-1.5 ${
              isAdded
                ? "bg-emerald-50 text-emerald-900 dark:bg-emerald-500/10 dark:text-emerald-200"
                : "bg-red-50 text-red-900 dark:bg-red-500/10 dark:text-red-200"
            }`}
          >
            <span
              aria-hidden="true"
              className={`mr-1.5 select-none ${isAdded ? "text-emerald-700 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}
            >
              {isAdded ? "+" : "−"}
            </span>
            {extrait}
          </li>
        ))}
      </ul>
      {total > extraits.length && (
        <p className="text-xs text-amber-800 dark:text-amber-300">
          … et {total - extraits.length} autre{total - extraits.length > 1 ? "s" : ""}.
        </p>
      )}
    </div>
  );
}
