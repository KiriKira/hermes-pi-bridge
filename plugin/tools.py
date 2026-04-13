"""
Tool handler implementations for the pi coding agent bridge.

All handlers follow the Hermes convention:
  handler(args: dict, **kwargs) -> str   (always returns JSON string, never raises)
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import List, Optional

from .sessions import (
    PiTask,
    complete_task,
    create_task,
    fail_task,
    get_task,
    list_tasks,
    running_count,
)

logger = logging.getLogger(__name__)

# Timeout defaults for pi tasks.
# pi is used with a fast local model (Qwen3-Coder-30B via llama.cpp).
DEFAULT_SYNC_TIMEOUT = 900    # 15 min
DEFAULT_ASYNC_TIMEOUT = 1800  # 30 min

# Set by __init__.py after registration so async threads can inject_message.
_ctx_ref = None


def set_context_ref(ctx) -> None:
    global _ctx_ref
    _ctx_ref = ctx


# ---------------------------------------------------------------------------
# pi binary discovery
# ---------------------------------------------------------------------------

def _find_pi() -> Optional[str]:
    found = shutil.which("pi")
    if found:
        return found
    for p in [
        Path.home() / ".local" / "bin" / "pi",
        Path.home() / ".local" / "share" / "npm-global" / "bin" / "pi",
        Path("/usr/local/bin/pi"),
    ]:
        if p.exists():
            return str(p)
    return None


def _pi_cmd(args_dict: dict, extra_flags: Optional[List[str]] = None) -> List[str]:
    """Build a pi CLI invocation for one-shot (--print) mode."""
    pi_bin = _find_pi()
    cmd: List[str] = [pi_bin] if pi_bin else ["npx", "--yes", "@mariozechner/pi-coding-agent"]

    prompt = args_dict.get("prompt", "")
    cmd += ["--print", prompt]
    cmd += ["--no-session"]

    model = args_dict.get("model")
    if model:
        cmd += ["--model", model]

    provider = args_dict.get("provider")
    if provider:
        cmd += ["--provider", provider]

    thinking = args_dict.get("thinking")
    if thinking:
        cmd += ["--thinking", thinking]

    tools = args_dict.get("tools")
    if tools:
        cmd += ["--tools", tools]

    system_prompt = args_dict.get("system_prompt")
    if system_prompt:
        cmd += ["--system-prompt", system_prompt]

    append_prompt = args_dict.get("append_system_prompt")
    if append_prompt:
        cmd += ["--append-system-prompt", append_prompt]

    if extra_flags:
        cmd += extra_flags

    return cmd


# ---------------------------------------------------------------------------
# Output parsing for --mode json
# ---------------------------------------------------------------------------

def _parse_json_stream(raw: str) -> dict:
    """
    Parse pi's NDJSON output stream.

    Key event types:
      turn_end    — final assistant message for this turn (has full text)
      agent_end   — all done (has all messages)
      message_update with assistantMessageEvent.type=text_delta — streaming chunks
    """
    text = ""
    tool_calls: List[dict] = []
    model = None
    provider = None
    num_turns = 0
    is_error = False
    error_message = None

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        etype = obj.get("type", "")

        if etype == "turn_end":
            num_turns += 1
            msg = obj.get("message", {})
            content = msg.get("content", [])
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            if texts:
                text = "\n".join(texts)
            model = msg.get("model") or model
            provider = msg.get("provider") or provider
            # Extract tool results summary
            for tr in obj.get("toolResults", []):
                tool_calls.append({
                    "name": tr.get("toolName", ""),
                    "result": str(tr.get("result", ""))[:200],
                })

        elif etype == "agent_end":
            # agent_end carries the complete final message list
            messages = obj.get("messages", [])
            for msg in messages:
                if msg.get("role") == "assistant":
                    content = msg.get("content", [])
                    texts = [c.get("text", "") for c in content if c.get("type") == "text"]
                    if texts:
                        text = "\n".join(texts)
                    model = msg.get("model") or model
                    provider = msg.get("provider") or provider

    return {
        "text": text,
        "tool_calls": tool_calls,
        "model": model,
        "provider": provider,
        "num_turns": num_turns,
        "is_error": is_error,
        "error_message": error_message,
    }


def _format_output(parsed: dict) -> str:
    parts: List[str] = []
    if parsed["tool_calls"]:
        names = ", ".join(tc["name"] for tc in parsed["tool_calls"] if tc["name"])
        if names:
            parts.append(f"[Tools used: {names}]")
    if parsed["text"]:
        parts.append(parsed["text"])
    model_info = ""
    if parsed.get("provider") and parsed.get("model"):
        model_info = f"{parsed['provider']}/{parsed['model']}"
    elif parsed.get("model"):
        model_info = parsed["model"]
    if model_info:
        parts.append(f"\n[{parsed['num_turns']} turn(s), model: {model_info}]")
    return "\n\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Async worker
# ---------------------------------------------------------------------------

def _async_worker(task_id: str, cmd: List[str], cwd: Optional[str], timeout: int) -> None:
    logger.debug("pi-bridge: starting async task %s — %s", task_id, cmd[:3])
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd or None,
        )
        parsed = _parse_json_stream(proc.stdout or "")

        # Fall back to plain stdout if JSON parsing yielded nothing
        result_text = _format_output(parsed) if parsed["text"] else (proc.stdout or "").strip()

        if not result_text and proc.returncode != 0:
            result_text = proc.stderr[:1000] if proc.stderr else f"Exit code {proc.returncode}"

        complete_task(
            task_id=task_id,
            result=result_text,
            num_turns=parsed["num_turns"],
            duration_ms=int((time.time() - get_task(task_id).created_at) * 1000),
            model=parsed.get("model"),
            provider=parsed.get("provider"),
        )
        task = get_task(task_id)

        if _ctx_ref:
            inject = (
                f"[pi-bridge] Task `{task_id}` completed "
                f"({task.num_turns} turns, {task.duration_ms / 1000:.1f}s)\n\n"
                f"{result_text}\n\n"
                f"Please review the above output and decide on next steps."
            )
            _ctx_ref.inject_message(inject, role="user")

    except subprocess.TimeoutExpired:
        fail_task(task_id, f"Timed out after {timeout}s")
        logger.warning("pi-bridge: task %s timed out", task_id)
        if _ctx_ref:
            _ctx_ref.inject_message(
                f"[pi-bridge] Task `{task_id}` timed out after {timeout}s.",
                role="user",
            )
    except Exception as exc:
        fail_task(task_id, f"{type(exc).__name__}: {exc}")
        logger.exception("pi-bridge: async task %s failed", task_id)
        if _ctx_ref:
            _ctx_ref.inject_message(
                f"[pi-bridge] Task `{task_id}` failed: {type(exc).__name__}: {exc}",
                role="user",
            )


# ---------------------------------------------------------------------------
# Tool handlers — one-shot tasks
# ---------------------------------------------------------------------------

def pi_task(args: dict, **kwargs) -> str:
    """Synchronous: run pi and block until done."""
    prompt = (args.get("prompt") or "").strip()
    if not prompt:
        return json.dumps({"error": "prompt is required"})

    pi_bin = _find_pi()
    if not pi_bin:
        return json.dumps({
            "error": "pi binary not found",
            "fix": "Install with: npm install -g @mariozechner/pi-coding-agent",
        })

    timeout = int(args.get("timeout") or DEFAULT_SYNC_TIMEOUT)
    working_dir = args.get("working_dir") or None

    # Use --mode json for structured output, --print for the prompt
    cmd = _pi_cmd(args, extra_flags=["--mode", "json"])

    logger.debug("pi-bridge: sync task — %s", cmd[:4])
    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=working_dir,
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"error": f"pi timed out after {timeout}s"})
    except FileNotFoundError:
        return json.dumps({"error": "pi binary not found", "fix": "npm install -g @mariozechner/pi-coding-agent"})
    except Exception as exc:
        return json.dumps({"error": str(type(exc).__name__), "detail": str(exc)})

    if proc.returncode != 0 and not proc.stdout.strip():
        return json.dumps({
            "error": "pi process exited non-zero with no output",
            "stderr": (proc.stderr or "")[:500],
            "returncode": proc.returncode,
        })

    parsed = _parse_json_stream(proc.stdout or "")
    result_text = _format_output(parsed) or (proc.stdout or "").strip()
    duration_ms = int((time.time() - start) * 1000)

    return json.dumps({
        "status": "completed",
        "result": result_text,
        "num_turns": parsed["num_turns"],
        "duration_ms": duration_ms,
        "model": parsed.get("model"),
        "provider": parsed.get("provider"),
        "is_error": parsed["is_error"],
        "error_message": parsed["error_message"],
    }, ensure_ascii=False)


def pi_task_async(args: dict, **kwargs) -> str:
    """Asynchronous: start pi in background, return task_id immediately."""
    prompt = (args.get("prompt") or "").strip()
    if not prompt:
        return json.dumps({"error": "prompt is required"})

    pi_bin = _find_pi()
    if not pi_bin:
        return json.dumps({"error": "pi binary not found", "fix": "npm install -g @mariozechner/pi-coding-agent"})

    timeout = int(args.get("timeout") or DEFAULT_ASYNC_TIMEOUT)
    working_dir = args.get("working_dir") or None

    cmd = _pi_cmd(args, extra_flags=["--mode", "json"])
    task = create_task(prompt=prompt, working_dir=working_dir)

    thread = threading.Thread(
        target=_async_worker,
        args=(task.task_id, cmd, working_dir, timeout),
        daemon=True,
        name=f"pi-{task.task_id}",
    )
    thread.start()
    logger.info("pi-bridge: launched async task %s", task.task_id)

    return json.dumps({
        "status": "started",
        "task_id": task.task_id,
        "message": (
            f"pi task `{task.task_id}` is running in the background "
            f"(timeout: {timeout}s). Hermes will be notified automatically when it completes."
        ),
    })


def pi_task_status(args: dict, **kwargs) -> str:
    task_id = (args.get("task_id") or "").strip()
    if task_id:
        task = get_task(task_id)
        if not task:
            return json.dumps({"error": f"Task {task_id!r} not found"})
        return json.dumps({
            "task_id": task.task_id,
            "status": task.status,
            "prompt": task.prompt,
            "working_dir": task.working_dir,
            "num_turns": task.num_turns,
            "duration_ms": task.duration_ms,
            "model": task.model,
            "provider": task.provider,
            "error": task.error,
            "created_at": time.strftime("%H:%M:%S", time.localtime(task.created_at)),
            "completed_at": (
                time.strftime("%H:%M:%S", time.localtime(task.completed_at))
                if task.completed_at else None
            ),
        })
    tasks = list_tasks()
    if not tasks:
        return json.dumps({"message": "No pi tasks in this session"})
    return json.dumps({
        "tasks": [
            {
                "task_id": t.task_id,
                "status": t.status,
                "prompt_preview": (t.prompt[:80] + "…") if len(t.prompt) > 80 else t.prompt,
                "created_at": time.strftime("%H:%M:%S", time.localtime(t.created_at)),
            }
            for t in tasks
        ]
    })


def pi_task_result(args: dict, **kwargs) -> str:
    task_id = (args.get("task_id") or "").strip()
    if not task_id:
        return json.dumps({"error": "task_id is required"})
    task = get_task(task_id)
    if not task:
        return json.dumps({"error": f"Task {task_id!r} not found"})
    if task.status == "running":
        return json.dumps({"status": "running", "message": "Task is still in progress"})
    return json.dumps({
        "task_id": task.task_id,
        "status": task.status,
        "result": task.result,
        "error": task.error,
        "num_turns": task.num_turns,
        "duration_ms": task.duration_ms,
        "model": task.model,
        "provider": task.provider,
        "working_dir": task.working_dir,
        "prompt": task.prompt,
    }, ensure_ascii=False)


def pi_check(args: dict, **kwargs) -> str:
    """Check pi installation and configuration."""
    pi_bin = _find_pi()
    info: dict = {"installed": bool(pi_bin), "binary": pi_bin}

    if pi_bin:
        try:
            r = subprocess.run([pi_bin, "--version"], capture_output=True, text=True, timeout=10)
            info["version"] = r.stdout.strip() or r.stderr.strip()
        except Exception as exc:
            info["version_error"] = str(exc)

        # Check settings
        auth_file = Path.home() / ".pi" / "agent" / "auth.json"
        info["auth_file"] = str(auth_file) if auth_file.exists() else None
        sessions_dir = Path.home() / ".pi" / "agent" / "sessions"
        if sessions_dir.exists():
            info["sessions_dir"] = str(sessions_dir)
            info["session_count"] = len(list(sessions_dir.glob("*.json")))
    else:
        info["install_command"] = "npm install -g @mariozechner/pi-coding-agent"

    info["running_tasks"] = running_count()

    from .rpc_session import active_session_count
    info["active_rpc_sessions"] = active_session_count()

    return json.dumps(info, indent=2)


# ---------------------------------------------------------------------------
# Tool handlers — interactive RPC sessions
# ---------------------------------------------------------------------------

def pi_session_start(args: dict, **kwargs) -> str:
    working_dir = (args.get("working_dir") or "").strip()
    if not working_dir:
        return json.dumps({"error": "working_dir is required"})
    if not Path(working_dir).is_dir():
        return json.dumps({"error": f"Directory not found: {working_dir}"})

    from .rpc_session import start_session, active_session_count

    if active_session_count() >= 3:
        return json.dumps({"error": "Maximum 3 concurrent RPC sessions. Stop one first."})

    session = start_session(
        working_dir=working_dir,
        model=args.get("model"),
        provider=args.get("provider"),
        thinking=args.get("thinking"),
        tools=args.get("tools"),
        system_prompt=args.get("system_prompt"),
        append_system_prompt=args.get("append_system_prompt"),
        persist_session=bool(args.get("persist_session", True)),
        ready_timeout=float(args.get("ready_timeout", 15)),
    )

    if session.status == "error":
        return json.dumps({"status": "error", "session_id": session.session_id, "error": session.error})

    return json.dumps({
        "status": session.status,
        "session_id": session.session_id,
        "working_dir": working_dir,
        "pi_session_file": session.pi_session_file,
        "message": (
            f"pi RPC session `{session.session_id}` is {session.status}. "
            f"Use pi_session_send to send prompts. "
            f"Use pi_session_stop when done."
        ),
    }, ensure_ascii=False)


def pi_session_send(args: dict, **kwargs) -> str:
    session_id = (args.get("session_id") or "").strip()
    message = (args.get("message") or "").strip()
    if not session_id:
        return json.dumps({"error": "session_id is required"})
    if not message:
        return json.dumps({"error": "message is required"})

    from .rpc_session import send_message

    result = send_message(
        session_id=session_id,
        message=message,
        streaming_behavior=args.get("streaming_behavior", "followUp"),
    )
    return json.dumps(result, ensure_ascii=False)


def pi_session_read(args: dict, **kwargs) -> str:
    session_id = (args.get("session_id") or "").strip()
    if not session_id:
        return json.dumps({"error": "session_id is required"})

    from .rpc_session import read_output

    result = read_output(
        session_id=session_id,
        full=bool(args.get("full", False)),
    )
    return json.dumps(result, ensure_ascii=False)


def pi_session_wait(args: dict, **kwargs) -> str:
    session_id = (args.get("session_id") or "").strip()
    if not session_id:
        return json.dumps({"error": "session_id is required"})

    from .rpc_session import wait_for_response

    result = wait_for_response(
        session_id=session_id,
        timeout=float(args.get("timeout", 30)),
    )
    return json.dumps(result, ensure_ascii=False)


def pi_session_stop(args: dict, **kwargs) -> str:
    session_id = (args.get("session_id") or "").strip()
    if not session_id:
        return json.dumps({"error": "session_id is required"})

    from .rpc_session import stop_session

    result = stop_session(session_id=session_id)
    return json.dumps(result, ensure_ascii=False)


def pi_session_list(args: dict, **kwargs) -> str:
    from .rpc_session import list_sessions

    sessions = list_sessions()
    if not sessions:
        return json.dumps({"message": "No pi RPC sessions in this Hermes session"})

    return json.dumps({
        "sessions": [
            {
                "session_id": s.session_id,
                "status": s.status,
                "working_dir": s.working_dir,
                "pi_session_file": s.pi_session_file,
                "model": s.model,
                "provider": s.provider,
                "created_at": time.strftime("%H:%M:%S", time.localtime(s.created_at)),
                "duration_seconds": round(time.time() - s.created_at, 1),
                "process_alive": s.is_alive,
            }
            for s in sessions
        ]
    }, ensure_ascii=False)
