from virtualme.interview.triples import PersonaTriple, extract_triples_from_session
from virtualme.storage.db import DB, Turn


class _Content:
    def __init__(self, text: str):
        self.text = text


class _Messages:
    async def create(self, **kwargs):
        return type(
            "Response",
            (),
            {
                "content": [
                    _Content(
                        """[
                          {
                            "subject": "interviewee",
                            "relation": "value_anchor",
                            "object": "directness over deference",
                            "source_turn_ids": [1],
                            "confidence": 0.8
                          }
                        ]"""
                    )
                ]
            },
        )


class _Claude:
    messages = _Messages()


async def test_triple_extraction_returns_persona_triples():
    turns = [
        Turn(id=1, session_id=1, role="user", content="I value directness.", content_hash="h")
    ]
    triples = await extract_triples_from_session(1, turns, _Claude())
    assert triples == [
        PersonaTriple(
            subject="interviewee",
            relation="value_anchor",
            object="directness over deference",
            source_turn_ids=[1],
            confidence=0.8,
        )
    ]


async def test_triple_persistence_roundtrip(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    triple = PersonaTriple(
        interviewee_id="u1",
        subject="interviewee",
        relation="skill",
        object="debugs small causes before complex causes",
        source_turn_ids=[1, 2],
    )
    await db.save_triple(triple)
    loaded = await db.load_triples("u1")
    assert loaded[0].model_dump(exclude={"id"}) == triple.model_dump()
