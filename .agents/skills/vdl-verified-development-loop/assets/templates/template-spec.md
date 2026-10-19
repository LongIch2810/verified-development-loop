# Spec Template

The planner writes this Spec from the user's request, confirmed interview answers, and relevant error history **before planning implementation**. Present it with the Plan and QA scenarios for one human approval. Store the proposed content in `proposal.json` as `spec`; store the exact criteria below separately as the `acceptance_criteria` array. `workflow.py propose --input proposal.json` creates the draft Markdown record for approval. Do not edit application code or create active workflow records before approval.

## Context and Goal

- **Request:** `<the user's goal in their terms>`.
- **Current behavior:** `<what the product does now, with repository evidence when relevant>`.
- **Desired outcome:** `<what the user should be able to observe after the change>`.

## Scope

- **Included:** `<behaviors and user flows this change must cover>`.
- **Excluded:** `<nearby behaviors that remain outside this request>`.
- **Affected users or interfaces:** `<UI, API, CLI, data, or other public boundary>`.

## Required Behavior

Describe inputs, actions, outputs, and error behavior from the user's perspective. Include relevant boundaries such as empty input, invalid data, repeated actions, and existing data only when they affect this request. State any security, accessibility, or compatibility requirement that the change must preserve.

## Acceptance Criteria

Write each criterion as one observable outcome. Use the **exact same text** in the proposal's Plan-level `acceptance_criteria` array; the main agent later attests these strings exactly. Task criteria may be more specific but must collectively cover the Spec criteria.

1. **Given** `<initial state or input>`, **when** `<action>`, **then** `<observable result>`.
2. **Given** `<relevant boundary or failure>`, **when** `<action>`, **then** `<observable result or error>`.

Every criterion must be assigned to at least one Plan Task and have a verification check. Every Task criterion needs at least one approved QA scenario in the [Plan template](template-plan.md).

## Constraints and Dependencies

- **Constraints:** `<confirmed technical, product, timing, or data constraints; write "None confirmed" if none>`.
- **Dependencies:** `<external state, access, or other prerequisite; write "None" if none>`.

## Open Questions and Assumptions

- **Questions blocking a testable outcome:** `<ask the main agent to resolve with the human before proposing; write "None" if none>`.
- **Assumptions:** `<state only supported assumptions and their source; do not treat unconfirmed assumptions as approved requirements>`.

The Spec defines **what** must be observed. Put implementation steps, test source, verification commands, Task dependencies, and fix rounds in the [Plan template](template-plan.md).
