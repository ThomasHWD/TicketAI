import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, Loader2, Megaphone, Save, TriangleAlert, Wrench } from "lucide-react";
import { getSiteConfig, setSiteConfig } from "../../../lib/api";
import MarqueeBanner from "../../../components/ui/MarqueeBanner";
import { useDialogFocus } from "../../../hooks/useDialogFocus";

const BANNER_MAX = 200;
const MAINT_MAX  = 300;

function Toggle({
  checked,
  onChange,
  color = "emerald",
  label,
}: {
  checked: boolean;
  onChange: () => void;
  color?: "emerald" | "amber";
  label?: string;
}) {
  const bg = checked
    ? color === "amber" ? "bg-amber-500" : "bg-emerald-500"
    : "bg-gray-200 dark:bg-white/[0.12]";
  return (
    <span className="p-2 -m-2 inline-flex shrink-0">
      <button
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={onChange}
        className={`relative w-10 h-5 rounded-full transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 ${
          color === "amber" ? "focus-visible:ring-amber-500" : "focus-visible:ring-emerald-500"
        } ${bg}`}
      >
        <span
          className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow-sm transition-transform duration-150 ${
            checked ? "translate-x-5" : ""
          }`}
        />
      </button>
    </span>
  );
}

function CardActions({
  isDirty,
  isPending,
  isSuccess,
  isError,
  onReset,
  onSave,
}: {
  isDirty: boolean;
  isPending: boolean;
  isSuccess: boolean;
  isError: boolean;
  onReset: () => void;
  onSave: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 pt-1">
      <button
        onClick={onReset}
        disabled={!isDirty || isPending}
        className="text-xs text-muted-foreground hover:text-gray-700 dark:hover:text-gray-200 disabled:opacity-40 transition-colors"
      >
        Réinitialiser
      </button>
      <div className="flex items-center gap-3">
        {isError && (
          <p role="alert" aria-live="assertive" className="flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400">
            <AlertCircle size={12} aria-hidden="true" />
            Échec de l'enregistrement
            {" · "}
            <button onClick={onSave} className="underline underline-offset-2 hover:text-red-600 transition-colors">
              Réessayer
            </button>
          </p>
        )}
        {isSuccess && (
          <span className="flex items-center gap-1.5 text-sm text-emerald-700 dark:text-emerald-400">
            <CheckCircle2 size={14} aria-hidden="true" />
            Enregistré
          </span>
        )}
        <button
          onClick={onSave}
          disabled={!isDirty || isPending}
          className="flex items-center gap-2 bg-primary hover:bg-primary-hover disabled:opacity-60 text-primary-foreground text-sm font-medium px-4 py-2 rounded-md transition-colors"
        >
          {isPending ? (
            <Loader2 size={14} className="motion-safe:animate-spin" aria-hidden="true" />
          ) : (
            <Save size={14} aria-hidden="true" />
          )}
          Enregistrer
        </button>
      </div>
    </div>
  );
}

function MaintConfirmDialog({
  onConfirm,
  onCancel,
}: {
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  // Action destructive (déconnecte tout le monde) : le focus part sur « Annuler ».
  useDialogFocus(dialogRef, { onClose: onCancel, initialFocus: cancelRef });
  return (
    <div ref={dialogRef} className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-labelledby="maint-confirm-title">
      <div
        className="absolute inset-0 bg-black/40 dark:bg-black/60 backdrop-blur-sm"
        onClick={onCancel}
        aria-hidden="true"
      />
      <div className="relative glass-card rounded-2xl p-6 max-w-sm w-full shadow-2xl">
        <div className="flex flex-col items-center gap-4 text-center">
          <div className="w-10 h-10 rounded-xl bg-amber-100 dark:bg-amber-500/15 flex items-center justify-center shrink-0">
            <TriangleAlert size={20} className="text-amber-600 dark:text-amber-400" aria-hidden="true" />
          </div>
          <div>
            <p id="maint-confirm-title" className="text-sm font-semibold text-gray-800 dark:text-gray-100">
              Activer le mode maintenance ?
            </p>
            <p className="mt-1.5 text-xs text-muted-foreground leading-relaxed">
              Tous les utilisateurs non-admins seront déconnectés du service.
              <br />
              Vous conserverez votre accès en tant qu'admin.
            </p>
          </div>
          <div className="flex gap-2 w-full">
            <button
              ref={cancelRef}
              onClick={onCancel}
              className="flex-1 text-sm font-medium text-gray-600 dark:text-gray-300 px-4 py-2 rounded-lg border border-gray-200 dark:border-white/10 hover:bg-gray-50 dark:hover:bg-white/[0.04] transition-colors"
            >
              Annuler
            </button>
            <button
              onClick={onConfirm}
              className="flex-1 text-sm font-medium text-amber-950 px-4 py-2 rounded-lg bg-amber-500 hover:bg-amber-600 transition-colors"
            >
              Activer quand même
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function UnpublishedBadge() {
  return (
    <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-200/70 dark:border-amber-500/20">
      Non publié
    </span>
  );
}

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
  const [urlError, setUrlError]           = useState<string | null>(null);

  const message = bannerMessage ?? data?.banner.message ?? "";
  const active  = bannerActive  ?? data?.banner.active  ?? false;
  const url     = bannerUrl     ?? data?.banner.url     ?? "";

  const isDirty = data != null && (
    message !== (data.banner.message ?? "") ||
    active  !== (data.banner.active  ?? false) ||
    url     !== (data.banner.url     ?? "")
  );

  const [maintActive, setMaintActive]     = useState<boolean | null>(null);
  const [maintMessage, setMaintMessage]   = useState<string | null>(null);
  const [showMaintConfirm, setShowMaintConfirm] = useState(false);

  const mActive  = maintActive  ?? data?.maintenance?.active  ?? false;
  const mMessage = maintMessage ?? data?.maintenance?.message ?? "";

  const isDirtyMaintenance = data != null && (
    mActive  !== (data.maintenance?.active  ?? false) ||
    mMessage !== (data.maintenance?.message ?? "")
  );

  useEffect(() => {
    onDirtyChange?.(isDirty || isDirtyMaintenance);
  }, [isDirty, isDirtyMaintenance, onDirtyChange]);

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
  useEffect(() => {
    if (!url.trim() || /^https?:\/\/.+/.test(url.trim())) setUrlError(null);
  }, [url]);

  const mutationMaintenance = useMutation({
    mutationFn: () => setSiteConfig("maintenance", { active: mActive, message: mMessage }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["site-config"] }),
  });
  useEffect(() => {
    if (!mutationMaintenance.isSuccess) return;
    const t = setTimeout(mutationMaintenance.reset, 3000);
    return () => clearTimeout(t);
  }, [mutationMaintenance.isSuccess, mutationMaintenance.reset]);

  const handleSave = () => {
    if (active && !message.trim()) {
      setValidationError("Ajoutez un message avant d'activer la bannière.");
      return;
    }
    if (url.trim() && !/^https?:\/\/.+/.test(url.trim())) {
      setUrlError("L'URL doit commencer par https:// ou http://");
      return;
    }
    setValidationError(null);
    setUrlError(null);
    mutation.mutate();
  };

  const handleSaveMaintenance = () => {
    const wasActive = data?.maintenance?.active ?? false;
    if (mActive && !wasActive) {
      setShowMaintConfirm(true);
      return;
    }
    mutationMaintenance.mutate();
  };

  const confirmMaintenance = () => {
    setShowMaintConfirm(false);
    mutationMaintenance.mutate();
  };

  const Sep = () => <div className="h-px bg-gray-100 dark:bg-white/[0.06]" />;
  const inputCls = "w-full rounded-lg border border-gray-200 dark:border-white/10 bg-white/60 dark:bg-white/[0.04] px-3.5 py-2.5 text-sm text-gray-900 dark:text-gray-100 placeholder:text-muted-foreground resize-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 transition";

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-muted-foreground">
        <Loader2 size={18} className="motion-safe:animate-spin" aria-hidden="true" />
      </div>
    );
  }

  return (
    <>
      {showMaintConfirm && (
        <MaintConfirmDialog
          onConfirm={confirmMaintenance}
          onCancel={() => setShowMaintConfirm(false)}
        />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 max-w-4xl">

        <div className="glass-card rounded-2xl overflow-hidden flex flex-col">

          <div className="flex items-start gap-3 px-5 py-4 border-b border-gray-100 dark:border-white/[0.06]">
            <div className="w-9 h-9 rounded-xl bg-emerald-50 dark:bg-emerald-500/10 flex items-center justify-center shrink-0 mt-0.5">
              <Megaphone size={16} className="text-emerald-600 dark:text-emerald-400" aria-hidden="true" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">Bannière d'annonce</p>
                {active ? (
                  <span aria-hidden="true" className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/20">
                    Active
                  </span>
                ) : (
                  <span aria-hidden="true" className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-gray-100 dark:bg-white/[0.06] text-muted-foreground">
                    Inactive
                  </span>
                )}
                {isDirty && <UnpublishedBadge />}
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Bandeau défilant affiché dans la barre de navigation pour tous les utilisateurs.
              </p>
            </div>
            <Toggle checked={active} onChange={() => setBannerActive(!active)} label="Activer la bannière d'annonce" />
          </div>

          <div className="px-5 py-4 space-y-4 flex-1">

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label htmlFor="banner-message" className="text-xs font-medium text-muted-foreground">
                  Message
                </label>
                <span className={`text-xs tabular-nums ${message.length > BANNER_MAX * 0.9 ? "text-amber-700 dark:text-amber-400" : "text-muted-foreground"}`}>
                  {message.length} / {BANNER_MAX} car.
                </span>
              </div>
              <textarea
                id="banner-message"
                rows={3}
                maxLength={BANNER_MAX}
                value={message}
                onChange={(e) => setBannerMessage(e.target.value)}
                placeholder="Maintenance planifiée, information générale…"
                className={inputCls}
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="banner-url" className="text-xs font-medium text-muted-foreground">
                Lien <span className="font-normal">(optionnel)</span>
              </label>
              <input
                id="banner-url"
                type="url"
                value={url}
                onChange={(e) => { setBannerUrl(e.target.value); }}
                placeholder="https://…"
                aria-describedby={urlError ? "banner-url-error" : undefined}
                className={`${inputCls} ${urlError ? "border-red-400 focus-visible:ring-red-400" : ""}`}
              />
              {urlError && (
                <p id="banner-url-error" role="alert" className="flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400">
                  <AlertCircle size={11} aria-hidden="true" /> {urlError}
                </p>
              )}
            </div>

            <Sep />

            <div className="space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground">Prévisualisation</p>
              <div className="overflow-hidden rounded-xl border border-gray-200 dark:border-white/10">
                <div className="h-10 flex items-center gap-2 px-3 bg-white dark:bg-[#111113]">
                  {active && message ? (
                    <MarqueeBanner message={message} url={url || undefined} />
                  ) : (
                    <div className="flex-1 flex items-center gap-2 px-1 min-w-0">
                      <Megaphone size={12} className="text-subtle shrink-0" aria-hidden="true" />
                      <span className="text-xs text-muted-foreground italic truncate">
                        {!active ? "Bannière désactivée" : "Aucun message saisi"}
                      </span>
                    </div>
                  )}
                  <div className="flex items-center gap-1 shrink-0" aria-hidden="true">
                    <div className="w-5 h-5 rounded bg-gray-100 dark:bg-white/[0.06]" />
                    <div className="w-5 h-5 rounded bg-gray-100 dark:bg-white/[0.06]" />
                    <div className="w-10 h-5 rounded bg-emerald-100 dark:bg-emerald-500/10" />
                  </div>
                </div>
              </div>
            </div>

            {validationError && (
              <p className="flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400" role="alert">
                <AlertCircle size={12} aria-hidden="true" /> {validationError}
              </p>
            )}
          </div>

          <div className="px-5 pb-4">
            <CardActions
              isDirty={isDirty}
              isPending={mutation.isPending}
              isSuccess={mutation.isSuccess}
              isError={mutation.isError && !validationError && !urlError}
              onReset={() => { setBannerMessage(null); setBannerActive(null); setBannerUrl(null); setValidationError(null); setUrlError(null); }}
              onSave={handleSave}
            />
          </div>
        </div>

        <div className={`glass-card rounded-2xl overflow-hidden flex flex-col transition-shadow duration-200 ${
          mActive ? "ring-1 ring-amber-300/50 dark:ring-amber-500/25" : ""
        }`}>

          <div className={`flex items-start gap-3 px-5 py-4 border-b transition-colors duration-200 ${
            mActive
              ? "bg-amber-50/60 dark:bg-amber-500/10 border-amber-200/70 dark:border-amber-500/20"
              : "border-gray-100 dark:border-white/[0.06]"
          }`}>
            <div className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 mt-0.5 transition-colors duration-200 ${
              mActive
                ? "bg-amber-100 dark:bg-amber-500/15"
                : "bg-gray-100 dark:bg-white/[0.06]"
            }`}>
              <Wrench size={16} className={mActive ? "text-amber-600 dark:text-amber-400" : "text-subtle"} aria-hidden="true" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">Mode maintenance</p>
                {mActive ? (
                  <span aria-hidden="true" className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-400 border border-amber-300/60 dark:border-amber-500/25">
                    Actif
                  </span>
                ) : (
                  <span aria-hidden="true" className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-gray-100 dark:bg-white/[0.06] text-muted-foreground">
                    Inactif
                  </span>
                )}
                {isDirtyMaintenance && <UnpublishedBadge />}
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Bloque l'accès au site pour tous les utilisateurs non-admins.
              </p>
            </div>
            <Toggle checked={mActive} onChange={() => setMaintActive(!mActive)} color="amber" label="Activer le mode maintenance" />
          </div>

          <div className="px-5 py-4 space-y-4 flex-1">

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label htmlFor="maint-message" className="text-xs font-medium text-muted-foreground">
                  Message <span className="font-normal">(optionnel)</span>
                </label>
                <span className={`text-xs tabular-nums ${mMessage.length > MAINT_MAX * 0.9 ? "text-amber-700 dark:text-amber-400" : "text-muted-foreground"}`}>
                  {mMessage.length} / {MAINT_MAX} car.
                </span>
              </div>
              <textarea
                id="maint-message"
                rows={3}
                maxLength={MAINT_MAX}
                value={mMessage}
                onChange={(e) => setMaintMessage(e.target.value)}
                placeholder="Ex. : Travaux planifiés jusqu'à 14h. Merci de votre compréhension."
                className={inputCls}
              />
            </div>

            <Sep />

            <div className="space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground">Prévisualisation</p>
              <div className="overflow-hidden rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-[#0d0d0d]">
                <div className="py-5 flex flex-col items-center gap-2 px-4">
                  <div className="w-9 h-9 rounded-xl bg-amber-500/10 flex items-center justify-center">
                    <Wrench size={16} className="text-amber-500" aria-hidden="true" />
                  </div>
                  <p className="text-xs font-semibold text-gray-800 dark:text-gray-100">Site en maintenance</p>
                  <p className="text-[11px] text-muted-foreground text-center leading-relaxed">
                    {mMessage || (
                      <span className="italic">Nous effectuons des opérations de maintenance. Le service sera bientôt disponible.</span>
                    )}
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="px-5 pb-4">
            <CardActions
              isDirty={isDirtyMaintenance}
              isPending={mutationMaintenance.isPending}
              isSuccess={mutationMaintenance.isSuccess}
              isError={mutationMaintenance.isError}
              onReset={() => { setMaintActive(null); setMaintMessage(null); }}
              onSave={handleSaveMaintenance}
            />
          </div>
        </div>

      </div>
    </>
  );
}
