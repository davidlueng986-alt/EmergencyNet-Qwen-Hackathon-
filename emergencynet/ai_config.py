"""Qwen Cloud model matrix and env-driven AI configuration.

All optional AI paths should read models/timeouts from here so strategy
and agent never share a single conflicting BASE_AI_MODEL default.

No llama.cpp / Gemma / Ollama defaults — primary backend is Qwen Cloud
(DashScope OpenAI-compatible).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

# Default Qwen Cloud (international) OpenAI-compatible base.
DEFAULT_QWEN_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL_FIELD = "qwen3.7-plus"
DEFAULT_MODEL_VISION = "qwen3.7-plus"
DEFAULT_MODEL_STRATEGY = "qwen3.7-max"
DEFAULT_MODEL_AGENT = "qwen3.7-plus"

_dotenv_loaded = False


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def load_dotenv_files(extra_paths: Optional[list] = None) -> list:
    """Load KEY=VALUE from .env files into os.environ (no overwrite of set vars).

    Looks next to package root (emergencynet_v5/) and CWD. Safe if missing.
    Returns list of paths that contributed at least one new key.
    """
    global _dotenv_loaded
    candidates: list[Path] = []
    root = Path(__file__).resolve().parents[1]  # emergencynet_v5/
    candidates.append(root / ".env")
    candidates.append(root / ".env.local")
    candidates.append(Path.cwd() / ".env")
    if extra_paths:
        candidates.extend(Path(p) for p in extra_paths)

    loaded: list[str] = []
    for path in candidates:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        n = 0
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if not key:
                continue
            # Do not clobber already-exported process env
            if os.environ.get(key):
                continue
            os.environ[key] = val
            n += 1
        if n:
            loaded.append(str(path))
    _dotenv_loaded = True
    return loaded


def apply_runtime_credentials(
    api_key: str = "",
    base_url: str = "",
    model_field: str = "",
) -> None:
    """Push UI/runtime credentials into process env for subsequent load_ai_config()."""
    key = (api_key or "").strip()
    if key:
        os.environ["DASHSCOPE_API_KEY"] = key
        # Keep alias in sync
        os.environ["QWEN_API_KEY"] = key
    url = (base_url or "").strip().rstrip("/")
    if url:
        # Strip accidental /chat/completions suffix so chat_completions_url is stable
        if url.endswith("/chat/completions"):
            url = url[: -len("/chat/completions")]
        os.environ["QWEN_BASE_URL"] = url
    model = (model_field or "").strip()
    if model:
        os.environ["QWEN_MODEL_FIELD"] = model


@dataclass(frozen=True)
class AIConfig:
    api_key: str
    base_url: str
    mt_base_url: str
    model_field: str
    model_vision: str
    model_strategy: str
    model_agent: str
    timeout_sec: float
    agent_max_steps: int
    max_tokens: int
    debug_raw: bool

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)

    def with_overrides(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_field: Optional[str] = None,
    ) -> "AIConfig":
        kw = {}
        if api_key is not None and str(api_key).strip():
            kw["api_key"] = str(api_key).strip()
        if base_url is not None and str(base_url).strip():
            b = str(base_url).strip().rstrip("/")
            if b.endswith("/chat/completions"):
                b = b[: -len("/chat/completions")]
            kw["base_url"] = b
            kw["mt_base_url"] = b
        if model_field is not None and str(model_field).strip():
            kw["model_field"] = str(model_field).strip()
        return replace(self, **kw) if kw else self


def load_ai_config(*, reload_dotenv: bool = False) -> AIConfig:
    """Load Qwen Cloud config from environment (and optional .env once)."""
    if reload_dotenv or not _dotenv_loaded:
        load_dotenv_files()

    base = _env("QWEN_BASE_URL", DEFAULT_QWEN_BASE_URL)
    return AIConfig(
        api_key=_env("DASHSCOPE_API_KEY") or _env("QWEN_API_KEY"),
        base_url=base.rstrip("/"),
        mt_base_url=base.rstrip("/"),  # unused (MT dropped); keep field for compat
        model_field=_env("QWEN_MODEL_FIELD", DEFAULT_MODEL_FIELD),
        model_vision=_env("QWEN_MODEL_VISION", DEFAULT_MODEL_VISION),
        model_strategy=_env("QWEN_MODEL_STRATEGY", DEFAULT_MODEL_STRATEGY),
        model_agent=_env("QWEN_MODEL_AGENT", DEFAULT_MODEL_AGENT),
        timeout_sec=_env_float("QWEN_TIMEOUT_SEC", 60.0),
        agent_max_steps=_env_int("QWEN_AGENT_MAX_STEPS", 6),
        max_tokens=_env_int("QWEN_MAX_TOKENS", 4096),
        debug_raw=_env("QWEN_DEBUG_RAW", "0") in ("1", "true", "True", "yes"),
    )


def chat_completions_url(base_url: str) -> str:
    """Normalize OpenAI-compatible chat completions endpoint."""
    b = base_url.rstrip("/")
    if b.endswith("/chat/completions"):
        return b
    if b.endswith("/v1"):
        return b + "/chat/completions"
    if "/compatible-mode/v1" in b or b.endswith("compatible-mode/v1"):
        return b + "/chat/completions"
    return b + "/chat/completions"


# Gradio / mesh / LoRa ops (env-configurable)
def gradio_field_server() -> tuple[str, int]:
    host = _env("FIELD_GRADIO_HOST", "0.0.0.0")
    port = _env_int("FIELD_GRADIO_PORT", 7860)
    return host, port


def gradio_base_server() -> tuple[str, int]:
    host = _env("BASE_GRADIO_HOST", "0.0.0.0")
    port = _env_int("BASE_GRADIO_PORT", 7861)
    return host, port


def meshtastic_app_port() -> int:
    return _env_int("MESHTASTIC_APP_PORT", 256)


def mesh_alert_limits() -> tuple[float, int]:
    """Return (min_interval_s, max_alert_bytes)."""
    return (
        _env_float("MESH_MIN_INTERVAL_S", 30.0),
        _env_int("MESH_MAX_ALERT_BYTES", 200),
    )


def gateway_patient_cap() -> int:
    return _env_int("GATEWAY_PATIENT_CAP", 500)
