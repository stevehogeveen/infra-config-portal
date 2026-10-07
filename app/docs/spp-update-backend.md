# Whole-SPP Backend

## Availability

The local-lab provider uses HPE's automatic offline SPP environment for qualified
iLO5/6 packages. Plan/apply/status/reconcile/verify endpoints are registered under
`/api/v1/rack-plans/{profile_id}/firmware-update`. Mock mode does not enable a real
installer. The separate remote SUM StepAdapter remains unconfigured; it is not
used by the offline execution path. No live SPP installation has been performed
as part of implementation testing.

## Automatic Offline Execution

`providers/hpe_spp_boot.py` qualifies the supplied Gen10 2026.05 and Gen11 2026.03
boot configurations: automatic mode after ten seconds, automatic reboot on success.
All three BIOS/UEFI menu files must match the inspected normalized templates;
kernel, initrd and EFI loader must exist. Unknown templates or manager generations
are rejected rather than silently booted. This check is not vendor authentication.
The entire selected ISO is SHA-256 bound to approval, and the served bytes are
checked against it before mounting. HPE's updater owns applicability, dependencies,
component signatures, installation order and any additional restarts.

The frontend shows one review and a Yes/No confirmation covering all applicable
firmware in the ISO, one-time CD boot, power-on/restart and final media removal.
The displayed component versions are independent verification targets, not a
complete deployment manifest or an app-controlled sequence. Unassessed components
are not reported as up to date. Health warnings remain advisory for this action.

`services/spp_offline_boot.py` persists mount, boot-selection, reset, observation
and eject phases using the existing device lock and approval ledger. Each send
is claimed before transport runs. It does not expand global write scope; the
approved operation's target and phase authorize only its own commands. Status
GET reads stored state only. Check status performs an explicit readback and can
resume a proven applied phase without resending it, or resume a paused preparation
whose next command was never sent. Missing HTTP admission uses the existing
exact-review fence, not hardware reconciliation.

Completion requires stable UUID/serial identity, unchanged identified drives,
matching listed firmware versions, idle UpdateService, and two distinct POST
timestamps newer than the original reading. The second POST distinguishes initial
SPP boot from the vendor updater's return. This is independent readback evidence,
not a captured SUM success report for every component. If the first POST was
missed, completion cannot be inferred from versions alone. After four hours the
operation is explicitly unresolved; Check status can read again, but no boot or
firmware command is automatically repeated. Power loss, vendor failure, unsupported
updates or a missed reboot may need operator inspection in the iLO console.

Only this operation's media is ejected, after fresh version readback. A backend
restart never repeats a claimed command. Restarting the backend while SPP is
using its media service interrupts ISO delivery and must be avoided.

`providers/spp_media_server.py` uses Starlette FileResponse for HTTP byte ranges.
It serves only top-level, non-symlink ISO files from the media folder, with no
directory listing or write methods. The listener starts on approval, not on page
load. Compose publishes port 8088; the ignored local override advertises the
operator host's routed LAN address with `ESXI_MEDIA_HTTP_HOST`. This plain HTTP
service is intended only for the configured lab network. An external service may
be selected by `SPP_MEDIA_BASE_URL`; it must serve the identical approved ISO.
The backend can validate served bytes, but cannot prove the iLO's network path
without an actual approved virtual-media attempt. Host/network firewalls must
allow the lab iLO to reach that media port.

HPE references: [SPP offline update procedure](https://support.hpe.com/hpesc/public/docDisplay?docId=sd00007941en_us&docLocale=en_US&page=GUID-620D9A7C-905C-4BC5-8E28-0BE972E8C357.html)
and [server boot-state reporting](https://servermanagementportal.ext.hpe.com/docs/references_and_material/blogposts/etc/masterserverstates/masterserverstates).
iLO5 host progress uses PostDiscoveryCompleteTimeStamp, not the DPU-only
BootProgress field. iLO7 needs a separately qualified route; no universal 2.78 hop
is introduced.

## Implemented Boundary

- `services/spp_update_contract.py` validates the review and recorded-progress
  shapes agreed in `agent-chat.md`. Serialize with `by_alias=True` to emit `from`.
- `services/spp_update_plan.py` projects normalized assessment evidence into an
  ordered review. It does not parse vendor reports or issue approval tokens.
- `providers/hpe_sum_assessment.py` inspects the local ISO and builds only
  report-mode invocations. It does not launch a process or contact hardware.
- `providers/hpe_sum_reports.py` parses the observed SUM 12.7.0 English repository
  inventory XML, bounded by size, depth and component count. It preserves vendor
  warnings and rejects ambiguous fields/unsupported formats. Repository contents
  never become target applicability, authenticated packages or installed versions.
- `services/spp_update_execution.py` issues persisted actor/target-bound reviews,
  consumes them through the existing guarded ledger, and commits each step claim
  before an injected adapter can send. Progress snapshots and ledger transitions
  are atomic. Duplicate/concurrent workers cannot claim the same step twice.
  The injected adapter interface covers preflight, run authority, send and
  independent readback; no production SUM adapter is registered.
- `services/spp_update_runtime.py` connects trusted assessment to review/admission
  and provides a restartable database queue. `main.py` configures OfflineBackend
  in local-lab-readwrite mode, or uses an explicitly injected test backend.
  Applying records work; it does not launch
  a vendor process inside the HTTP request. Sent/uncertain work is never resent.
- `api/spp_update.py` exposes exact-device routes with strict request shapes.
  Recorded status remains readable if the provider becomes unavailable.
  Reconciliation can atomically consume a never-recorded review, preventing a
  delayed apply request from dispatching it, including after review expiry.
- `providers/hpe_sum_runner.py` provides a private Linux subprocess transport,
  bounded XML capture, timeout cleanup and durable one-shot dispatch markers.
  Its firmware-only input builder selects exact components and restart policy.
  Tests use fake executables, not target hardware. This is not yet a production
  StepAdapter or proof that a complete SUM runtime is isolated/authenticated.
- `reconcile_step` accepts independent post-crash completion evidence only when
  target/version/time match and dispatch and authority cleanup have ended. It
  never sends an update. A real reconciliation reader is still required.

Plans carry `can_apply`, nullable approval credentials, stable `step_id` values,
and profile/device identity. `current_step` is a step ID, not an array index.
Unknown estimates remain null. An assessment projection cannot authorize writes.
Status carries the recorded operation's idempotency key; a missing or different
key is not proof that an ambiguous send did not happen. Uncertain operations keep
their device lock and cannot advance to another component.

## Offline SUM Findings

The locally supplied 2026.05 Gen10 SPP contains `sum1270_b16.txt` and SUM 12.7.0.
The binary's help and a repository-only inventory ran successfully in a disposable,
network-disabled container. Runtime dependencies added to the test image were
`libgssapi-krb5-2`, `iproute2`, `systemd-sysv`, `gawk`, `kmod`, `pciutils`,
`dmidecode`, `unzip` and `binutils`. This is runtime/report evidence only, not
authentication, hardware compatibility or an installation test.

The bundled CLI help explicitly distinguishes these report modes:

| Flag | Purpose |
| --- | --- |
| `--report` | Deployment preview without installation |
| `--firmware_report` | Installed component report without installation |
| `--dependency_report` | Failed dependency report without installation |
| `--inventory_report` | Repository inventory without installation |
| `--installed_report`, `--combined_report` | Can deploy; forbidden for assessment |

The report builder always includes `--dryrun` and `DRYRUN = YES`, fixes
`TARGETTYPE = iLO`, requires an explicit saved target, and rejects input-file
line injection. Credentials are not included in argv or object repr. The future
runner writes the input file with mode 0600 in a private job directory and removes
it after execution. Raw stdout/stderr are discarded. Do not log input content,
report bytes or environment secrets. Production qualification must also account
for SUM's own engine logs, daemon lifetime and shared runtime paths.

Direct binary invocation uses the inspected launcher's SUM_ROOT, LEGACYMODE and
INPUTFILEPATH selectors without its shell eval. This still needs end-to-end
report validation before becoming a production runner. Using the bundled bash
launcher, an explicit temporary baseline containing only the Gen10 SPP's iLO5
3.19 RPM generated repository XML. The baseline intentionally omitted signature
sidecars, so SUM reported `Component signature file missing` and exited with 3.
The engine shut down normally. The test fixture preserves the output structure,
normalizing only its temporary path and date; see its provenance README.
No target firmware, dependency or deployment-preview report has been captured.

## Generation Handling

Use detected manager generation and verified package/platform support, not server
generation alone. Gen12 is not a reliable synonym for iLO7. iLO7 offline update
plans are rejected; a supported online execution route is required. Do not inherit
the existing iLO5 binary adapter for iLO6/7 or insert a universal 2.78 hop.

## Separate Remote SUM Work

1. Authenticated SUM runtime and compatible baseline selection, with an isolated
   report runner and a parser validated against actual vendor report output.
2. Supply a trusted production assessment backend to the implemented routes and
   durable queue. Validate target applicability, dependencies, component signatures
   and installed versions against captured vendor reports, not repository metadata.
3. Run-owned firmware authority and only the power/restart actions disclosed in
   the reviewed plan. Revoke run authority on completion, failure or uncertainty;
   revocation never means an in-flight flash was cancelled.
4. Implement the production StepAdapter for SUM and generation-specific transport.
   The offline worker already tests single-dispatch execution, independent version
   verification and stopping on uncertainty. A claimed step remains locked after
   process death; a production reconciliation reader is still required. Authority
   cleanup failure retains the lock even when no command was sent.
5. Connect frontend lost-send reconciliation and run production-provider end-to-end
   tests. Keep status unavailable for unconfigured providers so the working iLO
   controls remain available. Qualify iLO5, iLO6 and iLO7 separately.

## Latest Offline-Route Verification (2026-09-29)

637 backend tests passed, three skipped, using disposable SQLite fixtures and
disabled Docker networking. The selection covers SPP/SUM, firmware, iLO, guarded
operations and write scope. Ruff passed. TypeScript and 36 browser checks passed,
including keyboard approval, exact attempts, offline reconciliation, completed
result retention and narrow layouts. Desktop and 320px screenshots were inspected.

The backend was rebuilt and deployed after a PostgreSQL backup. ISO range reads
returned the expected bytes through localhost and the advertised host address.
Recorded SPP status returned 200 through both backend and frontend proxy, with
no update started. Global scope remained read_only and no active operation was
recorded. No live hardware request was made for these deployment checks.

## Earlier Remote-SUM Foundation Verification

118 tests passed across contract, plan, execution, runtime/API, repository parser,
assessment construction and subprocess transport. They ran with mock providers,
a temporary SQLite database and Docker networking disabled. Coverage includes
duplicate apply, lost-send fencing, worker restart, interrupted admission,
post-crash proof validation, credential cleanup and retained dispatch markers.
These results are not a live SUM installation test.

The broader firmware/readback/recovery/iLO/scope selection passed 783 tests with
one skipped. An unrelated inventory-automation module was excluded from collection
because the offline image lacks fakeredis. Ruff checks passed for the changed
backend integration and tests. No deployment was performed for this slice.

Hardware execution requires a separate exact-plan approval. All development
checks for this slice use fixtures or network-disabled containers; no hardware
probe, firmware update, reboot, disk erase or RAID operation was performed.
