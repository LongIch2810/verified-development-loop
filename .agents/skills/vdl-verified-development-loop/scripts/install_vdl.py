"""Install the bundled skill and initialize its project state (Python 3.11+)."""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent


def copy_tree(src: Path, dst: Path, overwrite: bool = True):
    if src.resolve() == dst.resolve():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            if item.name in ("__pycache__", ".vdl", ".git"):
                continue
            copy_tree(item, target, overwrite)
        else:
            if overwrite or not target.exists():
                shutil.copy2(item, target)


def configure_gitignore(target_root: Path):
    gitignore = target_root / ".gitignore"
    entry = "\n.vdl/\n"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        if ".vdl/" not in content and ".vdl" not in content:
            gitignore.write_text(content.rstrip() + entry, encoding="utf-8")
    else:
        gitignore.write_text("__pycache__/\n*.pyc\n.vdl/\n", encoding="utf-8")


def hook_command(target_root: Path):
    scripts = target_root / ".agents" / "skills" / "vdl-verified-development-loop" / "scripts"
    if os.name == "nt":
        return '"' + (scripts / "vdl-hook.cmd").as_posix() + '"'
    return "python3 " + shlex.quote(str(scripts / "vdl_host_hook.py"))


def check_stop_hook(target_root: Path):
    with tempfile.TemporaryDirectory() as event_root:
        result = subprocess.run(
            hook_command(target_root), shell=True, cwd=target_root,
            input='{"hook_event_name":"Stop"}', capture_output=True, text=True,
            env={**os.environ, "VDL_PROJECT_ROOT": event_root}, timeout=10,
        )
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("VDL Stop hook must exit 0 and return exactly one JSON object") from exc
    if result.returncode != 0 or not isinstance(output, dict):
        raise RuntimeError("VDL Stop hook must exit 0 and return exactly one JSON object")


def configure_hooks(target_root: Path):
    codex_dir = target_root / ".codex"
    codex_dir.mkdir(parents=True, exist_ok=True)
    hooks_file = codex_dir / "hooks.json"

    hook_cmd = hook_command(target_root)

    hook_def = {
        "type": "command",
        "command": hook_cmd,
        "timeout": 10,
    }

    events = [
        "SessionStart",
        "UserPromptSubmit",
        "SubagentStart",
        "SubagentStop",
        "Stop",
    ]

    existing = json.loads(hooks_file.read_text(encoding="utf-8")) if hooks_file.exists() else {}
    if not isinstance(existing, dict) or not isinstance(existing.get("hooks", {}), dict):
        raise ValueError(f"Invalid hook configuration: {hooks_file}")

    hooks_dict = existing.setdefault("hooks", {})
    for ev in events:
        handlers = hooks_dict.setdefault(ev, [])
        # Check if already installed
        already = False
        for h in handlers:
            for sub_h in h.get("hooks", []):
                if "vdl-hook" in sub_h.get("command", "") or "vdl_codex_hook" in sub_h.get("command", "") or "vdl_host_hook" in sub_h.get("command", ""):
                    sub_h["command"] = hook_cmd
                    already = True
                    break
        if not already:
            handlers.append({"hooks": [hook_def]})

    hooks_file.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def configure_other_hooks(target_root: Path, host: str):
    config_file = target_root / (".claude/settings.json" if host == "claude" else ".cursor/hooks.json")
    config_file.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(config_file.read_text(encoding="utf-8")) if config_file.exists() else {}
    if not isinstance(existing, dict) or not isinstance(existing.get("hooks", {}), dict):
        raise ValueError(f"Invalid hook configuration: {config_file}")
    hooks = existing.setdefault("hooks", {})
    command = hook_command(target_root)
    names = ("SessionStart", "SubagentStart", "SubagentStop", "Stop") if host == "claude" else ("sessionStart", "subagentStart", "subagentStop", "sessionEnd")
    for name in names:
        handler = ({"hooks": [{"type": "command", "command": command + " " + name}]}
                   if host == "claude" else {"command": command + " " + name})
        current = hooks.setdefault(name, [])
        if not isinstance(current, list):
            raise ValueError(f"Invalid hook list for {name}: {config_file}")
        migrated = False
        for item in current:
            commands = item.get("hooks", []) if host == "claude" else [item]
            for existing_hook in commands:
                if any(script in existing_hook.get("command", "") for script in ("vdl-hook.cmd", "vdl_host_hook.py")):
                    existing_hook["command"] = command + " " + name
                    migrated = True
        if not migrated:
            current.append(handler)
    if host == "cursor":
        existing.setdefault("version", 1)
    config_file.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def configure_antigravity_hooks(target_root: Path):
    agents_dir = target_root / ".agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    hooks_file = agents_dir / "hooks.json"

    hook_cmd = hook_command(target_root)

    existing = json.loads(hooks_file.read_text(encoding="utf-8")) if hooks_file.exists() else {}
    if not isinstance(existing, dict):
        raise ValueError(f"Invalid hook configuration: {hooks_file}")

    tool_matcher = "run_command|replace_file_content|write_to_file|multi_replace_file_content"

    vdl_hook_config = {
        "PreToolUse": [
            {
                "matcher": tool_matcher,
                "hooks": [
                    {
                        "type": "command",
                        "command": f"{hook_cmd} PreToolUse",
                        "timeout": 10,
                    }
                ],
            }
        ],
        "PostToolUse": [
            {
                "matcher": tool_matcher,
                "hooks": [
                    {
                        "type": "command",
                        "command": f"{hook_cmd} PostToolUse",
                        "timeout": 10,
                    }
                ],
            }
        ],
        "PreInvocation": [
            {
                "type": "command",
                "command": f"{hook_cmd} PreInvocation",
                "timeout": 10,
            }
        ],
        "Stop": [
            {
                "type": "command",
                "command": f"{hook_cmd} Stop",
                "timeout": 10,
            }
        ],
    }

    hook_key = "vdl-verified-development-loop"
    legacy_key = "ai-coding-workflow"
    if legacy_key in existing and hook_key not in existing:
        existing[hook_key] = existing.pop(legacy_key)

    existing[hook_key] = vdl_hook_config
    hooks_file.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def control_center_roots(port: int):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/projects", timeout=0.3) as response:
            return {Path(item["root"]).resolve() for item in json.load(response)["projects"]}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def start_control_center(target_root: Path, port: int = 4040):
    roots = control_center_roots(port)
    if roots is not None:
        if target_root.resolve() in roots:
            return None
        raise RuntimeError(f"Port {port} is already serving a different Control Center project")
    script = target_root / ".agents/skills/vdl-verified-development-loop/scripts/control_center.py"
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    process = subprocess.Popen(
        [sys.executable, str(script), "--root", str(target_root), "--port", str(port)],
        cwd=target_root, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        **kwargs,
    )
    for _ in range(30):
        if target_root.resolve() in (control_center_roots(port) or set()):
            return process
        if process.poll() is not None:
            break
        time.sleep(0.1)
    process.terminate()
    raise RuntimeError(f"Control Center did not start on port {port}")


def install_vdl(
    target_root: Path,
    codex_hooks: bool = True,
    claude_hooks: bool = True,
    cursor_hooks: bool = True,
    antigravity_hooks: bool = True,
    start_dashboard: bool = True,
):
    target_root = target_root.resolve()
    print(f"Installing VDL into target repository: {target_root}")
    old_hook_path = ".agents/skills/ai-coding-workflow/scripts/vdl-hook.cmd"
    had_old_hook = any(
        old_hook_path in path.read_text(encoding="utf-8")
        for path in (
            target_root / ".codex/hooks.json",
            target_root / ".claude/settings.json",
            target_root / ".cursor/hooks.json",
            target_root / ".agents/hooks.json",
        )
        if path.exists()
    )

    # 1. Workflow Directories
    old_state = target_root / ".ai-coding-workflow"
    new_state = target_root / ".verified-development-loop"
    if old_state.exists():
        if new_state.exists():
            raise ValueError("Both old and new workflow state directories exist; merge them before installing")
        old_state.rename(new_state)
        for record in new_state.rglob("*.md"):
            content = record.read_text(encoding="utf-8")
            if ".ai-coding-workflow" in content:
                record.write_text(content.replace(".ai-coding-workflow", ".verified-development-loop"), encoding="utf-8")
    for d in [
        "plans/drafts", "plans/active", "plans/completed",
        "tasks/active", "tasks/completed",
        "errors", "evidence", "reports", "specs/drafts", "specs/active", "specs/completed",
    ]:
        dir_path = target_root / ".verified-development-loop" / d
        dir_path.mkdir(parents=True, exist_ok=True)

    # 2. Skill Directory
    skill_src = SKILL_ROOT
    skill_dst = target_root / ".agents" / "skills" / "vdl-verified-development-loop"
    old_skill = target_root / ".agents" / "skills" / "ai-coding-workflow"
    had_old_skill = old_skill.exists()
    if had_old_skill and not skill_dst.exists():
        old_skill.rename(skill_dst)
    if skill_src.exists():
        copy_tree(skill_src, skill_dst)
        print("  Installed skill: .agents/skills/vdl-verified-development-loop")
    if had_old_hook or had_old_skill:
        legacy_launcher = target_root / old_hook_path
        legacy_launcher.parent.mkdir(parents=True, exist_ok=True)
        legacy_launcher.write_text(
            '@echo off\ncall "%~dp0..\\..\\vdl-verified-development-loop\\scripts\\vdl-hook.cmd" %*\nexit /b %errorlevel%\n',
            encoding="utf-8",
        )

    for skill_name in ("ai-coding-workflow", "vdl-verified-development-loop"):
        entry = target_root / ".claude" / "skills" / skill_name / "SKILL.md"
        generated = (
            f"---\nname: {skill_name}\n"
            "description: Run the shared AI coding workflow when explicitly requested.\n"
            "---\n\n"
            f"Read and follow `.agents/skills/{skill_name}/SKILL.md` and its bundled references. "
            "The shared skill owns all role definitions and workflow scripts.\n"
        )
        if entry.exists() and entry.read_text(encoding="utf-8") == generated:
            entry.unlink()
            if not any(entry.parent.iterdir()):
                entry.parent.rmdir()

    # 3. Gitignore
    configure_gitignore(target_root)
    print("  Configured .gitignore (.vdl/ exclusion)")

    # 4. Lifecycle hooks
    if os.name == "nt" and (codex_hooks or claude_hooks or cursor_hooks or antigravity_hooks):
        check_stop_hook(target_root)
    if codex_hooks:
        configure_hooks(target_root)
        print("  Configured Codex lifecycle hooks in .codex/hooks.json")
    if claude_hooks:
        configure_other_hooks(target_root, "claude")
        print("  Configured Claude Code lifecycle hooks in .claude/settings.json")
    if cursor_hooks:
        configure_other_hooks(target_root, "cursor")
        print("  Configured Cursor lifecycle hooks in .cursor/hooks.json")
    if antigravity_hooks:
        configure_antigravity_hooks(target_root)
        print("  Configured Antigravity lifecycle hooks in .agents/hooks.json")

    if start_dashboard:
        process = start_control_center(target_root)
        print(f"  Control Center {'already running' if process is None else 'started'}: http://127.0.0.1:4040")

    print("\nVDL Installation successfully completed.")


def main():
    parser = argparse.ArgumentParser(description="Install VDL and real-time tracking in a repository")
    parser.add_argument("--target", type=Path, default=Path.cwd(), help="Target repository directory (default: cwd)")
    parser.add_argument("--no-hooks", action="store_true", help="skip automatic host hook registration")
    parser.add_argument("--no-control-center", action="store_true", help="install without starting the dashboard")
    parser.add_argument("--codex-hooks", action="store_true", help="with --no-hooks, install only Codex lifecycle hooks")
    parser.add_argument("--claude-hooks", action="store_true", help="with --no-hooks, install only Claude Code lifecycle hooks")
    parser.add_argument("--cursor-hooks", action="store_true", help="with --no-hooks, install only Cursor lifecycle hooks")
    parser.add_argument("--antigravity-hooks", action="store_true", help="with --no-hooks, install only Antigravity lifecycle hooks")
    args = parser.parse_args()
    install_vdl(
        args.target,
        codex_hooks=not args.no_hooks or args.codex_hooks,
        claude_hooks=not args.no_hooks or args.claude_hooks,
        cursor_hooks=not args.no_hooks or args.cursor_hooks,
        antigravity_hooks=not args.no_hooks or args.antigravity_hooks,
        start_dashboard=not args.no_control_center,
    )


if __name__ == "__main__":
    main()
