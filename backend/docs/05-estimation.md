# Estimation and sprint planning

The estimate runs as a background job (Celery task `estimate_project`) right after the client confirms the agreement. The result is internal: clients only ever see the price, the timeline and the payment schedule.

## Step 1: task breakdown (LLM)

The model breaks each user story into technical tasks (T1, T2…). Each task has exactly one configured type (backend, frontend, integration, qa, devops, design) and its dependencies. The model does not estimate hours.

The breakdown is validated: unknown task types, unknown stories, unknown or circular dependencies, and stories without tasks are rejected. The model gets the list of problems and up to three attempts. If it still fails, the estimate is marked as failed, an escalation is created and the client is told the team will review it personally.

## Step 2: similar past tasks (RAG)

For each task, the system searches the history of past tasks of the same type by semantic similarity. Matches at or above `HISTORY_MIN_SIMILARITY` (default 0.6) are used. The history includes the seed projects and every task the team closes in Holly.

## Step 3: three-point estimate (code)

For each task, starting from the configured range of its type:

- **Optimistic (O)** = the type's minimum hours.
- **Most likely (M)** = the midpoint of the range.
- **Pessimistic (P)** = the type's maximum hours × a complexity factor (low 1.0, medium 1.15, high 1.3).

If there are similar past tasks, M becomes the median of their actual hours, and O and P widen to include the lowest and highest actual values.

Then:

- Expected hours = (O + 4M + P) ÷ 6
- Standard deviation = (P − O) ÷ 6
- Planned hours = expected × (1 + risk margin). The default risk margin is 15%.

## Step 4: project totals

- Expected total = sum of the tasks' expected hours.
- P80 = expected total + 0.8416 × the combined standard deviation.
- **Committed hours** = the larger of (expected total × (1 + risk margin)) and P80.

The committed hours are what is sold to the client and what the forecast is compared against later.

## Step 5: sprint planning

- Effective capacity per sprint = capacity per sprint × velocity factor. With the defaults (180 h × 0.8) that is 144 h.
- Tasks are placed in dependency order. Each task goes into the first sprint that has room and is not earlier than the sprints of its dependencies. A dependency can sit in the same sprint.
- A task larger than a whole sprint gets a sprint of its own and a warning suggesting it should be split.
- Timeline in weeks = number of sprints × sprint length (default 2 weeks).

## Step 6: price

- List price = committed hours × hourly rate (default €55/h), never below the minimum price (default €6,000).
- The payment schedule is the deposit (default 30%) plus the milestones (default "Mid-project delivery" 40% and "Final delivery" 30%). The last payment absorbs rounding cents so the total is exact.

If the committed hours exceed the maximum scope (default 2,000 h), no price is shown to the client: the case is escalated and a person sends the proposal.

## Where to see the result

- Admins: **Clients → internal view** shows every task with its O/M/P, planned hours, the basis of the estimate (configured range or median of similar tasks), the sprints and the totals.
- The team: the backlog appears in **Projects** as soon as the estimate finishes.
