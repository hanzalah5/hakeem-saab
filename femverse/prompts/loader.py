"""On-disk markdown prompt loader.

Keeps system instructions out of YAML and Python source so prompt engineering
can iterate without code changes. Cached via `lru_cache` so repeated reads
during a long-running process are free.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent


class PromptNotFoundError(FileNotFoundError):
    """Raised when a requested prompt stem cannot be resolved on disk."""


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    """Load a markdown prompt by stem (no extension).

    Args:
        name: File stem inside `agent/prompts/`, e.g. ``"menstrual_system"``.

    Returns:
        The trimmed contents of ``agent/prompts/<name>.md``.

    Raises:
        PromptNotFoundError: If no matching ``.md`` file exists.
    """
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise PromptNotFoundError(
            f"Prompt '{name}' not found at {path}. "
            f"Available: {sorted(p.stem for p in _PROMPTS_DIR.glob('*.md'))}"
        )
    return path.read_text(encoding="utf-8").strip()


def clear_cache() -> None:
    """Drop cached prompt contents (useful in tests and hot-reload scenarios)."""
    load_prompt.cache_clear()
