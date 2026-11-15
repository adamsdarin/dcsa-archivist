"""Filename rules a collection's sources must follow before they can be staged.

A reviewer chooses the path, and a reviewer copies the nearest sibling. One outlier
(`2026-08 VOI.pdf`) was copied twice before anyone noticed, so a collection whose
names follow one pattern has that pattern checked here instead of trusted.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

from .common import norm

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"

# collection_id -> (pattern the filename stem must match in full, the shape to show a reviewer)
COLLECTION_NAMES: dict[str, tuple[re.Pattern[str], str]] = {
    "voi": (re.compile(rf"Voice of Industry - (?:{MONTHS}) 20\d\d (?:Newsletter|Bulletin|Special Bulletin)"),
            "Voice of Industry - <Month> <YYYY> Newsletter (or Bulletin / Special Bulletin)"),
}


def check_collection_name(record: dict[str, Any]) -> None:
    """Raise if a record's paths break its collection's filename rule.

    Collections without a rule pass. The robot text must share the source's stem, so
    the pair stays recognisable side by side.
    """
    rule = COLLECTION_NAMES.get(str(record.get("collection_id")))
    if rule is None:
        return
    pattern, shape = rule
    human = PurePosixPath(norm(record.get("human_source_path")))
    robot = PurePosixPath(norm(record.get("robot_text_path")))
    if not pattern.fullmatch(human.stem):
        raise ValueError(f"{record.get('collection_id')} filename must be '{shape}': {human.name}")
    if robot.stem != human.stem:
        raise ValueError(f"robot text must share the source's name '{human.stem}': {robot.name}")
