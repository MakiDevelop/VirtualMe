"""Central model-tier registry.

Each interview-engine LLM call selects a model by tier rather than a hardcoded
string. Tiers are environment-overridable so the whole pipeline can be
re-pointed (cheaper models, or a different vendor's compatible endpoint)
without touching call sites.

Overrides are read from process environment variables at import time
(VIRTUALME_MODEL_FAST / _STANDARD / _DEEP). They are intentionally NOT part
of pydantic Settings: model selection is an advanced, rarely-changed knob and
keeping it here avoids threading Settings through every extractor signature.
"""

from __future__ import annotations

import os

from anthropic import AsyncAnthropic

MODEL_FAST = os.getenv("VIRTUALME_MODEL_FAST", "claude-haiku-4-5")
MODEL_STANDARD = os.getenv("VIRTUALME_MODEL_STANDARD", "claude-sonnet-4-6")
MODEL_DEEP = os.getenv("VIRTUALME_MODEL_DEEP", "claude-opus-4-7")

_NO_TEMPERATURE_MODELS = {"claude-opus-4-7"}


async def create_message(client: AsyncAnthropic, **kwargs):
    """Central messages.create wrapper.

    Strips params unsupported by the target model (currently: temperature for
    claude-opus-4-7).
    """
    if kwargs.get("model") in _NO_TEMPERATURE_MODELS:
        kwargs.pop("temperature", None)
    return await client.messages.create(**kwargs)
