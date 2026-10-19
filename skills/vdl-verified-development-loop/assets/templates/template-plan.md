# Plan Template for the TDD Coder

Fill this template **after drafting the [Spec](template-spec.md)**, then present the Spec and Plan together for human approval. This guides the planner and main agent. Create official draft records with `workflow.py propose --input proposal.json`; do not copy this template directly into a state directory. Give Tasks to the TDD coder only after approval.

## Plan Information

- **Plan ID:** `PLAN-<short-name>` (unique; letters, digits, `-`, and `_` only).
- **Spec:** the intended behavior and link to its accompanying Spec.
- **Out of scope:** changes that could otherwise be mistaken as part of this Plan.
- **Plan acceptance criteria:** observable user outcomes; each needs a Task and a check that demonstrates it.
- **Assumptions needing confirmation:** state them explicitly; do not turn assumptions into approved requirements.

## Plan Test Overview

Show which Task owns each applicable Unit, Integration, and E2E check. Put a cross-Task user journey's E2E check in a Task that runs after its dependencies. Explain any level that does not apply to the Plan.

| Level | Task ID and test case | Verification command or reason it does not apply |
| --- | --- | --- |
| Unit | `<Task ID: case>` | `<command or reason>` |
| Integration | `<Task ID: case>` | `<command or reason>` |
| E2E | `<Task ID: case>` | `<command or reason>` |

## Tasks in Execution Order

Each Task owns **one independently checkable part of the behavior**. Add `depends_on` only when a later Task truly needs an earlier Task's output. Repeat this section for every Task.

### `TASK-<id>` — `<specific behavior>`

- **Goal:** who does what and what observable result must appear.
- **Dependencies:** `[]` or real Task IDs in this Plan; do not create cycles.
- **Change scope:** expected files or modules, including callers, tests, or fixtures when known. Do not prescribe internal design before the behavior requires it.
- **Acceptance criteria:**
  1. **Given** `<state/input>`, **when** `<action>`, **then** `<observable result>`.
  2. **Given** `<boundary or invalid input>`, **when** `<action>`, **then** `<expected result or error>`.
- **Required test matrix:** include all three rows for **every Task**. Name concrete test cases and the criteria they prove. For a level that truly does not apply, write `Not applicable` and explain the system boundary. Consider Integration when the Task crosses an API, database, file, or multiple modules. Consider E2E for a user flow through a public UI, CLI, or API. Do not mark a level inapplicable merely to reduce tests.

  | Level | Test case, criterion, and boundary checked | Status or reason it does not apply |
  | --- | --- | --- |
  | Unit | `<case; logic, branch, or edge>` | `<write test or reason>` |
  | Integration | `<case; collaborating components>` | `<write test or reason>` |
  | E2E | `<case; public flow from entry to result>` | `<write test or reason>` |

- **Ordered test cases:** list **every case to write** for each criterion: case ID, criterion, level, initial state or fixture, input, action, expected result, and relevant regression. Start with the simplest case that exposes the missing behavior, then relevant boundaries, errors, and regressions. Avoid vague items such as “test edge cases.”
- **Complete test source before handoff:** after the list, include `Unit test`, `Integration test`, and `E2E test` subsections matching the matrix. For each applicable level, include the **complete proposed contents of every test file** in a language-tagged code fence with its repository-relative path. Include imports, setup or fixtures, concrete data, calls, and assertions for every listed case. Repeat the reason for an inapplicable level instead of adding fake code. Use this repository's framework, API, and conventions; leave no `TODO`, `pass`, `...`, placeholder, or fake assertion. An API that does not exist yet may make the test fail to import before the coder creates it, but its path, signature, and expected behavior must be explicit. Do not write application code in the Plan.
- **Test correspondence:** each listed case has a matching test block, and each acceptance criterion has an assertion. Ask for missing details before requesting approval if a deterministic assertion cannot be written. The TDD coder begins Red from this approved source. A changed expectation caused by an unclear Spec goes back to the main agent for Plan revision and human approval.
- **Independent QA scenarios:** before coding, fill in the QA context and scenario table below for this Task. Give every acceptance criterion at least one scenario with steps and an expected result from the Spec. Present them with the Spec and Plan; store the approved text in `tasks[].qa_plan`. The coder's tests are not the QA oracle.
- **Red:** write one new case, run it alone, and keep the command, failed result, and explanation showing the missing behavior. Syntax and environment errors are not a valid Red.
- **Green:** make the smallest change to pass that case; rerun it and related cases. Repeat Red → Green for the next case.
- **Refactor:** clarify code or tests only while Green, then rerun checks. Add no behavior outside the approved criteria.
- **Official verification:** specify separate commands for applicable Unit, Integration, and E2E levels plus necessary regression checks. Store commands that actually run from the repository root as argv arrays in `tasks[].verification`, such as `[["python", "-m", "unittest", "discover", "-s", "tests", "-p", "test_feature.py", "-q"]]` **only when that command and path fit the repository**. Do not use `&&`, pretend shell commands, or unchecked commands. Do not invent a command for an inapplicable level.
- **Handoff:** provide Red/Green commands and results, changed files, verification results, and remaining limits. The main agent runs `workflow.py verify`; an independent reviewer follows PASS, then QA runs the approved scenarios after review PASS. The TDD coder does not mark the Task complete.

#### QA Context and Scenarios

- **Task ID:** `TASK-<id>`.
- **Linked Spec:** `<Spec path and relevant acceptance criteria>`.
- **Environment:** `<startup command, URL or CLI, test data, and setup>`.

Keep criterion text exactly as approved; escape a literal pipe as `\|` in the table. Label any extra QA case `additional`. For a check that cannot be automated, state why and give manual steps when possible.

| ID | Acceptance criterion | Type | Steps | Expected result from Spec |
| --- | --- | --- | --- | --- |
| QA-01 | `<exact acceptance criterion>` | `functional / edge case / regression / integration` | `<initial state → concrete action>` | `<observable result>` |

- **Relevant edge cases:** `<only cases relevant to this Task, with a scenario ID or a reason for exclusion>`.
- **Outside QA scope:** `<behavior outside this Task or Spec, with reason>`.

### Complete Test Source Example

Illustration only; replace it with code for the target repository. Suppose `normalize_name` trims outer whitespace, rejects blank names, and preserves Unicode and internal spaces.

| Level | Case | Status or reason |
| --- | --- | --- |
| Unit | Three cases below | Required for the pure function and input branches |
| Integration | Not applicable | No database, file, API, or collaborating module |
| E2E | Not applicable | No public UI, CLI, or API flow |

| Case | Criterion | Input | Expected |
| --- | --- | --- | --- |
| `test_trims_outer_spaces` | Trim outer whitespace | `"  Ada  "` | `"Ada"` |
| `test_rejects_whitespace_only` | Reject blank name | `"   "` | `ValueError` |
| `test_preserves_unicode_and_internal_spaces` | Preserve valid content | `"  Zoë  Adams  "` | `"Zoë  Adams"` |

**Unit test — complete source for this Task's `test_code`:**

### `tests/test_names.py`

```python
import unittest

from app.names import normalize_name


class NormalizeNameTests(unittest.TestCase):
    def test_trims_outer_spaces(self):
        self.assertEqual(normalize_name("  Ada  "), "Ada")

    def test_rejects_whitespace_only(self):
        with self.assertRaises(ValueError):
            normalize_name("   ")

    def test_preserves_unicode_and_internal_spaces(self):
        self.assertEqual(normalize_name("  Zoë  Adams  "), "Zoë  Adams")
```

**Integration test:** Not applicable because this example has no collaborating component boundary.

**E2E test:** Not applicable because this example has no public UI, CLI, or API flow.

This example is not a valid verification command for any particular repository. Replace its imports, framework, fixtures, paths, and commands with real ones. Include every complete test file needed by the Task.

## Map the Plan to `proposal.json`

`workflow.py propose` requires Plan `plan_id`, `spec`, `acceptance_criteria`, and `tasks`. Each Task requires `task_id`, `acceptance_criteria`, `verification` (argv arrays), `test_code` (Markdown containing the Unit/Integration/E2E matrix, complete applicable test source, and reasons for inapplicable levels), and `qa_plan` (Markdown containing that Task's QA context and scenarios above); `title` and `depends_on` are optional. The Plan and Task `.md` records retain `test_code` and `qa_plan` for each role. Preserve the **exact text** of approved criteria for `complete-task --accept` and `complete-plan --accept`. Check every verification command in the target repository before proposing it.
