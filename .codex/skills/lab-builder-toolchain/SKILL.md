---
name: lab-builder-toolchain
description: Use when working on Lab Builder tool orchestration, Toolchain Readiness, provider-specific tools for Cisco, HPE iLO, ESXi, NetApp, firmware workflows, or tool availability checks.
---

# Lab Builder Toolchain

## Use This Skill When

Use this skill before implementing provider tooling, checking tool
availability, designing Toolchain Readiness, or choosing how the app should
orchestrate external infrastructure tools.

## Tooling Principle

The app is a control plane. It should orchestrate proven tools instead of
hand-rolling provider protocols when reliable tools exist.

Do not invoke tools against real infrastructure unless the user explicitly asks
for a real-lab run and the matching runtime gates are present.

## Provider Tool Choices

- Cisco: local serial or `ser2net` first contact, then Netmiko, Ansible, or
  pyATS after SSH works.
- HPE/iLO: Redfish primary, optionally iLOrest where it improves operator
  workflows.
- ESXi: iLO VirtualMedia plus Kickstart for install, then `govc` or vSphere API
  after install.
- NetApp: `netapp-ontap` or ONTAP REST primary, SSH fallback where REST is not
  enough.
- Firmware: local baseline manifest, package inventory, and waiver gate before
  apply.

## Toolchain Readiness Contract

Surface tool availability in Toolchain Readiness with:

- tool name and purpose
- detection method or command
- detected version or `not_found`
- required version or policy
- status: ready, missing, warning, stale, or not_checked
- source type, checked time, freshness, and recheck command
- install or fix guidance when missing

Tool readiness is not provider readiness. A tool can be installed while the
real lab target is unreachable, stale, or not checked.
