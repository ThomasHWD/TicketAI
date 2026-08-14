import { useState } from "react";
import { SEUIL_EXPANSION } from "./utils";

export default function ExpandableText({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  const long = text.length > SEUIL_EXPANSION;
  return (
    <div>
      <p
        className={`text-sm leading-relaxed whitespace-pre-wrap text-gray-600 dark:text-gray-300 ${
          !expanded && long ? "line-clamp-3" : ""
        }`}
      >
        {text}
      </p>
      {long && (
        <button
          onClick={() => setExpanded((e) => !e)}
          aria-expanded={expanded}
          className="mt-1 py-1 text-xs font-medium text-emerald-600 dark:text-emerald-400 hover:underline"
        >
          {expanded ? "Réduire ↑" : "Voir tout ↓"}
        </button>
      )}
    </div>
  );
}
