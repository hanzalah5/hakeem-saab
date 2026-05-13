"""Minimal CLI entry: ``python -m agent``.

Spins up the fully wired runner (root agent + Memory Bank + SQL sessions)
and prints a one-line health summary. Useful as a smoke test before
launching ``adk web agent``.

For a real interactive loop, use the official ADK CLI:

    adk run agent
    adk web agent
    adk api_server agent
"""

from __future__ import annotations

import sys

from agent.core.runtime import APP_NAME, load_root_agent


def main() -> int:
    try:
        agent = load_root_agent()
    except Exception as exc:  # noqa: BLE001
        print(f"[femverse] Failed to load root agent: {exc}", file=sys.stderr)
        return 1

    sub_agents = getattr(agent, "sub_agents", []) or []
    sub_names = ", ".join(getattr(sa, "name", "?") for sa in sub_agents) or "(none)"
    print(
        f"[femverse] app={APP_NAME} root_agent={agent.name} "
        f"model={getattr(agent, 'model', '?')} sub_agents=[{sub_names}]"
    )
    print("[femverse] To chat interactively, run: adk run agent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
