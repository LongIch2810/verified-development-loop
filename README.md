# Verified Development Loop (VDL)

VDL is a reusable **agent skill** for software projects. When explicitly requested, it guides an agent through a development process backed by evidence: clarify requirements → write a Spec and Plan → obtain human approval → implement with TDD → verify → conduct independent code review → run QA → report the outcome.

The skill helps prevent unapproved scope changes, skipped checks, and claims of completion without evidence. It applies when you name the verified development loop (including "chạy loop") or ask about its steps or approval gates. Questions about the process do not start a feature workflow; ask the agent to run it for a feature when you want to begin. Ordinary coding, bug fixes, and workflow maintenance do not activate it.

## Repository contents

The skill source lives in `skills/vdl-verified-development-loop/`. The Skills CLI copies it into the appropriate skill directory when installed in a project.

- [SKILL.md](skills/vdl-verified-development-loop/SKILL.md): coordination instructions and state transition rules.
- `agents/`: contracts for the planner, TDD coder, code reviewer, and QA tester. The main agent delegates through the current host's native subagent tools; these files do not create agents by themselves.
- `assets/templates/`: Spec, Plan, and QA report templates.
- `scripts/workflow.py`: manages workflow state, runs approved verification commands, and records evidence in the consuming project's `.verified-development-loop/` directory.
- `scripts/control_center.py`: a dashboard for progress and events at `http://127.0.0.1:4040`.
- `scripts/install_vdl.py`: initializes workflow directories, configures hooks, and starts the Control Center.
- `tests/`: repository maintenance tests; they are not installed with the skill.
- [LICENSE](LICENSE): MIT license. [CHANGELOG.md](CHANGELOG.md) records unreleased changes.

VDL requires **Python 3.11+**, Git, and an agent that can read the skill, run Python commands, and delegate to independent subagents. If a host cannot delegate, the agent must report that limitation rather than claim an independent review or QA run.

## Install the skill in a project

### Quick Install (One-Liner)

Run one single command from your project root to install the skill, initialize workflow state, register lifecycle hooks (for Codex, Claude Code, Cursor, and Antigravity), and start the Control Center:

- **Windows (PowerShell):**
  ```powershell
  npx skills add LongIch2810/verified-development-loop --skill vdl-verified-development-loop --copy -y; python .agents/skills/vdl-verified-development-loop/scripts/install_vdl.py --target .
  ```

- **Windows (CMD):**
  ```cmd
  npx skills add LongIch2810/verified-development-loop --skill vdl-verified-development-loop --copy -y && python .agents/skills/vdl-verified-development-loop/scripts/install_vdl.py --target .
  ```

- **macOS / Linux:**
  ```bash
  npx skills add LongIch2810/verified-development-loop --skill vdl-verified-development-loop --copy -y && python3 .agents/skills/vdl-verified-development-loop/scripts/install_vdl.py --target .
  ```

### Step-by-Step Installation

1. **Install the skill files:**
   ```sh
   npx skills add LongIch2810/verified-development-loop --skill vdl-verified-development-loop --copy -y
   ```
   `npx skills` detects installed agents and places the skill in their directories (`.agents/skills/` for Codex, Cursor, and Antigravity; `.claude/skills/` for Claude Code). No npm package is required; [the Skills CLI installs directly from a Git repository](https://github.com/vercel-labs/skills#source-formats).

2. **Run setup for hooks and Control Center:**
   ```sh
   python .agents/skills/vdl-verified-development-loop/scripts/install_vdl.py --target .
   ```
   *(Use `python3` instead of `python` on macOS and Linux.)*

   The script creates `.verified-development-loop/`, adds `.vdl/` to `.gitignore`, registers lifecycle hooks for **Codex, Claude Code, Cursor, and Antigravity**, and starts the Control Center at `http://127.0.0.1:4040`.

   To register hooks for specific hosts only, combine `--no-hooks` with host flags:
   ```sh
   python .agents/skills/vdl-verified-development-loop/scripts/install_vdl.py --target . --no-hooks --antigravity-hooks
   ```
   Host flags include `--codex-hooks`, `--claude-hooks`, `--cursor-hooks`, and `--antigravity-hooks`. Use `--no-control-center` to skip starting the dashboard.

   The workflow still records checkpoints emitted explicitly through `workflow.py emit` and its state transition commands. **Without hooks, the Control Center cannot passively observe prompts, sessions, or subagents.** The installer uses a `.cmd` launcher on Windows and `python3` on macOS/Linux. See [portability](skills/vdl-verified-development-loop/references/portability.md) and [event tracking](skills/vdl-verified-development-loop/references/tracking.md).

## Use the skill

Ask an agent with the skill installed, for example: “Use `$vdl-verified-development-loop` to implement this feature.” The agent prepares a Spec, Plan, and QA scenarios for your approval before changing application code. After approval, it performs TDD, verification, review, and QA according to the [skill instructions](skills/vdl-verified-development-loop/SKILL.md).

## Check the published skill

This repository is public on GitHub. Confirm that the Skills CLI discovers the skill with:

```sh
npx skills add LongIch2810/verified-development-loop --list
```
