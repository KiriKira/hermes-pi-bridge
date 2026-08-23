# hermes-pi-bridge

A standalone Hermes plugin that lets Hermes supervise work executed by the [pi agent harness](https://github.com/earendil-works/pi).

**Hermes plans and judges. pi executes.**

The bridge is intentionally model-agnostic and domain-agnostic.

## Why this plugin still exists

Hermes already has several official RPC/integration surfaces, but they solve different directions of integration:

- **ACP / TUI gateway JSON-RPC / HTTP API** let external programs drive Hermes.
- Hermes documents a **Pi-style RPC mapping** for its own TUI gateway, so Pi-like clients can map concepts such as prompt, steer, abort, state, history, and session branching onto Hermes.
- Hermes also has a first-party **Codex app-server runtime** where Hermes delegates an entire turn/tool loop to Codex over stdio JSON-RPC.

None of those currently provide a generic built-in client that launches and supervises an arbitrary external agent such as pi. This plugin fills that narrower gap by speaking pi's own `--mode rpc` protocol from a normal Hermes plugin.

It does not replace Hermes' RPC server or provider transport APIs.

## pi_flow

`pi_flow` is the stable high-level convention exposed by this plugin.

Example:

```text
通过 pi_flow 去逆向这个 IoT 的本地协议
通过 pi_flow 去修复这个项目并验证测试
通过 pi_flow 去研究这些日志并找出根因
```

The plugin recognizes the explicit `pi_flow` token and nudges Hermes to load the bundled namespaced skill:

```text
pi-bridge:pi-flow
```

The skill is not a fixed domain workflow. Hermes creates the minimum goal-specific flow at runtime, chooses one-shot versus persistent RPC execution, assigns model effort, reviews evidence, and adapts the flow as new information appears.

## Profiles vs pi_flow

A Hermes **profile** is an independent agent home: its own config, API keys, SOUL, memories, sessions, skills, plugins, gateway state, and model defaults.

A `pi_flow` is only an execution/orchestration mode for one goal.

Therefore:

- do **not** create or switch profiles merely because a request should use pi;
- use `pi_flow` inside the current profile for ordinary per-goal delegation;
- create a dedicated profile only when you want a persistent specialist with separate state, for example a long-lived reverse-engineering/research agent with its own memory, model defaults, terminal cwd, and plugin set;
- when using a dedicated profile, install/enable `pi-bridge` in that profile and continue using `pi_flow` inside it.

## Official Hermes installation path

This repository is structured as a native standalone Hermes plugin and should be installed through Hermes' plugin manager:

```bash
hermes plugins install KiriKira/hermes-pi-bridge --enable
hermes plugins doctor pi-bridge --ci
```

Plugins are profile-scoped. To install into a named profile:

```bash
hermes -p <profile> plugins install KiriKira/hermes-pi-bridge --enable
hermes -p <profile> plugins doctor pi-bridge --ci
```

Hermes' plugin manager handles cloning, security scanning, enablement, update metadata, profile scoping, and the plugin lifecycle. This repository deliberately does not patch `config.yaml` or symlink itself into `~/.hermes/plugins`.

After installation, restart the Hermes session so the plugin is loaded.

## pi dependency

`pi` is a separate external CLI and is not installed by Hermes' Python plugin manager.

Check first:

```bash
pi --version
```

If it is missing:

```bash
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
```

Configure/authenticate pi through pi's own supported mechanisms. Do not store provider credentials in this repository.

## Execution primitives

The plugin exposes seven tools:

| Tool | Purpose |
|---|---|
| `pi_check` | Check local pi availability/config state |
| `pi_task` | Run one focused synchronous task |
| `pi_session_start` | Start a persistent pi RPC session |
| `pi_session_send` | Send one instruction to a session |
| `pi_session_read` | Read buffered session output |
| `pi_session_stop` | Stop a session |
| `pi_session_list` | List sessions |

There are intentionally only two execution modes:

- **one-shot** — `pi_task` for a focused phase that fits in one prompt;
- **persistent RPC** — a pi session for iterative, dependent, or steerable work.

The plugin does not add a second background-task subsystem because persistent RPC already provides state and steering.

## Model effort routing

The bridge does not hardcode model/provider IDs.

The bundled skill uses three semantic effort levels:

- `fast` — mechanical, high-volume, easily verified work;
- `standard` — normal implementation/debugging;
- `deep` — ambiguous reasoning, competing hypotheses, cross-system correlation, or expensive-to-redo decisions.

If the user/profile has explicit pi model mappings, Hermes may pass them to `pi_task` or `pi_session_start`. Otherwise it should omit `provider`/`model` and let pi use its configured default. Hermes should never invent model IDs merely to satisfy a tier label.

## Repository layout

```text
plugin.yaml                 native Hermes plugin manifest
__init__.py                 native plugin entrypoint
plugin/
  __init__.py               registration + explicit pi_flow trigger
  schemas.py                tool schemas
  tools.py                  one-shot execution + wrappers
  rpc_session.py            persistent pi RPC lifecycle
skills/
  pi-flow/
    SKILL.md                 bundled namespaced orchestration skill
after-install.md            instructions rendered by Hermes after install
HERMES_BOOTSTRAP.md         first-time operator/agent bootstrap sequence
tests/
  test_bridge.py            retained bridge contract tests
```

## Design constraints

- Follow Hermes' native plugin lifecycle instead of patching core config.
- No model/vendor assumptions in orchestration logic.
- No domain-specific workflows baked into the plugin.
- No automatic takeover of every coding-looking request; `pi_flow` is explicit.
- No secrets in repository files.
- No acceptance of worker claims without verification when verification is practical.
