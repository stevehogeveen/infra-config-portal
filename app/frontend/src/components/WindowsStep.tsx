import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { AlertTriangle, Check, Database, ExternalLink, HardDrive, Loader2, Monitor, Package, Rocket, Server, X } from "lucide-react";
import { api, windowsApi, type WindowsReview, type WindowsSetup, type WindowsStatus } from "../api";
import type { LabProfileList as LabProfileState } from "../types";
import type { RackPlan } from "./RackPlanner";
import { MediaDropZone } from "./MediaDropZone";
import { allowOnly, lockReadOnly } from "./storageInstall";
import { size } from "./bays";

/*
 * Install Windows: three steps per server. 1 choose the Windows OVA/OVF (or add one), 2 name the
 * VM and pick its datastore and network, 3 deploy. Steps 1 and 2 save the plan only; step 3 opens
 * the installer: one tick and one button import the image onto the verified ESXi host, power the
 * VM on, and wait for VMware Tools to report its address. Done returns the server to read-only.
 */

type ServerRow = { name: string; model: string; deviceId: string };

function Step({ n, title, done, icon, children, summary, keepOpen = false }: { n: number; title: string; done: boolean; icon: ReactNode; children: ReactNode; summary?: ReactNode; keepOpen?: boolean }) {
  const [open, setOpen] = useState(!done || keepOpen);
  useEffect(() => { if (!done || keepOpen) setOpen(true); }, [done, keepOpen]);
  const folded = done && !keepOpen && !open;
  return <section className={`ex-step ${done ? "is-done" : ""} ${folded ? "is-folded" : ""}`} aria-label={title}>
    <header><span className="ex-num">{done ? <Check size={15} aria-hidden="true" /> : n}</span><span className="ex-icon" aria-hidden="true">{icon}</span>
      <div><h2>{title}</h2>{summary && <p>{summary}</p>}</div>
      {done && !keepOpen && <button type="button" className="ex-change" aria-expanded={open} onClick={() => setOpen(value => !value)}>{open ? "Done" : "Change"}</button>}</header>
    {!folded && <div className="ex-body">{children}</div>}
  </section>;
}

function Row({ state, children }: { state: "done" | "now" | "todo" | "warn"; children: ReactNode }) {
  return <li className={`ei-row ei-${state}`}>
    <span aria-hidden="true">{state === "done" ? <Check size={14} /> : state === "now" ? <Loader2 size={14} className="dr-spin" /> : state === "warn" ? <AlertTriangle size={14} /> : null}</span>
    {children}
  </li>;
}

function SettingsForm({ profileId, deviceId, setup, image, onSaved }: { profileId: string; deviceId: string; setup: WindowsSetup; image: string | null; onSaved: (next: WindowsSetup) => void }) {
  const host = setup.host;
  const [name, setName] = useState(setup.vm_name || "windows01");
  const [datastore, setDatastore] = useState(setup.datastore || host.default_datastore || host.datastores.find(d => d.name !== "datastore1")?.name || host.datastores[0]?.name || "");
  const [network, setNetwork] = useState(setup.network || host.networks[0] || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const problem = !image ? "Choose the Windows image in step 1." : !/^[A-Za-z0-9][A-Za-z0-9-]{0,62}$/.test(name.trim()) ? "Name the VM with letters, digits and dashes."
    : !datastore ? "Choose a datastore." : !network ? "Choose a VM network." : "";
  async function save(event: FormEvent) {
    event.preventDefault();
    if (problem) { setError(problem); return; }
    setBusy(true); setError(""); setSaved("");
    try { onSaved(await windowsApi.save(profileId, deviceId, { image: image!, vm_name: name.trim(), datastore, network })); setSaved("Saved. Nothing was sent to ESXi."); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }
  return <form className="ex-form" onSubmit={event => void save(event)}>
    <div className="ex-grid">
      <label className="ex-field">VM name<input aria-label="Windows VM name" value={name} disabled={busy} onChange={e => setName(e.target.value)} autoComplete="off" />
        <small>As it appears in ESXi. Windows gets its own computer name from the image.</small></label>
      <div className="ex-field">Network<div className="ex-seg" role="radiogroup" aria-label="VM network">{host.networks.map(item =>
        <button key={item} type="button" role="radio" aria-checked={network === item} disabled={busy} onClick={() => setNetwork(item)}>{item}</button>)}</div>
        <small>The VM gets its address from DHCP on this network.</small></div>
    </div>
    <div className="ex-field">Datastore
      <div className="win-stores" role="radiogroup" aria-label="Datastore for the VM">{host.datastores.map(store =>
        <button key={store.name} type="button" role="radio" aria-checked={datastore === store.name} disabled={busy} onClick={() => setDatastore(store.name)}>
          <Database size={16} aria-hidden="true" /><b>{store.name}</b><span>{size(store.free)} free of {size(store.capacity)}</span>
          {store.name === host.default_datastore && <em>VM datastore</em>}</button>)}</div>
    </div>
    <div className="ex-actions">
      <button type="submit" className="primary-action" disabled={busy}>{busy ? "Saving…" : "Save VM settings"}</button>
      {saved && <span className="inst-ok" role="status"><Check size={15} />{saved}</span>}
    </div>
    {error && <p className="fw-stop" role="alert">{error}</p>}
  </form>;
}

function WindowsInstaller({ profileId, deviceId, deviceName, onClose }: { profileId: string; deviceId: string; deviceName: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const live = useRef(true);
  const [step, setStep] = useState<0 | 1 | 2 | null>(null);
  const [plan, setPlan] = useState<WindowsReview | null>(null);
  const [status, setStatus] = useState<WindowsStatus | null>(null);
  const [understood, setUnderstood] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { live.current = true; if (!dialog.current?.open) dialog.current?.showModal(); return () => { live.current = false; }; }, []);
  async function run(label: string, work: () => Promise<void>) {
    setBusy(label); setError("");
    try { await work(); } catch (err) { if (live.current) setError(err instanceof Error ? err.message : String(err)); }
    finally { if (live.current) setBusy(""); }
  }
  const opened = useRef(false);
  useEffect(() => {
    if (opened.current) return;
    opened.current = true;
    void run("Reading ESXi and the image…", async () => {
      const current = await windowsApi.status(profileId, deviceId);
      if (!live.current) return;
      setStatus(current);
      if (current.active) { setStep(1); return; }
      setPlan(await windowsApi.review(profileId, deviceId));
      if (live.current) setStep(0);
    });
  }, []);
  const running = step === 1 && !!status?.active && status.state === "running";
  useEffect(() => {
    if (!running) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function tick() {
      try { const next = await windowsApi.advance(profileId, deviceId); if (!active) return; setStatus(next); if (!next.active) return; }
      catch { /* ESXi busy; read again shortly */ }
      if (active) timer = setTimeout(() => void tick(), 15000);
    }
    timer = setTimeout(() => void tick(), 3000);
    return () => { active = false; clearTimeout(timer); };
  }, [running]);
  useEffect(() => { if (step === 1 && status?.state === "verified") setStep(2); }, [step, status?.state]);

  const start = () => run("Allowing only the Windows deployment on this server…", async () => {
    await allowOnly("vm_deploy_only");
    setBusy("Starting the import…");
    const next = await windowsApi.start(profileId, deviceId);
    if (live.current) { setStatus(next); setStep(1); }
  });
  const closeRun = () => run("Closing this run…", async () => {
    await windowsApi.close(profileId, deviceId); await lockReadOnly();
    if (live.current) { setStatus(null); setPlan(await windowsApi.review(profileId, deviceId)); setStep(0); }
  });
  const finish = () => run("Locking the server…", async () => { await lockReadOnly(); if (live.current) onClose(); });

  const ready = step === 0 && !!plan?.ready;
  const stuck = status?.state === "needs_attention";
  const phases = status?.phases ?? [];
  const done = phases.filter(p => p.state === "ok").length;
  const percent = step === null ? 0 : step === 0 ? (ready ? 20 : 8) : step === 2 ? 100 : 25 + 25 * done;
  const rowState = (state: string, index: number): "done" | "now" | "todo" | "warn" =>
    state === "ok" ? "done" : state === "failed" || state === "uncertain" ? "warn" : state === "sent" || (running && index === done) ? "now" : "todo";
  const next = step === 0 && ready ? { label: "Deploy Windows", run: () => void start(), disabled: !understood } : step === 2 ? { label: "Done", run: () => void finish(), disabled: false } : null;

  return <dialog ref={dialog} className="inst" aria-label={`Deploy Windows on ${deviceName}`} onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    <header className="inst-h">
      <span className="inst-icon"><Monitor size={22} aria-hidden="true" /></span>
      <div><h2>Deploy Windows</h2><p>{deviceName}</p></div>
      <button type="button" aria-label="Close Windows installer" disabled={!!busy && step !== 1} onClick={onClose}><X size={20} /></button>
    </header>
    <div className="inst-body">
      <ol className="inst-steps" aria-label="Installer steps">{["Check", "Deploy", "Finish"].map((label, index) =>
        <li key={label} className={step !== null && index < step ? "done" : index === step ? "now" : ""} aria-current={index === step ? "step" : undefined}>
          <span>{step !== null && index < step ? <Check size={13} /> : index + 1}</span>{label}</li>)}</ol>
      <section className="inst-main" aria-live="polite">
        {step === null && <p>Loading…</p>}
        {step === 0 && plan && <>
          <h3>{ready ? "Ready to deploy" : "Not ready yet"}</h3>
          {plan.image && <dl className="ei-summary">
            <div><dt>Image</dt><dd>{plan.image}{plan.size_bytes ? ` (${size(plan.size_bytes)})` : ""}</dd></div>
            <div><dt>VM</dt><dd>{plan.vm_name}</dd></div>
            <div><dt>Datastore</dt><dd>{plan.datastore}{plan.free_bytes ? ` · ${size(plan.free_bytes)} free` : ""}</dd></div>
            <div><dt>Network</dt><dd>{plan.network} · DHCP</dd></div>
            <div><dt>ESXi</dt><dd>{plan.address}</dd></div>
          </dl>}
          {!!plan.blockers.length && <div className="fw-stop" role="alert"><strong>Still to do</strong><ul>{plan.blockers.map(item => <li key={item}>{item}</li>)}</ul></div>}
          {ready && <>
            <p>The image is copied onto {plan.datastore} as a new, thin-provisioned VM, powered on, and checked once Windows starts and VMware Tools reports its address. Nothing else on the server or ESXi changes. Large images take a while; you can close this window and come back.</p>
            <label className="wipe-ok"><input type="checkbox" checked={understood} onChange={event => setUnderstood(event.target.checked)} />I understand a new VM named {plan.vm_name} is created and started.</label>
          </>}
        </>}
        {step === 1 && status && <>
          <h3>{stuck ? "The deployment needs attention" : "Deploying Windows…"}</h3>
          <ul className="ei-rows" aria-label="Deployment steps">{phases.map((phase, index) => <Row key={phase.phase} state={rowState(phase.state, index)}>{phase.label}</Row>)}</ul>
          {status.last_check && !stuck && <p className="ex-hint">Last check: VM {status.last_check.power ?? "unknown"}, VMware Tools {status.last_check.tools === "guestToolsRunning" ? "running" : "not running yet"}{status.last_check.address ? `, address ${status.last_check.address}` : ""}.</p>}
          {stuck ? <>
            <p className="fw-stop" role="alert">{status.message}</p>
            <p className="ex-hint">Nothing was sent again. If a partly imported VM is left on ESXi, remove it in the ESXi host client before deploying again.</p>
            <div className="ex-actions"><button type="button" className="secondary-action" disabled={!!busy} onClick={() => void closeRun()}>Close this run</button></div>
          </> : <p className="ex-hint">{status.message}</p>}
        </>}
        {step === 2 && status && <>
          <h3>Complete</h3>
          <p className="inst-ok"><Check size={16} />{status.vm_name} is running Windows at {status.address}.</p>
          <ul className="ei-rows">
            <Row state="done">VMware Tools running</Row>
            {status.hostname && <Row state="done">Computer name: {status.hostname}</Row>}
            {status.guest_os && <Row state="done">{status.guest_os}</Row>}
          </ul>
          {status.esxi_address && <p><a href={`https://${status.esxi_address}/ui/#/host/vms`} target="_blank" rel="noreferrer"><ExternalLink size={14} /> Open the VM in the ESXi host client</a></p>}
        </>}
        {busy && <p className="inst-busy" role="status">{busy}</p>}
        {error && <p className="fw-stop" role="alert">{error}</p>}
      </section>
    </div>
    <div className="inst-progress" aria-label="Progress">
      <div className={`inst-bar ${step === 2 ? "done" : stuck ? "warn" : ""} ${running || !!busy ? "moving" : ""}`} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}><span style={{ width: `${percent}%` }} /></div>
      <small>Step {step === null ? 1 : step + 1} of 3 · {step === null ? "" : ["Check", "Deploy", "Finish"][step]}</small>
    </div>
    <footer className="inst-f">
      <button type="button" className="secondary-action" disabled={!!busy && step !== 1} onClick={onClose}>{running ? "Close (keeps going)" : "Cancel"}</button>
      <span className="inst-grow" />
      {next && <button type="button" className="primary-action inst-next" disabled={!!busy || next.disabled} onClick={next.run}>{next.label}</button>}
    </footer>
  </dialog>;
}

export function WindowsStep({ labProfileState }: { labProfileState?: LabProfileState | null }) {
  const profileId = labProfileState?.active_profile?.id;
  const location = useLocation();
  const navigate = useNavigate();
  const [servers, setServers] = useState<ServerRow[] | null>(null);
  const [setup, setSetup] = useState<WindowsSetup | null>(null);
  const [status, setStatus] = useState<WindowsStatus | null>(null);
  const [image, setImage] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [installer, setInstaller] = useState(false);
  useEffect(() => {
    let active = true;
    setServers(null); setError("");
    if (!profileId) return;
    api.rackPlan(profileId).then((plan: RackPlan) => { if (active) setServers(plan.equipment.filter(item => item.kind === "server" && item.device_id).map(item => ({ name: item.name, model: item.model, deviceId: item.device_id! }))); })
      .catch(err => { if (active) setError(err instanceof Error ? err.message : String(err)); });
    return () => { active = false; };
  }, [profileId]);
  const requested = new URLSearchParams(location.search).get("device");
  const server = servers ? (servers.find(item => item.deviceId === requested) ?? servers[0]) : undefined;
  async function load() {
    if (!profileId || !server) return;
    try {
      const [nextSetup, nextStatus] = await Promise.all([windowsApi.setup(profileId, server.deviceId), windowsApi.status(profileId, server.deviceId)]);
      setSetup(nextSetup); setStatus(nextStatus); setImage(current => current ?? nextSetup.image);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }
  useEffect(() => { setSetup(null); setStatus(null); setImage(null); void load(); }, [profileId, server?.deviceId]);

  if (!profileId) return <p>Select a kit first.</p>;
  const chosen = setup?.images.find(item => item.path === image);
  const imageDone = !!chosen && !chosen.missing.length;
  const settingsDone = !!setup?.saved_at && setup.image === image;
  const host = setup?.host;
  return <section className="ex-page" aria-label="Install Windows">
    <header className="journey-heading"><h1>Install Windows</h1><p>Choose the Windows image, name the VM, then deploy it onto ESXi. Steps 1 and 2 only save your plan.</p></header>
    {error && <p className="fw-stop" role="alert">{error}</p>}
    {!servers && !error && <p role="status">Loading servers…</p>}
    {servers && servers.length > 1 && <label className="ex-server-pick">Server<select aria-label="Server for Windows" value={server?.deviceId} onChange={e => navigate("/setup/install-windows?device=" + encodeURIComponent(e.target.value))}>{servers.map(item => <option key={item.deviceId} value={item.deviceId}>{item.name}</option>)}</select></label>}
    {server && <article className="ex-card" aria-label={server.name}>
      <header className="ex-card-head"><Server size={20} aria-hidden="true" /><div><strong>{server.name}</strong><small>{host?.address ? `ESXi ${host.address}` : server.model}</small></div>
        {status?.state === "verified" && <span className="fw-pill fw-pill-ok">Windows running</span>}
        {status?.active && <span className="fw-pill fw-pill-up">Deploying</span>}</header>
      {!setup ? <p className="dr-loading" role="status">Loading…</p> : host?.problem ? <div className="fw-stop" role="alert"><p>{host.problem}</p><p><Link to={`/setup/prepare-esxi?device=${encodeURIComponent(server.deviceId)}`}>Open Prepare ESXi</Link></p></div> : <div className="ex-steps">
        <Step n={1} title="Windows image" icon={<Package size={18} />} done={imageDone} summary={chosen ? <>Using <b>{chosen.name}</b></> : "Choose the Windows OVA or OVF to deploy."}>
          {!setup.images.length && <p className="ex-hint">No OVA or OVF is in the media folder yet. Add your Windows image below.</p>}
          {!!setup.images.length && <div className="ex-isos" role="radiogroup" aria-label="Windows image">{setup.images.map(item => {
            const active = image === item.path;
            return <button key={item.path} type="button" role="radio" aria-checked={active} className={`ex-iso ${active ? "is-on" : ""}`} disabled={uploading || !!status?.active} onClick={() => setImage(item.path)}>
              <HardDrive size={22} aria-hidden="true" /><span><strong>{item.name}</strong><small>{item.kind.toUpperCase()}{item.folder ? ` · in ${item.folder}` : ""}{item.missing.length ? ` · incomplete, ${item.missing.length} ${item.missing.length === 1 ? "file" : "files"} missing` : ""}</small></span>
              <span className="ex-iso-meta">{item.missing.length ? "—" : size(item.size_bytes)}{item.windows && <b>Windows</b>}</span>
              {active && <Check className="ex-iso-check" size={18} aria-hidden="true" />}</button>;
          })}</div>}
          {chosen?.missing.length ? <div className="fw-stop" role="alert">
            <p><b>This OVF export is incomplete.</b> An .ovf is only the description; it needs the other files from the same export, in the same folder{chosen.folder ? <> (<b>{chosen.folder}</b>)</> : ""}:</p>
            <ul>{chosen.missing.map(name => <li key={name}><code>{name}</code>{/\.vmdk$/i.test(name) ? " (the virtual disk)" : /\.nvram$/i.test(name) ? " (the VM's firmware settings)" : ""}</li>)}</ul>
            <p>Copy them into that folder, or add them below; they upload next to the .ovf.</p>
          </div> : null}
          <details className="ex-add" open={!setup.images.length || !!chosen?.missing.length}><summary>{chosen?.missing.length ? "Add the missing files" : "Add a Windows image"}</summary>
            <MediaDropZone profileId={profileId} folder={chosen?.missing.length ? chosen.folder ?? "" : ""} kind="vm" disabled={!!status?.active} onUploading={setUploading} onUploaded={load} />
          </details>
        </Step>
        <Step n={2} title="VM settings" icon={<Database size={18} />} done={settingsDone} summary={settingsDone ? <>{setup.vm_name} · {setup.datastore} · {setup.network}</> : "Name, datastore and network."}>
          <SettingsForm key={setup.saved_at ?? "new"} profileId={profileId} deviceId={server.deviceId} setup={setup} image={image} onSaved={next => { setSetup(next); }} />
        </Step>
        <Step n={3} title="Deploy Windows" icon={<Rocket size={18} />} done={status?.state === "verified"} keepOpen summary={status?.state === "verified" ? `Running at ${status.address}.` : "Import, power on and verify."}>
          {status?.state === "verified" ? <div className="ex-done"><Check size={22} aria-hidden="true" />
            <div><strong>Windows is running</strong><p>{status.vm_name} at {status.address}{status.hostname ? ` · ${status.hostname}` : ""}</p></div>
            <button type="button" className="secondary-action" onClick={() => setInstaller(true)}>Review</button></div>
            : <>
              {!(imageDone && settingsDone) && <p className="ex-hint">Choose the image and save the VM settings first.</p>}
              <button type="button" className="primary-action ex-go" disabled={!(imageDone && settingsDone) && !status?.active} onClick={() => setInstaller(true)}><Rocket size={17} aria-hidden="true" />{status?.active ? "See progress" : "Deploy Windows"}</button>
            </>}
        </Step>
      </div>}
    </article>}
    {installer && server && <WindowsInstaller profileId={profileId} deviceId={server.deviceId} deviceName={server.name} onClose={() => { setInstaller(false); void load(); }} />}
  </section>;
}
