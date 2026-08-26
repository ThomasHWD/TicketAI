import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Plus } from "lucide-react";

type Props = {
  id?: string;
  value: string;
  onChange: (v: string) => void;
  existing: string[];
};

export default function DomaineCombobox({ id, value, onChange, existing }: Props) {
  const [open, setOpen] = useState(false);
  const [focusedIdx, setFocusedIdx] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  const q = value.trim().toUpperCase();
  const exactMatch = existing.includes(q);
  const canCreate = q.length >= 2 && !exactMatch;

  // Matching existing domains — filter by current query when non-empty
  const matchingExisting = q.length >= 1
    ? existing.filter((d) => d.startsWith(q) || d.includes(q))
    : existing.slice(0, 8); // cap at 8 when empty to avoid a huge dropdown

  const options: Array<{ type: "existing" | "create"; value: string }> = [
    ...matchingExisting.map((d) => ({ type: "existing" as const, value: d })),
    ...(canCreate ? [{ type: "create" as const, value: q }] : []),
  ];

  const showDropdown = open && options.length > 0;

  useEffect(() => {
    function onOut(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
        setFocusedIdx(-1);
      }
    }
    document.addEventListener("mousedown", onOut);
    return () => document.removeEventListener("mousedown", onOut);
  }, []);

  useEffect(() => {
    setFocusedIdx(-1);
  }, [q]);

  const inputRect = showDropdown ? inputRef.current?.getBoundingClientRect() : null;

  function optionId(idx: number) {
    return options[idx]?.type === "create" ? "domaine-option-create" : `domaine-option-${idx}`;
  }

  const activedescendant = focusedIdx >= 0 && focusedIdx < options.length
    ? optionId(focusedIdx)
    : undefined;

  function select(val: string) {
    onChange(val);
    setOpen(false);
    setFocusedIdx(-1);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        setOpen(true);
        e.preventDefault();
      }
      return;
    }
    if (e.key === "Escape") {
      setOpen(false);
      setFocusedIdx(-1);
      e.preventDefault();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setFocusedIdx((i) => (options.length > 0 ? Math.min(i + 1, options.length - 1) : -1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setFocusedIdx((i) => Math.max(i - 1, -1));
    } else if (e.key === "Enter" && focusedIdx >= 0 && focusedIdx < options.length) {
      e.preventDefault();
      select(options[focusedIdx].value);
    }
  }

  return (
    <div ref={wrapRef} className="flex flex-col gap-1">
      <input
        ref={inputRef}
        id={id}
        required
        type="text"
        value={value}
        placeholder="ex : RH"
        role="combobox"Domaine
        aria-expanded={open}
        aria-autocomplete="list"
        aria-controls={showDropdown ? "domaine-listbox" : undefined}
        aria-haspopup="listbox"
        aria-activedescendant={activedescendant}
        onFocus={() => setOpen(true)}
        onKeyDown={handleKeyDown}
        onChange={(e) => {
          onChange(e.target.value.toUpperCase());
          setOpen(true);
        }}
        className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-sm text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1"
      />
      {showDropdown &&
        inputRect &&
        createPortal(
          <ul
            id="domaine-listbox"
            role="listbox"
            aria-label="Domaines disponibles"
            style={{
              position: "fixed",
              top: inputRect.bottom + 4,
              left: inputRect.left,
              width: inputRect.width,
              zIndex: 9999,
            }}
            className="rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-[#141416] shadow-xl overflow-hidden"
          >
            {options.map((opt, idx) => {
              const itemId = optionId(idx);
              const isFocused = focusedIdx === idx;
              if (opt.type === "existing") {
                return (
                  <li key={opt.value} id={itemId} role="option" aria-selected={isFocused}>
                    <button
                      type="button"
                      onMouseDown={() => select(opt.value)}
                      className={`w-full text-left px-3 py-2.5 text-sm text-gray-700 dark:text-gray-300 transition-colors ${
                        isFocused
                          ? "bg-gray-50 dark:bg-white/10"
                          : "hover:bg-gray-50 dark:hover:bg-white/10"
                      }`}
                    >
                      {opt.value}
                    </button>
                  </li>
                );
              }
              return (
                <li key="create" id={itemId} role="option" aria-selected={isFocused}>
                  <button
                    type="button"
                    onMouseDown={() => select(opt.value)}
                    className={`w-full text-left px-3 py-2.5 text-sm font-medium text-emerald-700 dark:text-emerald-400 flex items-center gap-2 transition-colors ${
                      isFocused
                        ? "bg-emerald-50 dark:bg-emerald-400/10"
                        : "hover:bg-emerald-50 dark:hover:bg-emerald-400/10"
                    }`}
                  >
                    <Plus size={13} aria-hidden="true" />
                    Créer «&nbsp;<span>{opt.value}</span>&nbsp;»
                  </button>
                </li>
              );
            })}
          </ul>,
          document.body
        )}
    </div>
  );
}
