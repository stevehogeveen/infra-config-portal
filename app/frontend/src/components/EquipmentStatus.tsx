import { useEffect, useState } from "react";
import { api, windowsApi, type EsxiInstallStatus, type WindowsStatus } from "../api";
import { useStudio } from "./studio/StudioContext";
import type { DeviceInventoryItem, IloAccessSettings } from "../types";
import type { PlannedEquipment } from "./RackPlanner";
import { HardwarePreview } from "./HardwareThumbnail";

export function EquipmentStatus({ item, device }: { item: PlannedEquipment; device?: DeviceInventoryItem }) {
  const [access, setAccess] = useState<IloAccessSettings | null>(null);
  const [loading, setLoading] = useState(Boolean(item.device_id && item.kind === "server"));
  const [error, setError] = useState(false);
  useEffect(() => {
    let active = true;
    setAccess(null); setError(false); setLoading(Boolean(item.device_id && item.kind === "server"));
    if (!item.device_id || item.kind !== "server") return;
    // This endpoint reads saved settings and probe evidence; it does not contact hardware.
    api.iloAccessSettings(item.device_id).then(value => {
      if (active && value.device_id === item.device_id) setAccess(value);
    }).catch(() => { if (active) setError(true); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [item.device_id, item.kind]);
  // Recorded ESXi and Windows results (stored evidence; nothing is contacted).
  const profileId = useStudio()?.profileId ?? null;
  const [esxi, setEsxi] = useState<EsxiInstallStatus | null>(null);
  const [windows, setWindows] = useState<WindowsStatus | null>(null);
  useEffect(() => {
    let active = true;
    setEsxi(null); setWindows(null);
    if (!profileId || !item.device_id || item.kind !== "server") return;
    api.esxiInstall(profileId, item.device_id).then(value => { if (active) setEsxi(value); }).catch(() => {});
    windowsApi.status(profileId, item.device_id).then(value => { if (active) setWindows(value); }).catch(() => {});
    return () => { active = false; };
  }, [profileId, item.device_id, item.kind]);
  const esxiVerified = esxi?.state === "verified";
  const esxiVersion = esxi?.verification?.checks?.find(check => check.name === "ESXi answered the root sign-in")?.found;
  const current = access?.last_probe_is_current && access.last_probe_target_matches_access_host;
  const connection = loading ? "Loading status" : error ? "Status unavailable"
    : !access?.last_probe_time ? "Not checked"
    : !current ? "Needs recheck"
    : access.last_probe_status === "ok" ? "Connected at last check"
    : "Connection not confirmed";
  const host = access?.host || device?.host;
  return <section className="equipment-overview" aria-label="Equipment status">
    <HardwarePreview item={item} />
    <dl className="equipment-readiness">
      <div><dt>{item.kind === "server" ? "iLO connection" : "Connection"}</dt><dd>{connection}</dd></div>
      <div><dt>{item.kind === "server" ? "iLO IP / hostname" : "Management IP / hostname"}</dt><dd>{host || "Not entered"}{host && <small>Saved address</small>}</dd></div>
      <div><dt>{item.kind === "server" ? "iLO firmware" : "Firmware"}</dt><dd>{current && access?.observed_ilo_firmware || "Not checked"}</dd></div>
      {item.kind === "server" && <>
        <div><dt>Server firmware / BIOS</dt><dd>{current && access?.observed_bios_version || "Not checked"}</dd></div>
        <div><dt>ESXi IP / hostname</dt><dd>{esxiVerified ? <>{esxi!.management_ip}{esxi!.hostname && <small>{esxi!.hostname}</small>}</> : "Not installed yet"}</dd></div>
        <div><dt>ESXi version</dt><dd>{esxiVerified && esxiVersion ? esxiVersion : esxiVerified ? "Verified" : "Not checked"}</dd></div>
        <div><dt>Windows VM</dt><dd>{windows?.state === "verified" ? <>{windows.vm_name} · {windows.address}{windows.guest_os && <small>{windows.guest_os}</small>}</> : "Not deployed yet"}</dd></div>
      </>}
      <div><dt>Last connection check</dt><dd>{access?.last_probe_time ? new Date(access.last_probe_time).toLocaleString() : "Never"}</dd></div>
    </dl>
    {access?.last_probe_message && <p>{access.last_probe_message}</p>}
  </section>;
}
