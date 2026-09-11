import os

from runner.providers.base import Response, request_json


class Groq:
    def __init__(self, config):
        self.config = config
        if not os.environ.get("GROQ_API_KEY"):
            raise ValueError("Set GROQ_API_KEY in the local .env or environment")
        if config.logprobs:
            raise ValueError("Groq currently documents logprobs as unsupported; use two other methods")

    def generate(self, prompt, temperature=0.0):
        cfg = self.config
        raw, headers = request_json(
            "https://api.groq.com/openai/v1/chat/completions",
            {"model": cfg.model, "messages": [{"role": "user", "content": prompt}],
             "temperature": temperature, "max_completion_tokens": cfg.max_tokens,
             "response_format": {"type": "json_object"}, "stream": False},
            {"Authorization": "Bearer " + os.environ["GROQ_API_KEY"]}, cfg.timeout)
        choice = next(iter(raw.get("choices", [])), {})
        return Response(choice.get("message", {}).get("content") or "", raw,
                        raw.get("model", cfg.model), choice.get("finish_reason", "EMPTY"),
                        headers, choice.get("logprobs"))
