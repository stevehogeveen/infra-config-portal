import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, AlertTriangle, ArrowRight, Check, Circle, RefreshCw, X } from "lucide-react";
import { api, type BuildHistoryEntry } from "../api";
import { TimeLapse } from "./InsightPages";

/** Run history: what the app read, saved and changed, newest first, from its own records. */
export function ActivityPage() {
  const [entries, setEntries] = useState<BuildHistoryEntry[]>([]);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [filter, setFilter] = useState<"all" | "attention">("all");
  useEffect(() => {
    let active = true;
    api.buildHistory(200)
      .then(next => { if (active) { setEntries(next); setError(""); } })
      .catch(err => { if (active) setError(err instanceof Error ? err.message : String(err)); })
      .finally(() => { if (active) setLoaded(true); });
    return () => { active = false; };
  }, [refresh]);
  const attention = (entry: BuildHistoryEntry) => entry.outcome === "failed" || entry.outcome === "attention";
  const visible = filter === "attention" ? entries.filter(attention) : entries;
  const days = new Map<string, BuildHistoryEntry[]>();
  for (const entry of visible) {
    const day = new Date(entry.at).toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
    days.set(day, [...(days.get(day) ?? []), entry]);
  }
  return <section className="activity-page">
    <header className="activity-heading"><div><h1>Run history</h1><p>Every result, saved plan and confirmed change, newest first.</p></div>
      <button type="button" onClick={() => setRefresh(value => value + 1)}><RefreshCw size={16} />Refresh</button></header>
    <div className="activity-filters" role="group" aria-label="Activity filter">
      <button type="button" aria-pressed={filter === "all"} onClick={() => setFilter("all")}>Everything ({entries.length})</button>
      <button type="button" aria-pressed={filter === "attention"} onClick={() => setFilter("attention")}>Needs attention ({entries.filter(attention).length})</button>
    </div>
    {loaded && !error && <TimeLapse entries={entries} />}
    {error && <p role="alert">History could not be loaded: {error}</p>}
    {!loaded ? <p role="status">Loading history...</p>
      : !visible.length ? <div className="activity-empty"><Activity size={36} /><h2>{error ? "History unavailable" : filter === "all" ? "Nothing recorded yet" : "Nothing needs attention"}</h2><Link to="/setup/guide">Go to setup<ArrowRight size={16} /></Link></div>
      : <div className="history-days">{[...days].map(([day, items]) => <section key={day} aria-label={day}>
          <h2>{day}</h2>
          <ol className="history-list">{items.map(entry => <li key={entry.id} className={`history-${entry.outcome}`}>
            <span className="history-icon" aria-hidden="true">{entry.outcome === "ok" ? <Check size={15} /> : entry.outcome === "failed" ? <X size={15} /> : entry.outcome === "attention" ? <AlertTriangle size={15} /> : <Circle size={9} />}</span>
            <time dateTime={entry.at}>{new Date(entry.at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}</time>
            <span className="history-area">{entry.area}</span>
            <span className="history-message">{entry.message}</span>
          </li>)}</ol>
        </section>)}</div>}
  </section>;
}
