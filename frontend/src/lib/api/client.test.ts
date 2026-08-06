import { describe, expect, it } from "vitest";
import { extractApiErrorDetail } from "./client";

function makeResponse(body: unknown, status = 400): Response {
  return new Response(typeof body === "string" ? body : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("extractApiErrorDetail", () => {
  it("retourne le detail string du corps JSON", async () => {
    const res = makeResponse({ detail: "Ticket introuvable" });
    expect(await extractApiErrorDetail(res, "fallback")).toBe("Ticket introuvable");
  });

  it("retourne le fallback si detail n'est pas une string", async () => {
    const res = makeResponse({ detail: { code: 42 } });
    expect(await extractApiErrorDetail(res, "fallback")).toBe("fallback");
  });

  it("retourne le fallback si le corps n'est pas du JSON", async () => {
    const res = new Response("Internal Server Error", { status: 500 });
    expect(await extractApiErrorDetail(res, "fallback")).toBe("fallback");
  });

  it("retourne le fallback si detail est absent", async () => {
    const res = makeResponse({ message: "autre champ" });
    expect(await extractApiErrorDetail(res, "fallback")).toBe("fallback");
  });
});
