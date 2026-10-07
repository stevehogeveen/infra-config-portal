import { strict as assert } from "node:assert";
import { arrangePlacement, resizeRack } from "./rackPlacement";
import type { PlannedEquipment, RackPlan } from "./components/RackPlanner";

const device = (id: string, position: number, height = 1, mount: PlannedEquipment["mount"] = "rack"): PlannedEquipment => ({
  id, device_id: `saved-${id}`, name: id, kind: "pdu", model: "", position, height, mount, ports: 0, bay_count: 0, occupied_bays: []
});
const rack = (...equipment: PlannedEquipment[]): RackPlan => ({ revision: 5, rack_units: 8, equipment });

export function run() {
  const existing = device("existing", 6, 2);
  const unaffected = device("unaffected", 3);
  const source = rack(existing, unaffected);
  const before = JSON.stringify(source);
  const placed = arrangePlacement(source, device("new", 1), 6);
  assert.equal(placed.error, null);
  assert.equal(placed.moved[0].position, 4);
  assert.equal(placed.moved[0].device_id, existing.device_id);
  assert.equal(placed.plan!.equipment.find(item => item.id === "unaffected"), unaffected);
  assert.equal(JSON.stringify(source), before);
  assert.equal(placed.plan!.revision, 5);

  const swap = arrangePlacement(rack(device("a", 8), device("b", 1)), device("a", 8), 1);
  assert.equal(swap.plan!.equipment.length, 2);
  assert.equal(swap.plan!.equipment.find(item => item.id === "a")!.position, 1);
  assert.equal(swap.moved[0].position, 8);

  const multiple = arrangePlacement(rack(device("a", 7), device("b", 6)), device("new", 1, 2), 7);
  assert.equal(multiple.moved.length, 2);
  assert.deepEqual(multiple.moved.map(item => item.position), [5, 4]);

  const sides = arrangePlacement(rack(device("side", 1, 8, "left")), device("new", 1, 2), 2);
  assert.equal(sides.moved.length, 0);
  assert.equal(sides.error, null);

  const full = rack(device("full", 1, 8));
  assert.equal(arrangePlacement(full, device("new", 1), 5).plan, null);
  assert.equal(full.equipment[0].position, 1);
  assert.match(arrangePlacement(full, device("new", 1), 5).error!, /nothing was moved/);
  assert.equal(arrangePlacement(source, device("new", 1, 2), 1).plan, null);
  assert.equal(arrangePlacement(source, device("new", 1), 9).plan, null);
  assert.equal(arrangePlacement(source, device("new", 1), 1).moved.length, 0);
  const partial = rack(device("large", 4, 2), device("small", 6), device("fixed", 1));
  const original = JSON.stringify(partial);
  const failed = arrangePlacement(partial, device("new", 1, 5), 8);
  assert.equal(failed.plan, null);
  assert.deepEqual(failed.moved, []);
  assert.equal(JSON.stringify(partial), original);
  const tall = rack(device("top", 7, 2), device("middle", 4, 2), device("bottom", 1));
  const resized = resizeRack(tall, 5);
  assert.equal(resized.error, null);
  assert.deepEqual(resized.plan!.equipment.map(item => item.position), [4, 2, 1]);
  assert.deepEqual(tall.equipment.map(item => item.position), [7, 4, 1]);
  assert.equal(resized.plan!.equipment[0].device_id, "saved-top");
  assert.equal(resizeRack(tall, 4).plan, null);
  assert.deepEqual(resizeRack(tall, 12).moved, []);
  assert.equal(resizeRack(tall, 3).plan, null);
  const sideRack = rack(device("main", 7, 2), device("side", 6, 2, "left"));
  assert.deepEqual(resizeRack(sideRack, 4).plan!.equipment.map(item => item.position), [3, 3]);
  assert.equal(resizeRack(rack(device("side", 1, 8, "right")), 4).plan, null);
}
