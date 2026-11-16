"""The fast release path: parallel reading, linked staging, results computed once per run, one command.

Every test here is about a gate still failing when it should: a corrupted file, a stale
derived artifact and a manifest mismatch are caught after an earlier pass was kept.
"""
from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import stat
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from dcsa_custodian import doha_release, release, runcache, staging
from dcsa_custodian.audit import approved_release_once, audit_library
from dcsa_custodian.common import decode_text, hash_files, map_ordered, read_json, sha256_file, write_json
from dcsa_custodian.events import pending_events
from dcsa_custodian.intake import stage_intake
from dcsa_custodian.release import publish_candidate, validate_candidate
from dcsa_custodian.release_contract import POINTER, approved_release
import test_doha_era
import test_pipeline_gaps as gaps

ENRICHED = "ROBOT_READABLE_DIRECTORY/MANIFESTS/DOCUMENTS_ENRICHED.jsonl"
CHUNKS = "ROBOT_READABLE_DIRECTORY/CHUNKS/GENERAL_CITATION_SAFE_CHUNKS.jsonl"
MANIFEST = "ROBOT_READABLE_DIRECTORY/MANIFESTS/documents.jsonl"
RULE_TEXT = "ROBOT_READABLE_DIRECTORY/TEXT/AUTHORITIES/CFR/rule.txt"
RULE_PDF = "HUMAN_READABLE_DIRECTORY/AUTHORITIES/CFR/rule.pdf"
FAKE_VECTORS = dict(side_effect=lambda texts: [bytes(1536) for _ in texts])


def age(path: Path, seconds: int = 3600) -> None:
    """Give a file a modification time well in the past, as every long-held library file has."""
    past = time.time() - seconds
    os.utime(path, (past, past))


def age_tree(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file():
            age(path)


@contextlib.contextmanager
def environment(**values: str):
    saved = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in saved.items():
            os.environ.pop(key, None) if value is None else os.environ.__setitem__(key, value)


class ParallelReadingTests(gaps.Base):
    def test_parallel_hashes_are_the_serial_hashes_in_the_same_order(self) -> None:
        files = sorted(path for path in self.root.rglob("*") if path.is_file())
        self.assertGreater(len(files), 5)
        self.assertEqual(hash_files(files), [sha256_file(path) for path in files])
        with environment(DCSA_HASH_WORKERS="1"):
            self.assertEqual(hash_files(files), [sha256_file(path) for path in files])

    def test_the_first_failure_in_input_order_is_raised_as_a_serial_loop_raises_it(self) -> None:
        def fail_on_odd(value: int) -> int:
            if value % 2:
                raise ValueError(f"item {value}")
            return value
        self.assertEqual(map_ordered(fail_on_odd, [0, 2, 4]), [0, 2, 4])
        with self.assertRaisesRegex(ValueError, "item 3"):
            map_ordered(fail_on_odd, [0, 2, 3, 4, 5, 7])
        with self.assertRaises(FileNotFoundError):
            hash_files([self.root / RULE_TEXT, self.root / "absent.txt"])

    def test_bytes_decode_to_the_text_read_text_gives(self) -> None:
        sample = self.project / "sample.txt"
        for data in (b"TIER: 1\r\nSTATUS: current\r\n\r\nbody\rmore\n", b"caf\xc3\xa9 \xff broken \xe2\x82", b""):
            sample.write_bytes(data)
            self.assertEqual(decode_text(data), sample.read_text(encoding="utf-8", errors="replace"))

    def test_a_deep_audit_reports_the_same_thing_on_one_thread_and_on_many(self) -> None:
        self.publish_intake()
        (self.root / "HUMAN_READABLE_DIRECTORY/AUTHORITIES/CFR/gone.pdf").write_bytes(b"x")
        rows = [json.loads(line) for line in (self.root / MANIFEST).read_text(encoding="utf-8").splitlines()]
        # one record with a missing robot text, one with a missing human file, one off the tree, one short
        rows += [{**rows[0], "document_id": "no-robot", "robot_text_path": "ROBOT_READABLE_DIRECTORY/TEXT/absent.txt"},
                 {**rows[0], "document_id": "no-human", "human_source_path": "HUMAN_READABLE_DIRECTORY/absent.pdf"},
                 {**rows[0], "document_id": "escape", "robot_text_path": "LOCAL_INDEXES/x.txt"},
                 {"document_id": "short"}]
        (self.root / MANIFEST).write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8", newline="\n")

        def report(workers: str) -> dict:
            with environment(DCSA_HASH_WORKERS=workers), runcache.activate(False):
                found = audit_library(self.root, deep=True)
            found.pop("generated_utc")
            return found
        serial, parallel = report("1"), report("8")
        self.assertEqual(serial, parallel)
        self.assertEqual([error["code"] for error in serial["errors"]],
                         ["missing_robot", "missing_human_parity_artifact", "path_boundary", "manifest_missing_fields",
                          "broken_relationship_metadata"][:len(serial["errors"])])
        self.assertEqual(serial["human_hashes"]["rule"], sha256_file(self.root / RULE_PDF))


class LinkedStagingTests(gaps.Base):
    def snapshot(self) -> dict:
        return {str(path.relative_to(self.root)): (sha256_file(path), path.stat().st_mtime_ns)
                for path in self.root.rglob("*") if path.is_file()}

    def test_unchanged_files_are_links_and_every_file_the_intake_rewrites_is_a_copy(self) -> None:
        self.publish()
        plan, record = self.plan()
        destination = self.project / "staged"
        record_of_staging: dict = {}
        changed = stage_intake(self.root.resolve(), destination, plan, record_of_staging)
        self.assertEqual(record_of_staging["mode"], "hard_link")
        self.assertTrue(os.path.samefile(self.root / RULE_PDF, destination / RULE_PDF))
        self.assertTrue(os.path.samefile(self.root / RULE_TEXT, destination / RULE_TEXT))
        for relative in changed[:2]:  # both source manifests
            self.assertFalse(os.path.samefile(self.root / relative, destination / relative), relative)
        self.assertFalse((self.root / record["robot_text_path"]).exists())
        self.assertTrue((destination / record["robot_text_path"]).is_file())
        self.assertNotIn(MANIFEST, record_of_staging["guard"])
        self.assertIn(RULE_PDF, record_of_staging["guard"])
        self.assertEqual(staging.verify_untouched(self.root, record_of_staging)["changed"], 0)

    def test_an_intake_build_leaves_every_library_byte_and_timestamp_alone_and_records_how_it_staged(self) -> None:
        self.publish()
        plan, _ = self.plan()
        before = self.snapshot()
        result = self.build(plan)
        self.assertEqual(before, self.snapshot())
        self.assertTrue(result["validation"]["valid"])
        staged = read_json(Path(result["release_directory"]) / "reports/STAGING.json")
        self.assertEqual(staged["mode"], "hard_link")
        self.assertGreater(staged["linked"], 5)
        self.assertEqual(staged["library_untouched"], {"mode": "hard_link", "checked": staged["linked"], "changed": 0})
        self.assertNotIn("guard", staged)
        self.assertFalse(list((self.project / ".custodian").glob("intake-*")))

    def test_a_write_through_a_link_stops_the_build_before_the_candidate_is_sealed(self) -> None:
        self.publish()
        plan, _ = self.plan()
        real = release.build_chunks

        def writes_into_the_staged_root(root, records, *arguments):
            with (root / RULE_TEXT).open("ab") as handle:  # a defect: a build must never write to its root
                handle.write(b"\nwritten through the link\n")
            return real(root, records, *arguments)
        with patch("dcsa_custodian.release.build_chunks", side_effect=writes_into_the_staged_root):
            with self.assertRaisesRegex(RuntimeError, "library changed during the staged build"):
                self.build(plan, "written-through")
        candidate = self.project / ".custodian/releases/written-through"
        self.assertFalse((candidate / "RELEASE_MANIFEST.json").exists())
        self.assertEqual(validate_candidate(self.root, candidate), {"valid": False, "errors": ["missing RELEASE_MANIFEST.json"]})
        with self.assertRaises((OSError, RuntimeError, ValueError, KeyError)):
            publish_candidate(self.project, self.root, self.config, candidate)

    def test_a_read_only_library_file_is_copied_so_its_attribute_is_never_cleared(self) -> None:
        self.publish()
        plan, _ = self.plan()
        target = self.root / RULE_PDF
        os.chmod(target, stat.S_IREAD)
        self.addCleanup(os.chmod, target, stat.S_IWRITE | stat.S_IREAD)
        destination = self.project / "staged"
        stage_intake(self.root.resolve(), destination, plan)
        self.assertFalse(os.path.samefile(target, destination / RULE_PDF))
        self.assertEqual(sha256_file(target), sha256_file(destination / RULE_PDF))
        self.assertTrue(self.build(plan)["validation"]["valid"])
        self.assertFalse(os.access(target, os.W_OK))
        self.assertFalse(list((self.project / ".custodian").glob("intake-*")))

    def test_the_full_copy_is_still_available_and_builds_the_same_candidate(self) -> None:
        self.publish()
        plan, _ = self.plan()
        linked = Path(self.build(plan, "linked")["release_directory"])
        with environment(DCSA_STAGE_MODE="copy"):
            copied = Path(self.build(plan, "copied")["release_directory"])
        self.assertEqual(read_json(copied / "reports/STAGING.json")["mode"], "copy")
        for relative in (ENRICHED, CHUNKS, MANIFEST, "ROBOT_READABLE_DIRECTORY/MANIFESTS/relationships.jsonl"):
            self.assertEqual(sha256_file(linked / "production" / relative), sha256_file(copied / "production" / relative), relative)
        audits = [read_json(folder / "reports/PRODUCTION_AUDIT.json") for folder in (linked, copied)]
        self.assertEqual(audits[0]["human_hashes"], audits[1]["human_hashes"])


class ComputedOnceTests(gaps.Base):
    """A kept result is returned only while every input is proven the same; otherwise the gate runs and can fail."""

    def test_a_second_validation_is_reused_and_names_what_it_was_bound_to(self) -> None:
        first = validate_candidate(self.root, self.release)
        again = validate_candidate(self.root, self.release)
        self.assertTrue(first["valid"])
        reused = again.pop("reused")
        self.assertEqual({key: value for key, value in again.items()}, {key: value for key, value in first.items() if key != "reused"})
        bound = reused["bound_to"]
        self.assertGreater(bound["candidate_files"], 10)
        self.assertGreaterEqual(bound["library_files"], 2)  # the entry point and the rule's robot text at least
        self.assertEqual(bound["code_sha256"], runcache.code_fingerprint())
        self.assertRegex(bound["candidate_sha256"], "^[0-9a-f]{64}$")
        self.assertEqual(reused["validated_utc"], first["validated_utc"])

    def test_a_corrupted_candidate_file_is_caught_after_a_reused_validation(self) -> None:
        self.assertIn("reused", validate_candidate(self.root, self.release))
        chunks = self.release / "production" / CHUNKS
        data = chunks.read_bytes()
        chunks.write_bytes(data.replace(b"requirement", b"requiremenT", 1))  # same size, one byte different
        result = validate_candidate(self.root, self.release)
        self.assertNotIn("reused", result)
        self.assertFalse(result["valid"])
        self.assertTrue(any("release file hash mismatch" in error and "CHUNKS" in error for error in result["errors"]))
        self.assertTrue(any("chunk" in error for error in result["errors"]))
        with self.assertRaisesRegex(RuntimeError, "candidate validation failed"):
            self.publish()

    def test_a_corrupted_index_is_caught_after_a_reused_validation(self) -> None:
        self.assertIn("reused", validate_candidate(self.root, self.release))
        index = sorted((self.release / "indexes").glob("*.sqlite"))[0]
        with index.open("r+b") as handle:
            handle.seek(100)
            handle.write(b"\xff" * 64)
        try:
            result = validate_candidate(self.root, self.release)
        except sqlite3.DatabaseError:
            return  # a database too damaged to open stops validation outright, as it always did
        self.assertFalse(result["valid"])
        self.assertNotIn("reused", result)
        self.assertTrue(any("release file hash mismatch: indexes/" in error for error in result["errors"]))

    def test_a_manifest_mismatch_is_caught_after_a_reused_validation(self) -> None:
        self.assertIn("reused", validate_candidate(self.root, self.release))
        manifest = read_json(self.release / "RELEASE_MANIFEST.json")
        entry = next(item for item in manifest["files"] if item["path"].endswith("DOCUMENTS_ENRICHED.jsonl"))
        entry["sha256"] = "0" * 64
        write_json(self.release / "RELEASE_MANIFEST.json", manifest)
        result = validate_candidate(self.root, self.release)
        self.assertNotIn("reused", result)
        self.assertEqual([error for error in result["errors"] if "hash mismatch" in error],
                         [f"release file hash mismatch: {entry['path']}"])
        # a file the manifest lists and the candidate no longer holds is a mismatch too
        (self.release / "reports/WIKI_LINT.json").unlink()
        self.assertTrue(any("WIKI_LINT" in error for error in validate_candidate(self.root, self.release)["errors"]))

    def test_a_corrupted_library_text_is_caught_after_a_reused_validation(self) -> None:
        age_tree(self.root)
        age_tree(self.release)
        with runcache.activate(True) as cache:
            self.assertTrue(validate_candidate(self.root, self.release)["valid"])
            again = validate_candidate(self.root, self.release)
            self.assertIn("reused", again)
            self.assertGreater(cache.counts["files_not_reread"], 0)  # bound by identity, size and time, not read again
            text = self.root / RULE_TEXT
            text.write_bytes(text.read_bytes().replace(b"safeguarding", b"safeguardinG"))  # same size
            result = validate_candidate(self.root, self.release)
        self.assertNotIn("reused", result)
        self.assertFalse(result["valid"])
        self.assertTrue(any("chunk not found verbatim in robot source" in error for error in result["errors"]))
        with self.assertRaisesRegex(RuntimeError, "candidate validation failed"):
            self.publish()

    def test_a_file_is_not_read_twice_only_while_it_is_the_same_file_size_and_time(self) -> None:
        sample = self.project / "held.bin"
        sample.write_bytes(b"first contents")
        cache = runcache.RunCache(trust_unchanged=True)
        self.assertEqual(cache.sha256(sample), sha256_file(sample))
        self.assertEqual(cache.sha256(sample), sha256_file(sample))
        self.assertEqual(cache.counts["files_not_reread"], 0)  # just written: never taken on trust
        age(sample)
        first = cache.sha256(sample)
        self.assertEqual((cache.sha256(sample), cache.counts["files_not_reread"]), (first, 1))
        linked = self.project / "linked.bin"
        os.link(sample, linked)
        self.assertEqual((cache.sha256(linked), cache.counts["files_not_reread"]), (first, 2))  # the same file by another name
        sample.write_bytes(b"other contents")  # same size, new time
        self.assertEqual(cache.sha256(sample), sha256_file(sample))
        self.assertNotEqual(cache.sha256(sample), first)
        strict = runcache.RunCache(trust_unchanged=False)
        age(sample)
        strict.sha256(sample)
        strict.sha256(sample)
        self.assertEqual((strict.counts["files_read"], strict.counts["files_not_reread"]), (2, 0))

    def test_rereading_is_available_and_then_nothing_is_reused(self) -> None:
        with runcache.activate(False):
            self.assertNotIn("reused", validate_candidate(self.root, self.release))
            self.assertNotIn("reused", validate_candidate(self.root, self.release))
        with environment(DCSA_REREAD="1"):
            self.assertFalse(runcache.RunCache().trust_unchanged)
        self.assertTrue(runcache.RunCache().trust_unchanged)

    def test_a_failed_validation_is_never_kept(self) -> None:
        write_json(self.release / "reports/RETRIEVAL_EVALUATION.json", {"passed": False})
        for _ in range(2):
            result = validate_candidate(self.root, self.release)
            self.assertFalse(result["valid"])
            self.assertNotIn("reused", result)

    def test_the_publication_plan_records_whether_validation_was_reused(self) -> None:
        preview = publish_candidate(self.project, self.root, self.config, self.release, dry_run=True)
        self.assertEqual(preview["validation"]["reused"]["bound_to"]["code_sha256"], runcache.code_fingerprint())
        with runcache.activate(False):
            fresh = publish_candidate(self.project, self.root, self.config, self.release, dry_run=True)
        self.assertIsNone(fresh["validation"]["reused"])

    def test_corrupted_published_metadata_is_caught_after_a_kept_pass(self) -> None:
        self.publish_intake()
        age_tree(self.root)
        with runcache.activate(True) as cache:
            self.assertTrue(audit_library(self.root)["summary"]["production_response_ready"])
            self.assertTrue(audit_library(self.root)["summary"]["production_response_ready"])
            self.assertGreater(cache.counts["approved_release_reused"], 0)
            self.assertEqual(approved_release_once(self.root, check_integrity=True), approved_release(self.root, check_integrity=True))
            self.assertEqual(approved_release_once(self.root), approved_release(self.root))  # served from the stricter pass
            enriched = self.root / ENRICHED
            enriched.write_bytes(enriched.read_bytes().replace(b"new-voi", b"new-vox", 1))
            report = audit_library(self.root)
            self.assertFalse(report["summary"]["production_response_ready"])
            self.assertTrue(any("Published metadata hash mismatch" in error for error in report["release_metadata_errors"]))
            with self.assertRaisesRegex(ValueError, "Published metadata hash mismatch"):
                approved_release_once(self.root)

    def test_the_release_check_with_integrity_equals_the_contract_pass_and_fail(self) -> None:
        self.publish_intake()
        calls = (approved_release, approved_release_once)
        for trust in (False, True):
            with runcache.activate(trust):
                self.assertEqual(approved_release_once(self.root, check_integrity=True), approved_release(self.root, check_integrity=True))
                self.assertEqual(approved_release_once(self.root), approved_release(self.root))
        catalog = read_json(self.root / "ROBOT_READABLE_DIRECTORY/RETRIEVAL/INDEX_CATALOG.json")
        cases = ((self.root / catalog["indexes"][0]["production_path"], "Approved index hash mismatch"),
                 (self.root / "LOCAL_INDEXES/DOHA_CASE_TOPICS_FTS.sqlite", "Approved DOHA index hash mismatch"))
        for index, message in cases:
            original = index.read_bytes()
            with contextlib.closing(sqlite3.connect(index)) as db, db:
                db.execute("CREATE TABLE added_after_publication(x)")  # a sound database with other bytes
            for call in calls:
                with runcache.activate(True):
                    with self.assertRaisesRegex(ValueError, message):
                        call(self.root, check_integrity=True)
                    self.assertEqual(call(self.root)["release_id"], "intake-test")  # the plain check does not hash indexes
            index.write_bytes(b"not a database".ljust(len(original), b"\0"))  # same size, unreadable
            for call in calls:
                with runcache.activate(True):
                    with self.assertRaises((ValueError, sqlite3.Error)):
                        call(self.root, check_integrity=True)
            index.write_bytes(original)
            for call in calls:
                with runcache.activate(True):
                    self.assertEqual(call(self.root, check_integrity=True)["release_id"], "intake-test")

    def test_a_corrupted_published_index_is_caught_after_a_kept_pass(self) -> None:
        self.publish()
        age_tree(self.root)
        with runcache.activate(True) as cache:
            self.assertTrue(audit_library(self.root)["summary"]["integrity_healthy"])
            self.assertTrue(audit_library(self.root)["summary"]["integrity_healthy"])
            self.assertGreater(cache.counts["index_health_reused"], 0)
            index = self.root / read_json(self.root / "ROBOT_READABLE_DIRECTORY/RETRIEVAL/INDEX_CATALOG.json")["indexes"][0]["production_path"]
            size = index.stat().st_size
            index.write_bytes(b"not a database".ljust(size, b"\0"))  # same size
            report = audit_library(self.root)
        self.assertFalse(report["summary"]["integrity_healthy"])
        self.assertIn("approved_index_failure", [error["code"] for error in report["errors"]])
        self.assertTrue(report["release_metadata_errors"])

    def test_a_stale_derived_artifact_is_caught_after_a_kept_pass(self) -> None:
        self.publish_intake()
        age_tree(self.root)
        with runcache.activate(True):
            self.assertIs(audit_library(self.root)["summary"]["derived_artifacts_agree"], True)
            chunks = self.root / CHUNKS
            kept = [line for line in chunks.read_text(encoding="utf-8").splitlines() if '"new-voi"' not in line]
            chunks.write_text("".join(line + "\n" for line in kept), encoding="utf-8", newline="\n")
            report = audit_library(self.root)
            self.assertIs(report["summary"]["derived_artifacts_agree"], False)
            self.assertEqual(self.run_cli("doctor")[0], 2)


class DohaComputedOnceTests(unittest.TestCase):
    fixture = test_doha_era.ReleaseTests()

    def test_decisions_are_classified_the_same_on_one_thread_and_on_many_and_once_per_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "library"
            root.mkdir()
            self.fixture.make_library(root)
            with environment(DCSA_HASH_WORKERS="1"), runcache.activate(False):
                serial = doha_release.classify_rows(root, {}, {})
            with runcache.activate(False) as cache:
                parallel = doha_release.classify_rows(root, {}, {})
                self.assertEqual(serial, parallel)
                self.assertEqual(cache.counts["doha_classify_computed"], len(serial))
                doha_release.classify_rows(root, {}, {})
                self.assertEqual(cache.counts["doha_classify_reused"], len(serial))  # read again, not classified again
                self.assertEqual(cache.counts["files_not_reread"], 0)
            self.assertEqual({row["document_id"]: row["sead4_era"] for row in serial},
                             {"late-2016-case": "post_sead4", "day-before": "pre_sead4",
                              "effective-day": "post_sead4", "typo-header": "post_sead4"})

    def test_worker_processes_classify_exactly_as_this_process_does_and_a_failed_pool_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "library"
            root.mkdir()
            self.fixture.make_library(root)
            with environment(DCSA_CLASSIFY_PROCESSES="0"), runcache.activate(False):
                here = doha_release.classify_rows(root, {}, {})
            with environment(DCSA_CLASSIFY_PROCESSES="2"), runcache.activate(False) as cache:
                there = doha_release.classify_rows(root, {}, {})
                self.assertEqual(cache.counts["doha_classified_on_processes"], len(here))
            self.assertEqual(here, there)
            with environment(DCSA_CLASSIFY_PROCESSES="2"), runcache.activate(False) as cache, \
                    patch("concurrent.futures.ProcessPoolExecutor.submit", side_effect=OSError(6, "The handle is invalid")):
                fallback = doha_release.classify_rows(root, {}, {})
                self.assertEqual(cache.counts["doha_classify_pool_failed"], 1)
            self.assertEqual(here, fallback)
            # a review that cannot be applied raises from a worker exactly as it does here
            bad = {"late-2016-case": {"document_id": "late-2016-case", "reviewed_by": "", "reviewed_utc": "x", "evidence": "y"}}
            for processes in ("0", "2"):
                with environment(DCSA_CLASSIFY_PROCESSES=processes), runcache.activate(False):
                    with self.assertRaisesRegex(ValueError, "requires reviewed_by"):
                        doha_release.classify_rows(root, bad, {})

    def test_a_changed_decision_text_is_caught_after_a_reused_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with runcache.activate(True):
                root, result = self.fixture.build(Path(temp))
                candidate = Path(result["release_directory"])
                self.assertTrue(result["validation"]["valid"], result["validation"]["errors"])
                age_tree(root)
                age_tree(candidate)
                self.assertTrue(validate_candidate(root, candidate)["valid"])
                self.assertIn("reused", validate_candidate(root, candidate))
                text = next(root.rglob("day-before.txt"))
                text.write_bytes(text.read_bytes().replace(b"06/07/2017", b"06/09/2017"))  # same size, another era
                changed = validate_candidate(root, candidate)
                self.assertNotIn("reused", changed)
                self.assertFalse(changed["valid"])
                self.assertTrue(any("era differs from the decision-date classification" in error for error in changed["errors"]))
                self.assertTrue(any("differ" in error and "robot text" in error for error in changed["errors"]))

    def test_a_changed_doha_index_is_queried_again(self) -> None:
        import sqlite3
        with tempfile.TemporaryDirectory() as temp:
            with runcache.activate(True):
                root, result = self.fixture.build(Path(temp))
                candidate = Path(result["release_directory"])
                age_tree(root)
                age_tree(candidate)
                self.assertTrue(validate_candidate(root, candidate)["valid"])
                staged = candidate / "production" / doha_release.CONTENT
                self.assertTrue(staged.is_file())  # the fixture's eras are corrected, so the candidate carries the index
                with contextlib.closing(sqlite3.connect(staged)) as db, db:
                    db.execute("UPDATE decisions SET current_group='PRE_SEAD_4' WHERE document_id='late-2016-case'")
                errors = validate_candidate(root, candidate)["errors"]
                self.assertTrue(any("disagrees with the era manifest" in error for error in errors))


class OneCommandTests(gaps.Base):
    STEPS = ["audit --deep", "build-candidate --deep", "validate", "evaluate", "change set against the plan",
             "publish --dry-run", "publish", "doctor", "events --consumer dcsa-compare", "events --consumer fso-guidance-watch"]

    def one_command(self, *arguments: str) -> tuple[int, dict]:
        # the fixture's project folder stands in for the repository (its decisions and golden queries)
        with patch("dcsa_custodian.release.embed_texts", **FAKE_VECTORS), patch.object(gaps.cli, "PROJECT_ROOT", self.project):
            return self.run_cli("release", "--library-root", str(self.root), *arguments)

    def single(self, *arguments: str) -> tuple[int, dict]:
        with patch.object(gaps.cli, "PROJECT_ROOT", self.project):
            return self.run_cli(*arguments)

    def test_one_command_runs_every_gate_in_order_publishes_and_records_what_it_reused(self) -> None:
        self.publish()
        plan, record = self.plan()
        age_tree(self.root)
        outputs = self.project / "packets"
        code, run = self.one_command("--release-id", "one-command", "--intake-plan", str(plan), "--events-output", str(outputs))
        self.assertEqual(code, 0, run)
        self.assertEqual([step["step"] for step in run["steps"]], self.STEPS)
        self.assertEqual({step["exit_code"] for step in run["steps"]}, {0})
        self.assertEqual(run["status"], "published")
        steps = {step["step"]: step for step in run["steps"]}
        self.assertEqual(steps["build-candidate --deep"]["staging"]["mode"], "hard_link")
        self.assertIsNotNone(steps["validate"]["reused"])  # the build validated these same bytes
        self.assertIsNotNone(steps["publish --dry-run"]["validation"]["reused"])
        self.assertEqual(steps["change set against the plan"]["matches"], True)
        self.assertGreater(run["reuse"]["files_not_reread"], 0)
        self.assertTrue(run["reuse"]["trust_unchanged_files"])
        self.assertEqual(read_json(Path(run["report"]))["status"], "published")
        # the library is where the single commands would have left it
        self.assertEqual(read_json(self.root / POINTER)["release_id"], "one-command")
        self.assertEqual(approved_release(self.root, check_integrity=True)["release_id"], "one-command")
        self.assertTrue((self.root / record["robot_text_path"]).is_file())
        self.assertEqual(self.run_cli("doctor")[0], 0)
        for consumer in ("dcsa-compare", "fso-guidance-watch"):
            self.assertIn("one-command", [p["event"]["event_id"] for p in pending_events(self.project, self.config, self.root, consumer)])
            self.assertEqual(read_json(outputs / f"events-{consumer}.json")["status"], "review_required")

    def test_rereading_at_every_step_reaches_the_same_published_library(self) -> None:
        self.publish()
        plan, _ = self.plan()
        age_tree(self.root)
        code, run = self.one_command("--release-id", "reread", "--intake-plan", str(plan), "--reread")
        self.assertEqual((code, run["status"]), (0, "published"))
        self.assertFalse(run["reuse"]["trust_unchanged_files"])
        self.assertNotIn("files_not_reread", run["reuse"])
        self.assertIsNone({step["step"]: step for step in run["steps"]}["validate"]["reused"])
        self.assertEqual(approved_release(self.root, check_integrity=True)["release_id"], "reread")

    def test_the_sequence_stops_at_the_first_failed_gate_with_that_commands_exit_code(self) -> None:
        self.publish()
        plan, _ = self.plan()
        (self.root / RULE_TEXT).unlink()
        code, run = self.one_command("--release-id", "blocked", "--intake-plan", str(plan))
        self.assertEqual(code, 2)
        self.assertEqual([(step["step"], step["exit_code"]) for step in run["steps"]], [("audit --deep", 2)])
        self.assertEqual(run["status"], "stopped at audit --deep")
        self.assertFalse((self.project / ".custodian/releases/blocked").exists())

    def test_a_failed_evaluation_stops_the_run_and_nothing_is_published(self) -> None:
        self.publish()
        plan, _ = self.plan()
        write_json(self.project / "evals/golden_queries.json",
                   {"cases": [{"id": "new-required", "query": "absentnewrequirement", "require_hit": True}]})
        pointer = sha256_file(self.root / POINTER)
        code, run = self.one_command("--release-id", "fails-evaluation", "--intake-plan", str(plan))
        self.assertEqual(code, 2)
        self.assertEqual(run["steps"][-1]["step"], "build-candidate --deep")
        self.assertTrue(any("retrieval evaluation" in error for error in run["steps"][-1]["errors"]), run["steps"][-1])
        self.assertEqual(sha256_file(self.root / POINTER), pointer)
        self.assertNotIn("publish", [step["step"] for step in run["steps"]])

    def test_a_refused_plan_stops_at_the_build_as_the_single_command_does(self) -> None:
        self.publish()
        plan, _ = self.plan()
        broken = read_json(plan)
        broken["items"][0]["review"].pop("parity")
        write_json(plan, broken)
        code, run = self.one_command("--release-id", "refused", "--intake-plan", str(plan))
        self.assertEqual(code, 2)
        self.assertEqual(run["steps"][-1]["step"], "build-candidate --deep")
        self.assertIn("parity", run["steps"][-1]["error"])

    def test_stopping_before_publication_leaves_the_library_alone_and_the_single_commands_finish(self) -> None:
        self.publish()
        plan, _ = self.plan()
        before = {str(p.relative_to(self.root)): sha256_file(p) for p in self.root.rglob("*") if p.is_file()}
        code, run = self.one_command("--release-id", "paused", "--intake-plan", str(plan), "--stop-before-publish")
        self.assertEqual((code, run["status"]), (0, "ready_to_publish"))
        self.assertEqual(run["steps"][-1]["step"], "publish --dry-run")
        self.assertEqual(before, {str(p.relative_to(self.root)): sha256_file(p) for p in self.root.rglob("*") if p.is_file()})
        self.assertEqual(self.single("publish", "--library-root", str(self.root), "--release-id", "paused")[0], 0)
        self.assertEqual(read_json(self.root / POINTER)["release_id"], "paused")
        self.assertEqual(self.run_cli("doctor")[0], 0)

    def test_changes_the_plan_does_not_add_stop_the_run_before_publication_unless_allowed(self) -> None:
        self.publish()
        plan, _ = self.plan()
        rows = [json.loads(line) for line in (self.root / MANIFEST).read_text(encoding="utf-8").splitlines()]
        rows[0]["title"] = "A title edited outside any plan"
        (self.root / MANIFEST).write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8", newline="\n")
        pointer = sha256_file(self.root / POINTER)
        code, run = self.one_command("--release-id", "out-of-scope", "--intake-plan", str(plan))
        self.assertEqual(code, 2)
        self.assertEqual(run["steps"][-1]["step"], "change set against the plan")
        self.assertEqual(run["steps"][-1]["changes_outside_plan"], [{"document_id": "rule", "kind": "changed"}])
        self.assertEqual(sha256_file(self.root / POINTER), pointer)
        code, run = self.one_command("--release-id", "allowed", "--intake-plan", str(plan), "--allow-changes-outside-plan")
        self.assertEqual((code, run["status"]), (0, "published"))


if __name__ == "__main__":
    unittest.main()
