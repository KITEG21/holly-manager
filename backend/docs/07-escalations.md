# Escalations

An escalation is a request the agents are not allowed to resolve on their own. Admins handle them in **Escalations**. The sidebar shows the number of open escalations.

## When an escalation is created

- The client asks for terms outside the commercial limits (more discount, a lower deposit, more change rounds or more support).
- The sales agent decides a request cannot be resolved with its tools (a different payment calendar, a scope change, special conditions).
- A sales reply is blocked by the guardrails twice in a row.
- The automatic estimate fails.
- The committed hours exceed the maximum scope.

## What an escalation shows

- The client and a link to their internal view.
- The reason.
- The client's exact request.
- The rules that blocked it, with the requested value and the limit (for example `DISCOUNT_EXCEEDS_MAX: requested 40%, limit 10%`).

## Answering

Write the reply and click **Reply and close**. The reply appears in the client's chat as a message from the team, and the escalation is marked as resolved. Use the status filter to see open or all escalations.

Approving an exception in the reply does not change the stored offer automatically; the limits in Settings still apply to the agent.
