import json

from virtualme.interview.anchor_extractor import extract_anchors
from virtualme.interview.briefing import INTERVIEW_PURPOSE, InterviewBriefing
from virtualme.storage.db import Dimension, Question, Turn


class _Content:
    def __init__(self, text: str):
        self.text = text


class _Messages:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return type(
            "Response",
            (),
            {
                "content": [
                    _Content(
                        json.dumps(
                            [
                                {
                                    "dimension": "STATE",
                                    "layer": "fact",
                                    "content": "works through uncertainty",
                                }
                            ]
                        )
                    )
                ]
            },
        )


class _Claude:
    def __init__(self):
        self.messages = _Messages()


async def test_extract_anchors_prompt_includes_briefing_when_present():
    claude = _Claude()
    briefing = InterviewBriefing(
        purpose=INTERVIEW_PURPOSE,
        progress="Week 1 of 4.",
        durable_summary="- durable",
        coverage_gaps="- gap",
        recent_transcript="受訪者: one\n訪談者: two\n受訪者: three\n訪談者: four\n受訪者: five",
    )

    await extract_anchors(
        Turn(id=1, session_id=1, role="user", content="answer", content_hash="h"),
        Question(id="Q1", week=1, dimension=Dimension.STATE, text="Question?"),
        claude,
        briefing,
    )

    prompt = claude.messages.calls[0]["messages"][0]["content"]
    assert "INTERVIEW PURPOSE:" in prompt
    assert "RECENT CONVERSATION:" in prompt
    assert "WHAT WE KNOW SO FAR:" not in prompt
    assert "受訪者: one" not in prompt
    assert "訪談者: two" in prompt
