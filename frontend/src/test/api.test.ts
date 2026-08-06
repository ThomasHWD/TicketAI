import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  extractApiErrorDetail,
  getToken,
  TOKEN_KEY,
  USER_KEY,
} from "../lib/api";
import { getTickets, getTicket } from "../lib/api/tickets";
import { validerReponse } from "../lib/api/reponses";
import { lockTicket, LockConflictError } from "../lib/api/locks";
import { uploadDocument } from "../lib/api/documents";
import { login } from "../lib/api/auth";

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

function lastCall(): Request {
  return (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as Request;
}

function lastInit(): RequestInit {
  return (fetch as ReturnType<typeof vi.fn>).mock.calls[0][1] as RequestInit;
}

// ── Setup / teardown ──────────────────────────────────────────────────────────

beforeEach(() => {
  localStorage.setItem(TOKEN_KEY, "tok-test");
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

// ── extractApiErrorDetail ─────────────────────────────────────────────────────

describe("extractApiErrorDetail", () => {
  it("retourne le detail string du corps JSON", async () => {
    const res = new Response(JSON.stringify({ detail: "Ticket introuvable" }), { status: 400 });
    expect(await extractApiErrorDetail(res, "fallback")).toBe("Ticket introuvable");
  });

  it("retourne le fallback si detail n'est pas une string", async () => {
    const res = new Response(JSON.stringify({ detail: { code: 42 } }), { status: 400 });
    expect(await extractApiErrorDetail(res, "fallback")).toBe("fallback");
  });

  it("retourne le fallback si le corps n'est pas du JSON", async () => {
    const res = new Response("Internal Server Error", { status: 500 });
    expect(await extractApiErrorDetail(res, "fallback")).toBe("fallback");
  });

  it("retourne le fallback si detail est absent", async () => {
    const res = new Response(JSON.stringify({ message: "autre champ" }), { status: 400 });
    expect(await extractApiErrorDetail(res, "fallback")).toBe("fallback");
  });
});

// ── getToken ──────────────────────────────────────────────────────────────────

describe("getToken", () => {
  it("lit le token depuis localStorage", () => {
    expect(getToken()).toBe("tok-test");
  });

  it("retourne null si aucun token", () => {
    localStorage.removeItem(TOKEN_KEY);
    expect(getToken()).toBeNull();
  });
});

// ── login ─────────────────────────────────────────────────────────────────────

describe("login", () => {
  it("envoie un form OAuth2 sans header Authorization", async () => {
    mockFetch({ access_token: "jwt", token_type: "bearer", user: {} });
    await login("alice", "secret");
    const init = lastInit();
    expect((init.headers as Record<string, string>)?.["Authorization"]).toBeUndefined();
    expect(init.body?.toString()).toContain("username=alice");
  });

  it("lève une erreur avec le detail serveur", async () => {
    mockFetch({ detail: "Identifiants invalides" }, 401);
    await expect(login("x", "y")).rejects.toThrow("Identifiants invalides");
  });
});

// ── getTickets ────────────────────────────────────────────────────────────────

describe("getTickets", () => {
  it("envoie le header Authorization", async () => {
    mockFetch({ items: [], total: 0, page: 1, pages: 1 });
    await getTickets();
    const init = lastInit();
    expect((init.headers as Record<string, string>)?.Authorization).toBe("Bearer tok-test");
  });

  it("sérialise correctement les filtres dans l'URL", async () => {
    mockFetch({ items: [], total: 0, page: 1, pages: 1 });
    await getTickets({ page: 2, statut: "RÉPONDU", domaines: ["RH", "IT"] });
    const url = lastCall().url ?? (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(url).toContain("page=2");
    expect(url).toContain("statut=R%C3%89PONDU");
    expect(url).toContain("domaines=RH%2CIT");
  });

  it("lève une erreur sur réponse non-ok", async () => {
    mockFetch({}, 500);
    await expect(getTickets()).rejects.toThrow("Erreur chargement tickets");
  });
});

// ── getTicket ─────────────────────────────────────────────────────────────────

describe("getTicket", () => {
  it("appelle le bon endpoint", async () => {
    mockFetch({ id: "abc" });
    await getTicket("abc");
    const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(url).toContain("/tickets/abc");
  });
});

// ── validerReponse ────────────────────────────────────────────────────────────

describe("validerReponse", () => {
  it("envoie un POST JSON avec le payload", async () => {
    mockFetch({ id: "r1", statut: "VALIDÉE" });
    await validerReponse("r1", { commentaire: "OK" });
    const init = lastInit();
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ commentaire: "OK" });
  });

  it("lève LockConflictError sur 409 avec détail objet", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: {
              message: "Ticket verrouillé par alice@ex.com",
              locked_by_email: "alice@ex.com",
              lock_expires_at: "2026-08-06T17:00:00Z",
              is_assigned: false,
            },
          }),
          { status: 409 },
        ),
      ),
    );
    const err = await validerReponse("r1", {}).catch((e) => e);
    expect(err).toBeInstanceOf(LockConflictError);
    expect((err as LockConflictError).lockedByEmail).toBe("alice@ex.com");
  });
});

// ── lockTicket ────────────────────────────────────────────────────────────────

describe("lockTicket", () => {
  it("envoie validator_id dans le corps", async () => {
    mockFetch({ locked: true });
    await lockTicket("t1", "v1");
    expect(JSON.parse(lastInit().body as string)).toEqual({ validator_id: "v1" });
  });
});

// ── uploadDocument ────────────────────────────────────────────────────────────

describe("uploadDocument", () => {
  it("envoie un FormData avec le fichier et le domaine en query", async () => {
    mockFetch({ task_id: "job1" });
    const file = new File(["content"], "doc.pdf", { type: "application/pdf" });
    await uploadDocument(file, "RH", "ma description");
    const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(url).toContain("domaine=RH");
    expect(url).toContain("description=ma+description");
    expect(lastInit().body).toBeInstanceOf(FormData);
  });

  it("lève le detail serveur sur erreur", async () => {
    mockFetch({ detail: "Format non supporté" }, 422);
    const file = new File(["x"], "x.exe");
    await expect(uploadDocument(file, "RH")).rejects.toThrow("Format non supporté");
  });
});

// ── Redirect 401 ──────────────────────────────────────────────────────────────

describe("apiFetch — gestion 401", () => {
  it("purge le localStorage sur 401", async () => {
    localStorage.setItem(USER_KEY, JSON.stringify({ id: "u1" }));
    mockFetch({}, 401);
    // location.assign est un side-effect navigateur — on vérifie juste le localStorage
    try { await getTickets(); } catch { /* ignore */ }
    // jsdom ne purge pas automatiquement — on lit ce que apiFetch a fait
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(localStorage.getItem(USER_KEY)).toBeNull();
  });
});
