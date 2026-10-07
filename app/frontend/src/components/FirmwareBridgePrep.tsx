import { FIRMWARE_SCOPE_BLOCKER } from "./studio/WriteScope";
import { useEffect, useRef, useState } from "react";
import { FileCheck2, RefreshCw } from "lucide-react";
import { guardedApi, GuardedUnavailableError, type BridgePreparation, type FirmwareCapabilities } from "../api";
import { ProvenanceChip } from "./studio/ProvenanceChip";

/*
 * Two explicit steps before the iLO bridge review, both started only by the operator:
 * 1. a confirmed read-only capability read of this exact iLO (it contacts the server, read-only);
 * 2. offline preparation of the HPE-signed iLO 1.48 bridge from the selected SPP.
 * Neither installs anything, and preparation is never presented as install-ready.
 */
type Step<T> = { state: "idle" | "busy" | "done" | "error" | "unavailable"; data?: T; error?: string };

export function FirmwareBridgePrep({ profileId, deviceId, deviceName, onChanged }: { profileId: string; deviceId: string; deviceName: string; onChanged?: () => void }) {
  const [confirmRead, setConfirmRead] = useState(false);
  const [caps, setCaps] = useState<Step<FirmwareCapabilities>>({ state: "idle" });
  const [prep, setPrep] = useState<Step<BridgePreparation>>({ state: "idle" });
  const target = useRef(`${profileId}:${deviceId}`);
  useEffect(() => { target.current = `${profileId}:${deviceId}`; setConfirmRead(false); setCaps({ state: "idle" }); setPrep({ state: "idle" }); }, [profileId, deviceId]);

  async function run<T>(call: () => Promise<T>, set: (step: Step<T>) => void) {
    const key = target.current;
    set({ state: "busy" });
    try { const data = await call(); if (target.current === key) { set({ state: "done", data }); onChanged?.(); } }
    catch (err) {
      if (target.current !== key) return;
      if (err instanceof GuardedUnavailableError) set({ state: "unavailable" });
      else set({ state: "error", error: err instanceof Error ? err.message : String(err) });
    }
  }
  const c = caps.data, p = prep.data, auth = p?.authentication;
  return <section className="sd-guarded sd-bridge" aria-label="iLO bridge preparation">
    <header className="sd-guarded-h"><div><p className="eyebrow">Get ready · nothing is installed</p><h3>Read the iLO and prepare 1.48</h3></div></header>

    <div className="sd-bridge-step">
      <h4>1. Read firmware capabilities (read-only)</h4>
      <p className="sd-fine">Asks the iLO once what it runs and whether it can take an update. Nothing is installed.</p>
      <label className="workflow-checkbox"><input type="checkbox" checked={confirmRead} disabled={caps.state === "busy"} onChange={event => setConfirmRead(event.target.checked)} />I confirm a read-only check of {deviceName}'s iLO.</label>
      <div className="sd-guarded-act"><button type="button" className="secondary-action" disabled={!confirmRead || caps.state === "busy"} onClick={() => void run(() => guardedApi.capabilities(profileId, deviceId), setCaps)}><RefreshCw size={15} />{caps.state === "busy" ? "Reading iLO..." : "Read firmware capabilities (read-only)"}</button></div>
      {caps.state === "unavailable" && <p className="sd-guarded-why" role="note">Not available yet: the app cannot read firmware capabilities on this server yet.</p>}
      {caps.state === "error" && <p role="alert" className="workflow-alert">{caps.error}</p>}
      {c && <div className="sd-bridge-result" aria-label="Firmware capabilities">
        <p><ProvenanceChip kind="proven" time={c.checked_at}>read</ProvenanceChip> iLO firmware <strong>{c.manager_firmware_version || "not reported"}</strong>{c.system_health ? ` · system health ${c.system_health}` : ""}{c.state ? ` · update service ${c.state}` : ""}</p>
        {!!c.errors?.length && <ul className="sd-guarded-blockers">{c.errors.map(item => <li key={item}>{item}</li>)}</ul>}
        {(!!c.inventory?.length || !!c.health_issues?.length) && <details className="fw-details"><summary>Details from this read</summary>
        {!!c.health_issues?.length && <ul className="sd-guarded-blockers">{c.health_issues.map(issue => <li key={issue.group + issue.health}>{issue.group}: {issue.health}</li>)}</ul>}
        {!!c.inventory?.length && <table className="sd-guarded-ops"><thead><tr><th>Component</th><th>Version</th><th>Updateable</th></tr></thead>
          <tbody>{c.inventory.map((item, index) => <tr key={item.resource_path || index}><th scope="row">{item.name || "unnamed"}</th><td>{item.version || "not reported"}</td><td>{item.updateable === true ? "yes" : item.updateable === false ? "no" : "not reported"}</td></tr>)}</tbody></table>}</details>}
        {c.ilo_update_health ? <div className="sd-bridge-health" aria-label="iLO update health">
          {c.ilo_update_health.blockers.length ? <div className="sd-guarded-gates" role="note"><strong>Blocks the iLO update</strong><ul>{c.ilo_update_health.blockers.map(item => <li key={item}>{item}</li>)}</ul></div>
            : <p className="sd-fine">Nothing in this read blocks the iLO update.</p>}
          {!!c.ilo_update_health.warnings.length && <details className="sd-guarded-warnings fw-details"><summary>{c.ilo_update_health.warnings.length} other warning{c.ilo_update_health.warnings.length === 1 ? "" : "s"} (don't block this update)</summary>
            <ul>{c.ilo_update_health.warnings.map(item => <li key={item.group + item.title}><b>{item.group}</b> · {item.health}: {item.title}{item.details ? <small> {item.details}</small> : null}</li>)}</ul></details>}
        </div> : <div className="sd-guarded-gates" role="note"><strong>Read capabilities again to assess iLO update health</strong>
          <p>This result was read before the app assessed iLO update health. Nothing is checked automatically.</p>
          <button type="button" className="secondary-action" disabled={!confirmRead || caps.state === "busy"} onClick={() => void run(() => guardedApi.capabilities(profileId, deviceId), setCaps)}>Read capabilities again (read-only)</button></div>}
        {c.message && <p className="sd-fine">{c.message}</p>}
      </div>}
    </div>

    <div className="sd-bridge-step">
      <h4>2. Prepare the iLO 1.48 bridge from your SPP</h4>
      <p className="sd-fine">Finds the 1.48 file in your package and checks HPE's signature. Nothing is sent to the server.</p>
      <div className="sd-guarded-act"><button type="button" className="secondary-action" disabled={prep.state === "busy"} onClick={() => void run(() => guardedApi.prepareBridge(profileId, deviceId), setPrep)}><FileCheck2 size={15} />{prep.state === "busy" ? "Checking signature..." : "Prepare the iLO 1.48 bridge from your SPP"}</button></div>
      {prep.state === "unavailable" && <p className="sd-guarded-why" role="note">Not available yet: the app cannot prepare the iLO bridge on this server yet.</p>}
      {prep.state === "error" && <p role="alert" className="workflow-alert">{prep.error}</p>}
      {p && <div className="sd-bridge-result" aria-label="Bridge preparation">
        {auth?.binary_authenticated
          ? <div className="fw-done" role="status"><strong>Done: the 1.48 file in your package is genuine.</strong>
              <p>HPE's signature on it checks out. <b>Next:</b> step 3, <a href="#write-scope">Limit to firmware only</a>, then step 4, Review firmware install.</p></div>
          : <div className="sd-guarded-gates" role="alert"><strong>The 1.48 file could not be verified.</strong><p>Don't install it. Choose the SPP again, or get a fresh copy from HPE.</p></div>}
        <p><span className="sd-chip sd-chip-warn sd-chip-xs">install needs its own review</span></p>
        <details className="fw-details"><summary>Technical details</summary><dl className="sd-kv">
          <div><dt>preparation</dt><dd className="sd-mono">{String(p.preparation_id)}</dd></div>
          <div><dt>package selection</dt><dd className="sd-mono">{String(p.package_selection_id)}</dd></div>
          <div><dt>signature</dt><dd>{auth?.binary_authenticated ? `verified (${auth.authentication_method || "HPE-signed RPM"}${auth.signing_key_id ? `, key ${auth.signing_key_id}` : ""})` : "not verified"}</dd></div>
          <div><dt>exact BIN match</dt><dd>{auth?.binary_authenticated && auth.binary?.sha256 ? `yes · ${auth.binary.size_bytes ?? "?"} bytes · ${auth.binary.sha256}` : "not shown by the server"}</dd></div>
          {p.bridge.path && <div><dt>bridge file</dt><dd className="sd-mono">{p.bridge.path}</dd></div>}
          <div><dt>applies to this server</dt><dd>{auth?.applicability_verified ? "verified" : "checked in the install review"}</dd></div>
          <div><dt>can apply</dt><dd>{p.can_apply ? "yes" : "no, the install review decides"}</dd></div>
        </dl>
        {!!p.blockers.length && <><p className="sd-fine">The server's notes on this preparation:</p><ul className="sd-fine">{p.blockers.map(item => <li key={item}>{item}</li>)}</ul></>}
        </details>
      </div>}
    </div>
  </section>;
}
