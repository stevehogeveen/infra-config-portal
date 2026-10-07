import { useEffect, useRef, useState } from "react";
import { Power, RefreshCw, X, Check, CircleCheck, Clock, AlertTriangle, ArrowRight, Wrench } from "lucide-react";
import { api, type RaidOperationStatus, type RaidBootReview } from "../api";
import {DiskEraseProgress} from "./DiskEraseProgress";
import { GuidePrimary } from "./studio/Guide";

type Props = { profileId: string; deviceId: string; revision: number; disabled: boolean;
  onActive: (active: boolean) => void; onBusy: (busy: boolean) => void; onVerified: () => void;
  onContinue?: (operation: NonNullable<RaidOperationStatus["operation"]>) => void; onRecovery?:()=>void; onReturn?:()=>void;
  onStatus?: (status: RaidOperationStatus|null)=>void; onRetryErase?:()=>void };
const windowMs = 20 * 60 * 1000;
const monitoringWindow = (s: RaidOperationStatus | null) => s?.operation === "sanitize" ? 24 * 60 * 60 * 1000 : windowMs;
const disksActive = (s:RaidOperationStatus) => s.sanitization?.drives.some(d=>d.status==="erasing"||d.status==="queued");
const operationNames = {clear:"Remove existing RAID",create:"Create new RAID",reset:"Reset storage controller",sanitize:"Erase physical disks"};
const outcomes = {
  clear: {title:"RAID arrays removed",detail:"The recorded check confirmed the old RAID layout was cleared. Removing arrays does not sanitize disk contents.",next:"Prepare disk erasure"},
  reset: {title:"Storage reset verified",detail:"The controller reset was verified. This does not prove physical disks have been sanitized.",next:"Prepare disk erasure"},
  create: {title:"New RAID layout verified",detail:"The recorded check matched the requested RAID layout. ESXi installation is a separate operation.",next:"Continue to ESXi setup"},
  sanitize: {title:"Disk erasure verified",detail:"Every disk in the reviewed operation reported completion for its assigned erase method. New arrays have not been created by this operation.",next:"Plan new RAID"},
};

export function RaidOperation({ profileId, deviceId, revision, disabled, onActive, onBusy, onVerified, onContinue, onRecovery, onReturn, onStatus, onRetryErase }: Props) {
  const [status, setStatus] = useState<RaidOperationStatus | null>(null);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState("");
  const [checking, setChecking] = useState(false);
  const [monitor, setMonitor] = useState(false);
  const [open, setOpen] = useState(false);
  const [tick, setTick] = useState(0);
  const callbacks = useRef({ onActive, onBusy, onVerified, onStatus });
  callbacks.current = { onActive, onBusy, onVerified, onStatus };
  useEffect(()=>{callbacks.current.onStatus?.(error ? null : status);},[status,error]);
  useEffect(() => { callbacks.current.onBusy(checking || open); return () => callbacks.current.onBusy(false); }, [checking, open]);
  useEffect(() => {
    let active = true;
    api.raidOperationStatus(profileId, deviceId).then(s => {
      if (!active) return;
      setStatus(s); setError(""); callbacks.current.onActive(s.active);
      setMonitor((s.status === "waiting" || s.status!=="verified" && !!disksActive(s)) && !!s.boot_started_at && Date.now() - Date.parse(s.boot_started_at) < monitoringWindow(s));
    }).catch(e => { if (active) { setError(e.message); callbacks.current.onActive(true); } });
    return () => { active = false; };
  }, [profileId, deviceId, revision, tick]);
  useEffect(() => {
    if (!monitor || !status?.boot_started_at || disabled || open) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function check() {
      if (Date.now() - Date.parse(status!.boot_started_at!) >= monitoringWindow(status)) {
        setMonitor(false); setProgress("Automatic checking window ended. The hardware operation is not cancelled. Keep power on during disk erasure and check its result again."); return;
      }
      setChecking(true); setProgress("Reading iLO and RAID configuration. HPE POST can take several minutes. No additional power requests are sent.");
      try {
        const result = await api.verifyRaidRebuild(profileId, deviceId);
        if (!active) return;
        setProgress(result.message); setError("");
        if (status?.operation === "sanitize") {
          const latest = await api.raidOperationStatus(profileId, deviceId);
          if (!active) return;
          setStatus(latest);
          callbacks.current.onActive(latest.active);
          if (latest.status === "needs_attention" && !disksActive(latest)) {
            setMonitor(false); return;
          }
        }
        if (result.status === "failed") {
          setMonitor(false); setTick(t => t + 1); return;
        }
        if (result.verified) {
          setMonitor(false); setTick(t => t + 1); callbacks.current.onVerified(); return;
        }
      } catch (e) { if (active) setError(`Verification unavailable: ${e instanceof Error ? e.message : String(e)} No power request will be retried.`); }
      finally { if (active) setChecking(false); }
      if (active) timer = setTimeout(() => void check(), 15000);
    }
    timer = setTimeout(() => void check(), 1000);
    return () => { active = false; clearTimeout(timer); setChecking(false); };
  }, [monitor, status?.boot_started_at, profileId, deviceId, disabled, open]);
  async function verify() {
    setChecking(true); setError(""); setProgress("Reading iLO and RAID configuration. This can take up to two minutes.");
    try {
      const result = await api.verifyRaidRebuild(profileId, deviceId);
      setProgress(result.message); setTick(t => t + 1);
      if (result.verified) callbacks.current.onVerified();
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setChecking(false); }
  }
  if (!error && !status) return <p role="status">Loading the recorded storage operation...</p>;
  if (!error && status?.status === "not_started") return null;
  const verified = status?.status === "verified";
  const needsHelp = !!error || !!status && ["failed","uncertain","needs_attention"].includes(status.status);
  const outcome = status?.operation ? outcomes[status.operation] : null;
  const erasing = status?.sanitization?.drives.filter(d=>d.status==="erasing").length || 0;
  const queued = status?.sanitization?.drives.filter(d=>d.status==="queued").length || 0;
  const tone = needsHelp ? "attention" : verified ? "complete" : status?.status === "staged" ? "ready" : "running";
  const title = error ? "Status could not be refreshed" : verified ? outcome?.title || "Storage operation verified" :
    status?.status === "staged" ? (status.operation==="sanitize"?"Wipe staged - start server next":"Ready to start the server") : status?.status === "waiting" ? (status.operation==="sanitize"?(erasing?"Controller reports disk erasure in progress":queued?"Disks queued for erasure":"Waiting for the controller to confirm erasure"):"Waiting for verified results") :
    status?.status === "failed" ? "Storage operation rejected" : status?.status === "uncertain" ? "Request outcome is unknown" : status?.operation==="sanitize"?"Disk wipe needs attention":"Storage needs attention";
  const detail = verified && !error ? outcome?.detail : status?.status === "staged" ?
    "Settings are saved on the controller, but have not taken effect. Power-on requires your confirmation." :
    status?.status === "waiting" ? "Power-on was requested. The operation is not complete until the hardware result is verified." :
    "No success has been confirmed. Check the recorded result before sending another command.";
  const stage = verified ? 3 : status?.boot_started_at || status?.status === "waiting" ? 2 : status?.status === "staged" ? 1 : 0;
  const StatusIcon = needsHelp ? AlertTriangle : verified ? CircleCheck : status?.status === "staged" ? Power : Clock;
  return <section className={`raid-operation storage-operation-focus is-${tone}`} aria-label="RAID operation progress">
    <header className="storage-operation-heading">
      <div className="storage-operation-identity"><StatusIcon size={28}/><div><span className="storage-operation-kicker">{status?.operation ? operationNames[status.operation] : "Storage operation"}</span><h3>{title}</h3></div></div>
      <span className="storage-operation-state">{needsHelp ? "Attention needed" : verified ? "Verified result" : status?.status === "staged" ? "Your action needed" : erasing ? "Erasing reported" : "Awaiting evidence"}</span>
    </header>
    <p className="storage-operation-summary">{detail}</p>
    <ol className="storage-operation-steps" aria-label="Operation stages">
      {["Request accepted","Power-on requested","Result verified"].map((label,i)=>{
        const unreported = i===1 && verified && !status?.boot_started_at;
        return <li key={label} className={unreported?"is-unreported":i<stage?"is-done":i===stage?"is-current":"is-upcoming"} aria-current={i===stage?"step":undefined}>
          <span className="storage-step-marker">{unreported?<Clock size={17}/>:i<stage?<Check size={17}/>:i+1}</span><div><strong>{unreported?"Power-on":i<stage?label:["Send request","Start server","Verify result"][i]}</strong><small>{unreported?"Not recorded":i<stage?"Recorded":i===stage?(needsHelp?"Needs attention":i===1?"Confirmation needed":i===2?"Verification pending":"Not confirmed"):"Not yet"}</small></div>
        </li>;
      })}
    </ol>
    {status && <p className="storage-evidence-time">{verified ? `Verified ${status.verified_at ? new Date(status.verified_at).toLocaleString() : "(time not reported)"} • Recorded result, not a live health check.` : status.submitted_at ? `Request submitted ${new Date(status.submitted_at).toLocaleString()}` : "Submission time not reported"}</p>}
    {progress && !verified && status?.operation!=="sanitize" && <p className="storage-live-progress" role="status">{progress}</p>}
    {error && <p role="alert" className="workflow-alert">{error}</p>}
    {error && !status && <button className="secondary-action" onClick={() => {setError("");setTick(t => t + 1);}}><RefreshCw size={17}/>Reload storage operation</button>}
    {status?.operation==="sanitize"&&<DiskEraseProgress status={status} checking={checking} monitoring={monitor} readError={!!error} disabled={disabled||open} onRefresh={()=>void verify()}/>}
    {status?.erase_recovery && !error && <div className="workflow-pending"><strong>Choose a different erase method</strong><p>{status.erase_recovery.message}</p>
      {onRetryErase && <button className="primary-action" disabled={disabled || checking || open} onClick={onRetryErase}>Set up another wipe attempt<ArrowRight size={17}/></button>}
    </div>}
    {!!status?.boot_blockers?.length && <div className="workflow-pending"><strong>Power-on is blocked</strong><ul>{status.boot_blockers.map(b => <li key={b}>{b}</li>)}</ul></div>}
    {(status?.operation!=="sanitize" || verified&&(onContinue||onReturn) || needsHelp&&onRecovery&&!status?.erase_recovery || status?.status==="staged")&&<div className="storage-operation-next"><strong>{verified&&!error?"Next step":needsHelp?"Action needed":status?.status==="staged"?"Next: confirm power-on":"Now: verify the hardware result"}</strong><div className="raid-operation-actions">
      {verified && !error && outcome && status?.operation && onContinue && <GuidePrimary><button className="primary-action" disabled={disabled || checking || open} onClick={()=>onContinue(status.operation!)}>{outcome.next}<ArrowRight size={17}/></button></GuidePrimary>}
      {verified && !error && !onContinue && onReturn && <button className="primary-action" disabled={checking || open} onClick={onReturn}>Back to storage setup<ArrowRight size={17}/></button>}
      {needsHelp && !status?.erase_recovery && onRecovery && <GuidePrimary><button className="primary-action" disabled={disabled || checking || open} onClick={onRecovery}><Wrench size={17}/>Open storage recovery</button></GuidePrimary>}
      {status?.status === "staged" && <button className="primary-action" disabled={disabled || checking || open || !!status.boot_blockers?.length} onClick={() => setOpen(true)}><Power size={17} />{status.operation === "sanitize" ? "Start server and begin erasure" : "Start server and verify RAID"}</button>}
      {!monitor && status?.status!=="staged" && status?.operation!=="sanitize" && <button className="secondary-action" disabled={disabled || checking || open} onClick={() => void verify()}><RefreshCw size={17} className={checking ? "spin" : undefined} />{checking ? "Reading storage status..." : "Check RAID result"}</button>}
      {monitor && status?.operation!=="sanitize" && <p role="status">Checking the hardware automatically. Completion has not been verified. Keep the server powered on.</p>}
    </div></div>}
    {status && <details className="storage-operation-details"><summary>Operation details</summary><p>{status.message}</p>{verified&&progress&&<p>{progress}</p>}{status.attempt_id&&<p>Operation ID: <code>{status.attempt_id}</code></p>}</details>}
    {status?.boot_started_at && !verified && status.status!=="failed" && <small className="storage-monitor-note">{status.operation === "sanitize" ? "Disk erasure can take hours. Read-only checks run while this page is open for up to 24 hours after power-on. Closing the page does not cancel erasure; reopen it to resume checking. Never interrupt power." : "Automatic read-only checks run while this page is open, for up to 20 minutes after power-on. Returning to the page resumes that window."}</small>}
    {open && <BootConfirmation profileId={profileId} deviceId={deviceId} onClose={() => { setOpen(false); setTick(t => t + 1); }} />}
  </section>;
}

function BootConfirmation({ profileId, deviceId, onClose }: { profileId: string; deviceId: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [review, setReview] = useState<RaidBootReview | null>(null);
  const [busy, setBusy] = useState(true);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [checks, setChecks] = useState<string[]>([]);
  useEffect(() => {
    let active = true; dialog.current?.showModal();
    api.previewRaidBoot(profileId, deviceId).then(r => { if (active) setReview(r); })
      .catch(e => { if (active) setError(e.message); }).finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [profileId, deviceId]);
  async function start() {
    if (!review || submitted) return;
    setBusy(true); setSubmitted(true);
    try {
      const r = await api.startRaidBoot(profileId, deviceId, { preview_id: review.preview_id, confirmation,
        pending_changes_reviewed: true, data_loss_confirmed: true, maintenance_confirmed: true });
      setMessage(r.message);
      if (r.status === "waiting") onClose();
    } catch (e) { setError(`${e instanceof Error ? e.message : String(e)} Do not retry power-on. Close this window to inspect the recorded status.`); }
    finally { setBusy(false); }
  }
  const acknowledgements = [
    "I reviewed the pending storage operation below and accept its data loss or configuration changes, including physical erasure if selected.",
    "I reviewed other pending server changes in iLO. No firmware update is in progress, and booting this server is safe.",
    "This is the correct server, backups are complete or not needed, and the maintenance window is approved.",
  ];
  return <dialog ref={dialog} className="firmware-upgrade-dialog raid-rebuild-dialog" aria-label="Start server for RAID" onCancel={e => { if (busy) e.preventDefault(); else onClose(); }}>
    <header><h2>{review?.operation === "sanitize" ? "Start server and erase physical disks" : "Start server and apply pending RAID"}</h2><button aria-label="Close power-on review" disabled={busy} onClick={onClose}><X size={20} /></button></header>
    <p>{busy && !review ? "Checking server identity, power state and pending RAID. No power request has been sent." : "Powering on can apply pending configuration and destroy access to the old RAID data. This is not just a connection check."}</p>
    {error && <p role="alert" className="workflow-alert">{error}</p>}{message && <p role="status" className="workflow-pending">{message}</p>}
    {review && <><h3>{review.name}</h3><p>Pending operation: {review.operation === "sanitize" ? "Irreversible physical-disk erasure. Maintain power until every drive is complete" : review.operation === "reset" ? "Reset storage controller" : review.operation === "clear" ? "Delete old RAID" : "Create new RAID"}. The app will send power-on once, then read back the result. It will not force a restart or automatically submit another storage operation.</p>
      {!!review.blockers.length && <ul className="workflow-pending">{review.blockers.map(b => <li key={b}>{b}</li>)}</ul>}
      <details><summary>Pending RAID and exact power command</summary><pre className="raid-payload">{JSON.stringify(review.pending_payload, null, 2)}</pre><p><code>{review.method} {review.path}</code></p><pre className="raid-payload">{JSON.stringify(review.payload, null, 2)}</pre></details>
      <fieldset className="raid-confirmations" disabled={busy || submitted || !review.apply_enabled}><legend>Confirm power-on</legend>
        {acknowledgements.map(label => <label key={label} className="workflow-checkbox"><input type="checkbox" checked={checks.includes(label)} onChange={e => setChecks(c => e.target.checked ? [...c, label] : c.filter(v => v !== label))} />{label}</label>)}
        <label className="workflow-field">Type <strong>{review.confirmation}</strong><input aria-label="Power-on confirmation phrase" autoComplete="off" value={confirmation} onChange={e => setConfirmation(e.target.value)} /></label>
      </fieldset>
      <footer><button className="primary-action" disabled={busy || submitted || !review.apply_enabled || checks.length !== acknowledgements.length || confirmation !== review.confirmation} onClick={() => void start()}><Power size={17} />{busy ? "Checking and starting..." : review.operation === "sanitize" ? "Confirm power-on and begin erasure" : "Confirm power-on and apply RAID"}</button>
        {submitted && <button className="secondary-action" disabled={busy} onClick={onClose}>Continue to verification</button>}</footer>
    </>}
  </dialog>;
}
