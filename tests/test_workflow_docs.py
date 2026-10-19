"""Check approved test source stays readable in Markdown records."""

import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/vdl-verified-development-loop/scripts"))
from workflow_docs import read, write
from workflow import approve, propose


class WorkflowDocTests(unittest.TestCase):
    def test_proposal_requires_test_code(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            proposal = root / "proposal.json"
            write(proposal, {"plan_id": "p1", "spec": "Total numbers", "acceptance_criteria": ["2 + 3 = 5"],
                             "tasks": [{"task_id": "t1", "acceptance_criteria": ["2 + 3 = 5"],
                                        "verification": [["pytest", "tests/test_total.py"]],
                                        "qa_plan": "| QA-01 | 2 + 3 = 5 | add inputs | 5 |"}]})
            with self.assertRaisesRegex(ValueError, "test_code must be nonempty"):
                propose(root, proposal)

    def test_proposal_requires_qa_scenario_for_each_criterion(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            proposal = root / "proposal.json"
            write(proposal, {"plan_id": "p1", "spec": "Total numbers", "acceptance_criteria": ["sum", "difference"],
                             "tasks": [{"task_id": "t1", "acceptance_criteria": ["sum", "difference"],
                                        "verification": [["pytest", "tests/test_total.py"]],
                                        "qa_plan": "| QA-01 | sum | add inputs | result |",
                                        "test_code": "### tests/test_total.py\n```python\nassert True\n```"}]})
            with self.assertRaisesRegex(ValueError, "every task acceptance criterion"):
                propose(root, proposal)

    def test_proposal_matches_escaped_pipe_in_qa_criterion(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            proposal = root / "proposal.json"
            write(proposal, {"plan_id": "p1", "spec": "Handle either value", "acceptance_criteria": ["a | b works"],
                             "tasks": [{"task_id": "t1", "acceptance_criteria": ["a | b works"],
                                        "verification": [["pytest", "tests/test_values.py"]],
                                        "qa_plan": r"| QA-01 | a \| b works | Try both values | Both work |",
                                        "test_code": "### tests/test_values.py\n```python\ndef test_values():\n    assert True\n```"}]})
            propose(root, proposal)

    def test_proposal_rejects_non_text_test_code(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            proposal = root / "proposal.json"
            write(proposal, {"plan_id": "p1", "spec": "Total numbers", "acceptance_criteria": ["2 + 3 = 5"],
                             "tasks": [{"task_id": "t1", "acceptance_criteria": ["2 + 3 = 5"],
                                        "verification": [["pytest", "tests/test_total.py"]], "qa_plan": "| QA-01 | 2 + 3 = 5 | add inputs | 5 |", "test_code": []}]})
            with self.assertRaisesRegex(ValueError, "test_code must be nonempty"):
                propose(root, proposal)

    def test_plan_and_task_show_approved_tests_and_qa_scenarios(self):
        test_code = "### tests/test_total.py\n```python\ndef test_total():\n    assert total([2, 3]) == 5\n```"
        qa_plan = "| QA-01 | 2 + 3 = 5 | add inputs | 5 |"
        task = {"task_id": "t1", "title": "Total", "acceptance_criteria": ["2 + 3 = 5"],
                "verification": [["pytest", "tests/test_total.py"]], "qa_plan": qa_plan, "test_code": test_code}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            proposal = root / "proposal.json"
            write(proposal, {"plan_id": "p1", "spec": "Total numbers", "acceptance_criteria": ["2 + 3 = 5"],
                             "tasks": [task]})
            propose(root, proposal)
            plan_path = root / ".verified-development-loop/plans/drafts/p1.md"
            self.assertIn(test_code, plan_path.read_text(encoding="utf-8"))
            self.assertIn("QA scenarios:\n\n" + qa_plan, plan_path.read_text(encoding="utf-8"))
            approve(root, "p1", "approved")
            plan_path = root / ".verified-development-loop/plans/active/p1.md"
            task_path = root / ".verified-development-loop/tasks/active/t1.md"
            for path in (plan_path, task_path):
                self.assertIn(test_code, path.read_text(encoding="utf-8"))
                self.assertIn("QA scenarios:\n\n" + qa_plan, path.read_text(encoding="utf-8"))
            self.assertEqual(read(task_path)["test_code"], test_code)
            self.assertEqual(read(task_path)["qa_plan"], qa_plan)

    def test_proposal_requires_qa_scenarios(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            proposal = root / "proposal.json"
            write(proposal, {"plan_id": "p1", "spec": "Total numbers", "acceptance_criteria": ["2 + 3 = 5"],
                             "tasks": [{"task_id": "t1", "acceptance_criteria": ["2 + 3 = 5"],
                                        "verification": [["pytest", "tests/test_total.py"]]}]})
            with self.assertRaisesRegex(ValueError, "QA scenarios required"):
                propose(root, proposal)


if __name__ == "__main__":
    unittest.main()
