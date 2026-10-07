import { useState } from "react";
import { AlertTriangle, ArrowUpRight, CircleCheck, CircleHelp } from "lucide-react";
import type { FirmwareAssessment } from "../api";
import { HardwareHealthReview } from "./HardwareHealthReview";

export function FirmwareAssessmentTable({result,showHealth=true}: {result:FirmwareAssessment;showHealth?:boolean}) {
  const [filter,setFilter] = useState("all");
  const updates=result.rows.filter(r=>r.status==="Update available").length;
  const unknown=result.rows.filter(r=>r.status==="Cannot determine").length;
  const health=result.rows.filter(r=>r.health && !["OK","Unknown"].includes(r.health)).length;
  const rows=result.rows.filter(r=>filter==="all" || (filter==="unknown"?r.status==="Cannot determine":r.status==="Update available"||Boolean(r.health&&!['OK','Unknown'].includes(r.health))));
  return <>
    {showHealth&&result.health_review&&<HardwareHealthReview review={result.health_review}/>}
    <div className="workflow-summary"><span><strong>{updates}</strong> updates available</span><span><strong>{unknown}</strong> firmware matches not verified</span>{!result.health_review&&<span><strong>{health}</strong> health warnings</span>}</div>
    {unknown>0&&<p className="firmware-comparison-note">"Cannot determine" means no verified firmware comparison. It does not mean a drive has failed. Hardware health is reported separately.</p>}
    <div className="workflow-actionbar"><label>Show<select aria-label="Firmware result filter" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">All components</option><option value="attention">Updates and health warnings</option><option value="unknown">Unmatched components</option></select></label><span>{rows.length} components</span></div>
    <div className="workflow-table-wrap"><table className="workflow-table firmware-results"><thead><tr><th>Component</th><th>Installed</th><th>In selected SPP</th><th>Result</th></tr></thead><tbody>{rows.map((row,index)=>{
      const badHealth = Boolean(row.health && !["OK","Unknown"].includes(row.health));
      const unknown = row.status==="Cannot determine";
      const Icon=badHealth?AlertTriangle:unknown?CircleHelp:row.status==="Update available"?ArrowUpRight:CircleCheck;
      return <tr key={`${row.component}:${index}`}><th scope="row"><strong>{row.component}</strong>{badHealth&&<span className="state-label state-danger">Health: {row.health}</span>}<details><summary>Evidence and next action</summary><p>{row.reason}</p>{row.files.map(file=><code key={file}>{file}</code>)}</details></th><td data-label="Installed">{row.installed || "Not reported"}</td><td data-label="SPP">{row.target || "No verified match"}</td><td data-label="Result"><span className={`state-label ${badHealth?"state-danger":unknown?"state-unknown":row.status==="Update available"?"state-warning":"state-ok"}`}><Icon size={15}/>{row.status}</span></td></tr>;
    })}</tbody></table></div>{!rows.length&&<p>No components in this view.</p>}
  </>;
}
