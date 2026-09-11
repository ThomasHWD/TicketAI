/**
 * La page FAQ.
 *
 * Ce qui est verrouillé ici n'est pas le rendu mais le **coût** : une recherche
 * consomme un embedding Albert, dont le quota est de 1 000 requêtes/jour/modèle.
 * Une recherche à la frappe l'épuiserait en une poignée de sessions. La saisie et
 * la requête soumise sont donc deux états distincts (`hooks/useFaq.ts`), et c'est
 * cette séparation que les tests ci-dessous tiennent.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Faq from "../pages/user/Faq";

const rechercherFaq = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", () => ({ rechercherFaq }));

/** Un résultat dont le contenu identifie la question qui l'a produit. */
function reponse(question: string) {
  return {
    reponse_id: question,
    question: `question indexée pour ${question}`,
    contenu: `contenu de ${question}`,
    domaine: "IT",
    tag: null,
    nb_validations: 3,
    validated_at: null,
  };
}

function afficher() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Faq />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  rechercherFaq.mockReset();
  rechercherFaq.mockResolvedValue({ question: "q", resultats: [], incertains: [] });
});

describe("page FAQ", () => {
  // Propriété de coût : chaque recherche consomme un embedding Albert, dont le
  // quota est de 1 000 requêtes/jour. Une recherche à la frappe l'épuiserait.
  it("ne cherche pas pendant la frappe, seulement à la soumission", async () => {
    const user = userEvent.setup();
    afficher();

    await user.type(screen.getByLabelText(/votre question/i), "congés reportables");
    expect(rechercherFaq).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /rechercher/i }));
    expect(rechercherFaq).toHaveBeenCalledTimes(1);
    expect(rechercherFaq).toHaveBeenCalledWith("congés reportables");
  });

  // `setSaisie` puis `soumettre()` lirait l'état du rendu précédent : la recherche
  // ne partirait pas, sans la moindre erreur visible. D'où `soumettre(valeur)`.
  it("lance la recherche dès le clic sur une question d'exemple", async () => {
    const user = userEvent.setup();
    afficher();

    // N'importe quelle amorce : tout bouton qui n'est pas celui de recherche.
    const exemple = screen
      .getAllByRole("button")
      .find((b) => b.getAttribute("aria-label") !== "Rechercher")!;
    await user.click(exemple);

    expect(rechercherFaq).toHaveBeenCalledTimes(1);
    expect(rechercherFaq).toHaveBeenCalledWith(exemple.textContent);
  });

  // Le cœur du parti pris : une question à la fois. Si un résultat survivait à
  // la question suivante, la page redeviendrait un transcript — et laisserait
  // croire à un contexte conservé, que le serveur n'a jamais.
  it("remplace entièrement le résultat précédent à la question suivante", async () => {
    const user = userEvent.setup();
    rechercherFaq.mockImplementation((q: string) =>
      Promise.resolve({ question: q, resultats: [reponse(q)], incertains: [] }),
    );
    afficher();

    // Le champ est re-interrogé à chaque fois : passer de l'accueil au résultat
    // remonte un nouveau composeur, l'ancien nœud est détaché.
    await user.type(screen.getByLabelText(/votre question/i), "congés{Enter}");
    expect(await screen.findByText("contenu de congés")).toBeInTheDocument();

    await user.clear(screen.getByLabelText(/votre question/i));
    await user.type(screen.getByLabelText(/votre question/i), "télétravail{Enter}");

    expect(await screen.findByText("contenu de télétravail")).toBeInTheDocument();
    expect(screen.queryByText("contenu de congés")).not.toBeInTheDocument();
    expect(rechercherFaq).toHaveBeenCalledTimes(2);
  });

  // La question reste dans le champ : c'est ce qui fait lire la page comme une
  // barre de recherche, et non comme une conversation qu'on poursuit.
  it("conserve la question dans le champ après recherche", async () => {
    const user = userEvent.setup();
    afficher();

    await user.type(screen.getByLabelText(/votre question/i), "congés reportables{Enter}");

    expect(screen.getByLabelText(/votre question/i)).toHaveValue("congés reportables");
  });

  it("désactive la recherche tant que la question est trop courte", async () => {
    const user = userEvent.setup();
    afficher();

    await user.type(screen.getByLabelText(/votre question/i), "ab");
    expect(screen.getByRole("button", { name: /rechercher/i })).toBeDisabled();
  });
});
