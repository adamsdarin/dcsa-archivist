"""Real staged intake/publication and retryable handoff contracts, offline."""
import json
from pathlib import Path
from unittest.mock import patch
import unittest

from dcsa_custodian.common import read_json, sha256_file, write_json
from dcsa_custodian.events import pending_events, reconcile_event, event_directory, acknowledge, comparison_report
from dcsa_custodian.release import build_candidate, publish_candidate
from dcsa_custodian.release_contract import readiness
import test_publication_metadata as fixtures


class HandoffTests(unittest.TestCase):
    setUp = fixtures.PublicationMetadataTests.setUp
    publish = fixtures.PublicationMetadataTests.publish

    def plan(self):
        folder = self.project / 'quarantine'
        folder.mkdir()
        (folder / 'source.pdf').write_bytes(b'%PDF-synthetic-reviewed')
        (folder / 'robot.txt').write_text('TIER: 7\nSTATUS: current\nDOC TYPE: guidance\n\nA newly reviewed synthetic newsletter passage.\n', encoding='utf-8')
        write_json(folder / 'source.pdf.intake.json', {
            'approval_state': 'quarantined_unreviewed', 'requested_source_uri': 'https://www.dcsa.mil/source.pdf',
            'resolved_source_uri': 'https://www.dcsa.mil/source.pdf', 'retrieved_at': '2026-09-11T00:00:00Z',
            'mime_type': 'application/pdf', 'source_filename': 'source.pdf',
            'source_sha256': sha256_file(folder / 'source.pdf'), 'source_bytes': (folder / 'source.pdf').stat().st_size,
        })
        record = {'document_id': 'new-voi', 'collection_id': 'voi', 'domain': 'industrial_security', 'authority_tier': 7,
                  'current_status': 'current', 'human_source_path': 'HUMAN_READABLE_DIRECTORY/INDUSTRIAL_SECURITY/VOICE_OF_INDUSTRY/2026-09_VOI.pdf',
                  'robot_text_path': 'ROBOT_READABLE_DIRECTORY/TEXT/INDUSTRIAL_SECURITY/VOICE_OF_INDUSTRY/2026-09_VOI.txt'}
        item = {'package': 'source.pdf.intake.json', 'robot_file': 'robot.txt', 'robot_sha256': sha256_file(folder / 'robot.txt'),
                'record': record, 'review': {k: 'synthetic evidence' for k in ('identity','provenance','extraction','parity','taxonomy','lifecycle')}}
        item['review'].update(reviewed_by='test-agent', reviewed_utc='2026-09-11T00:00:00Z')
        write_json(folder / 'plan.json', {'schema_version': '1.0', 'items': [item]})
        return folder / 'plan.json', record

    def build(self, plan, identity='intake-test'):
        with patch('dcsa_custodian.release.embed_texts', side_effect=lambda texts: [bytes(1536) for _ in texts]):
            return build_candidate(self.project, self.root, self.config, identity, intake_plan=plan)

    def test_intake_stays_staged_then_publishes_with_wiki_and_both_handoffs(self):
        self.publish()
        plan, record = self.plan()
        before = {str(p.relative_to(self.root)): sha256_file(p) for p in self.root.rglob('*') if p.is_file()}
        result = self.build(plan)
        release = Path(result['release_directory'])
        self.assertTrue(result['validation']['publishable'])
        self.assertEqual(before, {str(p.relative_to(self.root)): sha256_file(p) for p in self.root.rglob('*') if p.is_file()})
        self.assertFalse((self.root / record['robot_text_path']).exists())
        publish_candidate(self.project, self.root, self.config, release)
        self.assertTrue(readiness(self.root)['ready'])
        self.assertTrue((self.root / record['robot_text_path']).exists())
        wiki = read_json(self.root / 'ROBOT_READABLE_DIRECTORY/WIKI/GRAPH.json')
        self.assertEqual(wiki['release_id'], 'intake-test')
        for consumer in ('dcsa-compare', 'fso-guidance-watch'):
            packets = pending_events(self.project, self.config, self.root, consumer)
            packet = next(p for p in packets if p['event']['event_id'] == 'intake-test')
            self.assertEqual([c['document_id'] for c in packet['changes']['changes']], ['new-voi'])
            self.assertFalse(comparison_report(packet['changes'])['supersession_verified'])

    def test_unreviewed_or_tampered_intake_cannot_modify_library(self):
        plan, _ = self.plan()
        original = read_json(plan)
        broken = read_json(plan)
        broken['items'][0]['review'].pop('parity')
        write_json(plan, broken)
        with self.assertRaisesRegex(ValueError, 'parity'):
            self.build(plan)
        write_json(plan, original)
        (plan.parent / 'source.pdf').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'hash/size'):
            self.build(plan)

    def test_event_recovery_idempotency_and_receipt_gates(self):
        self.publish()
        directory = event_directory(self.project, self.config, self.root) / self.release.name
        (directory / 'event.json').unlink()  # simulate interruption after pointer commit
        reconcile_event(self.project, self.config, self.root, self.release)
        reconcile_event(self.project, self.config, self.root, self.release)
        self.assertEqual(len(list(directory.glob('event.json'))), 1)
        event = read_json(directory / 'event.json')
        artifact = self.project / 'review.md'
        artifact.write_text('Synthetic complete-source review and cited disposition.', encoding='utf-8')
        receipt = {'event_id': self.release.name, 'consumer': 'dcsa-compare', 'changes_sha256': event['changes_sha256'],
                   'status': 'completed', 'reviewed_by': 'test-agent', 'summary': 'Synthetic review.',
                   'full_source_review': True, 'citation_closure': False, 'coverage_complete': True,
                   'artifacts': [{'path': 'review.md', 'sha256': sha256_file(artifact)}]}
        receipt_path = self.project / 'receipt.json'
        write_json(receipt_path, receipt)
        with self.assertRaisesRegex(ValueError, 'citation_closure'):
            acknowledge(self.project, self.config, self.root, 'dcsa-compare', self.release.name, receipt_path)
        receipt['citation_closure'] = True
        write_json(receipt_path, receipt)
        acknowledge(self.project, self.config, self.root, 'dcsa-compare', self.release.name, receipt_path)
        self.assertFalse(pending_events(self.project, self.config, self.root, 'dcsa-compare'))
        self.assertTrue(pending_events(self.project, self.config, self.root, 'fso-guidance-watch'))

    def test_failed_publication_emits_no_event_and_wiki_tamper_fails_readiness(self):
        import os
        replace = os.replace
        def interrupt(source, target):
            if str(target).endswith('CURRENT_CUSTODIAN_RELEASE.json'):
                raise OSError('interrupted')
            return replace(source, target)
        with patch('dcsa_custodian.release.os.replace', side_effect=interrupt):
            with self.assertRaises(OSError):
                self.publish()
        self.assertFalse(list(event_directory(self.project, self.config, self.root).glob('*/event.json')))
        self.publish()
        (self.root / 'ROBOT_READABLE_DIRECTORY/WIKI/GRAPH.json').write_text('{}')
        self.assertFalse(readiness(self.root)['ready'])

    def test_newer_release_prevents_stale_publication(self):
        self.publish()
        plan, _ = self.plan()
        result = self.build(plan)
        publish_candidate(self.project, self.root, self.config, Path(result['release_directory']))
        with self.assertRaisesRegex(RuntimeError, 'advanced'):
            self.publish()


if __name__ == '__main__':
    unittest.main()
