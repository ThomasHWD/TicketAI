import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, Loader2, Megaphone, Save } from "lucide-react";
import { getSiteConfig, setSiteConfig } from "../../../lib/api";
import MarqueeBanner from "../../../components/ui/MarqueeBanner";

export default function BanniereTab({
  onDirtyChange,
}: {
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["site-config"], queryFn: getSiteConfig });

  const [bannerMessage, setBannerMessage] = useState<string | null>(null);
  const [bannerActive, setBannerActive]   = useState<boolean | null>(null);
  const [bannerUrl, setBannerUrl]         = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const message = bannerMessage ?? data?.banner.message ?? "";
  const active  = bannerActive  ?? data?.banner.active  ?? false;
  const url     = bannerUrl     ?? data?.banner.url     ?? "";

  const isDirty = data != null && (
    message !== (data.banner.message ?? "") ||
    active !== (data.banner.active ?? false) ||
    url !== (data.banner.url ?? "")
  );

  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);

  const mutation = useMutation({
    mutationFn: () => setSiteConfig("banner", { active, message, url }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["site-config"] }),
  });

  useEffect(() => {
    if (!mutation.isSuccess) return;
    const t = setTimeout(mutation.reset, 3000);
    return () => clearTimeout(t);
  }, [mutation.isSuccess, mutation.reset]);

  useEffect(() => {
    if (active && message.trim()) setValidationError(null);
  }, [active, message]);

  const handleSave = () => {
    if (active && !message.trim()) {
      setValidationError("Ajoutez un message avant d'activer la bannière.");
      return;
    }
    setValidationError(null);
    mutation.mutate();
  };

  const handleReset = () => {
    setBannerMessage(null);
    setBannerActive(null);
    setBannerUrl(null);
    setValidationError(null);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-gray-400">
        <Loader2 size={18} className="animate-spin" aria-hidden="true" />
      </div>
    );
  }

  return (
    <div className="max-w-xl space-y-5">
      <div className="glass-card rounded-2xl p-6 space-y-5">

        {/* Toggle */}
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0">
            <p className="text-sm font-medium text-gray-800 dark:text-gray-100">
              Bannière d'annonce
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              Affichée dans la barre de navigation pour tous les utilisateurs.
            </p>
          </div>
          <button
            role="switch"
            aria-checked={active}
            onClick={() => setBannerActive(!active)}
            className={`relative w-10 h-5 rounded-full transition-colors duration-150 shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 ${
              active ? "bg-emerald-500" : "bg-gray-200 dark:bg-white/[0.12]"
            }`}
          >
            <span
              className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow-sm transition-transform duration-150 ${
                active ? "translate-x-5" : ""
              }`}
            />
          </button>
        </div>

        <div className="h-px bg-gray-100 dark:bg-white/[0.06]" />

        {/* Message */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <label
              htmlFor="banner-message"
              className="text-xs font-medium text-gray-500 dark:text-gray-400"
            >
              Message
            </label>
            <span className="text-xs text-gray-500 dark:text-gray-400 tabular-nums">
              {message.length} car.
            </span>
          </div>
          <textarea
            id="banner-message"
            rows={3}
            value={message}
            onChange={(e) => setBannerMessage(e.target.value)}
            placeholder="Saisissez le message à afficher dans la bannière…"
            className="w-full rounded-lg border border-gray-200 dark:border-white/10 bg-white/60 dark:bg-white/[0.04] px-3.5 py-2.5 text-sm text-gray-900 dark:text-gray-100 placeholder:text-gray-400 resize-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 transition"
          />
        </div>

        {/* URL */}
        <div className="space-y-1.5">
          <label
            htmlFor="banner-url"
            className="text-xs font-medium text-gray-500 dark:text-gray-400"
          >
            Lien{" "}
            <span className="font-normal text-gray-500 dark:text-gray-400">(optionnel)</span>
          </label>
          <input
            id="banner-url"
            type="url"
            value={url}
            onChange={(e) => setBannerUrl(e.target.value)}
            placeholder="https://…"
            className="w-full rounded-lg border border-gray-200 dark:border-white/10 bg-white/60 dark:bg-white/[0.04] px-3.5 py-2.5 text-sm text-gray-900 dark:text-gray-100 placeholder:text-gray-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 transition"
          />
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Le lien s'ouvre dans un nouvel onglet lors du clic sur la bannière.
          </p>
        </div>

        <div className="h-px bg-gray-100 dark:bg-white/[0.06]" />

        {/* Live preview */}
        <div className="space-y-2">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
            Prévisualisation dans la barre de navigation
          </p>
          <div className="overflow-hidden rounded-xl border border-gray-200 dark:border-white/10">
            <div className="h-11 flex items-center gap-2 px-3 bg-white dark:bg-[#111113]">
              {active && message ? (
                <MarqueeBanner message={message} url={url || undefined} />
              ) : (
                <div className="flex-1 flex items-center gap-2 px-2 min-w-0">
                  <Megaphone
                    size={13}
                    className="text-gray-300 dark:text-white/20 shrink-0"
                    aria-hidden="true"
                  />
                  <span className="text-xs text-gray-500 dark:text-gray-400 italic truncate">
                    {!active ? "Bannière désactivée — aucun message affiché" : "Aucun message saisi"}
                  </span>
                </div>
              )}
              <div className="flex items-center gap-1.5 shrink-0 pl-2">
                <div className="w-6 h-6 rounded bg-gray-100 dark:bg-white/[0.06]" />
                <div className="w-6 h-6 rounded bg-gray-100 dark:bg-white/[0.06]" />
                <div className="w-px h-4 bg-gray-200 dark:bg-white/10" />
                <div className="w-14 h-6 rounded-md bg-emerald-100 dark:bg-emerald-500/10" />
                <div className="w-6 h-6 rounded-full bg-gray-100 dark:bg-white/[0.06]" />
              </div>
            </div>
          </div>
        </div>

        {/* Validation / save errors */}
        {validationError && (
          <p className="flex items-center gap-1.5 text-xs text-red-500" role="alert">
            <AlertCircle size={12} aria-hidden="true" />
            {validationError}
          </p>
        )}
        {mutation.isError && !validationError && (
          <p className="flex items-center gap-1.5 text-xs text-red-500" role="alert">
            <AlertCircle size={12} aria-hidden="true" />
            Échec de l'enregistrement — réessayez ou contactez le support.
          </p>
        )}

        {/* Actions */}
        <div className="flex items-center justify-between gap-3 pt-1">
          <button
            onClick={handleReset}
            disabled={!isDirty || mutation.isPending}
            className="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 disabled:opacity-40 transition-colors"
          >
            Réinitialiser
          </button>
          <div className="flex items-center gap-3">
            {mutation.isSuccess && (
              <span className="flex items-center gap-1.5 text-sm text-emerald-600 dark:text-emerald-400">
                <CheckCircle2 size={14} aria-hidden="true" />
                Enregistré
              </span>
            )}
            <button
              onClick={handleSave}
              disabled={!isDirty || mutation.isPending}
              className="flex items-center gap-2 bg-emerald-500 hover:bg-emerald-600 disabled:opacity-60 text-white text-sm font-medium px-4 py-2 rounded-md transition-colors"
            >
              {mutation.isPending ? (
                <Loader2 size={14} className="animate-spin" aria-hidden="true" />
              ) : (
                <Save size={14} aria-hidden="true" />
              )}
              Enregistrer
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
