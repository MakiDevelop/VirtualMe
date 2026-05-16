from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from virtualme.config import Settings, sqlite_path
from virtualme.snapshot.core import export_snapshot
from virtualme.storage.db import DB


async def main() -> None:
    parser = argparse.ArgumentParser(description="Export a VirtualMe SOUL-lite snapshot.")
    parser.add_argument("--interviewee", default="local")
    parser.add_argument("--out", type=Path, default=Path("./exports"))
    parser.add_argument("--db", default=None)
    args = parser.parse_args()

    database_url = args.db if args.db is not None else Settings().database_url
    db = DB(sqlite_path(database_url))
    await db.init()
    paths = await export_snapshot(db, args.interviewee, args.out)
    for path in paths:
        print(path)


if __name__ == "__main__":
    asyncio.run(main())

