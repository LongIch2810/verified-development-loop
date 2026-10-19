# Error memory

For a completed bug-mode repair, use the existing error-record fields to retain the investigator-supported `root_cause`, original reproduction evidence, approved approach, verification/review/QA references, and resolved outcome. The initial repair is not a failed review or QA fix round; the existing three-round limits still govern later failures. Do not record a guessed cause as fact.

Each `.verified-development-loop/errors/ERROR.md` records IDs, description, evidence, root cause only if supported, fix attempt count, recurrence count, approaches and outcomes, verification logs, review findings, QA findings when applicable, status, and validated prevention lesson. Resolved records persist.

When the human considers accepting a remaining error, set its severity (`blocker`, `serious`, or `minor`) in the existing error record through `set-error-severity --task-id ID --error-id ERROR --severity LEVEL`. This also works after the Task is blocked. The accepted-error completion path requires `serious` or `minor` for every remaining error and preserves the error record; it never marks an accepted error `RESOLVED` without a passing repair.

At interview and task start, select records by relevant component, behavior, task, or symptom. Do not load the entire directory into model context.

Record every QA FAIL finding after its QA evidence using `record-error --classification code|spec|environment|uncertain`, one stable error ID per distinct issue. Code findings use `start-fix`, fresh verification, review, and full QA before `evaluate`; `persists` keeps the same error ID and may use the remaining fix rounds, blocking after the third failed fix. Environment findings are recorded but use no fix round; repair the environment, rerun QA, then `evaluate --result resolved` after QA PASS. Spec and uncertain findings block for human decision. Failed verification and review still use `record-error` and the existing fix flow. Use a new error ID only for a demonstrably distinct issue, never to evade the retry limit. A prevention lesson is recorded only with a passing resolution.
