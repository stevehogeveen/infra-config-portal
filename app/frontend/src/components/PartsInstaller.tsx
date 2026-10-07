import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, Cpu, Disc3, Loader2, X } from "lucide-react";
import { partsUpdateApi, sppUpdateApi, type PartsUpdatePlan, type PartsUpdateStatus, type SppUpdatePlan, type SppUpdateStatus } from "../api";
import { allowOnly, lockReadOnly } from "./storageInstall";

/*
 * One button for all firmware: Check -> Update -> Finish.
 * 1. Through the iLO, part by part: the System ROM first and read back, then the other parts the
 *    iLO or the BIOS can install. Each send happens once and is never repeated.
 * 2. Then HPE's SPP is asked what is still out of date. Anything left (typically drive firmware)
 *    can only be installed by booting the SPP disc, so the same window carries on with that.
 * Nothing is sent before the one tick and button. Done returns the server to read-only.
 */

const STEPS = ["Check", "Update", "Finish"] as const;
type Step = 0 | 1 | 2;
type Stage = "parts" | "checking" | "disc";
const HOW = { ilo: "The iLO installs it", bios: "The BIOS installs it at the next start" } as const;
const DISC_RUNNING = new Set(["running", "waiting_restart", "verifying"]);

function Row({ state, children }: { state: "done" | "now" | "todo" | "warn"; children: React.ReactNode }) {
  return <li className={`ei-row ei-${state}`}>
    <span aria-hidden="true">{state === "done" ? <Check size={14} /> : state === "now" ? <Loader2 size={14} className="dr-spin" /> : state === "warn" ? <AlertTriangle size={14} /> : null}</span>
    {children}
  </li>;
}

export function PartsInstaller({ profileId, deviceId, deviceName, onClose }: { profileId: string; deviceId: string; deviceName: string; onClose: (changed: boolean) => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const live = useRef(true);
  const [step, setStep] = useState<Step | null>(null);
  const [stage, setStage] = useState<Stage>("parts");
  const [plan, setPlan] = useState<PartsUpdatePlan | null>(null);
  const [discPlan, setDiscPlan] = useState<SppUpdatePlan | null>(null);
  const [status, setStatus] = useState<PartsUpdateStatus | null>(null);
  const [disc, setDisc] = useState<SppUpdateStatus | null>(null);
  const [discNote, setDiscNote] = useState("");
  const [understood, setUnderstood] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { live.current = true; if (!dialog.current?.open) dialog.current?.showModal(); return () => { live.current = false; }; }, []);

  async function run(label: string, work: () => Promise<void>) {
    setBusy(label); setError("");
    try { await work(); } catch (err) { if (live.current) setError(err instanceof Error ? err.message : String(err)); }
    finally { if (live.current) setBusy(""); }
  }
  // What HPE's boot disc would still install. A refusal here only means there is nothing to add.
  async function readDiscPlan() {
    try {
      const next = await sppUpdateApi.plan(profileId, deviceId);
      if (live.current) { setDiscPlan(next); setDiscNote(next.blockers?.[0] ?? ""); }
      return next;
    } catch (err) {
      if (live.current) { setDiscPlan(null); setDiscNote(err instanceof Error ? err.message : String(err)); }
      return null;
    }
  }
  const review = () => run("Reading the server and the SPP…", async () => {
    const next = await partsUpdateApi.review(profileId, deviceId);
    if (!live.current) return;
    setPlan(next); setUnderstood(false);
    if (!next.parts.length) await readDiscPlan();
  });
  const opened = useRef(false);
  useEffect(() => {
    if (opened.current) return;
    opened.current = true;
    void run("Reading the recorded status…", async () => {
      const [parts, spp] = await Promise.all([partsUpdateApi.status(profileId, deviceId), sppUpdateApi.status(profileId, deviceId).catch(() => null)]);
      if (!live.current) return;
      setStatus(parts);
      if (spp?.active) { setDisc(spp); setStage("disc"); setStep(1); return; }
      if (parts.active) { setStage("parts"); setStep(1); return; }
      setStep(0);
      const next = await partsUpdateApi.review(profileId, deviceId);
      if (!live.current) return;
      setPlan(next);
      if (!next.parts.length) await readDiscPlan();
    });
  }, []);

  const discUpdates = (p: SppUpdatePlan | null) => !!p && p.can_apply && !!p.review_token && !!p.confirmation_phrase && p.updates.length > 0;
  async function startDisc(p: SppUpdatePlan) {
    setStage("disc");
    const next = await sppUpdateApi.apply(profileId, deviceId, { review_token: p.review_token!, confirmation_phrase: p.confirmation_phrase!, idempotency_key: crypto.randomUUID() });
    if (live.current) { setDisc(next); setStep(1); }
  }

  // Stage 1: move the iLO run along, one bounded step per request, never overlapping.
  const partsRunning = step === 1 && stage === "parts" && !!status?.active && status.state === "running";
  useEffect(() => {
    if (!partsRunning) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function tick() {
      try {
        const next = await partsUpdateApi.advance(profileId, deviceId);
        if (!active) return;
        setStatus(next);
        if (!next.active) return;
      } catch { /* the iLO or server is restarting; try again shortly */ }
      if (active) timer = setTimeout(() => void tick(), 10000);
    }
    timer = setTimeout(() => void tick(), 1000);
    return () => { active = false; clearTimeout(timer); };
  }, [partsRunning]);

  // After stage 1: ask the SPP what is left; carry on with the boot disc only if something is.
  useEffect(() => {
    if (!(step === 1 && stage === "parts" && status && !status.active && status.state === "verified")) return;
    setStage("checking");
    void run("Checking for anything only HPE's boot disc can install…", async () => {
      const next = await readDiscPlan();
      if (!live.current) return;
      if (discUpdates(next)) await startDisc(next!);
      else setStep(2);
    });
  }, [step, stage, status?.state, status?.active]);

  // Stage 2: the boot-disc run is driven by the server; this window only reads its status.
  const discRunning = step === 1 && stage === "disc" && !!disc?.active;
  useEffect(() => {
    if (!discRunning) return;
    let active = true;
    const timer = setInterval(async () => {
      try {
        const next = await sppUpdateApi.status(profileId, deviceId);
        if (!active) return;
        setDisc(next);
        if (!next.active && next.status === "verified") setStep(2);
      } catch { /* server restarting */ }
    }, 15000);
    return () => { active = false; clearInterval(timer); };
  }, [discRunning]);

  const start = () => run("Allowing only firmware updates on this server…", async () => {
    if (!plan || !understood) return;
    await allowOnly("firmware_only");
    if (plan.parts.length) {
      setBusy("Starting with " + plan.parts[0].component + "…");
      const next = await partsUpdateApi.start(profileId, deviceId, plan.review_id);
      if (live.current) { setStatus(next); setStage("parts"); setStep(1); }
    } else if (discPlan && discUpdates(discPlan)) {
      setBusy("Starting HPE's boot disc…");
      await startDisc(discPlan);
    }
  });
  const closeRun = () => run("Closing this run…", async () => {
    await partsUpdateApi.close(profileId, deviceId);
    await lockReadOnly();
    if (live.current) { setStatus(null); setStage("parts"); setStep(0); await review(); }
  });
  const finish = () => run("Locking the server…", async () => { await lockReadOnly(); if (live.current) onClose(true); });

  const discOnly = !!plan && !plan.parts.length && discUpdates(discPlan);
  const ready = step === 0 && !!plan && !plan.blockers.length && (plan.parts.length > 0 || discOnly);
  const stuck = stage === "parts" ? status?.state === "needs_attention" : stage === "disc" && !!disc && !disc.active && disc.status !== "verified" || disc?.status === "uncertain";
  const phases = status?.phases ?? [];
  const doneCount = phases.filter(p => p.state === "ok").length;
  const discSteps = disc?.steps ?? [];
  const percent = step === null ? 0 : step === 0 ? (ready ? 20 : 8) : step === 2 ? 100
    : stage === "disc" ? Math.round(70 + 25 * discSteps.filter(s => s.state === "done").length / Math.max(1, discSteps.length))
    : Math.round(20 + (discOnly ? 0 : 55) * doneCount / Math.max(1, phases.length));
  const next = step === 0 ? (ready ? { label: "Update firmware", run: () => void start(), disabled: !understood } : null)
    : step === 2 ? { label: "Done", run: () => void finish(), disabled: false } : null;
  const phaseState = (state: string, index: number): "done" | "now" | "todo" | "warn" =>
    state === "ok" ? "done" : state === "failed" || state === "uncertain" ? "warn" : state === "sent" || (partsRunning && index === doneCount) ? "now" : "todo";
  const discState = (state: string): "done" | "now" | "todo" | "warn" =>
    state === "done" ? "done" : state === "failed" || state === "uncertain" ? "warn" : ["installing", "restarting", "verifying"].includes(state) || (DISC_RUNNING.has(disc?.status ?? "") && state === "waiting") ? "now" : "todo";
  const restarts = plan ? plan.restarts : 0;

  return <dialog ref={dialog} className="inst" aria-label={`Update firmware part by part on ${deviceName}`} onCancel={event => { event.preventDefault(); if (!busy) onClose(false); }}>
    <header className="inst-h">
      <span className="inst-icon"><Cpu size={22} aria-hidden="true" /></span>
      <div><h2>Update firmware</h2><p>{deviceName}</p></div>
      <button type="button" aria-label="Close firmware installer" disabled={!!busy && step !== 1} onClick={() => onClose(false)}><X size={20} /></button>
    </header>
    <div className="inst-body">
      <ol className="inst-steps" aria-label="Installer steps">{STEPS.map((label, index) =>
        <li key={label} className={step !== null && index < step ? "done" : index === step ? "now" : ""} aria-current={index === step ? "step" : undefined}>
          <span>{step !== null && index < step ? <Check size={13} /> : index + 1}</span>{label}</li>)}</ol>
      <section className="inst-main" aria-live="polite">
        {step === null && <p>Loading…</p>}

        {step === 0 && plan && <>
          <h3>{ready ? "Ready to update" : plan.parts.length ? "Not ready yet" : "Everything is up to date"}</h3>
          {plan.parts.length > 0 && <ol className="pu-parts" aria-label="Parts to update, in order">{plan.parts.map(part =>
            <li key={part.id}><b>{part.component}</b><span className="fw-path">{part.from}<i aria-hidden="true">→</i>{part.to}</span><small>{HOW[part.method]}{part.rom ? " · first, then read back" : ""}</small></li>)}</ol>}
          {discOnly && <ol className="pu-parts" aria-label="Parts HPE's boot disc updates">{discPlan!.updates.map(item =>
            <li key={item.step_id}><b>{item.component}</b><span className="fw-path">{item.from}<i aria-hidden="true">→</i>{item.to}</span><small><Disc3 size={12} aria-hidden="true" /> HPE's boot disc installs it</small></li>)}</ol>}
          {!!plan.elsewhere.length && <details className="fw-details"><summary>Not installed through the iLO ({plan.elsewhere.length})</summary>
            <ul className="sd-fine">{plan.elsewhere.map(item => <li key={item.component}><b>{item.component}</b> {item.from} → {item.to}: {item.reason}</li>)}</ul></details>}
          {!plan.parts.length && !discOnly && <p className="ex-hint">Every part already matches {plan.package}.{discNote ? ` (${discNote})` : ""}</p>}
          {!!plan.blockers.length && <div className="fw-stop" role="alert"><strong>Still to do</strong><ul>{plan.blockers.map(item => <li key={item}>{item}</li>)}</ul></div>}
          {ready && <>
            <div className="wipe-warn" role="note"><strong><AlertTriangle size={17} aria-hidden="true" />{discOnly ? "The server restarts into HPE's boot disc" : `The server restarts ${restarts === 1 ? "once" : `${restarts} times`}`}</strong>
              <span>Anything running on it (ESXi and its VMs) stops without shutting down. {plan.parts.length ? `About ${plan.minutes} minutes. If anything is still out of date afterwards (for example drive firmware), the app carries on with HPE's boot disc, which adds restarts and time. ` : ""}Keep the server's power connected and this window open; if you close it, the update pauses safely and carries on when you open it again.</span></div>
            <label className="wipe-ok"><input type="checkbox" checked={understood} onChange={event => setUnderstood(event.target.checked)} />I understand the server restarts and its firmware is updated.</label>
          </>}
        </>}

        {step === 1 && stage !== "disc" && status && <>
          <h3>{stuck ? "The update needs attention" : "Updating firmware…"}</h3>
          <ul className="ei-rows" aria-label="Update steps">{phases.map(phase =>
            <Row key={phase.index} state={phaseState(phase.state, phase.index)}>{phase.label}</Row>)}
            <Row state={stage === "checking" ? "now" : "todo"}>Check for anything only HPE's boot disc can install</Row></ul>
          {stuck ? <>
            <p className="fw-stop" role="alert">{status.message}</p>
            <p className="ex-hint">Nothing was sent again. Parts already read back stay installed. Close this run to review the update again.</p>
            <div className="ex-actions"><button type="button" className="secondary-action" disabled={!!busy} onClick={() => void closeRun()}>Close this run</button></div>
          </> : <p className="ex-hint">{status.message}</p>}
        </>}

        {step === 1 && stage === "disc" && disc && <>
          <h3>{stuck ? "The boot-disc update needs attention" : "HPE's boot disc is updating the rest…"}</h3>
          {disc.observed && <div className={disc.observed.waiting_for_reboot ? "fw-stop spp-observed" : "spp-observed"} role="status" aria-label="What the server shows now"><p>{disc.observed.summary}</p></div>}
          <ul className="ei-rows" aria-label="Boot-disc steps">{discSteps.map(item => <Row key={item.step_id} state={discState(item.state)}>{item.component}: {item.from} → {item.to}</Row>)}</ul>
          {stuck ? <p className="fw-stop" role="alert">{disc.message}{disc.next_action ? ` ${disc.next_action}` : ""}</p> : <p className="ex-hint">{disc.message}</p>}
        </>}

        {step === 2 && <>
          <h3>Complete</h3>
          <p className="inst-ok"><Check size={16} />Every part was read back at its new version.</p>
          <ul className="ei-rows">
            {(status?.parts ?? []).map(part => <Row key={part.id} state={part.state === "done" ? "done" : "warn"}>{part.component}: {part.to}</Row>)}
            {discSteps.map(item => <Row key={item.step_id} state={item.state === "done" ? "done" : "warn"}>{item.component}: {item.verified_version ?? item.to}</Row>)}
          </ul>
          {!discSteps.length && <p className="ex-hint">Nothing needed HPE's boot disc.</p>}
        </>}

        {busy && <p className="inst-busy" role="status">{busy}</p>}
        {error && <p className="fw-stop" role="alert">{error}</p>}
      </section>
    </div>
    <div className="inst-progress" aria-label="Progress">
      <div className={`inst-bar ${step === 2 ? "done" : stuck ? "warn" : ""} ${partsRunning || discRunning || !!busy ? "moving" : ""}`} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}><span style={{ width: `${percent}%` }} /></div>
      <small>Step {step === null ? 1 : step + 1} of {STEPS.length} · {step === null ? "" : STEPS[step]}</small>
    </div>
    <footer className="inst-f">
      <button type="button" className="secondary-action" disabled={!!busy && step !== 1} onClick={() => onClose(false)}>{discRunning ? "Close (keeps going)" : partsRunning ? "Close (pauses safely)" : "Cancel"}</button>
      <span className="inst-grow" />
      {next && <button type="button" className="primary-action inst-next" disabled={!!busy || next.disabled} onClick={next.run}>{next.label}</button>}
    </footer>
  </dialog>;
}
