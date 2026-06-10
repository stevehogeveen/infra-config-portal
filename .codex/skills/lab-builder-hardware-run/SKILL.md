---
name: lab-builder-hardware-run
description: Use when planning, documenting, validating, or implementing Lab Builder real hardware workflows, lab profile handling, console discovery, NetApp/Cisco/iLO/ESXi sequencing, or run artifacts.
---

# Lab Builder Hardware Run

## Use This Skill When

Use this skill for real hardware workflow design, lab profile changes,
provider run sequencing, console autodiscovery, validation reports, and
artifact-producing hardware tasks.

Do not run hardware workflows unless the user explicitly asks for a real-lab
run and the required local gates are present. Code and docs work should stay
mock-first unless the task is specifically scoped to real lab operation.

## Workflow

Hardware workflow order is always:

1. Discover.
2. Plan.
3. Apply.
4. Verify.
5. Report.

Do not skip fresh discovery before apply. Do not trust stale artifacts as
current state.

## Lab Profile

Use this lab profile when the task asks for the Lab Builder real-lab hardware
profile:

| Role | Address |
| --- | --- |
| iLO | `192.168.1.201` |
| Server NIC | `192.168.1.202` |
| ESXi | `192.168.1.203` |
| Cisco | `192.168.1.204` |
| Ansible/control host | `192.168.1.205` |
| Subnet | `192.168.1.0/24` |

## Hardware Rules

- Hardware runs must save artifacts under ignored local artifact paths.
- Console ports must be autodiscovered, not manually required.
- NetApp console autodiscovery should prefer live evidence over historical
  artifacts.
- Cisco first contact is console. Use SSH-dependent tooling only after SSH is
  confirmed.
- Ansible starts after SSH works.
- Use `local-lab-readwrite` for real hardware workflows that can apply changes;
  do not use mock output as a replacement for real status.

## Reporting Checklist

- Save discovery, plan, apply, verify, and final report artifacts.
- Label artifact age and source.
- Keep secrets redacted. Report credential state as configured, missing, or
  redacted only.
- Include recheck commands for every current blocker.
