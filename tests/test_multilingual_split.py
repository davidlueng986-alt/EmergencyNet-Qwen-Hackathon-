"""Multilingual escalate via plus only (no MT)."""
from __future__ import annotations

from emergencynet.multilingual import translate_and_review


def test_any_language_single_escalate_call():
    calls = []

    def escalate(prompt: str, system: str = None) -> str:
        calls.append((system or "", prompt))
        return (
            '{"detected_lang":"zh","translation_en":"trapped 45 min",'
            '"suggestions":[{"q":"q5","from":"No","to":"Yes","rationale":"45min"}]}'
        )

    answers = {f"q{i}": "No" for i in range(1, 13)}
    out = translate_and_review(
        "被困45分钟",
        answers,
        ai_callable=escalate,
        source_lang_hint="zh",
    )
    assert out["ok"]
    assert out["suggestions"][0]["q"] == "q5"
    assert len(calls) == 1


def test_empty_notes():
    out = translate_and_review("", {f"q{i}": "No" for i in range(1, 13)}, ai_callable=lambda p: "{}")
    assert out["ok"]
    assert out["suggestions"] == []
