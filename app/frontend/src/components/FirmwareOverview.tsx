import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { RefreshCw, Server, X } from "lucide-react";
import { api, type FirmwareAssessment } from "../api";
import type { IloAccessSettings } from "../types";
import { ProvenanceChip } from "./studio/ProvenanceChip";
import { IloInstaller } from "./IloInstaller";
import { guardedApi } from "../api";
import { useSppAvailability } from "./SppUpdatePanel";
import { PartsInstaller } from "./PartsInstaller";
import { partsUpdateApi } from "../api";
import { attemptKey, readAttempt } from "./GuardedExecution";

/*
 * One server's firmware at a glance: what is installed, what the selected package can take it
 * to, and the one update the app can run. Hardware health lives on the connection and disk
 * pages; this page only compares versions. Every write step sits in the update panel.
 */

type Row = FirmwareAssessment["rows"][number];
type Line = { key: string; label: string; detail?: string; installed: string | null; target: string | null; status: string; ilo: boolean };

// iLO 5 below 1.48 must install the 1.48 bridge first (the SPP marks it as the prerequisite).
// HPE iLO 5 3.19 release notes list no further intermediate step for Gen10 (checked 2026-09-29).
const ILO5_STEPS = ["1.48"];
const APP_ILO_STEPS = ["1.48", "3.19"];
const version = (text: string | null) => Number(/(\d+\.\d+)/.exec(text ?? "")?.[1] ?? NaN);

function iloPath(installed: string | null, target: string | null, ilo5 = true) {
  const from = version(installed), to = version(target);
  if (Number.isNaN(from) || Number.isNaN(to) || to <= from) return [];
  return [...(ilo5 ? ILO5_STEPS : []).filter(step => Number(step) > from && Number(step) < to), target!];
}

const PREFIX = /^(Storage controller|Network adapter|Drive):\s*/;
/** Drives and adapters with the same model, version and result collapse into one line. */
function lines(rows: Row[]): Line[] {
  const out = new Map<string, { row: Row; name: string; places: string[] }>();
  for (const row of rows) {
    // Only grouped parts carry a place after " / "; "System ROM / BIOS" is one name.
    const [name, place] = row.group ? row.component.replace(PREFIX, "").split(" / ") : [row.component];
    const key = [row.group ?? "", name, row.installed, row.target, row.status].join("|");
    const entry = out.get(key) ?? { row, name, places: [] };
    if (place) entry.places.push(place);
    out.set(key, entry);
  }
  return [...out.entries()].map(([key, { row, name, places }]) => {
    const drive = row.group === "Drive", count = Math.max(places.length, 1);
    return { key, installed: row.installed, target: row.target, status: row.status, ilo: /^iLO(\s|$)/i.test(row.component),
      label: count > 1 ? `${count} × ${name}${drive ? " drives" : ""}` : drive ? `${name} drive` : name,
      detail: !places.length ? undefined : /^slot/i.test(places[0]) ? places.join(", ") : `${drive ? (count > 1 ? "Bays" : "Bay") : count > 1 ? "Slots" : "Slot"} ${places.join(", ")}` };
  });
}

function Status({ line }: { line: Line }) {
  if (line.status === "Update available") return <span className="fw-pill fw-pill-up">Update available</span>;
  if (!line.target) return <span className="fw-pill">No update</span>;
  return <span className="fw-pill">{line.status === "Cannot determine" ? "Not compared" : "Up to date"}</span>;
}

export function FirmwareOverview({ profileId, deviceId, deviceName, model, packageName, packageCurrent }: {
  profileId: string; deviceId: string; deviceName: string; model: string; packageName?: string; packageCurrent?: boolean;
}) {
  const [access, setAccess] = useState<IloAccessSettings | null>(null);
  const [result, setResult] = useState<FirmwareAssessment | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [checkedHere, setCheckedHere] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  // Part by part through the iLO (System ROM first): the main way to update firmware.
  const [partsOpen, setPartsOpen] = useState(false);
  const [partsActive, setPartsActive] = useState(false);
  useEffect(() => {
    let active = true;
    partsUpdateApi.status(profileId, deviceId).then(value => { if (active) setPartsActive(value.active); }).catch(() => {});
    return () => { active = false; };
  }, [profileId, deviceId, partsOpen]);
  const [reload, setReload] = useState(0);
  const [filter, setFilter] = useState<"all" | "updates" | "now">("all");
  const [updateActive, setUpdateActive] = useState(() => !!readAttempt(attemptKey(profileId, "firmware-execution", deviceId)));
  // "Update in progress" comes from the recorded status (and any saved browser attempt), re-read when the installer closes.
  const [statusTick, setStatusTick] = useState(0);
  useEffect(() => {
    let active = true;
    guardedApi.status(profileId, "firmware-execution", deviceId)
      .then(value => { if (active) setUpdateActive(!!readAttempt(attemptKey(profileId, "firmware-execution", deviceId)) || ["submitting", "accepted", "running", "uncertain"].includes(value.status)); })
      .catch(() => {});
    return () => { active = false; };
  }, [profileId, deviceId, statusTick]);
  const requestId = useRef(0);
  const panel = useRef<HTMLDialogElement>(null);
  // When the backend offers a whole-package update, one Review update replaces per-part actions.
  const spp = useSppAvailability(profileId, deviceId);
  const sppMode = spp.state === "available";

  useEffect(() => {
    const id = ++requestId.current;
    setLoading(true); setBusy(false); setAccess(null); setResult(null); setError(""); setCheckedHere(false);
    Promise.all([api.iloAccessSettings(deviceId), api.firmwareAssessment(profileId, deviceId)])
      .then(([settings, assessment]) => { if (id === requestId.current) { setAccess(settings); setResult(assessment); } })
      .catch(err => { if (id === requestId.current) setError(err instanceof Error ? err.message : String(err)); })
      .finally(() => { if (id === requestId.current) setLoading(false); });
    return () => { ++requestId.current; };
  }, [profileId, deviceId, packageName, packageCurrent, reload]);
  useEffect(() => { if (panelOpen) panel.current?.showModal(); else panel.current?.close(); }, [panelOpen, sppMode]);

  const connected = Boolean(access?.host && access.username_configured && access.password_configured);
  async function check() {
    const id = ++requestId.current;
    setBusy(true); setError(""); setCheckedHere(false);
    try {
      const probe = await api.probeProvider("ilo-redfish", deviceId);
      if (id !== requestId.current) return;
      if (probe.status !== "ok") throw new Error(probe.message || "The server did not answer.");
      const assessment = await api.firmwareAssessment(profileId, deviceId);
      if (id !== requestId.current) return;
      // The comparison must come from this read, not an older or concurrent one.
      if (assessment.rows?.length && (!probe.checked_at || assessment.checked_at !== probe.checked_at)) throw new Error("The comparison does not match this read. Check again.");
      setResult(assessment); setCheckedHere(true);
    } catch (err) { if (id === requestId.current) setError(`Check unsuccessful: ${err instanceof Error ? err.message : String(err)}`); }
    finally { if (id === requestId.current) setBusy(false); }
  }

  const blocker = loading ? "" : !connected ? "connection" : !packageCurrent ? (packageName ? "The selected package is missing or changed. Choose it again above." : "Choose a firmware package above to compare.") : "";
  const all = result ? lines(result.rows ?? []) : [];
  const isIlo5 = (line: Line) => {
    const reportedGeneration = /\biLO\s*(\d+)\b/i.exec(`${line.label} ${line.installed ?? ""}`)?.[1];
    return reportedGeneration ? reportedGeneration === "5" : /\bGen10\b/i.test(result?.detected_model ?? "");
  };
  const canRunNow = (line: Line) => line.ilo && isIlo5(line) && line.status === "Update available" && APP_ILO_STEPS.includes(iloPath(line.installed, line.target)[0]) && !!packageCurrent && connected;
  const nextStep = all.find(canRunNow);
  const panelStep = nextStep ? iloPath(nextStep.installed, nextStep.target)[0] : "next version";
  const counts = { all: all.length, updates: all.filter(line => line.status === "Update available").length, now: all.filter(canRunNow).length };
  const filterOptions: Array<["all" | "updates" | "now", string, string]> = [["all", "All parts", ""], ["updates", "Updates available", "fw-f-up"]];
  if (!sppMode) filterOptions.push(["now", "App can install now", "fw-f-now"]);
  const rows = filter === "updates" ? all.filter(line => line.status === "Update available") : filter === "now" ? all.filter(canRunNow) : all;
  return <section className="fw-card" aria-label={deviceName}>
    <header className="fw-card-h">
      <Server size={20} aria-hidden="true" />
      <div><h2>{deviceName}</h2><p>{result?.detected_model || model}</p></div>
      <span className="fw-card-read">{result?.checked_at ? <ProvenanceChip kind={checkedHere ? "proven" : "recorded"} time={result.checked_at}>{checkedHere ? "read now" : "last read"}</ProvenanceChip>
        : !loading && <ProvenanceChip kind="blank">not read yet</ProvenanceChip>}</span>
      <button type="button" className="secondary-action" disabled={loading || busy || !!blocker} onClick={() => void check()}><RefreshCw size={15} />{busy ? "Reading..." : "Check again"}</button>
      {/* One button: through the iLO first, then HPE's boot disc only if something still needs it. */}
      {sppMode && <button type="button" className={partsActive || spp.inProgress ? "secondary-action" : "primary-action fw-review"} disabled={!partsActive && !spp.inProgress && (!!blocker || loading)}
        onClick={() => setPartsOpen(true)}>{partsActive || spp.inProgress ? "Updating firmware · open" : "Update firmware"}</button>}
    </header>
    {blocker === "connection" ? <p className="fw-card-why" role="note">Save this server's iLO address and sign-in first. <Link to={`/setup/connect?device=${encodeURIComponent(deviceId)}`}>Open connection settings</Link></p>
      : blocker && <p className="fw-card-why" role="note">{blocker}</p>}
    {error && <p className="fw-card-why fw-card-err" role="alert">{error}</p>}
    {all.length > 0 && <div className="fw-filter" role="group" aria-label="Show parts">
      {filterOptions.map(([key, label, tone]) =>
        <button key={key} type="button" className={tone} aria-pressed={filter === key} onClick={() => setFilter(key)}><b>{counts[key]}</b>{label}</button>)}
    </div>}
    {loading ? <p className="fw-card-empty" role="status">Loading…</p>
      : all.length && !rows.length ? <p className="fw-card-empty">Nothing in this view.</p>
      : !rows.length ? <p className="fw-card-empty">{result?.reason || "No firmware reading yet. Use Check again once a package is chosen."}</p>
      : <table className="fw-table">
        <thead><tr><th>Part</th><th>Installed</th><th>Can go to</th><th>Status</th><th><span className="sr-only">Action</span></th></tr></thead>
        <tbody>{rows.map(line => {
          const path = line.ilo ? iloPath(line.installed, line.target, isIlo5(line)) : [];
          const next = path[0];
          const appCanRun = canRunNow(line);
          return <tr key={line.key}>
            <th scope="row"><strong>{line.label}</strong>{line.detail && <small>{line.detail}</small>}</th>
            <td data-label="Installed" className="fw-v">{line.installed || "Not reported"}</td>
            <td data-label="Can go to">{path.length > 1 ? <><span className="fw-path">{path.map((step, index) => <span key={step}>{index > 0 && <i aria-hidden="true">→</i>}<b className={index === 0 ? "next" : ""}>{step}</b></span>)}</span>
                <small>Needs {path.slice(0, -1).join(" and ")} first</small></>
              : line.target ? <span className="fw-v">{line.target}</span> : <small>No match in package</small>}</td>
            <td data-label="Status"><Status line={line} /></td>
            <td className="fw-act">{sppMode || line.status !== "Update available" ? null
              : updateActive && line.ilo ? <button type="button" className="secondary-action" onClick={() => setPanelOpen(true)}>Update in progress · open</button>
              : appCanRun ? <button type="button" className="primary-action" onClick={() => setPanelOpen(true)}>Update to {next}</button>
              : <small>{line.ilo && !isIlo5(line) ? "Requires an adapter for the detected iLO generation" : line.ilo && next && !APP_ILO_STEPS.includes(next) ? `Step to ${next} not in the app yet` : "Not in the app yet"}</small>}</td>
          </tr>;
        })}</tbody>
      </table>}
    {/* Kept mounted so a sent or uncertain update is read back on every visit, even while closed. */}
    {connected && partsOpen && <PartsInstaller profileId={profileId} deviceId={deviceId} deviceName={deviceName}
      onClose={changed => { setPartsOpen(false); if (changed) setReload(value => value + 1); }} />}
    {connected && !sppMode && spp.state !== "loading" && panelOpen && <IloInstaller profileId={profileId} deviceId={deviceId} deviceName={deviceName}
      installed={String(version(all.find(line => line.ilo)?.installed ?? null) || "") || null}
      onClose={() => { setPanelOpen(false); setStatusTick(value => value + 1); }} onChanged={() => setReload(value => value + 1)} />}
  </section>;
}
