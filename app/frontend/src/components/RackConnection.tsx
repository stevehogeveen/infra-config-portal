import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { useRef, useState } from "react";
import type { RackPlan } from "./RackPlanner";
import type { DeviceInventoryItem } from "../types";
import { RackServerAccess, type AccessDraft } from "./RackServerAccess";
import { HardwareThumbnail } from "./HardwareThumbnail";
import { Guide, GuideActionProvider, useGuideActions } from "./studio/Guide";
import { useStudio } from "./studio/StudioContext";
import { ProvenanceChip, shortTime } from "./studio/ProvenanceChip";

export function RackConnection({ plan, profileId, loaded, busy, error, selectedId, onSelect }: {
  profileId: string;
  plan: RackPlan; loaded: boolean; busy: boolean; error: string; selectedId: string;
  onSelect: (id: string) => void; devices: DeviceInventoryItem[];
}) {
  const [detected, setDetected] = useState<Record<string,string>>({});
  const [revision, setRevision] = useState(0);
  const [connectionBusy, setConnectionBusy] = useState(false);
  // Unsaved connection details survive switching equipment; they are never saved implicitly.
  const drafts = useRef<Record<string, AccessDraft | undefined>>({});
  const actions = useGuideActions();
  const studio = useStudio();
  const selected = plan.equipment.find(item => item.id === selectedId);
  if (error) return <p role="alert">{error}</p>;
  if (!loaded || busy) return <p role="status">Loading equipment...</p>;
  if (!selected) return <div className="journey-empty"><h1>Connect equipment</h1><p>Add equipment to your rack before entering its connection details.</p><a href="/setup/guide" className="journey-primary">Choose equipment<ArrowRight size={16} /></a></div>;
  const evidence = selected.device_id ? studio?.devices.find(item => item.deviceId === selected.device_id) : undefined;
  const proven = !!evidence?.proven;
  const isServer = selected.kind === "server" && !!selected.device_id;
  // Connect is connection only; disks and RAID have their own steps after firmware.
  const next = `/setup/check-firmware?device=${encodeURIComponent(selected.device_id || selected.id)}`;
  const continueToFirmware = <Link className={proven ? "sd-primary primary-action" : "primary-action"} to={next}>Continue to firmware<ArrowRight size={17}/></Link>;
  const say = !selected.device_id ? <>{selected.name} is still a rack draft, so save the rack layout before connecting it.</>
    : selected.kind !== "server" ? <>Guided connection checks are for servers; review <em>{selected.name}</em>'s management settings in its own page.</>
    : proven ? <><em>{selected.name}</em> answered a read-only check at {shortTime(evidence!.answeredAt)}, so the next step is its firmware.</>
    : <>Enter the address <em>{selected.name}</em>'s iLO answers on and its sign-in from the pull-out tag, then check the connection.</>;
  return <>
    <Guide eyebrow={<>Your guide · <b>Step 3 of 7</b> · Connect equipment</>}
      say={say}
      reassure="The connection check only reads. Nothing on the server changes."
      actionRef={actions.ref}
      primary={proven ? continueToFirmware : undefined}
      label={(evidence ? (proven ? <><ProvenanceChip kind="proven" time={evidence.answeredAt} />answered a read-only check on this exact target</> : evidence.attention === "failed" ? <><ProvenanceChip kind="danger">last check failed</ProvenanceChip>nothing about this server is proven</> : evidence.attention === "stale" ? <><ProvenanceChip kind="warn">not current</ProvenanceChip>its last answer is too old or for another address</> : <><ProvenanceChip kind="blank">never answered</ProvenanceChip>model, bays and drives stay unknown until it answers</>) : undefined)} />
    <header className="journey-heading"><h1>Connect {selected.name}</h1><p>{selected.kind === "server" ? "Use the current address assigned to the server's iLO management connection. iLO is the server's built-in management chip." : "Save this equipment's management connection before checking readiness."}</p></header>
    <label className="connection-device-picker">Equipment<select aria-label="Equipment to connect" disabled={connectionBusy} value={selected.id} onChange={e => onSelect(e.target.value)}>{plan.equipment.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    <GuideActionProvider value={actions.value}><div id="connection-panel"><div className="connection-layout"><div>
      {!selected.device_id ? <div className="journey-empty"><h2>Save this equipment first</h2><p>This device is still a rack draft.</p><a href="/setup/guide" className="journey-primary">Return to rack layout</a></div>
        : selected.kind === "server" ? <RackServerAccess key={selected.device_id} deviceId={selected.device_id} checkConnection showTask={false} hoistSubmit={!proven}
            draft={drafts.current[selected.device_id]} onDraft={value => { drafts.current[selected.device_id!] = value; }}
            onBusyChange={setConnectionBusy} onChecked={()=>setRevision(r=>r+1)} onDetectedModel={model => setDetected(current => ({...current, [selected.id]:model}))} />
        : <div className="journey-empty"><h2>{selected.kind === "switch" ? "Switch management" : "Equipment connection"}</h2><p>{selected.kind === "switch" ? "Review the switch address and credentials in network settings." : "Connection automation for this equipment is not available in guided setup yet. Keep it in the rack plan and review its inventory details."}</p><a className="journey-primary" href={`${selected.kind === "switch" ? "/network" : "/rack-inventory"}?device=${encodeURIComponent(selected.device_id)}`}>Open connection settings<ArrowRight size={16} /></a></div>}
    </div><aside className="connection-equipment"><HardwareThumbnail item={selected} /><h2>{selected.name}</h2><p>{detected[selected.id] ? `${detected[selected.id]} / Detected by iLO` : `${selected.model || selected.kind} / Saved rack plan`} {detected[selected.id] ? <ProvenanceChip kind="proven" time={new Date().toISOString()}>detected</ProvenanceChip> : <ProvenanceChip kind="saved" />}</p>
      {selected.kind === "server" && !detected[selected.id] && !/Gen\d+/i.test(selected.model) && <p>Generation pending connection check.</p>}
      {detected[selected.id] && /DL360|DL380/i.exec(detected[selected.id])?.[0].toUpperCase() !== /DL360|DL380/i.exec(selected.model)?.[0].toUpperCase() && <p role="alert">Detected hardware differs from the rack selection. Review the equipment family; rack size and placement were not changed.</p>}
      <p>Checks are scoped to this equipment. Saving credentials alone does not verify connectivity.</p></aside></div>

    </div></GuideActionProvider>
    {!proven && <div className="journey-next journey-preview"><Link to={next}>Preview the next step: firmware<ArrowRight size={17} /></Link></div>}
  </>;
}
