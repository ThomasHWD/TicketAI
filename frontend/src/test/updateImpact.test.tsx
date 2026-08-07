/**
 * L'écran d'impact d'une mise à jour, et son panneau « passages ajoutés ».
 *
 * Ce panneau existe parce que la détection d'obsolescence est *asymétrique* :
 * elle ne voit que les passages qui fondaient une réponse. Un article ajouté
 * ailleurs ne rend rien obsolète — et la réponse qui l'ignore continue d'être
 * servie. Les tests ci-dessous verrouillent le seul comportement qui compte :
 * le panneau s'affiche quand il y a un ajout, se tait sinon, et ne prétend
 * jamais que le document est inchangé quand il n'a rien pu vérifier.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { JobsProvider } from "../context/JobsContext";
import UpdateDocModal from "../pages/backoffice/UpdateDocModal";
import type { UpdateImpact } from "../types.ts";

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
    nb_a_relire: 0,
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

describe("Passages ajoutés", () => {
  it("signale un ajout alors qu'aucune réponse ne devient obsolète", () => {
    // Le cas qui justifie la fonctionnalité : l'encadré vert « rien n'est remis
    // en cause » est vrai, mais serait trompeur tout seul.
    afficher(
      impact({
        nb_passages_ajoutes: 1,
        extraits_ajoutes: ["Article 7 bis : le télétravail est suspendu en forte activité."],
        nb_a_relire: 4,
      }),
    );

    expect(screen.getByText(/1 passage ajouté par cette version/)).toBeInTheDocument();
    expect(screen.getByText(/Article 7 bis/)).toBeInTheDocument();
    expect(screen.getByText(/4 réponses enregistrées/)).toBeInTheDocument();
    expect(screen.getByText(/Aucune réponse enregistrée n'est remise en cause/)).toBeInTheDocument();
  });

  it("se tait quand la nouvelle version n'ajoute rien", () => {
    afficher(impact({ nb_chunks_modifies: 2 }));

    expect(screen.queryByText(/passage ajouté|passages ajoutés/)).toBeNull();
  });

  it("se tait aussi quand rien n'a pu être vérifié", () => {
    // Document backfillé : pas de fichier courant à comparer. Afficher « 0
    // passage ajouté » se lirait comme une garantie qu'on ne peut pas donner.
    afficher(impact({ ajouts_analysables: false, nb_passages_ajoutes: 0, nb_a_relire: 0 }));

    expect(screen.queryByText(/passage ajouté|passages ajoutés/)).toBeNull();
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

  it("indique combien d'ajouts ne sont pas affichés", () => {
    // Le backend n'en renvoie que trois : sans ce report, l'écran laisserait
    // croire que la relecture se limite à ce qui est visible.
    afficher(
      impact({
        nb_passages_ajoutes: 9,
        extraits_ajoutes: ["Premier.", "Deuxième.", "Troisième."],
        nb_a_relire: 1,
      }),
    );

    expect(screen.getByText(/et 6 autres/)).toBeInTheDocument();
  });

  it("affiche les deux constats quand la version périme ET ajoute", () => {
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
    expect(screen.getByText(/2 passages ajoutés par cette version/)).toBeInTheDocument();
  });
});
