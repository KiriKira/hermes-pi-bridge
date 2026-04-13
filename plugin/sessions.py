"""
Task and session state management for the pi bridge.

Tracks in-progress and completed pi tasks within a Hermes session.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class PiTask:
    task_id: str
    prompt: str
    status: str          # "running" | "completed" | "failed" | "timeout"
    created_at: float
    completed_at: Optional[float] = None
    working_dir: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None
    num_turns: int = 0
    duration_ms: int = 0
    model: Optional[str] = None
    provider: Optional[str] = None


_tasks: Dict[str, PiTask] = {}
_pending_injection: List[str] = []


def create_task(prompt: str, working_dir: Optional[str] = None) -> PiTask:
    task = PiTask(
        task_id=str(uuid.uuid4())[:8],
        prompt=prompt,
        status="running",
        created_at=time.time(),
        working_dir=working_dir,
    )
    _tasks[task.task_id] = task
    return task


def get_task(task_id: str) -> Optional[PiTask]:
    return _tasks.get(task_id)


def list_tasks() -> List[PiTask]:
    return sorted(_tasks.values(), key=lambda t: t.created_at, reverse=True)


def complete_task(
    task_id: str,
    result: str,
    num_turns: int = 0,
    duration_ms: int = 0,
    model: Optional[str] = None,
    provider: Optional[str] = None,
) -> None:
    task = _tasks.get(task_id)
    if not task:
        return
    task.status = "completed"
    task.result = result
    task.num_turns = num_turns
    task.duration_ms = duration_ms
    task.model = model
    task.provider = provider
    task.completed_at = time.time()
    _pending_injection.append(task_id)


def fail_task(task_id: str, error: str) -> None:
    task = _tasks.get(task_id)
    if not task:
        return
    task.status = "failed"
    task.error = error
    task.completed_at = time.time()
    _pending_injection.append(task_id)


def pop_pending_results() -> List[PiTask]:
    items = list(_pending_injection)
    _pending_injection.clear()
    return [_tasks[tid] for tid in items if tid in _tasks]


def running_count() -> int:
    return sum(1 for t in _tasks.values() if t.status == "running")
