/** KnowledgeBase fusion contract: ingestion accessible without leaving the list; write actions hidden when the server would refuse them (403/409) — offering a doomed action is worse than hiding it. */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { JobsProvider } from "../context/JobsContext";
import { AuthProvider } from "../lib/auth";
import { TOKEN_KEY, USER_KEY } from "../lib/api";
import KnowledgeBase from "../pages/backoffice/KnowledgeBase";
import type { IndexedDocument } from "../types";

// ── Helpers ───────────────────────────────────────────────────────────────────

function doc(overrides: Partial<IndexedDocument> = {}): IndexedDocument {
  return {
    doc_id: "d1",
    filename: "charte-teletravail.md",
    domaine: "RH",
    stored_path: "/data/d1",
    description: "Règles de télétravail 2026",
    nb_chunks: 12,
    version: 2,
    statut: "ACTIF",
    nb_versions: 2,
    updated_at: "2026-02-10T09:00:00Z",
    ...overrides,
  };
}

/** Connecte un membre du groupe RH — ni admin, ni membre de l'IT. */
function connecterRH() {
  localStorage.setItem(TOKEN_KEY, "tok-test");
  localStorage.setItem(
    USER_KEY,
    JSON.stringify({
      id: "u1",
      email: "alice@example.com",
      prenom: "Alice",
      nom: "Martin",
      role: "AGENT",
      groupes: [{ id: "g1", nom: "RH", domaine: "RH", is_chef: false }],
    }),
  );
}

function afficher(items: IndexedDocument[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ total: items.length, items }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );

  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <AuthProvider>
          <JobsProvider>
            <KnowledgeBase />
          </JobsProvider>
        </AuthProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

/** Ouvre le menu kebab de la ligne d'un document et rend ses entrées. */
async function ouvrirMenu(nomFichier: string) {
  const declencheur = await screen.findByRole("button", { name: new RegExp(`Actions sur ${nomFichier}`) });
  await userEvent.click(declencheur);
  return within(screen.getByRole("menu")).getAllByRole("menuitem");
}

beforeEach(connecterRH);

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("Base de connaissances", () => {
  it("ouvre l'ingestion sans quitter la liste", async () => {
    // Tout l'objet de la fusion : ajouter un document ne doit plus coûter une
    // navigation. Le tableau reste monté derrière le panneau.
    afficher([doc()]);
    await screen.findByText("charte-teletravail.md");

    await userEvent.click(screen.getByRole("button", { name: /Ajouter un document/ }));

    expect(screen.getByRole("dialog", { name: /Ajouter un document/ })).toBeInTheDocument();
    expect(screen.getByText("charte-teletravail.md")).toBeInTheDocument();
  });

  it("filtre sur le nom comme sur la description", async () => {
    // La description est le seul indice lisible quand les noms de fichiers sont
    // opaques ; la chercher n'est pas un bonus, c'est ce qui rend la liste
    // navigable.
    afficher([
      doc(),
      doc({ doc_id: "d2", filename: "note-2026.pdf", description: "Barème des frais kilométriques" }),
    ]);
    await screen.findByText("note-2026.pdf");

    await userEvent.type(screen.getByRole("searchbox", { name: /Rechercher/ }), "kilométriques");

    expect(screen.getByText("note-2026.pdf")).toBeInTheDocument();
    expect(screen.queryByText("charte-teletravail.md")).toBeNull();
  });

  it("ferme la mise à jour et la suppression hors de son domaine", async () => {
    // Miroir de `check_domain_write` : proposer ces actions sur un document IT
    // à un membre RH ne mènerait qu'à un 403, après confirmation.
    afficher([doc({ domaine: "IT", filename: "vpn.md" })]);

    const entrees = await ouvrirMenu("vpn.md");
    const parLibelle = (motif: RegExp) => entrees.find((e) => motif.test(e.textContent ?? ""))!;

    expect(parLibelle(/Voir le contenu indexé/)).toBeEnabled();
    expect(parLibelle(/Télécharger/)).toBeEnabled();
    expect(parLibelle(/Mettre à jour/)).toBeDisabled();
    expect(parLibelle(/Supprimer/)).toBeDisabled();
  });

  it("verrouille les écritures pendant une mise à jour en cours", async () => {
    // `EN_MAJ` signale un job encore en vol : une seconde mise à jour partirait
    // en 409, et une suppression laisserait un staging orphelin.
    afficher([doc({ statut: "EN_MAJ" })]);

    const entrees = await ouvrirMenu("charte-teletravail.md");
    const parLibelle = (motif: RegExp) => entrees.find((e) => motif.test(e.textContent ?? ""))!;

    expect(screen.getByText(/Mise à jour…/)).toBeInTheDocument();
    expect(parLibelle(/Mettre à jour/)).toBeDisabled();
    expect(parLibelle(/Supprimer/)).toBeDisabled();
    // La lecture, elle, reste ouverte : c'est le moment où l'on veut vérifier
    // ce qui est encore servi.
    expect(parLibelle(/Historique/)).toBeEnabled();
  });

  it("distingue « aucun document » de « aucun résultat »", async () => {
    // Une base vide appelle un premier import ; une recherche infructueuse
    // appelle à effacer le filtre. Le même écran pour les deux ferait croire
    // que l'import a échoué.
    afficher([doc()]);
    await screen.findByText("charte-teletravail.md");

    await userEvent.type(screen.getByRole("searchbox", { name: /Rechercher/ }), "zzz");

    expect(screen.getByText(/Aucun document ne correspond à la recherche/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Afficher tous les documents/ })).toBeInTheDocument();
  });
});
