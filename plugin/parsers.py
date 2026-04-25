"""
Structured output parsing and schema validation for pi RPC events.

pi emits NDJSON events over stdout. This module defines the expected schema
for each event type, validates incoming events, and returns richly-typed
Python objects. If pi changes its output format, the validator reports
exactly which field is missing or wrong — making failures actionable rather
than silent.

Schema reference (pi --mode rpc):
  https://github.com/badlogic/pi-mono/blob/main/pi/src/main/java/com/github/badlogic/pi/actions/RpcAction.java
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Known event types
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    MESSAGE_START = "message_start"
    MESSAGE_UPDATE = "message_update"
    TEXT_DELTA = "text_delta"        # shortcut for message_update/assistantMessageEvent/type=text_delta
    TEXT_END = "text_end"            # shortcut for message_update/assistantMessageEvent/type=text_end
    TURN_END = "turn_end"
    RESPONSE = "response"
    ERROR = "error"
    UNKNOWN = "unknown"


# Schema: field name -> (required: bool, expected_type)
_EVENT_SCHEMAS: Dict[str, Dict[str, Tuple[bool, Any]]] = {
    EventType.MESSAGE_START: {
        "type": (True, str),
        "message": (True, dict),
    },
    EventType.MESSAGE_UPDATE: {
        "type": (True, str),
        "assistantMessageEvent": (True, dict),
    },
    EventType.TURN_END: {
        "type": (True, str),
        "message": (False, dict),
        "toolResults": (False, list),
    },
    EventType.RESPONSE: {
        "type": (True, str),
        "command": (True, str),
        "success": (False, bool),
        "error": (False, str),
        "data": (False, dict),
    },
    EventType.ERROR: {
        "type": (True, str),
        "message": (False, str),
        "code": (False, str),
    },
}

_KNOWN_COMMANDS = {"prompt", "get_state", "get_last_assistant_text", "abort", "reset"}


# ---------------------------------------------------------------------------
# Typed result objects
# ---------------------------------------------------------------------------

@dataclass
class AssistantMessageEvent:
    """Parsed assistantMessageEvent from message_update."""
    ae_type: str = ""
    delta: str = ""
    content: str = ""


@dataclass
class MessageStartEvent:
    """Parsed message_start event."""
    role: str = ""
    model: Optional[str] = None
    provider: Optional[str] = None


@dataclass
class TurnEndEvent:
    """Parsed turn_end event."""
    role: Optional[str] = None
    content: List[str] = field(default_factory=list)
    model: Optional[str] = None
    provider: Optional[str] = None
    tool_results: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ResponseEvent:
    """Parsed response event (RPC command completion)."""
    command: str = ""
    success: bool = False
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


@dataclass
class ErrorEvent:
    """Parsed error event from pi."""
    message: str = ""
    code: Optional[str] = None


@dataclass
class ParsedRPCEvent:
    """
    Fully parsed, validated pi RPC event.

    Exactly one of the typed attributes is non-None depending on etype.
    """
    raw: Dict[str, Any]
    etype: EventType
    message_start: Optional[MessageStartEvent] = None
    message_update: Optional[AssistantMessageEvent] = None
    turn_end: Optional[TurnEndEvent] = None
    response: Optional[ResponseEvent] = None
    error: Optional[ErrorEvent] = None
    validation_errors: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.validation_errors) == 0

    @property
    def is_turn_complete(self) -> bool:
        """True when we've seen the definitive end-of-turn signal."""
        return self.etype == EventType.RESPONSE and self.response is not None


# ---------------------------------------------------------------------------
# Schema validator
# ---------------------------------------------------------------------------

def _check_type(value: Any, expected: Any, path: str, errors: List[str]) -> None:
    """Append an error to errors if value doesn't match expected type."""
    if expected is None:
        return
    if isinstance(expected, type) and isinstance(value, expected):
        return
    if isinstance(expected, tuple) and isinstance(value, expected):
        return
    actual_type = type(value).__name__
    expected_name = expected.__name__ if isinstance(expected, type) else str(expected)
    errors.append(f"  {path}: expected {expected_name}, got {actual_type}")


def validate_event(raw: Dict[str, Any]) -> Tuple[EventType, List[str]]:
    """
    Validate a raw pi RPC event dict against its expected schema.

    Returns (detected_etype, list_of_errors).
    Errors are human-readable: "  field.subfield: expected str, got int".
    """
    errors: List[str] = []
    etype_str = raw.get("type", "")

    if etype_str == "message_start":
        etype = EventType.MESSAGE_START
    elif etype_str == "message_update":
        etype = EventType.MESSAGE_UPDATE
    elif etype_str == "turn_end":
        etype = EventType.TURN_END
    elif etype_str == "response":
        etype = EventType.RESPONSE
    elif etype_str == "error":
        etype = EventType.ERROR
    else:
        etype = EventType.UNKNOWN
        errors.append(f"  type: unknown event type {etype_str!r} — schema validation skipped")

    if etype == EventType.UNKNOWN:
        return etype, errors

    schema = _EVENT_SCHEMAS.get(etype, {})

    for field_name, (required, expected_type) in schema.items():
        value = raw.get(field_name)
        if value is None:
            if required:
                errors.append(f"  {field_name}: required field is missing")
        else:
            _check_type(value, expected_type, field_name, errors)

    # Additional semantic checks for RESPONSE events
    if etype == EventType.RESPONSE:
        cmd = raw.get("command", "")
        if cmd and cmd not in _KNOWN_COMMANDS:
            errors.append(
                f"  command: unknown command {cmd!r} "
                f"(known: {', '.join(sorted(_KNOWN_COMMANDS))})"
            )

    return etype, errors


# ---------------------------------------------------------------------------
# Full parser
# ---------------------------------------------------------------------------

def parse_event(raw: Dict[str, Any]) -> ParsedRPCEvent:
    """
    Parse and validate a raw pi RPC event dict.

    Returns a ParsedRPCEvent with typed sub-objects for known event types.
    validation_errors is non-empty if the event failed schema validation —
    pi may have changed its output format.
    """
    etype_str = raw.get("type", "unknown")
    etype, schema_errors = validate_event(raw)

    result = ParsedRPCEvent(raw=raw, etype=etype, validation_errors=schema_errors)

    # If the event failed schema validation, skip parsing typed sub-objects.
    # The validation_errors are already set; don't crash trying to parse
    # from malformed data (e.g., message field is a string instead of dict).
    if schema_errors:
        return result

    if etype == EventType.MESSAGE_START:
        msg = raw.get("message", {})
        result.message_start = MessageStartEvent(
            role=msg.get("role", ""),
            model=msg.get("model"),
            provider=msg.get("provider"),
        )

    elif etype == EventType.MESSAGE_UPDATE:
        ae = raw.get("assistantMessageEvent", {})
        ae_type = ae.get("type", "")
        result.message_update = AssistantMessageEvent(
            ae_type=ae_type,
            delta=ae.get("delta", "") if ae_type == "text_delta" else "",
            content=ae.get("content", "") if ae_type == "text_end" else "",
        )

    elif etype == EventType.TURN_END:
        msg = raw.get("message", {})
        content_list = msg.get("content", [])
        texts = [c.get("text", "") for c in content_list if c.get("type") == "text"]
        result.turn_end = TurnEndEvent(
            role=msg.get("role"),
            content=texts,
            model=msg.get("model"),
            provider=msg.get("provider"),
            tool_results=raw.get("toolResults", []),
        )

    elif etype == EventType.RESPONSE:
        result.response = ResponseEvent(
            command=raw.get("command", ""),
            success=raw.get("success", False),
            error=raw.get("error"),
            data=raw.get("data"),
        )

    elif etype == EventType.ERROR:
        result.error = ErrorEvent(
            message=raw.get("message", ""),
            code=raw.get("code"),
        )

    if schema_errors:
        logger.warning(
            "pi-rpc: schema validation failed for event type %r: %s",
            etype_str,
            "; ".join(schema_errors),
        )

    return result


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def extract_turn_text(event: ParsedRPCEvent) -> str:
    """Extract joined text from a turn_end ParsedRPCEvent."""
    if event.turn_end is None:
        return ""
    return "\n".join(event.turn_end.content)