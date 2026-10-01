/** Invariant : une SUGGESTION (réponse validée pour une autre question) ne se valide pas en un clic — chaque validation la rapproche du service sans relecture. */

import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { TicketReponse } from "../types";

const validerReponse = vi.fn().mockResolvedValue({});
vi.mock("../lib/api", () => ({
  validerReponse: (...a: unknown[]) => validerReponse(...a),
  updateTag: vi.fn().mockResolvedValue({}),
  corrigerReponse: vi.fn(),
  rejeterReponse: vi.fn(),
  LockConflictError: class extends Error {},
}));
vi.mock("../lib/currentUser", () => ({ getValidatorId: () => "v1" }));

const { useReponseActions } = await import("../hooks/useReponseActions");

function reponse(source: TicketReponse["source"]): TicketReponse {
  return {
    id: "r1", ticket_id: "t1", contenu: "Un mois.", contenu_corrige: null, question_suivi: null,
    statut: "EN_ATTENTE", source, nb_validations: 1, canonique: false, score_similarite: 0.9,
    created_at: null, validator_email: null, validator_nom_complet: null, raison_rejet: null, tag: null,
    obsolete: false, obsolete_raison: null, source_a_relire: false, source_a_relire_raison: null,
    source_analyse_justification: null,
  };
}

beforeEach(() => validerReponse.mockClear());

describe("validation d'une réponse réutilisée ou générée", () => {
  it.each(["SUGGESTION", "LLM"] as const)("%s : le premier clic demande confirmation, le second valide", async (source) => {
    const { result } = renderHook(() => useReponseActions(reponse(source), { onChanged: () => {}, onLockConflict: () => {} }));

    await act(() => result.current.handleValider());
    expect(validerReponse).not.toHaveBeenCalled();
    expect(result.current.confirmingValidation).toBe(true);

    await act(() => result.current.handleValider());
    expect(validerReponse).toHaveBeenCalledTimes(1);
  });
});
