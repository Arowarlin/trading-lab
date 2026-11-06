from __future__ import annotations

from tradinglab.llm import _strip_fences


def test_plain_json_untouched():
    assert _strip_fences('{"ok": true}') == '{"ok": true}'


def test_strips_json_fence():
    raw = '```json\n{"ok": true}\n```'
    assert _strip_fences(raw) == '{"ok": true}'


def test_strips_plain_fence():
    raw = '```\n{"ok": true}\n```'
    assert _strip_fences(raw) == '{"ok": true}'
