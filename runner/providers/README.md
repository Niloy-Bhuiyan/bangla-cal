# Providers

Only Gemini free tier, Groq free tier, and local Ollama are in scope for v1.
Paid OpenAI and Anthropic integrations remain unimplemented future work.
Never automatically fall back to a paid backend or enable billing.

Credentials load from the repo-local `.env` using python-dotenv; existing process
variables take precedence. Copy `.env.example`, fill in keys locally, and keep
`.env` ignored. Keys go only to the named provider's official HTTPS endpoint.

Configuration describes a free-tier account; it cannot inspect or override your
account's billing plan. Use accounts with billing disabled. No paid features,
grounding/search, caching, batch/flex processing, or paid fallback are requested.

Examples were checked against official documentation on 2026-09-11. Account
access can differ; use an explicitly verified free model available to your key:
[Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing),
[Gemini limits](https://ai.google.dev/gemini-api/docs/rate-limits),
[Groq free-plan limits](https://console.groq.com/docs/rate-limits).
Do not treat published quotas as guarantees for this account.

Groq uses its own OpenAI-compatible wire format, not the paid OpenAI service or
SDK. Its [API reference](https://console.groq.com/docs/api-reference) currently
marks logprobs unsupported. Gemini logprobs are opt-in and model-dependent;
unsupported requests fail explicitly. Local Ollama can return token logprobs per
its [chat API](https://docs.ollama.com/api/chat). Raw token scores are retained;
whole-JSON likelihood is not mislabeled as probability an answer is correct.

Ollama only calls loopback, uses installed local models, and does not download or
switch models automatically. Record its installed model digest with released runs.
