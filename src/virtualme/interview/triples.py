import json

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from virtualme.storage.db import Turn


class PersonaTriple(BaseModel):
    id: int | None = None
    interviewee_id: str = ""
    subject: str
    relation: str
    object: str
    source_turn_ids: list[int]
    confidence: float = 1.0


async def extract_triples_from_session(
    session_id: int,
    turns: list[Turn],
    claude: AsyncAnthropic,
) -> list[PersonaTriple]:
    transcript = "\n".join(f"{turn.id} {turn.role}: {turn.content}" for turn in turns)
    prompt = f"""
Extract stable persona triples from this interview session as JSON list.
Each item must have: subject, relation, object, source_turn_ids, confidence.
Relations: value_anchor, preference, fact, red_line, skill.
Return [] if there is no durable persona content.

Session id: {session_id}
Transcript:
{transcript}
"""
    response = await claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=900,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        rows = json.loads(response.content[0].text)
    except json.JSONDecodeError:
        return []

    triples: list[PersonaTriple] = []
    for row in rows[:15]:
        try:
            triples.append(PersonaTriple(**row))
        except ValueError:
            continue
    return [triple for triple in triples if triple.object.strip()]
