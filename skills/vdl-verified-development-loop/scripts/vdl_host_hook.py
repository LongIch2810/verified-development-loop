"""Host lifecycle hook handler for VDL real-time tracking.

Receives lifecycle events from supported hosts on STDIN, maps them to VDL events,
and records them in the project's append-only event store and local dashboard.
"""

import json
import os
import sys
from pathlib import Path

# Ensure local imports work
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from vdl_events import emit_event
except Exception:
    emit_event = None


def find_project_root() -> Path:
    """Detects repository root from cwd, tool payload, or environment."""
    # 1. Environment variable override
    env_root = os.environ.get("VDL_PROJECT_ROOT")
    if env_root and Path(env_root).exists():
        return Path(env_root).resolve()

    # 2. Check current working directory and walk up
    cwd = Path.cwd().resolve()
    curr = cwd
    while True:
        if (curr / ".git").exists() or (curr / "AGENTS.md").exists() or (curr / ".agents").exists():
            return curr
        if curr.parent == curr:
            break
        curr = curr.parent

    return cwd


def handle_hook():
    try:
        raw_input = sys.stdin.read().strip()
        if not raw_input:
            return
        data = json.loads(raw_input)
    except Exception:
        return

    if not isinstance(data, dict):
        return

    # Extract target root if tool_input has cwd
    root = find_project_root()
    tool_input = data.get("tool_input")
    if isinstance(tool_input, dict) and "cwd" in tool_input:
        cand = Path(tool_input["cwd"]).resolve()
        if cand.exists():
            root = cand

    if not emit_event:
        return

    event_name = data.get("hook_event_name") or data.get("event") or (sys.argv[1] if len(sys.argv) > 1 else "")
    session_id = data.get("session_id") or data.get("conversation_id") or data.get("parent_conversation_id") or "default"
    agent_id = data.get("agent_id") or data.get("subagent_id")
    agent_type = data.get("agent_type") or data.get("subagent_type") or ""
    model = data.get("model") or data.get("subagent_model")

    # Host lifecycle events remain generic; workflow roles come from explicit phase events.
    if event_name in ("SessionStart", "session_start", "sessionStart"):
        emit_event(
            root,
            event_type="session.started",
            status="RUNNING",
            source="hook",
            session_id=session_id,
            agent_id=agent_id,
            data={"model": model, "agent_type": agent_type},
        )

    elif event_name in ("UserPromptSubmit", "user_prompt_submit", "beforeSubmitPrompt"):
        prompt = data.get("prompt") or data.get("last_user_message") or ""
        preview = prompt[:100] + ("..." if len(prompt) > 100 else "")
        emit_event(
            root,
            event_type="prompt.received",
            status="COMPLETED",
            source="hook",
            session_id=session_id,
            data={"prompt_preview": preview},
        )

    elif event_name in ("SubagentStart", "subagent_start", "subagentStart"):
        emit_event(
            root,
            event_type="subagent.started",
            status="RUNNING",
            source="hook",
            session_id=session_id,
            agent_id=agent_id or agent_type,
            data={"agent_type": agent_type, "model": model},
        )

    elif event_name in ("SubagentStop", "subagent_stop", "subagentStop"):
        outcome = data.get("status", "completed")
        emit_event(
            root,
            event_type="subagent.completed" if outcome == "completed" else "subagent.failed",
            status="COMPLETED" if outcome == "completed" else "FAILED",
            source="hook",
            session_id=session_id,
            agent_id=agent_id or agent_type,
            data={"agent_type": agent_type, "outcome": outcome},
        )

    elif event_name in ("Stop", "stop", "sessionEnd"):
        emit_event(
            root,
            event_type="session.stopped",
            status="COMPLETED",
            source="hook",
            session_id=session_id,
            data={"reason": data.get("reason")},
        )


if __name__ == "__main__":
    try:
        handle_hook()
    except Exception:
        pass
    # Cursor requires JSON even from an observability-only subagentStart hook.
    print('{"permission":"allow"}' if "subagentStart" in sys.argv else "{}")
