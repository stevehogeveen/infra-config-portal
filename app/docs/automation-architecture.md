# Automation execution

## Current architecture and migration

The portal already has device inventory, per-device iLO credentials, an action
registry, audit events, and Docker Compose. Its existing InlineWorker runs in
the request process, and workflow_action_runner combines dispatch with vendor
operations. These existing paths remain in place during incremental migration.

The first separate workflow is read-only iLO system inventory:

1. The rack's Checks tab requests a job by device ID.
2. The API validates the fixed operation and current execution policy.
3. Redis/RQ queues a versioned envelope containing identity and context revisions.
4. A separate worker resolves current settings and runs the committed playbook
   with Ansible Runner.
5. The worker normalizes output, rechecks context, and records an audit event.
6. The rack polls job status. Observations expire after five minutes and mock
   results never become hardware evidence.

The job does not populate RAID readiness or unlock installation. System inventory
alone does not establish a boot mirror, usable drive bays, or installed ESXi.
The existing Access check retains its detailed first-contact diagnostics.

## Boundaries

| Component | Responsibility |
| --- | --- |
| API router | Typed requests, local actor, queue submission and status |
| Job contracts | Versioned operation, device identity, result schema |
| Target resolver | Current per-device access, profile context, execution policy |
| Redis/RQ | Dispatch, timeouts, process lifecycle, temporary job results |
| Worker task | Validate context, execute adapter, normalize and audit result |
| Ansible adapter | Fixed playbook, private variables, bounded output |
| Playbook | Vendor-module operations, no application workflow decisions |
| Rack UI | Explicit request, pending state, observation provenance |

This is one implemented operation, not a general user-programmable workflow engine.
The API rejects arbitrary playbooks, addresses, commands, and extra variables.
Later operations should add explicit typed contracts and tests. RQ dependencies
can sequence successful jobs, but setup prerequisites must check proven state;
a successful planning job is not permission to execute destructive work.

## Dynamic targets

Queue entries contain the device ID and access revision, not an IP or credential.
The worker loads access settings from the shared database at execution time.
Address, credential revision, profile, and provider mode changes invalidate queued
work. The worker also checks context after execution and discards changed-target
results. A new job uses the updated settings. DNS can be used as the saved address;
this workflow does not discover changed DHCP leases automatically.

The runtime profile is synthesized on read, so its generated timestamps are
excluded from the job fingerprint. Real profile settings remain part of it.

## Local container stack

### What is installed where

- Host prerequisites: Docker Engine and Compose on Linux, or Docker Desktop
  with a working WSL 2 backend on Windows. These are installed separately from
  the repository.
- Git tracks source, Dockerfiles, Compose definitions, Python requirements,
  the collection version, playbooks, and frontend dependency manifests/lockfile.
  It does not track installed runtimes, virtual environments, node_modules,
  Redis databases, credentials, or downloaded installers.
- Container builds install the declared dependencies. The worker image contains
  Python, Ansible Runner, Ansible Core, and the selected collection. Redis and
  PostgreSQL run as their own container services.
- A future release can publish prebuilt images to a container registry, so users
  pull images instead of building locally. This repository currently uses source
  builds; no published image release is configured by this change.

From the app directory:

```sh
docker compose -f docker-compose.yml -f docker-compose.automation.yml up --build
```

This starts the existing app plus Redis and a separate automation worker.
Both API and worker default to mock mode. A mock inventory job exercises the
queue without contacting hardware or inventing inventory.

Redis has no host port, uses a named persistent volume, and stores results for
24 hours. Queued jobs expire after five minutes; worker execution is bounded to
150 seconds, with Ansible bounded to 120 seconds. There are no automatic retries
of hardware operations.

The worker image pins its Python base tag, Ansible packages, and collection.
It runs as a non-root user with a read-only root filesystem, dropped capabilities,
and temporary data on tmpfs. It has no Docker socket. Credentials enter a private
temporary variables file, are not passed in command arguments or queue payloads,
and are removed with the temporary directory. The credential-bearing task uses
no_log. Only selected system fields are returned; raw provider failures are not
published.

Actual hardware reads require consistent explicit real-lab policy configuration
in both processes and locally saved credentials. This change does not enable
real mode or any write playbook. The existing incomplete AGENTS.md text is unchanged.
Keep the API and Redis on trusted local networks; existing local-user headers are
not production authentication.

## Testing

From the backend directory:

```sh
pip install -r requirements-test.txt
PROVIDER_MODE=mock python -m pytest -q tests/test_inventory_automation.py tests/test_compose_contract.py
```

Tests exercise the actual RQ serialization and worker against an in-memory Redis
substitute, API polling, target changes, profile changes, redaction, and the
playbook/result contract. The Ansible Runner invocation is substituted in unit
tests; those tests do not establish real controller compatibility.

From the frontend directory:

```sh
npm run test:component
npm run test:e2e -- tests/inventory-workflow.spec.ts tests/drive-allocation.spec.ts
```

Before enabling real inventory, build the worker image, run a playbook syntax check,
then explicitly test against one selected device. Verify returned system identity
against the intended machine. Docker Desktop and WSL 2 are now installed on this
host. The Linux engine is running, the combined Compose configuration validates,
and the worker image builds with the pinned collection installed. The inventory
playbook passes its syntax check inside the isolated worker container.
Hardware compatibility and a live inventory run remain unverified.

The full `infra-automation-dev` stack has also passed a mock integration run:
the API queued an inventory job, Redis delivered it, and the worker completed it
with explicitly unproven mock results. The frontend and its same-origin API proxy
were checked in a browser without JavaScript errors. On this host the isolated
frontend runs at http://127.0.0.1:15173/simple and the API at port 18001.
Set `FRONTEND_PORT=15173` and `BACKEND_PORT=18001` when managing this stack to
avoid the existing local development servers.

`automation/tests/smoke_inventory.py` exercises the real Ansible Runner and
collection against a temporary loopback HTTPS Redfish fixture. It passed inside
the read-only worker container with external networking disabled, checking
normalized system identity and GET-only requests. This is not a hardware test.

Frontend source/configuration bind mounts are read-only and individually scoped.
Linux dependencies live in the named container volume, not the host's
`node_modules`, so container installation cannot replace Windows dependencies.

## Next operations

1. Verify system inventory against the actual iLO generation and firmware.
2. Add normalized storage discovery using supported modules, preserving HPE bay IDs.
3. Move RAID preview behind a typed operation; bind its result to the target,
   desired-state revision, and exact prospective change.
4. Add separately confirmed apply only after controller/module compatibility is
   proven. Retain the existing execution gates and verify results afterward.
5. Extend the same contracts to Cisco/NetApp collections and existing govc paths.
6. Continue stage-dependent rack rendering and the profile-backed build flow using
   those results. Avoid moving every provider at once.
