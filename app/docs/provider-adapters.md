# Provider Adapters

Provider adapters isolate infrastructure-specific behavior from API routes and
workflow lifecycle code.

## Current MVP Adapters

- vSphere: mocked implementation for plan and execute.
- NetBox/Nautobot source of truth: mocked catalog validation.
- AWX/Ansible: mocked health only.
- Terraform/OpenTofu: mocked health only.
- HPE iLO/Redfish: placeholder health only.
- NetApp ONTAP: placeholder health only.
- network switch: placeholder health only.

All adapters report mock or placeholder status. None make network calls.

## Interface Expectations

Real adapters should implement small interfaces:

- `health()`
- `plan_*()`
- `execute_*()`

The workflow service should not know vendor API details. It should receive a
plan and result object from adapters and persist them.

## Real Adapter Requirements

A real provider adapter must:

- default to disabled or dry-run mode
- require explicit configuration
- use credential references only
- never log secret values
- support dry-run or plan before execution
- expose provider task identifiers where available
- convert vendor errors into structured application errors
- record audit events through workflow services

## Source Of Truth

Source-of-truth adapters validate whether requested values exist and are allowed.
For example, a VM deployment request should validate:

- environment exists
- site exists
- cluster belongs to site
- template exists
- network/VLAN exists
- datastore or storage tier exists

The MVP uses in-memory mock catalog data. Future NetBox or Nautobot adapters
should replace that mock without changing API routes.
