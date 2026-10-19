# QA Report Template

The QA tester records **observed results** from running the real product against the approved QA scenarios in the [Plan](template-plan.md). Save this Markdown report under `.verified-development-loop/evidence/TASK/` and return its path to the main agent. Do not report PASS without the actual command or action and its output or evidence.

## Summary

- **Task ID:** `TASK-<id>`.
- **Overall Result:** <PASS or FAIL, one word without backticks>.
- **QA round:** `<x/3>`; reruns caused only by the environment do not count as code fix rounds.
- **Commit/diff checked:** `<HEAD and current diff description>`.
- **Environment:** `<startup command, URL/port, configuration, and test data>`.

## Regression Results

- **Full test suite command:** `<actual command, or reason it could not run>`.
- **Result:** `<pass/fail counts and exit code, or NOT RUN with reason>`.
- **Actual output:** `<short excerpt and path to full log/output>`.

## Scenario Results

| ID | PASS/FAIL/NOT RUN | Command or action attempted | Actual result and evidence |
| --- | --- | --- | --- |
| QA-01 | `<PASS/FAIL/NOT RUN>` | `<command or exact actions; explain if not run>` | `<output or observation and log/screenshot path>` |

## Findings

Repeat this block for each finding; write `None` if there are none.

### `ERROR-<id>`

- **Severity:** `blocking / serious / minor`.
- **Reproduction:** `<initial state, data, and exact actions>`.
- **Expected from Spec:** `<approved criterion and result>`.
- **Actual:** `<observed result>`.
- **Evidence:** `<log, output, or screenshot path in Task evidence>`.
- **Suggested classification:** `code / spec / environment / uncertain` — `<one-sentence reason>`.

## Additional Edge Cases

| `additional` scenario | Command or action | Result and evidence |
| --- | --- | --- |
| `<description>` | `<action taken>` | `<observation and path>` |

## Limits

- `<what could not be checked and why; write "No known limits" if none>`.
