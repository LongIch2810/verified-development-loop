"""Evidence-backed state gates for the VDL skill (Python 3.11+)."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

try:
    from workflow_docs import read, write
except ImportError:
    from .workflow_docs import read, write

try:
    from vdl_events import emit_event
except Exception:
    try:
        from .vdl_events import emit_event
    except Exception:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from vdl_events import emit_event


def fail(message):
    raise ValueError(message)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def safe_emit(root, event_type, status="COMPLETED", **kwargs):
    try:
        return emit_event(root, event_type, status=status, source="script", **kwargs)
    except Exception:
        return None


def identifier(value):
    if not value or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in value):
        fail("IDs must contain only letters, digits, hyphen, or underscore")
    return value


def path(root, kind, state, name):
    return root / ".verified-development-loop" / kind / state / (identifier(name) + ".md")


def active_task(root, task_id, allow_pending=False):
    p = path(root, "tasks", "active", task_id)
    if not p.exists():
        fail("task is not active (approval required, or task already completed)")
    task = read(p)
    plan = path(root, "plans", "active", task["plan_id"])
    if not plan.exists() or read(plan)["status"] != "active":
        fail("approved active plan required")
    if task["status"] == "blocked":
        fail("task is blocked; wait for human decision")
    if task.get("pending_block_reason") and not allow_pending:
        fail("task awaits a blocked report and block-task")
    return p, task


def snapshot(root):
    """Bind evidence to HEAD and all tracked/untracked nonignored project files."""
    result = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root, capture_output=True, check=True)
    head = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=root, capture_output=True)
    digest = hashlib.sha256(head.stdout if head.returncode == 0 else b"<unborn HEAD>")
    excluded = (".git/", ".agents/skills/vdl-verified-development-loop/", "skills/vdl-verified-development-loop/", ".verified-development-loop/", ".vdl/")
    for raw in sorted(set(result.stdout.split(b"\0"))):
        if not raw:
            continue
        name = raw.decode("utf-8", "surrogateescape").replace("\\", "/")
        if name.startswith(excluded) or name == "AGENTS.md":
            continue
        file = root / name
        digest.update(raw + b"\0")
        digest.update(file.read_bytes() if file.is_file() else b"<missing>")
    return digest.hexdigest()


def evidence(root, kind, task_id, data):
    p = root / ".verified-development-loop" / "evidence" / task_id / f"{kind}-{uuid4().hex}.md"
    write(p, {"time": stamp(), **data})
    return p.relative_to(root).as_posix()


def record_diagnosis(root, plan_id, report, result, classification, confidence):
    identifier(plan_id)
    report_path = (report if report.is_absolute() else root / report).resolve()
    evidence_dir = (root / ".verified-development-loop" / "evidence" / plan_id).resolve()
    if report_path.parent != evidence_dir or report_path.suffix != ".md" or not report_path.is_file():
        fail("investigator report must be Markdown in this Plan's evidence directory")
    prior = list(evidence_dir.glob("diagnosis-*.md"))
    if len(prior) >= 2:
        fail("two diagnosis rounds exhausted; ask the human")
    if result not in ("REPRODUCED", "NOT_REPRODUCED") or classification not in ("code", "spec", "environment", "uncertain") or confidence not in ("high", "medium", "low"):
        fail("diagnosis result, classification, and confidence required")
    report_text = report_path.read_text(encoding="utf-8")
    for field, value in (("Result", result), ("Classification", classification), ("Confidence", confidence)):
        if not re.search(rf"\*\*{field}:\*\*\s*{value}\b", report_text):
            fail(f"investigator report must state {field}: {value}")
    cause = re.search(r"^\s*(?:-\s*)?\*\*Root cause:\*\*\s*(.+)$", report_text, re.MULTILINE)
    if result == "REPRODUCED" and classification == "code" and confidence != "low":
        if not cause or not re.search(r"\b[^\s:]+:\d+\b", cause.group(1)) or "**Evidence:**" not in report_text:
            fail("supported code diagnosis requires root-cause file:line and an evidence section")
    ref = evidence(root, "diagnosis", plan_id, {"plan_id": plan_id, "round": len(prior) + 1,
        "result": result, "classification": classification, "confidence": confidence,
        "root_cause": cause.group(1) if cause else None, "report": report_path.relative_to(root).as_posix(),
        "report_text": report_text, "revision": snapshot(root)})
    ready = result == "REPRODUCED" and classification == "code" and confidence in ("high", "medium")
    safe_emit(root, "diagnosis.completed", "COMPLETED" if ready else "BLOCKED",
              plan_id=plan_id, agent_id="investigator", evidence_reference=ref,
              data={"result": result, "classification": classification, "confidence": confidence, "round": len(prior) + 1})
    return ref


def require_diagnosis(root, record, unchanged=False):
    if record.get("mode", "feature") != "bug":
        return None
    ref = record.get("diagnosis_evidence")
    if not ref:
        fail("bug mode requires diagnosis evidence")
    p = (root / ref).resolve()
    expected = (root / ".verified-development-loop" / "evidence" / record["plan_id"]).resolve()
    if p.parent != expected or not p.is_file() or not p.name.startswith("diagnosis-"):
        fail("linked diagnosis evidence is missing or outside this Plan")
    data = read(p)
    report = (root / data["report"]).resolve()
    if report.parent != expected:
        fail("investigator report is outside this Plan's evidence directory")
    if (data["plan_id"] != record["plan_id"] or data["result"] != "REPRODUCED"
            or data["classification"] != "code" or data["confidence"] not in ("high", "medium")
            or not report.is_file() or report.read_text(encoding="utf-8") != data["report_text"]):
        fail("supported reproduced code diagnosis required")
    if unchanged and data["revision"] != snapshot(root):
        fail("application code changed since diagnosis; diagnose again before approval")
    return data


def stage_block(root, task, reason):
    task["pending_block_reason"] = task.get("pending_block_reason") or reason
    write(path(root, "tasks", "active", task["task_id"]), task)


REPORT_SECTIONS = ("Overview", "Commands and Results", "Review and QA Rounds", "Remaining Checks", "Evidence Paths")
OPEN_REPORT_SECTIONS = ("Open Errors", "Attempts", "Why Not Converged", "Human Options", "Human Decision")


def require_report(root, task, status):
    ref = task.get("latest_report")
    if not ref or task.get("report_status") != status:
        fail(f"{status} report required before transition")
    report = (root / ref).resolve()
    reports_dir = (root / ".verified-development-loop" / "reports").resolve()
    if report.parent != reports_dir or not report.name.startswith(f"{task['task_id']}-{status}-") or not report.is_file():
        fail("linked report is missing, empty, or outside reports directory")
    content = report.read_text(encoding="utf-8")
    if not content.strip() or f"**Task:** {task['task_id']}" not in content or f"**Status:** {status}" not in content:
        fail("linked report is empty or disagrees with task and status")
    return ref


def write_report(root, task_id, status, source):
    if status not in ("completed", "blocked", "completed-accepted"):
        fail("report status must be completed, blocked, or completed-accepted")
    task_path = path(root, "tasks", "active", task_id)
    task = read(task_path)
    if task["status"] != "active" and not (status == "completed-accepted" and task["status"] == "blocked"):
        fail("report requires an active task or blocked task accepting errors")
    source_path = (source if source.is_absolute() else root / source).resolve()
    if source_path.parent != (root / ".verified-development-loop" / "evidence" / task_id).resolve() or source_path.suffix != ".md" or not source_path.is_file():
        fail("report input must be a Markdown file in this task's evidence directory")
    body = source_path.read_text(encoding="utf-8")
    if not body.strip() or f"**Task:** {task_id}" not in body or f"**Status:** {status}" not in body:
        fail("report must identify its task and status")
    sections = REPORT_SECTIONS + (OPEN_REPORT_SECTIONS if status != "completed" else ())
    if status == "completed-accepted":
        sections += ("Accepted Errors",)
    for heading in sections:
        match = re.search(rf"^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)", body, re.MULTILINE | re.DOTALL)
        if not match or (heading != "Human Decision" and not match.group(1).strip()):
            fail(f"report requires {heading} section")
    for label in ("Plan", "Spec", "Code", "Fix rounds", "Review rounds", "QA rounds"):
        if not re.search(rf"^\s*-\s*\*\*{re.escape(label)}:\*\*\s*\S+", body, re.MULTILINE):
            fail(f"report requires {label} field")
    if status == "blocked" and not task.get("pending_block_reason"):
        fail("blocked report requires a pending blocker")
    reports_dir = root / ".verified-development-loop" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{task_id}-{status}-{datetime.now(timezone.utc):%Y%m%d-%H%M}"
    index = 1
    while True:
        suffix = "" if index == 1 else f"-{index}"
        report_path = reports_dir / f"{stem}{suffix}.md"
        try:
            with report_path.open("x", encoding="utf-8") as stream:
                stream.write(body)
            break
        except FileExistsError:
            index += 1
    ref = report_path.relative_to(root).as_posix()
    task.update(latest_report=ref, report_status=status)
    write(task_path, task)
    safe_emit(root, "report.recorded", "COMPLETED", plan_id=task["plan_id"], task_id=task_id,
              evidence_reference=ref, data={"report_status": status})
    return ref


def block(root, task, reason):
    require_report(root, task, "blocked")
    task["status"] = "blocked"
    task["blocked_reason"] = reason
    task.pop("pending_block_reason", None)
    plan_path = path(root, "plans", "active", task["plan_id"])
    plan = read(plan_path)
    plan["execution_state"] = "waiting_human"
    write(plan_path, plan)
    write(path(root, "tasks", "active", task["task_id"]), task)
    for error_path in (root / ".verified-development-loop" / "errors").glob("*.md") if (root / ".verified-development-loop" / "errors").exists() else []:
        error = read(error_path)
        if error["task_id"] == task["task_id"] and error["status"] == "OPEN":
            error["status"] = "BLOCKED"
            if error["attempts"] and error["attempts"][-1]["result"] == "pending":
                error["attempts"][-1].update(result="blocked", evidence=reason, verification=task.get("verification_evidence"), review=task.get("review_evidence"))
                if task.get("verification_evidence"):
                    error["verification_logs"].append(task["verification_evidence"])
                if task.get("review_evidence"):
                    error["review_findings"].append(task["review_evidence"])
            write(error_path, error)
    safe_emit(root, "task.blocked", "BLOCKED", plan_id=task.get("plan_id"), task_id=task.get("task_id"), data={"reason": reason})


def propose(root, source):
    draft = read(source)
    plan_id = identifier(draft["plan_id"])
    if draft.get("mode", "feature") not in ("feature", "bug"):
        fail("mode must be feature or bug")
    if draft.get("mode") == "bug" and (not draft.get("error_id") or not draft.get("fix_approach")):
        fail("bug mode requires error ID and approved fix approach")
    if draft.get("mode") == "bug":
        identifier(draft["error_id"])
    if not draft.get("spec") or not draft.get("acceptance_criteria") or not draft.get("tasks"):
        fail("spec, plan acceptance criteria, and tasks required")
    ids = set()
    for task in draft["tasks"]:
        tid = identifier(task["task_id"])
        if tid in ids or not task.get("acceptance_criteria") or not task.get("verification"):
            fail("unique task IDs, acceptance criteria, and verification commands required")
        if not isinstance(task.get("qa_plan"), str) or not re.search(r"\bQA-\d+\b", task["qa_plan"]):
            fail("approved QA scenarios required for each task")
        qa_criteria = {
            criterion.strip().replace(r"\|", "|")
            for criterion in re.findall(r"^\s*\|\s*QA-\d+\s*\|\s*((?:\\\||[^|\n])+?)\|", task["qa_plan"], re.MULTILINE)
        }
        if not set(task["acceptance_criteria"]).issubset(qa_criteria):
            fail("every task acceptance criterion requires a QA scenario row")
        if any(not isinstance(cmd, list) or not cmd or not all(isinstance(a, str) and a for a in cmd) for cmd in task["verification"]):
            fail("verification must be a list of nonempty argv lists")
        if not isinstance(task.get("test_code"), str) or not task["test_code"].strip():
            fail("test_code must be nonempty Markdown text")
        ids.add(tid)
    for task in draft["tasks"]:
        if any(dep not in ids or dep == task["task_id"] for dep in task.get("depends_on", [])):
            fail("invalid task dependency")
    remaining = {task["task_id"]: set(task.get("depends_on", [])) for task in draft["tasks"]}
    while remaining:
        ready = {tid for tid, deps in remaining.items() if not deps.intersection(remaining)}
        if not ready:
            fail("cyclic task dependency")
        for tid in ready:
            del remaining[tid]
    if any(path(root, "plans", s, plan_id).exists() for s in ("drafts", "active", "completed")):
        fail("plan ID already exists")
    if any(path(root, "specs", state, plan_id).exists() for state in ("drafts", "active", "completed")):
        fail("spec ID already exists")
    for tid in ids:
        if any(path(root, "tasks", s, tid).exists() for s in ("active", "completed")):
            fail("task ID already exists")
    draft["status"] = "draft"
    write(path(root, "specs", "drafts", plan_id), {"plan_id": plan_id, "spec": draft["spec"], "acceptance_criteria": draft["acceptance_criteria"], "status": "draft"})
    draft["spec_file"] = f".verified-development-loop/specs/drafts/{plan_id}.md"
    write(path(root, "plans", "drafts", plan_id), draft)
    safe_emit(root, "spec.completed", "COMPLETED", plan_id=plan_id, data={"spec": draft.get("spec")})
    safe_emit(root, "plan.completed", "COMPLETED", plan_id=plan_id, data={"tasks": [t.get("task_id") for t in draft.get("tasks", [])]})
    safe_emit(root, "approval.waiting", "WAITING_HUMAN", plan_id=plan_id)


def approve(root, plan_id, human):
    source = path(root, "plans", "drafts", plan_id)
    plan = read(source)
    require_diagnosis(root, plan, unchanged=True)
    if not human.strip():
        fail("human approval record required")
    draft_spec_path = path(root, "specs", "drafts", plan_id)
    if not draft_spec_path.exists():
        fail("draft spec required")
    draft_spec = read(draft_spec_path)
    if draft_spec["spec"] != plan["spec"] or draft_spec["acceptance_criteria"] != plan["acceptance_criteria"]:
        fail("draft Spec and Plan disagree")
    spec_path = path(root, "specs", "active", plan_id)
    if spec_path.exists():
        fail("approved spec already exists")
    for item in plan["tasks"]:
        if any(path(root, "tasks", state, item["task_id"]).exists() for state in ("active", "completed")):
            fail("task ID already exists")
    approval = {"record": human, "time": stamp()}
    write(spec_path, {**draft_spec, "status": "active", "human_approval": approval})
    plan.update(status="active", execution_state="running", human_approval=approval, spec_file=spec_path.relative_to(root).as_posix())
    for item in plan["tasks"]:
        task = {**item, "plan_id": plan_id, "status": "active", "fix_round": 0, "verification_evidence": None, "review_evidence": None, "qa_evidence": None, "qa_failures": [], "acceptance_evidence": None}
        if plan.get("mode") == "bug":
            task.update(mode="bug", diagnosis_evidence=plan["diagnosis_evidence"])
        write(path(root, "tasks", "active", item["task_id"]), task)
    write(path(root, "plans", "active", plan_id), plan)
    source.unlink()
    draft_spec_path.unlink()
    safe_emit(root, "approval.approved", "COMPLETED", plan_id=plan_id, data={"human_approval": human})
    safe_emit(root, "workflow.started", "COMPLETED", plan_id=plan_id)
    if plan.get("tasks"):
        first_task = plan["tasks"][0]["task_id"]
        safe_emit(root, "task.started", "RUNNING", plan_id=plan_id, task_id=first_task)


def verify(root, task_id):
    p, task = active_task(root, task_id)
    require_diagnosis(root, task)
    for dep in task.get("depends_on", []):
        if not path(root, "tasks", "completed", dep).exists():
            fail("task dependency is not completed")
    safe_emit(root, "verification.started", "RUNNING", plan_id=task.get("plan_id"), task_id=task_id)
    revision = snapshot(root)
    results = []
    for command in task["verification"]:
        try:
            run = subprocess.run(command, cwd=root, capture_output=True, text=True, errors="replace", timeout=600)
            result = {"command": command, "exit_code": run.returncode, "stdout": run.stdout, "stderr": run.stderr}
        except (OSError, subprocess.TimeoutExpired) as exc:
            result = {"command": command, "exit_code": None, "error": str(exc)}
        results.append(result)
    status = "UNVERIFIED" if any(r["exit_code"] is None for r in results) else "PASS" if all(r["exit_code"] == 0 for r in results) else "FAIL"
    ref = evidence(root, "verification", task_id, {"revision": revision, "status": status, "commands": results})
    task.update(verification_evidence=ref, review_evidence=None, qa_evidence=None, acceptance_evidence=None)
    if status == "PASS":
        safe_emit(root, "verification.passed", "COMPLETED", plan_id=task.get("plan_id"), task_id=task_id, evidence_reference=ref, data={"commands": results, "revision": revision})
    else:
        safe_emit(root, "verification.failed", "FAILED", plan_id=task.get("plan_id"), task_id=task_id, evidence_reference=ref, data={"commands": results, "revision": revision, "status": status})
    if status != "PASS" and task["fix_round"] >= 3:
        stage_block(root, task, "verification failed after third fix")
    else:
        write(p, task)
    print(f"{status}: {ref}")
    return status == "PASS"


def current_verification(root, task):
    ref = task.get("verification_evidence")
    if not ref:
        fail("verification evidence required")
    data = read(root / ref)
    if data["status"] != "PASS" or data["revision"] != snapshot(root):
        fail("current code has no passing verification")
    return data


def review(root, task_id, result, findings, reviewer):
    p, task = active_task(root, task_id)
    current_verification(root, task)
    safe_emit(root, "review.started", "RUNNING", plan_id=task.get("plan_id"), task_id=task_id, agent_id=reviewer)
    if result not in ("PASS", "FAIL"):
        fail("review result must be PASS or FAIL")
    if result == "FAIL" and not findings:
        fail("FAIL review requires substantiated findings")
    if result == "PASS" and findings:
        fail("PASS review cannot include findings")
    if reviewer != "code_reviewer":
        fail("independent code_reviewer attestation required")
    ref = evidence(root, "review", task_id, {"revision": snapshot(root), "status": result, "reviewer": reviewer, "findings": findings, "verification_evidence": task["verification_evidence"]})
    task.update(review_evidence=ref, qa_evidence=None)
    if result == "PASS":
        safe_emit(root, "review.passed", "COMPLETED", plan_id=task.get("plan_id"), task_id=task_id, agent_id=reviewer, evidence_reference=ref, data={"reviewer": reviewer, "findings": findings})
    else:
        safe_emit(root, "review.failed", "FAILED", plan_id=task.get("plan_id"), task_id=task_id, agent_id=reviewer, evidence_reference=ref, data={"reviewer": reviewer, "findings": findings})
    if result == "FAIL" and task["fix_round"] >= 3:
        stage_block(root, task, "review failed after third fix")
    else:
        write(p, task)
    print(f"{result}: {ref}")


def qa(root, task_id, result, report, tester):
    p, task = active_task(root, task_id)
    current_verification(root, task)
    review_ref = task.get("review_evidence")
    if not review_ref or read(root / review_ref)["status"] != "PASS" or read(root / review_ref)["revision"] != snapshot(root):
        fail("current passing code review required before QA")
    if tester != "qa_tester" or result not in ("PASS", "FAIL"):
        fail("qa_tester and PASS or FAIL result required")
    report_path = (report if report.is_absolute() else root / report).resolve()
    evidence_dir = (root / ".verified-development-loop" / "evidence" / task_id).resolve()
    if report_path.parent != evidence_dir or report_path.suffix != ".md" or not report_path.is_file():
        fail("QA report must be a Markdown file in this task's evidence directory")
    report_text = report_path.read_text(encoding="utf-8")
    if not report_text.strip() or "## Regression Results" not in report_text or "## Scenario Results" not in report_text:
        fail("QA report requires regression and scenario results")
    if f"**Overall Result:** {result}" not in report_text:
        fail("QA report result disagrees with attestation")
    if any(scenario not in report_text for scenario in set(re.findall(r"\bQA-\d+\b", task["qa_plan"]))):
        fail("QA report must include every approved scenario")
    ref = evidence(root, "qa", task_id, {"revision": snapshot(root), "status": result, "tester": tester, "report": report_path.relative_to(root).as_posix(), "report_text": report_text, "verification_evidence": task["verification_evidence"], "review_evidence": review_ref})
    task["qa_evidence"] = ref
    if result == "FAIL":
        task.setdefault("qa_failures", []).append(ref)
    write(p, task)
    safe_emit(root, "qa.completed", "COMPLETED" if result == "PASS" else "FAILED", plan_id=task.get("plan_id"), task_id=task_id, agent_id=tester, evidence_reference=ref, data={"result": result})
    print(f"{result}: {ref}")


def record_error(root, task_id, error_id, description, detection, root_cause, classification=None, severity=None):
    _, task = active_task(root, task_id, allow_pending=True)
    p = root / ".verified-development-loop" / "errors" / (identifier(error_id) + ".md")
    if p.exists() or not description.strip() or not detection.strip():
        fail("new error ID, description, and detection evidence required")
    ref = task.get("qa_evidence") or task.get("review_evidence") or task.get("verification_evidence")
    if not ref or read(root / ref)["status"] not in ("FAIL", "UNVERIFIED"):
        fail("current failed verification, review, or QA evidence required")
    if task.get("qa_evidence") and classification not in ("code", "spec", "environment", "uncertain"):
        fail("QA error classification required")
    if severity is not None and severity not in ("blocker", "serious", "minor"):
        fail("severity must be blocker, serious, or minor")
    safe_emit(root, "error.recording", "RUNNING", plan_id=task.get("plan_id"), task_id=task_id, data={"error_id": error_id})
    write(p, {"error_id": error_id, "task_id": task_id, "plan_id": task["plan_id"], "description": description, "root_cause": root_cause or None, "classification": classification, "severity": severity, "detection_evidence": detection, "fix_attempts": 0, "recurrences": 0, "attempts": [], "verification_logs": [task["verification_evidence"]] if task.get("verification_evidence") else [], "review_findings": [task["review_evidence"]] if task.get("review_evidence") else [], "qa_findings": [task["qa_evidence"]] if task.get("qa_evidence") else [], "status": "OPEN", "prevention_lesson": None})
    safe_emit(root, "error.recorded", "COMPLETED", plan_id=task.get("plan_id"), task_id=task_id, data={"error_id": error_id, "description": description, "detection": detection, "root_cause": root_cause})
    if classification in ("spec", "uncertain") or (classification == "code" and task["fix_round"] >= 3):
        stage_block(root, task, "QA requires human decision" if classification != "code" else "QA code failure after third fix")


def set_error_severity(root, task_id, error_id, severity):
    if severity not in ("blocker", "serious", "minor"):
        fail("severity must be blocker, serious, or minor")
    task = read(path(root, "tasks", "active", task_id))
    if task["status"] not in ("active", "blocked") or not path(root, "plans", "active", task["plan_id"]).exists():
        fail("active or blocked task in an approved Plan required")
    error_path = root / ".verified-development-loop" / "errors" / (identifier(error_id) + ".md")
    error = read(error_path)
    if error["task_id"] != task_id or error["status"] not in ("OPEN", "BLOCKED"):
        fail("unresolved error for this task required")
    error["severity"] = severity
    write(error_path, error)


def start_fix(root, task_id, error_id, approach):
    p, task = active_task(root, task_id)
    error_path = root / ".verified-development-loop" / "errors" / (identifier(error_id) + ".md")
    error = read(error_path)
    if error["task_id"] != task_id or error["status"] != "OPEN" or error.get("classification") in ("spec", "environment", "uncertain") or not approach.strip():
        fail("open task error and concrete fix approach required")
    if any(read(e)["task_id"] == task_id and read(e)["attempts"] and read(e)["attempts"][-1]["result"] == "pending" for e in (root / ".verified-development-loop" / "errors").glob("*.md")):
        fail("evaluate the current fix before another fix round")
    if task["fix_round"] >= 3:
        fail("three fix rounds exhausted")
    task["fix_round"] += 1
    task.update(verification_evidence=None, review_evidence=None, qa_evidence=None, acceptance_evidence=None)
    error["fix_attempts"] += 1
    error["attempts"].append({"round": task["fix_round"], "approach": approach, "time": stamp(), "result": "pending"})
    write(error_path, error)
    write(p, task)
    safe_emit(root, "fix.started", "RUNNING", plan_id=task.get("plan_id"), task_id=task_id, attempt=task["fix_round"], data={"error_id": error_id, "approach": approach})


def join_fix(root, task_id, error_id, approach):
    _, task = active_task(root, task_id)
    if not approach.strip() or not task["fix_round"] or task.get("verification_evidence") or task.get("review_evidence"):
        fail("join requires an unverified fix round and concrete approach")
    pending = any(
        read(p).get("task_id") == task_id
        and read(p).get("attempts")
        and read(p)["attempts"][-1]["result"] == "pending"
        and read(p)["attempts"][-1]["round"] == task["fix_round"]
        for p in (root / ".verified-development-loop" / "errors").glob("*.md")
    )
    if not pending:
        fail("current pending fix round required")
    error_path = root / ".verified-development-loop" / "errors" / (identifier(error_id) + ".md")
    error = read(error_path)
    if error["task_id"] != task_id or error["status"] != "OPEN" or (error["attempts"] and error["attempts"][-1]["result"] == "pending"):
        fail("distinct open task error required")
    error["fix_attempts"] += 1
    error["attempts"].append({"round": task["fix_round"], "approach": approach, "time": stamp(), "result": "pending"})
    write(error_path, error)
    safe_emit(root, "fix.joined", "RUNNING", plan_id=task.get("plan_id"), task_id=task_id, attempt=task["fix_round"], data={"error_id": error_id, "approach": approach})


def evaluate(root, task_id, error_id, result, evidence_note, lesson):
    _, task = active_task(root, task_id)
    error_path = root / ".verified-development-loop" / "errors" / (identifier(error_id) + ".md")
    error = read(error_path)
    environment_retry = error.get("classification") == "environment" and not error["attempts"] and result in ("resolved", "persists")
    if error["task_id"] != task_id or (not environment_retry and (not error["attempts"] or error["attempts"][-1]["result"] != "pending")):
        fail("pending fix for this task required")
    if not evidence_note.strip():
        fail("post-fix evidence required")
    qa_error = bool(error.get("qa_findings"))
    ref = (task.get("qa_evidence") if qa_error else None) or task.get("review_evidence") or task.get("verification_evidence")
    if not ref:
        fail("post-fix verification, review, or QA required")
    observed = read(root / ref)["status"]
    if result == "resolved":
        if qa_error and (not task.get("qa_evidence") or observed != "PASS" or read(root / ref)["revision"] != snapshot(root)):
            fail("QA error resolution requires current passing QA")
        review_ref = task.get("review_evidence")
        if not review_ref:
            fail("resolution requires current code review")
        current_verification(root, task)
        review_data = read(root / review_ref)
        if review_data["revision"] != snapshot(root):
            fail("resolution requires review of current code")
        if review_data["status"] == "FAIL":
            other_ids = {
                item["error_id"]
                for p in (root / ".verified-development-loop" / "errors").glob("*.md")
                if (item := read(p))["task_id"] == task_id
                and item["error_id"] != error_id
                and item["status"] == "OPEN"
                and review_ref in item["review_findings"]
            }
            if not other_ids or any(not finding.split() or finding.split()[0] not in other_ids for finding in review_data["findings"]):
                fail("failed review must identify only distinct recorded errors")
        elif review_data["status"] != "PASS":
            fail("resolution requires completed code review")
        error["status"] = "RESOLVED"
        error["prevention_lesson"] = lesson or None
        safe_emit(root, "fix.completed", "COMPLETED", plan_id=task.get("plan_id"), task_id=task_id, attempt=task.get("fix_round"), data={"error_id": error_id, "lesson": lesson, "evidence": evidence_note})
    elif result == "persists":
        if observed != "FAIL":
            fail("recurrence requires failed verification, review, or QA")
        error["recurrences"] += 1
        if not environment_retry and task["fix_round"] >= 3:
            error["status"] = "BLOCKED"
        safe_emit(root, "error.recurred", "BLOCKED" if error["status"] == "BLOCKED" else "FAILED", plan_id=task.get("plan_id"), task_id=task_id, attempt=task.get("fix_round"), data={"error_id": error_id, "recurrences": error["recurrences"], "evidence": evidence_note})
    else:
        fail("result must be resolved or persists")
    if not environment_retry:
        error["attempts"][-1]["result"] = result
        error["attempts"][-1]["evidence"] = evidence_note
        error["attempts"][-1]["verification"] = task.get("verification_evidence")
        error["attempts"][-1]["review"] = task.get("review_evidence")
        error["attempts"][-1]["qa"] = task.get("qa_evidence")
    if task.get("verification_evidence"):
        error["verification_logs"].append(task["verification_evidence"])
    if task.get("review_evidence"):
        error["review_findings"].append(task["review_evidence"])
    if task.get("qa_evidence"):
        error.setdefault("qa_findings", []).append(task["qa_evidence"])
    write(error_path, error)
    if result == "persists" and error["status"] == "BLOCKED":
        stage_block(root, task, "same confirmed error persisted after third fix")


def complete_task(root, task_id, acceptance):
    p, task = active_task(root, task_id)
    require_diagnosis(root, task)
    current_verification(root, task)
    ref = task.get("review_evidence")
    if not ref or read(root / ref)["status"] != "PASS" or read(root / ref)["revision"] != snapshot(root):
        fail("current passing code review required")
    qa_ref = task.get("qa_evidence")
    if not qa_ref or read(root / qa_ref)["status"] != "PASS" or read(root / qa_ref)["revision"] != snapshot(root) or read(root / qa_ref)["review_evidence"] != ref:
        fail("current passing QA evidence required")
    if set(acceptance) != set(task["acceptance_criteria"]) or len(acceptance) != len(task["acceptance_criteria"]):
        fail("all task acceptance criteria must be explicitly attested")
    for error_path in (root / ".verified-development-loop" / "errors").glob("*.md") if (root / ".verified-development-loop" / "errors").exists() else []:
        error = read(error_path)
        if error["task_id"] == task_id and error["status"] != "RESOLVED":
            fail("unresolved task error")
    recorded_qa_failures = {
        ref
        for error_path in (root / ".verified-development-loop" / "errors").glob("*.md")
        if (error := read(error_path))["task_id"] == task_id
        for ref in error.get("qa_findings", [])
    }
    if not set(task.get("qa_failures", [])).issubset(recorded_qa_failures):
        fail("every failed QA run must be recorded in error memory")
    require_report(root, task, "completed")
    task["acceptance_evidence"] = evidence(root, "acceptance", task_id, {"revision": snapshot(root), "criteria": acceptance, "verification": task["verification_evidence"], "review": ref, "qa": qa_ref})
    task["status"] = "completed"
    target = path(root, "tasks", "completed", task_id)
    write(target, task)
    p.unlink()
    safe_emit(root, "task.completed", "COMPLETED", plan_id=task.get("plan_id"), task_id=task_id, evidence_reference=task["acceptance_evidence"], data={"criteria": acceptance})


def complete_task_accepted(root, task_id, acceptance, error_ids, accepted_by, accepted_on):
    p = path(root, "tasks", "active", task_id)
    task = read(p)
    if task["status"] not in ("active", "blocked"):
        fail("active or blocked task required")
    plan_path = path(root, "plans", "active", task["plan_id"])
    if not plan_path.exists() or read(plan_path)["status"] != "active":
        fail("approved active plan required")
    if not accepted_by.strip() or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", accepted_on):
        fail("human name and acceptance date required")
    try:
        datetime.strptime(accepted_on, "%Y-%m-%d")
    except ValueError:
        fail("acceptance date must be a real YYYY-MM-DD date")
    if not error_ids or len(error_ids) != len(set(error_ids)):
        fail("distinct accepted error IDs required")
    require_diagnosis(root, task)
    current_verification(root, task)
    review_ref = task.get("review_evidence")
    qa_ref = task.get("qa_evidence")
    if not review_ref or read(root / review_ref)["status"] != "PASS" or read(root / review_ref)["revision"] != snapshot(root):
        fail("current passing code review required")
    if not qa_ref or read(root / qa_ref)["revision"] != snapshot(root) or read(root / qa_ref)["review_evidence"] != review_ref:
        fail("current QA evidence required")
    if set(acceptance) != set(task["acceptance_criteria"]) or len(acceptance) != len(task["acceptance_criteria"]):
        fail("all task acceptance criteria must be explicitly attested")
    errors = [read(error_path) for error_path in (root / ".verified-development-loop" / "errors").glob("*.md")]
    unresolved = {error["error_id"]: error for error in errors if error["task_id"] == task_id and error["status"] != "RESOLVED"}
    if set(error_ids) != set(unresolved):
        fail("accepted error IDs must match every unresolved task error")
    for error in unresolved.values():
        if error.get("severity") not in ("serious", "minor"):
            fail("Blocker or unclassified error cannot be accepted")
        if qa_ref not in error.get("qa_findings", []):
            fail("accepted error requires current QA finding")
    recorded_qa_failures = {ref for error in errors if error["task_id"] == task_id for ref in error.get("qa_findings", [])}
    if not set(task.get("qa_failures", [])).issubset(recorded_qa_failures):
        fail("every failed QA run must be recorded in error memory")
    require_report(root, task, "completed-accepted")
    report_text = (root / task["latest_report"]).read_text(encoding="utf-8")
    if accepted_by not in report_text or accepted_on not in report_text or any(error_id not in report_text for error_id in error_ids):
        fail("accepted report must name each error, human, and date")
    task["acceptance_evidence"] = evidence(root, "acceptance", task_id, {"revision": snapshot(root), "criteria": acceptance,
        "verification": task["verification_evidence"], "review": review_ref, "qa": qa_ref,
        "accepted_errors": error_ids, "accepted_by": accepted_by, "accepted_on": accepted_on})
    task.update(status="completed", completion_kind="accepted_errors", accepted_errors=error_ids,
                accepted_by=accepted_by, accepted_on=accepted_on)
    task.pop("pending_block_reason", None)
    target = path(root, "tasks", "completed", task_id)
    write(target, task)
    p.unlink()
    plan = read(plan_path)
    if not any((other_task := read(other))["status"] == "blocked" and other_task["plan_id"] == task["plan_id"]
               for other in (root / ".verified-development-loop" / "tasks" / "active").glob("*.md")):
        plan["execution_state"] = "running"
        write(plan_path, plan)
    safe_emit(root, "task.completed", "COMPLETED", plan_id=task["plan_id"], task_id=task_id,
              evidence_reference=task["acceptance_evidence"], data={"criteria": acceptance, "accepted_errors": error_ids})


def complete_plan(root, plan_id, acceptance, accepted=False):
    p = path(root, "plans", "active", plan_id)
    plan = read(p)
    diagnosis = require_diagnosis(root, plan)
    spec_path = path(root, "specs", "active", plan_id)
    if plan["status"] != "active" or plan["execution_state"] == "waiting_human":
        fail("plan is not running")
    if not spec_path.exists() or plan.get("spec_file") != spec_path.relative_to(root).as_posix():
        fail("matching active Spec required")
    if set(acceptance) != set(plan["acceptance_criteria"]) or len(acceptance) != len(plan["acceptance_criteria"]):
        fail("all plan acceptance criteria must be explicitly attested")
    for item in plan["tasks"]:
        tid = item["task_id"]
        if not path(root, "tasks", "completed", tid).exists() or path(root, "tasks", "active", tid).exists():
            fail("all plan tasks must be completed")
        completed_task = read(path(root, "tasks", "completed", tid))
        report_status = "completed-accepted" if completed_task.get("completion_kind") == "accepted_errors" else "completed"
        require_report(root, completed_task, report_status)
    task_records = [read(path(root, "tasks", "completed", item["task_id"])) for item in plan["tasks"]]
    accepted_ids = {error_id for task in task_records for error_id in task.get("accepted_errors", [])}
    if accepted != bool(accepted_ids):
        fail("use the matching normal or accepted Plan completion")
    for error_path in (root / ".verified-development-loop" / "errors").glob("*.md") if (root / ".verified-development-loop" / "errors").exists() else []:
        error = read(error_path)
        if error["plan_id"] == plan_id and error["status"] != "RESOLVED" and error["error_id"] not in accepted_ids:
            fail("unresolved plan error")
    if diagnosis:
        error_path = root / ".verified-development-loop" / "errors" / (identifier(plan["error_id"]) + ".md")
        if error_path.exists():
            previous = read(error_path)
            if previous["plan_id"] != plan_id or previous["status"] != "RESOLVED":
                fail("diagnosed error ID already exists")
            previous["root_cause"] = diagnosis["root_cause"]
            previous["detection_evidence"] = plan["diagnosis_evidence"]
            write(error_path, previous)
        else:
            tasks = [read(path(root, "tasks", "completed", item["task_id"])) for item in plan["tasks"]]
            write(error_path, {"error_id": plan["error_id"], "task_id": tasks[0]["task_id"], "plan_id": plan_id,
                "description": "Original bug reproduced in investigator report", "root_cause": diagnosis["root_cause"],
                "classification": "code", "detection_evidence": plan["diagnosis_evidence"],
                "fix_attempts": 1, "recurrences": 0,
                "attempts": [{"round": 1, "approach": plan["fix_approach"], "time": stamp(), "result": "resolved",
                              "evidence": ", ".join(task["acceptance_evidence"] for task in tasks)}],
                "verification_logs": [task["verification_evidence"] for task in tasks],
                "review_findings": [task["review_evidence"] for task in tasks],
                "qa_findings": [task["qa_evidence"] for task in tasks],
                "status": "RESOLVED", "prevention_lesson": None})
    plan.update(status="completed", execution_state="completed", acceptance_evidence={"criteria": acceptance, "time": stamp()})
    spec = read(spec_path)
    spec["status"] = "completed"
    write(path(root, "specs", "completed", plan_id), spec)
    spec_path.unlink()
    plan["spec_file"] = f".verified-development-loop/specs/completed/{plan_id}.md"
    write(path(root, "plans", "completed", plan_id), plan)
    p.unlink()
    safe_emit(root, "plan.completed", "COMPLETED", plan_id=plan_id, data={"criteria": acceptance})


def block_task(root, task_id, reason):
    task = read(path(root, "tasks", "active", task_id))
    if task["status"] != "active":
        fail("active task required")
    if not reason.strip():
        fail("blocking reason required")
    if task.get("pending_block_reason") and task["pending_block_reason"] != reason:
        fail("blocking reason disagrees with pending blocker")
    if not task.get("pending_block_reason"):
        stage_block(root, task, reason)
    block(root, task, reason)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="action", required=True)
    definitions = {
        "propose": ["--input"], "approve": ["--plan-id", "--human-approval"],
        "record-diagnosis": ["--plan-id", "--report", "--result", "--classification", "--confidence"],
        "verify": ["--task-id"], "review": ["--task-id", "--result", "--reviewer"],
        "qa": ["--task-id", "--result", "--report", "--tester"],
        "record-error": ["--task-id", "--error-id", "--description", "--detection"],
        "set-error-severity": ["--task-id", "--error-id"],
        "start-fix": ["--task-id", "--error-id", "--approach"],
        "join-fix": ["--task-id", "--error-id", "--approach"],
        "evaluate": ["--task-id", "--error-id", "--result", "--evidence"],
        "complete-task": ["--task-id"], "complete-plan": ["--plan-id"],
        "complete-task-accepted": ["--task-id", "--accepted-by", "--accepted-on"],
        "complete-plan-accepted": ["--plan-id"],
        "block-task": ["--task-id", "--reason"],
        "write-report": ["--task-id", "--status", "--input"],
        "emit": ["--event"],
    }
    for name, required in definitions.items():
        cmd = sub.add_parser(name)
        for flag in required:
            cmd.add_argument(flag, required=True)
        if name == "review":
            cmd.add_argument("--finding", action="append", default=[])
        if name == "record-error":
            cmd.add_argument("--root-cause")
            cmd.add_argument("--classification", choices=("code", "spec", "environment", "uncertain"))
            cmd.add_argument("--severity", choices=("blocker", "serious", "minor"))
        if name == "set-error-severity":
            cmd.add_argument("--severity", choices=("blocker", "serious", "minor"), required=True)
        if name == "evaluate":
            cmd.add_argument("--lesson")
        if name in ("complete-task", "complete-plan", "complete-task-accepted", "complete-plan-accepted"):
            cmd.add_argument("--accept", action="append", required=True)
        if name == "complete-task-accepted":
            cmd.add_argument("--accepted-error", action="append", required=True)
        if name == "emit":
            cmd.add_argument("--status", default="COMPLETED")
            cmd.add_argument("--plan-id")
            cmd.add_argument("--task-id")
            cmd.add_argument("--agent-id")
            cmd.add_argument("--attempt", type=int)
            cmd.add_argument("--evidence")
            cmd.add_argument("--data")
            cmd.add_argument("--source", default="agent")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.action == "propose": propose(root, Path(args.input))
        elif args.action == "record-diagnosis":
            print(record_diagnosis(root, args.plan_id, Path(args.report), args.result, args.classification, args.confidence))
        elif args.action == "approve": approve(root, args.plan_id, args.human_approval)
        elif args.action == "verify": return 0 if verify(root, args.task_id) else 1
        elif args.action == "review": review(root, args.task_id, args.result, args.finding, args.reviewer)
        elif args.action == "qa": qa(root, args.task_id, args.result, Path(args.report), args.tester)
        elif args.action == "record-error": record_error(root, args.task_id, args.error_id, args.description, args.detection, args.root_cause, args.classification, args.severity)
        elif args.action == "set-error-severity": set_error_severity(root, args.task_id, args.error_id, args.severity)
        elif args.action == "start-fix": start_fix(root, args.task_id, args.error_id, args.approach)
        elif args.action == "join-fix": join_fix(root, args.task_id, args.error_id, args.approach)
        elif args.action == "evaluate": evaluate(root, args.task_id, args.error_id, args.result, args.evidence, args.lesson)
        elif args.action == "complete-task": complete_task(root, args.task_id, args.accept)
        elif args.action == "complete-plan": complete_plan(root, args.plan_id, args.accept)
        elif args.action == "complete-task-accepted": complete_task_accepted(root, args.task_id, args.accept, args.accepted_error, args.accepted_by, args.accepted_on)
        elif args.action == "complete-plan-accepted": complete_plan(root, args.plan_id, args.accept, accepted=True)
        elif args.action == "block-task": block_task(root, args.task_id, args.reason)
        elif args.action == "write-report": print(write_report(root, args.task_id, args.status, Path(args.input)))
        elif args.action == "emit":
            if args.event == "main_agent.reported":
                if not args.task_id:
                    fail("main_agent.reported requires task ID and saved report")
                task_file = next((p for state in ("active", "completed") if (p := path(root, "tasks", state, args.task_id)).exists()), None)
                if task_file is None:
                    fail("reported task does not exist")
                reported_task = read(task_file)
                if reported_task["status"] not in ("blocked", "completed"):
                    fail("task must finish before main_agent.reported")
                payload = json.loads(args.data) if args.data else {}
                expected = "blocked" if reported_task["status"] == "blocked" else "completed-accepted" if reported_task.get("completion_kind") == "accepted_errors" else "completed"
                require_report(root, reported_task, expected)
                if payload.get("report") != reported_task["latest_report"]:
                    fail("main_agent.reported must cite the saved latest report")
            if args.event == "tdd.started":
                plan_id = getattr(args, "plan_id", None)
                task_id = getattr(args, "task_id", None)
                plan_file = None
                if plan_id:
                    plan_file = next((p for state in ("active", "drafts") if (p := path(root, "plans", state, plan_id)).exists()), None)
                elif task_id and path(root, "tasks", "active", task_id).exists():
                    plan_id = read(path(root, "tasks", "active", task_id))["plan_id"]
                    plan_file = path(root, "plans", "active", plan_id)
                if plan_file and read(plan_file).get("mode") == "bug":
                    if plan_file.parent.name != "active" or not task_id:
                        fail("approved bug Plan and diagnosis required before TDD")
                    _, task = active_task(root, task_id)
                    if task["plan_id"] != plan_id:
                        fail("TDD task does not belong to bug Plan")
                    require_diagnosis(root, task)
            payload_data = json.loads(args.data) if getattr(args, "data", None) else {}
            ev = emit_event(
                root,
                args.event,
                status=getattr(args, "status", "COMPLETED"),
                source=args.source,
                plan_id=getattr(args, "plan_id", None),
                task_id=getattr(args, "task_id", None),
                agent_id=getattr(args, "agent_id", None),
                attempt=getattr(args, "attempt", None),
                evidence_reference=getattr(args, "evidence", None),
                data=payload_data,
            )
            print(f"EMITTED: {ev.event_id}")
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
