# Tasks and projects

When an estimate finishes, its tasks become the project backlog. Each task keeps its key (T1, T2…), type, sprint, dependencies, planned hours and the user story it comes from.

## Projects

**Projects** lists every project with a backlog: progress (closed tasks), hours logged against committed hours, sprints left and whether the forecast is on track. Inside a project there are four views:

- **Board**: a kanban with To do, In progress and Done columns. Drag a card to change its status. A sprint filter narrows the board.
- **Sprints**: each sprint with its tasks and actual vs. planned hours.
- **Forecast**: the re-estimation of the project (see the Forecast document).
- **Docs**: the project's own documentation (see below).

## Project documentation

Every project has its own documentation, where the team keeps the business logic of that project. Developers and admins can use it.

- **Business agreement**: generated automatically from the requirements the client confirmed (summary, epics, user stories with acceptance criteria, non-functional requirements, out of scope, and the decisions taken while resolving open questions). It cannot be edited or deleted; it updates itself when the client confirms a new version.
- **Team pages**: Markdown pages written in the app with "New page" (business rules, edge cases, open points…). Use headings (##) so the assistant can cite each section. Pages can be edited and deleted.
- **Files**: upload Markdown, PDF, DOCX, HTML or PPTX files with "Upload".

Each project has its own assistant ("Ask"). It answers only from that project's documentation, never from other projects or from these system guides, and every statement links to the section it comes from.

## My tasks

**My tasks** lists tasks across every project. Filter by "Assigned to me", "Unassigned" or "All", by status (open by default), by project, or search by key and title.

## The task panel

Click any task to open its panel:

- Change the status and the assignee.
- See the agreed user story it comes from, its type and its dependencies (green when done, amber when still open).
- Log time with hours, day and an optional note.
- Start the timer.
- See the history of time entries and delete your own.

## Rules

| Rule | Detail |
|---|---|
| Dependencies first | A task cannot be moved to In progress or Done while any of its dependencies is not done. The card shows "Waiting on T…" |
| Hours before closing | A task cannot be closed without actual hours logged |
| Automatic start | Logging time on a To do task moves it to In progress |
| Automatic assignment | Whoever logs time first on an unassigned task becomes its assignee |
| Assignees | Tasks can only be assigned to developers and admins |
| History | Closing a task adds it, with its actual hours, to the history used to estimate future projects. Reopening it removes it again |
