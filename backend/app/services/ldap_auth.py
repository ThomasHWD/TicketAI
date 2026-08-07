"""Authentification LDAP / Active Directory.

Point d'entrée unique : ``authenticate(username, password)``. Il renvoie une
``LdapIdentity`` si les identifiants sont valides, ``None`` sinon.

On bind avec un compte de service, on cherche l'utilisateur, puis on **re-bind
avec son DN et son mot de passe** pour valider réellement les identifiants.
"""

import ssl
from dataclasses import dataclass

from app.config import settings
from ldap3 import ALL, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException


@dataclass
class LdapIdentity:
    username: str
    email: str
    prenom: str | None
    nom: str | None
    departement: str | None
    is_gestionnaire: bool
    role: str = "USER"


def authenticate(username: str, password: str) -> LdapIdentity | None:
    """Valide les identifiants contre l'annuaire LDAP / Active Directory."""
    if not username or not password:
        return None
    try:
        return _authenticate_ldap(username, password)
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
    is_gestionnaire = any(settings.ldap_group_gestionnaire.lower() in dn for dn in member_of)
    is_admin = any(settings.ldap_group_admin.lower() in dn for dn in member_of)

    return LdapIdentity(
        username=username,
        email=attr(settings.ldap_attr_email) or f"{username}@ticketai.local",
        prenom=attr(settings.ldap_attr_firstname),
        nom=attr(settings.ldap_attr_lastname),
        departement=attr(settings.ldap_attr_department),
        is_gestionnaire=is_gestionnaire,
        role="ADMIN" if is_admin else "USER",
    )


def _search_filter(username: str) -> str:
    return settings.ldap_user_search_filter.format(username=username)


def _search_attributes() -> list[str]:
    attrs = [
        settings.ldap_attr_email,
        settings.ldap_attr_firstname,
        settings.ldap_attr_lastname,
        settings.ldap_attr_department,
        "memberOf",
    ]
    return [a for a in attrs if a]


# ── Mode réel (Active Directory / LDAP) ──────────────────────────────


def _make_server(url: str) -> Server:
    tls = Tls(validate=ssl.CERT_REQUIRED if settings.ldap_tls_validate else ssl.CERT_NONE)
    return Server(url, tls=tls, get_info=ALL, connect_timeout=settings.ldap_timeout)


def _get_server() -> Server:
    """Retourne le serveur primaire ; bascule sur le secondaire si configuré et injoignable."""
    primary = _make_server(settings.ldap_server_url)
    if not settings.ldap_server_url_secondary:
        return primary
    try:
        conn = Connection(primary, auto_bind=True, receive_timeout=settings.ldap_timeout)
        conn.unbind()
        return primary
    except LDAPException:
        return _make_server(settings.ldap_server_url_secondary)


def _authenticate_ldap(username: str, password: str) -> LdapIdentity | None:
    server = _get_server()

    # 1. Bind du compte de service pour rechercher l'utilisateur.
    svc = Connection(
        server,
        user=settings.ldap_bind_dn or None,
        password=settings.ldap_bind_password or None,
        auto_bind=True,
        receive_timeout=settings.ldap_timeout,
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
