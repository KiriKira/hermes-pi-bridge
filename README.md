# hermes-pi-bridge

A small bridge that lets Hermes supervise work executed by the [pi agent harness](https://github.com/earendil-works/pi).

**Hermes plans and judges. pi executes.**

The bridge deliberately avoids tying itself to a particular model, provider, project type, or domain workflow.

## pi_flow

`pi_flow` is the stable high-level convention provided by this repository.

When the user says something such as:

```text
通过 pi_flow 去修复这个项目的测试
通过 pi_flow 去分析这些日志并找出根因
通过 pi_flow 去实现这个功能并验证它
```

The plugin detects the explicit `pi_flow` token and tells Hermes to load the `pi-flow` skill.

That skill does **not** contain a fixed workflow. Hermes creates a flow for the current goal by defining completion criteria, ordered phases, execution mode, model tier, expected artifacts, and verification. Hermes can adapt or discard phases as evidence changes.

Reusable flows may be saved under `~/.hermes/pi-flows/`, but new domains do not require new Hermes skills.

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

- **one-shot:** use `pi_task` for a focused phase that fits in one prompt;
- **persistent:** use an RPC session for iterative or multi-phase work.

Long work does not need a second background-task subsystem; a persistent RPC session already provides state, steering, and completion notifications.

## Model routing

The installer creates `~/.hermes/pi-flow.yaml` if it does not exist.

It provides optional semantic slots:

- `fast` — cheap/high-throughput work that is easy to verify;
- `standard` — normal implementation/debugging;
- `deep` — difficult ambiguous reasoning.

Provider and model values are blank by default. Hermes must not invent model IDs. Blank values mean pi should use its configured default.

The `pi-flow` skill uses a cheapest-suitable-then-escalate policy: execution mistakes such as a bad path or missing dependency stay on the current tier; stronger models are reserved for low-confidence material conclusions, contradictory evidence, unresolved hypotheses, or repeated reasoning failure.

## Requirements

- Hermes Agent
- Python 3.9+
- pi coding agent
- Node.js/npm only if pi still needs to be installed

Current pi package:

```bash
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
```

Pi authentication and provider configuration remain owned by pi under `~/.pi/agent/` and its supported login/provider mechanisms. This repository does not store provider secrets.

## Bootstrap

For a Hermes-readable first-time setup procedure, start with:

```text
HERMES_BOOTSTRAP.md
```

Manual installation:

```bash
git clone https://github.com/KiriKira/hermes-pi-bridge.git
cd hermes-pi-bridge
bash install.sh --install-pi
```

If pi is already installed:

```bash
bash install.sh
```

The installer:

1. links `plugin/` to `~/.hermes/plugins/pi-bridge`;
2. links `skill/SKILL_FLOW.md` as the `pi-flow` Hermes skill;
3. creates `~/.hermes/pi-flow.yaml` from the generic template only when absent;
4. creates `~/.hermes/pi-flows/` for optional reusable flows;
5. adds `pi_bridge` next to the existing `hermes-cli` toolset entry when that can be done safely.

Restart Hermes after installation, then run `pi_check()`.

## How Hermes runs a flow

At runtime Hermes should:

1. translate the request into an objective, done criteria, constraints, inputs, working directory, and verification;
2. create the minimum ordered phases needed for that goal;
3. choose one-shot or persistent execution per phase;
4. choose `fast`, `standard`, or `deep` routing without hardcoding model names;
5. delegate bounded work to pi;
6. review evidence and independently verify important results;
7. adapt the remaining phases when new evidence changes the plan;
8. stop all sessions and report the verified outcome or concrete blocker.

See `skill/SKILL_FLOW.md` for the full contract.

## Repository layout

```text
HERMES_BOOTSTRAP.md       first-time instructions for Hermes
install.sh                idempotent installer
config/
  pi-flow.example.yaml    generic optional model routing
plugin/
  __init__.py             registration + explicit pi_flow trigger
  plugin.yaml             plugin manifest
  schemas.py              tool schemas
  tools.py                one-shot tools and RPC wrappers
  rpc_session.py          persistent pi RPC lifecycle
skill/
  SKILL_FLOW.md           generic runtime flow creation/orchestration
```

## Design constraints

- No model/vendor assumptions in workflow logic.
- No domain-specific skills in this repository.
- No automatic takeover of every coding-looking user request; `pi_flow` is explicit.
- No API keys or captured credentials in repository/config files.
- No acceptance of worker claims without verification when verification is practical.
