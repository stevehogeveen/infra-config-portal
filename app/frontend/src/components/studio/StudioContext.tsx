import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { api, partsUpdateApi, sppUpdateApi, windowsApi, type RaidOperationStatus } from "../../api";
import type { IloAccessSettings, LabProfile } from "../../types";
import type { PlannedEquipment, RackPlan } from "../RackPlanner";

// Everything here is read from existing GET endpoints: saved plan, saved access settings with
// their recorded probe evidence, and the recorded storage operation. Nothing contacts hardware.

/**
 * Same window the backend uses for probe evidence (DEFAULT_STALE_AFTER_SECONDS in
 * app/backend/app/services/status_source.py): a check is current for 24 hours after checked_at.
 * The backend decides freshness when the page loads; this keeps it honest while the page stays open.
 */
export const PROOF_STALE_AFTER_MS = 24 * 60 * 60 * 1000;

export type StorageRead = { state: "ok"; status: RaidOperationStatus } | { state: "unavailable"; message: string } | { state: "loading" };

export type DeviceEvidence = {
  id: string;
  deviceId: string | null;
  name: string;
  kind: PlannedEquipment["kind"];
  model: string;
  position: number;
  height: number;
  access: IloAccessSettings | null;
  /** The access-settings read failed; nothing is known about this server's last check. */
  accessUnavailable: boolean;
  /** Current, target-bound, successful read-only check. The only state that may render green. */
  proven: boolean;
  /** A check was recorded but did not succeed, or it is no longer current for the saved target. */
  attention: "failed" | "stale" | null;
  answeredAt: string | null;
  storage: RaidOperationStatus | null;
  storageRead: StorageRead | null;
  /** Recorded, verified completion per later step; null while unread or unreadable. */
  milestones: Milestones | null;
};

export type Milestones = { firmware: boolean; esxi: boolean; windows: boolean };

export type StudioData = {
  profileId: string | null;
  profileName: string;
  plan: RackPlan | null;
  planSaved: boolean;
  draftPending: boolean;
  networkSaved: boolean;
  devices: DeviceEvidence[];
  loading: boolean;
  selectedId: string;
  select: (id: string) => void;
  selected: DeviceEvidence | null;
  refresh: () => void;
  drawerOpen: boolean;
  setDrawerOpen: (open: boolean) => void;
  paletteOpen: boolean;
  setPaletteOpen: (open: boolean) => void;
};

const StudioContext = createContext<StudioData | null>(null);

export function useStudio() {
  return useContext(StudioContext);
}

export const STUDIO_REFRESH_EVENT = "studio:refresh";
export function requestStudioRefresh() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(STUDIO_REFRESH_EVENT));
}

const DRAWER_KEY = "lab-builder-evidence-drawer";
function readDrawer() {
  try { return window.localStorage.getItem(DRAWER_KEY) !== "closed"; } catch { return true; }
}

function proofAge(access: IloAccessSettings, now: number) {
  const checked = access.last_probe_time ? Date.parse(access.last_probe_time) : NaN;
  return Number.isNaN(checked) ? Infinity : now - checked;
}

export function isProven(access: IloAccessSettings | null | undefined, now: number = Date.now()) {
  return !!access && access.last_probe_status === "ok" && !!access.last_probe_time && access.last_probe_is_current
    && access.last_probe_target_matches_access_host && proofAge(access, now) <= PROOF_STALE_AFTER_MS;
}

function attentionFor(access: IloAccessSettings | null, now: number): DeviceEvidence["attention"] {
  if (!access?.last_probe_time) return null;
  if (isProven(access, now)) return null;
  return access.last_probe_status === "ok" ? "stale" : "failed";
}

/** One kit's evidence. It is only ever shown while its profileId is the active one. */
type Snapshot = {
  profileId: string;
  plan: RackPlan | null;
  access: Record<string, IloAccessSettings | null>;
  accessFailed: Record<string, boolean>;
  storage: Record<string, StorageRead>;
  milestones: Record<string, Milestones>;
  loading: boolean;
};

const emptySnapshot = (profileId: string): Snapshot => ({ profileId, plan: null, access: {}, accessFailed: {}, storage: {}, milestones: {}, loading: true });

// Stored evidence only: each status endpoint returns recorded results and never contacts hardware.
async function readMilestones(profileId: string, deviceId: string): Promise<Milestones | null> {
  try {
    const [parts, spp, esxi, windows] = await Promise.all([
      partsUpdateApi.status(profileId, deviceId).catch(() => null),
      sppUpdateApi.status(profileId, deviceId).catch(() => null),
      api.esxiInstall(profileId, deviceId).catch(() => null),
      windowsApi.status(profileId, deviceId).catch(() => null),
    ]);
    return {
      firmware: (parts?.state === "verified" && !parts.active) || (spp?.status === "verified" && !spp.active),
      esxi: esxi?.state === "verified",
      windows: windows?.state === "verified",
    };
  } catch { return null; }
}

export function StudioProvider({ profile, children }: { profile: LabProfile | null; children: ReactNode }) {
  const location = useLocation();
  const profileId = profile?.id ?? null;
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [tick, setTick] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const [selectedId, setSelectedId] = useState("");
  const [drawerOpen, setDrawerState] = useState(readDrawer);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [draftPending, setDraftPending] = useState(false);
  const requestId = useRef(0);
  const requestedDevice = new URLSearchParams(location.search).get("device");

  const refresh = useCallback(() => setTick(value => value + 1), []);
  useEffect(() => {
    window.addEventListener(STUDIO_REFRESH_EVENT, refresh);
    return () => window.removeEventListener(STUDIO_REFRESH_EVENT, refresh);
  }, [refresh]);

  // A kit change drops the previous kit's evidence and selection at once.
  const [shownProfile, setShownProfile] = useState(profileId);
  if (shownProfile !== profileId) {
    setShownProfile(profileId);
    setSnapshot(profileId ? emptySnapshot(profileId) : null);
    setSelectedId("");
  }

  useEffect(() => {
    const id = ++requestId.current;
    if (!profileId) { setSnapshot(null); return; }
    const current = () => id === requestId.current;
    const update = (change: (value: Snapshot) => Snapshot) => {
      if (!current()) return;
      setSnapshot(value => value && value.profileId === profileId ? change(value) : value);
    };
    setSnapshot(value => value && value.profileId === profileId ? { ...value, loading: true } : emptySnapshot(profileId));
    api.rackPlan(profileId).then(async next => {
      if (!current()) return;
      const servers = next.equipment.filter(item => item.kind === "server" && item.device_id);
      update(value => ({ ...value, plan: next, storage: Object.fromEntries(servers.map(item => [item.device_id!, value.storage[item.device_id!] ?? { state: "loading" } as StorageRead])) }));
      const accessRows = await Promise.all(servers.map(item => api.iloAccessSettings(item.device_id!)
        .then(value => [item.device_id!, value, false] as const).catch(() => [item.device_id!, null, true] as const)));
      update(value => ({ ...value, access: Object.fromEntries(accessRows.map(([key, row]) => [key, row])), accessFailed: Object.fromEntries(accessRows.map(([key, , failed]) => [key, failed])) }));
      const storageRows = await Promise.all(servers.map(item => api.raidOperationStatus(profileId, item.device_id!)
        .then(status => [item.device_id!, { state: "ok", status } as StorageRead] as const)
        .catch(err => [item.device_id!, { state: "unavailable", message: err instanceof Error ? err.message : String(err) } as StorageRead] as const)));
      update(value => ({ ...value, storage: Object.fromEntries(storageRows) }));
      const milestoneRows = await Promise.all(servers.map(async item => [item.device_id!, await readMilestones(profileId, item.device_id!)] as const));
      update(value => ({ ...value, milestones: Object.fromEntries(milestoneRows.filter(([, row]) => row).map(([key, row]) => [key, row!])), loading: false }));
    }).catch(() => update(value => ({ ...value, plan: null, loading: false })));
  }, [profileId, location.pathname, tick]);

  // Proof ages out while the page stays open: re-evaluate every minute and exactly at the next expiry.
  useEffect(() => {
    const expiries = Object.values(snapshot?.access ?? {})
      .map(row => row?.last_probe_time ? Date.parse(row.last_probe_time) + PROOF_STALE_AFTER_MS + 1 - Date.now() : NaN)
      .filter(ms => Number.isFinite(ms) && ms > 0);
    const wait = Math.min(60_000, ...expiries);
    const timer = window.setTimeout(() => setNow(Date.now()), wait);
    return () => window.clearTimeout(timer);
  }, [snapshot, now]);

  useEffect(() => {
    if (!profileId) return;
    try { setDraftPending(!!window.localStorage.getItem(`rack-workbench-draft-v1:${profileId}`)); } catch { setDraftPending(false); }
  }, [profileId, location.pathname, tick, snapshot?.plan]);

  const active = snapshot && snapshot.profileId === profileId ? snapshot : null;
  const plan = active?.plan ?? null;
  const devices = useMemo<DeviceEvidence[]>(() => (plan?.equipment ?? [])
    .slice()
    .sort((a, b) => b.position - a.position)
    .map(item => {
      const itemAccess = item.device_id ? active?.access[item.device_id] ?? null : null;
      const storageRead = item.device_id && item.kind === "server" ? active?.storage[item.device_id] ?? { state: "loading" } as StorageRead : null;
      return {
        id: item.id, deviceId: item.device_id ?? null, name: item.name, kind: item.kind, model: item.model,
        position: item.position, height: item.height, access: itemAccess,
        accessUnavailable: !!(item.device_id && active?.accessFailed[item.device_id]),
        proven: isProven(itemAccess, now), attention: attentionFor(itemAccess, now), answeredAt: itemAccess?.last_probe_time ?? null,
        storage: storageRead?.state === "ok" ? storageRead.status : null, storageRead,
        milestones: item.device_id ? active?.milestones[item.device_id] ?? null : null,
      };
    }), [plan, active, now]);

  // The address picks the selection only when it changes (or first resolves); later evidence
  // refreshes must not undo a selection the operator made on the page.
  const appliedUrl = useRef<string | null>(null);
  useEffect(() => {
    if (!devices.length) return;
    const fromUrl = requestedDevice ? devices.find(item => item.deviceId === requestedDevice || item.id === requestedDevice) : null;
    if (fromUrl && appliedUrl.current !== requestedDevice) { appliedUrl.current = requestedDevice; setSelectedId(fromUrl.id); return; }
    setSelectedId(current => devices.some(item => item.id === current) ? current : (devices.find(item => item.kind === "server") ?? devices[0]).id);
  }, [devices, requestedDevice]);

  const setDrawerOpen = useCallback((open: boolean) => {
    setDrawerState(open);
    try { window.localStorage.setItem(DRAWER_KEY, open ? "open" : "closed"); } catch { /* per-page only */ }
  }, []);

  const drawerRef = useRef(drawerOpen);
  drawerRef.current = drawerOpen;
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const typing = !!target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));
      // Never open a Studio overlay over an open dialog (for example a destructive confirmation).
      const dialogOpen = !!document.querySelector("dialog[open], [role=dialog][aria-modal=true]:not(.sd-palette)");
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        if (dialogOpen) return;
        event.preventDefault(); setPaletteOpen(open => !open); return;
      }
      if (typing || event.ctrlKey || event.metaKey || event.altKey || dialogOpen || document.querySelector(".sd-palette")) return;
      if (event.key === "e" || event.key === "E") { event.preventDefault(); setDrawerOpen(!drawerRef.current); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setDrawerOpen]);

  const planSaved = !!plan && plan.revision > 0 && plan.equipment.length > 0 && plan.equipment.every(item => !!item.device_id);
  const networkSaved = !!profile && profile.source === "saved" && !!(profile.subnet_cidr || profile.gateway);
  const selected = devices.find(item => item.id === selectedId) ?? null;
  const value: StudioData = {
    profileId, profileName: profile?.name ?? "", plan, planSaved, draftPending, networkSaved, devices,
    loading: !active || active.loading,
    selectedId, select: setSelectedId, selected, refresh, drawerOpen, setDrawerOpen, paletteOpen, setPaletteOpen,
  };
  return <StudioContext.Provider value={value}>{children}</StudioContext.Provider>;
}
