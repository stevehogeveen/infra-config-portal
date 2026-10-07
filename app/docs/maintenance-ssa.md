# Read-only SSA through Ansible

Connect equipment > Drives & RAID > Storage troubleshooting > Advanced maintenance
diagnostics queues a fixed Ansible playbook on the existing automation worker.
It does not boot media, shut down ESXi, clear cache, delete arrays or create disks.
Results are diagnostic text, not interpreted health clearance or rebuild approval.

## Maintenance host prerequisites

Use a supported Linux maintenance environment booted on the physical HPE server,
not the portal container or a VM. Install the HPE-supported SSA CLI package for
that environment and controller, Python 3 at /usr/bin/python3, and OpenSSH server.
Expose the installed SSA CLI at /usr/sbin/ssacli. Do not assume SPP exposes SSH.
HPE binaries and a bootable ISO are NOT bundled by this change; compatibility,
distribution rights and the boot procedure must be validated before live use.

Provision a dedicated temporary SSH key and an account permitted to read DMI and
run SSA diagnostics. Pin the host key through a trusted console, not an unverified
network scan. No password fallback, host-key auto-acceptance, or automatic sudo
is used. A root maintenance account works but must be restricted to this isolated
environment. The playbook writes only Ansible temporary files under /tmp.

The maintenance environment must contain /run/lab-builder-maintenance with the
single line `lab-builder-maintenance-v1`. This is an enrollment marker, not proof
of a RAM-only boot or authorization for destructive commands. The playbook also
matches /sys/class/dmi/id/product_serial against a fresh iLO serial before SSA.

## Enroll a target

Under the ignored repository .local/maintenance/<device UUID>/ directory, provide:

- target.json: `{"host":"192.0.2.20","port":22,"username":"root"}`
- ssh_key: private SSH key, readable only by the operator and automation worker.
- known_hosts: verified OpenSSH known-host entry for that address/port.

The example address is documentation-only. Use the maintenance OS address, not
the iLO address. No host address is built into code. Only literal IP addresses
are accepted in this first version. Both backend and worker need their existing
.local mount. On Linux, ensure UID 10001 can read the enrollment files without
making private keys world-readable. Keys are copied to private temporary files
with mode 0600 for execution and removed afterward.

Rebuild backend and automation-worker after installation. The worker image now
includes openssh-client. Explicit hardware-read policy must be enabled on BOTH
services; mock mode does not connect. Do not enable destructive policy flags.

## Execution and evidence

The API binds each queued job to the device, iLO access revision, lab-profile
revision and maintenance enrollment digest. Credentials are never queued.
The worker obtains fresh iLO identity, verifies SSH host trust and the physical
serial, then runs only `controller all show status` and
`controller all show config detail`. No caller-provided commands are accepted.
Changes to enrollment or policy invalidate results. Requests are audited. Raw
diagnostics remain in the local Redis result for up to one hour; they can contain
hardware serials and must not be committed or shared without review.

This is the first diagnostic execution path, not an automated repair executor.
Live boot-image validation and destructive recovery are still pending.

References: [HPE SSA commands](https://support.hpe.com/hpesc/public/api/document/a00098103en_us)
and [Ansible SSH](https://docs.ansible.com/projects/ansible-core/2.18/collections/ansible/builtin/ssh_connection.html).
