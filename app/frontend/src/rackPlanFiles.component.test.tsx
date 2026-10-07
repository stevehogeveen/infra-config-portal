import { strict as assert } from "node:assert";
import { exportRackFile, importRackFile } from "./rackPlanFiles";
import type { RackPlan } from "./components/RackPlanner";

export function run() {
  const plan: RackPlan = { revision: 5, rack_units: 8, equipment: [{ id: "server", device_id: "connection", name: "Server", kind: "server", model: "HPE DL360 Gen11", height: 1, position: 8, mount: "rack", ports: 0, bay_count: 10, occupied_bays: [1, 2] }] };
  const validate = () => null;
  const file = exportRackFile(plan, " Kit A ");
  assert.equal(file.name, "Kit A");
  assert.equal("device_id" in file.equipment[0], false);
  assert.equal("revision" in file, false);
  const imported = importRackFile(JSON.stringify(file), plan, validate);
  assert.equal(imported.plan.revision, 5);
  assert.equal(imported.plan.equipment[0].device_id, "connection");
  const other = importRackFile(JSON.stringify(file), { ...plan, revision: 12, equipment: [] }, validate);
  assert.equal(other.plan.revision, 12);
  assert.equal(other.plan.equipment[0].device_id, null);
  const injected = { ...file, password: "not-exported", equipment: [{ ...file.equipment[0], device_id: "wrong-connection", password: "not-exported" }] };
  const clean = importRackFile(JSON.stringify(injected), plan, validate);
  assert.equal(clean.plan.equipment[0].device_id, "connection");
  assert.equal(JSON.stringify(exportRackFile(clean.plan, "Clean")).includes("not-exported"), false);
  for (const input of ["{", "null", JSON.stringify({ ...file, version: 2 }), JSON.stringify({ ...file, equipment: [null] }), JSON.stringify({ ...file, equipment: [file.equipment[0], file.equipment[0]] }), JSON.stringify({ ...file, equipment: [{ ...file.equipment[0], occupied_bays: [0] }] }), " ".repeat(1024 * 1024 + 1)]) {
    assert.throws(() => importRackFile(input, plan, validate));
  }
  assert.throws(() => importRackFile(JSON.stringify(file), plan, () => "Layout overlaps"), /Layout overlaps/);
}
