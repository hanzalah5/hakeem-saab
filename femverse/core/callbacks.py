"""ADK callbacks for FemVerse.

Two responsibilities:

1. **Prompt injection** -- each agent's YAML uses the state-placeholder
   ``"{system_prompt?}"`` for its `instruction` field. The `load_*_prompt`
   callbacks below run *before* the agent is invoked and write the actual
   markdown system prompt (loaded from disk via the prompt loader) into
   ``callback_context.state["system_prompt"]``. ADK then resolves the
   placeholder at runtime.

2. **Memory persistence** -- `save_session_to_memory` runs *after* an agent
   completes a turn and ships the most recent events to Memory Bank, which
   does its own LLM-driven extraction and server-side deduplication.
   We send the last 5 events (sliding window) rather than the full session
   so the same events aren't reprocessed every turn -- this matches the
   "Option 1 (Recommended)" pattern from the Memory Bank ADK quickstart.
"""

from __future__ import annotations

import logging

from google.adk.agents.callback_context import CallbackContext

from femverse.prompts.loader import load_prompt

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt-injection callbacks (one per agent)
# ---------------------------------------------------------------------------


async def load_menstrual_prompt(callback_context: CallbackContext) -> None:
    """Inject the menstrual specialist prompt + memory-extraction guidance."""
    callback_context.state["system_prompt"] = (
        load_prompt("menstrual_system")
        + "\n\n"
        + load_prompt("memory_extraction_guidance")
    )


async def load_pregnancy_prompt(callback_context: CallbackContext) -> None:
    """Inject the pregnancy specialist prompt + memory-extraction guidance."""
    callback_context.state["system_prompt"] = (
        load_prompt("pregnancy_system")
        + "\n\n"
        + load_prompt("memory_extraction_guidance")
    )


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
    turn. Failures are logged but never raised -- a memory-write hiccup
    should not break the user-facing response.
    """
    try:
        session = callback_context._invocation_context.session  # noqa: SLF001
        events = list(getattr(session, "events", []) or [])
        recent = events[-_MEMORY_EVENT_WINDOW:] if events else []
        if not recent:
            return
        await callback_context.add_events_to_memory(events=recent)
    except Exception:  # noqa: BLE001 -- never let memory errors bubble up.
        _logger.exception("Failed to persist events to Memory Bank")
