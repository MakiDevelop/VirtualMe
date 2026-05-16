import json

from anthropic import AsyncAnthropic

from virtualme.interview.json_utils import extract_json_payload
from virtualme.interview.models import MODEL_STANDARD, create_message
from virtualme.storage.db import Anchor, Dimension, Layer, Question, Turn


async def extract_anchors(
    turn: Turn,
    current_question: Question,
    claude: AsyncAnthropic,
) -> list[Anchor]:
    prompt = f"""
Extract 1-3 anchors as JSON list. Fields: dimension, layer, content.
Use dimensions: {[dimension.value for dimension in Dimension]}.
Use layers: fact, pattern, principle.

Question: {current_question.text}
Answer: {turn.content}
"""
    response = await create_message(
        claude,
        model=MODEL_STANDARD,
        max_tokens=500,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        rows = json.loads(extract_json_payload(response.content[0].text))
    except json.JSONDecodeError:
        rows = []
    anchors: list[Anchor] = []
    for row in rows[:3]:
        anchors.append(
            Anchor(
                interviewee_id="",
                dimension=Dimension(row.get("dimension", current_question.dimension)),
                layer=Layer(row.get("layer", Layer.FACT)),
                content=row.get("content", "").strip(),
                source_turn_ids=[turn.id],
                source_question_ids=[current_question.id],
            )
        )
    return [anchor for anchor in anchors if anchor.content]
