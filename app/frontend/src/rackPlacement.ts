import type { PlannedEquipment, RackPlan } from "./components/RackPlanner";

export function resizeRack(plan: RackPlan, rackUnits: number) {
  const failure = (error: string) => ({ plan: null, moved: [] as PlannedEquipment[], error });
  if (!Number.isInteger(rackUnits) || rackUnits < 4 || rackUnits > 60) return failure("Rack height must be 4 to 60 U.");
  const moved: PlannedEquipment[] = [];
  for (const mount of ["rack", "left", "right"] as const) {
    const items = plan.equipment.filter(item => item.mount === mount).sort((a, b) => b.position - a.position);
    if (items.some(item => !Number.isInteger(item.height) || item.height < 1) || items.reduce((sum, item) => sum + item.height, 0) > rackUnits) {
      return failure(`Equipment in the ${mount === "rack" ? "rack" : `${mount} side`} cannot fit in ${rackUnits}U. Rack size and positions are unchanged.`);
    }
    // Lower overflowing chassis in visual order, closing only the gaps needed to fit.
    let ceiling = rackUnits;
    for (const item of items) {
      const position = Math.min(item.position, ceiling - item.height + 1);
      if (position !== item.position) moved.push({ ...item, position });
      ceiling = position - 1;
    }
  }
  return { plan: { ...plan, rack_units: rackUnits, equipment: plan.equipment.map(item => moved.find(other => other.id === item.id) ?? item) }, moved, error: null };
}

export function arrangePlacement(plan: RackPlan, equipment: PlannedEquipment, topSlot: number) {
  const incoming = { ...equipment, position: topSlot - equipment.height + 1 };
  const moved: PlannedEquipment[] = [];
  const failure = (error: string) => ({ plan: null, moved: [], error });
  if (!Number.isInteger(plan.rack_units) || plan.rack_units < 4 || plan.rack_units > 60) return failure("Rack height must be 4 to 60 U.");
  if (!Number.isInteger(incoming.height) || incoming.height < 1 || incoming.height > 12) return failure("Equipment height must be 1 to 12 U.");
  if (!Number.isInteger(topSlot) || incoming.position < 1 || topSlot > plan.rack_units) {
    return failure(`${incoming.name} must fit inside the rack.`);
  }
  const overlaps = (a: PlannedEquipment, b: PlannedEquipment) => a.mount === b.mount &&
    a.position < b.position + b.height && b.position < a.position + a.height;
  const others = plan.equipment.filter(item => item.id !== incoming.id);
  const displaced = others.filter(item => overlaps(item, incoming))
    .sort((a, b) => b.height - a.height || b.position - a.position || a.id.localeCompare(b.id));
  const reserved = [incoming, ...others.filter(item => !overlaps(item, incoming))];
  // Reserve unaffected chassis, then fit larger displaced chassis before smaller ones.
  for (const item of displaced) {
    const positions = Array.from({ length: plan.rack_units - item.height + 1 }, (_, index) => index + 1);
    const candidates = [...positions.filter(position => position < item.position).reverse(),
      ...positions.filter(position => position >= item.position).reverse()];
    const position = candidates.find(position => !reserved.some(other => overlaps({ ...item, position }, other)));
    if (position === undefined) return failure(`No free ${item.height}U space for ${item.name}. Free space or increase rack height; nothing was moved.`);
    const shifted = { ...item, position };
    moved.push(shifted);
    reserved.push(shifted);
  }
  const equipmentList = plan.equipment.map(item => item.id === incoming.id ? incoming : moved.find(other => other.id === item.id) ?? item);
  if (!plan.equipment.some(item => item.id === incoming.id)) equipmentList.push(incoming);
  return { plan: { ...plan, equipment: equipmentList }, moved, error: null };
}
