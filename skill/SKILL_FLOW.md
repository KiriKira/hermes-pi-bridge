---
name: pi-flow
description: Create and run a goal-specific workflow with Hermes as supervisor and pi as execution worker
version: 1.0.0
author: hermes-pi-bridge
license: MIT
metadata:
  hermes:
    tags: [pi, flow, orchestration, delegation, workflow]
    requires_tools: [pi_check, pi_task, pi_session_start, pi_session_send, pi_session_read, pi_session_stop, pi_session_list]
---

# pi-flow

Use this skill whenever the user says `pi_flow`, `pi-flow`, `pi flow`, or otherwise explicitly asks Hermes to accomplish a goal through pi_flow.

`pi_flow` is not a fixed domain workflow. It is a method for creating the right workflow for the current goal.

## Roles

- **Hermes is the supervisor.** Hermes interprets the goal, decomposes it, chooses models and execution modes, reviews evidence, verifies results, and decides when to stop or escalate.
- **pi is the worker.** pi reads files, runs commands, edits artifacts, tests hypotheses, and reports concrete results.

Do not ask pi to make the final supervisory decision when Hermes can verify it independently.

## 1. Define the goal before execution

Translate the user's request into:

- `objective`: the desired end state;
- `done`: observable completion criteria;
- `working_dir`: where pi may operate;
- `constraints`: things that must not change or actions that require approval;
- `inputs`: files, repositories, logs, services, devices, or other resources needed;
- `verification`: how Hermes can prove the goal was achieved.

If some detail is unknown but work can safely begin, record it as an open question instead of blocking the whole flow.

## 2. Create a goal-specific flow

Build the minimum ordered set of phases needed to reach `done`. A phase should have one clear outcome.

For each phase define:

| Field | Meaning |
|---|---|
| `id` | short phase name |
| `objective` | what this phase must establish or produce |
| `depends_on` | earlier phases required first |
| `mode` | `task` or `session` |
| `tier` | `fast`, `standard`, or `deep` |
| `artifacts` | expected files/results/evidence |
| `verify` | concrete completion check |

Do not create phases merely to make the plan look comprehensive. Add a phase only when it changes what can be known, built, or verified.

Independent phases may run separately, but dependent phases must be evaluated in order.

## 3. Choose one-shot vs persistent session

Use `pi_task` when:

- the phase is focused and can be specified completely in one prompt;
- the result can be checked immediately;
- retaining conversational state is not important.

Use `pi_session_start` when:

- later steps depend on discoveries from earlier steps;
- iterative debugging or experimentation is expected;
- pi needs to retain substantial working context;
- Hermes expects to steer the worker multiple times.

For an RPC session, use this loop:

1. `pi_session_start`
2. `pi_session_send`
3. wait for the bridge completion notification
4. assess the result
5. send the next instruction only if needed
6. `pi_session_stop` when that flow/session is complete

Never stack prompts into a busy session.

## 4. Route model cost by task difficulty

If `~/.hermes/pi-flow.yaml` exists, read it before choosing a model. It contains optional `fast`, `standard`, and `deep` model/provider mappings.

If a mapping is blank, omit that field and let pi use its configured default. Never invent provider or model IDs.

Use tiers semantically:

### fast

Use for low-risk, high-volume, easily checked work such as:

- search and retrieval;
- inventory and inspection;
- formatting and extraction;
- repetitive mechanical edits;
- running known commands and collecting output.

### standard

Use for normal implementation and debugging such as:

- writing or modifying code;
- ordinary test failures;
- creating scripts and adapters;
- multi-file changes with clear requirements.

### deep

Reserve for tasks where stronger reasoning is likely to change the outcome, such as:

- ambiguous architecture or protocol reasoning;
- several plausible hypotheses with weak evidence;
- cross-system correlation;
- subtle failures after reasonable attempts;
- high-impact decisions that are expensive to redo.

Start with the cheapest tier that plausibly fits. Escalate only when the evidence justifies it.

Typical escalation signals:

- low confidence on a material conclusion;
- contradictory evidence;
- repeated failure after correcting obvious execution mistakes;
- the worker identifies multiple unresolved hypotheses;
- the current model cannot make progress without deeper reasoning.

Do **not** escalate because of a typo, missing package, wrong path, permission error, or another ordinary execution problem.

## 5. Give pi bounded phase prompts

A phase prompt should contain:

```text
[OBJECTIVE]
What this phase must accomplish.

[CONTEXT]
Relevant facts, paths, previous evidence, and constraints.

[WORK]
What pi should inspect/change/run. Avoid prescribing unnecessary implementation details.

[OUTPUT]
What artifacts or findings must be produced.

[VERIFY]
Exact checks to run before claiming completion.

[REPORT]
Return status, evidence, changed artifacts, verification, confidence, blockers, and suggested next step.
```

For long sessions, do not resend all history on every turn. Send only the new objective and relevant evidence; the session already retains context.

## 6. Require evidence, not confidence theater

Treat pi's response as worker output, not as proof.

A useful worker report has this shape:

```text
STATUS: done | partial | blocked | needs_escalation
RESULT: concise outcome
EVIDENCE: commands, paths, outputs, observations, or tests supporting the result
CHANGED: files/artifacts modified, or none
VERIFICATION: checks run and their results
CONFIDENCE: high | medium | low
BLOCKERS: unresolved issues, or none
NEXT: suggested next action
```

Hermes should independently inspect or run the verification when practical.

## 7. Adapt the flow as evidence changes

The initial flow is a hypothesis about the work, not a contract.

After each phase, Hermes may:

- mark the phase complete;
- retry with corrected context;
- split an oversized phase;
- remove a phase made unnecessary by new evidence;
- add a newly required phase;
- escalate the model tier;
- stop because the goal is already satisfied or cannot be achieved under the constraints.

Do not continue executing stale phases just because they appeared in the first plan.

## 8. Reusable flows

Do not create a new Hermes skill for each domain or project.

When a workflow becomes genuinely reusable, Hermes may save a concise flow definition under:

```text
~/.hermes/pi-flows/<flow-name>.md
```

A saved flow should contain only reusable phase structure, routing guidance, inputs, and verification rules. Do not store secrets, captured credentials, or project-specific transient output there.

When the user later invokes `pi_flow`, Hermes may reuse a matching saved flow, but must adapt it to the new goal rather than following it blindly.

## 9. Finish cleanly

A pi_flow is complete only when:

- the user's `done` criteria are met or a concrete blocker is established;
- verification has been performed where practical;
- active pi sessions created for the flow are stopped;
- Hermes gives the user a concise result, evidence summary, important artifacts, and unresolved limitations.

The governing rule is:

**Hermes plans and judges. pi executes. Evidence advances the flow.**
