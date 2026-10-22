import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { useRef, useState } from "react";
import type { RackPlan } from "./RackPlanner";
import type { DeviceInventoryItem } from "../types";
import { RackServerAccess, type AccessDraft } from "./RackServerAccess";
import { RackSwitchAccess } from "./RackSwitchAccess";
import type { SwitchCheck, SwitchConsoleRead } from "../api";
import { HardwareThumbnail } from "./HardwareThumbnail";
import { Guide, GuideActionProvider, useGuideActions } from "./studio/Guide";
import { PROOF_STALE_AFTER_MS, useStudio } from "./studio/StudioContext";
import { ProvenanceChip, shortTime } from "./studio/ProvenanceChip";

export function RackConnection({ plan, profileId, loaded, busy, error, selectedId, onSelect }: {
  profileId: string;
  plan: RackPlan; loaded: boolean; busy: boolean; error: string; selectedId: string;
  onSelect: (id: string) => void; devices: DeviceInventoryItem[];
}) {
  const [detected, setDetected] = useState<Record<string,string>>({});
  const [revision, setRevision] = useState(0);
  const [connectionBusy, setConnectionBusy] = useState(false);
  const [switchChecks, setSwitchChecks] = useState<Record<string, SwitchCheck | null>>({});
  const [consoleReads, setConsoleReads] = useState<Record<string, SwitchConsoleRead | null>>({});
  // Unsaved connection details survive switching equipment; they are never saved implicitly.
  const drafts = useRef<Record<string, AccessDraft | undefined>>({});
  const actions = useGuideActions();
  const studio = useStudio();
  const selected = plan.equipment.find(item => item.id === selectedId);
  if (error) return <p role="alert">{error}</p>;
  if (!loaded || busy) return <p role="status">Loading equipment...</p>;
  if (!selected) return <div className="journey-empty"><h1>Connect equipment</h1><p>Add equipment to your rack before entering its connection details.</p><a href="/setup/guide" className="journey-primary">Choose equipment<ArrowRight size={16} /></a></div>;
  const evidence = selected.device_id ? studio?.devices.find(item => item.deviceId === selected.device_id) : undefined;
  const isSwitch = selected.kind === "switch" && !!selected.device_id;
  const switchCheck = isSwitch ? switchChecks[selected.device_id!] : null;
  const consoleRead = isSwitch ? consoleReads[selected.device_id!] : null;
  // A switch check ages out like a server's (the same 24-hour rule the rail uses).
  const switchFresh = !!switchCheck && switchCheck.status === "ok" && !!switchCheck.checked_at && Date.now() - Date.parse(switchCheck.checked_at) <= PROOF_STALE_AFTER_MS;
  const proven = isSwitch ? switchFresh : !!evidence?.proven;
  // Connect is connection only; disks and RAID have their own steps after firmware. A switch
  // has no firmware step here, so its next step is the first server's firmware.
  const firstServer = plan.equipment.find(item => item.kind === "server" && item.device_id);
  const nextDevice = isSwitch ? firstServer?.device_id : selected.device_id || selected.id;
  const next = nextDevice ? `/setup/check-firmware?device=${encodeURIComponent(nextDevice)}` : "/setup/check-firmware";
  const continueToFirmware = <Link className={proven ? "sd-primary primary-action" : "primary-action"} to={next}>Next: Check firmware<ArrowRight size={17}/></Link>;
  // A connected server hands off to the kit's switch while it isn't set up; firmware stays one click away.
  const switchWaiting = !isSwitch && proven ? plan.equipment.find(item => item.kind === "switch" && item.device_id
    && !studio?.devices.find(device => device.deviceId === item.device_id)?.proven) : undefined;
  const toSwitch = switchWaiting && <button type="button" className="sd-primary primary-action" onClick={() => onSelect(switchWaiting.id)}>Set up {switchWaiting.name}<ArrowRight size={17}/></button>;
  const say = !selected.device_id ? "Save the rack layout first."
    : isSwitch ? (proven ? <><em>{selected.name}</em> is connected.</>
      : consoleRead?.answered ? <>Fill in the first setup, save, then set up <em>{selected.name}</em>.</>
      : <>Plug in the console cable, then read <em>{selected.name}</em>.</>)
    : selected.kind !== "server" ? "Nothing to connect here."
    : proven && switchWaiting ? <><em>{selected.name}</em> is connected. Now set up <em>{switchWaiting.name}</em>.</>
    : proven ? <><em>{selected.name}</em> is connected.</>
    : <>Enter the iLO address and sign-in, then check the connection.</>;
  return <>
    <Guide eyebrow={<><b>Step 3 of 7</b></>}
      say={say}
      reassure={`The connection check only reads. Nothing on the ${isSwitch ? "switch" : "server"} changes.`}
      actionRef={actions.ref}
      primary={toSwitch || (proven ? continueToFirmware : undefined)}
      label={isSwitch ? (switchCheck ? (proven ? <><ProvenanceChip kind="proven" time={switchCheck.checked_at || undefined} />answered a read-only check at this address</> : <><ProvenanceChip kind="danger">last check failed</ProvenanceChip>network connection not verified</>) : consoleRead?.answered ? <><ProvenanceChip kind="proven" time={consoleRead.checked_at} />answered on the console cable ({consoleRead.port})</> : <><ProvenanceChip kind="blank">never answered</ProvenanceChip>model and ports stay unknown until it answers</>) : (evidence ? (proven ? <><ProvenanceChip kind="proven" time={evidence.answeredAt} />answered a read-only check on this exact target</> : evidence.attention === "failed" ? <><ProvenanceChip kind="danger">last check failed</ProvenanceChip>nothing about this server is proven</> : evidence.attention === "stale" ? <><ProvenanceChip kind="warn">not current</ProvenanceChip>its last answer is too old or for another address</> : <><ProvenanceChip kind="blank">never answered</ProvenanceChip>model, bays and drives stay unknown until it answers</>) : undefined)} />
    <header className="journey-heading"><h1>Connect {selected.name}</h1><p>{selected.kind === "server" ? "Use the current address assigned to the server's iLO management connection. iLO is the server's built-in management chip." : isSwitch ? "A new switch is reached through its console cable first; its management address comes after first setup." : "This equipment has no connection check in guided setup."}</p></header>
    <label className="connection-device-picker">Equipment<select aria-label="Equipment to connect" disabled={connectionBusy} value={selected.id} onChange={e => onSelect(e.target.value)}>{plan.equipment.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    <GuideActionProvider value={actions.value}><div id="connection-panel"><div className="connection-layout"><div>
      {!selected.device_id ? <div className="journey-empty"><h2>Save this equipment first</h2><p>This device is still a rack draft.</p><a href="/setup/guide" className="journey-primary">Return to rack layout</a></div>
        : selected.kind === "server" ? <RackServerAccess key={selected.device_id} deviceId={selected.device_id} checkConnection showTask={false} hoistSubmit={!proven} folded={proven}
            draft={drafts.current[selected.device_id]} onDraft={value => { drafts.current[selected.device_id!] = value; }}
            onBusyChange={setConnectionBusy} onChecked={()=>setRevision(r=>r+1)} onDetectedModel={model => setDetected(current => ({...current, [selected.id]:model}))} />
        : isSwitch ? <RackSwitchAccess key={selected.device_id} profileId={profileId} deviceName={selected.name} deviceId={selected.device_id} hoistSubmit={!proven} plannedPorts={(selected.ports || 0) + (selected.uplink_ports || 0) || undefined}
            onBusyChange={setConnectionBusy} onChecked={check => setSwitchChecks(current => ({ ...current, [selected.device_id!]: check }))}
            onConsole={read => setConsoleReads(current => ({ ...current, [selected.device_id!]: read }))} />
        : <div className="journey-empty"><h2>Nothing to connect</h2><p>This equipment has no connection check in guided setup. It stays in the rack plan.</p></div>}
    </div><aside className="connection-equipment"><HardwareThumbnail item={selected} /><h2>{selected.name}</h2><p>{isSwitch && switchFresh && switchCheck!.model ? <>{switchCheck!.model} / Read from the switch <ProvenanceChip kind="proven" time={switchCheck!.checked_at}>detected</ProvenanceChip></>
        : detected[selected.id] ? <>{detected[selected.id]} / Detected by iLO <ProvenanceChip kind="proven" time={evidence?.answeredAt ?? null}>detected</ProvenanceChip></>
        : <>{selected.model || selected.kind} / Saved rack plan <ProvenanceChip kind="saved" /></>}</p>
      {selected.kind === "server" && !detected[selected.id] && !/Gen\d+/i.test(selected.model) && <p>Generation pending connection check.</p>}
      {detected[selected.id] && /DL360|DL380/i.exec(detected[selected.id])?.[0].toUpperCase() !== /DL360|DL380/i.exec(selected.model)?.[0].toUpperCase() && <p role="alert">Detected hardware differs from the rack selection. Review the equipment family; rack size and placement were not changed.</p>}</aside></div>

    </div></GuideActionProvider>
    {!proven && <div className="journey-next journey-preview"><Link to={next}>Preview the next step: firmware<ArrowRight size={17} /></Link></div>}
  </>;
}
