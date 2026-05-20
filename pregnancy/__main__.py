"""Minimal CLI entry: ``python -m pregnancy``.

Loads the YAML-defined root agent and prints a one-line health summary. Useful
as a smoke test before launching ``adk web pregnancy`` or
``adk api_server .``.

For a real interactive loop, use the official ADK CLI::

    adk run pregnancy
    adk web pregnancy
"""

from __future__ import annotations

import sys
from pathlib import Path

from femverse.core.runtime import load_root_agent

APP_NAME = "pregnancy"
_YAML_PATH = Path(__file__).resolve().parent / "root_agent.yaml"


def main() -> int:
    try:
        agent = load_root_agent(_YAML_PATH)
    except Exception as exc:  # noqa: BLE001
        print(f"[femverse] Failed to load {APP_NAME} root agent: {exc}", file=sys.stderr)
        return 1

    tool_names = ", ".join(getattr(t, "name", "?") for t in (getattr(agent, "tools", []) or [])) or "(none)"
    print(
        f"[femverse] app={APP_NAME} root_agent={agent.name} "
        f"model={getattr(agent, 'model', '?')} tools=[{tool_names}]"
    )
    print(f"[femverse] To chat interactively, run: adk run {APP_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
