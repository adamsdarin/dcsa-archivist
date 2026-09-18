from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import workflow_requests
from dcsa_custodian.common import iter_jsonl, write_jsonl
from dcsa_custodian.release import build_candidate, publish_candidate
import test_publication_metadata as fixtures


class SourceRequestIntegrationTests(unittest.TestCase):
    setUp=fixtures.PublicationMetadataTests.setUp

    def test_resolution_requires_published_matching_unchanged_robot_evidence(self):
        uri='https://example.gov/source'
        manifest=self.root/'ROBOT_READABLE_DIRECTORY/MANIFESTS/documents.jsonl'
        rows=[r for _,r in iter_jsonl(manifest)]
        rows[0]['canonical_source_uri']=uri
        write_jsonl(manifest,rows)
        with patch('dcsa_custodian.release.embed_texts',side_effect=lambda texts:[bytes(1536) for _ in texts]):
            result=build_candidate(self.project,self.root,self.config,'request-release')
        publish_candidate(self.project,self.root,self.config,Path(result['release_directory']))
        receipt=workflow_requests.approved_resolution(self.root,'rule',uri)
        self.assertEqual(receipt['release_id'],'request-release')
        with self.assertRaisesRegex(ValueError,'requested source'):
            workflow_requests.approved_resolution(self.root,'rule','https://example.gov/different')
        (self.root/rows[0]['robot_text_path']).write_text('corrupted after publication')
        with self.assertRaisesRegex(ValueError,'missing or changed'):
            workflow_requests.approved_resolution(self.root,'rule',uri)
