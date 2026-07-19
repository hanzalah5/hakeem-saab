"""ADK callbacks for FemVerse.

Two responsibilities:

1. **Prompt injection** — each agent's YAML ``instruction`` uses these state
   placeholders:
   - ``"{system_prompt?}"`` — the specialist markdown prompt (loaded from disk,
     appended with memory-extraction guidance, and — **only on the opening turn
     of an entry-point session** — the matching entry-point fragment). The
     ``load_*_prompt`` callbacks below build this via ``_compose_system_prompt``.
   - ``"{user_persona?}"`` / ``"{user_profile?}"`` — the durable persona and the
     per-session profile JSON. Populated by the backend at session-creation time
     and resolved from seeded state by ADK; empty string when unseeded.
   - ``"{entry_context?}"`` — why the user opened the chat (tip/alert/story/…),
     seeded by the backend. It is **not** touched here; ADK injects it every turn
     from state, so the entry content stays available for follow-up questions.

   **Entry points — two lifetimes.** The entry *data* (``{entry_context?}``) is
   present on every turn. The entry *opening-behavior* fragment (e.g.
   ``entry_tip``) is appended to ``system_prompt`` **only on the opening turn**
   (before any model output exists), so follow-ups converse normally while still
   seeing the entry content. Chat Now (no ``entry_context``) is unchanged.

2. **Memory persistence** — ``save_session_to_memory`` runs *after* an agent
   completes a turn and ships the most recent events to Memory Bank, which does
   its own LLM-driven extraction and server-side deduplication. We send the last
   5 events (sliding window) rather than the full session so the same events are
   not reprocessed every turn.
"""

from __future__ import annotations

import json
import logging

from google.adk.agents.callback_context import CallbackContext

from femverse.prompts.loader import PromptNotFoundError, load_prompt

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Entry-point helpers
# ---------------------------------------------------------------------------

# entry_context.type -> prompt-fragment stem. Alerts resolve by severity below.
_ENTRY_FRAGMENTS = {
    "tip": "entry_tip",
    "story": "entry_story",
    "health_checker": "entry_health_checker",
}


def _parse_entry_context(state) -> dict:
    """Return the seeded entry_context as a dict (tolerates JSON string or dict)."""
    raw = state.get("entry_context")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


def _entry_fragment_stem(entry: dict) -> str | None:
    """Map an entry_context to its opening-behavior fragment stem, or None."""
    entry_type = str(entry.get("type", "")).strip().lower()
    if not entry_type or entry_type == "chat_now":
        return None
    if entry_type == "alert":
        severity = str(entry.get("severity", "")).strip().lower()
        return "entry_alert_red" if severity == "red" else "entry_alert_yellow"
    return _ENTRY_FRAGMENTS.get(entry_type)


def _render_transcript(value) -> str:
    """Render a seeded call transcript to readable ``Caller:``/``Assistant:`` lines.

    Tolerates the backend's content-events shape (``{"events": [...]}`` or a bare
    list of ``{author, content:{role, parts:[{text}]}}``), a JSON string of either,
    or an already-plain-text transcript. Returns ``""`` when there's nothing usable.
    """
    if not value:
        return ""
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ""
        try:
            value = json.loads(stripped)
        except (ValueError, TypeError):
            return stripped  # already a plain-text transcript
    events = value.get("events") if isinstance(value, dict) else value
    if not isinstance(events, list):
        return str(value).strip()
    lines = []
    for event in events:
        if not isinstance(event, dict):
            continue
        content = event.get("content") or {}
        parts = content.get("parts") or []
        text = " ".join(
            p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text")
        ).strip()
        if not text:
            continue
        role = str(content.get("role") or event.get("author") or "").lower()
        speaker = "Caller" if role in ("user", "caller") else "Assistant"
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines)


def _is_opening_turn(callback_context: CallbackContext) -> bool:
    """True on the session's first agent turn (no prior model output yet).

    On the opening (sentinel) turn only the incoming user event exists; there is
    no event authored by the agent. On later turns prior agent events are present.
    Defaults to False on any error so entry rules never fire spuriously.
    """
    try:
        session = callback_context._invocation_context.session  # noqa: SLF001
        events = getattr(session, "events", []) or []
        return not any(getattr(e, "author", "user") != "user" for e in events)
    except Exception:  # noqa: BLE001
        return False


def _compose_system_prompt(callback_context: CallbackContext, domain: str) -> None:
    """Build ``system_prompt`` for a domain, adding the entry fragment on opening.

    Args:
        domain: prompt stem prefix, e.g. ``"menstrual"`` -> ``menstrual_system.md``.
    """
    # Base system prompt — same for every user; LRU-cached on disk reads.
    parts = [load_prompt(f"{domain}_system"), load_prompt("memory_extraction_guidance")]

    if _is_opening_turn(callback_context):
        stem = _entry_fragment_stem(_parse_entry_context(callback_context.state))
        if stem:
            try:
                parts.append(load_prompt(stem))
            except PromptNotFoundError:
                # Entry type not yet authored — degrade gracefully to base behavior.
                _logger.warning("Entry fragment '%s' not found; using base prompt.", stem)

    # An earlier voice-call transcript (seeded into state by the backend, possibly
    # mid-session via PATCH) is rendered to readable text and injected every turn it
    # is present — so the bot stays aware of the call for the rest of the conversation.
    transcript = _render_transcript(callback_context.state.get("call_transcript"))
    if transcript:
        try:
            parts.append(load_prompt("call_transcript_guidance") + "\n\n" + transcript)
        except PromptNotFoundError:
            parts.append(transcript)

    callback_context.state["system_prompt"] = "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Prompt-injection callbacks (one per agent)
# ---------------------------------------------------------------------------


async def load_menstrual_prompt(callback_context: CallbackContext) -> None:
    """Inject the menstrual specialist system prompt into session state."""
    _compose_system_prompt(callback_context, "menstrual")


async def load_pregnancy_prompt(callback_context: CallbackContext) -> None:
    """Inject the pregnancy specialist system prompt into session state."""
    _compose_system_prompt(callback_context, "pregnancy")


async def load_nutrition_prompt(callback_context: CallbackContext) -> None:
    """Inject the nutrition specialist system prompt into session state."""
    _compose_system_prompt(callback_context, "nutrition")


async def load_period_nutrition_prompt(callback_context: CallbackContext) -> None:
    """Inject the period + nutrition specialist system prompt into session state."""
    _compose_system_prompt(callback_context, "period_nutrition")


async def load_pregnancy_nutrition_prompt(callback_context: CallbackContext) -> None:
    """Inject the pregnancy + nutrition specialist system prompt into session state."""
    _compose_system_prompt(callback_context, "pregnancy_nutrition")


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
