/**
 * L'écran d'impact d'une mise à jour, et son panneau « ce que la version change ».
 *
 * Ce panneau existe parce que la détection d'obsolescence est *asymétrique* :
 * elle ne voit que les passages qui fondaient une réponse. Un article ajouté
 * ailleurs — ou une règle abrogée ailleurs — ne rend rien obsolète, et la
 * réponse qui l'ignore continue d'être servie. Les tests ci-dessous verrouillent
 * le seul comportement qui compte : le panneau s'affiche dès qu'un des deux sens
 * a tiré, se tait sinon, et ne prétend jamais que le document est inchangé quand
 * il n'a rien pu vérifier.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { JobsProvider } from "../context/JobsContext";
import UpdateDocModal from "../pages/backoffice/UpdateDocModal";
import type { ReponseARelire, UpdateImpact } from "../types.ts";

function impact(overrides: Partial<UpdateImpact> = {}): UpdateImpact {
  return {
    staging_id: "s1",
    filename: "charte.md",
    version_cible: 3,
    restauree_depuis: null,
    nb_chunks_modifies: 0,
    nb_total_chunks: 12,
    nb_obsoletes: 0,
    nb_canoniques: 0,
    items: [],
    ajouts_analysables: true,
    nb_passages_ajoutes: 0,
    extraits_ajoutes: [],
    nb_passages_retires: 0,
    extraits_retires: [],
    nb_a_relire: 0,
    a_relire: [],
    ...overrides,
  };
}

function aRelire(overrides: Partial<ReponseARelire> = {}): ReponseARelire {
  return {
    reponse_id: "r1",
    ticket_id: "t1",
    question: "Combien de jours de télétravail ?",
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

describe("Changements de contenu", () => {
  it("signale un ajout alors qu'aucune réponse ne devient obsolète", () => {
    // Le cas qui justifie la fonctionnalité : l'encadré vert « rien n'est remis
    // en cause » est vrai, mais serait trompeur tout seul.
    afficher(
      impact({
        nb_passages_ajoutes: 1,
        extraits_ajoutes: ["Article 7 bis : le télétravail est suspendu en forte activité."],
        nb_a_relire: 4,
        a_relire: [aRelire()],
      }),
    );

    expect(screen.getByText(/Cette version change le contenu/)).toBeInTheDocument();
    expect(screen.getByText(/1 passage ajouté/)).toBeInTheDocument();
    expect(screen.getByText(/Article 7 bis/)).toBeInTheDocument();
    expect(screen.getByText(/4 réponses enregistrées/)).toBeInTheDocument();
    expect(screen.getByText(/Aucune réponse enregistrée n'est remise en cause/)).toBeInTheDocument();
  });

  it("signale une règle abrogée, que le compte d'ajouts ne voit pas", () => {
    // Le seul cas qu'aucun ajout ne trahit : on retire un article sans rien
    // écrire à la place. Sans ce second sens, l'écran serait muet.
    afficher(
      impact({
        nb_passages_retires: 1,
        extraits_retires: ["Article 9 : une prime de 20 € compense les frais d'électricité."],
        nb_a_relire: 2,
      }),
    );

    expect(screen.getByText(/Cette version change le contenu/)).toBeInTheDocument();
    expect(screen.getByText(/1 passage retiré/)).toBeInTheDocument();
    expect(screen.getByText(/Article 9/)).toBeInTheDocument();
    expect(screen.queryByText(/passage ajouté|passages ajoutés/)).toBeNull();
  });

  it("affiche les deux sens quand la version ajoute et retire", () => {
    afficher(
      impact({
        nb_passages_ajoutes: 2,
        extraits_ajoutes: ["Article 7 bis.", "Article 7 ter."],
        nb_passages_retires: 1,
        extraits_retires: ["Article 9."],
        nb_a_relire: 3,
      }),
    );

    expect(screen.getByText(/2 passages ajoutés/)).toBeInTheDocument();
    expect(screen.getByText(/1 passage retiré/)).toBeInTheDocument();
  });

  it("ouvre chaque réponse à relire sans quitter la mise à jour", () => {
    // Un compte seul n'est pas actionnable, et une navigation classique perdrait
    // l'aperçu : il faudrait re-déposer le fichier, donc on ignorerait l'alerte.
    afficher(
      impact({
        nb_passages_ajoutes: 1,
        extraits_ajoutes: ["Article 7 bis."],
        nb_a_relire: 1,
        a_relire: [aRelire({ ticket_id: "t-42", question: "Puis-je télétravailler 3 jours ?" })],
      }),
    );

    const lien = screen.getByRole("link", { name: /Puis-je télétravailler 3 jours/ });

    expect(lien).toHaveAttribute("href", "/tickets/t-42");
    expect(lien).toHaveAttribute("target", "_blank");
  });

  it("renvoie vers Réponses enregistrées au-delà des dix premières", () => {
    // La modale amorce le tri, elle ne le porte pas : le reste doit être annoncé,
    // pas escamoté, sinon la charge réelle paraît plus faible qu'elle n'est.
    afficher(
      impact({
        nb_passages_ajoutes: 1,
        extraits_ajoutes: ["Article 7 bis."],
        nb_a_relire: 14,
        a_relire: Array.from({ length: 10 }, (_, i) =>
          aRelire({ reponse_id: `r${i}`, ticket_id: `t${i}` }),
        ),
      }),
    );

    expect(screen.getAllByRole("link")).toHaveLength(10);
    expect(screen.getByText(/et 4 autres/)).toBeInTheDocument();
  });

  it("se tait sur un pur reformatage, qui ne tire dans aucun sens", () => {
    // La propriété anti-inondation : un panneau qui s'affiche à chaque mise à
    // jour cesse d'être lu.
    afficher(impact({ nb_chunks_modifies: 2 }));

    expect(screen.queryByText(/Cette version change le contenu/)).toBeNull();
  });

  it("se tait aussi quand rien n'a pu être vérifié", () => {
    // Document backfillé : pas de fichier courant à comparer. Afficher « 0
    // passage ajouté » se lirait comme une garantie qu'on ne peut pas donner.
    afficher(impact({ ajouts_analysables: false, nb_passages_ajoutes: 0, nb_a_relire: 0 }));

    expect(screen.queryByText(/Cette version change le contenu/)).toBeNull();
  });

  it("n'annonce rien à relire quand aucune réponse ne survit", () => {
    afficher(
      impact({
        nb_obsoletes: 2,
        nb_canoniques: 1,
        nb_passages_ajoutes: 1,
        extraits_ajoutes: ["Un nouvel alinéa."],
        nb_a_relire: 0,
      }),
    );

    expect(screen.getByText(/Aucune réponse enregistrée ne subsiste/)).toBeInTheDocument();
  });

  it("indique combien d'extraits ne sont pas affichés, par sens", () => {
    // Le backend n'en renvoie que trois par sens : sans ce report, l'écran
    // laisserait croire que la relecture se limite à ce qui est visible.
    afficher(
      impact({
        nb_passages_ajoutes: 9,
        extraits_ajoutes: ["Premier.", "Deuxième.", "Troisième."],
        nb_passages_retires: 5,
        extraits_retires: ["Quatrième.", "Cinquième.", "Sixième."],
        nb_a_relire: 1,
      }),
    );

    expect(screen.getByText(/et 6 autres/)).toBeInTheDocument();
    expect(screen.getByText(/et 2 autres/)).toBeInTheDocument();
  });

  it("affiche les deux constats quand la version périme ET change le contenu", () => {
    afficher(
      impact({
        nb_obsoletes: 1,
        nb_canoniques: 1,
        nb_chunks_modifies: 1,
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
        nb_passages_ajoutes: 2,
        extraits_ajoutes: ["Article 7 bis.", "Article 9."],
        nb_a_relire: 3,
      }),
    );

    expect(screen.getByText(/va devenir obsolète/)).toBeInTheDocument();
    expect(screen.getByText(/2 passages ajoutés/)).toBeInTheDocument();
  });
});
