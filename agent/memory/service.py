"""Vertex AI Memory Bank factory.

Builds a `VertexAiMemoryBankService` from the env-driven settings. Keep this
factory small — Memory Bank topic provisioning lives outside the agent code
(see `agent/memory/topics.yaml` for the source of truth and provision it on
the Agent Engine instance via the Vertex Memory Bank console or API).
"""

from __future__ import annotations

from google.adk.memory import VertexAiMemoryBankService

from agent.config.settings import settings


class MemoryConfigError(RuntimeError):
    """Raised when required Memory Bank settings are missing."""


def build_memory_service() -> VertexAiMemoryBankService:
    """Construct the shared `VertexAiMemoryBankService` for the runner.

    Reads `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and
    `AGENT_ENGINE_ID` from settings. All three are required.

    Returns:
        A configured `VertexAiMemoryBankService` instance.

    Raises:
        MemoryConfigError: If any required setting is missing.
    """
    missing = [
        name
        for name, value in (
            ("GOOGLE_CLOUD_PROJECT", settings.google_cloud_project),
            ("GOOGLE_CLOUD_LOCATION", settings.google_cloud_location),
            ("AGENT_ENGINE_ID", settings.agent_engine_id),
        )
        if not value
    ]
    if missing:
        raise MemoryConfigError(
            "Cannot build VertexAiMemoryBankService — missing env vars: "
            + ", ".join(missing)
        )

    return VertexAiMemoryBankService(
        project=settings.google_cloud_project,
        location=settings.google_cloud_location,
        agent_engine_id=settings.agent_engine_id,
    )
