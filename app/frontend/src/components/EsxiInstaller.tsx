import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, ExternalLink, Loader2, Rocket, X } from "lucide-react";
import { api, type EsxiInstallerBuild, type EsxiInstallStatus, type EsxiSettings } from "../api";
import { allowOnly, lockReadOnly } from "./storageInstall";
import { size } from "./bays";

/*
 * Windows-style ESXi installer: Check -> Install -> Finish. One tick and one button, no typing.
 * Check builds the unattended installer ISO offline if needed (nothing touches the server).
 * Install narrows permission to "ESXi install only", then the server side attaches the installer,
 * sets a one-time boot from it and powers on or restarts, each step read back and never resent.
 * The window then watches until ESXi answers, signs in as root to prove the host name, address,
 * VLAN and boot disk, and only then ejects the installer and creates the reviewed VM datastore.
 * Done returns the server to read-only.
 */

const STEPS = ["Check", "Install", "Finish"] as const;
type Step = 0 | 1 | 2;

function Row({ state, children }: { state: "done" | "now" | "todo" | "warn"; children: React.ReactNode }) {
  return <li className={`ei-row ei-${state}`}>
    <span aria-hidden="true">{state === "done" ? <Check size={14} /> : state === "now" ? <Loader2 size={14} className="dr-spin" /> : state === "warn" ? <AlertTriangle size={14} /> : null}</span>
    {children}
  </li>;
}

function elapsed(since?: string) {
  if (!since) return "";
  const minutes = Math.max(0, Math.round((Date.now() - Date.parse(since)) / 60000));
  return minutes < 1 ? "just started" : `${minutes} min`;
}

export function EsxiInstaller({ profileId, deviceId, deviceName, settings, onClose }: {
  profileId: string; deviceId: string; deviceName: string; settings: EsxiSettings; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const live = useRef(true);
  const [step, setStep] = useState<Step | null>(null);
  const [build, setBuild] = useState<EsxiInstallerBuild | null>(null);
  const [status, setStatus] = useState<EsxiInstallStatus | null>(null);
  const [understood, setUnderstood] = useState(false);
  const [typedAddress, setTypedAddress] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [, tick] = useState(0);
  useEffect(() => { live.current = true; if (!dialog.current?.open) dialog.current?.showModal(); return () => { live.current = false; }; }, []);

  async function run(label: string, work: () => Promise<void>) {
    setBusy(label); setError("");
    try { await work(); } catch (err) { if (live.current) setError(err instanceof Error ? err.message : String(err)); }
    finally { if (live.current) setBusy(""); }
  }
  // Open: a run already underway lands on Install; otherwise check, building the installer if needed.
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void run("Reading the recorded status…", async () => {
      const current = await api.esxiInstall(profileId, deviceId);
      if (!live.current) return;
      setStatus(current);
      if (current.state === "verified" || current.state === "reachable") { setStep(2); return; }
      if (current.active) { setStep(1); return; }
      setStep(0);
      let next = await api.esxiInstaller(profileId, deviceId);
      if (!live.current) return;
      setBuild(next);
      if (next.status === "not_built" || next.status === "stale") {
        setBusy("Building the unattended installer from your ISO (about a minute; nothing touches the server)…");
        next = await api.buildEsxiInstaller(profileId, deviceId);
        if (live.current) setBuild(next);
      }
    });
  }, []);

  // Watch: read-only checks every 30 seconds until ESXi answers on its address.
  const watching = step === 1 && status?.state === "installing";
  useEffect(() => {
    if (!watching) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function check() {
      try {
        const next = await api.checkEsxiInstall(profileId, deviceId);
        if (!active) return;
        setStatus(next);
        if (next.state === "verified" || next.state === "reachable") { setStep(2); return; }
      } catch { /* the server is restarting; the next check will answer */ }
      if (active) timer = setTimeout(() => void check(), 30000);
    }
    timer = setTimeout(() => void check(), 20000);
    const clock = setInterval(() => tick(value => value + 1), 30000);
    return () => { active = false; clearTimeout(timer); clearInterval(clock); };
  }, [watching]);

  // However the run got there (watch, typed address, installed-host check or resume), a finished
  // run moves to Finish.
  useEffect(() => {
    if (step === 1 && (status?.state === "verified" || status?.state === "reachable")) setStep(2);
  }, [step, status?.state]);
  useEffect(() => {
    if (status?.state === "verified") void lockReadOnly().catch(() => { /* Done locks it again */ });
  }, [status?.state]);

  const install = () => run("Starting the install…", async () => {
    if (!understood || build?.status !== "ready") return;
    setBusy("Allowing only the ESXi install on this server…");
    await allowOnly("esxi_install_only");
    setBusy("Attaching the installer, setting a one-time boot and starting the server…");
    const next = await api.startEsxiInstall(profileId, deviceId);
    if (!live.current) return;
    setStatus(next); setStep(1);
  });
  const finish = () => run("Locking the server…", async () => { await lockReadOnly(); if (live.current) onClose(); });

  const ready = step === 0 && build?.status === "ready";
  const blocked = step === 0 && build?.status === "blocked";
  const stuck = status?.state === "needs_attention";
  const phases = status?.phases ?? {};
  const percent = step === null ? 0 : step === 0 ? (ready ? 25 : 10) : step === 2 ? 100
    : stuck ? 40 : phases.power === "ok" ? 55 + Math.min(35, Math.round((Date.now() - Date.parse(status?.started_at ?? new Date().toISOString())) / 60000 * 2)) : 35;
  const volume = settings.boot_volume;
  const data = settings.data_volume;
  const dhcp = settings.addressing === "dhcp";
  const verification = status?.verification ?? null;
  const next = step === 0 ? (ready ? { label: "Install ESXi", run: () => void install(), disabled: !understood } : null)
    : step === 2 ? { label: "Done", run: () => void finish(), disabled: false } : null;
  const state = (phase: string): "done" | "now" | "todo" | "warn" => phases[phase] === "ok" ? "done" : ["uncertain", "failed", "sent"].includes(phases[phase] ?? "") && stuck ? "warn" : busy ? "now" : "todo";

  return <dialog ref={dialog} className="inst" aria-label={`Install ESXi on ${deviceName}`} onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    <header className="inst-h">
      <span className="inst-icon"><Rocket size={22} aria-hidden="true" /></span>
      <div><h2>Install ESXi</h2><p>{deviceName}</p></div>
      <button type="button" aria-label="Close ESXi installer" disabled={!!busy && step !== 1} onClick={onClose}><X size={20} /></button>
    </header>
    <div className="inst-body">
      <ol className="inst-steps" aria-label="Installer steps">{STEPS.map((label, index) =>
        <li key={label} className={step !== null && index < step ? "done" : index === step ? "now" : ""} aria-current={index === step ? "step" : undefined}>
          <span>{step !== null && index < step ? <Check size={13} /> : index + 1}</span>{label}</li>)}</ol>
      <section className="inst-main" aria-live="polite">
        {step === null && <p>Loading…</p>}

        {step === 0 && <>
          <h3>{ready ? "Ready to install" : blocked ? "Not ready yet" : "Checking"}</h3>
          <dl className="ei-summary">
            <div><dt>Host</dt><dd>{settings.hostname}</dd></div>
            <div><dt>Address</dt><dd>{dhcp ? "From DHCP" : settings.management_ip}{settings.vlan_id ? ` · VLAN ${settings.vlan_id}` : " · untagged"}</dd></div>
            {data && <div><dt>Datastore</dt><dd>{settings.datastore_name} on {data.name}</dd></div>}
            <div><dt>Installer</dt><dd>{build?.built ? `${build.built.iso_name} (${size(build.built.size_bytes)})` : "Being prepared"}</dd></div>
          </dl>
          {blocked && <div className="fw-stop" role="alert"><strong>Still to do</strong><ul>{build!.blockers.map(item => <li key={item}>{item}</li>)}</ul></div>}
          {ready && <>
            {volume && <div className="wipe-warn" role="note"><strong><AlertTriangle size={17} aria-hidden="true" />ESXi replaces everything on {volume.name}</strong>
              <span>RAID 1, {size(volume.capacity_bytes)}, bays {volume.bays.map(bay => bay.split(":").pop()).join(" & ")}.{data ? <> After ESXi is verified, <b>{data.name}</b> ({data.raid.replace(/^RAID/, "RAID ")}, {size(data.capacity_bytes)}) is formatted as datastore <b>{settings.datastore_name}</b>, but only if it is still empty.</> : " The datastore disks are not touched."}</span></div>}
            <p>The server restarts into the installer, installs ESXi without any questions, restarts again and comes up {dhcp ? "with an address from DHCP" : <>on {settings.management_ip}</>}. The app then signs in as root to check it. That usually takes 10-20 minutes; you can close this window and it carries on.</p>
            <label className="wipe-ok"><input type="checkbox" checked={understood} onChange={event => setUnderstood(event.target.checked)} />I understand the boot mirror is overwritten{data ? ", the VM data volume is formatted" : ""} and the server restarts.</label>
          </>}
        </>}

        {step === 1 && <>
          <h3>{stuck ? "The install needs attention" : "Installing ESXi…"}</h3>
          <ul className="ei-rows">
            <Row state={state("media")}>Installer attached to the server</Row>
            <Row state={state("boot")}>One-time boot from the installer</Row>
            <Row state={state("power")}>Server started into the installer</Row>
            <Row state={phases.power === "ok" ? (status?.state === "installing" ? "now" : "done") : "todo"}>ESXi installing and restarting{phases.power === "ok" && status?.started_at ? ` · ${elapsed(status.started_at)}` : ""}</Row>
            <Row state={status?.last_check?.answering ? "done" : "todo"}>ESXi answering on {status?.management_ip ?? (dhcp ? "its DHCP address" : settings.management_ip)}</Row>
            <Row state={verification?.passed ? "done" : verification ? "warn" : "todo"}>Signed in as root and checked the host</Row>
            <Row state={phases.eject === "ok" ? "done" : phases.eject ? "warn" : "todo"}>Installer ejected</Row>
            {data && <Row state={phases.datastore === "ok" ? "done" : phases.datastore ? "warn" : "todo"}>Datastore {settings.datastore_name} created on {data.name}</Row>}
          </ul>
          {status?.last_check && !status.last_check.answering && <p className="ex-hint">Last check: {status.last_check.detail}</p>}
          {verification && !verification.passed && <div className="fw-stop" role="alert">
            <strong>{verification.problem ? "Signing in didn't work yet" : "ESXi doesn't match the plan yet"}</strong>
            {verification.problem ? <p>{verification.problem}</p> : <ul className="ei-checks">{verification.checks.filter(check => !check.ok).map(check =>
              <li key={check.name}><b>{check.name}</b>: expected {check.expected}, found {check.found || "nothing"}</li>)}</ul>}
            <p>Nothing was ejected or formatted. The app keeps checking.</p>
          </div>}
          {dhcp && status?.state === "installing" && !status.management_ip && <form className="ei-address" onSubmit={event => { event.preventDefault(); void run("Checking that address…", async () => { const next = await api.checkEsxiInstall(profileId, deviceId, typedAddress.trim()); if (live.current) { setStatus(next); if (next.state === "verified" || next.state === "reachable") setStep(2); } }); }}>
            <label>Address shown on the server's screen<input aria-label="ESXi address from the server screen" value={typedAddress} onChange={event => setTypedAddress(event.target.value)} placeholder="e.g. 192.0.2.77" inputMode="decimal" /></label>
            <button type="submit" className="secondary-action" disabled={!!busy || !/^\d{1,3}(\.\d{1,3}){3}$/.test(typedAddress.trim())}>Use this address</button>
          </form>}
          {status?.late && <p className="fw-stop" role="alert">{status.message} The app is still watching.</p>}
          {stuck && <>
            <p className="fw-stop" role="alert">{status?.message}</p>
            {status?.can_check_installed && <form className="ei-adopt" aria-label="Check an installed host" onSubmit={event => { event.preventDefault(); void run("Signing in to ESXi…", async () => { const next = await api.checkEsxiInstall(profileId, deviceId, dhcp ? typedAddress.trim() || undefined : undefined); if (live.current) { setStatus(next); if (next.state === "verified" || next.state === "reachable") setStep(2); } }); }}>
              <strong>Did ESXi install anyway?</strong>
              <p>With an empty boot mirror the server can start the attached installer by itself. If its screen shows ESXi running, the app can sign in as root and check it. The installer is ejected and {data ? <>the datastore created</> : "the run finished"} only if everything matches.</p>
              {dhcp && <label>Address shown on the server's screen<input aria-label="ESXi address from the server screen" value={typedAddress} onChange={event => setTypedAddress(event.target.value)} placeholder="Leave empty to ask the iLO" inputMode="decimal" /></label>}
              <button type="submit" className="primary-action" disabled={!!busy || (dhcp && !!typedAddress.trim() && !/^\d{1,3}(\.\d{1,3}){3}$/.test(typedAddress.trim()))}>Check the installed host</button>
            </form>}
            <div className="ex-actions">
              <button type="button" className={status?.can_check_installed ? "secondary-action" : "primary-action"} disabled={!!busy} onClick={() => void run("Reading the server back…", async () => { const next = await api.resumeEsxiInstall(profileId, deviceId); if (live.current) setStatus(next); })}>{status?.can_check_installed ? "Retry the boot and restart" : "Check the server again"}</button>
              <button type="button" className="secondary-action" disabled={!!busy} onClick={() => void run("Closing this run…", async () => { const next = await api.closeEsxiInstall(profileId, deviceId); if (live.current) { setStatus(next); setStep(0); } })}>Close this run</button>
            </div>
          </>}
        </>}

        {step === 2 && <>
          <h3>{status?.state === "reachable" ? "ESXi answers; verification pending" : "Complete"}</h3>
          {status?.state === "reachable" ? <p className="ex-hint">{status.message}</p> : <>
            <p className="inst-ok"><Check size={16} />ESXi is installed and verified at {status?.management_ip ?? settings.management_ip}.</p>
            {!!verification?.checks.length && <ul className="ei-rows">{verification.checks.map(check => <Row key={check.name} state={check.ok ? "done" : "warn"}>{check.name}: {check.found}</Row>)}</ul>}
            {status?.datastore ? <p className="inst-ok"><Check size={16} />Datastore {status.datastore.name} is ready for your VMs.</p>
              : data ? <p className="ex-hint">The VM datastore was not created; it can be added later.</p> : null}
          </>}
          {status?.ejected === false && <p className="fw-stop">The installer is still attached in the iLO. Eject it there before the next restart.</p>}
          <p><a href={`https://${status?.management_ip ?? settings.management_ip}/ui/`} target="_blank" rel="noreferrer"><ExternalLink size={14} /> Open the ESXi host client</a> and sign in as root with the password you set.</p>
        </>}

        {busy && <p className="inst-busy" role="status">{busy}</p>}
        {error && <p className="fw-stop" role="alert">{error}</p>}
      </section>
    </div>
    <div className="inst-progress" aria-label="Progress">
      <div className={`inst-bar ${step === 2 && status?.state === "verified" ? "done" : stuck || status?.state === "reachable" ? "warn" : ""} ${watching || !!busy ? "moving" : ""}`} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}><span style={{ width: `${percent}%` }} /></div>
      <small>Step {step === null ? 1 : step + 1} of {STEPS.length} · {step === null ? "" : STEPS[step]}</small>
    </div>
    <footer className="inst-f">
      <button type="button" className="secondary-action" disabled={!!busy && step !== 1} onClick={onClose}>{watching ? "Close (keeps going)" : "Cancel"}</button>
      <span className="inst-grow" />
      {next && <button type="button" className="primary-action inst-next" disabled={!!busy || next.disabled} onClick={next.run}>{next.label}</button>}
    </footer>
  </dialog>;
}
