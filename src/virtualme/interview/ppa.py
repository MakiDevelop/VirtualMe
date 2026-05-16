import json
import math
from collections import Counter

from anthropic import AsyncAnthropic

from virtualme.config import Settings
from virtualme.interview.lang import tokens
from virtualme.interview.models import MODEL_FAST, MODEL_STANDARD
from virtualme.interview.triples import PersonaTriple


async def ppa_response(
    dialogue_context: str,
    memory_pool: list[PersonaTriple],
    claude: AsyncAnthropic,
    settings: Settings,
) -> str:
    r_g = await _stage1_general_response(dialogue_context, claude)
    if not memory_pool:
        return r_g
    relevant = await _stage2_retrieve(
        r_g,
        memory_pool,
        k=settings.ppa_retrieval_k,
        threshold=settings.ppa_retrieval_threshold,
    )
    if not relevant:
        return r_g
    return await _stage3_refine(dialogue_context, r_g, relevant, claude)


async def _stage1_general_response(dialogue_context: str, claude: AsyncAnthropic) -> str:
    prompt = (
        "assistant is chatting with user.\n"
        "# The current conversation between user and assistant is as follows:\n"
        f"{dialogue_context}\n"
        "# Task: Output assistant's response to user in JSON.\n"
        'Format: {"assistant": <response>}'
    )
    response = await claude.messages.create(
        model=MODEL_FAST,
        max_tokens=150,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}],
    )
    return _assistant_text(response.content[0].text)


async def _stage2_retrieve(
    r_g: str,
    pool: list[PersonaTriple],
    k: int,
    threshold: float,
) -> list[PersonaTriple]:
    query = _vector(r_g)
    scored = [(_cosine(query, _vector(_triple_text(triple))), triple) for triple in pool]
    ranked = sorted(scored, key=lambda item: item[0], reverse=True)
    return [triple for score, triple in ranked[:k] if score >= threshold]


async def _stage3_refine(
    dialogue_context: str,
    r_g: str,
    triples: list[PersonaTriple],
    claude: AsyncAnthropic,
) -> str:
    memory = "\n".join(f"- ({t.subject}, {t.relation}, {t.object})" for t in triples)
    prompt = (
        "assistant is chatting with user.\n"
        f"Their conversation is as follows:\n{dialogue_context}\n"
        f'assistant was about to reply: "{r_g}"\n'
        "# Task: Refine assistant's response with the following information:\n"
        f"{memory}\n"
        "# Output assistant's response to user in JSON.\n"
        'Format: {"assistant": <assistant refined response>}'
    )
    response = await claude.messages.create(
        model=MODEL_STANDARD,
        max_tokens=512,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}],
    )
    return _assistant_text(response.content[0].text)


def _vector(text: str) -> Counter[str]:
    return Counter(tokens(text))


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(value * right.get(key, 0) for key, value in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return dot / (left_norm * right_norm)


def _triple_text(triple: PersonaTriple) -> str:
    return f"{triple.subject} {triple.relation} {triple.object}"


def _assistant_text(text: str) -> str:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text.strip()
    return str(parsed.get("assistant", text)).strip()
