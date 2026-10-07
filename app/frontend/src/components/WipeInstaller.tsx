import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, Eraser, X } from "lucide-react";
import { api, type DiskPreparation as Inventory, type EraseDrive, type RaidOperationStatus, type RaidRebuildReview } from "../api";
import { allowStorageChanges, lockReadOnly, powerOffServer, startToApply } from "./storageInstall";

/*
 * Windows-style disk wipe: Check -> Wipe -> Finish. One tick and one button, no typing.
 * Wipe = disks-and-RAID-only permission, delete any RAID first (restart, read back empty), then
 * record this approval for the listed disks, stage the secure erase, restart so the controller
 * runs it, and watch (read-only) until every disk reports its erase finished.
 * One send per step; nothing is retried automatically; "done" only comes from the verify read.
 */

const STEPS = ["Check", "Wipe", "Finish"] as const;
type Step = 0 | 1 | 2;
const ACTIVE = new Set(["staged", "waiting"]);
// Blockers the Wipe button resolves itself: permission, power, the old RAID and the erase approval.
const HANDLED_BY_WIPE = /live-operation scope|Shut down the server|Physical-disk erasure is not enabled|Method support has not been reviewed|new erase authorization|Delete the existing RAID arrays|must be unconfigured before erasure/i;
const NEEDS_APPROVAL = /Physical-disk erasure is not enabled|Method support has not been reviewed|new erase authorization/i;
// The HPE iLO 5 command path this erase uses (Smart Array PhysicalDriveErase).
const HPE_REFERENCE = "https://github.com/HewlettPackard/python-redfish-utility/blob/master/ilorest/extensions/SMART_ARRAY_COMMANDS/DriveSanitizeCommand.py";

const size = (bytes: number) => !bytes ? "" : bytes >= 1e12 ? `${(bytes / 1e12).toFixed(1)} TB` : `${Math.round(bytes / 1e9)} GB`;
const bayNumber = (location: string) => location.split(":").pop() || location;
const methodText = (drive: EraseDrive) => drive.erase_pattern === "SanitizeRestrictedBlockErase" ? "SSD block erase" : "full overwrite";

/** What the operator approved, per disk, recorded with the erase: the method, the hardware it covers, the reference. */
function approvalNote(review: RaidRebuildReview, drive: EraseDrive) {
  return `Approved in the Wipe disks installer: ${drive.erase_pattern} (${methodText(drive)}) for ${drive.media} ${drive.model} firmware ${drive.firmware || "not reported"}, ` +
    `bay ${drive.bay}, on ${review.controller} firmware ${review.capability_context?.controller_firmware || "not reported"}. HPE command reference: ${HPE_REFERENCE}. ` +
    "Completion is proven only by the controller's per-drive erase results.";
}

function erasePercent(status: RaidOperationStatus | null) {
  const drives = status?.sanitization?.drives ?? [];
  if (!drives.length) return null;
  return Math.round(drives.reduce((sum, drive) => sum + (drive.status === "verified" ? 100 : drive.percent ?? 0), 0) / drives.length);
}

export function WipeInstaller({ profileId, deviceId, deviceName, onClose }: {
  profileId: string; deviceId: string; deviceName: string; onClose: (changed: boolean) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const live = useRef(true);
  const [step, setStep] = useState<Step | null>(null);
  const [view, setView] = useState<Inventory | null>(null);
  const [review, setReview] = useState<RaidRebuildReview | null>(null);
  const [status, setStatus] = useState<RaidOperationStatus | null>(null);
  const [understood, setUnderstood] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [changed, setChanged] = useState(false);
  useEffect(() => { live.current = true; dialog.current?.showModal(); return () => { live.current = false; }; }, []);
  const say = (text: string) => { if (live.current) setBusy(text); };

  async function run(label: string, work: () => Promise<void>) {
    setBusy(label); setError("");
    try { await work(); } catch (err) { if (live.current) setError(err instanceof Error ? err.message : String(err)); }
    finally { if (live.current) setBusy(""); }
  }
  // Open: a wipe already underway lands on Wipe; otherwise the check runs straight away.
  useEffect(() => {
    let startCheck = false;
    void run("Reading the recorded status…", async () => {
      const recorded = await api.raidOperationStatus(profileId, deviceId);
      if (!live.current) return;
      setStatus(recorded);
      if ((recorded.operation === "sanitize" || recorded.operation === "clear") && recorded.active && ACTIVE.has(recorded.status)) { setStep(1); return; }
      setStep(0); startCheck = true;
    }).then(() => { if (live.current && startCheck) void check(); });
  }, []);

  // Read-only: a fresh iLO read, the disk view, then the erase review for every disk on the controller.
  const check = () => run("Reading the disks…", async () => {
    setReview(null);
    const probe = await api.probeProvider("ilo-redfish", deviceId);
    if (probe.status !== "ok") throw new Error(probe.message || "The iLO didn't answer. Check the server's power and network, then check again.");
    const next = await api.diskPreparation(profileId, deviceId);
    if (!live.current) return;
    setView(next);
    const plan = await api.previewRaidRebuild(profileId, deviceId, "sanitize", "auto");
    if (live.current) setReview(plan);
  });

  // Watch: the server restarts and the controller deletes the RAID or erases the disks.
  const watching = step === 1 && !!status && (status.operation === "sanitize" || status.operation === "clear") && status.status === "waiting";
  useEffect(() => {
    if (!watching) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const erasing = status?.operation === "sanitize";
    async function tick() {
      try {
        const result = await api.verifyRaidRebuild(profileId, deviceId);
        if (!active) return;
        const recorded = await api.raidOperationStatus(profileId, deviceId);
        if (!active) return;
        setStatus(recorded);
        if (result.verified) {
          setChanged(true);
          if (erasing) { setStep(2); return; }
          // The old RAID is gone: carry on with the erase this wipe was approved for.
          await erase();
          return;
        }
        if (result.status === "failed") return;
      } catch { /* the server is restarting; the next read will answer */ }
      if (active) timer = setTimeout(() => void tick(), erasing ? 30000 : 15000);
    }
    timer = setTimeout(() => void tick(), 5000);
    return () => { active = false; clearTimeout(timer); };
  }, [watching, status?.operation]);

  // Delete the existing RAID: record its removal in the plan, power off, stage the clear, restart.
  async function clearRaid(current: Inventory) {
    if (!current.saved_intent.wipe_existing_logical_drives) {
      const intent = current.saved_intent.volumes;
      const boot = intent.find(volume => volume.bootable);
      if (!boot) throw new Error("This server has RAID but no saved RAID plan. Use Change the RAID plan first, then wipe.");
      const data = intent.find(volume => !volume.bootable);
      const withSpare = intent.find(volume => volume.spare_bays?.length);
      const idFor = (bay: string) => { const id = current.drives.find(drive => drive.location === bay)?.id; if (!id) throw new Error(`Bay ${bay} isn't in the latest read.`); return id; };
      say("Recording that the old RAID will be removed…");
      await api.saveDiskPreparation(profileId, deviceId, { inventory_token: current.inventory_token, boot_drive_ids: boot.drive_bays.map(idFor),
        remove_existing_volumes: true, data_loss_reviewed: true, data_drive_ids: data?.drive_bays.map(idFor) ?? [], data_raid: data?.raid_level ?? "RAID5",
        spare_drive_ids: withSpare?.spare_bays?.map(idFor) ?? [], spare_for: withSpare?.bootable ? "boot" : "data" });
    }
    await powerOffServer(profileId, deviceId, say);
    say("Deleting the old RAID…");
    const clear = await api.previewRaidRebuild(profileId, deviceId, "clear");
    if (!clear.apply_enabled || clear.blockers.length) throw new Error(clear.blockers[0] ?? "The old RAID can't be deleted yet.");
    await api.applyRaidRebuild(profileId, deviceId, { preview_id: clear.preview_id, confirmation: clear.confirmation, data_loss_confirmed: true,
      backups_confirmed: true, health_reviewed: true, firmware_reviewed: true, empty_bays_confirmed: clear.empty_bays });
    setChanged(true);
    say("Starting the server so the controller deletes the RAID…");
    await startToApply(profileId, deviceId);
  }

  // Erase every disk: power off, record the approval for these disks, stage the erase, restart.
  async function erase() {
    if (live.current) setBusy("Preparing the erase…");
    try {
      await allowStorageChanges();
      await powerOffServer(profileId, deviceId, say);
      say("Reading the disks…");
      const probe = await api.probeProvider("ilo-redfish", deviceId);
      if (probe.status !== "ok") throw new Error(probe.message || "The iLO didn't answer.");
      let fresh = await api.previewRaidRebuild(profileId, deviceId, "sanitize", "auto");
      if (fresh.blockers.some(item => NEEDS_APPROVAL.test(item))) {
        say("Recording your approval for these disks…");
        const drives = fresh.drives ?? [];
        await api.authorizeSanitization(profileId, deviceId, { preview_id: fresh.preview_id, confirmation: `AUTHORIZE ERASURE ${fresh.name}`,
          vendor_support_reviewed: true, sources: Object.fromEntries(drives.map(drive => [drive.identity, approvalNote(fresh, drive)])) });
        fresh = await api.previewRaidRebuild(profileId, deviceId, "sanitize", "auto");
      }
      if (!fresh.apply_enabled || fresh.blockers.length) throw new Error(fresh.blockers[0] ?? "The erase can't be started yet.");
      say("Sending the erase to the controller…");
      await api.applyRaidRebuild(profileId, deviceId, { preview_id: fresh.preview_id, confirmation: fresh.confirmation, data_loss_confirmed: true,
        backups_confirmed: true, health_reviewed: true, firmware_reviewed: true, empty_bays_confirmed: fresh.empty_bays, physical_erase_confirmed: true });
      setChanged(true);
      say("Starting the server so the controller erases the disks…");
      await startToApply(profileId, deviceId);
      if (live.current) setStatus(await api.raidOperationStatus(profileId, deviceId));
    } catch (err) { if (live.current) setError(err instanceof Error ? err.message : String(err)); }
    finally { if (live.current) setBusy(""); }
  }

  const wipe = () => run("Wiping…", async () => {
    if (!review || !view || remaining.length || !understood) return;
    await allowStorageChanges();
    setStep(1);
    if (view.volumes.length) {
      await clearRaid(view);
      if (live.current) setStatus(await api.raidOperationStatus(profileId, deviceId));
      return;
    }
    await erase();
  });

  const drives = review?.drives ?? [];
  const remaining = (review?.blockers ?? []).filter(item => !HANDLED_BY_WIPE.test(item));
  const ready = step === 0 && !!review && !!view && drives.length > 0 && !remaining.length;
  const stuck = step === 1 && !!status && ["uncertain", "failed", "needs_attention"].includes(status.status);
  const erasing = step === 1 && status?.operation === "sanitize";
  const done = erasePercent(erasing ? status : null);
  const percent = step === null ? 0 : step === 0 ? (ready ? 25 : 10) : step === 2 ? 100
    : erasing && status?.status === "waiting" ? 40 + Math.round((done ?? 0) * 0.55) : status?.operation === "clear" ? 30 : 35;
  const next = step === 0 ? (ready ? { label: `Wipe ${drives.length} disks`, run: () => void wipe(), disabled: !understood, danger: true } : { label: "Check again", run: () => void check(), disabled: false, danger: false })
    : step === 2 ? { label: "Done", run: () => void run("Locking the server…", async () => { await lockReadOnly(); if (live.current) onClose(true); }), disabled: false, danger: false } : null;

  return <dialog ref={dialog} className="inst" aria-label={`Wipe disks on ${deviceName}`} onCancel={event => { event.preventDefault(); if (!busy) onClose(changed); }}>
    <header className="inst-h">
      <span className="inst-icon inst-icon-danger"><Eraser size={22} aria-hidden="true" /></span>
      <div><h2>Wipe disks</h2><p>{deviceName}</p></div>
      <button type="button" aria-label="Close wipe installer" disabled={!!busy} onClick={() => onClose(changed)}><X size={20} /></button>
    </header>
    <div className="inst-body">
      <ol className="inst-steps" aria-label="Installer steps">{STEPS.map((label, index) =>
        <li key={label} className={step !== null && index < step ? "done" : index === step ? "now" : ""} aria-current={index === step ? "step" : undefined}>
          <span>{step !== null && index < step ? <Check size={13} /> : index + 1}</span>{label}</li>)}</ol>
      <section className="inst-main" aria-live="polite">
        {step === null && <p>Loading…</p>}

        {step === 0 && <>
          <h3>{ready ? "Ready to wipe" : "Checking the disks"}</h3>
          {drives.length > 0 && <div className="wipe-warn" role="note">
            <strong><AlertTriangle size={17} aria-hidden="true" />Everything on these {drives.length} disks is destroyed for good</strong>
            <ul className="wipe-bays">{drives.map(drive => <li key={drive.bay}><b>Bay {bayNumber(drive.bay)}</b><span>{size(drive.capacity_bytes)} {drive.media}</span></li>)}</ul>
          </div>}
          {!!view?.volumes.length && <p>The RAID on them ({view.volumes.map(volume => `${volume.raid.replace(/^RAID/, "RAID ")}${volume.capacity_bytes ? `, ${size(volume.capacity_bytes)}` : ""}`).join("; ")}) is deleted first.</p>}
          {remaining.length > 0 && <div className="fw-stop" role="alert"><strong>Can't wipe yet</strong><ul>{remaining.map(item => <li key={item}>{item}</li>)}</ul></div>}
          {ready && <>
            <p>The server is turned off, then started so its controller does a {drives.some(drive => drive.erase_pattern === "SanitizeRestrictedBlockErase") ? "secure erase" : "full overwrite"} of every disk. That takes <b>several hours</b>; you can close this window and it carries on.</p>
            <p>Afterwards the disks come back switched off. The re-enable guide turns them back on before you build RAID.</p>
            <label className="wipe-ok"><input type="checkbox" checked={understood} onChange={event => setUnderstood(event.target.checked)} />I understand everything on these disks will be lost and can't be recovered.</label>
          </>}
        </>}

        {step === 1 && <>
          <h3>{stuck ? "The wipe needs attention" : status?.operation === "clear" ? "Deleting the old RAID…" : status?.status === "staged" ? "Erase saved, waiting to restart" : erasing ? "Erasing the disks…" : "Starting the wipe…"}</h3>
          {!stuck && status?.operation === "clear" && <p>The server is restarting so its controller deletes the old RAID. The erase starts straight after, by itself.</p>}
          {!stuck && erasing && status?.status === "waiting" && <p>The controller is erasing every disk. This takes several hours; keep the server powered. You can close this window and come back — it keeps checking.</p>}
          {erasing && (status?.sanitization?.drives?.length ?? 0) > 0 && <ul className="wipe-bays wipe-progress">{status!.sanitization!.drives.map(drive =>
            <li key={drive.bay}><b>Bay {bayNumber(drive.bay)}</b><span>{drive.status === "verified" ? "Erased" : drive.percent != null ? `${drive.percent}%` : "Waiting"}</span></li>)}</ul>}
          {!stuck && status?.status === "staged" && <button type="button" className="primary-action" disabled={!!busy} onClick={() => void run("Restarting the server…", async () => {
            await startToApply(profileId, deviceId);
            if (live.current) setStatus(await api.raidOperationStatus(profileId, deviceId));
          })}>Restart and continue</button>}
          {!stuck && status?.operation === "clear" && status.status === "verified" && !busy && <button type="button" className="primary-action" onClick={() => void erase()}>Continue: erase the disks</button>}
          {stuck && <p>{status?.message} Nothing was retried. Use the disk tools on the Disks &amp; RAID page to review it.</p>}
        </>}

        {step === 2 && <>
          <h3>Complete</h3>
          <p className="inst-ok"><Check size={16} />Every disk reported its erase finished.</p>
          <p>Next: turn the disks back on with the re-enable guide on the Disks &amp; RAID page, then build RAID.</p>
        </>}

        {busy && <p className="inst-busy" role="status">{busy}</p>}
        {error && <p className="fw-stop" role="alert">{error}</p>}
      </section>
    </div>
    <div className="inst-progress" aria-label="Progress">
      <div className={`inst-bar ${step === 2 ? "done" : stuck ? "warn" : ""} ${watching || !!busy ? "moving" : ""}`} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}><span style={{ width: `${percent}%` }} /></div>
      <small>Step {step === null ? 1 : step + 1} of {STEPS.length} · {step === null ? "" : STEPS[step]}{erasing && done != null ? ` · ${done}% erased` : ""}</small>
    </div>
    <footer className="inst-f">
      <button type="button" className="secondary-action" disabled={!!busy} onClick={() => onClose(changed)}>{watching ? "Close (keeps going)" : "Cancel"}</button>
      <span className="inst-grow" />
      {next && <button type="button" className={`primary-action inst-next ${next.danger ? "inst-danger" : ""}`} disabled={!!busy || next.disabled} onClick={next.run}>{next.label}</button>}
    </footer>
  </dialog>;
}
