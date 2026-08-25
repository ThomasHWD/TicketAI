/**
 * L'onglet « À relire » de *Réponses enregistrées*.
 *
 * L'écran répond à un problème de volume, pas de rendu : une phrase réécrite
 * dans une charte qui porte 40 réponses en signale 39. Ce qui est verrouillé ici,
 * c'est donc l'ergonomie qui rend l'onglet vidable — le diff lu **une fois** par
 * document, la confirmation en lot, et un badge qui compte les documents et non
 * les réponses. Une liste plate ferait relire le même diff trente-neuf fois, et
 * l'onglet ne redescendrait jamais à zéro.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TOKEN_KEY } from "../lib/api";
import SavedAnswers from "../pages/backoffice/SavedAnswers";
import type { ReponseCanonique, ReponseSignalee } from "../types";

function signalee(overrides: Partial<ReponseSignalee> = {}): ReponseSignalee {
  return {
    reponse_id: "r1",
    ticket_id: "t1",
    question: "Combien de jours de télétravail ?",
    canonique: true,
    nb_validations: 5,
    domaine: "RH",
    contenu: "Deux jours par semaine.",
    contenu_corrige: null,
    a_relire_raison: "DOC_MODIFIÉ",
    a_relire_version: 3,
    a_relire_at: "2026-08-01T10:00:00Z",
    analyse_justification: null,
    analyse_extraits: [],
    doc_id: "doc-rh",
    document_filename: "Charte_RH.md",
    document_supprime: false,
    changements: {
      nb_ajoutes: 1,
      nb_retires: 0,
      extraits_ajoutes: ["Article 7 bis : le télétravail est suspendu en forte activité."],
      extraits_retires: [],
    },
    ...overrides,
  };
}

function canonique(overrides: Partial<ReponseCanonique> = {}): ReponseCanonique {
  return {
    reponse_id: "c1",
    ticket_id: "t1",
    question: "Combien de jours de télétravail ?",
    domaine: "RH",
    contenu: "Deux jours par semaine.",
    contenu_corrige: null,
    nb_validations: 3,
    occurence: 7,
    a_relire: false,
    validated_at: "2026-07-01T10:00:00Z",
    created_at: "2026-07-01T10:00:00Z",
    ...overrides,
  };
}

/**
 * Un `fetch` routé par URL : la page tire quatre requêtes concurrentes (liste et
 * compteur, pour chaque onglet). Un stub qui renverrait le même corps à toutes
 * ferait passer les tests pour de mauvaises raisons.
 */
function router(reponses: {
  canoniques?: ReponseCanonique[];
  aRelire?: ReponseSignalee[];
  nbDocuments?: number;
}) {
  const envoyees: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      envoyees.push({ url, init });
      const items =
        url.includes("/a-relire") ? (reponses.aRelire ?? [])
        : url.includes("/canoniques") ? (reponses.canoniques ?? [])
        : [];
      const corps = {
        total: items.length,
        nb_documents: reponses.nbDocuments ?? 0,
        page: 1,
        limit: 10,
        items,
      };
      return new Response(JSON.stringify(corps), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  return envoyees;
}

function afficher() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <SavedAnswers />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => localStorage.setItem(TOKEN_KEY, "tok-test"));
afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("Onglet À relire", () => {
  it("compte les documents et non les réponses", async () => {
    // « 39 réponses » se subit, « 2 documents » se traite : c'est deux diffs à
    // lire, pas trente-neuf. Le badge doit annoncer le travail, pas le volume.
    router({
      aRelire: [signalee(), signalee({ reponse_id: "r2" }), signalee({ reponse_id: "r3" })],
      nbDocuments: 2,
    });
    afficher();

    const onglet = await screen.findByRole("tab", { name: /À relire/ });

    await waitFor(() => expect(onglet).toHaveTextContent("2"));
    expect(onglet).not.toHaveTextContent("3");
  });

  it("n'affiche le diff qu'une fois pour toutes les réponses d'un document", async () => {
    router({
      aRelire: [
        signalee({ reponse_id: "r1", question: "Combien de jours ?" }),
        signalee({ reponse_id: "r2", question: "Puis-je télétravailler le vendredi ?" }),
      ],
      nbDocuments: 1,
    });
    afficher();
    await userEvent.click(await screen.findByRole("tab", { name: /À relire/ }));

    expect(await screen.findByText(/Combien de jours \?/)).toBeInTheDocument();
    expect(screen.getByText(/Puis-je télétravailler le vendredi \?/)).toBeInTheDocument();
    // Un seul en-tête, un seul extrait, un seul bouton de lot pour les deux.
    expect(screen.getAllByText(/Article 7 bis/)).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: /Tout confirmer/ })).toHaveLength(1);
  });

  it("sépare deux documents en deux groupes", async () => {
    router({
      aRelire: [
        signalee({ reponse_id: "r1" }),
        signalee({
          reponse_id: "r2",
          doc_id: "doc-it",
          document_filename: "Politique_IT.md",
          a_relire_version: 2,
          changements: {
            nb_ajoutes: 0,
            nb_retires: 1,
            extraits_ajoutes: [],
            extraits_retires: ["Article 9 : la prime matériel est de 20 €."],
          },
        }),
      ],
      nbDocuments: 2,
    });
    afficher();
    await userEvent.click(await screen.findByRole("tab", { name: /À relire/ }));

    expect(await screen.findByText(/Charte_RH\.md/)).toBeInTheDocument();
    expect(screen.getByText(/Politique_IT\.md/)).toBeInTheDocument();
    // Chaque groupe se confirme séparément : les deux diffs ne se jugent pas ensemble.
    expect(screen.getAllByRole("button", { name: /Tout confirmer/ })).toHaveLength(2);
    // Le second sens du changement est bien affiché, pas seulement les ajouts.
    expect(screen.getByText(/1 passage retiré/)).toBeInTheDocument();
  });

  it("confirme un lot en citant le document ET sa version", async () => {
    // La version fait partie de la clé : un document remis à jour entre-temps a
    // reflagué ses réponses sur v(n+1), et une confirmation partie de l'écran de
    // v(n) ne doit pas balayer un signalement que personne n'a vu.
    // Note : la confirmation est en deux temps — "Tout confirmer" ouvre la demande,
    // "Confirmer" la valide. Le test doit reproduire les deux clics.
    const envoyees = router({ aRelire: [signalee()], nbDocuments: 1 });
    afficher();
    await userEvent.click(await screen.findByRole("tab", { name: /À relire/ }));
    await userEvent.click(await screen.findByRole("button", { name: /Tout confirmer/ }));
    await userEvent.click(await screen.findByRole("button", { name: /^Confirmer$/ }));

    await waitFor(() => {
      const post = envoyees.find((a) => a.init?.method === "POST");
      expect(post?.url).toContain("/reponses/confirmer-actualite");
      expect(JSON.parse(String(post?.init?.body))).toEqual({ doc_id: "doc-rh", version: 3 });
    });
  });

  it("dit pourquoi il est bruyant quand la version sortante était illisible", async () => {
    // Sans ça, un onglet plein sans un seul extrait passerait pour un bug.
    router({
      aRelire: [signalee({ a_relire_raison: "VERSION_SORTANTE_ILLISIBLE", changements: null })],
      nbDocuments: 1,
    });
    afficher();
    await userEvent.click(await screen.findByRole("tab", { name: /À relire/ }));

    expect(await screen.findByText(/n'a pas pu être relue/)).toBeInTheDocument();
  });

  it("dit aussi pourquoi il est bruyant sur une réécriture massive", async () => {
    // Quand tout a changé, il n'y a rien à discriminer : aucune réponse n'est
    // jugée et le groupe entier arrive sans extrait. Même risque de passer pour
    // un bug que la version illisible, donc même explication.
    router({
      aRelire: [signalee({ a_relire_raison: "REECRITURE_MASSIVE", changements: null })],
      nbDocuments: 1,
    });
    afficher();
    await userEvent.click(await screen.findByRole("tab", { name: /À relire/ }));

    expect(await screen.findByText(/réécrit en profondeur/)).toBeInTheDocument();
  });
});

describe("Motif propre à chaque réponse", () => {
  it("préfère la justification du verdict au motif générique du groupe", async () => {
    // Le diff se lit une fois par document ; la justification, elle, est propre
    // à la réponse. C'est la différence entre « ce document a bougé » et « voici
    // ce qui contredit cette réponse-là » — et c'est ce qui évite de redemander
    // à l'humain le travail que l'analyse vient de faire.
    router({
      aRelire: [
        signalee({
          a_relire_raison: "CONTREDITE_PROBABLE",
          analyse_justification: "La durée passe de 2 à 3 jours par semaine.",
        }),
      ],
      nbDocuments: 1,
    });
    afficher();
    await userEvent.click(await screen.findByRole("tab", { name: /À relire/ }));

    expect(await screen.findByText(/La durée passe de 2 à 3 jours/)).toBeInTheDocument();
    expect(screen.queryByText(/à confirmer avant tout retrait/)).toBeNull();
  });

  it("retombe sur le motif générique quand le modèle n'a rien dit", async () => {
    router({
      aRelire: [signalee({ a_relire_raison: "ANALYSE_INDISPONIBLE", analyse_justification: null })],
      nbDocuments: 1,
    });
    afficher();
    await userEvent.click(await screen.findByRole("tab", { name: /À relire/ }));

    expect(await screen.findByText(/n'a pas pu se prononcer/)).toBeInTheDocument();
  });

  it("ne propose aucune action tant que l'analyse tourne", async () => {
    // `ANALYSE_EN_COURS` est transitoire : trancher maintenant ferait juger
    // l'humain avant la machine, et sa décision serait écrasée deux minutes plus
    // tard par le verdict.
    router({
      aRelire: [signalee({ a_relire_raison: "ANALYSE_EN_COURS" })],
      nbDocuments: 1,
    });
    afficher();
    await userEvent.click(await screen.findByRole("tab", { name: /À relire/ }));

    expect(await screen.findByText(/résultat dans quelques minutes/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Confirmer|Retirer|Corriger/ })).toBeNull();
  });
});

describe("Pastille sur les canoniques", () => {
  it("signale une canonique encore servie dont le document a changé", async () => {
    // Elle est toujours servie, donc toujours dans cet onglet : sans la pastille,
    // l'écran la présenterait comme acquise.
    router({ canoniques: [canonique({ a_relire: true })] });
    afficher();

    expect(await screen.findByRole("button", { name: /À relire/ })).toBeInTheDocument();
  });

  it("ne signale rien quand le document n'a pas bougé", async () => {
    router({ canoniques: [canonique()] });
    afficher();

    await screen.findByText(/Combien de jours de télétravail/);
    expect(screen.queryByRole("button", { name: /À relire/ })).toBeNull();
  });
});
