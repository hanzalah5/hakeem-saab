# FemVerse OB/GYN Assistant

A modular, ADK-based conversational assistant for a female healthcare platform. FemVerse plays the role of a senior OB/GYN and dietitian, shipped as **three independent single-agent apps** — one for menstrual / gynecology care, one for pregnancy / prenatal care, and one for nutrition / dietary health.

This repository replaces the legacy `legacy_Imp.py` single-file Streamlit prototype with a clean Google [Agent Development Kit (ADK)](https://adk.dev/) implementation.

## Architecture

```
                            Frontend
                               |
        appName = "menstrual" | "pregnancy" | "nutrition"
        userId  = <patient UUID>
                               |
                               v
                 +-------------------------+
                 |     adk api_server      |  (single process, autodiscovers all apps)
                 +-----------+-------------+
                             |
     +-----------------------+-----------------------+
     |                       |                       |
+----v---------+    +--------v-------+    +----------v------+
| menstrual_   |    | pregnancy_     |    | nutrition_      |
| specialist   |    | specialist     |    | specialist      |
|              |    |                |    |                 |
| - cycle,     |    | - gestation,   |    | - calorie/macro |
|   PCOS,      |    |   prenatal,    |    |   targets       |
|   hormones,  |    |   labor prep,  |    | - allergies,    |
|   contracep. |    |   postpartum,  |    |   preferences   |
| - fertility  |    |   lactation    |    | - life-stage    |
|   tracking   |    |                |    |   nutrition     |
+----+---------+    +--------+-------+    +----------+------+
     |                       |                       |
     +-----------------------+-----------------------+
                             v
              |   DatabaseSessionService   (your SQL DB)
              |   VertexAiMemoryBankService (Agent Engine)

  Persona is pre-seeded into session state by the backend at
  session creation ({user_persona?}); the chatbot itself does
  not connect to any user-profile database.
```

The three apps are independent at runtime: sessions and Memory Bank state are siloed per `app_name`. They share the `femverse/` Python package for prompts, callbacks, settings, and service factories — but no app can transfer control to another. The frontend chooses which app to call.

| Concern            | Location                                                          |
|--------------------|-------------------------------------------------------------------|
| Menstrual app      | `menstrual/root_agent.yaml`, `menstrual/__init__.py`              |
| Pregnancy app      | `pregnancy/root_agent.yaml`, `pregnancy/__init__.py`              |
| Nutrition app      | `nutrition/root_agent.yaml`, `nutrition/__init__.py`              |
| Prompts            | `femverse/prompts/*.md` (loaded via `femverse.prompts.loader`)    |
| Memory             | `femverse/memory/service.py` + `femverse/memory/topics.yaml`      |
| Sessions           | `femverse/sessions/service.py` (SQL URL via `SESSION_DB_URL`)     |
| Callbacks          | `femverse/core/callbacks.py`                                      |
| Runtime wiring     | `femverse/core/runtime.py`                                        |
| Settings           | `femverse/config/settings.py`                                     |

## User context — how persona is delivered

The chatbot does **not** fetch the user profile itself. The backend reads the
user's persona from its own database (Cassandra) and **pre-seeds it into session
state** at session-creation time, under the `user_persona` key. ADK then resolves
the `{user_persona?}` placeholder in the agent instruction from that seeded state
automatically — the user never sees a tool call, and the chatbot never connects to
a user-profile database.

```
Backend (on "open chat"):
  1. Fetch persona from Cassandra for the user
  2. Format it into "## User Profile\n- age: …\n…"
  3. Create the ADK session with the persona pre-seeded:
       POST /apps/menstrual/users/{uuid}/sessions
            { "state": { "user_persona": "## User Profile\n- age: …" } }

Chatbot (every turn):
  → before_agent_callback injects only the system prompt
  → ADK resolves {user_persona?} from the seeded state
  → LLM receives full user context from turn 1
```

When no persona is seeded, the optional `{user_persona?}` placeholder resolves to
an empty string and the agent still responds normally.

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
   # All apps from a single ADK API server (recommended for production)
   adk api_server . --session_service_uri="$env:SESSION_DB_URL" `
                    --memory_service_uri="agentengine://$env:AGENT_ENGINE_ID"

   # Single app — interactive terminal
   adk run menstrual
   adk run pregnancy
   adk run nutrition

   # Single app — browser UI
   adk web menstrual
   adk web pregnancy
   adk web nutrition
   ```

   Verify the apps loaded:
   ```powershell
   curl http://localhost:8000/list-apps   # -> ["menstrual","nutrition","pregnancy"]
   ```

5. **Smoke test without the ADK CLI**
   ```powershell
   python -m menstrual
   python -m pregnancy
   python -m nutrition
   ```
   Prints a single summary line and exits 0 when the YAML, prompts, and callbacks all resolve cleanly.

## Memory model

All apps use [Vertex Memory Bank](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/memory-bank/overview) with four extraction categories defined in [`femverse/memory/topics.yaml`](femverse/memory/topics.yaml):

1. **Health Facts** — medical history, symptoms, cycle / gestational data, OB/GYN metrics.
2. **Nutritional Facts** — dietary habits, allergies, supplements, hydration.
3. **User Personal Details** — age, weight, height, ethnicity, parity.
4. **User Preferences** — tone, language, lifestyle, content sensitivities.

Memory is **retrieved on demand** via the `load_memory` built-in tool (token-efficient — not preloaded every turn) and **persisted after each turn** via the `after_agent_callback` using a 5-event sliding window.

Memory Bank state is siloed per `app_name`. Static user profile data is owned by the backend and pre-seeded into session state at session creation (see "User context" above).

## Session model

`DatabaseSessionService` is wired through `femverse/sessions/service.py::build_session_service()`. Plug in any SQLAlchemy-supported backend. Sessions survive process restarts so mid-flow conversations don't reset on redeploy. Sessions are siloed per `app_name`.

## Project layout

```
hakeem-saab/
  femverse/                       # shared library (no agent definitions live here)
    config/settings.py            # pydantic-settings env loader
    core/
      callbacks.py                # system-prompt injection + memory-persistence
      runtime.py                  # build_runner(app_name=..., yaml_path=...)
    memory/                       # Memory Bank factory + topics.yaml
    prompts/                      # externalized .md system prompts
    sessions/                     # DatabaseSessionService factory
    tools/                        # (reserved for future ADK tools)
  menstrual/                      # ADK app -> app_name = "menstrual"
    root_agent.yaml
    __init__.py
    __main__.py                   # python -m menstrual smoke test
  pregnancy/                      # ADK app -> app_name = "pregnancy"
    root_agent.yaml
    __init__.py
    __main__.py
  nutrition/                      # ADK app -> app_name = "nutrition"
    root_agent.yaml
    __init__.py
    __main__.py                   # python -m nutrition smoke test
  tests/
  requirements.txt
```
