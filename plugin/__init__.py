"""Hermes -> pi bridge implementation.

The plugin exposes a small set of pi execution primitives and one explicit
high-level convention: when the user asks to use ``pi_flow``, Hermes loads the
bundled namespaced skill and creates a goal-specific workflow at runtime.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Explicit user contract. Keep this deliberately narrow: the bridge should not
# guess that every coding-looking request must be delegated to pi.
_PI_FLOW_PATTERN = re.compile(r"\bpi[\s_-]*flow\b", re.IGNORECASE)


def _is_pi_flow_request(message: str) -> bool:
    return bool(isinstance(message, str) and _PI_FLOW_PATTERN.search(message))


_PI_FLOW_REMINDER = """\
[pi-bridge] PI_FLOW REQUEST DETECTED.
The user explicitly asked to use pi_flow.
Before executing the goal, call skill_view("pi-bridge:pi-flow") and follow that skill.
Create a goal-specific flow at runtime; do not substitute a fixed domain flow or switch profiles merely because pi_flow was requested.
Hermes owns planning, routing, review, and verification. pi executes delegated work."""


def register(ctx) -> None:
    from .schemas import (
        PI_CHECK_SCHEMA,
        PI_TASK_SCHEMA,
        PI_SESSION_START_SCHEMA,
        PI_SESSION_SEND_SCHEMA,
        PI_SESSION_READ_SCHEMA,
        PI_SESSION_STOP_SCHEMA,
        PI_SESSION_LIST_SCHEMA,
    )
    from .tools import (
        pi_check,
        pi_task,
        pi_session_start,
        pi_session_send,
        pi_session_read,
        pi_session_stop,
        pi_session_list,
        set_context_ref,
    )

    set_context_ref(ctx)

    ctx.register_tool(
        name="pi_check",
        toolset="pi_bridge",
        schema=PI_CHECK_SCHEMA,
        handler=pi_check,
        description="Check pi installation and configuration",
        emoji="🔍",
    )
    ctx.register_tool(
        name="pi_task",
        toolset="pi_bridge",
        schema=PI_TASK_SCHEMA,
        handler=pi_task,
        description="Run one focused pi task synchronously",
        emoji="🤖",
    )
    ctx.register_tool(
        name="pi_session_start",
        toolset="pi_bridge",
        schema=PI_SESSION_START_SCHEMA,
        handler=pi_session_start,
        description="Start a persistent pi RPC session",
        emoji="🖥️",
    )
    ctx.register_tool(
        name="pi_session_send",
        toolset="pi_bridge",
        schema=PI_SESSION_SEND_SCHEMA,
        handler=pi_session_send,
        description="Send one instruction to a pi RPC session",
        emoji="⌨️",
    )
    ctx.register_tool(
        name="pi_session_read",
        toolset="pi_bridge",
        schema=PI_SESSION_READ_SCHEMA,
        handler=pi_session_read,
        description="Read buffered output from a pi RPC session",
        emoji="👁️",
    )
    ctx.register_tool(
        name="pi_session_stop",
        toolset="pi_bridge",
        schema=PI_SESSION_STOP_SCHEMA,
        handler=pi_session_stop,
        description="Stop a pi RPC session",
        emoji="⏹️",
    )
    ctx.register_tool(
        name="pi_session_list",
        toolset="pi_bridge",
        schema=PI_SESSION_LIST_SCHEMA,
        handler=pi_session_list,
        description="List pi RPC sessions",
        emoji="📋",
    )

    skill_path = Path(__file__).resolve().parents[1] / "skills" / "pi-flow" / "SKILL.md"
    ctx.register_skill(
        "pi-flow",
        skill_path,
        "Create a goal-specific Hermes-supervised workflow executed through pi.",
    )

    ctx.register_hook("pre_llm_call", _pre_llm_call_hook)
    # Persistent pi sessions intentionally survive ordinary Hermes turns.
    # Clean them only when Hermes finalizes the conversation on reset/shutdown.
    ctx.register_hook("on_session_finalize", _on_session_finalize_hook)
    logger.info("pi-bridge: plugin loaded — 7 tools and 1 namespaced skill registered")


def _pre_llm_call_hook(**kwargs) -> str | None:
    from .rpc_session import active_session_count

    parts: list[str] = []
    user_message = kwargs.get("user_message", "")

    if _is_pi_flow_request(user_message):
        parts.append(_PI_FLOW_REMINDER)

    active_sessions = active_session_count()
    if active_sessions:
        parts.append(
            f"[pi-bridge] {active_sessions} pi RPC session(s) active. "
            "Use pi_session_list/read/send/stop as needed."
        )

    return "\n\n".join(parts) if parts else None


def _on_session_finalize_hook(**kwargs) -> None:
    from .rpc_session import list_sessions, stop_session

    active = [s for s in list_sessions() if s.status in ("starting", "ready", "busy")]
    for session in active:
        logger.warning("pi-bridge: stopping RPC session %s on Hermes finalization", session.session_id)
        try:
            stop_session(session.session_id)
        except Exception as exc:
            logger.error("pi-bridge: error stopping session %s: %s", session.session_id, exc)
