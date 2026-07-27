import { afterEach, describe, expect, it } from "vitest";

import { getValidatorId } from "./currentUser";
import { USER_KEY } from "./api";

const FALLBACK_ID = "00000000-0000-0000-0000-000000000001";

afterEach(() => {
  localStorage.clear();
});

describe("currentUser (identité courante)", () => {
  it("renvoie l'ID de repli quand aucun utilisateur n'est connecté", () => {
    expect(getValidatorId()).toBe(FALLBACK_ID);
  });

  it("renvoie l'id de l'utilisateur stocké par l'AuthProvider", () => {
    const id = "11111111-1111-1111-1111-111111111111";
    localStorage.setItem(
      USER_KEY,
      JSON.stringify({ id, email: "u@x.fr", prenom: "U", nom: "X", role: "USER" }),
    );
    expect(getValidatorId()).toBe(id);
  });

  it("renvoie le repli si le profil stocké est illisible", () => {
    localStorage.setItem(USER_KEY, "pas-du-json");
    expect(getValidatorId()).toBe(FALLBACK_ID);
  });
});
