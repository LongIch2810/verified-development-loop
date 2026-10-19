"""Event Contract and State Reducer for VDL Real-Time Tracking (Python 3.11+)."""

import json
import os
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

try:
    from workflow_docs import read as read_workflow_doc
except ImportError:
    from .workflow_docs import read as read_workflow_doc

VALID_STATUSES = {
    "PENDING",
    "RUNNING",
    "COMPLETED",
    "FAILED",
    "BLOCKED",
    "WAITING_HUMAN",
    "UNKNOWN",
}

VALID_SOURCES = {"script", "hook", "skill", "agent", "system"}

WORKFLOW_STEPS = [
    {"id": "raw_prompt", "name": "Raw Prompt", "name_vn": "Yêu cầu Gốc", "order": 1},
    {"id": "read_errors", "name": "Read Errors", "name_vn": "Đọc Lỗi Cũ", "order": 2},
    {"id": "interview", "name": "Interview", "name_vn": "Phỏng Vấn Làm Rõ", "order": 3},
    {"id": "spec", "name": "Spec", "name_vn": "Đặc Tả (Spec)", "order": 4},
    {"id": "plan", "name": "Plan", "name_vn": "Kế Hoạch (Plan)", "order": 5},
    {"id": "human_approval", "name": "Human Approval", "name_vn": "Phê Duyệt Con Người", "order": 6},
    {"id": "active", "name": "Active Execution", "name_vn": "Thực Thi Nhiệm Vụ", "order": 7},
    {"id": "tdd", "name": "TDD Implementation", "name_vn": "Lập Trình TDD", "order": 8},
    {"id": "verification", "name": "Verification Gate", "name_vn": "Cổng Kiểm Thử Argv", "order": 9},
    {"id": "code_review", "name": "Code Review", "name_vn": "Review Độc Lập", "order": 10},
    {"id": "qa", "name": "QA Testing", "name_vn": "QA Sản Phẩm", "order": 11},
    {"id": "fix_loop", "name": "Fix Loop", "name_vn": "Vòng Sửa Lỗi Giới Hạn", "order": 12},
    {"id": "main_agent_report", "name": "Main Agent Report", "name_vn": "Báo Cáo Nghiệm Thu", "order": 13},
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def detect_project_id(root: Path) -> str:
    """Derive stable project ID from root folder or git config."""
    try:
        git_config = root / ".git" / "config"
        if git_config.exists():
            content = git_config.read_text(encoding="utf-8", errors="ignore")
            match = re.search(r'url\s*=\s*.+?[/:]([^/\s]+?)(?:\.git)?$', content, re.MULTILINE)
            if match:
                return match.group(1).strip()
    except Exception:
        pass
    return root.resolve().name or "vdl-project"


@dataclass
class VDLEvent:
    event_id: str
    project_id: str
    session_id: str
    event_type: str
    status: str
    source: str
    timestamp: str
    plan_id: Optional[str] = None
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    attempt: Optional[int] = None
    evidence_reference: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "VDLEvent":
        event_id = str(d.get("event_id") or uuid4().hex)
        status = str(d.get("status", "UNKNOWN")).upper()
        if status not in VALID_STATUSES:
            status = "UNKNOWN"
        source = str(d.get("source", "script"))
        if source not in VALID_SOURCES:
            source = "script"
        return cls(
            event_id=event_id,
            project_id=str(d.get("project_id", "default")),
            session_id=str(d.get("session_id", "default")),
            event_type=str(d.get("event_type", "unknown")),
            status=status,
            source=source,
            timestamp=str(d.get("timestamp") or utc_now()),
            plan_id=d.get("plan_id"),
            task_id=d.get("task_id"),
            agent_id=d.get("agent_id"),
            attempt=int(d["attempt"]) if d.get("attempt") is not None else None,
            evidence_reference=d.get("evidence_reference"),
            data=dict(d.get("data") or {}),
        )


class EventStore:
    """Append-only local event store backed by .vdl/events.jsonl."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.vdl_dir = self.root / ".vdl"
        self.events_file = self.vdl_dir / "events.jsonl"
        self._lock = threading.Lock()

    def _ensure_dir(self):
        self.vdl_dir.mkdir(parents=True, exist_ok=True)
        gitignore = self.vdl_dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("*\n", encoding="utf-8")

    def append(self, event: VDLEvent) -> VDLEvent:
        self._ensure_dir()
        with self._lock:
            # Check for duplicate event_id
            if self.events_file.exists():
                with open(self.events_file, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                item = json.loads(line)
                                if item.get("event_id") == event.event_id:
                                    return event  # already recorded
                            except json.JSONDecodeError:
                                continue

            with open(self.events_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        return event

    def read_all(self, session_id: Optional[str] = None) -> List[VDLEvent]:
        if not self.events_file.exists():
            return []
        events = []
        with self._lock:
            with open(self.events_file, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        ev = VDLEvent.from_dict(d)
                        if session_id and ev.session_id != session_id:
                            continue
                        events.append(ev)
                    except Exception:
                        continue
        return events

    def get_events_since(self, since_event_id: Optional[str] = None) -> List[VDLEvent]:
        all_events = self.read_all()
        if not since_event_id:
            return all_events
        found = False
        res = []
        for ev in all_events:
            if found:
                res.append(ev)
            elif ev.event_id == since_event_id:
                found = True
        return res if found else all_events


def notify_server(event: VDLEvent, port: int = 4040, timeout: float = 0.2):
    """Optional fast notification to local Control Center server."""
    try:
        url = f"http://127.0.0.1:{port}/api/events"
        req = urllib.request.Request(
            url,
            data=json.dumps(event.to_dict()).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout):
            pass
    except Exception:
        # Server not running or unreachable; event is still safely in local store
        pass


def emit_event(
    root: Path,
    event_type: str,
    status: str = "COMPLETED",
    source: str = "script",
    session_id: Optional[str] = None,
    plan_id: Optional[str] = None,
    task_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    attempt: Optional[int] = None,
    evidence_reference: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    notify: bool = True,
) -> VDLEvent:
    root = root.resolve()
    project_id = detect_project_id(root)
    session_id = session_id or os.environ.get("VDL_SESSION_ID") or "default"

    # Contextual inference from active plan/task on disk if not supplied
    if not plan_id or not task_id:
        active_plans = list((root / ".verified-development-loop" / "plans" / "active").glob("*.md")) if (root / ".verified-development-loop" / "plans" / "active").exists() else []
        if active_plans and not plan_id:
            plan_id = active_plans[0].stem
        active_tasks = list((root / ".verified-development-loop" / "tasks" / "active").glob("*.md")) if (root / ".verified-development-loop" / "tasks" / "active").exists() else []
        if active_tasks and not task_id:
            task_id = active_tasks[0].stem

    event = VDLEvent(
        event_id=uuid4().hex,
        project_id=project_id,
        session_id=session_id,
        event_type=event_type,
        status=status.upper(),
        source=source,
        timestamp=utc_now(),
        plan_id=plan_id,
        task_id=task_id,
        agent_id=agent_id,
        attempt=attempt,
        evidence_reference=evidence_reference,
        data=data or {},
    )

    store = EventStore(root)
    store.append(event)
    if notify:
        notify_server(event)
    return event


class WorkflowStateReducer:
    """Folds event streams and ground-truth repository files into real-time UI state."""

    @staticmethod
    def reduce(root: Path, events: List[VDLEvent]) -> Dict[str, Any]:
        root = root.resolve()
        project_id = detect_project_id(root)
        valid_events = [ev for ev in events if not ev.project_id or ev.project_id in (project_id, "default")]
        start = max((i for i, ev in enumerate(valid_events) if ev.event_type == "raw_prompt.received"), default=0)
        current_events = valid_events[start:]
        bug_mode = any(ev.event_type.startswith("diagnosis.") or
                       (ev.event_type == "raw_prompt.received" and ev.data.get("mode") == "bug")
                       for ev in current_events)

        # Base steps structure
        steps: Dict[str, Dict[str, Any]] = {}
        for s in WORKFLOW_STEPS:
            steps[s["id"]] = {
                "id": s["id"],
                "name": s["name"],
                "order": s["order"],
                "status": "PENDING",
                "summary": "Awaiting previous steps",
                "details": {},
                "timestamp": None,
                "evidence_reference": None,
            }
        if bug_mode:
            steps["diagnosis"] = {"id": "diagnosis", "name": "Diagnosis", "order": 3,
                "status": "PENDING", "summary": "Awaiting diagnosis", "details": {},
                "timestamp": None, "evidence_reference": None}

        # Track state containers
        active_plan_id: Optional[str] = None
        active_task_id: Optional[str] = None
        session_id: str = "default"
        current_step_id: str = ""
        verification_details: Dict[str, Any] = {}
        review_details: Dict[str, Any] = {}
        fix_loop_details: Dict[str, Any] = {
            "attempts": 0,
            "max_attempts": 3,
            "status": "PENDING",
            "history": [],
            "current_approach": None,
            "error_id": None,
        }
        blocked_details: Dict[str, Any] = {
            "is_blocked": False,
            "reason": None,
            "evidence": None,
            "task_id": None,
        }
        report_details: Dict[str, Any] = {"summary": None, "criteria": []}

        # 1. Fold events sequentially
        for ev in valid_events:
            session_id = ev.session_id or session_id
            if ev.plan_id:
                active_plan_id = ev.plan_id
            if ev.task_id:
                active_task_id = ev.task_id

            etype = ev.event_type

            # Raw prompt
            if etype in ("raw_prompt.received", "workflow.started"):
                steps["raw_prompt"]["status"] = "COMPLETED"
                steps["raw_prompt"]["summary"] = ev.data.get("prompt_preview") or "User prompt received"
                steps["raw_prompt"]["timestamp"] = ev.timestamp
                if current_step_id in ("", "raw_prompt", "read_errors"):
                    current_step_id = "read_errors"

            # Read errors
            elif etype == "read_errors.started":
                steps["read_errors"]["status"] = "RUNNING"
                steps["read_errors"]["summary"] = "Checking relevant error history in .verified-development-loop/errors/"
                steps["read_errors"]["timestamp"] = ev.timestamp
                current_step_id = "read_errors"
            elif etype == "read_errors.completed":
                steps["read_errors"]["status"] = "COMPLETED"
                count = ev.data.get("error_count", 0)
                steps["read_errors"]["summary"] = f"Checked error memory ({count} relevant prior errors)"
                steps["read_errors"]["details"] = ev.data
                steps["read_errors"]["timestamp"] = ev.timestamp
                current_step_id = "diagnosis" if bug_mode else "interview"

            elif etype == "diagnosis.started" and bug_mode:
                steps["diagnosis"]["status"] = "RUNNING"
                steps["diagnosis"]["summary"] = "Investigator reproducing and diagnosing the bug"
                steps["diagnosis"]["timestamp"] = ev.timestamp
                current_step_id = "diagnosis"
            elif etype == "diagnosis.completed" and bug_mode:
                steps["diagnosis"]["status"] = ev.status
                steps["diagnosis"]["summary"] = f"Diagnosis: {ev.data.get('result', 'unknown')}"
                steps["diagnosis"]["details"] = ev.data
                steps["diagnosis"]["timestamp"] = ev.timestamp
                steps["diagnosis"]["evidence_reference"] = ev.evidence_reference
                current_step_id = "spec" if ev.status == "COMPLETED" and ev.data.get("classification") == "code" and ev.data.get("confidence") in ("high", "medium") else "diagnosis"

            # Interview
            elif etype == "interview.started":
                steps["interview"]["status"] = "RUNNING"
                steps["interview"]["summary"] = "Clarifying requirements, constraints, and verification with human"
                steps["interview"]["timestamp"] = ev.timestamp
                current_step_id = "interview"
            elif etype == "interview.completed":
                steps["interview"]["status"] = "COMPLETED"
                steps["interview"]["summary"] = "Interview completed and requirements confirmed"
                steps["interview"]["details"] = ev.data
                steps["interview"]["timestamp"] = ev.timestamp
                current_step_id = "spec"

            # Spec
            elif etype == "spec.started":
                steps["spec"]["status"] = "RUNNING"
                steps["spec"]["summary"] = "Planning agent generating specification"
                steps["spec"]["timestamp"] = ev.timestamp
                current_step_id = "spec"
            elif etype == "spec.completed":
                steps["spec"]["status"] = "COMPLETED"
                steps["spec"]["summary"] = "Spec created with observable acceptance criteria"
                steps["spec"]["details"] = ev.data
                steps["spec"]["timestamp"] = ev.timestamp
                current_step_id = "plan"

            # Plan
            elif etype == "plan.started":
                steps["plan"]["status"] = "RUNNING"
                steps["plan"]["summary"] = "Planning agent organizing task dependencies & verification"
                steps["plan"]["timestamp"] = ev.timestamp
                current_step_id = "plan"
            elif etype == "plan.completed" and "criteria" not in ev.data:
                steps["plan"]["status"] = "COMPLETED"
                steps["plan"]["summary"] = f"Plan draft prepared (ID: {ev.plan_id})"
                steps["plan"]["details"] = ev.data
                steps["plan"]["timestamp"] = ev.timestamp
                current_step_id = "human_approval"

            # Human Approval
            elif etype == "approval.waiting":
                steps["human_approval"]["status"] = "WAITING_HUMAN"
                steps["human_approval"]["summary"] = "Awaiting explicit human approval for Spec and Plan"
                steps["human_approval"]["timestamp"] = ev.timestamp
                current_step_id = "human_approval"
            elif etype == "approval.approved":
                steps["human_approval"]["status"] = "COMPLETED"
                steps["human_approval"]["summary"] = f"Plan approved by human: {ev.data.get('human_approval', 'Approved')}"
                steps["human_approval"]["timestamp"] = ev.timestamp
                steps["active"]["status"] = "RUNNING"
                steps["active"]["summary"] = f"Active plan: {ev.plan_id}"
                current_step_id = "active"

            # Active / Task
            elif etype == "task.started":
                steps["active"]["status"] = "RUNNING"
                steps["active"]["summary"] = f"Task in progress: {ev.task_id}"
                steps["active"]["timestamp"] = ev.timestamp
                active_task_id = ev.task_id
                steps["qa"]["status"] = "PENDING"
                current_step_id = "active"

            # TDD
            elif etype == "tdd.started":
                steps["tdd"]["status"] = "RUNNING"
                steps["tdd"]["summary"] = f"tdd_coder executing red, green, refactor for {ev.task_id}"
                steps["tdd"]["timestamp"] = ev.timestamp
                current_step_id = "tdd"
            elif etype == "tdd.completed":
                steps["tdd"]["status"] = "COMPLETED"
                steps["tdd"]["summary"] = f"tdd_coder finished changes for {ev.task_id}"
                steps["tdd"]["details"] = ev.data
                steps["tdd"]["timestamp"] = ev.timestamp
                current_step_id = "verification"

            # Verification
            elif etype == "verification.started":
                steps["verification"]["status"] = "RUNNING"
                steps["verification"]["summary"] = f"Running verification commands for {ev.task_id}"
                steps["verification"]["timestamp"] = ev.timestamp
                current_step_id = "verification"
            elif etype == "verification.passed":
                steps["verification"]["status"] = "COMPLETED"
                steps["verification"]["summary"] = "All verification commands PASSED against code fingerprint"
                steps["verification"]["evidence_reference"] = ev.evidence_reference
                steps["verification"]["timestamp"] = ev.timestamp
                verification_details = {
                    "status": "PASS",
                    "evidence": ev.evidence_reference,
                    "commands": ev.data.get("commands", []),
                    "revision": ev.data.get("revision"),
                }
                steps["verification"]["details"] = verification_details
                current_step_id = "code_review"
            elif etype in ("verification.failed", "verification.unverified"):
                vstatus = "UNVERIFIED" if etype == "verification.unverified" else "FAILED"
                steps["verification"]["status"] = vstatus
                steps["verification"]["summary"] = f"Verification {vstatus} on commands"
                steps["verification"]["evidence_reference"] = ev.evidence_reference
                steps["verification"]["timestamp"] = ev.timestamp
                verification_details = {
                    "status": vstatus,
                    "evidence": ev.evidence_reference,
                    "commands": ev.data.get("commands", []),
                    "revision": ev.data.get("revision"),
                }
                steps["verification"]["details"] = verification_details
                current_step_id = "fix_loop"

            # Code Review
            elif etype == "review.started":
                steps["qa"]["status"] = "PENDING"
                steps["code_review"]["status"] = "RUNNING"
                steps["code_review"]["summary"] = "Independent code_reviewer inspecting diff and spec"
                steps["code_review"]["timestamp"] = ev.timestamp
                current_step_id = "code_review"
            elif etype == "review.passed":
                steps["code_review"]["status"] = "COMPLETED"
                steps["code_review"]["summary"] = f"Review PASSED by {ev.data.get('reviewer', 'code_reviewer')} (0 findings)"
                steps["code_review"]["evidence_reference"] = ev.evidence_reference
                steps["code_review"]["timestamp"] = ev.timestamp
                review_details = {
                    "status": "PASS",
                    "reviewer": ev.data.get("reviewer", "code_reviewer"),
                    "findings": [],
                    "evidence": ev.evidence_reference,
                }
                steps["code_review"]["details"] = review_details
                current_step_id = "qa"
            elif etype == "review.failed":
                steps["code_review"]["status"] = "FAILED"
                findings = ev.data.get("findings", [])
                steps["code_review"]["summary"] = f"Review FAILED ({len(findings)} findings)"
                steps["code_review"]["evidence_reference"] = ev.evidence_reference
                steps["code_review"]["timestamp"] = ev.timestamp
                review_details = {
                    "status": "FAIL",
                    "reviewer": ev.data.get("reviewer", "code_reviewer"),
                    "findings": findings,
                    "evidence": ev.evidence_reference,
                }
                steps["code_review"]["details"] = review_details
                current_step_id = "fix_loop"

            # QA
            elif etype == "qa.started":
                steps["qa"]["status"] = "RUNNING"
                steps["qa"]["summary"] = f"qa_tester testing approved scenarios for {ev.task_id}"
                steps["qa"]["timestamp"] = ev.timestamp
                current_step_id = "qa"
            elif etype == "qa.completed":
                passed = ev.data.get("result") == "PASS" and ev.status == "COMPLETED"
                steps["qa"]["status"] = "COMPLETED" if passed else "FAILED"
                steps["qa"]["summary"] = f"QA {'PASS' if passed else 'FAIL'} for {ev.task_id}"
                steps["qa"]["evidence_reference"] = ev.evidence_reference
                steps["qa"]["details"] = ev.data
                steps["qa"]["timestamp"] = ev.timestamp
                current_step_id = "qa"

            # Error recording and Fix Loop
            elif etype == "error.recording":
                fix_loop_details["status"] = "RECORDING"
                current_step_id = "fix_loop"
            elif etype == "error.recorded":
                fix_loop_details["status"] = "RECORDED"
                current_step_id = "fix_loop"
            elif etype == "fix.started":
                steps["qa"]["status"] = "PENDING"
                attempt = ev.attempt or (fix_loop_details["attempts"] + 1)
                fix_loop_details["attempts"] = attempt
                fix_loop_details["status"] = "RUNNING"
                approach = ev.data.get("approach", "")
                fix_loop_details["current_approach"] = approach
                fix_loop_details["error_id"] = ev.data.get("error_id")
                fix_loop_details["history"].append({
                    "round": attempt,
                    "approach": approach,
                    "time": ev.timestamp,
                    "result": "pending",
                })
                steps["fix_loop"]["status"] = "RUNNING"
                steps["fix_loop"]["summary"] = f"Fix Round {attempt}/3 in progress: {approach[:60]}"
                steps["fix_loop"]["timestamp"] = ev.timestamp
                current_step_id = "fix_loop"
            elif etype == "fix.completed":
                fix_loop_details["status"] = "COMPLETED"
                if fix_loop_details["history"]:
                    fix_loop_details["history"][-1]["result"] = "resolved"
                steps["fix_loop"]["status"] = "COMPLETED"
                steps["fix_loop"]["summary"] = f"Error resolved on fix round {fix_loop_details['attempts']}/3"
                steps["fix_loop"]["timestamp"] = ev.timestamp
                current_step_id = "main_agent_report"
            elif etype == "error.recurred":
                fix_loop_details["status"] = "BLOCKED"
                if fix_loop_details["history"]:
                    fix_loop_details["history"][-1]["result"] = "persists"
                steps["fix_loop"]["status"] = "BLOCKED"
                steps["fix_loop"]["summary"] = f"Error recurred after fix round {fix_loop_details['attempts']}/3 (Blocked)"
                steps["fix_loop"]["timestamp"] = ev.timestamp
                current_step_id = "fix_loop"

            # Blocked Task
            elif etype == "task.blocked":
                reason = ev.data.get("reason", "Task blocked")
                blocked_details = {
                    "is_blocked": True,
                    "reason": reason,
                    "evidence": ev.evidence_reference,
                    "task_id": ev.task_id,
                }
                steps["active"]["status"] = "BLOCKED"
                steps["active"]["summary"] = f"BLOCKED: {reason}"
                steps["human_approval"]["status"] = "WAITING_HUMAN"
                steps["human_approval"]["summary"] = f"Waiting for human decision on blocked task: {reason}"
                current_step_id = "active"

            # Task completed
            elif etype == "task.completed":
                steps["active"]["status"] = "COMPLETED"
                steps["active"]["summary"] = f"Task {ev.task_id} completed"
                current_step_id = "main_agent_report"

            # Plan completed
            elif etype == "plan.completed":
                steps["active"]["status"] = "COMPLETED"
                steps["active"]["summary"] = f"All plan tasks completed ({ev.plan_id})"
                current_step_id = "main_agent_report"

            # Main agent report
            elif etype == "main_agent.started":
                steps["main_agent_report"]["status"] = "RUNNING"
                steps["main_agent_report"]["summary"] = "Main agent preparing the human report"
                steps["main_agent_report"]["timestamp"] = ev.timestamp
                current_step_id = "main_agent_report"
            elif etype == "main_agent.reported":
                steps["main_agent_report"]["status"] = "COMPLETED"
                steps["main_agent_report"]["summary"] = ev.data.get("summary") or "Report delivered to human"
                steps["main_agent_report"]["details"] = ev.data
                steps["main_agent_report"]["timestamp"] = ev.timestamp
                report_details = ev.data
                current_step_id = "main_agent_report"

        # 2. Ground-Truth Reconciliation with Repository Files
        WorkflowStateReducer._reconcile_with_disk(
            root,
            steps,
            fix_loop_details,
            blocked_details,
            verification_details,
            review_details,
            report_details,
        )


        # Check if workflow has started
        has_started = any(s["status"] != "PENDING" for s in steps.values()) or bool(valid_events)
        if not has_started:
            current_step_id = ""

        # 3. Mark current step and fallback unvisited steps
        step_list = [steps["diagnosis"] if bug_mode and s["id"] == "interview" else steps[s["id"]] for s in WORKFLOW_STEPS]

        # 4. Compute Dynamic Graph Model for visual loop tracking
        graph = WorkflowStateReducer.compute_graph_layout(
            steps=steps,
            current_step_id=current_step_id,
            verification=verification_details,
            review=review_details,
            fix_loop=fix_loop_details,
            blocked=blocked_details,
        )

        return {
            "project_id": project_id,
            "project_root": str(root),
            "mode": "bug" if bug_mode else ("feature" if current_step_id else None),
            "session_id": session_id,
            "active_plan_id": active_plan_id,
            "active_task_id": active_task_id,
            "current_step_id": current_step_id,
            "steps": step_list,
            "graph": graph,
            "verification": verification_details,
            "review": review_details,
            "fix_loop": fix_loop_details,
            "blocked": blocked_details,
            "report": report_details,
            "events_count": len(valid_events),
            "last_event_time": valid_events[-1].timestamp if valid_events else None,
        }

    @staticmethod
    def compute_graph_layout(
        steps: Dict[str, Any],
        current_step_id: str,
        verification: Dict[str, Any],
        review: Dict[str, Any],
        fix_loop: Dict[str, Any],
        blocked: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Builds directed state graph nodes and active loop edges for the UI."""
        is_blocked = blocked.get("is_blocked", False)
        attempts = fix_loop.get("attempts", 0)
        fix_running = fix_loop.get("status") == "RUNNING"
        review_failed = review.get("status") == "FAIL"
        ver_failed = verification.get("status") in ("FAIL", "UNVERIFIED")

        # Determine active node and next/upcoming node
        active_node_id = ""
        next_node_id = ""
        active_edge_ids = []

        if is_blocked:
            active_node_id = "blocked"
            next_node_id = ""
            active_edge_ids = ["verify->blocked", "fix_loop->blocked"]
        elif current_step_id == "raw_prompt":
            active_node_id = "prompt"
            next_node_id = "read_errors"
            active_edge_ids = ["prompt->read_errors"]
        elif current_step_id == "read_errors":
            active_node_id = "read_errors"
            next_node_id = "diagnosis" if "diagnosis" in steps else "interview"
            active_edge_ids = [f"read_errors->{next_node_id}"]
        elif current_step_id == "diagnosis":
            active_node_id = "diagnosis"
            next_node_id = "proposal"
            active_edge_ids = ["diagnosis->proposal"]
        elif current_step_id == "interview":
            active_node_id = "interview"
            next_node_id = "proposal"
            active_edge_ids = ["interview->proposal"]
        elif current_step_id in ("spec", "plan"):
            active_node_id = "proposal"
            next_node_id = "approval"
            active_edge_ids = ["proposal->approval"]
        elif current_step_id == "human_approval":
            active_node_id = "approval"
            next_node_id = "active"
            active_edge_ids = ["approval->active"]
        elif current_step_id == "active":
            active_node_id = "active"
            next_node_id = "tdd"
            active_edge_ids = ["active->tdd"]
        elif current_step_id == "tdd":
            active_node_id = "tdd"
            next_node_id = "verify"
            active_edge_ids = ["tdd->verify"]
        elif current_step_id == "verification":
            active_node_id = "verify"
            if ver_failed:
                next_node_id = "error_rec"
                active_edge_ids = ["verify->error_rec"]
            else:
                next_node_id = "review"
                active_edge_ids = ["verify->review"]
        elif current_step_id == "code_review":
            active_node_id = "review"
            if review_failed:
                next_node_id = "error_rec"
                active_edge_ids = ["review->error_rec"]
            else:
                next_node_id = "qa"
                active_edge_ids = ["review->qa"]
        elif current_step_id == "qa":
            if steps["qa"]["status"] == "FAILED":
                next_node_id = "error_rec"
                active_edge_ids = ["qa->error_rec"]
            elif steps["qa"]["status"] == "COMPLETED":
                next_node_id = "complete"
                active_edge_ids = ["qa->complete"]
            else:
                active_node_id = "qa"
                next_node_id = "complete"
                active_edge_ids = ["qa->complete"]
        elif current_step_id == "fix_loop":
            if fix_loop.get("status") == "RECORDING":
                active_node_id = "error_rec"
                next_node_id = "fix_loop"
                active_edge_ids = ["error_rec->fix_loop"]
            elif attempts > 0 and fix_running:
                active_node_id = "fix_loop"
                next_node_id = "tdd"
                active_edge_ids = ["fix_loop->tdd"]
            elif fix_loop.get("status") == "RECORDED":
                active_node_id = ""
                next_node_id = "fix_loop"
                active_edge_ids = []
            else:
                active_node_id = ""
                next_node_id = "error_rec"
                active_edge_ids = []
        elif current_step_id == "main_agent_report":
            report_status = steps["main_agent_report"]["status"]
            if report_status == "COMPLETED":
                active_node_id = ""
                next_node_id = ""
                active_edge_ids = []
            elif report_status == "RUNNING":
                active_node_id = "report"
                next_node_id = ""
                active_edge_ids = []
            else:
                active_node_id = ""
                next_node_id = "report" if steps["active"]["status"] == "COMPLETED" else "complete"
                active_edge_ids = []
        elif not current_step_id:
            # Idle / not started
            active_node_id = ""
            next_node_id = "prompt"
            active_edge_ids = []

        phase_status = {
            "prompt": steps["raw_prompt"]["status"],
            "read_errors": steps["read_errors"]["status"],
            "interview": steps["interview"]["status"],
            **({"diagnosis": steps["diagnosis"]["status"]} if "diagnosis" in steps else {}),
            "proposal": "RUNNING" if any(steps[name]["status"] == "RUNNING" for name in ("spec", "plan")) else "PENDING",
            "approval": steps["human_approval"]["status"],
            "active": steps["active"]["status"],
            "tdd": steps["tdd"]["status"],
            "verify": steps["verification"]["status"],
            "review": steps["code_review"]["status"],
            "qa": steps["qa"]["status"],
        }
        if active_node_id in phase_status and phase_status[active_node_id] not in ("RUNNING", "WAITING_HUMAN"):
            next_node_id = active_node_id
            active_node_id = ""
            active_edge_ids = []

        nodes = [
            {"id": "prompt", "label": "Raw Prompt", "label_vn": "Yêu cầu Gốc", "icon": "💬", "phase": "inception", "step_id": "raw_prompt", "status": steps["raw_prompt"]["status"], "is_active": active_node_id == "prompt", "is_next": next_node_id == "prompt"},
            {"id": "read_errors", "label": "Read Errors", "label_vn": "Đọc Lỗi Cũ", "icon": "📖", "phase": "inception", "step_id": "read_errors", "status": steps["read_errors"]["status"], "is_active": active_node_id == "read_errors", "is_next": next_node_id == "read_errors"},
            {"id": "diagnosis", "label": "Diagnosis", "label_vn": "Chẩn Đoán", "icon": "🔬", "phase": "inception", "step_id": "diagnosis", "status": steps["diagnosis"]["status"], "is_active": active_node_id == "diagnosis", "is_next": next_node_id == "diagnosis"} if "diagnosis" in steps else {"id": "interview", "label": "Interview", "label_vn": "Phỏng Vấn", "icon": "❓", "phase": "inception", "step_id": "interview", "status": steps["interview"]["status"], "is_active": active_node_id == "interview", "is_next": next_node_id == "interview"},
            {"id": "proposal", "label": "Spec & Plan", "label_vn": "Đặc Tả & Kế Hoạch", "icon": "📋", "phase": "inception", "step_id": "spec", "status": steps["spec"]["status"], "is_active": active_node_id == "proposal", "is_next": next_node_id == "proposal"},
            {"id": "approval", "label": "Approval Gate", "label_vn": "Cổng Duyệt Con Người", "icon": "🛡️", "phase": "gate", "step_id": "human_approval", "status": steps["human_approval"]["status"], "is_active": active_node_id == "approval", "is_next": next_node_id == "approval"},
            {"id": "active", "label": "Active Task", "label_vn": "Nhiệm Vụ Hiện Tại", "icon": "🎯", "phase": "execution", "step_id": "active", "status": steps["active"]["status"], "is_active": active_node_id == "active", "is_next": next_node_id == "active"},
            {"id": "tdd", "label": "TDD Coder", "label_vn": "Lập Trình TDD", "icon": "⚡", "phase": "execution", "step_id": "tdd", "status": steps["tdd"]["status"], "is_active": active_node_id == "tdd", "is_next": next_node_id == "tdd"},
            {"id": "verify", "label": "Verification Gate", "label_vn": "Cổng Kiểm Thử Argv", "icon": "🧪", "phase": "gate", "step_id": "verification", "status": steps["verification"]["status"], "is_active": active_node_id == "verify", "is_next": next_node_id == "verify"},
            {"id": "error_rec", "label": "Record Error", "label_vn": "Ghi Nhận Lỗi", "icon": "📝", "phase": "fixloop", "step_id": "fix_loop", "status": "COMPLETED" if attempts > 0 else "PENDING", "is_active": active_node_id == "error_rec", "is_next": next_node_id == "error_rec"},
            {"id": "fix_loop", "label": f"Fix Loop ({attempts}/3)", "label_vn": f"Vòng Sửa Lỗi ({attempts}/3)", "icon": "↺", "phase": "fixloop", "step_id": "fix_loop", "status": fix_loop.get("status", "PENDING"), "is_active": active_node_id == "fix_loop", "is_next": next_node_id == "fix_loop"},
            {"id": "review", "label": "Code Review", "label_vn": "Review Độc Lập", "icon": "🔍", "phase": "gate", "step_id": "code_review", "status": steps["code_review"]["status"], "is_active": active_node_id == "review", "is_next": next_node_id == "review"},
            {"id": "qa", "label": "QA Testing", "label_vn": "QA Sản Phẩm", "icon": "🧭", "phase": "gate", "step_id": "qa", "status": steps["qa"]["status"], "is_active": active_node_id == "qa", "is_next": next_node_id == "qa"},
            {"id": "complete", "label": "Task Done", "label_vn": "Nhiệm Vụ Xong", "icon": "🏆", "phase": "completion", "step_id": "active", "status": "COMPLETED" if steps["active"]["status"] == "COMPLETED" else "PENDING", "is_active": active_node_id == "complete", "is_next": next_node_id == "complete"},
            {"id": "report", "label": "Main Agent Report", "label_vn": "Báo Cáo Nghiệm Thu", "icon": "📢", "phase": "completion", "step_id": "main_agent_report", "status": steps["main_agent_report"]["status"], "is_active": active_node_id == "report", "is_next": next_node_id == "report"},
            {"id": "blocked", "label": "BLOCKED", "label_vn": "BỊ CHẶN", "icon": "⛔", "phase": "blocked", "step_id": "active", "status": "BLOCKED" if is_blocked else "PENDING", "is_active": active_node_id == "blocked", "is_next": False},
        ]

        # Edges and feedback loops
        edges = [
            {"from": "prompt", "to": "read_errors", "type": "sequence"},
            {"from": "read_errors", "to": "diagnosis" if "diagnosis" in steps else "interview", "type": "sequence"},
            {"from": "diagnosis" if "diagnosis" in steps else "interview", "to": "proposal", "type": "sequence"},
            {"from": "proposal", "to": "approval", "type": "sequence"},
            {"from": "approval", "to": "active", "type": "approved"},
            {"from": "approval", "to": "proposal", "type": "loop_revision"},
            {"from": "active", "to": "tdd", "type": "sequence"},
            {"from": "tdd", "to": "verify", "type": "sequence"},
            {"from": "verify", "to": "review", "type": "pass"},
            {"from": "verify", "to": "error_rec", "type": "fail_loop"},
            {"from": "error_rec", "to": "fix_loop", "type": "sequence"},
            {"from": "fix_loop", "to": "tdd", "type": "feedback_loop"},
            {"from": "review", "to": "qa", "type": "pass"},
            {"from": "qa", "to": "complete", "type": "pass"},
            {"from": "qa", "to": "error_rec", "type": "fail_loop"},
            {"from": "review", "to": "error_rec", "type": "fail_loop"},
            {"from": "complete", "to": "active", "type": "next_task_loop"},
            {"from": "complete", "to": "report", "type": "sequence"},
            {"from": "verify", "to": "blocked", "type": "blocked_branch"},
            {"from": "review", "to": "blocked", "type": "blocked_branch"},
            {"from": "fix_loop", "to": "blocked", "type": "blocked_branch"},
        ]

        return {
            "nodes": nodes,
            "edges": edges,
            "active_edges": active_edge_ids,
            "active_node_id": active_node_id,
            "next_node_id": next_node_id,
            "is_looping": attempts > 0 and not is_blocked,
            "loop_round": attempts,
            "is_blocked": is_blocked,
        }

    @staticmethod
    def _reconcile_with_disk(
        root: Path,
        steps: Dict[str, Any],
        fix_loop_details: Dict[str, Any],
        blocked_details: Dict[str, Any],
        verification_details: Dict[str, Any],
        review_details: Dict[str, Any],
        report_details: Dict[str, Any],
    ):
        """Cross-checks .verified-development-loop records as ground truth."""
        try:
            # Check draft plans
            draft_plans = list((root / ".verified-development-loop" / "plans" / "drafts").glob("*.md")) if (root / ".verified-development-loop" / "plans" / "drafts").exists() else []
            if draft_plans and steps["spec"]["status"] == "PENDING":
                steps["raw_prompt"]["status"] = "COMPLETED"
                steps["read_errors"]["status"] = "COMPLETED"
                steps["interview"]["status"] = "COMPLETED"
                steps["spec"]["status"] = "COMPLETED"
                steps["spec"]["summary"] = f"Draft plan found on disk ({draft_plans[0].stem})"
                steps["plan"]["status"] = "COMPLETED"
                steps["plan"]["summary"] = f"Plan draft {draft_plans[0].stem}"
                steps["human_approval"]["status"] = "WAITING_HUMAN"
                steps["human_approval"]["summary"] = "Waiting for human approval"

            # Check active plans
            active_plans = list((root / ".verified-development-loop" / "plans" / "active").glob("*.md")) if (root / ".verified-development-loop" / "plans" / "active").exists() else []
            for ppath in active_plans:
                try:
                    pdata = read_workflow_doc(ppath)
                    steps["raw_prompt"]["status"] = "COMPLETED"
                    steps["read_errors"]["status"] = "COMPLETED"
                    steps["interview"]["status"] = "COMPLETED"
                    steps["spec"]["status"] = "COMPLETED"
                    steps["plan"]["status"] = "COMPLETED"
                    steps["human_approval"]["status"] = "COMPLETED"
                    steps["human_approval"]["summary"] = f"Approved: {pdata.get('human_approval', {}).get('record', 'Yes')}"
                    if steps["active"]["status"] == "PENDING":
                        steps["active"]["status"] = "RUNNING"

                    if pdata.get("execution_state") == "waiting_human":
                        steps["human_approval"]["status"] = "WAITING_HUMAN"
                        steps["human_approval"]["summary"] = "Task is blocked; waiting for human decision"
                except Exception:
                    pass

            # Check active tasks
            active_tasks = list((root / ".verified-development-loop" / "tasks" / "active").glob("*.md")) if (root / ".verified-development-loop" / "tasks" / "active").exists() else []
            for tpath in active_tasks:
                try:
                    tdata = read_workflow_doc(tpath)
                    tid = tdata.get("task_id", tpath.stem)
                    fix_round = int(tdata.get("fix_round", 0))
                    if fix_round > 0:
                        fix_loop_details["attempts"] = fix_round
                        fix_loop_details["max_attempts"] = 3
                        if fix_loop_details["status"] == "PENDING":
                            fix_loop_details["status"] = "RUNNING"
                            steps["fix_loop"]["status"] = "RUNNING"
                            steps["fix_loop"]["summary"] = f"Fix Round {fix_round}/3"

                    if tdata.get("status") == "blocked":
                        reason = tdata.get("blocked_reason", "Task is blocked")
                        blocked_details["is_blocked"] = True
                        blocked_details["reason"] = reason
                        blocked_details["task_id"] = tid
                        steps["active"]["status"] = "BLOCKED"
                        steps["active"]["summary"] = f"BLOCKED: {reason}"
                        steps["fix_loop"]["status"] = "BLOCKED"

                    # Check verification evidence
                    ver_ref = tdata.get("verification_evidence")
                    if ver_ref:
                        vfile = root / ver_ref
                        if vfile.exists():
                            vdata = read_workflow_doc(vfile)
                            vstatus = vdata.get("status", "UNKNOWN")
                            steps["verification"]["status"] = "COMPLETED" if vstatus == "PASS" else "FAILED"
                            steps["verification"]["summary"] = f"Verification {vstatus}"
                            steps["verification"]["evidence_reference"] = ver_ref
                            verification_details.update({
                                "status": vstatus,
                                "evidence": ver_ref,
                                "commands": vdata.get("commands", []),
                                "revision": vdata.get("revision"),
                            })

                    # Check review evidence
                    rev_ref = tdata.get("review_evidence")
                    if rev_ref:
                        rfile = root / rev_ref
                        if rfile.exists():
                            rdata = read_workflow_doc(rfile)
                            rstatus = rdata.get("status", "UNKNOWN")
                            steps["code_review"]["status"] = "COMPLETED" if rstatus == "PASS" else "FAILED"
                            steps["code_review"]["summary"] = f"Review {rstatus} ({len(rdata.get('findings', []))} findings)"
                            steps["code_review"]["evidence_reference"] = rev_ref
                            review_details.update({
                                "status": rstatus,
                                "reviewer": rdata.get("reviewer", "code_reviewer"),
                                "findings": rdata.get("findings", []),
                                "evidence": rev_ref,
                            })

                    qa_ref = tdata.get("qa_evidence")
                    if qa_ref:
                        qfile = root / qa_ref
                        if qfile.exists():
                            qdata = read_workflow_doc(qfile)
                            qstatus = qdata.get("status", "UNKNOWN")
                            steps["qa"]["status"] = "COMPLETED" if qstatus == "PASS" else "FAILED"
                            steps["qa"]["summary"] = f"QA {qstatus}"
                            steps["qa"]["evidence_reference"] = qa_ref
                            steps["qa"]["details"] = {"result": qstatus, "tester": qdata.get("tester")}
                except Exception:
                    pass

            # Check completed plans
            completed_plans = list((root / ".verified-development-loop" / "plans" / "completed").glob("*.md")) if (root / ".verified-development-loop" / "plans" / "completed").exists() else []
            if completed_plans and not active_plans:
                cplan = completed_plans[0]
                try:
                    cdata = read_workflow_doc(cplan)
                    for sid in ["raw_prompt", "read_errors", "interview", "spec", "plan", "human_approval", "active", "tdd", "verification", "code_review", "qa"]:
                        steps[sid]["status"] = "COMPLETED"
                    if steps["main_agent_report"]["status"] == "COMPLETED":
                        steps["main_agent_report"]["summary"] = f"Plan {cplan.stem} completed and verified"
                        report_details["summary"] = f"Plan {cplan.stem} completed"
                    report_details["criteria"] = cdata.get("acceptance_evidence", {}).get("criteria", [])
                except Exception:
                    pass

            # Check errors directory for recurrences & blocked
            if (root / ".verified-development-loop" / "errors").exists():
                for epath in (root / ".verified-development-loop" / "errors").glob("*.md"):
                    try:
                        edata = read_workflow_doc(epath)
                        if edata.get("status") == "BLOCKED":
                            blocked_details["is_blocked"] = True
                            if not blocked_details.get("reason"):
                                blocked_details["reason"] = f"Error {edata.get('error_id')} blocked"
                        if edata.get("recurrences", 0) > 0:
                            fix_loop_details["recurrence_count"] = edata["recurrences"]
                            fix_loop_details["status"] = "BLOCKED"
                    except Exception:
                        pass
        except Exception:
            pass
