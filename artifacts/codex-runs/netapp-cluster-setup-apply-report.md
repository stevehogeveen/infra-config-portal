# NetApp Cluster Setup Apply Report

- Checked at: `2026-06-11T02:26:55.512739+00:00`
- Status: `blocked`
- Detected state: `login_required`
- Apply enabled: `False`
- Serial writes attempted: `False`
- ONTAP writes attempted: `False`

## Required Flags
- `PROVIDER_MODE=local-lab-readwrite`
- `NETAPP_SETUP_APPLY=true`
- `NETAPP_SETUP_CONFIRM="APPLY NETAPP CLUSTER SETUP"`
- `NETAPP_SETUP_ALLOW_CLUSTER_CREATE=true`

## Missing Setup Intent Fields
- `admin_access_source`

## Remediation Items
- `admin_access_source`: set `.env.local.real-lab: NETAPP_ADMIN_ACCESS_SOURCE` suggested `.env.local.real-lab NetApp admin access reference`; recheck `make provider-lab-netapp-setup-preview`

## Blockers
- Console state is `login_required`; setup apply only supports cluster/node setup wizard states.
- NetApp setup intent has missing required fields.
- NETAPP_SETUP_APPLY=true is required.
- NETAPP_SETUP_CONFIRM="APPLY NETAPP CLUSTER SETUP" is required.
- NETAPP_SETUP_ALLOW_CLUSTER_CREATE=true is required.

## Transcript Summary
- No transcript was captured because apply gates did not start an interactive setup session.

## Safety
- No secrets are written to this report.
