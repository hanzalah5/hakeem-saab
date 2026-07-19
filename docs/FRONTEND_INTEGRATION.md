# FemVerse Chatbot — Integration Guide

ALL IT TAKES IS A SMILE TO MAKE SOMEONES DAY. HERE IS YOURS. :) 

KAAM KI BAAT : five apps, the session-state contract, the
endpoints, and all five entry points

---

## 1. Overview

- You pick an app by its `app_name` in the URL.
- Everything about the user is **seeded into session state at session-creation time**.
- Every conversation is **two kinds of call**:
  1. **Create a session** (once, when the chat opens) — seed the user context + (optionally) the entry
     point.
  2. **Send turns** (each message) — stream the assistant's reply.
- An **entry point** = *why* the chat was opened (a generic "Chat Now", or a Tip / Story / Alert /
  Health-Checker card the user tapped). It shapes the assistant's **opening message**.

### Responsibility split

| Who | Does what |
|---|---|
| **Frontend** | Chooses the app; knows which entry point was tapped and its content; renders the stream; sends user messages; **hides the opening sentinel turn** (see §7). |
| **Backend** | Fetches the user's persona + profile from its own DB; assembles session state; creates the ADK session; will proxy `/run_sse`. |
| **Chatbot (ADK)** | Injects the seeded state into the prompt and replies. Never touches a user DB. |

---

## 2. The five applications

| `app_name` | Specialist | Modules it serves |
|---|---|---|
| `menstrual` | Gynecology (cycles, PCOS, hormones, fertility) | Period |
| `pregnancy` | Obstetrics (prenatal, trimesters, postpartum) | Pregnancy |
| `nutrition` | Registered dietitian (macros, calories, allergies) | Nutrition |
| `period_nutrition` | Gynecology **+** nutrition-aware | Period + Nutrition |
| `pregnancy_nutrition` | Obstetrics **+** nutrition-aware | Pregnancy + Nutrition |

Pick the `app_name` that matches the user's active module bundle. `GET /list-apps` returns them 
---

## 3. Base concepts

- **Session state** is a key/value store attached to a session. Three keys matter to the frontend:
  | State key | Lifetime | Purpose |
  |---|---|---|
  | `user_persona` | durable, per-user | slowly-changing clinician summary of the user |
  | `user_profile` | per-session | today's snapshot: profile, cycle/pregnancy/nutrition data, logs |
  | `entry_context` | per-session | why the chat was opened (entry point + its content) |
- The chatbot injects these automatically. **You never send the persona/profile inside chat messages** —
  only into session state at creation.
- **Seed each state value as a JSON string** (`JSON.stringify(...)`). Objects also work but render less
  cleanly in the model's context. All examples below show the objects; wrap them in a string when sending.

---

## 4. Required state — populate BEFORE the first turn

At session creation, seed `state` with (at minimum) `user_profile`; add `user_persona` when available,
and `entry_context` **only** for non-"Chat Now" entries.

### 4.1 `user_persona` (durable summary — optional but recommended)

```json
{
  "last_updated": "2025-12-21",
  "persona_version": "1.4",
  "identity_baseline": { "age": 29, "general_health_summary": "…" },
  "reproductive_health": { "cycle_health": "…", "phase_specific_patterns": { "luteal": "…" } },
  "clinician_summary": "29yo, regular ~28d cycles, mild luteal-phase PMS. Vegetarian."
}
```

### 4.2 `user_profile` (per-session snapshot — always seed)

This is the **raw module JSON** for the app. Shape varies by module (see §8). Menstrual example:

```json
{
  "log_date": "2025-12-22T00:00:00+00:00",
  "user_profile": { "age": 29, "weight_kg": 50, "height_ft_in": "5'2\"", "bmi": 22.1 },
  "cycle_data": {
    "average_cycle_length": 28, "current_cycle_day": 20,
    "current_cycle_phase": "Luteal", "current_phase_day": 8, "late_period_flag": false
  },
  "trying_to_conceive": { "is_trying": false, "sexual_activities": ["None"], "ovulation_test_result": "Not taken" },
  "user_logged_data": {
    "symptoms": ["Cramps", "Low energy"], "moods": ["Sensitive"],
    "sleep_quality": "Interrupted sleep", "diet_type": "Vegetarian",
    "physical_activities": ["Badminton"]
  }
}
```


### 4.3 `entry_context` (entry point — omit for Ask Anything)

```json
{
  "type": "tip | story | alert | health_checker",
  "severity": "yellow | red",           // alerts only
  "content": { "title": "…", "body": "…" },   // full text of the tapped card
  "trigger_logs": { }                    // the specific metric/flag that produced it
}
```

Full per-type schemas in §6.

---

## 5. Endpoints

### 5.1 Create a session

```
POST {baseUrl}/apps/{app_name}/users/{user_id}/sessions
Content-Type: application/json

{
  "state": {
    "user_persona": "<JSON string>",
    "user_profile": "<JSON string>",
    "entry_context": "<JSON string>"     // omit for Chat Now
  }
}
```

- `user_id` — your stable user identifier (UUID).
- **200 response** (capture `id` as `session_id`):

```json
{
  "id": "921aee82-dde9-47a6-…",
  "appName": "period_nutrition",
  "userId": "…",
  "state": { "user_persona": "…", "user_profile": "…", "entry_context": "…" },
  "events": [],
  "lastUpdateTime": 1781178532.6
}
```

> **Gotcha:** if you instead use the *create-with-your-own-id* variant
> `POST …/sessions/{session_id}`, that endpoint takes the **state object directly** as the body (no
> `{"state": …}` wrapper). Prefer the no-id form above and read `id` back.

### 5.2 Send a turn — streaming (production)

```
POST {baseUrl}/run_sse
Content-Type: application/json

{
  "appName": "period_nutrition",
  "userId": "…",
  "sessionId": "…",
  "newMessage": { "role": "user", "parts": [ { "text": "why am I so bloated today?" } ] },
  "streaming": true
}
```

- Response is **Server-Sent Events**: lines prefixed `data: ` each carrying one event JSON.
- Accumulate `event.content.parts[].text`. Events with `"partial": true` are incremental chunks;
  concatenate them. The turn is complete when the stream ends.
- Minimal consumer:

```js
const res = await fetch(`${baseUrl}/run_sse`, { method: "POST",
  headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = "", reply = "";
for (;;) {
  const { value, done } = await reader.read(); if (done) break;
  buf += dec.decode(value, { stream: true });
  for (const line of buf.split("\n")) {
    if (!line.startsWith("data:")) continue;
    const ev = JSON.parse(line.slice(5).trim());
    for (const p of ev.content?.parts ?? []) if (p.text) reply += p.text;  // render incrementally
  }
  buf = buf.slice(buf.lastIndexOf("\n") + 1);
}
```

### 5.3 Send a turn — non-streaming (easy testing)

```
POST {baseUrl}/run        # same body as /run_sse
```

Returns a **JSON array of events**; the assistant text is the concatenation of
`events[*].content.parts[*].text`.

### 5.4 Other

- `GET {baseUrl}/list-apps` → available `app_name`s.
- `GET {baseUrl}/apps/{app}/users/{user}/sessions/{session_id}` → inspect stored state + events.
- `DELETE {baseUrl}/apps/{app}/users/{user}/sessions/{session_id}` → end a session.

---

## 6. Entry points

An entry point is seeded as `entry_context` at session creation. Two rules govern its lifetime:

- **The entry data stays in context for the whole conversation** → follow-ups like "tell me more about
  that alert" work.
- **The special opening behavior applies to the first turn only** → after the opener, the bot
  converses normally.

### 6.1 Chat Now (baseline)

- **CTA:** generic "Chat Now".
- **entry_context:** **omit it** (or `{"type":"chat_now"}`).
- **Flow:** the **user types first**; no sentinel. Standard assistant behavior.

### 6.2 Tip

- **CTA:** "Unlock more important details".
- **entry_context:**

```json
{
  "type": "tip",
  "content": {
    "title": "Magnesium for Luteal Phase Cramps",
    "body": "Magnesium supports muscle relaxation. 300–400mg daily in the luteal phase. Sources: spinach, almonds."
  },
  "trigger_logs": { "symptom": "Cramps", "cycle_phase": "Luteal", "cycle_day": "20 of 28" }
}
```

- **Opening behavior:** acknowledges the topic, adds a **deeper insight the tip didn't state**, cites
  the user's numbers, ends with **one hook** — and asks **no** questions.

### 6.3 Story

- **CTA:** "Dig deeper into this".
- **entry_context:**

```json
{
  "type": "story",
  "content": {
    "title": "Managing Luteal Phase Energy & Mood",
    "body": "During the luteal phase your metabolism rises 16–20% and progesterone lowers serotonin, so cravings and mood dips are common. This is normal — your body is just operating differently this week. What helps: more afternoon carbs, magnesium for mood, lighter workouts, and prioritizing sleep."
  },
  "trigger_logs": { "symptoms": ["Fatigue", "Mood changes", "Cravings"], "cycle_phase": "Luteal" }
}
```

- `content` is just **`title` + `body`** (same shape as Tip/Alert). Put the story's explanation,
  reassurance, and recommended actions all inside `body` — the assistant reads them from that prose.
- **Opening behavior:** validates what they read, shifts "what/why" → **"how for you"**, references the
  story's own actions (from `body`), and **asks personal-history follow-up questions** (Stories *do* ask questions).

### 6.4 Alert — Yellow (advisory)

- **CTA:** "See why this matters".
- **entry_context:**

```json
{
  "type": "alert",
  "severity": "yellow",
  "content": { "title": "Low Protein Intake", "body": "Your protein intake is 16g today. Aim higher to avoid deficiencies." },
  "trigger_logs": { "protein_consumed_g": 16, "protein_target_g": 60 }
}
```

- Seed the relevant `medical_conditions` and today's `symptoms` in `user_profile`.
- **Opening behavior:** states the gap vs target, ties it to the condition + symptoms, stays
  urgent-but-not-scary, ends with an easy hook — **no** questions about their day.

### 6.5 Alert — Red (serious)

- **CTA:** "Fix this today".
- **entry_context:**

```json
{
  "type": "alert",
  "severity": "red",
  "content": { "title": "Dangerously High Carb Intake", "body": "Your carb intake is 182g today. Target: 120g. This can spike blood sugar and worsen diabetes symptoms." },
  "trigger_logs": { "carbs_consumed_g": 182, "carb_limit_g": 120 }
}
```

- **Opening behavior (guardrailed):** states the data, **directs the user to their doctor/educator —
  the AI does not position itself as the fix**, offers to help them **prepare** for that conversation,
  asks **one** diagnostic question, and affirms the clinician visit is the priority. **No
  region-specific emergency numbers** are ever given.

### 6.6 Health Checker

- **Trigger:** a health-checker card flags a pattern (e.g. a late period).
- **entry_context:**

```json
{
  "type": "health_checker",
  "content": { "title": "Your period is late", "body": "Flagged: period late vs your usual cycle." },
  "trigger_logs": { "flagged_pattern": "late period / possible PCOS pattern", "current_cycle_day": 40, "average_cycle_length": 30 }
}
```

- **Opening behavior (doctor–patient):** names the flagged pattern + a one-line definition, weaves in
  current cycle/gestational context, asks **2–3 short questions**, then **stops** (no causes/advice
  yet). Never diagnoses.

---

## 7. The two flows (step by step)

### Chat Now

1. `POST …/sessions` with `state` = `{ user_persona, user_profile }` (no `entry_context`). Capture `id`.
2. User types a message → `POST /run_sse` with that text. Render the stream.
3. Repeat step 2 per message.

### Any entry point (Tip / Story / Alert / Health Checker)

1. `POST …/sessions` with `state` = `{ user_persona, user_profile, entry_context }`. Capture `id`.
2. **Send the opening sentinel:** `POST /run_sse` with
   `newMessage.parts[0].text = "__ENTRY_OPEN__"`.
   - **The frontend MUST NOT render this sentinel turn** in the transcript — it only elicits the AI's
     opening message. Render the assistant reply as the first thing the user sees.
3. User replies → normal `POST /run_sse` turns from here on.

> `__ENTRY_OPEN__` is the agreed opening trigger. Send it exactly once, immediately after creating an
> entry-point session, and suppress it in the UI.

---

## 8. Per-application `user_profile` shapes

Common to all: `user_profile` (age/weight/height/bmi) + `user_logged_data` (today's symptoms/moods/
sleep/activity). Module-specific blocks:

- **`menstrual`** — add `cycle_data` (`current_cycle_phase`, `current_cycle_day`, `average_cycle_length`,
  `late_period_flag`) and `trying_to_conceive`.
- **`pregnancy`** — add `pregnancy_data` (`pregnancy_week`, `trimester`); `user_logged_data` uses
  pregnancy symptom groups (`daily_feelings`, `breast_symptoms`, `swelling_symptoms`, …).
- **`nutrition`** — add `nutritional_data` (`bmr`, `current_weight_kg`, `target_weight_kg`,
  `weight_change_rate`, `food_prefs`, `allergies`, `target_calories`, `health_goals`).
- **`period_nutrition`** — `cycle_data` + `trying_to_conceive` + `nutritional_data`.
- **`pregnancy_nutrition`** — `pregnancy_data` + `nutritional_data`.

Notes:
- **Alerts** that are macro-based (protein/carbs) only make sense for apps with the **Nutrition**
  module. Don't route a nutrition alert to `menstrual`/`pregnancy`.
- Always include `medical_conditions` (e.g. `["Type 2 Diabetes"]`) in `user_profile` when known — Yellow
  and Red alerts rely on it.

---

## 9. Global behaviors the frontend should expect

- **Language + script mirroring:** the bot replies in the **same language and script** the user typed.
  Roman Hindi in → Roman Hindi out (not Devanagari, not English). You do **not** send a language
  parameter; it's inferred from the message.
- **Generic escalation:** the bot never emits region-specific emergency numbers (911/999/112/…); it says
  "contact your healthcare provider / seek medical care".
- **Memory:** facts persist across the user's sessions (Vertex Memory Bank), so returning users are
  remembered without you re-sending everything — but always seed the fresh `user_profile` each session.
- **Disclaimers** appear automatically on medical/dietary guidance, rendered in the reply's language.

---

## 10. Complete worked examples

### 10.1 Tip on `period_nutrition`

**Create session**

```json
POST /apps/period_nutrition/users/USER-123/sessions
{
  "state": {
    "user_persona": "{\"clinician_summary\":\"29yo, regular ~28d cycles, luteal PMS, vegetarian\"}",
    "user_profile": "{\"user_profile\":{\"age\":29,\"bmi\":22.1},\"cycle_data\":{\"current_cycle_phase\":\"Luteal\",\"current_cycle_day\":20},\"user_logged_data\":{\"symptoms\":[\"Cramps\"],\"diet_type\":\"Vegetarian\"}}",
    "entry_context": "{\"type\":\"tip\",\"content\":{\"title\":\"Magnesium for Luteal Phase Cramps\",\"body\":\"300-400mg daily in the luteal phase; spinach, almonds.\"},\"trigger_logs\":{\"symptom\":\"Cramps\",\"cycle_phase\":\"Luteal\"}}"
  }
}
```

**Elicit the opening** (hide this turn in the UI)

```json
POST /run_sse
{ "appName": "period_nutrition", "userId": "USER-123", "sessionId": "<id>",
  "newMessage": { "role": "user", "parts": [ { "text": "__ENTRY_OPEN__" } ] }, "streaming": true }
```

→ assistant opens with a magnesium-timing insight + a food hook, no questions.

### 10.2 Red alert on `period_nutrition`

```json
POST /apps/period_nutrition/users/USER-123/sessions
{
  "state": {
    "user_profile": "{\"user_profile\":{\"age\":34},\"nutritional_data\":{\"daily_carb_limit_g\":120},\"medical_conditions\":[\"Type 2 Diabetes\"],\"user_logged_data\":{\"symptoms\":[\"Dizziness\",\"Fatigue\",\"Headache\"],\"total_carbs_g\":182}}",
    "entry_context": "{\"type\":\"alert\",\"severity\":\"red\",\"content\":{\"title\":\"Dangerously High Carb Intake\",\"body\":\"182g today; target 120g.\"},\"trigger_logs\":{\"carbs_consumed_g\":182,\"carb_limit_g\":120}}"
  }
}
```
→ then `__ENTRY_OPEN__`. Assistant defers to the doctor, offers prep, asks one diagnostic question.

### 10.3 Chat Now on `pregnancy`

```json
POST /apps/pregnancy/users/USER-777/sessions
{
  "state": {
    "user_profile": "{\"user_profile\":{\"age\":31},\"pregnancy_data\":{\"pregnancy_week\":28,\"trimester\":2},\"user_logged_data\":{\"symptoms\":[\"Heartburn\"]}}"
  }
}
```
→ then a normal user message (no sentinel). Assistant responds conversationally.

---

## 11. Pre-flight checklist (before the first turn)

- [ ] Correct `app_name` chosen for the user's module bundle.
- [ ] Session created; `session_id` captured.
- [ ] `user_profile` seeded (JSON string) with the module-appropriate blocks + `medical_conditions`.
- [ ] `user_persona` seeded when available.
- [ ] For entry points: `entry_context` seeded with `type` (+ `severity` for alerts) and the full
      card `content`.
- [ ] For entry points: `__ENTRY_OPEN__` sentinel sent as the first turn **and hidden** in the UI.
- [ ] Chat Now: **no** `entry_context`, **no** sentinel — user speaks first.
- [ ] SSE consumer accumulates `content.parts[].text` and renders incrementally.
```

---

## 12. Resuming from a prior voice-call transcript

If the user had a **voice call** (voicebot) whose transcript the chatbot should be aware of — even
**mid-conversation, after the chat session already exists and has had turns** — write the transcript
into the session's **`call_transcript`** state key. The chatbot renders it to readable text and treats
it as prior conversation from the next turn onward.

- **Endpoint (mid-session; does NOT run the agent, so no assistant reply):**

```
PATCH {baseUrl}/apps/{app_name}/users/{user_id}/sessions/{session_id}
{
  "state_delta": {
    "call_transcript": {
      "events": [
        { "author": "user",                 "content": { "role": "user",  "parts": [ { "text": "…caller line…" } ] } },
        { "author": "menstrual_specialist", "content": { "role": "model", "parts": [ { "text": "…voicebot line…" } ] } }
      ]
    }
  }
}
```

- `state_delta` **or** `stateDelta` (both accepted). The transcript goes under the plain key
  **`call_transcript`**; the value may be this **content-events** object, a bare list of those turns, a
  **JSON string**, or **plain text** — the backend renders any of them to `Caller:/Assistant:` lines.
- Use the app's agent name for the voicebot/model turns (`menstrual_specialist`, `pregnancy_specialist`,
  …); caller turns use `author:"user"`.
- From the user's **next** `/run_sse` turn, the bot has the transcript in context and refers to it
  naturally ("from your earlier call, you mentioned…"). **Re-PATCH** to replace it; PATCH `""` or `{}`
  to clear.
- Alternatively, inject the transcript **at session creation** by passing the same turns in the
  `create_session` `events` list (§5.1) — use that when the call happens *before* the chat opens.
