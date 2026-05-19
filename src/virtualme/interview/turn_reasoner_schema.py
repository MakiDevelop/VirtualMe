from enum import StrEnum


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


class TurnReasonerOutput:
    """Simple container for reasoner output (no Pydantic to avoid extra_forbidden issues)"""

    def __init__(self, **kwargs):
        self.read = kwargs.get("read", "")
        self.boundary_status = kwargs.get("boundary_status", "none")
        self.engagement_state = kwargs.get("engagement_state", "engaged")
        self.next_move = kwargs.get("next_move", "advance")
        self.next_question_id = kwargs.get("next_question_id")
        self.should_echo = kwargs.get("should_echo", False)
        self.echo_content = kwargs.get("echo_content")
        self.reflection_note = kwargs.get("reflection_note")
        self.reply = kwargs.get("reply", "")
