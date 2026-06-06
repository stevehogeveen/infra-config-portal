# Failure Case Hardening Report

- Checked at: `2026-06-06T18:52:38.681419+00:00`
- Provider mode: `mock`
- Credential values, tokens, and secrets are redacted.

## wrong iLO IP

- Classification: `stale_config`
- UI message: iLO target must be 192.168.1.201 for this lab.
- Report artifact detail: 3 stale active values; 2 active profile mismatches.
- Exact next action: Update active lab inputs to 192.168.1.201-.205 and remove stale 10.10.8.x values before certification.

## missing ESXi ISO

- Classification: `operator_action_required`
- UI message: ESXi ISO media inventory is operator_action_required.
- Report artifact detail: ESXi ISO media inventory is not configured.
- Exact next action: Place the ESXi ISO under MEDIA_INVENTORY_DIRS or set ESXI_INSTALL_ISO/ESXI_ISO_PATH before ESXi boot verification.

## iLO cannot reach media URL

- Classification: `operator_action_required`
- UI message: iLO media URL reachability is validated by the ESXi media URL stage.
- Report artifact detail: See artifacts/codex-runs/esxi-media-url-report.md for the real media URL result.
- Exact next action: Fix media URL reachability before virtual media insert.

## Cisco console adapter missing

- Classification: `operator_action_required`
- UI message: Cisco console discovery must find the stable Prolific adapter.
- Report artifact detail: See artifacts/codex-runs/cisco-console-discovery-report.md.
- Exact next action: Connect the Cisco console adapter and prefer the stable /dev/serial/by-id path.

## Cisco wrong baud

- Classification: `operator_action_required`
- UI message: Cisco prompt detection should identify 9600 baud for this lab.
- Report artifact detail: The Cisco workflow tries 9600, 19200, 38400, 57600, and 115200.
- Exact next action: Set CISCO_CONSOLE_BAUD=9600 or rerun console auto-discovery.

## Cisco user exec but no privileged exec

- Classification: `operator_action_required`
- UI message: Cisco bootstrap apply requires privileged exec.
- Report artifact detail: See artifacts/codex-runs/cisco-privilege-hardening-report.md.
- Exact next action: Confirm enable access or perform password recovery/factory reset before bootstrap apply.

## Cisco password recovery required

- Classification: `operator_action_required`
- UI message: Password recovery is operator-confirmed only; the app must not assume it.
- Report artifact detail: Enable rejection is inferred only from prompt state and redacted challenge evidence.
- Exact next action: Use the documented physical-console password recovery/factory reset procedure if no enable credential works.

## ESXi API/SSH unreachable before install/config

- Classification: `blocked_by_prior_stage`
- UI message: ESXi API is blocked_by_prior_stage.
- Report artifact detail: Install/configure ESXi management at 192.168.1.203, then set ESXI_CONFIGURED=true before API certification.
- Exact next action: Install/configure ESXi management at 192.168.1.203, then set ESXI_CONFIGURED=true before API certification.

## stale Cisco/ESXi/NetApp IPs

- Classification: `stale_config`
- UI message: Old 10.10.8.x values are stale for this lab unless explicitly overridden.
- Report artifact detail: 3 stale active values; 2 active profile mismatches.
- Exact next action: Update active lab inputs to 192.168.1.201-.205 and remove stale 10.10.8.x values before certification.

## MTU mismatch across paths

- Classification: `passed`
- UI message: MTU must be consistent per traffic path.
- Report artifact detail: 0 invalid MTU values; 0 path mismatches.
- Exact next action: MTU consistency passed for configured paths.

## username/password special character handling

- Classification: `passed`
- UI message: Credential values are tested for .env, JSON, YAML, shell, Ansible, Cisco CLI, iLO Redfish, ESXi, and NetApp compatibility.
- Report artifact detail: Field names are reported; credential values remain redacted.
- Exact next action: Credential compatibility passed for configured fields.
