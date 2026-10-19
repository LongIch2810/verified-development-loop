# Planning

## Bug mode

After the [investigator](../agents/investigator.md) reproduces and supports a code root cause, ask the planner for one [Bug Spec](../assets/templates/bug-spec.md) and repair Plan with a concrete fix approach, regression test source, and QA scenarios. The existing proposal fields remain, with `mode: "bug"`, `diagnosis_evidence`, `error_id`, and `fix_approach`; feature proposals omit these and retain their behavior. Keep the temporary proposal input under `.verified-development-loop/evidence/PLAN/` so it does not alter the pre-repair code fingerprint. Present Bug Spec and fix approach together for **one** explicit human approval. Do not edit application code before approval. A blocking open question or missing diagnosis evidence prevents approval.

The steps below describe feature mode.

1. Receive the raw prompt. Search `.verified-development-loop/errors/*.md` by relevant task, component, or symptom; read only matches before interviewing the human.
2. Main agent interviews the human about material gaps in scope, expected behavior, constraints, and verification. Record confirmed answers.
3. Ask `planner` to return one Spec using [the Spec template](../assets/templates/template-spec.md) and one Plan using [the Plan template](../assets/templates/template-plan.md). Spec states scope, exclusions, and observable acceptance criteria. Plan gives ordered task IDs, dependencies, complete test source for every Task, real verification commands, and independent QA scenarios for this repository. Every Task criterion has at least one QA scenario, written before coding. The planning agent does not approve or implement.
4. Present Spec, Plan, and its QA scenarios together for one human approval. If edited, regenerate the affected parts and present them together again.
5. Prepare a proposal input with `plan_id`, `spec`, `acceptance_criteria` (array of strings), and `tasks` (array of objects with `task_id`, `acceptance_criteria`, `verification` as argv arrays, `test_code` containing the approved Markdown test files, `qa_plan` containing the approved Markdown QA scenarios, and optional `depends_on`). Use `workflow.py propose --input proposal.json` to generate `.verified-development-loop/specs/drafts/ID.md` and `.verified-development-loop/plans/drafts/ID.md`. The input JSON is temporary; the stored workflow records are Markdown. No application edits or active state yet.
6. On explicit approval, use `workflow.py approve --plan-id ID --human-approval 'exact human approval or reference'`. This moves the approved Spec to `.verified-development-loop/specs/active/ID.md`, moves the Plan to `.verified-development-loop/plans/active/ID.md`, and creates active Task Markdown files. The script checks that draft Spec and Plan agree. It cannot authenticate who supplied the approval; the main agent must verify the human actually gave it.

Do not add separate Spec Review or Plan Review stages.
