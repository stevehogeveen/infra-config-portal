# NetApp Live State Report

- Checked at: `2026-06-10T21:52:08.047324+00:00`
- Status: `blocked`
- Configured state: `blocked`
- Configured: `False`
- Source: `live_verification`
- Manual env flag required: `False`

## Console

- Discovered port: `/dev/ttyS20`
- Baud: `none`
- Confidence: `medium`
- Last seen: `2026-06-10T21:49:12.407440`
- Source: `autodiscovery`

## Live Checks

- Cluster REST 443 reachable: `False`
- Cluster SSH 22 reachable: `False`
- API authenticated: `None`
- Storage protocol: `nfs` ready=`True`

## Blockers
- NetApp cluster management REST is not reachable.
- NetApp API access values are missing; keep any values local and redacted.

## Safety

- No secrets are written to this report.
- No NetApp write, setup, storage, upgrade, reboot, wipe, or apply command is run.
