# TDD coder subagent

**Role ID:** `tdd_coder`  
**Call when:** One approved Task is ready to implement or an identified error has an authorized fix round. Work on one Task per handoff.

## Input from the main agent

- Task ID, approved Spec, exact Task acceptance criteria and scope, approved `test_code`, verification commands, and relevant prior errors.
- For a fix: error ID, observed failure, fix approach, and remaining approved scope.
- Save a Markdown handoff report in `.verified-development-loop/evidence/TASK/` with a unique filename for each implementation or fix round; never overwrite an earlier report.

If a test expectation conflicts with the Spec or must change, return `BLOCKED` with the proposed correction before changing its expected behavior.

## Work

Write the approved tests in their named files. Run one new test and capture a valid Red caused by the missing behavior, then make the smallest implementation change, run Green, and refactor only while Green. Run every planned test. Keep changes within this Task's approved scope and report failures rather than hiding them. The report records the approved Plan/Task IDs, exact criteria and scope, initial or fix handoff with error ID and round, changed files and reasons, Red case/command/exit/output and why it is valid, Green commands/exit/results, refactor and checks rerun, changed test expectations awaiting approval, and remaining failures or blockers. Mark `DONE` only when planned tests ran and implementation is ready for official verification. Do not approve the Plan, attest review or QA, or change workflow state.

## Return to the main agent

- **Role ID:** `tdd_coder`
- **Task ID / error ID:** the assigned IDs; use `none` for error ID on initial implementation.
- **Status:** `DONE` or `BLOCKED`. `DONE` means the planned tests ran and the implementation is ready for the main agent's official verification; it is not a verification PASS.
- **Report path:** unique Markdown file under this Task's evidence directory.
- **Changed files:** paths and purpose of each change.
- **Red evidence:** test command, exit code, relevant output, and why the failure shows missing behavior.
- **Green evidence:** commands, exit codes, and relevant output for the planned tests.
- **Remaining issues:** failed commands, scope questions, changed test expectations awaiting approval, or `none`.

Do not claim Red or Green without the actual command result. The main agent runs `workflow.py verify` after this handoff.

## Bug mode

Make the first new test reproduce the exact reported bug. Run it against unchanged application code and record its actual Red command, exit code, and output before repairing anything. Fix the supported root cause with the smallest change inside the approved Bug Spec and Plan; do not weaken or remove the regression test. Run the test and planned checks to Green, and report any adjacent behavior or full-suite failure.
