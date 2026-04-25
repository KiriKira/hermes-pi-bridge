# Hermes Pi Bridge — Improvement Plan

## Project Summary

A Python plugin for the Hermes Agent framework that bridges to `pi` (a terminal-based AI coding agent). Enables Hermes to delegate coding tasks to pi via two modes: one-shot task execution (sync/async) and interactive RPC sessions (PTY-based multi-turn). Includes trigger detection to auto-identify coding requests in Hermes conversations and inject skill-loading instructions. Pure stdlib Python, no pip dependencies.

**Tech stack:** Python 3.9+, Hermes Agent plugin framework, subprocess/stdout protocol for pi communication.

---

## Quality-of-Life Improvements

### Phase 1: Reliability & Robustness

**1. Session Timeout Handling**
RPC sessions have a max of 3 concurrent but no per-session timeout beyond the implicit `pi_task_async` 30-minute default. Add configurable idle timeouts (e.g., "close session after 5 minutes of no new output") and heartbeat detection to detect stuck/zombie sessions.

**2. Process Leak Prevention**
Sessions kill with SIGINT → stdin close → kill fallback, but there's no race condition handling if the reader thread is still reading when `stop_session` returns. Add a context-manager pattern that guarantees cleanup on exception paths too.

**3. Structured Output Parsing (NDJSON)**
The RPC protocol parsing relies on specific event names and fields. If pi changes its output format, parsing silently fails. Add schema validation for incoming events with detailed error messages rather than silent drops.

**4. Concurrent Session Isolation**
With up to 3 concurrent sessions, output from one session could be misattributed to another if the reader thread reads too aggressively. Add per-session event queues with explicit routing via session ID.

### Phase 2: Feature Expansion

**5. Session Recording / Replay**
Record all session interactions (prompts sent, responses received, timing) to a file. Allow replaying a past session for debugging or documentation purposes. Export as JSON or structured markdown.

**6. Skill Auto-Loading Detection**
Currently the plugin instructs Hermes via `pre_llm_call` to "load the delegation skill." There's no verification that the skill actually loaded or is available. Add a startup hook that verifies all skill files exist and are readable, reporting errors early.

**7. Multi-Provider Support**
The pi subprocess accepts model/provider parameters but the plugin has no way to discover which models/providers pi supports. Add a `pi_check` command that probes pi's config and reports available models, thinking levels, and toolsets.

**8. Chunked Prompt Sending**
For very large prompts (>4096 chars), send them as multiple chunks with a delimiter so pi doesn't interpret the entire message as a single instruction. This could improve parsing for complex multi-part coding tasks.

### Phase 3: Integration & UX

**9. Hermes Context Enrichment**
When `inject_message` fires after an async task completes, it just dumps the raw text result. Add structured context: attach file diffs produced by pi, list of commands executed, and a summary of what was done. Makes it easier for Hermes to assess the output.

**10. Error Recovery Strategies**
If pi crashes mid-session, the plugin should detect this and automatically restart pi with an appropriate error message to Hermes rather than hanging indefinitely. Add exponential backoff for connection retries.

**11. Parallel Skill Installation Verification**
The `install.sh` symlinks are fragile — if the user changes their home directory structure or removes skills manually, the plugin silently fails. Add a runtime check in the plugin's startup hook that verifies all symlinks and reports missing components.

---

## Priority Order

| # | Feature | Effort | Impact | Rationale |
|---|---------|--------|--------|-----------|
| 1 | Process leak prevention | Low | High | Prevents resource leaks in long-running Hermes sessions |
| 2 | Session timeout/heartbeat | Low-Medium | High | Keeps zombie sessions from accumulating |
| 3 | Structured output parsing | Medium | High | Reliability of the entire bridge |
| 4 | Error recovery strategies | Low-Medium | Medium | Improves resilience |
| 5 | Hermes context enrichment | Low-Medium | Medium | Better integration with agent framework |
| 6 | Multi-provider support | Low | Medium | User configuration awareness |
| 7 | Session recording/replay | Medium | Medium | Debugging and documentation |
