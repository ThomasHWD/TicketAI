import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Plus } from "lucide-react";

type Props = {
  value: string;
  onChange: (v: string) => void;
  existing: string[];
};

export default function DomaineCombobox({ value, onChange, existing }: Props) {
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  const q = value.trim().toUpperCase();
  const matches = existing.filter((d) => d.includes(q));
  const canCreate = q.length > 0 && matches.length === 0;

  useEffect(() => {
    function onOut(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onOut);
    return () => document.removeEventListener("mousedown", onOut);
  }, []);

  const inputRect = open ? inputRef.current?.getBoundingClientRect() : null;

  return (
    <div ref={wrapRef}>
      <input
        ref={inputRef}
        required
        type="text"
        value={value}
        placeholder="ex : RH"
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          onChange(e.target.value.toUpperCase());
          setOpen(true);
        }}
        className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-sm text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
      />
      {open &&
        inputRect &&
        (matches.length > 0 || canCreate) &&
        createPortal(
          <ul
            style={{
              position: "fixed",
              top: inputRect.bottom + 4,
              left: inputRect.left,
              width: inputRect.width,
              zIndex: 9999,
            }}
            className="rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-gray-900 shadow-xl overflow-hidden"
          >
            {matches.map((d) => (
              <li
                key={d}
                className="flex items-center justify-between px-3 py-2.5 text-sm text-gray-400 dark:text-gray-500 select-none cursor-not-allowed"
              >
                <span className="font-mono">{d}</span>
                <span className="text-xs bg-gray-100 dark:bg-white/5 px-1.5 py-0.5 rounded">
                  déjà utilisé
                </span>
              </li>
            ))}
            {canCreate && (
              <li>
                <button
                  type="button"
                  onMouseDown={() => {
                    onChange(q);
                    setOpen(false);
                  }}
                  className="w-full text-left px-3 py-2.5 text-sm font-medium text-emerald-700 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-400/10 flex items-center gap-2"
                >
                  <Plus size={13} />
                  Créer «&nbsp;<span className="font-mono">{q}</span>&nbsp;»
                </button>
              </li>
            )}
          </ul>,
          document.body
        )}
    </div>
  );
}
