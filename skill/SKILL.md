---
name: pi-task-delegation
description: Delegate focused coding tasks to pi coding agent
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [delegation, pi, coding, implementation, refactor, debugging, testing]
    requires_tools: [pi_task, pi_task_async]
    related_skills: [pi-interactive-session]
---

# Pi Task Delegation

## Overview

Hermes orchestrates. pi executes.

pi is a full coding agent running the local Qwen3-Coder-30B model. It has read, write, edit, bash, grep, find, and ls tools — it can read/write files, run shell commands, install packages, run tests, and iterate on errors. Hermes' role is to delegate clearly, assess what comes back, and decide next steps.

**Use `pi_task` for focused, well-defined tasks where a single prompt is enough.**
**Use `pi_session_start` for large multi-phase projects — see the pi-interactive-session skill.**

---

## When to Delegate

### Use pi_task when:
| Signal | Examples |
|--------|---------|
| Single focused change | "Add input validation to the signup endpoint" |
| Specific bug fix | "Fix the off-by-one error in pagination.py line 47" |
| Well-scoped feature | "Add a /health endpoint to the Flask app" |
| Write tests for known code | "Write pytest tests for the User model" |
| Refactor a single file | "Refactor utils.py to use dataclasses" |
| Task < 5 min | Small edits, quick implementations |

### Use pi_session_start instead when:
- Multiple components or phases involved
- "don't stop", "continue until done", "build the whole thing"
- Scope is unclear and needs iterative guidance
- Work > 5-10 minutes or > 3-4 files

---

## Step 1 — Gather Context

Before calling `pi_task`, collect:
1. `working_dir` — absolute path, always required
2. Relevant files — read key files, summarise in the prompt
3. Constraints — language version, framework, test runner, conventions
4. Verification — command to confirm it worked

---

## Step 2 — Choose Sync vs Async

| Use `pi_task` (sync) | Use `pi_task_async` (async) |
|----------------------|------------------------------|
| Task likely < 5 min | Task likely > 5 min |
| Quick bug fix | Large refactor |
| Single focused change | Full test suite run |

---

## Step 3 — Choose Thinking Level

| Default (no thinking flag) | Use thinking=high/xhigh |
|---------------------------|--------------------------|
| Straightforward implementation | Complex algorithm design |
| Clear spec, just needs coding | Subtle debugging |
| Routine refactor | Multi-step architectural decisions |

---

## Step 4 — Construct the Prompt

Always include all four parts:

```
[TASK]
One clear sentence: what to build or fix.

[CONTEXT]
- Working directory: /absolute/path
- Relevant files and their purpose
- Framework/language/version
- Conventions to follow

[REQUIREMENTS]
- Explicit list of what must be true when done
- File paths, functions, behaviours required
- Constraints (no new deps, keep tests passing, etc.)

[VERIFICATION]
- Exact command to confirm success
- Expected output or exit code
```

---

## Step 5 — Call pi_task

```python
pi_task(
    prompt="<four-part prompt>",
    working_dir="/absolute/path",
    # thinking="high"       # only for complex reasoning
    # timeout=300           # increase for long tasks
)
```

---

## Step 6 — Assess the Output

When `pi_task` returns (or inject_message fires for async):

- [ ] Did the result contain actual code/output, not just an error?
- [ ] Does output address ALL requirements?
- [ ] Run the verification command yourself if pi didn't
- Watch for: "I couldn't", "TODO", "placeholder", error tracebacks without a fix

### Decide next action:
| Assessment | Action |
|------------|--------|
| Complete and verified | Report to user |
| Partially complete | Call pi_task again with specific gap |
| pi hit an error | Call pi_task with error context and fix instruction |
| Wrong approach | Rewrite prompt with corrected direction |
| Timed out | Break into smaller tasks |

---

## Red Flags

- Delegate without `working_dir`
- Accept output without verification
- Pass a vague prompt
- Use pi_task for a multi-phase project (use pi_session_start)

**pi executes. Hermes judges. The user gets verified, working code.**
