# AGENTS.md

## Project

This repository is an infrastructure configuration and automation portal.

The app is intended to help users request, validate, approve, execute, and audit
workflows for:

- VMware vSphere / ESXi
- HPE iLO / Redfish
- NetApp ONTAP
- OVF / OVA deployment
- VM deployment
- storage provisioning
- network switch and VLAN configuration
- datacenter infrastructure onboarding

## Core principle

The portal is a control plane, not the automation engine itself.

The app should:

- collect user input
- validate requests
- check source-of-truth data
- create a plan
- require approval for risky actions
- call automation backends
- track status
- record audit events

The app should not directly become a giant pile of vendor-specific scripts.

## Safety rules

Never add real credentials, secrets, IPs, tokens, passwords, hostnames, or
customer data.

All provider integrations must default to mock mode.

Any real infrastructure integration must require explicit configuration and
should support:

- dry-run
- plan
- approval
- audit logging
- rollback notes where possible

Never allow arbitrary user-provided code execution.

Never allow arbitrary Ansible variables from the UI without validation.

Never bypass request validation or approval gates for production-like workflows.

## Preferred stack

Backend:

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- pytest

Frontend:

- React
- TypeScript
- Vite

Local dev:

- Docker Compose
- `.env.example`
- mocked providers by default

Future integrations:

- AWX / Ansible Automation Platform
- Terraform / OpenTofu
- PowerCLI / govc
- NetBox / Nautobot
- HPE iLO Redfish
- NetApp ONTAP REST API
- network device APIs or Ansible network collections

## Architecture expectations

Use clean separation between:

- API routes
- request schemas
- domain models
- workflow state machine
- provider adapters
- source-of-truth adapters
- audit/event logging
- frontend UI components

Provider adapters should use interfaces or abstract base classes so real
implementations can replace mock implementations later.

## MVP

The first MVP is `Deploy VM from Template`.

The first implementation must use mock providers only.

Required request states:

- draft
- submitted
- validating
- needs_approval
- approved
- planned
- executing
- completed
- failed
- cancelled

## Testing

Add tests for:

- request validation
- lifecycle transitions
- audit event creation
- mock VM deployment execution
- API endpoint behavior

## Done means

A task is not done until:

- code is formatted
- relevant tests pass or limitations are documented
- README instructions are updated
- safety assumptions are clear
- no real infrastructure calls are made unless explicitly requested and
  configured
