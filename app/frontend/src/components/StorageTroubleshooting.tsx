import { useEffect, useRef, useState } from "react";
import { SearchCheck, ShieldCheck, Wrench } from "lucide-react";
import { api, type StorageDiagnosis } from "../api";

export function StorageTroubleshooting({profileId,deviceId,disabled,onBusy,onRead}:{profileId:string;deviceId:string;disabled:boolean;onBusy:(v:boolean)=>void;onRead:()=>void}) {
  const [result,setResult]=useState<StorageDiagnosis|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ssa,setSsa]=useState<{message:string;reports:string[];checked_at?:string}|null>(null);
  const [recovery,setRecovery]=useState(false);
  const [now,setNow]=useState(Date.now());
  const mounted=useRef(true);
  const callbacks=useRef({onBusy,onRead});callbacks.current={onBusy,onRead};
  useEffect(()=>{mounted.current=true;const t=setInterval(()=>setNow(Date.now()),15000);return()=>{mounted.current=false;clearInterval(t);callbacks.current.onBusy(false);};},[]);
  async function diagnose(){
    setBusy(true);callbacks.current.onBusy(true);setError("");setResult(null);
    try{const data=await api.diagnoseStorage(profileId,deviceId);if(mounted.current){setResult(data);setNow(Date.now());callbacks.current.onRead();}}
    catch(e){if(mounted.current)setError(e instanceof Error?e.message:String(e));}
    finally{if(mounted.current){setBusy(false);callbacks.current.onBusy(false);}}
  }
  const stale=result && now-Date.parse(result.checked_at)>5*60*1000;
  async function readSsa(){
    setBusy(true);callbacks.current.onBusy(true);setError('');setSsa({message:'Ansible maintenance diagnostics requested...',reports:[]});
    try{
      const job=await api.startSsaDiagnostic(deviceId);
      for(let i=0;i<110&&mounted.current;i++){
        await new Promise(resolve=>setTimeout(resolve,3000));
        if(!mounted.current)return;
        const read=await api.readSsaDiagnostic(deviceId,job.job_id);
        if(!mounted.current)return;
        if(read.result){setSsa(read.result);return;}
        if(['failed','stopped','canceled'].includes(read.status))throw new Error('Maintenance worker did not complete. Check worker availability and configuration.');
      }
      if(mounted.current)throw new Error('Diagnostics timed out. No storage changes were requested.');
    }catch(e){if(mounted.current){setError(e instanceof Error?e.message:String(e));setSsa(null);}}
    finally{if(mounted.current){setBusy(false);callbacks.current.onBusy(false);}}
  }
  return <section className="storage-troubleshooting" aria-label="Storage troubleshooting">
    <header><div><h3><Wrench size={22}/>Storage troubleshooting</h3><p>Read-only diagnosis. No disks, power settings or logs are changed.</p></div>
      <button className="primary-action" disabled={disabled||busy} onClick={()=>void diagnose()}><SearchCheck size={18}/>{busy?"Diagnosing server...":"Diagnose this server"}</button></header>
    {busy&&<p role="status">Reading this server's controller, RAID membership and hardware log. This can take up to three minutes.</p>}
    {error&&<p role="alert" className="workflow-alert">Diagnosis could not complete: {error} No repair was attempted.</p>}
    <details><summary>Advanced maintenance diagnostics</summary>
      <p>Read controller, cache and drive details through HPE SSA CLI. Requires an enrolled Linux maintenance environment on this server; no restart or disk changes.</p>
      <button className="secondary-action" disabled={disabled||busy} onClick={()=>void readSsa()}><SearchCheck size={18}/>Read SSA diagnostics with Ansible</button>
      {ssa&&<><p role="status">{ssa.message}</p>{ssa.checked_at&&<small>Recorded {new Date(ssa.checked_at).toLocaleString()}. Run again for current evidence.</small>}{ssa.reports.map((report,i)=><details key={i}><summary>{i===0?'Controller status':'Detailed storage configuration'}</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{report}</pre></details>)}</>}
    </details>
    {result&&<>
      <p className="diagnosis-result" role="status">{result.summary}</p>
      <small>{stale?"Previous reading; run diagnosis again before acting. ":"Read "}{new Date(result.checked_at).toLocaleString()} / {result.name}</small>
      <dl className="diagnosis-facts"><div><dt>Controller</dt><dd>{result.controller_health}</dd></div><div><dt>Detected drives</dt><dd>{result.healthy_drives} of {result.detected_drives} report healthy</dd></div><div><dt>Existing RAID volumes</dt><dd>{result.volume_count}</dd></div></dl>
      <div className="diagnosis-findings">{result.findings.map(f=><article key={f.id}><span className="diagnosis-source">{f.source}</span><h4>{f.title}</h4><p>{f.detail}</p><p><strong>Next:</strong> {f.action}</p>{!!f.evidence.length&&<details><summary>Evidence</summary><ul>{f.evidence.map((v,i)=><li key={i}>{v}</li>)}</ul></details>}</article>)}</div>
      <details><summary>Drive assignments and limits of this reading</summary><p>{result.controller}</p>{result.volumes.map((v,i)=><p key={i}>{v.raid}: members {v.members.join(", ")||"Not reported"}; spares {v.spares.join(", ")||"None reported"}.</p>)}<p>Cache backup power: {result.backup_power}. Battery health: {result.battery_health}.</p><p>{result.log_note}</p><p>{result.raid_verification}</p><p>{result.pending_changes?"Pending settings differ from the current layout. Do not restart blindly.":"No difference between current and pending RAID layouts was detected in this reading."}</p></details>
      <div className="raid-operation-actions"><button className="secondary-action" aria-expanded={recovery} onClick={()=>setRecovery(v=>!v)}><Wrench size={17}/>{recovery?"Hide recovery steps":"Review recovery steps"}</button></div>
      {recovery&&<section className="storage-recovery" aria-label="Guided storage recovery"><h4>Recovery in HPE SSA</h4><p className="workflow-pending"><strong>Manual vendor tool required.</strong> This app cannot discard controller cache or launch SSA yet. These steps guide the repair; they do not execute it. Removing cached data or RAID volumes can permanently destroy data.</p><ol>{result.recovery_steps.map(step=><li key={step}>{step}</li>)}</ol><button className="primary-action" disabled={disabled||busy} onClick={()=>void diagnose()}><ShieldCheck size={18}/>Verify recovery</button><p>Verification rereads hardware. It does not erase disks, restart the server or mark warnings as fixed.</p></section>}
    </>}
  </section>;
}
