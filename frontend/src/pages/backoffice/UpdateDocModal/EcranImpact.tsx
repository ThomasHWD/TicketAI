import { AlertTriangle, Archive, CheckCircle2, FilePlus2 } from "lucide-react";
import type { UpdateImpact } from "../../../types";
import LigneARelire from "./LigneARelire";
import LigneUnite from "./LigneUnite";

function EcranChangements({ impact }: { impact: UpdateImpact }) {
  const restantes = impact.nb_unites - impact.unites.length;
  const aAnalyser = impact.nb_a_analyser;

  return (
    <div className="rounded-xl border border-amber-200 dark:border-amber-500/30 bg-amber-50/80 dark:bg-amber-400/10 px-4 py-3.5 space-y-2.5">
      <p className="flex items-center gap-2 text-sm font-semibold text-amber-900 dark:text-amber-300">
        <FilePlus2 size={16} />
        {impact.nb_unites} changement{impact.nb_unites > 1 ? "s" : ""} dans le document
      </p>
      <ul className="space-y-2">
        {impact.unites.map((u, i) => (
          <LigneUnite key={i} unite={u} />
        ))}
      </ul>
      {restantes > 0 && (
        <p className="text-[11px] text-amber-900/70 dark:text-amber-200/70">
          … et {restantes} autre{restantes > 1 ? "s" : ""}.
        </p>
      )}
      {aAnalyser > 0 ? (
        <div className="space-y-2.5 pt-1">
          <p className="text-xs text-amber-900/80 dark:text-amber-200/80">
            {aAnalyser} réponse{aAnalyser > 1 ? "s" : ""} enregistrée{aAnalyser > 1 ? "s" : ""}{" "}
            {aAnalyser > 1 ? "seront relues" : "sera relue"} après la mise à jour
            {impact.nb_canoniques > 0 &&
              `, dont ${impact.nb_canoniques} canonique${impact.nb_canoniques > 1 ? "s" : ""}`}
            . Seules celles que le changement contredit seront retirées du service ; les autres ne
            bougeront pas.
          </p>
          <ul className="space-y-2 max-h-64 overflow-y-auto">
            {impact.a_analyser.map((r) => (
              <LigneARelire key={r.reponse_id} reponse={r} />
            ))}
          </ul>
          {aAnalyser > impact.a_analyser.length && (
            <p className="text-[11px] text-amber-900/70 dark:text-amber-200/70">
              … et {aAnalyser - impact.a_analyser.length} autre
              {aAnalyser - impact.a_analyser.length > 1 ? "s" : ""}.
            </p>
          )}
        </div>
      ) : (
        <p className="text-xs text-amber-900/80 dark:text-amber-200/80">
          Aucune réponse enregistrée ne s'appuie sur ce document.
        </p>
      )}
    </div>
  );
}

function EncadrePrioritaires({ impact }: { impact: UpdateImpact }) {
  const n = impact.nb_prioritaires;
  if (n === 0) return null;
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-500/30 bg-slate-50/80 dark:bg-slate-400/10 px-4 py-3.5 space-y-2">
      <p className="flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-300">
        <Archive size={16} />
        {n} réponse{n > 1 ? "s" : ""} {n > 1 ? "citent" : "cite"} un passage modifié
      </p>
      <p className="text-xs text-slate-600/90 dark:text-slate-300/80">
        {n > 1 ? "Elles seront examinées" : "Elle sera examinée"} en premier. Un passage modifié ne
        condamne rien à lui seul — une virgule corrigée suffit à le faire apparaître ici. Le retrait
        du service n'est prononcé que si le changement contredit réellement la réponse.
      </p>
      <ul className="space-y-1 pt-0.5">
        {impact.items.slice(0, 3).map((item) => (
          <li key={item.reponse_id} className="text-[11px] text-slate-600 dark:text-slate-400 line-clamp-1">
            • {item.question}
          </li>
        ))}
      </ul>
    </div>
  );
}

function EcranSansChangement({ impact }: { impact: UpdateImpact }) {
  if (!impact.diff_analysable) {
    return (
      <div className="rounded-xl border border-slate-200 dark:border-slate-500/30 bg-slate-50/80 dark:bg-slate-400/10 px-4 py-3.5 space-y-1.5">
        <p className="flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-300">
          <AlertTriangle size={16} />
          La version en ligne n'a pas pu être relue.
        </p>
        <p className="text-xs text-slate-600/90 dark:text-slate-300/80">
          Son fichier est introuvable sur le disque : aucune comparaison n'est possible et rien ne
          peut être jugé. Les réponses enregistrées du document seront déposées dans l'onglet À
          relire, à vérifier à la main.
        </p>
      </div>
    );
  }
  return (
    <div className="rounded-xl border border-emerald-200 dark:border-emerald-500/30 bg-emerald-50/80 dark:bg-emerald-400/10 px-4 py-3.5 space-y-1.5">
      <p className="flex items-center gap-2 text-sm font-semibold text-emerald-800 dark:text-emerald-300">
        <CheckCircle2 size={16} />
        Cette version ne dit rien de nouveau.
      </p>
      <p className="text-xs text-emerald-800/80 dark:text-emerald-200/80">
        Mise en forme, espaces, export : le fond est identique. Aucune réponse enregistrée ne sera
        examinée ni dérangée.
      </p>
    </div>
  );
}

export default function EcranImpact({ impact }: { impact: UpdateImpact }) {
  const aDuNeuf = impact.diff_analysable && impact.nb_unites > 0;
  const enAttente = impact.nb_en_attente;

  return (
    <div className="space-y-3">
      {aDuNeuf ? (
        <>
          <EcranChangements impact={impact} />
          <EncadrePrioritaires impact={impact} />
        </>
      ) : (
        <EcranSansChangement impact={impact} />
      )}
      {aDuNeuf && enAttente > 0 && (
        <p className="text-xs text-gray-500 dark:text-gray-400 px-1">
          {enAttente} réponse{enAttente > 1 ? "s" : ""} en attente de validation{" "}
          {enAttente > 1 ? "seront annulées et regénérées" : "sera annulée et regénérée"} sur la
          nouvelle version.
        </p>
      )}
    </div>
  );
}
