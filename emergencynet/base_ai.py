"""Base-station LLM wrapper over Qwen Cloud (tools + chat).

Delegates to ``QwenClient``. Used by ActionEngine / dashboard.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from .ai_config import load_ai_config
from .qwen_client import QwenClient


class BaseAI:
    """Base LLM via Qwen Cloud (agent model). No llama.cpp / Gemma / Ollama."""

    def __init__(
        self,
        endpoint: str | None = None,
        model: str | None = None,
        timeout_sec: float | None = None,
        max_tokens: int | None = None,
        client: Optional[QwenClient] = None,
        api_key: str | None = None,
        config: Optional[Any] = None,
    ):
        from .ai_config import chat_completions_url
        from .field_ai import _is_legacy_local_endpoint

        if endpoint and _is_legacy_local_endpoint(endpoint):
            endpoint = None
        cfg = config or load_ai_config()
        cfg = cfg.with_overrides(
            api_key=api_key,
            base_url=endpoint,
            model_field=model,
        )
        self.config = cfg
        self.endpoint = chat_completions_url(cfg.base_url)
        self.model = model or cfg.model_agent
        self.timeout_sec = timeout_sec if timeout_sec is not None else cfg.timeout_sec
        self.max_tokens = max_tokens if max_tokens is not None else cfg.max_tokens
        self._client = client or QwenClient(cfg)
        self._last_latency_ms: Optional[float] = None
        self._last_error: Optional[str] = None

    def available(self) -> bool:
        return self._client.available()

    def ping(self) -> tuple[bool, str]:
        if not self.available():
            return False, (
                "No API key. Set DASHSCOPE_API_KEY / QWEN_API_KEY, "
                "use emergencynet_v5/.env, or Base Settings → Apply."
            )
        text = self._client.chat_text(
            "Reply with exactly: pong",
            system="Connectivity probe. Reply with exactly: pong",
            model=self.model,
            enable_thinking=False,
        )
        self._last_latency_ms = self._client.last_latency_ms
        self._last_error = self._client.last_error
        if not text:
            return False, f"Qwen call failed: {self._last_error or 'empty'} (url={self.endpoint})"
        ms = self._last_latency_ms
        return True, f"OK — {ms:.0f} ms · model=`{self.model}` · `{self.endpoint}`"

    def chat(self, prompt: str, temperature: float = 0.0) -> str:
        text = self._client.chat_text(
            prompt,
            system="You are an Incident Command advisor. Output strict JSON only.",
            model=self.model,
            enable_thinking=False,
        )
        self._last_latency_ms = self._client.last_latency_ms
        self._last_error = self._client.last_error
        return text or ""

    def chat_with_tools(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
        temperature: float = 0.0,
        tool_choice: str = "auto",
        system_prompt: Optional[str] = None,
    ) -> str:
        """Return JSON-serialized assistant message (for ActionEngine parsers)."""
        default_sys = (
            "You are an Incident Command communications assistant. "
            "Use the provided functions to take action. Do not "
            "invent details outside the supplied context."
        )
        messages = [
            {"role": "system", "content": system_prompt or default_sys},
            {"role": "user", "content": prompt},
        ]
        resp = self._client.chat(
            messages,
            model=self.model,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=self.max_tokens,
            enable_thinking=False,
        )
        self._last_latency_ms = resp.latency_ms
        self._last_error = resp.error
        if not resp.ok:
            return ""
        # Serialize message shape expected by action_engine._extract_tool_call_args
        msg: Dict[str, Any] = {"content": resp.content or ""}
        if resp.tool_calls:
            msg["tool_calls"] = resp.tool_calls
        return json.dumps(msg)

    @property
    def last_latency_ms(self) -> Optional[float]:
        return self._last_latency_ms

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error
