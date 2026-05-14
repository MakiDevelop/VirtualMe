import argparse
import asyncio
from pathlib import Path

from virtualme.config import Settings, sqlite_path
from virtualme.export.markdown import export_markdown
from virtualme.storage.db import DB


async def main() -> None:
    parser = argparse.ArgumentParser(description="Export VirtualMe anchors to markdown.")
    parser.add_argument("--interviewee", default="local")
    parser.add_argument("--out", type=Path, default=Path("./exports"))
    parser.add_argument("--db", default=None)
    args = parser.parse_args()

    database_url = args.db if args.db is not None else Settings().database_url
    db_path = sqlite_path(database_url)
    paths = await export_markdown(DB(db_path), args.interviewee, args.out)
    for path in paths:
        print(path)


if __name__ == "__main__":
    asyncio.run(main())
