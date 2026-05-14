from virtualme.config import Settings
from virtualme.interview.ppa import _stage2_retrieve, ppa_response
from virtualme.interview.triples import PersonaTriple


class _Content:
    def __init__(self, text: str):
        self.text = text


class _Messages:
    def __init__(self, texts: list[str]):
        self.texts = texts
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return type("Response", (), {"content": [_Content(self.texts.pop(0))]})


class _Claude:
    def __init__(self, texts: list[str]):
        self.messages = _Messages(texts)


def _settings() -> Settings:
    return Settings(anthropic_api_key="test")


def _triple(text: str) -> PersonaTriple:
    return PersonaTriple(
        interviewee_id="u1",
        subject="interviewee",
        relation="value_anchor",
        object=text,
        source_turn_ids=[1],
    )


async def test_stage1_returns_general_text_when_memory_empty():
    claude = _Claude(["general response"])
    reply = await ppa_response("user: hello", [], claude, _settings())
    assert reply == "general response"


async def test_stage2_retrieval_returns_top_k_by_cosine_similarity():
    triples = [_triple("direct communication"), _triple("quiet weekends")]
    retrieved = await _stage2_retrieve("I prefer direct communication", triples, k=1, threshold=0.1)
    assert retrieved == [triples[0]]


async def test_stage3_prompt_contains_retrieved_triples():
    claude = _Claude(["direct response", "refined response"])
    triples = [_triple("direct communication")]
    reply = await ppa_response("user: say it plainly", triples, claude, _settings())
    assert reply == "refined response"
    assert "direct communication" in claude.messages.calls[1]["messages"][0]["content"]


async def test_fallback_empty_memory_pool_returns_general_response():
    claude = _Claude(["general response"])
    assert await ppa_response("user: hi", [], claude, _settings()) == "general response"


async def test_fallback_no_triples_above_threshold_returns_general_response():
    claude = _Claude(["general response"])
    settings = _settings()
    settings.ppa_retrieval_threshold = 0.99
    reply = await ppa_response("user: hi", [_triple("unrelated memory")], claude, settings)
    assert reply == "general response"
