"""Unit and integration tests for VDL Real-Time Tracking, Event Contract, and State Reducer."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "skills/vdl-verified-development-loop/scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import vdl_events as ve
import workflow as w


class VDLEventTrackingTests(unittest.TestCase):
    def test_bug_mode_returns_to_feature_graph_on_next_workflow(self):
        events = [ve.emit_event(self.root, "raw_prompt.received", data={"mode": "bug"}, notify=False)]
        bug = ve.WorkflowStateReducer.reduce(self.root, events)
        self.assertIn("diagnosis", {node["id"] for node in bug["graph"]["nodes"]})
        events.append(ve.emit_event(self.root, "diagnosis.started", status="RUNNING", notify=False))
        events.append(ve.emit_event(self.root, "raw_prompt.received", notify=False))
        feature = ve.WorkflowStateReducer.reduce(self.root, events)
        self.assertIn("interview", {node["id"] for node in feature["graph"]["nodes"]})
        self.assertNotIn("diagnosis", {node["id"] for node in feature["graph"]["nodes"]})

    def test_graph_highlights_only_a_phase_that_has_started(self):
        events = []
        def add(event_type, status="COMPLETED"):
            events.append(ve.emit_event(self.root, event_type, status=status, notify=False))
            return ve.WorkflowStateReducer.reduce(self.root, events)["graph"]

        graph = add("raw_prompt.received")
        self.assertEqual((graph["active_node_id"], graph["next_node_id"]), ("", "read_errors"))
        graph = add("read_errors.started", "RUNNING")
        self.assertEqual(graph["active_node_id"], "read_errors")
        graph = add("read_errors.completed")
        self.assertEqual((graph["active_node_id"], graph["next_node_id"]), ("", "interview"))
        graph = add("tdd.started", "RUNNING")
        self.assertEqual(graph["active_node_id"], "tdd")
        graph = add("tdd.completed")
        self.assertEqual((graph["active_node_id"], graph["next_node_id"]), ("", "verify"))
        graph = add("review.passed")
        self.assertEqual((graph["active_node_id"], graph["next_node_id"]), ("", "qa"))
        graph = add("qa.started", "RUNNING")
        self.assertEqual(graph["active_node_id"], "qa")
        events.append(ve.emit_event(self.root, "qa.completed", data={"result": "PASS"}, notify=False))
        graph = ve.WorkflowStateReducer.reduce(self.root, events)["graph"]
        self.assertEqual((graph["active_node_id"], graph["next_node_id"]), ("", "complete"))
        graph = add("task.completed")
        self.assertEqual((graph["active_node_id"], graph["next_node_id"]), ("", "report"))
        graph = add("main_agent.started", "RUNNING")
        self.assertEqual(graph["active_node_id"], "report")
        graph = add("main_agent.reported")
        self.assertEqual(graph["active_node_id"], "")

    def test_error_node_runs_only_while_recording(self):
        events = []
        def add(event_type, status="COMPLETED"):
            events.append(ve.emit_event(self.root, event_type, status=status, notify=False))
            return ve.WorkflowStateReducer.reduce(self.root, events)["graph"]

        graph = add("verification.failed", "FAILED")
        self.assertEqual((graph["active_node_id"], graph["next_node_id"]), ("", "error_rec"))
        graph = add("error.recording", "RUNNING")
        self.assertEqual(graph["active_node_id"], "error_rec")
        graph = add("error.recorded")
        self.assertEqual((graph["active_node_id"], graph["next_node_id"]), ("", "fix_loop"))
        graph = add("fix.started", "RUNNING")
        self.assertEqual(graph["active_node_id"], "fix_loop")

    def test_qa_failure_leads_to_error_recording(self):
        events = [ve.emit_event(self.root, "review.passed", notify=False)]
        events.append(ve.emit_event(self.root, "qa.started", status="RUNNING", notify=False))
        events.append(ve.emit_event(self.root, "qa.completed", status="FAILED", data={"result": "FAIL"}, notify=False))
        state = ve.WorkflowStateReducer.reduce(self.root, events)
        self.assertEqual((state["graph"]["active_node_id"], state["graph"]["next_node_id"]), ("", "error_rec"))
        self.assertEqual({s["id"]: s for s in state["steps"]}["qa"]["status"], "FAILED")

    def test_cli_emit_records_agent_phase_for_any_host(self):
        before = len(ve.EventStore(self.root).read_all())
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "workflow.py"), "--root", str(self.root),
             "emit", "--event", "tdd.started", "--status", "RUNNING", "--plan-id", "plan-alpha",
             "--task-id", "task-alpha-1", "--agent-id", "tdd_coder", "--source", "agent"],
            cwd=self.root, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        events = ve.EventStore(self.root).read_all()
        self.assertEqual(len(events), before + 1)
        self.assertEqual((events[-1].event_type, events[-1].agent_id, events[-1].source),
                         ("tdd.started", "tdd_coder", "agent"))

    def test_codex_hook_reports_lifecycle_without_guessing_role(self):
        payload = json.dumps({"hook_event_name": "SubagentStart", "agent_id": "child-1",
                              "agent_type": "tdd-coder", "session_id": "session-1"})
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "vdl_host_hook.py")],
            input=payload, cwd=self.root, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        event = ve.EventStore(self.root).read_all()[-1]
        self.assertEqual((event.event_type, event.agent_id, event.source),
                         ("subagent.started", "child-1", "hook"))

    def test_generic_prompt_hook_does_not_start_workflow_node(self):
        payload = json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "unrelated question"})
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "vdl_host_hook.py")],
            input=payload, cwd=self.root, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        events = ve.EventStore(self.root).read_all()
        self.assertEqual(events[-1].event_type, "prompt.received")
        self.assertEqual(ve.WorkflowStateReducer.reduce(self.root, events)["steps"][0]["status"], "PENDING")

    def test_cursor_hook_allows_agent_and_records_failed_stop(self):
        hook = str(SCRIPTS_DIR / "vdl_host_hook.py")
        started = subprocess.run(
            [sys.executable, hook, "subagentStart"],
            input=json.dumps({"hook_event_name": "subagentStart", "subagent_id": "worker-1",
                              "subagent_type": "generalPurpose", "subagent_model": "model-a"}),
            cwd=self.root, capture_output=True, text=True,
        )
        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertEqual(json.loads(started.stdout), {"permission": "allow"})
        stopped = subprocess.run(
            [sys.executable, hook, "subagentStop"],
            input=json.dumps({"hook_event_name": "subagentStop", "subagent_id": "worker-1",
                              "subagent_type": "generalPurpose", "status": "error"}),
            cwd=self.root, capture_output=True, text=True,
        )
        self.assertEqual(json.loads(stopped.stdout), {})
        events = ve.EventStore(self.root).read_all()
        self.assertEqual([(ev.event_type, ev.status, ev.agent_id) for ev in events[-2:]],
                         [("subagent.started", "RUNNING", "worker-1"),
                          ("subagent.failed", "FAILED", "worker-1")])

    def test_hook_uses_event_argument_when_payload_has_no_event_name(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "vdl_host_hook.py"), "subagentStart"],
            input=json.dumps({"subagent_id": "worker-2"}),
            cwd=self.root, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"permission": "allow"})
        self.assertEqual((ve.EventStore(self.root).read_all()[-1].event_type,
                          ve.EventStore(self.root).read_all()[-1].agent_id),
                         ("subagent.started", "worker-2"))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "--allow-empty", "-qm", "base"],
            cwd=self.root,
            check=True,
        )
        self.flag = self.root / "ok.txt"
        self.flag.write_text("ok", encoding="utf-8")
        self.proposal = self.root / "proposal.json"
        self.proposal.write_text(
            json.dumps({
                "plan_id": "plan-alpha",
                "spec": "Test spec acceptance criteria",
                "acceptance_criteria": ["plan works reliably"],
                "tasks": [{
                    "task_id": "task-alpha-1",
                    "acceptance_criteria": ["task 1 works reliably"],
                    "qa_plan": "| QA-01 | task 1 works reliably | Run public behavior | Observe ok |",
                    "test_code": "### tests/test_task.py\n```python\nfrom pathlib import Path\n\ndef test_task():\n    assert Path('ok.txt').read_text() == 'ok'\n```",
                    "verification": [[sys.executable, "-c", "from pathlib import Path; assert Path('ok.txt').read_text() == 'ok'"]],
                }],
            }),
            encoding="utf-8",
        )

    def save_human_report(self, status):
        source = self.root / ".verified-development-loop/evidence/task-alpha-1/human-report.md"
        source.parent.mkdir(parents=True, exist_ok=True)
        body = (f"# Human report\n\n- **Task:** task-alpha-1\n- **Status:** {status}\n\n"
                "## Overview\n\n- **Plan:** plan-alpha\n- **Spec:** plan-alpha\n- **Code:** test branch\n"
                "- **Fix rounds:** 1/3\n- **Review rounds:** 1/3\n- **QA rounds:** 1/3\n\n"
                "## Commands and Results\n\n- test: exit 0\n\n"
                "## Review and QA Rounds\n\n- review and QA evidence\n\n"
                "## Remaining Checks\n\n- none\n\n## Evidence Paths\n\n- evidence/task-alpha-1\n\n")
        if status == "blocked":
            body += ("## Open Errors\n\n- err-persists\n\n## Attempts\n\n- three rounds\n\n"
                     "## Why Not Converged\n\n- still failing\n\n## Human Options\n\n"
                     "- retry, revise, accept, cancel\n\n## Human Decision\n\n")
        source.write_text(body, encoding="utf-8")
        return w.write_report(self.root, "task-alpha-1", status, source)

    def test_event_schema_and_validation(self):
        ev = ve.VDLEvent.from_dict({
            "event_id": "test-123",
            "project_id": "repo-x",
            "session_id": "sess-456",
            "event_type": "custom.step",
            "status": "invalid_status",
            "source": "unknown_source",
            "attempt": "2",
            "data": {"key": "value"},
        })
        self.assertEqual(ev.event_id, "test-123")
        self.assertEqual(ev.status, "UNKNOWN")  # Fallback
        self.assertEqual(ev.source, "script")   # Fallback
        self.assertEqual(ev.attempt, 2)
        self.assertIn("timestamp", ev.to_dict())

    def test_event_store_append_and_dedup(self):
        store = ve.EventStore(self.root)
        ev1 = ve.VDLEvent.from_dict({
            "event_id": "unique-1",
            "project_id": "test",
            "session_id": "s1",
            "event_type": "workflow.started",
            "status": "RUNNING",
            "source": "script",
        })
        store.append(ev1)
        # Duplicate append with same event_id
        store.append(ev1)
        all_events = store.read_all()
        self.assertEqual(len(all_events), 1)

        ev2 = ve.VDLEvent.from_dict({
            "event_id": "unique-2",
            "project_id": "test",
            "session_id": "s1",
            "event_type": "task.started",
            "status": "RUNNING",
            "source": "script",
        })
        store.append(ev2)
        since_ev1 = store.get_events_since("unique-1")
        self.assertEqual(len(since_ev1), 1)
        self.assertEqual(since_ev1[0].event_id, "unique-2")

    def test_workflow_lifecycle_emissions_and_state_reduction(self):
        store = ve.EventStore(self.root)

        # 1. Propose
        w.propose(self.root, self.proposal)
        events = store.read_all()
        types = [e.event_type for e in events]
        self.assertIn("spec.completed", types)
        self.assertIn("plan.completed", types)
        self.assertIn("approval.waiting", types)

        state = ve.WorkflowStateReducer.reduce(self.root, events)
        step_map = {s["id"]: s for s in state["steps"]}
        self.assertEqual(step_map["spec"]["status"], "COMPLETED")
        self.assertEqual(step_map["plan"]["status"], "COMPLETED")
        self.assertEqual(step_map["human_approval"]["status"], "WAITING_HUMAN")

        # 2. Approve
        w.approve(self.root, "plan-alpha", "Human confirmed plan-alpha")
        events = store.read_all()
        types = [e.event_type for e in events]
        self.assertIn("approval.approved", types)
        self.assertIn("workflow.started", types)
        self.assertIn("task.started", types)

        state = ve.WorkflowStateReducer.reduce(self.root, events)
        step_map = {s["id"]: s for s in state["steps"]}
        self.assertEqual(step_map["human_approval"]["status"], "COMPLETED")
        self.assertEqual(step_map["active"]["status"], "RUNNING")

        # 3. Verification Fail
        self.flag.write_text("bad", encoding="utf-8")
        self.assertFalse(w.verify(self.root, "task-alpha-1"))
        events = store.read_all()
        self.assertEqual(events[-1].event_type, "verification.failed")
        self.assertEqual(events[-1].status, "FAILED")

        state = ve.WorkflowStateReducer.reduce(self.root, events)
        step_map = {s["id"]: s for s in state["steps"]}
        self.assertEqual(step_map["verification"]["status"], "FAILED")
        self.assertEqual(state["verification"]["status"], "FAIL")
        self.assertEqual(state["verification"]["commands"][0]["exit_code"], 1)

        # 4. Record Error and Start Fix (Round 1/3)
        w.record_error(self.root, "task-alpha-1", "err-1", "Wrong text content", "assertion failure", None)
        w.start_fix(self.root, "task-alpha-1", "err-1", "Fix text back to ok")
        events = store.read_all()
        types = [e.event_type for e in events]
        self.assertIn("error.recorded", types)
        self.assertIn("fix.started", types)

        state = ve.WorkflowStateReducer.reduce(self.root, events)
        step_map = {s["id"]: s for s in state["steps"]}
        self.assertEqual(step_map["fix_loop"]["status"], "RUNNING")
        self.assertEqual(state["fix_loop"]["attempts"], 1)
        self.assertEqual(state["fix_loop"]["current_approach"], "Fix text back to ok")

        # 5. Fix code, Re-verify (PASS)
        self.flag.write_text("ok", encoding="utf-8")
        self.assertTrue(w.verify(self.root, "task-alpha-1"))
        events = store.read_all()
        self.assertEqual(events[-1].event_type, "verification.passed")
        self.assertEqual(events[-1].status, "COMPLETED")

        # 6. Review (PASS)
        w.review(self.root, "task-alpha-1", "PASS", [], "code_reviewer")
        events = store.read_all()
        self.assertEqual(events[-1].event_type, "review.passed")

        state = ve.WorkflowStateReducer.reduce(self.root, events)
        self.assertEqual(state["review"]["status"], "PASS")

        # 7. Evaluate (resolved)
        w.evaluate(self.root, "task-alpha-1", "err-1", "resolved", "verified ok", "keep ok.txt in sync")
        events = store.read_all()
        self.assertEqual(events[-1].event_type, "fix.completed")

        # 8. QA (PASS), then Complete Task & Complete Plan
        report = self.root / ".verified-development-loop/evidence/task-alpha-1/qa-report.md"
        report.write_text("# QA\n\n**Overall Result:** PASS\n\n## Regression Results\n\nfull suite: 1 pass; output: ok\n\n## Scenario Results\n\nQA-01: read ok.txt; output: ok\n", encoding="utf-8")
        w.qa(self.root, "task-alpha-1", "PASS", report, "qa_tester")
        self.assertEqual(store.read_all()[-1].event_type, "qa.completed")
        qa_state = ve.WorkflowStateReducer.reduce(self.root, store.read_all())
        self.assertEqual({s["id"]: s for s in qa_state["steps"]}["qa"]["status"], "COMPLETED")
        self.assertEqual(qa_state["graph"]["next_node_id"], "complete")
        self.save_human_report("completed")
        w.complete_task(self.root, "task-alpha-1", ["task 1 works reliably"])
        w.complete_plan(self.root, "plan-alpha", ["plan works reliably"])
        events = store.read_all()
        types = [e.event_type for e in events]
        self.assertIn("task.completed", types)
        self.assertIn("plan.completed", types)

        state = ve.WorkflowStateReducer.reduce(self.root, events)
        step_map = {s["id"]: s for s in state["steps"]}
        self.assertEqual(step_map["active"]["status"], "COMPLETED")
        self.assertEqual(step_map["main_agent_report"]["status"], "PENDING")
        self.assertEqual(state["current_step_id"], "main_agent_report")
        self.assertEqual(step_map["human_approval"]["status"], "COMPLETED")
        self.assertFalse(next(node for node in state["graph"]["nodes"] if node["id"] == "report")["is_active"])
        self.assertEqual(state["graph"]["next_node_id"], "report")

        ve.emit_event(self.root, "main_agent.reported", data={"summary": "done"})
        state = ve.WorkflowStateReducer.reduce(self.root, store.read_all())
        self.assertEqual({s["id"]: s for s in state["steps"]}["main_agent_report"]["status"], "COMPLETED")

        ve.emit_event(self.root, "raw_prompt.received", data={"prompt_preview": "Why is the dashboard still running?"})
        state = ve.WorkflowStateReducer.reduce(self.root, store.read_all())
        self.assertEqual(state["current_step_id"], "main_agent_report")

    def test_persists_recurrence_blocks_and_updates_state(self):
        store = ve.EventStore(self.root)
        w.propose(self.root, self.proposal)
        w.approve(self.root, "plan-alpha", "Approved")
        self.flag.write_text("bad", encoding="utf-8")
        w.verify(self.root, "task-alpha-1")
        w.record_error(self.root, "task-alpha-1", "err-persists", "Wrong content", "fail log", None)
        for round_number in range(1, 4):
            w.start_fix(self.root, "task-alpha-1", "err-persists", f"Ineffective fix {round_number}")
            w.verify(self.root, "task-alpha-1")
            if round_number < 3:
                w.evaluate(self.root, "task-alpha-1", "err-persists", "persists", "still failing", None)

        self.save_human_report("blocked")
        reason = w.read(w.path(self.root, "tasks", "active", "task-alpha-1"))["pending_block_reason"]
        w.block_task(self.root, "task-alpha-1", reason)

        events = store.read_all()
        types = [e.event_type for e in events]
        self.assertIn("error.recurred", types)
        self.assertIn("task.blocked", types)

        state = ve.WorkflowStateReducer.reduce(self.root, events)
        self.assertTrue(state["blocked"]["is_blocked"])
        self.assertIn("third fix", state["blocked"]["reason"])
        step_map = {s["id"]: s for s in state["steps"]}
        self.assertEqual(step_map["active"]["status"], "BLOCKED")
        self.assertEqual(step_map["fix_loop"]["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
