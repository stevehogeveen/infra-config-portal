import { useEffect, useRef, useState } from "react";
import { Check, HardDrive, X } from "lucide-react";
import { api, type DiskPreparation as Inventory, type RaidOperationStatus, type RaidRebuildReview } from "../api";
import { allowStorageChanges, lockReadOnly, powerOffServer, startToApply } from "./storageInstall";

/*
 * Windows-style RAID installer: Check -> Build -> Finish, one button at a time, no typing.
 * Build = RAID-only permission, stage the reviewed layout on the controller, restart the server
 * so the controller applies it, then watch (read-only) until the iLO reports the new volumes.
 * One send per click; nothing is retried automatically; "done" only comes from the verify read.
 */

const STEPS = ["Check", "Build", "Finish"] as const;
type Step = 0 | 1 | 2;
const ACTIVE = new Set(["staged", "waiting"]);
// Blockers the Build button resolves itself: the RAID-only permission and powering the server off.
const HANDLED_BY_BUILD = /live-operation scope|Shut down the server cleanly first/i;
const size = (bytes: number) => bytes >= 1e12 ? `${(bytes / 1e12).toFixed(1)} TB` : `${Math.round(bytes / 1e9)} GB`;

function planLines(view: Inventory | null) {
  return (view?.saved_intent.volumes ?? []).map(volume => ({
    title: volume.bootable ? "Boot mirror (ESXi)" : volume.raid_level === "RAID5" ? "Datastore (RAID 5)" : `Datastore (${volume.raid_level.replace("RAID", "RAID ")})`,
    bays: volume.drive_bays, spare: volume.spare_bays ?? [],
  }));
}

export function RaidInstaller({ profileId, deviceId, deviceName, onClose }: {
  profileId: string; deviceId: string; deviceName: string; onClose: (changed: boolean) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const live = useRef(true);
  const [step, setStep] = useState<Step | null>(null);
  const [view, setView] = useState<Inventory | null>(null);
  const [review, setReview] = useState<RaidRebuildReview | null>(null);
  const [status, setStatus] = useState<RaidOperationStatus | null>(null);
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [changed, setChanged] = useState(false);
  useEffect(() => { live.current = true; dialog.current?.showModal(); return () => { live.current = false; }; }, []);

  async function run(label: string, work: () => Promise<void>) {
    setBusy(label); setError(""); setNote("");
    try { await work(); } catch (err) { if (live.current) setError(err instanceof Error ? err.message : String(err)); }
    finally { if (live.current) setBusy(""); }
  }
  // Open: an operation already underway lands on Build; otherwise the check runs straight away.
  useEffect(() => {
    let startCheck = false;
    void run("Reading the recorded status…", async () => {
      const recorded = await api.raidOperationStatus(profileId, deviceId);
      if (!live.current) return;
      setStatus(recorded);
      if (recorded.operation === "create" && ACTIVE.has(recorded.status)) { setStep(1); return; }
      setStep(0); startCheck = true;
    }).then(() => { if (live.current && startCheck) void check(); });
  }, []);

  // Read-only: a fresh iLO read, the disk view, then the reviewed RAID layout for this server.
  const check = () => run("Reading the disks and preparing the RAID plan…", async () => {
    setReview(null);
    const probe = await api.probeProvider("ilo-redfish", deviceId);
    if (probe.status !== "ok") throw new Error(probe.message || "The iLO didn't answer. Check the server's power and network, then check again.");
    const next = await api.diskPreparation(profileId, deviceId);
    if (!live.current) return;
    setView(next);
    if (next.blockers.length || next.volumes.length) return;
    const plan = await api.previewRaidRebuild(profileId, deviceId, "create");
    if (live.current) setReview(plan);
  });

  // Watch the build: the server restarts and the controller applies the layout during startup.
  const building = step === 1 && !!status && status.operation === "create" && status.status === "waiting";
  useEffect(() => {
    if (!building) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function tick() {
      try {
        const result = await api.verifyRaidRebuild(profileId, deviceId);
        if (!active) return;
        if (result.verified) { setStatus(await api.raidOperationStatus(profileId, deviceId)); setStep(2); setChanged(true); return; }
        if (result.status === "failed") { setStatus(await api.raidOperationStatus(profileId, deviceId)); return; }
      } catch { /* the server is restarting; the next read will answer */ }
      if (active) timer = setTimeout(() => void tick(), 15000);
    }
    timer = setTimeout(() => void tick(), 5000);
    return () => { active = false; clearTimeout(timer); };
  }, [building]);

  const build = () => run("Building RAID…", async () => {
    if (!review || remaining.length) return;
    await allowStorageChanges();
    await powerOffServer(profileId, deviceId, text => { if (live.current) setBusy(text); });
    setBusy("Checking the RAID plan against the server…");
    const fresh = await api.previewRaidRebuild(profileId, deviceId, "create");
    if (!fresh.apply_enabled || fresh.blockers.length) throw new Error(fresh.blockers[0] ?? "The RAID plan can't be applied yet.");
    setBusy("Saving the RAID layout to the controller…");
    await api.applyRaidRebuild(profileId, deviceId, { preview_id: fresh.preview_id, confirmation: fresh.confirmation, data_loss_confirmed: true,
      backups_confirmed: true, health_reviewed: true, firmware_reviewed: true, empty_bays_confirmed: fresh.empty_bays });
    setChanged(true);
    setBusy("Starting the server so the controller builds the RAID…");
    await startToApply(profileId, deviceId);
    if (!live.current) return;
    setStatus(await api.raidOperationStatus(profileId, deviceId));
    setStep(1);
  });

  const finish = () => run("Locking the server…", async () => {
    await lockReadOnly();
    if (live.current) onClose(true);
  });

  const lines = planLines(view);
  const remaining = (review?.blockers ?? []).filter(item => !HANDLED_BY_BUILD.test(item));
  const ready = step === 0 && !!review && !remaining.length && !view?.blockers.length && !view?.volumes.length;
  const stuck = step === 1 && !!status && ["uncertain", "failed", "needs_attention"].includes(status.status);
  const percent = step === null ? 0 : step === 0 ? (ready ? 30 : 12) : step === 2 ? 100 : status?.status === "waiting" ? 70 : 50;
  const next = step === 0 ? (ready ? { label: "Build RAID", run: () => void build() } : { label: "Check again", run: () => void check() })
    : step === 1 && status?.status === "staged" ? null
    : step === 2 ? { label: "Done", run: () => void finish() } : null;

  return <dialog ref={dialog} className="inst" aria-label={`Build RAID on ${deviceName}`} onCancel={event => { event.preventDefault(); if (!busy) onClose(changed); }}>
    <header className="inst-h">
      <span className="inst-icon"><HardDrive size={22} aria-hidden="true" /></span>
      <div><h2>Build RAID</h2><p>{deviceName}</p></div>
      <button type="button" aria-label="Close RAID installer" disabled={!!busy} onClick={() => onClose(changed)}><X size={20} /></button>
    </header>
    <div className="inst-body">
      <ol className="inst-steps" aria-label="Installer steps">{STEPS.map((label, index) =>
        <li key={label} className={step !== null && index < step ? "done" : index === step ? "now" : ""} aria-current={index === step ? "step" : undefined}>
          <span>{step !== null && index < step ? <Check size={13} /> : index + 1}</span>{label}</li>)}</ol>
      <section className="inst-main" aria-live="polite">
        {step === null && <p>Loading…</p>}

        {step === 0 && <>
          <h3>{ready ? "Ready to build" : "Checking the disks"}</h3>
          {lines.length > 0 && <ul className="raid-plan">{lines.map(line => <li key={line.title}><strong>{line.title}</strong>
            <span className="sd-mono">{line.bays.join(", ")}</span>{line.spare.length > 0 && <small>Spare: <span className="sd-mono">{line.spare.join(", ")}</span></small>}</li>)}</ul>}
          {view && !lines.length && <p className="fw-stop" role="alert">No RAID plan is saved for this server yet. Plan it first from the RAID page.</p>}
          {view?.volumes.length ? <p className="fw-stop" role="alert">This server already has {view.volumes.length} RAID volume{view.volumes.length === 1 ? "" : "s"} ({view.volumes.map(volume => `${volume.raid}, ${size(volume.capacity_bytes)}`).join("; ")}). Clear it in the Disks step first.</p> : null}
          {!!view?.blockers.length && <div className="fw-stop" role="alert"><strong>Can't build yet</strong><ul>{view.blockers.map(item => <li key={item}>{item}</li>)}</ul></div>}
          {remaining.length > 0 && <div className="fw-stop" role="alert"><strong>Can't build yet</strong><ul>{remaining.map(item => <li key={item}>{item}</li>)}</ul></div>}
          {ready && <p>The disks in these bays are empty. Building RAID uses them as shown. The server is turned off, then started once so its controller builds the arrays; there's no operating system on it yet. This takes about 5–10 minutes.</p>}
        </>}

        {step === 1 && <>
          <h3>{stuck ? "The build needs attention" : status?.status === "staged" ? "Layout saved, waiting to restart" : "Building RAID…"}</h3>
          {!stuck && status?.status === "waiting" && <p>The server is restarting and its controller is building the arrays. This usually takes a few minutes. This window says when it's complete; you can close it and come back.</p>}
          {!stuck && status?.status === "staged" && <p>The layout is saved on the controller. Click <b>Restart and build</b> to finish.</p>}
          {stuck && <p>{status?.message} Nothing was retried. Open the RAID page's full tools to review it.</p>}
          {status?.status === "staged" && <button type="button" className="primary-action" disabled={!!busy} onClick={() => void run("Restarting the server…", async () => {
            await startToApply(profileId, deviceId);
            if (live.current) setStatus(await api.raidOperationStatus(profileId, deviceId));
          })}>Restart and build</button>}
        </>}

        {step === 2 && <>
          <h3>Complete</h3>
          <p className="inst-ok"><Check size={16} />RAID is built and read back from the server.</p>
          {lines.length > 0 && <ul className="raid-plan">{lines.map(line => <li key={line.title}><strong>{line.title}</strong><span className="sd-mono">{line.bays.join(", ")}</span></li>)}</ul>}
          <p>Next: install ESXi onto the boot mirror.</p>
        </>}

        {busy && <p className="inst-busy" role="status">{busy}</p>}
        {note && <p className="inst-fine" role="status">{note}</p>}
        {error && <p className="fw-stop" role="alert">{error}</p>}
      </section>
    </div>
    <div className="inst-progress" aria-label="Progress">
      <div className={`inst-bar ${step === 2 ? "done" : stuck ? "warn" : ""} ${building || !!busy ? "moving" : ""}`} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}><span style={{ width: `${percent}%` }} /></div>
      <small>Step {step === null ? 1 : step + 1} of {STEPS.length} · {step === null ? "" : STEPS[step]}</small>
    </div>
    <footer className="inst-f">
      <button type="button" className="secondary-action" disabled={!!busy} onClick={() => onClose(changed)}>{building ? "Close (keeps going)" : "Cancel"}</button>
      <span className="inst-grow" />
      {next && <button type="button" className="primary-action inst-next" disabled={!!busy} onClick={next.run}>{next.label}</button>}
    </footer>
  </dialog>;
}
