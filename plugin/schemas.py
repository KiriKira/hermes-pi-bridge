"""
OpenAI function-calling schemas for all pi coding agent bridge tools.
"""

PI_TASK_SCHEMA = {
    "name": "pi_task",
    "description": (
        "Delegate a coding task to the pi coding agent and wait for the result. "
        "pi is a full AI coding agent with read, write, edit, bash, grep, find, and ls tools. "
        "It can read/write files, run commands, install packages, debug, and iterate.\n\n"
        "Use this for well-defined, focused coding tasks where a single prompt is sufficient. "
        "For large multi-phase projects, use pi_session_start instead."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The task or question to send to pi. Be specific and complete.",
            },
            "working_dir": {
                "type": "string",
                "description": "Absolute path to the directory pi should operate in.",
            },
            "model": {
                "type": "string",
                "description": "Model pattern or ID override (e.g. 'claude-opus-4-6', '*sonnet*'). Defaults to pi's configured model.",
            },
            "provider": {
                "type": "string",
                "description": "Provider name override (e.g. 'anthropic', 'openai'). Defaults to pi's configured provider.",
            },
            "thinking": {
                "type": "string",
                "enum": ["off", "minimal", "low", "medium", "high", "xhigh"],
                "description": "Thinking level. Use 'high' or 'xhigh' for complex reasoning tasks.",
            },
            "tools": {
                "type": "string",
                "description": "Comma-separated tools to enable (default: read,bash,edit,write). Also available: grep,find,ls.",
            },
            "system_prompt": {
                "type": "string",
                "description": "Override the default system prompt.",
            },
            "append_system_prompt": {
                "type": "string",
                "description": "Append additional instructions to pi's default system prompt.",
            },
            "timeout": {
                "type": "integer",
                "description": "Maximum seconds to wait. Default: 900 (15 min).",
                "default": 900,
            },
        },
        "required": ["prompt"],
    },
}

PI_TASK_ASYNC_SCHEMA = {
    "name": "pi_task_async",
    "description": (
        "Start a pi coding agent task in the background and return immediately. "
        "Hermes will be automatically notified with the full result when pi finishes. "
        "Use for tasks likely to take more than 5 minutes."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The task to send to pi.",
            },
            "working_dir": {
                "type": "string",
                "description": "Absolute path to the directory pi should operate in.",
            },
            "model": {"type": "string", "description": "Model pattern or ID override."},
            "provider": {"type": "string", "description": "Provider name override."},
            "thinking": {
                "type": "string",
                "enum": ["off", "minimal", "low", "medium", "high", "xhigh"],
            },
            "tools": {"type": "string", "description": "Comma-separated tools to enable."},
            "system_prompt": {"type": "string"},
            "append_system_prompt": {"type": "string"},
            "timeout": {
                "type": "integer",
                "description": "Maximum seconds before timing out. Default: 1800 (30 min).",
                "default": 1800,
            },
        },
        "required": ["prompt"],
    },
}

PI_TASK_STATUS_SCHEMA = {
    "name": "pi_task_status",
    "description": "Check the status of a pi background task, or list all tasks. Status: running | completed | failed | timeout.",
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "Task ID to check. Omit to list all tasks.",
            },
        },
        "required": [],
    },
}

PI_TASK_RESULT_SCHEMA = {
    "name": "pi_task_result",
    "description": "Retrieve the full stored result of a completed pi task.",
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "The task ID to retrieve."},
        },
        "required": ["task_id"],
    },
}

PI_CHECK_SCHEMA = {
    "name": "pi_check",
    "description": "Check whether pi is installed, its version, and configuration status.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

# ---------------------------------------------------------------------------
# Interactive RPC session schemas
# ---------------------------------------------------------------------------

PI_SESSION_START_SCHEMA = {
    "name": "pi_session_start",
    "description": (
        "Start a persistent interactive pi coding agent session using the RPC protocol. "
        "Unlike pi_task (single prompt), an RPC session stays alive across multiple turns, "
        "maintaining full conversation context and file state between messages.\n\n"
        "Use this for:\n"
        "- Large multi-phase projects requiring iterative guidance\n"
        "- Work where each step depends on reviewing the last\n"
        "- Long sessions where Hermes needs to steer Qwen turn by turn\n\n"
        "After starting, use pi_session_send to send prompts. "
        "Hermes is notified via inject_message when pi finishes each response. "
        "Stop with pi_session_stop when done."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "working_dir": {
                "type": "string",
                "description": "Absolute path to the directory pi should operate in. Required.",
            },
            "model": {
                "type": "string",
                "description": "Model pattern or ID override. Defaults to pi's configured model.",
            },
            "provider": {
                "type": "string",
                "description": "Provider name override.",
            },
            "thinking": {
                "type": "string",
                "enum": ["off", "minimal", "low", "medium", "high", "xhigh"],
                "description": "Thinking level for the session.",
            },
            "tools": {
                "type": "string",
                "description": "Comma-separated tools to enable (default: read,bash,edit,write).",
            },
            "system_prompt": {"type": "string"},
            "append_system_prompt": {"type": "string"},
            "persist_session": {
                "type": "boolean",
                "description": "Save the session to disk for later resume. Default: true.",
                "default": True,
            },
            "ready_timeout": {
                "type": "number",
                "description": "Seconds to wait for pi to confirm ready. Default: 15.",
                "default": 15,
            },
        },
        "required": ["working_dir"],
    },
}

PI_SESSION_SEND_SCHEMA = {
    "name": "pi_session_send",
    "description": (
        "Send a prompt to an active pi RPC session and return immediately. "
        "pi processes the prompt and Hermes is automatically notified via inject_message "
        "when pi finishes responding — no polling needed.\n\n"
        "After calling this, do NOT call any other tool. Wait for the inject_message "
        "notification with pi's output, then assess and decide the next step."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {
                "type": "string",
                "description": "The session ID returned by pi_session_start.",
            },
            "message": {
                "type": "string",
                "description": "The prompt to send to pi.",
            },
            "streaming_behavior": {
                "type": "string",
                "enum": ["followUp", "steer"],
                "description": (
                    "'followUp' (default): continue the conversation normally. "
                    "'steer': interrupt current direction and redirect (use when pi is off-track)."
                ),
                "default": "followUp",
            },
        },
        "required": ["session_id", "message"],
    },
}

PI_SESSION_READ_SCHEMA = {
    "name": "pi_session_read",
    "description": (
        "Read buffered output from a pi RPC session without sending anything. "
        "Returns text accumulated since the session started (or since the last turn)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "The session ID to read from."},
            "full": {
                "type": "boolean",
                "description": "If true, return all text since session start. Default: current turn only.",
                "default": False,
            },
        },
        "required": ["session_id"],
    },
}

PI_SESSION_WAIT_SCHEMA = {
    "name": "pi_session_wait",
    "description": (
        "Wait up to timeout seconds for the current pi prompt to complete. "
        "Returns the text pi has produced so far. "
        "Safe to call from the agent thread (default 30s cap). "
        "The background watcher from pi_session_send will still notify Hermes when done."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "The session ID to wait on."},
            "timeout": {
                "type": "number",
                "description": "Maximum seconds to block. Default: 30.",
                "default": 30,
            },
        },
        "required": ["session_id"],
    },
}

PI_SESSION_STOP_SCHEMA = {
    "name": "pi_session_stop",
    "description": (
        "Stop a pi RPC session. Sends abort, closes stdin, terminates the process. "
        "Returns the pi session file path (can be used to resume later). "
        "Always stop sessions when work is complete."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "The session ID to stop."},
        },
        "required": ["session_id"],
    },
}

PI_SESSION_LIST_SCHEMA = {
    "name": "pi_session_list",
    "description": "List all pi RPC sessions (active and closed) in this Hermes session.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}
