---
name: pi-task-delegation
description: Delegate focused coding and analysis tasks to pi coding agent
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [delegation, pi, coding, implementation, refactor, debugging, testing, analysis]
    requires_tools: [pi_task, pi_task_async]
    related_skills: [pi-interactive-session, pi-bootstrap, pi-reverse-engineering-flow]
---

# Pi Task Delegation

## Overview

Hermes orchestrates. pi executes.

Pi is a model-agnostic terminal coding agent with filesystem and shell tools. The bridge can select provider/model/thinking per task, so do not assume a specific local or cloud model.

Use `pi_task` for focused, well-defined work where a single prompt is enough. Use `pi_session_start` for large multi-phase projects. For authorized reverse engineering, load `pi-reverse-engineering-flow` before delegating.

## Model-tier routing

If `~/.hermes/pi-bridge-models.yaml` exists, read it before choosing a worker model. Use the cheapest suitable tier:

| Tier | Typical work |
|---|---|
| fast | search, grep, inventory, formatting, straightforward extraction |
| code | implementation, scripts, parsers, tests, debugging |
| deep | difficult reasoning, conflicting evidence, protocol/crypto/state-machine analysis |

Pass non-empty `provider`, `model`, and `thinking` values from that tier to the tool call. If provider/model are blank, let pi use its configured default. Escalate only when justified by evidence or failure.

## When to Delegate

### Use pi_task when

- one focused change or analysis task;
- a specific bug fix;
- a well-scoped feature;
- tests for known code;
- a single-file/small refactor;
- a bounded read/search/extract task.

### Use pi_session_start instead when

- multiple components or phases are involved;
- the user asks to continue until done;
- the next step depends on reviewing the previous result;
- the scope is exploratory;
- reverse engineering requires repeated hypothesis/experiment cycles.

## Step 1 — Gather Context

Before calling `pi_task`, collect:

1. `working_dir` — use an absolute path when project files are involved;
2. relevant files/artifacts and what they represent;
3. constraints — language/version/framework/safety scope;
4. verification — a command, observable result, or evidence requirement.

For reverse engineering, do not paste bulk decompiler output into Hermes when pi can inspect it directly and return an evidence-backed summary.

## Step 2 — Choose Sync vs Async

Use `pi_task` for bounded tasks. Use `pi_task_async` only when background execution is genuinely useful and the surrounding Hermes environment supports the completion notification flow. For an iterative project, prefer an interactive RPC session instead of repeatedly launching disconnected async tasks.

## Step 3 — Choose Thinking/Model Tier

Start cheap and escalate:

- straightforward extraction/search -> fast;
- implementation/debugging -> code;
- difficult ambiguity/cross-layer reasoning -> deep.

Do not spend a deep model on bulk grep, file listing, or formatting.

## Step 4 — Construct the Prompt

Include four parts:

```text
[TASK]
One clear outcome.

[CONTEXT]
- Working directory/artifacts
- Relevant files and prior findings
- Framework/tooling/environment
- Authorization/safety scope if applicable

[REQUIREMENTS]
- Explicit completion conditions
- Constraints
- Required evidence or files to update

[VERIFICATION]
- Exact command/test/experiment or evidence standard
```

For research tasks, also request this result contract when useful:

```text
CONFIDENCE: high|medium|low
FINDINGS:
EVIDENCE:
OPEN_QUESTIONS:
BLOCKERS:
RECOMMENDED_NEXT_STEP:
REQUEST_ESCALATION: none|code|deep
```

## Step 5 — Call pi_task

Example:

```python
pi_task(
    prompt="<structured prompt>",
    working_dir="/absolute/path",
    provider="<tier provider if non-empty>",
    model="<tier model if non-empty>",
    thinking="<tier thinking if configured>",
)
```

Omit provider/model instead of inventing values when a tier leaves them blank.

## Step 6 — Assess the Output

Check:

- Did pi actually complete the requested work?
- Does the result address every requirement?
- Is verification present and credible?
- For research, are conclusions tied to evidence rather than asserted?
- Are there TODOs/placeholders/unresolved errors?
- Is confidence low or escalation requested?

Then choose: accept, send a focused follow-up, correct direction, escalate tier, or switch to an interactive session.

## Red Flags

- vague delegation without artifacts/context;
- accepting output without verification;
- using an expensive model for bulk mechanical work;
- using one-shot tasks for a hypothesis/experiment loop;
- assuming a specific pi model is installed;
- exposing credentials/secrets in prompts or repository files.

Pi executes. Hermes judges. The user gets verified results.
