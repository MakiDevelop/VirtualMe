"""Helpers for parsing JSON-shaped LLM responses."""

from __future__ import annotations

import re


def extract_json_payload(text: str) -> str:
    """Return the JSON substring from a possibly markdown-fenced LLM response.

    Handles ```json fences, bare ``` fences, and leading/trailing prose.
    """
    payload = text.strip()
    if payload.startswith("```"):
        payload = re.sub(r"^```[A-Za-z0-9_-]*\s*\n?", "", payload, count=1)
        payload = re.sub(r"\n?```\s*$", "", payload, count=1).strip()
    if not payload.startswith(("{", "[")):
        match = re.search(r"(\{.*\}|\[.*\])", payload, re.DOTALL)
        if match:
            payload = match.group(1).strip()
    return payload
