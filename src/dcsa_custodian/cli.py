from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .audit import audit_library
from .common import iter_jsonl, read_json, resolve_library_root, write_json
from .evals import evaluate_candidate
from .pipeline import audit_output, doctor_result, events_result, run_release
from .release import approve_candidate, build_candidate, publish_candidate, validate_candidate
from .semantic import semantic_search
from .wiki import build_graph, lint_report
from .events import CONSUMERS, acknowledge, acknowledgment_states


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "custodian.config.json"


def _settings(args: argparse.Namespace) -> tuple[dict, Path]:
    config_path = Path(args.config).resolve() if args.config else DEFAULT_CONFIG
    config = read_json(config_path)
    root = resolve_library_root(PROJECT_ROOT, config["library_root"], getattr(args, "library_root", None))
    return config, root


def _release_dir(config: dict, release_id: str) -> Path:
    import re
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", release_id):
        raise ValueError("invalid release ID")
    return PROJECT_ROOT / config.get("state_directory", ".custodian") / "releases" / release_id


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="DCSA Library Custodian")
    root.add_argument("--config")
    commands = root.add_subparsers(dest="command", required=True)
    regenerate = commands.add_parser('regenerate', help='Legacy recipe utility; new standalone rebuilds belong to dcsa-library-rebuilder')
    regenerate.add_argument('--recipe', type=Path, required=True)
    regenerate.add_argument('--destination', type=Path, required=True)
    provenance = commands.add_parser("import-provenance", help="Add reviewed provenance decisions from the Librarian's byte-verified ledger")
    provenance.add_argument("--library-root")
    provenance.add_argument("--ledger", type=Path, required=True)
    provenance.add_argument("--dry-run", action="store_true")
    bulk = commands.add_parser("doha-intake-plan", help="Build a hash-bound DOHA intake plan from a Librarian doha-acquire run; writes only --out")
    bulk.add_argument("--library-root")
    bulk.add_argument("--run", type=Path, required=True, help="Librarian quarantine/doha-acquire/<run> directory")
    bulk.add_argument("--not-held", type=Path, required=True, help="Librarian state/provenance/doha_not_in_library.jsonl")
    bulk.add_argument("--out", type=Path, required=True, help="New directory for the plan, its sources and text")
    bulk.add_argument("--group", choices=["hearings", "appeals"])
    bulk.add_argument("--era", choices=["post_sead4", "pre_sead4"])
    bulk.add_argument("--limit", type=int, help="Stop after this many planned decisions")
    bulk.add_argument("--pilot", type=int, help="Plan a spread sample of this many decisions")
    bulk.add_argument("--pdftotext", help="Path to pdftotext if it is not on PATH")
    voi = commands.add_parser("voi-intake-plan",
                              help="Build the reviewed intake plan for a Voice of Industry issue from a Librarian "
                                   "quarantine package; writes only --out, never the library")
    voi.add_argument("--library-root")
    voi.add_argument("--package", type=Path, required=True, help="The Librarian's <source file>.intake.json, beside its source")
    voi.add_argument("--out", type=Path, required=True, help="New (or empty) folder for the plan, robot text and parity report")
    voi.add_argument("--confirm-period", type=Path,
                     help="Librarian confirm-period marker (<librarian state>/watch/<job>/<YYYY-MM>.json) or its receipt")
    voi.add_argument("--reviewed-by", help="Name recorded as the reviewer; default names this command")
    voi.add_argument("--pdftotext", help="Path to pdftotext for the parity check if it is not on PATH")
    batches = commands.add_parser("doha-plan-batches", help="Split a DOHA intake plan into batches; a case stays in one batch")
    batches.add_argument("--plan", type=Path, required=True)
    batches.add_argument("--size", type=int, default=5500, help="Decisions per batch (a case is never split)")
    batches.add_argument("--out", type=Path, required=True)
    sample = commands.add_parser("doha-accuracy-sample", help="Seeded stratified sample of a DOHA plan for the owner to check against the PDFs")
    sample.add_argument("--plan", type=Path, required=True)
    sample.add_argument("--out", type=Path, required=True, help="New .csv sheet")
    sample.add_argument("--size", type=int, default=150, help="Decisions in the scored estimate")
    sample.add_argument("--edge", type=int, default=3, help="Extra unscored draws per rare stratum")
    sample.add_argument("--seed", type=int, default=20260927)
    score = commands.add_parser("doha-accuracy-score", help="Score a checked accuracy or disagreement sheet")
    score.add_argument("--sheet", type=Path, required=True)
    score.add_argument("--target", type=float, default=0.05, help="Highest acceptable error rate (95%% upper bound)")
    recheck = commands.add_parser("doha-recheck", help="Re-run the intake rules over held DOHA decisions; writes only --out")
    recheck.add_argument("--library-root")
    recheck.add_argument("--out", type=Path, required=True)
    recheck.add_argument("--not-held", type=Path, help="Librarian doha_not_in_library.jsonl, to link to decisions not held")
    recheck.add_argument("--size", type=int, default=150)
    recheck.add_argument("--edge", type=int, default=3)
    recheck.add_argument("--disagreements", type=int, default=100, help="Disagreements to sample for review")
    recheck.add_argument("--seed", type=int, default=20260927)
    append = commands.add_parser("doha-append-provenance", help="Add a batch's provenance rows to decisions/doha_source_urls.jsonl")
    append.add_argument("--additions", type=Path, required=True)
    append.add_argument("--dry-run", action="store_true")
    endings = commands.add_parser("doha-line-endings-plan",
                                  help="List every DOHA robot text with CRLF line ends as reviewed LF rewrites; reads the library only")
    endings.add_argument("--library-root")
    endings.add_argument("--out", type=Path, help="Default: decisions/doha_robot_line_endings.jsonl; never overwritten")
    endings.add_argument("--dry-run", action="store_true")
    for name in ("doctor", "audit", "build-candidate"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--library-root")
        if name in {"audit", "build-candidate"}:
            cmd.add_argument("--deep", action="store_true", help="Hash human artifacts for parity; reads bytes for maintenance only")
        if name == "audit":
            cmd.add_argument("--output")
        if name == "build-candidate":
            cmd.add_argument("--release-id")
            cmd.add_argument("--intake-plan", type=Path, help="Reviewed, hash-bound quarantine additions; stage before publication")
            cmd.add_argument("--rename-plan", type=Path, help="Reviewed renames of existing sources; stage before publication")
    release = commands.add_parser(
        "release", help="The whole gated sequence in one process: audit --deep, [voi-intake-plan], build-candidate --deep, "
                        "validate, evaluate, publish --dry-run, publish, doctor, events; stops at the first failed gate")
    release.add_argument("--library-root", required=True)
    release.add_argument("--release-id", required=True)
    release.add_argument("--package", type=Path, help="A Voice of Industry issue: the Librarian's <source file>.intake.json; "
                                                       "the plan is written to --out as voi-intake-plan writes it")
    release.add_argument("--out", type=Path, help="With --package: new (or empty) folder for the plan, robot text and parity report")
    release.add_argument("--confirm-period", type=Path, help="With --package: Librarian confirm-period marker or its receipt")
    release.add_argument("--reviewed-by", help="With --package: name recorded as the reviewer")
    release.add_argument("--pdftotext", help="With --package: path to pdftotext if it is not on PATH")
    release.add_argument("--intake-plan", type=Path, help="A reviewed intake plan, instead of --package")
    release.add_argument("--rename-plan", type=Path, help="A reviewed rename plan, instead of an intake")
    release.add_argument("--events-output", type=Path, help="Folder for events-<consumer>.json, one per consumer")
    release.add_argument("--stop-before-publish", action="store_true",
                         help="Stop after the dry run; publish, doctor and events are then run as single commands")
    release.add_argument("--allow-changes-outside-plan", action="store_true",
                         help="Publish although the candidate changes documents the intake plan does not add")
    release.add_argument("--reread", action="store_true",
                         help="Read every file again at every step, as the single commands run one after another do")
    validate = commands.add_parser("validate")
    validate.add_argument("--library-root")
    validate.add_argument("--release-id", required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--release-id", required=True)
    evaluate.add_argument("--eval-file")
    approve = commands.add_parser("approve")
    approve.add_argument("--release-id", required=True)
    approve.add_argument("--approved-by", required=True)
    approve.add_argument("--note", required=True)
    publish = commands.add_parser("publish")
    publish.add_argument("--library-root")
    publish.add_argument("--release-id", required=True)
    publish.add_argument("--dry-run", action="store_true", help="Stage and show publication changes without modifying the library")
    commands.add_parser("status")
    events = commands.add_parser("events", help="Recover and list pending verified release handoffs")
    events.add_argument("--library-root", required=True)
    events.add_argument("--consumer", choices=CONSUMERS, required=True)
    events.add_argument("--output", type=Path)
    ack = commands.add_parser("ack-event", help="Record completed agent review with hashed output artifacts")
    ack.add_argument("--library-root", required=True)
    ack.add_argument("--consumer", choices=CONSUMERS, required=True)
    ack.add_argument("--event-id", required=True)
    ack.add_argument("--receipt", type=Path, required=True)
    lint = commands.add_parser("lint", help="Lint the derived knowledge graph for corpus-wide contradictions")
    lint.add_argument("--library-root")
    lint.add_argument("--release-id", help="lint a candidate release; omit to lint the published library")
    lint.add_argument("--output", help="write the full report and derived graph to this path")
    lint.add_argument("--fail-on-priority", type=int, help="exit 2 when any finding is at or below this priority")
    lint.add_argument("--check", action="append", help="restrict output to these checks; repeatable")
    search = commands.add_parser("search")
    search.add_argument("--release-id", required=True)
    search.add_argument("--index", required=True, help="index filename, e.g. DCSA_CONTROLLING_AUTHORITY_CHUNKS_FTS.sqlite")
    search.add_argument("--query", required=True)
    search.add_argument("--top-k", type=int, default=5)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == 'regenerate':
            from .regenerate import regenerate
            print('Legacy Custodian recipe utility. For a new standalone rebuild use dcsa-library-rebuilder/agents/rebuilder.md. Creating a library does not install ongoing maintenance.', file=sys.stderr)
            print(json.dumps(regenerate(args.recipe, args.destination), indent=2))
            return 0
        config, library_root = _settings(args)
        if args.command == "import-provenance":
            from .decisions import provenance_decisions
            entry = read_json(library_root / "START_HERE_FOR_ROBOTS.json")
            records = {str(r["document_id"]): r for _, r in iter_jsonl(library_root / entry["documents"])}
            rows = [row for _, row in iter_jsonl(args.ledger)]
            path = PROJECT_ROOT / config.get("metadata_decisions_file", "decisions/metadata_decisions.json")
            payload = read_json(path)
            added = provenance_decisions(rows, records, payload["decisions"])
            if added and not args.dry_run:
                payload["decisions"].extend(added)
                # Keep the reviewed file's existing non-ASCII text readable in diffs.
                path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
            print(json.dumps({"ledger_rows": len(rows), "decisions_added": len(added), "dry_run": args.dry_run,
                              "next": "build-candidate --deep, validate, evaluate, publish" if added else None}, indent=2))
            return 0
        if args.command == "doha-intake-plan":
            from .doha_bulk import build_plan, pdftotext_extractor
            summary = build_plan(library_root, args.run.resolve(), args.not_held.resolve(), args.out.resolve(),
                                 pdftotext_extractor(args.pdftotext), group=args.group, era=args.era,
                                 limit=args.limit, pilot=args.pilot)
            print(json.dumps(summary, indent=2))
            return 0 if summary["counts"].get("planned") else 2
        if args.command == "voi-intake-plan":
            from .voi_intake import build_voi_plan, pdftotext_pages
            summary = build_voi_plan(library_root, args.package, args.out, pdftotext_pages(args.pdftotext),
                                     confirm_period=args.confirm_period, reviewed_by=args.reviewed_by)
            print(json.dumps(summary, indent=2))
            return 0
        if args.command in ("doha-plan-batches", "doha-accuracy-sample", "doha-accuracy-score",
                            "doha-recheck", "doha-append-provenance"):
            from . import doha_quality as quality
            if args.command == "doha-plan-batches":
                result = quality.split_plan(args.plan.resolve(), args.size, args.out.resolve())
            elif args.command == "doha-accuracy-sample":
                result = quality.accuracy_sample(args.plan.resolve(), args.out.resolve(), args.size, args.edge, args.seed)
            elif args.command == "doha-accuracy-score":
                result = quality.score_sheet(args.sheet.resolve(), args.target)
            elif args.command == "doha-recheck":
                result = quality.recheck_library(library_root, args.out.resolve(),
                                                 args.not_held.resolve() if args.not_held else None,
                                                 args.size, args.disagreements, args.edge, args.seed)
            else:
                target = PROJECT_ROOT / config.get("doha_provenance_file", "decisions/doha_source_urls.jsonl")
                result = quality.append_provenance(args.additions.resolve(), target, args.dry_run)
            print(json.dumps(result, indent=2))
            return 2 if result.get("passed") is False else 0
        if args.command == "doha-line-endings-plan":
            from .common import write_jsonl
            from .doha_release import plan_line_endings
            target = args.out.resolve() if args.out else PROJECT_ROOT / config.get("doha_line_endings_file", "decisions/doha_robot_line_endings.jsonl")
            if target.exists() and not args.dry_run:
                raise FileExistsError(f"reviewed line-ending rows already exist: {target}")
            rows, summary = plan_line_endings(library_root)
            if rows and not args.dry_run:
                write_jsonl(target, rows)
            print(json.dumps({**summary, "rows": len(rows), "written_to": None if args.dry_run or not rows else str(target),
                              "next": "review, then build-candidate --deep, validate, evaluate, publish --dry-run" if rows else None}, indent=2))
            return 2 if summary["refused"] else 0
        if args.command == "release":
            code, result = run_release(
                PROJECT_ROOT, config, library_root, args.release_id, lambda identity: _release_dir(config, identity),
                package=args.package, out=args.out, confirm_period=args.confirm_period, reviewed_by=args.reviewed_by,
                pdftotext=args.pdftotext, intake_plan=args.intake_plan, rename_plan=args.rename_plan,
                events_output=args.events_output.resolve() if args.events_output else None,
                stop_before_publish=args.stop_before_publish,
                allow_changes_outside_plan=args.allow_changes_outside_plan, reread=args.reread)
            print(json.dumps(result, indent=2))
            return code
        if args.command == "doctor":
            code, result = doctor_result(audit_library(library_root, deep=False), library_root)
            print(json.dumps(result, indent=2))
            return code
        if args.command == "audit":
            report = audit_library(library_root, deep=args.deep)
            output = Path(args.output).resolve() if args.output else audit_output(PROJECT_ROOT, config)
            write_json(output, report)
            print(json.dumps({"output": str(output), "summary": report["summary"], "quality_blockers": report["quality_blockers"]}, indent=2))
            return 0 if report["summary"]["integrity_healthy"] else 2
        if args.command == "build-candidate":
            result = build_candidate(PROJECT_ROOT, library_root, config, args.release_id, args.deep, args.intake_plan, args.rename_plan)
            print(json.dumps(result, indent=2))
            return 0 if result["validation"]["valid"] else 2
        if args.command == "validate":
            result = validate_candidate(library_root, _release_dir(config, args.release_id))
            print(json.dumps(result, indent=2))
            return 0 if result["valid"] else 2
        if args.command == "evaluate":
            eval_file = Path(args.eval_file).resolve() if args.eval_file else PROJECT_ROOT / "evals/golden_queries.json"
            result = evaluate_candidate(_release_dir(config, args.release_id), eval_file)
            print(json.dumps(result, indent=2))
            return 0 if result["passed"] else 2
        if args.command == "approve":
            result = approve_candidate(_release_dir(config, args.release_id), args.approved_by, args.note)
            print(json.dumps(result, indent=2))
            return 0
        if args.command == "publish":
            result = publish_candidate(PROJECT_ROOT, library_root, config, _release_dir(config, args.release_id), dry_run=args.dry_run)
            print(json.dumps(result, indent=2))
            return 0
        if args.command == "events":
            result = events_result(PROJECT_ROOT, config, library_root, args.consumer, lambda identity: _release_dir(config, identity))
            if args.output:
                write_json(args.output.resolve(), result)
            print(json.dumps(result, indent=2))
            return 0
        if args.command == "ack-event":
            result = acknowledge(PROJECT_ROOT, config, library_root, args.consumer, args.event_id, args.receipt.resolve())
            print(json.dumps(result, indent=2))
            return 0
        if args.command == "lint":
            enriched_relative = "ROBOT_READABLE_DIRECTORY/MANIFESTS/DOCUMENTS_ENRICHED.jsonl"
            if args.release_id:
                manifest = _release_dir(config, args.release_id) / "production" / enriched_relative
                source = f"candidate:{args.release_id}"
            else:
                manifest = library_root / enriched_relative
                source = "published"
            if not manifest.is_file():
                print(f"ERROR: enriched manifest not found: {manifest}", file=sys.stderr)
                return 2
            records = [record for _, record in iter_jsonl(manifest)]
            report = lint_report(records, source)
            if args.check:
                selected = set(args.check)
                report["findings"] = [item for item in report["findings"] if item["check"] in selected]
                report["filtered_to_checks"] = sorted(selected)
            if args.output:
                write_json(Path(args.output).resolve(), {**report, "graph": build_graph(records)})
            summary = {key: value for key, value in report.items() if key != "findings"}
            print(json.dumps({**summary, "findings": report["findings"]}, indent=2))
            if args.fail_on_priority is not None:
                return 2 if any(item["priority"] <= args.fail_on_priority for item in report["findings"]) else 0
            return 0
        if args.command == "search":
            db_path = _release_dir(config, args.release_id) / "indexes" / args.index
            if not db_path.is_file():
                print(f"ERROR: index not found: {db_path}", file=sys.stderr)
                return 2
            results = semantic_search(db_path, args.query, args.top_k)
            print(json.dumps({"query": args.query, "index": args.index, "results": results}, indent=2))
            return 0
        if args.command == "status":
            releases_root = PROJECT_ROOT / config.get("state_directory", ".custodian") / "releases"
            releases = []
            for path in sorted(releases_root.glob("*")) if releases_root.exists() else []:
                if path.is_dir():
                    releases.append({"release_id": path.name, "valid": (path / "VALIDATION.json").is_file() and read_json(path / "VALIDATION.json").get("valid"), "approved": (path / "APPROVAL.json").is_file()})
            pointer_path = library_root / "ROBOT_READABLE_DIRECTORY/STATE/CURRENT_CUSTODIAN_RELEASE.json"
            print(json.dumps({"releases": releases, "published": read_json(pointer_path) if pointer_path.is_file() else None,
                              "consumer_acknowledgments": acknowledgment_states(PROJECT_ROOT, config, library_root)}, indent=2))
            return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError, RuntimeError, PermissionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
