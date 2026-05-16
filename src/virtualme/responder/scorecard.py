from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from anthropic import AsyncAnthropic

from virtualme.config import Settings
from virtualme.responder.core import ResponderResult, respond
from virtualme.responder.persona import load_persona


def load_poc_messages() -> list[dict[str, str]]:
    text = (
        resources.files("virtualme.responder")
        .joinpath("poc_messages.yaml")
        .read_text(encoding="utf-8")
    )
    data = yaml.safe_load(text)
    messages = data.get("messages", []) if isinstance(data, dict) else []
    if not isinstance(messages, list):
        raise ValueError("poc_messages.yaml must contain a messages list")

    loaded: list[dict[str, str]] = []
    for message in messages:
        if not isinstance(message, dict) or "id" not in message or "text" not in message:
            raise ValueError("each PoC message must contain id and text")
        loaded.append({"id": str(message["id"]), "text": str(message["text"])})
    return loaded


async def build_scorecard(persona_dir: str | Path, claude: Any, settings: Settings | None = None) -> str:
    persona_context = load_persona(persona_dir)
    messages = load_poc_messages()
    generated_at = datetime.now(UTC).isoformat()

    results: list[tuple[dict[str, str], ResponderResult]] = []
    for message in messages:
        result = await respond(message["text"], persona_context, claude, settings)
        results.append((message, result))

    lines = [
        "# VirtualMe HR PoC Responder Scorecard",
        "",
        f"Generated at: {generated_at}",
        f"Persona dir: {persona_dir}",
        "",
        "## Messages",
        "",
    ]
    for message, result in results:
        lines.extend(
            [
                f"### {message['id']}",
                "",
                "**收到的訊息**",
                "",
                message["text"],
                "",
                "**Responder 回覆全文**",
                "",
                "```text",
                result.reply,
                "```",
                "",
                f"**is_liability:** {'true' if result.is_liability else 'false'}",
                "",
                "| 評分欄位 | 分數 / 結果 |",
                "|---|---|",
                "| voice 像我嗎 (1-5) |  |",
                "| correctness 專業對嗎 (1-5) |  |",
                "| acceptability 這樣回出去OK嗎 (Y/N) |  |",
                "| 備註 |  |",
                "",
            ]
        )

    lines.extend(
        [
            "## 判準提醒",
            "",
            "- voice+acceptability ≥8/12 可送出。",
            "- correctness 不可出現「自信講錯」的嚴重案例。",
            "",
        ]
    )
    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Build a VirtualMe HR PoC responder scorecard.")
    parser.add_argument("--persona-dir", required=True)
    parser.add_argument("--out", type=Path, default=Path("./exports/poc-scorecard"))
    args = parser.parse_args()

    settings = Settings()
    claude = AsyncAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        max_retries=4,
    )
    scorecard = await build_scorecard(args.persona_dir, claude, settings)

    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "scorecard.md"
    path.write_text(scorecard, encoding="utf-8")
    print(path)


if __name__ == "__main__":
    asyncio.run(main())
