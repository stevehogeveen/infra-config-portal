import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, Check, CircleDashed, Loader2, Package, RotateCcw } from "lucide-react";
import { api, jobsApi, switchSetupApi, windowsApi, type EsxiSettings, type PreflightResult, type SwitchSetup, type WindowsSetup } from "../api";
import { useStudio } from "./studio/StudioContext";
import { HandoverPage } from "./HandoverPage";
import { NeedsYou, Paused, runInstall, STAGES, type Ctx, type StageResult } from "./installEngine";

/*
 * Build my kit: a Windows-installer style wizard over the whole build.
 * Welcome -> Check (read-only pre-flight) -> Settings (one page, edit links) -> Ready (the list of
 * changes and one approval) -> Installing (one progress bar, every step in order, already-done
 * steps skipped) -> Finish (one page with everything: the hand-over pack).
 * Leaving the page pauses the installer before its next change; runs already started on the
 * equipment keep going. Opening it again shows where it stopped and waits for Continue. The approval
 * is tied to a snapshot of the plan: if anything changed since, it asks again.
 */

const PAGES = ["Welcome", "Check", "Settings", "Ready", "Installing", "Finish"] as const;
type Page = 0 | 1 | 2 | 3 | 4 | 5;
type Device = { deviceId: string; name: string; model: string };
type Row = "todo" | "running" | StageResult | "stopped";
const LINKS: Record<string, [string, string]> = { connect: ["/setup/connect", "Open Connect"], switch: ["/setup/connect", "Open Set up the switch"],
  firmware: ["/setup/check-firmware", "Open Check firmware"], raid: ["/setup/disks", "Open Disks & RAID"], esxi: ["/setup/prepare-esxi", "Open Prepare ESXi"],
  windows: ["/setup/install-windows", "Open Install Windows"], accept: ["/setup/install-windows", "Open Install Windows"] };

type Memory = { approved: boolean; finished: boolean; plan?: string };
const memory = (profileId: string) => `kit-installer-v2:${profileId}`;
function remembered(profileId: string): Memory {
  try { return JSON.parse(localStorage.getItem(memory(profileId)) || "") as Memory; } catch { return { approved: false, finished: false }; }
}
function remember(profileId: string, value: Memory) {
  try { localStorage.setItem(memory(profileId), JSON.stringify(value)); } catch { /* only a convenience */ }
}
// Items that change from minute to minute are not part of what was approved.
const VOLATILE = /^(Connection check|Nothing half-done|Free disk space)$/;
/** A snapshot of the plan the operator approved: rack layout revision and every pre-flight setting. */
async function planSnapshot(profileId: string) {
  const [plan, check] = await Promise.all([api.rackPlan(profileId), jobsApi.preflight(profileId)]);
  return JSON.stringify([plan.revision, check.items.filter(item => !VOLATILE.test(item.name)).map(item => [item.name, item.detail])]);
}

function Settings({ profileId, servers, switches }: { profileId: string; servers: Device[]; switches: Device[] }) {
  const [esxi, setEsxi] = useState<Record<string, EsxiSettings | null>>({});
  const [win, setWin] = useState<Record<string, WindowsSetup | null>>({});
  const [sw, setSw] = useState<Record<string, SwitchSetup | null>>({});
  useEffect(() => {
    servers.forEach(s => {
      api.esxiSettings(profileId, s.deviceId).then(v => setEsxi(o => ({ ...o, [s.deviceId]: v }))).catch(() => setEsxi(o => ({ ...o, [s.deviceId]: null })));
      // A deployed VM is shown from the app's records; only an undeployed one needs its saved setup.
      windowsApi.status(profileId, s.deviceId).then(st => st.vm_name ? { vm_name: st.vm_name, image: st.image ?? null, datastore: st.datastore ?? null, network: st.network ?? null } as WindowsSetup
        : windowsApi.setup(profileId, s.deviceId)).then(v => setWin(o => ({ ...o, [s.deviceId]: v }))).catch(() => setWin(o => ({ ...o, [s.deviceId]: null })));
    });
    switches.forEach(s => switchSetupApi.setup(profileId, s.deviceId).then(v => setSw(o => ({ ...o, [s.deviceId]: v }))).catch(() => setSw(o => ({ ...o, [s.deviceId]: null }))));
  }, [profileId]);
  const first = servers[0] && esxi[servers[0].deviceId];
  const dash = (v?: string | number | null) => v === null || v === undefined || v === "" ? "—" : String(v);
  return <div className="ki-settings">
    <section><h3>Network <Link to="/setup/defaults">Edit</Link></h3>
      <dl className="ei-summary"><div><dt>Subnet</dt><dd>{dash(first?.kit.subnet)}</dd></div><div><dt>Gateway</dt><dd>{dash(first?.kit.gateway)}</dd></div>
        <div><dt>DNS</dt><dd>{first?.kit.dns.join(", ") || "—"}</dd></div><div><dt>Domain</dt><dd>{dash(first?.kit.domain_name)}</dd></div></dl></section>
    {switches.map(s => { const v = sw[s.deviceId]?.settings; return <section key={s.deviceId}><h3>{s.name} <Link to="/setup/connect">Edit</Link></h3>
      <dl className="ei-summary"><div><dt>Name</dt><dd>{dash(v?.hostname)}</dd></div><div><dt>Management</dt><dd>VLAN {dash(v?.vlan)} · {v?.mode === "static" ? `${dash(v?.address)}/${dash(v?.prefix)}` : v ? "DHCP" : "—"}</dd></div>
        <div><dt>Console</dt><dd>{dash(sw[s.deviceId]?.console.port)}</dd></div><div><dt>Admin user</dt><dd>{dash(sw[s.deviceId]?.username)}</dd></div></dl></section>; })}
    {servers.map(s => { const e = esxi[s.deviceId]; const w = win[s.deviceId]; return <section key={s.deviceId}><h3>{s.name}</h3>
      <dl className="ei-summary">
        <div><dt>ESXi <Link to="/setup/prepare-esxi">Edit</Link></dt><dd>{dash(e?.hostname)} · {e?.addressing === "dhcp" ? "DHCP" : dash(e?.management_ip)} · datastore {dash(e?.datastore_name)}</dd></div>
        <div><dt>Disks <Link to="/setup/disks">Edit</Link></dt><dd>{e?.boot_volume ? `Boot pair: bays ${e.boot_volume.bays.join(", ")}` : "—"}{e?.data_volume ? ` · VM storage: ${e.data_volume.raid}, bays ${e.data_volume.bays.join(", ")}` : ""}</dd></div>
        <div><dt>Windows <Link to="/setup/install-windows">Edit</Link></dt><dd>{w?.vm_name ? `${w.vm_name} · ${dash(w.image)} · ${dash(w.datastore)} · ${dash(w.network)}` : "—"}</dd></div>
      </dl></section>; })}
  </div>;
}

export function KitInstaller({ profileId: given, sleep: sleepOverride }: { profileId?: string; sleep?: (ms: number) => Promise<void> } = {}) {
  const studio = useStudio();
  const profileId = given ?? studio?.profileId;
  const [page, setPage] = useState<Page>(0);
  const [servers, setServers] = useState<Device[]>([]);
  const [switches, setSwitches] = useState<Device[]>([]);
  const [kitName, setKitName] = useState("");
  const [preflight, setPreflight] = useState<PreflightResult | null>(null);
  const [checking, setChecking] = useState(false);
  const [understood, setUnderstood] = useState(false);
  const [rows, setRows] = useState<Row[]>(STAGES.map(() => "todo"));
  const [now, setNow] = useState("");
  const [stopped, setStopped] = useState<{ index: number; message: string; where: string; label: string } | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const [notice, setNotice] = useState("");
  const [pausing, setPausing] = useState(false);
  const reviewed = useRef<string | null>(null);  // the plan as shown on Ready
  const abort = useRef<AbortController | null>(null);
  const busy = useRef(false);  // one install at a time, decided synchronously

  useEffect(() => {
    if (!profileId) return;
    let current = true;
    api.rackPlan(profileId).then(plan => {
      if (!current) return;
      const pick = (kind: string) => plan.equipment.filter(item => item.kind === kind && item.device_id).map(item => ({ deviceId: item.device_id!, name: item.name, model: item.model }));
      setServers(pick("server")); setSwitches(pick("switch"));
      const memo = remembered(profileId);
      if (memo.finished) setPage(5);
      else if (memo.approved) setPage(4);  // shows where it stopped; nothing starts until Continue
    }).catch(err => { if (current) setError(err instanceof Error ? err.message : String(err)); });
    setKitName(studio?.profileName ?? "");
    return () => { current = false; abort.current?.abort(); };
  }, [profileId]);

  async function check() {
    if (!profileId) return;
    setChecking(true); setError("");
    try { setPreflight(await jobsApi.preflight(profileId)); } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setChecking(false); }
  }
  useEffect(() => { if (page === 1 && !preflight) void check(); }, [page]);

  async function install(from: number) {
    if (!profileId || busy.current) return;
    busy.current = true;
    const controller = new AbortController();
    abort.current?.abort(); abort.current = controller;
    const stopIf = () => { if (controller.signal.aborted) throw new Paused(); };
    const sleep = async (ms: number) => {
      stopIf();
      if (sleepOverride) await sleepOverride(ms);
      else await new Promise<void>((resolve, reject) => {
        const timer = setTimeout(resolve, ms);
        controller.signal.addEventListener("abort", () => { clearTimeout(timer); reject(new Paused()); }, { once: true });
      });
      stopIf();
    };
    const ctx: Ctx = { profileId, servers, switches, say: text => { if (!controller.signal.aborted) setNow(text); }, warn: text => setWarning(text), stopIf, sleep };
    setRunning(true); setStopped(null); setError(""); setWarning("");
    // The approval covers the plan as it was approved; anything changed since needs a new approval.
    try {
      const memo = remembered(profileId);
      if (!memo.approved || memo.plan !== await planSnapshot(profileId)) {
        remember(profileId, { approved: false, finished: false });
        setUnderstood(false); setPreflight(null);
        setNotice("Something in the plan changed since you approved it. Check it and approve again.");
        setPage(1);
        busy.current = false; setRunning(false);
        return;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      busy.current = false; setRunning(false);
      return;
    }
    let current = from;
    setRows(old => old.map((row, i) => i < from ? row : "todo"));
    try {
      await runInstall(ctx, from, (index, state) => { current = index; setRows(old => old.map((row, i) => i === index ? state : row)); });
      if (controller.signal.aborted) return;
      remember(profileId, { approved: false, finished: true });
      setPage(5);
    } catch (err) {
      if (controller.signal.aborted || err instanceof Paused) return;
      const [where, label] = err instanceof NeedsYou ? [err.where, err.whereLabel] : LINKS[STAGES[current].id];
      setRows(old => old.map((row, i) => i === current ? "stopped" : row));
      setStopped({ index: current, message: err instanceof Error ? err.message : String(err), where, label });
    } finally {
      // The lock is released only once this run (and its permission clean-up) has really ended.
      busy.current = false;
      setRunning(false); setPausing(false);
    }
  }
  async function approve() {
    if (!profileId) return;
    try {
      const plan = await planSnapshot(profileId);
      if (plan !== reviewed.current) {  // something changed while Ready was open: show it again
        setUnderstood(false); setPreflight(null);
        setNotice("Something in the plan changed while you were reviewing it. Check it and approve again.");
        setPage(1);
        return;
      }
      remember(profileId, { approved: true, finished: false, plan }); setNotice("");
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); return; }
    setPage(4);
    void install(0);
  }
  function pause() { setPausing(true); setNow(""); abort.current?.abort(); }
  async function toReady() {
    if (!profileId) return;
    try { reviewed.current = await planSnapshot(profileId); setPage(3); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }
  function again() {
    if (!profileId) return;
    remember(profileId, { approved: false, finished: false });
    setRows(STAGES.map(() => "todo")); setUnderstood(false); setPreflight(null); setPage(0);
  }

  if (!profileId) return <p>Select a kit first.</p>;
  const finished = rows.filter(row => row === "done" || row === "skipped").length;
  const percent = page === 5 ? 100 : page === 4 ? Math.round(8 + 92 * finished / STAGES.length) : page * 4;
  const fails = preflight?.items.filter(item => item.state === "fail") ?? [];
  const warns = preflight?.items.filter(item => item.state === "warn") ?? [];

  if (page === 5) return <section className="ki-finish" aria-label="Kit built">
    <div className="ki-done-head"><Check size={22} aria-hidden="true" /><div><h1>Your kit is built</h1><p>Everything below comes from the app's own checks.</p></div>
      <button type="button" className="secondary-action" onClick={again}><RotateCcw size={15} aria-hidden="true" />Run the installer again</button></div>
    {warning && <p className="fw-stop" role="alert">{warning}</p>}
    <HandoverPage profileId={profileId} />
  </section>;

  return <section className="ki" aria-label="Build my kit">
    <aside className="ki-side">
      <div className="ki-brand"><Package size={26} aria-hidden="true" /><b>Build my kit</b><small>{kitName}</small></div>
      <ol>{PAGES.map((name, index) => <li key={name} className={index < page ? "done" : index === page ? "now" : ""} aria-current={index === page ? "step" : undefined}>
        <span>{index < page ? <Check size={12} /> : index + 1}</span>{name}</li>)}</ol>
    </aside>
    <div className="ki-main">
      <div className="ki-body">
        {page === 0 && <>
          <h1>Welcome</h1>
          <p>This installer builds the whole kit for you, step by step. It checks first, shows you every change, and asks once before it changes anything.</p>
          <h2>Equipment</h2>
          <ul className="ki-list">{[...servers, ...switches].map(item => <li key={item.deviceId}><b>{item.name}</b> <small>{item.model}</small></li>)}
            {!servers.length && !switches.length && <li>No equipment yet. <Link to="/">Add it on My Rack</Link> first.</li>}</ul>
        </>}
        {page === 1 && <>
          <h1>Check</h1>
          <p>A read-only check of everything the install needs. Nothing is changed.</p>
          {notice && <p className="fw-stop" role="status">{notice}</p>}
          {checking && <p role="status"><Loader2 size={15} className="dr-spin" aria-hidden="true" /> Checking…</p>}
          {preflight && <ul className="ei-rows" aria-label="Pre-flight">{preflight.items.map(item => <li key={`${item.group}-${item.name}`} className={`ei-row ${item.state === "ok" ? "ei-done" : item.state === "warn" ? "ei-todo" : "ei-warn"}`}>
            <span aria-hidden="true">{item.state === "ok" ? <Check size={14} /> : <AlertTriangle size={14} />}</span>
            <div><b>{item.name}</b> {item.detail}{item.state !== "ok" && item.fix && <small className="ki-fix"> {item.fix}</small>}</div></li>)}</ul>}
          {!!fails.length && <p className="fw-stop" role="alert">Fix the {fails.length === 1 ? "red item" : `${fails.length} red items`}, then check again.</p>}
          {!fails.length && !!warns.length && <p className="ex-hint">{warns.length} warning{warns.length === 1 ? "" : "s"}: the install can go ahead.</p>}
        </>}
        {page === 2 && <>
          <h1>Settings</h1>
          <p>What will be built. Change anything with Edit, then come back.</p>
          <Settings profileId={profileId} servers={servers} switches={switches} />
        </>}
        {page === 3 && <>
          <h1>Ready to install</h1>
          <p>In this order. Steps already done are skipped. Each change is sent once, checked, and recorded.</p>
          <ol className="ki-changes">{STAGES.map(stage => <li key={stage.id}><b>{stage.title}</b><span>{stage.changes}</span></li>)}</ol>
          <label className="wipe-ok"><input type="checkbox" checked={understood} onChange={e => setUnderstood(e.target.checked)} />I understand these changes: the restarts, the server being forced off if it has not shut down after two minutes, and the loss of any data on the planned RAID disks (nothing on them needs keeping).</label>
        </>}
        {page === 4 && <>
          <h1>{stopped ? "The install needs you" : running ? "Installing…" : "Paused"}</h1>
          <ul className="ei-rows ki-stages" aria-label="Install steps">{STAGES.map((stage, index) => {
            const row = rows[index];
            return <li key={stage.id} className={`ei-row ${row === "done" || row === "skipped" ? "ei-done" : row === "running" ? "ei-now" : row === "stopped" ? "ei-warn" : "ei-todo"}`}>
              <span aria-hidden="true">{row === "done" || row === "skipped" ? <Check size={14} /> : row === "running" ? <Loader2 size={14} className="dr-spin" /> : row === "stopped" ? <AlertTriangle size={14} /> : <CircleDashed size={14} />}</span>
              {stage.title}{row === "skipped" && <small className="ki-skip"> · already done</small>}</li>;
          })}</ul>
          {running && now && <p className="ki-now" role="status">{now}</p>}
          {stopped && <div className="fw-stop" role="alert"><p>{stopped.message}</p>
            <p><Link to={stopped.where}>{stopped.label}</Link> · nothing was sent again.</p></div>}
          {!running && !stopped && <p className="ex-hint">Paused. Nothing new is sent while paused; whatever was already running on the equipment carries on. Continue picks it up.</p>}
          {warning && <p className="fw-stop" role="alert">{warning}</p>}
        </>}
        {error && <p className="fw-stop" role="alert">{error}</p>}
      </div>
      <div className="inst-progress" aria-label="Progress">
        <div className={`inst-bar ${stopped ? "warn" : ""} ${running ? "moving" : ""}`} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}><span style={{ width: `${percent}%` }} /></div>
      </div>
      <footer className="ki-foot">
        {page > 0 && page < 4 && <button type="button" className="secondary-action" onClick={() => setPage((page - 1) as Page)}>Back</button>}
        <span className="inst-grow" />
        {page === 0 && <button type="button" className="primary-action" disabled={!servers.length && !switches.length} onClick={() => setPage(1)}>Next</button>}
        {page === 1 && <><button type="button" className="secondary-action" disabled={checking} onClick={() => void check()}>Check again</button>
          <button type="button" className="primary-action" disabled={checking || !preflight || !!fails.length} onClick={() => setPage(2)}>Next</button></>}
        {page === 2 && <button type="button" className="primary-action" onClick={() => void toReady()}>Next</button>}
        {page === 3 && <button type="button" className="primary-action" disabled={!understood} onClick={() => void approve()}>Install</button>}
        {page === 4 && running && <button type="button" className="secondary-action" disabled={pausing} onClick={pause}>{pausing ? "Pausing…" : "Pause"}</button>}
        {page === 4 && !running && <button type="button" className="primary-action" onClick={() => void install(stopped?.index ?? 0)}>{stopped ? "Try again" : "Continue"}</button>}
      </footer>
    </div>
  </section>;
}
