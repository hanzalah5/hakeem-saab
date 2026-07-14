# FemVerse — Postman collection

`FemVerse_EntryPoints.postman_collection.json` exercises the chatbot and the **entry-point** feature
across all five apps.

## Setup

1. Start the API server:
   ```powershell
   adk api_server . --session_service_uri="$env:SESSION_DB_URL" `
                    --memory_service_uri="agentengine://$env:AGENT_ENGINE_ID"
   # or simply: adk api_server .   (in-memory sessions, fine for testing)
   ```
2. In Postman: **Import** → select the `.json` file.
3. Set the collection variables (Collection → Variables) if needed:
   - `baseUrl` — default `http://localhost:8000` (match your `--port`)
   - `appName` — default `period_nutrition`; switch to `menstrual` / `pregnancy` / `nutrition` / `pregnancy_nutrition`
   - `userId` — any string
   - `sessionId` — auto-filled by each **Create session** request

## How to run

Per folder: run **Create session …** first (it stores `sessionId`), then the **Run** request(s).
Open the Postman **Console** (View → Show Postman Console) to read the assistant reply, which each
Run request logs under `===== ASSISTANT REPLY =====`.

| Folder | What it checks |
|---|---|
| 0 · Setup | `/list-apps` returns the 5 apps |
| 1 · Chat Now | baseline — no `entry_context`, user speaks first |
| 2 · Tip | opening = acknowledge + beyond-the-tip insight + numbers + hook, no questions; follow-up stays tip-aware |
| 3 · Story | "how for you" + references story actions + personal-history questions |
| 4 · Alert — Yellow | gap vs target + condition/symptoms + not-scary + hook, no day-questions |
| 5 · Alert — Red | defers to doctor (AI not the fix), offers prep, one diagnostic question, no region numbers |
| 6 · Health Checker | doctor-patient mode: name pattern + define + context + 2–3 `- ` questions, then stop; never diagnose |
| 7 · Utilities | inspect session state; Roman-Hindi language-mirroring check |

## Contract notes

- An **entry point** is seeded into session state as **`entry_context`**; the AI's opening message is
  produced in response to a **hidden sentinel first turn** (`__ENTRY_OPEN__`) that the frontend
  suppresses. Entry data stays in context for follow-ups; opening-behavior rules apply to the first
  turn only.
- State values are shown as **JSON objects** for readability. In production, seed `user_persona` /
  `user_profile` / `entry_context` as **JSON strings** (`json.dumps`) for clean prompt injection —
  both work.
- Requests use **`/run`** (returns a JSON array of events) for easy assertions. Production streams the
  same events via **`/run_sse`**. A **500** on a Run is usually a Gemini **429 quota** limit, not a bug.
- **Status:** all 5 entry points are implemented (Chat Now, Tip, Story, Alert yellow/red, Health
  Checker). An unknown/absent entry type degrades gracefully to base behavior (no crash).
