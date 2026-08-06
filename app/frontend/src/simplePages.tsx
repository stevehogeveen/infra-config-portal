import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "./api";
import type { DeviceInventoryItem, HpeStorageDiscovery, IloAccessSettings, ProviderStatus } from "./types";

// Two EXAMPLE simplified default pages, deliberately additive-only:
// nothing in the existing app changes until Steve picks a direction.
//   /simple        "Lab at a glance"  - one huge tile per device, one action each
//   /simple-steps  "Runbook"          - the lab as five giant ordered steps
// Both read only cheap, already-cached data. No probes fire from here.

type SimpleData = {
  devices: DeviceInventoryItem[];
  providers: ProviderStatus[];
  access: IloAccessSettings | null;
  storage: HpeStorageDiscovery | null;
  loaded: boolean;
};

function useSimpleData(): SimpleData {
  const [data, setData] = useState<SimpleData>({
    devices: [],
    providers: [],
    access: null,
    storage: null,
    loaded: false
  });

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const [devices, providers, access, storage] = await Promise.all([
        api.deviceInventory().catch(() => [] as DeviceInventoryItem[]),
        api.providers().catch(() => [] as ProviderStatus[]),
        api.iloAccessSettings().catch(() => null),
        api.hpeStorageDiscovery().catch(() => null)
      ]);
      if (!cancelled) {
        setData({ devices, providers, access, storage, loaded: true });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return data;
}

const PROVIDER_BY_TYPE: Record<string, string> = {
  ilo: "ilo-redfish",
  esxi_host: "esxi-readonly",
  cisco_switch: "cisco-ansible",
  netapp: "netapp-ontap"
};

function deviceWord(device: DeviceInventoryItem, providers: ProviderStatus[]): "Ready" | "Problem" | "Not checked" {
  const provider = providers.find((item) => item.id === PROVIDER_BY_TYPE[device.device_type]);
  if (!provider || provider.status === "not_checked" || provider.freshness === "not_checked") {
    return "Not checked";
  }
  if (provider.status === "ready" || provider.status === "ok") {
    return "Ready";
  }
  return "Problem";
}

function devicePage(device: DeviceInventoryItem): string {
  if (device.device_type === "ilo") return "/server";
  if (device.device_type === "esxi_host") return "/virtualization";
  if (device.device_type === "cisco_switch") return "/network";
  if (device.device_type === "netapp") return "/storage";
  return "/overview";
}

export function SimpleLabPage() {
  const { devices, providers, loaded } = useSimpleData();
  const words = devices.map((device) => deviceWord(device, providers));
  const firstUnready = devices.find((_, index) => words[index] !== "Ready");

  return (
    <main className="simple-page" aria-label="Simple lab view (example)">
      <header className="simple-head">
        <h1>Your lab</h1>
        <p className="simple-sub">
          Example simplified view. The full map stays at <Link to="/overview">Overview</Link>; the
          step-by-step example is at <Link to="/simple-steps">Runbook</Link>.
        </p>
      </header>
      {!loaded && <p className="simple-loading">Loading…</p>}
      <div className="simple-tiles">
        {devices.map((device, index) => (
          <Link className={`simple-tile is-${words[index].replace(" ", "-").toLowerCase()}`} key={device.id} to={devicePage(device)}>
            <span className="simple-tile-status">{words[index]}</span>
            <strong>{device.display_name}</strong>
            <span className="simple-tile-host">
              {device.host || "No address yet"}
              {device.dhcp_enabled ? " · DHCP" : ""}
            </span>
            <span className="simple-tile-go">Open →</span>
          </Link>
        ))}
      </div>
      {loaded && (
        <footer className="simple-next">
          {firstUnready
            ? <>Next: check <strong>{firstUnready.display_name}</strong> — it is not confirmed ready.</>
            : <>Everything reachable is confirmed. Nothing needs you right now.</>}
        </footer>
      )}
    </main>
  );
}

type StepState = "done" | "next" | "waiting";

export function SimpleStepsPage() {
  const { providers, access, storage, loaded } = useSimpleData();

  const iloReady = access?.last_probe_status === "ok" && access?.last_probe_is_current === true;
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
          Example simplified view. Tiles example at <Link to="/simple">Your lab</Link>; the full map
          stays at <Link to="/overview">Overview</Link>.
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
