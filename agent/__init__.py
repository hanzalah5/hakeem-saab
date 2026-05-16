"""FemVerse OB/GYN agent package.

This module is the entry point ADK discovers when you run::

    adk run agent
    adk web agent
    adk api_server agent

It re-exports `root_agent` (built from `agent/root_agent.yaml`) so the ADK
CLI can find it without any further configuration.

Loading the YAML at import time means the prompt files, tools, and
callback references are validated up front; a broken reference will surface
immediately rather than on the first user turn.
"""

from __future__ import annotations

from agent.core.runtime import APP_NAME, build_runner, load_root_agent
import agent.api  # ensure API middleware/openapi patch runs on import

root_agent = load_root_agent()
"""The FemVerse coordinator agent, discovered by the ADK CLI."""

__all__ = ["root_agent", "build_runner", "APP_NAME"]
