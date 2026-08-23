"""Function-calling schemas for the Hermes -> pi bridge tools."""

_COMMON_MODEL_PROPERTIES = {
    "effort": {
        "type": "string",
        "enum": ["fast", "standard", "deep"],
        "description": (
            "Semantic cost/reasoning tier. The bridge resolves this through the "
            "current Hermes profile's pi-bridge plugin settings. Explicit model/provider/thinking overrides win."
        ),
    },
    "model": {
        "type": "string",
        "description": "Optional pi model ID/pattern override. Omit to use the effort mapping or pi default.",
    },
    "provider": {
        "type": "string",
        "description": "Optional pi provider override. Omit to use the effort mapping or pi default.",
    },
    "thinking": {
        "type": "string",
        "enum": ["off", "minimal", "low", "medium", "high", "xhigh"],
        "description": "Optional reasoning depth override. Explicit values override the effort mapping.",
    },
    "tools": {
        "type": "string",
        "description": "Optional comma-separated pi tool list.",
    },
    "system_prompt": {
        "type": "string",
        "description": "Optional replacement for pi's default system prompt.",
    },
    "append_system_prompt": {
        "type": "string",
        "description": "Optional instructions appended to pi's default system prompt.",
    },
}

PI_CHECK_SCHEMA = {
    "name": "pi_check",
    "description": (
        "Check whether pi is installed and report basic local configuration state, "
        "including configured fast/standard/deep routing for this Hermes profile."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

PI_TASK_SCHEMA = {
    "name": "pi_task",
    "description": (
        "Run one focused pi task synchronously. Use this when the work can be described "
        "well in one prompt. Use a persistent pi session for iterative or multi-phase work."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Complete task instruction for pi.",
            },
            "working_dir": {
                "type": "string",
                "description": "Optional absolute working directory.",
            },
            **_COMMON_MODEL_PROPERTIES,
            "timeout": {
                "type": "integer",
                "description": "Maximum seconds to wait. Default: 900.",
                "default": 900,
            },
        },
        "required": ["prompt"],
    },
}

PI_SESSION_START_SCHEMA = {
    "name": "pi_session_start",
    "description": (
        "Start a persistent pi RPC session. Use it when several dependent steps, "
        "iteration, or steering are expected."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "working_dir": {
                "type": "string",
                "description": "Absolute directory pi should operate in.",
            },
            **_COMMON_MODEL_PROPERTIES,
            "persist_session": {
                "type": "boolean",
                "description": "Persist pi session state on disk. Default: true.",
                "default": True,
            },
            "ready_timeout": {
                "type": "number",
                "description": "Seconds to wait for RPC readiness. Default: 15.",
                "default": 15,
            },
        },
        "required": ["working_dir"],
    },
}

PI_SESSION_SEND_SCHEMA = {
    "name": "pi_session_send",
    "description": (
        "Send one instruction to an active pi RPC session. Returns immediately; "
        "Hermes is notified when the response completes. Do not stack prompts."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "message": {"type": "string"},
            "streaming_behavior": {
                "type": "string",
                "enum": ["followUp", "steer"],
                "description": "Use followUp normally; use steer only to redirect an active line of work.",
                "default": "followUp",
            },
        },
        "required": ["session_id", "message"],
    },
}

PI_SESSION_READ_SCHEMA = {
    "name": "pi_session_read",
    "description": "Read buffered text from an existing pi RPC session.",
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "full": {
                "type": "boolean",
                "description": "Return all session text instead of only the current/last turn.",
                "default": False,
            },
        },
        "required": ["session_id"],
    },
}

PI_SESSION_STOP_SCHEMA = {
    "name": "pi_session_stop",
    "description": "Abort and close a pi RPC session. Always close sessions when a flow finishes.",
    "parameters": {
        "type": "object",
        "properties": {"session_id": {"type": "string"}},
        "required": ["session_id"],
    },
}

PI_SESSION_LIST_SCHEMA = {
    "name": "pi_session_list",
    "description": "List pi RPC sessions in the current Hermes process.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}
