import { useEffect, useRef, useState } from "react";
import { Check, ExternalLink, HardDrive, X } from "lucide-react";
import { api, type DiskPreparation as Inventory } from "../api";
import { erasedDiskCount } from "./GuardedExecution";

/*
 * Guided, hands-on re-enable of erased disks (until the maintenance boot disk automates it).
 * HPE's own tool does the work: Smart Storage Administrator from Intelligent Provisioning (F10).
 * The command it runs is documented in ssacli 6.60 as "modify [enableeraseddrive]".
 * The app sends nothing to the server here; the last step is a read-only disk check.
 */

const STEPS = ["Open the console", "Start SSA", "Re-enable disks", "Check"] as const;
type Step = 0 | 1 | 2 | 3;
/** Bays whose drive reports a completed erase: on the drive itself, or (iLO 5 3.x) in the health review. */
export function erasedBays(view: Inventory): string[] {
  const fromDrives = view.drives.filter(drive => erasedDiskCount([drive]) === 1).map(drive => drive.location);
  const fromReview = (view.health_review?.issues ?? [])
    .filter(issue => issue.group === "Drive" && issue.details.some(line => /erase completed|erasecompleted/i.test(line)))
    .map(issue => issue.location);
  const present = new Set(view.drives.map(drive => drive.location));
  return [...new Set([...fromDrives, ...fromReview])].filter(bay => present.has(bay)).sort();
}

export function DiskReenableGuide({ profileId, deviceId, deviceName, view, onClose }: {
  profileId: string; deviceId: string; deviceName: string; view: Inventory; onClose: (changed: boolean) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [step, setStep] = useState<Step>(0);
  const [host, setHost] = useState<string | null>(null);
  const [done, setDone] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [after, setAfter] = useState<Inventory | null>(null);
  const bays = erasedBays(view);
  const remaining = after ? erasedBays(after) : null;
  useEffect(() => { dialog.current?.showModal(); api.iloAccessSettings(deviceId).then(settings => setHost(settings.host ?? null)).catch(() => setHost(null)); }, []);

  // Read-only: a fresh iLO read, then the disk inventory it produced.
  async function check() {
    setBusy(true); setError("");
    try {
      const probe = await api.probeProvider("ilo-redfish", deviceId);
      if (probe.status !== "ok") throw new Error(probe.message || "The iLO didn't answer. Check the server is powered on and try again.");
      setAfter(await api.diskPreparation(profileId, deviceId));
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }

  const allTicked = bays.every(bay => done[bay]);
  const next = step === 0 ? { label: "Next", run: () => setStep(1), enabled: true }
    : step === 1 ? { label: "Next", run: () => setStep(2), enabled: true }
    : step === 2 ? { label: "Next", run: () => { setStep(3); void check(); }, enabled: allTicked }
    : remaining && remaining.length === 0 ? { label: "Done", run: () => onClose(true), enabled: true }
    : { label: "Check again", run: () => void check(), enabled: !busy };
  const percent = step === 3 ? (remaining && remaining.length === 0 ? 100 : 85) : [15, 40, 65][step];

  return <dialog ref={dialog} className="inst" aria-label={`Re-enable erased disks on ${deviceName}`} onCancel={event => { event.preventDefault(); if (!busy) onClose(!!after); }}>
    <header className="inst-h">
      <span className="inst-icon"><HardDrive size={22} aria-hidden="true" /></span>
      <div><h2>Re-enable erased disks</h2><p>{deviceName} · {bays.length} disk{bays.length === 1 ? "" : "s"}</p></div>
      <button type="button" aria-label="Close guide" disabled={busy} onClick={() => onClose(!!after)}><X size={20} /></button>
    </header>
    <div className="inst-body">
      <ol className="inst-steps" aria-label="Guide steps">{STEPS.map((label, index) =>
        <li key={label} className={index < step ? "done" : index === step ? "now" : ""} aria-current={index === step ? "step" : undefined}>
          <span>{index < step ? <Check size={13} /> : index + 1}</span>{label}</li>)}</ol>
      <section className="inst-main" aria-live="polite">
        {step === 0 && <>
          <h3>Open the server's console</h3>
          <p>Open the iLO web page and sign in. Then open the <b>HTML5 remote console</b> (on the iLO Overview page, or under <b>Remote Console &amp; Media</b>).</p>
          {host && <a className="secondary-action inst-link" href={`https://${host}`} target="_blank" rel="noopener noreferrer"><ExternalLink size={15} />Open the iLO web page</a>}
          <p className="inst-fine">Keep this window open beside it. Nothing is sent to the server by this guide.</p>
        </>}

        {step === 1 && <>
          <h3>Start Smart Storage Administrator</h3>
          <ol className="guide-list">
            <li>In the console, restart the server: use the console's <b>Power</b> menu and choose <b>Reset</b> (or <b>Momentary Press</b> if it's off).</li>
            <li>When the HPE screen shows the key options, press <b>F10</b> to start Intelligent Provisioning.</li>
            <li>Choose <b>Perform Maintenance</b>, then <b>Smart Storage Administrator</b>.</li>
          </ol>
          <p className="inst-fine">The server has no operating system yet, so restarting it is safe.</p>
        </>}

        {step === 2 && <>
          <h3>Re-enable each erased disk</h3>
          <ol className="guide-list">
            <li>If you see a report or <b>Diagnostics</b> page, click <b>Home</b> (top left) to leave it.</li>
            <li>Click <b>Smart Array P408i-a SR Gen10</b>, then choose <b>Configure</b> (not Diagnose).</li>
            <li>Open <b>Physical Devices</b> (or <b>Unassigned Drives</b>) and click a disk below.</li>
            <li>In the <b>Actions</b> list on the right, choose <b>Enable Erased Drive</b> (it may say <b>Re-enable Erased Drive</b>). Do each disk and tick it here.</li>
          </ol>
          <p className="inst-fine"><b>No such action, disk Status OK and Create Array offered?</b> Then the disk is already back in service. Don't create an array here (the RAID step does that from your plan); just tick it.</p>
          <ul className="guide-bays">{bays.map(bay => <li key={bay}><label><input type="checkbox" checked={!!done[bay]} onChange={event => setDone(current => ({ ...current, [bay]: event.target.checked }))} /><span className="sd-mono">Bay {bay}</span></label></li>)}</ul>
          <p className="inst-fine">When all are done, exit Smart Storage Administrator and restart the server once more, then click Next.</p>
        </>}

        {step === 3 && <>
          <h3>{remaining === null ? "Checking the disks…" : remaining.length === 0 ? "All disks are back in service" : "Some disks are still erased"}</h3>
          {remaining?.length === 0 && <p className="inst-ok"><Check size={16} />All {bays.length} disks are ready. Next up: RAID.</p>}
          {remaining && remaining.length > 0 && <>
            <p>These still show as erased: <span className="sd-mono">{remaining.join(", ")}</span>.</p>
            <p>Go back into Smart Storage Administrator and choose <b>Enable Erased Drive</b> for them, restart, then check again. If the option isn't there, the server may still be booting; wait a minute and check again.</p>
          </>}
        </>}

        {busy && <p className="inst-busy" role="status">Reading the disks from the iLO…</p>}
        {error && <p className="fw-stop" role="alert">{error}</p>}
      </section>
    </div>
    <div className="inst-progress" aria-label="Progress">
      <div className={`inst-bar ${percent === 100 ? "done" : ""} ${busy ? "moving" : ""}`} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}><span style={{ width: `${percent}%` }} /></div>
      <small>Step {step + 1} of {STEPS.length} · {STEPS[step]}</small>
    </div>
    <footer className="inst-f">
      <button type="button" className="secondary-action" disabled={busy} onClick={() => onClose(!!after)}>{step === 3 ? "Close" : "Cancel"}</button>
      <span className="inst-grow" />
      {step > 0 && step < 3 && <button type="button" className="secondary-action" onClick={() => setStep((step - 1) as Step)}>Back</button>}
      {step === 3 && remaining && remaining.length > 0 && <button type="button" className="secondary-action" onClick={() => setStep(2)}>Back</button>}
      <button type="button" className="primary-action inst-next" disabled={!next.enabled || busy} onClick={next.run}>{next.label}</button>
    </footer>
  </dialog>;
}
