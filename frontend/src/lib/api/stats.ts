import { apiFetch, BASE_URL } from "./client";

export interface StatCarte {
  valeur: number;
  variation: number;
  hausse: boolean;
  count?: number;
}

export interface RepartitionStatut {
  statut: string;
  count: number;
  pct: number;
}

export interface DayCount {
  date: string;
  count: number;
}

export interface TicketSummaryDashboard {
  id: string;
  objet: string;
  domaine: string;
  statut_ticket: string;
  statut_job: string;
  branche?: "CANONIQUE" | "SUGGESTION" | "LLM" | "HORS_DOMAINE" | null;
  created_at: string | null;
}

export interface RepartitionBranche {
  branche: "CANONIQUE" | "SUGGESTION" | "LLM" | "HORS_DOMAINE";
  count: number;
  pct: number;
}

export interface DashboardStats {
  periode: string;
  stats_cartes: {
    nouveaux: StatCarte;
    en_cours: StatCarte;
    tickets_clotures: StatCarte;
    repondu_canonique: StatCarte;
    temps_premiere_reponse: StatCarte;
    temps_cloture: StatCarte;
  };
  repartition_statuts: RepartitionStatut[];
  repartition_branches: RepartitionBranche[];
  tickets_par_jour: DayCount[];
  traitement_par_jour: DayCount[];
  derniers_tickets: TicketSummaryDashboard[];
  satisfaction: {
    avg_qualite: number | null;
    avg_delai: number | null;
    nb_avec_notes: number;
  } | null;
}

export async function getDashboardStats(
  domaine?: string,
  periode = "semaine",
): Promise<DashboardStats> {
  const params = new URLSearchParams({ periode });
  if (domaine) params.set("domaine", domaine);
  const res = await apiFetch(`${BASE_URL}/stats/dashboard?${params}`);
  if (!res.ok) throw new Error("Erreur chargement statistiques");
  return res.json();
}

export interface MembreStats {
  id: string;
  email: string;
  prenom: string | null;
  nom: string | null;
  is_chef: boolean;
  nb_reponses_validees: number;
  nb_documents: number;
}

export interface GroupeMembresStats {
  groupe: { id: string; nom: string; domaine: string };
  membres: MembreStats[];
}

export async function getGroupeMembresStats(groupeId: string, periode = "semaine"): Promise<GroupeMembresStats> {
  const res = await apiFetch(`${BASE_URL}/stats/groupe/${groupeId}/membres?periode=${periode}`);
  if (!res.ok) throw new Error("Erreur chargement statistiques équipe");
  return res.json();
}

export interface HorsDomaineQuestion {
  id: string;
  objet: string | null;
  question: string;
  created_at: string | null;
}

export interface HorsDomaineEntry {
  domaine: string;
  nb_tickets: number;
  questions: HorsDomaineQuestion[];
}

export async function getHorsDomaine(periode = "mois"): Promise<HorsDomaineEntry[]> {
  const res = await apiFetch(`${BASE_URL}/stats/hors-domaine?periode=${periode}`);
  if (!res.ok) throw new Error("Erreur chargement angles morts");
  return res.json();
}

export async function masquerAngleMort(ticketId: string): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/stats/hors-domaine/${ticketId}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Erreur lors de la suppression");
}
