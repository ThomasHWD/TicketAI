import { AlertTriangle, CheckCircle2, FileDiff, Flag, ScanSearch } from "lucide-react";
import type { UpdateImpact } from "../../../../types";
import DiffUnite from "./DiffUnite";
import LigneARelire from "./LigneARelire";

function TitreSection({
  icon: Icon,
  children,
  ton = "neutre",
}: {
  icon: typeof FileDiff;
  children: React.ReactNode;
  ton?: "neutre" | "ambre";
}) {
  return (
    <p
      className={`flex items-center gap-2 text-sm font-semibold ${
        ton === "ambre"
          ? "text-amber-800 dark:text-amber-300"
          : "text-gray-900 dark:text-gray-100"
      }`}
    >
      <Icon size={15} className="shrink-0 opacity-70" aria-hidden="true" />
      {children}
    </p>
  );
}

/** Le diff réel : ce que la nouvelle version dit de différent, et rien de plus. */
function BlocChangements({ impact }: { impact: UpdateImpact }) {
  const restantes = impact.nb_unites - impact.unites.length;

  return (
    <section className="space-y-2.5">
      <TitreSection icon={FileDiff}>
        {impact.nb_unites} changement{impact.nb_unites > 1 ? "s" : ""} dans le document
      </TitreSection>
      <ul className="space-y-2">
        {impact.unites.map((u, i) => (
          <DiffUnite key={i} unite={u} />
        ))}
      </ul>
      {restantes > 0 && (
        <p className="text-[11px] text-gray-500 dark:text-gray-400">
          … et {restantes} autre{restantes > 1 ? "s" : ""}.
        </p>
      )}
    </section>
  );
}

/**
 * Ce qui part au jugement. Le ton est ambre et non rouge : la confirmation ne
 * détruit rien, elle enfile des relectures — la plupart des réponses survivront.
 */
function BlocARelire({ impact }: { impact: UpdateImpact }) {
  const n = impact.nb_a_analyser;

  if (n === 0) {
    return (
      <section className="rounded-xl border border-gray-200 bg-gray-50/60 px-4 py-3 dark:border-white/10 dark:bg-white/[0.03]">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Aucune réponse enregistrée ne s'appuie sur ce document.
        </p>
      </section>
    );
  }

  const reste = n - impact.a_analyser.length;

  return (
    <section className="space-y-2.5 rounded-xl border border-amber-200 bg-amber-50/60 px-4 py-3.5 dark:border-amber-500/25 dark:bg-amber-500/[0.07]">
      <TitreSection icon={ScanSearch} ton="ambre">
        Ce qui sera relu
      </TitreSection>
      <p className="text-xs leading-relaxed text-amber-900/80 dark:text-amber-200/80">
        {n} réponse{n > 1 ? "s" : ""} enregistrée{n > 1 ? "s" : ""}{" "}
        {n > 1 ? "seront relues" : "sera relue"} après la mise à jour
        {impact.nb_canoniques > 0 &&
          `, dont ${impact.nb_canoniques} canonique${impact.nb_canoniques > 1 ? "s" : ""}`}
        . Seules celles que le changement contredit seront retirées du service ; les autres ne
        bougeront pas.
      </p>
      <ul className="max-h-64 space-y-2 overflow-y-auto">
        {impact.a_analyser.map((r) => (
          <LigneARelire key={r.reponse_id} reponse={r} />
        ))}
      </ul>
      {reste > 0 && (
        <p className="text-[11px] text-amber-900/60 dark:text-amber-200/60">
          … et {reste} autre{reste > 1 ? "s" : ""}.
        </p>
      )}
    </section>
  );
}

/**
 * Les réponses qui citent un passage modifié. Elles passent en tête du budget
 * d'analyse — ce n'est pas une condamnation, et l'encadré doit le dire.
 */
function BlocPrioritaires({ impact }: { impact: UpdateImpact }) {
  const n = impact.nb_prioritaires;
  if (n === 0) return null;

  return (
    <section className="space-y-2 rounded-xl border border-gray-200 bg-gray-50/60 px-4 py-3.5 dark:border-white/10 dark:bg-white/[0.03]">
      <TitreSection icon={Flag}>
        {n} réponse{n > 1 ? "s" : ""} {n > 1 ? "citent" : "cite"} un passage modifié
      </TitreSection>
      <p className="text-xs leading-relaxed text-gray-500 dark:text-gray-400">
        {n > 1 ? "Elles seront examinées" : "Elle sera examinée"} en premier. Un passage modifié ne
        condamne rien à lui seul — une virgule corrigée suffit à le faire apparaître ici. Le retrait
        du service n'est prononcé que si le changement contredit réellement la réponse.
      </p>
      <ul className="space-y-1 pt-0.5">
        {impact.items.slice(0, 3).map((item) => (
          <li
            key={item.reponse_id}
            className="line-clamp-1 text-[11px] text-gray-500 dark:text-gray-400"
          >
            • {item.question}
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * Rien à signaler — deux cas qu'il ne faut surtout pas confondre.
 *
 * « Rien n'a changé » est une garantie ; « rien n'a pu être comparé » est un
 * avertissement. Afficher le vert dans le second cas promettrait ce qu'on ne
 * sait pas, alors que les réponses partiront quand même en relecture manuelle.
 */
function BlocSansChangement({ impact }: { impact: UpdateImpact }) {
  if (!impact.diff_analysable) {
    return (
      <section className="space-y-1.5 rounded-xl border border-amber-200 bg-amber-50/60 px-4 py-3.5 dark:border-amber-500/25 dark:bg-amber-500/[0.07]">
        <TitreSection icon={AlertTriangle} ton="ambre">
          La version en ligne n'a pas pu être relue.
        </TitreSection>
        <p className="text-xs leading-relaxed text-amber-900/80 dark:text-amber-200/80">
          Son fichier est introuvable sur le disque : aucune comparaison n'est possible et rien ne
          peut être jugé. Les réponses enregistrées du document seront déposées dans l'onglet À
          relire, à vérifier à la main.
        </p>
      </section>
    );
  }

  return (
    <section className="space-y-1.5 rounded-xl border border-emerald-200 bg-emerald-50/60 px-4 py-3.5 dark:border-emerald-500/25 dark:bg-emerald-500/[0.07]">
      <p className="flex items-center gap-2 text-sm font-semibold text-emerald-800 dark:text-emerald-300">
        <CheckCircle2 size={15} className="shrink-0" aria-hidden="true" />
        Cette version ne dit rien de nouveau.
      </p>
      <p className="text-xs leading-relaxed text-emerald-800/80 dark:text-emerald-200/80">
        Mise en forme, espaces, export : le fond est identique. Aucune réponse enregistrée ne sera
        examinée ni dérangée.
      </p>
    </section>
  );
}

export default function EtapeImpact({ impact }: { impact: UpdateImpact }) {
  const aDuNeuf = impact.diff_analysable && impact.nb_unites > 0;
  const enAttente = impact.nb_en_attente;

  return (
    <div className="space-y-4">
      {aDuNeuf ? (
        <>
          <BlocChangements impact={impact} />
          <BlocARelire impact={impact} />
          <BlocPrioritaires impact={impact} />
        </>
      ) : (
        <BlocSansChangement impact={impact} />
      )}

      {aDuNeuf && enAttente > 0 && (
        <p className="px-0.5 text-xs text-gray-500 dark:text-gray-400">
          {enAttente} réponse{enAttente > 1 ? "s" : ""} en attente de validation{" "}
          {enAttente > 1 ? "seront annulées et regénérées" : "sera annulée et regénérée"} sur la
          nouvelle version.
        </p>
      )}
    </div>
  );
}
