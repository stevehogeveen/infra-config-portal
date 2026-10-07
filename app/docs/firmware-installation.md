# SPP iLO Installation

The app supports separate, reviewed iLO 5 updates from the selected SPP:

- Below 1.48: prepare the signed 1.48 prerequisite.
- From 1.48 through versions below 3.19: prepare 3.19 directly. There is no mandatory 2.78 hop.
- At or above 3.19: no reinstall or downgrade.

In Check firmware, open the server's update action and select Yes or No for the
displayed server and version. Yes includes firmware-only access and preparation;
there are no typed confirmations. An accepted upload is not completion: use
Check if it's done after iLO reconnects. After the bridge, select the next update
for a separate Yes/No decision, never an automatic second flash.

## Authentication and Execution

The server-owned catalog in `backend/app/services/firmware_catalog.py` maps exact
supported versions to SPP paths. It does not accept arbitrary RPM paths or commands.
The offline verifier checks the pinned HPE signing key, RPM signature and payload
digests, exact BIN hash/size, and every signed target/version/direct-flash declaration.
For 3.19, all three declarations must describe the same binary. This authenticates
the BIN and signed RPM declaration, not the FWPKG wrapper signature.

Preview binds one matching updateable inventory target, installed/desired version,
package selection, binary bytes, identity and component-specific health evidence.
Apply repeats those checks and commits a single dispatch claim before one upload.
Lost responses retain the device lock; retries do not upload again. Completion
requires independent exact-target readback of the reviewed version. No host reboot
or storage operation is part of this adapter.

## Future SPPs and Newer Servers

An SPP comparison is not installation support. Future cumulative packages must use
their own authenticated manifests and model/iLO-specific prerequisites. Do not
copy the legacy bridge or a 2.78 minimum to every newer server. Nor does a version
above 2.78 by itself prove that an entire SPP can be applied without dependencies.

The UI does not offer the iLO 5 installer for a detected different iLO generation;
the backend also rejects an explicitly different manager generation and always
requires signed target matching. Detected manager/server models are review-bound.
Adding another iLO generation or SPP version requires catalog/adapter support,
primary vendor prerequisite evidence, signed-package verification, and offline
tests for its exact upload/readback contract. HPE SUM-driven whole-SPP cumulative
updates remain a separate integration, not claimed by the iLO 5 binary adapter.

## Offline Verification

Run the firmware catalog, trust, flow, adapter, worker, completion and reconciliation
pytest suites with mock providers and network disabled. The frontend firmware
update-panel and overview Playwright fixtures intercept all API traffic. Never
point those fixtures at a live hardware backend. Real SPP authentication can be
tested in a disposable network-disabled container with media mounted read-only.

## Upload Diagnostics and Unverified Attempts

The adapter creates a new session inside the claimed dispatch and deletes it only
after the upload returns or fails. The upload uses HPE's session cookie, token,
Accept/Expect/OData headers and multipart `file` field, without inherited Basic
authentication. Connect timeout is 30 seconds; upload read/write timeout is 300
seconds. A timeout never triggers an automatic retry.

Transport failures record only a fixed stage/reason, numeric HTTP status,
allowlisted content type and whether a JSON error key was present. No response
bodies, tokens, URLs or credential-bearing exception strings are retained.
Failures proven to occur before invoking the upload are failed, release the
device lock and report `dispatch_prevented=true`. Anything possibly sent remains
uncertain. Old generic errors cannot retrospectively prove no upload occurred.

For a settled uncertain attempt, the operator may dismiss it with a Yes/No
confirmation. No fresh verification or waiting period is required; an active
hardware dispatch lease must have finished. Preview and close endpoints do not
contact hardware. Yes supplies the existing confirmation token internally and closes the
attempt as an **operator-acknowledged unverified failure**, not proof that nothing
happened. The audit preserves `dispatch_prevented=false` and
`resolution=operator_closed_unverified`. The old attempt cannot be resent and
`safe_to_retry` stays false. A new update needs a new Yes/No confirmation.

The iLO installer has a single Yes/No dialog naming the server and update version.
Yes performs preparation, enables firmware-only access if needed, creates the
review and submits once. No closes without preparation or a hardware call.
There are no typed phrases or extra scope/review screens. For local-lab-readwrite,
hardware-health findings are informational for iLO firmware only; target/package
validation and conflicts with running operations remain enforced. Progress and
uncertain outcomes remain visible; closing the window does not cancel hardware.

This lab-only close-out differs from verified completion and from a proven unsent
attempt. Missing IEL entries or an unchanged version alone never auto-unlock it.
See [HPE Update Service documentation](https://servermanagementportal.ext.hpe.com/docs/redfishservices/ilos/supplementdocuments/updateservice)
for the transport contract; the explicit unverified close-out is app policy, not
an HPE guarantee of non-execution.
