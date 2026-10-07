# SPP firmware assessment

The firmware step compares device-scoped iLO readings against the selected kit ISO.
Opening the page uses saved readings only. **Check firmware against SPP** runs a
read-only iLO probe and then repeats the assessment. It never installs firmware.

Eligibility uses the detected server model, ROM family and SPP SYSTEM.XML mapping,
not a rack-plan label or ISO filename. New DL360/DL380 plans have no assumed
generation. A successful, current, target-matched iLO probe resolves the generation
in linked plans, with an audit event and revision increment. Custom names, drive
configuration and placement are preserved. Different families are not resized or
replaced automatically. Save-as resets generation for the new hardware identities.
A conflicting planned label is displayed during assessment. Baseline membership and META.XML component IDs
must agree. Controller and NIC firmware require exact PCI vendor, device and both
subsystem IDs. Drives require an exact model match in the manifest's supported
SAS/SATA device predicates. Compound predicates are not weakened into OR matches.
Drivers and firmware utility version numbers are excluded from firmware ordering.
Full Rock Ridge filenames are checked because ISO9660 aliases can
replace dots in payload names.

Results require a successful, current, device-scoped probe matching the saved
connection target and an unchanged selected ISO. Missing, stale, ambiguous or
unsupported evidence returns Cannot determine. Newer installed versions are not
marked for downgrade. A matching adapter with an unsupported server ROM remains
unapproved, with its specific reason shown. Firmware utility matches require HPE
SUM to inspect embedded versions. Unmatched drives remain unknown, never current.

The read-only provider follows HPE OEM NetworkAdapters links (including older
BaseNetworkAdapters), reads bounded PCI inventory, and preserves nested HPE
Firmware.Current.VersionString values. Hardware health is displayed separately
from firmware availability. A Critical drive or Warning controller is not cleared
by finding a matching firmware package.

XML inspection is bounded and rejects DTD/entity declarations. No payloads are
executed or extracted. A metadata SHA-256 identifies the inspected manifests; it
is not an ISO authenticity or HPE signature check. Reinspect changed media.

Version availability is not installation approval. Intermediate upgrade steps,
dependency checks, HPE signatures and reboot readiness still require validation.
No whole-server compliance verdict is issued. Saved kit report snapshots include
each server's current assessment and its limitations in the exported report data.
The comparison is also shown in the report's printable view.

## Health review and upgrades

The firmware page separates hardware alerts from firmware matching limitations.
HPE DiskDriveStatusReasons and DiskDriveUse are retained in discovery. An
unconfigured but healthy drive is not a fault. Missing model/capacity is described
as incomplete identification, not proof that the drive is absent or failed.
Alerts identify the bay/component, reported reason, known facts and next action.

Acknowledgement is an audited app-state write, not a waiver or installation
approval. It is bound to the kit, exact device, target fingerprint, reading time
and alert evidence. A new reading requires new acknowledgement. Readings older
than 15 minutes cannot be acknowledged. Re-reading genuinely resolved hardware
removes the alert; acknowledgement does not. Saved report assessments include
these alerts and their acknowledgement state.

**Review upgrades** opens the target, selected SPP, matching version changes,
remaining blockers and an attended HPE SUM procedure. Saving that review records
intent only. Automatic SPP execution is not connected: **Install automatically**
remains disabled with the reason shown. No endpoint in this review performs
firmware writes, virtual-media mounting, power actions or RAID changes. The SUM
handoff explicitly warns against automatic offline mode and requires operator
supervision and dependency/applicability review.

The recommended workflow is hardware/drive inspection and diagnosis, vendor
firmware assessment and approved updates, RAID creation, then ESXi. Drive planning
can happen earlier. Creating RAID is not a repair for an unhealthy physical drive;
a firmware-based repair must be justified by HPE diagnostics and prerequisites.

Endpoints: POST `/{profile_id}/health-acknowledgements` and GET/POST
`/{profile_id}/firmware-upgrade-review`, under `/api/v1/rack-plans`, with an exact
`device_id`. Tests cover current-target binding, stale evidence, unconfigured
healthy drives, acknowledgement invalidation and the absence of execution.

References:
- [HPE iLO resource definitions](https://servermanagementportal.ext.hpe.com/docs/redfishservices/ilos/ilo5/ilo5_306/ilo5_hpe_resourcedefns306)
- [HPE storage management](https://developer.hpe.com/blog/storage-management-with-redfish/)
- [HPE SPP / SUM deployment modes](https://support.hpe.com/hpesc/public/docDisplay?docId=c03190790&page=GUID-AF397BA5-4F05-47E2-A822-80301DC0123F.html)
- [HPE SSA and offline configuration](https://support.hpe.com/hpesc/public/docDisplay?docId=a00094063en_us&docLocale=en_US&page=GUID-2E1C5CC0-9908-4B52-8373-7C47BCE5D928.html)

## Connection Evidence

Opening the firmware page reads saved inventory only; it does not contact iLO.
Saved comparisons are collapsed and labelled as historical, not an online status.
Check firmware against SPP runs a device-scoped read-only probe and only displays
comparison rows whose inventory timestamp matches that probe. Failed or blocked
checks and transport errors clear the displayed comparison rather than falling
back to old success readings. A completed check is a point-in-time reading, not
continuous connection monitoring. No firmware or equipment settings are changed.

## Warning Diagnostics

New iLO probes retain Smart Array cache-module and controller-board status and
attempt a GET-only IML sample (one system, up to 16 first-page entries; no paging).
Unsupported, denied, failed or malformed log reads do not discard the inventory;
their limitations are reported. IML events and HPE recommendations are displayed
as historical evidence, never automatically matched as the cause of a warning.
Repaired events stay labelled historical. No logs are cleared or marked repaired.
Unknown causes remain explicit. Backup-power `Present` establishes presence only,
not charge or battery health. Existing saved readings need a new explicit check
to acquire the additional evidence. Overall server warnings retain their safety
gates and may list component alerts without asserting a causal link.

Diagnostic field definitions: [HPE Smart Array resources](https://servermanagementportal.ext.hpe.com/docs/redfishservices/ilos/ilo5/ilo5_273/ilo5_hpe_resourcedefns273)
and [HPE IML fields](https://servermanagementportal.ext.hpe.com/docs/redfishservices/ilos/ilo5/ilo5_adaptation).
