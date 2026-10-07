import { useEffect, useRef, useState } from "react";
import { RefreshCw, HardDrive, Save, ShieldCheck, Server } from "lucide-react";
import { api, type DiskPreparation as Inventory, type RaidOperationStatus } from "../api";
import { HardwareHealthReview } from "./HardwareHealthReview";
import { RaidRebuildReview } from "./RaidRebuildReview";
import { ShutdownForReset } from "./ShutdownForReset";
import { RaidOperation } from "./RaidOperation";
import { StorageTroubleshooting } from "./StorageTroubleshooting";
import { DiskSanitization, type DiskSanitizationHandle } from "./DiskSanitization";
import {useNavigate} from "react-router-dom";
import { GuardedExecution, erasedDiskCount } from "./GuardedExecution";

type Role = "unassigned" | "boot" | "data" | "spare";
type Draft = { roles: Record<string, Role>; dataRaid: string; spareFor: "boot" | "data"; remove: boolean };
/** "disks" shows reading, erase and re-enable; "raid" shows the layout plan and build. Default: both. */
type Section = "disks" | "raid";
type Props = { profileId: string; deviceId: string; section?: Section; inventoryRevision?: number; onBusyChange?: (busy: boolean) => void; onOperationStatus?: (status: RaidOperationStatus | null) => void };
const capacity = (bytes: number) => bytes ? Math.round(bytes / 1e9) + " GB" : "Not reported";

function savedDraft(view: Inventory): Draft {
  const volumes = view.saved_intent.volumes;
  const boot = volumes.find(v => v.bootable);
  const data = volumes.find(v => !v.bootable);
  return {
    roles: Object.fromEntries(view.drives.map(d => [d.id, boot?.drive_bays.includes(d.location) ? "boot" : data?.drive_bays.includes(d.location) ? "data" : volumes.some(v => v.spare_bays?.includes(d.location)) ? "spare" : "unassigned"])),
    dataRaid: data?.raid_level || "RAID5", spareFor: boot?.spare_bays?.length ? "boot" : "data",
    remove: view.saved_intent.wipe_existing_logical_drives,
  };
}

export function DiskPreparation(props: Props) {
  return <StoragePlanner key={props.profileId + ":" + props.deviceId} {...props} />;
}

function StoragePlanner({ profileId, deviceId, section, inventoryRevision = 0, onBusyChange, onOperationStatus }: Props) {
  const showDisks = section !== "raid", showRaid = section !== "disks";
  const recovery = useRef<HTMLDetailsElement>(null);
  const operationArea = useRef<HTMLDivElement>(null);
  const erasure = useRef<DiskSanitizationHandle>(null);
  const layoutArea = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  function openRecovery() {
    setRebuild(null);
    if (recovery.current) recovery.current.open = true;
    requestAnimationFrame(() => {
      recovery.current?.scrollIntoView({block: 'start', behavior: 'smooth'});
      recovery.current?.querySelector('summary')?.focus({preventScroll: true});
    });
  }
  const [view, setView] = useState<Inventory | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [ack, setAck] = useState(false);
  const [rebuild, setRebuild] = useState<"clear" | "create" | "reset" | null>(null);
  const [operationActive, setOperationActive] = useState(true);
  const [operationStatus,setOperationStatus]=useState<RaidOperationStatus|null>(null);
  const [operationBusy, setOperationBusy] = useState(false);
  const [diagnosing, setDiagnosing] = useState(false);
  const [sanitizing, setSanitizing] = useState(false);
  const [operationRevision, setOperationRevision] = useState(0);
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 15000); return () => clearInterval(timer); }, []);
  useEffect(() => { onBusyChange?.(busy || loading || !!rebuild || operationBusy || diagnosing || sanitizing); return () => onBusyChange?.(false); }, [busy, loading, rebuild, operationBusy, diagnosing, sanitizing, onBusyChange]);
  useEffect(() => {
    let active = true;
    setLoading(true);
    api.diskPreparation(profileId, deviceId).then(v => {
      if (active) { setView(v); if (v.current) setDraft(d => d || savedDraft(v)); setNow(Date.now()); }
    }).catch(e => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [profileId, deviceId, inventoryRevision]);

  function accept(v: Inventory) { setView(v); setNow(Date.now()); if (v.current) setDraft(d => d || savedDraft(v)); }
  async function refresh() {
    setBusy(true); setError(""); setMessage(""); setAck(false);
    try {
      const result = await api.probeProvider("ilo-redfish", deviceId);
      if (result.status !== "ok") throw Error(result.message);
      accept(await api.diskPreparation(profileId, deviceId));
    } catch (e) { setView(null); setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  const drives = view?.drives || [];
  const ids = (role: Role) => Object.keys(draft?.roles || {}).filter(id => draft?.roles[id] === role);
  const boot = ids("boot"), data = ids("data"), spare = ids("spare");
  const fresh = !!view?.current && now - Date.parse(view.checked_at) <= 300000;
  const locked = busy || loading || !!rebuild || operationBusy || diagnosing || sanitizing;
  const changed = !!draft && !!view && JSON.stringify(draft) !== JSON.stringify(savedDraft(view));
  const planned = !!view?.saved_intent.volumes.length;
  const invalid: string[] = [];
  if (boot.length !== 2) invalid.push("Assign two drives to OS RAID.");
  for (const [name, members] of [["OS", boot], ["Storage", data]] as const) {
    const rows = drives.filter(d => members.includes(d.id));
    if (rows.length !== members.length || rows.some(d => !d.eligible)) invalid.push(name + " includes an unavailable drive. Reassign it before saving.");
    if (new Set(rows.map(d => d.capacity_bytes + ":" + (d.media || ""))).size > 1) invalid.push(name + " drives must have matching capacity and media.");
  }
  const count = data.length;
  if (count && !(draft?.dataRaid === "RAID1" ? count === 2 : draft?.dataRaid === "RAID5" ? count >= 3 : draft?.dataRaid === "RAID6" ? count >= 4 : count >= 4 && count % 2 === 0)) invalid.push(draft?.dataRaid + ": " + (draft?.dataRaid === "RAID1" ? "two drives required" : draft?.dataRaid === "RAID5" ? "at least three drives required" : draft?.dataRaid === "RAID6" ? "at least four drives required" : "an even number of at least four drives required") + ".");
  if (spare.length) {
    const members = draft?.spareFor === "boot" ? boot : data;
    const protectedDrives = drives.filter(d => members.includes(d.id));
    const backup = drives.find(d => d.id === spare[0]);
    if (spare.length !== 1 || !backup?.eligible || !protectedDrives.length || protectedDrives.some(d => d.media !== backup.media || d.capacity_bytes > backup.capacity_bytes)) invalid.push("The hot spare must be healthy, match the protected array's media and be at least as large as each member drive.");
  }
  const savedVolumes = view?.saved_intent.volumes || [];
  const unsupported = savedVolumes.length > 2 || savedVolumes.filter(v => v.bootable).length > 1 || savedVolumes.reduce((n, v) => n + (v.spare_bays?.length || 0), 0) > 1;
  if (unsupported) invalid.push("The saved layout has additional arrays or spares. Review it in HPE SSA; this planner will not overwrite it.");
  const replacementReady = !view?.volumes?.length || !!draft?.remove && ack;
  const missingAssignments = [...boot, ...data, ...spare].filter(id => !drives.some(d => d.id === id));
  function update(values: Partial<Draft>) { setDraft(d => d ? { ...d, ...values } : d); setMessage(""); }
  function assign(id: string, role: Role) { if (draft) update({ roles: { ...draft.roles, [id]: role } }); }
  async function save() {
    if (!view || !draft) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await api.saveDiskPreparation(profileId, deviceId, {
        inventory_token: view.inventory_token, boot_drive_ids: boot, data_drive_ids: data, data_raid: draft.dataRaid,
        spare_drive_ids: spare, spare_for: draft.spareFor, remove_existing_volumes: draft.remove, data_loss_reviewed: ack,
      });
      const saved = await api.diskPreparation(profileId, deviceId);
      setView(saved); setDraft(savedDraft(saved)); setMessage(result.message);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  async function acknowledge(issueId: string) {
    if (!view?.health_review) return;
    setBusy(true); setError("");
    try { const review = await api.acknowledgeHealth(profileId, deviceId, view.health_review.review_token, issueId); setView(v => v ? { ...v, health_review: review } : v); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  return <section className="disk-preparation storage-planner" aria-label="Drives and RAID">
    <header className="storage-toolbar"><div><h2>{section === "disks" ? "Disks" : section === "raid" ? "RAID" : <>Drives &amp; RAID</>}</h2><p>{view?.checked_at ? "Inventory read " + new Date(view.checked_at).toLocaleString() : "Read this server's drives before assigning them."}</p></div><button className="secondary-action" disabled={locked} onClick={() => void refresh()}><RefreshCw size={16} />{busy ? "Working..." : "Refresh drive inventory"}</button></header>
    {error && <p role="alert" className="workflow-alert">{error}</p>}
    {loading && <p role="status">Loading storage...</p>}
    {message && <p role="status" className="workflow-pending">{message}</p>}
    <div ref={operationArea} tabIndex={-1} className="storage-current-operation">
      <RaidOperation profileId={profileId} deviceId={deviceId} revision={operationRevision} disabled={busy || loading || !!rebuild || diagnosing || sanitizing}
        onActive={setOperationActive} onBusy={setOperationBusy} onRecovery={openRecovery} onStatus={value => { setOperationStatus(value); onOperationStatus?.(value); }}
        onRetryErase={()=>erasure.current?.open()}
        onContinue={operation => {
          if(operation==="clear" || operation==="reset") erasure.current?.open();
          else if(operation==="sanitize" && !showRaid) navigate("/setup/disks?device="+encodeURIComponent(deviceId));
          else if(operation==="sanitize") {layoutArea.current?.scrollIntoView({block:"start",behavior:"smooth"});layoutArea.current?.focus({preventScroll:true});}
          else navigate("/setup/prepare-esxi?device="+encodeURIComponent(deviceId));
        }}
        onVerified={() => { api.diskPreparation(profileId, deviceId).then(accept).catch(e => setError(e.message)); }} />
    </div>
    {showDisks && <><details className="storage-diagnostics-drawer"><summary>Diagnostics and troubleshooting</summary><StorageTroubleshooting profileId={profileId} deviceId={deviceId} disabled={busy || loading || !!rebuild || operationBusy || sanitizing} onBusy={setDiagnosing}
      onRead={() => { setOperationRevision(r => r + 1); api.diskPreparation(profileId, deviceId).then(accept).catch(e => setError(e.message)); }} /></details>
    <DiskSanitization profileId={profileId} deviceId={deviceId} disabled={busy || loading || !!rebuild || operationBusy || diagnosing || operationActive}
      operationPending={operationActive}
      actionRef={erasure}
      contextual={!!operationStatus?.erase_recovery || operationStatus?.status==="verified" && (operationStatus.operation==="clear" || operationStatus.operation==="reset")}
      onShowOperation={() => {operationArea.current?.scrollIntoView({block:"start",behavior:"smooth"});operationArea.current?.focus({preventScroll:true});}}
      onBusy={setSanitizing} onChanged={() => setOperationRevision(r => r + 1)}
      onDeleteArrays={() => setRebuild("clear")}/></>}
    {showDisks && !!view && erasedDiskCount(view.drives) > 0 && <GuardedExecution kind="drives" profileId={profileId} deviceId={deviceId} deviceName={view.name || "this server"}
      onChanged={() => { api.diskPreparation(profileId, deviceId).then(accept).catch(e => setError(e.message)); }} />}
    {!!view?.blockers.length && <div className="workflow-pending">{view.blockers.map(text => <p key={text}>{text}</p>)}</div>}
    {view?.current && !fresh && <p className="workflow-pending">Inventory is over five minutes old. Refresh to edit or save drive assignments. RAID review reads the server again before allowing any changes. Your selections are kept.</p>}
    {showDisks && view?.health_review && <HardwareHealthReview compact review={view.health_review} busy={locked} onAcknowledge={id => void acknowledge(id)} />}
    {showDisks && !view?.health_review && !!view?.health_issues?.length && <details className="storage-health-summary"><summary>Hardware needs attention ({view.health_issues.length})</summary><ul>{view.health_issues.map(text => <li key={text}>{text}</li>)}</ul></details>}
    {showRaid && draft && !!drives.length && <>
      <div ref={layoutArea} tabIndex={-1} className="storage-plan-summary" aria-label="Planned drive groups">
        <div className="storage-group os"><Server size={22} /><h3>OS RAID</h3><strong>{boot.length} / 2 drives</strong><span>RAID 1 mirror</span></div>
        <div className="storage-group data"><HardDrive size={22} /><h3>Storage RAID</h3><strong>{data.length} drives</strong><label><span className="sr-only">Storage RAID level</span><select aria-label="Storage RAID level" disabled={locked} value={draft.dataRaid} onChange={e => update({ dataRaid: e.target.value })}><option value="RAID1">RAID 1</option><option value="RAID5">RAID 5</option><option value="RAID6">RAID 6</option><option value="RAID10">RAID 10</option></select></label></div>
        <div className="storage-group spare"><ShieldCheck size={22} /><h3>Backup drive</h3><strong>{spare.length} / 1 hot spare</strong><label><span className="sr-only">Hot spare protects</span><select aria-label="Hot spare protects" disabled={locked} value={draft.spareFor} onChange={e => update({ spareFor: e.target.value as Draft["spareFor"] })}><option value="data">Protect storage RAID</option><option value="boot">Protect OS RAID</option></select></label></div>
      </div>
      <p className="storage-plan-note">Planned layout. A hot spare replaces a failed RAID member; it is not a backup of your files.</p>
      <table className="storage-assignment-table"><caption>Drive assignments</caption><thead><tr><th>Drive bay</th><th>Capacity / model</th><th>Health</th><th>Assign to</th></tr></thead><tbody>{drives.map(d => <tr key={d.id} data-role={draft.roles[d.id] || "unassigned"}>
        <th scope="row"><HardDrive size={17} />{d.location}</th><td data-label="Capacity / model"><strong>{capacity(d.capacity_bytes)}</strong><small>{d.model}</small></td>
        <td data-label="Health"><span className={"state-label " + (d.health === "OK" ? fresh ? "state-ok" : "state-unknown" : d.health === "Critical" ? "state-danger" : "state-warning")}>{d.health === "OK" ? fresh ? "Healthy" : "Previous: healthy" : d.label || d.health}</span></td>
        <td data-label="Assign to"><select aria-label={"Role for drive " + d.location} disabled={locked || !fresh || (!d.eligible && (!draft.roles[d.id] || draft.roles[d.id] === "unassigned"))} value={draft.roles[d.id] || "unassigned"} onChange={e => assign(d.id, e.target.value as Role)}>
          <option value="unassigned">Unassigned</option><option disabled={!d.eligible || (boot.length >= 2 && draft.roles[d.id] !== "boot")} value="boot">OS RAID</option><option disabled={!d.eligible} value="data">Storage RAID</option><option disabled={!d.eligible || (spare.length >= 1 && draft.roles[d.id] !== "spare")} value="spare">Backup hot spare</option>
        </select></td>
      </tr>)}</tbody></table>
      {view && <details className="storage-existing"><summary>Existing configuration ({view.volumes.length} volume{view.volumes.length === 1 ? "" : "s"}){view.volumes.length > 0 && !replacementReady ? " - review required" : ""}</summary>
        {view.controllers.map(c => <p key={c.id}>{c.model} / Firmware {c.firmware || "not reported"}</p>)}
        {view.volumes.length ? <><ul>{view.volumes.map(v => <li key={v.id}>{v.name} / {v.raid} / {capacity(v.capacity_bytes)}</li>)}</ul><label className="workflow-checkbox"><input type="checkbox" disabled={locked} checked={draft.remove} onChange={e => { update({ remove: e.target.checked }); setAck(false); }} />Replace the existing RAID volumes</label>{draft.remove && <label className="workflow-checkbox danger-text"><input type="checkbox" disabled={locked} checked={ack} onChange={e => setAck(e.target.checked)} />I have reviewed the backups and understand that removing these volumes destroys access to their data.</label>}</> : <p>No logical volumes reported.</p>}
      </details>}
      <footer className="storage-plan-footer">
        {!!missingAssignments.length && <p>Some assigned drives were not returned by the latest read. <button className="secondary-action" disabled={locked} onClick={() => update({roles:Object.fromEntries(Object.entries(draft.roles).filter(([id]) => !missingAssignments.includes(id)))})}>Unassign unavailable drives</button></p>}
        {!!invalid.length && <ul className="storage-validation">{invalid.map(text => <li key={text}>{text}</li>)}</ul>}
        {!replacementReady && <p>Review the existing configuration above before saving a replacement plan.</p>}
        <div className="storage-operation-steps">
          <div><span>1. Proposed layout <small>{operationActive ? "Verify the submitted operation before saving another plan" : "Plan only; disks unchanged"}</small></span><button className="secondary-action" disabled={locked || operationActive || !fresh || !!invalid.length || !!view?.blockers.length || !replacementReady} onClick={() => void save()}><Save size={16} />Save proposed layout</button></div>
          <div><span>2. {view?.volumes.length ? "Delete existing RAID" : "Create replacement RAID"}<small>{locked ? "Another check or operation is running." : operationActive ? "An operation is pending or its status is unavailable. Check the status above." : !planned ? "Save a proposed layout first." : changed ? "Save your layout changes first." : invalid.length ? invalid[0] : "Reads the server again before review. No disks change until you confirm."}</small></span><button className="primary-action" disabled={locked || operationActive || !planned || changed || !!invalid.length} onClick={() => setRebuild(view?.volumes.length ? "clear" : "create")}><ShieldCheck size={16} />{view?.volumes.length ? "Delete old RAID" : "Create new RAID"}</button></div>
        </div>
        <p>{changed ? "Unsaved changes. " : planned ? "Plan saved. " : ""}Saving does not change disks. Deletion and creation require a separate confirmation.</p>
        <details ref={recovery} className="storage-existing"><summary>Advanced storage recovery</summary>
          <ShutdownForReset profileId={profileId} deviceId={deviceId} disabled={locked} onBusy={setOperationBusy}/>
          <p>Reset this storage controller to factory defaults, removing its arrays and custom settings. This does not reset iLO or securely erase disks. It is not a guaranteed repair for cache or hardware faults.</p>
          <button className="secondary-action" disabled={locked} onClick={() => setRebuild("reset")}><ShieldCheck size={16} />Review controller reset</button>
          <p>Review reads the target and shows any blockers. No reset is sent without a separate confirmation.</p>
        </details>
      </footer>
    </>}
    {rebuild && <RaidRebuildReview profileId={profileId} deviceId={deviceId} operation={rebuild} onRecovery={openRecovery} onClose={() => { setRebuild(null); setOperationRevision(r => r + 1); api.diskPreparation(profileId, deviceId).then(accept).catch(e => setError(e.message)); }} />}
  </section>;
}
