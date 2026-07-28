"""Authentification LDAP / Active Directory.

Point d'entrée unique : ``authenticate(username, password)``. Il renvoie une
``LdapIdentity`` si les identifiants sont valides, ``None`` sinon.

Deux implémentations derrière la même signature, choisies par ``settings.auth_mode`` :

- ``"mock"`` : annuaire simulé en mémoire via la stratégie ``MOCK_SYNC`` de ldap3.
  Se comporte comme un vrai annuaire (recherche + bind vérifiant le mot de passe),
  mais ne nécessite aucun serveur. Idéal en dev.
- ``"ldap"`` : vrai serveur. On bind avec un compte de service, on cherche l'utilisateur,
  puis on **re-bind avec son DN et son mot de passe** pour valider les identifiants.

Le passage mock → réel se fait uniquement via le ``.env`` (aucun changement de code).
"""

from dataclasses import dataclass

from app.config import settings
from app.services.mock_ldap_seed import MOCK_USERS
from ldap3 import ALL, MOCK_SYNC, OFFLINE_AD_2012_R2, Connection, Server
from ldap3.core.exceptions import LDAPException


@dataclass
class LdapIdentity:
    username: str
    email: str
    prenom: str | None
    nom: str | None
    departement: str | None
    is_gestionnaire: bool


def authenticate(username: str, password: str) -> LdapIdentity | None:
    """Valide les identifiants contre l'annuaire (mock ou réel)."""
    if not username or not password:
        return None
    try:
        if settings.auth_mode == "ldap":
            return _authenticate_ldap(username, password)
        return _authenticate_mock(username, password)
    except LDAPException:
        # Serveur injoignable, filtre invalide, etc. → échec d'auth silencieux.
        return None


def _identity_from_entry(username: str, entry) -> LdapIdentity:
    """Construit une identité à partir d'une entrée LDAP trouvée."""

    def attr(name: str) -> str | None:
        value = entry[name].value if name in entry else None
        return str(value) if value else None

    def multi_attr(name: str) -> list[str]:
        if name not in entry:
            return []
        v = entry[name].value
        return v if isinstance(v, list) else ([str(v)] if v else [])

    member_of = [s.lower() for s in multi_attr("memberOf")]
    is_gestionnaire = any(
        settings.ldap_group_gestionnaire.lower() in dn for dn in member_of
    )

    return LdapIdentity(
        username=username,
        email=attr(settings.ldap_attr_email) or f"{username}@ticketai.local",
        prenom=attr(settings.ldap_attr_firstname),
        nom=attr(settings.ldap_attr_lastname),
        departement=attr(settings.ldap_attr_department),
        is_gestionnaire=is_gestionnaire,
    )


def _search_filter(username: str) -> str:
    return settings.ldap_user_search_filter.format(username=username)


def _search_attributes() -> list[str]:
    return [
        settings.ldap_attr_email,
        settings.ldap_attr_firstname,
        settings.ldap_attr_lastname,
        settings.ldap_attr_department,
        "memberOf",
    ]


# ── Mode réel (Active Directory / LDAP) ──────────────────────────────


def _authenticate_ldap(username: str, password: str) -> LdapIdentity | None:
    server = Server(settings.ldap_server_url, get_info=ALL)

    # 1. Bind du compte de service pour rechercher l'utilisateur.
    svc = Connection(
        server,
        user=settings.ldap_bind_dn or None,
        password=settings.ldap_bind_password or None,
        auto_bind=True,
    )
    found = svc.search(
        settings.ldap_user_search_base,
        _search_filter(username),
        attributes=_search_attributes(),
    )
    if not found or not svc.entries:
        svc.unbind()
        return None
    entry = svc.entries[0]
    dn = entry.entry_dn
    identity = _identity_from_entry(username, entry)
    svc.unbind()

    # 2. Re-bind avec le DN de l'utilisateur : valide réellement le mot de passe.
    user_conn = Connection(server, user=dn, password=password)
    if not user_conn.bind():
        return None
    user_conn.unbind()
    return identity


# ── Mode simulé (dev) ────────────────────────────────────────────────


def _build_mock_connection() -> Connection:
    """Crée une connexion ldap3 MOCK_SYNC alimentée par l'annuaire fictif."""
    server = Server("mock_ldap", get_info=OFFLINE_AD_2012_R2)
    conn = Connection(server, client_strategy=MOCK_SYNC)
    for user in MOCK_USERS:
        # DN construit sous la base configurée pour que la recherche (qui utilise
        # settings.ldap_user_search_base) retrouve toujours l'entrée, même si le
        # .env pointe déjà vers la base du futur AD réel.
        dn = f"cn={user['username']},{settings.ldap_user_search_base}"
        conn.strategy.add_entry(
            dn,
            {
                "objectClass": ["top", "person", "organizationalPerson", "user"],
                "sAMAccountName": user["username"],
                "userPassword": user["password"],
                settings.ldap_attr_email: user["mail"],
                settings.ldap_attr_firstname: user["givenName"],
                settings.ldap_attr_lastname: user["sn"],
                settings.ldap_attr_department: user.get("department"),
                "memberOf": [
                    f"CN={g},{settings.ldap_user_search_base}"
                    for g in user.get("groups", [])
                ],
            },
        )
    conn.bind()
    return conn


def _authenticate_mock(username: str, password: str) -> LdapIdentity | None:
    conn = _build_mock_connection()
    found = conn.search(
        settings.ldap_user_search_base,
        _search_filter(username),
        attributes=_search_attributes(),
    )
    if not found or not conn.entries:
        return None
    entry = conn.entries[0]
    dn = entry.entry_dn
    identity = _identity_from_entry(username, entry)

    # Vérifie le mot de passe via un re-bind (MOCK_SYNC contrôle userPassword).
    if not conn.rebind(user=dn, password=password):
        return None
    return identity
