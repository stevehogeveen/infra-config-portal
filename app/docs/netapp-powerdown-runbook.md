# NetApp Power-Down Runbook

This runbook captures the current real-lab NetApp power-down sequence for the
`192.168.1.0/24` isolated lab profile.

## Scope

Use this only for the local lab NetApp hardware. Do not use it for production
storage or any target outside the current real-lab profile.

## Key Distinction

`system node halt` stops ONTAP and can leave the controller at `LOADER`, but it
does not remove controller host power. A controller at `LOADER` can still have
fans and standby hardware active.

For software-controlled host power-off, use the NetApp BMC from the serial
console after ONTAP is halted.

## Sequence

1. Power off dependent VMs first.
2. Power off the ESXi/HPE host through iLO after VM shutdown completes.
3. Halt ONTAP nodes cleanly.
4. Verify NetApp cluster, node management, and storage LIF ports are down.
5. Use the NetApp serial console to reach BMC and turn off controller host
   power.

## NetApp BMC Host Power-Off

Use the MCP2221 NetApp serial console at `115200`.

From `LOADER-B>`:

```text
Ctrl-G
BMC login:
```

Authenticate with configured local NetApp credentials from ignored local env.
Do not print or commit those values.

At the BMC prompt:

```text
system power status
system power off
system power status
```

The desired final BMC status is:

```text
Host Power is off
```

## Expected Final State

- NetApp cluster management is unreachable.
- NetApp node management is unreachable.
- NetApp NFS LIFs are unreachable.
- The BMC can report `Host Power is off`.
- Fans or LEDs can still run at lower speed because PSU/BMC standby power
  remains present.

Full fan stop may require physical AC or PDU power removal.

## Evidence Pattern

Redacted run artifacts for this workflow should be saved under
`artifacts/codex-runs/` and must not include secrets or raw credentials.
