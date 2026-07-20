"""Mocked Qwen Cloud client tests (no network)."""
from __future__ import annotations

import json

from emergencynet.ai_config import AIConfig, chat_completions_url
from emergencynet.qwen_client import QwenClient


def _cfg(**kwargs):
    base = dict(
        api_key="sk-test",
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        mt_base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        model_field="qwen3.7-plus",
        model_vision="qwen3.7-plus",
        model_strategy="qwen3.7-max",
        model_agent="qwen3.7-plus",
        timeout_sec=5.0,
        agent_max_steps=4,
        max_tokens=256,
        debug_raw=False,
    )
    base.update(kwargs)
    return AIConfig(**base)


def test_chat_completions_url():
    assert chat_completions_url(
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    ).endswith("/chat/completions")


def test_chat_parses_content():
    def post(url, body, key, timeout):
        assert body["model"] == "qwen3.7-plus"
        assert "max_tokens" in body
        return {
            "choices": [{"message": {"content": '{"ok": true}'}}]
        }, None

    c = QwenClient(config=_cfg(), post_json=post)
    r = c.chat([{"role": "user", "content": "hi"}], model="qwen3.7-plus")
    assert r.ok
    assert "ok" in r.content


def test_json_mode_omits_max_tokens():
    seen = {}

    def post(url, body, key, timeout):
        seen["body"] = body
        return {
            "choices": [{"message": {"content": '{"a":1}'}}]
        }, None

    c = QwenClient(config=_cfg(), post_json=post)
    r = c.chat(
        [{"role": "user", "content": "Return JSON only"}],
        json_mode=True,
    )
    assert r.ok
    assert "max_tokens" not in seen["body"]
    assert seen["body"].get("response_format") == {"type": "json_object"}


def test_chat_parses_tool_calls():
    def post(url, body, key, timeout):
        assert "tools" in body
        return {
            "choices": [{
                "message": {
                    "content": "",
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "draft_mesh_alert",
                            "arguments": json.dumps({
                                "severity": "high",
                                "anomaly_type": "RED_SURGE",
                                "message_body": "Request USAR",
                            }),
                        },
                    }],
                }
            }]
        }, None

    c = QwenClient(config=_cfg(), post_json=post)
    r = c.chat(
        [{"role": "user", "content": "draft"}],
        tools=[{"type": "function", "function": {"name": "draft_mesh_alert"}}],
    )
    assert r.ok
    assert r.tool_calls[0]["function"]["name"] == "draft_mesh_alert"


def test_no_api_key():
    c = QwenClient(config=_cfg(api_key=""))
    r = c.chat([{"role": "user", "content": "x"}])
    assert not r.ok
    assert r.error == "no-api-key"


def test_thinking_json_repair_workaround():
    calls = {"n": 0}

    def post(url, body, key, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            # Malformed "thinking" answer
            return {
                "choices": [{"message": {
                    "content": "Here is the result: name is Alex",
                    "reasoning_content": "I should extract fields...",
                }}]
            }, None
        # Repair model returns valid JSON
        assert body.get("response_format") == {"type": "json_object"}
        assert "max_tokens" not in body
        return {
            "choices": [{"message": {"content": '{"name":"Alex"}'}}]
        }, None

    c = QwenClient(config=_cfg(), post_json=post)
    r = c.chat_json(
        [
            {"role": "system", "content": "Extract as JSON"},
            {"role": "user", "content": "My name is Alex"},
        ],
        model="qwen3.7-max",
        enable_thinking=True,
    )
    assert r.ok
    assert '"name"' in r.content
    assert calls["n"] == 2
