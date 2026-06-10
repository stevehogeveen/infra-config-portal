# NetApp Management Network Scan

Checked at: 2026-06-09T22:32:03Z

## Scope

- Subnet: `192.168.1.0/24`
- Provider mode: `local-lab-readwrite`
- Probe methods: `ping -c 1 -W 1`, `nc -z -w 2` for TCP/443 and TCP/22, `ip neigh show`
- NetApp commands run: `none`
- Secrets printed: `no`

## Results

| Target | Role | Ping | TCP/443 | TCP/22 | Neighbor State | Classification |
| --- | --- | --- | --- | --- | --- | --- |
| `192.168.1.210` | Controller A SP | failed | closed | closed | FAILED | unused/free |
| `192.168.1.211` | Controller B SP | failed | closed | closed | FAILED | unused/free |
| `192.168.1.220` | Cluster management | failed | closed | closed | FAILED | unused/free |
| `192.168.1.221` | Node A management | failed | closed | closed | FAILED | unused/free |
| `192.168.1.222` | Node B management | failed | closed | closed | FAILED | unused/free |
| `192.168.1.223` | SVM management | failed | closed | closed | FAILED | unused/free |
| `192.168.1.230` | NFS LIF 1 | failed | closed | closed | FAILED | unused/free |
| `192.168.1.231` | NFS LIF 2 | failed | closed | closed | FAILED | unused/free |

## Classification Basis

Each address had no ICMP reply, no TCP/443 or TCP/22 connection, and a failed ARP neighbor entry on the local lab interface. That is treated as `unused/free` for planning because no host answered at L2/L3 during this scan.

## Caveat

Before any future apply workflow assigns these addresses, rerun this scan immediately before the change. A host that blocks ping and both TCP ports could still exist, so this scan is planning evidence, not an apply authorization.

## Next Action

Use these addresses in the NetApp setup plan preview and keep apply disabled until an explicit guarded setup workflow exists with `NETAPP_SETUP_APPLY=true` and separate confirmation flags.
