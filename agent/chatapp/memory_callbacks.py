from google.adk.agents.callback_context import CallbackContext


async def auto_save_session_to_memory_callback(
    callback_context: CallbackContext,
) -> None:
    """Persist the latest turn to Memory Bank for long-term recall.

    Sends only the last user message + agent reply via
    `add_events_to_memory` rather than re-ingesting the full session each
    turn. Memory Bank handles extraction and consolidation under the
    configured managed topics (USER_PERSONAL_INFO, USER_PREFERENCES,
    KEY_CONVERSATION_DETAILS, EXPLICIT_INSTRUCTIONS).
    """
    events = callback_context.session.events
    if not events:
        return
    await callback_context.add_events_to_memory(events=events[-2:])
