# AGENTS.md

## Safety Rules

Never add real credentials, secrets, tokens, passwords, private keys, customer data, or production-only hostnames.

Commit local lab profile files, `.env.local.real-lab`, generated runtime state, terminal logs, PID files, or raw hardware output.

real-lab workflow.

 Historical artifacts are evidence, not current blockers unless a fresh check proves the blocker still exists.

Real infrastructure calls are allowed only when all of the following are true:

- The user explicitly requests a real-lab workflow.
- The command is scoped to the local lab.
- The provider mode and target lab are clear.
- The workflow follows discover, plan, preview, apply only with explicit confirmation, verify, and report.
- Secrets are loaded from local ignored files or the operator environment and are never printed.

Make real calls to VMware vSphere, ESXi, HPE iLO, Redfish, NetApp ONTAP, network switches, storage APIs, AWX, Ansible Automation Platform, Terraform/OpenTofu backends, NetBox, Nautobot, DNS, IPAM, or production networks

Run destructive or state-changing actions unless the task explicitly asks for them and the required confirmation flags are present. This includes:

- Cisco write, reload, erase, or firmware actions.
- iLO power, reset, firmware, virtual media, BIOS, or boot-order actions.
- RAID create/delete/apply/reset actions.
- ESXi install, rebuild, datastore destructive operations, or host reconfiguration.
- NetApp setup apply, ONTAP upgrade apply, disk/shelf/SP firmware apply, volume delete, aggregate delete, or network changes.
- vCenter or datastore changes.
- Any firmware upgrade apply.

Use YOLO-style execution by default.

Normal mode should use:

- fast/default reasoning
- targeted validation

`danger-full-access` is permitted 

Do not use destructive Git resets, force pushes, broad cleanup commands


