"""FemVerse pregnancy / prenatal ADK app.

This package is what the ADK CLI discovers when you run::

    adk run pregnancy
    adk web pregnancy
    adk api_server .

It re-exports ``root_agent`` (built from ``pregnancy/root_agent.yaml``) so the
ADK CLI can find it without any further configuration.

At import time this module:
1. Validates the YAML, prompt files, and callback references up front so
   broken references surface immediately rather than on the first user turn.
2. Establishes the Cassandra connection eagerly so the TCP handshake and auth
   are already done before the first session callback fires.
"""

from __future__ import annotations

from pathlib import Path

from femverse.cassandra.cassandra_client import get_cassandra_session
from femverse.core.runtime import load_root_agent

APP_NAME = "pregnancy"

_ROOT_AGENT_YAML = Path(__file__).resolve().parent / "root_agent.yaml"

root_agent = load_root_agent(_ROOT_AGENT_YAML)
"""The FemVerse pregnancy specialist, discovered by the ADK CLI."""

# Establish the Cassandra connection now so the first session callback only
# pays for the SELECT query, not the connection setup.
get_cassandra_session()

__all__ = ["root_agent", "APP_NAME"]
