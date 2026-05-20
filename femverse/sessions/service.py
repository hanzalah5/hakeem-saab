"""SQL-backed session persistence for the FemVerse femverse.

ADK separates two persistence layers:

- **Session** (this module) â€” short-term per-conversation events + state,
  read/written every turn.
- **Memory** (`femverse.memory.service`) â€” long-term, cross-session extracted
  facts.

`build_session_service()` is invoked by the runner. It looks for a
SQLAlchemy URL in this order:

1. `SESSION_DB_URL` environment variable (via `femverse.config.settings`).
2. The `get_database_url()` stub below, which raises until you wire it up.

ADK auto-creates the schema on the first call to `DatabaseSessionService`,
so there are no migrations to run.
"""

from __future__ import annotations

from google.adk.sessions import DatabaseSessionService


def get_database_url() -> str:
    """Return the SQLAlchemy connection string for FemVerse session storage.

    **Plug in your SQL database here.** Examples of valid return values:

    - SQLite (dev/local):
        ``"sqlite:///./femverse_sessions.db"``
    - PostgreSQL:
        ``"postgresql+psycopg2://user:pass@host:5432/femverse"``
    - MySQL:
        ``"mysql+pymysql://user:pass@host:3306/femverse"``
    - MS SQL Server:
        ``"mssql+pyodbc://user:pass@host/femverse?driver=ODBC+Driver+17+for+SQL+Server"``

    You may also keep this stub raising and instead set ``SESSION_DB_URL``
    in your ``.env`` file â€” the resolution order in
    :func:`build_session_service` will pick that up first.

    Returns:
        A SQLAlchemy-compatible database URL.

    Raises:
        NotImplementedError: Until the FemVerse session DB is configured.
    """
    from femverse.config.settings import settings

    if settings.session_db_url:
        return settings.session_db_url

    raise NotImplementedError(
        "Configure FemVerse session DB: implement get_database_url() in "
        "agent/sessions/service.py, or set SESSION_DB_URL in .env."
    )


def build_session_service() -> DatabaseSessionService:
    """Construct the `DatabaseSessionService` used by the ADK runner.

    Resolution order for the connection string:

    1. ``settings.session_db_url`` (from the ``SESSION_DB_URL`` env var).
    2. :func:`get_database_url` above.

    Returns:
        A configured `DatabaseSessionService`. The schema is auto-created
        on first use.
    """
    from femverse.config.settings import settings

    db_url = settings.session_db_url or get_database_url()
    return DatabaseSessionService(db_url=db_url)
