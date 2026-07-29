import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Megaphone, Save, Loader2, CheckCircle2 } from "lucide-react";
import { getSiteConfig, setSiteConfig } from "../../lib/api";

export default function SiteConfigPage() {
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["site-config"],
    queryFn: getSiteConfig,
  });

  const [bannerMessage, setBannerMessage] = useState<string | null>(null);
  const [bannerActive, setBannerActive] = useState<boolean | null>(null);
  const [bannerUrl, setBannerUrl] = useState<string | null>(null);

  const message = bannerMessage ?? data?.banner.message ?? "";
  const active  = bannerActive  ?? data?.banner.active  ?? false;
  const url     = bannerUrl     ?? data?.banner.url     ?? "";

  const mutation = useMutation({
    mutationFn: () => setSiteConfig("banner", { active, message, url }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["site-config"] });
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        <Loader2 size={20} className="animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-6 py-10 space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">
          Configuration de l'app
        </h1>
      </div>

      {/* Bannière */}
      <section className="glass-card rounded-2xl p-6 space-y-5">
        <div className="flex items-center gap-2 text-gray-800 dark:text-gray-200">
          <Megaphone size={18} className="text-amber-500" />
          <h2 className="font-medium">Bannière d'annonce</h2>
        </div>

        <div className="space-y-4">
          <label className="flex items-center gap-3 cursor-pointer select-none">
            <div
              role="switch"
              aria-checked={active}
              tabIndex={0}
              onClick={() => setBannerActive(!active)}
              onKeyDown={(e) => e.key === " " && setBannerActive(!active)}
              className={`relative w-10 h-5 rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 ${
                active
                  ? "bg-emerald-500"
                  : "bg-gray-200 dark:bg-white/10"
              }`}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${
                  active ? "translate-x-5" : ""
                }`}
              />
            </div>
            <span className="text-sm text-gray-700 dark:text-gray-300">
              {active ? "Bannière activée" : "Bannière désactivée"}
            </span>
          </label>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              Message
            </label>
            <textarea
              rows={3}
              value={message}
              onChange={(e) => setBannerMessage(e.target.value)}
              placeholder="Saisissez le message à afficher dans la bannière…"
              className="w-full rounded-xl border border-gray-200 dark:border-white/10 bg-white/60 dark:bg-white/5 px-3.5 py-2.5 text-sm text-gray-900 dark:text-gray-100 placeholder:text-gray-400 resize-none focus:outline-none focus:ring-2 focus:ring-emerald-500/50 transition"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              Lien (optionnel)
            </label>
            <input
              type="url"
              value={url}
              onChange={(e) => setBannerUrl(e.target.value)}
              placeholder="https://…"
              className="w-full rounded-xl border border-gray-200 dark:border-white/10 bg-white/60 dark:bg-white/5 px-3.5 py-2.5 text-sm text-gray-900 dark:text-gray-100 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 transition"
            />
          </div>

          {/* Preview */}
          {active && message && (
            <div className="overflow-hidden rounded-xl border border-amber-200 dark:border-amber-500/20 bg-amber-50 dark:bg-amber-500/10 px-4 py-2.5 flex items-center gap-2">
              <Megaphone size={14} className="shrink-0 text-amber-500" />
              <p className="text-sm font-medium text-amber-700 dark:text-amber-300 truncate">
                {message}
              </p>
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 pt-1">
          {mutation.isSuccess && (
            <span className="flex items-center gap-1.5 text-sm text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 size={15} />
              Enregistré
            </span>
          )}
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            className="flex items-center gap-2 bg-emerald-500 hover:bg-emerald-600 disabled:opacity-60 text-white text-sm font-medium px-4 py-2 rounded-xl transition-colors shadow-sm shadow-emerald-200 dark:shadow-none"
          >
            {mutation.isPending ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <Save size={15} />
            )}
            Enregistrer
          </button>
        </div>
      </section>
    </div>
  );
}
