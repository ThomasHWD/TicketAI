# TicketAI — Frontend

Interface React du helpdesk TicketAI.

## Stack

| Outil | Version | Rôle |
|---|---|---|
| React | 19 | UI |
| Vite | 8 | Bundler + dev server |
| TypeScript | 6 | Typage |
| Tailwind CSS | v4 | Styles |
| React Query | v5 | État serveur |
| React Router | v7 | Routing |
| oxlint | — | Linting |

## Démarrer

```bash
# Depuis la racine du projet — lance toute la stack (backend inclus)
make dev
```

Le dev server Vite écoute sur `:5173`. Les appels `/api/*` sont proxiés vers le backend (`:8000`) par Vite.

Pour travailler sur le frontend seul (backend déjà lancé) :

```bash
npm install
npm run dev
```

## Commandes

```bash
npm run dev      # dev server avec HMR
npm run build    # tsc + Vite build (production)
npm run lint     # oxlint
npm run test     # vitest run
```

## Structure

```
src/
├── pages/
│   ├── user/          # Espace employé (tableau de bord, tickets, FAQ)
│   ├── backoffice/    # Espace validateur (file, tickets, réponses, documents)
│   └── admin/         # Administration (groupes, santé, config)
├── components/        # Composants réutilisables
├── hooks/             # React Query + SSE + verrous
├── lib/api/           # Appels API, découpés par domaine fonctionnel
├── context/           # Contextes React (suivi des jobs)
└── types/             # Types TypeScript partagés
```

## Temps réel

Le frontend ouvre une connexion SSE persistante (`useSSE`) qui invalide les caches React Query à chaque événement serveur. **Ne jamais attendre `networkidle`** dans les tests ou scripts browser — la connexion SSE garde le réseau occupé en permanence.

## Documentation

- [Fonctionnalités utilisateur](../Docs/fonctionnalites/espace-utilisateur.md)
- [Traitement des tickets (backoffice)](../Docs/fonctionnalites/backoffice-tickets.md)
- [Notifications et temps réel](../Docs/fonctionnalites/notifications-et-temps-reel.md)
