"""Database-backed user context tools.

These functions are exposed to the LLM as ADK FunctionTools (referenced by
fully qualified name in `agent/root_agent.yaml` and the specialist YAMLs).

They are currently **stubs** that return ``None``. Wire them to the real
FemVerse database when integration is ready. The docstrings, type hints,
and intended return shapes are intentionally complete so the LLM can decide
*when* and *how* to call them without further hints.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from agent.cassandra.cassandra_client import get_cassandra_session


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


def fetch_user_persona(user_id: str) -> dict[str, Any] | None:
    """Fetch the user's persona profile from the FemVerse database.

    Call this when you need static or slow-changing attributes about the user
    that are not present in the current session, such as:

    - Demographics: age, weight, height, ethnicity, location.
    - Reproductive history: parity, prior pregnancies, contraception, TTC
      status, fertility plans.
    - Known conditions: PCOS, endometriosis, thyroid disorders, hypertension,
      gestational diabetes history, allergies.
    - Communication preferences: preferred language, response tone,
      sensitivity flags (e.g., avoid graphic medical imagery).

    Typical usage: call once near the start of a conversation, then rely on
    the returned dictionary for the rest of the session. Do not poll it on
    every turn.

    Args:
        user_id: Stable identifier for the user (for example, ``"usr_8421"``).

    Returns:
        A dictionary of persona fields when the user exists, otherwise
        ``None``. The exact schema is owned by the FemVerse backend; expect
        keys such as ``age``, ``weight_kg``, ``height_cm``, ``known_conditions``,
        ``preferences``, etc.
    """
    client = get_cassandra_session()
    normalized_user_id = _normalize_user_id(user_id)

    try:
        rows = client.run_query(
            "SELECT persona_data FROM user_personas WHERE user_id = %s LIMIT 1",
            (normalized_user_id,),
        )
    except Exception as e:
        logger.exception("Persona lookup query failed. : %s", str(e))
        return None

    if not rows:
        return None

    persona = _decode_persona_payload(getattr(rows[0], "persona_data", None))
    if persona is not None:
        return persona

    return None


def fetch_daily_logs(user_id: str) -> list[dict[str, Any]] | None:
    """Fetch the user's recent daily health and activity logs.

    Call this when the answer depends on **current** state that changes over
    time, such as:

    - Cycle data: cycle day, phase, flow intensity, period start/end dates.
    - Pregnancy data: gestational age, fetal-movement counts, BP readings,
      glucose readings.
    - Symptoms: cramps, nausea, headache, mood swings, fatigue, sleep quality.
    - Lifestyle metrics: water intake, exercise, stress level.

    Prefer the most recent entries. Do not call this when the user's
    question is entirely general (e.g., "what is ovulation?").

    Args:
        user_id: Stable identifier for the user.

    Returns:
        A list of log entries ordered most-recent-first when logs exist,
        otherwise ``None``. The exact schema is owned by the FemVerse
        backend; expect each entry to carry a timestamp plus a domain
        payload (cycle, pregnancy, symptoms, lifestyle).
    """
    from datetime import datetime, timezone
    
    client = get_cassandra_session()
    normalized_user_id = _normalize_user_id(user_id)
    
    # Get current UTC time and format date/time bounds
    now = datetime.now(timezone.utc)
    year_month = now.strftime("%Y_%m")
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    # Try period_llm_response_history first
    try:
        rows = client.run_query(
            """
            SELECT user_data
            FROM period_llm_response_history
            WHERE user_id = %s
              AND year_month = %s
              AND generated_at >= %s
              AND generated_at <= %s
            LIMIT 1
            """,
            (normalized_user_id, year_month, day_start, day_end),
        )
        
        if rows:
            data = getattr(rows[0], "user_data", None)
            decoded = _decode_persona_payload(data)
            if decoded is not None:
                return [decoded] if isinstance(decoded, dict) else decoded
    except Exception as exc:
        logger.debug("Period logs lookup failed; trying pregnancy records.", exc_info=True)
    
    # Fall back to pregnancy_llm_response_history
    try:
        rows = client.run_query(
            """
            SELECT user_data
            FROM pregnancy_llm_response_history
            WHERE user_id = %s
              AND year_month = %s
              AND generated_at >= %s
              AND generated_at <= %s
            LIMIT 1
            """,
            (normalized_user_id, year_month, day_start, day_end),
        )
        
        if rows:
            data = getattr(rows[0], "user_data", None)
            decoded = _decode_persona_payload(data)
            if decoded is not None:
                return [decoded] if isinstance(decoded, dict) else decoded
    except Exception as exc:
        logger.debug("Pregnancy logs lookup failed.", exc_info=True)
    
    return None
