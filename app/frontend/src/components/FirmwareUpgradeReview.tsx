import { useEffect, useRef, useState } from "react";
import { ExternalLink, Save, X, Upload } from "lucide-react";
import { Link } from "react-router-dom";
import { api, type FirmwareUpgradeReview as Review } from "../api";

export function FirmwareUpgradeReview({profileId,deviceId,onClose}: {profileId:string;deviceId:string;onClose:()=>void}) {
  const dialog=useRef<HTMLDialogElement>(null);
  const [review,setReview]=useState<Review|null>(null);
  const [busy,setBusy]=useState(true);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  useEffect(()=>{dialog.current?.showModal();let active=true;
    api.firmwareUpgradeReview(profileId,deviceId).then(r=>{if(active)setReview(r);}).catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setBusy(false);});
    return()=>{active=false;};
  },[profileId,deviceId]);
  async function save(){if(!review)return;setBusy(true);setError("");try{const r=await api.saveFirmwareUpgradeReview(profileId,deviceId,review.review_token);setMessage(r.message);}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  let iloUrl:string|undefined;
  try {const u=new URL(`https://${review?.host}`);if(review?.host&&!u.username&&!u.password)iloUrl=u.href;}catch{/* Invalid saved hosts must not become links. */}
  return <dialog ref={dialog} className="firmware-upgrade-dialog" aria-label="Review firmware upgrades" onCancel={onClose} onClose={onClose}>
    <header><div><h2>Review firmware upgrades</h2><p>Installation is performed with HPE Smart Update Manager.</p></div><button aria-label="Close upgrade review" onClick={onClose}><X size={20}/></button></header>
    {busy&&!review&&<p role="status">Loading upgrade review...</p>}{error&&<p className="workflow-alert" role="alert">{error}</p>}{message&&<p className="workflow-pending" role="status">{message}</p>}
    {review&&<>
      <dl className="upgrade-target"><div><dt>Server</dt><dd>{review.server} / {review.model||"Model not verified"}</dd></div><div><dt>iLO</dt><dd>{review.host||"Not entered"}</dd></div><div><dt>Selected SPP</dt><dd>{review.package_file||"No verified package"}</dd></div></dl>
      <section className="workflow-alert"><h3>Before installation</h3><ul>{review.blockers.map(b=><li key={b}>{b}</li>)}</ul></section>
      {!!review.updates.length&&<><h3>{review.updates.length} matching updates to review in SUM</h3><div className="workflow-table-wrap"><table className="workflow-table"><thead><tr><th>Component</th><th>Installed</th><th>In SPP</th></tr></thead><tbody>{review.updates.map((r,i)=><tr key={i}><th>{r.component}</th><td>{r.installed}</td><td>{r.target}</td></tr>)}</tbody></table></div></>}
      <section className="workflow-section"><h3>Attended upgrade with HPE SUM</h3>
        <ol className="workflow-instructions"><li>Investigate the hardware alerts first. Review backups, stable power, the maintenance window and any required intermediate firmware versions.</li><li>Follow HPE's SPP interactive update procedure for this server and selected ISO. Supervise the console: an SPP boot menu may default to automatic installation. Do not select Automatic mode.</li><li>Let SUM inventory the server and validate applicability and dependencies. Review its proposed updates before confirming installation there. Do not force unmatched packages or downgrades.</li><li>After completion and any required restart, return to Check firmware against SPP. Save a new build report with the resulting readings.</li></ol>
        <div className="upgrade-links">{iloUrl&&<a href={iloUrl} target="_blank" rel="noopener noreferrer" className="secondary-action"><ExternalLink size={16}/>Open this server's iLO</a>}<a href={review.vendor_url} target="_blank" rel="noopener noreferrer">HPE SPP / SUM procedure</a><Link to={`/setup/prepare-esxi?device=${encodeURIComponent(deviceId)}`} onClick={onClose}>Inspect and plan drives</Link></div>
      </section>
      <footer><button className="primary-action" disabled={busy||!review.can_save_review||!!message} onClick={()=>void save()}><Save size={16}/>Save upgrade review</button><button className="primary-action" disabled title="Automatic SPP execution is not connected; use attended HPE SUM."><Upload size={16}/>Install automatically</button><p>Saving records this review only. It does not approve, start, mount or reboot anything.</p></footer>
    </>}
  </dialog>;
}
