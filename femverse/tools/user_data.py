"""Cassandra-backed user context helpers.

``fetch_user_persona`` is called by the before-agent callbacks in
``femverse.core.callbacks`` to silently pre-load the user's profile into
session state before the first LLM turn. It is not exposed as an LLM tool.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from femverse.cassandra.cassandra_client import get_cassandra_session


logger = logging.getLogger(__name__)


def _decode_persona_payload(payload: Any) -> dict[str, Any] | None:
    if payload is None:
        return None

    if isinstance(payload, dict):
        return payload

    if isinstance(payload, (bytes, bytearray, memoryview)):
        payload = bytes(payload).decode("utf-8")

    if isinstance(payload, str):
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("Cassandra persona payload was not valid JSON.")
            return {"persona_data": payload}

        return decoded if isinstance(decoded, dict) else {"persona_data": decoded}

    return {"persona_data": payload}


def _normalize_user_id(user_id: str) -> Any:
    try:
        return uuid.UUID(user_id)
    except (ValueError, AttributeError, TypeError):
        return user_id


async def fetch_user_persona(user_id: str) -> dict[str, Any] | None:
    """Fetch the user's persona profile from Cassandra.

    Called once per session by the before-agent callback. The result is cached
    in session state under ``"user_persona"`` so subsequent turns skip the
    Cassandra query entirely.

    Args:
        user_id: Stable identifier for the user (e.g. ``"usr_8421"``).

    Returns:
        A dictionary of persona fields when the user exists, otherwise ``None``.
        Expect keys such as ``age``, ``weight_kg``, ``height_cm``,
        ``known_conditions``, ``preferences``, etc.
    """
    client = get_cassandra_session()
    normalized_user_id = _normalize_user_id(user_id)

    try:
        rows = await client.run_query_async(
            "SELECT persona_data FROM user_personas WHERE user_id = %s LIMIT 1",
            (normalized_user_id,),
        )
    except Exception as e:
        logger.exception("Persona lookup query failed: %s", str(e))
        return None

    if not rows:
        return None

    persona = _decode_persona_payload(getattr(rows[0], "persona_data", None))
    return persona if persona is not None else None
