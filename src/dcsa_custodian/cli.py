from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .audit import audit_library
from .common import read_json, resolve_library_root, utc_now, write_json
from .evals import evaluate_candidate
from .release import approve_candidate, build_candidate, publish_candidate, validate_candidate


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
    commands.add_parser("status")
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        config, library_root = _settings(args)
        if args.command == "doctor":
            report = audit_library(library_root, deep=False)
            result = {"library_root": str(library_root), "integrity_healthy": report["summary"]["integrity_healthy"], "production_response_ready": report["summary"]["production_response_ready"], "quality_blockers": report["quality_blockers"]}
            print(json.dumps(result, indent=2))
            return 0 if result["integrity_healthy"] else 2
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
            result = publish_candidate(PROJECT_ROOT, library_root, config, _release_dir(config, args.release_id))
            print(json.dumps(result, indent=2))
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
