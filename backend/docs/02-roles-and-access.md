# Roles and access

Everyone signs in at `/login`. After signing in, each role is sent to its own home screen.

## Roles

| Role | How the account is created | Home screen | Can access |
|---|---|---|---|
| Client | Self sign-up at `/register` | `/chat` | Only their own conversation, requirements document and proposals |
| Developer | Created by the team (seed or database) | `/dev` | Dashboard, My tasks, Projects, Timesheet, Reports, Documentation |
| Admin | Created by the team (seed or database) | `/admin/leads` | Everything a developer can see, plus Clients, Escalations and Settings |

When a client signs up, their sales conversation is created at the same time and the assistant greets them with the first qualification question.

## Demo accounts

The seed (`python -m app.seed`) creates two team accounts:

- Admin: `admin@holly.app` / `admin1234`
- Developer: `dev@holly.app` / `dev12345`

Change these passwords before using the system outside a local environment.

## Sessions and security

- Passwords are hashed with scrypt.
- Sessions use tokens signed with HMAC-SHA256 using `SECRET_KEY` from `.env`. Tokens expire after 12 hours by default (`TOKEN_TTL_HOURS`).
- A client can only read their own conversation. Requests for another client's data return `403`.
- Admin-only endpoints return `403` for developers and clients. Requests without a valid token return `401`, and the app sends the user back to the sign-in screen.

## Permissions summary

| Action | Client | Developer | Admin |
|---|---|---|---|
| Chat with the sales agents | Own conversation | — | Any conversation (read-only view) |
| See internal estimates and traces | — | — | Yes |
| Move tasks, log and delete own time entries | — | Yes | Yes (can delete anyone's entries) |
| Answer escalations | — | — | Yes |
| Change settings | — | — | Yes |
| Read documentation and ask the assistant | — | Yes | Yes |
| Upload or delete documentation | — | — | Yes |
