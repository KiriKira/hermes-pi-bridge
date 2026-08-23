---
name: pi-flow
description: Create and run a goal-specific workflow with Hermes as supervisor and pi as execution worker
version: 1.2.0
author: hermes-pi-bridge
license: MIT
metadata:
  hermes:
    tags: [pi, flow, orchestration, delegation, workflow]
    requires_tools: [pi_check, pi_task, pi_session_start, pi_session_send, pi_session_read, pi_session_stop, pi_session_list]
---

# pi-flow

Use this skill when the user explicitly asks to accomplish a goal through `pi_flow`, `pi-flow`, or `pi flow`.

`pi_flow` is an invocation-level orchestration method, not a fixed domain workflow and not a Hermes profile. Create the workflow needed for the current goal at runtime.

## Roles

- **Hermes is the supervisor.** Interpret the goal, decompose work, choose execution modes and model effort, review evidence, verify results, and decide when to stop or escalate.
- **pi is the execution worker.** Read files, run commands, edit artifacts, test hypotheses, and report concrete results.

Do not delegate the final supervisory judgment when Hermes can verify the result independently.

## 1. Define the goal

Translate the request into:

- `objective`: desired end state;
- `done`: observable completion criteria;
- `working_dir`: where pi should operate;
- `constraints`: actions or areas that must not be changed without approval;
- `inputs`: files, repositories, logs, services, devices, or other resources;
- `verification`: how Hermes can establish that the goal is complete.

If work can safely start while a detail is unknown, record it as an open question instead of blocking the entire flow.

## 2. Build the minimum useful flow

Create only the ordered phases needed to reach `done`. Each phase should have one clear outcome.

For each phase track:

| Field | Meaning |
|---|---|
| `id` | short phase name |
| `objective` | what this phase must establish or produce |
| `depends_on` | earlier phases required first |
| `mode` | `task` or `session` |
| `effort` | `fast`, `standard`, or `deep` |
| `artifacts` | expected files/results/evidence |
| `verify` | concrete completion check |

Do not add phases merely to make the plan look comprehensive. Remove or change phases when evidence invalidates the initial plan.

## 3. Choose one-shot vs persistent RPC

Use `pi_task` when the phase is focused, can be specified completely in one prompt, and its result can be checked immediately.

Use `pi_session_start` when later work depends on discoveries from earlier work, iterative debugging/experimentation is expected, or Hermes expects to steer pi over several turns.

For a persistent session:

1. `pi_session_start`
2. `pi_session_send`
3. wait for the bridge completion notification
4. assess and verify the result
5. send another instruction only when needed
6. `pi_session_stop` when the phase/flow is complete

Never stack prompts into a busy session. Persistent pi sessions are allowed to survive ordinary Hermes turns; they are cleaned up explicitly by the flow or when the Hermes conversation is finalized/reset.

## 4. Route model effort through the current Hermes profile

Hermes decides how much capability a phase deserves. The bridge resolves the semantic tier through **this profile's** `pi-bridge` plugin settings, so different profiles may use different Pi model/cost policies without changing this skill.

At the start of a flow, call `pi_check` when the routing is not already known. Its `effort_routing` field reports the effective `fast` / `standard` / `deep` mappings for the current profile.

- **fast** — high-volume, mechanical, easily checked work: search, inventory, extraction, formatting, known commands, straightforward data collection.
- **standard** — normal implementation/debugging: scripts, adapters, ordinary code changes, tests, clear multi-file work.
- **deep** — reserve for ambiguous architecture/protocol reasoning, several plausible hypotheses, subtle repeated failures, cross-system correlation, or high-impact decisions that are expensive to redo.

Normally pass only the semantic tier:

```text
pi_task(..., effort="fast")
pi_session_start(..., effort="standard")
```

The bridge applies profile-scoped `provider`, `model`, and `thinking` defaults. An explicit `provider`, `model`, or `thinking` passed on a particular call overrides that tier's configured value.

Start with the cheapest tier that plausibly fits. Escalate only on material signals such as contradictory evidence, low confidence on an important conclusion, repeated failure after obvious execution errors are corrected, or unresolved competing hypotheses. A bad path, missing binary, dependency error, or malformed command is an execution problem and is not by itself a reason to buy a stronger model.

If provider/model mappings are blank, pi uses its own configured default. Never invent provider/model identifiers merely to satisfy a tier label.

## 5. Give pi bounded phase prompts

A useful phase prompt contains:

```text
[OBJECTIVE]
What this phase must accomplish.

[CONTEXT]
Relevant facts, paths, previous evidence, and constraints.

[WORK]
What pi should inspect/change/run. Avoid unnecessary implementation prescription.

[OUTPUT]
What artifacts or findings must be produced.

[VERIFY]
Exact checks to run before claiming completion.

[REPORT]
Return status, evidence, changed artifacts, verification, confidence, blockers, and suggested next step.
```

For persistent sessions, do not resend the entire history each turn. Send the new objective and newly relevant evidence.

## 6. Require evidence

Treat pi's response as worker output, not proof. Prefer reports with:

```text
STATUS: done | partial | blocked | needs_escalation
RESULT: concise outcome
EVIDENCE: commands, paths, outputs, observations, or tests
CHANGED: modified artifacts, or none
VERIFICATION: checks run and their results
CONFIDENCE: high | medium | low
BLOCKERS: unresolved issues, or none
NEXT: suggested next action
```

Hermes should independently inspect or repeat verification when practical.

## 7. Adapt continuously

After each phase Hermes may complete it, retry with corrected context, split it, remove it, add a newly required phase, increase/decrease model effort, or stop because the goal is satisfied or blocked under current constraints.

The initial flow is a hypothesis about the work, not a contract.

## 8. Profiles are optional specialization, not flow invocation

Hermes profiles isolate an entire agent's config, memory, skills, sessions, plugins, gateway state, and personality. Do **not** create or switch profiles merely because the user said `pi_flow`.

A dedicated profile is appropriate only when the user wants a persistent specialist with separate state — for example a long-lived reverse-engineering/research agent with its own memory, model defaults, terminal cwd, plugin settings, and plugin set. In that case install/enable `pi-bridge` in that profile, configure its effort mappings there, and still use `pi_flow` inside the profile for each concrete goal.

Profiles do not sandbox filesystem access by themselves; use Hermes terminal working-directory/sandbox settings when isolation matters.

## 9. Finish cleanly

A pi_flow is complete only when:

- the user's `done` criteria are met or a concrete blocker is established;
- verification has been performed where practical;
- active pi sessions created for the flow are stopped;
- Hermes reports the result, evidence, important artifacts, and unresolved limitations concisely.

**Hermes plans and judges. pi executes. Evidence advances the flow.**
