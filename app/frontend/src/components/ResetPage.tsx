import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, Eraser, KeyRound, Loader2, Lock, Network, Server, X } from "lucide-react";
import { resetApi, type KitReset, type SwitchResetReview, type SwitchResetStatus } from "../api";
import { useStudio } from "./studio/StudioContext";
import { WipeInstaller } from "./WipeInstaller";
import { allowTyped, lockReadOnly } from "./storageInstall";

/*
 * Reset for the next person. Locked down: the lab must allow it (LAB_ALLOW_FACTORY_RESET), the page
 * opens only after typing RESET THIS KIT, and every erase has its own review and typed confirmation.
 * 1 wipe each server's disks (the Disks & RAID wipe), 2 erase the switch over its console,
 * 3 forget this PC's saved sign-ins for the kit.
 */

const UNLOCK = "RESET THIS KIT";
const SCOPE_PHRASE = "ONLY RESET THE SWITCH";

function SwitchResetDialog({ profileId, deviceId, status, setStatus, onClose }: { profileId: string; deviceId: string; status: SwitchResetStatus; setStatus: (next: SwitchResetStatus) => void; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const live = useRef(true);
  const [review, setReview] = useState<SwitchResetReview | null>(null);
  const [typed, setTyped] = useState("");
  const [scopeTyped, setScopeTyped] = useState("");
  const [begun, setBegun] = useState(status.active);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { live.current = true; if (!dialog.current?.open) dialog.current?.showModal(); return () => { live.current = false; }; }, []);
  useEffect(() => { if (!status.active) resetApi.switchReview(profileId, deviceId).then(next => { if (live.current) setReview(next); }).catch(err => setError(err instanceof Error ? err.message : String(err))); }, []);
  async function run(label: string, work: () => Promise<void>) {
    setBusy(label); setError("");
    try { await work(); } catch (err) { if (live.current) setError(err instanceof Error ? err.message : String(err)); }
    finally { if (live.current) setBusy(""); }
  }
  const start = () => run("Allowing only the switch reset…", async () => {
    await allowTyped("switch_reset_only", scopeTyped);
    setBusy("Erasing over the console…");
    try { setStatus(await resetApi.switchStart(profileId, deviceId, typed)); if (live.current) setBegun(true); }
    catch (err) {
      // A lost reply may still have started the erase: read what the app recorded, never resend.
      const now = await resetApi.switchStatus(profileId, deviceId).catch(() => null);
      if (now?.active) { setStatus(now); if (live.current) setBegun(true); return; }
      await lockReadOnly().catch(() => undefined);
      throw err;
    }
  });
  const closeRun = () => run("Closing this run…", async () => {
    setStatus(await resetApi.switchClose(profileId, deviceId)); await lockReadOnly();
    if (live.current) { setBegun(false); setTyped(""); setReview(await resetApi.switchReview(profileId, deviceId)); }
  });
  const showRun = status.active || begun;
  const ready = !!review?.ready && !review.permission.length;
  return <dialog ref={dialog} className="inst" aria-label={`Erase ${status.name}`} onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    <header className="inst-h">
      <span className="inst-icon"><Eraser size={22} aria-hidden="true" /></span>
      <div><h2>Erase the switch</h2><p>{status.name}</p></div>
      <button type="button" aria-label="Close switch reset" onClick={onClose}><X size={20} /></button>
    </header>
    <div className="inst-body"><section className="inst-main" aria-live="polite">
      {showRun ? <>
        <h3>{status.state === "verified" ? "Back to factory settings" : status.state === "needs_attention" ? "The reset needs attention" : "Erasing…"}</h3>
        <ul className="ei-rows" aria-label="Reset steps">{status.phases.map(phase => <li key={phase.phase} className={`ei-row ${phase.state === "ok" ? "ei-done" : phase.state === "sent" ? "ei-now" : phase.state === "todo" ? "ei-todo" : "ei-warn"}`}>
          <span aria-hidden="true">{phase.state === "ok" ? <Check size={14} /> : phase.state === "sent" ? <Loader2 size={14} className="dr-spin" /> : phase.state === "todo" ? null : <AlertTriangle size={14} />}</span>{phase.label}</li>)}</ul>
        {status.step && status.state === "running" && <p className="ex-hint">Now: {status.step}.</p>}
        {status.state === "needs_attention" && <p className="fw-stop" role="alert">{status.message}</p>}
      </> : !review ? <p>Reading…</p> : <>
        <h3>{ready ? "This erases" : "Not ready yet"}</h3>
        <ul className="rs-erases">{review.erases.map(item => <li key={item}>{item}</li>)}</ul>
        <dl className="ei-summary">
          <div><dt>Console</dt><dd>{review.console_port ?? "—"}{review.baud ? ` · ${review.baud} baud` : ""}</dd></div>
          <div><dt>Switch</dt><dd>{review.model ?? "—"}{review.serial ? ` · serial ${review.serial}` : ""}</dd></div>
        </dl>
        {!!(review.blockers.length || review.permission.length) && <div className="fw-stop" role="alert"><strong>Still to do</strong><ul>{[...review.blockers, ...review.permission].map(item => <li key={item}>{item}</li>)}</ul></div>}
        {ready && <>
          <label className="ex-field">Type <b>{SCOPE_PHRASE}</b> to allow only this reset
            <input aria-label="Type the permission phrase" value={scopeTyped} autoComplete="off" onChange={e => setScopeTyped(e.target.value)} /></label>
          <label className="ex-field">Type <b>{review.phrase}</b> to erase it
            <input aria-label="Type the erase phrase" value={typed} autoComplete="off" onChange={e => setTyped(e.target.value)} /></label>
        </>}
      </>}
      {busy && <p className="inst-busy" role="status">{busy}</p>}
      {error && <p className="fw-stop" role="alert">{error}</p>}
    </section></div>
    <footer className="inst-f">
      <button type="button" className="secondary-action" disabled={!!busy} onClick={onClose}>{status.active ? "Close (keeps checking on this page)" : "Cancel"}</button>
      <span className="inst-grow" />
      {!showRun && ready && <button type="button" className="danger-action inst-next" disabled={!!busy || typed !== review!.phrase || scopeTyped !== SCOPE_PHRASE} onClick={() => void start()}>Erase the switch</button>}
      {status.state === "needs_attention" && status.active && <button type="button" className="secondary-action" disabled={!!busy} onClick={() => void closeRun()}>Close this run</button>}
      {status.state === "verified" && <button type="button" className="primary-action inst-next" onClick={onClose}>Done</button>}
    </footer>
  </dialog>;
}

function SwitchCard({ profileId, item }: { profileId: string; item: KitReset["switches"][number] }) {
  const [status, setStatus] = useState<SwitchResetStatus>(item.reset);
  const [open, setOpen] = useState(false);
  const running = status.active && status.state === "running";
  const wasActive = useRef(status.active);
  useEffect(() => {
    if (status.active) wasActive.current = true;
    else if (wasActive.current) { wasActive.current = false; void lockReadOnly().catch(() => undefined); }
  }, [status.active]);
  useEffect(() => {
    if (!running) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function tick() {
      try { const next = await resetApi.switchAdvance(profileId, item.device_id); if (!active) return; setStatus(next); if (!next.active) return; }
      catch { /* read again shortly */ }
      if (active) timer = setTimeout(() => void tick(), 10000);
    }
    timer = setTimeout(() => void tick(), 3000);
    return () => { active = false; clearTimeout(timer); };
  }, [running, profileId, item.device_id]);
  return <li className="rs-item">
    <Network size={18} aria-hidden="true" />
    <div><b>{item.name}</b> <small>{item.model}</small><ul className="rs-erases">{item.erases.map(text => <li key={text}>{text}</li>)}</ul>
      {status.state === "verified" && <p className="inst-ok"><Check size={15} />Back to factory settings.</p>}
      {status.state === "needs_attention" && <p className="fw-stop">{status.message}</p>}</div>
    <button type="button" className={status.active ? "secondary-action" : "danger-action"} onClick={() => setOpen(true)}>{status.active ? "See progress" : "Erase the switch"}</button>
    {open && <SwitchResetDialog profileId={profileId} deviceId={item.device_id} status={status} setStatus={setStatus} onClose={() => setOpen(false)} />}
  </li>;
}

export function ResetPage({ profileId: given }: { profileId?: string } = {}) {
  const studio = useStudio();
  const profileId = given ?? studio?.profileId;
  const [data, setData] = useState<KitReset | null>(null);
  const [error, setError] = useState("");
  const [unlock, setUnlock] = useState("");
  const [wiper, setWiper] = useState<{ deviceId: string; name: string } | null>(null);
  const [forget, setForget] = useState("");
  const [forgotten, setForgotten] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  const load = () => { if (profileId) resetApi.summary(profileId).then(setData).catch(err => setError(err instanceof Error ? err.message : String(err))); };
  useEffect(load, [profileId]);
  async function doForget() {
    if (!profileId) return;
    setBusy(true); setError("");
    try { const next = await resetApi.forget(profileId, forget); setData(next); setForgotten(next.removed ?? []); setForget(""); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }
  if (!profileId) return <p>Select a kit first.</p>;
  if (error && !data) return <p className="fw-stop" role="alert">{error}</p>;
  if (!data) return <p role="status">Loading…</p>;
  const signins = [...data.servers.flatMap(s => s.signins.map(x => `${s.name}: ${x}`)), ...data.switches.flatMap(s => s.signins.map(x => `${s.name}: ${x}`))];
  return <section className="ex-page rs-page" aria-label="Reset for the next person">
    <header className="journey-heading"><h1>Reset for the next person</h1><p>Erase this kit so it starts again as new equipment.</p></header>
    {!data.enabled ? <div className="rs-locked" role="status"><Lock size={20} aria-hidden="true" /><div><b>Reset is turned off for this lab.</b>
      <p>It needs LAB_ALLOW_FACTORY_RESET=true in the lab settings and the app in lab read-write mode.</p></div></div>
      : unlock !== UNLOCK ? <div className="rs-locked"><Lock size={20} aria-hidden="true" /><div><b>Locked.</b> Everything below erases equipment.
        <label className="ex-field">Type <b>{UNLOCK}</b> to show the reset steps<input aria-label="Type the unlock phrase" value={unlock} autoComplete="off" onChange={e => setUnlock(e.target.value)} /></label></div></div>
      : <div className="ex-steps">
        <section className="ex-step" aria-label="Wipe the server disks"><header><span className="ex-num">1</span><span className="ex-icon" aria-hidden="true"><Server size={18} /></span><div><h2>Wipe the server disks</h2></div></header>
          <div className="ex-body"><ul className="rs-list">{data.servers.map(item => <li key={item.device_id} className="rs-item"><Server size={18} aria-hidden="true" />
            <div><b>{item.name}</b> <small>{item.model}</small><ul className="rs-erases">{item.erases.map(text => <li key={text}>{text}</li>)}</ul></div>
            <button type="button" className="danger-action" onClick={() => setWiper({ deviceId: item.device_id, name: item.name })}>Wipe disks</button></li>)}
            {!data.servers.length && <li className="ex-hint">No servers in this kit.</li>}</ul></div></section>
        <section className="ex-step" aria-label="Erase the switch"><header><span className="ex-num">2</span><span className="ex-icon" aria-hidden="true"><Network size={18} /></span><div><h2>Erase the switch</h2><p>Over the console cable.</p></div></header>
          <div className="ex-body"><ul className="rs-list">{data.switches.map(item => <SwitchCard key={item.device_id} profileId={profileId} item={item} />)}
            {!data.switches.length && <li className="ex-hint">No switches in this kit.</li>}</ul></div></section>
        <section className="ex-step" aria-label="Forget saved sign-ins"><header><span className="ex-num">3</span><span className="ex-icon" aria-hidden="true"><KeyRound size={18} /></span><div><h2>Forget saved sign-ins</h2><p>Only on this PC. The iLO sign-in stays.</p></div></header>
          <div className="ex-body">
            {signins.length ? <><ul className="rs-erases">{signins.map(text => <li key={text}>{text}</li>)}</ul>
              <div className="ex-actions"><label className="ex-field">Type <b>{data.forget_phrase}</b><input aria-label="Type the forget phrase" value={forget} autoComplete="off" onChange={e => setForget(e.target.value)} /></label>
                <button type="button" className="danger-action" disabled={busy || forget !== data.forget_phrase} onClick={() => void doForget()}>Forget them</button></div></>
              : <p className="inst-ok"><Check size={15} />No saved sign-ins left for this kit.</p>}
            {forgotten && <p className="ex-hint" role="status">Forgot {forgotten.length} saved sign-in{forgotten.length === 1 ? "" : "s"}.</p>}
          </div></section>
      </div>}
    {error && <p className="fw-stop" role="alert">{error}</p>}
    {wiper && <WipeInstaller profileId={profileId} deviceId={wiper.deviceId} deviceName={wiper.name} onClose={() => { setWiper(null); load(); }} />}
  </section>;
}
