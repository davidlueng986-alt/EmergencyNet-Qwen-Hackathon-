"""Unified Qwen Cloud HTTP client (OpenAI-compatible Chat Completions).

Uses stdlib urllib. Tests inject ``post_json``.

Structured output (non-thinking):
  response_format={"type":"json_object"} and prompt must contain "JSON".
  Do not set max_tokens when json_mode=True (Qwen docs: avoids truncated JSON).

Thinking + JSON (strategy):
  Prefer enable_thinking=True with response_format json_object when supported.
  Fallback "thinking mode workaround" (official FAQ): think first without forced
  JSON if parse fails, then repair with a non-thinking flash-style model + json_object.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from urllib import request

from .ai_config import AIConfig, chat_completions_url, load_ai_config


@dataclass
class QwenResponse:
    content: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    reasoning_content: Optional[str] = None
    raw: Any = None
    latency_ms: Optional[float] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _http_post(
    url: str,
    body: Dict[str, Any],
    api_key: str,
    timeout_sec: float,
) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    data = json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    req = request.Request(url, data=data, method="POST", headers=headers)
    try:
        with request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8")
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
    try:
        return json.loads(raw), None
    except json.JSONDecodeError as exc:
        return None, f"parse-error: {exc}"


def _parse_message(obj: Dict[str, Any]) -> QwenResponse:
    try:
        msg = obj["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        return QwenResponse(error=f"bad-response-shape: {exc}", raw=obj)

    content = msg.get("content") or ""
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(str(p.get("text", "")))
            elif isinstance(p, str):
                parts.append(p)
        content = "".join(parts)

    tool_calls_raw = msg.get("tool_calls") or []
    tool_calls: List[Dict[str, Any]] = []
    for tc in tool_calls_raw:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") or {}
        tool_calls.append({
            "id": tc.get("id") or "",
            "type": tc.get("type") or "function",
            "function": {
                "name": fn.get("name") or "",
                "arguments": fn.get("arguments") or "{}",
            },
        })

    return QwenResponse(
        content=str(content),
        tool_calls=tool_calls,
        reasoning_content=msg.get("reasoning_content"),
        raw=obj,
    )


class QwenClient:
    """Chat / vision / tools against Qwen Cloud."""

    def __init__(
        self,
        config: Optional[AIConfig] = None,
        post_json: Optional[
            Callable[[str, Dict[str, Any], str, float], tuple[Optional[Dict[str, Any]], Optional[str]]]
        ] = None,
    ):
        self.config = config or load_ai_config()
        self._post = post_json or _http_post
        self._last_latency_ms: Optional[float] = None
        self._last_error: Optional[str] = None

    @property
    def last_latency_ms(self) -> Optional[float]:
        return self._last_latency_ms

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def available(self) -> bool:
        return bool(self.config.has_api_key)

    def chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        model: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Any = "auto",
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        enable_thinking: bool = False,
        json_mode: bool = False,
        extra_body: Optional[Dict[str, Any]] = None,
    ) -> QwenResponse:
        if not self.config.has_api_key:
            self._last_error = "no-api-key"
            return QwenResponse(error="no-api-key")

        body: Dict[str, Any] = {
            "model": model or self.config.model_field,
            "messages": messages,
            "temperature": float(temperature),
        }
        # Qwen structured-output docs: do NOT set max_tokens when json_mode
        if not json_mode:
            body["max_tokens"] = int(
                max_tokens if max_tokens is not None else self.config.max_tokens
            )
        if tools:
            body["tools"] = tools
            body["tool_choice"] = tool_choice
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        extra = dict(extra_body or {})
        if enable_thinking:
            extra["enable_thinking"] = True
        elif "enable_thinking" not in extra:
            if tools or json_mode:
                extra["enable_thinking"] = False
        if extra:
            body.update(extra)

        url = chat_completions_url(self.config.base_url)
        t0 = time.time()
        obj, err = self._post(url, body, self.config.api_key, self.config.timeout_sec)
        self._last_latency_ms = (time.time() - t0) * 1000.0
        if err:
            self._last_error = err
            return QwenResponse(error=err, latency_ms=self._last_latency_ms)
        self._last_error = None
        parsed = _parse_message(obj or {})
        parsed.latency_ms = self._last_latency_ms
        if self.config.debug_raw and obj is not None:
            print("=" * 40, "\nQWEN RAW:\n", json.dumps(obj)[:4000], flush=True)
        return parsed

    def chat_json(
        self,
        messages: List[Dict[str, Any]],
        *,
        model: Optional[str] = None,
        enable_thinking: bool = False,
        repair_model: Optional[str] = None,
    ) -> QwenResponse:
        """JSON output helper.

        - Non-thinking: json_mode=True, no max_tokens.
        - Thinking (e.g. strategy max): try thinking + json_object first; if
          content is not valid JSON, run official two-step repair with a
          non-thinking model (default: same as model_field / plus).
        """
        # Ensure "JSON" appears in messages (API requirement)
        messages = _ensure_json_word(messages)

        resp = self.chat(
            messages,
            model=model,
            enable_thinking=enable_thinking,
            json_mode=True,
        )
        if not resp.ok:
            return resp

        text = (resp.content or "").strip()
        if _looks_like_json(text):
            return resp

        # Thinking mode workaround (official FAQ): repair with non-thinking JSON model
        if enable_thinking and text:
            fix_model = repair_model or self.config.model_field
            fix_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a JSON format expert. Fix the user's text into a "
                        "valid JSON object only. Output JSON only."
                    ),
                },
                {"role": "user", "content": text},
            ]
            fixed = self.chat(
                fix_messages,
                model=fix_model,
                enable_thinking=False,
                json_mode=True,
            )
            if fixed.ok and _looks_like_json(fixed.content or ""):
                fixed.reasoning_content = resp.reasoning_content or resp.content
                return fixed
            return QwenResponse(
                content=text,
                reasoning_content=resp.reasoning_content,
                error="json-parse-failed-after-repair",
                raw=resp.raw,
                latency_ms=resp.latency_ms,
            )
        return resp

    def chat_text(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        model: Optional[str] = None,
        enable_thinking: bool = False,
        json_mode: bool = False,
    ) -> str:
        messages: List[Dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        if json_mode or enable_thinking:
            resp = self.chat_json(
                messages, model=model, enable_thinking=enable_thinking,
            )
        else:
            resp = self.chat(messages, model=model, enable_thinking=enable_thinking)
        if not resp.ok:
            return ""
        return resp.content

    def chat_vision(
        self,
        text: str,
        image_b64: str,
        *,
        mime: str = "image/jpeg",
        system: Optional[str] = None,
        model: Optional[str] = None,
        json_mode: bool = True,
    ) -> QwenResponse:
        user_content: List[Dict[str, Any]] = [
            {"type": "text", "text": text if "json" in text.lower() else text + "\nReturn JSON only."},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{image_b64}"},
            },
        ]
        messages: List[Dict[str, Any]] = []
        if system:
            sys = system if "json" in system.lower() else system + " Output JSON."
            messages.append({"role": "system", "content": sys})
        messages.append({"role": "user", "content": user_content})
        return self.chat(
            messages,
            model=model or self.config.model_vision,
            enable_thinking=False,
            json_mode=json_mode,
        )


def _ensure_json_word(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    blob = json.dumps(messages, ensure_ascii=False).lower()
    if "json" in blob:
        return messages
    out = list(messages)
    out.append({
        "role": "user",
        "content": "Respond with a single JSON object only.",
    })
    return out


def _looks_like_json(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:].strip()
    try:
        start = t.find("{")
        end = t.rfind("}")
        if start < 0 or end <= start:
            return False
        json.loads(t[start:end + 1])
        return True
    except json.JSONDecodeError:
        return False


_default: Optional[QwenClient] = None


def get_client(config: Optional[AIConfig] = None) -> QwenClient:
    global _default
    if config is not None:
        return QwenClient(config=config)
    if _default is None:
        _default = QwenClient()
    return _default


def reset_default_client() -> None:
    global _default
    _default = None
