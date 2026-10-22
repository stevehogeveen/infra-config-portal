import { useEffect, useRef, useState, type CSSProperties } from "react";
import { Trash2, List, Server, Move, Plus } from "lucide-react";
import { EquipmentOverview, EquipmentChecklist } from "./EquipmentOverview";
import { EquipmentStatus } from "./EquipmentStatus";
import { api } from "../api";
import type { DeviceInventoryItem } from "../types";
import { RackServerAccess } from "./RackServerAccess";
import { InventoryWorkflowPanel } from "./InventoryWorkflowPanel";
import { RackConnection } from "./RackConnection";
import { HardwareThumbnail, hardwareName } from "./HardwareThumbnail";
import { hardwareCatalog, serverFamily, RACK_UNIT_HEIGHT, type HardwarePreset } from "../hardwareCatalog";
import { arrangePlacement, resizeRack } from "../rackPlacement";
import { RackPlanFiles } from "./RackPlanFiles";
import { CheckConnections } from "./CheckConnections";
import { HealthLine, IdentifyButton, ResumeCard, useHealth } from "./KitJobs";
import { PreflightButton } from "./Preflight";
import { CableMap } from "./CableMap";
import "../rackPlanner.css";
import "../setupJourney.css";
import { Guide } from "./studio/Guide";
import { useStudio } from "./studio/StudioContext";
import { computeSteps } from "./studio/StudioRail";
import { ProvenanceChip, shortTime } from "./studio/ProvenanceChip";
import { bayNumber, merged } from "./bays";

/** Bays the server's last read-only check found a drive in (cached; reading this never contacts the server). */
function useReadBays(profileId: string, deviceId: string | undefined, active: boolean) {
  const [read, setRead] = useState<{ deviceId: string; bays: number[]; checkedAt: string | null } | null>(null);
  useEffect(() => {
    if (!active || !deviceId) return;
    let cancelled = false;
    api.diskPreparation(profileId, deviceId).then(view => {
      const source = view.drives?.length ? { drives: view.drives, at: view.checked_at } : view.last_read ? { drives: view.last_read.drives, at: view.last_read.checked_at } : null;
      if (cancelled || !source?.drives.length) return;
      const bays = merged(source.drives.filter(drive => !drive.presence || drive.presence === "identified"), []).drives
        .map(drive => Number(bayNumber(drive.location))).filter(bay => Number.isInteger(bay) && bay > 0);
      setRead({ deviceId, bays: [...new Set(bays)].sort((a, b) => a - b), checkedAt: source.at || null });
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [profileId, deviceId, active]);
  return read && read.deviceId === deviceId ? read : null;
}

export type PlannedEquipment = {
  id: string; name: string; kind: "server" | "switch" | "ups" | "pdu" | "storage";
  device_id?: string | null;
  model: string; position: number; height: number; mount: "rack" | "left" | "right";
  ports: 0 | 24 | 48; uplink_ports?: 0 | 4; bay_count: number; occupied_bays: number[];
};
export type RackPlan = { revision: number; rack_units: number; equipment: PlannedEquipment[] };

function hardwareKind(device: DeviceInventoryItem): PlannedEquipment["kind"] {
  return /ilo|server|bmc/i.test(device.device_type) ? "server" : /switch|cisco/i.test(device.device_type) ? "switch" : /ups/i.test(device.device_type) ? "ups" : /pdu/i.test(device.device_type) ? "pdu" : "storage";
}

export function rackPlanError(plan: RackPlan): string | null {
  if (!Number.isInteger(plan.rack_units) || plan.rack_units < 4 || plan.rack_units > 60) return "Rack height must be 4 to 60 U.";
  const occupied = new Set<string>();
  for (const item of plan.equipment) {
    if (!item.name.trim()) return "Each item needs a name.";
    if (!Number.isInteger(item.position) || !Number.isInteger(item.height) || item.position < 1 || item.height < 1 || item.height > 12 || item.position + item.height - 1 > plan.rack_units) return `${item.name} must fit inside the rack (height 1 to 12 U).`;
    if (!Number.isInteger(item.bay_count) || item.bay_count < 0 || item.bay_count > 24) return "Bay capacity must be 0 to 24.";
    const family = item.kind === "server" ? serverFamily(item.model) : null;
    if (family && item.bay_count > family.maxBays) return `${family.name} supports up to ${family.maxBays} front drive bays.`;
    if (family && item.height !== family.height) return `${family.name} requires ${family.height}U of rack space.`;
    if (item.occupied_bays.some((bay) => bay > item.bay_count)) return "Remove drives from the affected bays before reducing capacity.";
    for (let u = item.position; u < item.position + item.height; u++) {
      const key = `${item.mount}:${u}`;
      if (occupied.has(key)) return `${item.name} overlaps another item at U${u}.`;
      occupied.add(key);
    }
  }
  return null;
}

export function RackPlanner({ profileId, profileName = "Standalone Windows kit", devices = [], mode = "equipment" }: { profileId: string; profileName?: string; devices?: DeviceInventoryItem[]; mode?: "rack" | "equipment" | "connect" | "checklist" }) {
  const [plan, setPlan] = useState<RackPlan>({ revision: 0, rack_units: 12, equipment: [] });
  const [rackHeightInput, setRackHeightInput] = useState("12");
  const [saved, setSaved] = useState("");
  const [selectedId, select] = useState("");
  const [placing, setPlacing] = useState<PlannedEquipment | null>(null);
  // Tap targets must not cover the native drag source while a mouse drag starts.
  const [dragging, setDragging] = useState(false);
  const [dropSlot, setDropSlot] = useState<number | null>(null);
  const [busy, setBusy] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [requestedTab, setTab] = useState(mode === "equipment" ? "equipment" : "overview");
  const [view, setView] = useState(mode === "checklist" ? "list" : "rack");
  // My Rack opens as a status view; Edit rack turns on the same shelf, drag and move as Add equipment.
  const [editing, setEditing] = useState(mode === "equipment");
  const tab = mode === "rack" && !editing ? "overview" : requestedTab;
  const [connectionHosts, setConnectionHosts] = useState<Record<string, string>>({});
  const selectedRef = useRef<HTMLButtonElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const [unitHeight, setUnitHeight] = useState(RACK_UNIT_HEIGHT);
  const selected = plan.equipment.find((item) => item.id === selectedId);
  const selectedHasDrives = selected?.kind === "server" || selected?.kind === "storage";
  const readBays = useReadBays(profileId, selected?.kind === "server" ? selected.device_id ?? undefined : undefined, tab === "drives");
  const dirty = JSON.stringify(plan) !== saved || plan.equipment.some((item) => !item.device_id);
  const invalid = rackPlanError(plan);
  // A plan that could not be loaded is unknown, not empty: show only the error, never an empty rack.
  const failedLoad = !loaded && !!error;
  const draftKey = `rack-workbench-draft-v1:${profileId}`;
  const studio = useStudio();
  const health = useHealth(plan.equipment.filter(item => item.kind === "server" && item.device_id).map(item => item.device_id!), studio?.devices);
  // Keep the rail, evidence drawer and this rack pointing at the same piece of equipment.
  useEffect(() => {
    if (studio?.selectedId && studio.selectedId !== selectedId && plan.equipment.some(item => item.id === studio.selectedId)) select(studio.selectedId);
  }, [studio?.selectedId]);
  useEffect(() => {
    if (selectedId && studio && studio.selectedId !== selectedId) studio.select(selectedId);
  }, [selectedId]);
  const evidenceFor = (item: PlannedEquipment) => item.device_id ? studio?.devices.find(entry => entry.deviceId === item.device_id) : undefined;

  async function load(discardDraft = false) {
    setBusy(true); setError("");
    try {
      let next = await api.rackPlan(profileId);
      setSaved(JSON.stringify(next));
      if (next.revision === 0 && !next.equipment.length) {
        let used = 0;
        const physical = devices.filter((device) => !/esxi|vcenter|vcsa/i.test(device.device_type));
        next.rack_units = Math.min(60, Math.max(12, physical.length * 2));
        next.equipment = physical.map((device) => {
          const kind = hardwareKind(device);
          const height = kind === "switch" || kind === "pdu" ? 1 : 2;
          used += height;
          return { id: device.id, device_id: device.id, name: device.display_name, kind, model: "", position: next.rack_units - used + 1, height, mount: "rack", ports: kind === "switch" ? 24 : 0, bay_count: 0, occupied_bays: [] };
        });
      }
      let recovered = false;
      try {
        if (discardDraft) localStorage.removeItem(draftKey);
        const raw = localStorage.getItem(draftKey);
        if (raw) {
          const draft = JSON.parse(raw) as RackPlan;
          if (typeof draft.revision === "number" && typeof draft.rack_units === "number" && Array.isArray(draft.equipment) && draft.equipment.every((item) => item && typeof item.id === "string" && typeof item.name === "string" && typeof item.model === "string" && typeof item.position === "number" && typeof item.height === "number" && typeof item.bay_count === "number" && Array.isArray(item.occupied_bays) && ["server", "switch", "ups", "pdu", "storage"].includes(item.kind))) {
            next = draft; recovered = true;
          }
        }
      } catch { setError("Browser draft storage is unavailable. Save to the server before leaving."); }
      const requestedDevice = new URLSearchParams(window.location.search).get("device");
      next = { ...next, equipment: next.equipment.map(item => ({ ...item, name: hardwareName(item.name, item.kind) })) };
      const requested = requestedDevice ? next.equipment.find((item) => item.device_id === requestedDevice || item.id === requestedDevice) : null;
      setPlan(next); setLoaded(true); select(requested?.id ?? next.equipment[0]?.id ?? ""); setMessage(recovered ? "Recovered your rack draft. Save a copy to keep the active kit." : "");
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }
  useEffect(() => { void load(); }, [profileId]);
  useEffect(() => { setRackHeightInput(String(plan.rack_units)); }, [plan.rack_units]);
  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;
    const resize = () => setUnitHeight(Math.max(24, Math.min(RACK_UNIT_HEIGHT, Math.round((frame.clientWidth - 21) * RACK_UNIT_HEIGHT / 610))));
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(frame);
    return () => observer.disconnect();
  }, [view, mode]);
  useEffect(() => {
    if (!loaded) return;
    try {
      if (dirty) localStorage.setItem(draftKey, JSON.stringify(plan));
      else localStorage.removeItem(draftKey);
    } catch { setError("Browser draft storage is unavailable. Save to the server before leaving."); }
  }, [loaded, plan, dirty, draftKey]);
  useEffect(() => {
    const item = selectedRef.current;
    const viewport = item?.closest<HTMLElement>(".rack-plan-scroll");
    if (!item || !viewport) return;
    // Reveal the chassis inside the rack without scrolling the whole page.
    const reveal = () => {
      const top = item.getBoundingClientRect().top - viewport.getBoundingClientRect().top + viewport.scrollTop;
      if (top < viewport.scrollTop) viewport.scrollTop = Math.max(0, top - 20);
      else if (top + item.clientHeight > viewport.scrollTop + viewport.clientHeight) viewport.scrollTop = top + item.clientHeight - viewport.clientHeight + 20;
    };
    reveal();
    const observer = new ResizeObserver(reveal);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, [selectedId, view, selected?.position, selected?.height, plan.rack_units, unitHeight]);

  function update(item: Partial<PlannedEquipment>) {
    setMessage("");
    setPlan((current) => ({ ...current, equipment: current.equipment.map((entry) => entry.id === selectedId ? { ...entry, ...item } : entry) }));
  }
  function changeRackHeight() {
    if (Number(rackHeightInput) === plan.rack_units) return;
    const result = resizeRack(plan, Number(rackHeightInput));
    if (!result.plan) {
      setError(result.error!); setRackHeightInput(String(plan.rack_units)); return;
    }
    setPlan(result.plan); setError(""); setPlacing(null); setDropSlot(null);
    setMessage(`Rack resized to ${result.plan.rack_units}U.${result.moved.length ? ` ${result.moved.length} item(s) moved down to fit.` : ""}`);
  }
  const [showShelf, setShowShelf] = useState(false);
  /** A new kit's usual start: one DL360 at U1 and one Cisco switch at U3, as an unsaved draft. */
  function startKit() {
    const server = { ...newEquipment("server", undefined, hardwareCatalog.find(entry => entry.key === "dl360")!), position: 1 };
    const sw = { ...newEquipment("switch", undefined, hardwareCatalog.find(entry => entry.key === "c9300")!), position: Math.min(3, Math.max(2, plan.rack_units)) };
    setPlan({ ...plan, equipment: [server, sw] });
    select(server.id); setView("rack");
  }
  function newEquipment(kind: PlannedEquipment["kind"], sourceDevice?: DeviceInventoryItem, preset = hardwareCatalog.find(entry => entry.kind === kind)!): PlannedEquipment {
    if (sourceDevice) sourceDevice = { ...sourceDevice, display_name: hardwareName(sourceDevice.display_name, kind) };
    return { id: sourceDevice?.id ?? crypto.randomUUID(), device_id: sourceDevice?.id, kind, name: sourceDevice?.display_name ?? `${preset.label} ${plan.equipment.length + 1}`, model: sourceDevice ? "" : preset.model, position: 1, height: sourceDevice ? (kind === "server" || kind === "storage" || kind === "ups" ? 2 : 1) : preset.height, mount: "rack", ports: kind === "switch" ? 24 : 0, uplink_ports: sourceDevice ? 0 : preset.uplink_ports, bay_count: sourceDevice ? 0 : preset.bay_count, occupied_bays: [] };
  }
  function presetPreview(preset: HardwarePreset): PlannedEquipment {
    return { ...preset, id: preset.key, name: preset.label, position: 1, mount: "rack", occupied_bays: Array.from({ length: preset.bay_count }, (_, index) => index + 1) };
  }
  function placement(topSlot: number) {
    if (!placing) return null;
    return arrangePlacement(plan, placing, topSlot);
  }
  function place(topSlot: number) {
    if (!editing || busy || !loaded || !placing) return;
    const result = placement(topSlot)!;
    const next = result.plan;
    const problem = result.error || (next ? rackPlanError(next) : "Placement unavailable.");
    if (problem) { setError(problem); setDropSlot(null); return; }
    setPlan(next!); select(placing.id); setTab("equipment"); setError(""); setMessage(`${placing.name} placed at U${topSlot - placing.height + 1}.${result.moved.length ? ` Moved ${result.moved.map(item => `${item.name} to U${item.position}`).join(", ")}.` : ""}`); setPlacing(null); setDropSlot(null);
  }
  function removeItem(item: PlannedEquipment) {
    if (busy || !editing || !plan.equipment.some(entry => entry.id === item.id)) return;
    if (window.confirm(`Remove ${item.name} from the rack? Existing connection records will be retained.`)) {
      setPlan(current => ({ ...current, equipment: current.equipment.filter(entry => entry.id !== item.id) }));
      if (selectedId === item.id) select("");
      setMessage(`${item.name} removed from the rack. Connection records retained.`); setError("");
    }
    setPlacing(null); setDropSlot(null);
  }
  // Pointer dragging (mouse, pen and touch): the item follows the pointer, keeps the point where it
  // was grabbed, previews its slot live and settles with a short animation. A tap still selects.
  type Drag = { item: PlannedEquipment; fromRack: boolean; startX: number; startY: number; grab: number; moved: boolean };
  const drag = useRef<Drag | null>(null);
  const suppressClick = useRef(false);
  const removeZoneRef = useRef<HTMLButtonElement>(null);
  const [ghostTop, setGhostTop] = useState<number | null>(null);
  const [overRemove, setOverRemove] = useState(false);
  const latest = useRef({ place, removeItem, plan, unitHeight, dropSlot });
  latest.current = { place, removeItem, plan, unitHeight, dropSlot };
  function beginDrag(event: React.PointerEvent, item: PlannedEquipment, fromRack: boolean) {
    if (!editing || busy || !loaded || event.button !== 0) return;
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    drag.current = { item, fromRack, startX: event.clientX, startY: event.clientY, grab: fromRack ? event.clientY - rect.top : unitHeight / 2, moved: false };
  }
  useEffect(() => {
    function slotFor(clientY: number, current: Drag) {
      const frame = frameRef.current;
      if (!frame) return null;
      const { plan: p, unitHeight: unit } = latest.current;
      const top = frame.getBoundingClientRect().top;
      const itemTopIndex = Math.round((clientY - current.grab - top) / unit);
      return Math.max(current.item.height, Math.min(p.rack_units, p.rack_units - itemTopIndex));
    }
    function move(event: PointerEvent) {
      const current = drag.current;
      if (!current) return;
      if (!current.moved) {
        if (Math.hypot(event.clientX - current.startX, event.clientY - current.startY) < 5) return;
        current.moved = true;
        setPlacing(current.item); setDragging(true); setView("rack");
      }
      event.preventDefault();
      const frame = frameRef.current?.getBoundingClientRect();
      const zone = removeZoneRef.current?.getBoundingClientRect();
      const onZone = !!zone && current.fromRack && event.clientX >= zone.left && event.clientX <= zone.right && event.clientY >= zone.top && event.clientY <= zone.bottom;
      setOverRemove(onZone);
      const inside = !!frame && event.clientX >= frame.left - 80 && event.clientX <= frame.right + 80 && event.clientY >= frame.top - latest.current.unitHeight && event.clientY <= frame.bottom + latest.current.unitHeight;
      if (inside && !onZone) {
        // Kept inside the rack: a ghost past its edge would grow the scroll area and shift the rack.
        const maxTop = frame!.height - current.item.height * latest.current.unitHeight;
        setGhostTop(Math.max(0, Math.min(maxTop, event.clientY - frame!.top - current.grab)));
        setDropSlot(slotFor(event.clientY, current));
      } else { setGhostTop(null); setDropSlot(null); }
    }
    function end(event: PointerEvent) {
      const current = drag.current;
      drag.current = null;
      if (!current?.moved) return;
      suppressClick.current = true;
      setTimeout(() => { suppressClick.current = false; }, 0);
      const { place: drop, removeItem: remove, dropSlot: slot } = latest.current;
      const zone = removeZoneRef.current?.getBoundingClientRect();
      const onZone = !!zone && current.fromRack && event.clientX >= zone.left && event.clientX <= zone.right && event.clientY >= zone.top && event.clientY <= zone.bottom;
      setGhostTop(null); setOverRemove(false); setDragging(false);
      if (event.type === "pointercancel") { setPlacing(null); setDropSlot(null); return; }
      if (onZone) remove(current.item);
      else if (slot !== null) drop(slot);
      else { setPlacing(null); setDropSlot(null); }
    }
    function key(event: KeyboardEvent) {
      if (event.key !== "Escape" || !drag.current?.moved) return;
      drag.current = null; setGhostTop(null); setOverRemove(false); setDragging(false); setPlacing(null); setDropSlot(null);
    }
    window.addEventListener("pointermove", move, { passive: false });
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
    window.addEventListener("keydown", key);
    return () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", end); window.removeEventListener("pointercancel", end); window.removeEventListener("keydown", key); };
  }, []);
  const preview = dropSlot !== null ? placement(dropSlot) : null;
  const dropProblem = preview ? preview.error || (preview.plan ? rackPlanError(preview.plan) : null) : null;
  async function save() {
    const resized = Number(rackHeightInput) === plan.rack_units ? { plan, error: null } : resizeRack(plan, Number(rackHeightInput));
    if (!resized.plan) { setError(resized.error!); setRackHeightInput(String(plan.rack_units)); return false; }
    setBusy(true); setError(""); setMessage("");
    try {
      const next = await api.saveRackPlan(profileId, resized.plan);
      setPlan(next); setSaved(JSON.stringify(next)); setMessage("Rack plan saved. No hardware changed.");
      return true;
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); return false; }
    finally { setBusy(false); }
  }
  if (mode === "connect") return <section className="rack-planner"><RackConnection plan={plan} profileId={profileId} loaded={loaded} busy={busy} error={error} selectedId={selectedId} onSelect={select} devices={devices} /></section>;
  return <section className={`rack-planner ${editing ? "is-editing" : "is-viewing"}`} aria-label="Rack planner" onDragStartCapture={() => setDragging(true)} onDragEndCapture={() => setDragging(false)} onDropCapture={() => setDragging(false)}>
    {mode === "equipment" && <Guide
      eyebrow={<><b>Step 1 of 7</b></>}
      say={placing ? <>Drop <em>{placing.name}</em> on a slot.</>
        : !plan.equipment.length ? "Add your equipment."
        : dirty ? "Save the rack layout."
        : "Rack layout saved."}
      reassure={placing ? "Nothing is placed until you choose a slot. No hardware is touched." : "Planning and saving change your plan only. No hardware is touched."}
      primary={!placing && !dirty && plan.equipment.length > 0 ? <a href="/setup/defaults" className="sd-primary">Next: Network settings</a> : undefined}
      aside={placing ? "Cancel placement puts it back on the shelf." : dirty ? "Save with Save a copy below. It also saves the active kit." : !plan.equipment.length ? "Choose hardware from the shelf below." : undefined}
      label={<><ProvenanceChip kind="saved" />Everything on this page is your plan. Nobody has checked it against the machines.</>} />}
    {mode === "rack" && editing && <Guide
      eyebrow={<><b>My Rack</b> · editing</>}
      say={placing ? <>Drop <em>{placing.name}</em> on a slot.</>
        : dirty ? "Save your changes."
        : "Drag equipment to add or move it."}
      reassure="Editing changes your plan only. No hardware is touched."
      aside={placing ? "Cancel placement puts it back on the shelf." : dirty ? "Save changes is below the rack." : undefined}
      label={<><ProvenanceChip kind="saved" />Everything you change here is your plan. Nobody has checked it against the machines.</>} />}
    {mode === "rack" && !editing && (() => {
      const steps = computeSteps(studio);
      const now = steps.find(step => step.state === "now");
      const index = now ? steps.indexOf(now) : -1;
      const chosen = selected ? evidenceFor(selected) : undefined;
      const waitingSwitch = now?.path === "/setup/connect" ? studio?.devices.find(item => item.kind === "switch" && item.deviceId && !item.proven) : undefined;
      return <Guide
        eyebrow={now ? <><b>Step {index + 1} of 7</b></> : <><b>My Rack</b></>}
        say={steps.every(step => step.state === "done") ? "Your kit is built."
          : waitingSwitch ? <>Set up <em>{waitingSwitch.name}</em>.</>
          : now ? <>{now.name}.</>
          : "Continue setup."}
        reassure="Opening this page contacts nothing. Check connections only reads; Edit rack changes your saved plan only."
        primary={steps.every(step => step.state === "done") ? <a className="sd-primary" href="/simple?report=1">Review build report</a>
          : waitingSwitch ? <a className="sd-primary" href={`/setup/connect?device=${encodeURIComponent(waitingSwitch.deviceId!)}`}>Set up {waitingSwitch.name}</a>
          : <a className="sd-primary" href={now?.path ?? "/setup/guide"}>{now ? `Go to ${now.name}` : "Continue setup"}</a>}
        aside={now ? now.note : undefined} />;
    })()}
    {mode === "rack" && !editing && <ResumeCard />}
    <header className="rack-plan-toolbar">
      <div><h1>{mode === "equipment" ? "Choose equipment & rack layout" : mode === "checklist" ? "Equipment checklist" : "My Rack"}</h1><span>{profileName}</span></div>
      {!editing && mode === "rack" && <div className="rack-tools"><CheckConnections equipment={plan.equipment} /><PreflightButton profileId={profileId} /></div>}
      {!editing && mode === "rack" && selected?.kind === "server" && selected.device_id && <IdentifyButton key={selected.device_id} deviceId={selected.device_id} />}
      {!editing && <button type="button" className={mode === "rack" ? "rack-edit-start" : undefined} disabled={!loaded} onClick={() => { setEditing(true); setTab("equipment"); }}>{mode === "rack" ? <><Move size={16} />Edit rack</> : "Edit equipment"}</button>}
      <div className="rack-edit-controls" hidden={!editing}>
      <label>Rack height (U)<input aria-label="Rack height" type="number" min="4" max="60" value={rackHeightInput} disabled={busy || !loaded} onChange={(e) => setRackHeightInput(e.target.value)} onBlur={event => {
        // Let the footer click finish before resizing moves its target.
        if (!event.relatedTarget?.closest(".rack-file-actions")) changeRackHeight();
      }} onKeyDown={event => { if (event.key === "Enter") { event.preventDefault(); event.currentTarget.blur(); } }} /></label>
      {mode !== "equipment" && <button type="button" onClick={() => { setEditing(false); setTab("overview"); }}>Done editing</button>}
      </div>
    </header>
    {(error || invalid) && <p role="alert">{error || invalid}</p>}
    {message && <p role="status">{message}</p>}
    {editing && !plan.equipment.length && loaded && <div className="rack-starter">
      <button type="button" className="primary-action" disabled={busy} onClick={startKit}>Start with an HPE DL360 server and a Cisco switch</button>
      <span>Or pick hardware below.</span>
    </div>}
    {editing && mode === "equipment" && plan.equipment.length > 0 && !showShelf && !placing && <div className="rack-shelf-toggle">
      <button type="button" className="secondary-action" disabled={busy || !loaded} onClick={() => setShowShelf(true)}><Plus size={16} />Add equipment</button>
    </div>}
    {editing && (mode !== "equipment" || !plan.equipment.length || showShelf || !!placing) && <><fieldset className="hardware-picker drag-palette" disabled={busy || !loaded}><legend>Choose hardware</legend>{hardwareCatalog.map(preset => <button type="button" key={preset.key} aria-label={`Place ${preset.label}`} onPointerDown={event => { setShowShelf(true); beginDrag(event, newEquipment(preset.kind, undefined, preset), false); }} onClick={() => { setShowShelf(true); if (suppressClick.current) return; setPlacing(newEquipment(preset.kind, undefined, preset)); setView("rack"); }}><HardwareThumbnail item={presetPreview(preset)} /><span className="hw-catalog-label"><strong>{preset.label}</strong><small>{preset.detail}</small></span></button>)}</fieldset>
      <div className="rack-placement-bar" aria-live="polite">{placing ? <><strong>{placing.name} / {placing.height}U</strong><button type="button" onClick={() => { setPlacing(null); setDropSlot(null); }}>Cancel placement</button></> : <span>Drag hardware to a rack slot, or select an image and then a slot.</span>}</div>
      {/* Shown only while a rack item is being dragged; the equipment panel has its own Remove. */}
      <button ref={removeZoneRef} type="button" hidden={!(dragging && placing && plan.equipment.some(item => item.id === placing.id))} className={`rack-remove-zone ${overRemove ? "is-over" : ""}`} aria-label="Remove from rack" disabled={busy || !loaded} onDragOver={event => { if (placing && plan.equipment.some(item => item.id === placing.id)) { event.preventDefault(); setDropSlot(null); } }} onDrop={event => { event.preventDefault(); if (placing) removeItem(placing); }} onClick={() => { if (placing) removeItem(placing); }}><Trash2 size={20} />Remove from rack<span>Drop equipment here; saved connections are kept</span></button>
    </>}
    {!failedLoad && <>
    {dirty && <p className="workbench-plan-note">Draft kept in this browser; not saved yet.</p>}
    <div className="workbench-view-bar"><h2>Your equipment <span>{plan.equipment.length}</span></h2><div role="group" aria-label="Equipment view"><button type="button" aria-pressed={view === "rack"} onClick={() => setView("rack")}><Server size={16} />Rack</button><button type="button" aria-pressed={view === "list"} onClick={() => setView("list")}><List size={16} />List</button></div></div>
    <div className="rack-plan-workspace">
      {view === "list" ? <EquipmentChecklist readOnly={mode === "rack" && !editing} items={plan.equipment} selectedId={selectedId} onSelect={(id) => { select(id); setTab("overview"); }} /> : <div className="rack-plan-scroll" aria-label="Planned rack elevation">
        <div className="sd-rackrow">
        <div className="sd-rack" style={{ "--sd-u": `${unitHeight}px` } as CSSProperties}>
        <span className="sd-dimrule" aria-hidden="true"><span>{plan.rack_units}U · {(plan.rack_units * 44.45).toFixed(1)} mm</span></span>
        <div className="sd-rk-cap sd-metal" aria-hidden="true"><span><i />LAB BUILDER · {plan.rack_units}U</span></div>
        <div className="sd-rk-body">
        <div className="sd-rk-rail l" aria-hidden="true" style={{ height: Math.max(4, Math.min(60, plan.rack_units || 4)) * unitHeight }}>{Array.from({ length: Math.max(4, Math.min(60, plan.rack_units || 4)) }, (_, index) => <span key={index} style={{ top: index * unitHeight, height: unitHeight }}>{plan.rack_units - index}</span>)}</div>
        <div ref={frameRef} className="rack-plan-frame" style={{ height: Math.max(4, Math.min(60, plan.rack_units || 4)) * unitHeight }}>
          {Array.from({ length: Math.max(4, Math.min(60, plan.rack_units || 4)) }, (_, index) => <div className="rack-plan-unit" key={index} style={{ top: index * unitHeight, height: unitHeight }}><span>U{plan.rack_units - index}</span>{placing && editing && !dragging && <button type="button" className="rack-slot-target" aria-label={`Place at U${plan.rack_units - index}`} onClick={() => place(plan.rack_units - index)} onFocus={() => setDropSlot(plan.rack_units - index)}>U{plan.rack_units - index}</button>}</div>)}
          {dragging && placing && ghostTop !== null && <div className={`rack-plan-equipment hw-equipment rack-drag-ghost kind-${placing.kind} mount-${placing.mount}`} aria-hidden="true" style={{ top: ghostTop, height: placing.height * unitHeight - 4, "--rack-device-height": `${placing.height * unitHeight - 4}px` } as CSSProperties}><HardwareThumbnail item={placing} rack /></div>}
          {placing && dropSlot !== null && <div className={`rack-drop-preview ${dropProblem ? "invalid" : ""}`} style={{ top: (plan.rack_units - dropSlot) * unitHeight, height: placing.height * unitHeight }}><span>{dropProblem || `${placing.name} / U${dropSlot - placing.height + 1}-${dropSlot}${preview?.moved.length ? ` / ${preview.moved.length} existing item(s) will move` : ""}`}</span></div>}
          {plan.equipment.map((item) => <button ref={selectedId === item.id ? selectedRef : undefined} onPointerDown={event => beginDrag(event, item, true)} type="button" key={item.id} className={`rack-plan-equipment hw-equipment kind-${item.kind} mount-${item.mount} ${selectedId === item.id ? "selected" : ""} ${editing ? "is-movable" : ""} ${dragging && placing?.id === item.id ? "is-held" : ""}`} style={{ top: (plan.rack_units - item.position - item.height + 1) * unitHeight + 2, height: item.height * unitHeight - 4, "--rack-device-height": `${item.height * unitHeight - 4}px` } as CSSProperties} onClick={() => { if (!suppressClick.current) select(item.id); }} aria-label={`Select ${item.name}`} title={`${item.name} / ${item.model || item.kind} / Planned`}>
            <span className="hw-rack-label"><strong>{item.name}</strong><span>{item.model || item.kind.toUpperCase()}</span></span>
            <HardwareThumbnail item={item} rack />
            {item.mount === "rack" && <><span className="sd-cn tl" /><span className="sd-cn tr" /><span className="sd-cn bl" /><span className="sd-cn br" />
              {mode === "rack" && <span className={`sd-uled ${evidenceFor(item)?.proven ? "ok" : ""}`} />}<span className="sd-plate">{item.name}</span></>}
          </button>)}
        </div>
        <div className="sd-rk-rail r" aria-hidden="true" style={{ height: Math.max(4, Math.min(60, plan.rack_units || 4)) * unitHeight }} />
        </div>
        <div className="sd-rk-base sd-metal" aria-hidden="true"><span>FRONT</span></div>
        </div>
        <div className="sd-tags" aria-hidden="true" style={{ height: Math.max(4, Math.min(60, plan.rack_units || 4)) * unitHeight }}>
          {plan.equipment.filter(item => item.mount === "rack").map(item => {
            const evidence = evidenceFor(item);
            const span = item.height > 1 ? `U${item.position}–U${item.position + item.height - 1}` : `U${item.position}`;
            return <span key={item.id} className={`sd-callout ${selectedId === item.id ? "sel" : ""}`} style={{ top: (plan.rack_units - item.position - item.height + 1) * unitHeight, height: item.height * unitHeight }} onClick={() => select(item.id)}>
              <b>{item.name}</b>
              <small>{editing ? (selectedId === item.id ? "Selected · editing" : `${span} · ${item.kind}`)
                : evidence?.proven ? <ProvenanceChip kind="proven" time={evidence.answeredAt}>verified</ProvenanceChip>
                : <><i className="sd-pill-key" />{!item.device_id ? "draft, not saved" : evidence?.attention === "failed" ? "last check failed" : evidence?.attention === "stale" ? "check is old" : item.kind === "server" || item.kind === "switch" ? "not checked yet" : `${item.kind} · nothing to check`}</>}</small>
              {!editing && item.kind === "server" && item.device_id && <HealthLine health={health[item.device_id]} />}
            </span>;
          })}
          {!editing && (() => {
            const taken = new Set<number>();
            plan.equipment.filter(item => item.mount === "rack").forEach(item => { for (let u = item.position; u < item.position + item.height; u++) taken.add(u); });
            const runs: Array<[number, number]> = [];
            for (let u = plan.rack_units; u >= 1; u--) { if (taken.has(u)) continue; const last = runs[runs.length - 1]; if (last && last[1] === u + 1) last[1] = u; else runs.push([u, u]); }
            return runs.map(([hi, lo]) => <span key={hi} className="sd-callout sd-free" style={{ top: (plan.rack_units - hi) * unitHeight, height: (hi - lo + 1) * unitHeight }}><b>{hi === lo ? `U${lo}` : `U${lo}–U${hi}`} · empty</b><small>{hi - lo + 1} U free</small></span>);
          })()}
        </div>
        </div>
        {mode === "rack" && <div className="sd-legend"><span><i className="sd-led ok" />connection verified, with its time</span><span><i className="sd-pill-key" />not answered or no check</span><span>Drive bays drawn are your saved plan, not a drive read.</span></div>}
        {mode === "rack" && !editing && <CableMap profileId={profileId} />}
      </div>}
      <aside className="rack-plan-inspector">
        {!selected ? <><h2>Equipment plan</h2><p>{plan.equipment.length ? "No equipment selected." : "No equipment in this plan yet."}</p><p>Inventory and credentials remain separate.</p></> : <>
          <h2>{selected.name}</h2><p className="rack-plan-provenance">{selected.model || (selected.kind === "server" ? "HPE server" : selected.kind)} / Saved rack plan <ProvenanceChip kind="saved" />{(() => { const ev = evidenceFor(selected); return ev?.proven ? <> <ProvenanceChip kind="proven" time={ev.answeredAt}>answered</ProvenanceChip></> : null; })()}</p>
          {editing && <button type="button" className="rack-move-action" disabled={busy} onClick={() => { setPlacing(selected); setView("rack"); }}><Move size={16} />Move equipment</button>}
          {editing && <div className="workbench-inspector-tabs" role="tablist" aria-label="Equipment settings">
            {(["overview", "equipment", ...(selected.kind === "server" ? ["access", "drives", "checks"] : selected.kind === "storage" ? ["drives"] : [])]).map((name) => <button key={name} type="button" role="tab" aria-selected={tab === name} onClick={() => setTab(name)}>{name === "equipment" ? "Edit equipment" : name[0].toUpperCase() + name.slice(1)}</button>)}
          </div>}
          {mode === "rack" && !editing ? <EquipmentStatus key={JSON.stringify([selected.id, selected.device_id])} item={selected} device={devices.find(device => device.id === selected.device_id)} /> : tab === "overview" && <EquipmentOverview item={selected} busy={busy} invalid={Boolean(invalid)} onSave={() => void save()} onConnect={() => { if (mode === "equipment") setTab("access"); else window.location.assign(`/setup/connect?device=${encodeURIComponent(selected.device_id || selected.id)}`); }} onEdit={() => { setEditing(true); setTab("equipment"); }} />}
          {tab === "access" && selected.kind === "server" && <ol className="connection-steps" aria-label="Connection steps"><li aria-current="step">1. Enter details</li><li>2. Save connection</li><li>3. Open Checks</li></ol>}
          {tab === "access" && selected.kind === "server" && (selected.device_id ? <RackServerAccess key={selected.device_id} deviceId={selected.device_id} onContinue={(host) => { setConnectionHosts(current => ({ ...current, [selected.device_id!]: host })); setTab("checks"); }} /> : <p>Save the rack to create this server's hardware record, then enter its iLO connection.</p>)}
          {tab === "checks" && selected.kind === "server" && (selected.device_id ? <InventoryWorkflowPanel key={selected.device_id} deviceId={selected.device_id} currentHost={connectionHosts[selected.device_id] ?? devices.find((device) => device.id === selected.device_id)?.host ?? ""} /> : <p>Save this server and configure its connection before running checks.</p>)}
          <div hidden={tab === "overview" || (selectedHasDrives && tab !== "equipment" && tab !== "drives")}>
          <fieldset disabled={busy || !loaded}>
          <div className="workbench-equipment-fields" hidden={selectedHasDrives && tab === "drives"}>
          <label>Name<input aria-label="Equipment name" value={selected.name} maxLength={120} onChange={(e) => update({ name: e.target.value })} /></label>
          <label>Model<input aria-label="Equipment model" readOnly={selected.kind === "server"} list="rack-models" maxLength={120} value={selected.model} onChange={(e) => { const family = selected.kind === "server" ? serverFamily(e.target.value) : null; update({ model: e.target.value, ...(family ? { height: family.height } : {}) }); }} /></label>
          {selected.kind === "server" && !/Gen\d+/i.test(selected.model) && <p>Generation pending connection check.</p>}
          <datalist id="rack-models">{(selected.kind === "server" ? [] : selected.kind === "switch" ? ["Catalyst 9300"] : selected.kind === "ups" ? ["Rackmount UPS", "Eaton 5P 1550"] : selected.kind === "storage" ? ["NetApp 24 SFF"] : []).map((model) => <option key={model} value={model} />)}</datalist>
          <div className="rack-plan-pair"><label>Starting position (U)<input aria-label="Bottom slot" type="number" min="1" max={plan.rack_units} value={selected.position} onChange={(e) => update({ position: Number(e.target.value) })} /></label><label>Height (U)<input aria-label="Equipment height" type="number" min="1" max="12" value={selected.height} onChange={(e) => update({ height: Number(e.target.value) })} /></label></div>
          {selected.kind === "pdu" && <label>Mount<select aria-label="PDU mount" value={selected.mount} onChange={(e) => update({ mount: e.target.value as PlannedEquipment["mount"] })}><option value="rack">Rack units</option><option value="left">Left side (0U)</option><option value="right">Right side (0U)</option></select></label>}
          {selected.kind === "switch" && <label>Ports<select aria-label="Switch ports" value={selected.ports} onChange={(e) => update({ ports: Number(e.target.value) as 24 | 48 })}><option value="24">24 ports</option><option value="48">48 ports</option></select></label>}
          {selected.kind === "switch" && <label>SFP uplink slots<select aria-label="SFP uplink slots" value={selected.uplink_ports || 0} onChange={(e) => update({ uplink_ports: Number(e.target.value) as 0 | 4 })}><option value="0">Blank module</option><option value="4">4 SFP slots</option></select></label>}
          </div>
          {selectedHasDrives && tab === "drives" && <>
            <label>Drive bay capacity<input aria-label="Drive bay capacity" type="number" min="0" max={selected.kind === "server" ? serverFamily(selected.model)?.maxBays || 24 : 24} value={selected.bay_count} onChange={(e) => update({ bay_count: Number(e.target.value) })} /></label>
            <h3>{selected.occupied_bays.length} drives / {selected.bay_count} bays</h3>
            <div className="rack-plan-bay-editor">{Array.from({ length: Math.max(0, Math.min(24, Math.max(selected.bay_count || 0, ...(readBays?.bays ?? [])))) }, (_, index) => { const bay = index + 1; const installed = selected.occupied_bays.includes(bay); const found = readBays ? readBays.bays.includes(bay) : null; const note = found === null ? (installed ? "Drive" : "Empty") : installed && found ? "Drive" : installed ? "Not found" : found ? "Found" : "Empty"; return <button type="button" key={bay} className={found === null || installed === found ? undefined : found ? "is-found" : "is-missing"} aria-label={`Bay ${bay}${found === null ? "" : installed === found ? "" : found ? ", drive found but not planned" : ", planned but no drive found"}`} aria-pressed={installed} onClick={() => update({ occupied_bays: installed ? selected.occupied_bays.filter((value) => value !== bay) : [...selected.occupied_bays, bay].sort((a, b) => a - b) })}><span>{bay}</span><small>{note}</small></button>; })}</div>
            {readBays && <ReadBaysNote planned={selected.occupied_bays} read={readBays} onMatch={() => update({ occupied_bays: readBays.bays, bay_count: Math.max(selected.bay_count || 0, ...readBays.bays) })} />}
            {selected.occupied_bays.some((bay) => bay > selected.bay_count) && <button type="button" onClick={() => update({ occupied_bays: selected.occupied_bays.filter((bay) => bay <= selected.bay_count) })}>Remove drives outside capacity</button>}
            {!readBays && <p>{selected.kind === "server" ? "Occupancy is planned until the server answers a connection check; then the drives it reports show here too." : "Drive occupancy is planned, not detected."}</p>}
          </>}
          <button type="button" className="rack-plan-remove" onClick={() => { if (window.confirm(`Remove ${selected.name} from the rack? Existing connection records will be retained.`)) { setPlan({ ...plan, equipment: plan.equipment.filter((item) => item.id !== selected.id) }); select(""); } }}><Trash2 size={16} /> Remove equipment</button>
          </fieldset>
          </div>
        </>}
      </aside>
    </div>
    </>}
    {!failedLoad && (mode !== "rack" || editing) && <footer className="rack-plan-footer">
      {mode === "rack" && <button type="button" className="primary-action rack-save-changes" disabled={busy || !loaded || Boolean(invalid) || !(dirty || rackHeightInput !== String(plan.rack_units))} onClick={() => void save()}>Save changes</button>}
      <RackPlanFiles key={profileId} plan={plan} defaultName={profileName} disabled={busy || !loaded} invalid={Boolean(invalid)} dirty={dirty || rackHeightInput !== String(plan.rack_units)} validate={rackPlanError} onPrepare={changeRackHeight} onPersist={save} onMessage={setMessage} onError={setError} onLoad={next => { setPlan(next); setRackHeightInput(String(next.rack_units)); select(next.equipment[0]?.id ?? ""); setPlacing(null); setDropSlot(null); setEditing(true); setTab("equipment"); setView("rack"); }} />
      {mode === "equipment" && (dirty || !plan.equipment.length) && <p className="journey-next">Save your rack layout to continue to network settings.</p>}
    </footer>}
  </section>;
}

/** Planned bays against the bays the server reported: extra drives and missing ones, with one tap to match. */
function ReadBaysNote({ planned, read, onMatch }: { planned: number[]; read: { bays: number[]; checkedAt: string | null }; onMatch: () => void }) {
  const extra = read.bays.filter(bay => !planned.includes(bay));
  const missing = planned.filter(bay => !read.bays.includes(bay));
  const list = (bays: number[]) => bays.length === 1 ? `bay ${bays[0]}` : `bays ${bays.slice(0, -1).join(", ")} and ${bays[bays.length - 1]}`;
  return <div className="rack-read-bays" role="note">
    <p><ProvenanceChip kind="proven" time={read.checkedAt || undefined} />The server reported {read.bays.length} drive{read.bays.length === 1 ? "" : "s"}{read.checkedAt ? ` at ${shortTime(read.checkedAt)}` : ""}.
      {!extra.length && !missing.length && " That matches the plan."}</p>
    {extra.length > 0 && <p className="is-found">Found a drive the plan doesn't have in {list(extra)}.</p>}
    {missing.length > 0 && <p className="is-missing">No drive reported in planned {list(missing)}.</p>}
    {(extra.length > 0 || missing.length > 0) && <button type="button" className="connection-secondary" onClick={onMatch}>Match the plan to the server</button>}
  </div>;
}
