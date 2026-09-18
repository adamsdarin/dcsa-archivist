"""Reconstruct a recipe-scoped library from reviewed intake; never copy a personal corpus."""
from contextlib import closing
import hashlib
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import uuid

from .common import read_json, sha256_file, write_json, write_jsonl
from .release_contract import bounded_path, approved_release, CONFIG, POLICY, ROUTER, CATALOG, POINTER
from .release import build_candidate, publish_candidate

MARKER = '.custodian/regenerator/recipe.json'
DOHA = ['LOCAL_INDEXES/DOHA_CASE_TOPICS_FTS.sqlite', 'LOCAL_INDEXES/DOHA_CURRENT_PATHS.sqlite']


def load_recipe(path):
    path = Path(path).resolve()
    recipe = read_json(path)
    if recipe.get('schema_version') != '1.0' or not isinstance(recipe.get('scope'), str) or not recipe['scope'].strip():
        raise ValueError('Recipe requires schema_version 1.0 and reviewed scope')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', recipe.get('release_id', '')):
        raise ValueError('Invalid recipe release ID')
    expected = recipe.get('required_document_ids')
    if not isinstance(expected, list) or not expected or any(not isinstance(x, str) or not x.strip() for x in expected) or len(set(expected)) != len(expected):
        raise ValueError('Recipe requires unique nonempty required_document_ids')
    artifacts = {}
    for key in ('intake_plan', 'evaluations'):
        item = recipe.get(key, {})
        artifact = bounded_path(path.parent, item.get('path', ''), '')
        if not artifact.is_file() or sha256_file(artifact) != item.get('sha256'):
            raise ValueError(f'Recipe artifact hash mismatch: {key}')
        artifacts[key] = artifact
    cases = read_json(artifacts['evaluations']).get('cases', [])
    if not any(case.get('require_hit') is True and case.get('require_locator') is True
               and case.get('expected_document_ids') for case in cases):
        raise ValueError('Recipe evaluation needs a positive document-and-locator retrieval check')
    plan = read_json(artifacts['intake_plan'])
    items = plan.get('items', [])
    ids = [item['record']['document_id'] for item in items]
    if sorted(ids) != sorted(expected):
        raise ValueError('Reviewed intake does not exactly cover the declared recipe documents')
    if any(item['record'].get('collection_id') == 'doha_decisions' for item in items):
        raise ValueError('DOHA reconstruction is unsupported; no reviewed case/topic builder is available')
    # Validate asset hashes even on an idempotent retry after publication.
    hashes = [sha256_file(path)]
    for item in items:
        package_path = bounded_path(artifacts['intake_plan'].parent, item['package'], '')
        package = read_json(package_path)
        source = bounded_path(package_path.parent, package['source_filename'], '')
        robot = bounded_path(artifacts['intake_plan'].parent, item['robot_file'], '')
        if sha256_file(source) != package['source_sha256'] or sha256_file(robot) != item['robot_sha256']:
            raise ValueError('Recipe source or extraction hash mismatch')
        hashes.extend([sha256_file(package_path), sha256_file(source), sha256_file(robot)])
    fingerprint = hashlib.sha256('\n'.join(hashes).encode()).hexdigest()
    return recipe, artifacts, fingerprint


def initialize(destination, recipe, artifacts, fingerprint):
    destination = Path(destination).resolve()
    marker = destination / MARKER
    if marker.is_file():
        saved = read_json(marker)
        if saved.get('fingerprint') != fingerprint or saved.get('destination') != str(destination):
            raise ValueError('Destination belongs to another recipe or location')
        return destination / '.custodian/regenerator'
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError('Regeneration requires an empty destination; existing libraries are never replaced')
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.library-bootstrap-', dir=destination.parent))
    try:
        write_json(staging / 'START_HERE_FOR_ROBOTS.json', {
            'documents': 'ROBOT_READABLE_DIRECTORY/MANIFESTS/documents.jsonl',
            'relationships': 'ROBOT_READABLE_DIRECTORY/MANIFESTS/relationships.jsonl',
            'current_release': POINTER, 'index_catalog': CATALOG})
        for name in ('documents', 'relationships'):
            write_jsonl(staging / f'ROBOT_READABLE_DIRECTORY/MANIFESTS/{name}.jsonl', [])
        write_json(staging / CONFIG, {})
        write_json(staging / POLICY, {'content_access': {'retrieval_forbidden_indexes': []}})
        write_json(staging / ROUTER, {'doha_content_index': DOHA[0], 'current_doha_path_index': DOHA[1],
                                    'coverage': 'No DOHA cases in this general-source recipe', 'topics': []})
        # Schema-compatible empty case stores express absence, never synthetic case evidence.
        for relative in DOHA:
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(target)) as db, db:
                db.execute('CREATE TABLE current_paths(document_id TEXT, human_source_path TEXT, robot_text_path TEXT)')
                if relative == DOHA[0]:
                    db.execute('CREATE TABLE decisions(document_id TEXT,answer_eligible INTEGER,content_sha256 TEXT,case_id TEXT,decision_level TEXT,outcome TEXT,guideline_codes TEXT,current_group TEXT,decision_family TEXT,human_source_path TEXT,robot_text_path TEXT,case_year INTEGER,level_rank INTEGER,retrieval_priority INTEGER)')
                    db.execute('CREATE TABLE decision_topics(document_id TEXT,guideline_code TEXT)')
                    db.execute('CREATE VIRTUAL TABLE corpus USING fts5(document_id UNINDEXED,case_id UNINDEXED,decision_level UNINDEXED,current_group UNINDEXED,outcome UNINDEXED,guideline_codes UNINDEXED,human_source_path UNINDEXED,robot_text_path UNINDEXED,content)')
        (staging / 'AGENTS.md').write_text('# Unpublished library bootstrap\nNo content is approved for answers until Custodian publication passes.\n', encoding='utf-8')
        project = staging / '.custodian/regenerator'
        (project / 'evals').mkdir(parents=True)
        shutil.copy2(artifacts['evaluations'], project / 'evals/golden_queries.json')
        write_json(staging / MARKER, {'fingerprint': fingerprint, 'destination': str(destination), 'recipe': recipe})
        if destination.exists():
            destination.rmdir()  # Only the verified empty directory; no recursive removal.
        os.replace(staging, destination)
    finally:
        if staging.exists():
            # Staging is created by this call and is always a direct child of the destination parent.
            assert staging.resolve().parent == destination.parent and staging.name.startswith('.library-bootstrap-')
            shutil.rmtree(staging)
    return destination / '.custodian/regenerator'


def regenerate(recipe_path, destination):
    recipe, artifacts, fingerprint = load_recipe(recipe_path)
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.parent / f'.{destination.name}.regeneration.lock'
    with lock.open('x', encoding='utf-8') as handle:
        handle.write(str(os.getpid()))
    try:
        project = initialize(destination, recipe, artifacts, fingerprint)
        if sha256_file(project / 'evals/golden_queries.json') != recipe['evaluations']['sha256']:
            raise ValueError('Stored recipe evaluation was modified')
        config = {'state_directory': '.custodian', 'metadata_decisions_file': 'decisions/metadata_decisions.json'}
        release_dir = project / '.custodian/releases' / recipe['release_id']
        if (destination / POINTER).is_file():
            health = approved_release(destination, check_integrity=True)
            if health['release_id'] != recipe['release_id']:
                raise ValueError('Destination advanced beyond this recipe; use normal Custodian maintenance')
            return {'status': 'already_published', 'release_id': health['release_id'], 'destination': str(destination), 'scope': recipe['scope']}
        if not release_dir.exists():
            build_candidate(project, destination, config, recipe['release_id'], intake_plan=artifacts['intake_plan'])
        elif not (release_dir / 'VALIDATION.json').is_file():
            # This invocation holds the exclusive recipe writer lock. Retain the
            # incomplete attempt inside its owned workspace, then build anew.
            archived = project / '.custodian/failed-builds' / f"{recipe['release_id']}-{uuid.uuid4().hex}"
            if not release_dir.resolve().is_relative_to(project.resolve()) or not archived.resolve().is_relative_to(project.resolve()):
                raise ValueError('Candidate recovery path escape')
            archived.parent.mkdir(parents=True, exist_ok=True)
            os.replace(release_dir, archived)
            build_candidate(project, destination, config, recipe['release_id'], intake_plan=artifacts['intake_plan'])
        result = publish_candidate(project, destination, config, release_dir)
        return {**result, 'destination': str(destination), 'scope': recipe['scope'],
                'coverage_note': 'Only recipe-declared general sources; DOHA reconstruction is unsupported.'}
    finally:
        lock.unlink()
