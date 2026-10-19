import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/vdl-verified-development-loop/scripts"))
import workflow as w


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
        w.complete_task(self.root, "t1", ["task works"])
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
        w.complete_task(self.root, "t1", ["task works"])
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
        w.complete_task(self.root, "t1", ["task works"])
        with self.assertRaises(ValueError):
            w.complete_plan(self.root, "p1", ["plan works"])
        self.assertTrue(w.verify(self.root, "t2"))
        w.review(self.root, "t2", "PASS", [], "code_reviewer")
        self.qa_result("PASS", "t2")
        w.complete_task(self.root, "t2", ["second works"])
        w.complete_plan(self.root, "p1", ["plan works"])
        self.assertTrue(w.path(self.root, "plans", "completed", "p1").exists())

    def test_plan_cannot_complete_without_active_spec(self):
        self.approve()
        self.assertTrue(w.verify(self.root, "t1"))
        w.review(self.root, "t1", "PASS", [], "code_reviewer")
        self.qa_result("PASS")
        w.complete_task(self.root, "t1", ["task works"])
        w.path(self.root, "specs", "active", "p1").unlink()
        with self.assertRaisesRegex(ValueError, "active Spec"):
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
        w.block_task(self.root, "t1", "required tool unavailable")
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
        w.complete_task(self.root, "t1", ["task works"])
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
        w.complete_task(self.root, "t1", ["task works"])

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
        self.assertEqual(self.task()["status"], "blocked")
        self.assertEqual(self.task()["fix_round"], 3)

    def test_qa_spec_issue_blocks_for_human(self):
        self.approve()
        self.assertTrue(w.verify(self.root, "t1"))
        w.review(self.root, "t1", "PASS", [], "code_reviewer")
        self.qa_result("FAIL")
        w.record_error(self.root, "t1", "e-spec", "expected behavior conflicts", "QA report", None, "spec")
        self.assertEqual(self.task()["status"], "blocked")
        self.assertEqual(w.read(w.path(self.root, "plans", "active", "p1"))["execution_state"], "waiting_human")


if __name__ == "__main__":
    unittest.main()
