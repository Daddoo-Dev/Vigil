"""One scan: sources, repos, requirements, report. The tray is not involved."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import httpx

from vigil.config import (
    ConfigError,
    Paths,
    Repo,
    Settings,
    Source,
    load_repos,
    load_settings,
    load_sources,
)
from vigil.drift import DriftInput, build_drift
from vigil.extractors import Candidate, get_extractor
from vigil.fetchers import FetchResult, fetch_source, make_client
from vigil.holds import (
    PackageHold,
    active_holds,
    clear_stale_holds,
    is_held,
    is_ready,
    load_holds,
    make_hold,
    ready_holds,
    save_holds,
    upsert_hold,
)
from vigil.probe import collect_probe_candidates, run_canary_probes
from vigil.report import (
    now_iso,
    overall_state,
    split_proposals,
    todo_groups,
    write_report,
    write_status,
)
from vigil.requirements import (
    Finding,
    Proposal,
    RepoFacts,
    last_verified_text,
    load_proposals,
    load_requirements,
    merge_proposals,
    proposal_id,
    save_proposals,
    compare_repo,
    global_findings,
)
from vigil.scanners.android import AndroidSdk, read_android
from vigil.scanners.expiries import check_expiries, expiry_message, load_expiries
from vigil.scanners.flutter import FlutterInfo, read_flutter
from vigil.scanners.ios import IosTargets, read_ios
from vigil.scanners.packages import OutdatedPackage, read_lock, run_outdated
from vigil.scanners.pubdev import PubDevClient, PubInfo
from vigil.snapshots import diff_snapshot, load_snapshot, save_snapshot

logger = logging.getLogger("vigil.scan")


class TerminalProgress:
    """One status line. A terminal rewrites it; a log gets a new line each time."""

    def __init__(self, stream=None):
        self.stream = sys.stdout if stream is None else stream
        self._width = 0

    def __call__(self, message: str) -> None:
        text = str(message)
        if self.stream.isatty():
            self.stream.write("\r" + text.ljust(self._width))
            self.stream.flush()
            self._width = len(text)
            return
        self.stream.write(text + "\n")
        self.stream.flush()

    def finish(self) -> None:
        if not self._width:
            return
        self.stream.write("\n")
        self.stream.flush()
        self._width = 0


@dataclass
class RepoScan:
    repo: Repo
    flutter: FlutterInfo
    android: AndroidSdk | None = None
    ios: IosTargets | None = None
    lock: dict[str, str] = field(default_factory=dict)
    outdated: list[OutdatedPackage] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def run_scan(
    paths: Paths,
    *,
    client: httpx.Client | None = None,
    today: date | None = None,
    outdated_runner=None,
    pubdev_client: PubDevClient | None = None,
    notify_fn=None,
    sleeper=None,
    progress=None,
) -> dict:
    """Run every check. Source and repo failures are recorded; they do not abort the run."""
    paths.ensure()
    today = today or date.today()
    errors: list[str] = []
    progress = TerminalProgress() if progress is None else progress
    try:
        return _run_scan(
            paths,
            client,
            today,
            outdated_runner,
            pubdev_client,
            notify_fn,
            sleeper,
            progress,
            errors,
        )
    finally:
        finish = getattr(progress, "finish", None)
        if finish is not None:
            finish()


def _run_scan(paths, client, today, outdated_runner, pubdev_client, notify_fn, sleeper, progress, errors):
    settings = _settings(paths, errors)
    repos = _repos(paths, errors)
    sources = _sources(paths, errors)
    requirements, verified = _requirements(paths, errors)
    proposals = _existing_proposals(paths, errors)
    expiries, expiry_errors = _expiries(paths, today)
    errors.extend(expiry_errors)

    fetches, proposals = _sources_phase(
        paths, sources, settings, proposals, today, client, errors, sleeper, progress
    )
    runner = outdated_runner or run_outdated
    scans = []
    total = len(repos)
    noun = "project" if total == 1 else "projects"
    for index, repo in enumerate(repos, start=1):
        progress(f"Scanning {repo.name} ({index} of {total} {noun})")
        scans.append(_scan_repo(repo, runner))
    for scan in scans:
        errors.extend(scan.errors)

    pub_errors, pub_info = _pubdev(scans, client, pubdev_client, progress)
    errors.extend(pub_errors)

    holds, probe_notes = _holds_phase(paths, scans, settings, today, progress, errors)
    errors.extend(probe_notes)

    findings = list(global_findings(requirements, today))
    for scan in scans:
        findings.extend(compare_repo(_facts(scan), requirements, today))
        findings.extend(_package_findings(scan, pub_info, holds))
    for expiry in expiries:
        if expiry.severity == "info":
            continue
        priority = _priority_for(expiry.app, repos)
        findings.append(
            Finding(expiry.severity, expiry_message(expiry), expiry.app, priority, "expiry")
        )

    action_count = sum(1 for finding in findings if finding.severity == "action")
    pending = [item for item in proposals if item.status == "pending"]
    pending_rows = [item.to_dict() for item in pending]
    affects_apps, worth_knowing = split_proposals(pending_rows)
    state = overall_state(errors, action_count)
    drift = build_drift([_drift_input(scan) for scan in scans])
    blocked = active_holds(holds)
    ready = ready_holds(holds)
    context = {
        "state": state,
        "state_label": {"ok": "OK", "action": "Action needed", "degraded": "Degraded"}[state],
        "last_verified": verified,
        "action_count": action_count,
        "pending_count": len(pending),
        "affects_apps": affects_apps,
        "worth_knowing": worth_knowing,
        "errors": errors,
        "todo_groups": todo_groups(findings),
        "proposals": pending_rows,
        "drift": {
            "columns": drift.columns,
            "rows": [
                {
                    "name": row.name,
                    "cells": [{"text": cell.text, "outlier": cell.outlier} for cell in row.cells],
                }
                for row in drift.rows
            ],
        },
        "packages": [
            {"severity": finding.severity, "message": finding.message}
            for finding in findings
            if finding.category == "package"
        ],
        "ready": [
            {
                "package": hold.package,
                "blocked_major": hold.blocked_major,
                "latest_when_held": hold.latest_when_held,
                "discovered_in": hold.discovered_in,
                "reason": hold.reason,
            }
            for hold in ready
        ],
        "holds": [
            {
                "package": hold.package,
                "blocked_major": hold.blocked_major,
                "latest_when_held": hold.latest_when_held,
                "scope": hold.scope,
                "source": hold.source,
                "discovered_in": hold.discovered_in,
                "reason": hold.reason,
            }
            for hold in blocked
        ],
        "expiries": [
            {"severity": expiry.severity, "message": expiry_message(expiry)} for expiry in expiries
        ],
        "fetches": [
            {"name": item.name, "status": item.status, "detail": item.detail} for item in fetches
        ],
        "generated": now_iso(),
    }
    report_path = write_report(paths, context, today)
    status = {
        "state": state,
        "action_count": action_count,
        "pending_count": len(pending),
        "last_run": context["generated"],
        "report_path": str(report_path),
        "errors": errors,
    }
    write_status(paths, status)
    logger.info("scan %s actions=%s pending=%s", state, action_count, len(pending))
    _notify(settings, status, notify_fn)
    return status


def _settings(paths: Paths, errors: list[str]) -> Settings:
    try:
        return load_settings(paths.config_dir / "settings.yaml")
    except ConfigError as exc:
        errors.append(str(exc))
        return Settings()


def _repos(paths: Paths, errors: list[str]) -> list[Repo]:
    path = paths.config_dir / "repos.yaml"
    try:
        repos = load_repos(path)
    except ConfigError as exc:
        errors.append(str(exc))
        return []
    except FileNotFoundError:
        errors.append(f"missing config file: {path}")
        return []
    if not repos:
        errors.append("no repos configured. Run: vigil projects")
    return repos


def _sources(paths: Paths, errors: list[str]) -> list[Source]:
    path = paths.config_dir / "sources.yaml"
    try:
        sources = load_sources(path)
    except ConfigError as exc:
        errors.append(str(exc))
        return []
    except FileNotFoundError:
        errors.append(f"missing config file: {path}")
        return []
    if not sources:
        errors.append("no sources configured in sources.yaml")
    return sources


def _requirements(paths: Paths, errors: list[str]) -> tuple[dict, str]:
    path = paths.config_dir / "requirements.yaml"
    try:
        data = load_requirements(path)
    except FileNotFoundError:
        errors.append(f"missing config file: {path}")
        return {}, "never"
    except ValueError as exc:
        errors.append(str(exc))
        return {}, "unreadable"
    return data, last_verified_text(data)


def _existing_proposals(paths: Paths, errors: list[str]) -> list[Proposal]:
    path = paths.config_dir / "requirements.pending.yaml"
    try:
        return load_proposals(path)
    except ValueError as exc:
        errors.append(str(exc))
        return []


def _expiries(paths: Paths, today: date):
    path = paths.config_dir / "expiries.yaml"
    if not path.is_file():
        return [], []
    try:
        return check_expiries(load_expiries(path), today)
    except (ValueError, FileNotFoundError) as exc:
        return [], [str(exc)]


def _sources_phase(paths, sources, settings, proposals, today, client, errors, sleeper, progress):
    if not sources:
        return [], proposals
    try:
        extractor = get_extractor(settings.extractor)
    except NotImplementedError as exc:
        errors.append(str(exc))
        return [], proposals
    own_client = client is None
    if own_client:
        client = make_client()
    fetches: list[FetchResult] = []
    fresh: list[Proposal] = []
    try:
        total = len(sources)
        for index, source in enumerate(sources, start=1):
            progress(f"Checking {source.name} ({index} of {total})")
            kwargs = {"sleeper": sleeper} if sleeper is not None else {}
            result = fetch_source(source, client, **kwargs)
            fetches.append(result)
            logger.info("source %s %s %s", source.id, result.status, result.detail)
            if result.status != "ok":
                errors.append(f"{source.name}: {result.status} ({result.detail})")
                continue
            snapshot_path = paths.snapshots_dir / f"{source.id}.json"
            previous = load_snapshot(snapshot_path)
            diff = diff_snapshot(previous, result.paragraphs)
            if not diff.changed:
                continue
            if not diff.added:
                save_snapshot(snapshot_path, result.paragraphs)
                continue
            candidates = extractor.extract("\n\n".join(diff.added), source)
            if not candidates:
                errors.append(f"{source.name}: changed but nothing extracted: review manually")
                continue
            save_snapshot(snapshot_path, result.paragraphs)
            fresh.extend(_proposals_from(source.id, candidates, today))
    finally:
        if own_client:
            client.close()
    merged = merge_proposals(proposals, fresh)
    save_proposals(paths.config_dir / "requirements.pending.yaml", merged)
    return fetches, merged


def _proposals_from(source_id: str, candidates: list[Candidate], today: date) -> list[Proposal]:
    proposals = []
    for candidate in candidates:
        proposals.append(
            Proposal(
                id=proposal_id(source_id, candidate.quote),
                source_id=source_id,
                found_at=today.isoformat(),
                quote=candidate.quote,
                snippet_url=candidate.snippet_url,
                suggested_field=candidate.suggested_field,
                suggested_value=candidate.suggested_value,
                status="pending",
                suggested_deadline=candidate.suggested_deadline,
            )
        )
    return proposals


def _scan_repo(repo: Repo, outdated_runner) -> RepoScan:
    scan = RepoScan(repo=repo, flutter=FlutterInfo())
    try:
        scan.flutter = read_flutter(repo.path)
    except Exception as exc:
        logger.exception("flutter scan failed for %s", repo.name)
        scan.errors.append(f"{repo.name}: Flutter scan failed: {exc}")
    else:
        for note in scan.flutter.notes:
            scan.errors.append(f"{repo.name}: {note}")
    if "android" in repo.platforms:
        try:
            scan.android, problem = read_android(repo.path, scan.flutter.sdk_versions)
            if problem:
                scan.errors.append(f"{repo.name}: {problem}")
        except Exception as exc:
            logger.exception("android scan failed for %s", repo.name)
            scan.errors.append(f"{repo.name}: Android scan failed: {exc}")
    if "ios" in repo.platforms:
        try:
            scan.ios, problem = read_ios(repo.path)
            if problem:
                scan.errors.append(f"{repo.name}: {problem}")
        except Exception as exc:
            logger.exception("ios scan failed for %s", repo.name)
            scan.errors.append(f"{repo.name}: iOS scan failed: {exc}")
    try:
        scan.lock = read_lock(repo.path)
    except Exception as exc:
        logger.exception("lockfile scan failed for %s", repo.name)
        scan.errors.append(f"{repo.name}: pubspec.lock scan failed: {exc}")
    try:
        parsed, problem = outdated_runner(repo.path)
        if problem:
            scan.errors.append(f"{repo.name}: {problem}")
        scan.outdated = parsed or []
    except Exception as exc:
        logger.exception("outdated scan failed for %s", repo.name)
        scan.errors.append(f"{repo.name}: package scan failed: {exc}")
    return scan


def _pubdev(scans: list[RepoScan], client, pubdev_client: PubDevClient | None, progress):
    names: list[str] = []
    for scan in scans:
        names.extend(scan.flutter.direct_dependencies)
    if not names:
        return [], {}
    progress("Checking packages on pub.dev")
    own_client = client is None and pubdev_client is None
    if pubdev_client is None:
        if client is None:
            client = make_client()
        pubdev_client = PubDevClient(client)
    try:
        found, lookup_errors = pubdev_client.lookup(names)
        return lookup_errors, found
    finally:
        if own_client:
            client.close()


def _facts(scan: RepoScan) -> RepoFacts:
    pin = scan.android.target_sdk if scan.android else None
    ios = scan.ios
    flutter = scan.flutter
    channel = None
    if flutter.fvm_version and not flutter.pinned_flutter:
        channel = flutter.fvm_version
    return RepoFacts(
        name=scan.repo.name,
        priority=scan.repo.priority,
        platforms=list(scan.repo.platforms),
        target_sdk=pin.number if pin else None,
        target_sdk_unresolved=bool(pin and pin.unresolved and pin.number is None),
        ios_deployment=ios.minimum if ios else None,
        ios_unresolved=bool(ios and ios.unresolved),
        flutter_pin=flutter.pinned_flutter,
        flutter_constraint=flutter.flutter_constraint,
        fvm_channel=channel,
    )


def _holds_phase(
    paths: Paths,
    scans: list[RepoScan],
    settings: Settings,
    today: date,
    progress,
    errors: list[str],
) -> tuple[list[PackageHold], list[str]]:
    """Verify majors: solver blocks, then canary until Ready or Blocked for each."""
    notes: list[str] = []
    path = paths.config_dir / "holds.yaml"
    try:
        holds = load_holds(path)
    except ValueError as exc:
        errors.append(f"holds.yaml: {exc}")
        holds = []

    # Direct + transitive latest so blocked_by wake-ups see companion moves.
    latest_by_package: dict[str, str] = {}
    for scan in scans:
        for row in scan.outdated:
            if not row.latest:
                continue
            previous = latest_by_package.get(row.name)
            if previous is None or row.latest == previous:
                latest_by_package[row.name] = row.latest

    # Smart recheck: clear Ready/Blocked only when this package's latest moved,
    # or when a recorded blocked_by dependency's latest moved. Unchanged
    # verdicts stay put — no blanket re-canary.
    clear_stale_holds(holds, latest_by_package)

    for scan in scans:
        for row in scan.outdated:
            if row.kind != "direct" or not row.solver_blocked or not row.latest:
                continue
            if row.name not in scan.flutter.direct_dependencies:
                continue
            hold = make_hold(
                package=row.name,
                latest=row.latest,
                reason=(
                    f"pub outdated: resolvable {row.resolvable} cannot reach latest {row.latest}"
                ),
                source="solver",
                scope="repo",
                discovered_in=scan.repo.name,
                today=today,
                repo=scan.repo.name,
                status="blocked",
            )
            upsert_hold(holds, hold)

    if settings.probe_builds:
        candidates = collect_probe_candidates(scans)
        judged = {
            hold.package
            for hold in holds
            if (hold.is_blocked or hold.is_ready)
            and hold.scope == "global"
        }
        # Also skip packages already blocked/ready for the canary repo this scan.
        filtered = []
        for candidate in candidates:
            if candidate.package in judged:
                continue
            if is_held(
                holds,
                package=candidate.package,
                latest=candidate.latest,
                repo=candidate.repo_name,
            ):
                continue
            if is_ready(
                holds,
                package=candidate.package,
                latest=candidate.latest,
                repo=candidate.repo_name,
            ):
                continue
            filtered.append(candidate)
        if filtered:
            budget = settings.probe_budget
            planned = len(filtered) if budget == 0 else min(budget, len(filtered))
            progress(
                f"Verifying upgrades ({planned} of {len(filtered)} majors; "
                "slow on purpose — one failure blocks that major on all apps)"
            )
            for result in run_canary_probes(
                filtered,
                held_packages=judged,
                today=today,
                budget=budget,
            ):
                notes.append(f"probe: {result.detail}")
                if result.hold:
                    upsert_hold(holds, result.hold)
                    if result.hold.scope == "global":
                        judged.add(result.hold.package)

    try:
        save_holds(path, holds)
    except OSError as exc:
        errors.append(f"holds.yaml: could not write: {exc}")
    return holds, notes


def _package_findings(
    scan: RepoScan,
    pub_info: dict[str, PubInfo],
    holds: list[PackageHold] | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    holds = holds or []
    outdated = {item.name: item for item in scan.outdated if item.kind == "direct"}
    names = list(dict.fromkeys([*scan.flutter.direct_dependencies, *outdated]))
    for name in names:
        if name not in scan.flutter.direct_dependencies and name not in outdated:
            continue
        info = pub_info.get(name)
        row = outdated.get(name)
        locked = scan.lock.get(name) or (row.current if row else None)
        discontinued = bool((info and info.discontinued) or (row and row.discontinued))
        replaced = info.replaced_by if info else None
        if discontinued:
            extra = f", replaced by {replaced}" if replaced else ""
            findings.append(
                Finding(
                    "action",
                    f"{scan.repo.name}: {name} is discontinued{extra}",
                    scan.repo.name,
                    scan.repo.priority,
                    "package",
                )
            )
        retracted = bool(row and row.retracted)
        if info and locked and locked in info.retracted:
            retracted = True
        if retracted:
            version = locked or "current"
            findings.append(
                Finding(
                    "action",
                    f"{scan.repo.name}: {name} {version} is retracted",
                    scan.repo.name,
                    scan.repo.priority,
                    "package",
                )
            )
        if row and row.advisory:
            findings.append(
                Finding(
                    "watch",
                    f"{scan.repo.name}: {name} {locked or row.current} has a security advisory",
                    scan.repo.name,
                    scan.repo.priority,
                    "package",
                )
            )
        if row and row.major_behind:
            # Only Ready majors are bump recommendations. Blocked/unverified stay out.
            ready = is_ready(
                holds, package=name, latest=row.latest, repo=scan.repo.name
            )
            if not ready:
                continue
            findings.append(
                Finding(
                    "watch",
                    f"{scan.repo.name}: {name} {row.current} → {row.latest} (verified bump)",
                    scan.repo.name,
                    scan.repo.priority,
                    "package",
                )
            )
        elif row and row.is_outdated:
            if is_held(holds, package=name, latest=row.latest, repo=scan.repo.name):
                continue
            findings.append(
                Finding(
                    "info",
                    f"{scan.repo.name}: {name} {row.current} can update to {row.latest}",
                    scan.repo.name,
                    scan.repo.priority,
                    "package",
                )
            )
    return findings


def _drift_input(scan: RepoScan) -> DriftInput:
    flutter = scan.flutter
    flutter_cell = flutter.pinned_flutter or flutter.fvm_version or flutter.flutter_constraint or "—"
    packages = {
        name: scan.lock.get(name) or constraint
        for name, constraint in flutter.direct_dependencies.items()
    }
    if scan.android and scan.android.target_sdk:
        target = scan.android.target_sdk.label
    elif "android" in scan.repo.platforms:
        target = "unresolved"
    else:
        target = "—"
    if scan.ios:
        ios = scan.ios.label
    elif "ios" in scan.repo.platforms:
        ios = "unresolved"
    else:
        ios = "—"
    return DriftInput(
        name=scan.repo.name,
        priority=scan.repo.priority,
        flutter=flutter_cell,
        dart=flutter.dart_constraint or "—",
        target_sdk=target,
        ios=ios,
        packages=packages,
    )


def _priority_for(app: str, repos: list[Repo]) -> str:
    for repo in repos:
        if repo.name == app:
            return repo.priority
    return "normal"


def _notify(settings: Settings, status: dict, notify_fn) -> None:
    if not settings.notify or status["state"] == "ok":
        return
    if status["state"] == "degraded":
        message = (
            f"Vigil scan degraded ({status['action_count']} actions, "
            f"{len(status['errors'])} problems)"
        )
    else:
        message = f"Vigil: {status['action_count']} maintenance actions"
    if notify_fn is not None:
        notify_fn(message)
        return
    from vigil.notify import get_notifier

    report = Path(str(status["report_path"])) if status.get("report_path") else None
    get_notifier().notify("Vigil", message, report=report)


def external_alert_counts() -> dict[str, int]:
    """Hook for a future Dependabot or Sentry count. v1 does not call either."""
    return {}
