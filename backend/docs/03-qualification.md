# Lead qualification

The qualification agent decides whether a new client is a real opportunity before the team spends time on requirements.

## How a turn works

1. The model reads the conversation and extracts evidence into a fixed structure: budget (in euros), timeline (in weeks), whether the person makes the hiring decision, company name, email and how clear the need is (1 to 5). Every value comes with the client's literal quote.
2. Code computes the score with the configured weights.
3. If some criterion has no evidence yet, the status is **pending** and the agent asks the configured question for the first missing criterion.
4. When every criterion has evidence, the lead becomes **qualified**, **nurture** or **discarded**.

The email given at sign-up counts as evidence for the email criterion.

## Scoring rules

Each enabled criterion contributes `weight × factor`, normalised so the total is out of 100.

| Criterion | Factor |
|---|---|
| Budget | 1.0 if it covers the minimum price, 0.5 if it is at least half of it, otherwise 0 |
| Timeline | 1.0 if it is at least the minimum timeline (default 4 weeks), otherwise 0.3 |
| Decision maker | 1.0 if the person decides, 0.3 if not |
| Company | 1.0 once a company is identified |
| Company email | 1.0 for a company domain, 0.2 for a personal provider (Gmail, Outlook, Yahoo, iCloud…) |
| Need clarity | (level − 1) ÷ 4, so 1/5 gives 0 and 5/5 gives 1 |

Default weights: budget 30, decision maker 20, timeline 15, need clarity 15, company 10, company email 10.

## Outcomes

| Score | Status | What happens |
|---|---|---|
| ≥ qualified threshold (default 70) | Qualified | The chat moves on to requirements |
| ≥ nurture threshold (default 40) | Nurture | The client gets a polite "let's stay in touch" message |
| Below the nurture threshold | Discarded | The client gets a polite closing message |

Admins see the score breakdown, with each line's reason and the client's quote, in **Clients → internal view**. The explanation reads like: "Score 100 because: budget 25,000 covers the minimum 6,000 (+30); talking to the decision maker (+20)…".

## Guardrail

The qualification agent must never mention prices, timelines or discounts. If its reply contains a commercial figure, the reply is replaced by the plain configured question.

## Configuration

Questions, weights, which criteria are enabled and both thresholds are edited in **Settings → Qualification**. The nurture threshold must be lower than or equal to the qualified threshold.
