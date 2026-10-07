# Storage controller reset

Connect equipment > Drives & RAID > Advanced storage recovery exposes a read-only
reset preview and a separately confirmed execution. This is a controller reset,
not an iLO reset, server factory reset, physical drive sanitize, or secure erase.
It removes arrays and custom controller settings, destroying access to their data.

The implementation sends HPE's documented iLO 5 request through the existing
device-scoped provider and audit workflow:

```json
{"Actions": [{"Action": "FactoryReset"}], "DataGuard": "Disabled"}
```

Source: [HPE factoryresetcontroller](https://servermanagementportal.ext.hpe.com/docs/redfishclients/ilorest-userguide/smartarraycommands#factoryresetcontroller-command).

Only the existing single-system, single-controller SmartStorageConfig v2 executor
is supported. Gen11/RDE and multiple controllers are not covered. Existing
destructive-write gates still apply; additionally, policy must explicitly allow
`ilo-redfish.hpe-raid-factory-reset` and `LAB_ALLOW_FACTORY_RESET=true`. Do not
forget the device-specific `HPE_RAID_RESET_DEVICE_IDS` allowlist. Unlisted servers
cannot use this reset endpoint even with factory-reset permission enabled. Do not
enable these globally to bypass a failed storage operation. Mock/read-only modes
cannot perform the reset. No runtime policy is changed by this feature.

The preview shows the target, existing volumes, exact request and blockers.
Confirmation requires the specific RESET STORAGE CONTROLLER phrase, data-loss,
backup, hardware and firmware acknowledgements and inspection of unknown bays.
The server must be off. Preflight rechecks the saved plan and hardware state.
The conditional write is claimed durably before submission and is never retried.

The advanced recovery section provides a separate shutdown preview and typed
confirmation. It uses advertised GracefulShutdown, or a momentary PushPowerButton
when graceful shutdown is not advertised. Read power state afterward; acceptance
is not proof the OS stopped. The shutdown screen displays timestamped power
evidence and polls read-only after submission (also after an uncertain response),
with ten seconds between completed reads, stopping at Off or after ten minutes.
Monitoring can be paused; leaving the page stops scheduling further reads.
Read failures show Unknown, and readings older than one minute are labeled as
previous observations. Power reads preserve the typed confirmation and never
resubmit a power command. A separately confirmed ForceOff is available only
after a prior shutdown request and a two-minute wait. Power requests have durable
single-use claims and are not automatically retried. Shutdown additionally needs
`ilo-redfish.raid-shutdown`, power permission and the device allowlist. No power
request, reset or boot is sent merely by opening the page.

The workflow has separate explicit approvals for shutdown, storage reset and
power-on. It is not an unattended chain. If a response is lost, check power and
pending settings before continuing. This first version conservatively blocks
repeating a previously recorded shutdown mode for the device; it does not yet
start a new shutdown cycle automatically after a completed rebuild.

Power-on is separately confirmed and rechecks reset permission. Creation remains
a separate operation after reset verification; it is not automatically chained.

Verification requires the same target, no outstanding pending changes, no logical
volumes and only successful HPE settings messages. This proves an empty layout
and reported completion, not healthy cache or secure erasure. Health must be
read again before further work.

## Remaining recovery limitation

A previously uncertain deletion still blocks reset. A fresh, same-target
controller-status rejection can instead be recorded as failed when its settings
timestamp follows the recorded boot, the original submission was accepted, and
no pending settings remain. Missing, stale, future-dated or ambiguous evidence
does not release the operation. Failed deletion is not success: repeating that
deletion remains blocked, while a separately approved controller reset can be
reviewed. The original attempt and rejection evidence remain in the audit trail. This
feature does not yet provide an SSA maintenance-boot executor, obsolete-cache
discard. A Redfish reset may itself be rejected by an unhealthy
controller. Do not present it as a guaranteed repair.

Validation uses mocked hardware in backend and browser tests. Live reset and
rebuild must be separately approved and checked on the target before claiming
end-to-end hardware validation.
