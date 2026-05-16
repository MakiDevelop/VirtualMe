from __future__ import annotations

import random
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

from virtualme.storage.db import Anchor, Dimension, Question, Session


class QuestionSelector:
    def __init__(self, question_pool: dict[int, list[Question]]):
        self.question_pool = question_pool

    def select_next(
        self,
        session: Session,
        last_answer: str | None,
        accumulated_anchors: dict[Dimension, list[Anchor]],
        energy: int,
        asked_question_ids: set[str] | None = None,
        excluded_question_ids: set[str] | None = None,
        adaptive: bool = False,
    ) -> Question | None:
        asked = asked_question_ids or set()
        excluded = excluded_question_ids or set()
        questions = _flatten(self.question_pool) if adaptive else (
            self.question_pool.get(session.week) or _flatten(self.question_pool)
        )
        candidates = [question for question in questions if question.id not in excluded] or questions
        if not questions:
            return None
        if energy < 3:
            light = [q for q in candidates if q.energy_tax == "low"]
            return _prefer_dimension(light or questions, Dimension.STATE, asked)
        if last_answer:
            neighbor = _neighbor_dimension(last_answer)
            if neighbor:
                match = _prefer_dimension(candidates, neighbor, asked)
                if match:
                    return match
        if random.random() < 0.1:
            state = _prefer_dimension(candidates, Dimension.STATE, asked)
            if state:
                return state
        target = _biggest_gap(accumulated_anchors, candidates)
        fallback = next((question for question in candidates if question.id not in asked), candidates[0])
        return _prefer_dimension(candidates, target, asked) or fallback


def default_question_pool_path() -> Path:
    return Path(str(files("virtualme").joinpath("data/question-pool.yaml")))


def load_question_pool(path: str | Path | None = None) -> dict[int, list[Question]]:
    source = default_question_pool_path() if path is None else Path(path)
    raw = yaml.safe_load(source.read_text(encoding="utf-8")) or []
    items = _question_items(raw)
    placeholders = _default_placeholders(raw)
    pool: dict[int, list[Question]] = {}
    for item in items:
        question = Question(**_substitute_placeholders(item, placeholders))
        pool.setdefault(question.week, []).append(question)
    return pool


def _question_items(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        questions = raw.get("questions", [])
        if isinstance(questions, list):
            return questions
    raise ValueError("question pool YAML must be a list or contain a questions list")


def _default_placeholders(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    placeholders = raw.get("default_placeholders", {})
    if not isinstance(placeholders, dict):
        return {}
    return {str(key): str(value) for key, value in placeholders.items()}


def _substitute_placeholders(
    item: dict[str, Any], placeholders: dict[str, str]
) -> dict[str, Any]:
    if not placeholders:
        return item
    substituted = dict(item)
    for field in ("text", "rationale_probe"):
        value = substituted.get(field)
        if isinstance(value, str):
            substituted[field] = value.format_map(_SafePlaceholderMap(placeholders))
    return substituted


class _SafePlaceholderMap(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _flatten(pool: dict[int, list[Question]]) -> list[Question]:
    return [question for questions in pool.values() for question in questions]


def _neighbor_dimension(answer: str) -> Dimension | None:
    lowered = answer.lower()
    if any(
        word in lowered
        for word in (
            "client",
            "customer",
            "stakeholder",
            "客戶",
            "顧客",
            "對方",
            "客人",
            "利害關係人",
        )
    ):
        return Dimension.PEOPLE
    if any(
        word in lowered
        for word in ("write", "build", "sell", "teach", "寫", "賣", "教", "設計", "建立", "打造")
    ):
        return Dimension.SKILL
    return None


def _biggest_gap(anchors: dict[Dimension, list[Anchor]], questions: list[Question]) -> Dimension:
    candidate_dimensions = {question.dimension for question in questions} or set(Dimension)
    counts = {dimension: len(anchors.get(dimension, [])) for dimension in candidate_dimensions}
    return min(counts, key=counts.get)


def _prefer_dimension(
    questions: list[Question], dimension: Dimension, asked: set[str]
) -> Question | None:
    same_dim = [question for question in questions if question.dimension == dimension]
    unasked = [question for question in same_dim if question.id not in asked]
    pool = unasked or same_dim
    return pool[0] if pool else None
