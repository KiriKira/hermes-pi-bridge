---
name: pi-flow
description: Create and run a goal-specific workflow with Hermes supervising work delegated to pi
version: 1.1.0
author: hermes-pi-bridge
license: MIT
metadata:
  hermes:
    tags: [pi, flow, orchestration, delegation, workflow]
    requires_tools: [pi_check, pi_task, pi_session_start, pi_session_send, pi_session_read, pi_session_stop, pi_session_list]
---

# pi-flow

Use this skill when the user explicitly asks to accomplish a goal through `pi_flow`, `pi-flow`, or `pi flow`.

`pi_flow` is not a fixed domain workflow. Hermes creates the smallest useful workflow for the current goal and uses pi only as an execution worker.

## Roles

- **Hermes supervises:** interpret the goal, define completion criteria, decompose work, choose execution mode/model tier, review evidence, verify results, and decide whether to continue or stop.
- **pi executes:** inspect files, run commands, edit artifacts, test hypotheses, and return concrete evidence.

Pi output is worker output, not proof. Hermes should independently verify material claims when practical.

## 1. Define the goal

Before delegating, identify:

- `objective`: desired end state;
- `done`: observable completion criteria;
- `working_dir`: directory pi may operate in;
- `constraints`: things that must not change or actions that require approval;
- `inputs`: relevant files, repositories, logs, services, devices, or other resources;
- `verification`: how Hermes can prove the goal was achieved.

Unknown details that do not block safe progress should remain open questions rather than stopping the flow.

## 2. Create the minimum flow

Create only the phases needed to reach `done`. For each phase define:

| Field | Meaning |
|---|---|
| `id` | short phase name |
| `objective` | what this phase must establish or produce |
| `depends_on` | prerequisites |
| `mode` | `task` or `session` |
| `tier` | `fast`, `standard`, or `deep` |
| `artifacts` | expected outputs/evidence |
| `verify` | concrete completion check |

Independent phases can be handled separately. Dependent phases must be reviewed in order. Remove or change planned phases when new evidence makes them unnecessary or wrong.

## 3. Choose an execution primitive

Use `pi_task` for a focused phase that can be fully specified in one prompt and checked immediately.

Use a persistent RPC session when later work depends on discoveries from earlier work, when iterative debugging/experimentation is expected, or when retaining pi context is valuable:

1. `pi_session_start`
2. `pi_session_send`
3. review the returned settled-turn result
4. optionally inspect more state with `pi_session_read`
5. send the next instruction if needed
6. `pi_session_stop` when finished

`pi_session_send` waits for Pi's documented `agent_settled` event before returning. Do not assume a Pi RPC `response` acknowledging a prompt means the agent has finished.

## 4. Route cost by difficulty

The bridge exposes semantic tiers directly on `pi_task` and `pi_session_start`:

- `fast`: high-volume, low-risk, easy-to-check mechanical work;
- `standard`: normal implementation, debugging, and multi-file work with clear requirements;
- `deep`: ambiguous reasoning, competing hypotheses, cross-system correlation, or repeated reasoning failure.

Hermes should start with the cheapest tier that plausibly fits. Tier-to-provider/model mappings are plugin settings owned by Hermes; do not read or invent a separate routing file.

Escalate only for material reasoning signals such as:

- low confidence on an important conclusion;
- contradictory evidence;
- several unresolved plausible hypotheses;
- repeated failure after ordinary execution mistakes have been corrected;
- a stronger reasoning model is likely to change the outcome.

Do not escalate for a typo, missing package, bad path, permission error, or other routine execution problem.

Explicit `provider`, `model`, or `thinking` arguments override the selected tier for that call.

## 5. Give pi bounded prompts

A useful phase prompt contains:

```text
[OBJECTIVE]
What this phase must accomplish.

[CONTEXT]
Relevant facts, paths, previous evidence, and constraints.

[WORK]
What pi should inspect/change/run.

[OUTPUT]
What artifacts or findings must be produced.

[VERIFY]
Exact checks to run before claiming completion.

[REPORT]
Return status, evidence, changed artifacts, verification, confidence, blockers, and suggested next step.
```

For persistent sessions, send only the new objective and newly relevant evidence; the Pi session already retains its own history.

## 6. Require evidence

Prefer worker reports shaped like:

```text
STATUS: done | partial | blocked | needs_escalation
RESULT: concise outcome
EVIDENCE: commands, paths, outputs, observations, or tests
CHANGED: files/artifacts modified, or none
VERIFICATION: checks run and results
CONFIDENCE: high | medium | low
BLOCKERS: unresolved issues, or none
NEXT: suggested next action
```

Hermes decides whether the evidence is sufficient and performs independent verification where practical.

## 7. Adapt and finish

After every phase, Hermes may complete it, retry it with corrected context, split it, remove it, add a newly required phase, escalate its tier, or stop.

The flow is complete only when:

- the user's `done` criteria are met or a concrete blocker is established;
- verification has been performed where practical;
- Pi sessions created for the flow are stopped;
- Hermes reports the result, important evidence/artifacts, and unresolved limitations.

**Hermes plans and judges. Pi executes. Evidence advances the flow.**
