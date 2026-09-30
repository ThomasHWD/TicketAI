"""LDAP/AD authentication. Two-bind protocol: service account to look up the user DN, then re-bind with user"""

import re
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
    if not username or not password:
        return None
    try:
        return _authenticate_ldap(username, password)
    except LDAPException:
        # Serveur injoignable, filtre invalide, etc. → échec d'auth silencieux.
        return None


def _normaliser_dn(dn: str) -> str:
    """Casse et espaces autour des virgules ignorés : AD renvoie `CN=a,OU=b`, un .env peut porter `CN=a, OU=b`."""
    return re.sub(r"\s*,\s*", ",", dn.strip().lower())


def membre_du_groupe(groupe: str, member_of: list[str]) -> bool:
    """`groupe` : DN complet, ou nom seul comparé au CN de chaque groupe. Égalité, jamais sous-chaîne : `"" in dn`
    rendait tout le monde ADMIN quand la variable était vide, et un nom capturait ses homonymes (…-ADM-LECTURE)."""
    cible = _normaliser_dn(groupe)
    if not cible:
        return False
    dns = [_normaliser_dn(dn) for dn in member_of]
    if "=" in cible:
        return cible in dns
    return cible in {re.split(r"(?<!\\),", dn, maxsplit=1)[0].partition("=")[2] for dn in dns}


def _identity_from_entry(username: str, entry) -> LdapIdentity:
    def attr(name: str) -> str | None:
        value = entry[name].value if name in entry else None
        return str(value) if value else None

    def multi_attr(name: str) -> list[str]:
        if name not in entry:
            return []
        v = entry[name].value
        return v if isinstance(v, list) else ([str(v)] if v else [])

    member_of = multi_attr("memberOf")
    is_gestionnaire = membre_du_groupe(settings.ldap_group_gestionnaire, member_of)
    is_admin = membre_du_groupe(settings.ldap_group_admin, member_of)

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
    from ldap3.utils.conv import escape_filter_chars

    return settings.ldap_user_search_filter.format(username=escape_filter_chars(username))


def _search_attributes() -> list[str]:
    attrs = [
        settings.ldap_attr_email,
        settings.ldap_attr_firstname,
        settings.ldap_attr_lastname,
        settings.ldap_attr_department,
        "memberOf",
    ]
    return [a for a in attrs if a]


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

    # Re-bind with user DN — actually validates the password (service-account bind does not).
    user_conn = Connection(server, user=dn, password=password)
    if not user_conn.bind():
        return None
    user_conn.unbind()
    return identity
