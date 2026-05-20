"""State-Trait stability gate - Constitution v1.1 §P1 hard gate.

Decides which anchors are eligible to be rendered as "Core Truths" or stable
traits in persona representations.

P1 baseline (M1): exclude `Dimension.STATE` from SOUL/VOICE/SKILL/BOUNDARIES
Core Truths. STATE may still appear in its own STATE.md file as a current-state
snapshot (per DIMENSION_DESCRIPTIONS).
"""

from __future__ import annotations

from virtualme.storage.db import Anchor, Dimension


# Dimensions that represent durable identity/trait surfaces.
# STATE is current snapshot, not Core Truth.
CORE_TRUTH_DIMENSIONS: frozenset[Dimension] = frozenset(
    {
        Dimension.SOUL,
        Dimension.VOICE,
        Dimension.SKILL,
        Dimension.BOUNDARIES,
    }
)


def is_eligible_for_core_truths(anchor: Anchor) -> bool:
    """Return False for anchors whose source dimension is STATE."""
    return anchor.dimension != Dimension.STATE


def filter_core_truth_candidates(anchors: list[Anchor]) -> list[Anchor]:
    """Filter a list of candidate anchors for Core Truths surfaces."""
    return [anchor for anchor in anchors if is_eligible_for_core_truths(anchor)]
