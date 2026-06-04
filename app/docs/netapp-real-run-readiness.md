# NetApp Real-Run Readiness

This runbook prepares a real-lab NetApp readiness pass without performing real
ONTAP execution.

## Scope

Focus only on the NetApp setup and upgrade workflow. Do not run Cisco, iLO,
ESXi, OVF, or unrelated provider flows for this pass.

This is a readiness pass, not an ONTAP setup or upgrade pass.

## Safety

- Keep `NETAPP_CONFIGURED=false`.
- Keep provider mode mock by default.
- Use `PROVIDER_MODE=local-readonly` only for the explicit NetApp readiness
  command below.
- Do not perform real ONTAP config, firmware upgrade, takeover/giveback,
  reboot, wipe, storage provisioning, LIF creation, SSH, console command, SP
  API, or destructive action.
- Do not print or commit secrets.
- Do not commit `.env.local.real-lab` or anything under `artifacts/real-lab/`.

## Real-Lab Convention

- Controller A SP: `10.10.8.13`
- Controller B SP: `10.10.8.14`
- Cluster management: `10.10.8.45`
- Node A management/e0M: `10.10.8.46`
- Node B management/e0M: `10.10.8.47`
- SVM management: `10.10.8.48`
- iSCSI LIF range: `10.10.8.51-10.10.8.54`

## Command

From the repository root:

```bash
PROVIDER_MODE=local-readonly make netapp-real-readiness
```

The command writes redacted `netapp-readiness-*` JSON and Markdown reports
under ignored `artifacts/real-lab/`.

## Review Checklist

- Confirm the command prints `no_netapp_calls_made=true`.
- Confirm `NETAPP_CONFIGURED=false`.
- Confirm planned targets are separate from current/discovered targets.
- Confirm current/discovered targets are empty/not discovered.
- Confirm setup readiness remains blocked until manual physical/console checks
  and a future approved read-only discovery task exist.
- Confirm upgrade readiness remains blocked until setup readiness and safe
  discovery prerequisites exist.
- Confirm artifacts do not contain passwords, tokens, raw configs, or secrets.

## Normal Gates

After any source changes, run:

```bash
python3 -m compileall app/backend/app
cd app && PROVIDER_MODE=mock make backend-test
cd app/frontend && PROVIDER_MODE=mock npm run build
git diff --check
PROVIDER_MODE=mock make lint
```
