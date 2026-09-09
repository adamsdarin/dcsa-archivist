from __future__ import annotations

import unittest
from unittest import mock

from dcsa_custodian import wiki
from dcsa_custodian.wiki import (
    build_edges,
    build_graph,
    build_topics,
    issuance_family,
    lint_graph,
    lint_report,
    normalize_domain,
    subject_for,
)


def record(document_id: str, **overrides) -> dict:
    base = {
        "document_id": document_id,
        "title": document_id,
        "collection_id": "dodi",
        "domain": "authorities",
        "current_status": "current",
        "authority_role": "binding_government_issuance",
        "authority_priority": 30,
        "answer_eligibility": "answer_eligible",
        "duplicate_of": None,
    }
    base.update(overrides)
    return base


class IssuanceFamilyTests(unittest.TestCase):
    def test_extracts_across_issuance_series(self) -> None:
        cases = {
            "32 CFR Part 117": "cfr:32.117",
            "DoD Instruction 5200.48": "dod:I.5200.48",
            "DoDM 5200.01 Volume 2": "dod:M.5200.01.2",
            "SEAD 4": "sead:4",
            "SEAD-3": "sead:3",
            "Executive Order 13556": "eo:13556",
            "E.O. 12968": "eo:12968",
            "ISL 2021-02": "isl:2021.02",
            "NIST SP 800-171A": "nist:800-171A",
            "ICD 705": "icd:705",
            "CNSSI 7003": "cnssi:7003",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                family, display = issuance_family({"title": title, "document_id": ""})
                self.assertEqual(family, expected)
                self.assertTrue(display)

    def test_editions_share_a_family_but_volumes_do_not(self) -> None:
        first, _ = issuance_family({"title": "DoDI 5200.48, 6 March 2020", "document_id": ""})
        second, _ = issuance_family({"title": "DoDI 5200.48 Change 1, 2024", "document_id": ""})
        self.assertEqual(first, second)
        volume_one, _ = issuance_family({"title": "DoDM 5200.01 Volume 1", "document_id": ""})
        volume_two, _ = issuance_family({"title": "DoDM 5200.01 Volume 2", "document_id": ""})
        self.assertNotEqual(volume_one, volume_two)

    def test_falls_back_to_document_id_then_gives_up(self) -> None:
        family, _ = issuance_family({"title": "Untitled scan", "document_id": "dcsa-sead-sead-4"})
        self.assertEqual(family, "sead:4")
        self.assertEqual(issuance_family({"title": "Insider Threat Poster", "document_id": "poster"}), (None, None))


class SubjectAxisTests(unittest.TestCase):
    def test_domain_casing_is_folded(self) -> None:
        self.assertEqual(normalize_domain("TRAINING_AND_AWARENESS"), "training_and_awareness")
        self.assertEqual(normalize_domain(None), "unknown")

    def test_subject_precedence_is_collection_then_family_then_domain(self) -> None:
        self.assertEqual(subject_for({"collection_id": "cui"}, "cfr:32.2002"), ("cui", "subject_bearing_collection"))
        self.assertEqual(
            subject_for({"collection_id": "dodi"}, "dod:I.5200.48"),
            ("issuance:dod:I.5200.48", "issuance_family"),
        )
        self.assertEqual(
            subject_for({"collection_id": "dodi", "domain": "AUTHORITIES"}, None),
            ("domain:authorities", "domain_fallback"),
        )


class EdgeTests(unittest.TestCase):
    def test_recorded_edges_carry_recorded_confidence(self) -> None:
        records = [
            record("dup", duplicate_of="canon", answer_eligibility_basis="identical_robot_content_sha256"),
            record("renamed", rename_history=[{"previous_human_source_path": "OLD.pdf", "reason": "cleanup"}]),
        ]
        by_type = {edge["edge_type"]: edge for edge in build_edges(records)}
        self.assertEqual(by_type["duplicate_of"]["confidence"], "recorded")
        self.assertEqual(by_type["duplicate_of"]["to_document_id"], "canon")
        self.assertEqual(by_type["renamed_from"]["confidence"], "recorded")
        self.assertEqual(by_type["renamed_from"]["to_path"], "OLD.pdf")

    def test_supersession_is_derived_within_a_family(self) -> None:
        records = [
            record("new", title="DoDI 5200.48 (2024)", current_status="current"),
            record("old", title="DoDI 5200.48 (2020)", current_status="superseded"),
        ]
        supersedes = [edge for edge in build_edges(records) if edge["edge_type"] == "supersedes"]
        self.assertEqual(len(supersedes), 1)
        self.assertEqual(supersedes[0]["from_document_id"], "new")
        self.assertEqual(supersedes[0]["to_document_id"], "old")
        self.assertEqual(supersedes[0]["confidence"], "derived")

    def test_no_supersession_edge_without_a_current_edition(self) -> None:
        records = [
            record("a", title="ISL 2011-01", current_status="rescinded"),
            record("b", title="ISL 2011-01 rev", current_status="historical"),
        ]
        self.assertFalse([edge for edge in build_edges(records) if edge["edge_type"] == "supersedes"])


class GraphTests(unittest.TestCase):
    def test_doha_is_excluded_and_counted(self) -> None:
        graph = build_graph([record("a"), record("case", collection_id="doha_decisions")])
        self.assertEqual(graph["manifest_records"], 2)
        self.assertEqual(graph["graphed_records"], 1)
        self.assertEqual(graph["excluded_doha_records"], 1)
        self.assertNotIn("case", [topic["anchor_document_id"] for topic in graph["topics"]])

    def test_topic_anchor_is_the_highest_authority_member(self) -> None:
        records = [
            record("guide", collection_id="cui", authority_role="official_operational_guidance", authority_priority=50),
            record("reg", collection_id="cui", authority_role="controlling_regulation", authority_priority=10),
        ]
        topic = next(item for item in build_topics(records) if item["topic_id"] == "cui")
        self.assertEqual(topic["anchor_document_id"], "reg")
        self.assertTrue(topic["has_controlling_authority"])


class LintTests(unittest.TestCase):
    def lint(self, records: list[dict]) -> list[dict]:
        return lint_graph(records, build_graph(records))

    def checks(self, records: list[dict]) -> set[str]:
        return {finding["check"] for finding in self.lint(records)}

    def test_domain_case_variant_is_reported_with_counts(self) -> None:
        records = [record("a", domain="TRAINING"), record("b", domain="training"), record("c", domain="training")]
        finding = next(item for item in self.lint(records) if item["check"] == "domain_case_variant")
        self.assertEqual(finding["priority"], 10)
        self.assertEqual(finding["variants"], {"TRAINING": 1, "training": 2})

    def test_single_casing_is_not_reported(self) -> None:
        records = [record("a", domain="training"), record("b", domain="training")]
        self.assertNotIn("domain_case_variant", self.checks(records))

    def test_unmapped_subject_is_reported_rather_than_accused(self) -> None:
        records = [record("guide", collection_id="cui", authority_role="official_operational_guidance")]
        with mock.patch.dict(wiki.SUBJECT_CONTROLLING_AUTHORITY, {}, clear=True):
            checks = self.checks(records)
        self.assertIn("subject_authority_unmapped", checks)
        self.assertNotIn("subject_without_controlling_authority", checks)

    def test_empty_mapping_is_a_settled_finding_not_silence(self) -> None:
        records = [record("guide", collection_id="cui", authority_role="official_operational_guidance")]
        with mock.patch.dict(wiki.SUBJECT_CONTROLLING_AUTHORITY, {"cui": []}, clear=True):
            checks = {item["check"] for item in self.lint(records)}
        self.assertIn("subject_has_no_contractor_controlling_authority", checks)
        self.assertNotIn("subject_authority_unmapped", checks)
        self.assertNotIn("subject_without_controlling_authority", checks)

    def test_curated_authority_ids_are_internally_consistent(self) -> None:
        for subject, ids in wiki.SUBJECT_CONTROLLING_AUTHORITY.items():
            with self.subTest(subject=subject):
                self.assertEqual(len(ids), len(set(ids)), "duplicate document_id in mapping")
                self.assertTrue(all(isinstance(item, str) and item for item in ids))

    def test_casing_check_reads_the_preserved_raw_domain(self) -> None:
        # Enrichment folds `domain` and keeps the original in `source_domain`. The check
        # must follow the raw value or it stops seeing the defect it exists to catch.
        records = [
            record("a", domain="training_and_awareness", source_domain="TRAINING_AND_AWARENESS"),
            record("b", domain="training_and_awareness", source_domain="training_and_awareness"),
        ]
        finding = next(item for item in self.lint(records) if item["check"] == "domain_case_variant")
        self.assertEqual(finding["variants"], {"TRAINING_AND_AWARENESS": 1, "training_and_awareness": 1})

    def test_mapped_subject_with_absent_authority_is_a_priority_10_gap(self) -> None:
        records = [record("guide", collection_id="cui", authority_role="official_operational_guidance")]
        with mock.patch.dict(wiki.SUBJECT_CONTROLLING_AUTHORITY, {"cui": ["cfr-2002"]}, clear=True):
            finding = next(item for item in self.lint(records) if item["check"] == "subject_without_controlling_authority")
        self.assertEqual(finding["priority"], 10)
        self.assertEqual(finding["missing_from_corpus"], ["cfr-2002"])

    def test_mapped_authority_present_but_ineligible_is_still_a_gap(self) -> None:
        records = [
            record("guide", collection_id="cui", authority_role="official_operational_guidance"),
            record("cfr-2002", collection_id="cui", authority_role="controlling_regulation",
                   answer_eligibility="unresolved_currency"),
        ]
        with mock.patch.dict(wiki.SUBJECT_CONTROLLING_AUTHORITY, {"cui": ["cfr-2002"]}, clear=True):
            finding = next(item for item in self.lint(records) if item["check"] == "subject_without_controlling_authority")
        self.assertEqual(finding["present_but_not_answer_eligible"], ["cfr-2002"])

    def test_mapped_and_eligible_authority_produces_no_gap(self) -> None:
        records = [
            record("guide", collection_id="cui", authority_role="official_operational_guidance"),
            record("cfr-2002", collection_id="cui", authority_role="controlling_regulation"),
        ]
        with mock.patch.dict(wiki.SUBJECT_CONTROLLING_AUTHORITY, {"cui": ["cfr-2002"]}, clear=True):
            checks = {item["check"] for item in self.lint(records)}
        self.assertNotIn("subject_without_controlling_authority", checks)
        self.assertNotIn("subject_authority_unmapped", checks)

    def test_historical_by_design_collections_do_not_report_missing_successors(self) -> None:
        legacy = [record("isl", title="ISL 2011-01", collection_id="isl_legacy", current_status="rescinded")]
        self.assertNotIn("superseded_without_successor", self.checks(legacy))

    def test_a_live_collection_with_no_current_edition_is_reported(self) -> None:
        stale = [record("nist", title="NIST SP 800-172", collection_id="nist", current_status="superseded")]
        self.assertIn("superseded_without_successor", self.checks(stale))

    def test_referencing_collections_do_not_count_as_a_filing_split(self) -> None:
        records = [
            record("inst", title="DoDI 5200.08", collection_id="dodi"),
            record("deck", title="DoDI 5200.08 training", collection_id="cdse_resources",
                   authority_role="training_or_context", authority_priority=70),
        ]
        self.assertNotIn("family_split_across_collections", self.checks(records))

    def test_two_holding_collections_are_a_filing_split(self) -> None:
        records = [
            record("a", title="SF 901", collection_id="forms"),
            record("b", title="SF 901", collection_id="cui"),
        ]
        finding = next(item for item in self.lint(records) if item["check"] == "family_split_across_collections")
        self.assertEqual(finding["holding_collections"], ["cui", "forms"])

    def test_effective_date_inversion_is_reported(self) -> None:
        records = [
            record("new", title="SEAD 4", current_status="current", effective_date="2017-06-08"),
            record("old", title="SEAD 4", current_status="superseded", effective_date="2021-08-12"),
        ]
        finding = next(item for item in self.lint(records) if item["check"] == "effective_date_inversion")
        self.assertEqual(finding["current_document_id"], "new")
        self.assertEqual(finding["superseded_document_id"], "old")

    def test_orphan_document_is_reported_once(self) -> None:
        records = [record("poster", title="Insider Threat Poster", collection_id="dodi", domain="odd")]
        orphans = [item for item in self.lint(records) if item["check"] == "orphan_document"]
        self.assertEqual([item["document_id"] for item in orphans], ["poster"])

    def test_findings_are_sorted_most_urgent_first(self) -> None:
        records = [
            record("a", domain="TRAINING"),
            record("b", domain="training"),
            record("poster", title="Poster", collection_id="dodi", domain="odd"),
        ]
        priorities = [item["priority"] for item in self.lint(records)]
        self.assertEqual(priorities, sorted(priorities))


class ReportTests(unittest.TestCase):
    def test_report_summarises_counts_and_source(self) -> None:
        report = lint_report([record("a", domain="TRAINING"), record("b", domain="training")], "published")
        self.assertEqual(report["source"], "published")
        self.assertEqual(report["manifest_records"], 2)
        self.assertEqual(sum(report["counts_by_check"].values()), len(report["findings"]))
        self.assertEqual(sum(report["counts_by_priority"].values()), len(report["findings"]))

    def test_report_is_deterministic_for_the_same_input(self) -> None:
        records = [record("a", title="SEAD 4"), record("b", title="SEAD 3", collection_id="sead")]
        first = lint_report(records, "published")
        second = lint_report(records, "published")
        self.assertEqual(first["findings"], second["findings"])
        self.assertEqual(first["edge_counts"], second["edge_counts"])


if __name__ == "__main__":
    unittest.main()
