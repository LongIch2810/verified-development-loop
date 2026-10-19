"""Bug-mode diagnosis and state-gate regression checks."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import workflow as w
import vdl_events as ve


class BugModeGates(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
                        "commit", "--allow-empty", "-qm", "base"], cwd=self.root, check=True)
        self.report = self.root / ".verified-development-loop/evidence/bug-plan/investigator.md"
        self.report.parent.mkdir(parents=True)
        self.report.write_text(
            "# Diagnosis\n\n- **Result:** REPRODUCED\n- **Root cause:** app.py:4 wrong branch\n"
            "- **Evidence:** python app.py exited 1; output: wrong branch; app.py:4\n"
            "- **Confidence:** high — direct reproduction\n- **Classification:** code\n",
            encoding="utf-8",
        )
        self.proposal = self.root / ".verified-development-loop/evidence/bug-plan/proposal.json"
        self.data = {
            "plan_id": "bug-plan", "mode": "bug", "spec": "# Bug Spec\nBAC-01: correct output",
            "acceptance_criteria": ["correct output"], "error_id": "bug-1",
            "fix_approach": "correct the branch at app.py:4",
            "tasks": [{"task_id": "bug-task", "acceptance_criteria": ["correct output"],
                       "qa_plan": "| ID | Criterion | Steps | Expected |\n| --- | --- | --- | --- |\n| QA-01 | correct output | Run app | correct output |",
                       "test_code": "### tests/test_app.py\n```python\ndef test_bug():\n    assert True\n```",
                       "verification": [[sys.executable, "-c", "assert True"]]}],
        }

    def propose(self):
        self.proposal.write_text(json.dumps(self.data), encoding="utf-8")
        w.propose(self.root, self.proposal)

    def diagnose(self, result="REPRODUCED", classification="code", confidence="high"):
        text = self.report.read_text(encoding="utf-8")
        text = text.replace("**Result:** REPRODUCED", f"**Result:** {result}")
        text = text.replace("**Classification:** code", f"**Classification:** {classification}")
        text = text.replace("**Confidence:** high", f"**Confidence:** {confidence}")
        self.report.write_text(text, encoding="utf-8")
        return w.record_diagnosis(self.root, "bug-plan", self.report, result, classification, confidence)

    def test_bug_approval_and_tdd_require_diagnosis(self):
        self.propose()
        with self.assertRaisesRegex(ValueError, "diagnosis"):
            w.approve(self.root, "bug-plan", "approved")
        self.assertFalse(w.path(self.root, "plans", "active", "bug-plan").exists())
        self.data["diagnosis_evidence"] = self.diagnose()
        draft = w.read(w.path(self.root, "plans", "drafts", "bug-plan"))
        draft["diagnosis_evidence"] = self.data["diagnosis_evidence"]
        w.write(w.path(self.root, "plans", "drafts", "bug-plan"), draft)
        w.approve(self.root, "bug-plan", "approved")
        task = w.read(w.path(self.root, "tasks", "active", "bug-task"))
        task["diagnosis_evidence"] = None
        w.write(w.path(self.root, "tasks", "active", "bug-task"), task)
        with self.assertRaisesRegex(ValueError, "diagnosis"):
            w.verify(self.root, "bug-task")

    def test_two_low_confidence_reports_cannot_activate_bug(self):
        refs = [self.diagnose(confidence="low") for _ in range(2)]
        self.assertEqual(len(set(refs)), 2)
        with self.assertRaisesRegex(ValueError, "two diagnosis"):
            self.diagnose()
        self.data["diagnosis_evidence"] = refs[-1]
        self.propose()
        with self.assertRaisesRegex(ValueError, "diagnosis"):
            w.approve(self.root, "bug-plan", "approved")

    def test_code_change_after_diagnosis_blocks_approval(self):
        self.data["diagnosis_evidence"] = self.diagnose()
        self.propose()
        (self.root / "app.py").write_text("changed before approval", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed since diagnosis"):
            w.approve(self.root, "bug-plan", "approved")

    def test_not_reproduced_cannot_activate_bug(self):
        self.data["diagnosis_evidence"] = self.diagnose(result="NOT_REPRODUCED")
        self.propose()
        with self.assertRaisesRegex(ValueError, "diagnosis"):
            w.approve(self.root, "bug-plan", "approved")

    def test_tdd_checkpoint_cannot_start_without_bug_diagnosis(self):
        self.propose()
        saved_argv = sys.argv
        sys.argv = ["workflow.py", "--root", str(self.root), "emit", "--event", "tdd.started",
                    "--plan-id", "bug-plan", "--task-id", "bug-task"]
        try:
            self.assertEqual(w.main(), 2)
        finally:
            sys.argv = saved_argv

    def test_bug_completion_still_requires_review_and_qa(self):
        self.data["diagnosis_evidence"] = self.diagnose()
        self.propose()
        w.approve(self.root, "bug-plan", "approved")
        self.assertTrue(w.verify(self.root, "bug-task"))
        with self.assertRaisesRegex(ValueError, "review"):
            w.complete_task(self.root, "bug-task", ["correct output"])
        w.review(self.root, "bug-task", "PASS", [], "code_reviewer")
        with self.assertRaisesRegex(ValueError, "QA"):
            w.complete_task(self.root, "bug-task", ["correct output"])

    def test_completed_bug_keeps_root_cause_and_fix_in_existing_error_record(self):
        self.data["diagnosis_evidence"] = self.diagnose()
        self.propose()
        w.approve(self.root, "bug-plan", "approved")
        self.assertTrue(w.verify(self.root, "bug-task"))
        w.review(self.root, "bug-task", "PASS", [], "code_reviewer")
        qa_report = self.root / ".verified-development-loop/evidence/bug-task/qa-report.md"
        qa_report.parent.mkdir(parents=True, exist_ok=True)
        qa_report.write_text("# QA\n\n**Overall Result:** PASS\n\n## Regression Results\n\nfull suite PASS\n\n## Scenario Results\n\nQA-01 PASS\n", encoding="utf-8")
        w.qa(self.root, "bug-task", "PASS", qa_report, "qa_tester")
        human_report = qa_report.parent / "human-report.md"
        human_report.write_text(
            "# Human report\n\n- **Task:** bug-task\n- **Status:** completed\n\n"
            "## Overview\n\n- **Plan:** bug-plan\n- **Spec:** bug-plan\n- **Code:** test branch\n"
            "- **Fix rounds:** 0/3\n- **Review rounds:** 1/3\n- **QA rounds:** 1/3\n\n"
            "## Commands and Results\n\n- test: PASS\n\n## Review and QA Rounds\n\n- PASS\n\n"
            "## Remaining Checks\n\n- none\n\n## Evidence Paths\n\n- QA report\n",
            encoding="utf-8",
        )
        w.write_report(self.root, "bug-task", "completed", human_report)
        w.complete_task(self.root, "bug-task", ["correct output"])
        w.complete_plan(self.root, "bug-plan", ["correct output"])
        error = w.read(self.root / ".verified-development-loop/errors/bug-1.md")
        self.assertEqual(error["status"], "RESOLVED")
        self.assertIn("app.py:4", error["root_cause"])
        self.assertIn("correct the branch", error["attempts"][0]["approach"])

    def test_dashboard_diagnosis_node_is_bug_only(self):
        feature = ve.WorkflowStateReducer.reduce(self.root, [])
        self.assertNotIn("diagnosis", {n["id"] for n in feature["graph"]["nodes"]})
        event = ve.emit_event(self.root, "diagnosis.started", status="RUNNING", plan_id="bug-plan", notify=False)
        bug = ve.WorkflowStateReducer.reduce(self.root, [event])
        self.assertEqual(bug["graph"]["active_node_id"], "diagnosis")
        self.assertIn("diagnosis", {n["id"] for n in bug["graph"]["nodes"]})
        self.assertNotIn("interview", {n["id"] for n in bug["graph"]["nodes"]})


if __name__ == "__main__":
    unittest.main()
