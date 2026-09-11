import os
from urllib.parse import quote

from runner.providers.base import Response, request_json


class Gemini:
    def __init__(self, config):
        self.config = config
        if not os.environ.get("GEMINI_API_KEY"):
            raise ValueError("Set GEMINI_API_KEY in the local .env or environment")

    def generate(self, prompt, temperature=0.0):
        cfg = self.config
        generation = {"temperature": temperature, "maxOutputTokens": cfg.max_tokens,
                      "responseMimeType": "application/json"}
        if cfg.logprobs:
            generation.update(responseLogprobs=True, logprobs=1)
        raw, headers = request_json(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            + quote(cfg.model, safe="") + ":generateContent",
            {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
             "generationConfig": generation},
            {"x-goog-api-key": os.environ["GEMINI_API_KEY"]}, cfg.timeout)
        candidate = next(iter(raw.get("candidates", [])), {})
        text = "".join(p.get("text", "") for p in candidate.get("content", {}).get("parts", [])
                       if not p.get("thought"))
        return Response(text, raw, raw.get("modelVersion", cfg.model),
                        candidate.get("finishReason", "BLOCKED_OR_EMPTY"), headers,
                        candidate.get("logprobsResult"))
