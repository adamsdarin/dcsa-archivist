from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .audit import audit_library
from .common import iter_jsonl, read_json, resolve_library_root, utc_now, write_json
from .evals import evaluate_candidate
from .release import approve_candidate, build_candidate, publish_candidate, validate_candidate
from .semantic import semantic_search
from .wiki import build_graph, lint_report


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "custodian.config.json"


def _settings(args: argparse.Namespace) -> tuple[dict, Path]:
    config_path = Path(args.config).resolve() if args.config else DEFAULT_CONFIG
    config = read_json(config_path)
    root = resolve_library_root(PROJECT_ROOT, config["library_root"], getattr(args, "library_root", None))
    return config, root


def _release_dir(config: dict, release_id: str) -> Path:
    return PROJECT_ROOT / config.get("state_directory", ".custodian") / "releases" / release_id


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="DCSA Library Custodian")
    root.add_argument("--config")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("doctor", "audit", "build-candidate"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--library-root")
        if name in {"audit", "build-candidate"}:
            cmd.add_argument("--deep", action="store_true", help="Hash human artifacts for parity; reads bytes for maintenance only")
        if name == "audit":
            cmd.add_argument("--output")
        if name == "build-candidate":
            cmd.add_argument("--release-id")
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
        config, library_root = _settings(args)
        if args.command == "doctor":
            report = audit_library(library_root, deep=False)
            result = {"library_root": str(library_root), "integrity_healthy": report["summary"]["integrity_healthy"], "production_response_ready": report["summary"]["production_response_ready"], "quality_blockers": report["quality_blockers"], "release_metadata_errors": report["release_metadata_errors"], "verified_indexes": len(report["approved_indexes"])}
            print(json.dumps(result, indent=2))
            return 0 if result["integrity_healthy"] and result["production_response_ready"] else 2
        if args.command == "audit":
            report = audit_library(library_root, deep=args.deep)
            output = Path(args.output).resolve() if args.output else PROJECT_ROOT / config.get("state_directory", ".custodian") / "reports" / f"audit_{utc_now().replace(':', '').replace('+00:00', 'Z')}.json"
            write_json(output, report)
            print(json.dumps({"output": str(output), "summary": report["summary"], "quality_blockers": report["quality_blockers"]}, indent=2))
            return 0 if report["summary"]["integrity_healthy"] else 2
        if args.command == "build-candidate":
            result = build_candidate(PROJECT_ROOT, library_root, config, args.release_id, args.deep)
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
            print(json.dumps({"releases": releases, "published": read_json(pointer_path) if pointer_path.is_file() else None}, indent=2))
            return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError, RuntimeError, PermissionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
