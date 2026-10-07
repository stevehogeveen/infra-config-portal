export const standaloneKitStages = [
  { id: "access", title: "Server and iLO access", detail: "Identify the server and verify its current management address.", to: "/simple" },
  { id: "firmware", title: "Firmware and ESXi baseline", detail: "Review iLO, BIOS, storage controller, NIC and switch versions against the intended ESXi image. Compatibility decision not verified.", to: "/firmware-upgrades" },
  { id: "updates", title: "Approved updates and health", detail: "Preview and separately approve needed updates; verify versions and hardware health after reboot. Completion not verified.", to: "/firmware-upgrades" },
  { id: "network", title: "Switch and management network", detail: "Verify the selected switch, uplinks, management network and required VLANs. Readiness not verified.", to: "/network" },
  { id: "boot", title: "ESXi boot mirror", detail: "Reserve two drives for RAID 1. Preview changes, confirm separately and verify the resulting mirror. Layout not verified.", to: "/simple" },
  { id: "esxi", title: "Install and verify ESXi", detail: "Install the compatible image; verify host identity, management access, licensing and health. Installation not verified.", to: "/server" },
  { id: "resources", title: "Datastore and VM network", detail: "Verify writable datastore capacity, CPU/RAM and the intended VM port group. Resources not verified.", to: "/virtualization" },
  { id: "deploy", title: "Deploy Windows OVF/OVA", detail: "Validate the Windows image, map storage and networks, preview and confirm deployment. Deployment not verified.", to: "/virtualization" },
  { id: "verify", title: "Windows boot and connectivity", detail: "Verify the guest boots and its intended network access works. Windows activation remains a separate requirement. Guest readiness not verified.", to: "/virtualization" },
] as const;

export function currentServerAccess(mode: string | undefined, access: {
  last_probe_status: string;
  last_probe_is_current: boolean;
  last_probe_target_matches_access_host: boolean;
  last_probe_target_fingerprint_present: boolean;
  last_probe_time?: string | null;
} | null | undefined): boolean {
  return Boolean(mode && mode !== "mock" && access?.last_probe_time &&
    access.last_probe_status === "ok" && access.last_probe_is_current === true &&
    access.last_probe_target_matches_access_host === true &&
    access.last_probe_target_fingerprint_present === true);
}
