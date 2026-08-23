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

It does not replace Hermes' RPC server, native subagents, or provider transport APIs.

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

A `pi_flow` is an execution/orchestration method for one goal.

Therefore:

- do **not** create or switch profiles merely because a request should use pi;
- use `pi_flow` inside the current profile for ordinary per-goal delegation;
- create a dedicated profile only when you want a persistent specialist with separate state, for example a long-lived reverse-engineering/research agent with its own memory, model defaults, terminal cwd, plugin settings, and plugin set;
- when using a dedicated profile, install/enable `pi-bridge` in that profile and continue using `pi_flow` inside it.

Profiles do not sandbox filesystem access. Use `terminal.cwd` and an appropriate sandbox/backend separately when isolation matters.

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
| `pi_check` | Check local pi availability, effort routing, and async-delivery state |
| `pi_task` | Run one focused synchronous task |
| `pi_session_start` | Start a persistent pi RPC session |
| `pi_session_send` | Send one instruction to a session |
| `pi_session_read` | Read buffered session output |
| `pi_session_stop` | Stop a session |
| `pi_session_list` | List sessions |

There are intentionally only two execution modes:

- **one-shot** — `pi_task` for a focused phase that fits in one prompt;
- **persistent RPC** — a pi session for iterative, dependent, or steerable work.

Persistent Pi sessions survive normal Hermes turns and are cleaned up when the flow explicitly stops them or Hermes finalizes/resets the conversation.

## Profile-scoped model effort routing

The bridge does not hardcode model/provider IDs. Calls accept one semantic `effort` value:

- `fast` — mechanical, high-volume, easily verified work;
- `standard` — normal implementation/debugging;
- `deep` — ambiguous reasoning, competing hypotheses, cross-system correlation, or expensive-to-redo decisions.

The mapping lives in the official Hermes plugin settings for the active profile. Example:

```bash
hermes config set plugins.entries.pi-bridge.settings.fast_model "your-cheap-model-id"
hermes config set plugins.entries.pi-bridge.settings.fast_provider "your-provider"
hermes config set plugins.entries.pi-bridge.settings.standard_model "your-standard-model-id"
hermes config set plugins.entries.pi-bridge.settings.deep_model "your-strong-model-id"
hermes config set plugins.entries.pi-bridge.settings.deep_provider "your-provider"
```

For a named profile, prefix the same commands with `hermes -p <profile>` or use the profile alias.

Thinking defaults are `minimal` / `medium` / `high` for fast / standard / deep and may also be changed with `fast_thinking`, `standard_thinking`, and `deep_thinking` plugin settings.

Then Hermes normally passes only the semantic tier:

```text
pi_task(..., effort="fast")
pi_session_start(..., effort="deep")
```

Explicit `provider`, `model`, or `thinking` on a call always wins over the profile mapping. Blank mappings fall back to pi's own configured default. `pi_check` reports the current profile's effective mapping.

## Async completion and gateway security

Hermes distinguishes sessions that can deliver background completions from finite/stateless runtimes. `pi_session_send` follows that contract:

- interactive CLI and supported long-lived sessions may use persistent async Pi RPC;
- stateless API/one-shot contexts are refused and should use `pi_task` instead;
- messaging gateways require Hermes' explicit plugin grant before a background Pi completion may inject a new turn back into the originating chat.

For a profile that should allow persistent Pi flows from Telegram/Discord/etc.:

```bash
hermes config set plugins.entries.pi-bridge.allow_gateway_injection true
```

This is deliberately separate from plugin enablement. Without the grant, `pi_session_send` fails before promising a completion it cannot route.

Pi child processes use Hermes' filtered subprocess environment when available, following the same secret-boundary pattern as Hermes' first-party Codex app-server runtime: model/provider credentials may be inherited while Hermes-internal/gateway secrets are stripped.

## Repository layout

```text
plugin.yaml                 native Hermes plugin manifest
__init__.py                 native plugin entrypoint
plugin/
  __init__.py               registration + explicit pi_flow trigger
  schemas.py                tool schemas
  tools.py                  one-shot execution + profile routing/delivery checks
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
- Keep model/vendor choices in profile-scoped plugin settings, not repository logic.
- No domain-specific workflows baked into the plugin.
- No automatic takeover of every coding-looking request; `pi_flow` is explicit.
- No secrets in repository files or unfiltered child environments on current Hermes.
- No acceptance of worker claims without verification when verification is practical.
