"""LDAP authentication service with connection pooling."""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


async def ldap_authenticate(username: str, password: str) -> dict[str, Any] | None:
    """Authenticate via LDAP bind. Returns user attributes on success, None on failure."""
    if not settings.ldap_enabled:
        return None

    try:
        import ldap3

        user_dn = f"uid={username},{settings.ldap_base_dn}"

        server = ldap3.Server(
            settings.ldap_server,
            connect_timeout=settings.ldap_timeout_seconds,
        )
        conn = ldap3.Connection(
            server,
            user=user_dn,
            password=password,
            auto_bind=True,
            receive_timeout=settings.ldap_timeout_seconds,
        )

        search_filter = settings.ldap_user_filter % {"username": username}
        conn.search(
            settings.ldap_base_dn,
            search_filter,
            attributes=["cn", "mail", "memberOf"],
        )

        if not conn.entries:
            conn.unbind()
            return None

        entry = conn.entries[0]
        member_of = [str(g) for g in getattr(entry, "memberOf", [])]

        result = {
            "username": username,
            "display_name": str(getattr(entry, "cn", username)),
            "email": str(getattr(entry, "mail", "")),
            "member_of_groups": member_of,
        }
        conn.unbind()
        return result

    except Exception as exc:
        logger.warning("LDAP authentication failed: %s", exc)
        return None


def map_ldap_groups(ldap_groups: list[str]) -> list[str]:
    """Map LDAP group DNs to local project group IDs using configured mapping."""
    if not settings.ldap_group_mapping:
        return []
    mapped: list[str] = []
    for dn in ldap_groups:
        for pattern, group_id in settings.ldap_group_mapping.items():
            if pattern in dn:
                mapped.append(group_id)
    return list(set(mapped))
