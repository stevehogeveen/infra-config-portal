import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { localRaidInventoryBays } from "../operatorPages";
import type { LocalRaidInventoryBay } from "../operatorPages";
import type { HpeRaidIntent, HpeRaidVolumeIntent, HpeStorageDiscovery } from "../types";

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

export function DriveAllocationPanel({
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

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextDiscovery, nextIntent] = await Promise.all([
        api.hpeStorageDiscovery(deviceId),
        api.hpeRaidIntent(deviceId).catch(() => null)
      ]);
      setDiscovery(nextDiscovery);
      setIntent(nextIntent);
      setAllocation(allocationFromIntent(localRaidInventoryBays(nextDiscovery), nextIntent));
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

  async function save() {
    setSaving(true);
    setError("");
    setSaved("");
    try {
      await api.saveHpeRaidIntent(deviceId, {
        controller_ref: intent?.controller_ref ?? null,
        wipe_existing_logical_drives: intent?.wipe_existing_logical_drives ?? false,
        volumes: buildVolumes(allocation, intent?.volumes ?? []),
        notes: intent?.notes ?? null
      });
      setSaved("Plan saved. Nothing has been sent to the controller.");
      await load();
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
      </section>
    );
  }

  return (
    <section aria-label={`Drive allocation for ${deviceName}`} className="drive-alloc">
      <header className="drive-alloc-head">
        <h3>{deviceName} &middot; drive allocation</h3>
        <p>
          {bays.length} bays read from the controller
          {discovery?.last_probe_time ? ` · inventory ${new Date(discovery.last_probe_time).toLocaleTimeString()}` : ""}
        </p>
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
              onClick={() => setAllocation((current) => ({ ...current, [bay.bay]: role }))}
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

      <footer className="drive-alloc-foot">
        <span className="drive-alloc-note">
          Saving records the plan only. Creating the mirror erases those bays, and that stays a
          separate, confirmed step.
        </span>
        <button className="rack-action" disabled={saving || loading} onClick={() => void load()} type="button">
          Reset
        </button>
        <button
          className="rack-action is-primary"
          disabled={saving || loading || blockers.length > 0}
          onClick={() => void save()}
          type="button"
        >
          {saving ? "Saving…" : blockers.length ? `${blockers.length} to fix` : "Save this plan"}
        </button>
      </footer>
    </section>
  );
}
