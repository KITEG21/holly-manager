# Sales agent and guardrails

After the estimate, the sales agent talks to the client about price, payment terms, change rounds, support and the contract. Its job is to negotiate inside the configured limits and never beyond them.

## What the agent can see

Only a client-safe summary: list price, timeline in weeks, number of sprints, payment schedule, included change rounds, included months of support, epics and out-of-scope items. It never sees hours, the hourly rate, the risk margin or the negotiation limits.

## What the agent can do

| Tool | What it does |
|---|---|
| `propose_offer` | Requests terms (discount %, deposit %, change rounds, months of support). Code builds the price and the payment schedule and validates them |
| `search_contract` | Searches the contract template and the commercial policies |
| `escalate_to_human` | Hands a request it cannot resolve to a person |
| `generate_proposal` | Generates the proposal and contract PDF for the latest valid offer |

## Offer validation rules

| Code | Rule |
|---|---|
| `DISCOUNT_EXCEEDS_MAX` | The discount is above the maximum discount (default 10%) |
| `PRICE_BELOW_MIN` | The discounted price is below the minimum price |
| `PRICE_MISMATCH` | The price does not match list price and discount |
| `DEPOSIT_BELOW_MIN` | The deposit is lower than the configured deposit (a higher deposit is allowed) |
| `PAYMENTS_NOT_100` | The payments do not add up to the price and to 100% |
| `CHANGE_ROUNDS_EXCEED` | More change rounds than included (default 2) |
| `SUPPORT_EXCEEDS` | More months of support than included (default 3) |
| `SCOPE_EXCEEDS_MAX` | The committed hours exceed the maximum scope |

An invalid offer is stored, an escalation is created automatically, and the agent only receives "escalated". It is told it cannot accept, but not what the limits are.

## Checks on every reply

Before a reply reaches the client:

1. **Figures check.** Every commercial figure in the reply (amounts, percentages, weeks, months, rounds, hours) must come from the summary or from a validated offer. Otherwise the reply is blocked with `UNVALIDATED_NUMBER`. When the turn has been escalated, the agent may repeat what the client asked for ("you asked for 30%") without promising it.
2. **Citations check.** If the agent searched the contract, the reply must cite the excerpts it used with markers like [C1]. Otherwise it is blocked with `MISSING_CITATION`.

A blocked reply gets one rewrite. If the rewrite is also blocked, the client receives a safe fixed message ("I want to make sure I give you an exact answer, so I'm checking with the team…") and the case is escalated.

## Example

A client asks for a 40% discount. The agent calls `propose_offer` with 40%, the validation fails with `DISCOUNT_EXCEEDS_MAX`, an escalation appears for the admins with the client's exact words, and the agent replies that it will check with the team. If the model tried to say "Done, 40% off", the figures check would block it.

## Proposal PDF

When the client accepts a validated offer, the agent generates the proposal. A background job renders the PDF: summary, scope (epics, stories and acceptance criteria), non-functional requirements, out of scope, commercial terms, payment schedule and the draft agreement from the contract template. The client downloads it from the chat panel.
