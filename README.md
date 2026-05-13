# FemVerse OB/GYN Assistant

A modular, ADK-based conversational assistant for a female healthcare platform. FemVerse plays the role of a senior OB/GYN, providing empathetic, medically grounded guidance across menstrual health and pregnancy/prenatal care.

This package replaces the legacy `legacy_Imp.py` single-file Streamlit prototype with a clean Google [Agent Development Kit (ADK)](https://adk.dev/) implementation.

## Architecture

```
                +-------------------------------+
                |  femverse_coordinator (YAML)  |
                |  - routes by topic            |
                +---------------+---------------+
                                |
              +-----------------+-----------------+
              |                                   |
+-------------v-------------+       +-------------v-------------+
| menstrual_specialist      |       | pregnancy_specialist      |
| - cycle, hormones, perio. |       | - gestation, prenatal,    |
|   alerts, consults, tips  |       |   labor prep, postpartum  |
+-------------+-------------+       +-------------+-------------+
              |                                   |
              +-----------------+-----------------+
                                |
                  shared tools  v
                  - fetch_user_persona (stub)
                  - fetch_daily_logs   (stub)
                  - load_memory        (ADK built-in)

                  + DatabaseSessionService  (your SQL DB)
                  + VertexAiMemoryBankService (Agent Engine)
```

Three top-level concerns are intentionally separated:

| Concern            | Location                                                   |
|--------------------|------------------------------------------------------------|
| Agent definitions  | `agent/root_agent.yaml`, `agent/sub_agents/*.yaml`         |
| Prompts            | `agent/prompts/*.md` (loaded via `agent.prompts.loader`)   |
| Tools (stubs)      | `agent/tools/user_data.py`                                 |
| Memory             | `agent/memory/service.py` + `agent/memory/topics.yaml`     |
| Sessions           | `agent/sessions/service.py` (SQL stub for you to fill in)  |
| Callbacks          | `agent/core/callbacks.py`                                  |
| Runtime wiring     | `agent/core/runtime.py`                                    |
| Settings           | `agent/config/settings.py`                                 |

## Quick start

1. **Install dependencies**
   ```bash
   python -m venv .venv
   .venv\Scripts\Activate.ps1        # Windows PowerShell
   pip install -r requirements.txt
   ```

2. **Configure environment**
   ```bash
   copy .env.example .env             # Windows
   # then edit .env with your model + GCP + DB settings
   ```

3. **Plug in your SQL DB** for session persistence — edit `agent/sessions/service.py::get_database_url()` to return your SQLAlchemy URL, **or** set `SESSION_DB_URL` in `.env`.

4. **Run**
   ```bash
   # Interactive web UI:
   adk web agent --session_service_uri="$env:SESSION_DB_URL" --memory_service_uri="agentengine://$env:AGENT_ENGINE_ID"

   # API server:
   adk api_server agent --session_service_uri="$env:SESSION_DB_URL" --memory_service_uri="agentengine://$env:AGENT_ENGINE_ID"

   # Terminal:
   adk run agent
   ```

## Memory model

The agent uses [Vertex Memory Bank](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/memory-bank/overview) with four extraction categories defined in [`agent/memory/topics.yaml`](agent/memory/topics.yaml):

1. **Health Facts** — medical history, symptoms, cycle/gestational data, OB/GYN metrics.
2. **Nutritional Facts** — dietary habits, allergies, supplements, hydration.
3. **User Personal Details** — age, weight, height, ethnicity, parity.
4. **User Preferences** — tone, language, lifestyle, content sensitivities.

Memory is **retrieved on demand** via the `load_memory` tool (token-efficient — no preload every turn) and **persisted after each turn** via an `after_agent_callback`.

## Session model

`DatabaseSessionService` is wired through `agent/sessions/service.py::build_session_service()`. Plug in any SQLAlchemy-supported backend. Sessions survive process restarts so mid-flow conversations don't reset on redeploy.

## Project layout

```
agent/
  root_agent.yaml          # coordinator
  sub_agents/
    menstrual_agent.yaml
    pregnancy_agent.yaml
  prompts/                 # externalized .md system prompts
  tools/                   # fetch_user_persona / fetch_daily_logs stubs
  memory/                  # Memory Bank factory + topics.yaml
  sessions/                # DatabaseSessionService factory
  core/                    # callbacks + runtime wiring
  config/                  # pydantic-settings env loader
```
