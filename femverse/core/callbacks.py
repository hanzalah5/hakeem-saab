"""ADK callbacks for FemVerse.

Two responsibilities:

1. **Prompt injection** â€” each agent's YAML uses the state-placeholder
   ``"{system_prompt}"`` for its `instruction` field. The `load_*_prompt`
   callbacks below run *before* the agent is invoked and write the actual
   markdown system prompt (loaded from disk via the prompt loader) into
   ``callback_context.state["system_prompt"]``. ADK then resolves the
   placeholder at runtime.

2. **Memory persistence** â€” `save_session_to_memory` runs *after* an agent
   completes a turn and ships the session to Memory Bank, which does its
   own LLM-driven extraction and server-side deduplication.
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


async def save_session_to_memory(callback_context: CallbackContext) -> None:
    """Persist the current session to Vertex Memory Bank.

    Memory Bank performs its own LLM-driven extraction and deduplication
    server-side, so calling this once per turn is safe and idiomatic.
    Failures are logged but never raised â€” a memory-write hiccup should
    not break the user-facing response.
    """
    try:
        await callback_context.add_session_to_memory()
    except Exception:  # noqa: BLE001 â€” never let memory errors bubble up.
        _logger.exception("Failed to persist session to Memory Bank")
