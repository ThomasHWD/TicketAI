import { apiFetch, extractApiErrorDetail, BASE_URL } from "./client";
import type { AuthUser, LoginResponse } from "./client";

export async function login(username: string, password: string): Promise<LoginResponse> {
  const body = new URLSearchParams({ username, password });
  const res = await fetch(`${BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!res.ok) {
    const detail = await extractApiErrorDetail(res, "Identifiant ou mot de passe incorrect.");
    throw new Error(detail);
  }
  return res.json();
}

export async function getMe(): Promise<AuthUser> {
  const res = await apiFetch(`${BASE_URL}/auth/me`);
  if (!res.ok) throw new Error("Session invalide");
  return res.json();
}
