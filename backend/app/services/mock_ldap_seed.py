"""Annuaire LDAP fictif pour le mode de développement (auth_mode == "mock").

Ces entrées simulent un Active Directory : elles portent les mêmes attributs
(`sAMAccountName`, `mail`, `givenName`, `sn`) que ceux qu'on lira sur le vrai
serveur. Le mot de passe de tous les comptes de test est ``password``.

Le DN de chaque entrée est construit à l'exécution **sous la base configurée**
(`settings.ldap_user_search_base`), afin que le mock reste fonctionnel même si
l'on a déjà renseigné dans le `.env` la base du futur AD réel tout en gardant
``AUTH_MODE=mock``.

Pour passer en production, il n'y a RIEN à changer ici : on met
``AUTH_MODE=ldap`` dans le ``.env`` et l'annuaire réel prend le relais.
"""

MOCK_USERS = [
    {
        "username": "thomas",
        "password": "password",
        "mail": "thomas.henwood@ticketai.local",
        "givenName": "Thomas",
        "sn": "Henwood",
        "department": "IT",
        "groups": ["Gestionnaire", "Admin"],
    },
    {
        "username": "alice",
        "password": "password",
        "mail": "alice.martin@ticketai.local",
        "givenName": "Alice",
        "sn": "Martin",
        "department": "RH",
        "groups": ["Gestionnaire"],
    },
    {
        "username": "bob",
        "password": "password",
        "mail": "bob.durand@ticketai.local",
        "givenName": "Bob",
        "sn": "Durand",
        "department": "JURIDIQUE",
        "groups": ["tlm"],
    },
]
