import { afterEach, describe, expect, it } from "vitest";

import { getValidatorId, setValidatorId } from "./currentUser";

const DEFAULT_VALIDATOR_ID = "00000000-0000-0000-0000-000000000001";

afterEach(() => {
  localStorage.clear();
});

describe("currentUser (shim validateur)", () => {
  it("renvoie l'ID par défaut quand rien n'est stocké", () => {
    expect(getValidatorId()).toBe(DEFAULT_VALIDATOR_ID);
  });

  it("persiste puis relit l'ID stocké", () => {
    const id = "11111111-1111-1111-1111-111111111111";
    setValidatorId(id);
    expect(getValidatorId()).toBe(id);
  });

  it("écrase la valeur précédente", () => {
    setValidatorId("aaaa");
    setValidatorId("bbbb");
    expect(getValidatorId()).toBe("bbbb");
  });
});
