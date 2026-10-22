import { useEffect, useRef, useState } from "react";
import { Bell, BellOff, Lightbulb, Loader2, AlertTriangle, ArrowRight } from "lucide-react";
import { jobsApi, type DeviceHealth, type KitJob, type KitJobs } from "../api";

/** "12 min", "1 h 05 min": how long a job has been going. */
export function elapsed(since: string, now = Date.now()) {
  const minutes = Math.max(0, Math.round((now - Date.parse(since)) / 60000));
  if (minutes < 1) return "just started";
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")} min`;
}

const POLL_MS = 15000;
const NOTIFY_KEY = "lab-builder-notify-v1";

/** Shared poll of the jobs feed (database only; never contacts hardware). */
export function useKitJobs(pollMs = POLL_MS) {
  const [jobs, setJobs] = useState<KitJobs | null>(null);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try { const next = await jobsApi.list(); if (active) setJobs(next); } catch { /* keep the last answer */ }
      if (active) timer = setTimeout(() => void load(), pollMs);
    }
    void load();
    return () => { active = false; clearTimeout(timer); };
  }, [pollMs]);
  return jobs;
}

function chime() {
  try {
    const context = new AudioContext();
    [660, 880].forEach((frequency, index) => {
      const tone = context.createOscillator(); const gain = context.createGain();
      tone.frequency.value = frequency; tone.connect(gain); gain.connect(context.destination);
      const start = context.currentTime + index * 0.18;
      gain.gain.setValueAtTime(0.0001, start); gain.gain.exponentialRampToValueAtTime(0.2, start + 0.02); gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.3);
      tone.start(start); tone.stop(start + 0.32);
    });
  } catch { /* no sound available */ }
}

/**
 * Top-bar bell: shows running jobs with how long they've been going; when turned on, a desktop
 * notification and a chime when a job finishes or stops for attention.
 */
export function JobBell() {
  const jobs = useKitJobs();
  const [notify, setNotify] = useState(() => { try { return localStorage.getItem(NOTIFY_KEY) === "on"; } catch { return false; } });
  const [open, setOpen] = useState(false);
  const seen = useRef<Map<string, KitJob["state"]> | null>(null);
  useEffect(() => {
    if (!jobs) return;
    const current = new Map<string, KitJob["state"]>([...jobs.running, ...jobs.attention, ...jobs.recent].map(job => [job.id, job.state]));
    const before = seen.current;
    seen.current = current;
    if (!before || !notify) return;
    for (const job of [...jobs.attention, ...jobs.recent]) {
      if (before.get(job.id) === "running" && job.state !== "running") {
        const title = job.state === "done" ? `${job.label} finished` : `${job.label} needs you`;
        const body = `${job.device_name}${job.state === "done" ? " · done" : " · open Lab Builder to see why"}`;
        chime();
        try { if (Notification.permission === "granted") new Notification(title, { body, tag: job.id }); } catch { /* notifications unavailable */ }
      }
    }
  }, [jobs, notify]);
  async function toggle() {
    const next = !notify;
    if (next && typeof Notification !== "undefined" && Notification.permission === "default") {
      try { await Notification.requestPermission(); } catch { /* ignored */ }
    }
    setNotify(next);
    try { localStorage.setItem(NOTIFY_KEY, next ? "on" : "off"); } catch { /* ignored */ }
    if (next) chime();
  }
  const running = jobs?.running ?? [];
  const attention = jobs?.attention ?? [];
  const count = running.length + attention.length;
  return <div className="job-bell">
    <button type="button" className={`sd-icon-btn ${count ? "has-jobs" : ""}`} aria-label={`Jobs${count ? `: ${count} open` : ""}`} aria-expanded={open} onClick={() => setOpen(value => !value)}>
      {notify ? <Bell size={16} aria-hidden="true" /> : <BellOff size={16} aria-hidden="true" />}
      {count > 0 && <span className={`job-count ${attention.length ? "warn" : ""}`}>{count}</span>}
    </button>
    {open && <div className="sd-menu sd-menu-right job-menu" role="dialog" aria-label="Jobs">
      {!count && <p className="job-empty">Nothing running.</p>}
      {[...attention, ...running].map(job => <a key={job.id} href={job.path} className={`job-row ${job.state}`}>
        {job.state === "running" ? <Loader2 size={15} className="dr-spin" aria-hidden="true" /> : <AlertTriangle size={15} aria-hidden="true" />}
        <span><b>{job.label}</b><small>{job.device_name} · {job.state === "running" ? `running ${elapsed(job.started_at)}` : "needs you"}</small></span>
        <ArrowRight size={14} aria-hidden="true" />
      </a>)}
      <label className="job-notify"><input type="checkbox" checked={notify} onChange={() => void toggle()} />Chime and notify me when a job finishes</label>
    </div>}
  </div>;
}

/** My Rack: anything running or stopped mid-way comes first, before anything new. */
export function ResumeCard() {
  const jobs = useKitJobs();
  const items = [...(jobs?.attention ?? []), ...(jobs?.running ?? [])];
  if (!items.length) return null;
  return <section className="resume-card" aria-label="Pick up where you left off">
    <h2>Pick up where you left off</h2>
    {items.map(job => <div key={job.id} className={`resume-row ${job.state}`}>
      {job.state === "running" ? <Loader2 size={17} className="dr-spin" aria-hidden="true" /> : <AlertTriangle size={17} aria-hidden="true" />}
      <span><b>{job.label} · {job.device_name}</b><small>{job.state === "running" ? `Running for ${elapsed(job.started_at)}` : "Stopped and needs you"}</small></span>
      <a className="secondary-action" href={job.path}>Open<ArrowRight size={15} /></a>
    </div>)}
  </section>;
}

/** Find this exact box: blink the server's blue ID light and show its serial number. */
export function IdentifyButton({ deviceId }: { deviceId: string }) {
  const [state, setState] = useState<{ on: boolean; serial: string | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function run(on: boolean) {
    setBusy(true); setError("");
    try { const result = await jobsApi.identify(deviceId, on); setState({ on: /blink|lit/i.test(result.indicator ?? ""), serial: result.serial }); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }
  return <span className="identify">
    <button type="button" className={`secondary-action ${state?.on ? "is-on" : ""}`} disabled={busy} onClick={() => void run(!state?.on)}>
      <Lightbulb size={15} aria-hidden="true" />{busy ? "…" : state?.on ? "Turn ID light off" : "Blink ID light"}</button>
    {state?.serial && <small>Serial {state.serial}</small>}
    {error && <small role="alert">{error}</small>}
  </span>;
}


/** Health from each server's last stored check (database only). Refreshes when evidence changes. */
export function useHealth(deviceIds: string[], refreshKey: unknown) {
  const [health, setHealth] = useState<Record<string, DeviceHealth>>({});
  const key = deviceIds.join(",");
  useEffect(() => {
    let active = true;
    Promise.all(deviceIds.map(async id => [id, await jobsApi.health(id).catch(() => null)] as const))
      .then(rows => { if (active) setHealth(Object.fromEntries(rows.filter(([, value]) => value) as Array<[string, DeviceHealth]>)); });
    return () => { active = false; };
  }, [key, refreshKey]);
  return health;
}

/** "21°C · fans 6/6 · power 2/2", red when something is wrong. */
export function HealthLine({ health }: { health?: DeviceHealth }) {
  if (!health?.overall) return null;
  const parts = [health.inlet_c != null ? `${health.inlet_c}°C inlet` : null,
    health.fans ? `fans ${health.fans_ok}/${health.fans}` : null,
    health.psus ? `power ${health.psu_ok}/${health.psus}` : null].filter(Boolean);
  const bad = health.problems.length > 0;
  return <small className={`health-line ${bad ? "bad" : "ok"}`} title={bad ? health.problems.join("\n") : `Health from the last check${health.checked_at ? ` at ${new Date(health.checked_at).toLocaleString()}` : ""}`}>
    {bad ? `⚠ ${health.problems[0]}` : parts.join(" · ")}
  </small>;
}
