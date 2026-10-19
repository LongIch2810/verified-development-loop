# Human Report Template

The main agent completes this Markdown report from actual workflow evidence. Save the draft under `.verified-development-loop/evidence/TASK/`, then run `workflow.py write-report --task-id TASK --status completed|blocked|completed-accepted --input PATH`. The script saves a new file under `.verified-development-loop/reports/` and links it from the Task. Summarize that saved file to the human and include its path. Do not include tokens, passwords, environment variables, or copied long logs; link to evidence files instead.

- **Task:** `TASK-<id>`
- **Status:** `completed / blocked / completed-accepted` (use one exact value without backticks).

## Overview

- **Plan:** `<Plan ID and path>`.
- **Spec:** `<Spec ID, path, and relevant criteria>`.
- **Code:** `<commit or branch and relevant diff>`.
- **Fix rounds:** `<x/3>`.
- **Review rounds:** `<x/3>`.
- **QA rounds:** `<x/3 code-failure rounds; note environment-only reruns separately>`.
- **Outcome:** `<actual result and unmet criteria, if any>`.

## Commands and Results

| Command or action actually run | Exit code and observed result | Evidence path |
| --- | --- | --- |
| `<exact command or action>` | `<actual result>` | `<path to full output>` |

## Review and QA Rounds

| Round | Review result and findings | QA result and scenarios | Evidence paths |
| --- | --- | --- | --- |
| `<number>` | `<PASS/FAIL/NOT RUN and reason>` | `<PASS/FAIL/NOT RUN and reason>` | `<paths>` |

## Remaining Checks

- `<what was not checked and why; write "none" if complete>`.

## Evidence Paths

- `<verification, review, QA, error-memory, and other relevant evidence paths>`.

For `blocked` and `completed-accepted`, include the following sections. The main agent must give every open error an ID, severity, classification (`code / spec / environment / uncertain`), `file:line` or exact reproduction steps, and evidence path. State every attempted repair round and its observed result. Explain the four standard choices and their consequences; the human may request another course of action. These are report options, not script commands or a way to switch to bug mode. Leave the decision section empty for a blocked report; record the prior human acceptance in `Accepted Errors` for `completed-accepted`.

## Open Errors

| ID | Severity | Classification | File:line or reproduction | Evidence path |
| --- | --- | --- | --- | --- |
| `<error ID>` | `<blocker/serious/minor>` | `<classification>` | `<location or exact steps>` | `<path>` |

## Attempts

| Round | Change or action tried | Actual result and evidence |
| --- | --- | --- |
| `<number>` | `<approach>` | `<result and path>` |

## Why Not Converged

- `<supported hypothesis; label unverified explanations as hypotheses>`.

## Human Options

- **Another round with a different approach:** `<unavailable in this blocked Task: the CLI has no resume command. If 3/3 rounds were used, there is no fourth round or counter reset. Further work needs a newly approved Plan/Task with a different approach>`.
- **Revise Spec or Plan:** `<consequence and required approval>`.
- **Accept remaining errors:** `<consequence; never accept Blocker severity>`.
- **Cancel:** `<consequence>`.

## Human Decision


For `completed-accepted` only:

## Accepted Errors

- **Error IDs:** `<IDs accepted by the human>`.
- **Accepted by:** `<human identity>`.
- **Accepted on:** `<YYYY-MM-DD>`.
- **Basis:** `<decision reference and consequences explained>`.
