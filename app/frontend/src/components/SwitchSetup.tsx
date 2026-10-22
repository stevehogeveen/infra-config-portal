import { useEffect, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, Check, Loader2, Network, Save, Settings2, X } from "lucide-react";
import { switchSetupApi, type SwitchConsoleRead, type SwitchSetup, type SwitchSetupReview, type SwitchSetupSettings, type SwitchSetupStatus } from "../api";
import { allowOnly, lockReadOnly } from "./storageInstall";
import { GuidePrimary } from "./studio/Guide";

/*
 * First setup of a new switch over its console cable: the settings (name, admin user, management
 * address, SSH), then one window that reviews, runs once and proves the switch answers SSH.
 */

function Row({ state, children }: { state: "done" | "now" | "todo" | "warn"; children: ReactNode }) {
  return <li className={`ei-row ei-${state}`}>
    <span aria-hidden="true">{state === "done" ? <Check size={14} /> : state === "now" ? <Loader2 size={14} className="dr-spin" /> : state === "warn" ? <AlertTriangle size={14} /> : null}</span>
    {children}
  </li>;
}

type Form = SwitchSetupSettings & { username: string; password: string; enablePassword: string };

export function SwitchFirstSetup({ profileId, deviceId, deviceName, consoleRead, hoist, onVerified }: { profileId: string; deviceId: string; deviceName: string; consoleRead: SwitchConsoleRead | null; hoist: boolean; onVerified?: () => void }) {
  const [setup, setSetup] = useState<SwitchSetup | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [status, setStatus] = useState<SwitchSetupStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [open, setOpen] = useState(false);
  const [replacePassword, setReplacePassword] = useState(false);
  async function load() {
    const [next, current] = await Promise.all([switchSetupApi.setup(profileId, deviceId), switchSetupApi.status(profileId, deviceId)]);
    setSetup(next); setStatus(current);
    const base = next.settings ?? next.defaults;
    setForm({ ...base, prefix: base.prefix ?? 24, uplink: base.uplink || "auto", uplink_mode: base.uplink_mode || "access", username: next.username || next.defaults.username, password: "", enablePassword: "" });
  }
  useEffect(() => { setSetup(null); load().catch(err => setError(err instanceof Error ? err.message : String(err))); }, [deviceId]);
  if (!form || !setup) return <p role="status">{error || "Loading the switch settings…"}</p>;
  const set = (change: Partial<Form>) => { setForm({ ...form, ...change }); setMessage(""); };
  const verified = status?.state === "verified";
  const saved = !!setup.settings;
  const answered = !!consoleRead?.answered;
  // Field by field: the saved record and the form agree, so nothing needs saving.
  const stored = setup.settings;
  const same = !!stored && stored.hostname === form.hostname && stored.domain === form.domain && Number(stored.vlan) === Number(form.vlan)
    && stored.mode === form.mode && (form.mode !== "static" || (stored.address === form.address && Number(stored.prefix) === Number(form.prefix) && stored.gateway === form.gateway))
    && stored.save === form.save && (stored.uplink || "auto") === (form.uplink || "auto") && (stored.uplink_mode || "access") === (form.uplink_mode || "access")
    && setup.username === form.username;
  const edited = !saved || !!form.password || !!form.enablePassword || !same;
  const setupBlocker = !answered
    ? "Setup is waiting for step 1. Choose COM5 and select Read the switch; when the switch prompt answers, this button unlocks."
    : edited ? "Save these settings before setting up the switch." : "";
  const openButton = <button type="button" className="rack-plan-save" disabled={busy || !!setupBlocker} title={setupBlocker || undefined} aria-describedby={setupBlocker ? "switch-setup-blocker" : undefined} onClick={() => setOpen(true)}><Settings2 size={16} />{status?.active ? "Show the setup" : verified ? "Set up again" : "Set up the switch"}</button>;
  return <form className="workbench-access sw-setup" onSubmit={async event => {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      const next = await switchSetupApi.save(profileId, deviceId, { hostname: form.hostname.trim(), domain: form.domain.trim(), vlan: Number(form.vlan), mode: form.mode,
        address: form.mode === "static" ? (form.address || "").trim() : null, prefix: form.mode === "static" ? Number(form.prefix) : 24, gateway: form.mode === "static" ? (form.gateway || "").trim() : null,
        save: form.save, uplink: (form.uplink || "").trim() || "auto", uplink_mode: form.uplink_mode || "access", username: form.username.trim(), ...(form.password ? { password: form.password } : {}), ...(form.enablePassword ? { enable_password: form.enablePassword } : {}) });
      setSetup(next); setForm({ ...form, password: "", enablePassword: "" }); setReplacePassword(false);
      setMessage("Settings saved. Nothing was sent to the switch.");
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }}>
    {verified && <p className="inst-ok"><Check size={16} />{status?.message}</p>}
    <div className="sw-grid">
      <label><span className="input-label">Switch name <small>Required</small></span><input aria-label="Switch name" required value={form.hostname} disabled={busy} onChange={e => set({ hostname: e.target.value })} /></label>
      <label><span className="input-label">Domain <small>Needed for SSH keys</small></span><input aria-label="Domain" required value={form.domain} disabled={busy} onChange={e => set({ domain: e.target.value })} /></label>
      <label><span className="input-label">Management VLAN <small>Default 1</small></span><input aria-label="Management VLAN" type="number" min={1} max={4094} required value={form.vlan} disabled={busy} onChange={e => set({ vlan: Number(e.target.value) })} /></label>
    </div>
    <div className="sw-grid">
      <label><span className="input-label">Network cable port <small>{Number(form.vlan) === 1 ? "Not needed for VLAN 1" : "Auto finds it"}</small></span>
        <input aria-label="Network cable port" value={form.uplink === "auto" ? "" : form.uplink ?? ""} disabled={busy} placeholder="Auto-detect" onChange={e => set({ uplink: e.target.value.trim() ? e.target.value : "auto" })} /></label>
      <label><span className="input-label">Network port mode</span>
        <select aria-label="How the port carries the VLAN" value={form.uplink_mode || "access"} disabled={busy} onChange={e => set({ uplink_mode: e.target.value as "access" | "trunk" })}>
          <option value="access">Untagged (access port)</option><option value="trunk">Tagged (trunk port)</option></select></label>
    </div>
    <p className="ex-hint">The switch needs a port in the management VLAN with a cable to your network. The app puts the VLAN on that port; with auto-detect it uses the only port that has a cable connected.</p>
    <div className="sw-mode" role="radiogroup" aria-label="Management address">
      {(["dhcp", "static"] as const).map(mode => <button key={mode} type="button" role="radio" aria-checked={form.mode === mode} disabled={busy} onClick={() => set({ mode })}>
        <b>{mode === "dhcp" ? "DHCP" : "Static address"}</b><span>{mode === "dhcp" ? "The network hands the switch its address" : "You choose the address and gateway"}</span></button>)}
    </div>
    {form.mode === "static" && <div className="sw-grid">
      <label><span className="input-label">Address <small>Required</small></span><input aria-label="Switch management address" required value={form.address ?? ""} disabled={busy} onChange={e => set({ address: e.target.value })} placeholder="IPv4 address" /></label>
      <label><span className="input-label">Prefix length <small>24 = 255.255.255.0</small></span><input aria-label="Prefix length" type="number" min={8} max={30} required value={form.prefix ?? 24} disabled={busy} onChange={e => set({ prefix: Number(e.target.value) })} /></label>
      <label><span className="input-label">Gateway <small>Required</small></span><input aria-label="Gateway" required value={form.gateway ?? ""} disabled={busy} onChange={e => set({ gateway: e.target.value })} placeholder="IPv4 address" /></label>
    </div>}
    <div className="sw-grid">
      <label><span className="input-label">Admin username <small>Required</small></span><input aria-label="Admin username" required value={form.username} disabled={busy} onChange={e => set({ username: e.target.value })} autoComplete="username" /></label>
      {setup.password_configured && !replacePassword
        ? <div className="sw-saved"><span className="input-label">Admin password</span><p>Saved securely</p><button type="button" className="connection-secondary" disabled={busy} onClick={() => setReplacePassword(true)}>Change passwords</button></div>
        : <>
          <label><span className="input-label">Admin password <small>{setup.password_configured ? "Replacement" : "8+ characters"}</small></span><input aria-label="Admin password" type="password" required={!setup.password_configured} value={form.password} disabled={busy} onChange={e => set({ password: e.target.value })} autoComplete="new-password" /></label>
          <label><span className="input-label">Enable password <small>Optional</small></span><input aria-label="Enable password for setup" type="password" value={form.enablePassword} disabled={busy} onChange={e => set({ enablePassword: e.target.value })} autoComplete="new-password" placeholder={setup.enable_password_configured ? "Leave blank to keep saved" : ""} /></label>
        </>}
    </div>
    <label className="workbench-checkbox"><input type="checkbox" checked={form.save} disabled={busy} onChange={e => set({ save: e.target.checked })} />Save the settings on the switch so they survive a restart</label>
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    <div className="ex-actions">
      {edited && <button type="submit" className="rack-plan-save" disabled={busy}><Save size={16} />{busy ? "Saving…" : "Save settings"}</button>}
      {hoist && answered && !edited ? <GuidePrimary>{openButton}</GuidePrimary> : openButton}
    </div>
    {setupBlocker && <p id="switch-setup-blocker" className="ex-hint">{setupBlocker}</p>}
    {open && <SwitchSetupWindow profileId={profileId} deviceId={deviceId} deviceName={deviceName} onClose={async () => { setOpen(false); const current = await switchSetupApi.status(profileId, deviceId); setStatus(current); if (current.state === "verified") onVerified?.(); }} />}
  </form>;
}

function SwitchSetupWindow({ profileId, deviceId, deviceName, onClose }: { profileId: string; deviceId: string; deviceName: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const live = useRef(true);
  const [step, setStep] = useState<0 | 1 | 2 | null>(null);
  const [plan, setPlan] = useState<SwitchSetupReview | null>(null);
  const [status, setStatus] = useState<SwitchSetupStatus | null>(null);
  const [understood, setUnderstood] = useState(false);
  const [replace, setReplace] = useState(false);
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
    void run("Checking the settings and the console cable…", async () => {
      const current = await switchSetupApi.status(profileId, deviceId);
      if (!live.current) return;
      setStatus(current);
      if (current.active) { setStep(1); return; }
      setPlan(await switchSetupApi.review(profileId, deviceId));
      if (live.current) setStep(0);
    });
  }, []);
  const running = step === 1 && !!status?.active && status.state === "running";
  useEffect(() => {
    if (!running) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function tick() {
      try { const next = await switchSetupApi.advance(profileId, deviceId); if (!active) return; setStatus(next); if (!next.active) return; }
      catch { /* read again shortly */ }
      if (active) timer = setTimeout(() => void tick(), 5000);
    }
    timer = setTimeout(() => void tick(), 2000);
    return () => { active = false; clearTimeout(timer); };
  }, [running]);
  useEffect(() => { if (step === 1 && status?.state === "verified") setStep(2); }, [step, status?.state]);

  const start = () => run("Allowing only the switch setup…", async () => {
    await allowOnly("switch_setup_only");
    setBusy("Starting…");
    const next = await switchSetupApi.start(profileId, deviceId, !!plan?.replace_needed && replace);
    if (live.current) { setStatus(next); setStep(1); }
  });
  const closeRun = () => run("Closing this run…", async () => {
    await switchSetupApi.close(profileId, deviceId); await lockReadOnly();
    if (live.current) { setStatus(null); setPlan(await switchSetupApi.review(profileId, deviceId)); setStep(0); }
  });
  const finish = () => run("Locking changes…", async () => { await lockReadOnly(); if (live.current) onClose(); });

  const ready = step === 0 && !!plan?.ready;
  const stuck = status?.state === "needs_attention";
  const phases = status?.phases ?? [];
  const done = phases.filter(p => p.state === "ok").length;
  const percent = step === null ? 0 : step === 0 ? (ready ? 20 : 8) : step === 2 ? 100 : 30 + 35 * done;
  const rowState = (state: string, index: number): "done" | "now" | "todo" | "warn" =>
    state === "ok" ? "done" : state === "failed" || state === "uncertain" ? "warn" : state === "sent" || (running && index === done) ? "now" : "todo";
  const next = step === 0 && ready ? { label: "Set up the switch", run: () => void start(), disabled: !understood || (!!plan?.replace_needed && !replace) } : step === 2 ? { label: "Done", run: () => void finish(), disabled: false } : null;

  return <dialog ref={dialog} className="inst" aria-label={`Set up ${deviceName}`} onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    <header className="inst-h">
      <span className="inst-icon"><Network size={22} aria-hidden="true" /></span>
      <div><h2>Set up the switch</h2><p>{deviceName}</p></div>
      <button type="button" aria-label="Close switch setup" disabled={!!busy && step !== 1} onClick={onClose}><X size={20} /></button>
    </header>
    <div className="inst-body">
      <ol className="inst-steps" aria-label="Setup steps">{["Check", "Set up", "Finish"].map((label, index) =>
        <li key={label} className={step !== null && index < step ? "done" : index === step ? "now" : ""} aria-current={index === step ? "step" : undefined}>
          <span>{step !== null && index < step ? <Check size={13} /> : index + 1}</span>{label}</li>)}</ol>
      <section className="inst-main" aria-live="polite">
        {step === null && <p>Loading…</p>}
        {step === 0 && plan && <>
          <h3>{ready ? "Ready to set up" : "Not ready yet"}</h3>
          {plan.hostname && <dl className="ei-summary">
            <div><dt>Name</dt><dd>{plan.hostname}</dd></div>
            <div><dt>Console</dt><dd>{plan.console_port ?? "—"}{plan.baud ? ` at ${plan.baud}` : ""}</dd></div>
            <div><dt>Address</dt><dd>VLAN {plan.vlan} · {plan.mode === "static" ? `${plan.address}/${plan.prefix} via ${plan.gateway}` : "DHCP"}</dd></div>
            <div><dt>Sign-in</dt><dd>{plan.username} (SSH only)</dd></div>
            <div><dt>Save</dt><dd>{plan.save ? "Yes, survives a restart" : "No, lost on restart"}</dd></div>
          </dl>}
          {!!plan.blockers.length && <div className="fw-stop" role="alert"><strong>Still to do</strong><ul>{plan.blockers.map(item => <li key={item}>{item}</li>)}</ul></div>}
          {!plan.blockers.length && plan.notes?.map(note => <p key={note} className="sd-proof-note" role="note">{note}</p>)}
          {plan.preview && <details className="sw-preview"><summary>What is sent to the switch</summary><pre>{plan.preview.join("\n")}</pre></details>}
          {ready && <>
            <p>The app answers "no" to the new-switch setup dialog, sends the settings above over the console cable{plan.save ? " and saves them" : ""}, then checks that the switch answers SSH at its address. Nothing is erased or restarted. Passwords are sent but never shown or logged.</p>
            <label className="wipe-ok"><input type="checkbox" checked={understood} onChange={event => setUnderstood(event.target.checked)} />I understand {plan.hostname} gets this configuration.</label>
            {plan.replace_needed && <label className="wipe-ok"><input type="checkbox" checked={replace} onChange={event => setReplace(event.target.checked)} />Replace this switch's existing users, management address and SSH settings.</label>}
          </>}
        </>}
        {step === 1 && status && <>
          <h3>{stuck ? "The setup needs attention" : "Setting up the switch…"}</h3>
          <ul className="ei-rows" aria-label="Setup steps">{phases.map((phase, index) => <Row key={phase.phase} state={rowState(phase.state, index)}>{phase.label}{phase.message && phase.state !== "sent" ? <small> · {phase.message}</small> : null}</Row>)}</ul>
          {status.step && !stuck && <p className="ex-hint">Now: {status.step}.</p>}
          {stuck ? <>
            <p className="fw-stop" role="alert">{status.message}</p>
            <p className="ex-hint">Nothing was sent again. Read the switch on its console cable before trying again.</p>
            <div className="ex-actions"><button type="button" className="secondary-action" disabled={!!busy} onClick={() => void closeRun()}>Close this run</button></div>
          </> : <p className="ex-hint">{status.message}</p>}
        </>}
        {step === 2 && status && <>
          <h3>Complete</h3>
          <p className="inst-ok"><Check size={16} />{status.message}</p>
          <ul className="ei-rows">
            {status.model && <Row state="done">{status.model}{status.version ? `, software ${status.version}` : ""}</Row>}
            <Row state="done">Admin sign-in works over SSH</Row>
            <Row state={status.saved ? "done" : "todo"}>{status.saved ? "Settings saved on the switch" : "Settings not saved on the switch"}</Row>
          </ul>
        </>}
        {busy && <p className="inst-busy" role="status">{busy}</p>}
        {error && <p className="fw-stop" role="alert">{error}</p>}
      </section>
    </div>
    <div className="inst-progress" aria-label="Progress">
      <div className={`inst-bar ${step === 2 ? "done" : stuck ? "warn" : ""} ${running || !!busy ? "moving" : ""}`} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}><span style={{ width: `${percent}%` }} /></div>
      <small>Step {step === null ? 1 : step + 1} of 3 · {step === null ? "" : ["Check", "Set up", "Finish"][step]}</small>
    </div>
    <footer className="inst-f">
      <button type="button" className="secondary-action" disabled={!!busy && step !== 1} onClick={onClose}>{running ? "Close (keeps going)" : "Cancel"}</button>
      <span className="inst-grow" />
      {next && <button type="button" className="primary-action inst-next" disabled={!!busy || next.disabled} onClick={next.run}>{next.label}</button>}
    </footer>
  </dialog>;
}
