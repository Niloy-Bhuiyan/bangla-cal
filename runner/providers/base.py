from dataclasses import dataclass
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


def load_secrets():
    load_dotenv(ROOT / ".env", override=False)


def redact(text):
    for key in ("GEMINI_API_KEY", "GROQ_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


class ProviderError(RuntimeError):
    def __init__(self, status, detail, headers=None):
        self.status = status
        self.detail = redact(detail)
        self.headers = headers or {}
        super().__init__(f"HTTP {status}: {self.detail}")


def request_json(url, payload=None, headers=None, timeout=90):
    request = Request(url, data=None if payload is None else json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json", "User-Agent": "bangla-cal/0.1 (research)",
                               **(headers or {})})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read())
            response_headers = dict(response.headers)
    except HTTPError as exc:
        # Preserve the actual quota error and Retry-After, without credentials.
        raise ProviderError(exc.code, exc.read().decode(errors="replace"),
                            dict(exc.headers)) from None
    except (URLError, TimeoutError) as exc:
        raise ProviderError(0, str(exc)) from None
    safe_headers = {k.lower(): v for k, v in response_headers.items()
                    if k.lower().startswith("x-ratelimit") or k.lower() in
                    ("retry-after", "x-request-id")}
    return body, safe_headers


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    model: str
    tier: str = "free"
    max_tokens: int = 512
    interval_seconds: float = 6.0
    timeout: int = 90
    logprobs: bool = False

    def __post_init__(self):
        if self.provider not in ("gemini", "groq", "ollama"):
            raise ValueError("v1 permits only Gemini, Groq, and local Ollama")
        if self.tier != ("local" if self.provider == "ollama" else "free"):
            raise ValueError("v1 requires a free-tier account or local Ollama")
        if not self.model or self.max_tokens < 1 or self.interval_seconds < 0 or self.timeout < 1:
            raise ValueError("invalid model configuration")
        if self.provider == "ollama" and "cloud" in self.model.lower():
            raise ValueError("Ollama cloud models are out of scope; use a local model")


@dataclass
class Response:
    text: str
    raw: dict
    model_version: str
    finish_reason: str
    headers: dict
    logprobs: object = None


def get_provider(config):
    load_secrets()
    from runner.providers.gemini import Gemini
    from runner.providers.groq import Groq
    from runner.providers.ollama import Ollama
    return {"gemini": Gemini, "groq": Groq, "ollama": Ollama}[config.provider](config)
