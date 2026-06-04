"""Runner factory shared by every FemVerse app.

Each app (``menstrual/``, ``pregnancy/``, ...) ships a single ``root_agent.yaml``
plus a tiny ``__init__.py`` that calls :func:`load_root_agent` to expose
``root_agent``. The ADK CLI then discovers the app by folder name and supplies
its own runner; in that path you wire memory and sessions via CLI flags:

::

    adk api_server . \
      --session_service_uri="$SESSION_DB_URL" \
      --memory_service_uri="agentengine://$AGENT_ENGINE_ID"

For programmatic use (tests, custom servers, ``python -m <app>`` smoke tests),
call :func:`build_runner` with the app's name and YAML path and drive
``runner.run_async`` yourself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from google.adk.agents import config_agent_utils
from google.adk.agents.base_agent import BaseAgent
from google.adk.runners import Runner

from femverse.config.settings import settings
from femverse.memory.service import build_memory_service
from femverse.sessions.service import build_session_service

PathLike = Union[str, Path]


def load_root_agent(yaml_path: PathLike) -> BaseAgent:
    """Instantiate a root agent from its ``root_agent.yaml``.

    Tool and callback references inside the YAML are resolved by
    ``config_agent_utils.from_config``.

    Args:
        yaml_path: Absolute or workspace-relative path to the app's
            ``root_agent.yaml`` file.
    """
    return config_agent_utils.from_config(str(yaml_path))


def build_runner(*, app_name: str, yaml_path: PathLike) -> Runner:
    """Construct a fully wired ADK ``Runner`` for a single FemVerse app.

    The runner is configured with:

    - The YAML-defined root agent at ``yaml_path``.
    - A ``DatabaseSessionService`` backed by the SQL DB at ``SESSION_DB_URL``.
    - A ``VertexAiMemoryBankService`` backed by the Agent Engine instance
      referenced by ``AGENT_ENGINE_ID``.

    Sessions and Memory Bank state are siloed per ``app_name``, which keeps the
    two FemVerse apps independent at runtime.

    Args:
        app_name: ADK app identifier. Should match the app's folder name
            (``"menstrual"`` or ``"pregnancy"``) so that programmatic usage and
            the ``adk api_server`` autodiscovered names stay in sync.
        yaml_path: Path to the app's ``root_agent.yaml``.

    Returns:
        A ready-to-use ``Runner``. Use ``runner.run_async(...)`` to drive it.
    """
    return Runner(
        app_name=app_name,
        agent=load_root_agent(yaml_path),
        session_service=build_session_service(),
        memory_service=build_memory_service(),
    )


__all__ = ["build_runner", "load_root_agent", "settings"]
