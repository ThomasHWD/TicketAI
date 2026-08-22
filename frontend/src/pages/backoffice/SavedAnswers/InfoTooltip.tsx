import { useId } from "react";
import { Info } from "lucide-react";

type Props = {
  content: string;
  size?: number;
  className?: string;
};

export default function InfoTooltip({ content, size = 12, className = "" }: Props) {
  const id = useId();
  return (
    <span className={`relative group/tip inline-flex ${className}`}>
      <span
        tabIndex={0}
        aria-describedby={id}
        className="cursor-help rounded-sm outline-none focus-visible:ring-1 focus-visible:ring-gray-400/60"
      >
        <Info size={size} className="text-gray-400 dark:text-gray-500" aria-hidden="true" />
      </span>
      <span
        id={id}
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-30 w-max max-w-[220px] px-2.5 py-1.5 rounded-lg bg-gray-900 dark:bg-gray-700 text-white text-xs leading-snug opacity-0 group-hover/tip:opacity-100 group-focus-within/tip:opacity-100 transition-opacity duration-150 text-center shadow-lg"
      >
        {content}
        <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900 dark:border-t-gray-700" aria-hidden="true" />
      </span>
    </span>
  );
}
