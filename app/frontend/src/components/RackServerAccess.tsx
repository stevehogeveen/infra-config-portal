import { useEffect, useId, useState } from "react";
import { GuidePrimary } from "./studio/Guide";
import { requestStudioRefresh } from "./studio/StudioContext";
import { shortTime } from "./studio/ProvenanceChip";

/** Unsaved connection details kept per device while the operator switches equipment. */
export type AccessDraft = { host: string; username: string; password: string; verifyTls: boolean; replacePassword: boolean };
import { PlugZap, Save } from "lucide-react";
import { api } from "../api";
import type { IloAccessSettings, ProviderProbeResult } from "../types";

export function RackServerAccess({ deviceId, onContinue, onDetectedModel, onChecked, onBusyChange, checkConnection = false, draft, onDraft, hoistSubmit = false, showTask = true }: { deviceId: string; onContinue?: (host: string) => void; onDetectedModel?: (model: string) => void; onChecked?: () => void; onBusyChange?: (busy:boolean) => void; checkConnection?: boolean; draft?: AccessDraft; onDraft?: (draft: AccessDraft | undefined) => void; hoistSubmit?: boolean; showTask?: boolean }) {
  const formId = useId();
  const [access, setAccess] = useState<IloAccessSettings | null>(null);
  const [host, setHost] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [verifyTls, setVerifyTls] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [replacePassword, setReplacePassword] = useState(false);
  const [probe, setProbe] = useState<ProviderProbeResult | null>(null);
  useEffect(() => { onBusyChange?.(busy); return () => onBusyChange?.(false); }, [busy, onBusyChange]);
  const savedConnection = Boolean(access?.host && access.username_configured && access.password_configured && host === access.host && username === (access.username || "") && !password && verifyTls === access.verify_tls);
  useEffect(() => {
    let cancelled = false;
    api.iloAccessSettings(deviceId).then((value) => {
      if (cancelled) return;
      setAccess(value); setHost(value.host || ""); setUsername(value.username || ""); setVerifyTls(value.verify_tls);
      // A draft typed before switching equipment wins over the saved values until it is saved.
      if (draft) { setHost(draft.host); setUsername(draft.username); setPassword(draft.password); setVerifyTls(draft.verifyTls); setReplacePassword(draft.replacePassword); }
    }).catch((err) => { if (!cancelled) setError(String(err.message || err)); })
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, [deviceId]);
  useEffect(() => {
    if (!access || !onDraft) return;
    const changed = host !== (access.host || "") || username !== (access.username || "") || !!password || verifyTls !== access.verify_tls || replacePassword;
    onDraft(changed ? { host, username, password, verifyTls, replacePassword } : undefined);
  }, [access, host, username, password, verifyTls, replacePassword]);
  // Proof belongs to the saved target. Editing the target or access means it no longer proves this draft.
  const targetEdited = !!access && (host.trim() !== (access.host || "") || username.trim() !== (access.username || "") || !!password || verifyTls !== access.verify_tls);
  const submitButton = <button className="rack-plan-save" type="submit" form={formId} disabled={busy || !access}>{checkConnection ? <PlugZap size={16} /> : <Save size={16} />}{busy ? "Working..." : checkConnection ? savedConnection ? "Check connection" : "Save and check connection" : "Save iLO connection"}</button>;
  return <form id={formId} className="workbench-access" onChange={() => { setMessage(""); setProbe(null); onDetectedModel?.(""); }} onSubmit={async (event) => {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      if (!savedConnection) {
        const next = await api.saveIloAccessSettings(deviceId, { host: host.trim(), username: username.trim() || null, ...(password ? { password } : {}), verify_tls: verifyTls });
        setAccess(next); setHost(next.host || ""); setUsername(next.username || ""); setPassword(""); setReplacePassword(false); onDraft?.(undefined);
      }
      if (checkConnection) {
        setProbe(null);
        onDetectedModel?.("");
        const result = await api.probeProvider("ilo-redfish", deviceId);
        setProbe(result);
        onChecked?.();
        requestStudioRefresh();
        const systems = result.systems;
        if (result.status === "ok" && Array.isArray(systems) && systems.length === 1 && typeof systems[0]?.Model === "string") onDetectedModel?.(systems[0].Model);
      } else setMessage("Connection saved. No hardware check has run.");
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }}>
    {showTask && <div className="input-task" aria-live="polite"><span className="input-task-label">Your next step</span><h3>{savedConnection ? "Check the saved connection" : "Enter this server's connection details"}</h3><p>{savedConnection ? "Credentials saved for this server." : "Current iLO address and sign-in details required."}</p></div>}
    {targetEdited && access?.last_probe_time && <p className="sd-proof-note" role="note">The last answer ({shortTime(access.last_probe_time)}) was for the saved details{access.host ? <> at <strong>{access.host}</strong></> : null}. It does not prove these edited details; save and check again.</p>}
    <p>Current DHCP address for this server. Not its planned management address.</p>
    <label><span className="input-label">Current iLO address <small>Required</small></span><input aria-label="Current iLO address" required disabled={busy || !access} value={host} onChange={(e) => setHost(e.target.value)} placeholder="IP address or hostname" /></label>
    <label><span className="input-label">iLO username <small>{access?.username_configured ? "Saved; change if needed" : "Required"}</small></span><input aria-label="iLO username" required={!access?.username_configured} disabled={busy || !access} value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" /></label>
    {access?.password_configured && !replacePassword ? <div><p>Password saved securely</p><button type="button" className="connection-secondary" disabled={busy} onClick={() => setReplacePassword(true)}>Change password</button></div> : <label><span className="input-label">iLO password <small>{access?.password_configured ? "Replacement" : "Required"}</small></span><input aria-label="iLO password" type="password" required={!access?.password_configured} disabled={busy || !access} value={password} onChange={(e) => setPassword(e.target.value)} placeholder={access?.password_configured ? "Leave blank to keep saved password" : "Password"} autoComplete="new-password" /></label>}
    <label className="workbench-checkbox"><input type="checkbox" disabled={busy || !access} checked={verifyTls} onChange={(e) => setVerifyTls(e.target.checked)} />Verify TLS certificate</label>
    <p className="sd-tls-note">{verifyTls ? "On: the iLO must present a certificate this app trusts, so a different machine at this address would be refused." : "Off: the connection is still encrypted, but the iLO's identity is not checked, so a different machine at this address would not be noticed. Turn it on once a trusted certificate is installed."}</p>
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    {hoistSubmit ? <GuidePrimary>{submitButton}</GuidePrimary> : submitButton}
    {checkConnection && <p>Read-only iLO connection and firmware inventory. No updates are installed.</p>}
    {probe && <section aria-label="Connection check result" aria-live="polite"><h3>Check result: {probe.status}</h3><p>{probe.message}</p>{probe.checked_at && <p>{new Date(probe.checked_at).toLocaleString()}</p>}{[...probe.blockers, ...probe.warnings].map((text, index) => <p key={index}>{text}</p>)}<h4>Reported firmware versions</h4><FirmwareVersions probe={probe} /><p>Installed versions only. Service-pack compatibility and upgrade approval are not assessed by this check.</p></section>}
    {!checkConnection && (message || savedConnection) && onContinue && <button className={message ? "rack-plan-save" : "connection-secondary"} type="button" disabled={busy} onClick={() => onContinue(access?.host || host.trim())}>Continue to checks</button>}
  </form>;
}

export function FirmwareVersions({ probe }: { probe: ProviderProbeResult }) {
  const rows = ["managers", "systems", "firmware"].flatMap(group => {
    const resources = probe[group];
    if (!Array.isArray(resources)) return [];
    return resources.flatMap(resource => {
      if (!resource || typeof resource !== "object") return [];
      const version = resource.Version || resource.FirmwareVersion || resource.BiosVersion || resource.BIOSVersion;
      if (typeof version !== "string") return [];
      const name = typeof resource.Name === "string" ? resource.Name : group === "systems" ? "System BIOS" : group === "managers" ? "iLO" : "Firmware component";
      return [{ name, version }];
    });
  });
  return rows.length ? <dl>{rows.map((row, index) => <div key={index}><dt>{row.name}</dt><dd>{row.version}</dd></div>)}</dl> : <p>No firmware versions returned.</p>;
}
