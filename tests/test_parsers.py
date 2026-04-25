"""
Tests for parsers.py — schema validation and parsing for pi RPC events.

Run: python -m pytest tests/test_parsers.py -v
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from plugin.parsers import (
    EventType,
    ParsedRPCEvent,
    parse_event,
    validate_event,
    extract_turn_text,
    MessageStartEvent,
    TurnEndEvent,
    ResponseEvent,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def assert_valid(event: ParsedRPCEvent, expected_type: EventType) -> None:
    assert event.is_valid, f"Expected valid event, got errors: {event.validation_errors}"
    assert event.etype == expected_type, f"Expected {expected_type}, got {event.etype}"


def assert_invalid(raw: dict) -> None:
    event = parse_event(raw)
    assert not event.is_valid, f"Expected invalid event for {raw.get('type')}, but it was valid"
    assert len(event.validation_errors) > 0


# ---------------------------------------------------------------------------
# Schema validation — MESSAGE_START
# ---------------------------------------------------------------------------

def test_message_start_valid():
    raw = {"type": "message_start", "message": {"role": "assistant", "model": "claude"}}
    event = parse_event(raw)
    assert_valid(event, EventType.MESSAGE_START)
    assert event.message_start is not None
    assert event.message_start.role == "assistant"
    assert event.message_start.model == "claude"


def test_message_start_missing_type():
    assert_invalid({"message": {"role": "assistant"}})


def test_message_start_missing_message():
    assert_invalid({"type": "message_start"})


def test_message_start_message_wrong_type():
    assert_invalid({"type": "message_start", "message": "not a dict"})


# ---------------------------------------------------------------------------
# Schema validation — MESSAGE_UPDATE
# ---------------------------------------------------------------------------

def test_message_update_text_delta_valid():
    raw = {"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "delta": "hello"}}
    event = parse_event(raw)
    assert_valid(event, EventType.MESSAGE_UPDATE)
    assert event.message_update is not None
    assert event.message_update.ae_type == "text_delta"
    assert event.message_update.delta == "hello"


def test_message_update_text_end_valid():
    raw = {"type": "message_update", "assistantMessageEvent": {"type": "text_end", "content": "full response"}}
    event = parse_event(raw)
    assert_valid(event, EventType.MESSAGE_UPDATE)
    assert event.message_update is not None
    assert event.message_update.ae_type == "text_end"
    assert event.message_update.content == "full response"


def test_message_update_missing_ae():
    assert_invalid({"type": "message_update"})


def test_message_update_ae_wrong_type():
    assert_invalid({"type": "message_update", "assistantMessageEvent": ["list", "not", "dict"]})


# ---------------------------------------------------------------------------
# Schema validation — TURN_END
# ---------------------------------------------------------------------------

def test_turn_end_valid():
    raw = {
        "type": "turn_end",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "final answer"}],
            "model": "claude",
            "provider": "anthropic",
        },
        "toolResults": [],
    }
    event = parse_event(raw)
    assert_valid(event, EventType.TURN_END)
    te = event.turn_end
    assert te is not None
    assert te.role == "assistant"
    assert te.content == ["final answer"]
    assert te.model == "claude"
    assert te.provider == "anthropic"
    assert te.tool_results == []


def test_turn_end_optional_fields_missing():
    raw = {"type": "turn_end", "message": {"role": "assistant", "content": []}}
    event = parse_event(raw)
    assert_valid(event, EventType.TURN_END)
    assert event.turn_end is not None
    assert event.turn_end.tool_results == []


def test_turn_end_message_wrong_type():
    assert_invalid({"type": "turn_end", "message": "not a dict"})


def test_turn_end_tool_results_wrong_type():
    assert_invalid({"type": "turn_end", "message": {}, "toolResults": "not a list"})


# ---------------------------------------------------------------------------
# Schema validation — RESPONSE
# ---------------------------------------------------------------------------

def test_response_prompt_success():
    raw = {"type": "response", "command": "prompt", "success": True}
    event = parse_event(raw)
    assert_valid(event, EventType.RESPONSE)
    resp = event.response
    assert resp is not None
    assert resp.command == "prompt"
    assert resp.success is True
    assert resp.error is None


def test_response_prompt_failure():
    raw = {"type": "response", "command": "prompt", "success": False, "error": "timed out"}
    event = parse_event(raw)
    assert_valid(event, EventType.RESPONSE)
    resp = event.response
    assert resp is not None
    assert resp.success is False
    assert resp.error == "timed out"


def test_response_get_state():
    raw = {"type": "response", "command": "get_state", "success": True}
    event = parse_event(raw)
    assert_valid(event, EventType.RESPONSE)


def test_response_with_data():
    raw = {"type": "response", "command": "get_last_assistant_text", "success": True, "data": {"text": "output"}}
    event = parse_event(raw)
    assert_valid(event, EventType.RESPONSE)
    assert event.response is not None
    assert event.response.data == {"text": "output"}


def test_response_missing_command():
    assert_invalid({"type": "response", "success": True})


def test_response_unknown_command():
    assert_invalid({"type": "response", "command": "invalid_command", "success": True})


def test_response_success_wrong_type():
    assert_invalid({"type": "response", "command": "prompt", "success": "yes"})


# ---------------------------------------------------------------------------
# Schema validation — ERROR
# ---------------------------------------------------------------------------

def test_error_event():
    raw = {"type": "error", "message": "something went wrong", "code": "ERR_001"}
    event = parse_event(raw)
    assert_valid(event, EventType.ERROR)
    err = event.error
    assert err is not None
    assert err.message == "something went wrong"
    assert err.code == "ERR_001"


def test_error_event_minimal():
    raw = {"type": "error", "message": "oops"}
    event = parse_event(raw)
    assert_valid(event, EventType.ERROR)
    assert event.error is not None


# ---------------------------------------------------------------------------
# Schema validation — unknown type
# ---------------------------------------------------------------------------

def test_unknown_type_not_rejected():
    """Unknown event types are marked UNKNOWN but not flagged as schema errors."""
    raw = {"type": "tool_result", "tool": "read", "result": "/home/file.txt"}
    event = parse_event(raw)
    assert event.etype == EventType.UNKNOWN
    # Should be marked invalid due to unknown type
    assert not event.is_valid
    assert any("unknown event type" in e for e in event.validation_errors)


# ---------------------------------------------------------------------------
# extract_turn_text
# ---------------------------------------------------------------------------

def test_extract_turn_text_from_turn_end():
    raw = {
        "type": "turn_end",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "line1\nline2"}],
        },
    }
    event = parse_event(raw)
    text = extract_turn_text(event)
    assert text == "line1\nline2"


def test_extract_turn_text_empty():
    event = ParsedRPCEvent(raw={}, etype=EventType.MESSAGE_START)
    assert extract_turn_text(event) == ""


# ---------------------------------------------------------------------------
# Integration: parse_event preserves raw dict
# ---------------------------------------------------------------------------

def test_parsed_event_preserves_raw():
    raw = {"type": "response", "command": "prompt", "success": True}
    event = parse_event(raw)
    assert event.raw == raw


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [fn for fn in dir() if fn.startswith("test_")]
    passed = failed = 0
    for name in tests:
        fn = globals()[name]
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {name}: {e}")
            failed += 1
    print(f"\n{passed}/{passed+failed} passed")
    exit(0 if failed == 0 else 1)