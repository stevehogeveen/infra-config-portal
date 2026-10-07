import { FirmwareBridgePrep } from "./FirmwareBridgePrep";
import { GuardedExecution } from "./GuardedExecution";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { RefreshCw, ArrowUpCircle } from "lucide-react";
import { api, type FirmwareAssessment } from "../api";
import type { IloAccessSettings } from "../types";
import { FirmwareAssessmentTable } from "./FirmwareAssessmentTable";
import { HardwareHealthReview } from "./HardwareHealthReview";
import { FirmwareUpgradeReview } from "./FirmwareUpgradeReview";

export function FirmwareReadCheck({ profileId, deviceId, packageName, packageCurrent, execution, deviceName = "this server", hoistExecution = false }: { profileId: string; deviceId: string; packageName?: string; packageCurrent?: boolean; execution?: boolean; deviceName?: string; hoistExecution?: boolean }) {
  const [access, setAccess] = useState<IloAccessSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<FirmwareAssessment | null>(null);
  const [checkedHere, setCheckedHere] = useState(false);
  const [checkFailed, setCheckFailed] = useState(false);
  const requestId = useRef(0);
  const [upgradeOpen,setUpgradeOpen] = useState(false);
  useEffect(() => {
    const id = ++requestId.current;
    setLoading(true); setBusy(false); setAccess(null); setResult(null); setError("");
    setCheckedHere(false); setCheckFailed(false); setUpgradeOpen(false);
    Promise.all([api.iloAccessSettings(deviceId), api.firmwareAssessment(profileId, deviceId)])
      .then(([settings, assessment]) => { if (id === requestId.current) { setAccess(settings); setResult(assessment); } })
      .catch(err => { if (id === requestId.current) setError(err.message); })
      .finally(() => { if (id === requestId.current) setLoading(false); });
    return () => { ++requestId.current; };
  }, [profileId, deviceId, packageName, packageCurrent]);
  const ready = Boolean(access?.host && access.username_configured && access.password_configured);
  async function read() {
    const id = ++requestId.current;
    setBusy(true); setError(""); setResult(null); setCheckedHere(false); setCheckFailed(false);
    try {
      const probe = await api.probeProvider("ilo-redfish", deviceId);
      if (id !== requestId.current) return;
      if (probe.status !== "ok") throw new Error(probe.message || "Connection check did not succeed.");
      const assessment = await api.firmwareAssessment(profileId, deviceId);
      if (id !== requestId.current) return;
      // The comparison must use this probe, not a previous or concurrent reading.
      if (assessment.rows.length && (!probe.checked_at || assessment.checked_at !== probe.checked_at)) {
        throw new Error("The comparison does not match this hardware check. Run the check again.");
      }
      setResult(assessment); setCheckedHere(true);
    }
    catch (err) { if (id === requestId.current) { setError(err instanceof Error ? err.message : String(err)); setCheckFailed(true); } }
    finally { if (id === requestId.current) setBusy(false); }
  }
  async function acknowledge(issueId:string) {
    if(!result?.health_review)return;
    const id = ++requestId.current;
    setBusy(true);setError("");
    try {const review=await api.acknowledgeHealth(profileId,deviceId,result.health_review.review_token,issueId);if(id===requestId.current)setResult(r=>r?{...r,health_review:review}:r);}
    catch(e){if(id===requestId.current)setError(e instanceof Error?e.message:String(e));}
    finally{if(id===requestId.current)setBusy(false);}
  }
  // A disabled compare command always shows why, beside it (lab-build-rules section 6).
  const packageBlocker = !loading && !packageCurrent
    ? (!result?.rows.length && result?.reason) || (packageName ? "The selected SPP file is missing or changed. Reselect it above to compare installed firmware." : "Select an SPP above to compare installed firmware.")
    : "";
  const assessmentView = result && <>
    {result.health_review && <HardwareHealthReview review={result.health_review} busy={busy} onAcknowledge={id=>void acknowledge(id)}/>}
    <section aria-label="Firmware assessment" aria-live="polite">
      {result.detected_model && <h3>Detected: {result.detected_model}{result.rom_family ? ` / ${result.rom_family}` : ""}</h3>}
      {result.identity_mismatch && <p className="kit-report-warning">Rack label says {result.planned_model}. Comparison uses the detected {result.detected_model}, not the rack label.</p>}
      <h3>{result.status}</h3>{result.reason !== packageBlocker && <p>{result.reason}</p>}
      {result.checked_at && <p>Hardware read: {new Date(result.checked_at).toLocaleString()} / SPP {result.package_release}</p>}
      {result.rows.length>0 && <FirmwareAssessmentTable result={result} showHealth={false}/>}
      {result.limitations && <p className="kit-report-warning">{result.limitations}</p>}
    </section>
  </>;
  return <div className="firmware-read-check">
    <div className="rack-firmware-check"><div className="firmware-next-actions"><button className="firmware-inspect-action" type="button" disabled={loading || busy || !ready || !packageCurrent} onClick={() => void read()}><RefreshCw size={16} />{busy ? "Working..." : "Check firmware against SPP"}</button><button type="button" disabled={loading||busy} onClick={()=>setUpgradeOpen(true)}><ArrowUpCircle size={16}/>Review upgrades</button></div>
    {packageBlocker && <p className="firmware-blocked-reason" role="note">{packageBlocker}</p>}
    {loading ? <p role="status">Loading saved connection...</p> : ready ? <p>Target iLO: {access?.host}. Read-only; no updates installed.</p> : <p>Saved iLO address and credentials required. <Link to={`/setup/connect?device=${encodeURIComponent(deviceId)}`}>Open connection settings</Link></p>}</div>
    {error && <div className="firmware-check-notice is-failed" role="alert">{checkFailed && <strong>Check unsuccessful. Connection not verified.</strong>}<p>{error}</p>{checkFailed && <p>No new firmware comparison is available. Check the iLO cable, address and access details before trying again.</p>}</div>}
    {!loading && !error && <div className="firmware-check-notice" role="status">
      <strong>{busy && !result ? "Contacting iLO and reading firmware..." : checkedHere ? "Hardware check completed" : "Connection not checked on this visit"}</strong>
      <p>{busy && !result ? "Waiting for the server to respond. Previous readings are not being used as a new result." : checkedHere ? "This is a point-in-time reading, not continuous online monitoring." : "Saved readings do not confirm that the server is connected now."}</p>
    </div>}
    <p><strong>Comparison package:</strong> {packageName || "Select an SPP above"}{packageName && !packageCurrent ? " (missing or changed; reselect it)" : ""}</p>
    <div className="firmware-order" aria-label="Order of work"><span>Order of work</span><ol><li>Inspect drives and health alerts</li><li>Approve firmware</li><li>Create RAID</li><li>Install ESXi</li></ol><small>Drive planning can happen now. RAID changes are a separate, confirmed step.</small></div>
    {result && (checkedHere ? assessmentView : <details className="firmware-saved-readings">
      <summary>Saved readings - not a live connection{result.checked_at ? ` (${new Date(result.checked_at).toLocaleString()})` : " (reading time unavailable)"}</summary>
      {assessmentView}
    </details>)}
    {execution && hoistExecution && !loading && ready && <FirmwareBridgePrep profileId={profileId} deviceId={deviceId} deviceName={deviceName} />}
    {execution && !loading && (ready ? <GuardedExecution kind="firmware" profileId={profileId} deviceId={deviceId} deviceName={deviceName} hoist={hoistExecution} />
      : <section className="sd-guarded" aria-label="Firmware install"><header className="sd-guarded-h"><div><p className="eyebrow">Firmware install · {deviceName}</p><h3>Install firmware</h3></div></header><div className="sd-guarded-act"><button type="button" className="primary-action" disabled>Review firmware install</button><p className="sd-guarded-why" role="note">Blocked: save this server's iLO address and sign-in first.</p></div></section>)}
    {upgradeOpen&&<FirmwareUpgradeReview profileId={profileId} deviceId={deviceId} onClose={()=>setUpgradeOpen(false)}/>}
  </div>;
}
