# FemVerse OB/GYN Assistant

A modular, ADK-based conversational assistant for a female healthcare platform. FemVerse plays the role of a senior OB/GYN, shipped as **two independent single-agent apps** — one for menstrual / gynecology care and one for pregnancy / prenatal care.

This repository replaces the legacy `legacy_Imp.py` single-file Streamlit prototype with a clean Google [Agent Development Kit (ADK)](https://adk.dev/) implementation.

## Architecture

```
                       Frontend
                          |
              appName = "menstrual" or "pregnancy"
              userId  = <patient UUID>
                          |
                          v
              +-------------------------+
              |     adk api_server      |  (single process, autodiscovers both apps)
              +-----------+-------------+
                          |
        +-----------------+------------------+
        |                                    |
+-------v---------+                +---------v--------+
| menstrual_      |                | pregnancy_       |
| specialist      |                | specialist       |
|                 |                |                  |
| - cycle, PCOS,  |                | - gestation,     |
|   hormones,     |                |   prenatal,      |
|   contraception |                |   labor prep,    |
| - fertility     |                |   postpartum,    |
|   tracking      |                |   lactation      |
+-------+---------+                +---------+--------+
        |                                    |
        |   before_agent_callback            |
        |   (persona pre-loaded silently)    |
        |                                    |
        +----------------+-------------------+
                         v
              +-------------------+
              |     Cassandra     |
              |  (user_personas)  |
              +-------------------+
              |   DatabaseSessionService   (your SQL DB)
              |   VertexAiMemoryBankService (Agent Engine)
```

The two apps are independent at runtime: sessions and Memory Bank state are siloed per `app_name`. They share the `femverse/` Python package for prompts, callbacks, settings, and service factories — but neither app can transfer control to the other. The frontend chooses which app to call.

| Concern            | Location                                                          |
|--------------------|-------------------------------------------------------------------|
| Menstrual app      | `menstrual/root_agent.yaml`, `menstrual/__init__.py`              |
| Pregnancy app      | `pregnancy/root_agent.yaml`, `pregnancy/__init__.py`              |
| Prompts            | `femverse/prompts/*.md` (loaded via `femverse.prompts.loader`)    |
| User context       | `femverse/tools/user_data.py` (called by callbacks, not the LLM) |
| Memory             | `femverse/memory/service.py` + `femverse/memory/topics.yaml`      |
| Sessions           | `femverse/sessions/service.py` (SQL URL via `SESSION_DB_URL`)     |
| Callbacks          | `femverse/core/callbacks.py`                                      |
| Runtime wiring     | `femverse/core/runtime.py`                                        |
| Settings           | `femverse/config/settings.py`                                     |
| Cassandra client   | `femverse/cassandra/`                                             |

## User context — how persona is delivered

The user's Cassandra profile is fetched **once per session** inside the `before_agent_callback`, before the LLM ever speaks. It is injected silently into the agent's instruction via the `{user_persona?}` state placeholder — the user never sees a tool call.

```
New session created  (userId = patient UUID in URL path)
  → before_agent_callback fires
      1. state["user_persona"] not set yet
      2. Read user_id from session.user_id (or state["user_id"] override)
      3. Validate it is a real UUID (skip silently if not — e.g. ADK's "user" default)
      4. await fetch_user_persona(user_id)  →  one Cassandra query
      5. Format result into "## User Profile\n- age: …\n…"
      6. Write to state["user_persona"]  ←  cached for all subsequent turns
  → LLM receives full user context from turn 1, no tool call made

Subsequent turns  →  state["user_persona"] already set  →  Cassandra skipped
```

**Passing the patient UUID:** use the real UUID as the `userId` in the session-creation URL:

```
POST /apps/menstrual/users/6576c2a2-3d66-4753-8aaa-9a2ea8ab249e/sessions
```

ADK stores this as `session.user_id` and the callback picks it up automatically.
Alternatively, set `state["user_id"]` in the initial session state body.

## Quick start

1. **Install dependencies**
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. **Configure environment** — copy `.env.example` to `.env` and fill in:
   - `MODEL_NAME` — Gemini model (default: `gemini-2.5-flash`)
   - `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GOOGLE_APPLICATION_CREDENTIALS` — Vertex AI access
   - `AGENT_ENGINE_ID` — Vertex Agent Engine instance for Memory Bank
   - `SESSION_DB_URL` — SQLAlchemy URL for session persistence (see below)
   - `CASSANDRA_HOST`, `CASSANDRA_PORT`, `CASSANDRA_USERNAME`, `CASSANDRA_PASSWORD`, `CASSANDRA_KEYSPACE`

3. **Plug in your SQL DB** for session persistence — set `SESSION_DB_URL` in `.env`, or implement `get_database_url()` in `femverse/sessions/service.py`. Example values:
   ```
   sqlite+aiosqlite:///./femverse_sessions.db   # local dev
   postgresql+asyncpg://user:pass@host:5432/femverse
   ```

4. **Run**

   ```powershell
   # Both apps from a single ADK API server (recommended for production)
   adk api_server . --session_service_uri="$env:SESSION_DB_URL" `
                    --memory_service_uri="agentengine://$env:AGENT_ENGINE_ID"

   # Single app — interactive terminal
   adk run menstrual
   adk run pregnancy

   # Single app — browser UI
   adk web menstrual
   adk web pregnancy
   ```

   Verify both apps loaded:
   ```powershell
   curl http://localhost:8000/list-apps   # -> ["menstrual","pregnancy"]
   ```

5. **Smoke test without the ADK CLI**
   ```powershell
   python -m menstrual
   python -m pregnancy
   ```
   Prints a single summary line and exits 0 when the YAML, prompts, and callbacks all resolve cleanly.

## Memory model

Both apps use [Vertex Memory Bank](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/memory-bank/overview) with four extraction categories defined in [`femverse/memory/topics.yaml`](femverse/memory/topics.yaml):

1. **Health Facts** — medical history, symptoms, cycle / gestational data, OB/GYN metrics.
2. **Nutritional Facts** — dietary habits, allergies, supplements, hydration.
3. **User Personal Details** — age, weight, height, ethnicity, parity.
4. **User Preferences** — tone, language, lifestyle, content sensitivities.

Memory is **retrieved on demand** via the `load_memory` built-in tool (token-efficient — not preloaded every turn) and **persisted after each turn** via the `after_agent_callback` using a 5-event sliding window.

Memory Bank state is siloed per `app_name`. Static user profile data that should be available regardless of which app the user opens lives in Cassandra and is pre-loaded via the callback.

## Session model

`DatabaseSessionService` is wired through `femverse/sessions/service.py::build_session_service()`. Plug in any SQLAlchemy-supported backend. Sessions survive process restarts so mid-flow conversations don't reset on redeploy. Sessions are siloed per `app_name`.

## Project layout

```
hakeem-saab/
  femverse/                       # shared library (no agent definitions live here)
    cassandra/                    # Cassandra client
    config/settings.py            # pydantic-settings env loader
    core/
      callbacks.py                # prompt-injection + persona pre-load + memory-persistence
      runtime.py                  # build_runner(app_name=..., yaml_path=...)
    memory/                       # Memory Bank factory + topics.yaml
    prompts/                      # externalized .md system prompts
    sessions/                     # DatabaseSessionService factory
    tools/
      user_data.py                # fetch_user_persona (called by callbacks)
  menstrual/                      # ADK app -> app_name = "menstrual"
    root_agent.yaml
    __init__.py
    __main__.py                   # python -m menstrual smoke test
  pregnancy/                      # ADK app -> app_name = "pregnancy"
    root_agent.yaml
    __init__.py
    __main__.py
  tests/
  requirements.txt
```
