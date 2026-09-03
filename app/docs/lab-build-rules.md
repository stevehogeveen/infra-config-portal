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

vSAN needs vCenter; vCenter is a VM that needs somewhere to live. Therefore:

1. Carve the boot mirror on each host (destructive — preview, then confirm).
2. Install ESXi onto the mirror.
3. Deploy vCenter to **local** storage, because vSAN does not exist yet.
4. Form the cluster and enable vSAN, claiming the passthrough drives.
5. Optionally migrate vCenter onto vSAN.

Each step unlocks only when the previous one is proven.

## 8. Writes stay guarded

Planning writes nothing. Every hardware change is previewed first, shows the exact command,
and requires a separate confirmation. This holds on the flow page, the dashboard, and
anywhere else — read-only is the default everywhere.
