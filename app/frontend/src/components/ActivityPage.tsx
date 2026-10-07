import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, ArrowRight, RefreshCw, Circle } from "lucide-react";
import { api } from "../api";

type Entry = { id: string; name: string; status: string; at: string; to: string };
const labels: Record<string, string> = { executing: "Working", started: "Working", queued: "Waiting to start", needs_approval: "Needs approval", failed: "Could not finish", completed: "Completed", finished: "Finished", planned: "Plan ready", draft: "Draft", cancelled: "Cancelled", blocked: "Needs attention", expired: "Expired", submitted: "Submitted", validating: "Checking", approved: "Approved", rejected: "Rejected" };

export function ActivityPage() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [filter, setFilter] = useState("all");
  useEffect(() => {
    let active = true;
    let inFlight = false;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      if (!active || inFlight || document.hidden) return;
      inFlight = true;
      try {
        const [requests, runs, devices] = await Promise.all([api.requests(), api.workflowRuns(), api.deviceInventory()]);
        const servers = devices.filter(device => /ilo|server|bmc/i.test(device.device_type));
        const inventories = await Promise.all(servers.map(async device => ({ device, run: await api.latestInventoryJob(device.id) })));
        const next: Entry[] = [
          ...requests.map(request => ({ id: `request:${request.id}`, name: request.vm_deploy?.vm_name ? `Windows VM: ${request.vm_deploy.vm_name}` : "Deployment request", status: request.status, at: request.updated_at, to: `/requests/${request.id}` })),
          ...runs.map(run => ({ id: `run:${run.id}`, name: run.workflow_slug.replace(/[_-]/g, " "), status: run.status, at: run.updated_at, to: `/requests/${run.request_id}` })),
          ...inventories.flatMap(({ device, run }) => run ? [{ id: `inventory:${run.job_id}`, name: `${device.display_name}: inventory${run.result?.source === "mock" ? " (test)" : ""}`, status: run.result?.status || run.status, at: run.result?.checked_at || "", to: `/setup/connect?device=${encodeURIComponent(device.id)}` }] : []),
        ];
        if (active) { setEntries(next.sort((a, b) => b.at.localeCompare(a.at))); setError(""); }
      } catch (err) { if (active) setError(err instanceof Error ? err.message : String(err)); }
      finally { inFlight = false; if (active) { setLoaded(true); if (!document.hidden) timer = setTimeout(() => void load(), 15000); } }
    }
    function visibilityChanged() {
      clearTimeout(timer);
      if (!document.hidden) void load();
    }
    document.addEventListener("visibilitychange", visibilityChanged);
    void load();
    return () => { active = false; clearTimeout(timer); document.removeEventListener("visibilitychange", visibilityChanged); };
  }, [refresh]);
  const attention = (entry: Entry) => ["failed", "blocked", "needs_approval", "expired"].includes(entry.status);
  const visible = filter === "attention" ? entries.filter(attention) : entries;
  return <section className="activity-page"><header className="activity-heading"><div><h1>Run history</h1><p>Completed work, failures and pending approvals across all kits.</p></div><button onClick={() => setRefresh(value => value + 1)}><RefreshCw size={16} />Refresh</button></header>
    <div className="activity-filters" role="group" aria-label="Activity filter"><button aria-pressed={filter === "all"} onClick={() => setFilter("all")}>All activity ({entries.length})</button><button aria-pressed={filter === "attention"} onClick={() => setFilter("attention")}>Needs attention ({entries.filter(attention).length})</button></div>
    {error && <p role="alert">Could not refresh activity. {error}</p>}
    {!loaded ? <p role="status">Loading activity...</p> : !visible.length ? <div className="activity-empty"><Activity size={36} /><h2>{error ? "Activity unavailable" : filter === "all" ? "No activity yet" : "Nothing needs attention"}</h2><Link to="/setup/guide">Return to setup<ArrowRight size={16} /></Link></div> : <div className="activity-list">{visible.map(entry => <Link key={entry.id} to={entry.to}><Activity size={20} /><strong>{entry.name}</strong><span className={attention(entry) ? "attention" : ""}><Circle size={12} />{labels[entry.status] || entry.status}</span><time>{entry.at ? new Date(entry.at).toLocaleString() : "Time not recorded"}</time><ArrowRight size={16} /></Link>)}</div>}
    <footer className="setup-footer"><span>Completed jobs are not proof that the whole kit is ready.</span><Link to="/run-tools">Advanced run controls<ArrowRight size={16} /></Link></footer>
  </section>;
}
