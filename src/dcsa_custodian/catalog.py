"""The published collection catalog (`CATALOG/COLLECTIONS.json`) derived from the manifest.

The entry point names this file and reviewers use it for collection taxonomy, but no
build wrote it: its counts were whatever the last hand script left (voi was right only
because a one-off set it; doha_decisions was 21,562 short). A candidate now regenerates
it from the same records as every other derived artifact, and the audit compares it.
"""
from __future__ import annotations

import collections
from typing import Any, Iterable

from .common import normalize_domain

FIELDS = ("document_count", "domains", "authority_tiers")


def _tier_key(value: str) -> tuple[int, str]:
    return (int(value), "") if value.isdigit() else (10 ** 6, value)


def _derived(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    counts: collections.Counter[str] = collections.Counter()
    domains: dict[str, set[str]] = collections.defaultdict(set)
    tiers: dict[str, set[str]] = collections.defaultdict(set)
    for record in records:
        identity = str(record.get("collection_id"))
        counts[identity] += 1
        # Enriched records keep the manifest's own spelling in source_domain.
        domains[identity].add(normalize_domain(record.get("source_domain", record.get("domain"))))
        if record.get("authority_tier") is not None:
            tiers[identity].add(str(record["authority_tier"]))
    return {identity: {"document_count": counts[identity], "domains": sorted(domains[identity]),
                       "authority_tiers": sorted(tiers[identity], key=_tier_key)} for identity in counts}


def collection_catalog(records: Iterable[dict[str, Any]], existing: Any = None) -> list[dict[str, Any]]:
    """One entry per collection. Existing entries keep their order and any other keys; a
    collection that no longer has documents stays listed with a count of zero."""
    derived = _derived(records)
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in existing if isinstance(existing, list) else []:
        if not isinstance(entry, dict) or not entry.get("collection_id") or str(entry["collection_id"]) in seen:
            continue
        identity = str(entry["collection_id"])
        seen.add(identity)
        output.append({**entry, **derived.get(identity, {"document_count": 0})})
    for identity in sorted(set(derived) - seen):
        output.append({"collection_id": identity, **derived[identity]})
    return output


def catalog_differences(catalog: Any, records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Where a catalog disagrees with the manifest it describes."""
    derived = _derived(records)
    listed = {str(entry.get("collection_id")): entry for entry in catalog if isinstance(entry, dict)} if isinstance(catalog, list) else {}
    differences = []
    for identity in sorted(set(derived) | set(listed)):
        have, want = listed.get(identity), derived.get(identity, {"document_count": 0})
        if have is None:
            differences.append({"collection_id": identity, "problem": "not_in_catalog", "manifest": want["document_count"]})
        elif any(key in want and have.get(key) != want[key] for key in FIELDS):
            differences.append({"collection_id": identity, "problem": "differs",
                                "catalog": {key: have.get(key) for key in FIELDS},
                                "manifest": {key: want.get(key) for key in FIELDS}})
    return differences
