import {
  BookText,
  History,
  LayoutDashboard,
  MessageSquare,
  MessagesSquare,
  SlidersHorizontal,
  TicketMinus,
  Users,
} from "lucide-react";
import type { ElementType } from "react";

export interface NavItem {
  to: string;
  icon: ElementType;
  label: string;
}

export const navMain: NavItem[] = [
  { to: "/", icon: LayoutDashboard, label: "Tableau de bord" },
  { to: "/tickets", icon: TicketMinus, label: "Tickets" },
  { to: "/mon-suivi", icon: MessagesSquare, label: "Mon suivi" },
  { to: "/reponses-enregistrees", icon: MessageSquare, label: "Réponses enregistrées" },
  { to: "/base-de-connaissances", icon: BookText, label: "Base de connaissances" },
];

export const navSettings: NavItem[] = [
  { to: "/historique", icon: History, label: "Mon historique" },
];

export const navAdmin: NavItem[] = [
  { to: "/admin/dashboard", icon: LayoutDashboard, label: "Vue globale" },
  { to: "/admin", icon: Users, label: "Groupes" },
  { to: "/admin/config", icon: SlidersHorizontal, label: "Configuration" },
];
