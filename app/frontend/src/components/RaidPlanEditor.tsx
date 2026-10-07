import { useEffect, useRef, useState } from "react";
import { HardDrive, RotateCcw, Sparkles, X } from "lucide-react";
import { api, type DiskPreparation as Inventory } from "../api";
import { bayNumber, bayOrder, gapBays, size } from "./bays";

/*
 * RAID plan editor: shows what is on the disks now and the saved plan, then lets the operator
 * paint each bay with a job (boot mirror, datastore, spare, not used). It reads the disks when it
 * opens and again before saving if that read is getting old, so editing is never locked behind a
 * five-minute window. Saving writes the plan only; no disk changes.
 */

type Role = "boot" | "data" | "spare" | "none";
type Level = "RAID5" | "RAID6" | "RAID10" | "RAID1";
type Drive = Inventory["drives"][number];
const ROLES: Array<{ id: Role; label: string; hint: string }> = [
  { id: "boot", label: "Boot mirror", hint: "2 matching disks · ESXi" },
  { id: "data", label: "Datastore", hint: "your VMs" },
  { id: "spare", label: "Spare", hint: "1 disk · takes over on failure" },
  { id: "none", label: "Not used", hint: "left empty" },
];
const LEVELS: Array<{ id: Level; label: string; min: string }> = [
  { id: "RAID5", label: "RAID 5", min: "3+ disks · survives 1 failure" },
  { id: "RAID6", label: "RAID 6", min: "4+ disks · survives 2 failures" },
  { id: "RAID10", label: "RAID 10", min: "even 4+ disks · fastest" },
  { id: "RAID1", label: "RAID 1", min: "exactly 2 disks · mirror" },
];
// A plan read older than this is refreshed (read-only) before saving; the server accepts five minutes.
const REFRESH_AFTER_MS = 4 * 60 * 1000;
const kind = (drive: Drive) => `${drive.capacity_bytes}:${drive.media || ""}`;

function rolesFromPlan(view: Inventory): Record<string, Role> {
  const roles: Record<string, Role> = {};
  for (const volume of view.saved_intent.volumes) {
    for (const bay of volume.drive_bays) roles[bay] = volume.bootable ? "boot" : "data";
    for (const bay of volume.spare_bays ?? []) roles[bay] = "spare";
  }
  return roles;
}

/** Two smallest matching disks for boot; the largest matching group for the datastore; one spare when 4+. */
export function recommendedRoles(drives: Drive[]): { roles: Record<string, Role>; level: Level } {
  const usable = drives.filter(drive => drive.eligible);
  const groups = new Map<string, Drive[]>();
  for (const drive of usable) groups.set(kind(drive), [...(groups.get(kind(drive)) ?? []), drive]);
  const sorted = [...groups.values()].map(group => group.sort((a, b) => bayOrder(a.location) - bayOrder(b.location)));
  const roles: Record<string, Role> = {};
  const bootGroup = sorted.filter(group => group.length >= 2).sort((a, b) => a[0].capacity_bytes - b[0].capacity_bytes)[0];
  if (!bootGroup) return { roles, level: "RAID5" };
  bootGroup.slice(0, 2).forEach(drive => { roles[drive.location] = "boot"; });
  const rest = sorted.map(group => group.filter(drive => !roles[drive.location])).filter(group => group.length >= 2)
    .sort((a, b) => b.length - a.length || b[0].capacity_bytes - a[0].capacity_bytes)[0] ?? [];
  if (rest.length >= 4) { rest.slice(0, -1).forEach(drive => { roles[drive.location] = "data"; }); roles[rest[rest.length - 1].location] = "spare"; return { roles, level: "RAID5" }; }
  rest.forEach(drive => { roles[drive.location] = "data"; });
  return { roles, level: rest.length === 2 ? "RAID1" : "RAID5" };
}

function usable(level: Level, drives: Drive[]) {
  if (!drives.length) return 0;
  const each = Math.min(...drives.map(drive => drive.capacity_bytes)), n = drives.length;
  return level === "RAID5" ? (n - 1) * each : level === "RAID6" ? (n - 2) * each : level === "RAID10" ? (n / 2) * each : each;
}

/** Plain reasons this plan can't be saved yet; empty when it can. */
export function planProblems(drives: Drive[], roles: Record<string, Role>, level: Level) {
  const pick = (role: Role) => drives.filter(drive => roles[drive.location] === role);
  const boot = pick("boot"), data = pick("data"), spare = pick("spare");
  const problems: string[] = [];
  const matched = (group: Drive[]) => new Set(group.map(kind)).size <= 1;
  if (boot.length !== 2) problems.push(`Pick exactly 2 disks for the boot mirror (${boot.length} picked).`);
  else if (!matched(boot)) problems.push("The two boot mirror disks must be the same size and type.");
  if (data.length) {
    if (!matched(data)) problems.push("Datastore disks must all be the same size and type.");
    const n = data.length;
    const ok = level === "RAID1" ? n === 2 : level === "RAID5" ? n >= 3 : level === "RAID6" ? n >= 4 : n >= 4 && n % 2 === 0;
    if (!ok) problems.push(`${LEVELS.find(item => item.id === level)!.label} needs ${LEVELS.find(item => item.id === level)!.min.split(" · ")[0]}; you picked ${n}.`);
  }
  if (spare.length > 1) problems.push("Only one spare is supported.");
  if (spare.length === 1) {
    const protectedGroup = data.length ? data : boot;
    if (!protectedGroup.length || spare[0].media !== protectedGroup[0].media || spare[0].capacity_bytes < Math.max(...protectedGroup.map(drive => drive.capacity_bytes)))
      problems.push(`The spare must be the same type and at least as big as the ${data.length ? "datastore" : "boot mirror"} disks.`);
  }
  const unusable = [...boot, ...data, ...spare].filter(drive => !drive.eligible);
  if (unusable.length) problems.push(`Bay ${unusable.map(drive => bayNumber(drive.location)).join(", ")} ${unusable.length === 1 ? "isn't" : "aren't"} ready (erased, failed or not healthy).`);
  return problems;
}

function describeVolumes(view: Inventory) {
  if (!view.volumes.length) return "No RAID on the disks.";
  return view.volumes.map(volume => `${volume.raid.replace(/^RAID/, "RAID ")}${volume.bays?.length ? ` on bay ${volume.bays.map(bayNumber).join(", ")}` : ""}${volume.capacity_bytes ? ` (${size(volume.capacity_bytes)})` : ""}`).join(" · ");
}
function describePlan(view: Inventory) {
  const volumes = view.saved_intent.volumes;
  if (!volumes.length) return "No plan saved yet.";
  return volumes.map(volume => `${volume.bootable ? "Boot mirror" : `Datastore ${volume.raid_level.replace(/^RAID/, "RAID ")}`} bay ${volume.drive_bays.map(bayNumber).join(", ")}${volume.spare_bays?.length ? ` + spare bay ${volume.spare_bays.map(bayNumber).join(", ")}` : ""}`).join(" · ");
}

export function RaidPlanEditor({ profileId, deviceId, deviceName, onClose }: {
  profileId: string; deviceId: string; deviceName: string; onClose: (changed: boolean) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const live = useRef(true);
  const [view, setView] = useState<Inventory | null>(null);
  const [readAt, setReadAt] = useState(0);
  const [roles, setRoles] = useState<Record<string, Role>>({});
  const [level, setLevel] = useState<Level>("RAID5");
  const [brush, setBrush] = useState<Role>("boot");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  // One read per opening, even when React runs this effect twice in development.
  const started = useRef(false);
  useEffect(() => {
    live.current = true;
    if (!dialog.current?.open) dialog.current?.showModal();
    if (!started.current) { started.current = true; void read(true); }
    return () => { live.current = false; };
  }, []);

  // Read-only: ask the iLO for the disks now, then load the view (with the saved plan).
  async function read(initial = false) {
    setBusy("Reading the disks…"); setError("");
    try {
      const probe = await api.probeProvider("ilo-redfish", deviceId);
      const next = await api.diskPreparation(profileId, deviceId);
      if (!live.current) return null;
      setView(next);
      if (probe.status !== "ok" || !next.current) setError(`Couldn't read the disks just now${probe.message ? `: ${probe.message}` : "."} Showing the last read; try again to save.`);
      else setReadAt(Date.now());
      if (initial) {
        const saved = rolesFromPlan(next);
        setRoles(saved);
        setLevel((next.saved_intent.volumes.find(volume => !volume.bootable)?.raid_level as Level) || "RAID5");
      }
      return next;
    } catch (err) { if (live.current) setError(err instanceof Error ? err.message : String(err)); return null; }
    finally { if (live.current) setBusy(""); }
  }

  const drives = view ? (view.drives.length ? view.drives : view.last_read?.drives ?? []) : [];
  const byBay = new Map(drives.map(drive => [drive.location, drive]));
  const bays = [...drives.map(drive => drive.location), ...gapBays(drives.map(drive => drive.location))].sort((a, b) => bayOrder(a) - bayOrder(b));
  const problems = view ? planProblems(drives, roles, level) : [];
  const dataDrives = drives.filter(drive => roles[drive.location] === "data");
  const bootDrives = drives.filter(drive => roles[drive.location] === "boot");
  const spareDrive = drives.find(drive => roles[drive.location] === "spare");
  const savedRoles = view ? rolesFromPlan(view) : {};
  const savedLevel = view?.saved_intent.volumes.find(volume => !volume.bootable)?.raid_level || "RAID5";
  const changed = JSON.stringify(Object.entries(roles).filter(([, role]) => role !== "none").sort()) !== JSON.stringify(Object.entries(savedRoles).sort())
    || (dataDrives.length > 0 && level !== savedLevel);

  function paint(bay: string) {
    const drive = byBay.get(bay);
    if (!drive) return;
   
    setRoles(current => {
      const next = { ...current };
      const role = next[bay] === brush ? "none" : brush;
      // Boot keeps two and spare keeps one: the oldest pick gives way to the new one.
      if (role === "boot" || role === "spare") {
        const limit = role === "boot" ? 2 : 1;
        const same = drives.filter(item => next[item.location] === role && item.location !== bay).map(item => item.location);
        while (same.length >= limit) next[same.shift()!] = "none";
      }
      next[bay] = role;
      return next;
    });
  }

  async function save() {
    if (!view || problems.length) return;
    setBusy("Saving the plan…"); setError("");
    try {
      let current = view;
      if (!current.current || Date.now() - readAt > REFRESH_AFTER_MS) {
        const fresh = await read();
        if (!fresh || !fresh.current) return;
        current = fresh;
        setBusy("Saving the plan…");
      }
      const id = (bay: string) => { const drive = current.drives.find(item => item.location === bay); if (!drive) throw new Error(`Bay ${bayNumber(bay)} wasn't in the latest read. Try again.`); return drive.id; };
      const pick = (role: Role) => Object.entries(roles).filter(([, value]) => value === role).map(([bay]) => bay).sort((a, b) => bayOrder(a) - bayOrder(b));
      const hasData = pick("data").length > 0;
      await api.saveDiskPreparation(profileId, deviceId, {
        inventory_token: current.inventory_token, boot_drive_ids: pick("boot").map(id), data_drive_ids: pick("data").map(id), data_raid: level,
        spare_drive_ids: pick("spare").map(id), spare_for: hasData ? "data" : "boot",
        // Existing RAID is only marked for replacement in the plan; the disks change only when wiped or built.
        remove_existing_volumes: current.volumes.length > 0, data_loss_reviewed: current.volumes.length > 0,
      });
      if (live.current) onClose(true);
    } catch (err) { if (live.current) setError(err instanceof Error ? err.message : String(err)); }
    finally { if (live.current) setBusy(""); }
  }

  const reset = () => { if (!view) return; setRoles(rolesFromPlan(view)); setLevel(savedLevel as Level); };
  const recommend = () => { const next = recommendedRoles(drives); setRoles(next.roles); setLevel(next.level); };

  return <dialog ref={dialog} className="inst rp" aria-label={`RAID plan on ${deviceName}`} onCancel={event => { event.preventDefault(); if (!busy) onClose(false); }}>
    <header className="inst-h">
      <span className="inst-icon"><HardDrive size={22} aria-hidden="true" /></span>
      <div><h2>RAID plan</h2><p>{deviceName}</p></div>
      <button type="button" aria-label="Close RAID plan" disabled={!!busy} onClick={() => onClose(false)}><X size={20} /></button>
    </header>
    <div className="rp-body">
      {view && <section className="rp-now" aria-label="Current setup">
        <div><span>On the disks now</span><strong>{describeVolumes(view)}</strong></div>
        <div><span>Saved plan</span><strong>{describePlan(view)}</strong></div>
      </section>}

      {!view && busy && <p className="inst-busy" role="status">{busy}</p>}
      {view && drives.length > 0 && <>
        <div className="rp-tools">
          <div className="rp-brushes" role="radiogroup" aria-label="Pick a job, then click disks">
            {ROLES.map(role => <button key={role.id} type="button" role="radio" aria-checked={brush === role.id} className={`rp-brush rp-${role.id}`} onClick={() => setBrush(role.id)}>
              <i aria-hidden="true" /><span><b>{role.label}</b><small>{role.hint}</small></span></button>)}
          </div>
          <div className="rp-quick">
            <button type="button" className="fw-link" onClick={recommend}><Sparkles size={15} aria-hidden="true" />Use recommended</button>
            {view.saved_intent.volumes.length > 0 && <button type="button" className="fw-link" onClick={reset}><RotateCcw size={15} aria-hidden="true" />Back to saved plan</button>}
          </div>
        </div>
        <p className="rp-how">Pick a job above, then click the disks for it. Click a disk again to take the job off.</p>

        <div className="dr-chassis"><div className="dr-cage" role="list" aria-label="Drive bays">
          {bays.map(bay => {
            const drive = byBay.get(bay);
            const role = drive ? roles[bay] ?? "none" : "none";
            const inRaid = view.volumes.find(volume => volume.bays?.includes(bay));
            const label = `Bay ${bayNumber(bay)}: ${drive ? `${size(drive.capacity_bytes)} ${drive.media || ""}`.trim() : "empty"}, ${role === "none" ? "not used" : ROLES.find(item => item.id === role)!.label}`;
            return <div role="listitem" key={bay} className={`dr-bay ${drive ? (drive.eligible ? "dr-ready" : "dr-other") : "dr-empty"}`}>
              <span className="dr-num">{bayNumber(bay)}</span>
              <button type="button" className={`dr-caddy rp-caddy rp-on-${role}`} aria-label={label} aria-pressed={role !== "none"} disabled={!drive || !!busy} onClick={() => paint(bay)}>
                <span className="dr-led" aria-hidden="true" /><span className="dr-grip" aria-hidden="true" />
                <span className="dr-size">{drive ? size(drive.capacity_bytes) : "—"}</span>
                <span className="dr-media">{drive ? drive.media || "" : "no disk"}</span>
              </button>
              <span className="dr-state">{!drive ? "Empty" : !drive.eligible ? "Not ready" : inRaid ? `Now: ${inRaid.raid.replace(/^RAID/, "RAID ")}` : "Now: free"}</span>
              <span className={`dr-role ${role !== "none" ? `dr-role-${role}` : ""}`}>{role === "none" ? "Not used" : ROLES.find(item => item.id === role)!.label}</span>
            </div>;
          })}
        </div></div>

        <div className="rp-result">
          <div className="rp-sum rp-boot"><span>Boot mirror</span><strong>{bootDrives.length === 2 ? `RAID 1 · ${size(bootDrives[0].capacity_bytes)}` : `${bootDrives.length} of 2 disks`}</strong></div>
          <div className="rp-sum rp-data"><span>Datastore</span>
            {dataDrives.length ? <><label><span className="sr-only">Datastore RAID level</span><select aria-label="Datastore RAID level" value={level} disabled={!!busy} onChange={event => { setLevel(event.target.value as Level); }}>
              {LEVELS.map(item => <option key={item.id} value={item.id}>{item.label} — {item.min}</option>)}</select></label>
              <strong>{dataDrives.length} disks · about {size(usable(level, dataDrives))} usable</strong></> : <strong>None (optional)</strong>}</div>
          <div className="rp-sum rp-spare"><span>Spare</span><strong>{spareDrive ? `Bay ${bayNumber(spareDrive.location)} · protects the ${dataDrives.length ? "datastore" : "boot mirror"}` : "None (optional)"}</strong></div>
        </div>

        {problems.length > 0 && <ul className="rp-problems" role="alert">{problems.map(item => <li key={item}>{item}</li>)}</ul>}
        {!problems.length && view.volumes.length > 0 && changed && <p className="rp-note">The disks have RAID on them now. Saving marks it to be replaced; nothing changes on the disks until you wipe them or build RAID.</p>}
      </>}
      {view && !drives.length && !busy && <p className="fw-stop" role="alert">No disks were reported by this server. Check the connection, then try again.</p>}
      {busy && view && <p className="inst-busy" role="status">{busy}</p>}
      {error && <p className="fw-stop" role="alert">{error}</p>}
    </div>
    <footer className="inst-f">
      <button type="button" className="secondary-action" disabled={!!busy} onClick={() => onClose(false)}>Cancel</button>
      {error && <button type="button" className="secondary-action" disabled={!!busy} onClick={() => void read()}>Read disks again</button>}
      <span className="inst-grow" />
      <button type="button" className="primary-action inst-next" disabled={!!busy || !view || !drives.length || problems.length > 0 || !changed} onClick={() => void save()}>{changed ? "Save plan" : "No changes"}</button>
    </footer>
  </dialog>;
}
