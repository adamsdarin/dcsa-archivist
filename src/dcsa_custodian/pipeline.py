"""The whole gated release sequence in one process: ``custodian.py release``.

The steps, their order, their gates and their exit codes are the documented ones:

    audit --deep, [voi-intake-plan], build-candidate --deep, validate, evaluate,
    publish --dry-run, publish, doctor, events (dcsa-compare, fso-guidance-watch)

Each step calls the same function the single command calls. The sequence stops at the
first step whose single command would have exited non-zero, with that exit code, and
nothing after it runs. What one process adds is that a file read and hashed by one step
is not read again by the next while it is the same file with the same size and
modification time (``runcache``), and that a result computed by one step for the same
bytes is not computed again. ``--reread`` turns the first of those off.

A run report is written to ``<state_directory>/reports/release_<release id>.json``:
every step, its exit code and time, what was reused and what it was bound to.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

from . import runcache
from .audit import approved_release_once, audit_library
from .common import read_json, utc_now, write_json
from .evals import evaluate_candidate
from .events import CONSUMERS, acknowledgment_states, comparison_report, pending_events, reconcile_event
from . import release as releases

# The failures every single command reports as "ERROR: ..." with exit code 2 (cli.main).
FAILURES = (OSError, ValueError, KeyError, json.JSONDecodeError, RuntimeError, PermissionError)


def doctor_result(report: dict[str, Any], library_root: Path) -> tuple[int, dict[str, Any]]:
    result = {"library_root": str(library_root), "integrity_healthy": report["summary"]["integrity_healthy"],
              "production_response_ready": report["summary"]["production_response_ready"],
              "quality_blockers": report["quality_blockers"], "release_metadata_errors": report["release_metadata_errors"],
              "verified_indexes": len(report["approved_indexes"]),
              # False when documents.jsonl and the published derived artifacts hold different
              # documents (a manifest edit outside a release, or a stale derived file).
              "derived_artifacts_agree": report["summary"]["derived_artifacts_agree"],
              "derived_artifact_drift": [item for item in report["derived_artifacts"]["artifacts"] if item["missing"] or item["stale"]],
              "collection_catalog_agrees": report["summary"]["collection_catalog_agrees"]}
    healthy = result["integrity_healthy"] and result["production_response_ready"] and result["derived_artifacts_agree"] is not False
    return (0 if healthy else 2), result


def audit_output(project_root: Path, config: dict[str, Any]) -> Path:
    return project_root / config.get("state_directory", ".custodian") / "reports" / \
        f"audit_{utc_now().replace(':', '').replace('+00:00', 'Z')}.json"


def events_result(project_root: Path, config: dict[str, Any], library_root: Path, consumer: str,
                  release_dir_of: Callable[[str], Path]) -> dict[str, Any]:
    current = approved_release_once(library_root)["release_id"]
    release = release_dir_of(current)
    if (release / "reports/RELEASE_CHANGES.json").is_file():
        reconcile_event(project_root, config, library_root, release)
    packets = pending_events(project_root, config, library_root, consumer)
    if consumer == "dcsa-compare":
        for packet in packets:
            packet["comparison"] = comparison_report(packet["changes"])
    # Acknowledged-with-gaps is not pending, and it is not silent either: it stays listed
    # here with the documents the library still lacks.
    with_gaps = [{"event_id": row["event_id"], **row["consumers"][consumer]}
                 for row in acknowledgment_states(project_root, config, library_root)
                 if row["consumers"][consumer]["state"] == "acknowledged_with_gaps"]
    return {"consumer": consumer, "pending": packets, "acknowledged_with_gaps": with_gaps,
            "status": "review_required" if packets else "no_pending_events",
            "legacy_release_without_event": not (release / "reports/RELEASE_CHANGES.json").is_file()}


def plan_scope(release_dir: Path, intake_plan: Path | None) -> dict[str, Any]:
    """The candidate's change set beside the reviewed plan's: what the Release Manager checks before publication."""
    changes = read_json(release_dir / "reports/RELEASE_CHANGES.json")["changes"]
    actual = sorted((change["document_id"], change["kind"]) for change in changes)
    if intake_plan is None:
        return {"checked": False, "changes": len(actual)}
    planned = sorted(str(item["record"]["document_id"]) for item in read_json(intake_plan)["items"])
    added = sorted(identity for identity, kind in actual if kind == "added")
    outside = [{"document_id": identity, "kind": kind} for identity, kind in actual
               if not (kind == "added" and identity in planned)]
    return {"checked": True, "planned_additions": planned, "missing_from_candidate": sorted(set(planned) - set(added)),
            "changes_outside_plan": outside, "matches": added == planned and not outside}


def run_release(project_root: Path, config: dict[str, Any], library_root: Path, release_id: str,
                release_dir_of: Callable[[str], Path], *, package: Path | None = None, out: Path | None = None,
                confirm_period: Path | None = None, reviewed_by: str | None = None, pdftotext: str | None = None,
                intake_plan: Path | None = None, rename_plan: Path | None = None, events_output: Path | None = None,
                stop_before_publish: bool = False, allow_changes_outside_plan: bool = False,
                reread: bool = False) -> tuple[int, dict[str, Any]]:
    if package is not None and (intake_plan is not None or rename_plan is not None):
        raise ValueError("give --package (the plan is written for you) or a plan, not both")
    if package is not None and out is None:
        raise ValueError("--package needs --out, a new or empty folder for the plan")
    state = project_root / config.get("state_directory", ".custodian")
    report_path = state / "reports" / f"release_{release_id}.json"
    run: dict[str, Any] = {"schema_version": "1.0", "release_id": release_id, "library_root": str(library_root),
                           "started_utc": utc_now(), "steps": [], "status": "running"}
    began = time.perf_counter()
    release_dir = release_dir_of(release_id)

    def finish(code: int, status: str, cache: runcache.RunCache) -> tuple[int, dict[str, Any]]:
        run.update(status=status, exit_code=code, finished_utc=utc_now(), seconds=round(time.perf_counter() - began, 1),
                   reuse=cache.summary())
        write_json(report_path, run)
        return code, {**run, "report": str(report_path)}

    with runcache.activate(trust_unchanged=not (reread or runcache.reread_requested())) as cache:
        def step(name: str, action: Callable[[], tuple[int, dict[str, Any]]]) -> int:
            started = time.perf_counter()
            print(f"[release] {name} ...", file=sys.stderr, flush=True)
            try:
                code, summary = action()
            except FAILURES as exc:
                code, summary = 2, {"error": str(exc)}
                print(f"ERROR: {exc}", file=sys.stderr)
            seconds = round(time.perf_counter() - started, 1)
            run["steps"].append({"step": name, "exit_code": code, "seconds": seconds, **summary})
            print(f"[release] {name}: exit {code} in {seconds}s", file=sys.stderr, flush=True)
            return code

        def audit() -> tuple[int, dict[str, Any]]:
            report = audit_library(library_root, deep=True)
            output = audit_output(project_root, config)
            write_json(output, report)
            return (0 if report["summary"]["integrity_healthy"] else 2), {
                "output": str(output), "summary": report["summary"], "quality_blockers": report["quality_blockers"]}

        plan_holder = {"intake": intake_plan}

        def plan() -> tuple[int, dict[str, Any]]:
            from .voi_intake import build_voi_plan, pdftotext_pages
            summary = build_voi_plan(library_root, package, out, pdftotext_pages(pdftotext),
                                     confirm_period=confirm_period, reviewed_by=reviewed_by)
            plan_holder["intake"] = Path(summary["plan"])
            return 0, {key: summary[key] for key in ("status", "plan", "document_id", "period", "robot_sha256")}

        def build() -> tuple[int, dict[str, Any]]:
            result = releases.build_candidate(project_root, library_root, config, release_id, True,
                                              plan_holder["intake"], rename_plan)
            validation = result["validation"]
            staging = release_dir / "reports/STAGING.json"
            return (0 if validation["valid"] else 2), {
                "release_directory": result["release_directory"], "valid": validation["valid"],
                "publishable": validation.get("publishable"), "errors": validation.get("errors", [])[:20],
                "publication_blockers": validation.get("publication_blockers", []),
                "staging": read_json(staging) if staging.is_file() else None}

        def validate() -> tuple[int, dict[str, Any]]:
            result = releases.validate_candidate(library_root, release_dir)
            return (0 if result["valid"] else 2), {
                "valid": result["valid"], "publishable": result.get("publishable"), "errors": result.get("errors", [])[:20],
                "validated_utc": result.get("validated_utc"), "reused": result.get("reused")}

        def evaluate() -> tuple[int, dict[str, Any]]:
            result = evaluate_candidate(release_dir, project_root / "evals/golden_queries.json")
            return (0 if result["passed"] else 2), {"passed": result["passed"], "passed_cases": result["passed_cases"],
                                                   "total_cases": result["total_cases"]}

        def scope() -> tuple[int, dict[str, Any]]:
            found = plan_scope(release_dir, plan_holder["intake"])
            stop = found["checked"] and not found["matches"] and not allow_changes_outside_plan
            if stop:
                print("ERROR: the candidate's change set is not exactly the reviewed plan's additions; inspect "
                      "reports/RELEASE_CHANGES.json, then publish with the single commands or pass "
                      "--allow-changes-outside-plan", file=sys.stderr)
            return (2 if stop else 0), found

        def dry_run() -> tuple[int, dict[str, Any]]:
            result = releases.publish_candidate(project_root, library_root, config, release_dir, dry_run=True)
            return 0, {key: result[key] for key in ("status", "changed_files", "retired_files", "unchanged_files", "validation")}

        def publish() -> tuple[int, dict[str, Any]]:
            result = releases.publish_candidate(project_root, library_root, config, release_dir)
            return 0, {"status": result["status"], "copied": result["copied"], "retired": result["retired"],
                       "rollback_snapshot": result["pointer"]["rollback_snapshot"],
                       "verified_indexes": result["verified_indexes"], "handoff": result["handoff"]}

        def doctor() -> tuple[int, dict[str, Any]]:
            return doctor_result(audit_library(library_root, deep=False), library_root)

        def events(consumer: str) -> Callable[[], tuple[int, dict[str, Any]]]:
            def run_events() -> tuple[int, dict[str, Any]]:
                result = events_result(project_root, config, library_root, consumer, release_dir_of)
                summary: dict[str, Any] = {"status": result["status"], "pending": [p["event"]["event_id"] for p in result["pending"]]}
                if events_output is not None:
                    target = events_output / f"events-{consumer}.json"
                    write_json(target, result)
                    summary["output"] = str(target)
                return 0, summary
            return run_events

        sequence: list[tuple[str, Callable[[], tuple[int, dict[str, Any]]]]] = [("audit --deep", audit)]
        if package is not None:
            sequence.append(("voi-intake-plan", plan))
        sequence += [("build-candidate --deep", build), ("validate", validate), ("evaluate", evaluate),
                     ("change set against the plan", scope), ("publish --dry-run", dry_run)]
        if not stop_before_publish:
            sequence += [("publish", publish), ("doctor", doctor)]
            sequence += [(f"events --consumer {consumer}", events(consumer)) for consumer in CONSUMERS]
        for name, action in sequence:
            code = step(name, action)
            if code:
                return finish(code, f"stopped at {name}", cache)
        return finish(0, "ready_to_publish" if stop_before_publish else "published", cache)
