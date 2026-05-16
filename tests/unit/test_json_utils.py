import json

from virtualme.interview.json_utils import extract_json_payload


def test_extract_json_payload_removes_json_fence():
    payload = extract_json_payload('```json\n{"ok": true}\n```')
    assert json.loads(payload) == {"ok": True}


def test_extract_json_payload_removes_bare_fence():
    payload = extract_json_payload('```\n[{"ok": true}]\n```')
    assert json.loads(payload) == [{"ok": True}]


def test_extract_json_payload_finds_json_inside_prose():
    payload = extract_json_payload('Here is the answer:\n{"assistant": "hi"}\nThanks.')
    assert json.loads(payload) == {"assistant": "hi"}
