# ESXi installer artifact runbook

## Scope

`app/backend/app/services/esxi_installer_artifact.py` prepares one derived,
profile-bound ESXi installer ISO entirely on the application host. It does not
contact iLO, ESXi, the switch, storage, or any other provider. It is not an
install executor and is not registered as a Run Center write action.

This closes the media-preparation gap between the existing ESXi install
readiness check and the existing guarded iLO VirtualMedia/installer-boot
workflow. A `ready` artifact still requires separate live disk-identity,
attach, boot, install, and post-install validation gates.

## Reused lessons and tooling direction

- The repository toolchain skill selects iLO VirtualMedia plus Kickstart for
  ESXi install, then `govc` only after ESXi management exists.
- The Lab Builder reference requires discover, plan, validate, preview, apply,
  status, and report stages; generated media belongs under ignored
  `artifacts/`, never in source control.
- The existing lab-profile fingerprint is reused. A runtime fallback profile,
  stale version, changed fingerprint, or mismatched IP/default list is refused.
- The existing atomic JSON/text artifact writer is reused.
- Broadcom documents scripted ESXi installation as supported but warns that the
  exact destination disk must be checked because disk names can vary and the
  installer permanently overwrites data. The request therefore refuses
  `firstdisk` and requires one exact installer disk identifier.
- Broadcom documents `%firstboot` as unavailable with Secure Boot. This first
  slice uses `%firstboot` for additional DNS servers and NTP, so it fails closed
  when `secure_boot_expected` is true.
- GNU xorriso's boot-equipment `replay` mode is used after file mapping so the
  existing El Torito BIOS/UEFI boot equipment is remastered rather than
  hand-reconstructed.
- GNU xorriso `1.5.8.pl02` is the minimum accepted release. Earlier `1.5.8`
  patch levels lack fixes used by the replay path and fail the dependency check
  before a Kickstart or derived ISO is written.
- Every xorriso process starts with `-no_rc`. System and per-user xorriso
  startup files therefore cannot silently change the reviewed remaster or
  inspection commands.

Primary references:

- [Broadcom: Methods for installing ESXi 8.0](https://knowledge.broadcom.com/external/article/334435/methods-for-installing-esxi-80.html)
- [Broadcom: scripted install host identification and Kickstart behavior](https://knowledge.broadcom.com/external/article/440457/esxi-scripted-installation-fails-to-dyna.html)
- [Broadcom: DNS and `%firstboot` Secure Boot caveat](https://knowledge.broadcom.com/external/article/427841/esx-kickstart-script-warning-bootproto-w.html)
- [Broadcom ESXCLI reference: system NTP commands](https://developer.broadcom.com/xapis/esxcli-command-reference/latest/namespace/esxcli_system.html)
- [GNU xorriso manual: boot image replay](https://www.gnu.org/software/xorriso/man_1_xorriso.html)
- [GNU xorriso 1.5.8.pl02 release and signature instructions](https://www.gnu.org/software/xorriso/)

## Current dependency state

As checked on 2026-07-23, `xorriso` and `pycdlib` are not installed in the
current Windows/backend environment. WSL has no installed subsystem or
distribution, and Docker, MSYS2, Cygwin, `oscdimg`, `mkisofs`, and
`genisoimage` are also absent. The implementation intentionally does not fall
back to copying or renaming the source ISO. It returns
`builder_dependency_missing` and writes only a redacted report until GNU
xorriso `1.5.8.pl02` or newer passes an isolated local version check.

The safest Windows dependency path is a short, external MSYS2 tool root plus a
GPG-verified build of the current GNU xorriso source release. Do not vendor an
untracked `xorriso.exe` by itself: the MSYS build also needs its runtime DLLs,
and a copied binary loses package/signature provenance. The current MSYS2
binary repository still offers xorriso `1.5.6-1`, which is below the enforced
minimum. Installation or compilation is a separate host change and requires
explicit approval; this repository does not perform it.

## Required request

Keep the request in an ignored local path because it contains a salted root
password hash. Never commit it.

```json
{
  "profile_id": "lab-single-server",
  "profile_version": 1,
  "profile_fingerprint": "<64 hex characters from the active profile context>",
  "source_iso_path": "C:\\absolute\\allowed-media\\VMware-ESXi.iso",
  "expected_source_iso_sha256": "<64 hex characters>",
  "hostname": "esxi01.example.test",
  "management_ip": "192.0.2.203",
  "subnet_cidr": "192.0.2.0/24",
  "gateway": "192.0.2.1",
  "dns_servers": ["192.0.2.53", "192.0.2.54"],
  "ntp_servers": ["ntp1.example.test", "ntp2.example.test"],
  "management_nic": "vmnic0",
  "management_vlan_id": 100,
  "install_disk_id": "naa.example-exact-logical-drive-id",
  "system_media_size": "min",
  "root_password_sha512_crypt": "<local salted $6$ SHA-512 crypt value>",
  "secure_boot_expected": false,
  "allow_firstboot_network_services": true,
  "local_datastore_expected": true,
  "acknowledge_install_disk_overwrite": true
}
```

The active saved profile must be the single-server local-storage deployment
type. Its ESXi IP, subnet, gateway, complete ordered DNS list, complete ordered
NTP list, and VLAN must exactly match the request. Empty DNS or NTP defaults
block artifact generation.

The root input must be a salted SHA-512 crypt string beginning with `$6$`.
Plaintext is rejected during request validation. The encrypted value is
embedded only inside `KS.CFG` in the derived ISO and is omitted from JSON,
Markdown, the manifest, logs, and CLI summaries.

## Offline command

From `app/backend`:

```powershell
.\.venv\Scripts\python.exe scripts\esxi_installer_artifact.py C:\path\to\ignored-request.json
```

This command:

1. validates the complete request;
2. binds it to the active saved profile ID, version, and fingerprint;
3. requires the source ISO to be a nonsymlink file below
   `MEDIA_INVENTORY_DIRS`;
4. checks the explicitly approved source SHA-256;
5. copies the source to a temporary snapshot, so xorriso never receives the
   original path;
6. creates LF/UTF-8 `KS.CFG`;
7. updates both `/BOOT.CFG` and `/EFI/BOOT/BOOT.CFG` with exactly one local
   Kickstart reference plus the selected `systemMediaSize`;
8. runs xorriso boot-equipment replay into a temporary output;
9. reads back the Kickstart and both boot configs;
10. parses source and derived El Torito catalogs and requires explicitly
    bootable BIOS and UEFI entries in both;
11. compares catalog entry order, platform, bootability, emulation, load
    segment, partition type, load size, image path, and image options while
    allowing expected LBA relocation;
12. compares source and derived system-area options, summary, MBR geometry and
    partition types, GPT/APM type/flag/name/path characteristics while ignoring
    relocated addresses, enclosing-image sizes, and regenerated identity GUIDs;
13. rechecks the original source checksum;
14. publishes a content-addressed ISO, redacted manifest, and SHA-256 sidecar
    only after every check passes.

The manifest records source and derived boot platforms, system-area summaries,
and independent El Torito/system-area equivalence results. Generic text such as
"El Torito present" is not accepted as proof.

Outputs are under:

- `artifacts/derived-media/esxi/<profile-id>/`
- `artifacts/codex-runs/esxi-installer-artifact-redacted.json`
- `artifacts/codex-runs/esxi-installer-artifact-report.md`

## Mandatory live gates after a ready artifact

Do not attach or boot merely because offline preparation says `ready`.

1. Use current read-only storage/installer evidence to prove
   `install_disk_id` is the intended local RAID logical drive. The first
   attended run must not rely on `firstdisk`.
2. Reconfirm active profile fingerprint, source checksum, derived checksum,
   server identity, and iLO identity immediately before attach.
3. Use the existing guarded iLO virtual-media and installer-boot stages.
4. Observe the first install through console/iLO and keep the switch console
   available for independent network recovery.
5. Prove ESXi host identity, management IP, API reachability, DNS, NTP, exact
   disk-backed installation, local datastore, and virtual-media ejection.
6. Only after those proofs should VM deployment be enabled.

The derived ISO is destructive only when a later guarded workflow boots it.
This offline preparation step performs no live write.
