import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { ArrowRight, Check, CircleDashed, Pause, Play, Search, TriangleAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { insightApi, type AskAnswer, type BuildHistoryEntry, type TracePath } from "../api";
import { useStudio } from "./studio/StudioContext";

const when = (value?: string | null) => value ? new Date(value).toLocaleString() : "";

/* ---------------------------------------------------------------- trace the path */

/** VM -> ESXi -> port -> cable -> switch -> gateway, lit hop by hop up to where the evidence stops. */
export function TracePage({ profileId: given }: { profileId?: string } = {}) {
  const studio = useStudio();
  const profileId = given ?? studio?.profileId;
  const [data, setData] = useState<{ servers: TracePath[] } | null>(null);
  const [error, setError] = useState("");
  const [lit, setLit] = useState(0);
  useEffect(() => {
    let active = true;
    setData(null); setError("");
    if (profileId) insightApi.trace(profileId).then(next => { if (active) { setData(next); setLit(0); } })
      .catch(err => { if (active) setError(err instanceof Error ? err.message : String(err)); });
    return () => { active = false; };
  }, [profileId]);
  const longest = Math.max(0, ...(data?.servers ?? []).map(server => server.hops.length));
  useEffect(() => { if (lit < longest) { const timer = setTimeout(() => setLit(value => value + 1), 350); return () => clearTimeout(timer); } }, [lit, longest]);
  if (!profileId) return <p>Select a kit first.</p>;
  if (error) return <p className="fw-stop" role="alert">{error}</p>;
  if (!data) return <p role="status">Loading…</p>;
  return <section className="ex-page tr-page" aria-label="Trace the path">
    <header className="journey-heading"><h1>Trace the path</h1><p>From the Windows VM out to the gateway, using only what the app has checked.</p></header>
    {!data.servers.length && <p className="ex-hint">No servers in this kit.</p>}
    {data.servers.map(server => {
      const stop = server.stops_at;
      return <article key={server.device_id} className="tr-card" aria-label={`Path for ${server.name}`}>
        <h2>{server.name}</h2>
        <ol className="tr-hops">{server.hops.map((hop, index) => {
          const shown = index < lit;
          const cls = !shown ? "tr-wait" : hop.state === "proven" ? "tr-proven" : hop.state === "saved" ? "tr-saved" : "tr-unknown";
          return <li key={hop.name} className={`tr-hop ${cls} ${stop === index ? "tr-stop" : ""}`}>
            <span className="tr-icon" aria-hidden="true">{hop.state === "proven" ? <Check size={14} /> : hop.state === "saved" ? <CircleDashed size={14} /> : <TriangleAlert size={14} />}</span>
            <div><b>{hop.name}</b>{hop.detail && <span> · {hop.detail}</span>}
              <small>{hop.state === "proven" ? `Proven: ${hop.source}${hop.at ? `, ${when(hop.at)}` : ""}` : hop.state === "saved" ? `Planned only (${hop.source})` : hop.source}</small>
              {stop === index && hop.prove && <p className="tr-prove">Evidence stops here. {hop.prove}</p>}</div>
          </li>;
        })}</ol>
        {stop === null && <p className="inst-ok"><Check size={15} />Every hop is proven.</p>}
      </article>;
    })}
  </section>;
}

/* ---------------------------------------------------------------- ask the lab */

const EXAMPLES = ["Why is VLAN 100 here?", "What is 192.0.2.50?", "When was the firmware updated?"];

export function AskPage() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AskAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function ask(text: string, event?: FormEvent) {
    event?.preventDefault();
    if (!text.trim()) return;
    setQuestion(text); setBusy(true); setError("");
    try { setAnswer(await insightApi.ask(text.trim())); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }
  const groups: Array<[keyof Pick<AskAnswer, "plan" | "changes" | "checks">, string]> = [["plan", "Planned"], ["changes", "Changed"], ["checks", "Checked"]];
  return <section className="ex-page ask-page" aria-label="Ask the lab">
    <header className="journey-heading"><h1>Ask the lab</h1><p>Answers come only from the app's own records: what was planned, what was sent, what was checked.</p></header>
    <form className="ask-form" onSubmit={event => void ask(question, event)}>
      <Search size={18} aria-hidden="true" />
      <input aria-label="Question" value={question} maxLength={200} placeholder="Why is VLAN 100 here?" onChange={e => setQuestion(e.target.value)} />
      <button type="submit" className="primary-action" disabled={busy || !question.trim()}>{busy ? "Looking…" : "Ask"}</button>
    </form>
    {!answer && <div className="ask-examples">{EXAMPLES.map(text => <button key={text} type="button" className="secondary-action" onClick={() => void ask(text)}>{text}</button>)}</div>}
    {error && <p className="fw-stop" role="alert">{error}</p>}
    {answer && <div className="ask-answer" aria-live="polite">
      <p className="ask-summary" role="status">{answer.summary}</p>
      {groups.map(([key, label]) => answer[key].length ? <section key={key} aria-label={label}><h2>{label}</h2>
        <ul className="ho-list">{answer[key].map((row, index) => <li key={`${row.at}-${index}`}><b>{row.where}</b>{row.at ? ` · ${when(row.at)}` : ""} · {row.message}{row.outcome ? ` (${row.outcome})` : ""}</li>)}</ul></section> : null)}
    </div>}
  </section>;
}

/* ---------------------------------------------------------------- time-lapse */

const LIGHTS: Array<{ key: string; label: string; areas: string[] }> = [
  { key: "server", label: "Server", areas: ["Server check", "Server"] },
  { key: "firmware", label: "Firmware", areas: ["Firmware"] },
  { key: "disks", label: "Disks & RAID", areas: ["Disks & RAID"] },
  { key: "esxi", label: "ESXi", areas: ["ESXi"] },
  { key: "windows", label: "Windows", areas: ["Windows"] },
  { key: "switch", label: "Switch", areas: ["Switch"] },
];

/** Scrub through run history and watch each part of the build light up as it happened. */
export function TimeLapse({ entries }: { entries: BuildHistoryEntry[] }) {
  const ordered = useMemo(() => [...entries].sort((a, b) => a.at.localeCompare(b.at)), [entries]);
  const [index, setIndex] = useState(ordered.length);
  const [playing, setPlaying] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  useEffect(() => { setIndex(ordered.length); }, [ordered.length]);
  useEffect(() => {
    if (!playing) return;
    if (index >= ordered.length) { setPlaying(false); return; }
    timer.current = setTimeout(() => setIndex(value => value + 1), 250);
    return () => clearTimeout(timer.current);
  }, [playing, index, ordered.length]);
  if (!ordered.length) return null;
  const seen = ordered.slice(0, index);
  const state = (areas: string[]) => {
    const last = [...seen].reverse().find(entry => areas.includes(entry.area) && entry.outcome !== "info");
    return !last ? "idle" : last.outcome === "ok" ? "ok" : last.outcome === "failed" ? "bad" : "warn";
  };
  const current = seen[seen.length - 1];
  return <section className="tl" aria-label="Time-lapse">
    <div className="tl-lights">{LIGHTS.map(light => <span key={light.key} className={`tl-light tl-${state(light.areas)}`} data-testid={`tl-${light.key}`}>{light.label}</span>)}</div>
    <div className="tl-bar">
      <button type="button" className="secondary-action" aria-label={playing ? "Pause time-lapse" : "Play time-lapse"} onClick={() => { if (!playing && index >= ordered.length) setIndex(0); setPlaying(value => !value); }}>{playing ? <Pause size={15} /> : <Play size={15} />}</button>
      <input type="range" aria-label="Point in time" min={0} max={ordered.length} value={index} onChange={e => { setPlaying(false); setIndex(Number(e.target.value)); }} />
    </div>
    <p className="tl-now">{current ? <>{when(current.at)} · <b>{current.area}</b> · {current.message}</> : "Before the first record."}</p>
  </section>;
}

export function InsightLinks() {
  return <p className="ex-hint"><Link to="/trace">Trace the path <ArrowRight size={13} /></Link> · <Link to="/ask">Ask the lab <ArrowRight size={13} /></Link></p>;
}
