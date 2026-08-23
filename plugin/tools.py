"""Tool handlers for the Hermes -> pi bridge."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

PI_PACKAGE = "@earendil-works/pi-coding-agent"
DEFAULT_SYNC_TIMEOUT = 900
_EFFORTS = ("fast", "standard", "deep")
_DEFAULT_THINKING = {"fast": "minimal", "standard": "medium", "deep": "high"}
_VALID_THINKING = {"off", "minimal", "low", "medium", "high", "xhigh"}
_ctx_ref = None


def set_context_ref(ctx) -> None:
    global _ctx_ref
    _ctx_ref = ctx


def _pi_subprocess_env() -> dict[str, str]:
    """Build a child environment using Hermes' own secret-filtering policy."""
    try:
        from tools.environments.local import hermes_subprocess_env

        return hermes_subprocess_env(inherit_credentials=True)
    except (ImportError, AttributeError):
        logger.warning(
            "pi-bridge: Hermes subprocess environment filter unavailable; "
            "falling back to the host environment. Update Hermes for filtered child environments."
        )
        return os.environ.copy()


def _plugin_config(key: str, default=None):
    if _ctx_ref is None or not hasattr(_ctx_ref, "get_config"):
        return default
    try:
        return _ctx_ref.get_config(key, default)
    except Exception as exc:
        logger.warning("pi-bridge: failed to read plugin setting %s: %s", key, exc)
        return default


def _routing_for_effort(effort: str) -> dict[str, str]:
    if effort not in _EFFORTS:
        return {}

    provider = str(_plugin_config(f"{effort}_provider", "") or "").strip()
    model = str(_plugin_config(f"{effort}_model", "") or "").strip()
    thinking = str(
        _plugin_config(f"{effort}_thinking", _DEFAULT_THINKING[effort])
        or _DEFAULT_THINKING[effort]
    ).strip().lower()
    if thinking not in _VALID_THINKING:
        logger.warning(
            "pi-bridge: invalid %s_thinking=%r; using %s",
            effort,
            thinking,
            _DEFAULT_THINKING[effort],
        )
        thinking = _DEFAULT_THINKING[effort]

    result = {"thinking": thinking}
    if provider:
        result["provider"] = provider
    if model:
        result["model"] = model
    return result


def _apply_effort_defaults(args_dict: dict) -> dict:
    """Resolve a semantic effort tier through profile-scoped plugin settings."""
    effective = dict(args_dict)
    effort = str(effective.get("effort") or "").strip().lower()
    if not effort:
        return effective
    if effort not in _EFFORTS:
        logger.warning("pi-bridge: ignoring unknown effort tier %r", effort)
        return effective

    configured = _routing_for_effort(effort)
    for key in ("provider", "model", "thinking"):
        if not effective.get(key) and configured.get(key):
            effective[key] = configured[key]
    return effective


def _gateway_delivery_state() -> dict:
    """Return Hermes' current async-delivery/gateway-injection state.

    The values come from Hermes' session ContextVars, so concurrent gateway
    sessions do not leak routing identities into each other.
    """
    state = {
        "async_delivery_supported": True,
        "messaging_surface": False,
        "session_key": "",
        "gateway_injection_allowed": True,
    }
    try:
        from gateway.session_context import (
            async_delivery_supported,
            get_session_env,
            session_is_messaging_surface,
        )

        state["async_delivery_supported"] = bool(async_delivery_supported())
        state["messaging_surface"] = bool(session_is_messaging_surface())
        state["session_key"] = str(get_session_env("HERMES_SESSION_KEY", "") or "")
    except (ImportError, AttributeError):
        return state

    if not state["messaging_surface"]:
        return state

    # PluginContext.inject_message intentionally requires a separate explicit
    # gateway-injection grant. Read only that documented plugin-entry flag so
    # pi_session_send can fail before promising a completion it cannot deliver.
    state["gateway_injection_allowed"] = False
    try:
        from hermes_cli.config import load_config_readonly

        config = load_config_readonly() or {}
        entries = ((config.get("plugins") or {}).get("entries") or {})
        plugin_id = getattr(_ctx_ref, "plugin_id", "pi-bridge") if _ctx_ref else "pi-bridge"
        entry = entries.get(plugin_id) or {}
        state["gateway_injection_allowed"] = entry.get("allow_gateway_injection") is True
    except Exception:
        pass
    return state


def _find_pi() -> Optional[str]:
    found = shutil.which("pi")
    if found:
        return found
    for path in (
        Path.home() / ".local" / "bin" / "pi",
        Path.home() / ".local" / "share" / "npm-global" / "bin" / "pi",
        Path("/usr/local/bin/pi"),
    ):
        if path.exists():
            return str(path)
    return None


def _pi_cmd(pi_bin: str, args_dict: dict, extra_flags: Optional[List[str]] = None) -> List[str]:
    cmd: List[str] = [pi_bin, "--print", args_dict.get("prompt", ""), "--no-session"]

    for key, flag in (
        ("model", "--model"),
        ("provider", "--provider"),
        ("thinking", "--thinking"),
        ("tools", "--tools"),
        ("system_prompt", "--system-prompt"),
        ("append_system_prompt", "--append-system-prompt"),
    ):
        value = args_dict.get(key)
        if value:
            cmd += [flag, str(value)]

    if extra_flags:
        cmd += extra_flags
    return cmd


def _parse_json_stream(raw: str) -> dict:
    """Extract the final assistant text and metadata from pi NDJSON output."""
    text = ""
    model = None
    provider = None
    num_turns = 0
    tool_names: List[str] = []
    errors: List[str] = []

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type = event.get("type", "")
        if event_type == "turn_end":
            num_turns += 1
            message = event.get("message") or {}
            content = message.get("content") or []
            texts = [item.get("text", "") for item in content if item.get("type") == "text"]
            if texts:
                text = "\n".join(texts)
            model = message.get("model") or model
            provider = message.get("provider") or provider
            for result in event.get("toolResults") or []:
                name = result.get("toolName")
                if name:
                    tool_names.append(name)
        elif event_type == "agent_end":
            for message in event.get("messages") or []:
                if message.get("role") != "assistant":
                    continue
                content = message.get("content") or []
                texts = [item.get("text", "") for item in content if item.get("type") == "text"]
                if texts:
                    text = "\n".join(texts)
                model = message.get("model") or model
                provider = message.get("provider") or provider
        elif event_type == "error":
            errors.append(str(event.get("message") or event.get("error") or "pi error"))

    return {
        "text": text,
        "model": model,
        "provider": provider,
        "num_turns": num_turns,
        "tool_names": tool_names,
        "errors": errors,
    }


def _format_output(parsed: dict) -> str:
    parts: List[str] = []
    if parsed["tool_names"]:
        parts.append("[Tools used: " + ", ".join(dict.fromkeys(parsed["tool_names"])) + "]")
    if parsed["text"]:
        parts.append(parsed["text"])
    if parsed["errors"]:
        parts.append("[Errors: " + "; ".join(parsed["errors"]) + "]")
    return "\n\n".join(parts)


def pi_check(args: dict, **kwargs) -> str:
    """Report pi availability and this profile's semantic routing policy."""
    pi_bin = _find_pi()
    info: dict = {"installed": bool(pi_bin), "binary": pi_bin}

    if pi_bin:
        try:
            result = subprocess.run(
                [pi_bin, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                env=_pi_subprocess_env(),
            )
            info["version"] = result.stdout.strip() or result.stderr.strip()
        except Exception as exc:
            info["version_error"] = f"{type(exc).__name__}: {exc}"

        agent_dir = Path.home() / ".pi" / "agent"
        auth_file = agent_dir / "auth.json"
        info["agent_dir"] = str(agent_dir) if agent_dir.exists() else None
        info["auth_config_present"] = auth_file.exists()
    else:
        info["install_command"] = f"npm install -g --ignore-scripts {PI_PACKAGE}"

    info["effort_routing"] = {
        effort: _routing_for_effort(effort) for effort in _EFFORTS
    }
    delivery = _gateway_delivery_state()
    info["async_delivery_supported"] = delivery["async_delivery_supported"]
    info["gateway_injection_allowed"] = (
        delivery["gateway_injection_allowed"] if delivery["messaging_surface"] else None
    )

    from .rpc_session import active_session_count

    info["active_rpc_sessions"] = active_session_count()
    return json.dumps(info, indent=2)


def pi_task(args: dict, **kwargs) -> str:
    """Run one focused pi task synchronously."""
    prompt = (args.get("prompt") or "").strip()
    if not prompt:
        return json.dumps({"error": "prompt is required"})

    working_dir = (args.get("working_dir") or "").strip() or None
    if working_dir and not Path(working_dir).is_dir():
        return json.dumps({"error": f"Directory not found: {working_dir}"})

    pi_bin = _find_pi()
    if not pi_bin:
        return json.dumps({
            "error": "pi binary not found",
            "fix": f"npm install -g --ignore-scripts {PI_PACKAGE}",
        })

    effective = _apply_effort_defaults(args)
    timeout = int(effective.get("timeout") or DEFAULT_SYNC_TIMEOUT)
    cmd = _pi_cmd(pi_bin, effective, extra_flags=["--mode", "json"])
    started = time.time()

    try:
        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=working_dir,
            env=_pi_subprocess_env(),
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"status": "timeout", "error": f"pi timed out after {timeout}s"})
    except Exception as exc:
        return json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})

    parsed = _parse_json_stream(process.stdout or "")
    result_text = _format_output(parsed) or (process.stdout or "").strip()
    duration_ms = int((time.time() - started) * 1000)

    if process.returncode != 0:
        return json.dumps({
            "status": "failed",
            "result": result_text,
            "stderr": (process.stderr or "")[-1000:],
            "returncode": process.returncode,
            "duration_ms": duration_ms,
            "effort": effective.get("effort"),
            "model": parsed.get("model"),
            "provider": parsed.get("provider"),
        }, ensure_ascii=False)

    return json.dumps({
        "status": "completed",
        "result": result_text,
        "num_turns": parsed["num_turns"],
        "duration_ms": duration_ms,
        "effort": effective.get("effort"),
        "model": parsed.get("model"),
        "provider": parsed.get("provider"),
    }, ensure_ascii=False)


def pi_session_start(args: dict, **kwargs) -> str:
    working_dir = (args.get("working_dir") or "").strip()
    if not working_dir:
        return json.dumps({"error": "working_dir is required"})
    if not Path(working_dir).is_dir():
        return json.dumps({"error": f"Directory not found: {working_dir}"})

    from .rpc_session import active_session_count, start_session

    if active_session_count() >= 3:
        return json.dumps({"error": "Maximum 3 concurrent RPC sessions. Stop one first."})

    effective = _apply_effort_defaults(args)
    session = start_session(
        working_dir=working_dir,
        model=effective.get("model"),
        provider=effective.get("provider"),
        thinking=effective.get("thinking"),
        tools=effective.get("tools"),
        system_prompt=effective.get("system_prompt"),
        append_system_prompt=effective.get("append_system_prompt"),
        persist_session=bool(effective.get("persist_session", True)),
        ready_timeout=float(effective.get("ready_timeout", 15)),
    )

    if session.status == "error":
        return json.dumps({
            "status": "error",
            "session_id": session.session_id,
            "error": session.error,
        }, ensure_ascii=False)

    return json.dumps({
        "status": session.status,
        "session_id": session.session_id,
        "working_dir": working_dir,
        "pi_session_file": session.pi_session_file,
        "effort": effective.get("effort"),
    }, ensure_ascii=False)


def pi_session_send(args: dict, **kwargs) -> str:
    session_id = (args.get("session_id") or "").strip()
    message = (args.get("message") or "").strip()
    if not session_id:
        return json.dumps({"error": "session_id is required"})
    if not message:
        return json.dumps({"error": "message is required"})

    delivery = _gateway_delivery_state()
    if not delivery["async_delivery_supported"]:
        return json.dumps({
            "error": "This Hermes runtime cannot deliver an asynchronous pi completion after the current turn.",
            "fix": "Use pi_task for this phase, or run the flow in an interactive CLI/gateway session.",
        })
    if delivery["messaging_surface"] and not delivery["gateway_injection_allowed"]:
        return json.dumps({
            "error": "Gateway completion injection is not authorized for pi-bridge.",
            "fix": (
                "Grant plugins.entries.pi-bridge.allow_gateway_injection=true in this Hermes profile, "
                "or use pi_task instead of a persistent asynchronous session."
            ),
        })

    from .rpc_session import send_message

    return json.dumps(send_message(
        session_id=session_id,
        message=message,
        streaming_behavior=args.get("streaming_behavior", "followUp"),
        completion_session_key=delivery["session_key"] or None,
    ), ensure_ascii=False)


def pi_session_read(args: dict, **kwargs) -> str:
    session_id = (args.get("session_id") or "").strip()
    if not session_id:
        return json.dumps({"error": "session_id is required"})

    from .rpc_session import read_output

    return json.dumps(read_output(
        session_id=session_id,
        full=bool(args.get("full", False)),
    ), ensure_ascii=False)


def pi_session_stop(args: dict, **kwargs) -> str:
    session_id = (args.get("session_id") or "").strip()
    if not session_id:
        return json.dumps({"error": "session_id is required"})

    from .rpc_session import stop_session

    return json.dumps(stop_session(session_id), ensure_ascii=False)


def pi_session_list(args: dict, **kwargs) -> str:
    from .rpc_session import list_sessions

    sessions = list_sessions()
    return json.dumps({
        "sessions": [
            {
                "session_id": session.session_id,
                "status": session.status,
                "working_dir": session.working_dir,
                "pi_session_file": session.pi_session_file,
                "model": session.model,
                "provider": session.provider,
                "duration_seconds": round(time.time() - session.created_at, 1),
                "process_alive": session.is_alive,
            }
            for session in sessions
        ]
    }, ensure_ascii=False)
