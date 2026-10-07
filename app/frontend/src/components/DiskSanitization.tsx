import {useEffect, useImperativeHandle, useRef, useState, type Ref} from "react";
import {AlertTriangle, ArrowLeft, ArrowRight, BookOpen, Download, Eraser, FilePlus2, ShieldCheck, X} from "lucide-react";
import {api, eraseMethodLabel, type RaidRebuildReview, type EraseMethod, type EraseOptions} from "../api";
import {ShutdownForReset} from "./ShutdownForReset";
import {RaidOperation} from "./RaidOperation";

export type DiskSanitizationHandle = {open:()=>void};
const HPE_ERASE_REFERENCE = "https://developer.hpe.com/blog/storage-management-with-redfish/";

export function DiskSanitization({profileId, deviceId, disabled, onBusy, onChanged, onDeleteArrays, actionRef, contextual=false, onShowOperation, operationPending=false}: {
  profileId:string; deviceId:string; disabled:boolean; onBusy:(busy:boolean)=>void; onChanged:()=>void;
  onDeleteArrays?:()=>void;
  actionRef?:Ref<DiskSanitizationHandle>; contextual?:boolean; onShowOperation?:()=>void; operationPending?:boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const readVersion = useRef(0);
  const [review, setReview] = useState<RaidRebuildReview|null>(null);
  const [method,setMethod]=useState<EraseMethod|"auto">("auto");
  const [reviewMethod,setReviewMethod]=useState<EraseMethod|"auto">("auto");
  const [readingReview,setReadingReview]=useState(false);
  const [readStarted,setReadStarted]=useState(0);
  const [now,setNow]=useState(Date.now());
  const [options,setOptions]=useState<EraseOptions|null>(null);
  const [readAt, setReadAt] = useState(0);
  const [open, setOpen] = useState(false);
  const [requestBusy, setBusy] = useState(false);
  const [powerBusy, setPowerBusy] = useState(false);
  const busy = requestBusy || powerBusy;
  const [step,setStep]=useState<"overview"|"prepare"|"shutdown"|"authorization"|"confirm">("overview");
  const [submitted, setSubmitted] = useState(false);
  const [settled,setSettled]=useState(false);
  const [checks, setChecks] = useState<string[]>([]);
  const [phrase, setPhrase] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [sources, setSources] = useState<Record<string,string>>({});
  const [sharedSource,setSharedSource]=useState("");
  const [separateSources,setSeparateSources]=useState(false);
  const [authorizationPhrase, setAuthorizationPhrase] = useState("");
  const [supportReviewed, setSupportReviewed] = useState(false);
  const overwriteCount = review?.drives?.filter(d=>d.erase_pattern==="SanitizeRestrictedOverwrite" || d.erase_pattern==="OnePass").length || 0;
  const blockEraseCount = review?.drives?.filter(d=>d.erase_pattern==="SanitizeRestrictedBlockErase").length || 0;
  const needsAuthorization = !!review && (!review.authorization_expires_at || !!review.preparation?.support_review_bays.length);
  const reviewExpired=!!review?.expires_at && now>=Date.parse(review.expires_at);
  const sourceFor=(identity:string)=>separateSources?sources[identity]||"":sharedSource;
  const missingSources=(review?.drives||[]).filter(d=>sourceFor(d.identity).trim().length<10).length;
  const invalidSources=(review?.drives||[]).some(d=>sourceFor(d.identity).trim().length>2000);
  const authorizationProblem=!review?.drives?.length?"No identified disks are available."
    :review.drives.some(d=>!d.identity||!d.erase_pattern)?"A disk identity or erase method is missing. Refresh the hardware check."
    :missingSources?separateSources?`Add a vendor reference and applicability notes for ${missingSources} ${missingSources===1?"disk":"disks"}.`:"Required: add a vendor reference and applicability notes in the highlighted field."
    :invalidSources?"Keep each reference and its notes within 2,000 characters."
    :!supportReviewed?"Confirm that the reference covers every listed disk and its planned method."
    :authorizationPhrase!==`AUTHORIZE ERASURE ${review.name}`?"Enter the authorization phrase exactly as shown.":"";
  useEffect(() => {onBusy(open || busy); return () => onBusy(false);}, [open, busy, onBusy]);
  useEffect(()=>()=>{readVersion.current++;},[]);
  useEffect(()=>{if(!open)return;const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[open]);
  useEffect(()=>{if(open){dialog.current?.scrollTo({top:0});heading.current?.focus({preventScroll:true});}},[open,step,submitted]);
  useImperativeHandle(actionRef,()=>({open:()=>{if(!disabled&&!busy&&!open)void preview("auto");}}));
  const acknowledgements = [
    ["loss", "I approve permanent data loss on every listed disk. Backups are verified or the data is no longer needed."],
    ["review", "I reviewed these disks, their health and supported erase methods. No known failed disks are included. I will maintain power until every disk is verified."],
  ];
  async function preview(selected:EraseMethod|"auto"=method, destination:"overview"|"prepare"="overview") {
    const version=++readVersion.current;
    setMethod(selected);setOptions(null);
    setReadingReview(true);setReadStarted(Date.now());
    setOpen(true); dialog.current?.showModal(); setBusy(true); setReview(null); setSubmitted(false); setSettled(false);
    setStep(destination);
    setChecks([]); setPhrase(""); setError(""); setMessage("");
    setSupportReviewed(false); setAuthorizationPhrase("");
    try {
      const fresh=await api.previewRaidRebuild(profileId, deviceId, "sanitize",selected);
      if(version!==readVersion.current)return;
      setReview(fresh);setReviewMethod(selected);setOptions(fresh.erase_options || null);setReadAt(Date.now());setNow(Date.now());
    }
    catch (e) {
      if(version!==readVersion.current)return;
      setError(e instanceof Error ? e.message : String(e));
      try {const catalog=await api.eraseOptions(profileId,deviceId);if(version===readVersion.current)setOptions(catalog);} catch { /* Preserve the original readiness error. */ }
    }
    finally {if(version===readVersion.current){setBusy(false);setReadingReview(false);}}
  }
  async function apply() {
    if (!review || reviewExpired || method!==reviewMethod || !review.apply_enabled || checks.length !== acknowledgements.length || phrase !== review.confirmation) return;
    setSubmitted(true); setBusy(true); setError("");
    try {
      const result = await api.applyRaidRebuild(profileId, deviceId, {preview_id:review.preview_id, confirmation:phrase,
        data_loss_confirmed:true, backups_confirmed:true, health_reviewed:true, firmware_reviewed:true,
        empty_bays_confirmed:[], physical_erase_confirmed:true});
      setMessage(result.status === "pending" ? "Erasure staged, not completed. Confirm power-on below to begin. Keep power on while erasure runs." : result.message);
    } catch (e) {setError(`${e instanceof Error ? e.message : String(e)} The outcome may be uncertain. Do not resubmit; check the recorded operation.`);}
    finally {setBusy(false); setSettled(true); onChanged();}
  }
  async function refreshAfterPowerOff() {
    setBusy(true); setChecks([]); setPhrase(""); setError("");
    setReview(r => r ? {...r,apply_enabled:false} : r);
    try {
      const fresh=await api.previewRaidRebuild(profileId, deviceId, "sanitize",method);
      setOptions(fresh.erase_options || null);
      setReview(fresh);setReadAt(Date.now());setStep("prepare");
      setMessage(fresh.power==="Off"?"Server is off. Disk readiness has been refreshed.":"Power state changed. Review the latest reading before continuing.");
    }
    catch(e) {setError(e instanceof Error ? e.message : String(e));}
    finally {setBusy(false);}
  }
  async function authorize() {
    if (!review || reviewExpired || authorizationProblem) return;
    setBusy(true); setError("");
    try {
      const result = await api.authorizeSanitization(profileId, deviceId, {
        preview_id:review.preview_id, confirmation:authorizationPhrase,
        vendor_support_reviewed:true, sources:Object.fromEntries((review.drives || []).map(d => [d.identity,sourceFor(d.identity)]))});
      setMessage(result.message); setChecks([]); setPhrase("");
      const fresh=await api.previewRaidRebuild(profileId, deviceId, "sanitize",method);
      setReview(fresh);setOptions(fresh.erase_options || null);
      setReadAt(Date.now());
      setStep("prepare");
      setAuthorizationPhrase(""); setSupportReviewed(false);
    } catch (e) {setError(e instanceof Error ? e.message : String(e));}
    finally {setBusy(false);}
  }
  function close() {
    if(busy&&!readingReview)return;
    readVersion.current++;setReadingReview(false);setBusy(false);
    dialog.current?.close();setOpen(false);onChanged();
  }
  async function report() {
    setBusy(true); setError(""); setMessage("");
    try {
      const data = await api.sanitizationReport(profileId, deviceId);
      if (data.status === "not_started") {setMessage(data.message); return;}
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type:"application/json"}));
      const a = document.createElement("a"); a.href = url; a.download = `disk-erasure-${profileId}-${deviceId}.json`; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {setError(e instanceof Error ? e.message : String(e));}
    finally {setBusy(false);}
  }
  const methodPicker = options && <section className="erase-options" aria-label="Erase method choices">
    <fieldset disabled={busy}><legend>Erase method</legend>
      {options.options.map(option=><label className="erase-option" key={option.id}>
        <input type="radio" name="erase-method" checked={option.id===method} disabled={!option.selectable}
          onChange={()=>{setMethod(option.id as EraseMethod|"auto");setSources({});setSharedSource("");setChecks([]);setPhrase("");setSupportReviewed(false);setAuthorizationPhrase("");}}/>
        <span><strong>{option.label}{!option.selectable && <small> - {option.status}</small>}</strong>
          <span>{option.selectable?option.speed:option.reason}</span>
          {option.selectable&&<small>{option.protection}</small>}
        </span>
      </label>)}
    </fieldset>
    <p className="erase-method-note">Next checks your selection against this server. Nothing is erased until you confirm the wipe and power-on.</p>
  </section>;
  const stageIndex=submitted?3:step==="overview"?0:step==="confirm"?2:1;
  function nextPreparation() {
    if(!review)return;
    if(reviewExpired || method!==reviewMethod){void preview(method,"prepare");return;}
    if(review.power!=="Off")setStep("shutdown");
    else if(review.arrays_present && onDeleteArrays){close();onDeleteArrays();}
    else if(needsAuthorization)setStep("authorization");
    else if(review.apply_enabled)setStep("confirm");
    else void preview(method,"prepare");
  }
  function addHpeReference() {
    // A procedure link is a starting reference, never an automatic support approval.
    setSharedSource(value=>[value.trim(),`HPE erase procedure: ${HPE_ERASE_REFERENCE}`].filter(Boolean).join("\n\n"));
    setSupportReviewed(false);
  }
  return <>{!contextual && <section className="disk-sanitization" aria-label="Physical-disk sanitization">
    <header><Eraser size={22}/><div><h3>Physical-disk sanitization</h3><p>Erase disk contents before rebuilding arrays. RAID deletion alone does not wipe disks.</p></div></header>
    <p className="workflow-alert"><AlertTriangle size={18}/>Irreversible. Existing arrays must first be removed and verified. Includes all detected disks on the reviewed controller; other boot devices are outside this operation.</p>
    <div className="sanitize-controls"><button className="secondary-action" disabled={disabled || busy || open} onClick={() => void preview()}><Eraser size={17}/>Review all disks for erasure</button>
    <button className="secondary-action" disabled={busy || open} onClick={() => void report()}><Download size={17}/>Erasure report</button></div>
    {disabled && <p>{operationPending ? "A previous storage operation must finish before a new erase request." : "A check or confirmation is open. Finish or close it before starting an erase review."}</p>}
    {operationPending && onShowOperation && <button className="secondary-action" onClick={onShowOperation}>Go to current storage operation</button>}
    {!open && error && <p role="alert" className="workflow-alert">{error}</p>}
    {!open && message && <p role="status">{message}</p>}
    </section>}
    <dialog ref={dialog} className="firmware-upgrade-dialog raid-rebuild-dialog sanitize-dialog" aria-label="Confirm physical-disk erasure" onCancel={e => {e.preventDefault(); close();}}>
      <header><h2>Disk wipe setup</h2><button aria-label="Close erase review" disabled={busy&&!readingReview} onClick={close}><X size={20}/></button></header>
      <ol className="erase-wizard-steps" aria-label="Wipe setup steps">{["Choose method","Prepare server","Confirm wipe","Progress"].map((label,i)=><li key={label} aria-current={i===stageIndex?"step":undefined}><span>{i+1}</span>{label}</li>)}</ol>
      <h3 ref={heading} tabIndex={-1} className="erase-wizard-title">Step {stageIndex+1} of 4: {submitted?"Progress":step==="overview"?"Choose an erase method":step==="shutdown"?"Shut down the server":step==="authorization"?"Approve erase support":step==="confirm"?"Confirm drive wipe":"Prepare the server"}</h3>
      {requestBusy && !settled && <p className="storage-live-progress" role="status">{submitted ? "Sending wipe request. Erasure is not yet confirmed. Do not retry." : readingReview ? `Reading this server's disks and controller (${Math.max(0,Math.floor((now-readStarted)/1000))} seconds). This can take up to three minutes. You can cancel waiting; no wipe request is sent.` : "Saving approval or refreshing server readiness. No wipe request is being sent."}</p>}
      {error && <p role="alert" className="workflow-alert">{error}</p>}{message && <p role="status">{message}</p>}
      {!submitted && !review && step==="overview" && methodPicker}
      {settled&&<><RaidOperation profileId={profileId} deviceId={deviceId} revision={0} disabled={false} onActive={()=>{}} onBusy={setBusy} onVerified={()=>{}} onReturn={close} onRetryErase={()=>void preview("auto")}/><button className="secondary-action" disabled={busy} onClick={()=>void report()}><Download size={17}/>Erasure report</button></>}
      {review && !submitted && <><p className="erase-target"><strong>{review.name}</strong><span>{review.host} · {review.drives?.length || 0} disks</span></p>
        {(step==="authorization"||step==="confirm")&&<p className="storage-live-progress" role="status"><strong>No wipe request sent.</strong> {step==="authorization"?"Next: approve erase support.":"Next: confirm permanent data loss."}</p>}
        {step==="overview" && <>
          <p>Select a method for these disks. No wipe request has been sent.</p>
          {method===reviewMethod&&<section className="erase-method-summary" aria-label="Selected erase method">
            {!!overwriteCount && <p><strong>{overwriteCount} {overwriteCount===1?"disk":"disks"}: full overwrite</strong><span>Can take hours. This is not a quick erase.</span></p>}
            {!!blockEraseCount && <p><strong>{blockEraseCount} {blockEraseCount===1?"disk":"disks"}: SSD block erase</strong><span>Duration depends on the drive and firmware.</span></p>}
          </section>}
          {methodPicker}
        </>}
        {step==="prepare" && <>
          <p className="workflow-alert"><AlertTriangle size={18}/>Physical erasure is irreversible. All listed disks will lose their data.</p>
          <section className={`erase-next-action${review.apply_enabled?" is-ready":""}`} aria-label="Wipe readiness"><h3>{review.apply_enabled?"Ready for wipe confirmation":"Preparation required: erasure has not started"}</h3>
            {!!review.preparation?.raw_bays.length && <p>{review.raw_preparation?.assignment_verified
              ? `Disk assignment check passed: ${review.preparation.raw_bays.length} unassigned disks. No controller-mode conversion is needed.`
              : `${review.preparation.raw_bays.length} Raw disks need their assignment checked. ${review.raw_preparation?.blockers[0] || "Refresh disk readiness to check controller mode and array membership."}`}</p>}
            {review.arrays_present && <p>Existing RAID arrays must be deleted and verified first.</p>}
            {(!review.authorization_expires_at || !!review.preparation?.support_review_bays.length) && <p>Erase support must be reviewed for this server.</p>}
            {review.power!=="Off" && <p>Shut down the server before sending the wipe request.</p>}
            {!review.apply_enabled && review.power==="Off" && !review.arrays_present && !needsAuthorization && <p>{review.blockers[0] || "Readiness could not be confirmed. Recheck the server before continuing."}</p>}
            {!!review.blockers.length && <details><summary>All readiness issues</summary><ul>{Array.from(new Set([
              ...review.blockers.filter(b=>!b.startsWith("Bay ")),
              ...(review.drives || []).flatMap(d=>d.blockers || []),
            ])).map(b=><li key={b}>{b}</li>)}</ul></details>}
          </section>
          <p className="erase-next-description"><strong>Next:</strong> {review.power!=="Off"?"Confirm a shutdown request. No disks will be erased.":review.arrays_present?"Open RAID deletion, then return to this wizard after the deletion is verified.":needsAuthorization?"Review firmware and erase-method support for these disks.":review.apply_enabled?"Review the final data-loss confirmation.":"Recheck the unresolved requirements above. No changes will be sent."}</p>
        </>}
        {step==="shutdown" && <ShutdownForReset profileId={profileId} deviceId={deviceId} context="erase" initialPower={review.power} initialPowerAt={readAt} disabled={requestBusy} onBusy={setPowerBusy} onPowerOff={() => void refreshAfterPowerOff()}/>}
        {(step==="overview" || step==="confirm") && <details open={step==="confirm"} className="erase-disk-scope"><summary>Disks included ({review.drives?.length || 0})</summary>
          <div className="sanitize-drive-list">{review.drives?.map(d=><article key={d.path || d.identity || d.bay}><strong>Bay {d.bay}</strong><span>{d.model} / {Math.round(d.capacity_bytes/1e9)} GB / {d.media}</span><span>Planned method: {eraseMethodLabel(d.erase_pattern)}</span></article>)}</div>
          <p>{review.scope_note}</p>
        </details>}
        {step==="authorization" && <section aria-label="Erase authorization">
          {!separateSources&&<label className={`workflow-field erase-reference-field${missingSources?" is-required":""}`}>Vendor reference and applicability notes for all listed disks (required)<textarea required aria-invalid={!!missingSources} aria-describedby="erase-reference-help" placeholder="Vendor document URL or support-case number, plus why it covers these disks, firmware and erase method." maxLength={2000} disabled={busy} value={sharedSource} onChange={e=>{setSharedSource(e.target.value);setSupportReviewed(false);}}/></label>}
          {separateSources&&review.drives?.map(d => <label className={`workflow-field erase-reference-field${sourceFor(d.identity).trim().length<10?" is-required":""}`} key={d.path || d.bay}>Bay {d.bay}: vendor reference and applicability notes (required)
            <textarea required aria-invalid={sourceFor(d.identity).trim().length<10} aria-describedby="erase-reference-help" placeholder="Vendor reference and applicability to this disk, firmware and method." maxLength={2000} disabled={busy || !d.identity} value={sources[d.identity] || ""} onChange={e => {setSources(v => ({...v,[d.identity]:e.target.value}));setSupportReviewed(false);}}/>
          </label>)}
          <section className="erase-support-reference" aria-label="HPE erase documentation">
            <a href={HPE_ERASE_REFERENCE} target="_blank" rel="noreferrer"><BookOpen size={18}/>Read HPE documentation (opens a new tab)</a>
            {!separateSources&&<button className="secondary-action" disabled={busy || sharedSource.includes(HPE_ERASE_REFERENCE) || sharedSource.length+HPE_ERASE_REFERENCE.length+24>2000} onClick={addHpeReference}><FilePlus2 size={17}/>Add HPE reference</button>}
          </section>
          <p id="erase-reference-help" className="erase-reference-help">HPE documents the erase procedure. It does not certify support for your exact disk and controller firmware. Add applicable vendor guidance or support-case notes; do not approve unknown support.</p>
          <label className="workflow-checkbox"><input type="checkbox" disabled={busy} checked={separateSources} onChange={e=>{setSeparateSources(e.target.checked);setSupportReviewed(false);}}/>Use a different reference for each disk</label>
          <label className="workflow-checkbox"><input type="checkbox" disabled={busy} checked={supportReviewed} onChange={e => setSupportReviewed(e.target.checked)}/>I reviewed vendor support for every listed disk, its firmware, controller and selected method, and authorize physical erasure on this server only.</label>
          <label className="workflow-field">Type <strong>AUTHORIZE ERASURE {review.name}</strong><input disabled={busy} value={authorizationPhrase} onChange={e => setAuthorizationPhrase(e.target.value)}/></label>
          <details><summary>Hardware covered by this approval ({review.drives?.length || 0} disks)</summary><p>{review.controller} / Firmware: {review.capability_context?.controller_firmware || "Not reported"}</p><ul>{review.drives?.map(d=><li key={d.identity}>Bay {d.bay}: {d.model} / Firmware: {d.firmware || "Not reported"} / {eraseMethodLabel(d.erase_pattern)}</li>)}</ul></details>
        </section>}
        {step==="confirm" && <><fieldset className="raid-confirmations" disabled={busy || submitted || !review.apply_enabled}><legend>Approve irreversible data loss</legend>
          {acknowledgements.map(([id, label]) => <label className="workflow-checkbox" key={id}><input type="checkbox" checked={checks.includes(id)} onChange={e => setChecks(c => e.target.checked ? [...c,id] : c.filter(v => v !== id))}/>{label}</label>)}
          <label className="workflow-field">Type <strong>{review.confirmation}</strong><input aria-label="Physical erasure confirmation phrase" autoComplete="off" value={phrase} onChange={e => setPhrase(e.target.value)}/></label>
        </fieldset>
        <p>Confirm wipe request sends the settings now. Power-on needs a separate confirmation. Keep power on until erasure is verified.</p></>}
        <details className="erase-technical"><summary>Technical details</summary><p>{review.controller}</p><p>{review.assurance}</p>
          {review.raw_preparation && <p>Controller mode: {review.raw_preparation.controller_mode || "Not reported"}. Assignment checks do not establish firmware/method compatibility. <a href="https://github.com/HewlettPackard/python-redfish-utility/blob/master/ilorest/extensions/SMART_ARRAY_COMMANDS/DriveSanitizeCommand.py" target="_blank" rel="noreferrer">HPE iLO 5 erase workflow</a></p>}
          <code>{review.method} {review.path}</code><pre className="raid-payload">{JSON.stringify(review.payload,null,2)}</pre></details>
      </>}
      {!submitted&&reviewExpired&&<p role="status" className="workflow-pending">The hardware check expired. Refresh it before continuing; your reference notes are kept.</p>}
      {!submitted&&<footer className="erase-wizard-footer">
        {step==="authorization"&&review&&!reviewExpired&&authorizationProblem&&<p role="status" id="erase-approval-problem" className="erase-approval-help"><AlertTriangle size={17}/>{authorizationProblem}</p>}
        <button className="secondary-action" disabled={busy&&!readingReview} onClick={()=>{if(step==="overview"||readingReview)close();else {setError("");setMessage("");setStep(step==="prepare"?"overview":"prepare");}}}>{step!=="overview"&&!readingReview&&<ArrowLeft size={17}/>} {step==="overview"||readingReview?"Cancel":"Back"}</button>
        {!busy&&(!review||reviewExpired)&&<button className="primary-action" onClick={()=>void preview(method,step==="overview"?"overview":"prepare")}>{reviewExpired?"Refresh check":"Retry check"}<ArrowRight size={17}/></button>}
        {(step==="overview"||step==="prepare")&&review&&!reviewExpired&&<button className="primary-action" disabled={busy} onClick={()=>step==="overview"?(method===reviewMethod?setStep("prepare"):void preview(method,"prepare")):nextPreparation()}>{step==="prepare"&&review.power==="Off"&&!review.arrays_present&&!needsAuthorization&&!review.apply_enabled?"Retry checks":"Next"}<ArrowRight size={17}/></button>}
        {step==="authorization"&&review&&!reviewExpired&&<button className="primary-action" aria-describedby={authorizationProblem?"erase-approval-problem":undefined} disabled={busy || !!authorizationProblem} onClick={() => void authorize()}><ShieldCheck size={17}/>Save and Next<ArrowRight size={17}/></button>}
        {step==="confirm"&&!reviewExpired&&<button className="primary-action" disabled={busy||!review?.apply_enabled||checks.length!==acknowledgements.length||phrase!==review.confirmation} onClick={()=>void apply()}><Eraser size={17}/>Confirm wipe request</button>}
      </footer>}
    </dialog>
  </>;
}
