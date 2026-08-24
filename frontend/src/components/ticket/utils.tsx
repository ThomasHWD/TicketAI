import { Fragment } from "react";

export function renderMarkdown(text: string) {
  if (!text) return null;
  return text.split("\n").map((line, i) => (
    <Fragment key={i}>
      {line.split(/(\*\*.*?\*\*)/g).map((part, j) => {
        if (part.startsWith("**") && part.endsWith("**")) {
          return (
            <strong key={j} className="font-bold text-gray-900 dark:text-white">
              {part.slice(2, -2)}
            </strong>
          );
        }
        return <span key={j}>{part}</span>;
      })}
      <br />
    </Fragment>
  ));
}
