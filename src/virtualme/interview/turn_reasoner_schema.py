from dataclasses import dataclass
from enum import StrEnum
from typing import Optional


class BoundaryStatus(StrEnum):
    NONE = "none"
    EXPLICIT_REFUSAL = "explicit_refusal"
    STRONG_RELUCTANCE = "strong_reluctance"


class EngagementState(StrEnum):
    ENGAGED = "engaged"
    FATIGUED = "fatigued"
    DRIFTING = "drifting"
    GUARDED = "guarded"
    DISTRUSTFUL = "distrustful"


class NextMove(StrEnum):
    ADVANCE = "advance"
    PROBE = "probe"
    HONOR_SKIP = "honor_skip"
    ADDRESS_META = "address_meta"
    SOFTEN = "soften"


@dataclass
class TurnReasonerOutput:
    read: str
    boundary_status: BoundaryStatus
    engagement_state: EngagementState
    next_move: NextMove
    next_question_id: Optional[str]
    should_echo: bool
    echo_content: Optional[str]
    reflection_note: Optional[str]
    reply: str
