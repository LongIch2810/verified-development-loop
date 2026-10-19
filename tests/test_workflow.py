import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/vdl-verified-development-loop/scripts"))
import workflow as w
import vdl_events as ve


class WorkflowGates(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "--allow-empty", "-qm", "base"], cwd=self.root, check=True)
        self.flag = self.root / "ok.txt"
        self.flag.write_text("ok", encoding="utf-8")
        self.proposal = self.root / "proposal.json"
        self.proposal.write_text(json.dumps({
            "plan_id": "p1", "spec": "Implement observed behavior", "acceptance_criteria": ["plan works"],
            "tasks": [{"task_id": "t1", "acceptance_criteria": ["task works"],
                       "qa_plan": "| ID | Criterion | Steps | Expected |\n| --- | --- | --- | --- |\n| QA-01 | task works | Use the public interface | Task works |",
                       "test_code": "### tests/test_task.py\n```python\nfrom pathlib import Path\n\ndef test_task():\n    assert Path('ok.txt').read_text() == 'ok'\n```",
                       "verification": [[sys.executable, "-c", "from pathlib import Path; assert Path('ok.txt').read_text() == 'ok'"]]}]
        }), encoding="utf-8")
        w.propose(self.root, self.proposal)

    def approve(self):
        w.approve(self.root, "p1", "Human approved Spec and Plan")

    def task(self):
        return w.read(w.path(self.root, "tasks", "active", "t1"))

    def qa_result(self, result, task_id="t1"):
        report = self.root / ".verified-development-loop" / "evidence" / task_id / f"qa-report-{result.lower()}.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(f"# QA\n\n**Overall Result:** {result}\n\n## Regression Results\n\nfull suite: 1 passed; output: ok\n\n## Scenario Results\n\nQA-01: command run; output: {result}\n", encoding="utf-8")
        w.qa(self.root, task_id, result, report, "qa_tester")

    def report(self, status, task_id="t1"):
        source = self.root / ".verified-development-loop" / "evidence" / task_id / "human-report.md"
        source.parent.mkdir(parents=True, exist_ok=True)
        body = (f"# Human report\n\n- **Task:** {task_id}\n- **Status:** {status}\n\n"
                "## Overview\n\n- **Plan:** p1\n- **Spec:** p1\n- **Code:** test branch\n"
                "- **Fix rounds:** 0/3\n- **Review rounds:** 1/3\n- **QA rounds:** 1/3\n\n"
                "## Commands and Results\n\n- test: exit 0\n\n"
                "## Review and QA Rounds\n\n- review and QA evidence\n\n"
                "## Remaining Checks\n\n- none\n\n"
                "## Evidence Paths\n\n- .verified-development-loop/evidence\n\n")
        if status != "completed":
            body += ("## Open Errors\n\n- error evidence\n\n## Attempts\n\n- round result\n\n"
                     "## Why Not Converged\n\n- hypothesis\n\n## Human Options\n\n"
                     "- another round, revise Spec, accept errors, cancel\n\n## Human Decision\n\n")
        if status == "completed-accepted":
            body += "## Accepted Errors\n\n- **Error IDs:** e-minor\n- **Accepted by:** Human\n- **Accepted on:** 2026-10-19\n"
        source.write_text(body, encoding="utf-8")
        return w.write_report(self.root, task_id, status, source)

    def complete(self, task_id="t1", acceptance=None):
        self.report("completed", task_id)
        w.complete_task(self.root, task_id, acceptance or ["task works"])

    def finish_block(self, task_id="t1"):
        reason = self.task()["pending_block_reason"]
        self.report("blocked", task_id)
        w.block_task(self.root, task_id, reason)

    def test_no_execution_before_approval(self):
        with self.assertRaises(ValueError):
            w.verify(self.root, "t1")
        self.assertFalse(w.path(self.root, "plans", "active", "p1").exists())
        self.assertTrue((self.root / ".verified-development-loop" / "specs" / "drafts" / "p1.md").exists())
        self.assertFalse(w.path(self.root, "specs", "active", "p1").exists())
        self.assertIn("## Spec", (self.root / ".verified-development-loop" / "specs" / "drafts" / "p1.md").read_text(encoding="utf-8"))
        self.assertIn("## Tasks", w.path(self.root, "plans", "drafts", "p1").read_text(encoding="utf-8"))

    def test_snapshot_in_repository_without_first_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            source = root / "app.py"
            source.write_text("first", encoding="utf-8")
            first = w.snapshot(root)
            source.write_text("second", encoding="utf-8")
            self.assertNotEqual(first, w.snapshot(root))

    def test_snapshot_ignores_bundled_skill_source(self):
        source = self.root / "skills/vdl-verified-development-loop/SKILL.md"
        source.parent.mkdir(parents=True)
        source.write_text("first", encoding="utf-8")
        first = w.snapshot(self.root)
        source.write_text("second", encoding="utf-8")
        self.assertEqual(first, w.snapshot(self.root))

    def test_approval_rejects_draft_spec_plan_disagreement(self):
        spec_path = self.root / ".verified-development-loop" / "specs" / "drafts" / "p1.md"
        spec = w.read(spec_path)
        spec["spec"] = "Different scope"
        w.write(spec_path, spec)
        with self.assertRaisesRegex(ValueError, "disagree"):
            self.approve()
        self.assertFalse(w.path(self.root, "plans", "active", "p1").exists())

    def test_approval_does_not_overwrite_task_from_another_plan(self):
        proposal = json.loads(self.proposal.read_text(encoding="utf-8"))
        proposal["plan_id"] = "p2"
        self.proposal.write_text(json.dumps(proposal), encoding="utf-8")
        w.propose(self.root, self.proposal)
        self.approve()
        with self.assertRaisesRegex(ValueError, "task ID already exists"):
            w.approve(self.root, "p2", "Approved second plan")
        self.assertEqual(self.task()["plan_id"], "p1")
        self.assertFalse(w.path(self.root, "plans", "active", "p2").exists())

    def test_verification_fail_blocks_completion_and_records_log(self):
        self.approve()
        self.flag.write_text("bad", encoding="utf-8")
        self.assertFalse(w.verify(self.root, "t1"))
        with self.assertRaises(ValueError):
            w.complete_task(self.root, "t1", ["task works"])
        evidence_path = self.root / self.task()["verification_evidence"]
        self.assertEqual(evidence_path.suffix, ".md")
        self.assertIn("## Record", evidence_path.read_text(encoding="utf-8"))
        log = w.read(evidence_path)
        self.assertEqual(log["commands"][0]["exit_code"], 1)
        self.assertEqual(log["status"], "FAIL")

    def test_review_fail_blocks_completion_and_reviewer_cannot_create_task(self):
        self.approve()
        self.assertTrue(w.verify(self.root, "t1"))
        w.review(self.root, "t1", "FAIL", ["ok.txt:1: wrong content"], "code_reviewer")
        with self.assertRaises(ValueError):
            w.complete_task(self.root, "t1", ["task works"])
        self.assertEqual(len(list((self.root / ".verified-development-loop" / "tasks" / "active").glob("*.md"))), 1)

    def test_successful_fix_and_completion(self):
        self.approve()
        approved_spec = w.read(w.path(self.root, "specs", "active", "p1"))
        self.assertEqual(approved_spec["spec"], "Implement observed behavior")
        self.assertEqual(approved_spec["human_approval"]["record"], "Human approved Spec and Plan")
        self.assertEqual(w.read(w.path(self.root, "plans", "active", "p1"))["spec_file"], ".verified-development-loop/specs/active/p1.md")
        self.assertFalse((self.root / ".verified-development-loop" / "specs" / "drafts" / "p1.md").exists())
        self.flag.write_text("bad", encoding="utf-8")
        self.assertFalse(w.verify(self.root, "t1"))
        w.record_error(self.root, "t1", "e1", "wrong output", "verification log", None)
        w.start_fix(self.root, "t1", "e1", "correct output")
        self.flag.write_text("ok", encoding="utf-8")
        self.assertTrue(w.verify(self.root, "t1"))
        w.review(self.root, "t1", "PASS", [], "code_reviewer")
        w.evaluate(self.root, "t1", "e1", "resolved", "passing verification and review", "assert output")
        self.qa_result("PASS")
        self.complete()
        w.complete_plan(self.root, "p1", ["plan works"])
        self.assertTrue(w.path(self.root, "tasks", "completed", "t1").exists())
        self.assertTrue(w.path(self.root, "plans", "completed", "p1").exists())
        self.assertFalse(w.path(self.root, "specs", "active", "p1").exists())
        self.assertTrue(w.path(self.root, "specs", "completed", "p1").exists())
        self.assertEqual(w.read(w.path(self.root, "plans", "completed", "p1"))["spec_file"], ".verified-development-loop/specs/completed/p1.md")
        error = w.read(self.root / ".verified-development-loop" / "errors" / "e1.md")
        self.assertEqual((error["fix_attempts"], error["recurrences"], error["status"]), (1, 0, "RESOLVED"))
        self.assertEqual(len(error["verification_logs"]), 2)
        self.assertEqual(len(error["review_findings"]), 1)

    def test_same_error_can_use_three_fix_rounds_before_block(self):
        self.approve()
        self.flag.write_text("bad", encoding="utf-8")
        self.assertFalse(w.verify(self.root, "t1"))
        w.record_error(self.root, "t1", "e1", "wrong output", "verification log", None)
        for round_number in range(1, 4):
            w.start_fix(self.root, "t1", "e1", f"attempt {round_number}")
            self.assertFalse(w.verify(self.root, "t1"))
            if round_number < 3:
                w.evaluate(self.root, "t1", "e1", "persists", "same assertion failure", None)
                self.assertEqual(self.task()["status"], "active")
        self.finish_block()
        self.assertEqual(self.task()["status"], "blocked")
        self.assertEqual(self.task()["fix_round"], 3)
        self.assertEqual(w.read(self.root / ".verified-development-loop" / "errors" / "e1.md")["recurrences"], 2)
        self.assertEqual(w.read(w.path(self.root, "plans", "active", "p1"))["execution_state"], "waiting_human")
        self.assertTrue(w.path(self.root, "specs", "active", "p1").exists())
        self.assertFalse(w.path(self.root, "specs", "completed", "p1").exists())
        with self.assertRaises(ValueError):
            w.start_fix(self.root, "t1", "e1", "retry")

    def test_two_review_findings_share_one_fix_round(self):
        self.approve()
        self.assertTrue(w.verify(self.root, "t1"))
        w.review(self.root, "t1", "FAIL", ["finding one", "finding two"], "code_reviewer")
        w.record_error(self.root, "t1", "e1", "first issue", "review", None)
        w.record_error(self.root, "t1", "e2", "second issue", "review", None)
        w.start_fix(self.root, "t1", "e1", "fix first")
        w.join_fix(self.root, "t1", "e2", "fix second")
        self.assertEqual(self.task()["fix_round"], 1)
        with self.assertRaises(ValueError):
            w.join_fix(self.root, "t1", "e2", "repeat")
        self.assertTrue(w.verify(self.root, "t1"))
        w.review(self.root, "t1", "PASS", [], "code_reviewer")
        w.evaluate(self.root, "t1", "e1", "resolved", "review confirms first fixed", None)
        w.evaluate(self.root, "t1", "e2", "resolved", "review confirms second fixed", None)
        self.qa_result("PASS")
        self.complete()
        for error_id in ("e1", "e2"):
            error = w.read(self.root / ".verified-development-loop" / "errors" / f"{error_id}.md")
            self.assertEqual((error["fix_attempts"], error["recurrences"], error["status"]), (1, 0, "RESOLVED"))

    def test_new_review_error_does_not_fake_a_pass_or_reset_fix_round(self):
        self.approve()
        self.assertTrue(w.verify(self.root, "t1"))
        w.review(self.root, "t1", "FAIL", ["e1 initial finding"], "code_reviewer")
        w.record_error(self.root, "t1", "e1", "first issue", "review", None)
        w.start_fix(self.root, "t1", "e1", "fix first")
        self.assertTrue(w.verify(self.root, "t1"))
        w.review(self.root, "t1", "FAIL", ["e2 new distinct finding"], "code_reviewer")
        with self.assertRaises(ValueError):
            w.evaluate(self.root, "t1", "e1", "resolved", "review says fixed", None)
        w.record_error(self.root, "t1", "e2", "second issue", "new review", None)
        w.evaluate(self.root, "t1", "e1", "resolved", "review explicitly confirms first fixed", None)
        self.assertEqual(w.read(w.path(self.root, "tasks", "active", "t1"))["review_evidence"] is not None, True)
        with self.assertRaises(ValueError):
            w.complete_task(self.root, "t1", ["task works"])
        w.start_fix(self.root, "t1", "e2", "fix second")
        self.assertEqual(self.task()["fix_round"], 2)

    def test_third_failed_fix_blocks_without_reset(self):
        self.approve()
        self.flag.write_text("bad", encoding="utf-8")
        self.assertFalse(w.verify(self.root, "t1"))
        for i in range(3):
            error_id = f"e{i}"
            w.record_error(self.root, "t1", error_id, f"distinct issue {i}", "failure log", None)
            w.start_fix(self.root, "t1", error_id, "attempt")
            if i < 2:
                self.flag.write_text("ok", encoding="utf-8")
                self.assertTrue(w.verify(self.root, "t1"))
                w.review(self.root, "t1", "PASS", [], "code_reviewer")
                w.evaluate(self.root, "t1", error_id, "resolved", "passing checks", None)
                self.flag.write_text(f"bad-{i}", encoding="utf-8")
                self.assertFalse(w.verify(self.root, "t1"))
            else:
                self.assertFalse(w.verify(self.root, "t1"))
        self.finish_block()
        self.assertEqual(self.task()["status"], "blocked")
        self.assertEqual(self.task()["fix_round"], 3)
        self.assertEqual(w.read(w.path(self.root, "plans", "active", "p1"))["execution_state"], "waiting_human")
        with self.assertRaises(ValueError):
            w.complete_plan(self.root, "p1", ["plan works"])

    def test_old_evidence_cannot_complete_new_code(self):
        self.approve()
        self.assertTrue(w.verify(self.root, "t1"))
        w.review(self.root, "t1", "PASS", [], "code_reviewer")
        self.flag.write_text("changed", encoding="utf-8")
        with self.assertRaises(ValueError):
            w.complete_task(self.root, "t1", ["task works"])

    def test_proposal_rejects_cyclic_task_dependencies(self):
        draft = json.loads(self.proposal.read_text(encoding="utf-8"))
        draft["tasks"][0]["depends_on"] = ["t2"]
        draft["tasks"].append({"task_id": "t2", "acceptance_criteria": ["second works"],
                               "depends_on": ["t1"], "qa_plan": "| QA-02 | second works | Run task | It works |",
                               "test_code": "### tests/test_second.py\n```python\ndef test_second():\n    assert True\n```",
                               "verification": [[sys.executable, "-c", "assert True"]]})
        self.proposal.write_text(json.dumps(draft), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "cyclic task dependency"):
            w.propose(self.root, self.proposal)

    def test_plan_waits_for_all_linked_tasks(self):
        draft = w.read(w.path(self.root, "plans", "drafts", "p1"))
        draft["tasks"].append({"task_id": "t2", "acceptance_criteria": ["second works"], "depends_on": ["t1"], "qa_plan": "QA-01: second works", "verification": [[sys.executable, "-c", "assert True"]]})
        w.write(w.path(self.root, "plans", "drafts", "p1"), draft)
        self.approve()
        with self.assertRaises(ValueError):
            w.verify(self.root, "t2")
        self.assertTrue(w.verify(self.root, "t1"))
        w.review(self.root, "t1", "PASS", [], "code_reviewer")
        self.qa_result("PASS")
        self.complete()
        with self.assertRaises(ValueError):
            w.complete_plan(self.root, "p1", ["plan works"])
        self.assertTrue(w.verify(self.root, "t2"))
        w.review(self.root, "t2", "PASS", [], "code_reviewer")
        self.qa_result("PASS", "t2")
        self.complete("t2", ["second works"])
        w.complete_plan(self.root, "p1", ["plan works"])
        self.assertTrue(w.path(self.root, "plans", "completed", "p1").exists())

    def test_plan_cannot_complete_without_active_spec(self):
        self.approve()
        self.assertTrue(w.verify(self.root, "t1"))
        w.review(self.root, "t1", "PASS", [], "code_reviewer")
        self.qa_result("PASS")
        self.complete()
        w.path(self.root, "specs", "active", "p1").unlink()
        with self.assertRaisesRegex(ValueError, "active Spec"):
            w.complete_plan(self.root, "p1", ["plan works"])

    def test_plan_cannot_complete_after_report_becomes_empty(self):
        self.approve()
        self.assertTrue(w.verify(self.root, "t1"))
        w.review(self.root, "t1", "PASS", [], "code_reviewer")
        self.qa_result("PASS")
        self.complete()
        task = w.read(w.path(self.root, "tasks", "completed", "t1"))
        (self.root / task["latest_report"]).write_text("", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "linked report"):
            w.complete_plan(self.root, "p1", ["plan works"])

    def test_unavailable_command_never_passes(self):
        self.approve()
        task = self.task()
        task["verification"] = [["definitely-missing-workflow-command"]]
        w.write(w.path(self.root, "tasks", "active", "t1"), task)
        self.assertFalse(w.verify(self.root, "t1"))
        log = w.read(self.root / self.task()["verification_evidence"])
        self.assertEqual(log["status"], "UNVERIFIED")
        self.assertIsNone(log["commands"][0]["exit_code"])
        with self.assertRaisesRegex(ValueError, "report"):
            w.block_task(self.root, "t1", "required tool unavailable")
        self.finish_block()
        self.assertEqual(self.task()["status"], "blocked")

    def test_qa_requires_review_and_blocks_completion_without_pass(self):
        self.approve()
        self.assertTrue(w.verify(self.root, "t1"))
        with self.assertRaisesRegex(ValueError, "review"):
            self.qa_result("PASS")
        w.review(self.root, "t1", "PASS", [], "code_reviewer")
        with self.assertRaisesRegex(ValueError, "QA evidence"):
            w.complete_task(self.root, "t1", ["task works"])
        self.qa_result("PASS")
        self.assertEqual(w.read(self.root / self.task()["qa_evidence"])["status"], "PASS")
        self.complete()
        acceptance = w.read(self.root / w.read(w.path(self.root, "tasks", "completed", "t1"))["acceptance_evidence"])
        self.assertTrue(acceptance["qa"])

    def test_qa_report_must_cover_approved_scenarios(self):
        self.approve()
        self.assertTrue(w.verify(self.root, "t1"))
        w.review(self.root, "t1", "PASS", [], "code_reviewer")
        report = self.root / ".verified-development-loop/evidence/t1/qa-report.md"
        report.write_text("# QA\n\n**Overall Result:** PASS\n\n## Regression Results\n\noutput: ok\n\n## Scenario Results\n\nNo scenario was run.\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "every approved scenario"):
            w.qa(self.root, "t1", "PASS", report, "qa_tester")

    def test_qa_code_error_retests_all_scenarios_and_blocks_after_third_fix(self):
        self.approve()
        self.assertTrue(w.verify(self.root, "t1"))
        w.review(self.root, "t1", "PASS", [], "code_reviewer")
        self.qa_result("FAIL")
        w.record_error(self.root, "t1", "e-qa", "public flow fails", "QA-01 output", None, "code")
        for round_number in range(1, 4):
            w.start_fix(self.root, "t1", "e-qa", f"repair {round_number}")
            self.assertTrue(w.verify(self.root, "t1"))
            w.review(self.root, "t1", "PASS", [], "code_reviewer")
            self.qa_result("FAIL")
            w.evaluate(self.root, "t1", "e-qa", "persists", "QA-01 still fails", None)
            if round_number == 3:
                self.finish_block()
            self.assertEqual(self.task()["status"], "active" if round_number < 3 else "blocked")
        self.assertEqual(w.read(self.root / ".verified-development-loop/errors/e-qa.md")["fix_attempts"], 3)

    def test_qa_environment_retry_does_not_count_as_fix(self):
        self.approve()
        self.assertTrue(w.verify(self.root, "t1"))
        w.review(self.root, "t1", "PASS", [], "code_reviewer")
        self.qa_result("FAIL")
        w.record_error(self.root, "t1", "e-env", "server unavailable", "QA report", None, "environment")
        self.qa_result("FAIL")
        w.evaluate(self.root, "t1", "e-env", "persists", "server is still unavailable", None)
        self.qa_result("PASS")
        w.evaluate(self.root, "t1", "e-env", "resolved", "server started; all QA scenarios passed", None)
        self.assertEqual(self.task()["fix_round"], 0)
        self.assertEqual(w.read(self.root / ".verified-development-loop/errors/e-env.md")["recurrences"], 1)
        self.complete()

    def test_failed_qa_run_must_be_recorded_even_if_retry_passes(self):
        self.approve()
        self.assertTrue(w.verify(self.root, "t1"))
        w.review(self.root, "t1", "PASS", [], "code_reviewer")
        self.qa_result("FAIL")
        self.qa_result("PASS")
        with self.assertRaisesRegex(ValueError, "failed QA run"):
            w.complete_task(self.root, "t1", ["task works"])

    def test_same_review_error_can_be_repaired_three_times(self):
        self.approve()
        self.assertTrue(w.verify(self.root, "t1"))
        w.review(self.root, "t1", "FAIL", ["e1 same finding"], "code_reviewer")
        w.record_error(self.root, "t1", "e1", "same review issue", "review evidence", None)
        for round_number in range(1, 4):
            w.start_fix(self.root, "t1", "e1", f"repair {round_number}")
            self.assertTrue(w.verify(self.root, "t1"))
            w.review(self.root, "t1", "FAIL", ["e1 same finding"], "code_reviewer")
            if round_number < 3:
                w.evaluate(self.root, "t1", "e1", "persists", "same review finding", None)
                self.assertEqual(self.task()["status"], "active")
        self.finish_block()
        self.assertEqual(self.task()["status"], "blocked")
        self.assertEqual(self.task()["fix_round"], 3)

    def test_qa_spec_issue_blocks_for_human(self):
        self.approve()
        self.assertTrue(w.verify(self.root, "t1"))
        w.review(self.root, "t1", "PASS", [], "code_reviewer")
        self.qa_result("FAIL")
        w.record_error(self.root, "t1", "e-spec", "expected behavior conflicts", "QA report", None, "spec")
        self.finish_block()
        self.assertEqual(self.task()["status"], "blocked")
        self.assertEqual(w.read(w.path(self.root, "plans", "active", "p1"))["execution_state"], "waiting_human")

    def test_all_findings_from_one_failed_qa_can_be_recorded_before_block(self):
        self.approve()
        self.assertTrue(w.verify(self.root, "t1"))
        w.review(self.root, "t1", "PASS", [], "code_reviewer")
        self.qa_result("FAIL")
        w.record_error(self.root, "t1", "e-spec-1", "first spec gap", "QA-01 evidence", None, "spec")
        w.record_error(self.root, "t1", "e-spec-2", "second spec gap", "QA-01 evidence", None, "spec")
        self.finish_block()
        self.assertTrue((self.root / ".verified-development-loop/errors/e-spec-1.md").exists())
        self.assertTrue((self.root / ".verified-development-loop/errors/e-spec-2.md").exists())

    def test_completed_requires_saved_report(self):
        self.approve()
        self.assertTrue(w.verify(self.root, "t1"))
        w.review(self.root, "t1", "PASS", [], "code_reviewer")
        self.qa_result("PASS")
        with self.assertRaisesRegex(ValueError, "completed report"):
            w.complete_task(self.root, "t1", ["task works"])
        self.assertEqual(self.task()["status"], "active")
        ref = self.report("completed")
        (self.root / ref).write_text("", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "empty"):
            w.complete_task(self.root, "t1", ["task works"])

    def test_blocked_requires_saved_report(self):
        self.approve()
        with self.assertRaisesRegex(ValueError, "blocked report"):
            w.block_task(self.root, "t1", "human decision required")
        self.assertEqual(self.task()["status"], "active")
        self.assertEqual(self.task()["pending_block_reason"], "human decision required")
        ref = self.report("blocked")
        w.block_task(self.root, "t1", "human decision required")
        self.assertEqual(self.task()["latest_report"], ref)
        self.assertTrue((self.root / ref).is_file())

    def test_blocked_report_contains_continuation_context(self):
        self.approve()
        with self.assertRaisesRegex(ValueError, "report"):
            w.block_task(self.root, "t1", "QA-01 still fails")
        source = self.root / ".verified-development-loop/evidence/t1/human-report.md"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            "# Human report\n\n- **Task:** t1\n- **Status:** blocked\n\n"
            "## Overview\n\n- **Plan:** p1 (.verified-development-loop/plans/active/p1.md)\n"
            "- **Spec:** p1 (.verified-development-loop/specs/active/p1.md)\n"
            "- **Code:** base commit on test branch\n- **Fix rounds:** 3/3\n"
            "- **Review rounds:** 3/3\n- **QA rounds:** 3/3\n- **Outcome:** QA-01 still fails\n\n"
            "## Commands and Results\n\n| Command | Result | Evidence |\n| --- | --- | --- |\n"
            "| python -m unittest | exit 1; QA-01 fails | .verified-development-loop/evidence/t1/qa.md |\n\n"
            "## Review and QA Rounds\n\n| Round | Review | QA | Evidence |\n| --- | --- | --- | --- |\n"
            "| 1/3 | PASS | FAIL QA-01 | .verified-development-loop/evidence/t1/qa.md |\n"
            "| 2/3 | PASS | FAIL QA-01 | .verified-development-loop/evidence/t1/qa.md |\n"
            "| 3/3 | PASS | FAIL QA-01 | .verified-development-loop/evidence/t1/qa.md |\n\n"
            "## Remaining Checks\n\n- Production data not checked; use test fixtures only.\n\n"
            "## Evidence Paths\n\n- .verified-development-loop/evidence/t1/qa.md\n\n"
            "## Open Errors\n\n| ID | Severity | Classification | File:line or reproduction | Evidence path |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| e-qa | serious | code | Run QA-01 with test fixture | .verified-development-loop/evidence/t1/qa.md |\n\n"
            "## Attempts\n\n| Round | Change | Result |\n| --- | --- | --- |\n"
            "| 1/3 | Repair branch | QA-01 FAIL |\n| 2/3 | Repair validation | QA-01 FAIL |\n"
            "| 3/3 | Repair state | QA-01 FAIL |\n\n"
            "## Why Not Converged\n\n- Hypothesis: the test fixture misses a dependent state; unverified.\n\n"
            "## Human Options\n\n- Another round with a different approach: requires new authorization.\n"
            "- Revise Spec or Plan: requires approval and new Plan ID.\n"
            "- Accept remaining errors: leaves QA-01 failing; serious only.\n"
            "- Cancel: stops the work.\n\n## Human Decision\n\n",
            encoding="utf-8",
        )
        ref = w.write_report(self.root, "t1", "blocked", source)
        w.block_task(self.root, "t1", "QA-01 still fails")
        saved = (self.root / ref).read_text(encoding="utf-8")
        for required in ("e-qa", "serious", "QA-01", "1/3", "2/3", "3/3", "Human Options", "Human Decision"):
            self.assertIn(required, saved)
        self.assertEqual(self.task()["latest_report"], ref)

    def test_new_report_updates_task_without_overwriting_previous(self):
        self.approve()
        first = self.report("completed")
        first_text = (self.root / first).read_text(encoding="utf-8")
        second = self.report("completed")
        self.assertNotEqual(first, second)
        self.assertEqual((self.root / first).read_text(encoding="utf-8"), first_text)
        self.assertEqual(self.task()["latest_report"], second)
        self.assertIn(second, w.path(self.root, "tasks", "active", "t1").read_text(encoding="utf-8"))
        self.assertEqual([event.event_type for event in ve.EventStore(self.root).read_all()].count("report.recorded"), 2)

    def test_report_write_failure_keeps_task_active(self):
        self.approve()
        with self.assertRaisesRegex(ValueError, "report input"):
            w.write_report(self.root, "t1", "completed", self.root / "missing-report.md")
        self.assertEqual(self.task()["status"], "active")
        self.assertIsNone(self.task().get("latest_report"))

    def test_accepted_minor_error_requires_human_and_report(self):
        self.approve()
        self.assertTrue(w.verify(self.root, "t1"))
        w.review(self.root, "t1", "PASS", [], "code_reviewer")
        self.qa_result("FAIL")
        w.record_error(self.root, "t1", "e-minor", "minor display issue", "QA-01 evidence", None, "code", "minor")
        with self.assertRaisesRegex(ValueError, "completed-accepted report"):
            w.complete_task_accepted(self.root, "t1", ["task works"], ["e-minor"], "Human", "2026-10-19")
        ref = self.report("completed-accepted")
        w.complete_task_accepted(self.root, "t1", ["task works"], ["e-minor"], "Human", "2026-10-19")
        w.complete_plan(self.root, "p1", ["plan works"], accepted=True)
        task = w.read(w.path(self.root, "tasks", "completed", "t1"))
        self.assertEqual(task["latest_report"], ref)
        self.assertEqual(task["completion_kind"], "accepted_errors")
        self.assertEqual(w.read(self.root / ".verified-development-loop/errors/e-minor.md")["status"], "OPEN")

    def test_human_can_accept_minor_error_after_task_was_blocked(self):
        self.approve()
        self.assertTrue(w.verify(self.root, "t1"))
        w.review(self.root, "t1", "PASS", [], "code_reviewer")
        self.qa_result("FAIL")
        w.record_error(self.root, "t1", "e-minor", "display issue", "QA-01 evidence", None, "code")
        with self.assertRaisesRegex(ValueError, "blocked report"):
            w.block_task(self.root, "t1", "await human decision")
        self.report("blocked")
        w.block_task(self.root, "t1", "await human decision")
        subprocess.run([sys.executable, str(Path(w.__file__)), "--root", str(self.root),
                        "set-error-severity", "--task-id", "t1", "--error-id", "e-minor",
                        "--severity", "minor"], check=True)
        self.report("completed-accepted")
        w.complete_task_accepted(self.root, "t1", ["task works"], ["e-minor"], "Human", "2026-10-19")
        w.complete_plan(self.root, "p1", ["plan works"], accepted=True)
        self.assertEqual(w.read(w.path(self.root, "tasks", "completed", "t1"))["completion_kind"], "accepted_errors")

    def test_blocker_cannot_be_accepted(self):
        self.approve()
        self.assertTrue(w.verify(self.root, "t1"))
        w.review(self.root, "t1", "PASS", [], "code_reviewer")
        self.qa_result("FAIL")
        w.record_error(self.root, "t1", "e-minor", "blocking failure", "QA-01 evidence", None, "code", "blocker")
        self.report("completed-accepted")
        with self.assertRaisesRegex(ValueError, "Blocker"):
            w.complete_task_accepted(self.root, "t1", ["task works"], ["e-minor"], "Human", "2026-10-19")


if __name__ == "__main__":
    unittest.main()
