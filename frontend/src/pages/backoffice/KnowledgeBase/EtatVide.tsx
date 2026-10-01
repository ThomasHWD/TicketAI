import type { FolderOpen } from "lucide-react";

export function EtatVide({
  icon: Icon,
  titre,
  detail,
  action,
}: {
  icon: typeof FolderOpen;
  titre: string;
  detail: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-20 text-center">
      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gray-100 dark:bg-white/5">
        <Icon size={18} className="text-subtle" />
      </div>
      <p className="text-sm font-medium text-gray-700 dark:text-gray-300">{titre}</p>
      <p className="max-w-sm text-xs leading-relaxed text-muted-foreground">{detail}</p>
      {action}
    </div>
  );
}
