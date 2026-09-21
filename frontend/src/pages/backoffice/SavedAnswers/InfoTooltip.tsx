import { useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Info } from "lucide-react";

type Props = {
  content: string;
  size?: number;
  className?: string;
};

type State = {
  open: boolean;
  top: number;
  left: number;
  arrowLeft: number;
  measured: boolean;
};

export default function InfoTooltip({ content, size = 12, className = "" }: Props) {
  const id = useId();
  const triggerRef = useRef<HTMLSpanElement>(null);
  const tooltipRef = useRef<HTMLSpanElement>(null);
  const [state, setState] = useState<State>({
    open: false,
    top: 0,
    left: 0,
    arrowLeft: 0,
    measured: false,
  });

  function show() {
    if (!triggerRef.current) return;
    const r = triggerRef.current.getBoundingClientRect();
    setState({ open: true, top: r.top - 8, left: r.left + r.width / 2, arrowLeft: 0, measured: false });
  }

  function hide() {
    setState((s) => ({ ...s, open: false }));
  }

  // Guard prevents infinite loop — clamps tooltip to viewport and shifts arrow to stay pointed at trigger.
  useLayoutEffect(() => {
    if (!state.open || state.measured || !tooltipRef.current) return;
    const t = tooltipRef.current.getBoundingClientRect();
    const margin = 8;
    const centerX = state.left;
    let newLeft = centerX;

    if (t.right > window.innerWidth - margin) {
      newLeft -= t.right - (window.innerWidth - margin);
    } else if (t.left < margin) {
      newLeft += margin - t.left;
    }

    const arrowLeft = Math.max(8, Math.min(t.width - 8, centerX - newLeft + t.width / 2));
    setState((s) => ({ ...s, left: newLeft, arrowLeft, measured: true }));
  });

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
          ref={tooltipRef}
          id={id}
          role="tooltip"
          style={
            state.open
              ? {
                  position: "fixed",
                  top: state.top,
                  left: state.left,
                  transform: "translateX(-50%) translateY(-100%)",
                  zIndex: 9999,
                  visibility: state.measured ? "visible" : "hidden",
                }
              : { display: "none" }
          }
          className="pointer-events-none w-max max-w-[220px] px-2.5 py-1.5 rounded-lg bg-gray-900 dark:bg-gray-700 text-white text-xs leading-snug text-center shadow-lg"
        >
          {content}
          <span
            style={{ left: `${state.arrowLeft}px` }}
            className="absolute top-full -translate-x-1/2 border-4 border-transparent border-t-gray-900 dark:border-t-gray-700"
            aria-hidden="true"
          />
        </span>,
        document.body
      )}
    </span>
  );
}
