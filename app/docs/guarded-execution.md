# Guarded execution backend

The first iLO 1.48 bridge has an implemented, gated backend executor; deployment
and frontend integration are not verified. Erased-drive return-to-service remains
disabled. No automatic worker or hardware action is enabled by status polling.

## Durable dispatch contract

Before using the ledger, the firmware orchestrator validates an unexpired,
single-use review, typed confirmation, immutable package identity, fresh exact
target evidence, supported capability and dependency ordering. Reservation itself
does not perform or replace these checks. Never put credentials in reviewed intent.

Reservations bind kit, device, resource and idempotency key to a canonical intent
digest. Reusing that key with different intent fails. A database unique device
lock excludes different keys, resources and kits from reserving competing work.
Mutations use a dedicated session and commit the operation and audit atomically.

Only the successful atomic accepted-to-running claimant may dispatch. It must
commit before sending. A crash before or after sending leaves running work locked;
timeouts become uncertain. Neither state can be reclaimed or automatically retried.
Only target-bound independent readback can complete a dispatched operation and
release its lock. Unsent attempts can instead be durably fenced before dispatch.

## Recorded reconciliation

GET status returns the latest recorded operation for that kit/device/resource.
GET reconcile requires the exact idempotency key as well. A match returns the
recorded operation ID and key, but does not prove hardware completion. Missing
records return uncertain, null recorded key and safe_to_retry=false. The
requested_idempotency_key field is only a lookup echo and must never unlock the UI.

A browser request lost before the server recorded it uses the explicit unsent
fencing workflow described below, with its persisted review token and attempt key.
Do not clear it from a historical operation, missing row, preview, timeout, or
operator acknowledgment. Legacy attempts without server-issued reviews stay blocked.

## Schema and verification

Migration 0006 adds guarded_operations without changing existing data. Startup
create_all installations are also supported. Downgrade refuses to discard
operation history. This implementation session did not apply live migrations.

Offline tests cover repeated and conflicting intent, cross-resource/device
exclusion, concurrent claims, persisted crash state and exact-key API lookup.
Live availability remains conditional on deployment, frontend integration and
every package, target, policy and hardware-health prerequisite described below.

## Offline firmware implementation

POST firmware-execution/inspect-component accepts only component_id and the
kit/device scope. It resolves the selected SPP from audit, rereads its catalog
without the comparison cache, hashes the actual files in /packages and records
an audit with the package-selection ID. Traversal, ambiguous names, symbolic
links, oversized payloads and changed media fail closed.

For iLO FWPKG archives, bounded ZIP inspection reads payload.json and hashes the
declared BIN without extracting files or running vendor installers. Declared
targets, update agents and versions are package claims, not hardware proof.
Signatures and upgrade dependencies remain unverified. Malformed archives carry
an explicit inspection_error; content hashing alone never enables apply.

The internal firmware worker rechecks an immutable server-built review,
confirmation, expiry and adapter preflight before reserving and claiming dispatch.
It sends once, keeps successful upload pending and records exceptions as uncertain
without persisting raw transport messages. The first-bridge adapter is registered
behind the explicit review and policy gates.

The narrow HPE transport implements the documented multipart BIN upload only.
It checks the reviewed digest, exact IP, known same-target direct-flash URI and
bounded filename/content, refuses redirects and performs no retry or host reboot.
It is connected to the public apply route through the guarded worker and tested
with MockTransport. No actual upload was performed during implementation.

The pure readback evaluator requires authenticated, fresh, post-submission
identity/version evidence and idle/complete update state without errors. It neither
collects evidence nor releases a ledger lock. The completion service now connects
trusted collection, single-use review evidence and atomic audited lock release.

POST firmware-execution/capabilities requires confirm_read_only=true, kit membership
and existing read-only policy gates. It performs fresh exact-target inventory and
GET-only UpdateService/firmware discovery, refusing external links, redirects and
incomplete collections. Status and preview never invoke it automatically.

## Local Package Observation

Read-only inspection of the mounted Gen10 2026.05 SPP identified iLO 5 v3.19:

- FWPKG: ilo5_319.fwpkg, 33587882 bytes.
- FWPKG SHA-256: c8fc9ea5784c2c296417364c1d916bd5b099dd9d339f1b6d9010c4c6cf0e731b.
- Embedded BIN: ilo5_319.bin, 33557086 bytes.
- BIN SHA-256: b37a3b863d97cc5966105bda6b52ac59dfa7fc0e99342fec45d36eedae423f92.

These are local content identities, not HPE signature verification or authorization
to upgrade the experimental server. Its exact installed-version upgrade path and
current capabilities remain unverified.

HPE documents direct binary upload and automatic iLO reset after its firmware
update. That reset must be disclosed in the firmware approval; it is not a host
reboot authorization. FWPKG metadata differs between package generations, so do
not assume every package embeds payload.json.

References:
- https://github.com/HewlettPackard/ilo-rest-api-docs/blob/master/source/includes/_ilo5_updateservicedoc.md
- https://servermanagementportal.ext.hpe.com/docs/references_and_material/blogposts/firmware_updates/part1/firmware_update_part1

## Latest Offline Verification

245 targeted tests passed using mock mode and network-disabled containers.
A separate opt-in PostgreSQL 16 test passed on a disposable network-isolated
database: eight concurrent reservations retained one operation and eight dispatch
claims produced one winner. The fixture container was removed after the run.
No live database migration or deployment was performed.

## Upgrade Prerequisites

Subsequent package-readme review establishes the bridge sequence for the recorded
iLO 1.37 target: 1.48, then 2.78, then the SPP's 3.19. Each step needs a fresh review
and separate confirmation including automatic iLO reset. The 2.78 readme explicitly
requires 1.48 or later; its known-issues section also requires 1.48 before 2.44+.

Do not implement the vendor's historical "32 MB" format limit as a raw BIN-length
comparison: the valid 1.48 bridge image itself exceeds 32 MiB when measured.
ilo_upgrade_path.py therefore blocks skipped prerequisite versions rather than
rejecting bridge binaries by that threshold. Size remains measured and bounded
for parsing/upload resource safety, not used as a substitute for version support.
61 targeted backend tests and 22 independent guarded frontend tests passed after
this correction. Deployment of these changes has not been verified by Codex.

## Standalone And Authenticated Bridge Preparation

Firmware execution now exposes kit/device-scoped local preparation endpoints:

- GET `standalone-packages?folder=...`: bounded FWPKG browsing under the media root.
- POST `select-standalone` with `path`: inspect and audit local bytes, independently
  of the kit's existing SPP selection. GET `selected-standalone` restores that selection.
- POST `prepare-spp-bridge` with an empty object: inspect the selected SPP's 1.48
  prerequisite FWPKG, verify its companion RPM with pinned HPE public keys in an
  isolated temporary RPM key database, and require exact binary equality.

Preparation never contacts hardware, installs an RPM, executes vendor code or
enables apply. Missing legacy power declarations remain explicitly unknown.
RPM tooling is an added backend image dependency; an older image fails closed.
Key assets come from the official URLs documented at
https://downloads.linux.hpe.com/project/fwpp/ and their SHA-256 values are pinned
in firmware_trust.py. Verification requires RSA/SHA384 key 74c3a4a2, successful
header SHA256 and payload SHA256 validation, plus exact BIN digest and size.

Observed against the local SPP: its prerequisite FWPKG SHA-256 is
48e02049b5a8acf552f82b668bc860d41e1ec7910e572a5820b04224a296026c;
the authenticated BIN is 33556514 bytes, SHA-256
59419c9b3f34d4cee7730f836ebcd61b6ad7c4843476551746781947a6437664.
The separately downloaded 1.48 FWPKG contains DIFFERENT binary bytes and fails
this exact-match check. The version label alone must never bypass the mismatch.

This establishes authentication of the binary via the RPM, not independent
verification of the FWPKG wrapper signature or its metadata, target applicability,
upgrade dependencies or permission to reset iLO. At that preparation milestone,
production review/dispatch and completion integration remained disabled.
143 related offline tests passed after
formatting, including strict metadata, selection scope, key tampering, absent or
failed signatures, binary mismatch, and media changes during verification.

## First Bridge Backend Integration (Not Deployed)

The backend now implements the selected SPP's authenticated iLO 1.48 bridge only.
Signed RPM payload.json authenticates the target, device class and direct-flash
power declarations as well as the BIN. Reviews expire after five minutes and bind
the actor, device, identity, package selection, content hashes and exact versions.
Review consumption and the durable device reservation are atomic. Only one worker
can claim dispatch; a lost response retains the lock and never triggers a retry.

All routes below use the existing kit prefix and device_id query:

- POST firmware-execution/preview with {} uses recorded fresh capabilities and
  local authenticated media, without hardware calls. It supplies the typed phrase.
- POST firmware-execution/apply requires review_token, confirmation_phrase and
  idempotency_key. A fresh preflight revalidates target and bytes before reservation.
  The adapter makes one CGI binary upload and discloses automatic iLO reset.
- POST firmware-execution/verify requires operation_id and confirm_read_only:true.
  A new authenticated exact-target readback must prove the reviewed version before
  completion is recorded and the device lock is released. GET status never probes.
- POST firmware-execution/reconcile-unsent requires review_token, idempotency_key
  and prevent_late_dispatch:true. It durably prevents a delayed send for an unsent
  server-issued review. It cannot cancel an already claimed dispatch or resolve
  legacy unknown attempts without a persisted review. Persist token and key in the
  browser before apply. dispatch_prevented:true means create a NEW review, not retry.

Current gates require iLO-specific operational health, firmware policy permission
and exclusive LAB_ALLOWED_WRITE_ACTIONS=ilo.firmware-update. Other legacy hardware
write paths do not yet share the durable lock, so mixed-write runtimes are blocked.
No runtime permission settings have been changed. In-app prerequisites and explicit
verify/reconcile actions still require frontend integration; do not claim deployment
or ask the user to approve installation merely because backend code exists.

Migration 0007 adds firmware_approvals without replacing saved data and refuses to
silently discard approval history on downgrade. No live migration, restart, probe,
upload, reboot or storage change was performed during implementation. Later firmware
bridges and erased-drive return-to-service remain unsupported by this adapter.

Final offline verification: 109 focused tests passed; full backend suite 1980
passed, 4 skipped, 1 failed. The remaining QA capability audit failure is missing
visual-test markers in frontend/tests/safe-action-runner.spec.ts, reported to the
frontend owner. Ruff passed. Disposable PostgreSQL also passed two concurrency
tests, including 16 races between dispatch and unsent fencing. Tests ran with
network disabled, fixture databases and no writes to the mounted app data.

## Component-Scoped iLO Health

Following the operator's clarification about deliberate rebuild conditions, overall
Warning is no longer a blanket firmware block. For the iLO-only bridge, drive and
storage-controller warnings remain listed without being treated as proof that iLO
cannot update. This does not clear those components for storage or RAID work.
A single healthy powered supply can qualify; the review explicitly requires power
to remain connected. Two supplies do not prove two independent PDUs.

Fresh server-collected evidence must establish healthy iLO, at least one healthy
enabled supply with input voltage, and complete healthy cooling/temperature sensors.
Critical server/chassis state, faulted energized power, unknown power, active erase
or rebuild and unresolved guarded operations still block. Missing component evidence
requires a new explicitly requested capability read. No background probes occur.

Preview returns structured warnings; the immutable review includes their assessment.
Preflight reassesses it and refuses changed evidence before dispatch. Storage alerts
are not repaired, suppressed or reclassified as healthy by firmware approval.
