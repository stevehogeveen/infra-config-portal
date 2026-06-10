# NetApp Bring-Up Baseline

Checked at: 2026-06-09T22:25:13Z

## Scope

- Provider mode: `local-lab-readwrite`
- Env seed: `.env.local.real-lab`
- Real-lab workflow: NetApp bring-up, read-only discovery and readiness planning
- Secrets printed: `no`
- Destructive NetApp commands run: `no`

## Existing Evidence Read

- `artifacts/codex-runs/netapp-console-autodiscovery-report.md`
- `artifacts/codex-runs/netapp-console-state-report.md`
- `artifacts/codex-runs/netapp-nfs-vcenter-readiness-report.md`
- `artifacts/codex-runs/build-verification-report.md`

Older evidence before this run showed:

- NetApp console autodiscovery/read-state selected `/dev/ttyACM0` at `115200` from prompt evidence.
- The stable by-id MCP2221 candidate was present but earlier probe output came from `/dev/ttyACM0`.
- Prompt state was `login_required`.
- Console port was not required in `.env.local.real-lab`; autodiscovery treated it as optional.
- NFS/vCenter preview was blocked because live NetApp configured state and vCenter/govc readiness were not verified.
- Build Verification was using the older NetApp plan `192.168.1.206-.215`, so the planned profile needed correction before this bring-up run.

## Env/Profile Baseline

- `PROVIDER_MODE`: `local-lab-readwrite`
- `LAB_SUBNET_CIDR`: `192.168.1.0/24`
- Real-lab acknowledgements: configured
- NetApp-specific console/API credentials: missing
- NetApp-specific IP env overrides: not set in the redacted scan
- `.env.local.real-lab` role: bootstrap/profile seed, not live state storage
- `NETAPP_CONSOLE_PORT`: not required
- `NETAPP_CONFIGURED`: legacy/desired context only; live configured state is derived from validation

## Active IP Profile

- Controller A SP: `192.168.1.210`
- Controller B SP: `192.168.1.211`
- Cluster management: `192.168.1.220`
- Node A management: `192.168.1.221`
- Node B management: `192.168.1.222`
- SVM management: `192.168.1.223`
- NFS LIFs: `192.168.1.230`, `192.168.1.231`
- Future iSCSI LIFs: `192.168.1.240`, `192.168.1.241`, `192.168.1.242`, `192.168.1.243`

## Baseline Classification

- Current console evidence before fresh checks: historical artifact
- Active profile after source correction: ready for fresh real-lab checks
- NetApp login/read-only identification: blocked until NetApp-specific console or API credentials are configured
- NetApp management/API readiness: not configured yet
- NFS/vCenter readiness: preview only; apply disabled

## Next Action

Run fresh serial discovery, NetApp console autodiscovery, and console read-state in `local-lab-readwrite` mode, then build a read-only setup plan from live evidence and the corrected IP profile.
