from __future__ import annotations

import argparse
import asyncio

from virtualme.config import sqlite_path
from virtualme.storage.db import DB
from virtualme.subject import render_checklist_md, score_completeness


async def main() -> None:
    parser = argparse.ArgumentParser(description="Show VirtualMe subject extraction status.")
    parser.add_argument("--db", required=True, help="SQLite URL, e.g. sqlite:///./data/virtualme.db")
    parser.add_argument("--interviewee", required=True)
    check_group = parser.add_mutually_exclusive_group()
    check_group.add_argument("--check", metavar="ITEM_KEY")
    check_group.add_argument("--uncheck", metavar="ITEM_KEY")
    args = parser.parse_args()

    db = DB(sqlite_path(args.db))
    subject = await db.get_subject(args.interviewee)
    if subject is None:
        print(f"Subject not found: {args.interviewee}")
        return

    checklist = await db.get_checklist(args.interviewee)
    if not checklist:
        checklist = await db.seed_poc_checklist(args.interviewee)

    if args.check or args.uncheck:
        await db.set_checklist_item(
            args.interviewee,
            args.check or args.uncheck,
            done=args.check is not None,
        )
        print(render_checklist_md(await db.get_checklist(args.interviewee)))
        return

    anchors_by_dimension = await db.load_anchors_summary(args.interviewee)
    report = score_completeness(anchors_by_dimension)

    print(f"Subject: {subject.display_name or subject.interviewee_id}")
    print(f"domain: {subject.domain.value}")
    print(f"status: {subject.status.value}")
    print(f"goal: {subject.goal or ''}")
    print()

    for score in report.per_dimension:
        print(
            f"{score.dimension.value} | anchors {score.anchor_count} | "
            f"triangulated {score.triangulated_count} | coverage {score.coverage:.0%}"
        )

    print()
    print(f"總完成度 {report.total_score:.1f}%")
    if report.weakest is not None:
        print(f"建議下次對話多聊 {report.weakest.value}")
    print()
    print(render_checklist_md(checklist))


if __name__ == "__main__":
    asyncio.run(main())
