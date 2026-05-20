"""FemVerse menstrual / gynecology ADK app.

This package is what the ADK CLI discovers when you run::

    adk run menstrual
    adk web menstrual
    adk api_server .

It re-exports ``root_agent`` (built from ``menstrual/root_agent.yaml``) so the
ADK CLI can find it without any further configuration.

Loading the YAML at import time means prompt files, tools, and callback
references are validated up front; a broken reference surfaces immediately
rather than on the first user turn.
"""

from __future__ import annotations

from pathlib import Path

from femverse.core.runtime import load_root_agent

APP_NAME = "menstrual"

_ROOT_AGENT_YAML = Path(__file__).resolve().parent / "root_agent.yaml"

root_agent = load_root_agent(_ROOT_AGENT_YAML)
"""The FemVerse menstrual specialist, discovered by the ADK CLI."""

__all__ = ["root_agent", "APP_NAME"]
