"""Function-calling schemas for the Hermes -> pi bridge tools."""

_TIER_PROPERTY = {
    "tier": {
        "type": "string",
        "enum": ["fast", "standard", "deep"],
        "description": (
            "Optional semantic routing tier. The bridge resolves it from the "
            "pi-bridge plugin settings. Explicit model/provider/thinking values override it."
        ),
    },
}

_COMMON_MODEL_PROPERTIES = {
    **_TIER_PROPERTY,
    "model": {
        "type": "string",
        "description": "Optional pi model ID/pattern override. Omit to use the tier setting or pi default.",
    },
    "provider": {
        "type": "string",
        "description": "Optional pi provider override. Omit to use the tier setting or pi default.",
    },
    "thinking": {
        "type": "string",
        "enum": ["off", "minimal", "low", "medium", "high", "xhigh", "max"],
        "description": "Optional pi reasoning-depth override.",
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
        "Check whether pi is installed and report basic local configuration plus "
        "the configured fast/standard/deep routing tiers. No credential contents are returned."
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
        "Start a persistent pi RPC session. Use it when several dependent steps or "
        "iterative work are expected."
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
        "Send one instruction to a ready pi RPC session and wait until pi emits its "
        "documented agent_settled completion event. A prompt acknowledgement alone is not completion."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "message": {"type": "string"},
            "wait_timeout": {
                "type": "number",
                "description": (
                    "Maximum seconds to wait for agent_settled. Default: 900. "
                    "A timeout does not kill the pi process; inspect with pi_session_read/list."
                ),
                "default": 900,
            },
        },
        "required": ["session_id", "message"],
    },
}

PI_SESSION_READ_SCHEMA = {
    "name": "pi_session_read",
    "description": "Read buffered text and status from an existing pi RPC session.",
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
