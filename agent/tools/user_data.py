"""Database-backed user context tools.

These functions are exposed to the LLM as ADK FunctionTools (referenced by
fully qualified name in `agent/root_agent.yaml` and the specialist YAMLs).

They are currently **stubs** that return ``None``. Wire them to the real
FemVerse database when integration is ready. The docstrings, type hints,
and intended return shapes are intentionally complete so the LLM can decide
*when* and *how* to call them without further hints.
"""

from __future__ import annotations

from typing import Any


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
    # TODO: wire to FemVerse user database (Postgres / Firestore / etc.)
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
    # TODO: wire to FemVerse logs/timeseries store
    return None
