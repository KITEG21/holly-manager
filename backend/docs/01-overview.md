# Overview

Holly is a sales and delivery platform for a software agency. It covers the whole life of a project: a prospective client talks to AI agents, the agents turn the conversation into an agreed scope, the system estimates and prices the work, and the team then executes the backlog while logging their time.

## The core principle

The language model talks; it does not decide. Agents extract information, write questions and break work down into tasks, but every number that reaches a client is computed by deterministic code:

- Qualification scores come from configured weights, not from the model's opinion.
- Hours come from PERT estimates over configured ranges and real historical data.
- Sprints come from a planning algorithm that respects capacity and dependencies.
- Prices and payment schedules come from the commercial rules in Settings.

The sales agent can never accept anything outside the configured limits. When a client asks for more, the request is escalated to a person.

## The project lifecycle

1. **Qualification.** A client signs up and the qualification agent asks the configured questions until it can score the lead.
2. **Requirements.** Qualified leads talk to the requirements agent, which builds a requirements document (epics, user stories, acceptance criteria, non-functional requirements, out-of-scope items).
3. **Agreement.** The client clicks "Confirm agreement" and the document is frozen as an immutable version.
4. **Estimate.** A background job breaks the stories into tasks, estimates them and plans the sprints. The client receives the price, timeline and payment schedule.
5. **Proposal.** The sales agent negotiates within the limits, answers contract questions with citations and generates the proposal PDF.
6. **Delivery.** The estimate becomes the project backlog. Developers move tasks, log time, and the forecast updates with every entry.

## Main areas of the app

| Area | Who uses it | What it is for |
|---|---|---|
| Client chat | Clients | Qualification, requirements, estimate and proposal |
| Dashboard, My tasks, Projects, Timesheet, Reports | Developers and admins | Executing projects and tracking time |
| Documentation | Developers and admins | Reading how the system works and asking the documentation assistant |
| Clients, Escalations, Settings | Admins | Supervising agents, answering escalations and configuring every rule |
