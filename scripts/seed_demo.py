#!/usr/bin/env python3
"""Seed a synthetic demo persona and export it to examples/.

This populates a throwaway database with a SYNTHETIC, FICTIONAL persona
(no real person) and runs the real export pipeline, so a fresh cloner can
see what a VirtualMe persona archive looks like without doing 8 weeks of
interviews.

The persona is bilingual (English + Traditional Chinese) on purpose, to
show the CJK-aware extraction path.

Usage:
    python scripts/seed_demo.py
    python scripts/seed_demo.py --out examples --interviewee sample-maker
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from virtualme.export.markdown import export_markdown
from virtualme.storage.db import DB, Dimension, Layer, init_db

# --- SYNTHETIC DEMO DATA — fictional persona, not a real person ---


@dataclass(frozen=True)
class AnchorSeed:
    dimension: Dimension
    layer: Layer
    content: str
    source_question_ids: tuple[str, ...]
    source_weeks: tuple[int, ...]


# PRINCIPLE anchors with three distinct question IDs become recurring. They enter
# the validated section only when their source turns span multiple sessions.
ANCHORS: list[AnchorSeed] = [
    # SOUL — core identity / values
    AnchorSeed(
        Dimension.SOUL,
        Layer.PRINCIPLE,
        "Across the synthetic interviews so far, the maker tends to ship imperfect "
        "things on purpose — a working v0.5 today beats a perfect v1.0 that never "
        "ships. 寧可今天出一個會動的 v0.5，也不要永遠出不了的完美 v1.0。",
        ("Q03", "Q11", "Q24"),
        (1, 4, 7),
    ),
    AnchorSeed(
        Dimension.SOUL,
        Layer.PRINCIPLE,
        "Across the synthetic interviews, commitments that lock scope, price, or "
        "delivery dates appear to be treated as expensive decisions; the maker "
        "slows down before promising all three.",
        ("Q07", "Q18", "Q31"),
        (2, 5, 8),
    ),
    AnchorSeed(
        Dimension.SOUL,
        Layer.PRINCIPLE,
        "Across several synthetic sessions, future attention appears to matter "
        "more than raw output — 最稀缺的資源是專注力，不是工時。",
        ("Q05", "Q22", "Q29"),
        (1, 4, 8),
    ),
    AnchorSeed(
        Dimension.SOUL,
        Layer.PRINCIPLE,
        "Within one synthetic session, the maker repeatedly reached for the "
        "smallest experiment that could disprove an idea before committing to it.",
        ("Q14", "Q35", "Q36"),
        (3, 3, 3),
    ),
    # BOUNDARIES — red lines
    AnchorSeed(
        Dimension.BOUNDARIES,
        Layer.PRINCIPLE,
        "Across the synthetic interviews, outbound automated messages tend to stay "
        "in draft until a human review — draft → review → ship.",
        ("Q08", "Q19", "Q33"),
        (2, 5, 7),
    ),
    AnchorSeed(
        Dimension.BOUNDARIES,
        Layer.PRINCIPLE,
        "The synthetic interviews suggest that private or sensitive context should "
        "remain local rather than enter shared or third-party spaces.",
        ("Q12", "Q26", "Q34"),
        (1, 4, 8),
    ),
    AnchorSeed(
        Dimension.BOUNDARIES,
        Layer.PRINCIPLE,
        "Within one synthetic session, requests that exceed the agreed scope were "
        "repeatedly refused unless scope, budget, or timeline changed.",
        ("Q39", "Q40", "Q41"),
        (6, 6, 6),
    ),
    AnchorSeed(
        Dimension.BOUNDARIES,
        Layer.PATTERN,
        "One synthetic answer suggested protecting weekends from non-urgent work "
        "messages — 不在週末處理非緊急的工作訊息。",
        ("Q21",),
        (6,),
    ),
    # VOICE — how the agent should sound
    AnchorSeed(
        Dimension.VOICE,
        Layer.PRINCIPLE,
        "Within one synthetic session, refusals tended to name the constraint "
        "mismatch in one sentence, then offer two concrete options instead of a "
        "long apology.",
        ("Q10", "Q28", "Q37"),
        (5, 5, 5),
    ),
    AnchorSeed(
        Dimension.VOICE,
        Layer.PATTERN,
        "Two synthetic answers suggested mixing Traditional Chinese notes with "
        "English code and API terms — 中英混用是常態，不刻意統一。",
        ("Q09", "Q27"),
        (4, 4),
    ),
    AnchorSeed(
        Dimension.VOICE,
        Layer.FACT,
        "One synthetic answer suggested a direct but not hostile register: "
        "「這個條件目前對不上，我不能照原案承諾。」",
        ("Q15",),
        (6,),
    ),
    # SKILL — domain know-how
    AnchorSeed(
        Dimension.SKILL,
        Layer.PRINCIPLE,
        "Within one synthetic session, the maker repeatedly preferred CLI plus "
        "plain files over heavy frameworks, especially for tools that should "
        "survive vendor changes.",
        ("Q16", "Q30", "Q38"),
        (2, 2, 2),
    ),
    AnchorSeed(
        Dimension.SKILL,
        Layer.FACT,
        "One synthetic answer described a small fictional lab made of one mini "
        "server and one VPS, both running Docker.",
        ("Q17",),
        (3,),
    ),
    AnchorSeed(
        Dimension.SKILL,
        Layer.FACT,
        "One synthetic answer mentioned experimenting with local language models, "
        "vector search, and a small RAG pipeline.",
        ("Q23",),
        (6,),
    ),
    # PEOPLE — relationships
    AnchorSeed(
        Dimension.PEOPLE,
        Layer.FACT,
        "One synthetic answer described collaborating with a small set of "
        "fictional AI agents, each assigned one clear role.",
        ("Q20",),
        (2,),
    ),
    AnchorSeed(
        Dimension.PEOPLE,
        Layer.FACT,
        "One synthetic answer suggested explicitly reserving calendar time for a "
        "fictional household and close relationships.",
        ("Q25",),
        (5,),
    ),
    # HISTORY — life narrative
    AnchorSeed(
        Dimension.HISTORY,
        Layer.FACT,
        "One synthetic answer described a fictional career path from operations to "
        "product work, then to personal AI tooling as a side project.",
        ("Q01",),
        (1,),
    ),
    AnchorSeed(
        Dimension.HISTORY,
        Layer.FACT,
        "One synthetic answer described growing a fictional side project from a "
        "demo into a tiny product with test users.",
        ("Q02",),
        (3,),
    ),
    # STATE — recent context
    AnchorSeed(
        Dimension.STATE,
        Layer.FACT,
        "At the latest synthetic session, the maker appeared to be maintaining "
        "several small open-source repositories as one personal knowledge stack.",
        ("Q32",),
        (8,),
    ),
]


async def seed_and_export(interviewee: str, out_dir: Path) -> list[Path]:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "demo.db")
        await init_db(db_path)
        db = DB(db_path)
        await db.init()
        for anchor_index, seed in enumerate(ANCHORS, start=1):
            source_turn_ids: list[int] = []
            for evidence_index, week in enumerate(seed.source_weeks, start=1):
                session = await db.get_or_create_session(interviewee, week=week)
                turn = await db.save_turn(
                    session.id,
                    "user",
                    f"Synthetic evidence {anchor_index}.{evidence_index}; no real-person data.",
                )
                source_turn_ids.append(turn.id)
            await db.save_anchor(
                interviewee_id=interviewee,
                dimension=seed.dimension,
                layer=seed.layer,
                content=seed.content,
                source_turn_ids=source_turn_ids,
                source_question_ids=list(seed.source_question_ids),
                model="synthetic-demo",
            )
        return await export_markdown(db, interviewee, out_dir)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a synthetic demo persona and export it.")
    parser.add_argument("--interviewee", default="sample-maker")
    parser.add_argument("--out", type=Path, default=Path("examples"))
    args = parser.parse_args()

    written = await seed_and_export(args.interviewee, args.out)
    print(f"Exported {len(written)} files to {args.out / args.interviewee}/")
    for path in written:
        print(f"  - {path}")


if __name__ == "__main__":
    asyncio.run(main())
