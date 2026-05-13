"""Environment-driven settings for the FemVerse agent.

Values are loaded from `.env` (via `pydantic-settings`) and from real
environment variables. Import the module-level `settings` singleton anywhere
in the codebase:

    from agent.config.settings import settings
    print(settings.model_name)

All fields have sensible defaults so importing this module never crashes;
services that actually require a value (e.g., the Memory Bank factory)
validate at construction time.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide configuration for the FemVerse ADK app."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- LLM ---------------------------------------------------------------
    model_name: str = Field(
        default="gemini-2.5-flash",
        description="Gemini model used by every agent unless overridden in YAML.",
    )

    # ---- Gemini access -----------------------------------------------------
    google_genai_use_vertexai: bool = Field(
        default=False,
        description="Set true to route Gemini calls through Vertex AI.",
    )
    google_api_key: str | None = Field(
        default=None,
        description="Google AI Studio API key (used when not on Vertex).",
    )
    google_cloud_project: str | None = Field(
        default=None,
        description="GCP project id (required for Vertex + Memory Bank).",
    )
    google_cloud_location: str | None = Field(
        default=None,
        description="GCP location, e.g. 'us-central1'.",
    )

    # ---- Memory Bank -------------------------------------------------------
    agent_engine_id: str | None = Field(
        default=None,
        description=(
            "Numeric id of the Vertex Agent Engine instance hosting the "
            "Memory Bank. Required to construct VertexAiMemoryBankService."
        ),
    )

    # ---- Session DB --------------------------------------------------------
    session_db_url: str | None = Field(
        default=None,
        description=(
            "SQLAlchemy URL for DatabaseSessionService. When unset, "
            "agent.sessions.service.get_database_url() is invoked."
        ),
    )

    # ---- Convenience -------------------------------------------------------
    @property
    def memory_service_uri(self) -> str | None:
        """ADK-style URI for `--memory_service_uri`, when an engine id is set."""
        if not self.agent_engine_id:
            return None
        return f"agentengine://{self.agent_engine_id}"


settings = Settings()
"""Module-level singleton; import this rather than re-instantiating."""
