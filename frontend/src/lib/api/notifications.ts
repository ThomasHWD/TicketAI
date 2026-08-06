import { apiFetch, BASE_URL } from "./client";
import type { Notification } from "../../types.ts";

export async function getNotifications(): Promise<Notification[]> {
  const res = await apiFetch(`${BASE_URL}/notifications`);
  if (!res.ok) throw new Error("Erreur chargement notifications");
  return res.json();
}

export async function marquerNotificationLue(id: string): Promise<void> {
  await apiFetch(`${BASE_URL}/notifications/${id}/lire`, { method: "POST" });
}

export async function toutMarquerLu(): Promise<void> {
  await apiFetch(`${BASE_URL}/notifications/tout-lire`, { method: "POST" });
}
