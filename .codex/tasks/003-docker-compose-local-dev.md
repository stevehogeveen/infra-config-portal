# Task 003: Docker Compose Local Dev

## Goal

Make local Docker Compose development clearer and safer without adding real
provider access.

## Constraints

- Keep `PROVIDER_MODE=mock`.
- Do not add real infrastructure endpoints, IPs, hostnames, credentials,
  tokens, or secrets.
- Do not change Compose to call real provider APIs.
- Do not require external services beyond local dev containers unless clearly
  documented.

## Expected Work

- Inspect `app/docker-compose.yml`, Dockerfiles, `.env.example`, and README
  instructions.
- Improve one small Compose/local-dev issue, such as health checks, startup
  docs, env defaults, volume clarity, or command consistency.
- Update docs for any changed local command.

## Verification

Run the most relevant local checks. If Docker is unavailable or Compose cannot
be run locally, document the exact limitation.

## Completion

End with files changed, local-dev behavior changed, commands run, limitations,
and the next recommended task.
