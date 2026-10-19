# Bug Spec Template

The planner writes this Bug Spec from the [investigator report](../../agents/investigator.md) after reproduction and diagnosis. Present it with one repair Plan and its QA scenarios for one human approval. Store the proposed Markdown in `proposal.json` as `spec`; store the exact BAC text in `acceptance_criteria`. Do not edit application code before approval.

## Information

- **Title:** `<observed bug>`.
- **Date:** `<YYYY-MM-DD>`.
- **Status:** `draft / active / completed`.
- **Severity:** `blocking / serious / minor`.
- **Violated requirement or AC:** `<FR/AC/PRD ID, or none>`.

## Observed and Expected Behavior

- **Actual:** `<observed result with evidence>`.
- **Expected:** `<result and its Spec/PRD/AC source>`.

## Reproduction and Environment

- **Exact steps:** `<initial state, inputs, and ordered actions or commands>`.
- **Environment:** `<version, configuration, data, and relevant conditions>`.

## Impact

- **Affected users:** `<who encounters the bug>`.
- **Data correctness:** `<whether data is wrong or at risk, with evidence>`.

## Diagnosis

Copy supported findings from the investigator report; do not invent a cause.

- **Root cause:** `<cause or unverified>`.
- **Evidence:** `<command and output, plus file:line>`.
- **Confidence:** `high / medium / low` — `<reason>`.
- **Rejected hypotheses:** `<hypotheses and evidence, or none>`.

## Repair Scope

- **In scope:** `<smallest root-cause repair, regression test, and affected callers or fixtures>`.
- **Out of scope:** `<nearby changes that must not be made>`.

## Acceptance Criteria

Make each BAC a binary check. Keep its exact text in the proposal and QA mapping.

1. **BAC-01:** `<the exact reproduction steps now produce the expected result>`.
2. **BAC-02:** `<a new regression test fails on unchanged code and passes after the repair>`.
3. **BAC-03:** `<the existing full test suite passes>`.
4. **BAC-04:** `<the named adjacent behaviors remain unchanged>`.

## Minimum QA Scenarios

- **Reproduction:** `<rerun the exact reported steps and compare actual with expected>`.
- **Adjacent behavior:** `<check each named neighboring behavior>`.
- **Full suite:** `<repository-specific command and PASS result>`.

## Open Questions

- `<questions or none; a blocking question prevents approval>`.

Put the fix approach, complete regression test source, verification argv arrays, and QA scenario table in the [Plan template](template-plan.md). The Bug Spec defines the observable bug and repair boundary.
