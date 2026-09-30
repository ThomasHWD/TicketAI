import { useState } from "react";

export const STAR_PATH =
  "M11.48 3.499a.562.562 0 0 1 1.04 0l2.125 5.111a.563.563 0 0 0 .475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 0 0-.182.557l1.285 5.385a.562.562 0 0 1-.84.61l-4.725-2.885a.562.562 0 0 0-.586 0L6.982 20.54a.562.562 0 0 1-.84-.61l1.285-5.386a.562.562 0 0 0-.182-.557l-4.204-3.602a.562.562 0 0 1 .321-.988l5.518-.442a.563.563 0 0 0 .475-.345L11.48 3.5Z";

interface StarPickerProps {
  label: string;
  value: number | null;
  onChange: (v: number) => void;
}

export default function StarPicker({ label, value, onChange }: StarPickerProps) {
  const [hovered, setHovered] = useState<number | null>(null);

  return (
    <div className="space-y-1.5">
      <p className="text-sm font-medium text-gray-700 dark:text-gray-200">{label}</p>
      <div role="group" aria-label={label} className="flex items-center gap-1">
        {Array.from({ length: 5 }, (_, i) => {
          const star = i + 1;
          const filled = star <= (hovered ?? value ?? 0);
          return (
            <button
              key={star}
              type="button"
              aria-label={`${star} étoile${star > 1 ? "s" : ""}`}
              onClick={() => onChange(star)}
              onMouseEnter={() => setHovered(star)}
              onMouseLeave={() => setHovered(null)}
              className={`transition-colors duration-100 ${
                filled
                  ? "text-amber-400 hover:text-amber-500"
                  : "text-muted-foreground hover:text-amber-300"
              }`}
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill={filled ? "currentColor" : "none"}
                stroke="currentColor"
                strokeWidth={filled ? 0 : 1.5}
                className="w-7 h-7"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d={STAR_PATH}
                />
              </svg>
            </button>
          );
        })}
        {value !== null && (
          <span className="ml-1 text-sm text-muted-foreground">
            {value} / 5
          </span>
        )}
      </div>
    </div>
  );
}
