---
name: vdl-verified-development-loop
description: Use when the user asks about the verified development loop's steps or approval gates, or explicitly asks to run it for one feature or significant bug. Explain the process for questions; do not start it for ordinary coding, small bug fixes, or workflow maintenance.
---

# VDL-Verified-Development-Loop

The main agent owns scope, human communication, and every state transition. The role files below are the subagent contracts; pass the selected file's full text and its required Task inputs to the host's native subagent tool. These shared definitions require no `.codex/agents`, `.claude/agents`, or `.cursor/agents` files. Confirm the actual child model and effort when visible; if delegation is unavailable, report the limitation and do not claim a role ran. Scripts gate transitions and store evidence; they do not run agents.

## Modes

Use the feature flow below unchanged. Use bug mode only when the user explicitly invokes VDL for a significant bug; ask one question if bug versus feature is unclear. Reproduce, delegate read-only diagnosis to [investigator](agents/investigator.md), then prepare the [Bug Spec](assets/templates/bug-spec.md) and repair Plan for one human approval before TDD. Read [execution](references/execution.md) for routing and stop conditions. Load only the role contract needed for the current handoff.

| Handoff | Role contract | Main agent action on return |
| --- | --- | --- |
| After interview, before proposal | [planner](agents/planner.md) | Check `READY` Spec, Plan, proposal fields, test source, and QA mapping; run `propose`, then present drafts for approval. |
| After approval, or for an authorized fix round | [TDD coder](agents/tdd-coder.md) | Check the coder's Markdown handoff report, `DONE` files, and Red/Green evidence; run official `verify`. |
| After current verification PASS | [code reviewer](agents/code-reviewer.md) | Check the reviewer's Markdown report, `PASS`/`FAIL` findings, and evidence; record the actual `review` result. |
| After current review PASS | [QA tester](agents/qa-tester.md) | Check the report and every approved scenario; record the actual `qa` result. |

At each handoff, identify the role ID, Plan/Task ID, approved scope, input paths or content, required return fields, and the action the child must avoid. Use the role ID as the native subagent task name when the host supports names; retain the actual child identity separately because a CLI `--agent-id` role label does not prove who ran. Read the role's returned status and evidence before any state gate. Missing fields, `BLOCKED`, or unfinished work are not PASS; resolve the handoff or block the Task as appropriate. Keep reviewer and QA independent of the coder, and do not run them against code still being changed. The main agent alone runs `workflow.py` state transitions and communicates with the human.

For feature mode:

1. Read only relevant `.verified-development-loop/errors/*.md`, then interview the human. Read [planning](references/planning.md) for the approval boundary.
2. Ask the planner for a Spec using the [Spec template](assets/templates/template-spec.md) and a [Plan](assets/templates/template-plan.md) containing QA scenarios for every Task. Use `workflow.py propose --input ...` to save both as Markdown in `.verified-development-loop/specs/drafts/` and `.verified-development-loop/plans/drafts/`, then present them together for one human approval. Until approval, do not edit application code or populate active directories.
3. After approval, run `python <skill-dir>/scripts/workflow.py approve ...`; this moves the Spec to `.verified-development-loop/specs/active/` and activates the Plan and Task. Completing the Plan moves its Spec to `.verified-development-loop/specs/completed/`. Read [execution](references/execution.md) for TDD, verification, review, QA, and bounded fixes.
4. Use the script for verification, review, QA evidence, errors, and completion transitions. After review PASS, delegate QA using the approved scenarios and [QA report template](assets/templates/template-qa-report.md); record its result with `workflow.py qa` before `complete-task`. For a live dashboard on any host, emit `raw_prompt.received` when this workflow actually starts, then emit each phase's `.started` checkpoint immediately before doing that work and its completion only after finishing, including `qa.started` and `qa.completed`. The main agent owns these checkpoints around native subagent work; state-gate commands emit their own events. Do not infer a workflow phase from an arbitrary tool call or generic host hook. Read [real-time tracking](references/tracking.md) for commands, and [state management](references/state-management.md), [error memory](references/error-memory.md), [evidence contract](references/evidence-contract.md) when performing those operations.
5. At every completed, blocked, or human-accepted-error ending, fill the [human report template](assets/templates/template-human-report.md), run `workflow.py write-report` to save a new file in `.verified-development-loop/reports/`, then make the matching state transition. Summarize that saved file to the human with its path. If writing fails, keep the current state and report the file error. A blocked Task stays in the active group until a human decision; the report records its blocker, evidence, attempted rounds, and choices.

For installation and host-specific limits, read [portability](references/portability.md). Host hooks are optional lifecycle telemetry; the shared CLI emits workflow checkpoints without them. The script gates only transitions made through it. Human approval, reviewer independence, acceptance judgment, and adherence to scope require agent and human discipline.
