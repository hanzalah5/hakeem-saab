"""ADK callbacks for FemVerse.

Three responsibilities:

1. **Prompt injection** — each agent's YAML uses two state placeholders in its
   `instruction` field:
   - ``"{system_prompt?}"`` — the specialist markdown prompt (loaded from disk
     via the prompt loader and appended with memory-extraction guidance).
   - ``"{user_persona?}"`` — the user's Cassandra profile, pre-loaded once per
     session and cached in session state for subsequent turns.

   The ``load_*_prompt`` callbacks below run *before* the agent is invoked and
   write both values into ``callback_context.state``. ADK resolves the
   placeholders at runtime, injecting them silently into the instruction without
   the user ever seeing a tool call.

2. **Memory persistence** — ``save_session_to_memory`` runs *after* an agent
   completes a turn and ships the most recent events to Memory Bank, which
   does its own LLM-driven extraction and server-side deduplication.
   We send the last 5 events (sliding window) rather than the full session
   so the same events are not reprocessed every turn — this matches the
   "Option 1 (Recommended)" pattern from the Memory Bank ADK quickstart.
"""

from __future__ import annotations

import json
import logging
import uuid

from google.adk.agents.callback_context import CallbackContext

from femverse.prompts.loader import load_prompt
from femverse.tools.user_data import fetch_user_persona

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _format_persona(persona: dict | None) -> str:
    """Format a persona dict into a markdown section for the instruction.

    Returns an empty string when persona is None or empty so that the
    ``{user_persona?}`` placeholder resolves to nothing rather than a
    blank section header.
    """
    if not persona:
        return ""

    lines = ["## User Profile (pre-loaded — do not ask the user to repeat this)"]
    for key, value in persona.items():
        if value is not None and value != "" and value != []:
            if isinstance(value, (dict, list)):
                lines.append(f"- {key}: {json.dumps(value, ensure_ascii=False)}")
            else:
                lines.append(f"- {key}: {value}")
    return "\n".join(lines)


async def _fetch_and_cache_persona(callback_context: CallbackContext) -> None:
    """Fetch the user persona from Cassandra and cache it in session state.

    Runs once per session: if ``state["user_persona"]`` is already set (from a
    prior turn in the same session), the Cassandra query is skipped entirely.
    The formatted string is written to ``state["user_persona"]`` so ADK can
    resolve the ``{user_persona?}`` instruction placeholder automatically.

    ``user_id`` resolution order:
    1. ``state["user_id"]`` — set explicitly by the client in initial state.
    2. ``session.user_id``  — the identifier ADK stores at session-creation time
       (from the URL path in ``adk api_server``, or the CLI user in ``adk run``).
    """
    if "user_persona" in callback_context.state:
        return  # Already fetched this session — use the cached value.

    # Try state first; fall back to the ADK session-level user_id.
    user_id: str | None = callback_context.state.get("user_id")
    if not user_id:
        try:
            user_id = callback_context._invocation_context.session.user_id  # noqa: SLF001
        except AttributeError:
            pass

    # Guard: ADK defaults session.user_id to "user" in adk run / adk web.
    # Only proceed if the value is actually a valid UUID — anything else
    # (e.g. "user") would cause a Cassandra type error on the UUID column.
    if user_id:
        try:
            uuid.UUID(user_id)
        except ValueError:
            _logger.debug(
                "user_id=%r is not a valid UUID — skipping persona fetch. "
                "Pass the patient UUID in state['user_id'] to enable it.",
                user_id,
            )
            user_id = None

    persona: dict | None = None

    if user_id:
        try:
            persona = await fetch_user_persona(user_id)
        except Exception:
            _logger.exception("Persona pre-load failed for user_id=%s", user_id)
    else:
        _logger.debug("No valid user_id available; persona will be empty.")

    callback_context.state["user_persona"] = _format_persona(persona)


# ---------------------------------------------------------------------------
# Prompt-injection callbacks (one per agent)
# ---------------------------------------------------------------------------


async def load_menstrual_prompt(callback_context: CallbackContext) -> None:
    """Inject the menstrual specialist prompt and pre-load the user persona."""
    # Base system prompt — same for every user; LRU-cached on disk reads.
    callback_context.state["system_prompt"] = (
        load_prompt("menstrual_system")
        + "\n\n"
        + load_prompt("memory_extraction_guidance")
    )
    # User persona — fetched from Cassandra once per session, then cached.
    await _fetch_and_cache_persona(callback_context)


async def load_pregnancy_prompt(callback_context: CallbackContext) -> None:
    """Inject the pregnancy specialist prompt and pre-load the user persona."""
    # Base system prompt — same for every user; LRU-cached on disk reads.
    callback_context.state["system_prompt"] = (
        load_prompt("pregnancy_system")
        + "\n\n"
        + load_prompt("memory_extraction_guidance")
    )
    # User persona — fetched from Cassandra once per session, then cached.
    await _fetch_and_cache_persona(callback_context)


# ---------------------------------------------------------------------------
# Memory-persistence callback
# ---------------------------------------------------------------------------


_MEMORY_EVENT_WINDOW = 5
"""Number of trailing session events shipped to Memory Bank per turn.

The Memory Bank ADK quickstart recommends incremental event submission
("Option 1") over re-sending the full session each turn, which would
make server-side dedup work grow O(turns^2).
"""


async def save_session_to_memory(callback_context: CallbackContext) -> None:
    """Persist the most recent events of this turn to Vertex Memory Bank.

    Memory Bank performs its own LLM-driven extraction and deduplication
    server-side. We send a sliding window of the last few events rather
    than the full session so the same events are not re-extracted every
    turn. Failures are logged but never raised — a memory-write hiccup
    should not break the user-facing response.
    """
    try:
        session = callback_context._invocation_context.session  # noqa: SLF001
        events = list(getattr(session, "events", []) or [])
        recent = events[-_MEMORY_EVENT_WINDOW:] if events else []
        if not recent:
            return
        await callback_context.add_events_to_memory(events=recent)
    except Exception:  # noqa: BLE001 — never let memory errors bubble up.
        _logger.exception("Failed to persist events to Memory Bank")
