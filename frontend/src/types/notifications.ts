export interface Notification {
  id: string;
  ticket_id: string;
  reponse_id: string | null;
  type: "REPONSE_VALIDEE";
  read_at: string | null;
  created_at: string | null;
  ticket_objet: string | null;
  ticket_question: string | null;
}
