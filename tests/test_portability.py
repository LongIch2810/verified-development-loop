"""Check that a fresh repository receives all supported host adapters."""

import sys
import json
import shlex
import shutil
import socket
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "skills/vdl-verified-development-loop/scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import install_vdl as installer
from install_vdl import install_vdl, start_control_center


class PortabilityTests(unittest.TestCase):
    def test_install_migrates_existing_markdown_state(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            old = repo / ".ai-coding-workflow/plans/active"
            old.mkdir(parents=True)
            (old / "p1.md").write_text(".ai-coding-workflow/specs/active/p1.md", encoding="utf-8")
            install_vdl(repo, start_dashboard=False)
            self.assertFalse((repo / ".ai-coding-workflow").exists())
            self.assertEqual(
                (repo / ".verified-development-loop/plans/active/p1.md").read_text(encoding="utf-8"),
                ".verified-development-loop/specs/active/p1.md",
            )

    def test_install_renames_existing_skill_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            old = repo / ".agents/skills/ai-coding-workflow"
            old.mkdir(parents=True)
            (old / "user-note.md").write_text("keep", encoding="utf-8")
            install_vdl(repo, start_dashboard=False)
            self.assertFalse((old / "SKILL.md").exists())
            self.assertTrue((old / "scripts/vdl-hook.cmd").is_file())
            self.assertEqual((repo / ".agents/skills/vdl-verified-development-loop/user-note.md").read_text(encoding="utf-8"), "keep")

    def test_install_starts_control_center_by_default(self):
        with tempfile.TemporaryDirectory() as temp, patch("install_vdl.start_control_center") as start:
            repo = Path(temp)
            install_vdl(repo)
            start.assert_called_once_with(repo.resolve())

    def test_control_center_starts_and_reuses_same_project(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            install_vdl(repo, start_dashboard=False)
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            process = start_control_center(repo, port=port)
            try:
                self.assertIsNone(start_control_center(repo, port=port))
                self.assertIsNone(process.poll())
            finally:
                process.terminate()
                process.wait(timeout=5)

    def test_skill_folder_alone_initializes_shared_roles_and_state(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            installed_skill = repo / ".agents/skills/vdl-verified-development-loop"
            shutil.copytree(SCRIPTS_DIR.parent, installed_skill)
            subprocess.run([sys.executable, str(installed_skill / "scripts/install_vdl.py"), "--target", str(repo), "--no-control-center"], check=True, capture_output=True, text=True)
            for role in ("planner", "tdd-coder", "code-reviewer", "qa-tester"):
                self.assertTrue((installed_skill / "agents" / f"{role}.md").read_text(encoding="utf-8").strip())
            self.assertTrue((repo / ".verified-development-loop/specs/drafts").is_dir())
            self.assertTrue((repo / ".codex/hooks.json").is_file())
            self.assertTrue((repo / ".claude/settings.json").is_file())
            self.assertTrue((repo / ".cursor/hooks.json").is_file())
            self.assertFalse((repo / ".claude/skills/vdl-verified-development-loop/SKILL.md").exists())

    def test_installs_shared_skill_without_host_agent_files(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            (repo / "AGENTS.md").write_text("existing project guidance\n", encoding="utf-8")
            install_vdl(repo, start_dashboard=False)

            self.assertEqual((repo / "AGENTS.md").read_text(encoding="utf-8"), "existing project guidance\n")
            self.assertTrue((repo / ".agents/skills/vdl-verified-development-loop/scripts/workflow.py").is_file())
            self.assertFalse((repo / ".codex/agents").exists())
            self.assertTrue((repo / ".codex/hooks.json").is_file())
            self.assertFalse((repo / ".claude/agents").exists())
            self.assertFalse((repo / ".cursor/agents").exists())
            claude_entry = repo / ".claude/skills/vdl-verified-development-loop/SKILL.md"
            self.assertFalse(claude_entry.exists())
            claude_entry.parent.mkdir(parents=True, exist_ok=True)
            claude_entry.write_text("existing discovery instructions\n", encoding="utf-8")
            install_vdl(repo, start_dashboard=False)
            self.assertEqual(claude_entry.read_text(encoding="utf-8"), "existing discovery instructions\n")
            for directory in ("specs/drafts", "specs/active", "specs/completed", "plans/active", "tasks/active", "errors", "evidence"):
                self.assertTrue((repo / ".verified-development-loop" / directory).is_dir())
            self.assertFalse(list((repo / ".verified-development-loop").rglob(".gitkeep")))

    def test_reinstall_removes_only_generated_claude_skill_entry(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            entry = repo / ".claude/skills/vdl-verified-development-loop/SKILL.md"
            entry.parent.mkdir(parents=True)
            entry.write_text(
                "---\nname: vdl-verified-development-loop\n"
                "description: Run the shared AI coding workflow when explicitly requested.\n"
                "---\n\n"
                "Read and follow `.agents/skills/vdl-verified-development-loop/SKILL.md` and its bundled references. "
                "The shared skill owns all role definitions and workflow scripts.\n",
                encoding="utf-8",
            )
            install_vdl(repo, start_dashboard=False)
            self.assertFalse(entry.exists())

    @unittest.skipUnless(sys.platform == "win32", "Windows launcher only")
    def test_default_host_hooks_preserve_existing_config_and_do_not_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            (repo / ".claude").mkdir()
            (repo / ".claude/settings.json").write_text('{"permissions":{"allow":["Read"]}}', encoding="utf-8")
            install_vdl(repo, start_dashboard=False)
            install_vdl(repo, start_dashboard=False)
            codex = json.loads((repo / ".codex/hooks.json").read_text(encoding="utf-8"))
            claude = json.loads((repo / ".claude/settings.json").read_text(encoding="utf-8"))
            cursor = json.loads((repo / ".cursor/hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(claude["permissions"]["allow"], ["Read"])
            self.assertEqual(len(codex["hooks"]["SubagentStart"]), 1)
            self.assertEqual(len(codex["hooks"]["Stop"]), 1)
            self.assertEqual(len(claude["hooks"]["SubagentStart"]), 1)
            self.assertEqual(len(cursor["hooks"]["subagentStart"]), 1)
            self.assertIn("vdl-hook.cmd", cursor["hooks"]["subagentStart"][0]["command"])
            hook = repo / ".agents/skills/vdl-verified-development-loop/scripts/vdl-hook.cmd"
            run = subprocess.run(
                [str(hook), "subagentStart"], cwd=repo,
                input=json.dumps({"hook_event_name": "subagentStart", "subagent_id": "worker-1"}),
                capture_output=True, text=True,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout), {"permission": "allow"})
            self.assertIn("subagent.started", (repo / ".vdl/events.jsonl").read_text(encoding="utf-8"))
            stop_command = codex["hooks"]["Stop"][0]["hooks"][0]["command"]
            stop = subprocess.run(stop_command, shell=True, cwd=repo,
                                  input='{"hook_event_name":"Stop"}', capture_output=True, text=True)
            self.assertEqual(stop.returncode, 0, stop.stderr)
            self.assertEqual(json.loads(stop.stdout), {})

    @unittest.skipUnless(sys.platform == "win32", "Windows launcher only")
    def test_install_rejects_empty_stop_hook_stdout(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            empty_hook = repo / "empty-stop.cmd"
            empty_hook.write_text("@echo off\nexit /b 0\n", encoding="utf-8")
            with patch("install_vdl.hook_command", return_value=f'"{empty_hook.as_posix()}"'):
                with self.assertRaisesRegex(RuntimeError, "Stop hook.*JSON"):
                    install_vdl(repo, start_dashboard=False)

    @unittest.skipUnless(sys.platform == "win32", "Windows launcher only")
    def test_codex_hook_runs_from_path_with_shell_metacharacter(self):
        with tempfile.TemporaryDirectory(prefix="vdl & hook ") as temp:
            repo = Path(temp)
            install_vdl(repo, start_dashboard=False)
            hooks = json.loads((repo / ".codex/hooks.json").read_text(encoding="utf-8"))
            command = hooks["hooks"]["SessionStart"][0]["hooks"][0]["command"]
            run = subprocess.run(command, shell=True, input='{"hook_event_name":"SessionStart"}', text=True, capture_output=True, cwd=repo)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("session.started", (repo / ".vdl/events.jsonl").read_text(encoding="utf-8"))

    @unittest.skipUnless(sys.platform == "win32", "Windows launcher only")
    def test_install_updates_old_hook_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            install_vdl(repo, start_dashboard=False)
            old_commands = []
            for config in (repo / ".codex/hooks.json", repo / ".claude/settings.json", repo / ".cursor/hooks.json"):
                old = config.read_text(encoding="utf-8").replace("vdl-verified-development-loop", "ai-coding-workflow")
                config.write_text(old, encoding="utf-8")
                event = "sessionStart" if config.parent.name == ".cursor" else "SessionStart"
                handler = json.loads(old)["hooks"][event][0]
                old_commands.append(handler["command"] if config.parent.name == ".cursor" else handler["hooks"][0]["command"])
            install_vdl(repo, start_dashboard=False)
            for config in (repo / ".codex/hooks.json", repo / ".claude/settings.json", repo / ".cursor/hooks.json"):
                self.assertNotIn("skills/ai-coding-workflow", config.read_text(encoding="utf-8"))
                self.assertIn("skills/vdl-verified-development-loop", config.read_text(encoding="utf-8"))
            for command in old_commands:
                run = subprocess.run(command, shell=True, input='{"hook_event_name":"SessionStart"}', text=True, capture_output=True, cwd=repo)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(json.loads(run.stdout), {})

    def test_invalid_existing_codex_config_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            (repo / ".codex").mkdir()
            config = repo / ".codex/hooks.json"
            config.write_text("{invalid", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                install_vdl(repo, start_dashboard=False)
            self.assertEqual(config.read_text(encoding="utf-8"), "{invalid")

    def test_no_hooks_switch_skips_all_host_configs(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "install_vdl.py"),
                 "--target", str(repo), "--no-hooks", "--no-control-center"],
                check=True, capture_output=True, text=True,
            )
            self.assertFalse((repo / ".codex/hooks.json").exists())
            self.assertFalse((repo / ".claude/settings.json").exists())
            self.assertFalse((repo / ".cursor/hooks.json").exists())

    def test_posix_hooks_use_python3_and_keep_existing_config(self):
        with tempfile.TemporaryDirectory(prefix="vdl hook ' space ") as temp:
            repo = Path(temp)
            (repo / ".claude").mkdir()
            (repo / ".claude/settings.json").write_text('{"permissions":{"allow":["Read"]}}', encoding="utf-8")
            if sys.platform == "win32":
                install_vdl(repo, start_dashboard=False)
            with patch.object(installer, "os", SimpleNamespace(name="posix")):
                install_vdl(repo, start_dashboard=False)
                install_vdl(repo, start_dashboard=False)
            codex = json.loads((repo / ".codex/hooks.json").read_text(encoding="utf-8"))
            claude = json.loads((repo / ".claude/settings.json").read_text(encoding="utf-8"))
            cursor = json.loads((repo / ".cursor/hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(claude["permissions"]["allow"], ["Read"])
            for config, event, nested in ((codex, "SessionStart", True), (claude, "SubagentStart", True), (cursor, "subagentStart", False)):
                handlers = config["hooks"][event]
                self.assertEqual(len(handlers), 1)
                command = handlers[0]["hooks"][0]["command"] if nested else handlers[0]["command"]
                self.assertIn("python3 ", command)
                self.assertIn("vdl_host_hook.py", command)
                self.assertNotIn("vdl-hook.cmd", command)
                parts = shlex.split(command)
                self.assertEqual(parts[:2], ["python3", str(repo / ".agents/skills/vdl-verified-development-loop/scripts/vdl_host_hook.py")])


if __name__ == "__main__":
    unittest.main()
