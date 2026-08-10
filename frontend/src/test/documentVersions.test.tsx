import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TOKEN_KEY } from "../lib/api";
import {
  downloadDocumentVersion,
  getDocumentVersions,
  restoreDocumentVersion,
} from "../lib/api/documents";
import DocHistoryModal from "../pages/backoffice/DocHistoryModal";
import type { DocumentVersion } from "../types.ts";

// ── Helpers ───────────────────────────────────────────────────────────────────

function mockFetch(body: unknown, status = 200): void {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
}

function calls() {
  return (fetch as ReturnType<typeof vi.fn>).mock.calls;
}

function version(overrides: Partial<DocumentVersion> = {}): DocumentVersion {
  return {
    version: 1,
    filename: "charte.md",
    taille_octets: 2048,
    nb_chunks: 3,
    restauree_depuis: null,
    courante: false,
    auteur: "Alice Martin",
    fichier_disponible: true,
    created_at: "2026-01-15T10:00:00Z",
    remplacee_at: null,
    ...overrides,
  };
}

beforeEach(() => {
  localStorage.setItem(TOKEN_KEY, "tok-test");
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

// ── API ───────────────────────────────────────────────────────────────────────

describe("API des versions", () => {
  it("liste les versions d'un document", async () => {
    mockFetch({ doc_id: "d1", version_courante: 2, items: [] });

    const res = await getDocumentVersions("d1");

    expect(calls()[0][0]).toBe("/api/v1/documents/d1/versions");
    expect(res.version_courante).toBe(2);
  });

  it("restaure via POST, pas via GET", async () => {
    // Un GET partirait sans erreur visible et ne créerait aucun staging :
    // l'écran d'impact s'ouvrirait sur des données fantômes.
    mockFetch({ staging_id: "s1", restauree_depuis: 1, version_cible: 3 });

    const impact = await restoreDocumentVersion("d1", 1);

    expect(calls()[0][0]).toBe("/api/v1/documents/d1/versions/1/restaurer");
    expect(calls()[0][1]).toMatchObject({ method: "POST" });
    expect(impact.restauree_depuis).toBe(1);
  });

  it("remonte le message du serveur quand la restauration est refusée", async () => {
    mockFetch({ detail: "Le fichier de la v1 n'est plus disponible." }, 409);

    await expect(restoreDocumentVersion("d1", 1)).rejects.toThrow(
      "Le fichier de la v1 n'est plus disponible.",
    );
  });

  it("télécharge une archive avec l'en-tête Authorization", async () => {
    // Régression déjà survenue dans ce projet : un `<a href>` nu part sans le
    // Bearer (stocké en localStorage) et se fait refuser en 401.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        blob: () => Promise.resolve(new Blob(["contenu"])),
      }),
    );
    vi.stubGlobal("URL", { ...URL, createObjectURL: () => "blob:x", revokeObjectURL: () => {} });

    await downloadDocumentVersion("d1", 2, "charte.md");

    expect(calls()[0][0]).toBe("/api/v1/documents/d1/versions/2/download");
    expect(calls()[0][1].headers).toMatchObject({ Authorization: "Bearer tok-test" });
  });
});

// ── Modale d'historique ───────────────────────────────────────────────────────

function afficher(items: DocumentVersion[], peutRestaurer = true) {
  mockFetch({ doc_id: "d1", version_courante: 2, items });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onImpact = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <DocHistoryModal
        doc={{ doc_id: "d1", filename: "charte.md", version: 2 }}
        peutRestaurer={peutRestaurer}
        onClose={vi.fn()}
        onImpact={onImpact}
      />
    </QueryClientProvider>,
  );
  return { onImpact };
}

describe("DocHistoryModal", () => {
  it("n'offre pas de restaurer la version courante", async () => {
    afficher([version({ version: 2, courante: true }), version({ version: 1 })]);

    await screen.findByText(/version courante/);

    // Une seule des deux lignes porte le bouton : restaurer la courante
    // renverrait 409 « déjà la version actuelle ».
    expect(screen.getAllByRole("button", { name: /Restaurer/ })).toHaveLength(1);
  });

  it("désactive la restauration quand l'archive a disparu du disque", async () => {
    // Cas des documents backfillés : aucun fichier sous `v{n}/`. Proposer le
    // bouton serait promettre une action qui échoue à coup sûr.
    afficher([
      version({ version: 2, courante: true }),
      version({ version: 1, fichier_disponible: false }),
    ]);

    const bouton = await screen.findByRole("button", { name: /Restaurer/ });

    expect(bouton).toBeDisabled();
  });

  it("masque la restauration sans droit d'écriture sur le domaine", async () => {
    afficher([version({ version: 2, courante: true }), version({ version: 1 })], false);

    await screen.findByText(/version courante/);

    expect(screen.queryByRole("button", { name: /Restaurer/ })).toBeNull();
  });

  it("remonte l'aperçu d'impact à l'appelant", async () => {
    const { onImpact } = afficher([
      version({ version: 2, courante: true }),
      version({ version: 1 }),
    ]);
    const bouton = await screen.findByRole("button", { name: /Restaurer/ });

    mockFetch({ staging_id: "s1", version_cible: 3, restauree_depuis: 1, nb_obsoletes: 0 });
    await userEvent.click(bouton);

    // La modale ne confirme rien elle-même : elle passe la main à l'écran
    // d'impact, seul endroit d'où part la confirmation.
    await waitFor(() => expect(onImpact).toHaveBeenCalledOnce());
    expect(onImpact.mock.calls[0][0]).toMatchObject({ staging_id: "s1", restauree_depuis: 1 });
  });

  it("affiche l'échec sans fermer la modale", async () => {
    afficher([version({ version: 2, courante: true }), version({ version: 1 })]);
    const bouton = await screen.findByRole("button", { name: /Restaurer/ });

    mockFetch({ detail: "Une mise à jour est déjà en cours." }, 409);
    await userEvent.click(bouton);

    expect(await screen.findByText(/Une mise à jour est déjà en cours./)).toBeInTheDocument();
  });

  it("signale qu'une version restaurée est née d'une autre", async () => {
    afficher([version({ version: 3, courante: true, restauree_depuis: 1 })]);

    expect(await screen.findByText(/restaurée depuis la v1/)).toBeInTheDocument();
  });
});
