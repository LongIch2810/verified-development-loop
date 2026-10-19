"""Readable Markdown workflow records with embedded machine state."""

import json


START = "<!-- vdl-json\n"
END = "\n-->"


def read(path):
    content = path.read_text(encoding="utf-8")
    if path.suffix != ".md":
        return json.loads(content)
    if not content.startswith(START):
        raise ValueError(f"missing workflow state in {path}")
    end = content.find(END, len(START))
    if end < 0:
        raise ValueError(f"unterminated workflow state in {path}")
    return json.loads(content[len(START):end])


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(data, indent=2, ensure_ascii=False)
    if path.suffix != ".md":
        path.write_text(encoded + "\n", encoding="utf-8")
        return
    kind = path.parent.parent.name if path.parent.name in ("drafts", "active", "completed") or path.parent.parent.name == "evidence" else path.parent.name
    name = data.get("plan_id") or data.get("task_id") or data.get("error_id") or path.stem
    lines = [f"# {kind.title()}: {name}", "", f"**Status:** {data.get('status', 'approved')}", ""]
    if kind == "specs":
        spec = data.get("spec")
        lines += ["## Spec", ""]
        if isinstance(spec, dict):
            for key, value in spec.items():
                lines += [f"### {key.replace('_', ' ').title()}", ""]
                lines += [f"- {item}" for item in value] if isinstance(value, list) else [str(value)]
                lines.append("")
        else:
            lines += [str(spec), ""]
    if kind == "plans":
        lines += ["## Tasks", ""]
        for item in data.get("tasks", []):
            lines += [f"### {item['task_id']}: {item.get('title', '')}", ""]
            lines += [f"- {criterion}" for criterion in item.get("acceptance_criteria", [])]
            if item.get("test_code"):
                lines += ["", "Test code:", "", item["test_code"]]
            if item.get("qa_plan"):
                lines += ["", "QA scenarios:", "", item["qa_plan"]]
            lines += ["", "Verification:", ""]
            lines += [f"- `{' '.join(command)}`" for command in item.get("verification", [])]
            lines.append("")
    if kind == "tasks":
        lines += [f"**Plan:** {data.get('plan_id', '')}", "", f"{data.get('title', '')}", ""]
        if data.get("latest_report"):
            lines += [f"**Latest report:** {data['latest_report']}", ""]
        if data.get("test_code"):
            lines += ["## Test code", "", data["test_code"], ""]
        if data.get("qa_plan"):
            lines += ["QA scenarios:", "", data["qa_plan"], ""]
        lines += ["## Verification", ""]
        lines += [f"- `{' '.join(command)}`" for command in data.get("verification", [])]
        lines.append("")
    if kind == "errors":
        lines += ["## Error", "", data.get("description", ""), "", f"**Task:** {data.get('task_id', '')}", "", f"**Plan:** {data.get('plan_id', '')}", "", f"**Fix attempts:** {data.get('fix_attempts', 0)}", "", f"**Recurrences:** {data.get('recurrences', 0)}", ""]
        for attempt in data.get("attempts", []):
            lines += [f"- Round {attempt['round']}: {attempt['approach']} — {attempt['result']}"]
        lines.append("")
    if kind == "evidence":
        lines += ["## Record", ""]
        lines += ["    " + line for line in encoded.splitlines()]
        lines.append("")
    criteria = data.get("acceptance_criteria", [])
    if criteria:
        lines += ["## Acceptance criteria", ""]
        lines += [f"- {item}" for item in criteria]
        lines.append("")
    path.write_text(START + encoded + END + "\n\n" + "\n".join(lines), encoding="utf-8")
