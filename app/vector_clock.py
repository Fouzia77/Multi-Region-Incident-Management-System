"""
Vector Clock implementation for causal ordering in distributed systems.

A vector clock is a dictionary mapping region_id -> integer counter.
Example: {"us": 2, "eu": 1, "apac": 0}
"""

from enum import Enum
from typing import Dict

VectorClock = Dict[str, int]


class ClockRelation(str, Enum):
    BEFORE = "BEFORE"
    AFTER = "AFTER"
    EQUAL = "EQUAL"
    CONCURRENT = "CONCURRENT"


REGIONS = ["us", "eu", "apac"]


def new_clock() -> VectorClock:
    """Create a new zero-initialized vector clock for all regions."""
    return {r: 0 for r in REGIONS}


def increment(vc: VectorClock, region_id: str) -> VectorClock:
    """
    Increment the local region's counter in the vector clock.
    Returns a new clock (immutable operation).
    """
    updated = dict(vc)
    updated[region_id] = updated.get(region_id, 0) + 1
    return updated


def merge(vc1: VectorClock, vc2: VectorClock) -> VectorClock:
    """
    Merge two vector clocks by taking the element-wise maximum.
    merged[i] = max(vc1[i], vc2[i]) for all i.
    """
    all_keys = set(vc1.keys()) | set(vc2.keys())
    return {k: max(vc1.get(k, 0), vc2.get(k, 0)) for k in all_keys}


def compare(vc1: VectorClock, vc2: VectorClock) -> ClockRelation:
    """
    Compare two vector clocks and return their causal relationship.

    Returns:
        EQUAL      — vc1 == vc2 (same state)
        BEFORE     — vc1 happened-before vc2 (vc1 is causally older)
        AFTER      — vc1 happened-after vc2 (vc1 is causally newer)
        CONCURRENT — neither happened-before the other (concurrent updates)

    Rules for BEFORE: every element of vc1 <= corresponding element of vc2,
    AND at least one element of vc1 is strictly less than vc2.
    """
    all_keys = set(vc1.keys()) | set(vc2.keys())

    vc1_le_vc2 = all(vc1.get(k, 0) <= vc2.get(k, 0) for k in all_keys)
    vc2_le_vc1 = all(vc2.get(k, 0) <= vc1.get(k, 0) for k in all_keys)

    if vc1_le_vc2 and vc2_le_vc1:
        return ClockRelation.EQUAL
    elif vc1_le_vc2:
        return ClockRelation.BEFORE
    elif vc2_le_vc1:
        return ClockRelation.AFTER
    else:
        return ClockRelation.CONCURRENT
