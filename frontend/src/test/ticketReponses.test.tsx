/** Invariant côté affichage : le relecteur est prévenu qu'une SUGGESTION réutilise une réponse signalée, et le fil de l'employé tient quand l'API masque un brouillon (contenu null). */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ReponseItem from "../pages/backoffice/TicketDetail/ReponseItem";
import ConversationThread from "../pages/user/UserTicketDetail/ConversationThread";
import type { TicketReponse } from "../types";

function reponse(overrides: Partial<TicketReponse> = {}): TicketReponse {
  return {
    id: "r1",
    ticket_id: "t1",
    contenu: "Le préavis est d'un mois.",
    contenu_corrige: null,
    question_suivi: null,
    statut: "EN_ATTENTE",
    source: "SUGGESTION",
    nb_validations: 0,
    canonique: false,
    score_similarite: 0.95,
    created_at: "2026-09-28T10:00:00Z",
    validator_email: null,
    validator_nom_complet: null,
    raison_rejet: null,
    tag: null,
    obsolete: false,
    obsolete_raison: null,
    source_a_relire: false,
    source_a_relire_raison: null,
    source_analyse_justification: null,
    ...overrides,
  };
}

function monterItem(r: TicketReponse) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <ReponseItem reponse={r} domaine="RH" readOnly onChanged={() => {}} onLockConflict={() => {}} />
    </QueryClientProvider>,
  );
}

describe("ReponseItem — source signalée", () => {
  it("prévient le relecteur, avec la justification de l'analyse", () => {
    monterItem(reponse({
      source_a_relire: true,
      source_a_relire_raison: "CONTREDITE_PROBABLE",
      source_analyse_justification: "Le préavis passe à deux mois.",
    }));
    expect(screen.getByRole("note")).toHaveTextContent("Le préavis passe à deux mois.");
  });

  it("reste muet quand la source est saine", () => {
    monterItem(reponse());
    expect(screen.queryByRole("note")).toBeNull();
  });
});

describe("ConversationThread — brouillon masqué par l'API", () => {
  it("affiche l'attente sans planter ni fuiter de texte", () => {
    render(
      <ConversationThread
        question="Quel est le préavis ?"
        created_at="2026-09-28T09:00:00Z"
        reponses={[reponse({ contenu: null, source: "LLM" })]}
      />,
    );
    expect(screen.getByText("Quel est le préavis ?")).toBeInTheDocument();
    expect(screen.queryByText(/préavis est/)).toBeNull();
  });
});
