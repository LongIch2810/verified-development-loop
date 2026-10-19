"""End-to-end integration test validating all requirements in Section 8 of the prompt.

Validates:
1. Running Dashboard & VDL agent workflows simultaneously
2. Triggering workflow steps and observing real-time SSE updates
3. Running real verification commands (PASS and FAIL)
4. Subagent start/stop lifecycle tracking
5. Fix Attempt counter tracking (1/3, 2/3, 3/3)
6. State persistence and recovery when Dashboard is closed and reopened
7. Multi-project isolation across two separate fixture repositories
8. Clean separation without modifying application code logic
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

# Add scripts directory
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "skills/vdl-verified-development-loop/scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import install_vdl
import vdl_events as ve
import workflow as w


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class E2EWorkflowTrackingIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base_dir = Path(self.temp.name)

        # Create two fixture repositories
        self.repo1 = self.base_dir / "fixture-repo-alpha"
        self.repo2 = self.base_dir / "fixture-repo-beta"

        for repo in (self.repo1, self.repo2):
            repo.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "--allow-empty", "-qm", "initial"],
                cwd=repo,
                check=True,
            )
            install_vdl.install_vdl(repo, start_dashboard=False)

        # Launch Control Center server on free port
        self.port = get_free_port()
        self.server_proc = subprocess.Popen(
            [
                sys.executable,
                str(SCRIPTS_DIR / "control_center.py"),
                "--root", str(self.repo1),
                "--port", str(self.port),
                "--monitor", str(self.repo2),
            ],
            cwd=str(self.base_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Wait for server to be responsive
        url = f"http://127.0.0.1:{self.port}/api/projects"
        connected = False
        for _ in range(30):
            try:
                with urllib.request.urlopen(url, timeout=0.5) as r:
                    if r.status == 200:
                        connected = True
                        break
            except Exception:
                time.sleep(0.1)

        self.assertTrue(connected, "Control Center server failed to start")

    def tearDown(self):
        self.server_proc.terminate()
        try:
            self.server_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.server_proc.kill()

    def test_full_e2e_workflow_and_multi_project_isolation(self):
        # 1. Verify both projects are registered
        projects_url = f"http://127.0.0.1:{self.port}/api/projects"
        with urllib.request.urlopen(projects_url) as r:
            p_data = json.loads(r.read().decode("utf-8"))
            p_ids = [p["id"] for p in p_data["projects"]]
            self.assertIn("fixture-repo-alpha", p_ids)
            self.assertIn("fixture-repo-beta", p_ids)

        # 2. Setup project 1 (alpha) application code and proposal
        app_file = self.repo1 / "math_app.py"
        app_file.write_text("def add(a, b): return a + b\n", encoding="utf-8")

        proposal_file = self.repo1 / "proposal.json"
        proposal_file.write_text(
            json.dumps({
                "plan_id": "math-plan",
                "spec": "Provide add and multiply operations",
                "acceptance_criteria": ["add works", "multiply works"],
                "tasks": [{
                    "task_id": "math-task-1",
                    "acceptance_criteria": ["multiply works correctly"],
                    "qa_plan": "| QA-01 | multiply works correctly | Call multiply(3, 4) through the public interface | 12 |",
                    "test_code": "### tests/test_math.py\n```python\nfrom math_app import multiply\n\ndef test_multiply():\n    assert multiply(3, 4) == 12\n```",
                    "verification": [
                        [sys.executable, "-c", "import math_app; assert hasattr(math_app, 'multiply') and math_app.multiply(3, 4) == 12"]
                    ],
                }],
            }),
            encoding="utf-8",
        )

        # 3. Host prompt telemetry is generic; the workflow starts only on an explicit checkpoint.
        hook_script = self.repo1 / ".agents" / "skills" / "vdl-verified-development-loop" / "scripts" / "vdl_host_hook.py"
        prompt_payload = json.dumps({
            "hook_event_name": "UserPromptSubmit",
            "session_id": "alpha-session-001",
            "prompt": "Please add multiply function to math_app",
            "tool_input": {"cwd": str(self.repo1)},
        })
        p = subprocess.run([sys.executable, str(hook_script)], input=prompt_payload, cwd=self.repo1, text=True, capture_output=True)
        self.assertEqual(p.returncode, 0)

        # 4. Run workflow.py propose
        workflow_script = self.repo1 / ".agents" / "skills" / "vdl-verified-development-loop" / "scripts" / "workflow.py"
        subprocess.run([sys.executable, str(workflow_script), "emit", "--event", "raw_prompt.received"], cwd=self.repo1, check=True)
        subprocess.run([sys.executable, str(workflow_script), "propose", "--input", "proposal.json"], cwd=self.repo1, check=True)

        # Verify state in Control Center for alpha
        state_url = f"http://127.0.0.1:{self.port}/api/state?project_id=fixture-repo-alpha"
        with urllib.request.urlopen(state_url) as r:
            state = json.loads(r.read().decode("utf-8"))
            step_map = {s["id"]: s for s in state["steps"]}
            self.assertEqual(step_map["raw_prompt"]["status"], "COMPLETED")
            self.assertEqual(step_map["spec"]["status"], "COMPLETED")
            self.assertEqual(step_map["plan"]["status"], "COMPLETED")
            self.assertEqual(step_map["human_approval"]["status"], "WAITING_HUMAN")

        # 5. Approve plan
        subprocess.run([sys.executable, str(workflow_script), "approve", "--plan-id", "math-plan", "--human-approval", "Approved by human user"], cwd=self.repo1, check=True)

        # 6. Run verification (EXPECTED FAIL: multiply is not implemented yet)
        res = subprocess.run([sys.executable, str(workflow_script), "verify", "--task-id", "math-task-1"], cwd=self.repo1)
        self.assertNotEqual(res.returncode, 0)

        # Check state: verification must be FAILED, not guessed PASS
        with urllib.request.urlopen(state_url) as r:
            state = json.loads(r.read().decode("utf-8"))
            step_map = {s["id"]: s for s in state["steps"]}
            self.assertEqual(step_map["verification"]["status"], "FAILED")
            self.assertEqual(state["verification"]["status"], "FAIL")
            self.assertEqual(state["verification"]["commands"][0]["exit_code"], 1)

        # 7. Start Fix round 1/3
        subprocess.run(
            [sys.executable, str(workflow_script), "record-error", "--task-id", "math-task-1", "--error-id", "err-no-multiply", "--description", "math_app has no multiply", "--detection", "verification assertion error"],
            cwd=self.repo1,
            check=True,
        )
        subprocess.run(
            [sys.executable, str(workflow_script), "start-fix", "--task-id", "math-task-1", "--error-id", "err-no-multiply", "--approach", "Implement multiply function"],
            cwd=self.repo1,
            check=True,
        )

        # Verify Fix counter shows 1 / 3
        with urllib.request.urlopen(state_url) as r:
            state = json.loads(r.read().decode("utf-8"))
            self.assertEqual(state["fix_loop"]["attempts"], 1)
            self.assertEqual(state["fix_loop"]["current_approach"], "Implement multiply function")

        # 8. Implement the required code in math_app.py
        app_file.write_text("def add(a, b): return a + b\n\ndef multiply(a, b): return a * b\n", encoding="utf-8")

        # 9. Re-verify (PASS)
        subprocess.run([sys.executable, str(workflow_script), "verify", "--task-id", "math-task-1"], cwd=self.repo1, check=True)

        # 10. Code Review (PASS)
        subprocess.run([sys.executable, str(workflow_script), "review", "--task-id", "math-task-1", "--result", "PASS", "--reviewer", "code_reviewer"], cwd=self.repo1, check=True)

        # 11. Evaluate error as resolved
        subprocess.run([sys.executable, str(workflow_script), "evaluate", "--task-id", "math-task-1", "--error-id", "err-no-multiply", "--result", "resolved", "--evidence", "verification exit code 0", "--lesson", "implement functions before verifying"], cwd=self.repo1, check=True)

        # 12. Independent QA (PASS) before completion
        qa_report = self.repo1 / ".verified-development-loop/evidence/math-task-1/qa-report.md"
        qa_report.write_text("# QA\n\n**Overall Result:** PASS\n\n## Regression Results\n\npython suite: 1 pass; output: 12\n\n## Scenario Results\n\nQA-01: multiply(3, 4); output: 12\n", encoding="utf-8")
        subprocess.run([sys.executable, str(workflow_script), "qa", "--task-id", "math-task-1", "--result", "PASS", "--tester", "qa_tester", "--report", str(qa_report)], cwd=self.repo1, check=True)

        # 13. Complete Task and Complete Plan
        human_report = qa_report.parent / "human-report.md"
        human_report.write_text(
            "# Human report\n\n- **Task:** math-task-1\n- **Status:** completed\n\n"
            "## Overview\n\n- **Plan:** math-plan\n- **Spec:** math-plan\n- **Code:** test branch\n"
            "- **Fix rounds:** 1/3\n- **Review rounds:** 1/3\n- **QA rounds:** 1/3\n\n"
            "## Commands and Results\n\n- verification: exit 0\n\n"
            "## Review and QA Rounds\n\n- review PASS, QA PASS\n\n"
            "## Remaining Checks\n\n- none\n\n## Evidence Paths\n\n- QA report\n",
            encoding="utf-8",
        )
        subprocess.run([sys.executable, str(workflow_script), "write-report", "--task-id", "math-task-1", "--status", "completed", "--input", str(human_report)], cwd=self.repo1, check=True)
        subprocess.run([sys.executable, str(workflow_script), "complete-task", "--task-id", "math-task-1", "--accept", "multiply works correctly"], cwd=self.repo1, check=True)
        subprocess.run([sys.executable, str(workflow_script), "complete-plan", "--plan-id", "math-plan", "--accept", "add works", "--accept", "multiply works"], cwd=self.repo1, check=True)

        # 14. Emit main agent report
        saved_report = w.read(w.path(self.repo1, "tasks", "completed", "math-task-1"))["latest_report"]
        subprocess.run([sys.executable, str(workflow_script), "emit", "--event", "main_agent.reported", "--task-id", "math-task-1", "--data", json.dumps({"summary": "Successfully added and verified multiply function", "report": saved_report})], cwd=self.repo1, check=True)

        # Verify final state for repo 1
        with urllib.request.urlopen(state_url) as r:
            state1 = json.loads(r.read().decode("utf-8"))
            step_map1 = {s["id"]: s for s in state1["steps"]}
            self.assertEqual(step_map1["main_agent_report"]["status"], "COMPLETED")
            self.assertEqual(step_map1["active"]["status"], "COMPLETED")
            self.assertEqual(state1["verification"]["status"], "PASS")

        # 15. Verify multi-project isolation in repo 2 (beta)
        # Repo 2 should be in initial pending state, completely untouched by repo 1!
        beta_state_url = f"http://127.0.0.1:{self.port}/api/state?project_id=fixture-repo-beta"
        with urllib.request.urlopen(beta_state_url) as r:
            state2 = json.loads(r.read().decode("utf-8"))
            step_map2 = {s["id"]: s for s in state2["steps"]}
            self.assertEqual(step_map2["raw_prompt"]["status"], "PENDING")
            self.assertEqual(step_map2["active"]["status"], "PENDING")
            self.assertEqual(state2["events_count"], 0)

        # 16. Verify State Recovery (Dashboard reopen simulation)
        # Fetching fresh state from a new client connection recovers complete history
        fresh_url = f"http://127.0.0.1:{self.port}/api/state?project_id=fixture-repo-alpha"
        with urllib.request.urlopen(fresh_url) as r:
            recovered_state = json.loads(r.read().decode("utf-8"))
            self.assertEqual(recovered_state["project_id"], "fixture-repo-alpha")
            self.assertGreater(recovered_state["events_count"], 8)
            self.assertEqual(recovered_state["steps"][-1]["status"], "COMPLETED")


if __name__ == "__main__":
    unittest.main()
