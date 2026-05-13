# FemVerse — Backend integration (sessions SQL + persona / daily logs)

This guide is for backend engineers wiring **FemVerse’s SQL session store** into ADK and implementing the **persona** and **daily logs** tools consumed by the LLM. It does **not** prescribe JSON shapes for persona or logs — those contracts are owned by your API/DB team; the agent only requires JSON-serializable payloads and stable, human-readable keys.

---

## 1. Overview — three integration points

| Concern | Where it lives |
|--------|----------------|
| **SQL session persistence** | [`agent/sessions/service.py`](../agent/sessions/service.py) — `get_database_url()` and `build_session_service()` |
| **Persona tool** | [`agent/tools/user_data.py`](../agent/tools/user_data.py) — `fetch_user_persona(user_id: str)` |
| **Daily logs tool** | Same file — `fetch_daily_logs(user_id: str)` |

```mermaid
flowchart LR
  subgraph ADK
    R[Runner]
    DSS[DatabaseSessionService]
    A[Agent + tools]
  end
  SQL[(Sessions SQL DB)]
  PV[(Persona / logs store)]

  R --> DSS
  DSS --> SQL
  R --> A
  A --> fetch_user_persona
  A --> fetch_daily_logs
  fetch_user_persona --> PV
  fetch_daily_logs --> PV
```

---

## 2. Environment variables

Loaded via [`agent/config/settings.py`](../agent/config/settings.py) (`pydantic-settings`, `.env` + process env). Names are **case-insensitive** for env vars.

| Variable | Maps to | Purpose |
|----------|---------|---------|
| `SESSION_DB_URL` | `session_db_url` | SQLAlchemy URL for `DatabaseSessionService` |
| `GOOGLE_CLOUD_PROJECT` | `google_cloud_project` | GCP project (Vertex / Memory Bank paths) |
| `GOOGLE_CLOUD_LOCATION` | `google_cloud_location` | Region, e.g. `us-central1` |
| `AGENT_ENGINE_ID` | `agent_engine_id` | Vertex Agent Engine id for Memory Bank URI `agentengine://…` |
| `GOOGLE_API_KEY` | `google_api_key` | Google AI Studio key when not using Vertex |
| `MODEL_NAME` | `model_name` | Default model id (default in code: `gemini-2.5-flash`) |

Optional: `GOOGLE_GENAI_USE_VERTEXAI` — set true to route Gemini through Vertex.

**CLI alignment:** launch with `--session_service_uri="$env:SESSION_DB_URL"` and `--memory_service_uri="agentengine://$env:AGENT_ENGINE_ID"` as in the project README.

---

## 3. Session persistence — `DatabaseSessionService`

### 3.1 Configuration (two ways)

1. **Recommended:** set **`SESSION_DB_URL`** in `.env`. `build_session_service()` reads `settings.session_db_url` first ([`agent/sessions/service.py`](../agent/sessions/service.py) around line 69).
2. **Inline:** implement **`get_database_url()`** to return a DSN string instead of raising `NotImplementedError` (lines 49–52 today).

Resolution order: **`settings.session_db_url` OR `get_database_url()`**.

### 3.2 DSN examples (SQLAlchemy)

Same examples as the module docstring:

| Engine | Example DSN |
|--------|-------------|
| SQLite (dev) | `sqlite:///./femverse_sessions.db` |
| PostgreSQL | `postgresql+psycopg2://user:pass@host:5432/femverse` |
| MySQL | `mysql+pymysql://user:pass@host:3306/femverse` |
| MS SQL Server | `mssql+pyodbc://user:pass@host/femverse?driver=ODBC+Driver+17+for+SQL+Server` |

### 3.3 Driver matrix

| DSN prefix | Typical driver package |
|------------|-------------------------|
| `postgresql+psycopg2://` | `psycopg2-binary` |
| `mysql+pymysql://` | `pymysql` |
| `mssql+pyodbc://` | `pyodbc` + ODBC driver installed on host |
| `sqlite://` | stdlib / SQLAlchemy built-in |

Add the driver to **`requirements.txt`** (or your lockfile) for non-SQLite databases.

### 3.4 Schema auto-creation

ADK’s `DatabaseSessionService` **creates the `sessions` and `events` tables on first use**. There are **no migrations** in this layer — plan backups and upgrades accordingly.

### 3.5 Operations

- **Pooling / timeouts:** use your platform defaults or SQLAlchemy pool settings in the URL / engine if you outgrow defaults.
- **Managed cloud DBs:** watch **idle connection** limits and **SSL** query params required by the provider.
- **Backups:** session DB is the source of chat recovery; include it in RPO/RTO planning.

---

## 4. Persona tool — `fetch_user_persona`

**Signature (keep as-is):** `fetch_user_persona(user_id: str) -> dict[str, Any] | None`

**Contract (no field-level schema prescribed):**

- Return a **JSON-serializable `dict`** when the user exists, or **`None`** when unknown / not found.
- The dict is passed **verbatim** to the model as tool output — keys should be **human-readable** semantic hints.
- Keep serialized size modest (rule of thumb **under ~2 KB**) so it fits comfortably in context.

**Implementation pattern:** keep [`user_data.py`](../agent/tools/user_data.py) thin; delegate to a repo (see §6).

**Error policy:** return **`None`** for “not found”; **do not raise** for expected misses — prompts under `agent/prompts/` assume `None` means the model should ask the user briefly.

**Caching:** the LLM may call the tool whenever it chooses; use an **in-process LRU** keyed by `user_id` with a **short TTL (~5 minutes)** for hot chats to protect your DB.

---

## 5. Daily logs tool — `fetch_daily_logs`

**Signature:** `fetch_daily_logs(user_id: str) -> list[dict[str, Any]] | None`

**Contract (no per-entry schema prescribed):**

- Return **`list[dict]`** JSON-serializable entries, or **`None`** when there are no logs / user unknown.
- Prefer **most recent first** ordering.
- Cap length (e.g. **~14 entries**) to keep context tight.
- Human-readable keys, same rationale as persona.

**Error policy:** **`None`**, never raise for expected empty/absent data.

---

## 6. Recommended layout — `agent/data/`

Keep LLM-facing tools stable and move DB/network code here:

| File | Role |
|------|------|
| `agent/data/__init__.py` | Export a shared **`engine`**, **`Session` factory**, or connection pool singleton |
| `agent/data/persona_repo.py` | Pure data access for persona by `user_id` |
| `agent/data/logs_repo.py` | Pure data access for daily logs by `user_id` |
| `agent/tools/user_data.py` | Thin wrappers: call repos, normalize to `dict \| None` / `list \| None` |

This separates **prompt-facing tool signatures** from **FemVerse SQL/HTTP plumbing**.

---

## 7. Testing

1. **`python -m agent`** — loads the root agent and prints a one-line health summary ([`agent/__main__.py`](../agent/__main__.py)). After wiring repos, this should still pass with sane env vars.
2. **`adk run agent`** — interactive terminal smoke test for end-to-end behavior.
3. **Unit tests (suggested, not shipped here):** pytest modules that mock DB sessions and assert `persona_repo` / `logs_repo` SQL or HTTP clients in isolation, then a thin integration test that monkeypatches the repos from `user_data`.

---

## 8. Observability

- In **`fetch_user_persona`** / **`fetch_daily_logs`**: log **latency**, **cache hit/miss**, and **missing user** at INFO/DEBUG; log **unexpected failures** at ERROR with **no PII** in message text if possible.
- **Tool exceptions** surface to the model as tool errors — keep responses small and avoid leaking stack traces or secrets into tool return payloads.

---

## 9. FAQ / pitfalls

**“My DB driver isn’t installed.”**  
Match your DSN dialect to a package in `requirements.txt` (see §3.3).

**“ADK created tables I don’t want in my public schema.”**  
Point the DSN at a **dedicated schema** or database. Postgres example using `search_path`:

`postgresql+psycopg2://user:pass@host/db?options=-csearch_path%3Dfemverse_sessions`

**“Sessions DB grows forever.”**  
Prune old sessions (and rely on ADK table layout). Example pattern (adjust table/column names to match ADK’s schema in your version):

```sql
-- Illustrative only — verify table names against your deployed ADK version.
DELETE FROM events
WHERE session_id IN (
  SELECT id FROM sessions
  WHERE last_update_time < EXTRACT(EPOCH FROM NOW() - INTERVAL '90 days') * 1000
);
DELETE FROM sessions
WHERE last_update_time < EXTRACT(EPOCH FROM NOW() - INTERVAL '90 days') * 1000;
```

**“Tool returns huge payloads.”**  
Trim fields at the repo layer; the model quality degrades when context is flooded.

**“I raised `ValueError` for missing user.”**  
Prefer **`None`** — raising trains the model on error strings and adds noise to traces.

---

## 10. Cross-reference: prompts

Specialists load system prompts from `agent/prompts/`. When persona/logs return `None`, instructions should steer the model to ask concise clarifying questions — keep tool behavior aligned with those prompts when you change return conventions.
