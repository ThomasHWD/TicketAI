export default function IncidentBadge({ label, variant }: { label: string; variant: "red" | "amber" }) {
  const cls =
    variant === "red"
      ? "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400"
      : "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400";
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${cls}`}>
      {label}
    </span>
  );
}
