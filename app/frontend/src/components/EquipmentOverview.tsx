import { ArrowRight, Circle, Server, Network, Battery, Plug, HardDrive } from "lucide-react";
import type { PlannedEquipment } from "./RackPlanner";
import { HardwareThumbnail, HardwarePreview } from "./HardwareThumbnail";

export const equipmentIcons = { server: Server, switch: Network, ups: Battery, pdu: Plug, storage: HardDrive };

export function EquipmentOverview({ item, busy, invalid, onSave, onConnect, onEdit }: {
  item: PlannedEquipment; busy: boolean; invalid: boolean;
  onSave: () => void; onConnect: () => void; onEdit: () => void;
}) {
  const Icon = equipmentIcons[item.kind];
  return <div className="equipment-overview">
    <HardwarePreview item={item} />
    <div className="equipment-next"><Icon size={28} aria-hidden="true" /><div><h3>{!item.device_id ? "Save this equipment first" : item.kind === "server" ? "Start with the server connection" : "Review equipment details"}</h3><p>{!item.device_id ? "This equipment is a draft." : item.kind === "server" ? "Have the current iLO address and sign-in details ready." : "Equipment is planned. Hardware readiness has not been verified."}</p></div></div>
    <button className="overview-primary" disabled={busy || (!item.device_id && invalid)} onClick={!item.device_id ? onSave : item.kind === "server" ? onConnect : onEdit}>{!item.device_id ? "Save equipment" : item.kind === "server" ? "Connect server" : "Review details"}<ArrowRight size={17} /></button>
    <dl className="equipment-readiness">{(item.kind === "server" ? ["Connection", "Firmware", "ESXi", "Windows"] : ["Connection", "Firmware"]).map(label => <div key={label}><dt>{label}</dt><dd><Circle size={13} />Not checked</dd></div>)}</dl>
    <p>Saved settings are not proof of a working connection.</p>
  </div>;
}

export function EquipmentChecklist({ items, selectedId, onSelect, readOnly = false }: { items: PlannedEquipment[]; selectedId: string; onSelect: (id: string) => void; readOnly?: boolean }) {
  return <div className="equipment-checklist" aria-label="Equipment checklist">
    <div className="checklist-heading"><span>Equipment</span><span>{readOnly ? "Details" : "Next step"}</span></div>
    {items.length === 0 && <p>No equipment added yet.</p>}
    {items.map(item => <button key={item.id} type="button" aria-pressed={selectedId === item.id} onClick={() => onSelect(item.id)}><HardwareThumbnail item={item} /><span><strong>{item.name}</strong><small>{item.model || item.kind} / Planned</small></span><span>{readOnly ? "Status" : !item.device_id ? "Save equipment" : item.kind === "server" ? "Set up connection" : "Review details"}<ArrowRight size={16} /></span></button>)}
  </div>;
}
