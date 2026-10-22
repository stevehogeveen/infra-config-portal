import { useEffect, useRef, useState, type FormEvent } from "react";
import { AlertTriangle, Check, Loader2, ShieldCheck, X } from "lucide-react";
import { windowsApi, type AcceptanceStatus } from "../api";
import { allowOnly, lockReadOnly } from "./storageInstall";

/*
 * Acceptance test: proves the Windows VM is usable, not just deployed. Outside checks, inside checks
 * (through VMware Tools, with the saved Windows sign-in), one guarded restart, then outside again.
 * The sign-in is saved once, owner-only on this PC, and never shown again.
 */

const when = (value?: string) => value ? new Date(value).toLocaleString() : "";

function Signin({ profileId, deviceId, saved, onSaved }: { profileId: string; deviceId: string; saved: { username: string | null; password_saved: boolean }; onSaved: (next: { username: string | null; password_saved: boolean }) => void }) {
  const [username, setUsername] = useState(saved.username || "Administrator");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!username.trim() || !password) { setError("Enter the Windows administrator user name and password."); return; }
    setBusy(true); setError("");
    try { onSaved(await windowsApi.saveSignin(profileId, deviceId, { username: username.trim(), password })); setPassword(""); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }
  return <form className="ex-form" onSubmit={event => void save(event)}>
    <div className="ex-grid">
      <label className="ex-field">Windows user<input aria-label="Windows administrator user" value={username} disabled={busy} autoComplete="off" onChange={e => setUsername(e.target.value)} /></label>
      <label className="ex-field">Password<input aria-label="Windows administrator password" type="password" value={password} disabled={busy} autoComplete="new-password" onChange={e => setPassword(e.target.value)} />
        <small>Kept on this PC only. Never shown again.</small></label>
    </div>
    <div className="ex-actions"><button type="submit" className="secondary-action" disabled={busy}>{busy ? "Saving…" : "Save sign-in"}</button></div>
    {error && <p className="fw-stop" role="alert">{error}</p>}
  </form>;
}

function Tester({ profileId, deviceId, deviceName, lookup, status, setStatus, onClose }: { profileId: string; deviceId: string; deviceName: string; lookup: string;
  status: AcceptanceStatus; setStatus: (next: AcceptanceStatus) => void; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const live = useRef(true);
  const [understood, setUnderstood] = useState(false);
  const [begun, setBegun] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { live.current = true; if (!dialog.current?.open) dialog.current?.showModal(); return () => { live.current = false; }; }, []);
  async function run(label: string, work: () => Promise<void>) {
    setBusy(label); setError("");
    try { await work(); } catch (err) { if (live.current) setError(err instanceof Error ? err.message : String(err)); }
    finally { if (live.current) setBusy(""); }
  }
  const running = status.active && status.state === "running";
  const start = () => run("Allowing only the VM restart on this server…", async () => {
    await allowOnly("vm_deploy_only");
    setBusy("Starting the test…");
    let next: AcceptanceStatus;
    try { next = await windowsApi.testStart(profileId, deviceId, lookup); }
    catch (err) { await lockReadOnly().catch(() => undefined); throw err; }
    setStatus(next);
    if (live.current) setBegun(true);
  });
  const closeRun = () => run("Closing this run…", async () => {
    const next = await windowsApi.testClose(profileId, deviceId); await lockReadOnly();
    setStatus(next);
    if (live.current) { setBegun(false); setUnderstood(false); }
  });
  const finish = () => run("Locking the server…", async () => { await lockReadOnly(); if (live.current) onClose(); });

  const fresh = !status.active && !begun;
  const stuck = status.state === "needs_attention";
  const passed = status.state === "verified";
  const phases = fresh ? [] : status.phases;
  return <dialog ref={dialog} className="inst" aria-label={`Acceptance test on ${deviceName}`} onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    <header className="inst-h">
      <span className="inst-icon"><ShieldCheck size={22} aria-hidden="true" /></span>
      <div><h2>Acceptance test</h2><p>{deviceName}</p></div>
      <button type="button" aria-label="Close acceptance test" onClick={onClose}><X size={20} /></button>
    </header>
    <div className="inst-body">
      <section className="inst-main" aria-live="polite">
        {fresh ? <>
          <h3>Prove Windows works</h3>
          <ul className="ei-rows">
            <li className="ei-row ei-todo"><span />Answers from outside: on, VMware Tools, address, ping from this PC</li>
            <li className="ei-row ei-todo"><span />Works from inside: signs in, pings the gateway, looks up {lookup}</li>
            <li className="ei-row ei-todo"><span />Restarts cleanly, once</li>
            <li className="ei-row ei-todo"><span />Is back after the restart</li>
          </ul>
          <label className="wipe-ok"><input type="checkbox" checked={understood} onChange={event => setUnderstood(event.target.checked)} />I understand Windows restarts once.</label>
        </> : <>
          <h3>{passed ? "Passed" : stuck ? "The test needs attention" : status.state === "failed" ? "Failed" : "Testing…"}</h3>
          <ul className="ei-rows" aria-label="Acceptance checks">{phases.map(phase => <li key={phase.phase} className={`ei-row ${phase.state === "ok" ? "ei-done" : phase.state === "running" ? "ei-now" : phase.state === "todo" ? "ei-todo" : "ei-warn"}`}>
            <span aria-hidden="true">{phase.state === "ok" ? <Check size={14} /> : phase.state === "running" ? <Loader2 size={14} className="dr-spin" /> : phase.state === "todo" ? null : <AlertTriangle size={14} />}</span>
            <div>{phase.label}{phase.checks.some(check => !check.ok) && <ul className="ac-checks">{phase.checks.filter(check => !check.ok).map(check => <li key={check.name}>✗ {check.name}</li>)}</ul>}</div>
          </li>)}</ul>
          {stuck && <p className="fw-stop" role="alert">{status.message}</p>}
          {passed && <p className="inst-ok"><Check size={16} />{status.message} {when(status.finished_at)}</p>}
        </>}
        {busy && <p className="inst-busy" role="status">{busy}</p>}
        {error && <p className="fw-stop" role="alert">{error}</p>}
      </section>
    </div>
    <footer className="inst-f">
      <button type="button" className="secondary-action" disabled={!!busy} onClick={onClose}>{running ? "Close (keeps checking on this page)" : "Cancel"}</button>
      <span className="inst-grow" />
      {fresh && <button type="button" className="primary-action inst-next" disabled={!!busy || !understood} onClick={() => void start()}>Run the test</button>}
      {stuck && <button type="button" className="secondary-action" disabled={!!busy} onClick={() => void closeRun()}>Close this run</button>}
      {passed && <button type="button" className="primary-action inst-next" disabled={!!busy} onClick={() => void finish()}>Done</button>}
    </footer>
  </dialog>;
}

/** Step 4 on Install Windows, once the VM is verified. */
export function AcceptancePanel({ profileId, deviceId, deviceName }: { profileId: string; deviceId: string; deviceName: string }) {
  const [status, setStatus] = useState<AcceptanceStatus | null>(null);
  const [changing, setChanging] = useState(false);
  const [lookup, setLookup] = useState("");
  const [open, setOpen] = useState(false);
  const load = () => windowsApi.test(profileId, deviceId).then(next => { setStatus(next); setLookup(current => current || next.lookup || next.default_lookup || ""); }).catch(() => undefined);
  useEffect(() => { void load(); }, [profileId, deviceId]);
  // The page, not the dialog, keeps the test moving; a run that ends returns the server to read-only.
  const running = !!status?.active && status.state === "running";
  const wasActive = useRef(false);
  useEffect(() => {
    if (status?.active) wasActive.current = true;
    else if (wasActive.current && status && status.state !== "running") { wasActive.current = false; void lockReadOnly().catch(() => undefined); }
  }, [status?.active, status?.state]);
  useEffect(() => {
    if (!running) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function tick() {
      try { const next = await windowsApi.testAdvance(profileId, deviceId); if (!active) return; setStatus(next); if (!next.active || next.state !== "running") return; }
      catch { /* ESXi busy; read again shortly */ }
      if (active) timer = setTimeout(() => void tick(), 10000);
    }
    timer = setTimeout(() => void tick(), 1000);
    return () => { active = false; clearTimeout(timer); };
  }, [running, profileId, deviceId]);
  if (!status) return <p className="dr-loading" role="status">Loading…</p>;
  const signedIn = status.signin.password_saved && !changing;
  return <div className="ac-panel">
    {status.state === "verified" && <p className="inst-ok"><Check size={16} />Passed {when(status.finished_at)}</p>}
    {status.state === "needs_attention" && <p className="fw-stop">{status.message}</p>}
    {signedIn ? <p className="ex-hint">Signs in as <b>{status.signin.username}</b> · <button type="button" className="link-button" onClick={() => setChanging(true)}>Change</button></p>
      : <Signin profileId={profileId} deviceId={deviceId} saved={status.signin} onSaved={next => { setChanging(false); setStatus({ ...status, signin: next }); }} />}
    {signedIn && <div className="ex-actions">
      <label className="ex-field ac-lookup">Name to look up<input aria-label="Name for Windows to look up" value={lookup} onChange={e => setLookup(e.target.value)} autoComplete="off" /></label>
      <button type="button" className="primary-action" disabled={!lookup.trim() && !status.active} onClick={() => setOpen(true)}><ShieldCheck size={17} aria-hidden="true" />{status.active ? "See progress" : status.state === "verified" ? "Run again" : "Run the test"}</button>
    </div>}
    {open && <Tester profileId={profileId} deviceId={deviceId} deviceName={deviceName} lookup={lookup.trim()} status={status} setStatus={setStatus} onClose={() => { setOpen(false); void load(); }} />}
  </div>;
}
