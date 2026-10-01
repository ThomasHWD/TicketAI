/** Invariant : aucune touche seule n'ajoute une validation (elle compte pour la promotion canonique), et rien ne traverse une modale ouverte. */

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { setRaccourcisActifs, useRaccourcisReponse } from "../hooks/useRaccourcisReponse";

const valider = vi.fn();
const corriger = vi.fn();

function Fiche({ modale = false }: { modale?: boolean }) {
  useRaccourcisReponse(() => {});
  return (
    <>
      <ul>
        <li data-reponse-item>
          <div data-reponse-actions>
            <button data-action="valider" onClick={valider}>Valider</button>
            <button data-action="corriger" onClick={corriger}>Corriger</button>
          </div>
        </li>
      </ul>
      {modale && <div role="dialog" aria-modal="true"><button>Fermer</button></div>}
    </>
  );
}

afterEach(() => {
  vi.clearAllMocks();
  setRaccourcisActifs(true);
});

describe("raccourcis de la fiche ticket", () => {
  it("E déclenche bien son action (le hook est branché)", () => {
    render(<Fiche />);
    fireEvent.keyDown(document.body, { key: "e" });
    expect(corriger).toHaveBeenCalledTimes(1);
  });

  it("V amène le focus sur Valider sans valider", () => {
    render(<Fiche />);
    fireEvent.keyDown(document.body, { key: "v" });
    expect(valider).not.toHaveBeenCalled();
    expect(screen.getByText("Valider")).toHaveFocus();
  });

  it.each([
    ["modale ouverte", () => render(<Fiche modale />)],
    ["raccourcis désactivés", () => { setRaccourcisActifs(false); render(<Fiche />); }],
  ])("rien ne part quand : %s", (_, monter) => {
    monter();
    fireEvent.keyDown(document.body, { key: "e" });
    fireEvent.keyDown(document.body, { key: "v" });
    expect(corriger).not.toHaveBeenCalled();
    expect(screen.getByText("Valider")).not.toHaveFocus();
  });
});
