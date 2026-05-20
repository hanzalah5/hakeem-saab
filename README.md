# FemVerse OB/GYN Assistant

A modular, ADK-based conversational assistant for a female healthcare platform. FemVerse plays the role of a senior OB/GYN, shipped as **two independent single-agent apps** — one for menstrual / gynecology care and one for pregnancy / prenatal care.

This repository replaces the legacy `legacy_Imp.py` single-file Streamlit prototype with a clean Google [Agent Development Kit (ADK)](https://adk.dev/) implementation.

## Architecture

```
                       Frontend
                          |
              appName = "menstrual" or "pregnancy"
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
        | fetch_user_persona, load_memory    |
        |                                    |
+-------v---------+                +---------v--------+
| fetch_period_   |                | fetch_pregnancy_ |
| daily_logs      |                | daily_logs       |
+-------+---------+                +---------+--------+
        |                                    |
        +----------------+-------------------+
                         v
                +-------------------+
                |     Cassandra     |
                | (persona + logs)  |
                +-------------------+
                |   DatabaseSessionService   (your SQL DB)
                |   VertexAiMemoryBankService (Agent Engine)
```

The two apps are independent at runtime: sessions and Memory Bank state are siloed per `app_name`. They share the `femverse/` Python package for tools, prompts, callbacks, settings, and service factories — but neither app can transfer control to the other. The frontend chooses which app to call.

| Concern            | Location                                                          |
|--------------------|-------------------------------------------------------------------|
| Menstrual app      | `menstrual/root_agent.yaml`, `menstrual/__init__.py`              |
| Pregnancy app      | `pregnancy/root_agent.yaml`, `pregnancy/__init__.py`              |
| Prompts            | `femverse/prompts/*.md` (loaded via `femverse.prompts.loader`)    |
| Tools              | `femverse/tools/user_data.py`                                     |
| Memory             | `femverse/memory/service.py` + `femverse/memory/topics.yaml`      |
| Sessions           | `femverse/sessions/service.py` (SQL URL via `SESSION_DB_URL`)     |
| Callbacks          | `femverse/core/callbacks.py`                                      |
| Runtime wiring     | `femverse/core/runtime.py`                                        |
| Settings           | `femverse/config/settings.py`                                     |
| Cassandra client   | `femverse/cassandra/`                                             |

## Quick start

1. **Install dependencies**
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. **Configure environment**
   ```powershell
   copy .env.example .env
   # then edit .env with your model + GCP + DB settings
   ```

3. **Plug in your SQL DB** for session persistence — edit `femverse/sessions/service.py::get_database_url()` to return your SQLAlchemy URL, **or** set `SESSION_DB_URL` in `.env`.

4. **Run**

   ```powershell
   # Run both apps from a single ADK API server (recommended).
   # The dot tells ADK to autodiscover every top-level app folder
   # (menstrual/, pregnancy/) and expose each as its own app_name.
   adk api_server . --session_service_uri="$env:SESSION_DB_URL" --memory_service_uri="agentengine://$env:AGENT_ENGINE_ID"

   # Or run a single app interactively in a terminal:
   adk run menstrual
   adk run pregnancy

   # Web UI for one app:
   adk web menstrual
   adk web pregnancy
   ```

   Verify both apps loaded:
   ```powershell
   # In another terminal:
   curl http://localhost:8000/list-apps   # -> ["menstrual","pregnancy"]
   ```

5. **Smoke test without the ADK CLI**
   ```powershell
   python -m menstrual
   python -m pregnancy
   ```
   Each command prints a single line (`app=... root_agent=... model=... tools=[...]`) and exits zero when the YAML, prompts, tools, and callbacks all resolve cleanly.

## Memory model

Both apps use [Vertex Memory Bank](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/memory-bank/overview) with four extraction categories defined in [`femverse/memory/topics.yaml`](femverse/memory/topics.yaml):

1. **Health Facts** — medical history, symptoms, cycle / gestational data, OB/GYN metrics.
2. **Nutritional Facts** — dietary habits, allergies, supplements, hydration.
3. **User Personal Details** — age, weight, height, ethnicity, parity.
4. **User Preferences** — tone, language, lifestyle, content sensitivities.

Memory is **retrieved on demand** via the `load_memory` tool (token-efficient — no preload every turn) and **persisted after each turn** via an `after_agent_callback`.

Memory Bank state is siloed per `app_name`, so cross-module persona facts that should follow the user across apps belong in Cassandra (via `fetch_user_persona`), not Memory Bank.

## Session model

`DatabaseSessionService` is wired through `femverse/sessions/service.py::build_session_service()`. Plug in any SQLAlchemy-supported backend. Sessions survive process restarts so mid-flow conversations don't reset on redeploy. Sessions are also siloed per `app_name`.

## Project layout

```
hakeem-saab/
  femverse/                       # shared library (no agent definitions live here)
    cassandra/                    # Cassandra client
    config/settings.py            # pydantic-settings env loader
    core/
      callbacks.py                # prompt-injection + memory-persistence
      runtime.py                  # build_runner(app_name=..., yaml_path=...)
    memory/                       # Memory Bank factory + topics.yaml
    prompts/                      # externalized .md system prompts
    sessions/                     # DatabaseSessionService factory
    tools/                        # fetch_user_persona,
                                  # fetch_period_daily_logs,
                                  # fetch_pregnancy_daily_logs
  menstrual/                      # ADK app -> app_name = "menstrual"
    root_agent.yaml
    __init__.py
    __main__.py                   # python -m menstrual smoke test
  pregnancy/                      # ADK app -> app_name = "pregnancy"
    root_agent.yaml
    __init__.py
    __main__.py
  docs/                           # frontend / backend integration docs
  tests/
  .env.example
  requirements.txt
```
