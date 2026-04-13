---
name: pi-interactive-session
description: Drive pi coding agent interactively for large multi-phase projects
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [delegation, pi, coding, interactive, session, project, iterative, rpc]
    requires_tools: [pi_session_start, pi_session_send, pi_session_read, pi_session_wait, pi_session_stop]
    related_skills: [pi-task-delegation]
---

# Pi Interactive Session

## Overview

Hermes drives. pi builds. Turn by turn.

pi's RPC mode gives Hermes a live JSON protocol connection — send a prompt, get notified when pi finishes, read the output, decide next steps. Unlike `pi_task` (fire-and-forget), a session persists conversation context and file state across many turns.

**Use this for work too large or iterative for a single prompt.**

**The key advantage over qwen sessions:** pi uses explicit JSON-RPC completion signals. There's no idle-timeout guessing — when pi sends `{"type":"response","command":"prompt","success":true}`, the turn is definitively done. Hermes gets notified immediately via inject_message.

**Core loop:** start → send → wait for notification → assess → send next (or stop)

---

## When to Use

### Use `pi_session_start` (interactive) when:
| Signal | Examples |
|--------|----------|
| Multi-phase project | "Build a full REST API with auth, tests, and deployment" |
| "don't stop"/"continue until done" | Any explicit keep-going instruction |
| Iterative course-correction | Work where steps depend on reviewing previous results |
| Scope unclear upfront | "Explore this codebase and improve the worst parts" |
| Multiple named components | Chat + viewer + tracker + radio interface |

### Use `pi_task` (one-shot) when:
| Signal | Examples |
|--------|----------|
| Well-defined, single task | "Add input validation to signup" |
| Single prompt is enough | "Write unit tests for User model" |
| < 5 min, < 3 files | Small focused changes |

---

## Step 1 — Start the Session

```python
pi_session_start(
    working_dir="/absolute/path/to/project",
    # model="*sonnet*"         # override model if needed
    # thinking="high"          # for complex architectural decisions
    # persist_session=True     # default: save session to disk
)
```

Returns `session_id`. The session is ready when status is `"ready"`.
The `pi_session_file` path is returned — save it if you want to resume later.

---

## Step 2 — The Interaction Loop

### 2a. Send an instruction

```python
pi_session_send(
    session_id="<id>",
    message="<clear, specific instruction>",
    # streaming_behavior="steer"  # use "steer" to redirect if pi is off-track
)
```

**Returns immediately.** Do NOT call any other tool after this.
Wait for Hermes to receive the inject_message notification from pi.
When it arrives, the notification contains pi's full response text.

Build complex projects incrementally:
```
Turn 1: "Scaffold a Flask app with blueprints for auth and api in /src"
Turn 2: "Add SQLAlchemy User and Session models in src/models/"
Turn 3: "Create registration and login endpoints in src/api/auth.py"
Turn 4: "Write pytest tests for the auth endpoints"
Turn 5: "Run pytest -v and fix any failures"
Turn 6: "Add a Dockerfile and docker-compose.yml"
```

### 2b. Assess the notification

The inject_message notification contains pi's response text.
Assess it before sending the next instruction:

- **Did pi complete the instruction?** Check for file creation, test results, confirmation.
- **Did pi hit an error?** Look for tracebacks, "permission denied", "not found".
- **Is the approach correct?** Even if pi succeeded, is it what you wanted?
- **Are there tool calls to verify?** Read files pi claims to have created.

### 2c. Decide next action

| Assessment | Action |
|------------|--------|
| Step complete, more remain | `pi_session_send` with next instruction |
| Minor correction needed | `pi_session_send("Actually, change X to Y")` |
| Wrong direction | `pi_session_send(..., streaming_behavior="steer")` to redirect |
| Need to check current state | `pi_session_read(session_id)` |
| All work complete | Verify, then `pi_session_stop(session_id)` |
| pi is stuck/looping | `pi_session_stop` and start fresh |

---

## Step 3 — Checking on Progress

If you want to poll before the notification arrives (not usually needed):

```python
# Check if pi is done yet — safe, 30s max block
pi_session_wait(session_id="<id>", timeout=10)

# Read text without sending — see what pi has produced so far
pi_session_read(session_id="<id>")

# Full transcript since session start
pi_session_read(session_id="<id>", full=True)
```

---

## Step 4 — Stopping the Session

```python
pi_session_stop(session_id="<id>")
```

Returns the `pi_session_file` path. This file can be used to resume the session:
```python
# Resume by passing the file in the system prompt or as a session context hint
pi_session_start(working_dir="/path", ...)
# Then reference the previous work in the first message
pi_session_send(session_id="<new_id>", message="Continue the work from the previous session. The files are already in /path.")
```

**Always stop sessions when done** — they hold a process open.

---

## Interaction Patterns

### Pattern A — Full Project Build

```
Start session in working_dir

Turn 1: "Create the project structure: explain what you'll build first, then scaffold src/, tests/, config files."
[Wait for notification — pi describes structure and creates files]
Turn 2: "Good. Now implement the core data models."
[Wait — pi writes models]
Turn 3: "Add the main business logic in src/. Follow the patterns in the models."
[Wait — pi implements logic]
Turn 4: "Write tests covering the main paths."
[Wait — pi writes tests]
Turn 5: "Run the tests. Fix any failures."
[Wait — pi runs tests and iterates]
Turn 6: "The tests pass. Add a README and clean up any TODOs."
→ Stop
```

### Pattern B — Iterative Debugging

```
Turn 1: "Run pytest tests/ -v --tb=short and show me the output"
[Wait — pi runs tests, shows failures]
Turn 2: "Focus on test_user_creation. Read the test and the code it tests."
[Wait — pi reads and explains]
Turn 3: "The mock is wrong. Fix it in conftest.py."
[Wait — pi fixes]
Turn 4: "Re-run just test_user_creation to verify."
[Wait — pi runs]
Turn 5: "Good. Now fix the remaining 2 failures using the same pattern."
→ Stop
```

### Pattern C — Multi-Component Interface

```
Turn 1: "Create the project skeleton with index.html, package.json, and src/ directory."
Turn 2: "Implement the chat interface component in src/chat.js. Connect to local OpenAI API at localhost:8082."
Turn 3: "Add the epub.js viewer component in src/reader.js."
Turn 4: "Add the sun tracker widget using suncalc in src/sun.js."
Turn 5: "Wire all components into index.html with a tabbed layout."
Turn 6: "Run a local server and verify each tab loads without errors."
→ Stop
```

---

## Red Flags

- Call another tool immediately after `pi_session_send` — always wait for inject_message
- Send the next instruction before reading pi's response
- Leave sessions open after work is done
- Use `streaming_behavior="steer"` when pi is still on track (only use to redirect)
- Start fresh sessions for work that should continue the current context

---

## Iron Laws

```
Send → wait for notification → assess → send next
One prompt at a time — never stack
Stop sessions when done — always clean up
Use steer for redirection, followUp for continuation
```

**Hermes drives the protocol. pi does the work. The user gets an iterative, guided build.**
