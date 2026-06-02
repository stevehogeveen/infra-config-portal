# Security

## Safety Posture

This project starts in mock-only mode. It must not perform real production or
lab infrastructure actions until a future adapter is explicitly configured,
reviewed, and tested.

## Secrets

- Do not store plaintext secrets.
- Do not commit credentials, tokens, private keys, real hostnames, IPs, or
  customer data.
- `ProviderCredentialRef` records are references only. They may identify a
  secret manager path or external credential ID, but not the secret value.
- Future secret retrieval should go through a dedicated secret provider service
  with audit logging.

## Provider Execution Controls

All provider adapters default to mock mode. A future real adapter must require:

- explicit provider mode configuration
- named credential reference
- dry-run or plan output
- approval before execution for production-like environments
- audit logging around each status transition and provider task ID

## Input Safety

The UI and API should collect structured fields only. They must not accept:

- arbitrary scripts
- arbitrary Ansible variables
- raw Terraform files
- unvalidated provider payloads
- free-form command lines

Provider-specific options should be modeled as typed fields with allow-lists,
range validation, and source-of-truth checks.

## Approval Gates

Production-impacting workflows must not bypass approval. The MVP requires
approval for every VM deployment so the gate is exercised from day one.

## Audit Events

Every important action records an audit event, including:

- request creation
- submit
- validation start and pass/fail
- approval
- plan creation
- execution start
- completion
- failure
- cancellation

Audit events should be treated as immutable application history.
