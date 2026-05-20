from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from zoneinfo import ZoneInfo

from virtualme.export.auto import auto_export_persona
from virtualme.interview.progress_card import (
    calculate_weighted_completion,
    render_coverage_summary,
    weakest_dimension_labels,
)
from virtualme.interview.turn_state import CoverageSnapshot
from virtualme.storage.db import DB

_TAIPEI = ZoneInfo("Asia/Taipei")
_EXPORT_NOTE = "本次匯出說明.txt"


@dataclass(frozen=True)
class PersonaExportPackage:
    zip_path: Path
    file_name: str
    caption: str
    written_files: list[Path]


async def build_persona_export_package(
    db: DB,
    interviewee_id: str,
    export_dir: str,
    snapshot: CoverageSnapshot,
    now: datetime | None = None,
) -> PersonaExportPackage:
    """Export persona markdown, add the user-facing note, commit, and zip files."""
    exported_at = now.astimezone(_TAIPEI) if now else datetime.now(_TAIPEI)
    note = render_export_note(snapshot, exported_at)
    written = await auto_export_persona(
        db,
        interviewee_id,
        export_dir,
        extra_files={_EXPORT_NOTE: note},
    )

    file_name = f"VirtualMe_人格檔_{exported_at:%Y%m%d}.zip"
    zip_dir = Path(export_dir) / "_packages" / interviewee_id
    zip_dir.mkdir(parents=True, exist_ok=True)
    zip_path = zip_dir / file_name
    _write_zip(zip_path, written, Path(export_dir) / interviewee_id)
    return PersonaExportPackage(
        zip_path=zip_path,
        file_name=file_name,
        caption="你的人格檔 zip 已準備好",
        written_files=written,
    )


def render_export_note(snapshot: CoverageSnapshot, exported_at: datetime) -> str:
    completion = calculate_weighted_completion(snapshot)
    weak = "、".join(weakest_dimension_labels(snapshot)) or "暫無"
    return "\n".join(
        [
            "本次匯出說明",
            "",
            f"匯出時間：{exported_at.isoformat(timespec='seconds')}",  # noqa: RUF001
            f"目前加權完成度：約 {completion}%",  # noqa: RUF001
            "",
            "目前 8 維 × 3 層覆蓋情況：",  # noqa: RUF001
            render_coverage_summary(snapshot),
            "",
            f"較弱維度提醒：{weak}",  # noqa: RUF001
            "",
            "這是階段性版本，隨著訪談繼續會越來越成熟。",  # noqa: RUF001
            "",
        ]
    )


def _write_zip(zip_path: Path, paths: list[Path], subject_dir: Path) -> None:
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            archive.write(path, arcname=path.relative_to(subject_dir))
