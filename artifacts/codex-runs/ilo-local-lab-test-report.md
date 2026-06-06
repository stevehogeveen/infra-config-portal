# iLO local-lab Test Report

Checked at: 2026-06-05T15:50:14Z

## Command

```bash
make provider-inventory-ilo-local-lab
```

Equivalent smoke path:

```bash
PROVIDER_MODE=local-lab PROVIDER_SMOKE_PROVIDERS=ilo-redfish make provider-smoke
```

## Result

Status: blocked before network contact.

The configured iLO target is present, but the new `local-lab` acknowledgement
flags are not enabled in the existing `.env.local.real-lab` file.

Missing or disabled policy statuses:

- `LAB_ENVIRONMENT`: missing
- `LAB_ACKNOWLEDGE_REAL_HARDWARE`: disabled
- `LAB_ALLOW_READONLY`: disabled
- `LAB_ALLOW_SAFE_WRITES`: disabled

Dangerous action statuses:

- `LAB_ALLOW_POWER_ACTIONS`: disabled
- `LAB_ALLOW_FIRMWARE_UPDATES`: disabled
- `LAB_ALLOW_VIRTUAL_MEDIA`: disabled
- `LAB_ALLOW_NETWORK_CHANGES`: disabled
- `LAB_ALLOW_FACTORY_RESET`: disabled

## Target Reachability

- iLO target configured: yes
- TCP/HTTPS attempted: no
- Redfish attempted: no
- Authentication attempted: no
- Reason: local-lab acknowledgement policy blocked the probe first

## Artifacts

Sanitized smoke artifacts:

- `artifacts/real-lab/provider-smoke-20260605T155014Z.json`
- `artifacts/real-lab/provider-smoke-20260605T155014Z.md`

## Not Attempted

No firmware, power, virtual media, boot order, BIOS, user/password, iLO network,
factory reset, POST, PATCH, PUT, or DELETE action was run.

## Next Action

Add the required local-lab acknowledgement flags to `.env.local.real-lab` when
you are ready for GET-only iLO inventory from a shell with lab network access,
then rerun:

```bash
make provider-inventory-ilo-local-lab
```
