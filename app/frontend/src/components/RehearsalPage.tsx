import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, Loader2, Play, RotateCcw, Shuffle, Wrench } from "lucide-react";

/*
 * Rehearsal rack: practise the whole build on simulated equipment. Everything runs in this browser
 * tab; the page makes no requests to the app's API, so nothing can reach real hardware.
 * Steps follow the app's order (the switch is set up with Connect, before the server is changed).
 * Each step plays its phases like the real installers. With surprises on, some steps stop with the
 * same kind of problem the real app reports, and the operator picks the fix to carry on.
 */

type Problem = { at: number; says: string; fixes: Array<{ label: string; right: boolean; why: string }> };
type Stage = { id: string; title: string; device: "server" | "switch" | "vm"; phases: string[]; problem: Problem };

export const STAGES: Stage[] = [
  { id: "connect", title: "Connect the server", device: "server", phases: ["Reach the iLO at 192.0.2.10", "Sign in with the tag's user", "Read the server's parts"],
    problem: { at: 0, says: "Nothing answered at 192.0.2.10.", fixes: [
      { label: "Check the cable is in the iLO port, then read again", right: true, why: "The iLO has its own port; a cable in a normal network port never reaches it." },
      { label: "Restart the server", right: false, why: "Nothing changes on the server until the app can reach it. Check the cable first." }] } },
  { id: "switch", title: "Set up the switch", device: "switch", phases: ["Read the switch on COM5", "Send the reviewed setup", "Wait for a DHCP address", "SSH answers at the new address"],
    problem: { at: 2, says: "Vlan1 has no address from DHCP after 3 minutes.", fixes: [
      { label: "Put the uplink port in the VLAN that has DHCP", right: true, why: "The switch only gets an address if its uplink reaches a DHCP server." },
      { label: "Run the setup again", right: false, why: "The settings were sent and saved; sending them again changes nothing. Fix the uplink." }] } },
  { id: "firmware", title: "Update firmware", device: "server", phases: ["Read versions", "Compare with the package", "Send the iLO update", "iLO restarts", "Read back the new version"],
    problem: { at: 3, says: "The iLO did not come back in time. The update outcome is not known.", fixes: [
      { label: "Read the iLO again (do not send the update again)", right: true, why: "A lost reply is decided by reading. Sending twice is how firmware gets interrupted." },
      { label: "Send the update again", right: false, why: "Never resend a firmware update whose outcome is unknown. Read first." }] } },
  { id: "raid", title: "Build RAID", device: "server", phases: ["Turn the server off", "Stage the layout on the controller", "Restart so it applies", "Read back the volumes"],
    problem: { at: 3, says: "Bay 3 reports a predictive failure. The data volume is degraded.", fixes: [
      { label: "Swap the disk in bay 3, then read again", right: true, why: "A failing disk under a new array is a rebuild waiting to happen." },
      { label: "Carry on to ESXi", right: false, why: "The app stops here on purpose: never install onto a degraded array." }] } },
  { id: "esxi", title: "Install ESXi", device: "server", phases: ["Attach the installer", "Boot once from it", "Install (about 15 minutes)", "ESXi answers at 192.0.2.20", "Create the VM datastore"],
    problem: { at: 3, says: "ESXi has not answered at 192.0.2.20 after 30 minutes.", fixes: [
      { label: "Open the iLO remote console and look at the installer screen", right: true, why: "The installer shows what it is waiting for (often a disk or network question)." },
      { label: "Start the install again", right: false, why: "A second install can wipe the first half-done one. Look before you resend." }] } },
  { id: "windows", title: "Deploy Windows", device: "vm", phases: ["Import the image onto VMdata", "Power the VM on", "VMware Tools reports the address"],
    problem: { at: 0, says: "The import stopped: datastore1 is full.", fixes: [
      { label: "Choose VMdata (the big datastore) and deploy again", right: true, why: "datastore1 is the small one on the boot disks; VMs belong on VMdata." },
      { label: "Delete files from datastore1", right: false, why: "datastore1 is the boot pair's leftover space. Use the VM datastore." }] } },
  { id: "accept", title: "Acceptance test", device: "vm", phases: ["Answers from outside", "Works from inside", "Restarts once", "Back after the restart"],
    problem: { at: 1, says: "Windows cannot reach its gateway 192.0.2.1.", fixes: [
      { label: "Check the VM is on the right network (VM Network)", right: true, why: "A VM on the wrong port group has an address but no way out." },
      { label: "Restart Windows", right: false, why: "A restart does not move the VM to the right network." }] } },
];

type Run = { stage: number; phase: number; state: "idle" | "running" | "problem" | "stage-done" | "done"; wrong: string | null };
const fresh: Run = { stage: 0, phase: 0, state: "idle", wrong: null };

export function RehearsalPage({ tick = 700 }: { tick?: number }) {
  const [surprises, setSurprises] = useState(true);
  const [picked, setPicked] = useState<Set<string>>(() => new Set(["firmware", "raid", "switch"]));
  const [run, setRun] = useState<Run>(fresh);
  const [handled, setHandled] = useState<string[]>([]);
  const [mistakes, setMistakes] = useState(0);
  const [started, setStarted] = useState<number | null>(null);
  const [finished, setFinished] = useState<number | null>(null);
  const solved = useRef(new Set<string>());
  const stage = STAGES[run.stage];

  useEffect(() => {
    if (run.state !== "running") return;
    const timer = setTimeout(() => {
      const trouble = surprises && picked.has(stage.id) && !solved.current.has(stage.id) && run.phase === stage.problem.at;
      if (trouble) { setRun({ ...run, state: "problem", wrong: null }); return; }
      if (run.phase + 1 < stage.phases.length) { setRun({ ...run, phase: run.phase + 1 }); return; }
      if (run.stage + 1 < STAGES.length) setRun({ ...run, phase: stage.phases.length, state: "stage-done" });
      else { setRun({ ...run, phase: stage.phases.length, state: "done" }); setFinished(Date.now()); }
    }, tick);
    return () => clearTimeout(timer);
  }, [run, surprises, picked, stage, tick]);

  const begin = () => { if (started === null) setStarted(Date.now()); setRun({ ...run, state: "running" }); };
  const next = () => setRun({ stage: run.stage + 1, phase: 0, state: "running", wrong: null });
  const restart = () => { solved.current = new Set(); setRun(fresh); setHandled([]); setMistakes(0); setStarted(null); setFinished(null); };
  const choose = (fix: Problem["fixes"][number]) => {
    if (!fix.right) { setMistakes(value => value + 1); setRun({ ...run, wrong: fix.why }); return; }
    solved.current.add(stage.id);
    setHandled(list => [...list, stage.title]);
    setRun({ ...run, state: "running", wrong: null });
  };
  const doneCount = run.state === "done" ? STAGES.length : run.stage + (run.state === "stage-done" ? 1 : 0);
  const light = (device: Stage["device"]) => {
    const own = STAGES.map((item, index) => ({ item, index })).filter(({ item }) => item.device === device);
    if (own.some(({ index }) => index === run.stage && run.state === "problem")) return "bad";
    if (own.every(({ index }) => index < doneCount)) return "ok";
    if (own.some(({ index }) => index === run.stage && run.state === "running")) return "busy";
    return own.some(({ index }) => index < doneCount) ? "part" : "idle";
  };
  const minutes = started && finished ? Math.max(1, Math.round((finished - started) / 1000)) : null;

  return <section className="ex-page rh-page" aria-label="Rehearsal rack">
    <header className="journey-heading"><h1>Rehearsal rack</h1><p>Practise the whole build on pretend equipment. Nothing here reaches real hardware.</p></header>
    <div className="rh-grid">
      <aside className="rh-rack" aria-label="Pretend rack">
        {(["server", "vm", "switch"] as const).map(device => <div key={device} className={`rh-unit rh-${light(device)}`} data-testid={`rh-${device}`}>
          <span className="rh-dot" aria-hidden="true" />{device === "server" ? "HPE DL360 (practice)" : device === "vm" ? "Windows VM (practice)" : "Cisco switch (practice)"}</div>)}
        <div className="rh-opts">
          <label className="wipe-ok"><input type="checkbox" checked={surprises} disabled={run.state !== "idle"} onChange={e => setSurprises(e.target.checked)} />With surprises</label>
          {surprises && <fieldset className="rh-pick" disabled={run.state !== "idle"}><legend>Problems to practise</legend>
            {STAGES.map(item => <label key={item.id}><input type="checkbox" checked={picked.has(item.id)} onChange={e => setPicked(current => { const copy = new Set(current); if (e.target.checked) copy.add(item.id); else copy.delete(item.id); return copy; })} />{item.title}</label>)}
            <button type="button" className="link-button" onClick={() => setPicked(new Set(STAGES.filter(() => Math.random() < 0.5).map(item => item.id)))}><Shuffle size={13} aria-hidden="true" /> Surprise me</button>
          </fieldset>}
        </div>
      </aside>
      <div className="rh-main">
        <ol className="rh-steps" aria-label="Build steps">{STAGES.map((item, index) => <li key={item.id} className={index < doneCount ? "done" : index === run.stage ? "now" : ""} aria-current={index === run.stage ? "step" : undefined}>
          <span>{index < doneCount ? <Check size={13} /> : index + 1}</span>{item.title}</li>)}</ol>
        {run.state === "done" ? <div className="rh-card rh-finish" role="status">
          <h2><Check size={20} aria-hidden="true" /> Kit built (practice)</h2>
          <p>{STAGES.length} steps{minutes ? ` in ${minutes} seconds` : ""}. Problems handled: {handled.length ? handled.join(", ") : "none"}.{mistakes ? ` Wrong first tries: ${mistakes}.` : ""}</p>
          <button type="button" className="primary-action" onClick={restart}><RotateCcw size={16} aria-hidden="true" />Practise again</button>
        </div> : <div className="rh-card">
          <h2>{stage.title}</h2>
          <ul className="ei-rows" aria-label={`${stage.title} phases`}>{stage.phases.map((phase, index) => {
            const state = index < run.phase || run.state === "stage-done" ? "done" : index === run.phase && run.state === "problem" ? "warn" : index === run.phase && run.state === "running" ? "now" : "todo";
            return <li key={phase} className={`ei-row ei-${state}`}><span aria-hidden="true">{state === "done" ? <Check size={14} /> : state === "now" ? <Loader2 size={14} className="dr-spin" /> : state === "warn" ? <AlertTriangle size={14} /> : null}</span>{phase}</li>;
          })}</ul>
          {run.state === "problem" && <div className="rh-problem" role="alert">
            <p><b>{stage.problem.says}</b> What do you do?</p>
            <div className="rh-fixes">{stage.problem.fixes.map(fix => <button key={fix.label} type="button" className="secondary-action" onClick={() => choose(fix)}><Wrench size={14} aria-hidden="true" />{fix.label}</button>)}</div>
            {run.wrong && <p className="fw-stop">{run.wrong}</p>}
          </div>}
          <div className="ex-actions">
            {run.state === "idle" && <button type="button" className="primary-action" onClick={begin}><Play size={16} aria-hidden="true" />Start practice</button>}
            {run.state === "stage-done" && <button type="button" className="primary-action" onClick={next}>Next: {STAGES[run.stage + 1].title}</button>}
            {run.state !== "idle" && <button type="button" className="secondary-action" onClick={restart}><RotateCcw size={15} aria-hidden="true" />Start over</button>}
          </div>
        </div>}
      </div>
    </div>
  </section>;
}
