"""Render the self-contained HTML report and status.json."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from jinja2 import Environment

from vigil.config import Paths
from vigil.requirements import Finding

_STATE_LABELS = {
    "ok": "OK",
    "action": "Action needed",
    "degraded": "Degraded",
}
_PRIORITY = {"high": 0, "normal": 1, "low": 2}
_REQUIREMENT_FIELDS = frozenset(
    {
        "android.target_api_min",
        "ios.min_xcode",
        "ios.min_deployment_target",
        "flutter.recommended_stable",
    }
)


def template_text() -> str:
    local = Path(__file__).resolve().parent / "templates" / "report.html.j2"
    if local.is_file():
        return local.read_text(encoding="utf-8")
    from importlib.resources import files

    return files("vigil").joinpath("templates", "report.html.j2").read_text(encoding="utf-8")


def render_report(context: dict) -> str:
    environment = Environment(autoescape=True, trim_blocks=True, lstrip_blocks=True)
    return environment.from_string(template_text()).render(**context)


def overall_state(errors: list[str], action_count: int) -> str:
    if errors:
        return "degraded"
    if action_count:
        return "action"
    return "ok"


def todo_groups(findings: list[Finding]) -> list[dict]:
    buckets: dict[str, list[Finding]] = {}
    for finding in findings:
        if finding.severity not in {"action", "watch"}:
            continue
        buckets.setdefault(finding.repo or "General", []).append(finding)
    groups = []
    for name, lines in buckets.items():
        lines.sort(key=lambda finding: (0 if finding.severity == "action" else 1, finding.message))
        priority = min(lines, key=lambda finding: _PRIORITY.get(finding.priority, 1)).priority
        groups.append(
            {
                "name": name,
                "priority": priority,
                "lines": [{"severity": line.severity, "message": line.message} for line in lines],
            }
        )
    groups.sort(key=lambda group: (0 if group["name"] == "General" else 1, _PRIORITY.get(group["priority"], 1), group["name"]))
    return groups


def proposal_affects_apps(proposal: dict) -> bool:
    """True when the proposal names a concrete requirement field and value."""
    field = proposal.get("suggested_field")
    value = proposal.get("suggested_value")
    if field not in _REQUIREMENT_FIELDS:
        return False
    if value is None:
        return False
    return str(value).strip() != ""


def split_proposals(proposals: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split pending proposals into ones that affect apps vs awareness items."""
    affects: list[dict] = []
    awareness: list[dict] = []
    for proposal in proposals:
        if proposal_affects_apps(proposal):
            affects.append(proposal)
        else:
            awareness.append(proposal)
    return affects, awareness


def write_report(paths: Paths, context: dict, today) -> Path:
    paths.reports_dir.mkdir(parents=True, exist_ok=True)
    filename = f"report-{today.isoformat()}.html"
    destination = paths.reports_dir / filename
    destination.write_text(render_report(context), encoding="utf-8")
    link = paths.reports_dir / "latest.html"
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(destination.name)
    return destination


def write_status(paths: Paths, status: dict) -> None:
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    temporary = paths.status_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    temporary.replace(paths.status_path)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
