"""
RPC-based interactive session manager for pi coding agent.

Spawns pi with --mode rpc, communicates via JSON Lines over stdin/stdout.
Unlike the qwen PTY approach, pi's RPC mode gives us explicit completion
signals: a {"type":"response","command":"prompt","success":true} event means
the current turn is done — no idle-timeout guessing required.
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

from .parsers import EventType, parse_event

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Session dataclass
# ---------------------------------------------------------------------------

@dataclass
class PiRpcSession:
    session_id: str           # our internal ID
    working_dir: str
    status: str = "starting"  # starting | ready | busy | closed | error
    created_at: float = field(default_factory=time.time)

    # pi session file path (persists conversation across turns)
    pi_session_file: Optional[str] = None

    # subprocess handle
    _proc: Optional[subprocess.Popen] = field(default=None, repr=False)

    # Accumulated events and text from pi
    _event_buffer: List = field(default_factory=list, repr=False)
    _text_buffer: str = field(default="", repr=False)      # assistant text so far this session
    _turn_text: str = field(default="", repr=False)        # text for the current/last turn
    _turn_done: bool = field(default=False, repr=False)    # True when current prompt is complete
    _last_event_time: float = field(default=0.0, repr=False)

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _turn_event: threading.Event = field(default_factory=threading.Event, repr=False)
    _reader_thread: Optional[threading.Thread] = field(default=None, repr=False)
    _stop_reader: bool = field(default=False, repr=False)

    error: Optional[str] = None

    # Model/provider info populated from events
    model: Optional[str] = None
    provider: Optional[str] = None

    @property
    def is_alive(self) -> bool:
        if self._proc is None:
            return False
        return self._proc.poll() is None

    def current_turn_text(self) -> str:
        with self._lock:
            return self._turn_text

    def all_text(self) -> str:
        with self._lock:
            return self._text_buffer


# ---------------------------------------------------------------------------
# Session store
# ---------------------------------------------------------------------------

_sessions: Dict[str, PiRpcSession] = {}


def get_session(session_id: str) -> Optional[PiRpcSession]:
    return _sessions.get(session_id)


def list_sessions() -> List[PiRpcSession]:
    return sorted(_sessions.values(), key=lambda s: s.created_at, reverse=True)


def active_session_count() -> int:
    return sum(1 for s in _sessions.values() if s.status in ("starting", "ready", "busy"))


# ---------------------------------------------------------------------------
# Background reader thread
# ---------------------------------------------------------------------------

def _reader_loop(session: PiRpcSession) -> None:
    """
    Read stdout from the pi RPC process line by line.
    Each line is a JSON event. Parse them and update session state.
    """
    proc = session._proc
    while not session._stop_reader and session.is_alive:
        try:
            line = proc.stdout.readline()
            if not line:
                # EOF
                break
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("pi-rpc: non-JSON line from session %s: %s", session.session_id, line[:100])
                continue

            with session._lock:
                session._event_buffer.append(event)
                session._last_event_time = time.time()

                etype = event.get("type", "")

                # Accumulate text deltas
                if etype == "message_update":
                    ae = event.get("assistantMessageEvent", {})
                    ae_type = ae.get("type", "")
                    if ae_type == "text_delta":
                        delta = ae.get("delta", "")
                        session._turn_text += delta
                    elif ae_type == "text_end":
                        # Full content of this text block
                        content = ae.get("content", "")
                        # Replace what we built from deltas with the authoritative text_end
                        # (in case any deltas were missed)
                        session._turn_text = content

                # Capture model/provider from message_start
                elif etype == "message_start":
                    msg = event.get("message", {})
                    if msg.get("role") == "assistant":
                        session.model = msg.get("model") or session.model
                        session.provider = msg.get("provider") or session.provider

                # turn_end: the LLM response for this prompt is complete
                elif etype == "turn_end":
                    msg = event.get("message", {})
                    # Get final authoritative text from turn_end
                    content = msg.get("content", [])
                    texts = [c.get("text", "") for c in content if c.get("type") == "text"]
                    final_text = "\n".join(texts)
                    if final_text:
                        session._turn_text = final_text
                    session._text_buffer += ("\n\n" if session._text_buffer else "") + session._turn_text

                # RPC response for "prompt" command — this is the definitive "done" signal
                elif etype == "response":
                    cmd = event.get("command", "")
                    success = event.get("success", False)
                    if cmd == "prompt":
                        session._turn_done = True
                        session._turn_event.set()
                        if success:
                            logger.debug("pi-rpc: session %s prompt complete", session.session_id)
                        else:
                            err = event.get("error", "unknown error")
                            logger.warning("pi-rpc: session %s prompt failed: %s", session.session_id, err)
                    elif cmd == "get_state":
                        # Initial state check — mark as ready
                        if success and session.status == "starting":
                            session.status = "ready"
                    elif cmd == "get_last_assistant_text":
                        if success:
                            text = (event.get("data") or {}).get("text") or ""
                            if text:
                                session._turn_text = text

        except Exception as exc:
            logger.warning("pi-rpc: reader error for session %s: %s", session.session_id, exc)
            break

    if not session.is_alive and session.status not in ("closed", "error"):
        session.status = "closed"
        session._turn_event.set()  # unblock any waiters
        logger.info("pi-rpc: session %s process exited", session.session_id)


# ---------------------------------------------------------------------------
# RPC helpers
# ---------------------------------------------------------------------------

def _send_rpc(session: PiRpcSession, command: dict) -> bool:
    """Write a JSON command to the pi RPC process stdin. Returns False on error."""
    if not session.is_alive:
        return False
    try:
        line = json.dumps(command) + "\n"
        session._proc.stdin.write(line)
        session._proc.stdin.flush()
        return True
    except (BrokenPipeError, OSError) as exc:
        logger.warning("pi-rpc: write error for session %s: %s", session.session_id, exc)
        return False


# ---------------------------------------------------------------------------
# Session lifecycle
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
) -> PiRpcSession:
    """
    Start a pi coding agent process in RPC mode.

    Args:
        working_dir: Directory for pi to operate in.
        model: Model pattern/ID override.
        provider: Provider name override.
        thinking: Thinking level (off/minimal/low/medium/high/xhigh).
        tools: Comma-separated tools to enable (default: read,bash,edit,write).
        system_prompt: Override system prompt.
        append_system_prompt: Append to default system prompt.
        persist_session: If True, save pi session to disk for later resume.
        ready_timeout: Seconds to wait for RPC ready signal.
    """
    session_id = str(uuid.uuid4())[:8]
    session = PiRpcSession(
        session_id=session_id,
        working_dir=working_dir,
    )

    pi_bin = _find_pi()
    if not pi_bin:
        session.status = "error"
        session.error = "pi binary not found. Install with: npm install -g @mariozechner/pi-coding-agent"
        _sessions[session_id] = session
        return session

    # Build command
    cmd = [pi_bin, "--mode", "rpc"]

    if model:
        cmd += ["--model", model]
    if provider:
        cmd += ["--provider", provider]
    if thinking:
        cmd += ["--thinking", thinking]
    if tools:
        cmd += ["--tools", tools]
    if system_prompt:
        cmd += ["--system-prompt", system_prompt]
    if append_system_prompt:
        cmd += ["--append-system-prompt", append_system_prompt]

    # Session file for persistence
    if persist_session:
        sessions_dir = Path.home() / ".pi" / "agent" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        session_file = str(sessions_dir / f"hermes-{session_id}.json")
        session.pi_session_file = session_file
        cmd += ["--session", session_file]
    else:
        cmd += ["--no-session"]

    logger.info("pi-rpc: starting session %s in %s — %s", session_id, working_dir, " ".join(cmd[:5]))

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=working_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,  # line-buffered
            env={**os.environ},
        )
        session._proc = proc
    except Exception as exc:
        session.status = "error"
        session.error = f"Failed to start pi: {type(exc).__name__}: {exc}"
        _sessions[session_id] = session
        return session

    # Start background reader
    session._reader_thread = threading.Thread(
        target=_reader_loop,
        args=(session,),
        daemon=True,
        name=f"pi-reader-{session_id}",
    )
    session._reader_thread.start()

    # Wait for ready: send get_state and wait for the response event
    time.sleep(0.5)  # give pi a moment to start up
    _send_rpc(session, {"type": "get_state"})

    deadline = time.time() + ready_timeout
    while time.time() < deadline:
        with session._lock:
            if session.status == "ready":
                break
        if not session.is_alive:
            break
        time.sleep(0.2)

    if session.status == "starting":
        if session.is_alive:
            # Alive but didn't confirm — mark ready anyway
            session.status = "ready"
            logger.warning(
                "pi-rpc: session %s didn't confirm ready in %.0fs, marking ready anyway",
                session_id, ready_timeout,
            )
        else:
            session.status = "error"
            session.error = "pi process exited during startup"

    _sessions[session_id] = session
    return session


# ---------------------------------------------------------------------------
# Sending messages
# ---------------------------------------------------------------------------

def _response_watcher(session: PiRpcSession, sent_at: float) -> None:
    """
    Background thread: waits for the RPC 'response' event for the current
    prompt, then injects Qwen's response into Hermes via inject_message.
    """
    from .tools import _ctx_ref

    # Wait for the turn_event to be set (by the reader when it sees the response)
    # Use a generous timeout — pi handles its own timeout internally
    timeout = 600.0
    fired = session._turn_event.wait(timeout=timeout)

    if not fired:
        logger.warning("pi-rpc: session %s response watcher timed out after %.0fs", session.session_id, timeout)

    with session._lock:
        turn_text = session._turn_text
        timed_out = not fired
        alive = session.is_alive
        model = session.model
        provider = session.provider

    if alive:
        session.status = "ready"
    else:
        session.status = "closed"

    duration = time.time() - sent_at

    logger.debug(
        "pi-rpc: session %s response collected (%.1fs, %d chars, timed_out=%s)",
        session.session_id, duration, len(turn_text), timed_out,
    )

    if _ctx_ref:
        if timed_out:
            note = (
                f"[pi-bridge] Session `{session.session_id}` response timed out after {timeout:.0f}s. "
                f"Partial output below.\n\n"
            )
        else:
            model_info = f"{provider}/{model}" if provider and model else (model or provider or "")
            note = f"[pi-bridge] Session `{session.session_id}` response ready. {model_info}\n\n"

        inject = (
            f"{note}"
            f"**pi output:**\n{turn_text or '(no text output — pi may have used tools only)'}\n\n"
            f"Review pi's output above. Decide whether to:\n"
            f"- Send the next instruction: pi_session_send(session_id=\"{session.session_id}\", message=\"...\")\n"
            f"- Read buffered events: pi_session_read(session_id=\"{session.session_id}\")\n"
            f"- Stop the session: pi_session_stop(session_id=\"{session.session_id}\")"
        )
        _ctx_ref.inject_message(inject, role="user")
    else:
        logger.warning("pi-rpc: no ctx_ref for session %s, response not injected", session.session_id)


def send_message(
    session_id: str,
    message: str,
    streaming_behavior: str = "followUp",
) -> dict:
    """
    Send a prompt to the pi RPC session and return immediately.

    A background watcher thread waits for the explicit 'response' completion
    event, then injects the result into Hermes via inject_message.

    Args:
        session_id: The session to send to.
        message: The prompt text.
        streaming_behavior: "followUp" (continue conversation) or "steer" (redirect).
    """
    session = _sessions.get(session_id)
    if not session:
        return {"error": f"Session {session_id!r} not found"}
    if session.status == "closed":
        return {"error": f"Session {session_id!r} is closed"}
    if session.status == "error":
        return {"error": f"Session {session_id!r} is in error state: {session.error}"}
    if not session.is_alive:
        session.status = "closed"
        return {"error": f"Session {session_id!r} process has exited"}

    # Reset turn state
    with session._lock:
        session._turn_text = ""
        session._turn_done = False
        session._turn_event.clear()

    session.status = "busy"
    sent_at = time.time()

    # Send the RPC prompt command
    ok = _send_rpc(session, {
        "type": "prompt",
        "message": message,
        "streamingBehavior": streaming_behavior,
    })

    if not ok:
        session.status = "ready"
        return {"error": f"Failed to send message to session {session_id!r}"}

    # Start background watcher that will inject_message when done
    watcher = threading.Thread(
        target=_response_watcher,
        args=(session, sent_at),
        daemon=True,
        name=f"pi-watcher-{session_id}",
    )
    watcher.start()

    logger.debug("pi-rpc: sent prompt to session %s, watcher started", session_id)

    return {
        "status": "responding",
        "session_id": session_id,
        "message": (
            f"Prompt sent to pi session `{session_id}`. "
            f"Hermes will be automatically notified when pi finishes responding. "
            f"Do NOT poll — wait for the notification, then assess pi's output and decide next steps."
        ),
    }


# ---------------------------------------------------------------------------
# Read / wait
# ---------------------------------------------------------------------------

def read_output(session_id: str, full: bool = False) -> dict:
    """Return buffered text from the session without sending anything."""
    session = _sessions.get(session_id)
    if not session:
        return {"error": f"Session {session_id!r} not found"}

    with session._lock:
        text = session._text_buffer if full else session._turn_text
        event_count = len(session._event_buffer)

    return {
        "status": session.status,
        "text": text,
        "turn_done": session._turn_done,
        "event_count": event_count,
        "process_alive": session.is_alive,
    }


def wait_for_response(session_id: str, timeout: float = 30.0) -> dict:
    """
    Block up to timeout seconds waiting for the current prompt to complete.
    Returns current text whether or not the turn finished.
    Safe to call (30s default keeps agent thread responsive).
    """
    session = _sessions.get(session_id)
    if not session:
        return {"error": f"Session {session_id!r} not found"}

    fired = session._turn_event.wait(timeout=timeout)

    with session._lock:
        text = session._turn_text
        done = session._turn_done

    return {
        "status": session.status,
        "text": text,
        "turn_done": done,
        "timed_out": not fired,
        "process_alive": session.is_alive,
        "note": (
            "pi has finished responding." if done
            else "pi is still responding. The background watcher will notify Hermes when done."
        ),
    }


# ---------------------------------------------------------------------------
# Stop
# ---------------------------------------------------------------------------

def stop_session(session_id: str) -> dict:
    """Abort and close a pi RPC session."""
    session = _sessions.get(session_id)
    if not session:
        return {"error": f"Session {session_id!r} not found"}

    session._stop_reader = True

    if session.is_alive:
        # Try graceful abort first
        _send_rpc(session, {"type": "abort"})
        time.sleep(0.5)

        # Close stdin to signal EOF to pi
        try:
            session._proc.stdin.close()
        except OSError:
            pass

        # Give it a moment to exit cleanly
        try:
            session._proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            session._proc.kill()

    # Unblock any waiters
    session._turn_event.set()

    if session._reader_thread and session._reader_thread.is_alive():
        session._reader_thread.join(timeout=3.0)

    session.status = "closed"
    duration = time.time() - session.created_at

    return {
        "status": "closed",
        "session_id": session_id,
        "pi_session_file": session.pi_session_file,
        "duration_seconds": round(duration, 1),
        "model": session.model,
        "provider": session.provider,
    }
