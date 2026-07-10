# RÉFÉRENCIEL QUALITÉ OMNICORP – OC-HR-IT-2026-V3
## TITRE : PROCÉDURE STANDARD D'ONBOARDING ET DE PROVISIONING INFORMATIQUE

### 1. OBJET & CHAMP D'APPLICATION
La présente procédure définit le flux de travail (workflow) obligatoire pour l'intégration technique de tout nouveau collaborateur au sein d'OmniCorp. Elle vise à garantir la conformité réglementaire avec l'Article L1221-1 du Code du travail concernant l'exécution des contrats, tout en assurant la sécurité des accès logiques dès le premier jour d'activité.

### 2. DÉCLENCHEMENT ET SYNCHRONISATION WORKDAY
Le processus s'amorce automatiquement à la validation de la promesse d'embauche par la Direction des Ressources Humaines (DRH) dans l'ERP **Workday**. 
* **M-15 jours avant l'arrivée :** Workday génère un identifiant unique temporaire (ID_OMNI) et pousse le profil futur vers le système de gestion des identités et des accès (IAM).
* **M-7 jours avant l'arrivée :** Le manager N+1 reçoit une notification automatique l'enjoignant à se connecter au portail ITSM (ServiceNow) pour initier la demande de dotation matérielle ("Ticket Onboarding Asset").

### 3. COMMANDE ET PROVISIONING DU MATÉRIEL
Le catalogue de dotation standard impose la sélection exclusive des équipements homologués par la DSI :
* **Poste de travail :** PC Portable Corporate avec chiffrement BitLocker ou MacBook Pro (selon profil métier).
* **Sécurité forte :** Attribution d'une clé d'authentification multifacteur matérielle **Yubikey 5C FIPS**, obligatoire pour tout accès distant ou VPN.

Le provisionnement des comptes s'effectue par la synchronisation automatisée entre Workday et l'**Active Directory (AD)** Azure. Les comptes de messagerie `prenom.nom@omnicorp.fr` sont créés au statut "Disabled" et ne passent au statut "Active" qu'à la date d'effet du contrat de travail à 00h01.

### 4. ATTRIBUTION DES DROITS ET SLA (DÉLAIS)
La DSI s'engage sur un Contrat de Niveau de Service (**SLA**) de **48 heures maximum** à compter de l'arrivée du collaborateur pour l'attribution complète des droits applicatifs de base (Accès ERP, suites collaboratives, partages réseau de service). Toute demande de droits spécifiques (rôles d'administration, accès bases de données) doit faire l'objet d'un ticket complémentaire approuvé par le Responsable de la Sécurité des Systèmes d'Information (RSSI).