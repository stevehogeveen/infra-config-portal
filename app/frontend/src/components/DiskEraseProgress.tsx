import {useEffect, useState} from "react";
import {AlertTriangle, CheckCircle2, Clock, HardDrive, LoaderCircle, Power, RefreshCw} from "lucide-react";
import {eraseMethodLabel, type RaidOperationStatus} from "../api";

function duration(milliseconds:number) {
  const minutes=Math.max(0,Math.floor(milliseconds/60000));
  return minutes<1?"less than a minute":minutes<60?`${minutes} min`:`${Math.floor(minutes/60)} hr ${minutes%60} min`;
}

export function DiskEraseProgress({status, checking, monitoring, readError, disabled, onRefresh}: {
  status:RaidOperationStatus; checking:boolean; monitoring:boolean; readError:boolean; disabled:boolean; onRefresh:()=>void;
}) {
  const [now,setNow]=useState(Date.now());
  useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),10000);return()=>clearInterval(timer);},[]);
  const reading=status.sanitization;
  const drives=reading?.drives ?? status.erase_scope ?? [];
  const checkedAt=Date.parse(reading?.checked_at || "");
  const stale=readError || (Number.isFinite(checkedAt)&&now-checkedAt>120000);
  const completed=drives.filter(d=>d.status==="completed").length;
  const erasing=drives.filter(d=>d.status==="erasing").length;
  const queued=drives.filter(d=>d.status==="queued").length;
  const failed=drives.filter(d=>d.status==="failed").length;
  const unconfirmed=drives.length-completed-erasing-queued-failed;
  const controllerErrors=reading?.controller_errors || [];
  const bootAt=Date.parse(status.boot_started_at || "");
  // One note shared by every disk is said once, above the list, instead of six times.
  const sharedNote=drives.length>1&&drives[0].progress_note&&drives.every(d=>d.progress_note===drives[0].progress_note)?drives[0].progress_note:null;
  return <section className={`disk-erase-progress${stale?" is-stale":""}`} aria-label="Disk wipe progress">
    <header><h4><HardDrive size={20}/>Disk wipe progress</h4><strong>{completed} of {drives.length} disks verified</strong>
      {!monitoring&&status.status!=="staged"&&<button className="secondary-action" disabled={disabled||checking} onClick={onRefresh}><RefreshCw size={17} className={checking?"spin":undefined}/>{checking?"Reading disk progress...":"Check every disk's erase result"}</button>}
    </header>
    {!!controllerErrors.length&&<div className="erase-progress-error" role="alert"><AlertTriangle size={20}/><div>
      <strong>{controllerErrors.some(e=>e.endsWith(".PropertyValueEnumNotInList"))?"Controller rejected an erase setting":"Controller reported an erase error"}</strong>
      <p>{erasing||queued?"Some disks still report active work. Keep power on; do not submit another wipe.":status.erase_recovery?"This attempt failed before confirmed erase activity. Set up a new attempt with a different method below.":"No successful wipe is confirmed. Do not rebuild arrays or submit another wipe."}</p>
      <details><summary>Controller error details</summary><ul>{controllerErrors.map(e=><li key={e}><code>{e}</code></li>)}</ul></details>
    </div></div>}
    {drives.length>0&&<><progress className="erase-total-progress" aria-label="Verified disks" value={completed} max={drives.length}/>
      <p className="erase-progress-counts">{erasing} erasing <span>/</span> {queued} queued <span>/</span> {failed} failed <span>/</span> {unconfirmed} not confirmed</p></>}
    <div className="erase-progress-reading">
      <span><Power size={16}/>Power at last check: <strong>{reading?.power || "Not read"}</strong></span>
      <span><Clock size={16}/>{Number.isFinite(checkedAt)?`Last read ${new Date(checkedAt).toLocaleTimeString()}`:"Waiting for the first disk reading"}</span>
      {status.status!=="verified"&&Number.isFinite(bootAt)&&<span>Since power-on request: {duration(now-bootAt)}</span>}
    </div>
    {readError?<p className="erase-progress-warning" role="status">Live update unavailable. Any readings below are last known, not current progress.</p>
      :stale?<p className="erase-progress-warning" role="status">Reading is {duration(now-checkedAt)} old. Current progress has not been confirmed.</p>:null}
    <p className="erase-monitor-status" role="status">{checking?"Reading disk progress from iLO...":monitoring?"Automatic disk checks are running while this page is open.":status.status==="staged"?"Waiting for your power-on confirmation. Erasure has not been verified.":status.status==="verified"?"Recorded completion evidence for this operation.":"A fresh disk check is read-only. It does not send erase or power commands."}</p>
    {!drives.length&&<p>The disk list has not been returned. No disk completion can be assumed.</p>}
    {sharedNote&&<p className="erase-progress-shared-note">Applies to every disk below: {sharedNote}</p>}
    <ol className="erase-progress-drives">{drives.map(d=>{
      const state=d.status || (status.status==="staged"?"awaiting_power":"unverified");
      const label=state==="completed"?"Verified erased":state==="erasing"?"Erasing":state==="queued"?"Queued":state==="failed"?"Failed":state==="awaiting_power"?"Awaiting power-on":"Not confirmed";
      const percent=(state==="erasing"||state==="completed")&&typeof d.percent==="number"&&Number.isFinite(d.percent)&&d.percent>=0&&d.percent<=100?d.percent:null;
      const Icon=state==="completed"?CheckCircle2:state==="failed"?AlertTriangle:state==="erasing"?LoaderCircle:Clock;
      return <li key={d.identity || d.bay} className={`erase-drive-row is-${state}`}>
        <div className="erase-drive-identity"><strong>Bay {d.bay}</strong><span>{d.model}{d.capacity_bytes>0?` / ${Math.round(d.capacity_bytes/1e9)} GB`:""} / {d.media}</span><small>{eraseMethodLabel(d.erase_pattern)}</small></div>
        <div className="erase-drive-status"><strong><Icon size={18}/>{stale&&state==="erasing"?"Last reported: erasing":label}{percent!==null&&<span>{percent}%</span>}</strong>
          {percent!==null?<progress aria-label={`Erase progress bay ${d.bay}`} max={100} value={percent}/>:state==="erasing"&&!stale?<progress aria-label={`Erase progress bay ${d.bay}`} max={100}/>:null}
          {!sharedNote&&<span>{d.progress_note || (state==="erasing"?(percent===null?"Percentage not reported by controller.":"Percentage reported by controller."):state==="completed"?"Completion evidence recorded.":state==="queued"?"Waiting for the controller to begin this disk.":state==="awaiting_power"?"No start recorded for this wipe.":"No verified completion evidence.")}</span>}
        </div>
      </li>;
    })}</ol>
  </section>;
}
