import { strict as assert } from "node:assert";
import { currentServerAccess, standaloneKitStages } from "./standaloneKit";

export function run() {
  const access = { last_probe_status: "ok", last_probe_is_current: true,
    last_probe_target_matches_access_host: true, last_probe_target_fingerprint_present: true,
    last_probe_time: "2026-09-10T12:00:00Z" };
  assert.equal(currentServerAccess("mock", access), false);
  assert.equal(currentServerAccess(undefined, access), false);
  assert.equal(currentServerAccess("real", null), false);
  assert.equal(currentServerAccess("real", access), true);
  for (const field of ["last_probe_is_current", "last_probe_target_matches_access_host", "last_probe_target_fingerprint_present"]) {
    assert.equal(currentServerAccess("real", { ...access, [field]: false }), false);
  }
  assert.equal(currentServerAccess("real", { ...access, last_probe_time: null }), false);
  assert.deepEqual(standaloneKitStages.map((stage) => stage.id),
    ["access", "firmware", "updates", "network", "boot", "esxi", "resources", "deploy", "verify"]);
}
