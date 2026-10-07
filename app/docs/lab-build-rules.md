# Lab build rules

These govern how Lab Builder builds a lab. They are the rules the design mockups in
`app/docs/design/` encode, written so they can be implemented and tested. When code and
this file disagree, one of them is a bug — decide which, do not quietly diverge.

## 1. Three levels, and nothing crosses them

- **Metal** — what is physically in the rack: servers, switch, storage array. Only these
  appear as rack units.
- **Software** — what is installed *on* a server: the hypervisor, and the VMs it runs.
  ESXi is never a rack unit; it is a property of a server.
- **Cluster** — what spans several servers: vSAN, and vCenter as the thing managing them.
  A cluster is never a rack unit or a device.

## 2. Two drives per host belong to ESXi

- Every host that runs ESXi reserves exactly **two** drives as a RAID 1 mirror to boot from.
- Those two never join vSAN, never back a datastore, and are never counted as capacity.
- Every remaining bay has exactly one job: vSAN, local datastore, or unassigned.
- The sum of assigned roles can never exceed the bay count reported by the controller.

## 3. Nothing is shown that hardware has not said

Each displayed value carries one of four provenances, and the interface must make it visible:

| Provenance | Meaning | May render green |
| --- | --- | --- |
| Proven | a read-only check succeeded against this exact target | yes, always with its timestamp |
| Saved plan | stored in the lab profile, never verified | no |
| Suggested | the app proposed it | no |
| Blank | nothing knows it | no |

- A device that has never answered has **no** model, **no** bay count, and **no** drives.
  Do not infer them from the name, the model string, or a sibling device.
- Green is reserved for current proof bound to the exact target. Evidence is per device;
  one device's probe never colours another's state.
- Stale proof is not proof. When it ages out, it stops being green.

## 4. A server the app has never met can still be added

The starting condition is a rack of machines the app knows nothing about. Adding one takes
only what an operator can read off the machine:

1. A name they choose.
2. The address it currently answers on (front display, or the DHCP lease table).
3. The iLO UID / username and password (the pull-out tag).

Saving records it. Nothing connects until an explicit **first contact** is run, and that is
read-only. Until it succeeds, the device stays in the build as planned, with everything about
it unknown.

## 5. First contact fails in specific ways, and each is said plainly

Use the backend's own classifications (`_endpoint_message`,
`_classify_collection_access_response` in `app/backend/app/providers/ilo_redfish.py`). Never
collapse them into a generic failure — the fixes are different:

- **Nothing answered** — off, wrong network, or the address moved.
- **Not an iLO** — a web server answered; usually the OS address or another device.
- **Sign-in refused** — it is an iLO, the credentials were wrong.
- **No inventory permission** — the credentials *worked*; the account lacks the role.
  This is not a password problem and must not be worded as one.
- **Certificate not trusted** — expected for a self-signed lab iLO.
- **Older iLO** — real iLO, pre-Redfish; cannot be inventoried or be a cluster member.
- **Target mismatch** — it answered, but its fingerprint is a device already in the rack.

Every failure states what was tried, what it means, what to check in order, and leaves the
saved details editable. A failure never invents a model, a bay count, or a drive layout.

## 6. Blocked is visible, with its reason

- An option that cannot be chosen stays on screen, disabled, with the reason beside it.
  Never hide it, never fail silently.
- Reasons name the specific shortfall: "vSAN needs 3 hosts — you have 2", not "invalid".
- Save is disabled while any blocker stands.

## 7. Order that cannot be reordered

For the first standalone Windows kit, firmware compatibility assessment and approved
updates precede ESXi installation. Verify switch/network readiness, create the boot
mirror, install ESXi, verify the VM datastore and port group, then deploy and verify
the Windows OVF/OVA. vCenter and vSAN are not required for this path. The scope and
remaining evidence contracts are in `standalone-windows-kit.md`.

The guided steps, per server, are: Add equipment → Network settings → Connect → Firmware →
Disks → RAID → Prepare ESXi → (Windows / vCenter). Decided 2026-09-29 with Steve:

- **Connect** is first contact and a read of each server (model, firmware, disks, existing
  RAID). It writes nothing and holds no storage decisions.
- **Firmware** comes before any disk or RAID change: newer controller firmware handles
  sanitize and erased-drive return better, drive firmware is safest to update while drives are
  unconfigured, and any array disturbed by an update is about to be rebuilt anyway. Erase
  first only when data must be destroyed before anything else, which is a separate choice.
- **Disks** classifies each server from its read and asks only when there is a real decision:
  new (no RAID, all disks eligible) passes with no button; old RAID or data offers erase
  securely / clear RAID only / keep, with no default; erased disks offer re-enable; a failed
  drive is blocked with its bay. The erase method per drive comes from its media type.
- **RAID** builds the saved layout. A server's RAID waits until its own Disks decision is
  resolved; an old array must be cleared in Disks first.
- **Several servers** move through these independently; order is enforced within each server
  only. A batch action is one review listing every server, disk, method and estimate with one
  typed phrase, then runs and verifies each server separately; one failure never stops the
  others and nothing is retried automatically. Cluster steps (vCenter, vSAN) wait for every
  member host's ESXi to be verified; a standalone server waits for no one.

Diagnosing hardware alerts is read-only and can happen at any point.
Prepare ESXi contains hypervisor configuration and installer actions only. The
OS mirror, storage array and optional dedicated hot spare are saved together;
spare capacity is never counted as boot or datastore capacity. A hot spare is
not a backup copy of data. Moving the planner does not waive firmware review or
the separate confirmations required to execute storage changes.
Unconfigured is an assignment state, not necessarily a health fault. Drive/RAID
planning may happen before firmware review, but creating/deleting RAID is separate
from diagnosis and is not a repair for physical faults. Use HPE SUM to establish
firmware dependencies before the normal RAID-create/ESXi path; a firmware-based
repair needs its own justified vendor recovery plan. Acknowledging a health alert
records awareness only, never health clearance or permission to execute.

Empty or unidentified drive records are occupancy/identification warnings, with
the original hardware status preserved. They are never RAID candidates. Known
failed physical drives remain critical. Removing obsolete RAID metadata is a
separately reviewed destructive recovery operation, not a repair claim; it may
be prepared before firmware work. New array creation still requires review of
firmware prerequisites. Preview, explicit confirmation, pending state and verified
readback remain distinct; a missing response never authorizes an automatic retry.

vSAN needs vCenter; vCenter is a VM that needs somewhere to live. Therefore:

1. Carve the boot mirror on each host (destructive — preview, then confirm).
2. Install ESXi onto the mirror.
3. Deploy vCenter to **local** storage, because vSAN does not exist yet.
4. Form the cluster and enable vSAN, claiming the passthrough drives.
5. Optionally migrate vCenter onto vSAN.

Each step unlocks only when the previous one is proven.

## 8. Writes stay guarded

For local-lab iLO firmware updates, the operator interaction is one Yes/No
confirmation naming the server and version. No typed phrase, separate access
approval, or manual preflight/review step is required. Yes authorizes firmware-only
access and the named update; preparation and review run internally. Hardware-health
findings are advisory for this action, not clearance for storage operations.
Exact target/package validation, active-operation conflicts and duplicate-send
accounting remain internal. An uncertain attempt may be explicitly dismissed with
Yes/No, without a fresh readback or waiting period; this records an unknown outcome,
does not stop an update on the iLO, and never resends the previous attempt.
This specific user-approved lab interaction supersedes typed/multi-step approval
requirements for iLO firmware only.

Planning writes nothing. Every hardware change is previewed first, shows the exact command,
and requires a separate confirmation. This holds on the flow page, the dashboard, and
anywhere else — read-only is the default everywhere.

## 9. Complete workflows inside the app

Operators must be able to complete supported build and recovery workflows in the
app without editing JSON, environment variables, or running shell commands.
Every unmet prerequisite must offer an in-app next action or explain a genuine
external requirement such as replacing failed hardware or obtaining vendor
support evidence. Permission changes must be explicit, scoped, durable and
audited. Approval is not proof of hardware capability. This rule never removes
destructive confirmations, target verification or completion evidence.

Action labels must distinguish preparation from execution. A confirmation opener
names the intended action; the final command names what it sends. After a write,
replace the completed form with visible sending, accepted/pending, uncertain, or
failed feedback. Keep the next guarded action (including power-on) in that flow.
Staging is not completion, and neither acceptance nor a timeout authorizes retry.

Storage results occupy a prominent, independent section above diagnostics and
erase controls. Show the operation name, outcome, recorded evidence time, and
submission/power-on/verification stages. Use text and icons as well as color.
A verified deletion leads to erase preparation, verified erasure to RAID
planning, and verified creation to ESXi setup. Those links open the next
workflow, never perform destructive operations themselves. Technical messages
remain available under operation details; unresolved errors stay visible.

Do not duplicate a next-step action with a second full workflow section. When
the verified storage result offers erase preparation, that is the sole erase
entry point; its dialog owns the warnings, controls and report. Keep a standalone
entry only when the current result does not already offer that action.
