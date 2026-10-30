"""Interactive review. This is the only path that edits requirements.yaml."""

from __future__ import annotations

from datetime import date

from vigil.config import Paths
from vigil.requirements import (
    load_proposals,
    load_requirements,
    save_proposals,
    save_requirements,
    set_last_verified,
    set_requirement_field,
    validate_field,
)


def run_review(paths: Paths, today: date, input_fn=input, output_fn=print) -> None:
    requirements_path = paths.config_dir / "requirements.yaml"
    pending_path = paths.config_dir / "requirements.pending.yaml"
    requirements = load_requirements(requirements_path) if requirements_path.is_file() else {}
    proposals = load_proposals(pending_path)
    pending = [item for item in proposals if item.status == "pending"]
    if not pending:
        _touch_verified(requirements_path, requirements, today, output_fn)
        return
    for index, proposal in enumerate(pending, start=1):
        output_fn("")
        output_fn(f"[{index}/{len(pending)}] {proposal.source_id}")
        output_fn(proposal.snippet_url)
        output_fn(proposal.quote)
        if proposal.suggested_field:
            hint = proposal.suggested_field
            if proposal.suggested_value:
                hint = f"{hint} = {proposal.suggested_value}"
            output_fn(f"suggested: {hint}")
        if proposal.suggested_deadline:
            output_fn(f"suggested deadline: {proposal.suggested_deadline}")
        while True:
            choice = input_fn("[a]ccept  [d]ismiss  [s]kip: ").strip().lower()
            if choice in {"a", "accept"}:
                if _accept(requirements, proposal, input_fn, output_fn):
                    proposal.status = "accepted"
                    save_requirements(requirements_path, requirements)
                    break
            elif choice in {"d", "dismiss"}:
                proposal.status = "dismissed"
                output_fn("dismissed")
                break
            elif choice in {"s", "skip"}:
                output_fn("skipped")
                break
            else:
                output_fn("Enter a, d, or s.")
        save_proposals(pending_path, proposals)
    if any(item.status == "pending" for item in proposals):
        output_fn("Pending proposals remain. last_verified was not changed.")
        return
    _touch_verified(requirements_path, requirements, today, output_fn)


def _touch_verified(path, requirements: dict, today: date, output_fn) -> None:
    set_last_verified(requirements, today)
    path.parent.mkdir(parents=True, exist_ok=True)
    save_requirements(path, requirements)
    output_fn(f"Nothing pending. Requirements last verified set to {today.isoformat()}.")


def _accept(requirements: dict, proposal, input_fn, output_fn) -> bool:
    default_field = proposal.suggested_field or ""
    default_value = proposal.suggested_value or ""
    field = input_fn(f"field [{default_field}]: ").strip() or default_field
    problem = validate_field(field)
    if problem:
        output_fn(problem)
        return False
    value = input_fn(f"value [{default_value}]: ").strip() or default_value
    if not value:
        output_fn("A value is required.")
        return False
    default_deadline = proposal.suggested_deadline or ""
    deadline = input_fn(f"deadline YYYY-MM-DD [{default_deadline}]: ").strip() or default_deadline
    if deadline:
        try:
            date.fromisoformat(deadline)
        except ValueError:
            output_fn("Deadline must be YYYY-MM-DD.")
            return False
    source = proposal.snippet_url or None
    set_requirement_field(requirements, field, value, deadline or None, source)
    output_fn(f"accepted {field}")
    return True
