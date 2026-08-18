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
          ? "text-emerald-700/80 dark:text-emerald-300/70"
          : "text-red-600/80 dark:text-red-400/70"
      }`}>
        {total} passage{total > 1 ? "s" : ""} {titre}{total > 1 ? "s" : ""}
      </p>
      <ul className="space-y-1">
        {extraits.map((extrait, i) => (
          <li
            key={i}
            className={`text-xs font-mono leading-relaxed rounded px-2.5 py-1.5 ${
              isAdded
                ? "bg-emerald-50 text-emerald-900 dark:bg-emerald-500/10 dark:text-emerald-200"
                : "bg-red-50 text-red-900 dark:bg-red-500/10 dark:text-red-200"
            }`}
          >
            <span className={`mr-1.5 select-none ${isAdded ? "text-emerald-500" : "text-red-400"}`}>
              {isAdded ? "+" : "−"}
            </span>
            {extrait}
          </li>
        ))}
      </ul>
      {total > extraits.length && (
        <p className="text-xs text-amber-800/70 dark:text-amber-300/60">
          … et {total - extraits.length} autre{total - extraits.length > 1 ? "s" : ""}.
        </p>
      )}
    </div>
  );
}
