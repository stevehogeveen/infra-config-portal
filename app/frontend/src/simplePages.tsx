import { useCallback, useEffect, useState, type KeyboardEvent } from "react";
import { Cpu, Database, FileText, HardDrive, Layers3, ListChecks, PlayCircle, Pencil, Plus, Server, Settings2, Trash2 } from "lucide-react";
import { Link, NavLink } from "react-router-dom";
import { api } from "./api";
import { DeviceInventoryForm } from "./components/DeviceInventoryForm";
import { RackDeviceConfigurator, RackIloConfigurator, localRaidInventoryBays } from "./operatorPages";
import type { LocalRaidInventoryBay } from "./operatorPages";
import type {
  DeviceInventoryItem,
  HpeStorageDiscovery,
  HpeVsanReadiness,
  IloAccessSettings,
  LabProfileList,
  ProviderStatus
} from "./types";

// The rack workspace and ordered runbook use only cheap, already-cached data.
// They do not probe hardware or expose apply operations.

type IloAccessByDeviceId = Record<string, IloAccessSettings | null>;

type SimpleData = {
  devices: DeviceInventoryItem[];
  providers: ProviderStatus[];
  accessByDeviceId: IloAccessByDeviceId;
  storage: HpeStorageDiscovery | null;
  vsan: HpeVsanReadiness | null;
  profiles: LabProfileList | null;
  health: Awaited<ReturnType<typeof api.health>> | null;
  loaded: boolean;
  loadError: string | null;
};

async function readSimpleData(): Promise<SimpleData> {
  const [healthResult, devicesResult] = await Promise.allSettled([
    api.health(),
    api.deviceInventory()
  ]);
  if (healthResult.status === "rejected" || devicesResult.status === "rejected") {
    return {
      devices: [],
      providers: [],
      accessByDeviceId: {},
      storage: null,
      vsan: null,
      profiles: null,
      health: healthResult.status === "fulfilled" ? healthResult.value : null,
      loaded: true,
      loadError: "Lab Builder cannot reach its local backend. Rack data has not been loaded."
    };
  }
  const iloDevices = devicesResult.value.filter((device) => rackDeviceKind(device) === "ilo");
  const primaryIloDevice = iloDevices[0];
  const [providers, accessEntries, storage, vsan, profiles] = await Promise.all([
    optionalRackRead(api.providers(), [] as ProviderStatus[]),
    Promise.all(iloDevices.map(async (device) => (
      [device.id, await optionalRackRead(api.iloAccessSettings(device.id), null)] as const
    ))),
    primaryIloDevice
      ? optionalRackRead(api.hpeStorageDiscovery(primaryIloDevice.id), null)
      : Promise.resolve(null),
    primaryIloDevice
      ? optionalRackRead(api.hpeVsanReadiness(primaryIloDevice.id), null)
      : Promise.resolve(null),
    optionalRackRead(api.labProfiles(), null)
  ]);
  return {
    devices: devicesResult.value,
    providers,
    accessByDeviceId: Object.fromEntries(accessEntries),
    storage,
    vsan,
    profiles,
    health: healthResult.value,
    loaded: true,
    loadError: null
  };
}

function optionalRackRead<T>(promise: Promise<T>, fallback: T, timeoutMs = 8000): Promise<T> {
  let timer: number | undefined;
  const timeout = new Promise<T>((resolve) => {
    timer = window.setTimeout(() => resolve(fallback), timeoutMs);
  });
  return Promise.race([promise.catch(() => fallback), timeout]).finally(() => {
    if (timer !== undefined) window.clearTimeout(timer);
  });
}

function useSimpleData(): SimpleData & { reload: () => Promise<void> } {
  const [data, setData] = useState<SimpleData>({
    devices: [],
    providers: [],
    accessByDeviceId: {},
    storage: null,
    vsan: null,
    profiles: null,
    health: null,
    loaded: false,
    loadError: null
  });

  const reload = useCallback(async () => {
    setData((current) => ({ ...current, loaded: false, loadError: null }));
    setData(await readSimpleData());
  }, []);

  useEffect(() => {
    let cancelled = false;
    void readSimpleData().then((next) => {
      if (!cancelled) setData(next);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return { ...data, reload };
}

const PROVIDERS_BY_TYPE: Record<string, string[]> = {
  ilo: ["ilo-redfish"],
  esxi_host: ["esxi-readonly"],
  cisco_switch: ["cisco-console", "cisco-ansible"],
  netapp: ["netapp-ontap"],
  vcenter: ["vcenter"]
};

function rackDeviceKind(device: DeviceInventoryItem): string {
  const normalized = device.device_type.toLowerCase().replace(/[^a-z0-9]+/g, "_");
  if (normalized.includes("ilo") || normalized.includes("bmc")) return "ilo";
  if (normalized.includes("cisco") || normalized.includes("switch")) return "cisco_switch";
  if (normalized.includes("esxi") || normalized.includes("hypervisor")) return "esxi_host";
  if (normalized.includes("netapp") || normalized.includes("ontap")) return "netapp";
  if (normalized.includes("vcenter") || normalized.includes("vcsa")) return "vcenter";
  if (normalized.includes("server")) return "server";
  return normalized;
}

function rackKindLabel(kind: string, fallback: string): string {
  if (kind === "ilo") return "iLO";
  if (kind === "cisco_switch") return "Cisco switch";
  if (kind === "esxi_host") return "ESXi host";
  if (kind === "netapp") return "NetApp";
  if (kind === "vcenter") return "vCenter";
  if (kind === "server") return "server";
  return fallback.replace(/_/g, " ");
}

function deviceWord(device: DeviceInventoryItem, providers: ProviderStatus[], access?: IloAccessSettings | null): "Ready" | "Problem" | "Not checked" {
  const kind = rackDeviceKind(device);
  if (kind === "ilo") {
    if (
      !access ||
      access.last_probe_is_current !== true ||
      access.last_probe_target_matches_access_host !== true ||
      access.last_probe_target_fingerprint_present !== true
    ) {
      return "Not checked";
    }
    const accessStatus = access.last_probe_status.trim().toLowerCase();
    if (["ok", "passed", "reachable", "ready", "success", "succeeded"].includes(accessStatus)) return "Ready";
    if (!accessStatus || accessStatus === "not_checked" || accessStatus === "unknown") return "Not checked";
    return "Problem";
  }
  const providerIds = PROVIDERS_BY_TYPE[kind] ?? [];
  const provider = providers.find((item) => providerIds.includes(item.id));
  if (!provider || !provider.is_current || provider.status === "not_checked" || provider.freshness === "not_checked") {
    return "Not checked";
  }
  if (provider.status === "ready" || provider.status === "ok") {
    return "Ready";
  }
  return "Problem";
}

function devicePage(device: DeviceInventoryItem): string {
  const kind = rackDeviceKind(device);
  if (kind === "ilo") return "/server";
  if (kind === "esxi_host") return "/virtualization";
  if (kind === "cisco_switch") return "/network";
  if (kind === "netapp") return "/storage";
  if (kind === "vcenter") return "/virtualization";
  if (kind === "server") return "/server";
  return "/simple";
}

function rackConfigAvailable(device: DeviceInventoryItem): boolean {
  return ["cisco_switch", "esxi_host", "netapp", "vcenter", "server"].includes(rackDeviceKind(device));
}

function rackConfigLabel(device: DeviceInventoryItem): string {
  return rackKindLabel(rackDeviceKind(device), device.device_type);
}

type RackWord = "Ready" | "Problem" | "Not checked";
type RackBayState = "boot" | "data" | "free" | "unknown";
type RackBay = { id: string; label: string; state: RackBayState };

function recordText(record: Record<string, unknown> | undefined, ...keys: string[]): string | null {
  if (!record) return null;
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value.trim();
    if (typeof value === "number") return String(value);
  }
  return null;
}

function rackWordClass(word: RackWord): string {
  return word.toLowerCase().replace(" ", "-");
}

function rackStatusCounts(devices: DeviceInventoryItem[], providers: ProviderStatus[], accessByDeviceId: IloAccessByDeviceId) {
  return devices.reduce(
    (counts, device) => {
      const word = deviceWord(device, providers, accessByDeviceId[device.id]);
      if (word === "Ready") counts.ready += 1;
      else if (word === "Problem") counts.problem += 1;
      else counts.notChecked += 1;
      return counts;
    },
    { notChecked: 0, problem: 0, ready: 0 }
  );
}

function selectedRackGuidance(selected: DeviceInventoryItem | undefined, word: RackWord, access: IloAccessSettings | null): string {
  if (!selected) return "Add the first piece of equipment to start building this rack.";
  const isIlo = rackDeviceKind(selected) === "ilo";
  const iloCredentialsReady = isIlo && Boolean(access?.username_configured && access.password_configured);

  if (isIlo && word === "Ready") return "Current proof matches this exact iLO, so configuration and storage reads can happen beside the rack.";
  if (isIlo && iloCredentialsReady) return "Credentials are saved locally. Run the explicit read-only iLO check before trusting this rack unit as green.";
  if (isIlo) return "Save the iLO address and local credentials first; the rack stays unconfirmed until a read-only check succeeds.";
  if (word === "Ready") return "Cached proof says this device is reachable. Use beside-rack configuration for the next safe edit.";
  if (word === "Problem") return "Open beside-rack configuration, fix the blocker, then rerun the relevant read-only check.";
  return "Add the missing setup details, then run a read-only check from the configuration panel.";
}

function RackWorkspaceSummary({
  accessByDeviceId,
  bays,
  devices,
  mode,
  providers,
  selected,
  word
}: {
  accessByDeviceId: IloAccessByDeviceId;
  bays: RackBay[];
  devices: DeviceInventoryItem[];
  mode: string;
  providers: ProviderStatus[];
  selected?: DeviceInventoryItem;
  word: RackWord;
}) {
  const counts = rackStatusCounts(devices, providers, accessByDeviceId);
  const freeBays = bays.filter((bay) => bay.state === "free").length;
  const guidance = selectedRackGuidance(selected, word, selected ? accessByDeviceId[selected.id] : null);
  const safeMode = mode.includes("readwrite") ? "Guarded writes" : "Read-only checks";

  return (
    <section className="rack-workspace-summary" aria-label="Rack status and next step">
      <div className={`rack-summary-card rack-summary-primary is-${rackWordClass(word)}`}>
        <span>Selected device</span>
        <strong>{selected?.display_name ?? "No device selected"}</strong>
        <p>{guidance}</p>
      </div>
      <div className="rack-summary-metrics" aria-label="Device proof counts">
        <div><span>Ready</span><strong>{counts.ready}</strong></div>
        <div><span>Needs check</span><strong>{counts.notChecked}</strong></div>
        <div><span>Problem</span><strong>{counts.problem}</strong></div>
        <div><span>Bays free</span><strong>{bays.length ? `${freeBays}/${bays.length}` : "Not read"}</strong></div>
      </div>
      <div className="rack-summary-card rack-summary-safety">
        <span>Lab safety</span>
        <strong>{safeMode}</strong>
        <p>Green means current cached proof only. Saving rack details never probes hardware by itself.</p>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Machine contents: the software and storage that live inside one physical box.
//
// Everything here is derived from cached read-only evidence. Where the app has
// not read something yet it says so; it never invents a datastore, a capacity,
// or a VM that no probe has actually reported.
// ---------------------------------------------------------------------------

type InsideItemKind = "hypervisor" | "local" | "vsan" | "shared";

type InsideItem = {
  id: string;
  kind: InsideItemKind;
  name: string;
  detail: string;
  badge: string;
  /** Volume label used to colour the chassis bay map in the configure level. */
  volumeLabel?: string;
};

function asText(value: unknown): string {
  if (typeof value === "string") return value.trim();
  if (typeof value === "number") return String(value);
  return "";
}

function records(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object") : [];
}

/** Named local volumes exactly as the controller reports them. */
function localDatastoreItems(storage: HpeStorageDiscovery | null): InsideItem[] {
  return records(storage?.logical_drives).map((volume, index) => {
    const name = asText(volume.display_label) || asText(volume.Name) || `Logical drive ${index + 1}`;
    const raid = asText(volume.raid_level) || asText(volume.RAIDType);
    const capacity = asText(volume.capacity_label) || asText(volume.CapacityGiB) || asText(volume.CapacityBytes);
    return {
      id: `local:${asText(volume.Id) || asText(volume.LogicalDriveNumber) || index}`,
      kind: "local" as const,
      name,
      detail: [raid, capacity].filter(Boolean).join(" · ") || "Details not read",
      badge: "Local",
      volumeLabel: raid ? `${name} · ${raid}` : name
    };
  });
}

function vsanItem(vsan: HpeVsanReadiness | null): InsideItem | null {
  if (!vsan?.storage_inventory_available) return null;
  const summary = (vsan.summary ?? {}) as Record<string, unknown>;
  const ready = asText(summary.passthrough_ready_count) || String(
    records(vsan.drives).filter((drive) => asText(drive.vsan_status) === "passthrough_ready").length
  );
  const capacity = asText(summary.passthrough_ready_capacity_label);
  return {
    id: "vsan:cluster",
    kind: "vsan",
    // vSAN datastores are named at the cluster, which this app cannot read
    // yet. Say that rather than inventing a name.
    name: "vSAN datastore not created yet",
    detail: [`${ready} drives ready to contribute`, capacity].filter(Boolean).join(" · "),
    badge: "vSAN"
  };
}

/** Shared storage belongs to another rack device, so it stays a reference. */
function sharedStorageItems(devices: DeviceInventoryItem[]): InsideItem[] {
  return devices
    .filter((device) => rackDeviceKind(device) === "netapp")
    .map((device) => ({
      id: `shared:${device.id}`,
      kind: "shared" as const,
      name: device.display_name,
      detail: device.host ? `Served from ${device.host}` : "Address not set",
      badge: "Shared"
    }));
}

function insideItems(
  storage: HpeStorageDiscovery | null,
  vsan: HpeVsanReadiness | null,
  devices: DeviceInventoryItem[],
  providers: ProviderStatus[]
): InsideItem[] {
  const esxi = providers.find((provider) => provider.id === "esxi-readonly");
  const hypervisor: InsideItem = {
    id: "hypervisor:esxi",
    kind: "hypervisor",
    name: "ESXi host",
    detail: esxi && esxi.is_current && esxi.status !== "not_checked"
      ? `Reported ${esxi.status}`
      : "No current check has proven this yet",
    badge: "Hypervisor"
  };
  return [hypervisor, ...localDatastoreItems(storage), ...(vsanItem(vsan) ? [vsanItem(vsan) as InsideItem] : []), ...sharedStorageItems(devices)];
}

function insideItemIcon(kind: InsideItemKind) {
  if (kind === "hypervisor") return <Server size={15} />;
  if (kind === "shared") return <Database size={15} />;
  return <HardDrive size={15} />;
}

function rackBays(vsan: HpeVsanReadiness | null): RackBay[] {
  if (!vsan?.storage_inventory_available) return [];
  return vsan.drives.slice(0, 16).map((drive, index) => {
    const label = recordText(drive, "bay_id", "bay", "slot", "location") ?? String(index + 1);
    const volume = recordText(drive, "volume_name", "logical_drive", "usage")?.toLowerCase() ?? "";
    const readiness = recordText(drive, "vsan_status", "status", "readiness")?.toLowerCase() ?? "";
    const state: RackBayState = volume.includes("boot") || volume.includes("esxi") || volume.includes("os")
      ? "boot"
      : volume
        ? "data"
        : readiness.includes("passthrough") || readiness.includes("ready")
          ? "free"
          : "unknown";
    return { id: `${label}-${index}`, label, state };
  });
}

function rackUnitHeight(device: DeviceInventoryItem): number {
  const kind = rackDeviceKind(device);
  if (kind === "ilo" || kind === "netapp") return 88;
  if (kind === "cisco_switch") return 68;
  return 60;
}

function RackElevationGraphic({ devices, providers, accessByDeviceId, bays, storageDeviceId, selectedId, onSelect }: {
  devices: DeviceInventoryItem[];
  providers: ProviderStatus[];
  accessByDeviceId: IloAccessByDeviceId;
  bays: RackBay[];
  storageDeviceId: string;
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  const keySelect = (event: KeyboardEvent<SVGGElement>, id: string) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(id);
    }
  };

  let rackCursor = 62;
  const rows = devices.map((device, index) => {
    const height = rackUnitHeight(device);
    const row = { device, height, index, y: rackCursor };
    rackCursor += height + 12;
    return row;
  });
  const rackHeight = Math.max(560, rackCursor + 44);
  const rackBodyHeight = rackHeight - 60;

  return (
    <svg className="rack-light-svg" viewBox={`0 0 620 ${rackHeight}`} role="img" aria-label="Interactive rack elevation">
      <defs>
        <linearGradient id="rackFrame" x1="0" x2="1"><stop offset="0" stopColor="#dce7eb" /><stop offset=".5" stopColor="#f8fbfc" /><stop offset="1" stopColor="#c8d6dc" /></linearGradient>
        <linearGradient id="deviceFace" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#fff" /><stop offset="1" stopColor="#e8f0f3" /></linearGradient>
        <pattern id="rackVent" width="8" height="8" patternUnits="userSpaceOnUse"><circle cx="4" cy="4" r="1.1" fill="#91a5ad" opacity=".45" /></pattern>
        <filter id="rackShadow" x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="7" stdDeviation="8" floodColor="#102932" floodOpacity=".14" /></filter>
      </defs>
      <ellipse cx="320" cy={rackHeight - 20} rx="190" ry="18" fill="#b7c7cd" opacity=".22" />
      <rect x="85" y="22" width="470" height={rackBodyHeight} rx="20" fill="url(#rackFrame)" stroke="#bccbd1" />
      <rect x="104" y="38" width="432" height={rackBodyHeight - 36} rx="10" fill="#dbe5e9" stroke="#aebfc6" />
      <rect x="125" y="45" width="390" height={rackBodyHeight - 50} rx="6" fill="url(#rackVent)" />

      {rows.map(({ device, height, index, y }) => {
        const access = accessByDeviceId[device.id];
        const word = deviceWord(device, providers, access);
        const kind = rackDeviceKind(device);
        const isCisco = kind === "cisco_switch";
        const isIlo = kind === "ilo";
        const iloCredentialsReady = isIlo && Boolean(access?.username_configured && access.password_configured);
        const hasDeviceStorage = isIlo && storageDeviceId === device.id;
        const isNetapp = kind === "netapp";
        const isEsxi = kind === "esxi_host";
        return <g key={device.id} className={`rack-unit is-${rackWordClass(word)} ${selectedId === device.id ? "is-selected" : ""}`} role="button" tabIndex={0} aria-label={`Open ${device.display_name}`} onClick={() => onSelect(device.id)} onKeyDown={(event) => keySelect(event, device.id)}>
          <text x="109" y={y + 22} className="rack-u-label">{String(devices.length - index).padStart(2, "0")}</text>
          <rect x="143" y={y} width="354" height={height} rx="7" fill="url(#deviceFace)" filter="url(#rackShadow)" />
          <circle cx="157" cy={y + 18} r="5" className="rack-status-dot" />
          <text x="170" y={y + 22} className="rack-face-title">{device.display_name}</text>
          <text x="478" y={y + 22} textAnchor="end" className="rack-face-meta">{rackKindLabel(kind, device.device_type)}</text>
          {isCisco && Array.from({ length: 24 }).map((_, port) => <rect key={port} x={168 + (port % 12) * 25} y={y + 34 + Math.floor(port / 12) * 12} width="18" height="8" rx="1.5" className="rack-port" />)}
          {isIlo && <>
            <rect x="158" y={y + 32} width="72" height="38" rx="5" className="rack-management-module" />
            <text x="194" y={y + 55} textAnchor="middle" className="rack-module-label">iLO MGMT</text>
            {hasDeviceStorage && bays.length ? bays.slice(0, 8).map((bay, bayIndex) => <g key={bay.id}><rect x={242 + bayIndex * 29} y={y + 34} width="23" height="32" rx="3" className={`rack-drive is-${bay.state}`} /><text x={253.5 + bayIndex * 29} y={y + 53} textAnchor="middle" className="rack-drive-label">{bay.label}</text></g>) : <><rect x="242" y={y + 34} width="230" height="32" rx="4" fill="url(#rackVent)" /><text x="357" y={y + 54} textAnchor="middle" className="rack-empty-label">{iloCredentialsReady ? "LOCAL STORAGE NOT READ" : "FIRST CONTACT REQUIRED"}</text></>}
          </>}
          {isNetapp && Array.from({ length: 24 }).map((_, bay) => <rect key={bay} x={158 + (bay % 12) * 27} y={y + 34 + Math.floor(bay / 12) * 22} width="21" height="16" rx="2" className="rack-shelf-bay" />)}
          {isEsxi && <><rect x="158" y={y + 32} width="190" height="15" rx="3" fill="url(#rackVent)" /><rect x="362" y={y + 33} width="22" height="12" rx="2" className="rack-port" /><rect x="390" y={y + 33} width="22" height="12" rx="2" className="rack-port" /><rect x="418" y={y + 33} width="22" height="12" rx="2" className="rack-port" /><circle cx="466" cy={y + 39} r="4" className="rack-host-led" /></>}
          {!isCisco && !isIlo && !isNetapp && !isEsxi && <rect x="158" y={y + 32} width="314" height={Math.max(15, height - 44)} rx="4" fill="url(#rackVent)" />}
        </g>;
      })}
    </svg>
  );
}

function RackInspector({ selected, word, bays, access, storage, storageMatchesDevice, onEdit, onAdd, onConfigure, onRemove }: {
  selected?: DeviceInventoryItem;
  word: RackWord;
  bays: RackBay[];
  access: IloAccessSettings | null;
  storage: HpeStorageDiscovery | null;
  storageMatchesDevice: boolean;
  onEdit: () => void;
  onAdd: () => void;
  onConfigure: () => void;
  onRemove: () => void;
}) {
  if (!selected) {
    return <aside className="rack-inspector rack-inspector-empty"><div className="rack-empty-icon"><Plus size={22} /></div><h2>Build your rack</h2><p>No devices are in this kit yet. Add the first piece of equipment without contacting it.</p><button className="rack-action is-primary" onClick={onAdd} type="button">Add first device</button></aside>;
  }
  const selectedKind = rackDeviceKind(selected);
  const isIlo = selectedKind === "ilo";
  const isEsxi = selectedKind === "esxi_host";
  const iloCredentialsReady = isIlo && Boolean(access?.username_configured && access.password_configured);
  const iloFirstContactComplete = isIlo && word === "Ready";
  const controllerName = storageMatchesDevice ? recordText(storage?.controllers?.[0], "model", "name", "id") ?? "Not read yet" : iloCredentialsReady ? "Not read yet" : "First contact required";
  const freeBays = bays.filter((bay) => bay.state === "free").length;
  const primaryRoute = devicePage(selected);
  const typeLabel = rackKindLabel(selectedKind, selected.device_type);
  const canConfigureBesideRack = rackConfigAvailable(selected);
  const statusDetail = word === "Ready"
    ? "Current cached evidence confirms access."
    : word === "Problem"
      ? "The latest cached check did not succeed."
      : "No current check proves access yet.";

  return (
    <aside className="rack-inspector" aria-live="polite">
      <div className={`rack-inspector-status is-${rackWordClass(word)}`}><span />{word}</div>
      <h2>{selected.display_name}</h2>
      <p className="rack-inspector-kind">{typeLabel} · {selected.dhcp_enabled ? "DHCP" : "static address"}</p>
      <p className="rack-evidence-note">{statusDetail}</p>
      {isIlo && <div className={`rack-first-contact ${iloFirstContactComplete ? "is-complete" : ""}`}>
        <span>{iloFirstContactComplete ? "First contact complete" : iloCredentialsReady ? "Step 3 of 3" : "Step 2 of 3"}</span>
        <strong>{iloFirstContactComplete ? "This iLO is proven reachable" : iloCredentialsReady ? "Verify this exact iLO address" : "Add the iLO username and password"}</strong>
        <small>{iloFirstContactComplete ? "You can now configure iLO and read local storage." : "The map stays unconfirmed until an explicit read-only check succeeds."}</small>
      </div>}
      {isIlo && bays.length > 0 && <div className="rack-bay-legend"><span className="is-boot">Boot volume</span><span className="is-data">Data volume</span><span className="is-free">Free / ready</span><span className="is-unknown">Unclassified</span></div>}
      <dl className="rack-facts">
        <div><dt>{selected.dhcp_enabled ? "Observed address" : "Address"}</dt><dd>{selected.host ?? (selected.dhcp_enabled ? "Not observed" : "Not set")}</dd></div>
        {isIlo && <div><dt>Credentials</dt><dd>{iloCredentialsReady ? "Saved locally" : "Still required"}</dd></div>}
        {isIlo && <div><dt>Controller</dt><dd>{controllerName}</dd></div>}
        {isIlo && <div><dt>Local storage</dt><dd>{storageMatchesDevice && bays.length ? `${bays.length} bays · ${freeBays} free` : iloCredentialsReady ? "Inventory not read" : "First contact required"}</dd></div>}
        <div><dt>Inventory updated</dt><dd>{new Date(selected.updated_at).toLocaleString()}</dd></div>
        <div><dt>Notes</dt><dd>{selected.notes || "None"}</dd></div>
      </dl>
      <div className="rack-actions">
        {isIlo && iloCredentialsReady
          ? <button className="rack-action is-primary" onClick={onConfigure} type="button">Configure iLO beside rack</button>
          : isIlo
          ? <button className="rack-action is-primary" onClick={onEdit} type="button">Continue: set up this iLO</button>
          : canConfigureBesideRack
          ? <button className="rack-action is-primary" onClick={onConfigure} type="button">{`Configure ${rackConfigLabel(selected)} beside rack`}</button>
          : <Link className="rack-action is-primary" to={primaryRoute}>{`Configure ${typeLabel}`}</Link>}
        {isIlo && <Link className="rack-action" to="/storage">Local storage &amp; RAID</Link>}
        {isEsxi && <Link className="rack-action" to="/virtualization">ESXi installation &amp; config</Link>}
        <button className="rack-action" onClick={onEdit} type="button"><Pencil size={14} /> Edit rack details</button>
        <button className="rack-action is-remove" onClick={onRemove} type="button"><Trash2 size={14} /> Remove from rack</button>
        <button className="rack-add-another" onClick={onAdd} type="button"><Plus size={14} /> Add another device</button>
      </div>
    </aside>
  );
}

// Operator surfaces never show raw runtime-mode vocabulary, so the rail says
// what the mode means for the operator rather than echoing the env value.
function railModeLabel(mode: string): string {
  const normalized = mode.trim().toLowerCase();
  if (!normalized || normalized === "unknown") return "Not known yet";
  if (normalized.includes("mock")) return "Test mode";
  if (normalized.includes("readwrite")) return "Live · guarded writes";
  return "Live · read-only";
}

function MachineInsidePanel({
  device,
  items,
  selectedItemId,
  storageRead,
  onSelectItem
}: {
  device: DeviceInventoryItem;
  items: InsideItem[];
  selectedItemId: string;
  storageRead: boolean;
  onSelectItem: (id: string) => void;
}) {
  const shared = items.filter((item) => item.kind === "shared");
  const owned = items.filter((item) => item.kind !== "shared");

  return (
    <section className="machine-inside" aria-label={`Inside ${device.display_name}`}>
      <header className="machine-inside-head">
        <div>
          <p className="operator-kicker">Inside {device.display_name}</p>
          <h2>Software and storage on this machine</h2>
        </div>
        <span>Select an item to configure it</span>
      </header>

      <div className="machine-inside-grid">
        {owned.map((item) => (
          <button
            aria-pressed={selectedItemId === item.id}
            className={`machine-item is-${item.kind} ${selectedItemId === item.id ? "is-selected" : ""}`}
            key={item.id}
            onClick={() => onSelectItem(item.id)}
            type="button"
          >
            <span className="machine-item-badge">{insideItemIcon(item.kind)} {item.badge}</span>
            <strong>{item.name}</strong>
            <small>{item.detail}</small>
          </button>
        ))}
      </div>

      {!storageRead && (
        <p className="machine-inside-empty">
          Local storage has not been read from this machine yet, so no datastores are listed.
          Run the read-only iLO storage read from <Link to="/storage">Local storage &amp; RAID</Link> to populate them.
        </p>
      )}

      {shared.length > 0 && (
        <div className="machine-inside-shared" aria-label="Shared storage available to this machine">
          {shared.map((item) => (
            <span className="machine-shared-chip" key={item.id}>
              <Database size={13} /> {item.name}
              <small>{item.detail}</small>
            </span>
          ))}
          <small className="machine-shared-note">
            Shared storage belongs to its own rack device — configure it there.
          </small>
        </div>
      )}
    </section>
  );
}

function MachineItemConfigPanel({
  bays,
  device,
  item,
  onClose
}: {
  bays: LocalRaidInventoryBay[];
  device: DeviceInventoryItem;
  item: InsideItem;
  onClose: () => void;
}) {
  const ownedBays = item.volumeLabel
    ? bays.filter((bay) => bay.currentLayout === item.volumeLabel)
    : [];

  return (
    <section className="machine-config" aria-label={`Configure ${item.name}`}>
      <header className="machine-config-head">
        <div>
          <p className="operator-kicker">Configure</p>
          <nav className="machine-crumbs" aria-label="Breadcrumb">
            <span>Rack</span> <span aria-hidden="true">›</span> <span>{device.display_name}</span> <span aria-hidden="true">›</span> <strong>{item.name}</strong>
          </nav>
        </div>
        <button onClick={onClose} type="button">Close</button>
      </header>

      {item.kind === "local" && (
        <div className="machine-config-body">
          <div className="machine-bay-map" aria-label="Drive bays in this chassis">
            <p className="operator-kicker">Drive bays in this chassis</p>
            {bays.length === 0 ? (
              <p className="machine-config-note">No drive inventory has been read from this machine yet.</p>
            ) : (
              <>
                <div className="machine-bay-grid">
                  {bays.map((bay) => (
                    <span
                      className={`machine-bay ${bay.currentLayout === item.volumeLabel ? "is-owned" : bay.currentLayout === "Unassigned" ? "is-free" : "is-other"}`}
                      key={bay.bay}
                      title={`${bay.label} · ${bay.currentLayout} · ${bay.detail}`}
                    >
                      {bay.bay}
                    </span>
                  ))}
                </div>
                <p className="machine-bay-legend">
                  <span className="is-owned" /> this datastore
                  <span className="is-other" /> other volumes
                  <span className="is-free" /> unassigned
                </p>
              </>
            )}
          </div>

          <dl className="machine-config-facts">
            <div><dt>Name</dt><dd>{item.name}</dd></div>
            <div><dt>Layout</dt><dd>{item.detail}</dd></div>
            <div><dt>Bays used</dt><dd>{ownedBays.length ? `${ownedBays.length} of ${bays.length}` : "Not read"}</dd></div>
          </dl>

          <div className="machine-config-actions">
            <Link className="machine-config-action" to="/storage">Open local storage &amp; RAID</Link>
            <span className="machine-config-guard">
              Changing RAID destroys data, so it stays behind the guarded workspace and its confirmations.
            </span>
          </div>
        </div>
      )}

      {item.kind === "vsan" && (
        <div className="machine-config-body">
          <p className="machine-config-note">
            {item.detail}. vSAN pools drives across every host in a cluster, so it is configured for the
            cluster rather than for this one machine.
          </p>
          <div className="machine-config-actions">
            <Link className="machine-config-action" to="/storage">Review vSAN readiness</Link>
            <span className="machine-config-guard">
              Read-only. Creating a vSAN datastore needs the cluster built first.
            </span>
          </div>
        </div>
      )}

      {item.kind === "hypervisor" && (
        <div className="machine-config-body">
          <p className="machine-config-note">{item.detail}.</p>
          <div className="machine-config-actions">
            <Link className="machine-config-action" to="/virtualization">Open ESXi &amp; virtualization</Link>
            <span className="machine-config-guard">
              Installing or reconfiguring ESXi stays behind its guarded workflow.
            </span>
          </div>
        </div>
      )}
    </section>
  );
}

function RemoveDeviceDialog({
  device,
  onCancel,
  onRemoved
}: {
  device: DeviceInventoryItem;
  onCancel: () => void;
  onRemoved: () => Promise<void> | void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function remove() {
    setBusy(true);
    setError("");
    try {
      await api.deleteDevice(device.id);
      await onRemoved();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="rack-remove-overlay" role="dialog" aria-modal="true" aria-label={`Remove ${device.display_name} from the rack`}>
      <div className="rack-remove-panel">
        <p className="operator-kicker">Remove from rack</p>
        <h2>{device.display_name}</h2>
        <p>
          This removes the rack record for {device.display_name}
          {device.host ? ` (${device.host})` : ""} and any access details saved against it.
        </p>
        <p className="rack-remove-safe">
          The hardware itself is never contacted or changed. You can add it back at any time.
        </p>
        {error && <p className="rack-remove-error" role="alert">{error}</p>}
        <div className="rack-remove-actions">
          <button disabled={busy} onClick={onCancel} type="button">Keep it</button>
          <button className="is-destructive" disabled={busy} onClick={() => void remove()} type="button">
            {busy ? "Removing…" : "Remove from rack"}
          </button>
        </div>
      </div>
    </div>
  );
}

function railLinkClass({ isActive }: { isActive: boolean }): string {
  return isActive ? "is-active" : "";
}

type RackRailData = {
  deviceCount: number;
  profile: LabProfileList["active_profile"] | null;
  mode: string;
  loadError: string | null;
};

function useRackRailData(): RackRailData {
  const [data, setData] = useState<RackRailData>({ deviceCount: 0, profile: null, mode: "unknown", loadError: null });
  useEffect(() => {
    let cancelled = false;
    void Promise.allSettled([api.health(), api.deviceInventory(), api.labProfiles()]).then(([healthResult, devicesResult, profilesResult]) => {
      if (cancelled) return;
      if (healthResult.status === "rejected" && devicesResult.status === "rejected") {
        setData((current) => ({ ...current, loadError: "Lab Builder cannot reach its local backend." }));
        return;
      }
      const health = healthResult.status === "fulfilled" ? healthResult.value : null;
      const devices = devicesResult.status === "fulfilled" ? devicesResult.value : [];
      const profiles = profilesResult.status === "fulfilled" ? profilesResult.value : null;
      setData({
        deviceCount: devices.length,
        profile: profiles?.active_profile ?? null,
        mode: health?.provider_mode ?? health?.operator_runtime_mode ?? "unknown",
        loadError: null
      });
    });
    return () => {
      cancelled = true;
    };
  }, []);
  return data;
}

export function RackRail() {
  const { deviceCount, profile, mode, loadError } = useRackRailData();

  return (
    <aside className="rack-rail">
      <div className="rack-brand"><span>L</span><div><strong>Lab Builder</strong><small>{profile?.name ?? "Current kit"}</small></div></div>
      <nav aria-label="Lab Builder navigation">
        <p>Console</p>
        <NavLink className={railLinkClass} to="/simple"><Layers3 size={17} /> Rack home</NavLink>
        <NavLink className={railLinkClass} to="/simple-steps"><ListChecks size={17} /> Runbook</NavLink>
        <p>Manage</p>
        <NavLink className={railLinkClass} to="/setup/defaults"><Settings2 size={17} /> Lab defaults</NavLink>
        <NavLink className={railLinkClass} to="/firmware-upgrades"><Cpu size={17} /> Firmware</NavLink>
        <NavLink className={railLinkClass} to="/run-center"><PlayCircle size={17} /> Run Center</NavLink>
        <NavLink className={railLinkClass} to="/validation"><FileText size={17} /> Reports</NavLink>
        <NavLink className={railLinkClass} to="/lab-profiles#new"><Plus size={17} /> Create or change kit</NavLink>
      </nav>
      <dl className="rack-rail-facts">
        <div><dt>Subnet</dt><dd>{loadError ? "Unavailable" : profile?.subnet_cidr ?? "Not set"}</dd></div>
        <div><dt>Rack</dt><dd>{loadError ? "Unavailable" : `R1 · ${deviceCount} devices`}</dd></div>
        <div><dt>Mode</dt><dd>{loadError ? "Disconnected" : railModeLabel(mode)}</dd></div>
      </dl>
    </aside>
  );
}

export function SimpleLabPage() {
  const { devices, providers, accessByDeviceId, storage, vsan, profiles, health, loaded, loadError, reload } = useSimpleData();
  const visibleIds = devices.map((device) => device.id);
  const visibleKey = visibleIds.join("|");
  const [selectedId, setSelectedId] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [editingDevice, setEditingDevice] = useState<DeviceInventoryItem | null>(null);
  const [configuringId, setConfiguringId] = useState("");
  const [selectedItemId, setSelectedItemId] = useState("");
  const [removingDevice, setRemovingDevice] = useState<DeviceInventoryItem | null>(null);
  useEffect(() => {
    if (visibleIds.length && !visibleIds.includes(selectedId)) setSelectedId(visibleIds[0]);
    if (!visibleIds.length && selectedId) setSelectedId("");
  }, [selectedId, visibleKey]);
  useEffect(() => {
    if (!configuringId) return;
    window.requestAnimationFrame(() => {
      const header = document.querySelector<HTMLElement>(".rack-workspace-head");
      header?.scrollIntoView?.({ block: "start", behavior: "smooth" });
    });
  }, [configuringId]);
  const bays = rackBays(vsan);
  const selected = devices.find((device) => device.id === selectedId) ?? devices[0];
  const selectedAccess = selected ? accessByDeviceId[selected.id] ?? null : null;
  const selectedWord: RackWord = selected ? deviceWord(selected, providers, selectedAccess) : "Not checked";
  const storageProbeTime = storage?.last_probe_time || vsan?.last_probe_time || null;
  const storageDeviceId = storageProbeTime
    ? devices.find((device) => (
        rackDeviceKind(device) === "ilo" &&
        accessByDeviceId[device.id]?.last_probe_time === storageProbeTime &&
        accessByDeviceId[device.id]?.last_probe_target_matches_access_host === true
      ))?.id ?? ""
    : "";
  const editingIloAccess = editingDevice ? accessByDeviceId[editingDevice.id] ?? null : null;
  const profile = profiles?.active_profile;
  const mode = health?.provider_mode ?? health?.operator_runtime_mode ?? "unknown";

  // The inside/configure levels only describe machines that actually host
  // software. A switch or a filer has no hypervisor or local datastores here.
  const selectedKind = selected ? rackDeviceKind(selected) : "";
  const insideAvailable = selectedKind === "ilo" || selectedKind === "server" || selectedKind === "esxi_host";
  // Storage evidence is only this machine's when the cached probe targeted it.
  const storageMatchesSelected = Boolean(selected && selected.id === storageDeviceId);
  const machineStorage = storageMatchesSelected ? storage : null;
  const machineVsan = storageMatchesSelected ? vsan : null;
  const machineItems = insideAvailable
    ? insideItems(machineStorage, machineVsan, devices, providers)
    : [];
  const selectedItem = machineItems.find((item) => item.id === selectedItemId) ?? null;
  const chassisBays = localRaidInventoryBays(machineStorage);

  // Selecting a different device invalidates the item drilled into below it.
  useEffect(() => {
    setSelectedItemId("");
  }, [selectedId]);

  return (
    <main className="rack-light-page" aria-label="Rack elevation">
      <p className="rack-direction"><span /> Rack workspace · cached evidence only</p>
      <section className="rack-workspace">
        <header className="rack-workspace-head"><div><h1>Rack elevation</h1><p>Add equipment, select it, then configure it.</p></div><div className="rack-workspace-head-actions"><span className={`rack-runtime-badge ${loadError ? "is-disconnected" : mode.includes("readwrite") ? "is-write" : ""}`}>{loadError ? "Backend disconnected" : mode.includes("readwrite") ? "Live lab · guarded writes" : "Live lab · read-only checks"}</span><button className="rack-head-add" disabled={Boolean(loadError)} onClick={() => setAddOpen(true)} type="button"><Plus size={15} /> Add equipment</button></div></header>
        {loaded && !loadError && (
          <RackWorkspaceSummary
            accessByDeviceId={accessByDeviceId}
            bays={bays}
            devices={devices}
            mode={mode}
            providers={providers}
            selected={selected}
            word={selectedWord}
          />
        )}
        {!loaded
          ? <div className="rack-loading"><Server size={24} /> Reading cached lab state…</div>
          : loadError
            ? <div className="rack-disconnected" role="alert"><Server size={30} /><h2>Backend disconnected</h2><p>{loadError}</p><button onClick={() => void reload()} type="button">Reconnect</button><small>Adding or changing equipment is paused so a connection failure cannot look like an empty rack or a successful save.</small></div>
            : <div className={`rack-stage ${configuringId ? "is-configuring" : ""}`}><div className="rack-canvas"><RackElevationGraphic devices={devices} providers={providers} accessByDeviceId={accessByDeviceId} bays={bays} storageDeviceId={storageDeviceId} selectedId={selected?.id ?? ""} onSelect={(id) => { setSelectedId(id); setConfiguringId(""); }} /></div><div className="rack-detail">{configuringId && selected?.id === configuringId && rackDeviceKind(selected) === "ilo" ? <RackIloConfigurator activeProfile={profile ?? null} device={selected} onClose={() => setConfiguringId("")} onReload={reload} /> : configuringId && selected?.id === configuringId && rackConfigAvailable(selected) ? <RackDeviceConfigurator activeProfile={profile ?? null} device={selected} health={health} onClose={() => setConfiguringId("")} onReload={reload} /> : <><RackInspector selected={selected} word={selectedWord} bays={bays} access={selectedAccess} storage={storage} storageMatchesDevice={Boolean(selected && selected.id === storageDeviceId)} onEdit={() => selected && setEditingDevice(selected)} onAdd={() => setAddOpen(true)} onConfigure={() => selected && setConfiguringId(selected.id)} onRemove={() => selected && setRemovingDevice(selected)} /><p className="rack-help">Select a device, then configure its essential settings beside the rack. Green is shown only when a current provider check proves access.</p></>}</div></div>}
        {loaded && !loadError && selected && insideAvailable && (
          <MachineInsidePanel
            device={selected}
            items={machineItems}
            selectedItemId={selectedItemId}
            storageRead={storageMatchesSelected && Boolean(storage?.storage_inventory_available)}
            onSelectItem={(id) => setSelectedItemId((current) => (current === id ? "" : id))}
          />
        )}
        {loaded && !loadError && selected && selectedItem && (
          <MachineItemConfigPanel
            bays={chassisBays}
            device={selected}
            item={selectedItem}
            onClose={() => setSelectedItemId("")}
          />
        )}
      </section>
      {removingDevice && (
        <RemoveDeviceDialog
          device={removingDevice}
          onCancel={() => setRemovingDevice(null)}
          onRemoved={async () => {
            setRemovingDevice(null);
            setSelectedId("");
            setConfiguringId("");
            setSelectedItemId("");
            await reload();
          }}
        />
      )}
      {addOpen && <DeviceInventoryForm defaultDeviceType="ilo" iloOnboarding onClose={() => setAddOpen(false)} onReload={reload} onSaved={(device) => setSelectedId(device.id)} submitLabel="Add to rack" />}
      {editingDevice && <DeviceInventoryForm device={editingDevice} iloOnboarding initialIloUsername={editingIloAccess?.username} iloCredentialsConfigured={Boolean(editingIloAccess?.username_configured && editingIloAccess.password_configured)} onClose={() => setEditingDevice(null)} onReload={reload} onSaved={(device) => setSelectedId(device.id)} submitLabel="Save rack details" />}
    </main>
  );
}

type StepState = "done" | "next" | "waiting";

export function SimpleStepsPage() {
  const { devices, providers, accessByDeviceId, storage, loaded } = useSimpleData();

  const iloDevices = devices.filter((device) => rackDeviceKind(device) === "ilo");
  const iloReady = iloDevices.length > 0 && iloDevices.every((device) => {
    const access = accessByDeviceId[device.id];
    return (
      access?.last_probe_status === "ok" &&
      access.last_probe_is_current === true &&
      access.last_probe_target_matches_access_host === true &&
      access.last_probe_target_fingerprint_present === true
    );
  });
  const inventoryRead = Boolean(storage?.storage_inventory_available);
  const esxiProvider = providers.find((item) => item.id === "esxi-readonly");
  const esxiReady = esxiProvider?.status === "ready" || esxiProvider?.status === "ok";

  const steps: Array<{ title: string; detail: string; done: boolean; to: string }> = [
    {
      title: "Reach the iLO",
      detail: iloReady ? "Proven reachable with current evidence." : "Save access and run the iLO check.",
      done: Boolean(iloReady),
      to: "/server"
    },
    {
      title: "Read the hardware",
      detail: inventoryRead ? "Drive inventory is loaded from the server." : "Run the iLO inventory read.",
      done: inventoryRead,
      to: "/storage"
    },
    {
      title: "Decide the storage layout",
      detail: "Review the drive plan (and vSAN readiness once available).",
      done: false,
      to: "/storage"
    },
    {
      title: "Reach ESXi",
      detail: esxiReady ? "ESXi answers with current evidence." : "Validate the ESXi target.",
      done: Boolean(esxiReady),
      to: "/virtualization"
    },
    {
      title: "Deploy the VM",
      detail: "Run the guarded VM deploy once everything above is green.",
      done: false,
      to: "/virtualization"
    }
  ];
  const nextIndex = steps.findIndex((step) => !step.done);

  return (
    <main className="simple-page" aria-label="Runbook view (example)">
      <header className="simple-head">
        <h1>Build the lab, in order</h1>
        <p className="simple-sub">
          Return to <Link to="/simple">Rack home</Link>. Each step opens the controls for the device it needs.
        </p>
      </header>
      {!loaded && <p className="simple-loading">Loading…</p>}
      <ol className="simple-steps">
        {steps.map((step, index) => {
          const state: StepState = step.done ? "done" : index === nextIndex ? "next" : "waiting";
          return (
            <li className={`simple-step is-${state}`} key={step.title}>
              <span className="simple-step-number">{index + 1}</span>
              <div className="simple-step-body">
                <strong>{step.title}</strong>
                <span>{step.detail}</span>
              </div>
              <Link className="simple-step-go" to={step.to}>
                {state === "done" ? "Review" : "Go"} →
              </Link>
            </li>
          );
        })}
      </ol>
    </main>
  );
}
