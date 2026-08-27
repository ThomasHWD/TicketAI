import { useId, useState } from "react";
import { renderMarkdown } from "../../../components/ticket/utils";
import { SEUIL_EXPANSION } from "./utils";

export default function ExpandableText({ text, label }: { text: string; label?: string }) {
  const [expanded, setExpanded] = useState(false);
  const id = useId();
  const textId = `expandable-${id}`;
  const long = text.length > SEUIL_EXPANSION;
  return (
    <div>
      <p
        id={textId}
        className={`text-sm leading-relaxed text-gray-500 dark:text-gray-400 ${
          !expanded && long ? "line-clamp-3" : ""
        }`}
      >
        {renderMarkdown(text)}
      </p>
      {long && (
        <button
          onClick={() => setExpanded((e) => !e)}
          aria-expanded={expanded}
          aria-controls={textId}
          aria-label={
            label
              ? expanded
                ? `Réduire — ${label}`
                : `Voir tout — ${label}`
              : undefined
          }
          className="mt-1 text-xs font-medium text-emerald-600 dark:text-emerald-400 hover:text-emerald-700 dark:hover:text-emerald-300 transition-colors"
        >
          {expanded ? "Réduire" : "Voir tout"}
        </button>
      )}
    </div>
  );
}
