import type { PlannedEquipment, RackPlan } from "./components/RackPlanner";

export const MAX_RACK_FILE_BYTES = 1024 * 1024;
const format = "lab-builder-rack-plan";

export function exportRackFile(plan: RackPlan, name: string) {
  return {
    format, version: 1, name: name.trim(), rack_units: plan.rack_units,
    equipment: plan.equipment.map(item => ({
      id: item.id, name: item.name, kind: item.kind, model: item.model,
      position: item.position, height: item.height, mount: item.mount,
      ports: item.ports, uplink_ports: item.uplink_ports || 0,
      bay_count: item.bay_count, occupied_bays: [...item.occupied_bays]
    }))
  };
}

export function importRackFile(text: string, current: RackPlan, validate: (plan: RackPlan) => string | null) {
  if (new TextEncoder().encode(text).length > MAX_RACK_FILE_BYTES) throw new Error("Rack plan files must be smaller than 1 MB.");
  let data;
  try { data = JSON.parse(text); } catch { throw new Error("This is not a valid rack plan JSON file."); }
  const fail = () => { throw new Error("This file is not a supported rack plan. Choose a file created by Save a copy."); };
  if (!data || data.format !== format || data.version !== 1 || typeof data.name !== "string" || !data.name.trim() || data.name.length > 120 || !Number.isInteger(data.rack_units) || !Array.isArray(data.equipment) || data.equipment.length > 100) fail();
  const ids = new Set<string>();
  const equipment: PlannedEquipment[] = data.equipment.map((item: any) => {
    if (!item || typeof item.id !== "string" || !item.id || item.id.length > 80 || ids.has(item.id) || typeof item.name !== "string" || !item.name.trim() || item.name.length > 120 || typeof item.model !== "string" || item.model.length > 120 || !["server", "switch", "ups", "pdu", "storage"].includes(item.kind) || !["rack", "left", "right"].includes(item.mount) || !Number.isInteger(item.position) || !Number.isInteger(item.height) || !Number.isInteger(item.bay_count) || ![0, 24, 48].includes(item.ports) || ![0, 4].includes(item.uplink_ports ?? 0) || !Array.isArray(item.occupied_bays) || item.occupied_bays.length > 24 || item.occupied_bays.some((bay: unknown) => !Number.isInteger(bay) || Number(bay) < 1) || new Set(item.occupied_bays).size !== item.occupied_bays.length) fail();
    if ((item.kind !== "pdu" && item.mount !== "rack") || (item.kind === "switch" ? ![24, 48].includes(item.ports) : item.ports !== 0 || (item.uplink_ports ?? 0) !== 0) || (!["server", "storage"].includes(item.kind) && (item.bay_count || item.occupied_bays.length))) fail();
    ids.add(item.id);
    // Only reuse a connection already attached to this exact item in the current rack.
    const existing = current.equipment.find(entry => entry.id === item.id && entry.kind === item.kind);
    return { id: item.id, name: item.name, kind: item.kind, model: item.model,
      position: item.position, height: item.height, mount: item.mount, ports: item.ports,
      uplink_ports: item.uplink_ports ?? 0, bay_count: item.bay_count, occupied_bays: [...item.occupied_bays],
      device_id: existing?.device_id ?? null };
  });
  const plan = { revision: current.revision, rack_units: data.rack_units, equipment };
  const error = validate(plan);
  if (error) throw new Error(error);
  return { name: data.name.trim() as string, plan };
}
