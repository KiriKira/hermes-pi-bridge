"""Persistent pi RPC session manager.

Spawns ``pi --mode rpc`` and communicates with strict LF-delimited JSON Lines.
Pi's ``response`` for a ``prompt`` only acknowledges acceptance; a turn is
complete when Pi emits the documented ``agent_settled`` event.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)
PI_PACKAGE = "@earendil-works/pi-coding-agent"


@dataclass
class PiRpcSession:
    session_id: str
    working_dir: str
    status: str = "starting"  # starting | ready | busy | closed | error
    created_at: float = field(default_factory=time.time)
    pi_session_file: Optional[str] = None
    error: Optional[str] = None
    tier: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None

    _proc: Optional[subprocess.Popen] = field(default=None, repr=False)
    _event_buffer: List[dict] = field(default_factory=list, repr=False)
    _text_buffer: str = field(default="", repr=False)
    _turn_text: str = field(default="", repr=False)
    _turn_done: bool = field(default=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _turn_event: threading.Event = field(default_factory=threading.Event, repr=False)
    _reader_thread: Optional[threading.Thread] = field(default=None, repr=False)
    _stop_reader: bool = field(default=False, repr=False)

    @property
    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None


_sessions: Dict[str, PiRpcSession] = {}


def get_session(session_id: str) -> Optional[PiRpcSession]:
    return _sessions.get(session_id)


def list_sessions() -> List[PiRpcSession]:
    return sorted(_sessions.values(), key=lambda item: item.created_at, reverse=True)


def active_session_count() -> int:
    return sum(
        1 for session in _sessions.values()
        if session.status in ("starting", "ready", "busy")
    )


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


def _send_rpc(session: PiRpcSession, command: dict) -> bool:
    """Write one UTF-8 JSON object followed by a single LF delimiter."""
    if not session.is_alive:
        return False
    try:
        payload = (json.dumps(command, ensure_ascii=False) + "\n").encode("utf-8")
        session._proc.stdin.write(payload)
        session._proc.stdin.flush()
        return True
    except (BrokenPipeError, OSError, AttributeError) as exc:
        logger.warning("pi-rpc: write failed for %s: %s", session.session_id, exc)
        return False


def _handle_event(session: PiRpcSession, event: dict) -> None:
    """Apply one decoded Pi RPC event to session state."""
    with session._lock:
        session._event_buffer.append(event)
        event_type = event.get("type", "")

        if event_type == "message_update":
            assistant_event = event.get("assistantMessageEvent") or {}
            update_type = assistant_event.get("type", "")
            if update_type == "text_delta":
                session._turn_text += assistant_event.get("delta", "")
            elif update_type == "text_end":
                session._turn_text = assistant_event.get("content", "")

        elif event_type == "message_start":
            message = event.get("message") or {}
            if message.get("role") == "assistant":
                session.model = message.get("model") or session.model
                session.provider = message.get("provider") or session.provider

        elif event_type == "turn_end":
            message = event.get("message") or {}
            content = message.get("content") or []
            texts = [
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            if texts:
                session._turn_text = "\n".join(texts)
            if session._turn_text:
                if session._text_buffer:
                    session._text_buffer += "\n\n"
                session._text_buffer += session._turn_text

        elif event_type == "response":
            command = event.get("command", "")
            success = bool(event.get("success", False))

            if command == "get_state" and session.status == "starting":
                if success:
                    data = event.get("data") or {}
                    model_info = data.get("model") or {}
                    if isinstance(model_info, dict):
                        session.provider = model_info.get("provider") or session.provider
                        session.model = model_info.get("id") or session.model
                    session.status = "ready"
                else:
                    session.status = "error"
                    session.error = str(event.get("error") or "pi get_state failed")

            elif command == "prompt":
                # Pi documents this as prompt acceptance/rejection only. Success
                # does NOT mean the agent is idle; wait for agent_settled.
                if not success:
                    session.error = str(event.get("error") or "pi prompt rejected")
                    session._turn_done = True
                    if session.is_alive:
                        session.status = "ready"
                    session._turn_event.set()

            elif command == "get_last_assistant_text" and success:
                text = (event.get("data") or {}).get("text") or ""
                if text:
                    session._turn_text = text

        elif event_type == "agent_settled":
            session._turn_done = True
            if session.is_alive:
                session.status = "ready"
            session._turn_event.set()

        elif event_type in ("error", "extension_error"):
            session.error = str(
                event.get("message")
                or event.get("error")
                or "pi RPC error"
            )


def _reader_loop(session: PiRpcSession) -> None:
    """Read Pi's strict JSONL stream without treating Unicode separators as records."""
    process = session._proc
    while not session._stop_reader and session.is_alive:
        try:
            raw_line = process.stdout.readline()
            if not raw_line:
                break

            # Pi requires LF framing and accepts optional CRLF input. Binary
            # readline splits only on LF, unlike generic Unicode line readers.
            if raw_line.endswith(b"\n"):
                raw_line = raw_line[:-1]
            if raw_line.endswith(b"\r"):
                raw_line = raw_line[:-1]
            if not raw_line:
                continue

            try:
                line = raw_line.decode("utf-8")
                event = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                logger.debug("pi-rpc: ignored malformed JSONL record from %s", session.session_id)
                continue

            _handle_event(session, event)

        except Exception as exc:
            logger.warning("pi-rpc: reader failed for %s: %s", session.session_id, exc)
            with session._lock:
                session.error = f"reader error: {type(exc).__name__}: {exc}"
            break

    if not session.is_alive and session.status not in ("closed", "error"):
        with session._lock:
            session.status = "closed"
            session._turn_event.set()


def _terminate_process(session: PiRpcSession) -> None:
    session._stop_reader = True
    if not session.is_alive:
        return
    try:
        session._proc.stdin.close()
    except (OSError, AttributeError):
        pass
    try:
        session._proc.terminate()
        session._proc.wait(timeout=3.0)
    except subprocess.TimeoutExpired:
        session._proc.kill()
        session._proc.wait(timeout=2.0)


def start_session(
    working_dir: str,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    thinking: Optional[str] = None,
    tools: Optional[str] = None,
    system_prompt: Optional[str] = None,
    append_system_prompt: Optional[str] = None,
    persist_session: bool = True,
    ready_timeout: float = 15.0,
    tier: Optional[str] = None,
) -> PiRpcSession:
    session_id = str(uuid.uuid4())[:8]
    session = PiRpcSession(
        session_id=session_id,
        working_dir=working_dir,
        tier=tier,
    )
    _sessions[session_id] = session

    pi_bin = _find_pi()
    if not pi_bin:
        session.status = "error"
        session.error = (
            "pi binary not found. Install with: "
            f"npm install -g --ignore-scripts {PI_PACKAGE}"
        )
        return session

    cmd = [pi_bin, "--mode", "rpc"]
    for value, flag in (
        (model, "--model"),
        (provider, "--provider"),
        (thinking, "--thinking"),
        (tools, "--tools"),
        (system_prompt, "--system-prompt"),
        (append_system_prompt, "--append-system-prompt"),
    ):
        if value:
            cmd += [flag, str(value)]

    if persist_session:
        sessions_dir = Path.home() / ".pi" / "agent" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        session.pi_session_file = str(sessions_dir / f"hermes-{session_id}.jsonl")
        cmd += ["--session", session.pi_session_file]
    else:
        cmd += ["--no-session"]

    try:
        process = subprocess.Popen(
            cmd,
            cwd=working_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=False,
            bufsize=0,
            env={**os.environ},
        )
        session._proc = process
    except Exception as exc:
        session.status = "error"
        session.error = f"Failed to start pi: {type(exc).__name__}: {exc}"
        return session

    session._reader_thread = threading.Thread(
        target=_reader_loop,
        args=(session,),
        daemon=True,
        name=f"pi-reader-{session_id}",
    )
    session._reader_thread.start()

    time.sleep(0.3)
    if not _send_rpc(session, {"type": "get_state"}):
        session.status = "error"
        session.error = "pi RPC process did not accept get_state"
        _terminate_process(session)
        return session

    deadline = time.time() + ready_timeout
    while time.time() < deadline:
        if session.status in ("ready", "error") or not session.is_alive:
            break
        time.sleep(0.1)

    if session.status != "ready":
        if session.status != "error":
            session.status = "error"
            session.error = (
                "pi RPC did not confirm readiness before timeout"
                if session.is_alive else "pi process exited during startup"
            )
        _terminate_process(session)

    return session


def send_message(
    session_id: str,
    message: str,
    wait_timeout: float = 900.0,
) -> dict:
    """Send a prompt and wait until Pi emits ``agent_settled``."""
    session = _sessions.get(session_id)
    if not session:
        return {"error": f"Session {session_id!r} not found"}
    if session.status == "busy":
        return {"error": f"Session {session_id!r} is busy; inspect or wait for it to settle"}
    if session.status in ("closed", "error"):
        return {"error": f"Session {session_id!r} is {session.status}: {session.error or ''}".rstrip()}
    if not session.is_alive:
        session.status = "closed"
        return {"error": f"Session {session_id!r} process has exited"}

    with session._lock:
        session._turn_text = ""
        session._turn_done = False
        session.error = None
        session._turn_event.clear()

    session.status = "busy"
    started = time.time()
    if not _send_rpc(session, {"type": "prompt", "message": message}):
        session.status = "ready"
        return {"error": f"Failed to send message to session {session_id!r}"}

    settled = session._turn_event.wait(timeout=max(0.1, wait_timeout))
    duration = time.time() - started

    with session._lock:
        text = session._turn_text
        error = session.error
        done = session._turn_done
        status = session.status
        model = session.model
        provider = session.provider

    if not settled:
        # The process keeps running. A later agent_settled event will move the
        # session back to ready; callers can inspect with read/list meanwhile.
        return {
            "status": "timeout",
            "session_id": session_id,
            "text": text,
            "turn_done": done,
            "process_alive": session.is_alive,
            "duration_seconds": round(duration, 1),
            "message": "Timed out waiting for agent_settled; pi was not terminated.",
        }

    if status == "closed":
        return {
            "status": "failed",
            "session_id": session_id,
            "text": text,
            "error": error or "pi process exited before the turn settled",
            "duration_seconds": round(duration, 1),
        }

    return {
        "status": "failed" if error else "completed",
        "session_id": session_id,
        "text": text,
        "error": error,
        "turn_done": done,
        "duration_seconds": round(duration, 1),
        "tier": session.tier,
        "model": model,
        "provider": provider,
    }


def read_output(session_id: str, full: bool = False) -> dict:
    session = _sessions.get(session_id)
    if not session:
        return {"error": f"Session {session_id!r} not found"}
    with session._lock:
        text = session._text_buffer if full else session._turn_text
        event_count = len(session._event_buffer)
        turn_done = session._turn_done
        error = session.error
    return {
        "status": session.status,
        "text": text,
        "turn_done": turn_done,
        "event_count": event_count,
        "process_alive": session.is_alive,
        "error": error,
        "tier": session.tier,
        "model": session.model,
        "provider": session.provider,
    }


def stop_session(session_id: str) -> dict:
    session = _sessions.get(session_id)
    if not session:
        return {"error": f"Session {session_id!r} not found"}

    if session.is_alive:
        _send_rpc(session, {"type": "abort"})
        time.sleep(0.2)
    _terminate_process(session)
    session._turn_event.set()

    if session._reader_thread and session._reader_thread.is_alive():
        session._reader_thread.join(timeout=2.0)

    session.status = "closed"
    return {
        "status": "closed",
        "session_id": session_id,
        "pi_session_file": session.pi_session_file,
        "duration_seconds": round(time.time() - session.created_at, 1),
        "tier": session.tier,
        "model": session.model,
        "provider": session.provider,
    }
