# Hermes bootstrap entrypoint

This file is intentionally written as an instruction page for a Hermes Agent that has access to this repository but may not yet have pi or the pi bridge installed.

## Goal

Prepare a repeatable Hermes -> pi setup, verify it, and make the reverse-engineering workflow available to Hermes.

## Safety boundary

Use the reverse-engineering workflow only on software, devices, accounts, and networks you own or are explicitly authorized to test. Prefer interoperability and local-control research. Do not use captured credentials or secrets belonging to other users.

## Required order

Hermes should execute these stages in order and stop on a failed stage rather than guessing.

### 1. Inspect prerequisites

Check:

```bash
command -v node || true
command -v npm || true
command -v python3 || true
command -v hermes || command -v hermes-cli || true
command -v pi || true
```

Requirements:

- Hermes Agent is already installed.
- Python 3.9+ is available.
- Node.js/npm are required only if pi is not already installed.

### 2. Install pi when missing

If `pi --version` succeeds, keep the existing installation even if it came from the legacy package namespace.

Otherwise install the current package:

```bash
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
pi --version
```

Do not overwrite pi authentication files. The older `@mariozechner/pi-coding-agent` package was renamed/deprecated; an existing working `pi` binary can still be used, but new installs should use `@earendil-works/pi-coding-agent`.

### 3. Configure pi authentication/model access

Pi owns its provider authentication and model configuration under `~/.pi/agent/`.

First inspect without printing secrets:

```bash
ls -la ~/.pi/agent 2>/dev/null || true
pi --version
```

If pi is not authenticated/configured, ask the user which provider/model they want to use, then use pi's supported provider setup. Prefer Pi's interactive `/login` flow for supported subscription/provider authentication. Never echo API keys into chat, logs, commits, or repository files.

The bridge is model-agnostic: every task/session can pass `provider`, `model`, and `thinking` explicitly.

### 4. Install this bridge and its skills

From this repository:

```bash
bash install.sh
```

Or, if pi is missing and npm is available:

```bash
bash install.sh --install-pi
```

This installs/symlinks:

- the `pi-bridge` Hermes plugin;
- `pi-task-delegation`;
- `pi-interactive-session`;
- `pi-bootstrap`;
- `pi-reverse-engineering-flow`;
- a model-tier config template at `~/.hermes/pi-bridge-models.yaml` if none exists.

### 5. Configure model tiers

Open:

```text
~/.hermes/pi-bridge-models.yaml
```

The file defines three semantic tiers:

- `fast`: cheap/high-throughput work such as grep, JADX searches, strings triage, pcap field extraction, formatting, and documentation updates.
- `code`: implementation work such as Frida hooks, parsers, mitmproxy addons, Python PoCs, tests, and Home Assistant integration code.
- `deep`: expensive reasoning for protocol state machines, cryptographic/key-flow analysis, obfuscation, native/managed/network correlation, contradictory evidence, and repeated failed hypotheses.

Hermes should read this file before starting a reverse-engineering flow and pass the selected tier's provider/model/thinking values to `pi_task` or `pi_session_start`.

If a tier is left blank, fall back to pi's configured default rather than inventing a model name.

### 6. Restart Hermes and verify the bridge

Restart Hermes so the plugin and skills are loaded. Then call:

```text
pi_check()
```

Expected minimum state:

- `installed: true`
- a pi version is reported
- no bridge import error

Then run a read-only smoke test in a disposable directory:

```text
pi_task(
  prompt="List the files in this directory and report what you see. Do not modify anything.",
  working_dir="/tmp",
  tools="read,grep,find,ls"
)
```

### 7. Load the reverse-engineering workflow

For an authorized reverse-engineering/local-IoT task, Hermes must load:

```text
skill_view("pi-reverse-engineering-flow")
```

Then follow that skill's phase ordering, evidence contract, model escalation rules, and workspace layout.

## Completion criteria

Bootstrap is complete only when all of the following are true:

1. `pi --version` works.
2. Pi has a usable model/provider configuration.
3. `pi_check()` reports pi installed.
4. Hermes can call a pi bridge tool successfully.
5. `pi-bootstrap` and `pi-reverse-engineering-flow` are visible to Hermes.
6. `~/.hermes/pi-bridge-models.yaml` exists and contains no secrets.
