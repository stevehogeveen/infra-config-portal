import { AlertTriangle, ClipboardCheck } from "lucide-react";
import type { HardwareHealthReview as Review } from "../api";

export function HardwareHealthReview({review,busy=false,onAcknowledge,compact=false}: {
  review:Review;busy?:boolean;onAcknowledge?:(id:string)=>void;compact?:boolean;
}) {
  if (compact) return <details className={`storage-health-summary ${review.issues.some(i=>i.health==="Critical")?"has-critical":""}`}>
    <summary><AlertTriangle size={17}/><strong>{review.issues.length ? `${review.issues.length} hardware alert${review.issues.length===1?"":"s"}` : "Hardware health"}</strong><span>{review.current ? review.issues.length ? review.issues.map(i=>`${i.title}: ${i.health}`).join("; ") : "No alerts in available inventory" : "Current check required"}</span></summary>
    <HardwareHealthReview review={review} busy={busy} onAcknowledge={onAcknowledge}/>
  </details>;
  return <section className="hardware-health-review" aria-label="Hardware health review">
    <header><h3><AlertTriangle size={20}/>Hardware health {review.issues.length ? `: ${review.issues.length} alert${review.issues.length===1?"":"s"}` : "review"}</h3>
      {review.checked_at && <small>Read {new Date(review.checked_at).toLocaleString()}</small>}</header>
    {review.refresh_required && <p className="workflow-pending">{review.refresh_required} Old alerts below are historical, not a fresh diagnosis.</p>}
    {!review.issues.length && <p>{review.current ? "No health alerts were returned in the available inventory. This is not a complete hardware diagnostic." : "Current hardware health has not been verified."}</p>}
    {review.diagnostic_log && <details className="health-diagnostic-log">
      <summary>Server diagnostic log (IML): {review.diagnostic_log.entries.length} entries collected</summary>
      <p>{review.diagnostic_log.message}</p>
      {review.diagnostic_log.entries.map((entry,index)=><article key={`${entry.Id}:${index}`}>
        <strong>{entry.Repaired===true || entry.HpeSeverity==="Repaired" || entry.HpeUserAction==="Repaired" ? "Marked repaired (historical)" : `${entry.HpeSeverity || entry.Severity || "Severity not reported"} - historical event; current relevance unverified`}</strong>
        <p>{entry.Message || "No event message returned."}</p>
        {entry.Created && <p>Recorded: {entry.Created}</p>}
        {entry.HpeRecommendedAction && <p><strong>HPE recommendation:</strong> {entry.HpeRecommendedAction}</p>}
      </article>)}
    </details>}
    {review.issues.map(issue=><article className="hardware-health-issue" key={issue.id}>
      <header><h4>{issue.title}</h4><span className={`state-label ${issue.health==="Critical"?"state-danger":"state-warning"}`}>{issue.health}</span></header>
      {issue.details.map(detail=><p key={detail}>{detail}</p>)}
      <dl>{Object.entries(issue.facts).map(([key,value])=><div key={key}><dt>{({DiskDriveUse:"Drive assignment",BackupPowerSourceStatus:"Cache backup power",CapacityBytes:"Reported capacity"} as Record<string,string>)[key]||key}</dt><dd>{key==="CapacityBytes" ? Number(value)>0?`${Math.round(Number(value)/1e9)} GB`:"Not reported" : key==="DiskDriveUse"&&value==="Unconfigured" ? "Unassigned to RAID (not itself a fault)" : String(value)}</dd></div>)}</dl>
      <p className="health-next-action"><strong>Next:</strong> {issue.next_step}</p>
      <footer>{issue.acknowledged_at ? <span className="health-acknowledged"><ClipboardCheck size={16}/>Acknowledged, still unresolved · {new Date(issue.acknowledged_at).toLocaleString()}</span> : onAcknowledge ? <button className="secondary-action" disabled={busy||!review.current} onClick={()=>onAcknowledge(issue.id)} aria-label={`Acknowledge ${issue.title}`}><ClipboardCheck size={16}/>Acknowledge</button> : <span>Not acknowledged</span>}</footer>
    </article>)}
    {!!review.issues.length && <p className="health-review-note">{review.message}</p>}
  </section>;
}
