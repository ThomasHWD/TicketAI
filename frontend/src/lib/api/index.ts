export { TOKEN_KEY, USER_KEY, BASE_URL, getToken, apiFetch, extractApiErrorDetail } from "./client";
export type { AuthUser, LoginResponse } from "./client";

export { login, getMe } from "./auth";

export { LockConflictError, lockTicket, heartbeatTicket, unlockTicket } from "./locks";

export {
  soumettreQuestion,
  poserSuivi,
  cloturerTicket,
  getTickets,
  getParticipatedTickets,
  getTicket,
  getReponsesByTicket,
} from "./tickets";

export {
  getReponsesEnAttente,
  getReponsesCanoniques,
  editerReponseCanonique,
  supprimerReponseCanonique,
  validerReponse,
  rejeterReponse,
  corrigerReponse,
} from "./reponses";

export {
  uploadDocument,
  getDocumentStatus,
  listDocuments,
  getDocumentChunks,
  deleteDocument,
  downloadDocument,
} from "./documents";

export type { MembreGroupe } from "./assignation";
export {
  getValidateursByDomaine,
  assignTicket,
  unassignTicket,
  getTicketWorkflow,
  getMyAssignedTickets,
} from "./assignation";

export { getNotifications, marquerNotificationLue, toutMarquerLu } from "./notifications";

export {
  setChefGroupe,
  getSiteConfig,
  setSiteConfig,
  getServicesHealth,
  getIncidents,
  deleteTicketIncident,
  retryTicket,
  retryDocument,
  downloadDocumentUrl,
  deleteDocumentIncident,
} from "./admin";
export type {
  BannerConfig,
  SiteConfigData,
  ServiceStatusValue,
  ServiceHealth,
  FunctionalStats,
  ServicesHealthData,
  DocumentIncident,
  TicketIncident,
  IncidentsData,
} from "./admin";

export {
  getDashboardStats,
  getGroupeMembresStats,
} from "./stats";
export type {
  StatCarte,
  RepartitionStatut,
  RepartitionBranche,
  DayCount,
  TicketSummaryDashboard,
  DashboardStats,
  MembreStats,
  GroupeMembresStats,
} from "./stats";
