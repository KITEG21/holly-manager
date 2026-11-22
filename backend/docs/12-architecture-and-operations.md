# Architecture and operations

## Services

| Service | Purpose | Default host port |
|---|---|---|
| web | React app (Vite) | 5174 |
| api | FastAPI; runs the database migrations on start | 8010 |
| worker | Celery jobs: estimates, document ingestion, proposal PDFs, embeddings | — |
| flower | Celery monitoring | 5555 |
| postgres | PostgreSQL 17 with pgvector | 5434 |
| redis | Celery broker | 6380 |
| ollama | Local fallback model and embeddings | 11600 |
| jaeger | OpenTelemetry traces | 16687 (UI) |

## AI models

Calls go through a LiteLLM router with a fallback chain. The available providers are:

| Name in `LLM_CHAIN` | Provider | Model setting | Credential |
|---|---|---|---|
| `gemini` | Gemini | `PRIMARY_MODEL` | `GEMINI_API_KEY` |
| `gemini_secondary` | A second Gemini model, useful when the first is overloaded | `SECONDARY_MODEL` | `GEMINI_API_KEY` |
| `claude` | Claude (Anthropic) | `CLAUDE_MODEL` (default `anthropic/claude-sonnet-5-5`) | `ANTHROPIC_API_KEY` |
| `openai` | Codex / GPT (OpenAI) | `OPENAI_MODEL` (default `openai/gpt-5`) | `OPENAI_API_KEY` |
| `ollama` | Local model | `FALLBACK_MODEL` | none |

`LLM_CHAIN` sets the order (default `gemini,gemini_secondary,claude,openai,ollama`). Providers without credentials are skipped, so adding a key is enough to bring a provider into the chain. Each remote call gives up after 30 seconds and moves to the next provider, and a provider that just failed is skipped for 5 minutes. If no provider has credentials, only the local model is used.

Admins can see the chain, which providers are active or temporarily skipped, and test each one from **Settings → AI providers**. Changes to `.env` need a restart of the api and worker containers.

All embeddings use a single model (`nomic-embed-text`) so every vector lives in the same space: contract chunks, documentation, and the task history.

## Background jobs

| Job | Triggered by |
|---|---|
| `estimate_project` | The client confirming the agreement |
| `render_proposal_pdf` | The sales agent generating a proposal |
| `ingest_document` | An admin uploading a contract or policy |
| `ingest_guide` / `sync_builtin_docs` | Documentation uploads (system and project) and syncing the built-in docs |
| `sync_agreement_doc` | The client confirming the agreement (and the first visit to a project's Docs tab) |
| `embed_historical` | Seeding history and closing tasks |

Follow them in Flower (http://localhost:5555).

## Observability

Every chat turn is traced in Jaeger (http://localhost:16687) as a `conversation.turn` span with nested `llm.*`, `tool.*` and `rag.*` spans. The rules applied, violations and tool calls are recorded as attributes. In **Clients → internal view**, every assistant message has a "trace" link that opens its trace.

## Common operations

| Task | Command |
|---|---|
| Start everything | `docker compose up -d` |
| Seed settings, history, documents and accounts | `docker compose exec api python -m app.seed` |
| Download the local models | `docker compose run --rm ollama-init` |
| Apply code changes (backend) | `docker compose restart api worker` |
| See logs | `docker compose logs -f api worker` |
| Run the tests | `cd backend && uv run pytest` (needs the postgres container) |

## Troubleshooting

| Problem | Fix |
|---|---|
| A port is already in use | Change it in `.env` (`API_PORT`, `PG_PORT`, `WEB_PORT`…) |
| Gemini returns 503 "high demand" | Temporary; the router falls back to the secondary model and then to the local model |
| "model not found" from Ollama | Run `docker compose run --rm ollama-init` |
| Documents stay pending | The first Docling run downloads its models; check the worker logs |
| The estimate failed | An escalation is created with the error; check the worker logs |
