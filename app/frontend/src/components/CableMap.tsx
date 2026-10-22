import { useEffect, useState } from "react";
import { Cable, RefreshCw } from "lucide-react";
import { jobsApi, type CableMapResult } from "../api";
import { ProvenanceChip } from "./studio/ProvenanceChip";

/** My Rack: which server port is plugged into which switch port. Read on click; shows the last read. */
export function CableMap({ profileId }: { profileId: string }) {
  const [map, setMap] = useState<CableMapResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { jobsApi.cableMap(profileId).then(setMap).catch(() => setMap(null)); }, [profileId]);
  async function read() {
    setBusy(true); setError("");
    try { setMap(await jobsApi.readCableMap(profileId)); } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }
  const read_ = map && map.state !== "not_read";
  return <section className="cable-map" aria-label="Cables">
    <header><h2><Cable size={18} aria-hidden="true" />Cables</h2>
      {read_ && map?.checked_at && <ProvenanceChip kind="recorded" time={map.checked_at}>read</ProvenanceChip>}
      <button type="button" className="secondary-action" disabled={busy} onClick={() => void read()}><RefreshCw size={15} className={busy ? "dr-spin" : ""} />{busy ? "Reading…" : read_ ? "Read again" : "Read cables"}</button></header>
    {error && <p role="alert">{error}</p>}
    {!read_ && !error && <p className="cable-hint">Reads which server port is plugged into which switch port. Only reads; needs the switch set up.</p>}
    {read_ && <>
      {map!.problems?.map(problem => <p key={problem} className="cable-problem">{problem}</p>)}
      {map!.cables.length > 0 && <ul className="cable-list">{map!.cables.map(cable => <li key={cable.mac}>
        <b>{cable.server}</b> <span>{cable.server_port}</span><i aria-hidden="true">→</i><b>{cable.switch}</b> <span>{cable.switch_port} · VLAN {cable.vlan}</span>
      </li>)}</ul>}
      {map!.unmatched_server_ports.map(port => <p key={port.server + port.server_port} className="cable-problem"><b>{port.server} {port.server_port}:</b> {port.note}</p>)}
      {map!.other_switch_ports.map(port => <p key={port.switch + port.switch_port} className="cable-note"><b>{port.switch} {port.switch_port}</b> (VLAN {port.vlan}): {port.note}</p>)}
      {!map!.cables.length && !map!.problems?.length && <p className="cable-hint">No server port was seen on the switch yet.</p>}
    </>}
  </section>;
}
