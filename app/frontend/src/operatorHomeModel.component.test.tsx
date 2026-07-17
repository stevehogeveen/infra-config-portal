import assert from "node:assert/strict";

import { buildOperatorHomeModel } from "./operatorHomeModel";
import type { LabAddressPlan, LabProfile } from "./types";

export function run() {
  readinessCountsAgreeWithMapWhenEveryDeviceIsNotChecked();
  readinessCountsDistinguishBlockedFromNotChecked();
  readinessCountsAlwaysSumToTotal();
}

const address: LabAddressPlan = {
  subnet: "10.20.7.0/24",
  ilo: null,
  ilo_initial: null,
  server_embedded_nic: null,
  esxi_management: null,
  cisco_management: null,
  ansible_control_host: null,
  netapp_controller_a_sp: null,
  netapp_controller_b_sp: null,
  netapp_cluster_mgmt: null,
  netapp_node_a_mgmt: null,
  netapp_node_b_mgmt: null,
  netapp_svm_mgmt: null,
  netapp_nfs_lifs: [],
  netapp_iscsi_lifs: []
};

const profile = { name: "Test kit" } as unknown as LabProfile;

function readinessCountsAgreeWithMapWhenEveryDeviceIsNotChecked() {
  const model = buildOperatorHomeModel({
    address,
    buildVerification: null,
    features: null,
    firmwareSummaries: [],
    profile,
    providers: [],
    validation: null,
    vcenterNetapp: null
  });

  // Regression for: rail showed "0 ready, 6 blocked, 0 not checked" while the map
  // showed all six devices as "Not checked". One fact, one owner - the rail's
  // counts must always agree with the per-device states shown on the map.
  const notCheckedDevices = model.DeviceSummary.filter((item) => item.State === "Not checked");
  assert.equal(model.DeviceSummary.length, 6);
  assert.equal(notCheckedDevices.length, 6);
  assert.equal(model.Progress.Ready, 0);
  assert.equal(model.Progress.Blocked, 0);
  assert.equal(model.Progress.NotChecked, 6);
  assert.equal(model.AttentionItems.length, 0);
}

function readinessCountsDistinguishBlockedFromNotChecked() {
  const model = buildOperatorHomeModel({
    address,
    buildVerification: null,
    features: null,
    firmwareSummaries: [],
    profile,
    providers: [
      {
        id: "cisco-1",
        name: "Cisco switch",
        kind: "cisco",
        mode: "read_only",
        status: "blocked",
        capabilities: [],
        message: "",
        source_type: "provider",
        checked_at: null,
        freshness: "fresh",
        ttl_seconds: null,
        stale_after_seconds: null,
        is_current: true,
        is_operator_visible: true,
        recheck_command: null,
        evidence_artifacts: [],
        configuration: {},
        discovery: null,
        blockers: [],
        warnings: []
      }
    ],
    validation: null,
    vcenterNetapp: null
  });

  const blockedDevices = model.DeviceSummary.filter((item) => item.State === "Blocked");
  const notCheckedDevices = model.DeviceSummary.filter((item) => item.State === "Not checked");

  // The blocked count must equal the devices whose status is literally "blocked",
  // not every device that merely needs attention (which also includes not-checked).
  assert.equal(blockedDevices.length, 1);
  assert.equal(model.Progress.Blocked, 1);
  assert.equal(model.Progress.NotChecked, notCheckedDevices.length);
  assert.equal(model.Progress.Ready, 0);
}

function readinessCountsAlwaysSumToTotal() {
  const model = buildOperatorHomeModel({
    address,
    buildVerification: null,
    features: null,
    firmwareSummaries: [],
    profile,
    providers: [
      {
        id: "cisco-1",
        name: "Cisco switch",
        kind: "cisco",
        mode: "read_only",
        status: "blocked",
        capabilities: [],
        message: "",
        source_type: "provider",
        checked_at: null,
        freshness: "fresh",
        ttl_seconds: null,
        stale_after_seconds: null,
        is_current: true,
        is_operator_visible: true,
        recheck_command: null,
        evidence_artifacts: [],
        configuration: {},
        discovery: null,
        blockers: [],
        warnings: []
      },
      {
        id: "ilo-1",
        name: "HPE iLO",
        kind: "ilo",
        mode: "read_only",
        status: "ready",
        capabilities: [],
        message: "",
        source_type: "provider",
        checked_at: null,
        freshness: "fresh",
        ttl_seconds: null,
        stale_after_seconds: null,
        is_current: true,
        is_operator_visible: true,
        recheck_command: null,
        evidence_artifacts: [],
        configuration: {},
        discovery: null,
        blockers: [],
        warnings: []
      }
    ],
    validation: null,
    vcenterNetapp: null
  });

  assert.equal(model.Progress.Ready + model.Progress.Blocked + model.Progress.NotChecked, model.DeviceSummary.length);
}
