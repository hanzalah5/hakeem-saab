"""Database-backed user context tools.

These functions are exposed to the LLM as ADK FunctionTools, referenced by
fully qualified name in each app's ``root_agent.yaml``:

- ``menstrual/root_agent.yaml`` -> ``fetch_user_persona``, ``fetch_period_daily_logs``
- ``pregnancy/root_agent.yaml`` -> ``fetch_user_persona``, ``fetch_pregnancy_daily_logs``

Each function targets its own Cassandra table, so the two apps stay
independent and there is no cross-module fallback logic.
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


def _today_bounds() -> tuple[str, "datetime", "datetime"]:
    """Return (year_month, day_start, day_end) in UTC for the current day."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    year_month = now.strftime("%Y_%m")
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    return year_month, day_start, day_end


def fetch_period_daily_logs(user_id: str) -> list[dict[str, Any]] | None:
    """Fetch the user's recent menstrual / cycle daily logs.

    Use this when the answer depends on **current** menstrual or hormonal
    state that changes over time, such as:

    - Cycle data: cycle day, phase, flow intensity, period start/end dates.
    - Hormonal symptoms: cramps, mood swings, breast tenderness, acne.
    - Cycle-adjacent lifestyle metrics: sleep quality, energy, libido.

    Prefer the most recent entry. Do not call this when the question is
    entirely general (e.g., "what is ovulation?") or unrelated to the user's
    own current cycle.

    Args:
        user_id: Stable identifier for the user.

    Returns:
        A list with the most recent period log entry when one exists for
        today, otherwise ``None``. The exact payload schema is owned by the
        FemVerse backend.
    """
    client = get_cassandra_session()
    normalized_user_id = _normalize_user_id(user_id)
    year_month, day_start, day_end = _today_bounds()

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
    except Exception as exc:
        logger.exception("Period logs lookup failed: %s", exc)
        return None

    if not rows:
        return None

    data = getattr(rows[0], "user_data", None)
    decoded = _decode_persona_payload(data)
    if decoded is None:
        return None
    return [decoded] if isinstance(decoded, dict) else decoded


def fetch_pregnancy_daily_logs(user_id: str) -> list[dict[str, Any]] | None:
    """Fetch the user's recent pregnancy daily logs.

    Use this when the answer depends on **current** pregnancy-related state
    that changes over time, such as:

    - Gestational data: gestational age in weeks / days, trimester.
    - Fetal-monitoring metrics: fetal-movement counts, kick counts.
    - Maternal vitals: blood pressure (systolic / diastolic), fasting
      glucose, weight, hydration.
    - Pregnancy symptoms: nausea, fatigue, swelling, sleep quality.

    Prefer the most recent entry. Do not call this when the question is
    entirely general (e.g., "what foods to avoid during pregnancy?") or
    unrelated to the user's own current pregnancy data.

    Args:
        user_id: Stable identifier for the user.

    Returns:
        A list with the most recent pregnancy log entry when one exists for
        today, otherwise ``None``. The exact payload schema is owned by the
        FemVerse backend.
    """
    client = get_cassandra_session()
    normalized_user_id = _normalize_user_id(user_id)
    year_month, day_start, day_end = _today_bounds()

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
    except Exception as exc:
        logger.exception("Pregnancy logs lookup failed: %s", exc)
        return None

    if not rows:
        return None

    data = getattr(rows[0], "user_data", None)
    decoded = _decode_persona_payload(data)
    if decoded is None:
        return None
    return [decoded] if isinstance(decoded, dict) else decoded
