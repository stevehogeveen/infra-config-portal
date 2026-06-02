# 001f - Smoke Test Make Targets

## Goal

Add named Makefile targets for running the mock VM lifecycle smoke tests quickly.

Keep this task small. Do not change application behavior.

## Context

The backend now has a smoke test file:

- `app/backend/tests/test_smoke_vm_lifecycle.py`

The full test suite passes, but we want a shorter command for the API lifecycle smoke subset.

## Safety

Do not call real:
- vCenter
- ESXi
- HPE iLO
- Redfish
- NetApp ONTAP
- switches
- DNS
- IPAM
- storage arrays
- AWX
- Terraform
- OpenTofu
- NetBox
- Nautobot
- PowerCLI
- govc
- OVF Tool

Do not add credentials, real IPs, real hostnames, tokens, passwords, SSH keys, or customer data.

Keep PROVIDER_MODE=mock.

## Required Work

Add Makefile targets for smoke testing.

Preferred targets:

At repo root:

- `make smoke`
- `make backend-smoke`

Under `app/` if appropriate:

- `make backend-smoke`

The backend smoke target should run:

```bash
cd app/backend && .venv/bin/pytest -q tests/test_smoke_vm_lifecycle.py
