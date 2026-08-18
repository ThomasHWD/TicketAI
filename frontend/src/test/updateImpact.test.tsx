/**
 * L'écran d'impact d'une mise à jour.
 *
 * Cet écran a un rôle précis et étroit : montrer ce que la nouvelle version
 * change, et **rien d'autre**. L'aperçu n'appelle ni reranker ni LLM — il ne
 * peut donc pas dire quelles réponses seront retirées du service, et il ne doit
 * jamais laisser croire qu'il le sait. Les tests ci-dessous verrouillent cette
 * frontière : le diff est affiché apparié, les réponses sont annoncées comme
 * « à relire » et non comme condamnées, et un document qu'on n'a pas pu comparer
 * ne passe pas pour un document inchangé.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { JobsProvider } from "../context/JobsContext";
import UpdateDocModal from "../pages/backoffice/UpdateDocModal";
import type { ReponseARelire, UniteChangement, UpdateImpact } from "../types";

function impact(overrides: Partial<UpdateImpact> = {}): UpdateImpact {
  return {
    staging_id: "s1",
    filename: "charte.md",
    version_cible: 3,
    restauree_depuis: null,
    nb_chunks_modifies: 0,
    nb_total_chunks: 12,
    nb_prioritaires: 0,
    items: [],
    diff_analysable: true,
    nb_unites: 0,
    unites: [],
    nb_ajoutes: 0,
    extraits_ajoutes: [],
    nb_retires: 0,
    extraits_retires: [],
    nb_a_analyser: 0,
    nb_canoniques: 0,
    a_analyser: [],
    nb_en_attente: 0,
    ...overrides,
  };
}

function unite(overrides: Partial<UniteChangement> = {}): UniteChangement {
  return {
    sens: "AJOUT",
    extrait_avant: "",
    extrait_apres: "Article 7 bis : le télétravail est suspendu en forte activité.",
    ...overrides,
  };
}

function aAnalyser(overrides: Partial<ReponseARelire> = {}): ReponseARelire {
  return {
    reponse_id: "r1",
    ticket_id: "t1",
    question: "Combien de jours de télétravail ?",
    contenu: "Deux jours par semaine.",
    canonique: true,
    nb_validations: 5,
    ...overrides,
  };
}

function afficher(i: UpdateImpact) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <JobsProvider>
        <UpdateDocModal
          doc={{ doc_id: "d1", filename: "charte.md", version: 2 }}
          impactInitial={i}
          onClose={vi.fn()}
        />
      </JobsProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => localStorage.clear());

describe("Unités de changement", () => {
  it("montre une réécriture appariée, avant et après", () => {
    // C'est le couple qui rend le changement jugeable — « 2 jours » seul ne dit
    // rien, « 2 jours → 3 jours » dit tout. C'est aussi sous cette forme exacte
    // que l'unité sera soumise au verdict côté worker.
    afficher(
      impact({
        nb_unites: 1,
        unites: [
          unite({
            sens: "REECRITURE",
            extrait_avant: "Le télétravail est limité à 2 jours par semaine.",
            extrait_apres: "Le télétravail est limité à 3 jours par semaine.",
          }),
        ],
        nb_a_analyser: 4,
      }),
    );

    expect(screen.getByText(/1 changement dans le document/)).toBeInTheDocument();
    expect(screen.getByText("Réécrit")).toBeInTheDocument();
    expect(screen.getByText(/limité à 2 jours/)).toBeInTheDocument();
    expect(screen.getByText(/limité à 3 jours/)).toBeInTheDocument();
  });

  it("montre un retrait, que le seul compte d'ajouts ne verrait pas", () => {
    // Une règle abrogée sans rien écrire à la place : aucun ajout ne la trahit.
    afficher(
      impact({
        nb_unites: 1,
        unites: [
          unite({
            sens: "RETRAIT",
            extrait_avant: "Article 9 : une prime de 20 € compense les frais d'électricité.",
            extrait_apres: "",
          }),
        ],
        nb_a_analyser: 2,
      }),
    );

    expect(screen.getByText("Retiré")).toBeInTheDocument();
    expect(screen.getByText(/Article 9/)).toBeInTheDocument();
    expect(screen.queryByText("Ajouté")).toBeNull();
  });

  it("indique combien d'unités ne sont pas affichées", () => {
    // Le backend n'en renvoie que trois : sans ce report, l'écran laisserait
    // croire que le document n'a bougé qu'à trois endroits.
    afficher(
      impact({
        nb_unites: 9,
        unites: [unite(), unite({ extrait_apres: "Deuxième." }), unite({ extrait_apres: "Troisième." })],
        nb_a_analyser: 1,
        a_analyser: [aAnalyser()],
      }),
    );

    expect(screen.getByText(/9 changements dans le document/)).toBeInTheDocument();
    expect(screen.getByText(/et 6 autres/)).toBeInTheDocument();
  });
});

describe("Ce qui sera analysé", () => {
  it("annonce une relecture, pas une condamnation", () => {
    // La nuance est tout le projet : la confirmation ne détruit rien, elle
    // enfile des jugements. Promettre des obsolescences ici serait faux — la
    // plupart des réponses survivront.
    afficher(
      impact({
        nb_unites: 1,
        unites: [unite()],
        nb_a_analyser: 4,
        nb_canoniques: 2,
        a_analyser: [aAnalyser()],
      }),
    );

    expect(screen.getByText(/4 réponses enregistrées seront relues/)).toBeInTheDocument();
    expect(screen.getByText(/dont 2 canoniques/)).toBeInTheDocument();
    expect(screen.getByText(/Seules celles que le changement contredit/)).toBeInTheDocument();
    expect(screen.queryByText(/obsolète/i)).toBeNull();
  });

  it("compte les réponses à relire sous le bouton de confirmation", () => {
    afficher(impact({ nb_unites: 1, unites: [unite()], nb_a_analyser: 4, a_analyser: [aAnalyser()] }));

    expect(screen.getByText("4 réponses seront relues")).toBeInTheDocument();
  });

  it("le dit quand aucune réponse ne s'appuie sur le document", () => {
    afficher(impact({ nb_unites: 2, unites: [unite()], nb_a_analyser: 0 }));

    expect(screen.getByText(/Aucune réponse enregistrée ne s'appuie sur ce document/)).toBeInTheDocument();
  });

  it("ouvre chaque réponse sans quitter la mise à jour", () => {
    // Une navigation classique perdrait l'aperçu : il faudrait re-déposer le
    // fichier, donc on renoncerait à regarder.
    afficher(
      impact({
        nb_unites: 1,
        unites: [unite()],
        nb_a_analyser: 1,
        a_analyser: [aAnalyser({ ticket_id: "t-42", question: "Puis-je télétravailler 3 jours ?" })],
      }),
    );

    const lien = screen.getByRole("link", { name: /Puis-je télétravailler 3 jours/ });

    expect(lien).toHaveAttribute("href", "/tickets/t-42");
    expect(lien).toHaveAttribute("target", "_blank");
  });

  it("annonce le reste au-delà des dix premières", () => {
    // La modale amorce la liste, elle ne la porte pas : le surplus doit être
    // annoncé, pas escamoté, sinon la charge réelle paraît plus faible.
    afficher(
      impact({
        nb_unites: 1,
        unites: [unite()],
        nb_a_analyser: 14,
        a_analyser: Array.from({ length: 10 }, (_, i) =>
          aAnalyser({ reponse_id: `r${i}`, ticket_id: `t${i}` }),
        ),
      }),
    );

    expect(screen.getAllByRole("link")).toHaveLength(10);
    expect(screen.getByText(/et 4 autres/)).toBeInTheDocument();
  });

  it("prévient que les réponses en attente seront regénérées", () => {
    afficher(impact({ nb_unites: 1, unites: [unite()], nb_a_analyser: 1, nb_en_attente: 3 }));

    expect(screen.getByText(/3 réponses en attente de validation/)).toBeInTheDocument();
  });
});

describe("Passages cités", () => {
  it("annonce une priorité d'examen, jamais une obsolescence", () => {
    // Le correctif du défaut historique : un chunk cité qui a bougé ne condamne
    // plus rien. Une virgule corrigée suffit à faire apparaître une réponse ici.
    afficher(
      impact({
        nb_unites: 1,
        unites: [unite()],
        nb_prioritaires: 2,
        items: [
          {
            reponse_id: "r1",
            question: "Combien de jours de télétravail ?",
            canonique: true,
            nb_validations: 3,
            chunks_modifies: [0],
            extraits: ["limité à 2 jours par semaine"],
          },
        ],
        nb_a_analyser: 5,
      }),
    );

    expect(screen.getByText(/2 réponses citent un passage modifié/)).toBeInTheDocument();
    expect(screen.getByText(/ne condamne rien à lui seul/)).toBeInTheDocument();
    expect(screen.queryByText(/va devenir obsolète/)).toBeNull();
  });

  it("se tait quand aucun passage cité n'a bougé", () => {
    afficher(impact({ nb_unites: 1, unites: [unite()], nb_prioritaires: 0, nb_a_analyser: 3 }));

    expect(screen.queryByText(/cite un passage modifié|citent un passage modifié/)).toBeNull();
  });
});

describe("Rien à signaler", () => {
  it("se tait sur un pur reformatage", () => {
    // La propriété anti-inondation : zéro unité ⇒ aucun job d'analyse n'est même
    // enfilé. Un écran qui alarme à chaque mise à jour cesse d'être lu.
    afficher(impact({ nb_chunks_modifies: 2, nb_unites: 0, nb_a_analyser: 0 }));

    expect(screen.getByText(/Cette version ne dit rien de nouveau/)).toBeInTheDocument();
    expect(screen.queryByText(/changement dans le document|changements dans le document/)).toBeNull();
  });

  it("distingue « rien n'a changé » de « rien n'a pu être comparé »", () => {
    // Document backfillé : le fichier de la version en ligne est introuvable.
    // Afficher l'encadré vert se lirait comme une garantie qu'on ne peut pas
    // donner — et ici, contrairement au reformatage, les réponses partiront
    // quand même en relecture manuelle.
    afficher(impact({ diff_analysable: false, nb_unites: 0, nb_a_analyser: 0 }));

    expect(screen.getByText(/La version en ligne n'a pas pu être relue/)).toBeInTheDocument();
    expect(screen.getByText(/déposées dans l'onglet À relire/)).toBeInTheDocument();
    expect(screen.queryByText(/Cette version ne dit rien de nouveau/)).toBeNull();
  });
});
