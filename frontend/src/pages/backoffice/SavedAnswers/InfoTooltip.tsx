import { useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Info } from "lucide-react";

type Props = {
  content: string;
  size?: number;
  className?: string;
};

export default function InfoTooltip({ content, size = 12, className = "" }: Props) {
  const id = useId();
  const triggerRef = useRef<HTMLSpanElement>(null);
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(null);

  function show() {
    if (!triggerRef.current) return;
    const r = triggerRef.current.getBoundingClientRect();
    setCoords({ top: r.top - 8, left: r.left + r.width / 2 });
  }

  function hide() {
    setCoords(null);
  }

  return (
    <span className={`inline-flex ${className}`}>
      <span
        ref={triggerRef}
        tabIndex={0}
        aria-describedby={id}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        className="cursor-help rounded-sm outline-none focus-visible:ring-1 focus-visible:ring-gray-400/60"
      >
        <Info size={size} className="text-gray-500 dark:text-gray-400" aria-hidden="true" />
      </span>
      {createPortal(
        <span
          id={id}
          role="tooltip"
          style={
            coords
              ? {
                  position: "fixed",
                  top: coords.top,
                  left: coords.left,
                  transform: "translateX(-50%) translateY(-100%)",
                  zIndex: 9999,
                }
              : { display: "none" }
          }
          className="pointer-events-none w-max max-w-[220px] px-2.5 py-1.5 rounded-lg bg-gray-900 dark:bg-gray-700 text-white text-xs leading-snug text-center shadow-lg"
        >
          {content}
          <span
            className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900 dark:border-t-gray-700"
            aria-hidden="true"
          />
        </span>,
        document.body
      )}
    </span>
  );
}
