# AI disclosure

I used Claude Code (Anthropic) as a pair-programmer for most of this project. [`prompt-history.md`](prompt-history.md) has every message I sent it.

## Tools used

- **Claude Code (Anthropic):** the main tool; every prompt is in [`prompt-history.md`](prompt-history.md).
- **ChatGPT:** consulted for advice on choosing an SMTP relay. I pasted one reply into the Claude session, so that reply is reflected in the history, but the prompts I sent ChatGPT were not exported and are not reproduced. I did not follow its recommendation (SMTP2GO); I used a Gmail relay.

## Where AI accelerated the work

- Scaffolding and boilerplate: FastAPI routers, Alembic migrations, React pages, Flutter screens, systemd/nginx/deploy scripts.
- First drafts of the generator, the categorization rules, the recurring-series detector and the evaluation harness, which I then ran, measured and adjusted.
- Test writing: most of the 190+ tests were drafted by the assistant from the edge-case register.
- Documentation drafts (data dictionary generation, edge-case table, this README).
- Server work over SSH: installing Postgres access, nginx, TLS, systemd, and stopping unrelated services.

## Where I relied on it heavily

- The visual design and front-end implementation. I chose from directions it proposed ("Hisaab Register") and reviewed the result.
- The structure of the engine pipeline and the API surface.
- Android build and signing configuration.

## What I decided, reviewed, changed or validated myself

- Product decisions: a real application with real users rather than a synthetic-data demo; new sign-ups get their own empty household; a shared password for the sample households; stopping unrelated services on the server; scope (web console for all four roles, small Android app).
- I reviewed the security-sensitive choices: roles re-read from the database per request, algorithm-pinned token verification, lockout, no Google-to-household takeover (edge case A23, reversed after I questioned it), export path-traversal guard.
- Acceptance is by measurement, not by the assistant's say-so: `validate-dataset`, `evaluate`, `validate-outputs` and the reproducibility check produce reports in `reports/`; the starter generation was re-run on the server and its manifest hash matched the Windows one.
- Anything that failed was fixed in the open (migration constraint naming, Postgres parameter typing, id collisions on reload, Windows encoding); the commit history shows it.

## Not verified

- Visual polish was not pixel-reviewed by a designer; it was checked through layout assertions and the live site at desktop and phone widths.
- The Android app was built and signed, but I have not exercised it across a range of devices.
- Google sign-in has not been exercised end to end (no Firebase project configured).
- Continuous-integration runs are the evidence for tests passing; the badge in the README links to them.
