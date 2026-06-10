# Lab Profile Examples

Lab profile selection drives default values across the app. Saved profiles are
local-only under `.local/lab-profiles.json` and must not be committed.
`.env.local.real-lab` is bootstrap, secret, and emergency override state only.
Reports and artifacts are evidence, not configuration source.

## /24 High-Address Lab

Use `profile_topology=high_address_lab` for a `/24` lab profile unless the
profile intentionally overrides individual addresses.

For `192.168.1.0/24`, defaults are:

- Gateway: `192.168.1.1`
- iLO: `192.168.1.201`
- Server NIC: `192.168.1.202`
- ESXi: `192.168.1.203`
- Cisco: `192.168.1.204`
- Ansible/control host: `192.168.1.205`
- NetApp controller A SP: `192.168.1.210`
- NetApp controller B SP: `192.168.1.211`
- NetApp cluster management: `192.168.1.220`
- NetApp node A management: `192.168.1.221`
- NetApp node B management: `192.168.1.222`
- NetApp SVM management: `192.168.1.223`
- NetApp NFS LIFs: `192.168.1.230`, `192.168.1.231`
- NetApp iSCSI LIFs: `192.168.1.240` through `192.168.1.243`

NetApp and vCenter participate only when enabled by the active profile. When
enabled, provider defaults and validation use the profile-derived addresses.

## /26 Compact Edge Lab

Use `profile_topology=compact_edge_lab` for compact edge labs. NetApp and
vCenter are disabled by default and appear as `not_in_scope`, not blockers.

For `10.10.5.0/26`, defaults are:

- Gateway: `10.10.5.1`
- Primary switch: `10.10.5.2`
- Possible second switch: `10.10.5.3`
- Reserved: `10.10.5.4` through `10.10.5.6`
- UPS: `10.10.5.7`
- Backup storage: `10.10.5.8`
- VM / utility host: `10.10.5.9`
- ESXi: `10.10.5.10`
- iLO: `10.10.5.11`
- NetApp: `not_in_scope`
- vCenter: `not_in_scope`

Custom profiles may override any address, but derived and overridden addresses
must stay inside the active subnet, must not use network or broadcast
addresses, and must not duplicate another active address.
