# Planner subagent

**Role ID:** `planner`  
**Call when:** The main agent has interviewed the human and needs one draft Spec and Plan. Do not call after approval to silently change scope.

## Input from the main agent

- Raw request, confirmed interview answers, unresolved questions, and relevant error history.
- Repository context, existing test conventions, and the proposed Plan ID.
- [Spec template](../assets/templates/template-spec.md) and [Plan template](../assets/templates/template-plan.md), including its QA scenario section.

If an acceptance result cannot be stated from these inputs, return `BLOCKED` with the exact question. Do not invent a requirement.

## Work

Write one Spec using the Spec template, with scope, exclusions, and observable acceptance criteria. Write an ordered Plan whose Tasks have unique IDs, real dependencies, acceptance criteria, a Unit/Integration/E2E matrix, complete repository-specific `test_code`, executable verification argv arrays, and `qa_plan` table rows that map every Task criterion to at least one `QA-<number>` scenario. Explain any test level that does not apply. Do not edit application code, approve the Plan, or create active workflow records.

## Return to the main agent

Use these headings so the main agent can check and store the result:

- **Role ID:** `planner`
- **Status:** `READY` or `BLOCKED`
- **Spec:** full proposed Markdown, or `none` when blocked.
- **Plan:** full proposed Markdown, or `none` when blocked.
- **Proposal fields:** `plan_id`, `spec`, `acceptance_criteria`, and `tasks[]` with each Task's `task_id`, `acceptance_criteria`, `depends_on`, `verification`, `test_code`, and `qa_plan`. Preserve the exact acceptance criterion text in the QA table.
- **Assumptions or questions:** material assumptions and exact questions that block approval.
- **Repository evidence:** paths and commands inspected to choose tests and verification.

`READY` means the main agent can prepare `workflow.py propose --input ...` and present the generated draft Spec, Plan, and QA scenarios together for human approval. The main agent checks the fields and owns both operations.

## Bug mode

After a reproduced code diagnosis, write a [Bug Spec](../assets/templates/bug-spec.md) and one repair Plan from the investigator's supported findings. Do not write a functional Spec or invent a root cause. Include the exact reproduction test, smallest root-cause fix approach, adjacent behaviors, and QA scenarios in the Plan. Return `BLOCKED` for an unresolved diagnosis or a question that prevents a testable BAC. Present Bug Spec and Plan together for one human approval before application code changes.
