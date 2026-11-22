# Requirements and agreement

Once a lead is qualified, the requirements agent talks to the client and builds a structured requirements document while the conversation happens. The client sees it update live next to the chat.

## What the document contains

- **Epics** (E-1, E-2…): the large areas of the product.
- **User stories** (US-1, US-2…): "As a … I want … so that …", each linked to an epic and with testable acceptance criteria.
- **Non-functional requirements** (NFR-1…): performance, security, accessibility, legal (for example GDPR)…
- **Out of scope**: what is explicitly excluded.
- **Open questions**: ambiguities or contradictions the agent detected and has to ask about.
- **Summary**: the text the client confirms.

Every story and non-functional requirement records the ids of the client messages it came from, so the team can trace a task back to what the client actually said.

## How the agent works

- It records information with tools (create epic, create story, add NFR, add out-of-scope item, flag ambiguity, resolve ambiguity, propose summary).
- When something is ambiguous or contradicts what was already recorded, it flags it and asks before moving on.
- It asks at most two questions per message.
- It never talks about prices, hours, dates or discounts.

## When the document can be confirmed

The "Confirm agreement" button is only enabled when all of these are true:

- There is at least one user story.
- There are no open questions.
- Every story belongs to an existing epic.
- Every story has acceptance criteria.
- There is a summary.

The panel lists whatever is still missing.

## The agreement

When the client confirms:

1. The document is saved as a new **version** (v1, v2…) with a SHA-256 hash of its content.
2. A database trigger makes versions immutable: they cannot be updated or deleted.
3. The estimate job starts and the chat shows "Agreement confirmed (version N)".

The agreed version is the source of truth for the estimate, the proposal PDF and the task backlog.
