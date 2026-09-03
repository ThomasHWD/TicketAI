import type { ServiceHealth } from "../../lib/api";

export function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)} M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(n >= 10_000 ? 0 : 1)} k`;
  return String(n);
}

export function cleanModelName(raw: string): string {
  const s = raw
    .replace(/^[^/]+\//, "")
    .replace(/-instruct.*$/i, "")
    .replace(/-\d{4}$/, "");
  const parts = s.split("-").filter((p) => !/^\d+$/.test(p));
  return parts.map((w) => w.toUpperCase()).join(" ").trim() || raw.toUpperCase();
}

export function ServiceRow({ svc, label }: { svc: ServiceHealth; label: string }) {
  const ok = svc.status === "ok";
  return (
    <li className="flex items-start gap-3 py-2.5 border-b border-gray-100 dark:border-white/[0.06] last:border-0">
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 mt-[0.375rem] ${ok ? "bg-emerald-500" : "bg-red-500"}`} />
      <div className="flex-1 min-w-0">
        <span className="text-sm text-gray-700 dark:text-gray-200">{label}</span>
        {!ok && svc.detail && (
          <p className="text-xs text-red-500 dark:text-red-400 mt-0.5">{svc.detail}</p>
        )}
      </div>
      {svc.latency_ms != null && ok && (
        <span className="font-mono text-xs text-gray-500 dark:text-gray-400 tabular-nums mt-0.5">
          {svc.latency_ms} ms
        </span>
      )}
      <span className={`text-xs font-medium min-w-[3rem] text-right mt-0.5 shrink-0 ${ok ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
        {ok ? "OK" : "Erreur"}
      </span>
    </li>
  );
}

export function MetricChip({ label, value, mono = false }: { label: string; value: string | number | null; mono?: boolean }) {
  return (
    <div className="glass-card rounded-xl px-4 py-3.5">
      <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
      <p className={`mt-1 text-sm font-semibold text-gray-900 dark:text-gray-50 tabular-nums ${mono ? "font-mono" : ""}`}>
        {value ?? "—"}
      </p>
    </div>
  );
}

export function PipelineRow({
  label, hint, value, warn = false, danger = false,
}: {
  label: string; hint?: string; value: number | null; warn?: boolean; danger?: boolean;
}) {
  const valueClass = danger
    ? "text-red-600 dark:text-red-400"
    : warn
    ? "text-amber-600 dark:text-amber-400"
    : "text-gray-700 dark:text-gray-200";

  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-white/[0.06] last:border-0">
      <div>
        <span className="text-sm text-gray-500 dark:text-gray-400">{label}</span>
        {hint && <p className="text-xs text-gray-500 dark:text-gray-400">{hint}</p>}
      </div>
      <span className={`font-mono text-sm font-medium tabular-nums ${valueClass}`}>{value ?? "—"}</span>
    </div>
  );
}

export function MetricBar({
  pct, value, limit, formatValue, barClass, valueClass,
}: {
  pct: number;
  value: string | number;
  limit: string | number | null;
  formatValue?: (v: string | number) => string;
  barClass: string;
  valueClass: string;
}) {
  const display = formatValue ? formatValue(value) : String(value);
  const limitDisplay = limit != null ? (formatValue ? formatValue(limit) : String(limit)) : null;
  return (
    <div className="flex flex-col gap-1 min-w-0">
      <div className="flex items-baseline justify-between gap-2">
        <span className={`font-mono text-xs tabular-nums whitespace-nowrap ${valueClass}`}>
          {display}
          {limitDisplay != null && <span className="text-gray-400 dark:text-gray-500"> / {limitDisplay}</span>}
        </span>
        {limitDisplay != null && (
          <span className={`text-[10px] tabular-nums shrink-0 ${valueClass}`}>{Math.round(pct)}%</span>
        )}
      </div>
      <div className="h-1.5 rounded-full bg-gray-100 dark:bg-white/[0.08] overflow-hidden">
        <div className={`h-full rounded-full transition-[width] duration-700 ease-out ${barClass}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
