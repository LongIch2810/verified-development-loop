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

Run this from the project where you want to use VDL:

```sh
npx skills add LongIch2810/verified-development-loop --skill vdl-verified-development-loop
```

That command is enough to install the skill. `npx skills` detects installed agents and places the skill in their skill directories. For example, Codex and Cursor use `.agents/skills/`, while Claude Code also receives it in `.claude/skills/`. Add `--copy -y` if you want a copied installation without prompts. No npm package is required; [the Skills CLI installs directly from a Git repository](https://github.com/vercel-labs/skills#source-formats).

### Optional: set up hooks and Control Center

The install command does not run the setup script or activate hooks. To initialize workflow directories, register lifecycle hooks, and start the dashboard, run this in the same project:

```sh
python .agents/skills/vdl-verified-development-loop/scripts/install_vdl.py --target .
```

Use `python3` instead of `python` on macOS and Linux. The script creates `.verified-development-loop/`, adds `.vdl/` to `.gitignore`, and starts the Control Center. On **Windows, macOS, and Linux**, it also registers lifecycle hooks for Codex, Claude Code, and Cursor by default. These hooks let the dashboard observe sessions and subagents.

To register hooks for one host only, combine `--no-hooks` with that host's flag:

```sh
python .agents/skills/vdl-verified-development-loop/scripts/install_vdl.py --target . --no-hooks --codex-hooks
```

Replace `--codex-hooks` with `--claude-hooks` or `--cursor-hooks` as needed; you can combine host flags. Use `--no-control-center` to skip starting the dashboard.

The workflow still records checkpoints emitted explicitly through `workflow.py emit` and its state transition commands. **Without hooks, the Control Center cannot passively observe prompts, sessions, or subagents.** The installer uses a `.cmd` launcher on Windows and `python3` on macOS/Linux. Other hosts need their own hook adapter for passive observation. See [portability](skills/vdl-verified-development-loop/references/portability.md) and [event tracking](skills/vdl-verified-development-loop/references/tracking.md).

## Use the skill

Ask an agent with the skill installed, for example: “Use `$vdl-verified-development-loop` to implement this feature.” The agent prepares a Spec, Plan, and QA scenarios for your approval before changing application code. After approval, it performs TDD, verification, review, and QA according to the [skill instructions](skills/vdl-verified-development-loop/SKILL.md).

## Check the published skill

This repository is public on GitHub. Confirm that the Skills CLI discovers the skill with:

```sh
npx skills add LongIch2810/verified-development-loop --list
```
