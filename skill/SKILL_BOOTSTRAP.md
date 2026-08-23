---
name: pi-bootstrap
description: Install, configure, and verify pi plus the Hermes pi bridge in a safe repeatable order
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [pi, bootstrap, install, configuration, delegation]
    related_skills: [pi-task-delegation, pi-interactive-session, pi-reverse-engineering-flow]
---

# Pi Bootstrap

Use this skill when pi or the bridge is not yet ready, or when the user asks Hermes to configure the Hermes -> pi stack.

## Rules

- Follow the stages in order.
- Do not overwrite existing pi auth/config files without explicit user approval.
- Never print, store, commit, or echo API keys/tokens.
- If provider authentication requires a secret, ask the user to enter it through the provider/pi mechanism rather than sending it through Hermes.
- Do not guess model IDs. If a model tier is blank, allow pi to use its default.
- Preserve an existing working `pi` installation; only use the package installer when `pi` is missing.

## Stage 1 — Inspect

Run:

```bash
command -v node || true
command -v npm || true
command -v python3 || true
command -v pi || true
pi --version 2>/dev/null || true
```

If pi exists, do not reinstall it just to normalize the environment.

## Stage 2 — Install pi if missing

Require npm. Use the current package namespace:

```bash
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
pi --version
```

The old `@mariozechner/pi-coding-agent` package was renamed/deprecated. Existing installations may continue to provide a valid `pi` binary; new installs should use `@earendil-works/pi-coding-agent`.

Stop and report the exact error if installation fails.

## Stage 3 — Verify pi configuration without exposing secrets

Inspect only file presence/metadata:

```bash
ls -la ~/.pi/agent 2>/dev/null || true
```

Do not `cat` auth files into the conversation.

If pi is not configured for a provider/model, ask the user which provider they want and guide them through pi's supported authentication flow. Prefer Pi's interactive `/login` mechanism for supported subscription/provider logins.

## Stage 4 — Install bridge

From the hermes-pi-bridge repository:

```bash
bash install.sh
```

If pi is missing and npm is available, `bash install.sh --install-pi` may perform Stage 2 and Stage 4 together.

The installer should be idempotent.

## Stage 5 — Configure model tiers

Read `~/.hermes/pi-bridge-models.yaml`.

Interpret tiers semantically:

| Tier | Use for |
|---|---|
| fast | search, grep, strings, JADX triage, pcap extraction, formatting, notes |
| code | scripts, parsers, Frida hooks, mitmproxy addons, PoCs, tests, HA code |
| deep | state-machine reasoning, crypto/key flow, obfuscation, native/managed/network correlation, contradictory evidence |

When invoking pi, pass the selected tier's non-empty values to `provider`, `model`, and `thinking`.

Escalation rule: start at the cheapest tier that plausibly fits; escalate only when the worker reports low confidence, unresolved blockers, contradictory evidence, or repeated failure.

## Stage 6 — Restart and smoke-test Hermes

After plugin installation, restart Hermes so new tools/skills are loaded.

Then call `pi_check()`.

Run a read-only smoke test with `tools="read,grep,find,ls"` before allowing write-capable delegation.

## Stage 7 — Reverse-engineering readiness

For authorized RE/local-IoT work, load:

```text
skill_view("pi-reverse-engineering-flow")
```

Do not invent a custom RE process before loading that skill; it defines the shared workspace, phase ordering, evidence format, and cost-aware model routing.

## Completion checklist

- [ ] pi binary works
- [ ] provider/model access is usable
- [ ] bridge plugin is installed
- [ ] `pi_check()` succeeds
- [ ] model-tier config exists
- [ ] reverse-engineering skill is installed
- [ ] no secrets were added to repository files or chat logs
