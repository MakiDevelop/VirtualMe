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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from virtualme.export.markdown import export_markdown
from virtualme.storage.db import DB, Dimension, Layer, init_db

# --- SYNTHETIC DEMO DATA — fictional persona, not a real person ---
# (dimension, layer, content, question_ids)
# PRINCIPLE-layer anchors with >=3 distinct question_ids export as
# "triangulated" core truths.
ANCHORS: list[tuple[Dimension, Layer, str, list[str]]] = [
    # SOUL — core identity / values (triangulated principles)
    (Dimension.SOUL, Layer.PRINCIPLE,
     "Ships imperfect things on purpose — a working v0.5 today beats a perfect "
     "v1.0 that never ships. 寧可今天出一個會動的 v0.5，也不要永遠出不了的完美 v1.0。",
     ["Q03", "Q11", "Q24"]),
    (Dimension.SOUL, Layer.PRINCIPLE,
     "Treats reversible decisions as cheap and irreversible ones as expensive — "
     "moves fast on the former, slows right down on the latter.",
     ["Q07", "Q18", "Q31"]),
    (Dimension.SOUL, Layer.PRINCIPLE,
     "Optimises for future attention, not raw output — 最稀缺的資源是專注力，不是工時。",
     ["Q05", "Q22", "Q29"]),
    (Dimension.SOUL, Layer.PATTERN,
     "Reaches for the smallest experiment that could disprove an idea before "
     "committing to it.",
     ["Q14"]),
    # BOUNDARIES — red lines (principles)
    (Dimension.BOUNDARIES, Layer.PRINCIPLE,
     "Never lets an automated agent send anything outward without a human review "
     "step — draft → review → ship, every time.",
     ["Q08", "Q19", "Q33"]),
    (Dimension.BOUNDARIES, Layer.PRINCIPLE,
     "Keeps private/sensitive context local; refuses to put it in shared or "
     "third-party spaces.",
     ["Q12", "Q26", "Q34"]),
    (Dimension.BOUNDARIES, Layer.PATTERN,
     "不在週末處理非緊急的工作訊息 — 保護休息與家庭時間。",
     ["Q21"]),
    # VOICE — how the agent should sound (patterns)
    (Dimension.VOICE, Layer.PATTERN,
     "Writes notes and commits in Traditional Chinese, code and APIs in English — "
     "中英混用是常態，不刻意統一。",
     ["Q09", "Q27"]),
    (Dimension.VOICE, Layer.PATTERN,
     "Direct and a little blunt; skips hedging. Says 'this is wrong because X' "
     "rather than 'maybe consider X'.",
     ["Q10", "Q28"]),
    (Dimension.VOICE, Layer.FACT,
     "Prefers concrete examples over abstract advice — 「給我看 code」勝過「跟我講理論」。",
     ["Q15"]),
    # SKILL — domain know-how (facts/patterns)
    (Dimension.SKILL, Layer.PATTERN,
     "Builds multi-agent systems with CLI + plain files instead of heavy "
     "frameworks; values things that still run when a vendor disappears.",
     ["Q16", "Q30"]),
    (Dimension.SKILL, Layer.FACT,
     "Runs a small home lab (single mini server + a VPS) with Docker; treats "
     "infrastructure as replaceable cattle, not pets.",
     ["Q17"]),
    (Dimension.SKILL, Layer.FACT,
     "熟悉本地 LLM 部署、向量檢索與 RAG pipeline。",
     ["Q23"]),
    # PEOPLE — relationships (facts)
    (Dimension.PEOPLE, Layer.FACT,
     "Collaborates with a small set of named AI agents, each given one clear role "
     "rather than one agent doing everything.",
     ["Q20"]),
    (Dimension.PEOPLE, Layer.FACT,
     "Has a partner and family whose time is explicitly protected on the calendar.",
     ["Q25"]),
    # HISTORY — life narrative (facts)
    (Dimension.HISTORY, Layer.FACT,
     "Moved from a sales/operations role into product, then into building personal "
     "AI infrastructure as a long-running side project.",
     ["Q01"]),
    (Dimension.HISTORY, Layer.FACT,
     "曾把一個副專案從 demo 養成有真實使用者的小產品。",
     ["Q02"]),
    # STATE — recent context (fact)
    (Dimension.STATE, Layer.FACT,
     "Currently maintaining several small open-source repos that together form a "
     "personal knowledge stack.",
     ["Q32"]),
]


async def seed_and_export(interviewee: str, out_dir: Path) -> list[Path]:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "demo.db")
        await init_db(db_path)
        db = DB(db_path)
        await db.init()
        for i, (dimension, layer, content, question_ids) in enumerate(ANCHORS):
            await db.save_anchor(
                interviewee_id=interviewee,
                dimension=dimension,
                layer=layer,
                content=content,
                source_turn_ids=[i + 1],
                source_question_ids=question_ids,
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
