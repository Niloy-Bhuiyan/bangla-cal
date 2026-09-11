from runner.providers.base import Response, request_json


class Ollama:
    def __init__(self, config):
        self.config = config

    def generate(self, prompt, temperature=0.0):
        cfg = self.config
        raw, headers = request_json("http://127.0.0.1:11434/api/chat",
            {"model": cfg.model, "messages": [{"role": "user", "content": prompt}],
             "stream": False, "format": "json", "think": False,
             "logprobs": cfg.logprobs,
             "options": {"temperature": temperature, "num_predict": cfg.max_tokens}},
            timeout=cfg.timeout)
        return Response(raw.get("message", {}).get("content", ""), raw,
                        raw.get("model", cfg.model), raw.get("done_reason", "unknown"),
                        headers, raw.get("logprobs"))
