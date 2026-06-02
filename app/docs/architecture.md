# Architecture

`infra-config-portal` is a control plane for infrastructure automation. It keeps
request intake, validation, approval, planning, execution, and audit history in
one place while delegating vendor-specific work to provider adapters.

## Layers

- Frontend: React/Vite TypeScript application for request entry, status review,
  approvals, workflow runs, provider health, and audit events.
- API: FastAPI application exposing versioned REST endpoints.
- Schemas: Pydantic models for API validation and response shaping.
- Domain models: SQLAlchemy models for requests, workflow runs, approvals,
  audit events, provider credential references, and catalog-like entities.
- Workflow services: lifecycle transition logic, approval gates, planning, and
  execution orchestration.
- Provider adapters: interfaces for vSphere, AWX/Ansible, Terraform/OpenTofu,
  source-of-truth systems, iLO/Redfish, ONTAP, and switch integrations.
- Source-of-truth abstraction: mock NetBox/Nautobot-style catalog validation
  for environment, site, cluster, template, network, and storage choices.
- Audit logging: durable event records for request creation, state transitions,
  planning, approval, execution, and failures.

## MVP Boundary

The first workflow is `vm_deploy_from_template`. It accepts a VM deployment
request, validates it against schema and mock catalog data, records the request,
requires approval, creates a dry-run plan, and simulates vSphere execution.

The MVP intentionally does not call real infrastructure APIs.

## Request Lifecycle

```text
draft
submitted
validating
needs_approval
approved
planned
executing
completed
failed
cancelled
```

The submit operation moves a draft through `submitted` and `validating` into
`needs_approval` when validation passes. Planning is only allowed after
approval. Cancellation is allowed before execution starts. Execution is only
allowed after a plan exists.

## Database

Local development defaults to SQLite for speed. Docker Compose includes
PostgreSQL so the API can also be exercised against the production-class
database family.

Alembic is included so schema changes can move through migrations instead of
ad hoc table creation. The MVP app also initializes tables on startup for a
fast local development path.

## Worker Abstraction

The current worker abstraction executes mock work synchronously. It is shaped so
Celery, RQ, Dramatiq, Argo Workflows, or Temporal can replace it later without
rewriting API routes.

## Future Real Provider Flow

Future real adapters should follow this sequence:

1. Validate user request and source-of-truth constraints.
2. Create a read-only plan or dry-run.
3. Persist plan details and audit events.
4. Require approval for production-impacting actions.
5. Execute only through explicitly configured provider credentials.
6. Persist provider task identifiers, results, errors, and rollback notes.
