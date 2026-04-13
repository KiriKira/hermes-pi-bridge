"""
Pi Coding Agent Bridge — Hermes Agent Plugin
============================================

Connects Hermes Agent to pi (https://github.com/badlogic/pi-mono),
a minimal terminal coding agent with read, bash, edit, write tools.

Registered tools
----------------
  pi_task             Run a task synchronously (blocks until done)
  pi_task_async       Start a task in background; Hermes is notified on completion
  pi_task_status      Check status of one or all tasks
  pi_task_result      Retrieve the stored result of a completed task
  pi_check            Verify pi installation and configuration
  pi_session_start    Start an interactive pi RPC session
  pi_session_send     Send a prompt to a session (non-blocking; inject_message on done)
  pi_session_read     Read buffered output from a session
  pi_session_wait     Wait up to N seconds for the current prompt to complete
  pi_session_stop     Close a pi RPC session
  pi_session_list     List all pi RPC sessions

Lifecycle hooks
---------------
  pre_llm_call   — Detects coding requests and injects the right delegation reminder;
                   large/multi-phase projects → pi_session_start skill;
                   focused tasks → pi_task skill.
                   Also reports active background tasks and RPC sessions.
  on_session_end — Cleans up running tasks and RPC sessions on shutdown.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Coding request detection
# ---------------------------------------------------------------------------

_CODING_TRIGGERS: list[re.Pattern] = [p for p in (re.compile(r, re.IGNORECASE | re.DOTALL) for r in [
    # Create / generate a code artifact
    r'\b(write|create|make|generate)\b.{0,60}\b(code|script|function|class|module|program|app|application|endpoint|api|test|tests|spec|component|service|tool|plugin|daemon|cli|utility|library|schema|migration|dockerfile|workflow|pipeline)\b',

    # Implement anything non-trivial
    r'\bimplement\b',

    # Build with a target
    r'\bbuild\b.{0,60}\b(a|an|me|the|this|that|new|simple|basic)\b',

    # Add features / capabilities to existing code
    r'\badd\b.{0,60}\b(feature|function|method|endpoint|test|tests|spec|class|module|handler|route|command|hook|support|validation|auth|authentication|authorization|caching|logging|error.handling|retry|rate.limit|pagination|search|filter|middleware|config)\b',

    # Modify existing code
    r'\b(update|modify|change|edit|patch|extend|enhance)\b.{0,60}\b(the|this|that|my|our)\b.{0,60}\b(function|class|method|module|file|code|service|model|schema|api|endpoint|handler|hook|component|controller|middleware|route|config|pipeline|workflow|script|query|test|spec)\b',

    # Fix: bugs, errors, or named code artifacts
    r'\bfix\b.{0,60}\b(bug|error|issue|test|tests|failing|broken|crash|exception|problem|the|this|that|my)\b',

    # Refactor / migrate / port / rewrite
    r'\b(refactor|rewrite|migrate|port|convert|transform)\b',

    # Debug
    r'\bdebug\b',

    # Run tests (often followed by fix)
    r'\brun\b.{0,40}\b(the\s+)?(tests?|specs?|pytest|jest|mocha|vitest|cargo\s+test|go\s+test|npm\s+test|yarn\s+test|make\s+test)\b',
    r'\brun\b.{0,20}\band\b.{0,20}\bfix\b',

    # Project setup
    r'\b(set up|scaffold|bootstrap|initialise|initialize|spin up|stub out)\b',

    # Integration / wiring
    r'\b(integrate|connect|wire\s+up|hook\s+(up|into))\b.{0,60}\b(with|to|into|the)\b',

    # DevOps
    r'\b(dockerize|containerize)\b',
    r'\b(dockerfile|docker-?compose)\b.{0,40}\b(for|the|my|this|that)\b',

    # File path references — anything with a real path is file work, not a snippet
    r'[~/][\w./_-]+\.(py|js|ts|rs|go|rb|java|sh|bash|yaml|yml|json|toml|sql|html|css|tsx|jsx|vue|svelte|cpp|c|h|swift|kt)\b',
    r'\bsrc/|lib/|app/|tests?/|pkg/|cmd/\b',

    # "In my project / codebase / repo"
    r'\b(in|for|within|to)\b.{0,20}\b(the|my|this|our)\b.{0,40}\b(project|codebase|repo|repository|app|application|service|module|package)\b',

    # Write/add tests broadly
    r'\b(write|add|create|generate)\b.{0,40}\btests?\b',

    # Make it work / production-ready
    r'\bmake\b.{0,30}\b(it|this|the|that)\b.{0,60}\b(work|run|pass|compile|build|deploy|production.?ready|type.?safe)\b',

    # "can you X" imperative
    r'\bcan you\b.{0,60}\b(write|build|code|implement|create|make|add|fix|update|refactor|migrate|integrate)\b',

    # Language + task context
    r'\b(python|javascript|typescript|rust|go|bash|shell|ruby|java|c\+\+|c#|kotlin|swift)\b.{0,60}\b(script|function|class|program|module|snippet|that|to|for|which)\b',
])]

_LARGE_PROJECT_TRIGGERS: list[re.Pattern] = [p for p in (re.compile(r, re.IGNORECASE | re.DOTALL) for r in [
    # Explicit "keep going" instructions
    r"\b(don'?t stop|keep going|continue until|until (you'?re |it'?s )?(done|complete|finished)|as far as you can)\b",

    # Multiple named UI/system components in one ask
    r'\b(chat|interface|viewer|tracker|radio|ebook|wiki|dashboard|auth|login|api|frontend|backend|panel|sidebar|modal|editor|player|map|graph|chart)\b.{0,200}\b(and|,)\b.{0,200}\b(chat|interface|viewer|tracker|radio|ebook|wiki|dashboard|auth|login|api|frontend|backend|panel|sidebar|modal|editor|player|map|graph|chart)\b',

    # Scope words: full / complete / entire / whole
    r'\bfull\b.{0,30}\b(project|app|application|stack|system|platform|suite|website|service|pipeline)\b',
    r'\b(full.?stack|fullstack)\b',
    r'\bcomplete\b.{0,30}\b(project|app|application|system|platform|suite|website)\b',
    r'\bentire\b.{0,30}\b(project|app|codebase|system|platform|website|suite)\b',
    r'\bwhole\b.{0,30}\b(project|app|codebase|system|service)\b',

    # Build from nothing
    r'\bfrom scratch\b',

    # End-to-end
    r'\bend.to.end\b|\be2e\b.{0,30}\b(app|project|system|build|setup)\b',

    # Multiple named requirements (3+ conjunctions/commas — a list of deliverables)
    r'\b(include|with|has|have|featuring)\b.{0,100}(?:\band\b|,).{0,100}(?:\band\b|,).{0,100}(?:\band\b|,)',

    # Production / deployment readiness scope
    r'\b(production.?ready|production.?grade)\b',

    # Exploration of existing codebase
    r'\b(explore|audit|review|analyse|analyze)\b.{0,40}\b(the|my|this|our)\b.{0,40}\b(codebase|project|repo|repository|code)\b',

    # Explicitly multi-phase or multi-component
    r'\b(multiple|several)\b.{0,30}\b(components?|modules?|services?|endpoints?|files?|phases?|features?)\b',
    r'\b(phase\s+\d|step\s+\d|part\s+\d)\b',
])]


def _is_coding_request(message: str) -> bool:
    if not message or not isinstance(message, str):
        return False
    return any(p.search(message[:2000]) for p in _CODING_TRIGGERS)


def _is_large_project(message: str) -> bool:
    if not message or not isinstance(message, str):
        return False
    return any(p.search(message[:4000]) for p in _LARGE_PROJECT_TRIGGERS)


_INTERACTIVE_SESSION_REMINDER = """\

---
[pi-bridge] LARGE MULTI-PHASE PROJECT DETECTED.
This request spans multiple components or explicitly asks you to continue until complete.
Use an INTERACTIVE SESSION, not pi_task_async. Before doing anything:
1. Call skill_view("pi-interactive-session") to load the interactive session guide.
2. Follow the skill — start a session with pi_session_start, then drive it turn by turn.
Do NOT use pi_task or pi_task_async for this. Do NOT skip skill_view. Use interactive."""

_DELEGATION_REMINDER = """\

---
[pi-bridge] CODING TASK DETECTED.
You have the pi_task tool available. Before writing any code yourself:
1. Call skill_view("pi-task-delegation") to load delegation instructions.
2. Follow the skill — delegate the work to pi via pi_task.
Do NOT produce code directly. Do NOT skip skill_view. Delegate first."""


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------

def register(ctx) -> None:
    from .schemas import (
        PI_TASK_SCHEMA, PI_TASK_ASYNC_SCHEMA, PI_TASK_STATUS_SCHEMA,
        PI_TASK_RESULT_SCHEMA, PI_CHECK_SCHEMA,
        PI_SESSION_START_SCHEMA, PI_SESSION_SEND_SCHEMA, PI_SESSION_READ_SCHEMA,
        PI_SESSION_WAIT_SCHEMA, PI_SESSION_STOP_SCHEMA, PI_SESSION_LIST_SCHEMA,
    )
    from .tools import (
        pi_task, pi_task_async, pi_task_status, pi_task_result, pi_check,
        pi_session_start, pi_session_send, pi_session_read,
        pi_session_wait, pi_session_stop, pi_session_list,
        set_context_ref,
    )

    set_context_ref(ctx)

    ctx.register_tool(name="pi_task", toolset="pi_bridge", schema=PI_TASK_SCHEMA,
                      handler=pi_task, description="Run a pi coding task synchronously", emoji="🤖")
    ctx.register_tool(name="pi_task_async", toolset="pi_bridge", schema=PI_TASK_ASYNC_SCHEMA,
                      handler=pi_task_async, description="Start a pi task in the background", emoji="⚡")
    ctx.register_tool(name="pi_task_status", toolset="pi_bridge", schema=PI_TASK_STATUS_SCHEMA,
                      handler=pi_task_status, description="Check status of pi tasks", emoji="📊")
    ctx.register_tool(name="pi_task_result", toolset="pi_bridge", schema=PI_TASK_RESULT_SCHEMA,
                      handler=pi_task_result, description="Retrieve full result of a pi task", emoji="📋")
    ctx.register_tool(name="pi_check", toolset="pi_bridge", schema=PI_CHECK_SCHEMA,
                      handler=pi_check, description="Check pi installation and config", emoji="🔍")

    ctx.register_tool(name="pi_session_start", toolset="pi_bridge", schema=PI_SESSION_START_SCHEMA,
                      handler=pi_session_start, description="Start an interactive pi RPC session", emoji="🖥️")
    ctx.register_tool(name="pi_session_send", toolset="pi_bridge", schema=PI_SESSION_SEND_SCHEMA,
                      handler=pi_session_send, description="Send a prompt to a pi RPC session", emoji="⌨️")
    ctx.register_tool(name="pi_session_read", toolset="pi_bridge", schema=PI_SESSION_READ_SCHEMA,
                      handler=pi_session_read, description="Read output from a pi RPC session", emoji="👁️")
    ctx.register_tool(name="pi_session_wait", toolset="pi_bridge", schema=PI_SESSION_WAIT_SCHEMA,
                      handler=pi_session_wait, description="Wait for pi RPC session response", emoji="⏳")
    ctx.register_tool(name="pi_session_stop", toolset="pi_bridge", schema=PI_SESSION_STOP_SCHEMA,
                      handler=pi_session_stop, description="Stop a pi RPC session", emoji="⏹️")
    ctx.register_tool(name="pi_session_list", toolset="pi_bridge", schema=PI_SESSION_LIST_SCHEMA,
                      handler=pi_session_list, description="List all pi RPC sessions", emoji="📋")

    ctx.register_hook("pre_llm_call", _pre_llm_call_hook)
    ctx.register_hook("on_session_end", _on_session_end_hook)

    logger.info("pi-bridge: plugin loaded — 11 tools registered (5 task, 6 interactive)")


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------

def _pre_llm_call_hook(**kwargs) -> str | None:
    from .sessions import running_count
    from .rpc_session import active_session_count

    parts: list[str] = []

    user_message = kwargs.get("user_message", "")
    if _is_large_project(user_message):
        parts.append(_INTERACTIVE_SESSION_REMINDER)
        logger.debug("pi-bridge: large project detected, injecting interactive session reminder")
    elif _is_coding_request(user_message):
        parts.append(_DELEGATION_REMINDER)
        logger.debug("pi-bridge: coding request detected, injecting delegation reminder")

    active_tasks = running_count()
    if active_tasks > 0:
        parts.append(
            f"[pi-bridge] {active_tasks} pi task(s) running in background. "
            f"You will be notified on completion. Use pi_task_status to poll."
        )

    active_sessions = active_session_count()
    if active_sessions > 0:
        parts.append(
            f"[pi-bridge] {active_sessions} pi RPC session(s) active. "
            f"Use pi_session_send to interact."
        )

    return "\n\n".join(parts) if parts else None


def _on_session_end_hook(**kwargs) -> None:
    from .sessions import list_tasks
    from .rpc_session import list_sessions, stop_session

    running = [t for t in list_tasks() if t.status == "running"]
    if running:
        logger.warning(
            "pi-bridge: session ended with %d task(s) still running: %s",
            len(running), ", ".join(t.task_id for t in running),
        )

    active = [s for s in list_sessions() if s.status in ("starting", "ready", "busy")]
    for s in active:
        logger.warning("pi-bridge: stopping RPC session %s on shutdown", s.session_id)
        try:
            stop_session(s.session_id)
        except Exception as exc:
            logger.error("pi-bridge: error stopping session %s: %s", s.session_id, exc)
