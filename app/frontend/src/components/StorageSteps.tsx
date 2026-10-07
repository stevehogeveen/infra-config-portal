import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, RefreshCw, Server, X } from "lucide-react";
import { api, type DiskPreparation as Inventory, type RaidOperationStatus } from "../api";
import type { RackPlan } from "./RackPlanner";
import { DiskPreparation } from "./DiskPreparation";
import { DiskReenableGuide, erasedBays } from "./DiskReenableGuide";
import { RaidInstaller } from "./RaidInstaller";
import { WipeInstaller } from "./WipeInstaller";
import { RaidPlanEditor } from "./RaidPlanEditor";
import { bayNumber, bayOrder, gapBays, size } from "./bays";
import { ProvenanceChip } from "./studio/ProvenanceChip";
import { useStudio } from "./studio/StudioContext";

/*
 * Disks & RAID: one card per server with a picture of its drive bays. Each bay shows what is in
 * it now (ready, in a RAID, erased, failed, empty) and what the saved plan will make it (boot
 * mirror, datastore, spare). One sentence says what to do and one button does it. The picture is
 * drawn from the saved read only; "Read disks" is a read-only check. Any change runs through the
 * existing guarded installers and guides.
 */

type ServerRow = { id: string; name: string; model: string; deviceId: string | null };
type Read = { state: "loading" } | { state: "error"; message: string } | { state: "ok"; view: Inventory; op: RaidOperationStatus | null };
type Drive = Inventory["drives"][number];
type Volume = Inventory["volumes"][number];

function useServers(profileId?: string) {
  const [servers, setServers] = useState<ServerRow[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setServers(null); setError("");
    if (!profileId) return;
    api.rackPlan(profileId).then((plan: RackPlan) => { if (active) setServers(plan.equipment.filter(item => item.kind === "server")
      .map(item => ({ id: item.id, name: item.name, model: item.model, deviceId: item.device_id ?? null }))); })
      .catch(err => { if (active) setError(err instanceof Error ? err.message : String(err)); });
    return () => { active = false; };
  }, [profileId]);
  return { servers, error };
}

function useInventories(profileId: string | undefined, servers: ServerRow[] | null, revision: number) {
  const [reads, setReads] = useState<Record<string, Read>>({});
  useEffect(() => {
    let active = true;
    if (!profileId || !servers) return;
    for (const server of servers) {
      if (!server.deviceId) continue;
      const id = server.deviceId;
      setReads(current => ({ ...current, [id]: current[id]?.state === "ok" ? current[id] : { state: "loading" } }));
      // The storage operation status says whether an erase or build is running or finished.
      Promise.all([api.diskPreparation(profileId, id), api.raidOperationStatus(profileId, id).catch(() => null)])
        .then(([view, op]) => { if (active) setReads(current => ({ ...current, [id]: { state: "ok", view: completeView(view), op } })); })
        .catch(err => { if (active) setReads(current => ({ ...current, [id]: { state: "error", message: err instanceof Error ? err.message : String(err) } })); });
    }
    return () => { active = false; };
  }, [profileId, servers, revision]);
  return reads;
}

/** A partial answer (an older backend, a failed read) draws as "not read yet", never a blank page. */
export function completeView(raw: Partial<Inventory> | null | undefined): Inventory {
  const view = (raw ?? {}) as Inventory;
  return { ...view, drives: view.drives ?? [], volumes: view.volumes ?? [], controllers: view.controllers ?? [], blockers: view.blockers ?? [],
    health_issues: view.health_issues ?? [], saved_intent: { wipe_existing_logical_drives: view.saved_intent?.wipe_existing_logical_drives ?? false, volumes: view.saved_intent?.volumes ?? [] } };
}

/** The drives and volumes to draw: the fresh read, or the last read kept for display. */
export function shownRead(view: Inventory) {
  if (view.drives.length || !view.last_read) return { ...merged(view.drives, view.volumes), checkedAt: view.checked_at, stale: !view.current };
  return { ...merged(view.last_read.drives, view.last_read.volumes), checkedAt: view.last_read.checked_at, stale: true };
}

/* The iLO reports each disk and logical drive twice: once through HPE's storage view (with the bay)
   and once through standard Redfish (without it). Show one of each, preferring the one with a bay. */
function merged<D extends { location: string; model?: string | null }, V extends { name: string; raid: string; bays?: string[] | null }>(drives: D[], volumes: V[]) {
  const located = new Set(drives.filter(drive => drive.location && drive.location !== "Unknown bay").map(drive => drive.model ?? ""));
  const withBays = new Set(volumes.filter(volume => volume.bays?.length).map(volume => volume.name + "|" + volume.raid));
  return {
    drives: drives.filter(drive => (drive.location && drive.location !== "Unknown bay") || !located.has(drive.model ?? "")),
    volumes: volumes.filter(volume => volume.bays?.length || !withBays.has(volume.name + "|" + volume.raid)),
  };
}


/** Erased bays in the drives being shown (the fresh read, or the last one). */
function erasedIn(view: Inventory) {
  return erasedBays({ ...view, drives: shownRead(view).drives });
}
type Role = "boot" | "data" | "spare";
function plannedRoles(view: Inventory) {
  const roles = new Map<string, Role>();
  for (const volume of view.saved_intent.volumes) {
    for (const bay of volume.drive_bays) roles.set(bay, volume.bootable ? "boot" : "data");
    for (const bay of volume.spare_bays ?? []) roles.set(bay, "spare");
  }
  return roles;
}


type BayState = "ready" | "raid" | "erased" | "failed" | "empty" | "other";
function bayState(drive: Drive | undefined, erased: string[], inRaid: Set<string>): BayState {
  if (!drive || (drive.presence && drive.presence !== "identified")) return "empty";
  if (drive.health === "Critical") return "failed";
  if (erased.includes(drive.location)) return "erased";
  if (inRaid.has(drive.location)) return "raid";
  return drive.eligible ? "ready" : "other";
}
const stateText: Record<BayState, string> = { ready: "Ready", raid: "In RAID", erased: "Erased", failed: "Failed", empty: "Empty", other: "Check" };
const roleText: Record<Role, string> = { boot: "Boot mirror", data: "Datastore", spare: "Spare" };


function sameBays(a: string[], b: string[]) {
  return a.length === b.length && a.every(item => b.includes(item));
}

/** Does the RAID on the disks already match the saved plan? Only when every volume's bays are known. */
export function raidMatchesPlan(view: Inventory, volumes: Volume[]) {
  const plan = view.saved_intent.volumes;
  if (!plan.length || volumes.length !== plan.length) return false;
  if (volumes.some(volume => !volume.bays?.length)) return view.boot_mirror_matches && plan.length === 1;
  return plan.every(intent => volumes.some(volume => sameBays(volume.bays ?? [], intent.drive_bays)));
}

type Tone = "ok" | "up" | "stop" | "none";
type Action = "read" | "guide" | "build" | "wipe" | "tools-disks" | "tools-raid" | "esxi" | "progress";
export type Verdict = { tone: Tone; title: string; detail: string; action?: Action; label?: string };

/** One decision per server, from what is on the disks and the saved plan. */
export function diskRaidVerdict(view: Inventory, createVerified: boolean, running?: RaidOperationStatus | null): Verdict {
  if (running?.active) return running.operation === "create"
    ? { tone: "up", title: "RAID is being built", detail: "The app is watching it. Open it to see where it is.", action: "build", label: "See progress" }
    : { tone: "up", title: running.operation === "sanitize" ? "Disks are being erased" : running.operation === "clear" ? "Old RAID is being deleted" : "The storage controller is being reset",
      detail: "It carries on by itself. Open it to see where it is.", action: running.operation === "reset" ? "progress" : "wipe", label: "See progress" };
  const { drives, volumes } = shownRead(view);
  if (!drives.length) return { tone: "none", title: "Disks not read yet", detail: "Read the disks to see what is in each bay. Reading changes nothing.", action: "read", label: "Read disks" };
  const failed = drives.filter(drive => drive.health === "Critical");
  if (failed.length) return { tone: "stop", title: `Replace the drive in bay ${failed.map(drive => bayNumber(drive.location)).join(", ")}`, detail: "A failed drive can't go into RAID. Swap it, then read the disks again.", action: "read", label: "Read disks again" };
  const erased = erasedIn(view);
  if (erased.length) return { tone: "up", title: `${erased.length} disk${erased.length === 1 ? " was" : "s were"} securely erased`, detail: "They're empty and safe, but the controller keeps them switched off until you turn them back on. The guide shows you where to click.", action: "guide", label: "Start re-enable guide" };
  // A recorded build only counts while its volumes are still on the disks.
  if (volumes.length && (createVerified || raidMatchesPlan(view, volumes))) return { tone: "ok", title: "RAID is built as planned", detail: "The boot mirror and datastore are on the disks. Next, install ESXi.", action: "esxi", label: "Continue to ESXi" };
  if (volumes.length) return { tone: "up", title: "These disks already have RAID on them", detail: "It doesn't match your plan and may hold someone's data. Wiping deletes the RAID and securely erases every disk, so nothing old is left before you build.", action: "wipe", label: "Wipe disks" };
  if (!view.saved_intent.volumes.length) return { tone: "none", title: "No RAID plan yet", detail: "Pick the two boot disks and the datastore disks. It takes a minute and changes nothing on the server.", action: "tools-raid", label: "Plan RAID" };
  const byBay = new Map(drives.map(drive => [drive.location, drive]));
  const notReady = [...plannedRoles(view).keys()].filter(bay => !byBay.get(bay)?.eligible);
  if (notReady.length) return { tone: "up", title: `Bay ${notReady.map(bayNumber).join(", ")} ${notReady.length === 1 ? "isn't" : "aren't"} ready`, detail: "Your plan uses a bay that is empty or not healthy. Change the plan or fix the disk.", action: "tools-raid", label: "Change plan" };
  return { tone: "up", title: "Ready to build RAID", detail: "Every disk is ready and matches your plan. The app turns the server off, builds the RAID and starts it again.", action: "build", label: "Build RAID" };
}

function isCreateVerified(op: RaidOperationStatus | null) {
  return !!op && !op.active && op.status === "verified" && op.operation === "create";
}

function Panel({ server, section, profileId, onClose }: { server: ServerRow; section: "disks" | "raid"; profileId: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { dialog.current?.showModal(); }, []);
  return <dialog ref={dialog} className="fw-panel fw-panel-wide" aria-label={`${section === "disks" ? "Disk tools" : "RAID plan"} on ${server.name}`} onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    <header><div><p className="eyebrow">{server.name}</p><h2>{section === "disks" ? "Erase or clear" : "RAID plan"}</h2></div>
      <button type="button" aria-label="Close panel" disabled={busy} onClick={onClose}><X size={20} /></button></header>
    <DiskPreparation profileId={profileId} deviceId={server.deviceId!} section={section} onBusyChange={setBusy} />
  </dialog>;
}

/** The server's front drive cage: one slot per bay, coloured by state, labelled with its planned role. */
function BayCage({ view }: { view: Inventory }) {
  const { drives, volumes } = shownRead(view);
  const roles = plannedRoles(view);
  const erased = erasedIn(view);
  const volumeOf = new Map<string, Volume>();
  for (const volume of volumes) for (const bay of volume.bays ?? []) volumeOf.set(bay, volume);
  const inRaid = new Set(volumeOf.keys());
  // Volumes whose members the iLO did not list still count: every drive is shown as possibly in RAID.
  const unknownMembers = volumes.some(volume => !volume.bays?.length);
  const known = [...new Set([...drives.map(drive => drive.location), ...roles.keys()])];
  const bays = [...known, ...gapBays(known)].sort((a, b) => bayOrder(a) - bayOrder(b) || a.localeCompare(b));
  const byBay = new Map(drives.map(drive => [drive.location, drive]));
  return <div className="dr-cage" role="list" aria-label="Drive bays">
    {bays.map(bay => {
      const drive = byBay.get(bay);
      const state = bayState(drive, erased, inRaid);
      const role = roles.get(bay);
      const volume = volumeOf.get(bay);
      const label = `Bay ${bayNumber(bay)}: ${stateText[state]}${volume ? ` (${volume.raid})` : ""}${role ? `, planned ${roleText[role]}` : ", not in plan"}`;
      return <div key={bay} role="listitem" aria-label={label} className={`dr-bay dr-${state}`} title={drive ? `${bay} · ${drive.model} · ${drive.health}` : `Bay ${bayNumber(bay)} · no disk reported`}>
        <span className="dr-num">{bayNumber(bay)}</span>
        <span className="dr-caddy"><span className="dr-led" aria-hidden="true" /><span className="dr-grip" aria-hidden="true" />
          <span className="dr-size">{drive ? size(drive.capacity_bytes) : "—"}</span>
          <span className="dr-media">{drive?.media || (drive ? "" : "no disk")}</span></span>
        <span className="dr-state">{stateText[state]}{volume ? ` · ${volume.raid.replace(/^RAID/, "RAID ")}` : state === "ready" && unknownMembers ? "?" : ""}</span>
        <span className={`dr-role ${role ? `dr-role-${role}` : ""}`}>{role ? roleText[role] : "Not used"}</span>
      </div>;
    })}
  </div>;
}

/** Plain answer to "is there anything on these disks?", from what the controller can see. */
type EraseRecord = { date: string; proven: boolean } | null;

/** The last recorded erase, and whether every disk's result still proves it. */
function eraseRecord(op: RaidOperationStatus | null): EraseRecord {
  if (!op || op.active || op.operation !== "sanitize" || !op.verified_at) return null;
  const drives = op.sanitization?.drives ?? [];
  return { date: new Date(op.verified_at).toLocaleDateString(), proven: drives.length > 0 && drives.every(drive => drive.status === "verified") };
}

function DataFacts({ view, erasedRecorded, built = false }: { view: Inventory; erasedRecorded: EraseRecord; built?: boolean }) {
  const { drives, volumes } = shownRead(view);
  if (!drives.length) return null;
  const erased = erasedIn(view);
  const inRaid = new Set(volumes.flatMap(volume => volume.bays ?? []));
  const loose = drives.filter(drive => drive.eligible && !inRaid.has(drive.location) && !erased.includes(drive.location));
  const facts: Array<{ tone: Tone; text: ReactNode }> = [];
  // Once the planned RAID is verified, the bay map already says what each disk holds.
  if (!built) for (const volume of volumes) facts.push({ tone: "up", text: <><b>{volume.name} · {volume.raid.replace(/^RAID/, "RAID ")}{volume.capacity_bytes ? ` · ${size(volume.capacity_bytes)}` : ""}</b> on {volume.bays?.length ? `bay ${volume.bays.map(bayNumber).join(", ")}` : "these disks"}. Treat it as holding data until you know otherwise.</> });
  if (erased.length) facts.push({ tone: "ok", text: <><b>Bay {erased.map(bayNumber).join(", ")}</b> {erased.length === 1 ? "was" : "were"} securely erased. Nothing is on {erased.length === 1 ? "it" : "them"}.</> });
  if (loose.length && !volumes.length) facts.push({ tone: erasedRecorded?.proven ? "ok" : "none", text: erasedRecorded?.proven
    ? <><b>No RAID on the disks.</b> A secure erase finished here on {erasedRecorded.date} and every disk confirmed it, so they're clean.</>
    : erasedRecorded
    ? <><b>No RAID on the disks.</b> An erase ran here on {erasedRecorded.date}, but the disks can no longer confirm it. The controller can't look inside a disk that isn't in RAID, so if you're unsure, erase again.</>
    : <><b>No RAID on the disks.</b> The controller can't look inside a disk that isn't in RAID. If these came from another server and you're not sure what's on them, erase them first.</> });
  else if (loose.length) facts.push({ tone: "none", text: <><b>Bay {loose.map(drive => bayNumber(drive.location)).join(", ")}</b> {loose.length === 1 ? "is" : "are"} outside any RAID.</> });
  if (!facts.length) return null;
  return <ul className="dr-facts" aria-label="What's on the disks">{facts.map((fact, index) => <li key={index} className={`dr-fact dr-fact-${fact.tone}`}>{fact.text}</li>)}</ul>;
}

function Legend() {
  return <div className="dr-legend" aria-hidden="true">
    <span><i className="dr-sw dr-ready" />Ready</span><span><i className="dr-sw dr-raid" />In RAID</span><span><i className="dr-sw dr-erased" />Erased</span>
    <span><i className="dr-sw dr-failed" />Failed</span><span><i className="dr-sw dr-empty" />Empty</span>
    <span className="dr-legend-sep" /><span><i className="dr-rs dr-role-boot" />Boot mirror</span><span><i className="dr-rs dr-role-data" />Datastore</span><span><i className="dr-rs dr-role-spare" />Spare</span>
  </div>;
}

function ServerCard({ server, read, op, erasedRecorded, onRead, reading, onAction }: {
  server: ServerRow; read?: Read; op: RaidOperationStatus | null; erasedRecorded: EraseRecord;
  onRead: () => void; reading: boolean; onAction: (action: Action, view: Inventory) => void;
}) {
  const view = read?.state === "ok" ? read.view : undefined;
  const verdict = view ? diskRaidVerdict(view, isCreateVerified(op), op) : null;
  const shown = view ? shownRead(view) : null;
  const controller = view?.controllers?.[0];
  return <article className={`dr-card dr-tone-${verdict?.tone ?? "none"}`} aria-label={server.name}>
    <header className="dr-head">
      <span className="st-server"><Server size={20} aria-hidden="true" /><span><strong>{server.name}</strong><small>{server.model}{controller ? ` · ${controller.model}` : ""}</small></span></span>
      <span className="dr-head-side">
        {shown?.checkedAt && shown.drives.length > 0 && <ProvenanceChip kind="recorded" time={shown.checkedAt}>{shown.stale ? "last read" : "disks read"}</ProvenanceChip>}
        {server.deviceId && <button type="button" className="secondary-action dr-read" disabled={reading} onClick={onRead}><RefreshCw size={15} aria-hidden="true" className={reading ? "dr-spin" : ""} />{reading ? "Reading…" : "Read disks"}</button>}
      </span>
    </header>
    {!server.deviceId ? <div className="dr-verdict"><div><strong>Not connected</strong><p>Connect this server first so the app can see its disks.</p></div><Link className="primary-action" to="/setup/connect">Connect</Link></div>
      : read?.state === "error" ? <div className="dr-verdict"><div><strong>Couldn't load the disks</strong><p>{read.message}</p></div></div>
      : !view || !verdict ? <p role="status" className="dr-loading">Loading…</p>
      : <>
        <div className="dr-verdict" role="status">
          <div><strong>{verdict.title}</strong><p>{verdict.detail}</p></div>
          {verdict.action === "esxi" ? <Link className="secondary-action" to="/setup/prepare-esxi">{verdict.label}<ArrowRight size={16} /></Link>
            : verdict.action === "read" ? <button type="button" className="primary-action" disabled={reading} onClick={onRead}>{reading ? "Reading…" : verdict.label}</button>
            : verdict.action ? <button type="button" className="primary-action" onClick={() => onAction(verdict.action!, view)}>{verdict.label}</button> : null}
        </div>
        {shown && shown.drives.length > 0 && <div className="dr-body">
          <div className="dr-chassis"><BayCage view={view} /></div>
          <Legend />
          <DataFacts view={view} erasedRecorded={erasedRecorded} built={verdict?.tone === "ok"} />
          <p className="dr-more">
            {verdict.action !== "tools-raid" && <button type="button" className="fw-link" onClick={() => onAction("tools-raid", view)}>{view.saved_intent.volumes.length ? "Change the RAID plan" : "Plan RAID"}</button>}
            {verdict.action !== "wipe" && <button type="button" className="fw-link" onClick={() => onAction("wipe", view)}>Wipe disks</button>}
            <button type="button" className="fw-link dr-quiet" onClick={() => onAction("tools-disks", view)}>Advanced disk tools</button>
          </p>
        </div>}
      </>}
  </article>;
}

export function DisksRaidStep({ profileId }: { profileId?: string }) {
  const { servers, error } = useServers(profileId);
  const [revision, setRevision] = useState(0);
  const reads = useInventories(profileId, servers, revision);
  const studio = useStudio();
  const [reading, setReading] = useState<Record<string, boolean>>({});
  const [readError, setReadError] = useState<Record<string, string>>({});
  const [panel, setPanel] = useState<{ server: ServerRow; section: "disks" | "raid" } | null>(null);
  const [guide, setGuide] = useState<{ server: ServerRow; view: Inventory } | null>(null);
  const [installer, setInstaller] = useState<ServerRow | null>(null);
  const [wiper, setWiper] = useState<ServerRow | null>(null);
  const [planner, setPlanner] = useState<ServerRow | null>(null);
  const rows = servers ?? [];
  // The page's own status read comes first; the studio's shared read covers the gap while it loads.
  const opFor = (server: ServerRow): RaidOperationStatus | null => {
    if (!server.deviceId) return null;
    const read = reads[server.deviceId];
    if (read?.state === "ok" && read.op) return read.op;
    const shared = studio?.devices.find(item => item.deviceId === server.deviceId)?.storageRead;
    return shared?.state === "ok" ? shared.status : null;
  };
  async function readDisks(server: ServerRow) {
    if (!server.deviceId) return;
    const id = server.deviceId;
    setReading(current => ({ ...current, [id]: true })); setReadError(current => ({ ...current, [id]: "" }));
    try {
      const result = await api.probeProvider("ilo-redfish", id);
      if (result.status !== "ok") throw Error(result.message || "The iLO did not answer.");
      setRevision(value => value + 1);
    } catch (err) { setReadError(current => ({ ...current, [id]: err instanceof Error ? err.message : String(err) })); }
    finally { setReading(current => ({ ...current, [id]: false })); }
  }
  function act(server: ServerRow, action: Action, view: Inventory) {
    if (action === "guide") setGuide({ server, view: { ...view, drives: shownRead(view).drives } });
    else if (action === "build") setInstaller(server);
    else if (action === "wipe") setWiper(server);
    else if (action === "tools-disks" || action === "progress") setPanel({ server, section: "disks" });
    else if (action === "tools-raid") setPlanner(server);
  }
  const verdicts = rows.map(server => { const read = server.deviceId ? reads[server.deviceId] : undefined;
    const op = opFor(server);
    return read?.state === "ok" ? diskRaidVerdict(read.view, isCreateVerified(op), op) : null; });
  const built = verdicts.filter(item => item?.action === "esxi").length;
  return <section className="fw-page storage-step">
    <header className="journey-heading"><h1>Disks &amp; RAID</h1><p>See what's in every bay, clear anything old, then build the boot mirror and datastore.</p></header>
    {error && <p role="alert">Could not load this rack. {error}</p>}
    {!profileId ? <p>Select a kit first.</p> : !servers && !error ? <p role="status">Loading servers…</p> : null}
    {servers && !rows.length && <p>No servers in this rack yet. <Link to="/setup/guide">Add equipment</Link></p>}
    {rows.length > 1 && <p className="st-sum"><b>{built}</b> of {rows.length} servers have RAID built. Each server is done on its own, so one problem never holds up the others.</p>}
    <div className="dr-list">
      {profileId && rows.map(server => {
        const op = opFor(server);
        return <div key={server.id}>
          <ServerCard server={server} read={server.deviceId ? reads[server.deviceId] : undefined}
            op={op} erasedRecorded={eraseRecord(op)}
            reading={!!(server.deviceId && reading[server.deviceId])} onRead={() => void readDisks(server)} onAction={(action, view) => act(server, action, view)} />
          {server.deviceId && readError[server.deviceId] && <p role="alert" className="dr-error">Couldn't read the disks: {readError[server.deviceId]}</p>}
        </div>;
      })}
    </div>
    {guide && profileId && guide.server.deviceId && <DiskReenableGuide profileId={profileId} deviceId={guide.server.deviceId} deviceName={guide.server.name} view={guide.view}
      onClose={changed => { setGuide(null); if (changed) setRevision(value => value + 1); }} />}
    {installer && profileId && installer.deviceId && <RaidInstaller profileId={profileId} deviceId={installer.deviceId} deviceName={installer.name}
      onClose={changed => { setInstaller(null); if (changed) setRevision(value => value + 1); }} />}
    {planner && profileId && planner.deviceId && <RaidPlanEditor profileId={profileId} deviceId={planner.deviceId} deviceName={planner.name}
      onClose={changed => { setPlanner(null); if (changed) setRevision(value => value + 1); }} />}
    {wiper && profileId && wiper.deviceId && <WipeInstaller profileId={profileId} deviceId={wiper.deviceId} deviceName={wiper.name}
      onClose={changed => { setWiper(null); if (changed) setRevision(value => value + 1); }} />}
    {panel && profileId && <Panel server={panel.server} section={panel.section} profileId={profileId} onClose={() => { setPanel(null); setRevision(value => value + 1); }} />}
  </section>;
}
