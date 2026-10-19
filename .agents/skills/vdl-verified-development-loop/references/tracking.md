# Real-Time Workflow Tracking

The VDL Control Center displays real-time events for the 13-step workflow. Before a workflow starts, it shows **Chưa chọn mode**, explains both modes, and displays separate Interview and Diagnosis nodes. Feature Mode shows only Interview to clarify requirements; Bug Mode shows only Diagnosis to reproduce the bug and identify its cause before Spec/Plan. The sequential log follows the selected branch, then the shared later steps. If the human requests changes before approval, revise the draft Spec/Plan and present both again; the approval arrow returns to Spec/Plan in either mode. A new diagnosis is needed only when the bug evidence or cause needs investigation again. **Thử Nghiệm FX** only simulates the UI; it does not start a workflow or write events. State-gate commands emit events automatically; the main agent must emit chat-only phase checkpoints. Host hooks add passive session and subagent lifecycle events where an adapter is installed. Without either source, the dashboard cannot observe agent activity.
1. `raw_prompt`
2. `read_errors`
3. `interview`
   - Bug mode: `diagnosis` in this position.
4. `spec`
5. `plan`
6. `human_approval`
7. `active`
8. `tdd`
9. `verification`
10. `code_review`
11. `qa`
12. `fix_loop`
13. `main_agent_report`

## Event Emission Checkpoints

All state gates in `workflow.py` automatically emit telemetry events to the append-only store in `.vdl/events.jsonl` and broadcast to running Control Center instances:
- `propose` -> emits `spec.completed`, `plan.completed`, `approval.waiting`
- `record-diagnosis` -> emits `diagnosis.completed` with the investigator evidence reference; the main agent emits `diagnosis.started` before delegation
- `approve` -> emits `approval.approved`, `workflow.started`, `task.started`
- `verify` -> emits `verification.started`, and `verification.passed` (with exit codes) or `verification.failed`
- `review` -> emits `review.started`, and `review.passed` (0 findings) or `review.failed` (with findings)
- `qa` -> emits `qa.completed` with PASS/FAIL and the QA evidence reference; the main agent emits `qa.started` before delegation
- `record-error` -> emits `error.recorded`
- `start-fix` -> emits `fix.started` (attempt counter 1/3, 2/3, 3/3)
- `join-fix` -> emits `fix.joined` (another confirmed error in the current round)
- `evaluate` -> emits `fix.completed` (resolved) or `error.recurred` + `task.blocked` (persists)
- `complete-task` -> emits `task.completed`
- `complete-plan` -> emits `plan.completed`
- `block-task` -> emits `task.blocked`
- `write-report` -> emits `report.recorded` with the saved report path before `task.blocked` or `task.completed`
- `complete-task-accepted` -> emits `task.completed` with the accepted error IDs
- `complete-plan-accepted` -> emits `plan.completed`

For workflow phases occurring in model chat, the main agent emits explicit checkpoints via CLI:
```bash
python <skill-dir>/scripts/workflow.py emit --event raw_prompt.received
# For bug mode, include --data '{"mode":"bug"}' so Control Center shows Diagnosis immediately.
python <skill-dir>/scripts/workflow.py emit --event read_errors.started
python <skill-dir>/scripts/workflow.py emit --event read_errors.completed --data '{"error_count": 0}'
python <skill-dir>/scripts/workflow.py emit --event interview.started
python <skill-dir>/scripts/workflow.py emit --event interview.completed --data '{"confirmed_scope": "..."}'
python <skill-dir>/scripts/workflow.py emit --event diagnosis.started --status RUNNING --plan-id ID --agent-id investigator
# After the investigator returns, the main agent records the report and actual diagnosis result:
python <skill-dir>/scripts/workflow.py record-diagnosis --plan-id ID --report .verified-development-loop/evidence/ID/investigator.md --result REPRODUCED --classification code --confidence high
python <skill-dir>/scripts/workflow.py emit --event tdd.started --task-id ID
python <skill-dir>/scripts/workflow.py emit --event tdd.completed --task-id ID
python <skill-dir>/scripts/workflow.py emit --event qa.started --status RUNNING --task-id ID --agent-id qa_tester
python <skill-dir>/scripts/workflow.py emit --event main_agent.started --status RUNNING
python <skill-dir>/scripts/workflow.py write-report --task-id TASK --status blocked --input .verified-development-loop/evidence/TASK/human-report.md
# After the matching state transition, summarize the saved file and emit its path:
python <skill-dir>/scripts/workflow.py emit --event main_agent.reported --task-id TASK --data '{"summary": "...", "report": ".verified-development-loop/reports/TASK-blocked-YYYYMMDD-HHMM.md"}'
```

Emit `.started` **before** the first tool call or native delegation for that phase. Emit `.completed` only after the work has actually finished. The graph highlights only a started phase; a completed phase makes the next node upcoming until it starts. Generic host prompt and subagent hook events remain in the event log but do not select a workflow node. `propose`, `approve`, `verify`, `review`, `qa`, error recording, and completion gates emit their own checkpoints when called. The QA node appears after review PASS; QA FAIL routes to error recording.

## Subagents on any host

Use the host's native subagent tool with the matching `agents/*.md` role contract. The **main agent** runs the shared CLI from the repository root at the real handoff; children do not need hooks or shell access:

```bash
python <skill-dir>/scripts/workflow.py emit --event spec.started --status RUNNING --plan-id ID --agent-id planner
# Delegate the Spec and Plan to planner; workflow.py propose emits spec.completed and plan.completed after the draft is saved.
python <skill-dir>/scripts/workflow.py emit --event tdd.started --status RUNNING --plan-id ID --task-id TASK --agent-id tdd_coder
# Delegate the approved Task to tdd_coder.
python <skill-dir>/scripts/workflow.py emit --event tdd.completed --plan-id ID --task-id TASK --agent-id tdd_coder
# Run workflow.py verify. After PASS, start independent review:
python <skill-dir>/scripts/workflow.py emit --event review.started --status RUNNING --plan-id ID --task-id TASK --agent-id code_reviewer
# Delegate to code_reviewer; workflow.py review records the actual PASS or FAIL.
# After review PASS, delegate every approved scenario to qa_tester and save its report in the Task evidence directory.
python <skill-dir>/scripts/workflow.py emit --event qa.started --status RUNNING --plan-id ID --task-id TASK --agent-id qa_tester
# Delegate to qa_tester; workflow.py qa records its actual PASS or FAIL and emits qa.completed.
```

When a child stops early or cannot finish, emit its actual status and report the blocker; never emit `tdd.completed` or a passing review for unfinished work. Pass `--task-id` and `--agent-id` for each concurrent Task so the event log identifies the worker. The dashboard's 13-step summary shows the latest phase; use the event log to inspect overlapping agents. `workflow.py emit` writes `.vdl/events.jsonl`, then notifies the dashboard at port 4040. It now returns a failure if the event cannot be stored.

## Running the Dashboard

The optional `install_vdl.py` setup starts the passive monitoring web UI automatically. To launch it manually later:
```bash
python <skill-dir>/scripts/control_center.py --port 4040
```
Open `http://127.0.0.1:4040` in a browser window alongside Codex CLI/IDE.
The dashboard automatically syncs via SSE (`/api/stream`) with automatic reconnection and `Last-Event-ID` state recovery.

Host hooks are optional. On Windows, macOS, and Linux, `install_vdl.py --target . --no-hooks --codex-hooks` registers only Codex's bundled lifecycle hook; replace `--codex-hooks` with `--claude-hooks` or `--cursor-hooks` for those hosts, or combine flags. Each supported host sends generic session and subagent events to the same `.vdl/events.jsonl` store. Other hosts still get workflow phase events through the shared CLI above. In Codex, review and trust the hook with `/hooks`; start a fresh session if configured after the current session began. Claude Code also requires workspace trust for interactive sessions. Cursor loads its project hook after a config reload. Role-specific phases always use the shared CLI, because lifecycle payloads identify host agent types rather than workflow roles.
