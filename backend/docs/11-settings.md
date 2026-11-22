# Settings

Admins configure every rule the agents and the estimate use in **Settings**. Changes apply to the next conversations and estimates; existing estimates and offers are not recalculated.

## Task types

Each task type has a name, a minimum and maximum number of hours, and a complexity (low, medium or high) that widens the pessimistic estimate. The minimum cannot be greater than the maximum, and names must be unique.

| Type | Default range | Complexity |
|---|---|---|
| backend | 6–24 h | medium |
| frontend | 4–20 h | medium |
| integration | 8–32 h | high |
| qa | 2–8 h | low |
| devops | 4–16 h | medium |
| design | 4–16 h | low |

## Team

| Setting | Default | Used for |
|---|---|---|
| People | 3 | Weekly target per person |
| Capacity per sprint | 180 h | Sprint planning and forecast |
| Velocity (fraction delivered) | 0.8 | Effective capacity = capacity × velocity |
| Sprint length | 2 weeks | Timeline in weeks |
| Deviation alert | 10% | When the forecast flags a project |

## Commercial rules

| Setting | Default |
|---|---|
| Hourly rate | €55/h |
| Minimum price | €6,000 |
| Maximum discount | 10% |
| Deposit | 30% |
| Milestones | Mid-project delivery 40%, Final delivery 30% |
| Included change rounds | 2 |
| Months of support | 3 |
| Maximum scope | 2,000 h |
| Risk margin | 15% |

The deposit plus the milestones must add up to exactly 100%, otherwise the settings are not saved.

## Qualification

The questions the agent asks, the weight of each criterion, which criteria are enabled, the qualified threshold (default 70), the nurture threshold (default 40) and the minimum realistic timeline (default 4 weeks). Weights are normalised, so they do not need to add up to 100.

## Documents

Upload contract templates and policies (PDF, DOCX, Markdown, HTML, TXT, PPTX). They are processed with Docling, split into sections and indexed for the sales agent's contract answers. The status changes from pending to ready, or failed with the error.

## AI providers

The **AI providers** card lists every provider in the fallback chain (Gemini, Claude, Codex/GPT and the local model) in order, with its model and status: Active, Skipped for a few minutes after a failure, No API key, or Not in chain. "Test" sends a short request to that single provider and shows the response time or the error; a successful test also brings a skipped provider back immediately. Keys and order are set in `.env` (see Architecture and operations).

## Environment settings

A few settings live in `.env` instead of the app: the AI providers and models (`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `PRIMARY_MODEL`, `SECONDARY_MODEL`, `CLAUDE_MODEL`, `OPENAI_MODEL`, `FALLBACK_MODEL`, `LLM_CHAIN`), `EMBEDDING_MODEL`, `HISTORY_MIN_SIMILARITY`, `SECRET_KEY`, `COMPANY_NAME` (the name clients see) and the host ports.
