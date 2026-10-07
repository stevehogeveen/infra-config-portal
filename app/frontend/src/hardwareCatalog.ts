import type { PlannedEquipment } from "./components/RackPlanner";

export const RACK_UNIT_HEIGHT = 76;
export type HardwarePreset = {
  key: string; label: string; detail: string; kind: PlannedEquipment["kind"];
  model: string; height: number; bay_count: number; ports: 0 | 24 | 48; uplink_ports: 0 | 4;
};
export const hardwareCatalog: HardwarePreset[] = [
  { key: "dl360", label: "HPE DL360", detail: "1U / up to 10 drives", kind: "server", model: "HPE DL360", height: 1, bay_count: 10, ports: 0, uplink_ports: 0 },
  { key: "dl380", label: "HPE DL380", detail: "2U / up to 24 drives", kind: "server", model: "HPE DL380", height: 2, bay_count: 24, ports: 0, uplink_ports: 0 },
  { key: "c9300", label: "Cisco switch", detail: "24 ports / 4 SFP", kind: "switch", model: "Catalyst 9300", height: 1, bay_count: 0, ports: 24, uplink_ports: 4 },
  { key: "ups", label: "UPS", detail: "2U rackmount", kind: "ups", model: "Rackmount UPS", height: 2, bay_count: 0, ports: 0, uplink_ports: 0 },
  { key: "eaton", label: "Eaton 1550", detail: "5P / 1U rackmount", kind: "ups", model: "Eaton 5P 1550", height: 1, bay_count: 0, ports: 0, uplink_ports: 0 },
  { key: "pdu", label: "PDU", detail: "Rack or side mount", kind: "pdu", model: "", height: 1, bay_count: 0, ports: 0, uplink_ports: 0 },
  { key: "netapp", label: "NetApp storage", detail: "2U / 24 drive bays", kind: "storage", model: "NetApp 24 SFF", height: 2, bay_count: 24, ports: 0, uplink_ports: 0 }
];

export function serverFamily(model: string) {
  if (/\bDL360\b/i.test(model)) return { name: "DL360", height: 1, maxBays: 10 };
  if (/\bDL380\b/i.test(model)) return { name: "DL380", height: 2, maxBays: 24 };
  return null;
}
