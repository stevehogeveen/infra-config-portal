import {useEffect,useRef,useState} from "react";
import {AlertTriangle,Upload,X,ArrowRight,LoaderCircle} from "lucide-react";
import {api,type RaidRebuildReview as Review} from "../api";
import {RaidOperation} from "./RaidOperation";

export function RaidRebuildReview({profileId,deviceId,operation,onClose,onRecovery}:{profileId:string;deviceId:string;operation:"clear"|"create"|"reset";onClose:()=>void;onRecovery?:()=>void}) {
  const dialog=useRef<HTMLDialogElement>(null);
  const [review,setReview]=useState<Review|null>(null);
  const [busy,setBusy]=useState(true);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const [submitted,setSubmitted]=useState(false);
  const [settled,setSettled]=useState(false);
  const [resultStatus,setResultStatus]=useState("");
  const outcome=useRef<HTMLElement>(null);
  useEffect(()=>{if(submitted)outcome.current?.scrollIntoView({block:"start"});},[submitted,settled]);
  const [confirmation,setConfirmation]=useState("");
  const [checks,setChecks]=useState<string[]>([]);
  useEffect(()=>{let active=true;dialog.current?.showModal();api.previewRaidRebuild(profileId,deviceId,operation).then(r=>{if(active)setReview(r);}).catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setBusy(false);});return()=>{active=false;};},[profileId,deviceId,operation]);
  const acknowledgements=[
    ["backup","Backups are complete and verified, or this server's existing data is no longer required."],
    ["loss",operation === "reset" ? "I approve resetting the storage controller, losing all its arrays, data access and custom controller settings." : "I approve permanent loss of access to the reviewed RAID volumes and their data."],
    ["health","I have investigated the reported hardware warnings; no known failed physical drive will be used."],
    ["firmware","HPE firmware prerequisites and storage compatibility have been reviewed for this operation."],
    ...(review?.empty_bays.length?[["empty",`I physically confirmed these empty bays: ${review.empty_bays.join(", ")}. If a drive is present, stop and diagnose it.`]]:[]),
  ];
  async function apply(){if(!review||busy||submitted)return;setBusy(true);setSubmitted(true);setError("");try{const result=await api.applyRaidRebuild(profileId,deviceId,{preview_id:review.preview_id,confirmation,data_loss_confirmed:true,backups_confirmed:true,health_reviewed:true,firmware_reviewed:true,empty_bays_confirmed:review.empty_bays});setResultStatus(result.status);setMessage(result.message);}catch(e){setError(`${e instanceof Error?e.message:String(e)} Do not retry blindly. Read the server's pending configuration before creating a new preview.`);}finally{setBusy(false);setSettled(true);}}
  return <dialog ref={dialog} className="firmware-upgrade-dialog raid-rebuild-dialog" aria-label="Review RAID rebuild" onCancel={e=>{if(busy)e.preventDefault();else onClose();}}>
    <header><div><h2>{submitted?"RAID operation progress":operation==="reset"?"Confirm storage controller reset":operation==="clear"?"Confirm RAID deletion":"Confirm RAID creation"}</h2><p>{submitted?"The storage request is sent once. Power-on requires a separate confirmation.":busy&&!review?"Reading this server. No storage write has been sent.":"Nothing has been changed. Confirmation stages the operation for the next server boot; no automatic reboot."}</p></div><button aria-label="Close RAID review" disabled={busy} onClick={onClose}><X size={20}/></button></header>
    {submitted&&<section ref={outcome} className="raid-submit-outcome" aria-label="Storage request result" role="status">
      <h3>{!settled?<><LoaderCircle className="spin" size={20}/>Sending storage request...</>:resultStatus==="pending"?"Request accepted: waiting for server power-on":"Submission needs attention"}</h3>
      <p>{!settled?"Waiting for the controller response. Do not close this window or submit again.":resultStatus==="pending"?"The controller accepted the settings. The RAID change has NOT been verified yet. Continue below to confirm power-on and apply the pending change.":"The outcome is not confirmed. Check the recorded status below; do not send the storage command again."}</p>
    </section>}
    {error&&<p role="alert" className="workflow-alert">{error}</p>}{message&&<p role="status" className="workflow-pending">{message}</p>}
    {settled&&<RaidOperation profileId={profileId} deviceId={deviceId} revision={0} disabled={false} onActive={()=>{}} onBusy={setBusy} onVerified={()=>{}} onReturn={onClose}/>}
    {review&&!submitted&&<>
      <dl className="upgrade-target"><div><dt>Server / iLO</dt><dd>{review.name} / {review.host}</dd></div><div><dt>Controller</dt><dd>{review.controller}</dd></div></dl>
      <p className="workflow-alert"><AlertTriangle size={18}/> {operation==="reset"?"Removes all arrays and custom storage-controller settings. Does not reset iLO, securely erase disks, or prove that cache and hardware faults are repaired.":operation==="clear"?"Deletes every logical volume and clears RAID configuration metadata on this controller. This does not securely erase physical drives.":"Creates the saved arrays on the verified empty controller. Unselected drives stay unassigned."}</p>
      {!!review.blockers.length&&<section className="workflow-pending"><h3>Action needed before deletion or creation</h3><ul>{review.blockers.map(b=><li key={b}>{b}</li>)}</ul>{onRecovery&&<><p>Continue with the shutdown and controller-reset controls. Opening recovery does not change the server.</p><button className="primary-action" disabled={busy||submitted} onClick={onRecovery}>Open guided storage recovery<ArrowRight size={18}/></button></>}</section>}
      {!!review.warnings.length&&<details><summary>Hardware warnings ({review.warnings.length})</summary><ul>{review.warnings.map(w=><li key={w}>{w}</li>)}</ul></details>}
      {operation!=="create"&&<><h3>Volumes to remove</h3><ul>{review.volumes.map(v=><li key={v.id}>{v.name} / {v.raid} / {Math.round(v.capacity_bytes/1e9)} GB</li>)}</ul></>}
      <h3>Exact operation</h3><p><code>{review.method} {review.path}</code></p><pre className="raid-payload">{JSON.stringify(review.payload,null,2)}</pre>
      <fieldset disabled={busy||submitted||!review.apply_enabled} className="raid-confirmations"><legend>Confirm this operation</legend>{acknowledgements.map(([key,label])=><label className="workflow-checkbox" key={key}><input type="checkbox" checked={checks.includes(key)} onChange={e=>setChecks(c=>e.target.checked?[...c,key]:c.filter(k=>k!==key))}/>{label}</label>)}<label className="workflow-field">Type <strong>{review.confirmation}</strong><input aria-label="RAID confirmation phrase" autoComplete="off" value={confirmation} onChange={e=>setConfirmation(e.target.value)}/></label></fieldset>
      <footer><button className="primary-action" disabled={busy||submitted||!review.apply_enabled||checks.length!==acknowledgements.length||confirmation!==review.confirmation} onClick={()=>void apply()}><Upload size={16}/>{operation==="reset"?"Confirm and stage controller reset":operation==="clear"?"Confirm and stage RAID deletion":"Confirm and stage RAID creation"}</button><p>After staging, review pending settings in iLO before the next power-on. Let HPE complete POST, then check the applied RAID after restart. A timeout must never be treated as a failed write that is safe to retry.</p></footer>
    </>}
  </dialog>;
}
