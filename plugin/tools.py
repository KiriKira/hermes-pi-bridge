"""Tool handlers for the Hermes -> pi bridge."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

PI_PACKAGE = "@earendil-works/pi-coding-agent"
DEFAULT_SYNC_TIMEOUT = 900
_TIER_DEFAULT_THINKING = {
    "fast": "minimal",
    "standard": "medium",
    "deep": "high",
}
_ctx_ref = None


def set_context_ref(ctx) -> None:
    global _ctx_ref
    _ctx_ref = ctx


def _plugin_config(key: str, default=None):
    """Read this plugin's Hermes-owned settings namespace."""
    if _ctx_ref is None or not hasattr(_ctx_ref, "get_config"):
        return default
    try:
        return _ctx_ref.get_config(key, default=default)
    except Exception as exc:
        logger.warning("pi-bridge: failed to read plugin setting %s: %s", key, exc)
        return default


def _resolve_execution_options(args_dict: dict) -> dict:
    """Apply an optional semantic tier without overriding explicit arguments."""
    resolved = dict(args_dict)
    tier = str(resolved.get("tier") or "").strip().lower()
    if not tier:
        resolved["_resolved_tier"] = None
        return resolved
    if tier not in _TIER_DEFAULT_THINKING:
        raise ValueError(f"Unknown pi tier: {tier}")

    for field in ("provider", "model"):
        if not resolved.get(field):
            value = _plugin_config(f"{tier}_{field}", "")
            if isinstance(value, str) and value.strip():
                resolved[field] = value.strip()

    if not resolved.get("thinking"):
        value = _plugin_config(
            f"{tier}_thinking",
            _TIER_DEFAULT_THINKING[tier],
        )
        if isinstance(value, str) and value.strip():
            resolved["thinking"] = value.strip()

    resolved["_resolved_tier"] = tier
    return resolved


def _routing_snapshot() -> dict:
    snapshot = {}
    for tier, fallback_thinking in _TIER_DEFAULT_THINKING.items():
        snapshot[tier] = {
            "provider": _plugin_config(f"{tier}_provider", "") or "",
            "model": _plugin_config(f"{tier}_model", "") or "",
            "thinking": _plugin_config(f"{tier}_thinking", fallback_thinking)
            or fallback_thinking,
        }
    return snapshot


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
    """Report whether pi is installed without exposing credential contents."""
    pi_bin = _find_pi()
    info: dict = {
        "installed": bool(pi_bin),
        "binary": pi_bin,
        "routing": _routing_snapshot(),
    }

    if pi_bin:
        try:
            result = subprocess.run(
                [pi_bin, "--version"], capture_output=True, text=True, timeout=10
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

    try:
        resolved = _resolve_execution_options(args)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})

    timeout = int(resolved.get("timeout") or DEFAULT_SYNC_TIMEOUT)
    cmd = _pi_cmd(pi_bin, resolved, extra_flags=["--mode", "json"])
    started = time.time()

    try:
        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=working_dir,
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"status": "timeout", "error": f"pi timed out after {timeout}s"})
    except Exception as exc:
        return json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})

    parsed = _parse_json_stream(process.stdout or "")
    result_text = _format_output(parsed) or (process.stdout or "").strip()
    duration_ms = int((time.time() - started) * 1000)

    common = {
        "result": result_text,
        "duration_ms": duration_ms,
        "model": parsed.get("model"),
        "provider": parsed.get("provider"),
        "tier": resolved.get("_resolved_tier"),
    }

    if process.returncode != 0:
        return json.dumps({
            "status": "failed",
            **common,
            "stderr": (process.stderr or "")[-1000:],
            "returncode": process.returncode,
        }, ensure_ascii=False)

    return json.dumps({
        "status": "completed",
        **common,
        "num_turns": parsed["num_turns"],
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

    try:
        resolved = _resolve_execution_options(args)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})

    session = start_session(
        working_dir=working_dir,
        model=resolved.get("model"),
        provider=resolved.get("provider"),
        thinking=resolved.get("thinking"),
        tools=resolved.get("tools"),
        system_prompt=resolved.get("system_prompt"),
        append_system_prompt=resolved.get("append_system_prompt"),
        persist_session=bool(resolved.get("persist_session", True)),
        ready_timeout=float(resolved.get("ready_timeout", 15)),
        tier=resolved.get("_resolved_tier"),
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
        "tier": session.tier,
        "model": session.model,
        "provider": session.provider,
    }, ensure_ascii=False)


def pi_session_send(args: dict, **kwargs) -> str:
    session_id = (args.get("session_id") or "").strip()
    message = (args.get("message") or "").strip()
    if not session_id:
        return json.dumps({"error": "session_id is required"})
    if not message:
        return json.dumps({"error": "message is required"})

    from .rpc_session import send_message

    return json.dumps(
        send_message(
            session_id=session_id,
            message=message,
            wait_timeout=float(args.get("wait_timeout", 900)),
        ),
        ensure_ascii=False,
    )


def pi_session_read(args: dict, **kwargs) -> str:
    session_id = (args.get("session_id") or "").strip()
    if not session_id:
        return json.dumps({"error": "session_id is required"})

    from .rpc_session import read_output

    return json.dumps(
        read_output(
            session_id=session_id,
            full=bool(args.get("full", False)),
        ),
        ensure_ascii=False,
    )


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
                "tier": session.tier,
                "model": session.model,
                "provider": session.provider,
                "duration_seconds": round(time.time() - session.created_at, 1),
                "process_alive": session.is_alive,
            }
            for session in sessions
        ]
    }, ensure_ascii=False)
