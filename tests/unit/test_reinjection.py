from virtualme.interview.reinjection import build_reinjection_anchor, should_reinject
from virtualme.interview.triples import PersonaTriple


def test_should_reinject_interval():
    assert should_reinject(20) is True
    assert should_reinject(19) is False
    assert should_reinject(0) is False


def test_build_reinjection_anchor_includes_key_triples():
    anchor = build_reinjection_anchor(
        "u1",
        [
            PersonaTriple(
                subject="interviewee",
                relation="value_anchor",
                object="directness over deference",
                source_turn_ids=[1],
            )
        ],
    )
    assert "u1" in anchor
    assert "directness over deference" in anchor
