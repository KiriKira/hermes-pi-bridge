# Hermes bootstrap entrypoint

This is the file Hermes should read when setting up `hermes-pi-bridge` on a machine/profile that may not have pi or the plugin installed yet.

## Goal

Prepare a working Hermes -> pi bridge using Hermes' official plugin lifecycle. After setup, a user can say:

```text
通过 pi_flow 去 <goal>
```

Hermes should load the bundled `pi-bridge:pi-flow` skill, create a goal-specific flow, delegate bounded execution to pi, review evidence, and adapt until the goal is verified or concretely blocked.

## Important architecture facts

Before installing anything, preserve these distinctions:

- Hermes ACP, TUI gateway JSON-RPC, and HTTP APIs are **server-side interfaces for external programs to drive Hermes**.
- Hermes' documented Pi-style RPC mapping maps Pi-like control concepts onto Hermes' TUI gateway; it does not make Hermes a generic Pi client.
- Hermes' Codex app-server runtime is a first-party, Codex-specific external-agent runtime. It is not a generic arbitrary-agent adapter.
- `hermes-pi-bridge` remains a normal third-party Hermes plugin that launches pi and speaks pi's own RPC protocol.
- A Hermes **profile** is an independent long-lived agent state/config boundary. `pi_flow` is a per-goal orchestration convention. Do not create/switch profiles merely because `pi_flow` was requested.

## Required order

### 1. Identify the target Hermes profile

Determine which profile should own the plugin.

Use the current/default profile unless the user explicitly wants a separate long-lived specialist with independent config, memory, SOUL, sessions, skills/plugins, gateway state, or model defaults.

Useful checks:

```bash
hermes profile
hermes profile list
```

If a named profile is intentionally selected, use `hermes -p <profile> ...` for all plugin/config/doctor commands below.

### 2. Inspect prerequisites

Run:

```bash
command -v hermes || true
command -v node || true
command -v npm || true
command -v pi || true
```

Requirements:

- Hermes Agent is already installed.
- Node.js/npm are needed only when pi is not already installed.

### 3. Install pi only when missing

If `pi --version` succeeds, keep the existing installation.

Otherwise run:

```bash
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
pi --version
```

Do not replace a working installation just to normalize versions.

### 4. Configure pi authentication/model access

Pi owns its provider authentication/model configuration. Inspect only presence/metadata; never print auth-file contents or secrets into chat/logs/commits.

```bash
ls -la ~/.pi/agent 2>/dev/null || true
pi --version
```

If pi still needs authentication, use pi's supported setup/login mechanism.

### 5. Install and enable the plugin using Hermes itself

Default profile:

```bash
hermes plugins install KiriKira/hermes-pi-bridge --enable
hermes plugins doctor pi-bridge --ci
```

Named profile:

```bash
hermes -p <profile> plugins install KiriKira/hermes-pi-bridge --enable
hermes -p <profile> plugins doctor pi-bridge --ci
```

Do not manually symlink the plugin, patch `toolsets`, or edit `plugins.enabled` by hand unless the official plugin command is unavailable and the user explicitly chooses a manual recovery path.

Hermes' plugin manager should own clone/install metadata, security scan, enablement, update semantics, skill namespacing, and profile scoping.

### 6. Optionally configure cost/model tiers in this profile

The bridge exposes semantic `fast`, `standard`, and `deep` effort levels. Their mappings live in Hermes' official profile-scoped plugin settings.

Only set mappings the user actually wants. Blank provider/model values mean: let pi use its own configured default.

Example:

```bash
hermes config set plugins.entries.pi-bridge.settings.fast_provider "<provider>"
hermes config set plugins.entries.pi-bridge.settings.fast_model "<cheap-model>"
hermes config set plugins.entries.pi-bridge.settings.standard_model "<normal-model>"
hermes config set plugins.entries.pi-bridge.settings.deep_provider "<provider>"
hermes config set plugins.entries.pi-bridge.settings.deep_model "<strong-model>"
```

For a named profile, prefix each command with `hermes -p <profile>` or use the profile alias.

Default thinking depths are:

- `fast`: `minimal`
- `standard`: `medium`
- `deep`: `high`

They can be overridden with `fast_thinking`, `standard_thinking`, and `deep_thinking` in the same settings subtree.

Do not invent provider/model IDs. If the user has not chosen mappings, leave them blank.

### 7. Decide whether gateway async completion is needed

Persistent `pi_session_*` flows return results asynchronously. Hermes only supports that promise on channels that can deliver a later completion.

- Interactive CLI/TUI-style long-lived sessions can use persistent Pi sessions normally.
- Stateless/one-shot/API runtimes should use synchronous `pi_task` phases instead.
- Messaging gateways such as Telegram/Discord/Slack require Hermes' explicit plugin injection grant before Pi completion may wake the originating chat.

If the user wants persistent Pi flows from a messaging gateway, explicitly configure the target profile:

```bash
hermes config set plugins.entries.pi-bridge.allow_gateway_injection true
```

Do not enable that grant merely because the plugin is installed. It is a separate operator choice.

### 8. Restart the Hermes session and verify the bridge

Start a fresh Hermes session in the target profile, then run/call:

```text
pi_check()
```

Minimum expected state:

- `installed: true`;
- a pi version is reported;
- plugin registration succeeds;
- `effort_routing` reflects this profile's intended mappings/defaults;
- async/gateway delivery state matches the current surface;
- the bundled skill is available as `pi-bridge:pi-flow`.

Then run a harmless one-shot smoke test in a disposable directory:

```text
pi_task(
  prompt="List the files in this directory. Do not modify anything.",
  working_dir="/tmp",
  tools="read,grep,find,ls",
  effort="fast"
)
```

### 9. Verify the pi_flow contract

Ask Hermes something containing the explicit token `pi_flow`, for example:

```text
通过 pi_flow 去检查这个项目的测试为什么失败
```

Hermes should load:

```text
skill_view("pi-bridge:pi-flow")
```

Then it should create the minimum flow needed for that specific goal rather than loading a fixed domain workflow or switching profiles automatically.

## Profiles: when they are appropriate

Use a dedicated profile when persistent specialization is desired, for example:

```bash
hermes profile create re --description "Reverse-engineering and protocol research specialist using pi workers"
re setup
re plugins install KiriKira/hermes-pi-bridge --enable
```

That gives the specialist its own Hermes config, memory, SOUL, sessions, skills/plugins, gateway state, plugin settings, and model defaults. It does **not** sandbox filesystem access by itself; set `terminal.cwd` and an appropriate terminal/sandbox backend separately when isolation matters.

For a specialist profile, it is reasonable to put a standing instruction in that profile's `SOUL.md`, for example:

```text
For hands-on reverse-engineering or protocol-research tasks, use the pi-bridge:pi-flow skill and Pi workers unless I explicitly ask otherwise. Keep Hermes responsible for planning, evidence review, and verification.
```

That makes the profile itself carry the specialization, so the user can simply say `逆向这个 IoT 的本地协议` instead of repeating `通过 pi_flow` every time. The underlying per-goal orchestration is still `pi_flow`; the profile does not replace the bridge.

## Completion criteria

Bootstrap is complete when:

1. `pi --version` works.
2. Pi has usable provider/model access.
3. `hermes plugins doctor pi-bridge --ci` succeeds for the target profile.
4. `pi_check()` reports pi installed and the expected profile routing/delivery policy.
5. Hermes can invoke `pi_task` successfully.
6. `pi-bridge:pi-flow` is visible.
7. An explicit `pi_flow` request loads the namespaced skill without changing profiles automatically.
8. If messaging-gateway persistent sessions are intended, the gateway-injection grant was an explicit operator choice.
