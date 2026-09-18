"""Synthetic, offline evidence and routing checks for portable DOHA stores."""
from contextlib import closing
from copy import deepcopy
from pathlib import Path
import sqlite3
import tempfile
import unittest

from dcsa_custodian.common import read_json, sha256_file, write_json
from dcsa_custodian.doha import (CONTENT, MANIFEST, PATHS, TAXONOMY, append_cases,
                                review_metadata, validate_cases)


class DohaTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.taxonomy = {'schema_version': '1.0', 'guidelines': {'F': {'aliases': ['financial considerations']}, 'E': {'aliases': ['personal conduct']}}}

    def record(self, identity='case-one', level='h1', group='POST_SEAD_4', eligible=True, outcome='approved'):
        relative = f'ROBOT_READABLE_DIRECTORY/TEXT/DOHA/{identity}.txt'
        robot = self.root / relative
        robot.parent.mkdir(parents=True, exist_ok=True)
        robot.write_text(f'Synthetic {identity} financial considerations evidence. No actual case.', encoding='utf-8')
        return dict(document_id=identity, collection_id='doha_decisions', authority_tier=8,
            current_status='historical_case_research', human_source_path=f'HUMAN_READABLE_DIRECTORY/DOHA/{identity}.pdf',
            robot_text_path=relative, robot_sha256=sha256_file(robot),
            doha_review=dict(case_id='26-12345', decision_level=level, decision_date='2026-08-01',
                current_group=group, outcome=outcome, guidelines=['F'], answer_eligible=eligible,
                reviewed_by='synthetic reviewer', reviewed_utc='2026-09-16T00:00:00Z',
                metadata_basis='Synthetic reviewed metadata only'))

    def test_build_routes_only_eligible_hearings_and_preserves_exact_text(self):
        records = [self.record(), self.record('appeal', 'a1', eligible=False),
                   self.record('old', group='PRE_SEAD_4', eligible=False),
                   self.record('unresolved', group='UNDETERMINED', eligible=False)]
        append_cases(self.root, records, self.taxonomy)
        self.assertEqual(validate_cases(self.root, records, self.taxonomy), [])
        with closing(sqlite3.connect(self.root / CONTENT)) as db:
            rows = db.execute("SELECT d.document_id FROM decisions d JOIN corpus c ON d.document_id=c.document_id WHERE d.answer_eligible=1 AND d.current_group='POST_SEAD_4' AND d.decision_family='hearing' AND c.content MATCH 'financial'").fetchall()
            self.assertEqual(rows, [('case-one',)])
            self.assertEqual(db.execute('SELECT content FROM corpus WHERE document_id=?', ('case-one',)).fetchone()[0],
                             (self.root / records[0]['robot_text_path']).read_text())
        self.assertFalse((self.root / 'HUMAN_READABLE_DIRECTORY').exists(), 'Builder must not dereference human artifacts')

    def test_unreviewed_or_ineligible_claim_refused_before_index_writes(self):
        base = self.record()
        variants = []
        missing = deepcopy(base); missing.pop('doha_review'); variants.append(missing)
        for field, value in [('decision_level', 'a1'), ('current_group', 'PRE_SEAD_4'),
                             ('outcome', 'remanded'), ('guidelines', []), ('answer_eligible', 1),
                             ('reviewed_utc', '2026-09-16'), ('guidelines', ['Z']), ('case_id', '../case')]:
            bad = deepcopy(base); bad['doha_review'][field] = value; variants.append(bad)
        for record in variants:
            with self.subTest(record=record['doha_review'] if 'doha_review' in record else 'missing'):
                with self.assertRaises(ValueError):
                    append_cases(self.root, [record], self.taxonomy)
                self.assertFalse((self.root / CONTENT).exists())

    def test_changed_robot_bytes_and_path_escape_refused(self):
        record = self.record()
        (self.root / record['robot_text_path']).write_text('changed extraction')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            append_cases(self.root, [record], self.taxonomy)
        record['robot_text_path'] = '../outside.txt'
        with self.assertRaisesRegex(ValueError, 'outside'):
            append_cases(self.root, [record], self.taxonomy)
        self.assertFalse((self.root / CONTENT).exists())

    def test_existing_cases_preserved_and_duplicates_refused(self):
        first = self.record()
        append_cases(self.root, [first], self.taxonomy)
        second = self.record('second', outcome='denied')
        append_cases(self.root, [second], self.taxonomy)
        self.assertEqual(validate_cases(self.root, [first, second], self.taxonomy), [])
        before = sha256_file(self.root / CONTENT)
        with self.assertRaisesRegex(ValueError, 'replace'):
            append_cases(self.root, [first], self.taxonomy)
        self.assertEqual(sha256_file(self.root / CONTENT), before)

    def test_changed_taxonomy_requires_migration(self):
        append_cases(self.root, [self.record()], self.taxonomy)
        changed = deepcopy(self.taxonomy)
        changed['guidelines']['F']['aliases'].append('another alias')
        with self.assertRaisesRegex(ValueError, 'migration'):
            append_cases(self.root, [self.record('second')], changed)
        self.assertEqual(read_json(self.root / TAXONOMY), self.taxonomy)

    def test_validation_detects_topic_content_and_path_tampering(self):
        record = self.record()
        append_cases(self.root, [record], self.taxonomy)
        with closing(sqlite3.connect(self.root / CONTENT)) as db, db:
            db.execute("UPDATE decision_topics SET guideline_code='E'")
            db.execute("UPDATE corpus SET content='invented passage'")
        with closing(sqlite3.connect(self.root / PATHS)) as db, db:
            db.execute("UPDATE current_paths SET current_group='PRE_SEAD_4'")
        errors = validate_cases(self.root, [record], self.taxonomy)
        self.assertIn('DOHA topic routing mismatch', errors)
        self.assertIn('DOHA indexed evidence mismatch', errors)
        self.assertIn('DOHA indexed path mismatch', errors)
        with (self.root / MANIFEST).open('a') as out:
            out.write((self.root / MANIFEST).read_text().splitlines()[0] + '\n')
        self.assertIn('Duplicate DOHA manifest IDs', validate_cases(self.root, [record], self.taxonomy))

    def test_doha_never_becomes_current_controlling_guidance(self):
        record = self.record()
        record['current_status'] = 'current'
        with self.assertRaisesRegex(ValueError, 'historical_case_research'):
            review_metadata(record, self.taxonomy)


if __name__ == '__main__':
    unittest.main()
