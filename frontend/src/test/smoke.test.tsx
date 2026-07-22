import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

// Smoke-test : valide le câblage jsdom + React Testing Library + matchers
// jest-dom. Sert de socle pour les futurs tests de composants (rendre un vrai
// composant applicatif une fois les dépendances router/query mockées).
function Hello({ name }: { name: string }) {
  return <h1>Bonjour {name}</h1>;
}

describe("environnement de test frontend", () => {
  it("rend un composant React dans le DOM", () => {
    render(<Hello name="TicketAI" />);
    expect(
      screen.getByRole("heading", { name: /bonjour ticketai/i }),
    ).toBeInTheDocument();
  });
});
