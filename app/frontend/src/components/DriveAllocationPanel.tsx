import { useCallback, useEffect, useMemo, useState } from "react";
import { Eye, RotateCcw, Save, ShieldAlert } from "lucide-react";
import { api } from "../api";
import { localRaidInventoryBays } from "../operatorPages";
import type { LocalRaidInventoryBay } from "../operatorPages";
import type { HpeRaidIntent, HpeRaidPlanPreview, HpeRaidVolumeIntent, HpeStorageDiscovery, IloAccessSettings } from "../types";

// Every bay has exactly one job (app/docs/lab-build-rules.md section 2).
//
// Boot and Local become RAID volumes in the intent. vSAN is the absence of a
// volume: vSAN consumes raw drives, so a bay assigned to vSAN is deliberately
// left out of every volume and the controller passes it through untouched.
// That absence is a decision, so this panel names it rather than leaving those
// bays looking merely unassigned.
export type BayRole = "boot" | "vsan" | "local";

export const BOOT_VOLUME_NAME = "ESXi-OS";
export const LOCAL_VOLUME_NAME = "VM-Datastore";
const BOOT_PAIR_SIZE = 2;

export type DriveAllocation = Record<string, BayRole>;

type RoleCounts = Record<BayRole, number>;

export type AllocationRule = {
  id: string;
  ok: boolean;
  text: string;
  detail: string | null;
};

export function countRoles(allocation: DriveAllocation): RoleCounts {
  const counts: RoleCounts = { boot: 0, vsan: 0, local: 0 };
  Object.values(allocation).forEach((role) => {
    counts[role] += 1;
  });
  return counts;
}

// The boot pair is a RAID 1 mirror, so it is exactly two drives: never one,
// which would take the host down with it, and never three.
export function allocationRules(allocation: DriveAllocation, bayCount: number): AllocationRule[] {
  const counts = countRoles(allocation);
  const assigned = counts.boot + counts.vsan + counts.local;
  return [
    {
      id: "boot-pair",
      ok: counts.boot === BOOT_PAIR_SIZE,
      text: "ESXi boot pair is exactly two drives",
      detail:
        counts.boot === BOOT_PAIR_SIZE
          ? "Mirrored, so the host survives losing one"
          : counts.boot < BOOT_PAIR_SIZE
            ? `${BOOT_PAIR_SIZE - counts.boot} more bay needed for the mirror`
            : `${counts.boot} assigned, and a mirror takes two`
    },
    {
      id: "within-bays",
      ok: assigned <= bayCount,
      text: "Roles stay within the bays the controller reported",
      detail: `${assigned} of ${bayCount} bays assigned`
    },
    {
      id: "vsan-contribution",
      ok: counts.vsan > 0,
      text: "At least one drive left raw for vSAN",
      detail:
        counts.vsan > 0
          ? `${counts.vsan} passed through to the cluster`
          : "A host with no raw drives cannot join a vSAN cluster"
    }
  ];
}

// Mirrors the thresholds the backend recommender uses in hpe_raid.py, so a plan
// saved here previews without the planner rejecting the level outright.
export function localRaidLevel(driveCount: number): string {
  if (driveCount >= 6) return "RAID6";
  if (driveCount >= 3) return "RAID5";
  if (driveCount === 2) return "RAID1";
  return "RAID0";
}

// Real HPE bay ids are port:box:bay, e.g. "1I:1:1" through "2I:1:8" -- not plain
// numbers. Sort on the trailing bay number so 2I:1:5 follows 1I:1:4, and fall
// back to a plain compare for controllers that report something else.
export function bayNumber(bay: string): number {
  const tail = bay.split(":").pop() ?? bay;
  const value = Number(tail);
  return Number.isFinite(value) ? value : Number.NaN;
}

function sortBays(bays: string[]): string[] {
  return [...bays].sort((a, b) => {
    const left = bayNumber(a);
    const right = bayNumber(b);
    if (Number.isFinite(left) && Number.isFinite(right) && left !== right) return left - right;
    return a.localeCompare(b);
  });
}

// Boot and Local become volumes; vSAN bays are intentionally omitted so the
// controller leaves them raw.
export function buildVolumes(
  allocation: DriveAllocation,
  existing: HpeRaidVolumeIntent[]
): HpeRaidVolumeIntent[] {
  const baysFor = (role: BayRole) =>
    sortBays(
      Object.entries(allocation)
        .filter(([, value]) => value === role)
        .map(([bay]) => bay)
    );
  const previous = (name: string) => existing.find((volume) => volume.name === name);
  const base = { spare_bays: [] as string[], spare_rebuild_mode: null, size_policy: "max" };
  const volumes: HpeRaidVolumeIntent[] = [];

  const bootBays = baysFor("boot");
  if (bootBays.length) {
    volumes.push({
      ...base,
      ...previous(BOOT_VOLUME_NAME),
      spare_bays: [],
      spare_rebuild_mode: null,
      name: BOOT_VOLUME_NAME,
      purpose: "ESXi boot",
      raid_level: "RAID1",
      drive_bays: bootBays,
      bootable: true
    });
  }

  const localBays = baysFor("local");
  if (localBays.length) {
    volumes.push({
      ...base,
      ...previous(LOCAL_VOLUME_NAME),
      spare_bays: [],
      spare_rebuild_mode: null,
      name: LOCAL_VOLUME_NAME,
      purpose: "Local VM datastore",
      raid_level: localRaidLevel(localBays.length),
      drive_bays: localBays,
      bootable: false
    });
  }

  return volumes;
}

// Read a saved intent back into per-bay roles. Anything no volume claims is
// raw, which is exactly what vSAN needs.
export function allocationFromIntent(
  bays: LocalRaidInventoryBay[],
  intent: HpeRaidIntent | null
): DriveAllocation {
  const allocation: DriveAllocation = {};
  bays.forEach((bay) => {
    allocation[bay.bay] = "vsan";
  });
  (intent?.volumes ?? []).forEach((volume) => {
    const role: BayRole = volume.bootable || volume.name === BOOT_VOLUME_NAME ? "boot" : "local";
    volume.drive_bays.forEach((bay) => {
      if (bay in allocation) allocation[bay] = role;
    });
  });
  return allocation;
}

const ROLE_LABEL: Record<BayRole, string> = {
  boot: "ESXi boot",
  vsan: "vSAN",
  local: "Local"
};

const ROLE_HINT: Record<BayRole, string> = {
  boot: "The mirrored pair the hypervisor boots from. It never joins vSAN.",
  vsan: "Left raw so the cluster can claim it.",
  local: "A RAID volume on this server alone. A VM stored here dies with its host."
};

const ROLES: BayRole[] = ["boot", "vsan", "local"];

export function DriveAllocationPanel(props: {
  deviceId: string;
  deviceName: string;
  currentHost?: string | null;
  onSaved?: () => void;
}) {
  return <DeviceDriveAllocationPanel key={JSON.stringify([props.deviceId, props.currentHost])} {...props} />;
}

function accessSignature(access: IloAccessSettings): string {
  return JSON.stringify([access.device_id, access.host, access.updated_at, access.verify_tls]);
}

function intentSignature(intent: HpeRaidIntent): string {
  return JSON.stringify([
    intent.device_id, intent.controller_ref, intent.wipe_existing_logical_drives,
    intent.volumes.map((volume) => [
      volume.name, volume.purpose, volume.raid_level, volume.drive_bays,
      volume.spare_bays, volume.spare_rebuild_mode, volume.size_policy, volume.bootable
    ]), intent.notes
  ]);
}

function DeviceDriveAllocationPanel({
  deviceId,
  deviceName,
  onSaved
}: {
  deviceId: string;
  deviceName: string;
  onSaved?: () => void;
}) {
  const [discovery, setDiscovery] = useState<HpeStorageDiscovery | null>(null);
  const [intent, setIntent] = useState<HpeRaidIntent | null>(null);
  const [allocation, setAllocation] = useState<DriveAllocation>({});
  const [role, setRole] = useState<BayRole>("boot");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [dirty, setDirty] = useState(false);
  const [preview, setPreview] = useState<HpeRaidPlanPreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [access, setAccess] = useState<IloAccessSettings | null>(null);
  const busy = loading || saving || previewing;

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    setPreview(null);
    setDiscovery(null);
    setIntent(null);
    setAllocation({});
    setAccess(null);
    try {
      const before = await api.iloAccessSettings(deviceId);
      const [nextDiscovery, nextIntent] = await Promise.all([
        api.hpeStorageDiscovery(deviceId),
        api.hpeRaidIntent(deviceId)
      ]);
      const after = await api.iloAccessSettings(deviceId);
      if (!before.host || before.device_id !== deviceId || accessSignature(before) !== accessSignature(after)) {
        throw new Error("Device access changed or has no address. Reload inventory from the current address.");
      }
      if (nextIntent.device_id !== deviceId) throw new Error("Saved plan belongs to a different device.");
      setDiscovery(nextDiscovery);
      setAccess(after);
      setIntent(nextIntent);
      setAllocation(allocationFromIntent(localRaidInventoryBays(nextDiscovery), nextIntent));
      setDirty(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [deviceId]);

  useEffect(() => {
    void load();
  }, [load]);

  const bays = useMemo(() => localRaidInventoryBays(discovery), [discovery]);
  const counts = countRoles(allocation);
  const rules = allocationRules(allocation, bays.length);
  const blockers = rules.filter((rule) => !rule.ok);
  const unresolvedBays = (discovery?.physical_drives.length ?? 0) !== bays.length;

  async function requireCurrentAccess() {
    const current = await api.iloAccessSettings(deviceId);
    if (!access || accessSignature(current) !== accessSignature(access)) {
      setDiscovery(null);
      setIntent(null);
      setPreview(null);
      throw new Error("Device access changed. Reload inventory from the current address before continuing.");
    }
  }

  async function readPreview() {
    if (busy || dirty || !intent || blockers.length || unresolvedBays) return;
    setPreviewing(true);
    setPreview(null);
    setError("");
    try {
      await requireCurrentAccess();
      const next = await api.hpeRaidPlanPreview(deviceId);
      await requireCurrentAccess();
      if (intentSignature(next.desired_intent) !== intentSignature(intent)) {
        throw new Error("The saved plan changed. Reload it before reviewing the impact.");
      }
      setPreview(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPreviewing(false);
    }
  }

  async function save() {
    if (busy || !intent || blockers.length || unresolvedBays) return;
    setSaving(true);
    setError("");
    setSaved("");
    setPreview(null);
    try {
      await requireCurrentAccess();
      const nextIntent = await api.saveHpeRaidIntent(deviceId, {
        controller_ref: intent?.controller_ref ?? null,
        wipe_existing_logical_drives: intent?.wipe_existing_logical_drives ?? false,
        volumes: buildVolumes(allocation, intent?.volumes ?? []),
        notes: intent?.notes ?? null
      });
      await requireCurrentAccess();
      if (nextIntent.device_id !== deviceId) throw new Error("Saved plan belongs to a different device.");
      setIntent(nextIntent);
      setAllocation(allocationFromIntent(bays, nextIntent));
      setDirty(false);
      setSaved("Plan saved. Nothing has been sent to the controller.");
      onSaved?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  // Fail closed: with no current inventory there are no bays to divide up, and
  // this panel must never invent them.
  if (!loading && !discovery?.storage_inventory_available) {
    return (
      <section aria-label={`Drive allocation for ${deviceName}`} className="drive-alloc is-unknown">
        <h3>Bays unknown</h3>
        <p>
          {deviceName} has not reported a drive inventory. Run the read-only iLO storage read first:
          the bay count and every drive size come from the controller itself.
        </p>
        {discovery?.next_safe_action ? <p className="drive-alloc-next">{discovery.next_safe_action}</p> : null}
        {error ? <p className="drive-alloc-error">{error}</p> : null}
        <button className="rack-action" onClick={() => void load()} type="button">Retry inventory</button>
      </section>
    );
  }

  return (
    <section aria-label={`Drive allocation for ${deviceName}`} className="drive-alloc">
      <header className="drive-alloc-head">
        <h3>{deviceName} &middot; drive allocation</h3>
        {access?.host ? <p>Current saved address: {access.host}</p> : null}
        <p>
          {bays.length} bays read from the controller
          {discovery?.last_probe_time ? ` · inventory ${new Date(discovery.last_probe_time).toLocaleTimeString()}` : ""}
        </p>
        <p>{dirty ? "Unsaved plan" : intent?.volumes.length ? "Saved plan" : "Suggested allocation"} &middot; drive roles are not hardware proof</p>
      </header>

      <div aria-label="Role to assign" className="drive-alloc-roles" role="radiogroup">
        {ROLES.map((item) => (
          <button
            aria-checked={role === item}
            className={`drive-alloc-role is-${item} ${role === item ? "is-active" : ""}`}
            key={item}
            onClick={() => setRole(item)}
            role="radio"
            type="button"
          >
            <span className="drive-alloc-swatch" />
            {ROLE_LABEL[item]}
            <small>{counts[item]}</small>
          </button>
        ))}
      </div>
      <p className="drive-alloc-hint">{ROLE_HINT[role]}</p>

      {loading ? <p>Reading the drive inventory&hellip;</p> : null}

      <div className="drive-alloc-bays">
        {bays.map((bay) => {
          const assigned = allocation[bay.bay] ?? "vsan";
          return (
            <button
              className={`drive-alloc-bay is-${assigned}`}
              key={bay.bay}
              disabled={busy}
              onClick={() => {
                setAllocation((current) => ({ ...current, [bay.bay]: role }));
                setDirty(true);
                setPreview(null);
                setSaved("");
              }}
              title={`${bay.label} · ${bay.detail} · currently ${bay.currentLayout}`}
              type="button"
            >
              <span className="drive-alloc-bay-no" title={bay.bay}>
                {Number.isFinite(bayNumber(bay.bay)) ? `Bay ${bayNumber(bay.bay)}` : bay.bay}
              </span>
              <span className="drive-alloc-bay-bar" />
              <span className="drive-alloc-bay-role">{ROLE_LABEL[assigned]}</span>
              <span className="drive-alloc-bay-detail">{bay.detail}</span>
            </button>
          );
        })}
      </div>

      <ul className="drive-alloc-rules">
        {rules.map((rule) => (
          <li className={rule.ok ? "is-ok" : "is-blocked"} key={rule.id}>
            <span aria-hidden="true">{rule.ok ? "✓" : "!"}</span>
            <span>
              {rule.text}
              {rule.detail ? <small>{rule.detail}</small> : null}
            </span>
          </li>
        ))}
      </ul>

      {error ? <p className="drive-alloc-error">{error}</p> : null}
      {saved ? <p className="drive-alloc-saved">{saved}</p> : null}
      {unresolvedBays ? <p className="drive-alloc-error">Some drives have missing or duplicate bay IDs. Resolve storage discovery before saving or previewing.</p> : null}

      {preview ? (
        <section className="drive-alloc-preview" aria-label="RAID plan preview">
          <h3>Plan impact for {deviceName}</h3>
          <p>Saved plan &middot; {preview.status}. No controller write has run.</p>
          <dl>
            <div><dt>Controller</dt><dd>{preview.desired_intent.controller_ref || "Not selected"}</dd></div>
            <div><dt>Logical drives to delete</dt><dd>{String(preview.impact.logical_drives_to_delete ?? "Unknown")}</dd></div>
            <div><dt>Bays planned raw</dt><dd>{Array.isArray(preview.impact.physical_drives_not_selected) ? preview.impact.physical_drives_not_selected.join(", ") || "None" : "Unknown"}</dd></div>
          </dl>
          {preview.desired_intent.volumes.map((volume, index) => (
            <p key={index}><strong>{volume.name} &middot; {volume.raid_level}</strong><br />{volume.drive_bays.join(", ")}</p>
          ))}
          {preview.blockers.length ? <ul className="drive-alloc-error">{preview.blockers.map((message, index) => <li key={index}>{message}</li>)}</ul> : null}
          {preview.warnings.length ? <ul>{preview.warnings.map((message, index) => <li key={index}>{message}</li>)}</ul> : null}
          <p>{preview.next_safe_action}</p>
          <button className="rack-action" disabled type="button"><ShieldAlert size={15} /> Apply RAID plan</button>
          <p>The existing apply endpoint uses the default lab target. Applying from this panel is blocked until preview and confirmation are bound to this device.</p>
        </section>
      ) : null}

      <footer className="drive-alloc-foot">
        <span className="drive-alloc-note">
          Saving records the plan only. Creating the mirror erases those bays, and that stays a
          separate, confirmed step.
        </span>
        <button className="rack-action" title="Reload saved allocation" aria-label="Reload saved allocation" disabled={busy} onClick={() => { setSaved(""); void load(); }} type="button">
          <RotateCcw size={15} />
        </button>
        <button
          className="rack-action is-primary"
          disabled={busy || !intent || unresolvedBays || blockers.length > 0}
          onClick={() => void save()}
          type="button"
        >
          <Save size={15} /> {saving ? "Saving…" : blockers.length ? `${blockers.length} to fix` : "Save this plan"}
        </button>
        <button className="rack-action" disabled={busy || dirty || !intent || unresolvedBays || blockers.length > 0} onClick={() => void readPreview()} type="button">
          <Eye size={15} /> {previewing ? "Reading preview…" : "Preview saved plan"}
        </button>
        {dirty ? <span className="drive-alloc-note">Save the edited allocation before previewing.</span> : null}
      </footer>
    </section>
  );
}
