# Hermes bootstrap entrypoint

This is the file Hermes should read when setting up this repository on a machine that may not have pi or the bridge installed yet.

## Goal

Prepare a working Hermes -> pi bridge and make `pi_flow` available as the stable high-level workflow convention.

After setup, a user should be able to say:

```text
通过 pi_flow 去 <goal>
```

Hermes should then load the `pi-flow` skill, create a goal-specific flow, delegate execution to pi, review evidence, and adapt the flow until the goal is verified or blocked.

## Required order

### 1. Inspect prerequisites

Run:

```bash
command -v node || true
command -v npm || true
command -v python3 || true
command -v hermes || command -v hermes-cli || true
command -v pi || true
```

Requirements:

- Hermes Agent is already installed.
- Python 3.9+ is available for the bridge and installer helpers.
- Node.js/npm are needed only when pi is not already installed.

### 2. Install pi only when missing

If `pi --version` works, keep the existing installation.

Otherwise run:

```bash
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
pi --version
```

Do not replace an existing working pi installation merely to normalize versions.

### 3. Configure pi model/provider access

Pi owns its provider authentication and model configuration under `~/.pi/agent/` and through its supported login/provider mechanisms.

Inspect configuration presence without printing secrets:

```bash
ls -la ~/.pi/agent 2>/dev/null || true
pi --version
```

If pi still needs authentication, use pi's supported authentication flow. Never print API keys, tokens, or auth-file contents into chat, logs, commits, or this repository.

The bridge is model-agnostic. It passes `provider`, `model`, and `thinking` only when Hermes intentionally supplies them.

### 4. Install the bridge

From this repository run:

```bash
bash install.sh
```

Or let the installer install pi too when it is missing:

```bash
bash install.sh --install-pi
```

The installer provides:

- `~/.hermes/plugins/pi-bridge` — the bridge plugin;
- `~/.hermes/skills/software-development/pi-flow/SKILL.md` — the only operational skill;
- `~/.hermes/pi-flow.yaml` — model-routing preferences, created only when absent;
- `~/.hermes/pi-flows/` — optional library for reusable flows.

It also enables the `pi_bridge` toolset when it can identify the relevant Hermes config entry safely.

### 5. Configure optional model routing

Read:

```text
~/.hermes/pi-flow.yaml
```

It defines three semantic tiers:

- `fast` — cheap/high-throughput work that is easy to verify;
- `standard` — normal implementation and debugging;
- `deep` — difficult ambiguous reasoning where stronger models may materially improve the result.

Provider/model fields are intentionally blank by default. Blank fields mean: use pi's configured default. Do not invent model IDs.

Hermes should start with the cheapest tier that plausibly fits and escalate only when there is evidence that stronger reasoning is needed.

### 6. Restart Hermes and verify

Restart Hermes so the plugin and skill are loaded. Then call:

```text
pi_check()
```

Minimum expected state:

- `installed: true`;
- a pi version is reported;
- the `pi_bridge` toolset loads without an import error.

Then run a harmless one-shot smoke test in a disposable directory:

```text
pi_task(
  prompt="List the files in this directory. Do not modify anything.",
  working_dir="/tmp",
  tools="read,grep,find,ls"
)
```

### 7. Verify the pi_flow contract

Ask Hermes something containing the explicit token `pi_flow`, for example:

```text
通过 pi_flow 去检查这个项目的测试为什么失败
```

Hermes must load:

```text
skill_view("pi-flow")
```

The skill will instruct Hermes to create a flow for that specific goal rather than loading a fixed domain workflow.

## Completion criteria

Bootstrap is complete when:

1. `pi --version` works.
2. Pi has usable provider/model access.
3. `pi_check()` reports pi installed.
4. Hermes can invoke `pi_task` successfully.
5. `pi-flow` is visible to Hermes.
6. `~/.hermes/pi-flow.yaml` exists and contains no secrets.
7. An explicit `pi_flow` request causes Hermes to load the generic flow skill.
