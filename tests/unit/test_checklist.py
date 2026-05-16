import pytest

from virtualme.storage.db import DB, POC_CHECKLIST_TEMPLATE, ChecklistItem
from virtualme.subject import render_checklist_md


async def test_seed_poc_checklist_creates_items_and_preserves_done(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()

    first = await db.seed_poc_checklist("friend0")
    await db.set_checklist_item("friend0", "persona_exported", True)
    second = await db.seed_poc_checklist("friend0")

    assert len(first) == 7
    assert len(second) == 7
    exported = next(item for item in second if item.item_key == "persona_exported")
    assert exported.done is True


async def test_get_checklist_returns_template_order_and_empty_for_missing(tmp_path):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()

    assert await db.get_checklist("missing") == []

    items = await db.seed_poc_checklist("friend0")

    assert [item.item_key for item in items] == [
        item_key for item_key, _label in POC_CHECKLIST_TEMPLATE
    ]


async def test_set_checklist_item_toggles_done_updates_timestamp_and_rejects_unknown(
    tmp_path,
):
    db = DB(str(tmp_path / "virtualme.db"))
    await db.init()
    await db.seed_poc_checklist("friend0")

    async with db._connect() as conn:
        await conn.execute(
            """
            UPDATE checklist_items
            SET updated_at = '2000-01-01 00:00:00'
            WHERE interviewee_id = ? AND item_key = ?
            """,
            ("friend0", "persona_exported"),
        )
        await conn.commit()

    checked = await db.set_checklist_item("friend0", "persona_exported", True)
    unchecked = await db.set_checklist_item("friend0", "persona_exported", False)

    assert checked.done is True
    assert checked.updated_at is not None
    assert checked.updated_at != "2000-01-01 00:00:00"
    assert unchecked.done is False
    with pytest.raises(ValueError, match="checklist item not found"):
        await db.set_checklist_item("friend0", "unknown", True)


def test_render_checklist_md_outputs_checked_and_unchecked():
    items = [
        ChecklistItem(
            interviewee_id="friend0",
            item_key=item_key,
            label=label,
            done=index == 0,
            note="done" if index == 0 else None,
        )
        for index, (item_key, label) in enumerate(POC_CHECKLIST_TEMPLATE[:2])
    ]

    text = render_checklist_md(items)

    assert "- [x]" in text
    assert "- [ ]" in text
    assert "done" in text
