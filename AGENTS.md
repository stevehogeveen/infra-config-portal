# AGENTS.md

## Safety Rules

Never add real credentials, secrets, tokens, passwords, private keys, customer data, or production-only hostnames.

Never commit local lab profile files, `.env.local.real-lab`, generated runtime state, terminal logs, PID files, or raw hardware output.

<!-- INCOMPLETE: the start of this sentence was lost. Do not infer its meaning; ask the operator. -->
real-lab workflow.

 Historical artifacts are evidence, not current blockers unless a fresh check proves the blocker still exists.

Real infrastructure calls are allowed only when all of the following are true:

- The user explicitly requests a real-lab workflow.
- The command is scoped to the local lab.
- The provider mode and target lab are clear.
- The workflow follows discover, plan, preview, apply only with explicit confirmation, verify, and report.
- Secrets are loaded from local ignored files or the operator environment and are never printed.

Never make real calls to VMware vSphere, ESXi, HPE iLO, Redfish, NetApp ONTAP, network switches, storage APIs, AWX, Ansible Automation Platform, Terraform/OpenTofu backends, NetBox, Nautobot, DNS, IPAM, or production networks unless every condition above is true.

Never run destructive or state-changing actions unless the task explicitly asks for them and the required confirmation flags are present. This includes:

- Cisco write, reload, erase, or firmware actions.
- iLO power, reset, firmware, virtual media, BIOS, or boot-order actions.
- RAID create/delete/apply/reset actions.
- ESXi install, rebuild, datastore destructive operations, or host reconfiguration.
- NetApp setup apply, ONTAP upgrade apply, disk/shelf/SP firmware apply, volume delete, aggregate delete, or network changes.
- vCenter or datastore changes.
- Any firmware upgrade apply.

Never use YOLO-style execution by default.

Normal mode should use:

- fast/default reasoning
- targeted validation

<!-- INCOMPLETE: this sentence was truncated. Treat `danger-full-access` as NOT permitted until the operator restores the condition. -->
`danger-full-access` is permitted

Do not use destructive Git resets, force pushes, broad cleanup commands



## Building labs

`app/docs/lab-build-rules.md` holds the rules for how Lab Builder builds a lab: the three
levels, the two-drive ESXi boot pair, provenance of every displayed value, first contact and
its failure modes, blocked-with-reason, and the fixed ordering of cluster bring-up. Read it
before changing the rack workspace, the build flow, or any provider evidence handling.

Design references for those rules are in `app/docs/design/` (self-contained HTML, open in a
browser).
