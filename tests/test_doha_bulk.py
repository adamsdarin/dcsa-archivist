"""A Librarian doha-acquire run becomes an intake plan stage_intake accepts; doubtful decisions become exceptions.

Decision texts, case numbers and URLs here are synthetic. The extractor is replaced
by one that returns prepared text, so pdftotext is not needed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from dcsa_custodian.common import iter_jsonl, read_json, sha256_file, write_json, write_jsonl
from dcsa_custodian.doha import MANIFEST, TAXONOMY, append_cases
from dcsa_custodian.doha_bulk import build_plan, identity, outcome, topics
from dcsa_custodian.intake import stage_intake

DOHA = "https://doha.ogc.osd.mil/Industrial-Security-Program/Industrial-Security-Clearance-Decisions"
TAXONOMY_BODY = {"schema_version": "1.0", "guidelines": {
    "B": {"label": "Foreign Influence", "aliases": ["foreign influence"]},
    "C": {"label": "Foreign Preference", "aliases": ["foreign preference"]},
    "F": {"label": "Financial Considerations", "aliases": ["financial considerations", "delinquent debt"]}}}
FILLER = "\nThe record was reviewed in full and the applicable guidelines were applied.\n" * 6


def hearing(case: str, level: str, date: str, keyword: str, conclusion: str) -> str:
    return (f"KEYWORD: {keyword}\n\nDIGEST: Synthetic digest.\n\nCASENO: {case}.{level}\n\nDATE: {date}\n\n"
            f"In the matter of: ISCR Case No. {case}\n\nDecision\n{FILLER}\nConclusion\n{conclusion}\n")


def appeal(case: str, date: str, keyword: str, order: str) -> str:
    return (f"KEYWORD: {keyword}\n\nDIGEST: Synthetic digest. {order}\n\nCASENO: {case}.a1\n\nDATE: {date}\n\n"
            f"ISCR Case No. {case}\n\nAPPEAL BOARD DECISION\n{FILLER}\nOrder\n{order}\n")


TEXTS = {
    "19-01234.h1": hearing("19-01234", "h1", "01/15/2020", "Guideline F",
                           "National security eligibility for access to classified information is denied."),
    "06-25928.a1": appeal("06-25928", "04/09/2008", "Guideline C; Guideline B",
                          "The Judge's adverse security clearance decision is REMANDED."),
    "07-00001.h1": hearing("07-00001", "h1", "11/20/2007", "Foreign Preference; Foreign Influence",
                           "Eligibility for access to classified information is granted."),
    "20-00002.h1": hearing("20-00002", "h1", "03/03/2021", "Guideline F",
                           "Eligibility is granted. Eligibility is denied."),
    "20-00003.h1": hearing("20-99999", "h1", "03/03/2021", "Guideline F",
                           "Eligibility for access to classified information is denied."),
    "20-00004.h1": "",
    "18-00005.h1": hearing("18-00005", "h1", "05/05/2019", "Guideline F",
                           "Eligibility for access to classified information is denied."),
}


class DohaBulkTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.library, self.run, self.out, self.staged = base / "library", base / "run", base / "plan", base / "staged"
        manifests = self.library / "ROBOT_READABLE_DIRECTORY/MANIFESTS"
        manifests.mkdir(parents=True)
        write_json(self.library / TAXONOMY, TAXONOMY_BODY)
        write_jsonl(manifests / "documents.jsonl", [])
        write_jsonl(manifests / "relationships.jsonl", [])
        # One decision the library already holds, stored the way the Archivist stores it.
        robot = self.library / "ROBOT_READABLE_DIRECTORY/TEXT/PERSONNEL_VETTING/DOHA_DECISIONS/POST_SEAD_4/18-00005.h1_denied_F.txt"
        robot.parent.mkdir(parents=True)
        robot.write_text("Synthetic held decision text.", encoding="utf-8")
        append_cases(self.library, [{
            "document_id": "held", "collection_id": "doha_decisions", "authority_tier": 5,
            "current_status": "historical_case_research",
            "human_source_path": "HUMAN_READABLE_DIRECTORY/PERSONNEL_VETTING/DOHA_DECISIONS/POST_SEAD_4/18-00005.h1_denied_F.pdf",
            "robot_text_path": robot.relative_to(self.library).as_posix(), "robot_sha256": sha256_file(robot),
            "doha_review": {"case_id": "18-00005", "decision_level": "h1", "decision_date": "2019-05-05",
                            "current_group": "POST_SEAD_4", "outcome": "denied", "guidelines": ["F"],
                            "answer_eligible": True, "reviewed_by": "synthetic", "reviewed_utc": "2026-09-01T00:00:00Z",
                            "metadata_basis": "synthetic"}}], TAXONOMY_BODY)
        write_json(self.library / "START_HERE_FOR_ROBOTS.json", {
            "documents": "ROBOT_READABLE_DIRECTORY/MANIFESTS/documents.jsonl",
            "relationships": "ROBOT_READABLE_DIRECTORY/MANIFESTS/relationships.jsonl"})
        self.texts = dict(TEXTS)
        self.not_held = base / "not_held.jsonl"
        self.listings: list[dict] = []
        for key in TEXTS:
            self.add(key, TEXTS[key])

    def add(self, key: str, text: str | None, title: str = "Synthetic listing") -> None:
        """A decision in the acquisition run (or, with text None, only on a DOHA listing)."""
        url = f"{DOHA}/ISCR-Hearing-Decisions/Listing/FileId/{abs(hash(key)) % 10**6}/"
        if text is not None:
            self.texts[key] = text
            folder = self.run / ("doha-appeal-board-decisions" if ".a" in key else "iscr-hearing-decisions")
            folder.mkdir(parents=True, exist_ok=True)
            body = f"%PDF-1.5 synthetic {key}".encode()
            (folder / f"{key}.pdf").write_bytes(body)
            write_json(folder / f"{key}.pdf.intake.json", {
                "submission_id": key, "producer_id": "dcsa-librarian", "retrieved_at": "2026-09-25T15:12:00Z",
                "requested_source_uri": url, "resolved_source_uri": url, "source_filename": f"{key}.pdf",
                "mime_type": "application/pdf", "source_sha256": hashlib.sha256(body).hexdigest(),
                "source_bytes": len(body), "approval_state": "quarantined_unreviewed", "publisher_claim": f"{key}.pdf"})
        self.listings.append({"case_key": key, "listing_titles": [title], "urls_by_format": {"pdf": [url]},
                              "captured_utc": "2026-09-22T00:00:00Z"})
        write_jsonl(self.not_held, self.listings)

    def extract(self, source: Path, target: Path) -> None:
        target.write_text(self.texts[source.stem], encoding="utf-8")

    def build(self, **kwargs):
        return build_plan(self.library, self.run, self.not_held, self.out, self.extract, **kwargs)

    def test_the_plan_is_accepted_by_stage_intake(self) -> None:
        summary = self.build()
        self.assertEqual(summary["counts"]["planned"], 3)
        plan = read_json(self.out / "intake-plan.json")
        changed = stage_intake(self.library, self.staged, self.out / "intake-plan.json")
        self.assertIn(MANIFEST, changed)
        staged = {row["document_id"] for _, row in iter_jsonl(self.staged / MANIFEST)}
        self.assertEqual(staged - {"held"}, {item["record"]["document_id"] for item in plan["items"]})
        self.assertEqual([row["document_id"] for _, row in iter_jsonl(self.library / MANIFEST)], ["held"],
                         "the library must not be written")

    def test_metadata_follows_the_text_and_existing_conventions(self) -> None:
        self.build()
        records = {item["record"]["doha_review"]["case_id"]: item["record"]
                   for item in read_json(self.out / "intake-plan.json")["items"]}
        post = records["19-01234"]
        self.assertEqual(post["document_id"], "dcsa-doha_decisions-pdf-s-19-01234-h1_denied_f")
        self.assertEqual(post["human_source_path"],
                         "HUMAN_READABLE_DIRECTORY/PERSONNEL_VETTING/DOHA_DECISIONS/POST_SEAD_4/19-01234.h1_denied_F.pdf")
        self.assertEqual(post["doha_review"]["decision_date"], "2020-01-15")
        self.assertTrue(post["doha_review"]["answer_eligible"])
        self.assertEqual(post["authority_tier"], 5)
        remand = records["06-25928"]["doha_review"]
        self.assertEqual((remand["outcome"], remand["guidelines"], remand["answer_eligible"]), ("remanded", ["B", "C"], False))
        old = records["07-00001"]["doha_review"]
        self.assertEqual((old["current_group"], old["outcome"], old["guidelines"]), ("PRE_SEAD_4", "approved", ["B", "C"]))
        self.assertIn("KEYWORD line", old["metadata_basis"])

    def test_doubtful_decisions_become_exceptions_and_held_ones_are_skipped(self) -> None:
        summary = self.build()
        reasons = {row["case_key"]: row["reason"] for _, row in iter_jsonl(self.out / "exceptions.jsonl")}
        self.assertIn("conflicting outcome", reasons["20-00002.h1"])
        self.assertIn("does not match", reasons["20-00003.h1"])
        self.assertIn("needs OCR", reasons["20-00004.h1"])
        self.assertEqual(summary["counts"]["already_held"], 1)
        self.assertNotIn("18-00005.h1", reasons)

    def test_provenance_rows_carry_the_fetched_bytes(self) -> None:
        self.build()
        rows = [row for _, row in iter_jsonl(self.out / "doha_source_urls.additions.jsonl")]
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row["source_url_basis"] == "acquisition_bytes_identical" and row["source_bytes_sha256"]
                            for row in rows))

    def test_selection_by_group_era_and_pilot(self) -> None:
        self.assertEqual(self.build(group="appeals")["counts"]["planned"], 1)

    def test_an_existing_output_directory_is_refused(self) -> None:
        self.out.mkdir()
        with self.assertRaises(FileExistsError):
            self.build()

    def test_outcome_and_topic_rules(self) -> None:
        self.assertEqual(outcome("…" + "Favorable decision reversed." , "a1")[0], "denied")
        self.assertEqual(outcome("It is not clearly consistent with the national interest to grant", "h1")[0], "denied")
        self.assertIsNone(outcome("The hearing was held.", "h1")[0])
        self.assertEqual(topics("KEYWORD: Delinquent debt\n", TAXONOMY_BODY)[0], ["F"])
        self.assertEqual(topics("no keyword\nGuideline F: AGAINST APPLICANT\n", TAXONOMY_BODY)[0], ["F"])

    def test_an_unreadable_package_is_an_exception_not_a_stop(self) -> None:
        (self.run / "iscr-hearing-decisions" / "19-01234.h1.pdf.intake.json").write_text("", encoding="utf-8")
        summary = self.build()
        self.assertEqual(summary["counts"]["planned"], 2)
        reasons = {row["case_key"]: row["reason"] for _, row in iter_jsonl(self.out / "exceptions.jsonl")}
        self.assertIn("intake package unreadable", reasons["19-01234.h1"])

    def test_a_wrong_library_root_names_what_is_missing(self) -> None:
        with self.assertRaises(ValueError) as raised:
            build_plan(self.library / "nowhere", self.run, self.not_held, self.out, self.extract)
        self.assertIn("check --library-root", str(raised.exception))

    def reviews(self) -> dict[str, dict]:
        return {f"{item['record']['doha_review']['case_id']}.{item['record']['doha_review']['decision_level']}":
                item["record"]["doha_review"] for item in read_json(self.out / "intake-plan.json")["items"]}

    def test_an_appeal_names_the_decision_it_reviewed_and_a_remand_decision_its_appeal(self) -> None:
        # The real sequence of ISCR Case No. 06-25928: denied, remanded, granted on remand.
        self.add("06-25928.h1", hearing("06-25928", "h1", "11/20/2007", "Foreign Preference; Foreign Influence",
                                        "Eligibility for access to classified information is denied."))
        self.add("06-25928.h2", hearing("06-25928", "h2", "06/16/2008", "Guideline C; Guideline B",
                                        "On April 9, 2008, the Appeal Board remanded the case for a new decision.\n"
                                        "Eligibility for access to classified information is granted."))
        self.build()
        reviews = self.reviews()
        appeal = reviews["06-25928.a1"]
        self.assertEqual((appeal["appeal_disposition"], appeal["appealed_by"], appeal["outcome"]), ("remanded", "Applicant", "remanded"))
        self.assertEqual(appeal["reviewed_decision"]["case_key"], "06-25928.h1")
        self.assertEqual(appeal["reviewed_decision"]["outcome"], "denied")
        self.assertEqual(appeal["reviewed_decision"]["decision_date"], "2007-11-20")
        self.assertEqual(appeal["reviewed_decision"]["status"], "in this plan")
        self.assertEqual(reviews["06-25928.h2"]["decided_on_remand_from"]["case_key"], "06-25928.a1")
        self.assertNotIn("decided_on_remand_from", reviews["06-25928.h1"])

    def test_affirmed_and_reversed_keep_the_boards_action_and_the_clearance_result(self) -> None:
        self.add("21-01882.h1", None)
        self.add("21-01882.a1", appeal("21-01882", "04/08/2024", "Guideline F",
                                       "Applicant appealed.\n The Decision is AFFIRMED."))
        self.add("98-00252.a1", "CASENO: 98-00252.a1\nDATE: 09/15/1999\n" + FILLER +
                 "The case is before the Board on Department Counsel's appeal from that favorable decision. "
                 "For the reasons set forth below, the Board reverses the Administrative Judge's decision.\n")
        summary = self.build()
        reviews = self.reviews()
        affirmed = reviews["21-01882.a1"]
        self.assertEqual((affirmed["appeal_disposition"], affirmed["outcome"]), ("affirmed", "denied"))
        self.assertEqual(affirmed["reviewed_decision"]["case_key"], "21-01882.h1")
        self.assertEqual(affirmed["reviewed_decision"]["status"], "listed by DOHA, not acquired")
        reversed_ = reviews["98-00252.a1"]
        self.assertEqual((reversed_["appeal_disposition"], reversed_["appealed_by"], reversed_["outcome"]),
                         ("reversed", "Department Counsel", "denied"))
        self.assertEqual(reversed_["reviewed_decision"]["outcome"], "approved")
        self.assertIsNone(reversed_["reviewed_decision"]["case_key"])
        self.assertEqual(summary["counts"]["PRE_SEAD_4/appeal/reversed (clearance denied)"], 1)


class RealWordingTests(unittest.TestCase):
    """Rules against wording taken from real DOHA decisions in the 2026-09-27 pilot."""

    def test_a_bare_affirmance_takes_its_meaning_from_who_appealed(self) -> None:
        body = "Applicant appealed pursuant to Directive E3.1.28.\n" + FILLER
        order = "                                                  Order\n       The Decision is AFFIRMED.\n"
        self.assertEqual(outcome(body + order, "a1")[0], "denied")
        government = "Department Counsel appealed the favorable decision.\n" + FILLER
        self.assertEqual(outcome(government + "The Administrative Judge's decision is AFFIRMED.", "a1")[0], "approved")
        self.assertIsNone(outcome(FILLER + order, "a1")[0], "without an appellant a bare affirmance means nothing")

    def test_an_order_naming_the_decision_it_affirms(self) -> None:
        text = ("(App. Bd. Oct. 13, 2004). Therefore, the decision of the Administrative Judge denying Applicant a "
                "security clearance is\n  AFFIRMED.\n  Signed:")
        self.assertEqual(outcome(text, "a1")[0], "denied")

    def test_not_split_from_clearly_by_a_line_break_is_still_a_denial(self) -> None:
        text = ("DOHA could not make the preliminary affirmative finding under the Directive that it is clearly "
                "consistent with the national interest to grant or continue a security clearance.\n" + FILLER +
                "                                        Conclusion\n"
                "         In light of all of the circumstances presented by the record in this case, it is not\n"
                "clearly consistent with the national interest to grant Applicant a security clearance.\n"
                "Eligibility for access to classified information is denied.\n")
        self.assertEqual(outcome(text, "h1"), ("denied", "not clearly consistent with the national interest"))

    def test_the_opening_boilerplate_is_not_an_outcome(self) -> None:
        text = ("DOHA could not make the preliminary affirmative finding under the Directive that it is clearly "
                "consistent with the national interest to grant or continue a security clearance for Applicant.\n"
                "It is clearly consistent with the national interest to grant or continue a security clearance for Applicant.")
        self.assertEqual(outcome(text, "h1")[0], "approved")

    def test_a_1997_decision_is_identified_by_its_key_line_or_osd_caption(self) -> None:
        head = "97-0050.h1\n  Date: April 30, 1997\n  ISCR OSD Case No. 97-0050\n"
        self.assertIsNone(identity(head, "97-00050", "h1")[0])
        self.assertIsNone(identity("  ISCR OSD Case No. 97-0050\n", "97-00050", "h1")[0])
        self.assertIn("does not match", identity(head, "97-00051", "h1")[0])

    def test_topics_fall_back_to_the_guidelines_the_sor_alleged(self) -> None:
        text = "Statement of the Case\nDOHA issued an SOR detailing security concerns under Guidelines F and E. " + FILLER
        self.assertEqual(topics(text, TAXONOMY_BODY | {"guidelines": TAXONOMY_BODY["guidelines"] | {
            "E": {"label": "Personal Conduct", "aliases": ["personal conduct"]}}})[0], ["E", "F"])
        self.assertEqual(topics("Paragraph 1, Criterion F:   AGAINST APPLICANT\n", TAXONOMY_BODY)[0], ["F"])

    def test_1990s_board_orders_and_the_decision_they_review(self) -> None:
        affirm = ("Applicant. The case is before the Board on Department Counsel's appeal from that favorable decision.\n"
                  "appealed that decision. For the reasons set forth below, the Board affirms the Administrative Judge's decision.")
        self.assertEqual(outcome(affirm, "a1")[0], "approved")
        reverse = ("case is before the Board on Department Counsel's appeal from that favorable decision.\n"
                   "appealed. For the reasons set forth below, the Board reverses the Administrative Judge's decision.")
        self.assertEqual(outcome(reverse, "a1")[0], "denied")

    def test_the_burden_of_proof_sentence_is_not_an_outcome(self) -> None:
        text = ("CONCLUSIONS\nApplicant has the ultimate burden of persuasion in proving that it is clearly consistent with "
                "the national interest to grant him or her a security clearance. In light of all the circumstances presented "
                "by the record in this case, it is not clearly consistent with the national interest to grant a clearance.")
        self.assertEqual(outcome(text, "h1")[0], "denied")

    def test_formal_findings_without_a_colon_and_lower_case_criteria(self) -> None:
        self.assertEqual(topics("Paragraph 1, Guideline F (Financial Considerations)           FOR APPLICANT\n",
                                TAXONOMY_BODY)[0], ["F"])
        self.assertEqual(topics("Guideline F applies; the evidence weighs for Applicant.\n" + FILLER,
                                TAXONOMY_BODY)[1], "guidelines alleged in the Statement of the Case")
        body = FILLER * 30 + "most pertinent to this case, with regard to criteria H, E and J.\n"
        taxonomy = {"schema_version": "1.0", "guidelines": {c: {"aliases": [c.lower() + "-alias"]} for c in "EHJ"}}
        self.assertEqual(topics(body, taxonomy), (["E", "H", "J"], "guidelines the decision applies"))


if __name__ == "__main__":
    unittest.main()
