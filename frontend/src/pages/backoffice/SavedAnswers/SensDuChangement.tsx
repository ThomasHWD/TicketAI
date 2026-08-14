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

  return (
    <div className="space-y-1">
      <p className="text-xs font-medium uppercase tracking-wider text-amber-900/70 dark:text-amber-200/70">
        {total} passage{total > 1 ? "s" : ""} {titre}
        {total > 1 ? "s" : ""}
      </p>
      <ul className="space-y-1">
        {extraits.map((extrait, i) => (
          <li
            key={i}
            className="text-xs text-gray-600 dark:text-gray-400 font-mono leading-relaxed bg-amber-100/70 dark:bg-amber-500/10 rounded px-2 py-1"
          >
            {extrait}
          </li>
        ))}
      </ul>
      {total > extraits.length && (
        <p className="text-xs text-amber-900/70 dark:text-amber-200/70">
          … et {total - extraits.length} autre{total - extraits.length > 1 ? "s" : ""}.
        </p>
      )}
    </div>
  );
}
