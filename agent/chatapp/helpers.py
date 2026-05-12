from google.adk.agents.callback_context import CallbackContext
import json
from pathlib import Path
from typing import Any

CHATAPP_DIR = Path(__file__).parent


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



async def gt_persona_dailylogs(
    callback_context: CallbackContext,
) -> None:
    """Preload persona + daily logs into session state for personalization."""
    callback_context.state["persona_dailylogs"] = get_persona_dailylogs_tool(
        detail_level="summary",
        include_raw=False,
    )


def get_persona_dailylogs_tool(
    detail_level: str = "summary",
    include_raw: bool = False,
) -> dict[str, Any]:
    """Get user persona and cycle logs for personalized guidance.

    Use this tool when you need user-specific menstrual, lifestyle, or symptom
    context before giving recommendations.

    Args:
        detail_level: One of:
            - "summary": concise, token-efficient personalization context
            - "full": richer context with larger text fields
        include_raw: If true, includes raw `persona` and `dailylogs` payloads.
            Keep false for normal chat responses to reduce token usage.

    Returns:
        dict: Structured result with a stable shape:
            - success:
              {
                "status": "success",
                "source": {"persona_version": "...", "last_updated": "..."},
                "snapshot": {
                    "age": int | None,
                    "cycle_day": int | None,
                    "cycle_phase": str | None,
                    "trying_to_conceive": bool | None,
                    "key_symptoms": list[str],
                    "mood_signals": list[str],
                    "diet_type": str | None,
                    "supplements": str | None,
                    "active_flags": list[str]
                },
                "context": str,
                "raw": {"persona": {...}, "dailylogs": {...}}  # optional
              }
            - error:
              {"status": "error", "error_message": "..."}
    """
    detail_level_normalized = detail_level.strip().lower()
    if detail_level_normalized not in {"summary", "full"}:
        return {
            "status": "error",
            "error_message": "Invalid detail_level. Use 'summary' or 'full'.",
        }

    try:
        dailylogs_path = Path(__file__).with_name("dailylogs.json")
        persona_path = Path(__file__).with_name("persona.json")

        with dailylogs_path.open("r", encoding="utf-8") as f:
            dailylogs = json.load(f)
        with persona_path.open("r", encoding="utf-8") as f:
            persona = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "error", "error_message": f"Data read failed: {exc}"}

    cycle_data = dailylogs.get("cycle_data", {})
    user_logged_data = dailylogs.get("user_logged_data", {})
    active_flags = [
        flag.get("signal", "")
        for flag in persona.get("health_watchlist", {}).get("active_flags", [])
        if flag.get("signal")
    ]

    snapshot = {
        "age": dailylogs.get("age") or persona.get("identity_baseline", {}).get("age"),
        "cycle_day": cycle_data.get("current_cycle_day"),
        "cycle_phase": cycle_data.get("current_cycle_phase"),
        "trying_to_conceive": dailylogs.get("try_to_conceive", {}).get("trying_to_conceive"),
        "key_symptoms": user_logged_data.get("symptoms", []),
        "mood_signals": user_logged_data.get("moods", []),
        "diet_type": user_logged_data.get("diet_type"),
        "supplements": user_logged_data.get("supplements"),
        "active_flags": active_flags,
    }

    summary_parts = [
        f"Cycle day {snapshot['cycle_day']} ({snapshot['cycle_phase']})"
        if snapshot["cycle_day"] is not None and snapshot["cycle_phase"]
        else "Cycle timing unavailable",
        "Symptoms: " + ", ".join(snapshot["key_symptoms"]) if snapshot["key_symptoms"] else "Symptoms not logged",
        "Mood: " + ", ".join(snapshot["mood_signals"]) if snapshot["mood_signals"] else "Mood not logged",
        f"Diet: {snapshot['diet_type']}" if snapshot["diet_type"] else "Diet not logged",
    ]
    if detail_level_normalized == "full":
        clinician_summary = persona.get("clinician_summary")
        if clinician_summary:
            summary_parts.append(f"Clinician summary: {clinician_summary}")

    result: dict[str, Any] = {
        "status": "success",
        "source": {
            "persona_version": persona.get("persona_version"),
            "last_updated": persona.get("last_updated"),
        },
        "snapshot": snapshot,
        "context": " | ".join(summary_parts),
    }

    if include_raw:
        result["raw"] = {"persona": persona, "dailylogs": dailylogs}

    return result