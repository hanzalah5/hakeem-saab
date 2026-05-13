"""Runner factory for the FemVerse agent.

Wires the YAML-defined root agent together with the SQL-backed
`DatabaseSessionService` and the Vertex `VertexAiMemoryBankService`.

Two usage paths:

1. **`adk web agent` / `adk api_server agent` / `adk run agent`** — the
   ADK CLI discovers `agent.root_agent` (re-exported from
   `agent/__init__.py`) and supplies its own runner. In that path you wire
   memory and sessions via the CLI flags:

   ::

       adk web agent \
         --session_service_uri="$SESSION_DB_URL" \
         --memory_service_uri="agentengine://$AGENT_ENGINE_ID"

2. **Programmatic** (tests, custom servers) — call
   :func:`build_runner` and drive `runner.run_async` yourself. This is
   what `python -m agent` does.
"""

from __future__ import annotations

from pathlib import Path

from google.adk.agents import config_agent_utils
from google.adk.agents.base_agent import BaseAgent
from google.adk.runners import Runner

from agent.config.settings import settings
from agent.memory.service import build_memory_service
from agent.sessions.service import build_session_service

APP_NAME = "femverse"

_ROOT_AGENT_YAML = Path(__file__).resolve().parent.parent / "root_agent.yaml"


def load_root_agent() -> BaseAgent:
    """Instantiate the root agent from `agent/root_agent.yaml`.

    Sub-agents and tool/callback references are resolved transitively by
    `config_agent_utils.from_config`.
    """
    return config_agent_utils.from_config(str(_ROOT_AGENT_YAML))


def build_runner() -> Runner:
    """Construct a fully wired ADK `Runner` for the FemVerse agent.

    The runner is configured with:

    - The YAML-defined `femverse_coordinator` root agent (with its two
      specialists already attached via `sub_agents`).
    - A `DatabaseSessionService` backed by your SQL DB.
    - A `VertexAiMemoryBankService` backed by the Agent Engine instance
      referenced by `AGENT_ENGINE_ID`.

    Returns:
        A ready-to-use `Runner`. Use `runner.run_async(...)` to drive it.
    """
    return Runner(
        app_name=APP_NAME,
        agent=load_root_agent(),
        session_service=build_session_service(),
        memory_service=build_memory_service(),
    )


__all__ = ["APP_NAME", "build_runner", "load_root_agent", "settings"]
