from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dcsa_custodian.common import read_json, sha256_file, write_json
from dcsa_custodian.regenerate import regenerate, initialize, load_recipe
from dcsa_custodian.release_contract import approved_release, POINTER


class RegenerationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'new-library'
        (self.base / 'source.txt').write_text('TIER: 1\nSTATUS: current\nDOC TYPE: regulation\n\nSynthetic contractor safeguarding requirement.', encoding='utf-8')
        (self.base / 'robot.txt').write_bytes((self.base / 'source.txt').read_bytes())
        write_json(self.base / 'source.intake.json', dict(approval_state='quarantined_unreviewed',
            requested_source_uri='https://example.gov/source', resolved_source_uri='https://example.gov/source',
            retrieved_at='2026-09-14T00:00:00Z', mime_type='text/plain', source_filename='source.txt',
            source_sha256=sha256_file(self.base / 'source.txt'), source_bytes=(self.base / 'source.txt').stat().st_size))
        review = {key: 'Synthetic reviewed evidence' for key in ('identity', 'provenance', 'extraction', 'parity', 'taxonomy', 'lifecycle')}
        review.update(reviewed_by='test', reviewed_utc='2026-09-14T00:00:00Z')
        write_json(self.base / 'plan.json', dict(schema_version='1.0', items=[dict(package='source.intake.json', robot_file='robot.txt',
            robot_sha256=sha256_file(self.base / 'robot.txt'), review=review,
            record=dict(document_id='rule', collection_id='cfr', domain='authorities', authority_tier=1, current_status='current',
                human_source_path='HUMAN_READABLE_DIRECTORY/AUTHORITIES/CFR/rule.txt',
                robot_text_path='ROBOT_READABLE_DIRECTORY/TEXT/AUTHORITIES/CFR/rule.txt'))]))
        write_json(self.base / 'eval.json', dict(schema_version='1.0', cases=[dict(id='safeguarding',
            query='contractor safeguarding requirement', require_hit=True, require_locator=True,
            expected_document_ids=['rule'], expected_first_role='controlling_regulation')]))
        self.recipe = self.base / 'recipe.json'
        self.refresh_recipe()

    def refresh_recipe(self):
        write_json(self.recipe, dict(schema_version='1.0', scope='Synthetic general-source test only',
            release_id='rebuild-1', required_document_ids=['rule'],
            intake_plan=dict(path='plan.json', sha256=sha256_file(self.base / 'plan.json')),
            evaluations=dict(path='eval.json', sha256=sha256_file(self.base / 'eval.json'))))

    def run_recipe(self):
        with patch('dcsa_custodian.release.embed_texts', side_effect=lambda texts: [bytes(1536) for _ in texts]):
            return regenerate(self.recipe, self.root)

    def test_empty_destination_to_approved_retrieval_and_retry(self):
        result = self.run_recipe()
        self.assertEqual(result['status'], 'published')
        health = approved_release(self.root, check_integrity=True)
        self.assertEqual(health['release_id'], 'rebuild-1')
        self.assertTrue((self.root / 'ROBOT_READABLE_DIRECTORY/WIKI/GRAPH.json').is_file())
        before = sha256_file(self.root / POINTER)
        self.assertEqual(self.run_recipe()['status'], 'already_published')
        self.assertEqual(before, sha256_file(self.root / POINTER))

    def test_bootstrap_is_not_approved_and_existing_files_are_untouched(self):
        recipe, artifacts, fingerprint = load_recipe(self.recipe)
        initialize(self.root, recipe, artifacts, fingerprint)
        with self.assertRaises((ValueError, FileNotFoundError)):
            approved_release(self.root)
        other = self.base / 'existing'
        other.mkdir(); (other / 'keep.txt').write_text('retain')
        with self.assertRaisesRegex(ValueError, 'empty destination'):
            regenerate(self.recipe, other)
        self.assertEqual((other / 'keep.txt').read_text(), 'retain')

    def test_missing_coverage_tamper_and_concurrent_run_rejected(self):
        recipe = read_json(self.recipe); recipe['required_document_ids'].append('missing')
        write_json(self.recipe, recipe)
        with self.assertRaisesRegex(ValueError, 'exactly cover'):
            self.run_recipe()
        self.assertFalse(self.root.exists())
        self.refresh_recipe()
        lock = self.base / '.new-library.regeneration.lock'
        lock.write_text('existing writer')
        with self.assertRaises(FileExistsError):
            self.run_recipe()
        self.assertEqual(lock.read_text(), 'existing writer')
        lock.unlink()
        (self.base / 'robot.txt').write_text('modified')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            self.run_recipe()
        self.assertFalse(self.root.exists())

    def test_doha_recipe_is_refused_before_creating_destination(self):
        plan = read_json(self.base / 'plan.json')
        plan['items'][0]['record']['collection_id'] = 'doha_decisions'
        write_json(self.base / 'plan.json', plan)
        self.refresh_recipe()
        with self.assertRaisesRegex(ValueError, 'DOHA reconstruction is unsupported'):
            self.run_recipe()
        self.assertFalse(self.root.exists())

    def test_source_review_and_evaluation_cannot_be_skipped(self):
        plan = read_json(self.base / 'plan.json'); plan['items'][0]['review'].pop('parity')
        write_json(self.base / 'plan.json', plan); self.refresh_recipe()
        with self.assertRaisesRegex(ValueError, 'parity'):
            self.run_recipe()
        self.assertFalse((self.root / POINTER).exists())

    def test_failed_evaluation_never_publishes(self):
        write_json(self.base / 'eval.json', dict(cases=[dict(id='missing', query='absent requirement', require_hit=True,
            require_locator=True, expected_document_ids=['rule'])]))
        self.refresh_recipe()
        with self.assertRaises(RuntimeError):
            self.run_recipe()
        self.assertFalse((self.root / POINTER).exists())

    def test_interrupted_build_is_preserved_and_retry_completes(self):
        recipe, artifacts, fingerprint = load_recipe(self.recipe)
        project = initialize(self.root, recipe, artifacts, fingerprint)
        partial = project / '.custodian/releases/rebuild-1'
        partial.mkdir(parents=True)
        (partial / 'interrupted.txt').write_text('preserve')
        self.assertEqual(self.run_recipe()['status'], 'published')
        saved = list((project / '.custodian/failed-builds').glob('*/interrupted.txt'))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].read_text(), 'preserve')

    def test_stored_evaluation_drift_is_not_a_gate_bypass(self):
        recipe, artifacts, fingerprint = load_recipe(self.recipe)
        project = initialize(self.root, recipe, artifacts, fingerprint)
        write_json(project / 'evals/golden_queries.json', dict(cases=[]))
        with self.assertRaisesRegex(ValueError, 'evaluation was modified'):
            self.run_recipe()


if __name__ == '__main__':
    unittest.main()
