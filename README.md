# hermes-pi-bridge

A [Hermes Agent](https://github.com/cloudmindlab/hermes) plugin that connects Hermes to [pi](https://github.com/badlogic/pi-mono), a minimal AI coding agent. Hermes orchestrates; pi executes.

---

## What it does

Hermes is a general-purpose AI agent with memory, skills, and tool routing. Pi is a focused coding agent with direct filesystem and shell access. This bridge wires them together so Hermes can delegate coding work to pi rather than attempting it directly.

Two delegation modes are provided:

| Mode | When to use | How it works |
|------|-------------|--------------|
| **One-shot task** | Single focused change, bug fix, test write | Runs `pi --print <prompt> --mode json`, blocks or backgrounds, injects result |
| **Interactive session** | Multi-phase project, iterative build | Spawns `pi --mode rpc`, drives it turn-by-turn via JSON-RPC; notified via `inject_message` when each response is ready |

The plugin also hooks into `pre_llm_call` to detect coding requests and automatically remind Hermes to delegate — so Hermes routes to pi without the user having to ask explicitly.

---

## Architecture

```
Hermes Agent
│
├── pre_llm_call hook
│   ├── Detects large/multi-phase project → injects interactive session reminder
│   └── Detects any coding task → injects task delegation reminder
│
├── pi_task / pi_task_async  ──────────────────────────────────────┐
│   Subprocess: pi --print "<prompt>" --no-session --mode json     │
│   Parses NDJSON (turn_end, agent_end events) → result text       │
│   async: background thread → inject_message on completion        │
│                                                                  │
└── pi RPC session (pi_session_*)  ────────────────────────────────┘
    Subprocess: pi --mode rpc
    stdin ← JSON commands  {"type":"prompt","message":"..."}
    stdout → JSON events   {"type":"response","command":"prompt","success":true}
    Background reader thread parses events, accumulates text
    Background watcher thread fires inject_message on completion
    Hermes sends next instruction → repeat
```

### Files

```
plugin/
  __init__.py       Plugin registration, pre_llm_call hook, trigger detection
  tools.py          Tool handler implementations (11 tools)
  schemas.py        OpenAI function-calling schemas for all tools
  rpc_session.py    pi RPC session lifecycle and protocol
  sessions.py       In-memory task state store
  plugin.yaml       Hermes plugin manifest

skill/
  SKILL.md          pi-task-delegation skill (one-shot tasks)
  SKILL_SESSION.md  pi-interactive-session skill (multi-turn sessions)

install.sh          Installer — symlinks plugin and skills, patches config.yaml
```

---

## Prerequisites

**Hermes Agent** installed and configured.

**pi coding agent** installed:

```bash
npm install -g @mariozechner/pi-coding-agent
pi --version
```

Pi needs a model configured. It uses an OpenAI-compatible API — point it at a local server (llama.cpp, Ollama, LM Studio) or a cloud provider. Pi's configuration lives at `~/.pi/agent/`.

**Python 3.9+** — no extra packages required. The bridge uses only stdlib (`subprocess`, `threading`, `json`, `uuid`, `pathlib`).

---

## Installation

```bash
git clone <this-repo> ~/Projects/hermes-pi-bridge
cd ~/Projects/hermes-pi-bridge
bash install.sh
```

The installer:

1. Symlinks `plugin/` → `~/.hermes/plugins/pi-bridge`
2. Symlinks `skill/SKILL.md` → `~/.hermes/skills/software-development/pi-task-delegation/SKILL.md`
3. Symlinks `skill/SKILL_SESSION.md` → `~/.hermes/skills/software-development/pi-interactive-session/SKILL.md`
4. Patches `~/.hermes/config.yaml` to add `pi_bridge` to toolsets (after every `hermes-cli` entry)
5. Checks that the `pi` binary is reachable

Re-running `install.sh` is safe — symlinks are updated, config is not duplicated.

**Force-replace existing directories:**

```bash
bash install.sh --force
```

**Restart Hermes** to load the plugin after installation.

---

## Trigger detection

The `pre_llm_call` hook runs before every Hermes LLM call and scans the user's message for coding-related patterns. When it fires, it injects a reminder pointing Hermes at the right skill so it delegates rather than writing code itself.

### Large / multi-phase project → interactive session

Fires when the message matches any of:

- Explicit continuation: *"don't stop"*, *"keep going"*, *"continue until done"*, *"as far as you can"*
- Multiple named components in one ask: chat + viewer + tracker + dashboard + auth + API (any two from a set of ~20 component names)
- Scope words: *"full project/app/stack/system"*, *"complete app"*, *"entire codebase"*, *"from scratch"*, *"whole project"*
- *"full-stack"* or *"fullstack"*
- *"end-to-end"*, *"e2e build/app/system"*
- Lists of 3+ deliverables: *"with auth, tests, and deployment"*
- *"production-ready"*, *"production-grade"*
- *"explore/audit/review/analyse my codebase/repo"*
- Multiple explicit components: *"multiple services"*, *"several phases"*
- Phased framing: *"phase 1"*, *"step 2"*, *"part 3"*

### Any coding task → one-shot task

Fires when the message matches any of:

- Create/generate code artifacts: `write/create/make/generate` + function, class, module, endpoint, API, test, script, CLI, schema, migration, Dockerfile, workflow…
- `implement` (anything — bare verb is enough)
- `build` + a target article
- `add` + feature, method, endpoint, test, validation, auth, middleware, caching, logging, pagination, search…
- `update/modify/change/edit/patch/extend/enhance` + an existing code artifact by name
- `fix` + bug, error, issue, the/this/that [code thing]
- `refactor`, `rewrite`, `migrate`, `port`, `convert`, `transform`
- `debug` (anything)
- `run [the] tests/pytest/jest/…`
- `run … and fix`
- `set up`, `scaffold`, `bootstrap`, `initialize`, `spin up`
- `integrate/connect/wire up` + with/to/into
- `dockerize`, `containerize`
- `dockerfile`/`docker-compose` + for/the/my
- File path in the message (`src/api.py`, `~/Projects/…`, `lib/`, `tests/`)
- *"in/for/within my project/codebase/repo"*
- `write/add/create tests for`
- `make it/this work/production-ready/type-safe`
- `can you write/build/implement/update/refactor/…`
- Language + task: `python/typescript/rust/go/bash … script/function/class/that`

### What stays with Hermes (no delegation)

- Knowledge questions: *"How do I parse JSON in Python?"*, *"Explain how closures work"*
- Syntax / concept explanations
- Standalone one-liner snippets with no project context
- Anything not matching a coding pattern above

---

## Tools

### One-shot tasks

#### `pi_task`

Delegate a task to pi and **block until done** (default timeout: 15 min).

```
pi_task(
    prompt                  required  Full task description — what to build/fix/change
    working_dir             optional  Absolute path for pi to work in
    model                   optional  Model pattern override (e.g. "claude-opus-4-6", "*sonnet*")
    provider                optional  Provider override (e.g. "anthropic", "openai")
    thinking                optional  "off" | "minimal" | "low" | "medium" | "high" | "xhigh"
    tools                   optional  Comma-separated tool list (default: read,bash,edit,write)
    system_prompt           optional  Replace pi's default system prompt
    append_system_prompt    optional  Append to pi's default system prompt
    timeout                 optional  Max seconds. Default: 900
)
```

Returns: `status`, `result` (pi's response text), `num_turns`, `duration_ms`, `model`, `provider`.

Uses `pi --print <prompt> --no-session --mode json` internally. NDJSON output is parsed — `turn_end` events give the authoritative text.

#### `pi_task_async`

Start a pi task in the **background and return immediately**. Hermes is notified via `inject_message` when pi finishes.

Same parameters as `pi_task` (timeout default: 30 min). Returns `task_id` immediately.

Use for tasks likely to take more than 5 minutes.

#### `pi_task_status`

Check the status of one task or list all tasks in the session.

```
pi_task_status(task_id="abc12345")   # specific task
pi_task_status()                     # list all
```

Status values: `running` | `completed` | `failed` | `timeout`.

#### `pi_task_result`

Retrieve the full stored output of a completed task.

```
pi_task_result(task_id="abc12345")
```

#### `pi_check`

Verify pi installation and report current state.

```
pi_check()
```

Returns: binary path, version, auth file presence, session count, running task count, active RPC session count.

---

### Interactive RPC sessions

These tools drive pi over its native JSON-RPC protocol (`pi --mode rpc`). The session persists across many prompts — pi retains full conversation context and file state between turns.

#### `pi_session_start`

Spawn a pi process in RPC mode and wait for it to confirm ready.

```
pi_session_start(
    working_dir             required  Absolute path for pi to operate in
    model                   optional  Model override
    provider                optional  Provider override
    thinking                optional  Thinking level
    tools                   optional  Tool list override
    system_prompt           optional
    append_system_prompt    optional
    persist_session         optional  Save session to ~/.pi/agent/sessions/. Default: true
    ready_timeout           optional  Seconds to wait for ready signal. Default: 15
)
```

Returns: `session_id`, `status`, `pi_session_file` (path to disk state). Maximum 3 concurrent sessions.

#### `pi_session_send`

Send a prompt to an active session. **Returns immediately.** A background watcher waits for pi's explicit `{"type":"response","command":"prompt"}` completion signal, then fires `inject_message` with pi's full response.

```
pi_session_send(
    session_id          required
    message             required  The instruction to send
    streaming_behavior  optional  "followUp" (default) | "steer"
)
```

- `followUp` — continue the conversation normally
- `steer` — interrupt current direction and redirect (use when pi is off-track)

**After calling this, do not call any other tool.** Wait for the `inject_message` notification, read pi's output, then decide whether to send the next instruction or stop.

#### `pi_session_read`

Read accumulated text from a session without sending anything.

```
pi_session_read(session_id, full=False)
```

`full=True` returns all text since session start. Default returns the current/last turn only.

#### `pi_session_wait`

Block up to `timeout` seconds for the current prompt to complete (default: 30s). Safe to call from the agent thread — the background watcher from `pi_session_send` still fires `inject_message` independently.

```
pi_session_wait(session_id, timeout=30)
```

#### `pi_session_stop`

Abort and close a session. Sends `{"type":"abort"}`, closes stdin, waits for clean exit, kills if needed.

```
pi_session_stop(session_id)
```

Returns `pi_session_file` path. **Always stop sessions when work is complete** — each holds a subprocess open.

#### `pi_session_list`

List all sessions (active and closed) in the current Hermes session.

```
pi_session_list()
```

---

## RPC protocol details

Pi's `--mode rpc` runs a JSON Lines protocol over stdin/stdout.

**Commands sent by Hermes (stdin):**

```json
{"type": "prompt", "message": "...", "streamingBehavior": "followUp"}
{"type": "get_state"}
{"type": "abort"}
```

**Events received from pi (stdout):**

| Event type | When it fires | What it carries |
|------------|---------------|-----------------|
| `message_start` | Start of assistant turn | `model`, `provider` |
| `message_update` | During generation | `assistantMessageEvent.type = "text_delta"` with incremental text |
| `message_update` | End of text block | `assistantMessageEvent.type = "text_end"` with full text |
| `turn_end` | LLM response complete | Final `message.content` with authoritative text |
| `response` | RPC command acknowledged | `command="prompt"`, `success=true/false` — definitive "done" signal |

The `response` event with `command="prompt"` is what unblocks the watcher thread and triggers `inject_message`. Unlike idle-timeout approaches, this is an explicit synchronous completion signal — no guessing required.

---

## Skills

The bridge registers two Hermes skills.

### `pi-task-delegation`

Loaded via `skill_view("pi-task-delegation")`. Guides Hermes through:

1. Gathering context (working dir, relevant files, constraints, verification command)
2. Choosing sync vs async
3. Choosing thinking level
4. Constructing a four-part prompt: `[TASK]` / `[CONTEXT]` / `[REQUIREMENTS]` / `[VERIFICATION]`
5. Calling `pi_task` or `pi_task_async`
6. Assessing output and deciding next steps

### `pi-interactive-session`

Loaded via `skill_view("pi-interactive-session")`. Guides Hermes through:

1. Starting a session with `pi_session_start`
2. The send → wait → assess → send loop
3. When to use `steer` vs `followUp`
4. How to use `pi_session_read` and `pi_session_wait`
5. Stopping cleanly with `pi_session_stop`

Includes three interaction patterns: full project build, iterative debugging, and multi-component interface.

---

## Configuration

The plugin has no configuration file. Behaviour is controlled entirely by pi's own settings (`~/.pi/agent/`) and by the parameters passed to each tool call.

### Using a non-default model

Pass `model` and `provider` to any tool:

```
pi_task(prompt="...", working_dir="/path", model="claude-opus-4-6", provider="anthropic")
pi_session_start(working_dir="/path", model="*sonnet*", provider="anthropic")
```

### Adjusting thinking depth

For complex algorithmic or architectural work:

```
pi_task(prompt="...", thinking="high")
pi_session_start(working_dir="/path", thinking="xhigh")
```

### Restricting pi's tools

Pi has `read`, `bash`, `edit`, `write`, `grep`, `find`, `ls`. To restrict:

```
pi_task(prompt="...", tools="read,grep,find,ls")   # read-only
```

### Custom system prompt

```
pi_task(prompt="...", append_system_prompt="Always write type annotations. Never use `any`.")
```

---

## Session persistence

When `persist_session=True` (the default), pi saves conversation state to `~/.pi/agent/sessions/hermes-<id>.json`. This lets a session be referenced again after a Hermes restart:

```
pi_session_start(working_dir="/path")
# ... do work ...
pi_session_stop(session_id="abc12345")
# Returns pi_session_file path

# Later — start a new session and reference the previous work
pi_session_start(working_dir="/path")
pi_session_send(session_id="new_id", message="Continue from the previous session. The files are in /path.")
```

---

## Example interaction

**User:** Build a CLI tool in ~/Projects/mytool that parses JSON logs and outputs summaries. Include filtering by log level and a `--since` flag. Add tests and a README.

**What happens:**

1. `pre_llm_call` fires — message matches `build` + target + multiple features → large project trigger → injects interactive session reminder
2. Hermes calls `skill_view("pi-interactive-session")`
3. Hermes calls `pi_session_start(working_dir="/home/user/Projects/mytool")`
4. Hermes calls `pi_session_send(session_id="abc12345", message="Scaffold a Python CLI project with src/, tests/, pyproject.toml. The tool will parse JSON log files.")`
5. Hermes waits for inject_message — pi creates the scaffold
6. Hermes sends the next instruction: `"Add the core parser in src/parser.py. Each log line is JSON with level, message, timestamp."`
7. … continues turn by turn until complete
8. Hermes calls `pi_session_stop(session_id="abc12345")`

---

## Development

The plugin is a plain Python package. No build step. Changes to files under `plugin/` take effect immediately on Hermes restart (the symlink points at the repo directory).

To test trigger detection without running Hermes:

```bash
cd ~/Projects/hermes-pi-bridge
python3 -c "
from plugin import _is_coding_request, _is_large_project
print(_is_coding_request('Add input validation to the signup endpoint'))
print(_is_large_project('Build a full-stack app from scratch'))
"
```

### Adding a tool

1. Add the schema to `schemas.py`
2. Add the handler to `tools.py`
3. Import and register both in `__init__.py` (in `register()`)
4. Add the tool name to `plugin.yaml` under `provides_tools`
