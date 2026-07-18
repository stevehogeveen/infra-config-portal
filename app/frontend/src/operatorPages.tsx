import {
  Activity,
  Ban,
  CheckCircle2,
  Database,
  EthernetPort,
  Gauge,
  HardDrive,
  Layers,
  Play,
  RefreshCw,
  Route,
  Save,
  Server,
  ShieldCheck,
  Wrench
} from "lucide-react";
import { createContext, FormEvent, ReactNode, useContext, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { api } from "./api";
import { OperatorHomeView } from "./components/operator/OperatorHomeView";
import {
  ActionLink,
  BlockerItem,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CompactTable,
  CompactTableCell,
  CompactTableHeader,
  CompactTableRow,
  RemediationLadder,
  type RemediationStep,
  StatusBadge,
  type StatusBadgeStatus
} from "./components/ui";
import type {
  AiChangeRequest,
  AuditEvent,
  FirmwareFileCandidate,
  FirmwareFileSelections,
  FirmwareSummary,
  FirmwareUpgradePath,
  HpeRaidPlanPreview,
  LabAddressPlan,
  LabProfile,
  LabProfileFeatures,
  LabProfileList,
  LabProfileWrite,
  LabSafetySettings,
  LabSafetySettingsWrite,
  LabValidationItem,
  LabValidationSummary,
  ProviderProbeResult,
  ProviderStatus,
  UiIntentOp,
  UiIntentRegion,
  UiIntentRegionLayout,
  WorkflowAction,
  WorkflowActionDiagnosis,
  WorkflowActionRun,
  WorkflowActionRunRequest
} from "./types";
import { buildOperatorHomeModel } from "./operatorHomeModel";

type HealthLike = {
  expected_runtime_mode?: string;
  host_ipv4_addresses?: string[];
  lab_subnet_cidr?: string | null;
  operator_runtime_mode?: string;
  provider_mode?: string;
  status?: string;
} | null;

type OperatorPageProps = {
  health?: HealthLike;
  isAdvancedMode?: boolean;
  labProfileError?: string;
  labProfileLoading?: boolean;
  labProfileState: LabProfileList | null;
  onReloadLabProfile?: () => Promise<void>;
};

type OperatorTabId =
  | "overview"
  | "network"
  | "server"
  | "storage"
  | "virtualization"
  | "firmware"
  | "validation";

type OperatorRunStatus = {
  actionId?: string;
  message: string;
  state: "idle" | "running" | "success" | "error";
};

type SettingsProfileEditState = {
  blockLegacyProtocols: boolean;
  description: string;
  disableIpv6: boolean;
  domainName: string;
  enableDns: boolean;
  enableNtp: boolean;
  enableSnmp: boolean;
  enableVcenter: boolean;
  name: string;
  storageProtocol: string;
  timezone: string;
};

type OperatorTabStateContextValue = {
  activeTab: OperatorTabId;
  runStatus: Record<OperatorTabId, OperatorRunStatus>;
  setRunStatus: (tabId: OperatorTabId, status: OperatorRunStatus) => void;
};

const operatorTabs: OperatorTabId[] = [
  "overview",
  "network",
  "server",
  "storage",
  "virtualization",
  "firmware",
  "validation"
];

const idleRunStatus: OperatorRunStatus = {
  message: "",
  state: "idle"
};

const OperatorTabStateContext = createContext<OperatorTabStateContextValue | null>(null);

export function OperatorTabStateProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const activeTab = tabFromPath(location.pathname);
  const [runStatus, setRunStatusState] = useState<Record<OperatorTabId, OperatorRunStatus>>(() =>
    operatorTabs.reduce((accumulator, tabId) => {
      accumulator[tabId] = idleRunStatus;
      return accumulator;
    }, {} as Record<OperatorTabId, OperatorRunStatus>)
  );

  function setRunStatus(tabId: OperatorTabId, status: OperatorRunStatus) {
    setRunStatusState((current) => ({
      ...current,
      [tabId]: status
    }));
  }

  return (
    <OperatorTabStateContext.Provider
      value={{
        activeTab,
        runStatus,
        setRunStatus
      }}
    >
      {children}
    </OperatorTabStateContext.Provider>
  );
}

function useOperatorTabState() {
  const context = useContext(OperatorTabStateContext);
  if (!context) {
    throw new Error("Operator tab state is unavailable.");
  }
  return context;
}

function tabFromPath(pathname: string): OperatorTabId {
  if (pathname.startsWith("/firmware")) return "firmware";
  if (pathname.startsWith("/validation")) return "validation";
  return "overview";
}

type ConfigValue = {
  label: string;
  source?: string;
  status?: string;
  value: string;
};

type CurrentViewModel = {
  available: boolean;
  blockers: string[];
  checkedAt: string;
  details: ConfigValue[];
  fixSteps: string[];
  freshness: string;
  recheckCommand: string;
  scanDetail: string;
  scanLabel: string;
  source: string;
  status: string;
  summary: string;
  warnings: string[];
};

type CurrentViewModelInput = {
  available: boolean;
  blockers?: Array<string | undefined | null>;
  checkedAt?: string | null;
  details: ConfigValue[];
  fixSteps: Array<string | undefined | null>;
  freshness?: string;
  recheckCommand?: string;
  scanDetail: string;
  scanLabel: string;
  signals?: unknown[];
  source?: string;
  status: string;
  summary: string;
  warnings?: Array<string | undefined | null>;
};

type OperatorObjectRow = {
  checkedAt?: string;
  details: ConfigValue[];
  freshness?: string;
  id: string;
  nextAction: string;
  source?: string;
  status: string;
  summary: string;
  target: string;
  title: string;
  type: string;
  warnings?: string[];
  blockers?: string[];
};

type AccessRow = {
  appSees: string;
  item: string;
  needs: string;
  status: string;
  target: string;
};

type InventoryRow = {
  accessTarget: string;
  item: string;
  role: string;
  source: string;
  status: string;
  version: string;
};

type OverviewFirmwareRow = {
  action: string;
  device: string;
  status: string;
  target: string;
  version: string;
};

type RunButtonDefinition = {
  actionIds?: string[];
  allowBlockedRun?: boolean;
  disabledReason?: string;
  icon?: ReactNode;
  kind?: "read" | "write" | "apply" | "link" | "custom";
  label: string;
  onClick?: () => Promise<void> | void;
  primary?: boolean;
  to?: string;
};

type TabRunConfig = {
  actionIds?: string[];
  actions?: WorkflowAction[];
  allowBlockedRun?: boolean;
  disabledReason?: string;
  kind?: "read" | "write" | "apply" | "link" | "custom";
  label: string;
  onReload?: () => Promise<void> | void;
  onRun?: () => Promise<string> | string;
};

type WorkflowRunState = {
  error: string;
  message: string;
  runningActionId: string;
};

const emptyRunState: WorkflowRunState = {
  error: "",
  message: "",
  runningActionId: ""
};

const noProofText = "Advanced proof is hidden unless you need it.";
const networkSwitchCheckActionIds = ["cisco.setup-readiness", "cisco.ssh-readonly-probe", "cisco.current-intent-diff"];
const serverCheckActionIds = ["ilo.reachability", "ilo.auth", "ilo.inventory", "esxi.management-validation", "raid.validate"];
const vcenterVmCheckActionIds = ["vcenter-netapp.readiness", "vcenter.install-readiness", "vcenter.post-attach-validation", "esxi.vm-deploy-validate"];
const directVmCheckActionIds = ["esxi.management-validation", "esxi.vm-deploy-validate"];

type PageIntentLayout = Record<string, UiIntentRegionLayout>;

function defaultIntentLayout(regions: UiIntentRegion[]): PageIntentLayout {
  return Object.fromEntries(
    regions.map((region, index) => [
      region.id,
      {
        collapsed: false,
        order: index,
        visible: region.defaultVisible ?? true
      }
    ])
  );
}

function usePageIntentLayout(page: string, regions: UiIntentRegion[], profileId?: string | null) {
  const defaults = useMemo(() => defaultIntentLayout(regions), [regions]);
  const storageKey = `ui-intent:${profileId || "runtime"}:${page}`;
  const [layout, setLayout] = useState<PageIntentLayout>(() => readIntentLayout(storageKey, defaults));
  const [undoLayout, setUndoLayout] = useState<PageIntentLayout | null>(null);
  const [summary, setSummary] = useState("");
  const [targetRegionId, setTargetRegionId] = useState("");

  useEffect(() => {
    setLayout(readIntentLayout(storageKey, defaults));
    setUndoLayout(null);
    setSummary("");
    setTargetRegionId("");
  }, [defaults, storageKey]);

  useEffect(() => {
    window.localStorage.setItem(storageKey, JSON.stringify(layout));
  }, [layout, storageKey]);

  function applyOps(ops: UiIntentOp[], nextSummary: string) {
    setLayout((current) => {
      const next = applyIntentOps(current, regions, ops);
      setUndoLayout(current);
      return next;
    });
    setSummary(nextSummary);
  }

  function undo() {
    if (!undoLayout) return;
    setLayout(undoLayout);
    setUndoLayout(null);
    setSummary("Undid the last page layout change.");
  }

  function reset() {
    setLayout(defaults);
    setUndoLayout(null);
    setSummary("Reset this page layout.");
  }

  return { applyOps, layout, reset, setTargetRegionId, summary, targetRegionId, undo, undoAvailable: Boolean(undoLayout) };
}

function readIntentLayout(key: string, defaults: PageIntentLayout): PageIntentLayout {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return defaults;
    const parsed = JSON.parse(raw) as PageIntentLayout;
    return Object.fromEntries(
      Object.entries(defaults).map(([regionId, fallback]) => {
        const saved = parsed[regionId];
        return [
          regionId,
          {
            collapsed: Boolean(saved?.collapsed),
            order: Number.isFinite(saved?.order) ? saved.order : fallback.order,
            visible: typeof saved?.visible === "boolean" ? saved.visible : fallback.visible
          }
        ];
      })
    );
  } catch {
    return defaults;
  }
}

function applyIntentOps(layout: PageIntentLayout, regions: UiIntentRegion[], ops: UiIntentOp[]): PageIntentLayout {
  const regionIds = new Set(regions.map((region) => region.id));
  const next: PageIntentLayout = Object.fromEntries(Object.entries(layout).map(([key, value]) => [key, { ...value }]));
  for (const op of ops) {
    if (!regionIds.has(op.region_id) || !next[op.region_id]) continue;
    if (op.op === "hide") next[op.region_id].visible = false;
    if (op.op === "show") next[op.region_id].visible = true;
    if (op.op === "collapse") next[op.region_id].collapsed = true;
    if (op.op === "expand") next[op.region_id].collapsed = false;
    if (op.op === "moveUp") next[op.region_id].order -= 1.5;
    if (op.op === "moveDown") next[op.region_id].order += 1.5;
  }
  return next;
}

function PageIntentBar({
  layout,
  onApply,
  onReset,
  onTargetRegionChange,
  onUndo,
  page,
  regions,
  summary,
  targetRegionId,
  undoAvailable
}: {
  layout: PageIntentLayout;
  onApply: (ops: UiIntentOp[], summary: string) => void;
  onReset: () => void;
  onTargetRegionChange: (regionId: string) => void;
  onUndo: () => void;
  page: string;
  regions: UiIntentRegion[];
  summary: string;
  targetRegionId: string;
  undoAvailable: boolean;
}) {
  const [request, setRequest] = useState("");
  const [queuedRequest, setQueuedRequest] = useState("");
  const [lastQueued, setLastQueued] = useState<AiChangeRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = request.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setError("");
    const selectedRegion = regions.find((region) => region.id === targetRegionId) ?? null;
    const scopedRegions = selectedRegion ? [selectedRegion] : regions;
    try {
      const response = await api.resolveUiIntent({
        current_layout: layout,
        page,
        regions: scopedRegions.map(({ id, kind, label }) => ({ id, kind, label })),
        request: trimmed
      });
      onApply(response.ops, response.summary);
      setQueuedRequest(response.ops.length ? "" : trimmed);
      if (response.ops.length) setLastQueued(null);
      setRequest("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function queueChangeRequest() {
    const trimmed = queuedRequest.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setError("");
    const selectedRegion = regions.find((region) => region.id === targetRegionId) ?? null;
    try {
      const response = await api.createAiChangeRequest({
        current_layout: layout,
        page,
        regions: regions.map(({ id, kind, label }) => ({ id, kind, label })),
        request: trimmed,
        route: window.location.pathname,
        screenshot_path: null,
        target: selectedRegion ? `${selectedRegion.label} (${selectedRegion.id})` : null
      });
      onApply([], response.message);
      setLastQueued(response);
      setQueuedRequest("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page-intent-bar" aria-label="Change this page">
      <form onSubmit={submit}>
        <label htmlFor={`page-intent-${page}`}>Change this page</label>
        <input
          id={`page-intent-${page}`}
          onChange={(event) => setRequest(event.target.value)}
          placeholder="Hide advanced proof, collapse storage details, move safety up..."
          value={request}
        />
        <button className="operator-primary-button" disabled={busy || !request.trim()} type="submit">
          {busy ? "Changing..." : "Apply"}
        </button>
        <button disabled={!undoAvailable || busy} onClick={onUndo} type="button">Undo</button>
        <button disabled={busy} onClick={onReset} type="button">Reset</button>
      </form>
      <div className="page-intent-targets" aria-label="Target area">
        <span>Target area</span>
        <button
          aria-pressed={!targetRegionId}
          disabled={busy}
          onClick={() => onTargetRegionChange("")}
          type="button"
        >
          Whole page
        </button>
        {regions.map((region) => (
          <button
            aria-pressed={targetRegionId === region.id}
            disabled={busy}
            key={region.id}
            onClick={() => onTargetRegionChange(region.id)}
            type="button"
          >
            {region.label}
          </button>
        ))}
      </div>
      {!lastQueued && <p>{summary || "Layout only. This cannot change data, settings, or run lab workflows."}</p>}
      {queuedRequest && (
        <div className="page-intent-queue">
          <span>This looks bigger than layout. Queue it for the Claude+Codex build loop?</span>
          <button disabled={busy} onClick={queueChangeRequest} type="button">Queue change request</button>
        </div>
      )}
      {lastQueued && (
        <div className="page-intent-receipt" role="status">
          <div>
            <strong>Sent to agent mailbox</strong>
            <span>{lastQueued.message}</span>
          </div>
          <code>{lastQueued.artifact}</code>
          <small>{lastQueued.next_action}</small>
        </div>
      )}
      {error && <div className="operator-feedback error">{error}</div>}
    </section>
  );
}

function orderedIntentRegions(regions: UiIntentRegion[], layout: PageIntentLayout) {
  return [...regions].sort((left, right) => (layout[left.id]?.order ?? 0) - (layout[right.id]?.order ?? 0));
}

function IntentRegion({
  children,
  highlighted,
  layout,
  region
}: {
  children: ReactNode;
  highlighted: boolean;
  layout: PageIntentLayout;
  region: UiIntentRegion;
}) {
  const state = layout[region.id];
  if (state && !state.visible) return null;
  return (
    <div className={`page-intent-region ${highlighted ? "is-intent-target" : ""}`} data-region-id={region.id}>
      {state?.collapsed ? (
        <div className="page-intent-collapsed">
          <span>{region.label}</span>
          <span>Collapsed by page AI</span>
        </div>
      ) : children}
    </div>
  );
}

const overviewIntentRegions: UiIntentRegion[] = [
  { id: "topology", label: "Living lab topology", kind: "section" },
  { id: "reset-rebuild", label: "Reset and rebuild entry", kind: "section" },
  { id: "advanced-proof", label: "Advanced proof", kind: "drawer", collapsible: true }
];

const storageIntentRegions: UiIntentRegion[] = [
  { id: "scenario", label: "Storage scenario", kind: "section" },
  { id: "reference", label: "Storage reference", kind: "section" },
  { id: "local-readiness", label: "Local storage readiness", kind: "section" },
  { id: "ontap-readiness", label: "NetApp ONTAP readiness", kind: "section" },
  { id: "configure", label: "Storage configure", kind: "section" },
  { id: "advanced-proof", label: "Storage proof", kind: "drawer", collapsible: true }
];

const networkIntentRegions: UiIntentRegion[] = [
  { id: "reference", label: "Network reference and Cisco driver", kind: "section" },
  { id: "advanced-proof", label: "Network proof", kind: "drawer", collapsible: true }
];

const virtualizationIntentRegions: UiIntentRegion[] = [
  { id: "setup-shape", label: "Virtualization setup shape", kind: "section" },
  { id: "reference", label: "Virtualization reference", kind: "section" },
  { id: "configure", label: "Virtualization configure", kind: "section" },
  { id: "advanced-proof", label: "Virtualization proof", kind: "drawer", collapsible: true }
];

const firmwareIntentRegions: UiIntentRegion[] = [
  { id: "setup-shape", label: "Firmware setup shape", kind: "section" },
  { id: "reference", label: "Firmware reference", kind: "section" },
  { id: "check-plan", label: "Firmware check and plan", kind: "section" },
  { id: "ontap-upgrade", label: "ONTAP upgrade", kind: "section" },
  { id: "media-files", label: "Firmware media files", kind: "section" },
  { id: "advanced-proof", label: "Firmware proof", kind: "drawer", collapsible: true }
];

const validationIntentRegions: UiIntentRegion[] = [
  { id: "setup-shape", label: "Validation setup shape", kind: "section" },
  { id: "scenario-scope", label: "Validation scenario scope", kind: "section" },
  { id: "reference", label: "Validation reference", kind: "section" },
  { id: "reset-rebuild", label: "Reset and rebuild", kind: "section" },
  { id: "smoke-handoff", label: "Real smoke and handoff", kind: "section" },
  { id: "advanced-proof", label: "Validation proof", kind: "drawer", collapsible: true }
];

export function OperatorOverviewPage({
  health,
  labProfileError = "",
  labProfileLoading = false,
  labProfileState,
  onReloadLabProfile
}: OperatorPageProps) {
  const navigate = useNavigate();
  const activeProfile = activeLabProfile(labProfileState);
  const address = activeAddressPlan(activeProfile);
  const global = activeProfile?.global_settings ?? null;
  const features = activeProfile?.features ?? null;
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [validation, setValidation] = useState<LabValidationSummary | null>(null);
  const [firmwareSummaries, setFirmwareSummaries] = useState<FirmwareSummary[]>([]);
  const [vcenterNetapp, setVcenterNetapp] = useState<ProviderProbeResult | null>(null);
  const [buildVerification, setBuildVerification] = useState<ProviderProbeResult | null>(null);
  const [ciscoReadiness, setCiscoReadiness] = useState<ProviderProbeResult | null>(null);
  const [netappConsole, setNetappConsole] = useState<ProviderProbeResult | null>(null);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [labSafety, setLabSafety] = useState<LabSafetySettings | null>(null);
  const [workflowActions, setWorkflowActions] = useState<WorkflowAction[]>([]);
  const [error, setError] = useState("");
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [detailsLoaded, setDetailsLoaded] = useState(false);
  const [detailsLoading, setDetailsLoading] = useState(false);

  async function load() {
    setError("");
    try {
      const [
        nextProviders,
        nextValidation,
        nextFirmware,
        nextVcenterNetapp,
        nextBuildVerification
      ] = await Promise.all([
        safeApi(api.providers, [] as ProviderStatus[]),
        safeApi(api.labValidation, null),
        safeApi(api.firmwareSummary, [] as FirmwareSummary[]),
        safeApi(api.vcenterNetappReadiness, null),
        safeApi(api.buildVerification, null)
      ]);
      setProviders(Array.isArray(nextProviders) ? nextProviders : []);
      setValidation(nextValidation);
      setFirmwareSummaries(Array.isArray(nextFirmware) ? nextFirmware : []);
      setVcenterNetapp(nextVcenterNetapp);
      setBuildVerification(nextBuildVerification);
      if (onReloadLabProfile) {
        await onReloadLabProfile();
      }
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function loadDetails() {
    setDetailsLoading(true);
    setError("");
    try {
      const [nextCiscoReadiness, nextNetappConsole, nextLabSafety, nextAuditEvents, nextWorkflowActions] = await Promise.all([
        safeApi(api.ciscoSetupReadiness, null),
        safeApi(api.netappConsoleReadiness, null),
        safeApi(api.labSafetySettings, null),
        safeApi(() => api.auditEvents(8000), [] as AuditEvent[]),
        safeApi(api.workflowActions, [] as WorkflowAction[])
      ]);
      setCiscoReadiness(nextCiscoReadiness as ProviderProbeResult | null);
      setNetappConsole(nextNetappConsole as ProviderProbeResult | null);
      setLabSafety(nextLabSafety as LabSafetySettings | null);
      setAuditEvents(Array.isArray(nextAuditEvents) ? nextAuditEvents : []);
      setWorkflowActions(Array.isArray(nextWorkflowActions) ? nextWorkflowActions : []);
      setDetailsLoaded(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setDetailsLoading(false);
    }
  }

  function toggleDetails() {
    const opening = !detailsOpen;
    setDetailsOpen(opening);
    if (opening && !detailsLoaded && !detailsLoading) {
      void loadDetails();
    }
  }

  const inventoryRows = useMemo(
    () => buildInventoryRows({ address, firmwareSummaries, providers, validation, vcenterNetapp }),
    [address, firmwareSummaries, providers, validation, vcenterNetapp]
  );
  const labValues = useMemo(
    () => overviewLabValues({ address, ciscoReadiness, features, global, netappConsole, profile: activeProfile, vcenterNetapp }),
    [address, activeProfile, ciscoReadiness, features, global, netappConsole, vcenterNetapp]
  );
  const accessRows = useMemo(
    () => overviewAccessRows({ address, ciscoReadiness, providers, validation, vcenterNetapp }),
    [address, ciscoReadiness, providers, validation, vcenterNetapp]
  );
  const currentView = overviewCurrentView({ buildVerification, providers, validation });
  const operatorHome = useMemo(
    () => buildOperatorHomeModel({
      address,
      buildVerification,
      features,
      firmwareSummaries,
      profile: activeProfile,
      providers,
      validation,
      vcenterNetapp
    }),
    [activeProfile, address, buildVerification, features, firmwareSummaries, providers, validation, vcenterNetapp]
  );
  const workspaceRows = useMemo<OperatorObjectRow[]>(
    () => [
      {
        checkedAt: activeProfile?.updated_at ? formatDateTime(activeProfile.updated_at) : currentView.checkedAt,
        details: labValues,
        freshness: "Operator config",
        id: "active-setup",
        nextAction: "Open the relevant device workspace if any saved lab value is wrong.",
        source: activeProfile ? "Saved setup" : "Not checked",
        status: activeProfile ? "ready" : "not_configured_yet",
        summary: `${activeProfile?.name ?? "No active setup"} / ${displayAddress(address.subnet)}`,
        target: displayAddress(address.subnet),
        title: "Active Lab Setup",
        type: "Context"
      },
      ...accessRows.map((row) => ({
        checkedAt: currentView.checkedAt,
        details: [
          { label: "App can see", value: row.appSees },
          { label: "Needs", value: row.needs },
          { label: "Target", value: row.target }
        ],
        freshness: currentView.freshness,
        id: `access-${row.item.toLowerCase().replace(/\s+/g, "-")}`,
        nextAction: row.needs === "Nothing right now" ? "No action required." : row.needs,
        source: currentView.source,
        status: row.status,
        summary: `${row.item} is ${displayStatus(row.status).toLowerCase()}.`,
        target: row.target,
        title: row.item,
        type: "Reachability"
      }))
    ],
    [accessRows, activeProfile, address.subnet, currentView.checkedAt, currentView.freshness, currentView.source, labValues]
  );
  const advancedProof = (
    <AdvancedDrawer title="Advanced proof" summary={noProofText}>
      <OperatorWorkspace currentView={currentView} rows={workspaceRows} compact />
      <InventoryTable rows={inventoryRows} />
      <ValidationProofList items={validation?.validation_items ?? []} proofLinks={validation?.proof_links.length ?? 0} />
      <ConfigValueList
        values={[
          { label: "Lab mode", value: displayStatus(runtimeStatus(health ?? null)) },
          { label: "Build verification", value: displayStatus(buildVerification?.status ?? "not_checked") },
          { label: "Validation rows", value: String(validation?.validation_items.length ?? 0) }
        ]}
      />
      <LabSafetySettingsSection
        auditEvents={auditEvents}
        labSafety={labSafety}
      />
    </AdvancedDrawer>
  );

  return (
    <OperatorPage title="Overview">
      <div className="operator-home-layout">
        <div className="operator-home-map-column">
          {detailsLoading && <p className="operator-home-feedback">Refreshing device status...</p>}
          <LabTopologyMap
            accessRows={accessRows}
            activeProfile={activeProfile}
            address={address}
            features={features}
            firmwareSummaries={firmwareSummaries}
            health={health}
            onReload={load}
            vcenterNetapp={vcenterNetapp}
            workflowActions={workflowActions}
          />
        </div>
        <aside className="operator-home-rail" aria-label="Operator Home status and next action">
          <OperatorHomeView
            detailsOpen={detailsOpen}
            error={error || labProfileError}
            loading={labProfileLoading}
            model={operatorHome}
            onPrimaryAction={() => navigate(operatorHome.NextAction.Target === "kit" ? "/lab-profiles#new" : "/run-center")}
            onViewDetails={toggleDetails}
          />
          {detailsOpen && (
            <section className="operator-home-details" aria-label="Operator Details">
              {advancedProof}
            </section>
          )}
        </aside>
      </div>
    </OperatorPage>
  );
}

export function OperatorLabDefaultsPage({ labProfileState, onReloadLabProfile }: OperatorPageProps) {
  const activeProfile = activeLabProfile(labProfileState);
  const address = activeAddressPlan(activeProfile);
  const global = activeProfile?.global_settings ?? null;
  const profileKey = `${activeProfile?.id ?? "none"}:${activeProfile?.version ?? 0}:${activeProfile?.source ?? "missing"}`;
  const [edit, setEdit] = useState<SettingsProfileEditState>(() => settingsProfileEditStateFrom(activeProfile));
  const [deviceToggles, setDeviceToggles] = useState<Record<string, boolean>>(() => labDefaultsDeviceToggles(activeProfile));
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const expectedDevices = labDefaultsDeviceRows(activeProfile, deviceToggles);
  const usernameSaved = false;
  const passwordSaved = false;

  useEffect(() => {
    setEdit(settingsProfileEditStateFrom(activeProfile));
    setDeviceToggles(labDefaultsDeviceToggles(activeProfile));
    setAdvancedOpen(false);
    setError("");
    setMessage("");
  }, [profileKey, activeProfile]);

  function update<K extends keyof SettingsProfileEditState>(key: K, value: SettingsProfileEditState[K]) {
    setEdit((current) => ({ ...current, [key]: value }));
  }

  function toggleDevice(deviceId: string) {
    setDeviceToggles((current) => {
      const nextIncluded = !current[deviceId];
      if (deviceId === "vcenter") {
        setEdit((editCurrent) => ({ ...editCurrent, enableVcenter: nextIncluded }));
      }
      return { ...current, [deviceId]: nextIncluded };
    });
  }

  async function saveDefaults(event: FormEvent) {
    event.preventDefault();
    if (!activeProfile) {
      setError("Load the active lab setup before saving defaults.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const payload = labDefaultsProfilePayload(activeProfile, edit, deviceToggles);
      if (activeProfile.source === "saved") {
        await api.updateLabProfile(activeProfile.id, payload);
      } else {
        const saved = await api.createLabProfile(payload);
        await api.activateLabProfile(saved.id);
      }
      await (onReloadLabProfile ?? (async () => {}))();
      setMessage("Lab defaults saved.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <OperatorPage title="Lab Defaults">
      <div className="operator-surface-heading">
        <p className="operator-kicker">Setup</p>
        <h1>Lab Defaults</h1>
        <p>Shared values this kit reuses everywhere: the network, sign-ins, and which devices are expected.</p>
      </div>
      <form className="lab-defaults-form" onSubmit={saveDefaults}>
        <div className="lab-defaults-grid">
          <Card aria-label="Network defaults" className="lab-defaults-network-card" hover={false}>
            <CardHeader>
              <div>
                <h2>Network</h2>
                <p className="muted">The address range every device in this kit lives on.</p>
              </div>
            </CardHeader>
            <CardContent>
              <dl className="lab-defaults-facts">
                <div>
                  <dt>Subnet</dt>
                  <dd><span>{displayAddress(address.subnet)}</span><StatusBadge {...labDefaultsValueStatus(address.subnet)} /></dd>
                </div>
                <div>
                  <dt>Gateway</dt>
                  <dd><span>{displayAddress(global?.gateway)}</span><StatusBadge {...labDefaultsValueStatus(global?.gateway)} /></dd>
                </div>
                <div>
                  <dt>DNS server</dt>
                  <dd><span>{displayAddress(global?.dns_servers?.[0])}</span><StatusBadge {...labDefaultsValueStatus(global?.dns_servers?.[0])} /></dd>
                </div>
              </dl>
              <label className="lab-defaults-select-field">
                <span>Storage protocol</span>
                <select
                  aria-label="Storage protocol"
                  disabled={busy || !activeProfile}
                  onChange={(event) => update("storageProtocol", event.target.value)}
                  value={labDefaultsStorageProtocolValue(edit.storageProtocol)}
                >
                  <option value="nfs">NFS</option>
                  <option value="iscsi">iSCSI</option>
                  <option value="local">Local</option>
                </select>
              </label>
            </CardContent>
          </Card>
          <Card aria-label="Shared sign-in" className="lab-defaults-signin-card" hover={false}>
            <CardHeader>
              <div>
                <h2>Shared sign-in</h2>
                <p className="muted">Reused when a device doesn't have its own. Enter the actual password on the device page, not here.</p>
              </div>
            </CardHeader>
            <CardContent>
              <dl className="lab-defaults-facts">
                <div>
                  <dt>Username</dt>
                  <dd><span>{usernameSaved ? "saved reference" : "set on device page"}</span><StatusBadge {...labDefaultsBooleanStatus(usernameSaved)} /></dd>
                </div>
                <div>
                  <dt>Password</dt>
                  <dd><span className="lab-defaults-secret-placeholder">{passwordSaved ? "******" : "not set"}</span><StatusBadge {...labDefaultsBooleanStatus(passwordSaved)} /></dd>
                </div>
              </dl>
            </CardContent>
          </Card>
        </div>
        {error && <div className="operator-feedback error lab-defaults-feedback">{error}</div>}
        {message && <div className="operator-feedback lab-defaults-feedback">{message}</div>}
        <div className="lab-defaults-actions">
          <button className="operator-primary-button" disabled={busy || !activeProfile} type="submit">
            <Save size={16} />
            {busy ? "Saving" : "Save defaults"}
          </button>
        </div>
      </form>
      <Card className="lab-defaults-devices-card" hover={false}>
        <CardHeader><div><h2>Expected devices</h2><p className="muted">Turn a device off here and it disappears from the map and the build.</p></div></CardHeader>
        <CardContent>
          <div className="lab-defaults-device-list" aria-label="Expected devices">
            {expectedDevices.map((device) => (
              <div className="lab-defaults-device-row" key={device.id}>
                <span className={`device-presence-dot ${device.enabled ? "on" : "off"}`} />
                <div>
                  <strong>{device.name}</strong>
                  <small>{device.detail} - {device.target}</small>
                </div>
                <span className={`lab-defaults-device-state ${device.enabled ? "enabled" : "disabled"}`}>{device.enabled ? "Included" : "Not included"}</span>
                <button
                  aria-checked={device.enabled}
                  aria-label={`Toggle ${device.name}`}
                  className={`lab-defaults-device-toggle ${device.enabled ? "enabled" : "disabled"}`}
                  onClick={() => toggleDevice(device.id)}
                  role="switch"
                  type="button"
                >
                  <span />
                </button>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
      <details className="lab-defaults-advanced" onToggle={(event) => setAdvancedOpen(event.currentTarget.open)} open={advancedOpen}>
        <summary>Advanced</summary>
        {advancedOpen && (
          <form aria-label="Advanced lab default fields" className="lab-defaults-advanced-form" onSubmit={saveDefaults}>
            <div className="lab-defaults-advanced-grid">
              <Field label="Setup name">
                <input disabled={busy || !activeProfile} onChange={(event) => update("name", event.target.value)} value={edit.name} />
              </Field>
              <Field label="Description">
                <input disabled={busy || !activeProfile} onChange={(event) => update("description", event.target.value)} value={edit.description} />
              </Field>
              <Field label="Domain">
                <input disabled={busy || !activeProfile} onChange={(event) => update("domainName", event.target.value)} value={edit.domainName} />
              </Field>
              <Field label="Timezone">
                <input disabled={busy || !activeProfile} onChange={(event) => update("timezone", event.target.value)} value={edit.timezone} />
              </Field>
            </div>
            <div className="network-config-toggles lab-defaults-feature-toggles" aria-label="Lab default feature toggles">
              <label><input checked={edit.enableDns} disabled={busy || !activeProfile} onChange={(event) => update("enableDns", event.target.checked)} type="checkbox" /><span>DNS</span></label>
              <label><input checked={edit.enableNtp} disabled={busy || !activeProfile} onChange={(event) => update("enableNtp", event.target.checked)} type="checkbox" /><span>NTP</span></label>
              <label><input checked={edit.enableSnmp} disabled={busy || !activeProfile} onChange={(event) => update("enableSnmp", event.target.checked)} type="checkbox" /><span>SNMP</span></label>
              <label><input checked={!edit.disableIpv6} disabled={busy || !activeProfile} onChange={(event) => update("disableIpv6", !event.target.checked)} type="checkbox" /><span>Allow IPv6</span></label>
              <label><input checked={edit.blockLegacyProtocols} disabled={busy || !activeProfile} onChange={(event) => update("blockLegacyProtocols", event.target.checked)} type="checkbox" /><span>Block legacy protocols</span></label>
              <label><input checked={edit.enableVcenter} disabled={busy || !activeProfile} onChange={(event) => update("enableVcenter", event.target.checked)} type="checkbox" /><span>vCenter in scope</span></label>
            </div>
            <div className="lab-defaults-advanced-actions">
              <button className="secondary-button" disabled={busy || !activeProfile} type="submit">
                {busy ? "Saving" : "Save advanced defaults"}
              </button>
            </div>
          </form>
        )}
      </details>
    </OperatorPage>
  );
}

function labDefaultsStorageProtocolValue(value: string): string {
  if (value === "none") return "local";
  return value || "nfs";
}

function labDefaultsValueStatus(value: unknown): { label: string; status: StatusBadgeStatus } {
  const text = asString(value);
  return text ? { label: "Saved", status: "ready" } : { label: "Not set", status: "not-configured" };
}

function labDefaultsBooleanStatus(value: boolean): { label: string; status: StatusBadgeStatus } {
  return value ? { label: "Saved", status: "ready" } : { label: "Not set", status: "not-configured" };
}

function labDefaultsDeviceToggles(profile: LabProfile | null): Record<string, boolean> {
  const address = activeAddressPlan(profile);
  return {
    cisco: Boolean(profile && (profile.devices?.cisco ?? address.cisco_management)),
    netapp: Boolean(profile?.features?.netapp_enabled ?? profile?.global_settings?.netapp_enabled),
    server: Boolean(profile && (profile.devices?.ilo ?? profile.devices?.esxi ?? address.ilo ?? address.esxi_management)),
    vcenter: Boolean(profile?.features?.vcenter_enabled ?? profile?.global_settings?.vcenter_enabled)
  };
}

function labDefaultsDeviceRows(profile: LabProfile | null, toggles: Record<string, boolean>) {
  const address = activeAddressPlan(profile);
  return [
    {
      detail: "C9300 - L3 core",
      enabled: Boolean(toggles.cisco),
      id: "cisco",
      name: "Cisco Switch",
      target: displayAddress(address.cisco_management)
    },
    {
      detail: "ESXi compute + iLO",
      enabled: Boolean(toggles.server),
      id: "server",
      name: "HPE Gen10 compute + iLO",
      target: displayAddress(address.ilo)
    },
    {
      detail: "Storage - NetApp",
      enabled: Boolean(toggles.netapp),
      id: "netapp",
      name: "NetApp ONTAP",
      target: displayAddress(address.netapp_cluster_mgmt)
    },
    {
      detail: "VM management",
      enabled: Boolean(toggles.vcenter),
      id: "vcenter",
      name: "vCenter",
      target: displayAddress(profile?.devices?.vcenter)
    }
  ];
}

function labDefaultsProfilePayload(profile: LabProfile, edit: SettingsProfileEditState, toggles: Record<string, boolean>): LabProfileWrite {
  const address = activeAddressPlan(profile);
  const payload = settingsProfilePayload(profile, edit);
  const netappEnabled = Boolean(toggles.netapp);
  const vcenterEnabled = Boolean(toggles.vcenter);
  const ciscoEnabled = Boolean(toggles.cisco);
  const serverEnabled = Boolean(toggles.server);
  return {
    ...payload,
    devices: {
      ...payload.devices,
      cisco: ciscoEnabled ? profile.devices?.cisco ?? address.cisco_management : null,
      esxi: serverEnabled ? profile.devices?.esxi ?? address.esxi_management : null,
      ilo: serverEnabled ? profile.devices?.ilo ?? address.ilo : null,
      netapp: netappEnabled ? profile.devices?.netapp ?? null : null,
      vcenter: vcenterEnabled ? profile.devices?.vcenter ?? null : null
    },
    features: {
      ...profile.features,
      ...payload.features,
      netapp_disabled_reason: netappEnabled ? null : "NetApp is disabled by Lab Defaults.",
      netapp_enabled: netappEnabled,
      vcenter_disabled_reason: vcenterEnabled ? null : "vCenter is disabled by Lab Defaults.",
      vcenter_enabled: vcenterEnabled
    },
    global_settings: {
      ...payload.global_settings,
      netapp_disabled_reason: netappEnabled ? null : "NetApp is disabled by Lab Defaults.",
      netapp_enabled: netappEnabled,
      vcenter_enabled: vcenterEnabled
    }
  };
}

function OverviewResetRebuildLink() {
  return (
    <section className="operator-section overview-danger-link" aria-label="Factory reset danger link">
      <div>
        <p className="operator-kicker danger">Factory reset</p>
        <h2>Dedicated reset and rebuild controls</h2>
        <p>Preview and guarded reset actions live on the Validation page, away from everyday readiness.</p>
      </div>
      <Link className="operator-link-button danger" to="/validation#factory-reset-rebuild">
        Open danger zone
      </Link>
    </section>
  );
}

export function OperatorNetworkPage({ labProfileState, onReloadLabProfile }: OperatorPageProps) {
  const activeProfile = activeLabProfile(labProfileState);
  const address = activeAddressPlan(activeProfile);
  const features = activeProfile?.features ?? null;
  const global = activeProfile?.global_settings ?? null;
  const [actions, setActions] = useState<WorkflowAction[]>([]);
  const [ciscoReadiness, setCiscoReadiness] = useState<ProviderProbeResult | null>(null);
  const [ciscoIntentDiff, setCiscoIntentDiff] = useState<ProviderProbeResult | null>(null);
  const [ciscoSshProbe, setCiscoSshProbe] = useState<ProviderProbeResult | null>(null);
  const [firmwareSummaries, setFirmwareSummaries] = useState<FirmwareSummary[]>([]);
  const [labSafety, setLabSafety] = useState<LabSafetySettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [runState, setRunState] = useState<WorkflowRunState>(emptyRunState);

  async function refreshCiscoSshProbe() {
      setCiscoSshProbe({
        provider_id: "cisco-ansible",
        status: "running",
        message: "Reading live Cisco SSH and current-intent state.",
        checked_at: new Date().toISOString(),
        warnings: [],
        blockers: []
      });
      setCiscoIntentDiff({
        provider_id: "cisco-ansible",
        status: "running",
        message: "Reading live Cisco current-to-intent state.",
        checked_at: new Date().toISOString(),
        warnings: [],
        blockers: []
      });
    try {
      const [nextSshProbe, nextIntentDiff] = await Promise.all([
        api.ciscoSshProbe(),
        api.ciscoCurrentIntentDiff()
      ]);
      setCiscoSshProbe(nextSshProbe);
      setCiscoIntentDiff(nextIntentDiff);
    } catch (err) {
      const message = errorMessage(err);
      setCiscoSshProbe({
        provider_id: "cisco-ansible",
        status: "blocked",
        message,
        checked_at: new Date().toISOString(),
        warnings: [],
        blockers: [message]
      });
      setCiscoIntentDiff({
        provider_id: "cisco-ansible",
        status: "blocked",
        message,
        checked_at: new Date().toISOString(),
        warnings: [],
        blockers: [message]
      });
    }
  }

  async function load() {
    setError("");
    setLoading(true);
    try {
      const nextLabSafety = await safeApi(api.labSafetySettings, null);
      setLabSafety(nextLabSafety as LabSafetySettings | null);
      const [nextActions, nextCisco, nextFirmware] = await Promise.all([
        safeApi(api.workflowActions, [] as WorkflowAction[]),
        safeApi(api.ciscoSetupReadiness, null),
        safeApi(api.firmwareSummary, [] as FirmwareSummary[])
      ]);
      setActions(Array.isArray(nextActions) ? nextActions : []);
      setCiscoReadiness(nextCisco as ProviderProbeResult | null);
      setFirmwareSummaries(Array.isArray(nextFirmware) ? nextFirmware : []);
      void refreshCiscoSshProbe();
      setLoading(false);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const consoleState = objectValue(ciscoReadiness?.console);
  const networkStatus = asString(ciscoReadiness?.status) || (address.cisco_management ? "ready" : "not_configured_yet");
  const currentView = networkCurrentView({ address, ciscoReadiness });
  const networkRows = useMemo<OperatorObjectRow[]>(
    () => [
      {
        checkedAt: currentView.checkedAt,
        details: [
          { label: "Management IP", value: displayAddress(address.cisco_management), source: "Saved setup" },
          { label: "Credentials", value: "Configured or missing only" },
          { label: "Prompt", value: displayValue(asString(objectValue(ciscoReadiness?.real_lab_run).prompt_state)) }
        ],
        freshness: currentView.freshness,
        id: "cisco-management",
        nextAction: humanize(asString(ciscoReadiness?.next_safe_action) || "Run Live Switch Check."),
        source: currentView.source,
        status: networkStatus,
        summary: asString(ciscoReadiness?.message) || "Cisco management reachability and setup readiness.",
        target: displayAddress(address.cisco_management),
        title: "Cisco Management",
        type: "Device"
      },
      {
        checkedAt: currentView.checkedAt,
        details: [
          { label: "Selected path", value: displayValue(asString(consoleState.selected_path)) },
          { label: "Effective path", value: displayValue(asString(consoleState.effective_path)) },
          { label: "Status", value: displayStatus(asString(consoleState.status) || "not_checked"), status: asString(consoleState.status) || "not_checked" }
        ],
        freshness: currentView.freshness,
        id: "console",
        nextAction: "Review saved setup details if the console path is wrong.",
        source: currentView.source,
        status: asString(consoleState.status) || "not_checked",
        summary: "First-contact access for Cisco setup and recovery.",
        target: displayValue(asString(consoleState.selected_path) || asString(consoleState.effective_path)),
        title: "Console",
        type: "Access"
      },
      {
        checkedAt: currentView.checkedAt,
        details: [
          { label: "SSH/SCP", value: boolStateLabel(asBoolean(ciscoReadiness?.management_configured)) },
          { label: "Secret handling", value: "Configured or missing only" }
        ],
        freshness: currentView.freshness,
        id: "ssh-scp",
        nextAction: "Run Live Switch Check after fixing connectivity or credentials.",
        source: currentView.source,
        status: asBoolean(ciscoReadiness?.management_configured) ? "ready" : "not_checked",
        summary: "Management access check without exposing secret values.",
        target: displayAddress(address.cisco_management),
        title: "SSH / SCP",
        type: "Access"
      },
      ...[
        { id: "vlan", label: "VLAN", status: "ready", value: displayValue(global?.vlan_id ?? activeProfile?.vlan_id) },
        { id: "dns", label: "DNS", status: featureStatus(features, "enable_dns"), value: listLabel(global?.dns_servers ?? activeProfile?.dns) },
        { id: "ntp", label: "NTP", status: featureStatus(features, "enable_ntp"), value: listLabel(global?.ntp_servers ?? activeProfile?.ntp) },
        { id: "snmp", label: "SNMP", status: featureStatus(features, "enable_snmp"), value: enabledLabel(features?.enable_snmp) },
        { id: "mtu", label: "MTU", status: "ready", value: displayValue(global?.mtu ?? activeProfile?.mtu) }
      ].map((item) => ({
        checkedAt: currentView.checkedAt,
        details: [{ label: item.label, value: item.value, source: "Saved setup", status: item.status }],
        freshness: "Operator config",
        id: item.id,
        nextAction: "Use Network Configure to change this value.",
        source: "Saved setup",
        status: item.status,
        summary: `${item.label} setting used by the network run.`,
        target: item.value,
        title: item.label,
        type: "Network setting"
      })),
      {
        checkedAt: currentView.checkedAt,
        details: [{ label: "Cisco firmware", value: firmwareVersion(firmwareSummaries, "cisco") }],
        freshness: currentView.freshness,
        id: "firmware",
        nextAction: "Open Firmware Upgrades for file selection and upgrade path.",
        source: "Firmware files",
        status: firmwareVersion(firmwareSummaries, "cisco") === "Not checked" ? "not_checked" : "ready",
        summary: "Firmware evidence that can affect switch readiness.",
        target: firmwareVersion(firmwareSummaries, "cisco"),
        title: "Cisco Firmware",
        type: "Firmware"
      }
    ],
    [activeProfile, address.cisco_management, ciscoReadiness, consoleState, currentView, features, firmwareSummaries, global]
  );
  const ciscoFirmware = firmwareVersion(firmwareSummaries, "cisco");
  const settingsRows = networkSettingsRows({ ciscoFirmware, features, global });
  const prerequisites = realLabPrerequisites(ciscoReadiness, consoleState, currentView, labSafety);
  const ciscoDriver = ciscoDriverPlan({ address, activeProfile, ciscoIntentDiff, ciscoReadiness, ciscoSshProbe, features, global });
  const byActionId = useMemo(() => new Map(actions.map((action) => [action.action_id, action])), [actions]);
  const switchRunConfig: TabRunConfig = {
    actionIds: networkSwitchCheckActionIds,
    actions,
    kind: "read",
    label: "Run switch check",
    onReload: load
  };
  const switchAction = firstRunnableAction(byActionId, networkSwitchCheckActionIds, switchRunConfig);
  const switchFallbackActionId = fallbackRunActionId(switchRunConfig, switchAction);
  const switchDisabledReason = switchAction
    ? disabledReasonForRunConfig(switchRunConfig, switchAction)
    : switchFallbackActionId
      ? ""
      : disabledReasonForRunConfig(switchRunConfig, switchAction);
  const switchAccess = networkSwitchAccessCardModel({
    address,
    ciscoReadiness,
    consoleState,
    currentView,
    networkStatus
  });

  async function runSwitchCheck() {
    const actionId = switchAction?.action_id ?? switchFallbackActionId;
    if (!actionId || switchDisabledReason || runState.runningActionId) return;
    setRunState({ error: "", message: "", runningActionId: actionId });
    try {
      const result = await api.runWorkflowAction(actionId);
      setRunState({
        error: "",
        message: switchAction ? workflowRunMessage(switchAction, result) : workflowRunResultMessage("Run switch check", result),
        runningActionId: ""
      });
      await load();
    } catch (err) {
      setRunState({ error: errorMessage(err), message: "", runningActionId: "" });
    }
  }

  return (
    <OperatorPage title="Network">
      <div className="operator-surface-heading">
        <p className="operator-kicker">Setup</p>
        <h1>Network</h1>
        <p>Can the Cisco switch be reached, and what one safe check should run next?</p>
      </div>
      <Feedback loading={false} error={error} />
      <section className="network-access-surface" aria-label="Switch Access">
        <Card className="network-access-card" hover={false}>
          <CardHeader>
            <div>
              <p className="operator-kicker">Switch access</p>
              <h2>{switchAccess.switchName}</h2>
            </div>
            <StatusBadge label={switchAccess.stateLabel} status={switchAccess.badgeStatus} />
          </CardHeader>
          <CardContent>
            <dl className="network-access-fields">
              <div>
                <dt>Switch</dt>
                <dd>{switchAccess.switchName}</dd>
              </div>
              <div>
                <dt>Management IP</dt>
                <dd>{switchAccess.managementIp}</dd>
              </div>
              <div>
                <dt>Access</dt>
                <dd>{switchAccess.accessLabel}</dd>
              </div>
            </dl>
            {switchAccess.reason && (
              <div className="network-access-reason" role="note">
                <strong>Needs attention</strong>
                <span>{switchAccess.reason}</span>
              </div>
            )}
            {runState.message && <div className="operator-feedback network-access-feedback">{runState.message}</div>}
            {runState.error && <div className="operator-feedback error network-access-feedback">{runState.error}</div>}
          </CardContent>
          <CardFooter>
            <div className="network-access-actions">
              <button
                className="operator-primary-button"
                disabled={Boolean(switchDisabledReason) || Boolean(runState.runningActionId)}
                onClick={() => void runSwitchCheck()}
                title={switchDisabledReason || "Run switch check"}
                type="button"
              >
                <RefreshCw size={16} />
                {runState.runningActionId ? "Checking" : "Run switch check"}
              </button>
              <button
                aria-expanded={detailsOpen}
                className="secondary-button"
                onClick={() => setDetailsOpen((current) => !current)}
                type="button"
              >
                View details
              </button>
            </div>
          </CardFooter>
        </Card>
      </section>
      {detailsOpen && (
        <section className="network-details" aria-label="Network details">
          <div className="network-details-grid">
            <Card className="network-details-card" hover={false}>
              <CardHeader>
                <div>
                  <p className="operator-kicker">Details</p>
                  <h2>Switch settings and access paths</h2>
                </div>
                <StatusBadge label={displayStatus(networkStatus)} status={statusBadgeStatus(networkStatus)} />
              </CardHeader>
              <CardContent>
                <ConfigValueList
                  values={[
                    { label: "Management IP", value: displayAddress(address.cisco_management), source: "Saved setup" },
                    { label: "Console path", value: displayValue(asString(consoleState.selected_path) || asString(consoleState.effective_path)), source: "Saved setup" },
                    { label: "SSH/SCP", value: boolStateLabel(asBoolean(ciscoReadiness?.management_configured)), source: "Read-only check" },
                    { label: "Prompt", value: displayValue(asString(objectValue(ciscoReadiness?.real_lab_run).prompt_state)), source: "Read-only check" },
                    { label: "Firmware", value: ciscoFirmware, source: "Firmware files" }
                  ]}
                />
              </CardContent>
            </Card>
            <Card className="network-details-card" hover={false}>
              <CardHeader>
                <div>
                  <p className="operator-kicker">Saved settings</p>
                  <h2>Network values</h2>
                </div>
                <span>{settingsRows.length} tracked</span>
              </CardHeader>
              <CompactTable>
                <CompactTableHeader>
                  <CompactTableCell>Item</CompactTableCell>
                  <CompactTableCell>Current</CompactTableCell>
                  <CompactTableCell>Status</CompactTableCell>
                </CompactTableHeader>
                <tbody>
                  {settingsRows.map((row) => (
                    <CompactTableRow key={row.item}>
                      <CompactTableCell><strong>{row.item}</strong></CompactTableCell>
                      <CompactTableCell>{row.current}</CompactTableCell>
                      <CompactTableCell><StatusBadge label={displayStatus(row.status)} status={statusBadgeStatus(row.status)} /></CompactTableCell>
                    </CompactTableRow>
                  ))}
                </tbody>
              </CompactTable>
            </Card>
            <NetworkConfigurePanel
              activeProfile={activeProfile}
              address={address}
              features={features}
              global={global}
              onSaved={async () => {
                if (onReloadLabProfile) {
                  await onReloadLabProfile();
                }
                await load();
              }}
            />
            <details className="network-advanced-switch-plan">
              <summary>
                <span>
                  <span className="operator-kicker">Advanced</span>
                  <strong>Advanced switch plan</strong>
                  <small>VLANs, ports, guardrails, drift, and candidate config stay here.</small>
                </span>
              </summary>
              <CiscoDriverPanel plan={ciscoDriver} onRefresh={refreshCiscoSshProbe} />
            </details>
            <AdvancedDrawer title="Network proof" summary={noProofText}>
              <OperatorWorkspace currentView={currentView} rows={networkRows} compact />
              <ConfigValueList
                values={[
                  { label: "Firmware", value: ciscoFirmware },
                  { label: "Prompt", value: displayValue(asString(objectValue(ciscoReadiness?.real_lab_run).prompt_state)) },
                  { label: "Warnings", value: String(stringArray(ciscoReadiness?.warnings).length) }
                ]}
              />
              <RealLabPrerequisitesPanel items={prerequisites} />
            </AdvancedDrawer>
          </div>
        </section>
      )}
    </OperatorPage>
  );
}

function networkSwitchAccessCardModel({
  address,
  ciscoReadiness,
  consoleState,
  currentView,
  networkStatus
}: {
  address: LabAddressPlan;
  ciscoReadiness: ProviderProbeResult | null;
  consoleState: Record<string, unknown>;
  currentView: CurrentViewModel;
  networkStatus: string;
}) {
  const stateLabel = networkSwitchStateLabel(networkStatus, Boolean(ciscoReadiness), address.cisco_management);
  const accessLabel = networkSwitchAccessLabel(ciscoReadiness, consoleState);
  const reason = stateLabel === "Blocked"
    ? humanize(
      !address.cisco_management
        ? "Set the Cisco management IP before running the switch check."
        : currentView.blockers[0] ||
          stringArray(ciscoReadiness?.blockers)[0] ||
          asString(ciscoReadiness?.next_safe_action) ||
          asString(ciscoReadiness?.message) ||
          "Switch access needs attention before network setup can continue."
    )
    : "";

  return {
    accessLabel,
    badgeStatus: networkSwitchBadgeStatus(stateLabel),
    managementIp: displayAddress(address.cisco_management),
    reason,
    stateLabel,
    switchName: "Cisco C9300"
  };
}

function networkSwitchStateLabel(status: string, readinessLoaded: boolean, managementIp: string | null | undefined): "Ready" | "Blocked" | "Not checked" {
  if (!managementIp) return "Blocked";
  const normalized = status.toLowerCase();
  if (["ready", "ok", "passed", "safe-to-run", "safe_to_run", "success"].includes(normalized)) return "Ready";
  if (!readinessLoaded || !normalized || ["not_checked", "unknown", "running"].includes(normalized)) return "Not checked";
  return "Blocked";
}

function networkSwitchBadgeStatus(label: "Ready" | "Blocked" | "Not checked"): StatusBadgeStatus {
  if (label === "Ready") return "ready";
  if (label === "Blocked") return "blocked";
  return "not-configured";
}

function networkSwitchAccessLabel(ciscoReadiness: ProviderProbeResult | null, consoleState: Record<string, unknown>): "Console ready" | "SSH ready" | "Needs sign-in" | "Not checked" {
  const consoleStatus = asString(consoleState.status).toLowerCase();
  if (["ready", "ok", "detected", "connected", "present"].includes(consoleStatus)) return "Console ready";
  if (asBoolean(ciscoReadiness?.management_configured)) return "SSH ready";
  if (!ciscoReadiness) return "Not checked";
  const text = [
    asString(ciscoReadiness.message),
    asString(ciscoReadiness.next_safe_action),
    ...stringArray(ciscoReadiness.blockers)
  ].join(" ").toLowerCase();
  if (/(credential|password|username|sign[- ]?in|login|secret|auth)/i.test(text)) return "Needs sign-in";
  return "Not checked";
}

export function OperatorServerPage({ labProfileState, onReloadLabProfile }: OperatorPageProps) {
  const activeProfile = activeLabProfile(labProfileState);
  const address = activeAddressPlan(activeProfile);
  const global = activeProfile?.global_settings ?? null;
  const [actions, setActions] = useState<WorkflowAction[]>([]);
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [firmwareSummaries, setFirmwareSummaries] = useState<FirmwareSummary[]>([]);
  const [raidPlan, setRaidPlan] = useState<ProviderProbeResult | null>(null);
  const [esxiReadiness, setEsxiReadiness] = useState<ProviderProbeResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [runState, setRunState] = useState<WorkflowRunState>(emptyRunState);

  async function load() {
    setError("");
    setLoading(true);
    try {
      const [nextActions, nextProviders, nextFirmware, nextRaidPlan, nextEsxiReadiness] = await Promise.all([
        safeApi(api.workflowActions, [] as WorkflowAction[]),
        safeApi(api.providers, [] as ProviderStatus[]),
        safeApi(api.firmwareSummary, [] as FirmwareSummary[]),
        safeApi(api.hpeRaidPlanPreview, null),
        safeApi(api.esxiInstallReadiness, null)
      ]);
      setActions(Array.isArray(nextActions) ? nextActions : []);
      setProviders(Array.isArray(nextProviders) ? nextProviders : []);
      setFirmwareSummaries(Array.isArray(nextFirmware) ? nextFirmware : []);
      setRaidPlan(nextRaidPlan as ProviderProbeResult | null);
      setEsxiReadiness(nextEsxiReadiness);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const iloStatus = providerStatus(providers, ["ilo", "redfish"]) || "not_checked";
  const esxiStatus = asString(esxiReadiness?.status) || providerStatus(providers, ["esxi"]) || "not_checked";
  const raidStatus = asString(raidPlan?.status) || "not_checked";
  const serverStatus = strongestStatus([iloStatus, esxiStatus, raidStatus]);
  const currentView = serverCurrentView({ address, esxiReadiness, iloStatus, raidPlan, raidStatus });
  const serverRows = useMemo<OperatorObjectRow[]>(
    () => [
      {
        checkedAt: currentView.checkedAt,
        details: [
          { label: "URL", value: address.ilo ? `https://${address.ilo}` : "Not set up yet" },
          { label: "Credentials", value: "Configured or missing only" },
          { label: "Power actions", value: "Guarded" }
        ],
        freshness: currentView.freshness,
        id: "ilo",
        nextAction: "Run Server Live Check before inventory or firmware work.",
        source: currentView.source,
        status: iloStatus,
        summary: "HPE iLO management endpoint for the server.",
        target: address.ilo ? `https://${address.ilo}` : "Not set up yet",
        title: "HPE iLO",
        type: "Management"
      },
      {
        checkedAt: currentView.checkedAt,
        details: [
          { label: "Management IP", value: displayAddress(address.esxi_management), source: "Saved setup" },
          { label: "Next safe action", value: humanize(asString(esxiReadiness?.next_safe_action) || "Validate ESXi after any server change.") }
        ],
        freshness: currentView.freshness,
        id: "esxi",
        nextAction: humanize(asString(esxiReadiness?.next_safe_action) || "Run Server Live Check."),
        source: currentView.source,
        status: esxiStatus,
        summary: asString(esxiReadiness?.message) || "ESXi management readiness.",
        target: displayAddress(address.esxi_management),
        title: "ESXi Management",
        type: "Hypervisor"
      },
      {
        checkedAt: currentView.checkedAt,
        details: [
          { label: "Layout", value: raidLayoutLabel(raidPlan), status: raidStatus },
          { label: "Controller", value: raidControllerModels(raidPlan) },
          { label: "Warnings", value: String(stringArray(raidPlan?.warnings).length) }
        ],
        freshness: currentView.freshness,
        id: "raid",
        nextAction: "Validate RAID after storage layout changes.",
        source: sourceLabel(raidPlan),
        status: raidStatus,
        summary: "Smart Array plan and current storage controller state.",
        target: raidLayoutLabel(raidPlan),
        title: "RAID Layout",
        type: "Storage controller",
        warnings: stringArray(raidPlan?.warnings)
      },
      {
        checkedAt: currentView.checkedAt,
        details: [
          { label: "Service Pack", value: servicePackSummary(firmwareSummaries), source: "Firmware files" },
          { label: "iLO / BIOS", value: firmwareVersion(firmwareSummaries, "ilo") },
          { label: "Smart Array", value: firmwareVersion(firmwareSummaries, "raid") }
        ],
        freshness: currentView.freshness,
        id: "hpe-firmware",
        nextAction: "Open Firmware Upgrades to select the HPE Service Pack file.",
        source: "Firmware files",
        status: servicePackSummary(firmwareSummaries) === "Scan needed" ? "not_checked" : "ready",
        summary: "HPE Service Pack, BIOS, iLO, and Smart Array firmware context.",
        target: servicePackSummary(firmwareSummaries),
        title: "HPE Firmware",
        type: "Firmware"
      }
    ],
    [address.esxi_management, address.ilo, currentView, esxiReadiness, esxiStatus, firmwareSummaries, iloStatus, raidPlan, raidStatus]
  );
  const byActionId = useMemo(() => new Map(actions.map((action) => [action.action_id, action])), [actions]);
  const serverRunConfig: TabRunConfig = {
    actionIds: serverCheckActionIds,
    actions,
    kind: "read",
    label: "Run server check",
    onReload: load
  };
  const serverAction = firstRunnableAction(byActionId, serverCheckActionIds, serverRunConfig);
  const serverFallbackActionId = fallbackRunActionId(serverRunConfig, serverAction);
  const serverDisabledReason = serverAction
    ? disabledReasonForRunConfig(serverRunConfig, serverAction)
    : serverFallbackActionId
      ? ""
      : disabledReasonForRunConfig(serverRunConfig, serverAction);
  const computeAccess = serverComputeAccessCardModel({
    activeProfile,
    address,
    currentView,
    esxiReadiness,
    iloStatus,
    raidPlan,
    raidStatus,
    serverStatus
  });
  const servicePack = servicePackSummary(firmwareSummaries);
  const firmwareStatus = servicePack === "Scan needed" ? "not_checked" : "ready";
  const serverDetailRows = [
    { current: displayAddress(address.ilo), item: "iLO access", status: iloStatus },
    { current: displayAddress(address.esxi_management), item: "ESXi management", status: esxiStatus },
    { current: raidLayoutLabel(raidPlan), item: "Local storage", status: raidStatus },
    { current: servicePack, item: "Firmware", status: firmwareStatus }
  ];

  async function runServerCheck() {
    const actionId = serverAction?.action_id ?? serverFallbackActionId;
    if (!actionId || serverDisabledReason || runState.runningActionId) return;
    setRunState({ error: "", message: "", runningActionId: actionId });
    try {
      const result = await api.runWorkflowAction(actionId);
      setRunState({
        error: "",
        message: serverAction ? workflowRunMessage(serverAction, result) : workflowRunResultMessage("Run server check", result),
        runningActionId: ""
      });
      await load();
    } catch (err) {
      setRunState({ error: errorMessage(err), message: "", runningActionId: "" });
    }
  }

  return (
    <OperatorPage title="Server">
      <div className="operator-surface-heading">
        <p className="operator-kicker">Setup</p>
        <h1>Compute & iLO</h1>
        <p>Can the compute host be reached, and what one safe server check should run next?</p>
      </div>
      <Feedback loading={loading && !activeProfile} error={error} />
      <section className="network-access-surface server-access-surface" aria-label="Compute Access">
        <Card className="network-access-card server-access-card" hover={false}>
          <CardHeader>
            <div>
              <p className="operator-kicker">Compute access</p>
              <h2>{computeAccess.host}</h2>
            </div>
            <StatusBadge label={computeAccess.stateLabel} status={computeAccess.badgeStatus} />
          </CardHeader>
          <CardContent>
            <dl className="network-access-fields server-access-fields">
              <div>
                <dt>Host</dt>
                <dd>{computeAccess.host}</dd>
              </div>
              <div>
                <dt>iLO IP</dt>
                <dd>{computeAccess.iloIp}</dd>
              </div>
              <div>
                <dt>ESXi IP</dt>
                <dd>{computeAccess.esxiIp}</dd>
              </div>
              <div>
                <dt>Storage role</dt>
                <dd>{computeAccess.storageRole}</dd>
              </div>
            </dl>
            {computeAccess.reason && (
              <div className="network-access-reason" role="note">
                <strong>Needs attention</strong>
                <span>{computeAccess.reason}</span>
              </div>
            )}
            {runState.message && <div className="operator-feedback network-access-feedback">{runState.message}</div>}
            {runState.error && <div className="operator-feedback error network-access-feedback">{runState.error}</div>}
          </CardContent>
          <CardFooter>
            <div className="network-access-actions server-access-actions">
              <button
                className="operator-primary-button"
                disabled={Boolean(serverDisabledReason) || Boolean(runState.runningActionId)}
                onClick={() => void runServerCheck()}
                title={serverDisabledReason || "Run server check"}
                type="button"
              >
                <RefreshCw size={16} />
                {runState.runningActionId ? "Checking" : "Run server check"}
              </button>
              <button
                aria-expanded={detailsOpen}
                className="secondary-button"
                onClick={() => setDetailsOpen((current) => !current)}
                type="button"
              >
                View details
              </button>
            </div>
          </CardFooter>
        </Card>
      </section>
      {detailsOpen && (
        <section className="network-details server-details" aria-label="Compute details">
          <div className="network-details-grid server-details-grid">
            <Card className="network-details-card" hover={false}>
              <CardHeader>
                <div>
                  <p className="operator-kicker">Details</p>
                  <h2>Access and saved addresses</h2>
                </div>
                <StatusBadge label={displayStatus(serverStatus)} status={statusBadgeStatus(serverStatus)} />
              </CardHeader>
              <CardContent>
                <ConfigValueList
                  values={[
                    { label: "Host", value: computeAccess.host, source: "Saved setup" },
                    { label: "iLO IP", value: computeAccess.iloIp, source: "Saved setup", status: iloStatus },
                    { label: "ESXi IP", value: computeAccess.esxiIp, source: "Saved setup", status: esxiStatus },
                    { label: "Storage role", value: computeAccess.storageRole, source: "Saved setup" },
                    { label: "Next check", value: humanize(asString(esxiReadiness?.next_safe_action) || "Run server check.") }
                  ]}
                />
              </CardContent>
            </Card>
            <Card className="network-details-card" hover={false}>
              <CardHeader>
                <div>
                  <p className="operator-kicker">Saved signals</p>
                  <h2>Server checks</h2>
                </div>
                <span>{serverDetailRows.length} tracked</span>
              </CardHeader>
              <CompactTable>
                <CompactTableHeader>
                  <CompactTableCell>Item</CompactTableCell>
                  <CompactTableCell>Current</CompactTableCell>
                  <CompactTableCell>Status</CompactTableCell>
                </CompactTableHeader>
                <tbody>
                  {serverDetailRows.map((row) => (
                    <CompactTableRow key={row.item}>
                      <CompactTableCell><strong>{row.item}</strong></CompactTableCell>
                      <CompactTableCell>{row.current}</CompactTableCell>
                      <CompactTableCell><StatusBadge label={displayStatus(row.status)} status={statusBadgeStatus(row.status)} /></CompactTableCell>
                    </CompactTableRow>
                  ))}
                </tbody>
              </CompactTable>
            </Card>
            <section className="overview-safe-actions" aria-label="Server configure">
              <ServerConfigurePanel
                activeProfile={activeProfile}
                address={address}
                global={global}
                onSaved={async () => {
                  await onReloadLabProfile?.();
                  await load();
                }}
              />
            </section>
            <ServerSetupShapePanel
              activeProfile={activeProfile}
              address={address}
              currentView={currentView}
              esxiReadiness={esxiReadiness}
              esxiStatus={esxiStatus}
              firmwareSummaries={firmwareSummaries}
              iloStatus={iloStatus}
              raidPlan={raidPlan}
              raidStatus={raidStatus}
            />
            <details className="network-advanced-switch-plan server-advanced-raid-plan">
              <summary>
                <span>
                  <span className="operator-kicker">Advanced</span>
                  <strong>Advanced RAID plan</strong>
                  <small>Drive layout, local datastore readiness, and RAID recommendation stay one level deeper.</small>
                </span>
              </summary>
              <LocalStorageReadinessCard activeProfile={activeProfile} raidPlan={raidPlan} />
            </details>
            <AdvancedDrawer title="Server proof" summary={noProofText}>
              <OperatorWorkspace currentView={currentView} rows={serverRows} compact />
              <ConfigValueList
                values={[
                  { label: "RAID warnings", value: String(stringArray(raidPlan?.warnings).length) },
                  { label: "RAID controller model", value: raidControllerModels(raidPlan) },
                  { label: "ESXi blockers", value: String(stringArray(esxiReadiness?.blockers).length) },
                  { label: "Storage firmware", value: firmwareVersion(firmwareSummaries, "raid") }
                ]}
              />
            </AdvancedDrawer>
          </div>
        </section>
      )}
    </OperatorPage>
  );
}

function serverComputeAccessCardModel({
  activeProfile,
  address,
  currentView,
  esxiReadiness,
  iloStatus,
  raidPlan,
  raidStatus,
  serverStatus
}: {
  activeProfile: LabProfile | null;
  address: LabAddressPlan;
  currentView: CurrentViewModel;
  esxiReadiness: ProviderProbeResult | null;
  iloStatus: string;
  raidPlan: ProviderProbeResult | null;
  raidStatus: string;
  serverStatus: string;
}) {
  const hasTarget = Boolean(address.ilo || address.esxi_management);
  const stateLabel = serverComputeStateLabel(serverStatus, hasTarget);
  const localMode = activeProfile?.features?.storage_location === "server_local" || activeProfile?.features?.netapp_enabled === false;
  const reason = stateLabel === "Blocked"
    ? serverComputeReason({ address, currentView, esxiReadiness, raidPlan, raidStatus })
    : "";

  return {
    badgeStatus: serverComputeBadgeStatus(stateLabel),
    esxiIp: displayAddress(address.esxi_management),
    host: `HPE ${topologyServerModelLabel(activeProfile?.devices?.server_model)}`,
    iloIp: displayAddress(address.ilo),
    reason,
    stateLabel,
    storageRole: localMode ? "Local RAID datastore" : "Shared datastore host"
  };
}

function serverComputeStateLabel(status: string, hasTarget: boolean): "Ready" | "Blocked" | "Not checked" {
  if (!hasTarget) return "Blocked";
  const normalized = status.toLowerCase();
  if (["ready", "ok", "passed", "safe-to-run", "safe_to_run", "success"].includes(normalized)) return "Ready";
  if (!normalized || ["not_checked", "unknown", "running"].includes(normalized)) return "Not checked";
  return "Blocked";
}

function serverComputeBadgeStatus(label: "Ready" | "Blocked" | "Not checked"): StatusBadgeStatus {
  if (label === "Ready") return "ready";
  if (label === "Blocked") return "needs-attention";
  return "not-configured";
}

function serverComputeReason({
  address,
  currentView,
  esxiReadiness,
  raidPlan,
  raidStatus
}: {
  address: LabAddressPlan;
  currentView: CurrentViewModel;
  esxiReadiness: ProviderProbeResult | null;
  raidPlan: ProviderProbeResult | null;
  raidStatus: string;
}) {
  if (!address.ilo && !address.esxi_management) {
    return "Set the iLO and ESXi addresses before running the server check.";
  }
  if (!address.ilo) return "Set the iLO address before running the server check.";
  if (!address.esxi_management) return "Set the ESXi address before running the server check.";
  return humanize(
    currentView.blockers[0] ||
      stringArray(esxiReadiness?.blockers)[0] ||
      stringArray(raidPlan?.blockers)[0] ||
      stringArray(raidPlan?.warnings)[0] ||
      asString(esxiReadiness?.next_safe_action) ||
      asString(esxiReadiness?.message) ||
      (raidStatus && !statusIsReady(raidStatus) ? "Run server check before planning local storage." : "") ||
      "Server access needs attention before setup can continue."
  );
}

function ServerSetupShapePanel({
  activeProfile,
  address,
  currentView,
  esxiReadiness,
  esxiStatus,
  firmwareSummaries,
  iloStatus,
  raidPlan,
  raidStatus
}: {
  activeProfile: LabProfile | null;
  address: LabAddressPlan;
  currentView: CurrentViewModel;
  esxiReadiness: ProviderProbeResult | null;
  esxiStatus: string;
  firmwareSummaries: FirmwareSummary[];
  iloStatus: string;
  raidPlan: ProviderProbeResult | null;
  raidStatus: string;
}) {
  const features = activeProfile?.features ?? null;
  const localServer = features?.storage_location === "server_local" || !features?.netapp_enabled;
  const servicePack = servicePackSummary(firmwareSummaries);
  const firmwareStatus = servicePack === "Scan needed" ? "not_checked" : "ready";
  const pageStatus = strongestStatus([iloStatus, esxiStatus, raidStatus, firmwareStatus]);
  const ladderStatus = statusBadgeStatus(pageStatus);
  const steps: RemediationStep[] = [
    {
      detail: address.ilo ? `iLO target ${address.ilo}` : "iLO management target is not saved yet.",
      label: "iLO management",
      nextAction: statusIsReady(iloStatus) ? "Use guarded inventory, power, and firmware actions." : "Save iLO values, then run Server Live Check.",
      status: statusBadgeStatus(iloStatus)
    },
    {
      detail: raidLayoutLabel(raidPlan),
      label: "RAID and local datastore",
      nextAction: statusIsReady(raidStatus)
        ? "Keep the validated layout as the local datastore intent."
        : "Run Validate RAID before any ESXi datastore or shipment decision.",
      status: statusBadgeStatus(raidStatus)
    },
    {
      detail: displayAddress(address.esxi_management),
      label: "ESXi management",
      nextAction: humanize(asString(esxiReadiness?.next_safe_action) || "Run ESXi management validation."),
      status: statusBadgeStatus(esxiStatus)
    },
    {
      detail: servicePack,
      label: "Firmware baseline",
      nextAction: firmwareStatus === "ready" ? "Use Firmware Upgrades only if a newer selected bundle is required." : "Open Firmware Upgrades and select the matching HPE bundle.",
      status: statusBadgeStatus(firmwareStatus)
    }
  ];
  const validationSummary = statusIsReady(pageStatus)
    ? "Server path is ready; keep validation evidence current before deployment."
    : currentView.summary;
  const optionalStatus = localServer ? "plan-only" : "needs-attention";
  const optionalSummary = localServer
    ? "NetApp and vCenter stay optional for this server-local shipment path."
    : "Shared storage and vCenter handoff remain part of the full lab path.";

  return (
    <Card className="server-setup-card" hover={false}>
      <CardHeader>
        <div>
          <p className="operator-kicker">Server setup shape</p>
          <h2>{localServer ? "Single Server Local VM Path" : "Server With Shared Storage Path"}</h2>
          <p>{localServer ? "Build the server so it can ship with ESXi and local RAID-backed storage." : "Prepare the server for ESXi while Storage and Virtualization own the shared datastore handoff."}</p>
        </div>
        <StatusBadge label={displayStatus(pageStatus)} status={ladderStatus} />
      </CardHeader>
      <CardContent>
        <div className="server-setup-grid" aria-label="Server setup intent">
          <div>
            <span>Needed</span>
            <strong>{localServer ? "RAID-backed ESXi host" : "ESXi host for shared datastore"}</strong>
          </div>
          <div>
            <span>Current</span>
            <strong>{currentView.available ? currentView.summary : "Run Server Live Check"}</strong>
          </div>
          <div>
            <span>Intent</span>
            <strong>{localServer ? "Local datastore leaves with server" : storageLocationLabel(features)}</strong>
          </div>
          <div>
            <span>Validation</span>
            <strong>{validationSummary}</strong>
          </div>
        </div>

        <RemediationLadder
          className="server-remediation-panel"
          defaultOpen={!statusIsReady(pageStatus)}
          status={ladderStatus}
          statusLabel={displayStatus(pageStatus)}
          steps={steps}
          summary={validationSummary}
          title="Server setup path"
        />

        <div className="server-action-strip" aria-label="Server actions">
          <ActionLink to="/firmware-upgrades">Firmware</ActionLink>
          <ActionLink to="/overview#topology-map">Open map workspace</ActionLink>
          <ActionLink to="/validation">Validation</ActionLink>
        </div>

        <RemediationLadder
          className="server-optional-handoff"
          defaultOpen={false}
          status={statusBadgeStatus(optionalStatus)}
          statusLabel={displayStatus(optionalStatus)}
          steps={[
            {
              detail: localServer ? "No NetApp step is required for the server-local path." : "The NetApp workspace owns NFS or iSCSI readiness.",
              label: "Storage handoff",
              nextAction: localServer ? "Keep shared storage collapsed unless the scenario changes." : "Open the NetApp workspace from the map and validate the selected protocol.",
              status: localServer ? "plan-only" : "needs-attention"
            },
            {
              detail: localServer ? "vCenter is optional before shipment." : "The vCenter workspace owns host registration and VM portability.",
              label: "Virtualization handoff",
              nextAction: localServer ? "Open the vCenter workspace only if the build requires central management." : "Open the vCenter workspace after the datastore is ready.",
              status: localServer ? "plan-only" : "needs-attention"
            }
          ]}
          summary={optionalSummary}
          title="Optional shared-lab handoff"
          tone="optional"
        />
      </CardContent>
    </Card>
  );
}

function LocalStorageReadinessCard({
  activeProfile,
  raidPlan
}: {
  activeProfile: LabProfile | null;
  raidPlan: ProviderProbeResult | null;
}) {
  const readiness = objectValue(raidPlan?.local_storage_readiness);
  const facts = objectValue(readiness.facts);
  const candidateVolumes = recordArray(readiness.candidate_volumes);
  const blockers = stringArray(readiness.blockers);
  const warnings = stringArray(readiness.warnings);
  const status = asString(readiness.status) || asString(raidPlan?.status) || "not_checked";
  const isLocalMode = activeProfile?.features?.storage_location === "server_local";
  const scenario = isLocalMode ? "Active standalone path" : "Standalone server path";
  const firstBlocker = blockers[0] || warnings[0] || "";

  return (
    <Card className="local-storage-readiness-card" hover={false}>
      <CardHeader>
        <div>
          <p className="operator-kicker">Single server local storage</p>
          <h2>Local Storage Readiness</h2>
          <p>{asString(readiness.answer) || "Discover controller and drive inventory before planning local ESXi storage."}</p>
        </div>
        <div className="local-storage-status-stack">
          <StatusBadge label={displayStatus(status)} status={statusBadgeStatus(status)} />
          <span>{scenario}</span>
        </div>
      </CardHeader>
      <CardContent>
        <div className="local-storage-facts">
          <LocalStorageFact label="Controllers" value={displayValue(asString(facts.controller_count) || "0")} />
          <LocalStorageFact label="Drives" value={displayValue(asString(facts.physical_drive_count) || "0")} />
          <LocalStorageFact label="Usable" value={displayValue(asString(facts.usable_drive_count) || "0")} />
          <LocalStorageFact label="Logical" value={displayValue(asString(facts.logical_drive_count) || "0")} />
        </div>
        <div className="local-storage-recommendation">
          <strong>Recommendation</strong>
          <span>{asString(readiness.recommendation) || "Run Server Live Check to collect a read-only RAID inventory."}</span>
        </div>
        {firstBlocker && (
          <div className="operator-mini-alert" role="status">
            <strong>{blockers.length ? "Blocked by" : "Review"}</strong>
            <span>{firstBlocker}</span>
          </div>
        )}
      </CardContent>
      <CardFooter>
        <AdvancedDrawer
          title="RAID recommendation"
          summary={candidateVolumes.length ? `${candidateVolumes.length} candidate volume${candidateVolumes.length === 1 ? "" : "s"}` : "No candidate layout"}
        >
          {candidateVolumes.length ? (
            <CompactTable className="local-storage-volume-table">
              <CompactTableHeader>
                <CompactTableCell>Volume</CompactTableCell>
                <CompactTableCell>Purpose</CompactTableCell>
                <CompactTableCell>RAID</CompactTableCell>
                <CompactTableCell>Bays</CompactTableCell>
                <CompactTableCell>Boot</CompactTableCell>
              </CompactTableHeader>
              {candidateVolumes.map((volume, index) => (
                <CompactTableRow key={`${asString(volume.name) || "volume"}-${index}`}>
                  <CompactTableCell><strong>{displayValue(asString(volume.name))}</strong></CompactTableCell>
                  <CompactTableCell>{displayValue(asString(volume.purpose))}</CompactTableCell>
                  <CompactTableCell>{displayValue(asString(volume.raid_level))}</CompactTableCell>
                  <CompactTableCell>{listLabel(stringArray(volume.drive_bays))}</CompactTableCell>
                  <CompactTableCell>{asBoolean(volume.bootable) ? "Yes" : "No"}</CompactTableCell>
                </CompactTableRow>
              ))}
            </CompactTable>
          ) : (
            <p className="operator-muted">{asString(readiness.next_safe_action) || "Run Server Live Check to discover local storage inventory."}</p>
          )}
        </AdvancedDrawer>
      </CardFooter>
    </Card>
  );
}

function LocalStorageFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="local-storage-fact">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

type StorageScenarioModel = {
  activeProtocol: "nfs" | "iscsi" | "none";
  datastoreTarget: string;
  mode: "server_local" | "netapp_shared";
  nextAction: string;
  protocolNextAction: string;
  protocolSummary: string;
  primary: string;
  secondary: string;
  standbyProtocol: "nfs" | "iscsi" | "none";
  status: string;
};

function StorageScenarioDecisionPanel({
  address,
  activeProfile,
  raidPlan,
  storageScenario
}: {
  address: LabAddressPlan;
  activeProfile: LabProfile | null;
  raidPlan: ProviderProbeResult | null;
  storageScenario: StorageScenarioModel;
}) {
  const localActive = storageScenario.mode === "server_local";
  const readiness = objectValue(raidPlan?.local_storage_readiness);
  const facts = objectValue(readiness.facts);
  return (
    <Card className="storage-scenario-card" hover={false}>
      <CardHeader>
        <div>
          <p className="operator-kicker">Storage scenario</p>
          <h2>{storageScenario.primary}</h2>
          <p>{storageScenario.secondary}</p>
        </div>
        <StatusBadge label={localActive ? "Local datastore" : "Shared storage"} status={localActive ? "safe-to-run" : "ready"} />
      </CardHeader>
      <CardContent>
        <div className="storage-scenario-grid">
          <div>
            <span>Primary datastore</span>
            <strong>{storageScenario.datastoreTarget}</strong>
          </div>
          <div>
            <span>Required path</span>
            <strong>{localActive ? "RAID + ESXi local datastore" : "ONTAP + NFS/iSCSI + datastore mount"}</strong>
          </div>
          <div>
            <span>Optional path</span>
            <strong>{localActive ? "NetApp can stay skipped for this build" : "Server-local RAID remains boot/staging"}</strong>
          </div>
          <div>
            <span>Drive evidence</span>
            <strong>{displayValue(asString(facts.usable_drive_count) || asString(facts.physical_drive_count) || "Not checked")}</strong>
          </div>
        </div>
        <div className={localActive ? "storage-scenario-note local" : "storage-scenario-note shared"}>
          <strong>{activeProfile?.name ?? "Active setup"}</strong>
          <span>{storageScenario.nextAction}</span>
        </div>
        {!localActive && (
          <StorageProtocolDecisionStrip
            address={address}
            storageScenario={storageScenario}
          />
        )}
      </CardContent>
    </Card>
  );
}

function storageScenarioModel(activeProfile: LabProfile | null, raidPlan: ProviderProbeResult | null): StorageScenarioModel {
  const features = activeProfile?.features ?? null;
  const storageLocation = asString(features?.storage_location);
  const storageProtocol = asString(features?.storage_protocol).toLowerCase();
  const activeProtocol = storageProtocol === "iscsi" ? "iscsi" : storageProtocol === "none" ? "none" : "nfs";
  const standbyProtocol = activeProtocol === "iscsi" ? "nfs" : activeProtocol === "nfs" ? "iscsi" : "none";
  const netappEnabled = Boolean(features?.netapp_enabled);
  const localMode = storageLocation === "server_local" || !netappEnabled;
  const readiness = objectValue(raidPlan?.local_storage_readiness);
  const status = asString(readiness.status) || asString(raidPlan?.status) || "not_checked";
  const datastoreTarget = localMode
    ? "ESXi local datastore on server RAID"
    : storageLocationLabel(features);
  return {
    activeProtocol: localMode ? "none" : activeProtocol,
    datastoreTarget,
    mode: localMode ? "server_local" : "netapp_shared",
    nextAction: localMode
      ? asString(readiness.next_safe_action) || asString(readiness.recommendation) || "Run Local Storage Live Check, then confirm RAID layout before ESXi datastore work."
      : activeProtocol === "iscsi"
        ? "Run NetApp iSCSI preview, validate ONTAP SAN objects, then validate ESXi iSCSI before datastore mount work."
        : "Run NetApp Live Check and Validate NFS for the active datastore path; use iSCSI only when the profile is switched.",
    protocolNextAction: localMode
      ? "Use the Server page for RAID and local datastore readiness."
      : activeProtocol === "iscsi"
        ? "Active profile uses iSCSI; NFS remains the alternate shared-storage path."
        : "Active profile uses NFS; iSCSI remains available as the block-storage option with separate validation.",
    protocolSummary: localMode
      ? "This build uses server-local storage."
      : activeProtocol === "iscsi"
        ? "Block storage path: LIFs, target IQN, LUN, igroup, map, ESXi session, and VMFS visibility."
        : "File storage path: NFS LIFs, export policy, volume, and ESXi datastore mount readiness.",
    primary: localMode ? "Single server with local ESXi storage" : deploymentScenarioLabel(features),
    secondary: localMode
      ? "The shipped system should not depend on NetApp or vCenter staying online."
      : "Shared storage stays the required VM portability path for this setup.",
    standbyProtocol: localMode ? "none" : standbyProtocol,
    status
  };
}

function StorageProtocolDecisionStrip({
  address,
  storageScenario
}: {
  address: LabAddressPlan;
  storageScenario: StorageScenarioModel;
}) {
  const rows = [
    {
      key: "nfs" as const,
      label: "NFS",
      lifs: address.netapp_nfs_lifs,
      path: "File datastore",
      port: "TCP/2049",
      validation: "Validate NFS",
      status: storageScenario.activeProtocol === "nfs" ? "ready" : "plan_only"
    },
    {
      key: "iscsi" as const,
      label: "iSCSI",
      lifs: address.netapp_iscsi_lifs,
      path: "Block datastore",
      port: "TCP/3260",
      validation: "Validate NetApp + ESXi iSCSI",
      status: storageScenario.activeProtocol === "iscsi" ? "ready" : "plan_only"
    }
  ];
  return (
    <div className="storage-protocol-decision" aria-label="Storage protocol decision">
      <div className="storage-protocol-summary">
        <span>Active protocol</span>
        <strong>{storageScenario.activeProtocol === "iscsi" ? "iSCSI" : "NFS"}</strong>
        <small>{storageScenario.protocolSummary}</small>
      </div>
      {rows.map((row) => {
        const active = storageScenario.activeProtocol === row.key;
        return (
          <div className={active ? "active" : ""} key={row.key}>
            <span>{active ? "Selected path" : "Available option"}</span>
            <strong>{row.label}</strong>
            <small>{row.path} | {row.port} | {row.validation}</small>
            <small>{row.lifs.length ? row.lifs.join(", ") : "No LIFs planned"}</small>
            <SimpleStatusPill status={row.lifs.length ? row.status : "not_configured_yet"} />
          </div>
        );
      })}
      <div className="storage-protocol-next">
        <span>Decision note</span>
        <strong>{storageScenario.protocolNextAction}</strong>
      </div>
    </div>
  );
}

function localStorageRows({
  activeProfile,
  raidPlan,
  storageScenario
}: {
  activeProfile: LabProfile | null;
  raidPlan: ProviderProbeResult | null;
  storageScenario: StorageScenarioModel;
}): OperatorObjectRow[] {
  const readiness = objectValue(raidPlan?.local_storage_readiness);
  const facts = objectValue(readiness.facts);
  const candidateVolumes = recordArray(readiness.candidate_volumes);
  const firstVolume = candidateVolumes[0] ?? {};
  const status = storageScenario.status;
  return [
    {
      checkedAt: formatDateTime(asString(raidPlan?.checked_at)),
      details: [
        { label: "Scenario", value: deploymentScenarioLabel(activeProfile?.features ?? null), source: "Saved setup" },
        { label: "Storage location", value: storageLocationLabel(activeProfile?.features ?? null), source: "Saved setup" },
        { label: "Usable drives", value: displayValue(asString(facts.usable_drive_count) || asString(facts.physical_drive_count)) }
      ],
      freshness: sourceLabel(raidPlan),
      id: "local-datastore",
      nextAction: storageScenario.nextAction,
      source: sourceLabel(raidPlan),
      status,
      summary: asString(readiness.answer) || "Server-local datastore readiness for a standalone ESXi build.",
      target: storageScenario.datastoreTarget,
      title: "Local ESXi Datastore",
      type: "Scenario"
    },
    {
      checkedAt: formatDateTime(asString(raidPlan?.checked_at)),
      details: [
        { label: "Recommended layout", value: raidLayoutLabel(raidPlan), status },
        { label: "Candidate volume", value: displayValue(asString(firstVolume.name) || "No candidate yet") },
        { label: "RAID level", value: displayValue(asString(firstVolume.raid_level)) }
      ],
      freshness: sourceLabel(raidPlan),
      id: "local-raid",
      nextAction: asString(readiness.recommendation) || "Run RAID preview and validate before any guarded apply.",
      source: sourceLabel(raidPlan),
      status,
      summary: asString(raidPlan?.message) || "RAID plan provides the storage backing for local ESXi datastore.",
      target: raidLayoutLabel(raidPlan),
      title: "RAID Backing",
      type: "Server"
    },
    {
      details: [
        { label: "NetApp", value: "Skipped for this scenario", status: "plan_only" },
        { label: "vCenter", value: "Optional unless selected", status: "plan_only" },
        { label: "VM handoff", value: "Export or replicate before shipping" }
      ],
      id: "shared-storage-out-of-scope",
      nextAction: "No NetApp action is required unless the active setup changes to shared storage.",
      source: "Saved setup",
      status: "plan_only",
      summary: "Shared storage controls remain available but are not the required path for this build.",
      target: "Server-local storage",
      title: "Shared Storage Optional",
      type: "Scope"
    }
  ];
}

function storageLocalCurrentView({
  activeProfile,
  raidPlan,
  storageScenario
}: {
  activeProfile: LabProfile | null;
  raidPlan: ProviderProbeResult | null;
  storageScenario: StorageScenarioModel;
}): CurrentViewModel {
  const readiness = objectValue(raidPlan?.local_storage_readiness);
  return currentViewModel({
    available: Boolean(activeProfile),
    blockers: stringArray(readiness.blockers),
    checkedAt: asString(raidPlan?.checked_at),
    details: [
      { label: "Scenario", value: deploymentScenarioLabel(activeProfile?.features ?? null) },
      { label: "Storage location", value: storageLocationLabel(activeProfile?.features ?? null), status: "ready" },
      { label: "NetApp required", value: "No", status: "plan_only" }
    ],
    fixSteps: [
      storageScenario.nextAction,
      "Use the Server page for guarded RAID apply and reset controls.",
      "Switch the active lab setup to NetApp shared storage before running NetApp datastore workflows."
    ],
    recheckCommand: "Run Local Storage Live Check",
    scanDetail: "Local Storage Live Check validates the RAID/local datastore path for standalone ESXi builds.",
    scanLabel: "Local Storage Live Check",
    signals: [raidPlan],
    source: sourceLabel(raidPlan),
    status: storageScenario.status,
    summary: asString(readiness.answer) || "This active setup uses server-local storage; NetApp is not required."
  });
}

export function OperatorStoragePage({ labProfileState, onReloadLabProfile }: OperatorPageProps) {
  const activeProfile = activeLabProfile(labProfileState);
  const address = activeAddressPlan(activeProfile);
  const global = activeProfile?.global_settings ?? null;
  const [actions, setActions] = useState<WorkflowAction[]>([]);
  const [netappPlan, setNetappPlan] = useState<ProviderProbeResult | null>(null);
  const [consoleReadiness, setConsoleReadiness] = useState<ProviderProbeResult | null>(null);
  const [nfsReadiness, setNfsReadiness] = useState<ProviderProbeResult | null>(null);
  const [iscsiSetupPreview, setIscsiSetupPreview] = useState<ProviderProbeResult | null>(null);
  const [esxiIscsiPreview, setEsxiIscsiPreview] = useState<ProviderProbeResult | null>(null);
  const [vcenterNetapp, setVcenterNetapp] = useState<ProviderProbeResult | null>(null);
  const [raidPlan, setRaidPlan] = useState<ProviderProbeResult | null>(null);
  const [firmwareSummaries, setFirmwareSummaries] = useState<FirmwareSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [runState, setRunState] = useState<WorkflowRunState>(emptyRunState);

  async function load() {
    setError("");
    setLoading(true);
    try {
      void safeApi(api.workflowActions, [] as WorkflowAction[]).then((nextActions) => {
        setActions(Array.isArray(nextActions) ? nextActions : []);
      });
      void safeApi(api.netappConsoleReadiness, null).then((nextConsole) => {
        setConsoleReadiness(nextConsole as ProviderProbeResult | null);
      });
      void safeApi(api.netappNfsVcenterReadiness, null).then((nextNfs) => {
        setNfsReadiness(nextNfs);
      });
      void safeApi(api.netappIscsiSetupPreview, null).then((nextIscsiSetup) => {
        setIscsiSetupPreview(nextIscsiSetup);
      });
      void safeApi(api.esxiIscsiDatastorePreview, null).then((nextEsxiIscsi) => {
        setEsxiIscsiPreview(nextEsxiIscsi);
      });
      void safeApi(api.vcenterNetappReadiness, null).then((nextVcenter) => {
        setVcenterNetapp(nextVcenter);
      });
      const [nextPlan, nextFirmware, nextRaidPlan] = await Promise.all([
        safeApi(api.netappLiveState, null),
        safeApi(api.firmwareSummary, [] as FirmwareSummary[]),
        safeApi(api.hpeRaidPlanPreview, null)
      ]);
      setNetappPlan(nextPlan as ProviderProbeResult | null);
      setFirmwareSummaries(Array.isArray(nextFirmware) ? nextFirmware : []);
      setRaidPlan(nextRaidPlan as ProviderProbeResult | null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!activeProfile) return;
    void load();
  }, [activeProfile?.id]);

  const plannedNfs = objectValue(nfsReadiness?.planned_nfs);
  const plannedIscsi = objectValue(iscsiSetupPreview?.iscsi_plan);
  const esxiIscsiState = objectValue(esxiIscsiPreview?.current_state);
  const activeStorageProtocol = asString(activeProfile?.features?.storage_protocol).toLowerCase() || "nfs";
  const iscsiSignalStatus = strongestStatus([
    asString(iscsiSetupPreview?.status),
    asString(esxiIscsiPreview?.status)
  ]);
  const iscsiStatus = address.netapp_iscsi_lifs.length
    ? activeStorageProtocol === "iscsi" ? iscsiSignalStatus : "plan_only"
    : "not_configured_yet";
  const iscsiBlockers = uniqueStrings([
    ...stringArray(iscsiSetupPreview?.blockers),
    ...stringArray(esxiIscsiPreview?.blockers)
  ]);
  const iscsiWarnings = uniqueStrings([
    ...stringArray(iscsiSetupPreview?.warnings),
    ...stringArray(esxiIscsiPreview?.warnings)
  ]);
  const storageScenario = storageScenarioModel(activeProfile, raidPlan);
  const serverLocalStorage = storageScenario.mode === "server_local";
  const storageStatus = storagePageStatus({ netappPlan, nfsReadiness, vcenterNetapp });
  const pageStatus = serverLocalStorage ? storageScenario.status : storageStatus;
  const currentView = serverLocalStorage
    ? storageLocalCurrentView({ activeProfile, raidPlan, storageScenario })
    : storageCurrentView({ address, consoleReadiness, netappPlan, nfsReadiness, vcenterNetapp });
  const storageNextAction = serverLocalStorage ? storageScenario.nextAction : storagePageNextAction({ netappPlan, nfsReadiness, vcenterNetapp });
  const storageRows = useMemo<OperatorObjectRow[]>(
    () => serverLocalStorage ? localStorageRows({ activeProfile, raidPlan, storageScenario }) : [
      {
        checkedAt: currentView.checkedAt,
        details: [
          { label: "Cluster management", value: displayAddress(address.netapp_cluster_mgmt), source: "Saved setup" },
          { label: "SVM management", value: displayAddress(address.netapp_svm_mgmt), source: "Saved setup" },
          { label: "ONTAP version", value: firmwareVersion(firmwareSummaries, "netapp") }
        ],
        freshness: currentView.freshness,
        id: "cluster",
        nextAction: humanize(asString(netappPlan?.next_safe_action) || "Run NetApp Live Check."),
        source: currentView.source,
        status: storageStatus,
        summary: asString(netappPlan?.message) || "ONTAP management and setup readiness.",
        target: displayAddress(address.netapp_cluster_mgmt),
        title: "ONTAP Cluster",
        type: "Storage"
      },
      {
        checkedAt: currentView.checkedAt,
        details: [
          { label: "Console", value: displayValue(asString(objectValue(consoleReadiness?.runtime_state).console)) },
          { label: "Status", value: displayStatus(asString(consoleReadiness?.status) || "not_checked"), status: asString(consoleReadiness?.status) || "not_checked" }
        ],
        freshness: currentView.freshness,
        id: "console",
        nextAction: "Review saved setup details if the console path is wrong.",
        source: sourceLabel(consoleReadiness),
        status: asString(consoleReadiness?.status) || "not_checked",
        summary: "Serial console readiness for NetApp first-contact workflows.",
        target: displayValue(asString(objectValue(consoleReadiness?.runtime_state).console)),
        title: "Console",
        type: "Access"
      },
      {
        checkedAt: currentView.checkedAt,
        details: [
          { label: "NFS LIFs", value: listLabel(address.netapp_nfs_lifs), source: "Saved setup" },
          { label: "Volume", value: displayValue(asString(plannedNfs.volume) || asString(plannedNfs.volume_name)) },
          { label: "Export policy", value: displayValue(asString(plannedNfs.export_policy)) }
        ],
        freshness: currentView.freshness,
        id: "nfs",
        nextAction: humanize(asString(nfsReadiness?.next_safe_action) || "Validate NFS before any datastore mount action."),
        source: sourceLabel(nfsReadiness),
        status: asString(nfsReadiness?.status) || (address.netapp_nfs_lifs.length ? "ready" : "not_configured_yet"),
        summary: asString(nfsReadiness?.message) || "NFS data path and export readiness.",
        target: listLabel(address.netapp_nfs_lifs),
        title: "NFS Data Path",
        type: "Protocol",
        warnings: stringArray(nfsReadiness?.warnings)
      },
      {
        checkedAt: currentView.checkedAt,
        details: [
          { label: "iSCSI LIFs", value: listLabel(address.netapp_iscsi_lifs), source: "Saved setup" },
          { label: "NetApp SAN", value: displayStatus(asString(iscsiSetupPreview?.status) || "not_checked"), status: asString(iscsiSetupPreview?.status) || "not_checked", source: sourceLabel(iscsiSetupPreview) },
          { label: "ESXi datastore", value: displayStatus(asString(esxiIscsiPreview?.status) || "not_checked"), status: asString(esxiIscsiPreview?.status) || "not_checked", source: sourceLabel(esxiIscsiPreview) },
          { label: "Target portal", value: displayValue(asString(plannedIscsi.target_portal) || asString(plannedIscsi.target_ip) || listLabel(address.netapp_iscsi_lifs)) },
          { label: "VMFS datastore", value: displayValue(asString(esxiIscsiState.datastore_name) || asString(plannedIscsi.datastore_name)) }
        ],
        freshness: currentView.freshness,
        id: "iscsi",
        nextAction: humanize(asString(esxiIscsiPreview?.next_safe_action) || asString(iscsiSetupPreview?.next_safe_action) || "Preview iSCSI, validate NetApp iSCSI, then validate ESXi iSCSI before any guarded apply."),
        source: firstSource([esxiIscsiPreview, iscsiSetupPreview]),
        status: iscsiStatus,
        summary: asString(esxiIscsiPreview?.message) || asString(iscsiSetupPreview?.message) || "iSCSI SAN path is available as a selectable storage option with separate NetApp and ESXi validation.",
        target: listLabel(address.netapp_iscsi_lifs),
        title: "iSCSI Data Path",
        type: "Protocol",
        warnings: uniqueStrings([...iscsiBlockers, ...iscsiWarnings])
      },
      {
        checkedAt: currentView.checkedAt,
        details: [
          { label: "Datastore", value: datastoreName(vcenterNetapp), status: datastoreVisibleStatus(vcenterNetapp) },
          { label: "vCenter-NetApp source", value: sourceLabel(vcenterNetapp) }
        ],
        freshness: currentView.freshness,
        id: "datastore",
        nextAction: humanize(asString(vcenterNetapp?.next_safe_action) || "No datastore action required."),
        source: sourceLabel(vcenterNetapp),
        status: datastoreVisibleStatus(vcenterNetapp),
        summary: asString(vcenterNetapp?.message) || "Datastore visibility through vCenter.",
        target: datastoreName(vcenterNetapp),
        title: "vCenter Datastore",
        type: "Readiness"
      }
    ],
    [activeProfile, activeStorageProtocol, address.netapp_cluster_mgmt, address.netapp_iscsi_lifs, address.netapp_nfs_lifs, address.netapp_svm_mgmt, consoleReadiness, currentView, esxiIscsiPreview, esxiIscsiState, firmwareSummaries, iscsiBlockers, iscsiSetupPreview, iscsiStatus, iscsiWarnings, netappPlan, nfsReadiness, plannedIscsi, plannedNfs, raidPlan, serverLocalStorage, storageScenario, storageStatus, vcenterNetapp]
  );
  const profileReady = Boolean(activeProfile);
  const headerActionIds = serverLocalStorage
    ? ["raid.validate", "raid.pending-check", "raid.plan"]
    : [
      "netapp.live-state",
      "netapp.validate-setup",
      "netapp.setup-preview",
      "netapp.nfs-setup-validate",
      "netapp.iscsi-setup-preview",
      "netapp.iscsi-setup-validate",
      "esxi.iscsi-datastore-preview"
    ];
  const headerLabel = serverLocalStorage ? "Local Storage Live Check" : "NetApp Live Check";
  const runStorageChecks = async () => {
    const actionById = new Map(actions.map((action) => [action.action_id, action]));
    const results: Array<{ action: WorkflowAction | null; result: WorkflowActionRun }> = [];
    for (const actionId of headerActionIds) {
      const result = await api.runWorkflowAction(actionId);
      results.push({ action: actionById.get(actionId) ?? null, result });
    }
    const blocked = results.filter(({ result }) => isProblemRun(result));
    if (blocked.length) {
      const first = blocked[0];
      const label = first.action ? humanWorkflowActionLabel(first.action) : humanize(first.result.action_label || first.result.action_id);
      const detail = first.result.blockers[0] || first.result.next_action || first.result.summary || displayStatus(first.result.status);
      return `${headerLabel}: ${results.length} checks run; ${blocked.length} need attention. ${label}: ${humanize(detail)}`;
    }
    return `${headerLabel}: ${results.length} checks completed with device evidence.`;
  };
  const storageRegions: Record<string, ReactNode> = profileReady ? {
    "advanced-proof": (
      <AdvancedDrawer title="Storage proof" summary={noProofText}>
        <OperatorWorkspace currentView={currentView} rows={storageRows} compact />
        <ConfigValueList
          values={[
            { label: "NetApp blockers", value: String(stringArray(netappPlan?.blockers).length) },
            { label: "NFS warnings", value: String(stringArray(nfsReadiness?.warnings).length) },
            { label: "iSCSI NetApp status", value: displayStatus(asString(iscsiSetupPreview?.status) || "not_checked") },
            { label: "iSCSI ESXi status", value: displayStatus(asString(esxiIscsiPreview?.status) || "not_checked") },
            { label: "iSCSI blockers", value: String(iscsiBlockers.length) },
            { label: "vCenter-NetApp source", value: sourceLabel(vcenterNetapp) }
          ]}
        />
        <OperatorReferencePanel
          actionLabel="Open validation"
          actionTo="/validation"
          ariaLabel="Storage reference"
          currentView={currentView}
          rows={storageRows}
          subtitle="ONTAP, NFS, iSCSI, datastore"
          tableTitle="Storage Signals"
          title="Storage readiness at a glance"
        />
      </AdvancedDrawer>
    ),
    configure: (
      <section className="overview-safe-actions" aria-label="Storage configure">
        <StorageConfigurePanel
          activeProfile={activeProfile}
          address={address}
          features={activeProfile?.features ?? null}
          global={global}
          onSaved={async () => {
            await onReloadLabProfile?.();
            await load();
          }}
        />
      </section>
    ),
    "local-readiness": serverLocalStorage ? <LocalStorageReadinessCard activeProfile={activeProfile} raidPlan={raidPlan} /> : null,
    "ontap-readiness": (
      <NetAppOntapReadinessCard
        address={address}
        activeProfile={activeProfile}
        consoleReadiness={consoleReadiness}
        nfsReadiness={nfsReadiness}
        onReload={load}
      />
    ),
    scenario: (
      <StorageScenarioDecisionPanel
        address={address}
        activeProfile={activeProfile}
        raidPlan={raidPlan}
        storageScenario={storageScenario}
      />
    )
  } : {};
  const storagePath = storagePathCardModel({
    activeProtocol: activeStorageProtocol,
    pageStatus,
    serverLocalStorage,
    storageBlocker: currentView.blockers[0] || "",
    storageNextAction,
    storageScenario,
    vcenterNetapp
  });

  async function runDefaultStorageCheck() {
    if (!profileReady || runState.runningActionId) return;
    setRunState({ error: "", message: "", runningActionId: "storage-path-check" });
    try {
      const message = await runStorageChecks();
      setRunState({ error: "", message, runningActionId: "" });
      await load();
    } catch (err) {
      setRunState({ error: errorMessage(err), message: "", runningActionId: "" });
    }
  }

  return (
    <OperatorPage title="Storage">
      <div className="operator-surface-heading">
        <p className="operator-kicker">Setup</p>
        <h1>Storage</h1>
        <p>Which storage path this kit uses, and what to do next.</p>
      </div>
      <Feedback loading={false} error={profileReady ? error : ""} />
      <section className="storage-path-surface" aria-label="Storage Path">
        <Card className="storage-path-card" hover={false}>
          <CardHeader>
            <div>
              <p className="operator-kicker">Storage path</p>
              <h2>{storagePath.activePath}</h2>
            </div>
            <StatusBadge label={storagePath.stateLabel} status={storagePath.badgeStatus} />
          </CardHeader>
          <CardContent>
            <dl className="storage-path-fields">
              <div>
                <dt>Active path</dt>
                <dd>{storagePath.activePath}</dd>
              </div>
              <div>
                <dt>Protocol</dt>
                <dd><span className="storage-path-protocol-chip">{storagePath.protocol}</span></dd>
              </div>
              <div>
                <dt>Target datastore</dt>
                <dd>{storagePath.targetDatastore}</dd>
              </div>
            </dl>
            {storagePath.reason && (
              <div className="storage-path-reason" role="note">
                <strong>Needs attention</strong>
                <span>{storagePath.reason}</span>
              </div>
            )}
            {runState.message && <div className="operator-feedback storage-path-feedback">{runState.message}</div>}
            {runState.error && <div className="operator-feedback error storage-path-feedback">{runState.error}</div>}
          </CardContent>
          <CardFooter>
            <div className="storage-path-actions">
              <button
                className="operator-primary-button"
                disabled={!profileReady || Boolean(runState.runningActionId)}
                onClick={() => void runDefaultStorageCheck()}
                type="button"
              >
                <RefreshCw size={16} />
                {runState.runningActionId ? "Checking" : "Run storage check"}
              </button>
              <button
                aria-expanded={detailsOpen}
                className="secondary-button"
                onClick={() => setDetailsOpen((current) => !current)}
                type="button"
              >
                View storage details
              </button>
            </div>
          </CardFooter>
        </Card>
      </section>
      {detailsOpen && profileReady && (
        <section className="storage-path-details" aria-label="Storage path details">
          <div className="storage-path-details-grid">
            {storageRegions.scenario}
            {storageRegions.configure}
            {serverLocalStorage ? storageRegions["local-readiness"] : storageRegions["ontap-readiness"]}
            {storageRegions["advanced-proof"]}
          </div>
        </section>
      )}
    </OperatorPage>
  );
}

function storagePathCardModel({
  activeProtocol,
  pageStatus,
  serverLocalStorage,
  storageBlocker,
  storageNextAction,
  storageScenario,
  vcenterNetapp
}: {
  activeProtocol: string;
  pageStatus: string;
  serverLocalStorage: boolean;
  storageBlocker: string;
  storageNextAction: string;
  storageScenario: StorageScenarioModel;
  vcenterNetapp: ProviderProbeResult | null;
}) {
  const normalizedStatus = pageStatus.toLowerCase();
  const stateLabel = storagePathStateLabel(normalizedStatus);
  const protocol = serverLocalStorage ? "Local" : activeProtocol === "iscsi" ? "iSCSI" : "NFS";
  const targetDatastore = serverLocalStorage
    ? storageScenario.datastoreTarget
    : datastoreVisibleStatus(vcenterNetapp) === "ready" ? datastoreName(vcenterNetapp) : "Not mounted";
  return {
    activePath: serverLocalStorage ? "Server-local RAID" : "NetApp shared storage",
    badgeStatus: storagePathBadgeStatus(stateLabel),
    protocol,
    reason: stateLabel === "Blocked" ? humanize(storageBlocker || storageNextAction || "Storage needs attention before datastore work.") : "",
    stateLabel,
    targetDatastore
  };
}

function storagePathStateLabel(status: string): "Ready" | "Blocked" | "Not checked" {
  if (["ready", "safe-to-run", "plan_only"].includes(status)) return "Ready";
  if (["not_checked", "unknown"].includes(status)) return "Not checked";
  return "Blocked";
}

function storagePathBadgeStatus(label: "Ready" | "Blocked" | "Not checked"): StatusBadgeStatus {
  if (label === "Ready") return "ready";
  if (label === "Blocked") return "blocked";
  return "not-configured";
}

function NetAppOntapReadinessCard({
  address,
  activeProfile,
  consoleReadiness,
  nfsReadiness,
  onReload
}: {
  address: LabAddressPlan;
  activeProfile: LabProfile | null;
  consoleReadiness: ProviderProbeResult | null;
  nfsReadiness: ProviderProbeResult | null;
  onReload: () => Promise<void> | void;
}) {
  const [runState, setRunState] = useState<WorkflowRunState>(emptyRunState);
  const [directReadiness, setDirectReadiness] = useState<ProviderProbeResult | null>(consoleReadiness);
  const [liveState, setLiveState] = useState<ProviderProbeResult | null>(null);
  const [iscsiSetup, setIscsiSetup] = useState<ProviderProbeResult | null>(null);
  const [esxiIscsiDatastore, setEsxiIscsiDatastore] = useState<ProviderProbeResult | null>(null);
  const effectiveReadiness = directReadiness ?? consoleReadiness;
  const runtimeState = objectValue(liveState?.runtime_state ?? liveState ?? effectiveReadiness?.runtime_state);
  const consoleState = objectValue(runtimeState.console);
  const management = objectValue(runtimeState.management);
  const apiState = objectValue(runtimeState.api);
  const storage = objectValue(runtimeState.storage);
  const protocolOptions = objectValue(runtimeState.protocol_options);
  const storageChecks = objectValue(storage.checks);
  const selectedPort = consolePathFromNetapp(effectiveReadiness);
  const selectedBaud = displayValue(asString(consoleState.baud));
  const promptState = asString(consoleState.prompt_state) || asString(consoleReadiness?.selected_prompt_state);
  const promptLabel = asString(consoleState.prompt_label) || asString(consoleReadiness?.selected_prompt_label);
  const clusterReachable = asBoolean(management.rest_443_reachable) || asBoolean(management.ssh_22_reachable);
  const credentialsPresent = asBoolean(apiState.access_values_present);
  const storageReady = asBoolean(storage.ready) || asString(nfsReadiness?.status) === "ready";
  const protocol = asString(storage.protocol) || asString(activeProfile?.features?.storage_protocol) || "nfs";
  const protocolLabel = protocol.toLowerCase() === "iscsi" ? "iSCSI" : protocol.toUpperCase();
  const serviceStatus = asString(storage.service_status) || "not_checked";
  const serviceEnabled = storage.service_enabled;
  const serviceReady = asBoolean(serviceEnabled) || serviceStatus === "ready";
  const nfsLifs = stringArray(storage.nfs_lifs_detected).length
    ? stringArray(storage.nfs_lifs_detected)
    : address.netapp_nfs_lifs;
  const iscsiLifs = stringArray(storage.iscsi_lifs_detected).length
    ? stringArray(storage.iscsi_lifs_detected)
    : address.netapp_iscsi_lifs;
  const activeLifs = protocol.toLowerCase() === "iscsi" ? iscsiLifs : nfsLifs;
  const protocolPort = protocol.toLowerCase() === "iscsi" ? 3260 : 2049;
  const lifPortChecks = protocol.toLowerCase() === "iscsi"
    ? recordArray(storageChecks.iscsi_lifs_3260)
    : recordArray(storageChecks.nfs_lifs_2049);
  const reachableLifs = lifPortChecks.filter((check) => asBoolean(objectValue(check).reachable)).length;
  const storageBlockers = stringArray(storage.blockers);
  const storageWarnings = uniqueStrings([
    ...stringArray(liveState?.warnings),
    ...stringArray(nfsReadiness?.warnings),
    ...stringArray(effectiveReadiness?.warnings)
  ]).filter(isOperatorStorageWarning);
  const iscsiSetupStatus = asString(iscsiSetup?.status) || "not_checked";
  const iscsiSetupPlan = objectValue(iscsiSetup?.iscsi_plan);
  const iscsiInitiators = stringArray(iscsiSetupPlan.initiator_iqns);
  const iscsiInitiatorDiscovery = objectValue(iscsiSetupPlan.initiator_discovery);
  const iscsiCurrentState = objectValue(iscsiSetup?.current_state);
  const iscsiCurrentService = objectValue(iscsiCurrentState.iscsi_service);
  const iscsiCurrentLun = objectValue(iscsiCurrentState.lun);
  const iscsiCurrentIgroup = objectValue(iscsiCurrentState.igroup);
  const iscsiCurrentMap = objectValue(iscsiCurrentState.lun_map);
  const esxiIscsiState = objectValue(esxiIscsiDatastore?.current_state);
  const esxiIscsiDatastoreState = objectValue(esxiIscsiState.datastore);
  const esxiIscsiBlockers = stringArray(esxiIscsiDatastore?.blockers);
  const esxiIscsiStatus = asString(esxiIscsiDatastore?.status) || "not_checked";
  const esxiIscsiRemediation = objectValue(esxiIscsiDatastore?.remediation_plan);
  const esxiIscsiRemediationSteps: RemediationStep[] = recordArray(esxiIscsiRemediation.steps).map((step) => ({
    detail: asString(step.detail) || "No detail captured yet.",
    label: asString(step.label) || "iSCSI step",
    nextAction: asString(step.next_action) || asString(step.nextAction) || "Run the next safe validation action.",
    status: statusBadgeStatus(asString(step.status) || "not_checked")
  }));
  const esxiIscsiRemediationStatus = asString(esxiIscsiRemediation.status) || (esxiIscsiBlockers.length ? "blocked" : esxiIscsiStatus);
  const esxiIscsiRemediationSummary =
    asString(esxiIscsiRemediation.summary) ||
    (esxiIscsiBlockers.length
      ? "ESXi iSCSI needs operator remediation before VMFS can be treated as ready."
      : "Run Preview ESXi iSCSI to load the session and datastore remediation ladder.");
  const iscsiSetupBlockers = stringArray(iscsiSetup?.blockers);
  const iscsiRequiredFlags = stringArray(iscsiSetup?.required_flags);
  const iscsiFlagState = objectValue(iscsiSetup?.flag_state);
  const iscsiApplyState = objectValue(iscsiSetup?.apply);
  const iscsiGateStateEvaluated = Object.keys(iscsiFlagState).length > 0;
  const iscsiApplyEvidence = [
    `ONTAP writes ${asBoolean(iscsiApplyState.ontap_writes_attempted) ? "attempted" : "not attempted"}`,
    `ESXi writes ${asBoolean(iscsiApplyState.esxi_writes_attempted) ? "attempted" : "not attempted"}`,
    `vCenter writes ${asBoolean(iscsiApplyState.vcenter_writes_attempted) ? "attempted" : "not attempted"}`
  ];
  const iscsiGateState = [
    ["Read/write mode", asBoolean(iscsiFlagState.local_lab_readwrite)],
    ["Apply flag", asBoolean(iscsiFlagState.netapp_iscsi_setup_apply)],
    ["Confirm phrase", asBoolean(iscsiFlagState.netapp_iscsi_setup_confirm)],
    ["Storage create", asBoolean(iscsiFlagState.netapp_iscsi_setup_allow_storage_create)]
  ];
  const protocolOptionRows = ["nfs", "iscsi"].map((key) => {
    const option = objectValue(protocolOptions[key]);
    const lifs = stringArray(option.lifs);
    const checks = recordArray(option.checks);
    const reachable = asString(option.reachable_lif_count) || String(checks.filter((check) => asBoolean(objectValue(check).reachable)).length);
    return {
      active: asBoolean(option.active) || protocol.toLowerCase() === key,
      blockers: stringArray(option.blockers),
      key,
      label: asString(option.label) || (key === "iscsi" ? "iSCSI" : "NFS"),
      lifs,
      port: asString(option.port) || (key === "iscsi" ? "3260" : "2049"),
      ready: asBoolean(option.ready),
      reachable,
      serviceStatus: asString(option.service_status) || "not_checked"
    };
  });
  const rows = [
    {
      detail: selectedBaud === "Not set up yet" ? selectedPort : `${selectedPort} @ ${selectedBaud}`,
      label: "Console",
      status: promptState ? "ready" : "blocked",
      value: promptLabel || promptState || "Not confirmed"
    },
    {
      detail: [
        asBoolean(management.rest_443_reachable) ? "443" : "",
        asBoolean(management.ssh_22_reachable) ? "22" : ""
      ].filter(Boolean).join(" / ") || "No live TCP proof",
      label: "Cluster",
      status: clusterReachable ? "ready" : "blocked",
      value: displayAddress(asString(management.cluster_mgmt_ip) || address.netapp_cluster_mgmt)
    },
    {
      detail: lifPortChecks.length
        ? `${reachableLifs}/${lifPortChecks.length} answering TCP/${protocolPort}`
        : `${activeLifs.length} planned LIF${activeLifs.length === 1 ? "" : "s"}`,
      label: protocolLabel,
      status: storageReady ? "ready" : storageBlockers.length ? "blocked" : "warning",
      value: activeLifs.length ? activeLifs.join(", ") : "Not discovered"
    },
    {
      detail: serviceStatus === "not_checked" ? "Run NetApp Live Check for live service proof" : displayStatus(serviceStatus),
      label: "Protocol service",
      status: serviceReady ? "ready" : serviceStatus === "not_checked" ? "warning" : "blocked",
      value: serviceReady ? "Enabled" : "Blocked or not licensed"
    },
    {
      detail: credentialsPresent
        ? "Ready for guarded read-only validation"
        : "Set NETAPP_API_PASSWORD in .env.local.real-lab, then restart the backend",
      label: "Credentials",
      status: credentialsPresent ? "ready" : "blocked",
      value: credentialsPresent ? "Present" : "Password missing"
    }
  ];
  const actionButtons: Array<{
    icon: ReactNode;
    label: string;
    onClick: () => Promise<ProviderProbeResult>;
  }> = [
    { icon: <RefreshCw size={16} />, label: "Discover Console", onClick: api.runNetappConsoleDiscovery },
    { icon: <Play size={16} />, label: "Read Console", onClick: api.runNetappConsoleReadState },
    { icon: <ShieldCheck size={16} />, label: "Check Login State", onClick: api.runNetappConsoleLoginState },
    { icon: <Route size={16} />, label: "Check Protocols", onClick: api.runNetappLiveState },
    { icon: <Route size={16} />, label: "Preview iSCSI", onClick: api.netappIscsiSetupPreview },
    { icon: <Play size={16} />, label: "Apply iSCSI", onClick: api.runNetappIscsiSetupApply },
    { icon: <ShieldCheck size={16} />, label: "Validate iSCSI", onClick: api.validateNetappIscsiSetup },
    { icon: <Route size={16} />, label: "Preview ESXi iSCSI", onClick: api.esxiIscsiDatastorePreview },
    { icon: <ShieldCheck size={16} />, label: "Validate ESXi iSCSI", onClick: api.validateEsxiIscsiDatastore }
  ];

  useEffect(() => {
    setDirectReadiness(consoleReadiness);
  }, [consoleReadiness]);

  useEffect(() => {
    let ignore = false;
    void safeApi(api.netappConsoleReadiness, null).then((nextReadiness) => {
      if (!ignore) setDirectReadiness(nextReadiness as ProviderProbeResult | null);
    });
    void safeApi(api.netappLiveState, null).then((nextLiveState) => {
      if (!ignore) setLiveState(nextLiveState as ProviderProbeResult | null);
    });
    void safeApi(api.netappIscsiSetupPreview, null).then((nextIscsiSetup) => {
      if (!ignore) setIscsiSetup(nextIscsiSetup as ProviderProbeResult | null);
    });
    void safeApi(api.esxiIscsiDatastorePreview, null).then((nextEsxiIscsi) => {
      if (!ignore) setEsxiIscsiDatastore(nextEsxiIscsi as ProviderProbeResult | null);
    });
    return () => {
      ignore = true;
    };
  }, []);

  async function runDirectAction(label: string, onClick: () => Promise<ProviderProbeResult>) {
    setRunState({ error: "", message: "", runningActionId: label });
    try {
      const result = await onClick();
      const nextReadiness = await safeApi(api.netappConsoleReadiness, null);
      const nextLiveState = await safeApi(api.netappLiveState, null);
      const nextIscsiSetup = await safeApi(api.netappIscsiSetupPreview, null);
      const nextEsxiIscsi = await safeApi(api.esxiIscsiDatastorePreview, null);
      setDirectReadiness(nextReadiness as ProviderProbeResult | null);
      setLiveState(nextLiveState as ProviderProbeResult | null);
      setIscsiSetup(asString(result.action).startsWith("iscsi-setup") ? result : nextIscsiSetup as ProviderProbeResult | null);
      setEsxiIscsiDatastore(asString(result.action).startsWith("esxi-iscsi-datastore") ? result : nextEsxiIscsi as ProviderProbeResult | null);
      setRunState({
        error: "",
        message: `${label}: ${displayStatus(asString(result.status) || "completed")}. ${asString(result.message)}`,
        runningActionId: ""
      });
      await onReload();
    } catch (err) {
      setRunState({ error: errorMessage(err), message: "", runningActionId: "" });
    }
  }

  return (
    <Card aria-label="ONTAP readiness" className="operator-section ontap-readiness-card" hover={false}>
      <CardHeader>
        <div>
          <p className="operator-kicker">ONTAP readiness</p>
          <h2>NetApp access path</h2>
        </div>
        <StatusBadge className="simple-status-pill" label={credentialsPresent ? "Ready to validate" : "Needs password"} status={credentialsPresent ? "ready" : "blocked"} />
      </CardHeader>
      <CardContent>
        <div className="ontap-readiness-grid">
          {rows.map((row) => (
            <div className="ontap-readiness-item" key={row.label}>
              <span>{row.label}</span>
              <strong>{row.value}</strong>
              <small>{row.detail}</small>
              <SimpleStatusPill status={row.status} />
            </div>
          ))}
        </div>
        {storageBlockers.length > 0 && (
          <div className="operator-mini-alert" role="status">
            <strong>Storage blocker</strong>
            <span>{storageBlockers[0]}</span>
          </div>
        )}
        {!storageBlockers.length && storageWarnings.length > 0 && (
          <div className="operator-mini-alert" role="status">
            <strong>Storage warning</strong>
            <span>{storageWarnings[0]}</span>
          </div>
        )}
        <div className="protocol-option-strip" aria-label="Storage protocol options">
          {protocolOptionRows.map((option) => (
            <div className={option.active ? "active" : ""} key={option.key}>
              <span>{option.active ? "Active" : "Option"}</span>
              <strong>{option.label}</strong>
              <small>
                {option.lifs.length ? option.lifs.join(", ") : "No LIFs planned"} | {option.reachable}/{option.lifs.length || 0} TCP/{option.port} | {displayStatus(option.serviceStatus)}
              </small>
              <SimpleStatusPill status={option.ready ? "ready" : option.blockers.length ? "blocked" : "not_checked"} />
            </div>
          ))}
        </div>
        <div className="iscsi-setup-strip" aria-label="iSCSI setup path">
          <div>
            <span>iSCSI setup path</span>
            <strong>{displayStatus(iscsiSetupStatus)}</strong>
            <small>{asString(iscsiSetup?.message) || "Preview LUN, igroup, initiators, and ESXi datastore work before any apply exists."}</small>
          </div>
          <div>
            <span>LUN / igroup / datastore</span>
            <strong>
              {asString(iscsiSetupPlan.lun_name) || "Not set up yet"} / {asString(iscsiSetupPlan.igroup_name) || "Not set up yet"} /{" "}
              {asString(iscsiSetupPlan.datastore_name) || "Not set up yet"}
            </strong>
            <small>{iscsiSetupBlockers[0] || "Protocol ready; guarded create-and-mount workflow still needs to be built before apply."}</small>
          </div>
          <div>
            <span>ESXi initiator</span>
            <strong>{iscsiInitiators[0] || "Not discovered yet"}</strong>
            <small>{asString(iscsiInitiatorDiscovery.source) || "Run preview to discover the live initiator IQN."}</small>
          </div>
          <div>
            <span>ONTAP SAN state</span>
            <strong>
              LUN {asBoolean(iscsiCurrentLun.exists) ? "exists" : "missing"} / igroup{" "}
              {asBoolean(iscsiCurrentIgroup.exists) ? "exists" : "missing"} / map {asBoolean(iscsiCurrentMap.exists) ? "exists" : "missing"}
            </strong>
            <small>{asString(iscsiCurrentService.target_iqn) || "Run preview to read the live ONTAP target IQN."}</small>
          </div>
          <div>
            <span>ESXi iSCSI evidence</span>
            <strong>
              {Number(esxiIscsiState.adapter_count ?? 0)} adapters / {Number(esxiIscsiState.iscsi_path_count ?? 0)} paths / datastore{" "}
              {asBoolean(esxiIscsiState.datastore_visible) ? "visible" : "not visible"}
            </strong>
            <small>
              {esxiIscsiBlockers[0] ||
                asString(esxiIscsiDatastoreState.type) ||
                "Run Preview ESXi iSCSI to read adapter, session, device, and VMFS state."}
            </small>
          </div>
          <SimpleStatusPill status={iscsiSetupBlockers.length ? "blocked" : iscsiSetupStatus} />
          <SimpleStatusPill status={esxiIscsiBlockers.length ? "blocked" : esxiIscsiStatus} />
        </div>
        <RemediationLadder
          className="iscsi-remediation-panel"
          defaultOpen={statusBadgeStatus(esxiIscsiRemediationStatus) !== "ready"}
          emptyStep={{
            detail: "Adapter, target session, device, and VMFS state have not been read yet.",
            label: "Load live ESXi evidence",
            nextAction: "Run Preview ESXi iSCSI before making datastore decisions.",
            status: "not-configured"
          }}
          status={statusBadgeStatus(esxiIscsiRemediationStatus)}
          statusLabel={displayStatus(esxiIscsiRemediationStatus)}
          steps={esxiIscsiRemediationSteps}
          summary={esxiIscsiRemediationSummary}
          title="ESXi iSCSI remediation"
          tone="optional"
        />
        <details className="iscsi-gates-panel">
          <summary>iSCSI gates and write evidence</summary>
          <div className="iscsi-gates-grid">
            <div>
              <span>Required gates</span>
              <strong>{iscsiRequiredFlags.length ? `${iscsiRequiredFlags.length} gates` : "Run preview to load gates"}</strong>
              <small>{iscsiRequiredFlags.join(" | ") || "The backend will list the exact flags before any iSCSI apply can run."}</small>
            </div>
            <div>
              <span>Current gate state</span>
              <strong>
                {iscsiGateStateEvaluated ? `${iscsiGateState.filter(([, ready]) => ready).length}/${iscsiGateState.length} satisfied` : "Not evaluated"}
              </strong>
              <small>
                {iscsiGateStateEvaluated
                  ? iscsiGateState.map(([label, ready]) => `${label}: ${ready ? "ready" : "blocked"}`).join(" | ")
                  : "Click Apply iSCSI to evaluate the real flags before any write can be attempted."}
              </small>
            </div>
            <div>
              <span>Write evidence</span>
              <strong>{asString(iscsiSetup?.action) === "iscsi-setup-apply" ? "Apply response captured" : "No apply response yet"}</strong>
              <small>{iscsiApplyEvidence.join(" | ")}</small>
            </div>
          </div>
        </details>
      </CardContent>
      <CardFooter>
        <details className="storage-advanced-actions" aria-label="Advanced storage actions">
          <summary>Advanced storage actions</summary>
          <div className="page-run-buttons">
            {actionButtons.map((button) => {
              const running = runState.runningActionId === button.label;
              return (
                <div className="run-button-wrap" key={button.label}>
                  <button
                    disabled={running}
                    onClick={() => void runDirectAction(button.label, button.onClick)}
                    type="button"
                  >
                    {button.icon}
                    {running ? "Running" : button.label}
                  </button>
                </div>
              );
            })}
          </div>
          {(runState.message || runState.error) && (
            <p className={runState.error ? "operator-action-message error" : "operator-action-message"}>
              {runState.error || runState.message}
            </p>
          )}
        </details>
      </CardFooter>
    </Card>
  );
}

function NetAppWorkspaceStorageControls({
  activeProfile,
  address,
  onReload,
  storageProtocol
}: {
  activeProfile: LabProfile | null;
  address: LabAddressPlan;
  onReload: () => Promise<void> | void;
  storageProtocol: string;
}) {
  const [runState, setRunState] = useState<WorkflowRunState>(emptyRunState);
  const [consoleReadiness, setConsoleReadiness] = useState<ProviderProbeResult | null>(null);
  const [liveState, setLiveState] = useState<ProviderProbeResult | null>(null);
  const [setupPreview, setSetupPreview] = useState<ProviderProbeResult | null>(null);
  const [nfsValidation, setNfsValidation] = useState<ProviderProbeResult | null>(null);
  const [iscsiSetup, setIscsiSetup] = useState<ProviderProbeResult | null>(null);
  const [esxiIscsiDatastore, setEsxiIscsiDatastore] = useState<ProviderProbeResult | null>(null);
  const activeStorageProtocol = storageProtocol === "iscsi" ? "iscsi" : "nfs";
  const iscsiFlagState = objectValue(iscsiSetup?.flag_state);
  const iscsiApplyState = objectValue(iscsiSetup?.apply);
  const iscsiRequiredFlags = stringArray(iscsiSetup?.required_flags);
  const gateRows = [
    ["Read/write mode", asBoolean(iscsiFlagState.local_lab_readwrite)],
    ["Apply flag", asBoolean(iscsiFlagState.netapp_iscsi_setup_apply)],
    ["Confirm phrase", asBoolean(iscsiFlagState.netapp_iscsi_setup_confirm)],
    ["Storage create", asBoolean(iscsiFlagState.netapp_iscsi_setup_allow_storage_create)]
  ] as const;
  const gateEvaluated = Object.keys(iscsiFlagState).length > 0;
  const gateReadyCount = gateRows.filter(([, ready]) => ready).length;
  const applyEvidence = [
    `ONTAP writes ${asBoolean(iscsiApplyState.ontap_writes_attempted) ? "attempted" : "not attempted"}`,
    `ESXi writes ${asBoolean(iscsiApplyState.esxi_writes_attempted) ? "attempted" : "not attempted"}`,
    `vCenter writes ${asBoolean(iscsiApplyState.vcenter_writes_attempted) ? "attempted" : "not attempted"}`
  ];
  const evidenceRows = [
    {
      detail: sourceLabel(consoleReadiness),
      label: "Console",
      status: asString(consoleReadiness?.status) || "not_checked",
      value: asString(objectValue(objectValue(consoleReadiness?.runtime_state).console).prompt_label) || asString(consoleReadiness?.selected_prompt_label) || "Not checked"
    },
    {
      detail: sourceLabel(liveState),
      label: "Protocols",
      status: asString(liveState?.status) || "not_checked",
      value: asString(liveState?.message) || "Live protocol state not read"
    },
    {
      detail: sourceLabel(setupPreview),
      label: "Setup preview",
      status: asString(setupPreview?.status) || "not_checked",
      value: asString(setupPreview?.message) || "Setup plan not previewed"
    },
    {
      detail: sourceLabel(nfsValidation),
      label: "NFS validate",
      status: asString(nfsValidation?.status) || "not_checked",
      value: asString(nfsValidation?.message) || listLabel(address.netapp_nfs_lifs)
    },
    {
      detail: sourceLabel(iscsiSetup),
      label: "NetApp iSCSI",
      status: asString(iscsiSetup?.status) || "not_checked",
      value: asString(iscsiSetup?.message) || listLabel(address.netapp_iscsi_lifs)
    },
    {
      detail: sourceLabel(esxiIscsiDatastore),
      label: "ESXi iSCSI",
      status: asString(esxiIscsiDatastore?.status) || "not_checked",
      value: asString(esxiIscsiDatastore?.message) || "Datastore path not validated"
    }
  ];
  const actions: Array<{
    detail: string;
    icon: ReactNode;
    id: string;
    label: string;
    run: () => Promise<ProviderProbeResult>;
  }> = [
    { detail: "Discover console path and saved observation state.", icon: <RefreshCw size={14} />, id: "console-discovery", label: "Discover Console", run: api.runNetappConsoleDiscovery },
    { detail: "Read controller console state without configuring ONTAP.", icon: <Play size={14} />, id: "console-read", label: "Read Console", run: api.runNetappConsoleReadState },
    { detail: "Check whether console login state is usable.", icon: <ShieldCheck size={14} />, id: "console-login", label: "Check Login State", run: api.runNetappConsoleLoginState },
    { detail: "Read ONTAP protocol/service readiness.", icon: <Route size={14} />, id: "protocols", label: "Check Protocols", run: api.runNetappLiveState },
    { detail: "Validate cluster setup prerequisites.", icon: <ShieldCheck size={14} />, id: "setup-validate", label: "Validate Setup", run: api.validateNetappSetup },
    { detail: "Validate the NFS setup path before datastore work.", icon: <ShieldCheck size={14} />, id: "nfs-validate", label: "Validate NFS", run: api.validateNetappNfsSetup },
    { detail: "Preview ONTAP setup intent; no writes.", icon: <Route size={14} />, id: "setup-preview", label: "Setup Preview", run: api.netappSetupPreview },
    { detail: "Preview LUN, igroup, LIF, and initiator plan.", icon: <Route size={14} />, id: "iscsi-preview", label: "Preview iSCSI", run: api.netappIscsiSetupPreview },
    { detail: "Preview ESXi adapter/session/datastore state.", icon: <Route size={14} />, id: "esxi-iscsi-preview", label: "Preview ESXi iSCSI", run: api.esxiIscsiDatastorePreview },
    { detail: "Validate NetApp iSCSI without making it a casual apply.", icon: <ShieldCheck size={14} />, id: "iscsi-validate", label: "Validate iSCSI", run: api.validateNetappIscsiSetup },
    { detail: "Validate ESXi datastore visibility after preview.", icon: <ShieldCheck size={14} />, id: "esxi-iscsi-validate", label: "Validate ESXi iSCSI", run: api.validateEsxiIscsiDatastore }
  ];
  const readOnlyPrimary = actions.slice(0, 3);
  const readOnlyMore = actions.slice(3, 6);
  const previewActions = actions.slice(6, 9);
  const validationActions = actions.slice(9, 11);

  async function refreshEvidence() {
    const [nextConsole, nextLive, nextSetup, nextNfs, nextIscsi, nextEsxiIscsi] = await Promise.all([
      safeApi(api.netappConsoleReadiness, null),
      safeApi(api.netappLiveState, null),
      safeApi(api.netappSetupPreview, null),
      safeApi(api.netappNfsVcenterReadiness, null),
      safeApi(api.netappIscsiSetupPreview, null),
      safeApi(api.esxiIscsiDatastorePreview, null)
    ]);
    setConsoleReadiness(nextConsole as ProviderProbeResult | null);
    setLiveState(nextLive as ProviderProbeResult | null);
    setSetupPreview(nextSetup as ProviderProbeResult | null);
    setNfsValidation(nextNfs as ProviderProbeResult | null);
    setIscsiSetup(nextIscsi as ProviderProbeResult | null);
    setEsxiIscsiDatastore(nextEsxiIscsi as ProviderProbeResult | null);
  }

  useEffect(() => {
    let ignore = false;
    Promise.all([
      safeApi(api.netappConsoleReadiness, null),
      safeApi(api.netappLiveState, null),
      safeApi(api.netappSetupPreview, null),
      safeApi(api.netappNfsVcenterReadiness, null),
      safeApi(api.netappIscsiSetupPreview, null),
      safeApi(api.esxiIscsiDatastorePreview, null)
    ]).then(([nextConsole, nextLive, nextSetup, nextNfs, nextIscsi, nextEsxiIscsi]) => {
      if (ignore) return;
      setConsoleReadiness(nextConsole as ProviderProbeResult | null);
      setLiveState(nextLive as ProviderProbeResult | null);
      setSetupPreview(nextSetup as ProviderProbeResult | null);
      setNfsValidation(nextNfs as ProviderProbeResult | null);
      setIscsiSetup(nextIscsi as ProviderProbeResult | null);
      setEsxiIscsiDatastore(nextEsxiIscsi as ProviderProbeResult | null);
    });
    return () => {
      ignore = true;
    };
  }, [activeProfile?.id]);

  async function runWorkspaceStorageAction(action: typeof actions[number]) {
    setRunState({ error: "", message: "", runningActionId: action.id });
    try {
      const result = await action.run();
      await refreshEvidence();
      if (action.id.startsWith("console")) setConsoleReadiness(result);
      if (action.id === "protocols") setLiveState(result);
      if (action.id === "setup-preview" || action.id === "setup-validate") setSetupPreview(result);
      if (action.id === "nfs-validate") setNfsValidation(result);
      if (action.id === "iscsi-preview" || action.id === "iscsi-validate") setIscsiSetup(result);
      if (action.id.startsWith("esxi-iscsi")) setEsxiIscsiDatastore(result);
      await onReload();
      setRunState({
        error: "",
        message: `${action.label}: ${displayStatus(asString(result.status) || "completed")}. ${asString(result.message) || asString(result.next_safe_action)}`,
        runningActionId: ""
      });
    } catch (err) {
      setRunState({ error: errorMessage(err), message: "", runningActionId: "" });
    }
  }

  async function runGuardedIscsiApply() {
    setRunState({ error: "", message: "", runningActionId: "iscsi-apply" });
    try {
      const result = await api.runNetappIscsiSetupApply();
      await refreshEvidence();
      setIscsiSetup(result);
      await onReload();
      setRunState({
        error: "",
        message: `Apply iSCSI gate evaluated: ${displayStatus(asString(result.status) || "completed")}. ${asString(result.message) || asString(result.next_safe_action)}`,
        runningActionId: ""
      });
    } catch (err) {
      setRunState({ error: errorMessage(err), message: "", runningActionId: "" });
    }
  }

  function renderActionButton(action: typeof actions[number]) {
    const running = runState.runningActionId === action.id;
    return (
      <button disabled={running} key={action.id} onClick={() => void runWorkspaceStorageAction(action)} type="button">
        {action.icon}
        <span>{running ? "Running" : action.label}</span>
        <small>{action.detail}</small>
      </button>
    );
  }

  return (
    <section className="netapp-workspace-controls" aria-label="NetApp workspace storage controls">
      <div className="netapp-workspace-controls-head">
        <div>
          <p className="operator-kicker">Storage controls</p>
          <h4>{activeStorageProtocol === "iscsi" ? "iSCSI and ONTAP checks" : "NFS and ONTAP checks"}</h4>
          <span>These are the Storage-page controls moved into the device workspace. Unknown stays gray until a real check runs.</span>
        </div>
        <StatusBadge label={activeStorageProtocol.toUpperCase()} status="plan-only" />
      </div>

      <div className="netapp-workspace-evidence-grid">
        {evidenceRows.map((row) => (
          <div key={row.label}>
            <span>{row.label}</span>
            <strong>{row.value}</strong>
            <small>{row.detail}</small>
            <SimpleStatusPill status={row.status} />
          </div>
        ))}
      </div>

      <div className="netapp-workspace-action-groups">
        <section className="netapp-workspace-action-group">
          <div>
            <p className="operator-kicker">Read-only checks</p>
            <h5>Console and protocol proof</h5>
          </div>
          <div className="netapp-workspace-action-buttons">
            {readOnlyPrimary.map(renderActionButton)}
          </div>
          <details>
            <summary>More read-only checks</summary>
            <div className="netapp-workspace-action-buttons">
              {readOnlyMore.map(renderActionButton)}
            </div>
          </details>
        </section>

        <section className="netapp-workspace-action-group">
          <div>
            <p className="operator-kicker">Setup previews</p>
            <h5>Plan only, no writes</h5>
          </div>
          <div className="netapp-workspace-action-buttons">
            {previewActions.map(renderActionButton)}
          </div>
        </section>

        <section className="netapp-workspace-action-group">
          <div>
            <p className="operator-kicker">Validations</p>
            <h5>Protocol and datastore proof</h5>
          </div>
          <div className="netapp-workspace-action-buttons">
            {validationActions.map(renderActionButton)}
          </div>
        </section>
      </div>

      <section className="netapp-workspace-guarded-apply" aria-label="Guarded iSCSI apply">
        <div>
          <p className="operator-kicker">Guarded write</p>
          <h5>Apply iSCSI stays behind the existing backend gate</h5>
          <span>Runs the same guarded endpoint as Storage. If flags or confirmation are missing, the backend returns blockers and no write should proceed.</span>
        </div>
        <div className="netapp-workspace-gate-grid">
          <div>
            <span>Required flags</span>
            <strong>{iscsiRequiredFlags.length ? `${iscsiRequiredFlags.length} reported` : "Not loaded"}</strong>
            <small>{iscsiRequiredFlags.join(" | ") || "Run Preview iSCSI or guarded Apply to load real gate requirements."}</small>
          </div>
          <div>
            <span>Gate state</span>
            <strong>{gateEvaluated ? `${gateReadyCount}/${gateRows.length} satisfied` : "Unknown"}</strong>
            <small>{gateEvaluated ? gateRows.map(([label, ready]) => `${label}: ${ready ? "ready" : "blocked"}`).join(" | ") : "Not evaluated by backend yet."}</small>
          </div>
          <div>
            <span>Write evidence</span>
            <strong>{asString(iscsiSetup?.action) === "iscsi-setup-apply" ? "Apply response captured" : "No apply response"}</strong>
            <small>{applyEvidence.join(" | ")}</small>
          </div>
        </div>
        <button
          className="netapp-workspace-guarded-button"
          disabled={runState.runningActionId === "iscsi-apply"}
          onClick={() => void runGuardedIscsiApply()}
          type="button"
        >
          <ShieldCheck size={14} />
          <span>{runState.runningActionId === "iscsi-apply" ? "Checking gate" : "Apply iSCSI (guarded)"}</span>
        </button>
      </section>

      {(runState.message || runState.error) && (
        <p className={runState.error ? "operator-action-message error" : "operator-action-message success"}>
          {runState.error || runState.message}
        </p>
      )}
    </section>
  );
}

type ServerWorkspaceControlScope = "ilo" | "server";

type ServerRaidPlanEvidence = ProviderProbeResult | HpeRaidPlanPreview;

type ServerWorkspaceAction = {
  detail: string;
  icon: ReactNode;
  id: string;
  label: string;
  run: () => Promise<WorkflowActionRun | ProviderProbeResult | HpeRaidPlanPreview>;
};

function ServerWorkspaceControls({
  activeProfile,
  address,
  localStorageMode,
  onReload,
  scope,
  workflowActions
}: {
  activeProfile: LabProfile | null;
  address: LabAddressPlan;
  localStorageMode: boolean;
  onReload: () => Promise<void> | void;
  scope: ServerWorkspaceControlScope;
  workflowActions: WorkflowAction[];
}) {
  const [runState, setRunState] = useState<WorkflowRunState>(emptyRunState);
  const [workflowRunsById, setWorkflowRunsById] = useState<Record<string, WorkflowActionRun[]>>({});
  const [esxiReadiness, setEsxiReadiness] = useState<ProviderProbeResult | null>(null);
  const [raidPlan, setRaidPlan] = useState<ServerRaidPlanEvidence | null>(null);
  const [raidPending, setRaidPending] = useState<ProviderProbeResult | null>(null);
  const byId = useMemo(() => new Map(workflowActions.map((action) => [action.action_id, action])), [workflowActions]);
  const workflowActionIds = scope === "ilo"
    ? ["ilo.reachability", "ilo.auth", "ilo.inventory"]
    : ["esxi.management-validation", "raid.validate"];
  const workflowActionKey = workflowActionIds.join("|");

  useEffect(() => {
    let ignore = false;
    Promise.all(
      workflowActionIds.map(async (actionId) => [actionId, await safeApi(() => api.workflowActionRuns(actionId), [] as WorkflowActionRun[])] as const)
    ).then((entries) => {
      if (!ignore) {
        setWorkflowRunsById(Object.fromEntries(entries));
      }
    });
    return () => {
      ignore = true;
    };
  }, [workflowActionKey]);

  useEffect(() => {
    if (scope !== "server") return;
    let ignore = false;
    Promise.all([
      safeApi(api.esxiInstallReadiness, null),
      safeApi(api.hpeRaidPlanPreview, null),
      safeApi(api.hpeRaidPending, null)
    ]).then(([nextEsxi, nextRaidPlan, nextRaidPending]) => {
      if (ignore) return;
      setEsxiReadiness(nextEsxi as ProviderProbeResult | null);
      setRaidPlan(nextRaidPlan as ServerRaidPlanEvidence | null);
      setRaidPending(nextRaidPending as ProviderProbeResult | null);
    });
    return () => {
      ignore = true;
    };
  }, [activeProfile?.id, scope]);

  async function runWorkflowCheck(actionId: string): Promise<WorkflowActionRun> {
    const result = await api.runWorkflowAction(actionId);
    setWorkflowRunsById((current) => ({
      ...current,
      [actionId]: [result, ...(current[actionId] ?? [])].slice(0, 5)
    }));
    return result;
  }

  async function runRaidPlan(): Promise<HpeRaidPlanPreview> {
    const result = await api.hpeRaidPlanPreview();
    setRaidPlan(result);
    return result;
  }

  async function runRaidPending(): Promise<ProviderProbeResult> {
    const result = await api.hpeRaidPending();
    setRaidPending(result);
    return result;
  }

  async function runEsxiReadiness(): Promise<ProviderProbeResult> {
    const result = await api.esxiInstallReadiness();
    setEsxiReadiness(result);
    return result;
  }

  const iloActions: ServerWorkspaceAction[] = [
    {
      detail: "Read iLO reachability through the existing read-only workflow.",
      icon: <RefreshCw size={14} />,
      id: "ilo.reachability",
      label: byId.get("ilo.reachability")?.label || "iLO Live Check",
      run: () => runWorkflowCheck("ilo.reachability")
    },
    {
      detail: "Check credential usability without showing the secret.",
      icon: <ShieldCheck size={14} />,
      id: "ilo.auth",
      label: byId.get("ilo.auth")?.label || "iLO Auth Live Check",
      run: () => runWorkflowCheck("ilo.auth")
    },
    {
      detail: "Read server inventory through iLO/Redfish.",
      icon: <Server size={14} />,
      id: "ilo.inventory",
      label: byId.get("ilo.inventory")?.label || "iLO Inventory Read",
      run: () => runWorkflowCheck("ilo.inventory")
    }
  ];

  const serverActions: ServerWorkspaceAction[] = [
    {
      detail: "Validate ESXi management readiness without changing the host.",
      icon: <Gauge size={14} />,
      id: "esxi.management-validation",
      label: byId.get("esxi.management-validation")?.label || "ESXi Live Check",
      run: async () => {
        const result = await runWorkflowCheck("esxi.management-validation");
        await safeApi(runEsxiReadiness, null);
        return result;
      }
    },
    {
      detail: "Validate the Smart Array/RAID state through the read-only workflow.",
      icon: <ShieldCheck size={14} />,
      id: "raid.validate",
      label: byId.get("raid.validate")?.label || "Validate RAID",
      run: () => runWorkflowCheck("raid.validate")
    },
    {
      detail: "Preview desired RAID layout only. This does not create, delete, apply, or reset anything.",
      icon: <HardDrive size={14} />,
      id: "raid.plan",
      label: "Preview RAID",
      run: runRaidPlan
    },
    {
      detail: "Check pending RAID/reset state without committing the plan.",
      icon: <RefreshCw size={14} />,
      id: "raid.pending-check",
      label: "Check RAID Pending",
      run: runRaidPending
    }
  ];

  const latestWorkflowRun = workflowActionIds
    .flatMap((id) => workflowRunsById[id] ?? [])
    .sort((a, b) => asString(b.finished_at || b.started_at).localeCompare(asString(a.finished_at || a.started_at)))[0] ?? null;
  const latestRunFor = (actionId: string) => workflowRunsById[actionId]?.[0] ?? null;
  const evidenceRows = scope === "ilo"
    ? [
        {
          detail: "Saved setup",
          label: "iLO IP",
          status: address.ilo ? "planned" : "not_checked",
          value: displayAddress(address.ilo)
        },
        {
          detail: latestRunFor("ilo.reachability") ? "Workflow action run" : "Workflow history",
          label: "Reachability",
          status: latestRunFor("ilo.reachability")?.status || "not_checked",
          value: latestRunFor("ilo.reachability") ? displayStatus(latestRunFor("ilo.reachability")?.status || "completed") : "No workspace run yet"
        },
        {
          detail: latestRunFor("ilo.auth") ? "Workflow action run" : "Workflow history",
          label: "Auth",
          status: latestRunFor("ilo.auth")?.status || "not_checked",
          value: latestRunFor("ilo.auth") ? displayStatus(latestRunFor("ilo.auth")?.status || "completed") : "No credential check run yet"
        },
        {
          detail: latestRunFor("ilo.inventory") ? "Workflow action run" : "Workflow history",
          label: "Inventory",
          status: latestRunFor("ilo.inventory")?.status || "not_checked",
          value: latestRunFor("ilo.inventory") ? displayStatus(latestRunFor("ilo.inventory")?.status || "completed") : "No inventory read yet"
        }
      ]
    : [
        {
          detail: "Saved setup",
          label: "ESXi IP",
          status: address.esxi_management ? "planned" : "not_checked",
          value: displayAddress(address.esxi_management)
        },
        {
          detail: sourceLabel(esxiReadiness),
          label: "ESXi readiness",
          status: asString(esxiReadiness?.status) || "not_checked",
          value: asString(esxiReadiness?.message) || asString(esxiReadiness?.next_safe_action) || "No ESXi readiness check run yet"
        },
        {
          detail: sourceLabel(raidPlan),
          label: "RAID plan",
          status: asString(raidPlan?.status) || "not_checked",
          value: asString(objectValue(raidPlan).message) || asString(raidPlan?.next_safe_action) || raidLayoutLabel(raidPlan)
        },
        {
          detail: sourceLabel(raidPending),
          label: "RAID pending",
          status: asString(raidPending?.status) || "not_checked",
          value: asString(raidPending?.message) || "Pending state not checked"
        },
        {
          detail: latestWorkflowRun ? "Workflow action run" : "Workflow history",
          label: "Last workflow",
          status: latestWorkflowRun?.status || "not_checked",
          value: latestWorkflowRun ? `${latestWorkflowRun.action_id}: ${displayStatus(latestWorkflowRun.status)}` : "No server workflow run yet"
        }
      ];
  const primaryActions = scope === "ilo" ? iloActions : serverActions.slice(0, 2);
  const planActions = scope === "server" ? serverActions.slice(2) : [];

  async function runServerWorkspaceAction(action: ServerWorkspaceAction) {
    setRunState({ error: "", message: "", runningActionId: action.id });
    try {
      const result = await action.run();
      await onReload();
      const status = asString(result.status) || "completed";
      const message = "summary" in result
        ? asString(result.summary) || asString(result.next_action)
        : asString(objectValue(result).message) || asString(result.next_safe_action);
      setRunState({
        error: "",
        message: `${action.label}: ${displayStatus(status)}. ${message}`,
        runningActionId: ""
      });
    } catch (err) {
      setRunState({ error: errorMessage(err), message: "", runningActionId: "" });
    }
  }

  function renderActionButton(action: ServerWorkspaceAction) {
    const running = runState.runningActionId === action.id;
    return (
      <button disabled={running} key={action.id} onClick={() => void runServerWorkspaceAction(action)} type="button">
        {action.icon}
        <span>{running ? "Running" : action.label}</span>
        <small>{action.detail}</small>
      </button>
    );
  }

  return (
    <section className="netapp-workspace-controls server-workspace-controls" aria-label={scope === "ilo" ? "iLO workspace server controls" : "Server workspace checks"}>
      <div className="netapp-workspace-controls-head server-workspace-controls-head">
        <div>
          <p className="operator-kicker">{scope === "ilo" ? "iLO controls" : "Server controls"}</p>
          <h4>{scope === "ilo" ? "iLO read-only checks" : "ESXi and RAID checks"}</h4>
          <span>{scope === "ilo" ? "Server access checks moved into the iLO workspace. Unknown stays gray until a real workflow run." : "Read-only ESXi and RAID checks moved into the server workspace. RAID apply/reset/factory actions stay on Validation."}</span>
        </div>
        <StatusBadge label={scope === "ilo" ? "Read-only" : localStorageMode ? "Local RAID" : "Boot/staging"} status="safe-to-run" />
      </div>

      <div className="netapp-workspace-evidence-grid server-workspace-evidence-grid">
        {evidenceRows.map((row) => (
          <div key={row.label}>
            <span>{row.label}</span>
            <strong>{row.value}</strong>
            <small>{row.detail}</small>
            <SimpleStatusPill status={row.status} />
          </div>
        ))}
      </div>

      <div className="netapp-workspace-action-groups server-workspace-action-groups">
        <section className="netapp-workspace-action-group server-workspace-action-group">
          <div>
            <p className="operator-kicker">Read-only checks</p>
            <h5>{scope === "ilo" ? "Access and inventory proof" : "Host and controller proof"}</h5>
          </div>
          <div className="netapp-workspace-action-buttons server-workspace-action-buttons">
            {primaryActions.map(renderActionButton)}
          </div>
        </section>

        {planActions.length > 0 && (
          <section className="netapp-workspace-action-group server-workspace-action-group">
            <div>
              <p className="operator-kicker">Plan only</p>
              <h5>Local RAID checks, no apply</h5>
            </div>
            <div className="netapp-workspace-action-buttons server-workspace-action-buttons">
              {planActions.map(renderActionButton)}
            </div>
          </section>
        )}
      </div>

      {scope === "server" && (
        <div className="netapp-workspace-guarded-apply server-workspace-guarded-note" aria-label="RAID guarded write boundary">
          <div>
            <p className="operator-kicker">Guarded write boundary</p>
            <h5>RAID apply, reset, create, delete, factory, and rebuild stay off this map</h5>
            <span>Use Validation for the existing guarded workflows. This workspace only proves readiness and previews the plan.</span>
          </div>
        </div>
      )}

      {(runState.message || runState.error) && (
        <p className={runState.error ? "operator-action-message error" : "operator-action-message success"}>
          {runState.error || runState.message}
        </p>
      )}
    </section>
  );
}

type VirtualizationWorkspaceAction = {
  detail: string;
  icon: ReactNode;
  id: string;
  label: string;
  run: () => Promise<WorkflowActionRun>;
};

function VirtualizationWorkspaceControls({
  activeProfile,
  address,
  features,
  onReload,
  workflowActions
}: {
  activeProfile: LabProfile | null;
  address: LabAddressPlan;
  features: LabProfileFeatures | null;
  onReload: () => Promise<void> | void;
  workflowActions: WorkflowAction[];
}) {
  const [runState, setRunState] = useState<WorkflowRunState>(emptyRunState);
  const [workflowRunsById, setWorkflowRunsById] = useState<Record<string, WorkflowActionRun[]>>({});
  const [vcenterNetapp, setVcenterNetapp] = useState<ProviderProbeResult | null>(null);
  const [installReadiness, setInstallReadiness] = useState<ProviderProbeResult | null>(null);
  const [postAttach, setPostAttach] = useState<ProviderProbeResult | null>(null);
  const byId = useMemo(() => new Map(workflowActions.map((action) => [action.action_id, action])), [workflowActions]);
  const vcenterInScope = features?.vcenter_enabled !== false;
  const actionIds = vcenterInScope
    ? ["vcenter-netapp.readiness", "vcenter.install-readiness", "vcenter.post-attach-validation", "esxi.vm-deploy-validate"]
    : ["esxi.vm-deploy-validate"];
  const actionKey = actionIds.join("|");

  useEffect(() => {
    let ignore = false;
    Promise.all(
      actionIds.map(async (actionId) => [actionId, await safeApi(() => api.workflowActionRuns(actionId), [] as WorkflowActionRun[])] as const)
    ).then((entries) => {
      if (!ignore) {
        setWorkflowRunsById(Object.fromEntries(entries));
      }
    });
    return () => {
      ignore = true;
    };
  }, [actionKey]);

  useEffect(() => {
    let ignore = false;
    if (!vcenterInScope) {
      setVcenterNetapp(null);
      setInstallReadiness(null);
      setPostAttach(null);
      return () => {
        ignore = true;
      };
    }
    Promise.all([
      safeApi(api.vcenterNetappReadiness, null),
      safeApi(api.vcenterInstallReadiness, null),
      safeApi(api.vcenterPostAttachValidation, null)
    ]).then(([nextVcenterNetapp, nextInstallReadiness, nextPostAttach]) => {
      if (ignore) return;
      setVcenterNetapp(nextVcenterNetapp as ProviderProbeResult | null);
      setInstallReadiness(nextInstallReadiness as ProviderProbeResult | null);
      setPostAttach(nextPostAttach as ProviderProbeResult | null);
    });
    return () => {
      ignore = true;
    };
  }, [activeProfile?.id, vcenterInScope]);

  async function refreshVcenterEvidence() {
    if (!vcenterInScope) return;
    const [nextVcenterNetapp, nextInstallReadiness, nextPostAttach] = await Promise.all([
      safeApi(api.vcenterNetappReadiness, null),
      safeApi(api.vcenterInstallReadiness, null),
      safeApi(api.vcenterPostAttachValidation, null)
    ]);
    setVcenterNetapp(nextVcenterNetapp as ProviderProbeResult | null);
    setInstallReadiness(nextInstallReadiness as ProviderProbeResult | null);
    setPostAttach(nextPostAttach as ProviderProbeResult | null);
  }

  async function runWorkflowCheck(actionId: string): Promise<WorkflowActionRun> {
    const result = await api.runWorkflowAction(actionId);
    setWorkflowRunsById((current) => ({
      ...current,
      [actionId]: [result, ...(current[actionId] ?? [])].slice(0, 5)
    }));
    if (actionId.startsWith("vcenter")) {
      await refreshVcenterEvidence();
    }
    return result;
  }

  const latestRunFor = (actionId: string) => workflowRunsById[actionId]?.[0] ?? null;
  const postChecks = objectValue(postAttach?.checks);
  const target = vcenterAddress(vcenterNetapp || installReadiness, activeProfile);
  const evidenceRows = [
    {
      detail: vcenterInScope ? "Saved profile / readiness target" : asString(features?.vcenter_disabled_reason) || "vCenter disabled by this setup",
      label: "vCenter target",
      status: vcenterInScope ? target !== "Not set up yet" ? "planned" : "not_checked" : "not_in_scope",
      value: vcenterInScope ? target : "Not in this mode"
    },
    {
      detail: sourceLabel(vcenterNetapp),
      label: "vCenter readiness",
      status: asString(vcenterNetapp?.status) || latestRunFor("vcenter-netapp.readiness")?.status || "not_checked",
      value: asString(vcenterNetapp?.message) || latestRunFor("vcenter-netapp.readiness")?.summary || "No vCenter live check run yet"
    },
    {
      detail: sourceLabel(installReadiness),
      label: "Install readiness",
      status: asString(installReadiness?.status) || latestRunFor("vcenter.install-readiness")?.status || "not_checked",
      value: asString(installReadiness?.message) || latestRunFor("vcenter.install-readiness")?.summary || "No install readiness check run yet"
    },
    {
      detail: sourceLabel(postAttach),
      label: "Datastore validation",
      status: datastoreVisibleStatus(vcenterNetapp || postAttach),
      value: asString(postAttach?.message) || datastoreName(vcenterNetapp || postAttach)
    },
    {
      detail: latestRunFor("esxi.vm-deploy-validate") ? "Workflow action run" : "Workflow history",
      label: "VM inventory",
      status: latestRunFor("esxi.vm-deploy-validate")?.status || visibilityStatus(postChecks.vm_inventory_visible),
      value: latestRunFor("esxi.vm-deploy-validate")
        ? displayStatus(latestRunFor("esxi.vm-deploy-validate")?.status || "completed")
        : visibilityLabel(postChecks.vm_inventory_visible)
    },
    {
      detail: "Saved setup",
      label: "ESXi target",
      status: address.esxi_management ? "planned" : "not_checked",
      value: displayAddress(address.esxi_management)
    }
  ];

  const actions: VirtualizationWorkspaceAction[] = [
    {
      detail: "Read vCenter, ESXi attach, and datastore visibility evidence.",
      icon: <RefreshCw size={14} />,
      id: "vcenter-netapp.readiness",
      label: byId.get("vcenter-netapp.readiness")?.label || "vCenter Live Check",
      run: () => runWorkflowCheck("vcenter-netapp.readiness")
    },
    {
      detail: "Validate install values and credentials without deploying VCSA.",
      icon: <ShieldCheck size={14} />,
      id: "vcenter.install-readiness",
      label: byId.get("vcenter.install-readiness")?.label || "vCenter Install Readiness",
      run: () => runWorkflowCheck("vcenter.install-readiness")
    },
    {
      detail: "Validate datastore and post-attach state after storage or vCenter changes.",
      icon: <Database size={14} />,
      id: "vcenter.post-attach-validation",
      label: byId.get("vcenter.post-attach-validation")?.label || "Validate Datastore",
      run: () => runWorkflowCheck("vcenter.post-attach-validation")
    },
    {
      detail: "Validate VM inventory/deployment prerequisites without creating a VM.",
      icon: <Layers size={14} />,
      id: "esxi.vm-deploy-validate",
      label: byId.get("esxi.vm-deploy-validate")?.label || "Validate VM Inventory",
      run: () => runWorkflowCheck("esxi.vm-deploy-validate")
    }
  ];
  const vcenterActions = vcenterInScope ? actions.slice(0, 3) : [];
  const vmActions = actions.slice(3);

  async function runVirtualizationWorkspaceAction(action: VirtualizationWorkspaceAction) {
    setRunState({ error: "", message: "", runningActionId: action.id });
    try {
      const result = await action.run();
      await onReload();
      setRunState({
        error: "",
        message: `${action.label}: ${displayStatus(result.status)}. ${result.summary || result.next_action}`,
        runningActionId: ""
      });
    } catch (err) {
      setRunState({ error: errorMessage(err), message: "", runningActionId: "" });
    }
  }

  function renderActionButton(action: VirtualizationWorkspaceAction) {
    const running = runState.runningActionId === action.id;
    return (
      <button disabled={running} key={action.id} onClick={() => void runVirtualizationWorkspaceAction(action)} type="button">
        {action.icon}
        <span>{running ? "Running" : action.label}</span>
        <small>{action.detail}</small>
      </button>
    );
  }

  return (
    <section className="netapp-workspace-controls virtualization-workspace-controls" aria-label="vCenter workspace virtualization controls">
      <div className="netapp-workspace-controls-head virtualization-workspace-controls-head">
        <div>
          <p className="operator-kicker">Virtualization controls</p>
          <h4>{vcenterInScope ? "vCenter and VM checks" : "Direct ESXi VM checks"}</h4>
          <span>{vcenterInScope ? "Virtualization-page checks moved into the vCenter workspace. Unknown stays gray until a real run." : "This setup has no vCenter node; VM validation remains reachable from this workspace strip."}</span>
        </div>
        <StatusBadge label={vcenterInScope ? "vCenter" : "Direct ESXi"} status={vcenterInScope ? "safe-to-run" : "plan-only"} />
      </div>

      <div className="netapp-workspace-evidence-grid virtualization-workspace-evidence-grid">
        {evidenceRows.map((row) => (
          <div key={row.label}>
            <span>{row.label}</span>
            <strong>{row.value}</strong>
            <small>{row.detail}</small>
            <SimpleStatusPill status={row.status} />
          </div>
        ))}
      </div>

      <div className="netapp-workspace-action-groups virtualization-workspace-action-groups">
        {vcenterActions.length > 0 && (
          <section className="netapp-workspace-action-group virtualization-workspace-action-group">
            <div>
              <p className="operator-kicker">Read-only checks</p>
              <h5>vCenter and datastore proof</h5>
            </div>
            <div className="netapp-workspace-action-buttons virtualization-workspace-action-buttons">
              {vcenterActions.map(renderActionButton)}
            </div>
          </section>
        )}

        <section className="netapp-workspace-action-group virtualization-workspace-action-group">
          <div>
            <p className="operator-kicker">VM validation</p>
            <h5>Inventory and deployment prerequisites</h5>
          </div>
          <div className="netapp-workspace-action-buttons virtualization-workspace-action-buttons">
            {vmActions.map(renderActionButton)}
          </div>
        </section>
      </div>

      <div className="netapp-workspace-guarded-apply virtualization-workspace-guarded-note" aria-label="vCenter guarded write boundary">
        <div>
          <p className="operator-kicker">Guarded write boundary</p>
          <h5>vCenter attach, OVF deploy, datastore writes, and VM deploy apply stay off this map</h5>
          <span>Use the existing guarded workflow surfaces for apply/deploy work. This workspace only proves readiness and validation state.</span>
        </div>
      </div>

      {(runState.message || runState.error) && (
        <p className={runState.error ? "operator-action-message error" : "operator-action-message success"}>
          {runState.error || runState.message}
        </p>
      )}
    </section>
  );
}

export function OperatorVirtualizationPage({ labProfileState, onReloadLabProfile }: OperatorPageProps) {
  const activeProfile = activeLabProfile(labProfileState);
  const address = activeAddressPlan(activeProfile);
  const global = activeProfile?.global_settings ?? null;
  const features = activeProfile?.features ?? null;
  const vcenterEnabled = features?.vcenter_enabled !== false;
  const scenarioLabel = deploymentScenarioLabel(features);
  const storageLabel = storageLocationLabel(features);
  const [actions, setActions] = useState<WorkflowAction[]>([]);
  const [vcenterNetapp, setVcenterNetapp] = useState<ProviderProbeResult | null>(null);
  const [installReadiness, setInstallReadiness] = useState<ProviderProbeResult | null>(null);
  const [postAttach, setPostAttach] = useState<ProviderProbeResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [runState, setRunState] = useState<WorkflowRunState>(emptyRunState);

  async function load() {
    setError("");
    setLoading(true);
    try {
      const [nextActions, nextVcenterNetapp, nextInstall, nextPostAttach] = vcenterEnabled
        ? await Promise.all([
            safeApi(api.workflowActions, [] as WorkflowAction[]),
            safeApi(api.vcenterNetappReadiness, null),
            safeApi(api.vcenterInstallReadiness, null),
            safeApi(api.vcenterPostAttachValidation, null)
          ])
        : await Promise.all([
            safeApi(api.workflowActions, [] as WorkflowAction[]),
            Promise.resolve(null),
            Promise.resolve(null),
            Promise.resolve(null)
          ]);
      setActions(Array.isArray(nextActions) ? nextActions : []);
      setVcenterNetapp(nextVcenterNetapp);
      setInstallReadiness(nextInstall);
      setPostAttach(nextPostAttach);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [vcenterEnabled]);

  const virtualStatus = vcenterEnabled
    ? strongestStatus([
        asString(postAttach?.status) || "not_checked",
        asString(vcenterNetapp?.status) || "not_checked",
        asString(installReadiness?.status) || "not_checked"
      ])
    : "not_checked";
  const target = vcenterTarget(vcenterNetapp || installReadiness, activeProfile);
  const postChecks = objectValue(postAttach?.checks);
  const currentView = virtualizationCurrentView({ activeProfile, features, installReadiness, postAttach, vcenterNetapp });
  const virtualizationActionIds = vcenterEnabled ? vcenterVmCheckActionIds : directVmCheckActionIds;
  const virtualizationRows = useMemo<OperatorObjectRow[]>(
    () => {
      const baseRows: OperatorObjectRow[] = [
        {
          checkedAt: currentView.checkedAt,
          details: [
            { label: "ESXi target", value: displayAddress(address.esxi_management), source: "Saved setup" },
            { label: "Scenario", value: scenarioLabel, source: "Active profile" },
            { label: "Storage", value: storageLabel, source: "Active profile" }
          ],
          freshness: currentView.freshness,
          id: "esxi-direct",
          nextAction: vcenterEnabled ? "Validate attach state after ESXi or vCenter changes." : "Run ESXi Live Check before VM deployment validation.",
          source: currentView.source,
          status: virtualStatus,
          summary: vcenterEnabled ? "ESXi attachment and host visibility through vCenter." : "Direct ESXi host path for this setup.",
          target: displayAddress(address.esxi_management),
          title: vcenterEnabled ? "ESXi Attach" : "ESXi Direct",
          type: "Control plane"
        },
        {
          checkedAt: currentView.checkedAt,
          details: [
            {
              label: "Datastore",
              value: vcenterEnabled ? datastoreName(vcenterNetapp) : storageLabel,
              status: vcenterEnabled ? datastoreVisibleStatus(vcenterNetapp || postAttach) : "not_checked"
            },
            {
              label: "Visibility",
              value: vcenterEnabled ? visibilityLabel(postChecks.netapp_datastore_visible ?? objectValue(vcenterNetapp?.checks).datastore_mounted) : "Validate through ESXi."
            }
          ],
          freshness: currentView.freshness,
          id: "datastore",
          nextAction: vcenterEnabled ? "Validate datastore visibility after storage changes." : "Validate datastore visibility from ESXi before VM deployment.",
          source: currentView.source,
          status: vcenterEnabled ? datastoreVisibleStatus(vcenterNetapp || postAttach) : "not_checked",
          summary: vcenterEnabled ? "NetApp datastore visibility through vCenter." : "Datastore validation is scoped to the direct ESXi path.",
          target: vcenterEnabled ? datastoreName(vcenterNetapp) : storageLabel,
          title: "Datastore",
          type: "Storage"
        },
        {
          checkedAt: currentView.checkedAt,
          details: [
            {
              label: "VM inventory",
              value: vcenterEnabled ? visibilityLabel(postChecks.vm_inventory_visible) : "Validate after ESXi storage is ready.",
              status: vcenterEnabled ? visibilityStatus(postChecks.vm_inventory_visible) : "not_checked"
            }
          ],
          freshness: currentView.freshness,
          id: "vm-inventory",
          nextAction: vcenterEnabled ? "Validate inventory after datastore and vCenter access are ready." : "Validate VM deployment directly against ESXi.",
          source: currentView.source,
          status: vcenterEnabled ? visibilityStatus(postChecks.vm_inventory_visible) : "not_checked",
          summary: vcenterEnabled ? "VM inventory visibility for deployment validation." : "VM validation follows the direct ESXi workflow for this setup.",
          target: vcenterEnabled ? "vCenter inventory" : "ESXi inventory",
          title: "VM Inventory",
          type: "Inventory"
        },
        {
          checkedAt: currentView.checkedAt,
          details: [{ label: "OVF deployment", value: "Ready after validation", status: "not_checked" }],
          freshness: "Operator config",
          id: "ovf",
          nextAction: "Run validation before any guarded VM deployment.",
          source: "Saved setup",
          status: "not_checked",
          summary: "Deployment action remains gated behind validation.",
          target: "OVF deployment",
          title: "OVF Deployment",
          type: "Guarded action"
        }
      ];

      if (!vcenterEnabled) {
        return [
          {
            checkedAt: currentView.checkedAt,
            details: [
              { label: "Scenario", value: scenarioLabel, source: "Active profile" },
              { label: "Reason", value: asString(features?.vcenter_disabled_reason) || "vCenter is disabled for this setup.", source: "Active profile" }
            ],
            freshness: "Operator config",
            id: "vcenter-out-of-scope",
            nextAction: "No vCenter action is required unless the setup changes.",
            source: "Active profile",
            status: "not_in_scope",
            summary: "vCenter not in this setup.",
            target: "Direct ESXi workflow",
            title: "vCenter",
            type: "Out of scope"
          },
          ...baseRows
        ];
      }

      return [
        {
          checkedAt: currentView.checkedAt,
          details: [
            { label: "Target", value: target },
            { label: "Credentials", value: credentialSummary(vcenterNetapp) },
            { label: "Source", value: sourceLabel(vcenterNetapp || installReadiness) }
          ],
          freshness: currentView.freshness,
          id: "vcenter",
          nextAction: humanize(asString(vcenterNetapp?.next_safe_action) || "Run vCenter Live Check."),
          source: sourceLabel(vcenterNetapp || installReadiness),
          status: virtualStatus,
          summary: asString(vcenterNetapp?.message) || asString(installReadiness?.message) || "vCenter endpoint and readiness.",
          target,
          title: "vCenter",
          type: "Control plane"
        },
        ...baseRows
      ];
    },
    [address.esxi_management, currentView, features?.vcenter_disabled_reason, installReadiness, postAttach, postChecks, scenarioLabel, storageLabel, target, vcenterEnabled, vcenterNetapp, virtualStatus]
  );
  const byActionId = useMemo(() => new Map(actions.map((action) => [action.action_id, action])), [actions]);
  const vmRunConfig: TabRunConfig = {
    actionIds: virtualizationActionIds,
    actions,
    kind: "read",
    label: "Run VM check",
    onReload: load
  };
  const vmAction = firstRunnableAction(byActionId, virtualizationActionIds, vmRunConfig);
  const vmFallbackActionId = fallbackRunActionId(vmRunConfig, vmAction);
  const vmDisabledReason = vmAction
    ? disabledReasonForRunConfig(vmRunConfig, vmAction)
    : vmFallbackActionId
      ? ""
      : disabledReasonForRunConfig(vmRunConfig, vmAction);
  const vmManagement = virtualizationVmManagementCardModel({
    activeProfile,
    address,
    currentView,
    installReadiness,
    postAttach,
    storageLabel,
    target,
    vcenterEnabled,
    vcenterNetapp,
    virtualStatus
  });
  const virtualizationDetailRows = [
    { current: vmManagement.target, item: vcenterEnabled ? "vCenter target" : "ESXi target", status: virtualStatus },
    { current: vmManagement.datastore, item: "Datastore", status: vcenterEnabled ? datastoreVisibleStatus(vcenterNetapp || postAttach) : "not_checked" },
    { current: vcenterEnabled ? visibilityLabel(postChecks.vm_inventory_visible) : "Direct ESXi inventory", item: "VM inventory", status: vcenterEnabled ? visibilityStatus(postChecks.vm_inventory_visible) : "not_checked" },
    { current: "Guarded until validation passes", item: "VM deployment", status: "not_checked" }
  ];

  async function runVmCheck() {
    const actionId = vmAction?.action_id ?? vmFallbackActionId;
    if (!actionId || vmDisabledReason || runState.runningActionId) return;
    setRunState({ error: "", message: "", runningActionId: actionId });
    try {
      const result = await api.runWorkflowAction(actionId);
      setRunState({
        error: "",
        message: vmAction ? workflowRunMessage(vmAction, result) : workflowRunResultMessage("Run VM check", result),
        runningActionId: ""
      });
      await load();
    } catch (err) {
      setRunState({ error: errorMessage(err), message: "", runningActionId: "" });
    }
  }

  return (
    <OperatorPage title="Virtualization">
      <div className="operator-surface-heading">
        <p className="operator-kicker">Setup</p>
        <h1>Virtualization</h1>
        <p>Can this kit manage VMs through the right target, datastore, and access path?</p>
      </div>
      <Feedback loading={loading && Boolean(activeProfile) && vcenterEnabled && !vcenterNetapp} error={error} />
      <section className="network-access-surface virtualization-access-surface" aria-label="VM Management">
        <Card className="network-access-card virtualization-access-card" hover={false}>
          <CardHeader>
            <div>
              <p className="operator-kicker">VM management</p>
              <h2>{vmManagement.mode}</h2>
            </div>
            <StatusBadge label={vmManagement.stateLabel} status={vmManagement.badgeStatus} />
          </CardHeader>
          <CardContent>
            <dl className="network-access-fields virtualization-access-fields">
              <div>
                <dt>Mode</dt>
                <dd>{vmManagement.mode}</dd>
              </div>
              <div>
                <dt>Target</dt>
                <dd>{vmManagement.target}</dd>
              </div>
              <div>
                <dt>Datastore</dt>
                <dd>{vmManagement.datastore}</dd>
              </div>
              <div>
                <dt>Access</dt>
                <dd>{vmManagement.access}</dd>
              </div>
            </dl>
            {vmManagement.reason && (
              <div className="network-access-reason" role="note">
                <strong>Needs attention</strong>
                <span>{vmManagement.reason}</span>
              </div>
            )}
            {runState.message && <div className="operator-feedback network-access-feedback">{runState.message}</div>}
            {runState.error && <div className="operator-feedback error network-access-feedback">{runState.error}</div>}
          </CardContent>
          <CardFooter>
            <div className="network-access-actions virtualization-access-actions">
              <button
                className="operator-primary-button"
                disabled={Boolean(vmDisabledReason) || Boolean(runState.runningActionId)}
                onClick={() => void runVmCheck()}
                title={vmDisabledReason || "Run VM check"}
                type="button"
              >
                <RefreshCw size={16} />
                {runState.runningActionId ? "Checking" : "Run VM check"}
              </button>
              <button
                aria-expanded={detailsOpen}
                className="secondary-button"
                onClick={() => setDetailsOpen((current) => !current)}
                type="button"
              >
                View details
              </button>
            </div>
          </CardFooter>
        </Card>
      </section>
      {detailsOpen && (
        <section className="network-details virtualization-details" aria-label="VM details">
          <div className="network-details-grid virtualization-details-grid">
            <Card className="network-details-card" hover={false}>
              <CardHeader>
                <div>
                  <p className="operator-kicker">Details</p>
                  <h2>VM path and saved target</h2>
                </div>
                <StatusBadge label={vmManagement.stateLabel} status={vmManagement.badgeStatus} />
              </CardHeader>
              <CardContent>
                <ConfigValueList
                  values={[
                    { label: "Mode", value: vmManagement.mode, source: "Saved setup" },
                    { label: "Target", value: vmManagement.target, source: "Saved setup", status: virtualStatus },
                    { label: "Datastore", value: vmManagement.datastore, source: "Saved setup" },
                    { label: "Access", value: vmManagement.access },
                    { label: "Next check", value: vmManagement.nextAction }
                  ]}
                />
              </CardContent>
            </Card>
            <Card className="network-details-card" hover={false}>
              <CardHeader>
                <div>
                  <p className="operator-kicker">Saved signals</p>
                  <h2>Virtualization checks</h2>
                </div>
                <span>{virtualizationDetailRows.length} tracked</span>
              </CardHeader>
              <CompactTable>
                <CompactTableHeader>
                  <CompactTableCell>Item</CompactTableCell>
                  <CompactTableCell>Current</CompactTableCell>
                  <CompactTableCell>Status</CompactTableCell>
                </CompactTableHeader>
                <tbody>
                  {virtualizationDetailRows.map((row) => (
                    <CompactTableRow key={row.item}>
                      <CompactTableCell><strong>{row.item}</strong></CompactTableCell>
                      <CompactTableCell>{row.current}</CompactTableCell>
                      <CompactTableCell><StatusBadge label={displayStatus(row.status)} status={statusBadgeStatus(row.status)} /></CompactTableCell>
                    </CompactTableRow>
                  ))}
                </tbody>
              </CompactTable>
            </Card>
            <section className="overview-safe-actions" aria-label="Virtualization configure">
              <VirtualizationConfigurePanel
                activeProfile={activeProfile}
                address={address}
                features={features}
                global={global}
                onSaved={async () => {
                  await onReloadLabProfile?.();
                  await load();
                }}
              />
            </section>
            <VirtualizationSetupShapePanel
              activeProfile={activeProfile}
              currentView={currentView}
              features={features}
              installReadiness={installReadiness}
              postAttach={postAttach}
              storageLabel={storageLabel}
              target={target}
              vcenterEnabled={vcenterEnabled}
              vcenterNetapp={vcenterNetapp}
              virtualStatus={virtualStatus}
            />
            <AdvancedDrawer title="Virtualization proof" summary={noProofText}>
              <OperatorWorkspace currentView={currentView} rows={virtualizationRows} compact />
              <ConfigValueList
                values={[
                  { label: "vCenter source", value: sourceLabel(vcenterNetapp) },
                  { label: "Install blockers", value: String(stringArray(installReadiness?.blockers).length) },
                  { label: "Post-attach warnings", value: String(stringArray(postAttach?.warnings).length) }
                ]}
              />
            </AdvancedDrawer>
          </div>
        </section>
      )}
    </OperatorPage>
  );
}

function virtualizationVmManagementCardModel({
  activeProfile,
  address,
  currentView,
  installReadiness,
  postAttach,
  storageLabel,
  target,
  vcenterEnabled,
  vcenterNetapp,
  virtualStatus
}: {
  activeProfile: LabProfile | null;
  address: LabAddressPlan;
  currentView: CurrentViewModel;
  installReadiness: ProviderProbeResult | null;
  postAttach: ProviderProbeResult | null;
  storageLabel: string;
  target: string;
  vcenterEnabled: boolean;
  vcenterNetapp: ProviderProbeResult | null;
  virtualStatus: string;
}) {
  const stateLabel = virtualizationVmStateLabel(virtualStatus, vcenterEnabled ? target : address.esxi_management);
  const mode = vcenterEnabled ? "vCenter managed" : "Direct ESXi";
  const access = vcenterEnabled
    ? credentialSummary(vcenterNetapp || installReadiness)
    : asString(activeProfile?.devices?.esxi) || address.esxi_management
      ? "Saved target"
      : "Missing or not checked";
  const reason = stateLabel === "Blocked"
    ? virtualizationVmReason({ address, currentView, installReadiness, postAttach, vcenterEnabled, vcenterNetapp })
    : "";
  const nextAction = vcenterEnabled
    ? humanize(asString(vcenterNetapp?.next_safe_action) || asString(installReadiness?.next_safe_action) || "Run VM check.")
    : "Run VM check against the ESXi host; vCenter is not required for this setup.";

  return {
    access,
    badgeStatus: virtualizationVmBadgeStatus(stateLabel),
    datastore: vcenterEnabled ? datastoreName(vcenterNetapp || postAttach) : storageLabel,
    mode,
    nextAction,
    reason,
    stateLabel,
    target: vcenterEnabled ? target : displayAddress(address.esxi_management)
  };
}

function virtualizationVmStateLabel(status: string, target: string | null | undefined): "Ready" | "Blocked" | "Not checked" {
  if (!target) return "Blocked";
  const normalized = status.toLowerCase();
  if (["ready", "ok", "passed", "safe-to-run", "safe_to_run", "success"].includes(normalized)) return "Ready";
  if (!normalized || ["not_checked", "unknown", "running"].includes(normalized)) return "Not checked";
  return "Blocked";
}

function virtualizationVmBadgeStatus(label: "Ready" | "Blocked" | "Not checked"): StatusBadgeStatus {
  if (label === "Ready") return "ready";
  if (label === "Blocked") return "needs-attention";
  return "not-configured";
}

function virtualizationVmReason({
  address,
  currentView,
  installReadiness,
  postAttach,
  vcenterEnabled,
  vcenterNetapp
}: {
  address: LabAddressPlan;
  currentView: CurrentViewModel;
  installReadiness: ProviderProbeResult | null;
  postAttach: ProviderProbeResult | null;
  vcenterEnabled: boolean;
  vcenterNetapp: ProviderProbeResult | null;
}) {
  if (!vcenterEnabled && !address.esxi_management) {
    return "Set the ESXi address before running the VM check.";
  }
  return humanize(
    currentView.blockers[0] ||
      stringArray(postAttach?.blockers)[0] ||
      stringArray(vcenterNetapp?.blockers)[0] ||
      stringArray(installReadiness?.blockers)[0] ||
      asString(postAttach?.next_safe_action) ||
      asString(vcenterNetapp?.next_safe_action) ||
      asString(installReadiness?.next_safe_action) ||
      (vcenterEnabled ? "Run VM check before using the vCenter path." : "Run VM check before validating direct ESXi VM deployment.")
  );
}

function VirtualizationSetupShapePanel({
  activeProfile,
  currentView,
  features,
  installReadiness,
  postAttach,
  storageLabel,
  target,
  vcenterEnabled,
  vcenterNetapp,
  virtualStatus
}: {
  activeProfile: LabProfile | null;
  currentView: CurrentViewModel;
  features: LabProfileFeatures | null;
  installReadiness: ProviderProbeResult | null;
  postAttach: ProviderProbeResult | null;
  storageLabel: string;
  target: string;
  vcenterEnabled: boolean;
  vcenterNetapp: ProviderProbeResult | null;
  virtualStatus: string;
}) {
  const scenario = deploymentScenarioLabel(features);
  const postChecks = objectValue(postAttach?.checks);
  const datastoreStatus = vcenterEnabled ? datastoreVisibleStatus(vcenterNetapp || postAttach) : "not_checked";
  const inventoryStatus = vcenterEnabled ? visibilityStatus(postChecks.vm_inventory_visible) : "not_checked";
  const status = vcenterEnabled ? virtualStatus : "not_checked";
  const ladderStatus = statusBadgeStatus(status);
  const pathTitle = vcenterEnabled ? "vCenter VM Handoff Path" : "Direct ESXi VM Path";
  const pathSummary = vcenterEnabled
    ? "Use vCenter to prove host attachment, datastore visibility, and VM inventory."
    : "Use the ESXi host directly; vCenter stays out of the required path for this setup.";
  const validationSummary = vcenterEnabled
    ? currentView.summary
    : `${scenario}: validate datastore and VM deployment directly against ESXi.`;
  const steps: RemediationStep[] = [
    {
      detail: vcenterEnabled ? target : displayAddress(activeAddressPlan(activeProfile).esxi_management),
      label: vcenterEnabled ? "vCenter endpoint" : "ESXi endpoint",
      nextAction: vcenterEnabled
        ? humanize(asString(vcenterNetapp?.next_safe_action) || "Run vCenter Live Check.")
        : "Run ESXi Live Check before VM deployment validation.",
      status: vcenterEnabled ? statusBadgeStatus(virtualStatus) : "not-configured"
    },
    {
      detail: vcenterEnabled ? datastoreName(vcenterNetapp) : storageLabel,
      label: "Datastore visibility",
      nextAction: vcenterEnabled ? "Validate datastore visibility after storage changes." : "Validate datastore visibility from ESXi before VM deployment.",
      status: statusBadgeStatus(datastoreStatus)
    },
    {
      detail: vcenterEnabled ? visibilityLabel(postChecks.vm_inventory_visible) : "Direct ESXi inventory validation",
      label: "VM inventory",
      nextAction: vcenterEnabled ? "Validate inventory after datastore and vCenter access are ready." : "Validate VM deployment directly against ESXi.",
      status: statusBadgeStatus(inventoryStatus)
    },
    {
      detail: "Guarded OVF deployment",
      label: "VM deploy guard",
      nextAction: "Run validation before any guarded VM deployment.",
      status: "not-configured"
    }
  ];

  return (
    <Card className="virtualization-setup-card" hover={false}>
      <CardHeader>
        <div>
          <p className="operator-kicker">Virtualization setup shape</p>
          <h2>{pathTitle}</h2>
          <p>{pathSummary}</p>
        </div>
        <StatusBadge label={displayStatus(status)} status={ladderStatus} />
      </CardHeader>
      <CardContent>
        <div className="virtualization-setup-grid" aria-label="Virtualization setup intent">
          <div>
            <span>Needed</span>
            <strong>{vcenterEnabled ? "Portable VM handoff through vCenter" : "Single host VM deployment"}</strong>
          </div>
          <div>
            <span>Current</span>
            <strong>{currentView.available ? currentView.summary : validationSummary}</strong>
          </div>
          <div>
            <span>Intent</span>
            <strong>{vcenterEnabled ? "vCenter sees host, datastore, and VM inventory" : "ESXi owns datastore and VM lifecycle"}</strong>
          </div>
          <div>
            <span>Validation</span>
            <strong>{validationSummary}</strong>
          </div>
        </div>

        <RemediationLadder
          className="virtualization-remediation-panel"
          defaultOpen={ladderStatus !== "ready"}
          status={ladderStatus}
          statusLabel={displayStatus(status)}
          steps={steps}
          summary={validationSummary}
          title="Virtualization setup path"
        />

        <div className="server-action-strip" aria-label="Virtualization actions">
          <ActionLink to="/overview#topology-map">Open map workspace</ActionLink>
          <ActionLink to="/validation">Validation</ActionLink>
        </div>

        <RemediationLadder
          className="virtualization-optional-handoff"
          defaultOpen={false}
          status={vcenterEnabled ? "ready" : "plan-only"}
          statusLabel={vcenterEnabled ? "In scope" : "Optional"}
          steps={[
            {
              detail: vcenterEnabled ? "vCenter is active in this lab profile." : asString(features?.vcenter_disabled_reason) || "vCenter is disabled by the active lab setup.",
              label: "vCenter scope",
              nextAction: vcenterEnabled ? "Keep vCenter checks in the primary path." : "Enable vCenter only when centralized management is required.",
              status: vcenterEnabled ? "ready" : "plan-only"
            },
            {
              detail: storageLabel,
              label: "Storage dependency",
              nextAction: "Open the NetApp workspace when datastore readiness changes.",
              status: "plan-only"
            }
          ]}
          summary={vcenterEnabled ? "Direct ESXi remains a fallback validation surface." : "vCenter can stay collapsed for single-host shipment builds."}
          title="Optional control-plane handoff"
          tone="optional"
        />
      </CardContent>
    </Card>
  );
}

export function OperatorFirmwareUpgradesPage({ labProfileState }: OperatorPageProps) {
  const [actions, setActions] = useState<WorkflowAction[]>([]);
  const [firmwareSummaries, setFirmwareSummaries] = useState<FirmwareSummary[]>([]);
  const [compliance, setCompliance] = useState<ProviderProbeResult | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectionError, setSelectionError] = useState("");

  async function load() {
    setError("");
    setLoading(true);
    void safeApi(api.workflowActions, [] as WorkflowAction[]).then((nextActions) => {
      setActions(Array.isArray(nextActions) ? nextActions : []);
    });
    try {
      const [nextSummaries, nextCompliance, nextSelections] = await Promise.all([
        safeApi(api.firmwareSummary, [] as FirmwareSummary[]),
        safeApi(api.firmwareCompliance, null),
        safeApi(api.firmwareFileSelections, null)
      ]);
      setFirmwareSummaries(Array.isArray(nextSummaries) ? nextSummaries : []);
      setCompliance(nextCompliance);
      setSelectedFiles(nextSelections?.selected_files ?? {});
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const firmwareStatus = strongestStatus([
    asString(compliance?.status) || "not_checked",
    ...firmwareSummaries.map((summary) => summary.compliance_status || summary.path_status || "not_checked")
  ]);
  const rows = firmwareRows(firmwareSummaries, compliance, selectedFiles);

  async function planUpgrade() {
    const action = actions.find((candidate) => candidate.action_id === "firmware.upgrade-plan");
    if (!action) {
      setSelectionError("Upgrade planning is not available until the action list is loaded.");
      return;
    }
    setSelectionError("");
    try {
      await api.runWorkflowAction(action.action_id);
      setSelectionError("");
      setError("");
      await load();
    } catch (err) {
      setSelectionError(errorMessage(err));
    }
  }

  return (
    <OperatorPage title="Firmware Upgrades">
      <section className="firmware-simple-header" aria-labelledby="firmware-simple-title">
        <div>
          <p className="operator-kicker">Setup / Firmware</p>
          <h1 id="firmware-simple-title">Keep every device on the expected version.</h1>
          <p>Check the current version, compare it with the target, then upgrade or leave it as-is.</p>
        </div>
        <RunCheckButton actionIds={["firmware.inventory", "firmware.compliance-check"]} actions={actions} label="Check versions" onReload={load} />
      </section>
      <Feedback loading={loading && !firmwareSummaries.length} error={error} />
      <Feedback loading={false} error={selectionError} />
      <FirmwareSimpleTable
        actions={actions}
        rows={rows}
        selectedFiles={selectedFiles}
        onPlanUpgrade={planUpgrade}
      />
      <p className="firmware-simple-footer">Upgrade asks for confirmation before it can touch hardware. Bypass leaves the device as-is and records your choice.</p>
    </OperatorPage>
  );
}

function FirmwareSimpleTable({
  actions,
  onPlanUpgrade,
  rows,
  selectedFiles
}: {
  actions: WorkflowAction[];
  onPlanUpgrade: () => Promise<void>;
  rows: FirmwareTableRow[];
  selectedFiles: Record<string, string>;
}) {
  const [decisions, setDecisions] = useState<Record<string, "upgrade" | "bypass">>({});
  const hasPlanAction = actions.some((action) => action.action_id === "firmware.upgrade-plan");

  if (!rows.length) {
    return (
      <section className="firmware-simple-empty" aria-label="Firmware versions">
        <ShieldCheck size={24} />
        <strong>No device versions loaded yet.</strong>
        <span>Check versions to compare the lab hardware with its targets.</span>
      </section>
    );
  }

  return (
    <section className="firmware-simple-table-shell" aria-label="Firmware version decisions">
      <div className="firmware-simple-table-head">
        <div>
          <span className="operator-kicker">Firmware decisions</span>
          <h2>What should each device be?</h2>
        </div>
        <span className="firmware-simple-status">{firmwareDecisionSummary(rows)}</span>
      </div>
      <div className="firmware-simple-table-wrap">
        <table className="firmware-simple-table">
          <thead>
            <tr><th>Device</th><th>Current version</th><th>Target version</th><th>Action</th></tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const decision = decisions[row.componentId];
              const current = row.current || "Not checked";
              const target = row.target || "Not set";
              const currentState = row.pathStatus === "current";
              const canUpgrade = !currentState && row.pathStatus !== "scan_needed" && hasPlanAction;
              const reason = firmwareDecisionReason(row, currentState);
              return (
                <tr key={row.componentId}>
                  <td>
                    <div className="firmware-simple-device">
                      <span className="firmware-simple-device-icon"><Server size={18} /></span>
                      <span><strong>{row.equipment}</strong><small>{row.component}</small></span>
                    </div>
                  </td>
                  <td className="firmware-version">{current}</td>
                  <td>
                    <div className="firmware-target-version"><strong>{target}</strong><small>{reason}</small></div>
                  </td>
                  <td>
                    <div className="firmware-row-actions">
                      <button aria-pressed={decision === "upgrade"} className="firmware-upgrade-button" disabled={!canUpgrade} onClick={() => { setDecisions((previous) => ({ ...previous, [row.componentId]: "upgrade" })); void onPlanUpgrade(); }} title={canUpgrade ? "Start guarded upgrade planning" : "Upgrade unavailable"} type="button">Upgrade</button>
                      <button aria-pressed={decision === "bypass"} className="firmware-bypass-button" onClick={() => setDecisions((previous) => ({ ...previous, [row.componentId]: "bypass" }))} type="button">Bypass</button>
                    </div>
                    {decision && <small className="firmware-decision-state">{decision === "upgrade" ? "Upgrade planned" : "Bypassed"}</small>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function firmwareDecisionReason(row: FirmwareTableRow, current: boolean): string {
  if (current) return "Already current";
  if (row.pathStatus === "scan_needed") return "Check versions first";
  const raw = row.disabledReason.trim();
  if (!raw) return "Upgrade available";
  if (/missing target|baseline/i.test(raw)) return row.target === "Not set" ? "Target not set" : "Review baseline";
  if (/manual review/i.test(raw)) return "Review baseline";
  return humanize(raw.replace(/[.:]+$/, "")).slice(0, 52);
}

function RunCheckButton({
  actionIds,
  actions,
  label,
  onReload
}: {
  actionIds: string[];
  actions: WorkflowAction[];
  label: string;
  onReload: () => Promise<void> | void;
}) {
  const [running, setRunning] = useState(false);
  const action = actionIds.map((id) => actions.find((candidate) => candidate.action_id === id)).find(Boolean) ?? null;

  async function run() {
    if (!action) return;
    setRunning(true);
    try {
      await api.runWorkflowAction(action.action_id);
      await onReload();
    } catch {
      // The page-level feedback owns API errors; keep the button usable when a check fails.
    } finally {
      setRunning(false);
    }
  }

  return <button className="primary firmware-check-button" disabled={!action || running} onClick={() => void run()} type="button"><RefreshCw size={16} />{running ? "Checking..." : label}</button>;
}

export function OperatorValidationPage({ isAdvancedMode = false, labProfileState }: OperatorPageProps) {
  const activeProfile = activeLabProfile(labProfileState);
  const [actions, setActions] = useState<WorkflowAction[]>([]);
  const [validation, setValidation] = useState<LabValidationSummary | null>(null);
  const [buildVerification, setBuildVerification] = useState<ProviderProbeResult | null>(null);
  const [vcenterNetapp, setVcenterNetapp] = useState<ProviderProbeResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [advancedProofOpen, setAdvancedProofOpen] = useState(false);
  const [runState, setRunState] = useState<WorkflowRunState>(emptyRunState);
  const [diagnosis, setDiagnosis] = useState<WorkflowActionDiagnosis | null>(null);
  const [diagnosisLoading, setDiagnosisLoading] = useState(false);

  async function load() {
    setError("");
    setLoading(true);
    try {
      const actionsPromise = safeApi(api.workflowActions, [] as WorkflowAction[]).then((nextActions) => {
        setActions(Array.isArray(nextActions) ? nextActions : []);
      });
      const validationPromise = safeApi(api.labValidation, null).then((nextValidation) => {
        setValidation(nextValidation);
        setLoading(false);
      });
      await Promise.all([
        actionsPromise,
        validationPromise,
        safeApi(api.buildVerification, null).then((nextBuildVerification) => {
          setBuildVerification(nextBuildVerification);
        }),
        safeApi(api.vcenterNetappReadiness, null).then((nextVcenterNetapp) => {
          setVcenterNetapp(nextVcenterNetapp);
        })
      ]);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const differentFromExpected = validation?.validation_items.filter((item) => item.status !== "ready").length ?? 0;
  const currentView = validationCurrentView({ buildVerification, validation, vcenterNetapp });
  const scenarioScope = validationScenarioScope(activeProfile, validation);
  const validationRows = useMemo<OperatorObjectRow[]>(
    () => [
      ...(validation?.validation_items ?? []).map((item) => ({
        checkedAt: item.last_checked ? formatDateTime(item.last_checked) : currentView.checkedAt,
        details: [
          { label: "Category", value: labelize(item.category || "validation") },
          { label: "Current state", value: item.current_state || "Not checked" },
          { label: "Setup summary", value: item.setup_summary || "Not checked" },
          { label: "Management URL", value: item.management_url || "Not set up yet" }
        ],
        freshness: currentView.freshness,
        id: item.id,
        nextAction: humanize(item.next_action || validation?.next_action || "Review validation result."),
        source: currentView.source,
        status: item.status,
        summary: item.setup_summary || item.current_state || "Validation item.",
        target: item.management_url || item.label,
        title: item.label,
        type: labelize(item.category || item.stage || "Validation"),
        warnings: item.warnings
      })),
      {
        checkedAt: currentView.checkedAt,
        details: [
          { label: "Different from expected", value: String(differentFromExpected), status: differentFromExpected ? "warning" : "ready" },
          { label: "Build verification", value: displayStatus(buildVerification?.status ?? "not_checked"), status: buildVerification?.status ?? "not_checked" },
          { label: "Report", value: validation?.handoff_report ? "Ready to review" : "Not created", status: validation?.handoff_report ? "ready" : "not_checked" }
        ],
        freshness: currentView.freshness,
        id: "handoff",
        nextAction: validation?.handoff_report ? "Generate handoff after reviewing validation." : "Run validation before handoff.",
        source: currentView.source,
        status: validation?.overall_status ?? "not_checked",
        summary: validation?.next_action || "Lab-wide validation and handoff readiness.",
        target: "Golden State",
        title: "Golden State / Handoff",
        type: "Summary",
        blockers: validation?.top_blocker ? [validation.top_blocker.problem] : []
      }
    ],
    [buildVerification, currentView, differentFromExpected, validation]
  );
  const validationActionIds = ["build-verification.run-full", "full-lab.validation", "lab-validation.summary"];
  const validationRunConfig: TabRunConfig = { actionIds: validationActionIds, actions, label: "Validation" };
  const validationActionById = useMemo(() => new Map(actions.map((action) => [action.action_id, action])), [actions]);
  const validationAction = firstRunnableAction(validationActionById, validationActionIds, validationRunConfig);
  const validationFallbackActionId = fallbackRunActionId(validationRunConfig, validationAction);
  const validationDisabledReason = validationAction
    ? disabledReasonForRunConfig(validationRunConfig, validationAction)
    : validationFallbackActionId
      ? ""
      : disabledReasonForRunConfig(validationRunConfig, null);
  const validationCard = validationReadinessCardModel(validation);
  const validationAdvancedProof = (
    <details
      className="advanced-drawer"
      onToggle={(event) => setAdvancedProofOpen(event.currentTarget.open)}
    >
      <summary>
        <Wrench size={16} />
        <span>Advanced proof</span>
        <small>{noProofText}</small>
      </summary>
      {advancedProofOpen && (
        <div>
          <OperatorReferencePanel
            ariaLabel="Validation reference"
            currentView={currentView}
            rows={validationRows}
            subtitle="Golden State and proof"
            tableTitle="Validation Signals"
            title="Validation readiness at a glance"
          />
          <OperatorWorkspace currentView={currentView} rows={validationRows} compact />
          <ValidationProofList items={validation?.validation_items ?? []} proofLinks={validation?.proof_links.length ?? 0} />
          <ConfigValueList
            values={[
              { label: "Source", value: sourceLabel(validation) },
              { label: "Warnings", value: String(validation?.warnings.length ?? 0) },
              { label: "Raw proof links", value: String(validation?.proof_links.length ?? 0) }
            ]}
          />
        </div>
      )}
    </details>
  );
  const resetRebuildPanel = <LabResetRebuildPanel actions={actions} onReload={load} />;

  async function runDefaultValidation() {
    if (validationDisabledReason || runState.runningActionId) return;
    const actionId = validationAction?.action_id ?? validationFallbackActionId;
    if (!actionId) return;
    setDiagnosis(null);
    setRunState({ error: "", message: "Validation is running.", runningActionId: actionId });
    try {
      const result = await api.runWorkflowAction(actionId);
      setRunState({
        error: "",
        message: validationAction ? workflowRunMessage(validationAction, result) : workflowRunResultMessage("Validation", result),
        runningActionId: ""
      });
      if (isProblemRun(result)) {
        await loadValidationDiagnosis(actionId);
      }
      await load();
    } catch (err) {
      setRunState({ error: errorMessage(err), message: "", runningActionId: "" });
    }
  }

  async function createHandoffReport() {
    if (runState.runningActionId) return;
    setDiagnosis(null);
    setRunState({ error: "", message: "Creating report.", runningActionId: "full-lab.handoff-report" });
    try {
      await api.labValidationHandoff();
      setRunState({
        error: "",
        message: "Report is ready.",
        runningActionId: ""
      });
      await load();
    } catch (err) {
      setRunState({ error: errorMessage(err), message: "", runningActionId: "" });
    }
  }

  function reviewHandoff() {
    setDetailsOpen(true);
    setRunState({ error: "", message: "", runningActionId: "" });
  }

  async function loadValidationDiagnosis(actionId: string) {
    setDiagnosisLoading(true);
    try {
      setDiagnosis(await api.workflowActionDiagnosis(actionId));
    } catch {
      setDiagnosis(null);
    } finally {
      setDiagnosisLoading(false);
    }
  }

  return (
    <OperatorPage title="Validation">
      <div className="operator-surface-heading">
        <p className="operator-kicker">Run</p>
        <h1>Validation</h1>
        <p>Is this kit ready to ship, and what is the one check to run next?</p>
      </div>
      <Feedback loading={false} error={error} />
      <section className="validation-readiness-surface" aria-label="Readiness Check">
        <Card className="validation-readiness-card" hover={false}>
          <CardHeader>
            <div>
              <p className="operator-kicker">Final check</p>
              <h2>Ready to ship?</h2>
            </div>
            <StatusBadge label={validationCard.state} status={validationCard.badgeStatus} />
          </CardHeader>
          <CardContent>
            <div className="handoff-readiness-headline">
              <h3>{validationCard.headline}</h3>
              <p>{validationCard.supportingMessage}</p>
            </div>
            <div className="handoff-readiness-meter" aria-label="Kit readiness meter">
              <div>
                <span>Readiness</span>
                <strong>{validationCard.meterText}</strong>
              </div>
              <div className="handoff-meter-track">
                <i style={{ width: `${validationCard.meterPercent}%` }} />
              </div>
            </div>
            {validationCard.attentionMessage && (
              <div className="validation-readiness-reason" role="note">
                <strong>{validationCard.attentionLabel}</strong>
                <span>{validationCard.attentionMessage}</span>
              </div>
            )}
            {runState.message && <div className="operator-feedback validation-readiness-feedback">{runState.message}</div>}
            {runState.error && <div className="operator-feedback error validation-readiness-feedback">{runState.error}</div>}
            {diagnosisLoading && <p className="operator-action-message">Preparing advisory diagnosis...</p>}
            {diagnosis && <WorkflowDiagnosisCard diagnosis={diagnosis} />}
          </CardContent>
          <CardFooter>
            <div className="validation-readiness-actions">
              {validationCard.primaryAction.kind === "fix" ? (
                <Link className="operator-primary-button" to={validationCard.primaryAction.to ?? "/validation"}>
                  <Wrench size={16} />
                  {validationCard.primaryAction.label}
                </Link>
              ) : (
                <button
                  className="operator-primary-button"
                  disabled={
                    Boolean(runState.runningActionId) ||
                    (validationCard.primaryAction.kind === "run-validation" && Boolean(validationDisabledReason))
                  }
                  onClick={() => {
                    if (validationCard.primaryAction.kind === "run-validation") {
                      void runDefaultValidation();
                    } else if (validationCard.primaryAction.kind === "create-handoff") {
                      void createHandoffReport();
                    } else {
                      reviewHandoff();
                    }
                  }}
                  title={validationCard.primaryAction.kind === "run-validation" ? validationDisabledReason || validationCard.primaryAction.label : validationCard.primaryAction.label}
                  type="button"
                >
                  {validationCard.primaryAction.kind === "review-handoff" ? <ShieldCheck size={16} /> : <CheckCircle2 size={16} />}
                  {runState.runningActionId ? "Running" : validationCard.primaryAction.label}
                </button>
              )}
              <button
                aria-expanded={detailsOpen}
                className="secondary-button"
                onClick={() => setDetailsOpen((current) => !current)}
                type="button"
              >
                {detailsOpen ? "Hide details" : "View details"}
              </button>
            </div>
            {validationCard.primaryAction.kind === "run-validation" && validationDisabledReason && (
              <span className="run-button-safety-note">{validationDisabledReason}</span>
            )}
          </CardFooter>
        </Card>
      </section>

      {detailsOpen && (
        <section className="validation-details" aria-label="Validation details">
          <div className="handoff-details-panel" aria-label="Kit readiness details">
            <article>
              <span>What was checked</span>
              <strong>{validationCard.checkedSummary}</strong>
              {validationCard.exceptions.length ? (
                <ul className="handoff-exception-list">
                  {validationCard.exceptions.map((item) => (
                    <li key={item.id}>
                      <b>{item.label}</b>
                      <small>{item.nextAction}</small>
                    </li>
                  ))}
                </ul>
              ) : (
                <p>Healthy devices are summarized here; there are no exceptions to expand.</p>
              )}
            </article>
            <article>
              <span>What changed</span>
              <strong>{validationCard.changeSummary}</strong>
              <p>{validationCard.changeDetail}</p>
            </article>
            <article>
              <span>Report files</span>
              <strong>{validationCard.handoffSummary}</strong>
              <p>{validationCard.handoffDetail}</p>
            </article>
          </div>
          {validationAdvancedProof}
        </section>
      )}

      {isAdvancedMode && (
        <details className="validation-danger-zone" aria-label="Danger zone">
          <summary>
            <span>
              <span className="operator-kicker danger">Danger zone</span>
              <strong>Reset and rebuild controls</strong>
              <small>Closed by default. These workflows stay behind existing guarded confirmations.</small>
            </span>
          </summary>
          <div>
            {resetRebuildPanel}
          </div>
        </details>
      )}
    </OperatorPage>
  );
}

function validationReadinessCardModel(validation: LabValidationSummary | null) {
  const items = validation?.validation_items ?? [];
  const readyCount = items.filter((item) => validationItemIsReady(item.status)).length;
  const totalCount = items.length;
  const status = validation?.overall_status || (validation ? strongestStatus(items.map((item) => item.status)) : "not_checked");
  const state = validationReadinessStateLabel(status);
  const exceptions = items
    .filter((item) => !validationItemIsReady(item.status) && item.status !== "not_in_scope")
    .map((item) => ({
      id: item.id,
      label: item.label,
      nextAction: humanize(item.next_action || item.setup_summary || item.current_state || "Review this item."),
      status: item.status
    }));
  const firstIssue = items.find((item) => !validationItemIsReady(item.status) && item.status !== "not_in_scope");
  const firstFix = validationFixTarget(firstIssue);
  const blockerText = humanize(
    validation?.top_blocker?.problem ||
    validation?.top_blocker?.recommended_action ||
    firstIssue?.next_action ||
    firstIssue?.setup_summary ||
    firstIssue?.current_state ||
    validation?.next_action ||
    ""
  );
  const handoffReady = Boolean(validation?.handoff_report);
  const meterPercent = totalCount ? Math.round((readyCount / totalCount) * 100) : 0;
  const warnings = (validation?.warnings ?? []).map((warning) => humanize(warning)).filter(Boolean);
  const headline = state === "Ready"
    ? "Ready to ship"
    : state === "Blocked"
      ? "Needs one fix"
      : "Not checked";
  const supportingMessage = state === "Ready"
    ? handoffReady
      ? "All required checks are ready and the report exists."
      : "All required checks are ready. Create the report before closing the kit."
    : state === "Blocked"
      ? blockerText || "One item needs attention before this kit can ship."
      : "Run validation to see whether this kit is ready.";
  const primaryAction: ValidationPrimaryAction = state === "Ready"
    ? handoffReady
      ? { kind: "review-handoff", label: "Review report" }
      : { kind: "create-handoff", label: "Create report" }
    : state === "Blocked"
      ? { kind: "fix", label: firstFix.label, to: firstFix.to }
      : { kind: "run-validation", label: "Run validation" };
  return {
    attentionLabel: state === "Blocked" ? "Needs attention" : state === "Not checked" ? "Next check" : "",
    attentionMessage: state === "Blocked"
      ? blockerText || "Open the matching setup page and fix the first exception."
      : state === "Not checked"
        ? "Nothing is marked ready until validation runs."
        : "",
    badgeStatus: validationReadinessBadgeStatus(state),
    changeDetail: warnings[0] || (blockerText ? `First fix: ${blockerText}` : "No blockers are currently reported."),
    changeSummary: warnings.length ? `${warnings.length} warning${warnings.length === 1 ? "" : "s"} need review` : exceptions.length ? "One fix is blocking handoff" : "No changes need attention",
    checkedSummary: totalCount ? `${readyCount} of ${totalCount} checks are ready` : "No checks have run yet",
    exceptions,
    handoffDetail: handoffReady
      ? "The report is available for review. Supporting proof stays in Advanced proof."
      : state === "Ready"
        ? "Create the report from this page when the kit is ready."
        : "A report is created after validation is ready.",
    handoffSummary: handoffReady ? "Report is ready" : "No report yet",
    headline,
    meterPercent,
    meterText: `${readyCount} / ${totalCount} ready`,
    primaryAction,
    state,
    supportingMessage
  };
}

type ValidationPrimaryAction =
  | { kind: "run-validation"; label: string }
  | { kind: "review-handoff"; label: string }
  | { kind: "create-handoff"; label: string }
  | { kind: "fix"; label: string; to: string };

function validationItemIsReady(status: string): boolean {
  return ["ready", "ok", "passed", "completed", "success"].includes(status);
}

function validationFixTarget(item: LabValidationItem | undefined): { label: string; to: string } {
  const text = `${item?.id ?? ""} ${item?.category ?? ""} ${item?.stage ?? ""} ${item?.label ?? ""}`.toLowerCase();
  if (textIncludes(text, ["cisco", "network", "switch"])) return { label: "Fix Cisco switch", to: "/network" };
  if (textIncludes(text, ["ilo", "server", "compute", "raid"])) return { label: "Fix compute access", to: "/server" };
  if (textIncludes(text, ["netapp", "storage", "datastore", "nfs", "iscsi"])) return { label: "Fix storage path", to: "/storage" };
  if (textIncludes(text, ["esxi", "vcenter", "virtualization", "vm"])) return { label: "Fix virtualization", to: "/virtualization" };
  if (textIncludes(text, ["firmware", "upgrade"])) return { label: "Fix firmware", to: "/firmware-upgrades" };
  return { label: "Fix lab defaults", to: "/lab-defaults" };
}

function validationReadinessStateLabel(status: string): "Ready" | "Blocked" | "Not checked" {
  const normalized = status.toLowerCase();
  if (["ready", "ok", "passed", "completed", "success"].includes(normalized)) return "Ready";
  if (!normalized || ["not_checked", "unknown", "not_configured", "not_configured_yet"].includes(normalized)) return "Not checked";
  return "Blocked";
}

function validationReadinessBadgeStatus(label: "Ready" | "Blocked" | "Not checked"): StatusBadgeStatus {
  if (label === "Ready") return "ready";
  if (label === "Blocked") return "blocked";
  return "not-configured";
}

function ValidationSetupShapePanel({
  buildVerification,
  currentView,
  scenarioScope,
  validation
}: {
  buildVerification: ProviderProbeResult | null;
  currentView: CurrentViewModel;
  scenarioScope: ValidationScenarioScope;
  validation: LabValidationSummary | null;
}) {
  const overallStatus = validation?.overall_status ?? "not_checked";
  const totalItems = validation?.validation_items.length ?? 0;
  const issues = validation?.validation_items.filter((item) => item.status !== "ready").length ?? 0;
  const proofLinks = validation?.proof_links.length ?? 0;
  const handoffReady = Boolean(validation?.handoff_report);
  const summary = validation?.next_action || scenarioScope.summary;
  const ladderStatus = statusBadgeStatus(overallStatus);

  return (
    <Card className="validation-setup-card" hover={false}>
      <CardHeader>
        <div>
          <p className="operator-kicker">Validation setup shape</p>
          <h2>Prove, Repair, Handoff</h2>
          <p>Validation turns the selected lab scenario into clear readiness, reset/rebuild evidence, and final report output.</p>
        </div>
        <StatusBadge label={displayStatus(overallStatus)} status={ladderStatus} />
      </CardHeader>
      <CardContent>
        <div className="validation-setup-grid" aria-label="Validation setup intent">
          <div>
            <span>Needed</span>
            <strong>{scenarioScope.scenario}</strong>
          </div>
          <div>
            <span>Current</span>
            <strong>{currentView.available ? currentView.summary : "Run validation to load the golden-state view."}</strong>
          </div>
          <div>
            <span>Intent</span>
            <strong>{scenarioScope.activePath}</strong>
          </div>
          <div>
            <span>Validation</span>
            <strong>{totalItems ? `${totalItems - issues}/${totalItems} ready, ${proofLinks} proof link${proofLinks === 1 ? "" : "s"}` : "No validation run yet"}</strong>
          </div>
        </div>

        <RemediationLadder
          className="validation-remediation-panel"
          defaultOpen={ladderStatus !== "ready"}
          status={ladderStatus}
          statusLabel={displayStatus(overallStatus)}
          steps={[
            {
              detail: scenarioScope.summary,
              label: "Scenario scope",
              nextAction: scenarioScope.nextAction,
              status: statusBadgeStatus(scenarioScope.status)
            },
            {
              detail: totalItems ? `${issues} item${issues === 1 ? "" : "s"} need attention` : "No validation items loaded",
              label: "Golden-state validation",
              nextAction: humanize(validation?.next_action || "Run validation."),
              status: statusBadgeStatus(overallStatus)
            },
            {
              detail: displayStatus(buildVerification?.status ?? "not_checked"),
              label: "Live-device evidence",
              nextAction: "Run the live-device smoke check and read-only sweep before handoff.",
              status: statusBadgeStatus(buildVerification?.status ?? "not_checked")
            },
            {
              detail: handoffReady ? "Handoff report available" : "No handoff report generated yet",
              label: "Handoff report",
              nextAction: handoffReady ? "Generate handoff after reviewing current proof." : "Run validation before handoff.",
              status: handoffReady ? "ready" : "not-configured"
            }
          ]}
          summary={summary}
          title="Validation setup path"
        />

        <div className="server-action-strip" aria-label="Validation actions">
          <ActionLink to="/overview">Overview</ActionLink>
          <ActionLink to="/audit-events">Audit Log</ActionLink>
          <ActionLink to="/overview#topology-map">Map workspace</ActionLink>
        </div>

        <RemediationLadder
          className="validation-optional-handoff"
          defaultOpen={false}
          status="needs-attention"
          statusLabel="Danger"
          steps={[
            {
              detail: "Factory reset and rebuild can destroy local VM datastore state once a real executor is enabled.",
              label: "Factory reset",
              nextAction: "Use the Start from scratch danger-zone panel only with explicit confirmation and current proof.",
              status: "needs-attention"
            },
            {
              detail: "Rebuild evidence feeds the final validation and handoff path.",
              label: "Rebuild proof",
              nextAction: "Run full validation and handoff evidence only after an intentional rebuild.",
              status: "plan-only"
            }
          ]}
          summary="Destructive reset/rebuild work stays separated from normal validation and must remain an explicit danger-zone choice."
          title="Guarded reset and rebuild handoff"
        />
      </CardContent>
    </Card>
  );
}

type ValidationScenarioScope = {
  activePath: string;
  datastorePath: string;
  items: Array<{ label: string; status: string; value: string }>;
  nextAction: string;
  scenario: string;
  status: string;
  summary: string;
};

function ValidationScenarioScopePanel({ scope }: { scope: ValidationScenarioScope }) {
  return (
    <section className="validation-scope-panel" aria-label="Validation scenario scope">
      <div className="validation-scope-head">
        <div>
          <p className="operator-kicker">Scenario scope</p>
          <h2>{scope.scenario}</h2>
          <p>{scope.summary}</p>
        </div>
        <StatusBadge label={displayStatus(scope.status)} status={statusBadgeStatus(scope.status)} />
      </div>
      <div className="validation-scope-grid">
        <div>
          <span>Active handoff path</span>
          <strong>{scope.activePath}</strong>
        </div>
        <div>
          <span>Datastore path</span>
          <strong>{scope.datastorePath}</strong>
        </div>
        {scope.items.map((item) => (
          <div key={item.label}>
            <span>{item.label}</span>
            <strong>{item.value}</strong>
            <StatusBadge label={displayStatus(item.status)} status={statusBadgeStatus(item.status)} />
          </div>
        ))}
      </div>
      <div className="validation-scope-next">
        <span>Next validation action</span>
        <strong>{scope.nextAction}</strong>
      </div>
    </section>
  );
}

function validationScenarioScope(activeProfile: LabProfile | null, validation: LabValidationSummary | null): ValidationScenarioScope {
  const features = activeProfile?.features ?? null;
  const scenario = deploymentScenarioLabel(features);
  const storageLocation = asString(features?.storage_location);
  const protocol = asString(features?.storage_protocol).toLowerCase() || "nfs";
  const netappShared = storageLocation !== "server_local" && Boolean(features?.netapp_enabled);
  const vcenterEnabled = Boolean(features?.vcenter_enabled);
  const items = validation?.validation_items ?? [];
  const byId = new Map(items.map((item) => [item.id, item]));
  const nfs = byId.get("netapp-nfs");
  const iscsi = byId.get("esxi-iscsi-datastore");
  const vcenter = byId.get("vcenter");
  const vcenterDatastore = byId.get("vcenter-netapp-datastore");
  const activePath = netappShared
    ? protocol === "iscsi"
      ? "NetApp iSCSI + ESXi VMFS"
      : "NetApp NFS + direct ESXi datastore"
    : "Server-local RAID datastore";
  const datastorePath = netappShared
    ? protocol === "iscsi"
      ? "ONTAP LUN, igroup, map, ESXi iSCSI session"
      : "ONTAP NFS export, LIFs, ESXi NFS mount"
    : "Local Smart Array logical drive presented to ESXi";
  return {
    activePath,
    datastorePath,
    items: [
      {
        label: "NFS",
        status: nfs?.status ?? (protocol === "nfs" && netappShared ? "not_checked" : "not_in_scope"),
        value: protocol === "nfs" && netappShared ? "Selected shared datastore path" : "Available when profile selects NFS"
      },
      {
        label: "iSCSI",
        status: iscsi?.status ?? (protocol === "iscsi" && netappShared ? "not_checked" : "not_in_scope"),
        value: protocol === "iscsi" && netappShared ? "Selected block datastore path" : "Available option, not active"
      },
      {
        label: "vCenter",
        status: vcenterEnabled ? vcenter?.status ?? vcenterDatastore?.status ?? "not_checked" : "not_in_scope",
        value: vcenterEnabled ? "In scope for inventory and VM handoff" : "Out of scope for this profile"
      }
    ],
    nextAction: validation?.next_action || (netappShared ? "Run validation and resolve the first partial/warning item." : "Validate local storage and ESXi handoff."),
    scenario,
    status: validation?.overall_status ?? "not_checked",
    summary: netappShared
      ? `${protocol.toUpperCase()} is the active shared-storage protocol; alternate protocol checks stay separated from the handoff path.`
      : "Single-server/local-storage validation keeps NetApp and vCenter out of the required path."
  };
}

function LabResetRebuildPanel({
  actions,
  onReload
}: {
  actions: WorkflowAction[];
  onReload: () => Promise<void> | void;
}) {
  const [recoveredActions, setRecoveredActions] = useState<WorkflowAction[]>([]);
  const effectiveActions = actions.length ? actions : recoveredActions.length ? recoveredActions : resetRebuildFallbackActions();
  const byId = useMemo(() => new Map(effectiveActions.map((action) => [action.action_id, action])), [effectiveActions]);
  const inventory = resetRebuildInventory(byId);

  useEffect(() => {
    if (actions.length || recoveredActions.length) return;
    let ignore = false;
    void api.workflowActions()
      .then((nextActions) => {
        if (!ignore) {
          setRecoveredActions(Array.isArray(nextActions) ? nextActions : []);
        }
      })
      .catch(() => {
        if (!ignore) {
          setRecoveredActions([]);
        }
      });
    return () => {
      ignore = true;
    };
  }, [actions.length, recoveredActions.length]);

  return (
    <section className="operator-section reset-rebuild-panel" id="factory-reset-rebuild" aria-label="Factory Reset and Rebuild">
      <div className="operator-section-head">
        <div>
          <p className="operator-kicker danger">Factory reset danger zone</p>
          <h2>Start from scratch</h2>
          <p>These actions can delete ESXi-OS and the 3.27 TiB VM-Datastore once a real executor exists.</p>
        </div>
        <StatusBadge label="Guarded" status="needs-attention" />
      </div>
      <div className="reset-rebuild-steps" aria-label="Reset rebuild sequence">
        <article>
          <ShieldCheck size={20} />
          <span>1</span>
          <strong>Plan</strong>
          <p>Full lab build plan and golden-state drift review.</p>
        </article>
        <article>
          <HardDrive size={20} />
          <span>2</span>
          <strong>Reset</strong>
          <p>Device reset actions remain blocked behind guarded confirmations.</p>
        </article>
        <article>
          <CheckCircle2 size={20} />
          <span>3</span>
          <strong>Validate</strong>
          <p>Full lab validation and handoff evidence after rebuild.</p>
        </article>
      </div>
      <div className="reset-rebuild-inventory">
        <div className="operator-section-head">
          <div>
            <p className="operator-kicker">Stage inventory</p>
            <h2>Real run readiness</h2>
          </div>
          <StatusBadge label="Connected consoles" status="safe-to-run" />
        </div>
        <CompactTable className="reset-rebuild-table">
          <CompactTableHeader>
            <CompactTableCell>Stage</CompactTableCell>
            <CompactTableCell>Automation</CompactTableCell>
            <CompactTableCell>Classification</CompactTableCell>
            <CompactTableCell>Restore partner</CompactTableCell>
            <CompactTableCell>Execution</CompactTableCell>
            <CompactTableCell>Gate</CompactTableCell>
          </CompactTableHeader>
          <tbody>
            {inventory.map((item) => (
              <CompactTableRow key={item.stage}>
                <CompactTableCell>
                  <strong>{item.stage}</strong>
                  <span>{item.detail}</span>
                </CompactTableCell>
                <CompactTableCell>{item.actionLabel}</CompactTableCell>
                <CompactTableCell>
                  <StatusBadge label={item.classification} status={item.status} />
                </CompactTableCell>
                <CompactTableCell>
                  <strong>{item.restoreLabel}</strong>
                  <span>{item.restoreDetail}</span>
                </CompactTableCell>
                <CompactTableCell>
                  <StatusBadge label={item.execution} status={item.executionStatus} />
                </CompactTableCell>
                <CompactTableCell>{item.gate}</CompactTableCell>
              </CompactTableRow>
            ))}
          </tbody>
        </CompactTable>
      </div>
      <AdditionalTabActions
        actions={effectiveActions}
        buttons={[
          { actionIds: ["full-lab.build-plan"], icon: <Wrench size={16} />, label: "Run Full Lab Build Plan", primary: true },
          { actionIds: ["full-lab.repair"], icon: <RefreshCw size={16} />, label: "Run Golden-State Repair Plan" },
          { actionIds: ["full-lab.validation"], icon: <CheckCircle2 size={16} />, label: "Run Full Lab Validation" }
        ]}
        defaultOpen
        description="Read-only automation for rebuilding from a known plan."
        onReload={onReload}
        title="Plan and verify"
      />
      <AdditionalTabActions
        actions={effectiveActions}
        buttons={[
          { actionIds: ["netapp.factory-reset-preview"], icon: <ShieldCheck size={16} />, kind: "read", label: "Preview NetApp Factory Reset" },
          { actionIds: ["netapp.factory-reset-apply"], icon: <Ban size={16} />, kind: "apply", label: "Apply NetApp Factory Reset" },
          { icon: <ShieldCheck size={16} />, kind: "custom", label: "Preview HPE RAID Factory Reset", onClick: async () => { await api.hpeRaidFactoryResetPreview(); } },
          { actionIds: ["raid.factory-reset-apply"], icon: <Ban size={16} />, kind: "apply", label: "Reset HPE RAID" },
          { actionIds: ["raid.reset-commit"], icon: <RefreshCw size={16} />, kind: "apply", label: "Power Commit HPE RAID" },
          { actionIds: ["esxi.rebuild-install"], icon: <Ban size={16} />, kind: "apply", label: "Rebuild ESXi Host" },
          { actionIds: ["ilo.reset-server"], icon: <Ban size={16} />, kind: "apply", label: "Reset Server Power" },
          { actionIds: ["netapp.factory-reset-validate"], icon: <CheckCircle2 size={16} />, kind: "read", label: "Validate NetApp Factory Reset" }
        ]}
        defaultOpen
        description="Guarded controls stay here, separated from daily readiness. HPE RAID apply currently refuses until the delete/recreate executor is proven."
        onReload={onReload}
        title="Device reset controls"
      />
    </section>
  );
}

function resetRebuildFallbackActions(): WorkflowAction[] {
  return [
    resetRebuildFallbackAction("full-lab.build-plan", "Build Plan", "reports", "report", "read_only", true),
    resetRebuildFallbackAction("full-lab.repair", "Golden-State Repair Plan", "reports", "plan", "read_only", true),
    resetRebuildFallbackAction("full-lab.validation", "Full Lab Validation", "reports", "verify", "read_only", true),
    resetRebuildFallbackAction("cisco.discover-console", "Console Discovery", "network", "discover", "read_only", true),
    resetRebuildFallbackAction("firmware.compliance-check", "Firmware Compliance Check", "firmware", "verify", "read_only", true),
    resetRebuildFallbackAction("netapp.factory-reset-preview", "Preview Factory Reset", "storage", "plan", "read_only", true),
    resetRebuildFallbackAction("netapp.factory-reset-apply", "Apply Factory Reset", "storage", "reset", "destructive", false, true),
    resetRebuildFallbackAction("raid.factory-reset-preview", "Preview RAID Factory Reset", "raid", "plan", "read_only", true),
    resetRebuildFallbackAction("raid.factory-reset-apply", "Apply RAID Factory Reset", "raid", "reset", "destructive", false, true),
    resetRebuildFallbackAction("raid.reset-commit", "Reset / Commit", "raid", "reset", "destructive", false, true),
    resetRebuildFallbackAction("raid.apply", "Apply RAID", "raid", "apply", "destructive", false, true),
    resetRebuildFallbackAction("raid.validate", "Validate RAID", "raid", "verify", "read_only", true),
    resetRebuildFallbackAction("esxi.rebuild-install", "Rebuild ESXi Host", "virtualization", "reset", "destructive", false, true),
    resetRebuildFallbackAction("esxi.management-validation", "ESXi Management Validation", "virtualization", "verify", "read_only", true),
    resetRebuildFallbackAction("ilo.reset-server", "Reset Server", "server", "reset", "destructive", false, true),
    resetRebuildFallbackAction("netapp.setup-apply", "Apply NetApp Setup", "storage", "apply", "write", false, true),
    resetRebuildFallbackAction("netapp.factory-reset-validate", "Validate Factory Reset", "storage", "verify", "read_only", true)
  ];
}

function resetRebuildFallbackAction(
  actionId: string,
  label: string,
  stage: string,
  category: WorkflowAction["category"],
  mode: WorkflowAction["mode"],
  uiRunSupported: boolean,
  guardedRunSupported = false
): WorkflowAction {
  const apiEndpoint = `/api/v1/workflows/actions/${actionId}/run`;
  return {
    action_id: actionId,
    label,
    stage,
    stage_label: labelize(stage),
    provider: stage,
    category,
    mode,
    description: "Local reset/rebuild fallback metadata while the full workflow registry loads.",
    source_type: "api_endpoint",
    command: null,
    api_endpoint: apiEndpoint,
    api_method: "POST",
    required_mode: mode === "read_only" ? "local-readonly or local-lab-readwrite" : "local-lab-readwrite",
    required_gates: [],
    required_confirmations: [],
    required_credentials: [],
    safety_notes: [],
    inputs: [],
    outputs: [],
    reports: [],
    last_run_report: null,
    last_run_status: "not_checked",
    current_availability: uiRunSupported ? "available" : "manual_command_required",
    blockers: [],
    next_action: uiRunSupported ? "Run from the page." : "Use the guarded workflow confirmation.",
    evidence_artifacts: [],
    stale_after_seconds: 300,
    last_run_trace: {
      action_id: actionId,
      blockers: [],
      command: null,
      finished_at: null,
      freshness: "not_checked",
      next_action: "Run the action for current evidence.",
      report_artifacts: [],
      run_id: `${actionId}:fallback`,
      source_type: "not_checked",
      stage_id: stage,
      started_at: null,
      status: "not_checked",
      summary: "Fallback metadata only.",
      warnings: []
    },
    ui_run_supported: uiRunSupported,
    ui_run_blockers: uiRunSupported ? [] : ["Needs guarded confirmation before changes are allowed."],
    guarded_run_supported: guardedRunSupported,
    guarded_run_blockers: guardedRunSupported ? [] : ["This action is not a guarded write, destructive, or upgrade action."],
    run_endpoint: apiEndpoint,
    runs_endpoint: `/api/v1/workflows/actions/${actionId}/runs`
  };
}

type ResetRebuildInventoryRow = {
  actionLabel: string;
  classification: string;
  detail: string;
  execution: string;
  executionStatus: StatusBadgeStatus;
  gate: string;
  restoreDetail: string;
  restoreLabel: string;
  stage: string;
  status: StatusBadgeStatus;
};

function resetRebuildInventory(byId: Map<string, WorkflowAction>): ResetRebuildInventoryRow[] {
  return [
    resetRebuildInventoryRow(
      byId,
      "Build plan",
      "full-lab.build-plan",
      "Report-only rebuild baseline before any reset.",
      null,
      "Read-only workflow runner"
    ),
    resetRebuildInventoryRow(
      byId,
      "Console discovery",
      "cisco.discover-console",
      "Cisco and NetApp consoles are physically connected; discovery should be live-testable.",
      null,
      "Connected console cables"
    ),
    resetRebuildInventoryRow(
      byId,
      "Firmware gate",
      "firmware.compliance-check",
      "Compliance check blocks unsafe rebuild stages before reset.",
      null,
      "Read-only compliance result"
    ),
    resetRebuildInventoryRow(
      byId,
      "NetApp reset preview",
      "netapp.factory-reset-preview",
      "Factory reset plan and warnings before ONTAP wipe.",
      "netapp.setup-apply",
      "Preview only"
    ),
    resetRebuildInventoryRow(
      byId,
      "NetApp factory reset",
      "netapp.factory-reset-apply",
      "Destructive ONTAP factory reset stays behind explicit gates.",
      "netapp.setup-apply",
      "Guarded confirmation"
    ),
    resetRebuildInventoryRow(
      byId,
      "HPE RAID reset preview",
      "raid.factory-reset-preview",
      "Preview logical drives to delete and the recreate payload before any Smart Array wipe.",
      "raid.apply",
      "Preview only"
    ),
    resetRebuildInventoryRow(
      byId,
      "HPE RAID factory reset",
      "raid.factory-reset-apply",
      "Guarded delete/recreate lane; currently refuses until the HPE delete executor is proven.",
      "raid.apply",
      "Guarded confirmation"
    ),
    resetRebuildInventoryRow(
      byId,
      "HPE RAID power commit",
      "raid.reset-commit",
      "Power on or restart the server to commit already-staged SmartStorage settings; not a delete primitive.",
      "raid.validate",
      "Guarded power action"
    ),
    resetRebuildInventoryRow(
      byId,
      "ESXi rebuild",
      "esxi.rebuild-install",
      "Installer boot and host rebuild require power action gates.",
      "esxi.management-validation",
      "Guarded confirmation"
    ),
    resetRebuildInventoryRow(
      byId,
      "Post-build validation",
      "full-lab.validation",
      "Full validation and handoff evidence after the rebuild.",
      null,
      "Read-only validation"
    )
  ];
}

function resetRebuildInventoryRow(
  byId: Map<string, WorkflowAction>,
  stage: string,
  actionId: string,
  detail: string,
  restoreActionId: string | null,
  gate: string
): ResetRebuildInventoryRow {
  const action = byId.get(actionId);
  const restoreAction = restoreActionId ? byId.get(restoreActionId) : null;
  const execution = action ? resetRebuildExecutionLabel(action) : "Unknown";
  const restoreLabel = restoreActionId ? restoreAction?.label || restoreActionId : "Not destructive";
  const restoreDetail = restoreActionId
    ? restoreAction
      ? "Configure-back action is registered."
      : "Configure-back action still needs a registry entry."
    : "No restore partner required.";
  if (!action) {
    return {
      actionLabel: actionId,
      classification: "Missing",
      detail,
      execution,
      executionStatus: "not-configured",
      gate: "Registry entry required",
      restoreDetail,
      restoreLabel,
      stage,
      status: "not-configured"
    };
  }
  const guarded = isChangingAction(action) || !action.ui_run_supported || action.guarded_run_supported;
  return {
    actionLabel: action.label || actionId,
    classification: guarded ? "Guarded real run" : "Real read-only",
    detail,
    execution,
    executionStatus: execution === "In-process API" ? "safe-to-run" : "needs-attention",
    gate: guarded ? gate : "Safe from UI",
    restoreDetail,
    restoreLabel,
    stage,
    status: guarded ? "needs-attention" : "safe-to-run"
  };
}

function resetRebuildExecutionLabel(action: WorkflowAction): string {
  if (action.source_type === "api_endpoint" && action.api_endpoint) {
    return "In-process API";
  }
  if (action.source_type === "make_target" || action.command) {
    return "Make/subprocess";
  }
  return "Unknown";
}

export function SettingsGlobalProfilePanel({
  activeProfile,
  onSaved
}: {
  activeProfile: LabProfile | null;
  onSaved: () => Promise<void>;
}) {
  const [edit, setEdit] = useState<SettingsProfileEditState>(() => settingsProfileEditStateFrom(activeProfile));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const profileKey = `${activeProfile?.id ?? "none"}:${activeProfile?.version ?? 0}:${activeProfile?.source ?? "missing"}`;

  useEffect(() => {
    setEdit(settingsProfileEditStateFrom(activeProfile));
    setError("");
    setMessage("");
  }, [profileKey, activeProfile]);

  function update<K extends keyof SettingsProfileEditState>(key: K, value: SettingsProfileEditState[K]) {
    setEdit((current) => ({ ...current, [key]: value }));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!activeProfile) {
      setError("Load the active lab setup before editing lab defaults.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const payload = settingsProfilePayload(activeProfile, edit);
      if (activeProfile.source === "saved") {
        await api.updateLabProfile(activeProfile.id, payload);
      } else {
        const saved = await api.createLabProfile(payload);
        await api.activateLabProfile(saved.id);
      }
      await onSaved();
      setMessage("Lab defaults saved.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="network-config-panel settings-global-profile-panel" hover={false}>
      <CardHeader>
        <div>
          <p className="operator-kicker">Lab defaults</p>
          <h2>Shared lab policy</h2>
        </div>
        <StatusBadge
          label={activeProfile?.source === "saved" ? "Saved setup" : activeProfile ? "Save as setup" : "No setup"}
          status={activeProfile ? "ready" : "not-configured"}
        />
      </CardHeader>
      <CardContent>
        <form className="network-config-form" onSubmit={save}>
          <Field label="Setup name">
            <input
              disabled={busy || !activeProfile}
              onChange={(event) => update("name", event.target.value)}
              value={edit.name}
            />
          </Field>
          <Field label="Description">
            <input
              disabled={busy || !activeProfile}
              onChange={(event) => update("description", event.target.value)}
              value={edit.description}
            />
          </Field>
          <Field label="Domain">
            <input
              disabled={busy || !activeProfile}
              onChange={(event) => update("domainName", event.target.value)}
              value={edit.domainName}
            />
          </Field>
          <Field label="Timezone">
            <input
              disabled={busy || !activeProfile}
              onChange={(event) => update("timezone", event.target.value)}
              value={edit.timezone}
            />
          </Field>
          <Field label="Storage protocol">
            <select
              disabled={busy || !activeProfile}
              onChange={(event) => update("storageProtocol", event.target.value)}
              value={edit.storageProtocol}
            >
              <option value="nfs">NFS</option>
              <option value="iscsi">iSCSI</option>
              <option value="none">Local only</option>
            </select>
          </Field>
          <div className="network-config-toggles" aria-label="Lab default feature toggles">
            <label>
              <input
                checked={edit.enableDns}
                disabled={busy || !activeProfile}
                onChange={(event) => update("enableDns", event.target.checked)}
                type="checkbox"
              />
              <span>DNS</span>
            </label>
            <label>
              <input
                checked={edit.enableNtp}
                disabled={busy || !activeProfile}
                onChange={(event) => update("enableNtp", event.target.checked)}
                type="checkbox"
              />
              <span>NTP</span>
            </label>
            <label>
              <input
                checked={edit.enableSnmp}
                disabled={busy || !activeProfile}
                onChange={(event) => update("enableSnmp", event.target.checked)}
                type="checkbox"
              />
              <span>SNMP</span>
            </label>
            <label>
              <input
                checked={!edit.disableIpv6}
                disabled={busy || !activeProfile}
                onChange={(event) => update("disableIpv6", !event.target.checked)}
                type="checkbox"
              />
              <span>Allow IPv6</span>
            </label>
            <label>
              <input
                checked={edit.blockLegacyProtocols}
                disabled={busy || !activeProfile}
                onChange={(event) => update("blockLegacyProtocols", event.target.checked)}
                type="checkbox"
              />
              <span>Block legacy protocols</span>
            </label>
            <label>
              <input
                checked={edit.enableVcenter}
                disabled={busy || !activeProfile}
                onChange={(event) => update("enableVcenter", event.target.checked)}
                type="checkbox"
              />
              <span>vCenter in scope</span>
            </label>
          </div>
          {(message || error) && <div className={error ? "operator-feedback error" : "operator-feedback"}>{error || message}</div>}
          <div className="network-config-actions">
            <button className="operator-primary-button" disabled={busy || !activeProfile} type="submit">
              <Save size={16} />
              {busy ? "Saving..." : activeProfile?.source === "saved" ? "Save defaults" : "Save As Lab Setup"}
            </button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function OperatorPage({ children, title }: { children: ReactNode; title: string }) {
  return (
    <div className="operator-page" data-page-title={title}>
      {children}
    </div>
  );
}

function PageStatusHeader({
  description,
  helper,
  icon,
  nextAction,
  runConfig,
  status,
  tabId,
  title
}: {
  description: string;
  helper: string;
  icon: ReactNode;
  nextAction?: string;
  runConfig: TabRunConfig;
  status?: string;
  tabId: OperatorTabId;
  title: string;
}) {
  const { runStatus, setRunStatus } = useOperatorTabState();
  const [diagnosis, setDiagnosis] = useState<WorkflowActionDiagnosis | null>(null);
  const [diagnosisLoading, setDiagnosisLoading] = useState(false);
  const byId = useMemo(() => new Map((runConfig.actions ?? []).map((action) => [action.action_id, action])), [runConfig.actions]);
  const action = firstRunnableAction(byId, runConfig.actionIds ?? [], runConfig);
  const fallbackActionId = fallbackRunActionId(runConfig, action);
  const disabledReason = runConfig.disabledReason || (runConfig.onRun || fallbackActionId ? "" : disabledReasonForRunConfig(runConfig, action));
  const tabRunStatus = runStatus[tabId] ?? idleRunStatus;
  const running = tabRunStatus.state === "running";

  async function runActiveTab() {
    if (disabledReason || running) return;
    setDiagnosis(null);
    setRunStatus(tabId, {
      actionId: action?.action_id ?? fallbackActionId,
      message: `${runConfig.label} is running.`,
      state: "running"
    });
    try {
      let message = "";
      if (runConfig.onRun) {
        message = await runConfig.onRun();
      } else if (action) {
        const result = await api.runWorkflowAction(action.action_id);
        message = workflowRunMessage(action, result);
        if (isProblemRun(result)) {
          await loadHeaderDiagnosis(action.action_id);
        }
      } else if (fallbackActionId) {
        const result = await api.runWorkflowAction(fallbackActionId);
        message = workflowRunResultMessage(runConfig.label, result);
        if (isProblemRun(result)) {
          await loadHeaderDiagnosis(fallbackActionId);
        }
      } else {
        throw new Error("PageStatusHeader runConfig requires onRun or actionIds.");
      }
      if (runConfig.onReload) {
        await runConfig.onReload();
      }
      setRunStatus(tabId, {
        actionId: action?.action_id ?? fallbackActionId,
        message: message || `${runConfig.label} completed.`,
        state: "success"
      });
    } catch (err) {
      setRunStatus(tabId, {
        actionId: action?.action_id ?? fallbackActionId,
        message: errorMessage(err),
        state: "error"
      });
    }
  }

  async function loadHeaderDiagnosis(actionId: string) {
    setDiagnosisLoading(true);
    try {
      setDiagnosis(await api.workflowActionDiagnosis(actionId));
    } catch {
      setDiagnosis(null);
    } finally {
      setDiagnosisLoading(false);
    }
  }

  return (
    <>
      <header className="operator-status-header">
        <div className="operator-status-icon">{icon}</div>
        <div className="operator-status-main">
          <p className="operator-kicker">Infra Config</p>
          <h1>{title}</h1>
          <p>{description}</p>
          <span>{helper}</span>
        </div>
        <div className="operator-status-side">
          {status && <SimpleStatusPill status={status} />}
          {nextAction && (
            <div>
              <span>Next action</span>
              <strong>{nextAction}</strong>
            </div>
          )}
          <div className="operator-header-actions">
            <button
              className="primary"
              disabled={Boolean(disabledReason) || running}
              onClick={() => void runActiveTab()}
              title={disabledReason || `Run ${runConfig.label}`}
              type="button"
            >
              <Play size={16} />
              {running ? "Running" : `Run ${runConfig.label}`}
            </button>
          </div>
          {disabledReason && <p className="operator-run-hint">{disabledReason}</p>}
        </div>
      </header>
      {tabRunStatus.message && (
        <p className={`operator-action-message ${tabRunStatus.state === "error" ? "error" : tabRunStatus.state}`}>
          {tabRunStatus.message}
        </p>
      )}
      {diagnosisLoading && <p className="operator-action-message">Preparing advisory diagnosis...</p>}
      {diagnosis && <WorkflowDiagnosisCard diagnosis={diagnosis} />}
    </>
  );
}

function OperatorWorkspace({
  compact = false,
  currentView,
  emptyDetail,
  renderDetailExtra,
  rows
}: {
  compact?: boolean;
  currentView: CurrentViewModel;
  emptyDetail?: string;
  renderDetailExtra?: (row: OperatorObjectRow) => ReactNode;
  rows: OperatorObjectRow[];
}) {
  const [selectedId, setSelectedId] = useState(rows[0]?.id ?? "");
  const selected = rows.find((row) => row.id === selectedId) ?? rows[0] ?? null;

  useEffect(() => {
    if (!rows.some((row) => row.id === selectedId)) {
      setSelectedId(rows[0]?.id ?? "");
    }
  }, [rows, selectedId]);

  const counts = workspaceCounts(rows);

  return (
    <Card aria-label="Current view" className={compact ? "operator-console compact" : "operator-console"} hover={false}>
      <div className="operator-console-head">
        <div>
          <p className="operator-kicker">Current View</p>
          <h2>Current state and targets</h2>
          <p>{currentView.summary}</p>
        </div>
        <SimpleStatusPill status={currentView.status} />
      </div>
      <div className="domain-summary-strip" aria-label="Domain summary">
        <SummaryMetric label="Ready" status="ready" value={String(counts.ready)} />
        <SummaryMetric label="Needs review" status="warning" value={String(counts.warning)} />
        <SummaryMetric label="Blocked" status="blocked" value={String(counts.blocked)} />
        <SummaryMetric label="Not checked" status="not_checked" value={String(counts.neutral)} />
        <SummaryMetric label="Source" value={currentView.source} />
        <SummaryMetric label="Freshness" status={freshnessStatus(currentView.freshness)} value={currentView.freshness} />
        <SummaryMetric label="Checked" value={currentView.checkedAt} />
      </div>
      <div className="operator-workspace-grid">
        <div className="operator-object-list" aria-label="Objects">
          <div className="operator-object-list-head">
            <span>Object inventory</span>
            <strong>{rows.filter((row) => statusTone(row.status) === "ready").length} of {rows.length} objects ready</strong>
          </div>
          {rows.map((row) => (
            <button
              aria-pressed={selected?.id === row.id}
              className={selected?.id === row.id ? "operator-object-row selected" : "operator-object-row"}
              key={row.id}
              onClick={() => setSelectedId(row.id)}
              type="button"
            >
              <span>
                <strong>{row.title}</strong>
                <small>{row.type}</small>
              </span>
              <span>
                <strong>{row.target}</strong>
                <small>{row.source || currentView.source}</small>
              </span>
              <SimpleStatusPill status={row.status} />
            </button>
          ))}
        </div>
        <article className="operator-detail-pane" aria-label="Selected object detail">
          {selected ? (
            <>
              <div className="operator-detail-head">
                <div>
                  <p className="operator-kicker">{selected.type}</p>
                  <h2>{selected.title}</h2>
                  <p>{selected.summary}</p>
                </div>
                <SimpleStatusPill status={selected.status} />
              </div>
              <div className="operator-detail-action">
                <span>Next action</span>
                <strong>{selected.nextAction}</strong>
              </div>
              <ConfigValueList
                values={[
                  { label: "Target", value: selected.target },
                  { label: "Source", value: selected.source || currentView.source },
                  { label: "Freshness", value: selected.freshness || currentView.freshness, status: freshnessStatus(selected.freshness || currentView.freshness) },
                  { label: "Checked", value: selected.checkedAt || currentView.checkedAt },
                  ...selected.details
                ]}
              />
              <IssueList blockers={selected.blockers ?? []} warnings={selected.warnings ?? []} />
              {renderDetailExtra?.(selected)}
            </>
          ) : (
            <p className="operator-muted">{emptyDetail ?? "No objects are available yet."}</p>
          )}
        </article>
      </div>
      {currentView.recheckCommand && (
        <div className="operator-recheck-strip">
          <span>Recheck</span>
          <code>{currentView.recheckCommand}</code>
        </div>
      )}
    </Card>
  );
}

function OperatorReferencePanel({
  actionLabel,
  actionTo,
  ariaLabel,
  currentView,
  rows,
  subtitle,
  tableTitle,
  title
}: {
  actionLabel?: string;
  actionTo?: string;
  ariaLabel: string;
  currentView: CurrentViewModel;
  rows: OperatorObjectRow[];
  subtitle: string;
  tableTitle: string;
  title: string;
}) {
  const counts = workspaceCounts(rows);
  const visibleRows = rows.slice(0, 3);
  const issues = operatorReferenceIssues(currentView, rows);
  const blockerIssueCount = issues.filter((issue) => issue.severity === "critical").length;
  const warningIssueCount = issues.filter((issue) => issue.severity === "warning").length;
  const safeActions = operatorReferenceActions(currentView, rows);

  return (
    <section className="overview-reference" aria-label={ariaLabel}>
      <div className="overview-reference-head">
        <div>
          <p className="operator-kicker">Operator console</p>
          <h2>{title}</h2>
        </div>
        <StatusBadge label="Redesigned view" status="safe-to-run" />
      </div>

      <div className="overview-stat-grid" aria-label={`${title} summary`}>
        <OverviewStatCard
          label="Current status"
          meta={currentView.source}
          status={statusBadgeStatus(currentView.status)}
          value={displayStatus(currentView.status)}
        />
        <OverviewStatCard
          label="Ready objects"
          meta={`${counts.warning + counts.blocked} need review`}
          status={counts.blocked ? "blocked" : counts.warning ? "needs-attention" : counts.ready ? "ready" : "not-configured"}
          value={`${counts.ready}/${rows.length}`}
        />
        <OverviewStatCard
          label="Active blockers"
          meta={`${currentView.warnings.length} warnings`}
          status={currentView.blockers.length ? "blocked" : currentView.warnings.length ? "needs-attention" : "ready"}
          value={String(currentView.blockers.length)}
        />
        <OverviewStatCard
          label="Last checked"
          meta={currentView.freshness}
          status={freshnessStatus(currentView.freshness) === "ready" ? "ready" : "plan-only"}
          value={currentView.checkedAt}
        />
      </div>

      <div className="overview-panel-head">
        <div>
          <p className="operator-kicker">{subtitle}</p>
          <h2>Current state and targets</h2>
        </div>
        <StatusBadge label={`${rows.length} tracked`} status="plan-only" />
      </div>
      <div className="overview-provider-grid">
        {visibleRows.map((row) => (
          <Card className="overview-provider-card" key={row.id}>
            <CardHeader>
              <div>
                <p className="operator-kicker">{row.type}</p>
                <h3>{row.title}</h3>
              </div>
              <StatusBadge label={displayStatus(row.status)} status={statusBadgeStatus(row.status)} />
            </CardHeader>
            <CardContent>
              <dl className="overview-fact-list">
                {operatorReferenceFacts(row, currentView).map((fact) => (
                  <div key={`${row.id}-${fact.label}`}>
                    <dt>{fact.label}</dt>
                    <dd>{fact.value}</dd>
                  </div>
                ))}
              </dl>
              <div className="overview-current-state-box">
                <p><strong>Current State:</strong> {row.summary}</p>
                <p><strong>Target:</strong> {row.target}</p>
                <p><strong>Gap:</strong> {row.nextAction}</p>
                <p><strong>{operatorReferenceIssueLine(row, currentView).label}:</strong> {operatorReferenceIssueLine(row, currentView).message}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <section className="overview-safe-actions" aria-label="Next safe actions">
        <p className="operator-kicker">Next safe actions</p>
        <ul>
          {safeActions.map((action) => (
            <li key={action}>{action}</li>
          ))}
        </ul>
        {actionLabel && actionTo && <ActionLink to={actionTo}>{actionLabel}</ActionLink>}
      </section>

      <div className="overview-bottom-grid">
        <Card className="overview-firmware-panel" hover={false}>
          <CardHeader>
            <div>
              <h2>{tableTitle}</h2>
            </div>
            <span>{rows.length} tracked</span>
          </CardHeader>
          <CompactTable>
            <CompactTableHeader>
              <CompactTableCell>Object</CompactTableCell>
              <CompactTableCell>Current</CompactTableCell>
              <CompactTableCell>Target</CompactTableCell>
              <CompactTableCell>Status</CompactTableCell>
            </CompactTableHeader>
            <tbody>
              {rows.map((row) => (
                <CompactTableRow key={row.id}>
                  <CompactTableCell><strong>{row.title}</strong></CompactTableCell>
                  <CompactTableCell>{row.summary}</CompactTableCell>
                  <CompactTableCell>{row.target}</CompactTableCell>
                  <CompactTableCell><StatusBadge label={displayStatus(row.status)} status={statusBadgeStatus(row.status)} /></CompactTableCell>
                </CompactTableRow>
              ))}
            </tbody>
          </CompactTable>
        </Card>

        <Card className="overview-blockers-panel" hover={false}>
          <CardHeader>
            <div>
              <h2>Active Blockers</h2>
            </div>
            <span>{blockerIssueCount} blockers · {warningIssueCount} warnings</span>
          </CardHeader>
          <CardContent>
            <div className="overview-blocker-list">
              {issues.length ? (
                issues.slice(0, 4).map((issue) => (
                  <BlockerItem
                    code={issue.code}
                    key={`${issue.code}-${issue.message}`}
                    message={issue.message}
                    severity={issue.severity}
                  />
                ))
              ) : (
                <div className="overview-clear-state">
                  <StatusBadge status="ready" />
                  <span>No active blockers are loaded for the current view.</span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}

type TopologyNodeTone = "ready" | "warning" | "offline" | "unknown" | "created";

type TopologyNode = {
  details: string;
  icon: ReactNode;
  id: string;
  meta?: string;
  page: string;
  status: string;
  title: string;
  tone: TopologyNodeTone;
  zone: "management" | "storage";
};

type TopologyLink = {
  from: string;
  id: string;
  label: string;
  labelX: number;
  labelY: number;
  path: string;
  status: "ready" | "warning" | "created" | "unknown";
  to: string;
};

type TopologySubnetState = {
  detail: string;
  label: string;
  status: "matches" | "mismatch" | "unknown";
};

type TopologyDesignScenario = "server_netapp_vcenter" | "server_netapp_direct" | "single_server_local_storage";

type DesignPartId = "switch" | "ilo" | "server-gen10" | "server-gen10plus" | "netapp" | "vcenter" | "windows";

type RackSlotId = "u1" | "u2" | "u3" | "u4" | "virtual";
type DesignLaneId = "management" | "storage" | "virtualization";
type DesignConnectionId = "switch-server" | "switch-netapp" | "server-netapp" | "server-vm";

type DesignPart = {
  id: DesignPartId;
  label: string;
  meta: string;
  rackUnits: string;
  state: "placed" | "available" | "draft" | "soon";
};

type DeviceSettings = Record<DesignPartId, Record<string, string>>;
type LaneSettings = Record<DesignLaneId, Record<string, string>>;
type ConnectionSettings = Record<DesignConnectionId, Record<string, string>>;

type RackSlot = {
  id: RackSlotId;
  label: string;
  note: string;
};

function LabTopologyMap({
  accessRows,
  activeProfile,
  address,
  features,
  firmwareSummaries,
  health,
  onReload,
  vcenterNetapp,
  workflowActions
}: {
  accessRows: AccessRow[];
  activeProfile: LabProfile | null;
  address: LabAddressPlan;
  features: LabProfileFeatures | null;
  firmwareSummaries: FirmwareSummary[];
  health?: HealthLike;
  onReload: () => Promise<void> | void;
  vcenterNetapp: ProviderProbeResult | null;
  workflowActions: WorkflowAction[];
}) {
  const netappInScope = features?.netapp_enabled !== false;
  const vcenterInScope = features?.vcenter_enabled === true;
  const vmInScope = vcenterInScope || netappInScope;
  const runtimeReady = Boolean(health);
  const realRuntime = health?.operator_runtime_mode === "real_lab" || health?.provider_mode === "local-lab-readwrite";
  const runtimeLabel = runtimeReady
    ? (realRuntime ? "Live lab - read-only checks" : "Test mode - no hardware touched")
    : "Checking status";
  const runtimeClass = runtimeReady ? (realRuntime ? "topology-pill-live" : "topology-pill-test") : "topology-pill-runtime-unknown";
  const subnetState = topologySubnetState(address.subnet, health);
  const [workspaceTarget, setWorkspaceTarget] = useState<DesignPartId>("switch");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [mapFitEnabled, setMapFitEnabled] = useState(false);
  const [mapOverflowing, setMapOverflowing] = useState(false);
  const mapCanvasRef = useRef<HTMLDivElement | null>(null);
  const mapPlaneRef = useRef<HTMLDivElement | null>(null);
  const ciscoStatus = topologyStatusFromAccess(accessRows, "Cisco");
  const iloStatus = topologyStatusFromAccess(accessRows, "iLO");
  const esxiStatus = topologyStatusFromAccess(accessRows, "ESXi");
  const netappStatus = topologyStatusFromAccess(accessRows, "NetApp");
  const datastoreStatus = topologyStatusFromAccess(accessRows, "Datastore");
  const vmStatus = topologyStatusFromAccess(accessRows, "VM inventory");
  const serverStatus = topologyWorstStatus([iloStatus, esxiStatus]);
  const storageProtocol = asString(features?.storage_protocol) || (netappInScope ? "nfs" : "local");
  const datastoreLabel = netappInScope ? datastoreName(vcenterNetapp) : "Local ESXi datastore";
  const serverModelLabel = topologyServerModelLabel(activeProfile?.devices?.server_model);
  const nodes: TopologyNode[] = [
    {
      details: "C9300 - L3 core",
      icon: topologyIndustryIcon("switch"),
      id: "cisco",
      meta: displayAddress(address.cisco_management),
      page: "/overview#topology-map",
      status: ciscoStatus,
      title: "Cisco Switch",
      tone: topologyTone(ciscoStatus),
      zone: "management"
    },
    {
      details: "iLO 5 - server management",
      icon: topologyIndustryIcon("ilo"),
      id: "ilo",
      meta: displayAddress(address.ilo),
      page: "/overview#topology-map",
      status: iloStatus,
      title: "HPE iLO",
      tone: topologyTone(iloStatus),
      zone: "management"
    },
    {
      details: `${serverModelLabel} - ${netappInScope ? "ESXi host" : "local RAID host"}`,
      icon: topologyIndustryIcon("server"),
      id: "server",
      meta: displayAddress(address.esxi_management),
      page: "/overview#topology-map",
      status: serverStatus,
      title: `HPE ${serverModelLabel.replace(/^DL360\s+/i, "")}`,
      tone: topologyTone(serverStatus),
      zone: "storage"
    }
  ];

  if (netappInScope) {
    nodes.push(
      {
        details: `ONTAP - ${storageProtocol.toUpperCase()} storage`,
        icon: topologyIndustryIcon("netapp"),
        id: "netapp",
        meta: displayAddress(address.netapp_cluster_mgmt),
        page: "/overview#topology-map",
        status: netappStatus,
        title: "NetApp ONTAP",
        tone: topologyTone(netappStatus),
        zone: "storage"
      },
      {
        details: "VM storage path",
        icon: topologyIndustryIcon("datastore"),
        id: "datastore",
        meta: datastoreVisibleStatus(vcenterNetapp) === "ready" ? "mounted" : "not mounted",
        page: "/overview#topology-map",
        status: datastoreStatus,
        title: "Datastore",
        tone: topologyTone(datastoreStatus),
        zone: "storage"
      }
    );
  }

  if (vmInScope) {
    nodes.push({
      details: vcenterInScope ? "VCSA - VM management" : "ESXi - direct host",
      icon: topologyIndustryIcon(vcenterInScope ? "vcenter" : "hypervisor"),
      id: "vcenter",
      meta: topologyVmMapTarget(vcenterNetapp, vcenterInScope, address),
      page: "/overview#topology-map",
      status: vmStatus,
      title: vcenterInScope ? "vCenter" : "Direct ESXi VM",
      tone: topologyTone(vmStatus, "created"),
      zone: "management"
    });
  }

  const links = topologyLinks({ datastoreStatus, iloStatus, netappInScope, netappStatus, serverStatus, storageProtocol, vmInScope, vmStatus });
  const storageOrbitNodes = nodes.filter((node) => node.zone === "storage");
  useEffect(() => {
    const canvas = mapCanvasRef.current;
    const plane = mapPlaneRef.current;
    if (!canvas || !plane) return;
    const canvasEl = canvas;
    const planeEl = plane;

    function measureOverflow() {
      const canvasBox = canvasEl.getBoundingClientRect();
      const planeBox = planeEl.getBoundingClientRect();
      const overflowing = planeBox.width > canvasBox.width - 36 || planeBox.height > canvasBox.height - 88;
      setMapOverflowing(overflowing);
      if (!overflowing) setMapFitEnabled(false);
    }

    measureOverflow();
    const observer = new ResizeObserver(measureOverflow);
    observer.observe(canvasEl);
    observer.observe(planeEl);
    return () => observer.disconnect();
  }, [links.length, netappInScope, nodes.length, workspaceOpen]);

  function openNodeWorkspace(nodeId: string) {
    setWorkspaceTarget(topologyNodeFaceplatePart(nodeId, netappInScope));
    setSelectedNodeId(nodeId);
    setWorkspaceOpen(true);
  }

  function closeNodeWorkspace() {
    setWorkspaceOpen(false);
    setSelectedNodeId(null);
  }

  return (
    <section className="lab-topology-map" id="topology-map" aria-label="Living lab topology">
      <div className="lab-topology-head">
        <div>
            <p className="operator-kicker">Lab topology</p>
          <h2>{nodes.length} devices - subnet {displayAddress(address.subnet)}</h2>
        </div>
        <div className="lab-topology-head-actions">
          <div className="lab-topology-pills" aria-label="Topology status">
            <span className={`topology-pill ${runtimeClass}`}><CheckCircle2 size={14} /> {runtimeLabel}</span>
            <span className={`topology-pill topology-pill-subnet-${subnetState.status}`}><Route size={14} /> {subnetState.label}</span>
          </div>
        </div>
      </div>

      {subnetState.status !== "matches" && (
        <div className={`topology-subnet-notice topology-subnet-notice-${subnetState.status}`}>
          <div>
            <strong>{subnetState.status === "mismatch" ? "Subnet mismatch" : "Subnet not proven"}</strong>
            <span>{subnetState.detail}</span>
          </div>
          <Link to="/overview#system-setup">Edit system setup</Link>
        </div>
      )}

      <div
        className={`lab-topology-canvas zones-canvas map-first-canvas ${netappInScope ? "has-netapp" : "single-server"} ${mapFitEnabled ? "is-fit" : ""}`}
        aria-label="Zoned lab map"
        data-workspace-open={workspaceOpen ? "true" : undefined}
        ref={mapCanvasRef}
      >
        <div className="topology-map-plane" ref={mapPlaneRef}>
          <div className="topology-zone topology-zone-management topology-zone-band" aria-hidden="true">
            <span>Management network</span>
          </div>
          <div className="topology-zone topology-zone-storage topology-zone-band" aria-hidden="true">
            <span>{netappInScope ? "Storage & compute" : "Local RAID"}</span>
          </div>
          <div className="topology-zone-node-flow topology-orbit-node-flow topology-management-orbit" aria-label="Management zone devices">
            {nodes.filter((node) => node.zone === "management").map((node) => (
                <TopologyMapNodeCard
                  className={`topology-orbit-node topology-orbit-${node.id}`}
                  node={node}
                  onOpenWorkspace={openNodeWorkspace}
                  selected={selectedNodeId === node.id}
                  key={node.id}
                />
              ))}
          </div>
          <div className="topology-zone-node-flow topology-orbit-node-flow topology-storage-orbit" aria-label={netappInScope ? "Storage fabric zone devices" : "Local RAID zone devices"}>
            {storageOrbitNodes.map((node) => (
                <TopologyMapNodeCard
                  className={`topology-orbit-node topology-orbit-${node.id}`}
                  node={node}
                  onOpenWorkspace={openNodeWorkspace}
                  selected={selectedNodeId === node.id}
                  key={node.id}
                />
              ))}
          </div>
        </div>
          {mapOverflowing && (
            <button
              className="topology-map-fit-button"
              onClick={() => setMapFitEnabled((enabled) => !enabled)}
              type="button"
              aria-label={mapFitEnabled ? "Reset map zoom" : "Fit map to viewport"}
            >
              {mapFitEnabled ? "1:1" : "Fit"}
            </button>
          )}
          {!netappInScope && (
            <div className="topology-local-raid-hero" aria-label="Local RAID mode summary">
              <HardDrive size={15} />
              <div>
                <strong>Server-local RAID is the storage fabric</strong>
                <span>No NetApp or vCenter nodes are in this active profile.</span>
              </div>
            </div>
          )}
          <svg className="lab-topology-links" viewBox="0 0 1000 620" role="img" aria-label="Current lab links">
            {links.map((link) => (
              <g className={`topology-link topology-link-${link.status}`} key={link.id}>
                <path d={link.path} id={link.id} />
                <text textAnchor="middle" x={link.labelX} y={link.labelY}>{link.label}</text>
              </g>
            ))}
          </svg>
      </div>

      {workspaceOpen && (
        <div className="topology-workspace-overlay" aria-label="Device workspace overlay">
          <div className="topology-workspace-backdrop" onClick={closeNodeWorkspace} />
          <aside className="topology-workspace-drawer" aria-label="Device workspace drawer">
            <div className="topology-workspace-drawer-head">
              <span>Device setup</span>
              <button className="topology-workspace-close" type="button" onClick={closeNodeWorkspace}>Close</button>
            </div>
            <LabDesignComposer
              activeProfile={activeProfile}
              address={address}
              features={features}
              firmwareSummaries={firmwareSummaries}
              health={health}
              initialSelectedDevice={workspaceTarget}
              onReload={onReload}
              subnetState={subnetState}
              workspaceOnly
              workflowActions={workflowActions}
            />
          </aside>
        </div>
      )}

      <div className="lab-topology-footer">
        <div className="topology-legend" aria-label="Topology legend">
          <span><i className="legend-dot legend-ready" /> Ready</span>
          <span><i className="legend-dot legend-warning" /> Blocked</span>
          <span><i className="legend-dot legend-offline" /> Not checked</span>
        </div>
      </div>
    </section>
  );
}

type CiscoWorkspaceAction = {
  detail: string;
  icon: ReactNode;
  id: string;
  label: string;
  run: () => Promise<WorkflowActionRun | ProviderProbeResult>;
};

function CiscoWorkspaceNetworkControls({
  address,
  firmwareSummaries,
  onReload,
  workflowActions
}: {
  address: LabAddressPlan;
  firmwareSummaries: FirmwareSummary[];
  onReload: () => Promise<void> | void;
  workflowActions: WorkflowAction[];
}) {
  const [runState, setRunState] = useState<WorkflowRunState>(emptyRunState);
  const [setupReadiness, setSetupReadiness] = useState<ProviderProbeResult | null>(null);
  const [sshProbe, setSshProbe] = useState<ProviderProbeResult | null>(null);
  const [intentDiff, setIntentDiff] = useState<ProviderProbeResult | null>(null);
  const [workflowRunsById, setWorkflowRunsById] = useState<Record<string, WorkflowActionRun[]>>({});
  const ciscoFirmware = firmwareVersion(firmwareSummaries, "cisco");
  const byId = useMemo(() => new Map(workflowActions.map((action) => [action.action_id, action])), [workflowActions]);
  const actionIds = [
    "cisco.ssh-readonly-probe",
    "cisco.validate-ssh-scp",
    "cisco.firmware-inventory",
    "cisco.current-intent-diff",
    "cisco.setup-readiness",
    "cisco.privilege-check"
  ];
  const actionKey = actionIds.join("|");

  useEffect(() => {
    let ignore = false;
    safeApi(api.ciscoSetupReadiness, null).then((nextReadiness) => {
      if (!ignore) {
        setSetupReadiness(nextReadiness as ProviderProbeResult | null);
      }
    });
    return () => {
      ignore = true;
    };
  }, [address.cisco_management]);

  useEffect(() => {
    let ignore = false;
    Promise.all(
      actionIds.map(async (actionId) => [actionId, await safeApi(() => api.workflowActionRuns(actionId), [] as WorkflowActionRun[])] as const)
    ).then((entries) => {
      if (!ignore) {
        setWorkflowRunsById(Object.fromEntries(entries));
      }
    });
    return () => {
      ignore = true;
    };
  }, [actionKey]);

  async function runWorkflowCheck(actionId: string): Promise<WorkflowActionRun> {
    const result = await api.runWorkflowAction(actionId);
    setWorkflowRunsById((current) => ({
      ...current,
      [actionId]: [result, ...(current[actionId] ?? [])].slice(0, 5)
    }));
    return result;
  }

  async function runCombinedRefresh(): Promise<ProviderProbeResult> {
    setSshProbe({
      provider_id: "cisco-ansible",
      status: "running",
      message: "Reading live Cisco SSH and current-intent state.",
      checked_at: new Date().toISOString(),
      warnings: [],
      blockers: []
    });
    setIntentDiff({
      provider_id: "cisco-ansible",
      status: "running",
      message: "Reading live Cisco current-to-intent state.",
      checked_at: new Date().toISOString(),
      warnings: [],
      blockers: []
    });
    const [nextSshProbe, nextIntentDiff, nextReadiness] = await Promise.all([
      api.ciscoSshProbe(),
      api.ciscoCurrentIntentDiff(),
      safeApi(api.ciscoSetupReadiness, null)
    ]);
    setSshProbe(nextSshProbe);
    setIntentDiff(nextIntentDiff);
    setSetupReadiness(nextReadiness as ProviderProbeResult | null);
    return nextIntentDiff;
  }

  const actions: CiscoWorkspaceAction[] = [
    {
      detail: "Run the same direct probe + current-to-intent diff refresh used by the Network driver.",
      icon: <RefreshCw size={14} />,
      id: "cisco.refresh-live-evidence",
      label: "Refresh live evidence",
      run: runCombinedRefresh
    },
    {
      detail: "Approved show commands through the workflow runner.",
      icon: <Play size={14} />,
      id: "cisco.ssh-readonly-probe",
      label: byId.get("cisco.ssh-readonly-probe")?.label || "Cisco SSH read-only probe",
      run: () => runWorkflowCheck("cisco.ssh-readonly-probe")
    },
    {
      detail: "Prove SSH/SCP readiness without changing switch config.",
      icon: <ShieldCheck size={14} />,
      id: "cisco.validate-ssh-scp",
      label: byId.get("cisco.validate-ssh-scp")?.label || "Validate SSH/SCP",
      run: () => runWorkflowCheck("cisco.validate-ssh-scp")
    },
    {
      detail: "Inventory IOS XE and related firmware evidence.",
      icon: <Layers size={14} />,
      id: "cisco.firmware-inventory",
      label: byId.get("cisco.firmware-inventory")?.label || "Cisco Firmware Inventory",
      run: () => runWorkflowCheck("cisco.firmware-inventory")
    },
    {
      detail: "Compare live read-only state to the saved network intent.",
      icon: <Route size={14} />,
      id: "cisco.current-intent-diff",
      label: byId.get("cisco.current-intent-diff")?.label || "Cisco Current Intent Diff",
      run: () => runWorkflowCheck("cisco.current-intent-diff")
    },
    {
      detail: "Read setup readiness, console, credential, and prompt boundaries.",
      icon: <CheckCircle2 size={14} />,
      id: "cisco.setup-readiness",
      label: byId.get("cisco.setup-readiness")?.label || "Cisco Access Live Check",
      run: () => runWorkflowCheck("cisco.setup-readiness")
    },
    {
      detail: "Confirm privilege level before any guarded config path can be considered.",
      icon: <ShieldCheck size={14} />,
      id: "cisco.privilege-check",
      label: byId.get("cisco.privilege-check")?.label || "Privilege Check",
      run: () => runWorkflowCheck("cisco.privilege-check")
    }
  ];
  const readOnlyPrimary = actions.slice(0, 3);
  const readOnlyMore = actions.slice(3);
  const latestWorkflowRun = actionIds
    .flatMap((id) => workflowRunsById[id] ?? [])
    .sort((a, b) => asString(b.finished_at || b.started_at).localeCompare(asString(a.finished_at || a.started_at)))[0] ?? null;
  const evidenceRows = [
    {
      detail: "Saved setup",
      label: "Management IP",
      status: address.cisco_management ? "planned" : "not_checked",
      value: displayAddress(address.cisco_management)
    },
    {
      detail: sourceLabel(setupReadiness),
      label: "Setup readiness",
      status: asString(setupReadiness?.status) || (setupReadiness ? "ready" : "not_checked"),
      value: asString(setupReadiness?.message) || asString(setupReadiness?.next_safe_action) || "Not checked"
    },
    {
      detail: sourceLabel(sshProbe),
      label: "SSH probe",
      status: asString(sshProbe?.status) || "not_checked",
      value: asString(sshProbe?.message) || "No live SSH probe run from workspace"
    },
    {
      detail: sourceLabel(intentDiff),
      label: "Intent diff",
      status: asString(intentDiff?.status) || "not_checked",
      value: asString(intentDiff?.message) || "No current-to-intent diff run from workspace"
    },
    {
      detail: "Firmware summary",
      label: "Firmware",
      status: ciscoFirmware === "Not checked" ? "not_checked" : "ready",
      value: ciscoFirmware
    },
    {
      detail: latestWorkflowRun ? "Workflow action run" : "Workflow history",
      label: "Last workflow",
      status: latestWorkflowRun?.status || "not_checked",
      value: latestWorkflowRun ? `${latestWorkflowRun.action_id}: ${displayStatus(latestWorkflowRun.status)}` : "No workspace workflow run yet"
    }
  ];

  async function runWorkspaceNetworkAction(action: CiscoWorkspaceAction) {
    setRunState({ error: "", message: "", runningActionId: action.id });
    try {
      const result = await action.run();
      await onReload();
      const status = asString(result.status) || "completed";
      const message = "summary" in result
        ? asString(result.summary) || asString(result.next_action)
        : asString(result.message) || asString(result.next_safe_action);
      setRunState({
        error: "",
        message: `${action.label}: ${displayStatus(status)}. ${message}`,
        runningActionId: ""
      });
    } catch (err) {
      setRunState({ error: errorMessage(err), message: "", runningActionId: "" });
    }
  }

  function renderActionButton(action: CiscoWorkspaceAction) {
    const running = runState.runningActionId === action.id;
    return (
      <button disabled={running} key={action.id} onClick={() => void runWorkspaceNetworkAction(action)} type="button">
        {action.icon}
        <span>{running ? "Running" : action.label}</span>
        <small>{action.detail}</small>
      </button>
    );
  }

  return (
    <section className="network-workspace-controls" aria-label="Cisco workspace network controls">
      <div className="network-workspace-controls-head">
        <div>
          <p className="operator-kicker">Network controls</p>
          <h4>Cisco read-only checks</h4>
          <span>Network-page checks moved into the switch workspace. Unknown stays gray until a real check runs.</span>
        </div>
        <StatusBadge label="Read-only" status="safe-to-run" />
      </div>

      <div className="network-workspace-evidence-grid">
        {evidenceRows.map((row) => (
          <div key={row.label}>
            <span>{row.label}</span>
            <strong>{row.value}</strong>
            <small>{row.detail}</small>
            <SimpleStatusPill status={row.status} />
          </div>
        ))}
      </div>

      <div className="network-workspace-action-groups">
        <section className="network-workspace-action-group">
          <div>
            <p className="operator-kicker">Read-only checks</p>
            <h5>Live switch proof</h5>
          </div>
          <div className="network-workspace-action-buttons">
            {readOnlyPrimary.map(renderActionButton)}
          </div>
          <details>
            <summary>More read-only checks</summary>
            <div className="network-workspace-action-buttons">
              {readOnlyMore.map(renderActionButton)}
            </div>
          </details>
        </section>
      </div>

      {(runState.message || runState.error) && (
        <p className={runState.error ? "operator-action-message error" : "operator-action-message success"}>
          {runState.error || runState.message}
        </p>
      )}
    </section>
  );
}

function TopologySystemSafetyStrip({
  labSafety,
  loading,
  onUpdated
}: {
  labSafety: LabSafetySettings | null;
  loading: boolean;
  onUpdated: () => Promise<void>;
}) {
  const ready = labSafetyReady(labSafety);
  const missing = (labSafety?.flags ?? []).filter((flag) => flag.required && !flag.enabled).length;

  return (
    <details className="topology-system-safety" aria-label="System lab safety gates">
      <summary>
        <span>
          <ShieldCheck size={14} />
          <strong>Lab safety</strong>
          <small>{loading ? "Checking gates" : !labSafety ? "Unavailable" : ready ? "Ready for real-lab checks" : `${missing} gate${missing === 1 ? "" : "s"} missing`}</small>
        </span>
        <StatusBadge label={ready ? "Ready" : "Gated"} status={ready ? "ready" : "blocked"} />
      </summary>
      <div className="topology-system-safety-panel">
        <p>System-wide real-lab gates stay here, not inside a single device workspace.</p>
        <LabSafetyControls labSafety={labSafety} onUpdated={onUpdated} />
      </div>
    </details>
  );
}

type SystemSetupPanelMode = "switch" | "new";

type SystemSetupAdvancedEditState = {
  ciscoManagement: string;
  datastoreTarget: string;
  dnsServers: string;
  enableDns: boolean;
  enableNtp: boolean;
  enableSnmp: boolean;
  enableVcenter: boolean;
  esxiManagement: string;
  gateway: string;
  ilo: string;
  iloInitial: string;
  iscsiLifs: string;
  mtu: string;
  netappClusterMgmt: string;
  netappControllerASp: string;
  netappControllerBSp: string;
  netappNodeAMgmt: string;
  netappNodeBMgmt: string;
  netappSvmMgmt: string;
  nfsLifs: string;
  ntpServers: string;
  serverEmbeddedNic: string;
  storageProtocol: string;
  subnet: string;
  vcenterTarget: string;
  vlanId: string;
};

type SystemSetupAdvancedTextKey = {
  [K in keyof SystemSetupAdvancedEditState]: SystemSetupAdvancedEditState[K] extends string ? K : never;
}[keyof SystemSetupAdvancedEditState];

type SystemSetupAdvancedField = {
  inputMode?: "numeric";
  key: SystemSetupAdvancedTextKey;
  label: string;
  note: string;
};

type SystemSetupAdvancedGroup = {
  fields: SystemSetupAdvancedField[];
  id: string;
  label: string;
  summary: string;
};

function SystemSetupPicker({
  activeProfile,
  address,
  features,
  labProfileState,
  onChanged
}: {
  activeProfile: LabProfile | null;
  address: LabAddressPlan;
  features: LabProfileFeatures | null;
  labProfileState: LabProfileList | null;
  onChanged: () => Promise<void> | void;
}) {
  const [open, setOpen] = useState(false);
  const [panelMode, setPanelMode] = useState<SystemSetupPanelMode>("switch");
  const pickerRef = useRef<HTMLElement | null>(null);
  const profileOptions = useMemo(() => systemSetupProfileOptions(labProfileState, activeProfile), [activeProfile, labProfileState]);
  const currentScenario = topologyScenarioFromProfile(activeProfile, features);
  const [selectedProfileId, setSelectedProfileId] = useState(activeProfile?.id ?? "runtime");
  const [newName, setNewName] = useState(() => systemSetupDefaultName(activeProfile));
  const [newSubnet, setNewSubnet] = useState(() => displayAddress(address.subnet) === "Not set up yet" ? "192.168.200.0/24" : displayAddress(address.subnet));
  const [newScenario, setNewScenario] = useState<TopologyDesignScenario>(currentScenario);
  const [advancedEdit, setAdvancedEdit] = useState<SystemSetupAdvancedEditState>(() =>
    systemSetupAdvancedEditStateFrom(activeProfile, address, features)
  );
  const [status, setStatus] = useState<{ kind: "idle" | "running" | "ok" | "error"; message: string }>({ kind: "idle", message: "" });
  const advancedProfileResetKey = [
    activeProfile?.id ?? "none",
    activeProfile?.version ?? "0",
    activeProfile?.updated_at ?? "",
    activeProfile?.source ?? "",
    address.subnet ?? "",
    address.cisco_management ?? "",
    address.esxi_management ?? "",
    address.ilo ?? "",
    address.ilo_initial ?? "",
    address.server_embedded_nic ?? "",
    address.ansible_control_host ?? "",
    address.netapp_cluster_mgmt ?? "",
    address.netapp_controller_a_sp ?? "",
    address.netapp_controller_b_sp ?? "",
    address.netapp_node_a_mgmt ?? "",
    address.netapp_node_b_mgmt ?? "",
    address.netapp_svm_mgmt ?? "",
    address.netapp_nfs_lifs.join(","),
    address.netapp_iscsi_lifs.join(","),
    String(features?.enable_dns ?? ""),
    String(features?.enable_ntp ?? ""),
    String(features?.enable_snmp ?? ""),
    String(features?.vcenter_enabled ?? ""),
    features?.storage_protocol ?? "",
    currentScenario
  ].join("|");

  useEffect(() => {
    setSelectedProfileId(activeProfile?.id ?? "runtime");
    setNewName(systemSetupDefaultName(activeProfile));
    setNewSubnet(displayAddress(address.subnet) === "Not set up yet" ? "192.168.200.0/24" : displayAddress(address.subnet));
    setNewScenario(currentScenario);
    setAdvancedEdit(systemSetupAdvancedEditStateFrom(activeProfile, address, features));
  }, [advancedProfileResetKey]);

  useEffect(() => {
    if (!open) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    function closeOnPointer(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Node && pickerRef.current && !pickerRef.current.contains(target)) {
        setOpen(false);
      }
    }
    document.addEventListener("keydown", closeOnEscape);
    document.addEventListener("pointerdown", closeOnPointer);
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      document.removeEventListener("pointerdown", closeOnPointer);
    };
  }, [open]);

  const subnetValidation = topologySubnetDraftValidation(newSubnet);
  const previewAddress = topologyAddressPlanForSubnet(address, cleanNetworkNullable(newSubnet));
  const previewRows = systemSetupPreviewRows(previewAddress, newScenario);
  const savedCount = Math.max(0, profileOptions.filter((profile) => profile.source === "saved").length);
  const selectedProfile = profileOptions.find((profile) => profile.id === selectedProfileId) ?? profileOptions[0] ?? null;
  const advancedDerived = useMemo(
    () => systemSetupAdvancedDerivedState(advancedEdit.subnet || address.subnet, activeProfile, features),
    [activeProfile, address.subnet, advancedEdit.subnet, features]
  );
  const advancedGroups = useMemo(() => systemSetupAdvancedGroups(), []);
  const advancedOverrideCount = systemSetupAdvancedOverrideCount(advancedEdit, advancedDerived);
  const canCreate = Boolean(activeProfile && newName.trim() && subnetValidation.status !== "error" && status.kind !== "running");
  const canActivate = Boolean(selectedProfileId && selectedProfileId !== (activeProfile?.id ?? "runtime") && status.kind !== "running");
  const canSaveAdvanced = Boolean(activeProfile && status.kind !== "running");

  function updateAdvanced<K extends keyof SystemSetupAdvancedEditState>(key: K, value: SystemSetupAdvancedEditState[K]) {
    setAdvancedEdit((current) => ({ ...current, [key]: value }));
  }

  async function activateSelectedProfile() {
    if (!selectedProfile || status.kind === "running") return;
    setStatus({ kind: "running", message: "Switching active setup. No hardware action is running." });
    try {
      await api.activateLabProfile(selectedProfile.id);
      await onChanged();
      setStatus({ kind: "ok", message: `Switched to ${selectedProfile.name} - device status is unknown until a check runs.` });
      setOpen(false);
    } catch (err) {
      setStatus({ kind: "error", message: errorMessage(err) });
    }
  }

  async function createAndActivate() {
    if (!activeProfile || !canCreate) return;
    setStatus({ kind: "running", message: "Creating saved setup from subnet plan. Hardware remains untouched." });
    try {
      const created = await api.createLabProfile(systemSetupProfilePayload({
        address: previewAddress,
        name: newName,
        scenario: newScenario,
        sourceProfile: activeProfile
      }));
      await api.activateLabProfile(created.id);
      await onChanged();
      setStatus({ kind: "ok", message: `Created ${created.name} - device status is unknown until a check runs.` });
      setOpen(false);
    } catch (err) {
      setStatus({ kind: "error", message: errorMessage(err) });
    }
  }

  async function saveAdvancedFields(event: FormEvent) {
    event.preventDefault();
    if (!activeProfile || status.kind === "running") return;
    setStatus({ kind: "running", message: "Saving advanced profile fields. Hardware remains untouched." });
    try {
      const payload = systemSetupAdvancedProfilePayload(activeProfile, advancedEdit);
      if (activeProfile.source === "saved") {
        await api.updateLabProfile(activeProfile.id, payload);
      } else {
        const saved = await api.createLabProfile(payload);
        await api.activateLabProfile(saved.id);
      }
      await onChanged();
      setStatus({ kind: "ok", message: "Advanced profile fields saved. Map state will re-derive from the saved setup; live checks still need to be run separately." });
    } catch (err) {
      setStatus({ kind: "error", message: errorMessage(err) });
    }
  }

  function renderAdvancedField(field: SystemSetupAdvancedField) {
    const value = advancedEdit[field.key];
    const derivedValue = advancedDerived[field.key];
    const isOverride = systemSetupAdvancedIsOverride(value, derivedValue);
    return (
      <label className={`system-setup-advanced-field ${isOverride ? "is-override" : "is-derived"}`} key={field.key}>
        <span>
          {field.label}
          <em>{isOverride ? "Override" : "Planned"}</em>
        </span>
        <input
          aria-label={`Advanced ${field.label}`}
          inputMode={field.inputMode}
          placeholder={derivedValue || "Derived from setup"}
          value={value}
          onChange={(event) => updateAdvanced(field.key, event.target.value)}
        />
        <small>Derived: {derivedValue || "not derived"} - {field.note}</small>
      </label>
    );
  }

  return (
    <section className={`system-setup-picker ${open ? "is-open" : ""}`} id="system-setup" aria-label="System setup picker" ref={pickerRef}>
      <button
        aria-label="Open system setup picker"
        aria-expanded={open}
        className="system-setup-strip"
        onClick={() => setOpen((value) => !value)}
        type="button"
      >
        <span className="system-setup-dot" aria-hidden="true" />
        <span className="system-setup-eyebrow">Setup</span>
        <strong>{activeProfile?.name ?? "Runtime Lab"}</strong>
        <code>{displayAddress(address.subnet)}</code>
        <span className="system-setup-mode">{topologyScenarioShortLabel(currentScenario)}</span>
        <span className="system-setup-chevron" aria-hidden="true">Open</span>
      </button>

      {open && (
        <div className="system-setup-panel" role="dialog" aria-label="Setup and IP plan">
          <div className="system-setup-panel-head">
            <div>
              <span>Setup & IP plan</span>
              <small>{panelMode === "switch" ? "Pick a saved system or create a subnet-derived plan." : "Name it, choose the shape, enter a subnet. No probes or writes."}</small>
            </div>
          </div>
          <div className="system-setup-tabs" role="group" aria-label="Setup picker mode">
            <button
              aria-pressed={panelMode === "switch"}
              className={panelMode === "switch" ? "is-active" : ""}
              onClick={() => setPanelMode("switch")}
              type="button"
            >
              Switch system
            </button>
            <button
              aria-pressed={panelMode === "new"}
              className={panelMode === "new" ? "is-active" : ""}
              onClick={() => setPanelMode("new")}
              type="button"
            >
              New system
            </button>
          </div>

          {panelMode === "switch" ? (
            <div className="system-setup-pane" aria-label="Saved setups">
              <div className="system-setup-list">
                {profileOptions.map((profile) => {
                  const profileScenario = topologyScenarioFromProfile(profile, profile.features);
                  const profileSubnet = displayAddress(profile.resolved_address_plan?.subnet ?? profile.address_plan.subnet ?? profile.subnet_cidr);
                  const isActive = profile.id === (activeProfile?.id ?? "runtime");
                  const isSelected = profile.id === selectedProfileId;
                  return (
                    <button
                      aria-pressed={isSelected}
                      className={`system-setup-row ${isSelected ? "is-selected" : ""}`}
                      key={profile.id}
                      onClick={() => setSelectedProfileId(profile.id)}
                      type="button"
                    >
                      <span className="system-setup-row-radio" aria-hidden="true" />
                      <span className="system-setup-row-main">
                        <strong>{profile.name}</strong>
                        <span>
                          <code>{profileSubnet}</code>
                          <small>{topologyScenarioShortLabel(profileScenario)}</small>
                        </span>
                        <small>{systemSetupLastLabel(profile)}</small>
                      </span>
                      <em className={isActive ? "system-setup-active-badge" : ""}>{isActive ? "Active" : profile.source === "saved" ? "Saved" : "Runtime"}</em>
                    </button>
                  );
                })}
              </div>
              <button className="system-setup-primary" disabled={!canActivate} onClick={activateSelectedProfile} type="button">
                Activate system
              </button>
              <p className="system-setup-muted">{savedCount} saved setup{savedCount === 1 ? "" : "s"}. History stays attached to each saved profile.</p>
            </div>
          ) : (
            <div className="system-setup-pane system-setup-new" aria-label="Create setup from subnet">
              <label>
                <span>New setup name</span>
                <input value={newName} onChange={(event) => setNewName(event.target.value)} />
              </label>
              <div className="system-setup-mode-field" role="group" aria-label="Deployment mode">
                <span>Deployment mode</span>
                <div className="system-setup-mode-options">
                  {topologyDesignScenarios().map((scenario) => (
                    <button
                      aria-pressed={newScenario === scenario.id}
                      className={newScenario === scenario.id ? "is-active" : ""}
                      key={scenario.id}
                      onClick={() => setNewScenario(scenario.id)}
                      type="button"
                    >
                      <strong>{scenario.label}</strong>
                      <small>{scenario.detail}</small>
                    </button>
                  ))}
                </div>
              </div>
              <label>
                <span>Subnet CIDR</span>
                <input value={newSubnet} onChange={(event) => setNewSubnet(event.target.value)} placeholder="192.168.200.0/24" />
              </label>
              <p className={`system-setup-validation system-setup-validation-${subnetValidation.status}`}>
                {subnetValidation.detail} Entering a subnet auto-fills planned IPs only.
              </p>
              <div className="system-setup-preview" aria-label="Derived IP preview">
                <div className="system-setup-preview-head">
                  <span className="system-setup-preview-title"><i aria-hidden="true" /> <strong>Planned IPs</strong></span>
                  <span>Auto-derived from subnet</span>
                </div>
                <div className="system-setup-preview-grid">
                  {previewRows.map((row) => (
                    <span className={`system-setup-preview-chip system-setup-preview-${row.status}`} key={row.label}>
                      <small>{row.label}</small>
                      <code>{row.value}</code>
                      <em>{row.status === "out" ? "Out" : row.status === "optional" ? "Optional" : "Planned"}</em>
                    </span>
                  ))}
                </div>
              </div>
              <button className="system-setup-primary" disabled={!canCreate} onClick={createAndActivate} type="button">
                Create setup
              </button>
            </div>
          )}

          <details className="system-setup-advanced" aria-label="Advanced fields">
            <summary>
              <span>
                <strong>Advanced fields</strong>
                <small>{advancedOverrideCount ? `${advancedOverrideCount} override${advancedOverrideCount === 1 ? "" : "s"} staged` : "Collapsed by default; subnet-derived unless overridden."}</small>
              </span>
              <em>{advancedOverrideCount ? "OVERRIDE" : "PLANNED"}</em>
            </summary>
            <form className="system-setup-advanced-form" onSubmit={saveAdvancedFields}>
              <p className="system-setup-muted">
                Profile/config editing only. These values save the lab setup; no probes, hardware writes, guarded writes, power, reset, factory, or rebuild actions run here.
              </p>
              {advancedGroups.map((group) => (
                <details className="system-setup-advanced-group" key={group.id}>
                  <summary>
                    <span>
                      <strong>{group.label}</strong>
                      <small>{group.summary}</small>
                    </span>
                  </summary>
                  <div className="system-setup-advanced-grid">
                    {group.fields.map(renderAdvancedField)}
                    {group.id === "storage" && (
                      <label className={`system-setup-advanced-field ${advancedEdit.storageProtocol === advancedDerived.storageProtocol ? "is-derived" : "is-override"}`}>
                        <span>Storage protocol <em>{advancedEdit.storageProtocol === advancedDerived.storageProtocol ? "Planned" : "Override"}</em></span>
                        <select
                          aria-label="Advanced Storage protocol"
                          value={advancedEdit.storageProtocol}
                          onChange={(event) => updateAdvanced("storageProtocol", event.target.value)}
                        >
                          <option value="nfs">NFS</option>
                          <option value="iscsi">iSCSI</option>
                          <option value="local">Local RAID</option>
                        </select>
                        <small>Derived: {advancedDerived.storageProtocol || "nfs"} - Protocol intent only; apply remains guarded elsewhere.</small>
                      </label>
                    )}
                    {group.id === "services" && (
                      <div className="system-setup-advanced-toggles" aria-label="Advanced service toggles">
                        {([
                          ["enableDns", "DNS", advancedDerived.enableDns],
                          ["enableNtp", "NTP", advancedDerived.enableNtp],
                          ["enableSnmp", "SNMP", advancedDerived.enableSnmp]
                        ] as Array<["enableDns" | "enableNtp" | "enableSnmp", string, boolean]>).map(([typedKey, label, derived]) => {
                          const isOverride = advancedEdit[typedKey] !== derived;
                          return (
                            <label className={isOverride ? "is-override" : "is-derived"} key={typedKey}>
                              <input
                                aria-label={`Advanced ${label} toggle`}
                                checked={advancedEdit[typedKey]}
                                onChange={(event) => updateAdvanced(typedKey, event.target.checked)}
                                type="checkbox"
                              />
                              <span>{label}</span>
                              <em>{isOverride ? "Override" : "Planned"}</em>
                            </label>
                          );
                        })}
                      </div>
                    )}
                    {group.id === "virtualization" && (
                      <div className="system-setup-advanced-toggles" aria-label="Advanced virtualization toggles">
                        <label className={advancedEdit.enableVcenter === advancedDerived.enableVcenter ? "is-derived" : "is-override"}>
                          <input
                            aria-label="Advanced vCenter in scope toggle"
                            checked={advancedEdit.enableVcenter}
                            onChange={(event) => updateAdvanced("enableVcenter", event.target.checked)}
                            type="checkbox"
                          />
                          <span>vCenter in scope</span>
                          <em>{advancedEdit.enableVcenter === advancedDerived.enableVcenter ? "Planned" : "Override"}</em>
                        </label>
                      </div>
                    )}
                  </div>
                </details>
              ))}
              <div className="system-setup-advanced-actions">
                <button className="system-setup-primary" disabled={!canSaveAdvanced} type="submit">
                  {status.kind === "running" ? "Saving" : activeProfile?.source === "saved" ? "Save advanced fields" : "Save as lab setup"}
                </button>
                <span>One profile commit. Workspaces remain display/test only.</span>
              </div>
            </form>
          </details>

          <p className="system-setup-footnote">
            Selects which saved setup and IP plan you are working on. It does not probe or reconfigure any device.
          </p>

          {status.message && (
            <p className={`system-setup-status system-setup-status-${status.kind}`} role="status">
              {status.message}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

function systemSetupDefaultName(activeProfile: LabProfile | null): string {
  const base = activeProfile?.name?.replace(/\s+\(copy\)$/i, "").trim() || "Lab system";
  return `${base} copy`;
}

function systemSetupProfileOptions(state: LabProfileList | null, activeProfile: LabProfile | null): LabProfile[] {
  const options = [state?.runtime_profile, ...(state?.profiles ?? []), activeProfile].filter(Boolean) as LabProfile[];
  const seen = new Set<string>();
  return options.filter((profile) => {
    if (seen.has(profile.id)) return false;
    seen.add(profile.id);
    return true;
  });
}

function systemSetupLastLabel(profile: LabProfile): string {
  const latestHistory = (profile.history ?? []).slice(-1)[0];
  if (latestHistory) return `revision v${latestHistory.version}`;
  const selected = asString(profile.last_selected_at);
  if (selected) return `last activated ${selected.slice(0, 10)}`;
  return profile.source === "saved" ? "saved profile" : "runtime profile";
}

function systemSetupPreviewRows(address: LabAddressPlan, scenario: TopologyDesignScenario): Array<{ label: string; status: string; value: string }> {
  const netappInScope = scenario !== "single_server_local_storage";
  const vcenterInScope = scenario === "server_netapp_vcenter";
  return [
    { label: "iLO", status: "planned", value: displayAddress(address.ilo) },
    { label: "Cisco mgmt", status: "planned", value: displayAddress(address.cisco_management) },
    { label: "ESXi", status: "planned", value: displayAddress(address.esxi_management) },
    { label: "NetApp cluster", status: netappInScope ? "planned" : "out", value: netappInScope ? displayAddress(address.netapp_cluster_mgmt) : "Out of scope" },
    { label: "NFS LIFs", status: netappInScope ? "planned" : "out", value: netappInScope ? address.netapp_nfs_lifs.map(displayAddress).join(", ") || "Not set up yet" : "Out of scope" },
    { label: "vCenter / control", status: vcenterInScope ? "planned" : "optional", value: vcenterInScope ? displayAddress(address.ansible_control_host) : "Direct ESXi path" }
  ];
}

function systemSetupAdvancedEditStateFrom(
  activeProfile: LabProfile | null,
  address: LabAddressPlan,
  features: LabProfileFeatures | null
): SystemSetupAdvancedEditState {
  const global = activeProfile?.global_settings ?? null;
  const devices = activeProfile?.devices ?? {};
  const netappDevice = devices.netapp && typeof devices.netapp === "object" ? devices.netapp : {};
  return {
    ciscoManagement: address.cisco_management ?? "",
    datastoreTarget: asString(netappDevice.datastore_target) || asString(netappDevice.datastore),
    dnsServers: (global?.dns_servers ?? activeProfile?.dns ?? []).join(", "),
    enableDns: features?.enable_dns ?? true,
    enableNtp: features?.enable_ntp ?? true,
    enableSnmp: features?.enable_snmp ?? false,
    enableVcenter: features?.vcenter_enabled ?? Boolean(devices.vcenter),
    esxiManagement: address.esxi_management ?? "",
    gateway: global?.gateway ?? activeProfile?.gateway ?? "",
    ilo: address.ilo ?? "",
    iloInitial: address.ilo_initial ?? "",
    iscsiLifs: address.netapp_iscsi_lifs.join(", "),
    mtu: global?.mtu !== null && global?.mtu !== undefined ? String(global.mtu) : activeProfile?.mtu ? String(activeProfile.mtu) : "",
    netappClusterMgmt: address.netapp_cluster_mgmt ?? "",
    netappControllerASp: address.netapp_controller_a_sp ?? "",
    netappControllerBSp: address.netapp_controller_b_sp ?? "",
    netappNodeAMgmt: address.netapp_node_a_mgmt ?? "",
    netappNodeBMgmt: address.netapp_node_b_mgmt ?? "",
    netappSvmMgmt: address.netapp_svm_mgmt ?? "",
    nfsLifs: address.netapp_nfs_lifs.join(", "),
    ntpServers: (global?.ntp_servers ?? activeProfile?.ntp ?? []).join(", "),
    serverEmbeddedNic: address.server_embedded_nic ?? "",
    storageProtocol: features?.storage_protocol === "iscsi" ? "iscsi" : features?.storage_protocol === "local" ? "local" : "nfs",
    subnet: address.subnet ?? activeProfile?.subnet_cidr ?? "",
    vcenterTarget: asString(devices.vcenter),
    vlanId: global?.vlan_id ?? activeProfile?.vlan_id ?? ""
  };
}

function systemSetupAdvancedDerivedState(
  subnet: string | null,
  activeProfile: LabProfile | null,
  features: LabProfileFeatures | null
): SystemSetupAdvancedEditState {
  const plan = systemSetupDerivedAddressPlan(cleanNetworkNullable(subnet) ?? activeProfile?.subnet_cidr ?? activeProfile?.address_plan.subnet ?? "192.168.1.0/24");
  const gateway = topologyGatewayFromSubnet(plan.subnet);
  const storageProtocol = features?.storage_protocol === "iscsi" ? "iscsi" : features?.storage_protocol === "local" ? "local" : "nfs";
  return {
    ciscoManagement: plan.cisco_management ?? "",
    datastoreTarget: storageProtocol === "local" ? "local_esxi_datastore" : "netapp_nfs_ds01",
    dnsServers: activeProfile?.global_settings.dns_servers?.join(", ") || activeProfile?.dns?.join(", ") || gateway,
    enableDns: features?.enable_dns ?? true,
    enableNtp: features?.enable_ntp ?? true,
    enableSnmp: features?.enable_snmp ?? false,
    enableVcenter: features?.vcenter_enabled ?? Boolean(activeProfile?.devices?.vcenter),
    esxiManagement: plan.esxi_management ?? "",
    gateway,
    ilo: plan.ilo ?? "",
    iloInitial: plan.ilo_initial ?? "",
    iscsiLifs: plan.netapp_iscsi_lifs.join(", "),
    mtu: activeProfile?.global_settings.mtu !== null && activeProfile?.global_settings.mtu !== undefined ? String(activeProfile.global_settings.mtu) : activeProfile?.mtu ? String(activeProfile.mtu) : "1500",
    netappClusterMgmt: plan.netapp_cluster_mgmt ?? "",
    netappControllerASp: plan.netapp_controller_a_sp ?? "",
    netappControllerBSp: plan.netapp_controller_b_sp ?? "",
    netappNodeAMgmt: plan.netapp_node_a_mgmt ?? "",
    netappNodeBMgmt: plan.netapp_node_b_mgmt ?? "",
    netappSvmMgmt: plan.netapp_svm_mgmt ?? "",
    nfsLifs: plan.netapp_nfs_lifs.join(", "),
    ntpServers: activeProfile?.global_settings.ntp_servers?.join(", ") || activeProfile?.ntp?.join(", ") || gateway,
    serverEmbeddedNic: plan.server_embedded_nic ?? "",
    storageProtocol,
    subnet: plan.subnet ?? "",
    vcenterTarget: plan.ansible_control_host ?? "",
    vlanId: activeProfile?.global_settings.vlan_id ?? activeProfile?.vlan_id ?? "100"
  };
}

function systemSetupDerivedAddressPlan(subnet: string | null): LabAddressPlan {
  const base = topologySubnetBase(subnet);
  const at = (offset: number) => base ? `${base}.${offset}` : null;
  return {
    ansible_control_host: at(205),
    cisco_management: at(204),
    esxi_management: at(203),
    ilo: at(201),
    ilo_initial: at(201),
    netapp_cluster_mgmt: at(220),
    netapp_controller_a_sp: at(210),
    netapp_controller_b_sp: at(211),
    netapp_iscsi_lifs: [240, 241, 242, 243].map(at).filter(Boolean) as string[],
    netapp_nfs_lifs: [230, 231].map(at).filter(Boolean) as string[],
    netapp_node_a_mgmt: at(221),
    netapp_node_b_mgmt: at(222),
    netapp_svm_mgmt: at(223),
    server_embedded_nic: at(202),
    subnet: cleanNetworkNullable(subnet)
  };
}

function systemSetupAdvancedGroups(): SystemSetupAdvancedGroup[] {
  return [
    {
      fields: [
        { key: "subnet", label: "Subnet", note: "Primary profile subnet; changes the derived plan." },
        { key: "gateway", label: "Gateway", note: "Shared gateway for the lab profile." },
        { inputMode: "numeric", key: "mtu", label: "MTU", note: "Shared MTU override." }
      ],
      id: "addressing",
      label: "Shared addressing",
      summary: "Subnet, gateway, and MTU."
    },
    {
      fields: [
        { key: "dnsServers", label: "DNS servers", note: "Comma-separated profile DNS servers." },
        { key: "ntpServers", label: "NTP servers", note: "Comma-separated profile NTP servers." }
      ],
      id: "services",
      label: "Shared services",
      summary: "DNS, NTP, and service toggles."
    },
    {
      fields: [
        { key: "ciscoManagement", label: "Cisco mgmt IP", note: "Switch management address." },
        { key: "vlanId", label: "VLAN", note: "Default management VLAN." }
      ],
      id: "network",
      label: "Network / Switch",
      summary: "Cisco management and VLAN overrides."
    },
    {
      fields: [
        { key: "ilo", label: "iLO IP", note: "Saved iLO/BMC address." },
        { key: "iloInitial", label: "Initial iLO IP", note: "Factory/default iLO address when needed." },
        { key: "serverEmbeddedNic", label: "Embedded NIC", note: "Server embedded NIC planning address." },
        { key: "esxiManagement", label: "ESXi mgmt IP", note: "Shared with virtualization attach target." }
      ],
      id: "server",
      label: "Server / iLO / ESXi",
      summary: "Server management addresses."
    },
    {
      fields: [
        { key: "netappClusterMgmt", label: "Cluster mgmt", note: "ONTAP cluster management IP." },
        { key: "netappSvmMgmt", label: "SVM mgmt", note: "Storage VM management IP." },
        { key: "netappNodeAMgmt", label: "Node A mgmt", note: "Controller/node A management IP." },
        { key: "netappNodeBMgmt", label: "Node B mgmt", note: "Controller/node B management IP." },
        { key: "netappControllerASp", label: "Controller A SP", note: "Controller A service processor IP." },
        { key: "netappControllerBSp", label: "Controller B SP", note: "Controller B service processor IP." },
        { key: "nfsLifs", label: "NFS LIFs", note: "Comma-separated NFS data LIFs." },
        { key: "iscsiLifs", label: "iSCSI LIFs", note: "Comma-separated iSCSI data LIFs." },
        { key: "datastoreTarget", label: "Datastore target", note: "Datastore name visible to ESXi/vCenter." }
      ],
      id: "storage",
      label: "Storage / NetApp",
      summary: "ONTAP management, protocols, and datastore."
    },
    {
      fields: [
        { key: "vcenterTarget", label: "vCenter target", note: "VCSA or SDK target; apply/deploy remains guarded elsewhere." }
      ],
      id: "virtualization",
      label: "Virtualization",
      summary: "vCenter scope and target."
    }
  ];
}

function systemSetupAdvancedNormalize(value: unknown): string {
  return asString(value)
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .join(",")
    .toLowerCase();
}

function systemSetupAdvancedIsOverride(value: unknown, derived: unknown): boolean {
  const normalizedValue = systemSetupAdvancedNormalize(value);
  if (!normalizedValue) return false;
  return normalizedValue !== systemSetupAdvancedNormalize(derived);
}

function systemSetupAdvancedOverrideCount(edit: SystemSetupAdvancedEditState, derived: SystemSetupAdvancedEditState): number {
  return (Object.keys(edit) as Array<keyof SystemSetupAdvancedEditState>)
    .filter((key) => edit[key] !== derived[key] && (typeof edit[key] === "boolean" || systemSetupAdvancedIsOverride(edit[key], derived[key])))
    .length;
}

function systemSetupHostFromTarget(value: string): string | null {
  const cleaned = cleanNetworkNullable(value);
  if (!cleaned) return null;
  try {
    return new URL(cleaned).hostname || cleaned;
  } catch {
    return cleaned.replace(/^https?:\/\//, "").replace(/\/sdk\/?$/, "");
  }
}

function systemSetupAdvancedProfilePayload(profile: LabProfile, edit: SystemSetupAdvancedEditState): LabProfileWrite {
  const subnet = cleanNetworkNullable(edit.subnet);
  const subnetPrefix = networkPrefixFromCidr(subnet) ?? profile.global_settings.subnet_prefix ?? 24;
  const gateway = cleanNetworkNullable(edit.gateway);
  const mtu = parseNetworkMtu(edit.mtu);
  const dnsServers = splitNetworkList(edit.dnsServers);
  const ntpServers = splitNetworkList(edit.ntpServers);
  const storageProtocol = edit.storageProtocol === "iscsi" ? "iscsi" : edit.storageProtocol === "local" ? "local" : "nfs";
  const vcenterTarget = cleanNetworkNullable(edit.vcenterTarget);
  const vcenterHost = systemSetupHostFromTarget(edit.vcenterTarget);
  const netappDevice = profile.devices?.netapp && typeof profile.devices.netapp === "object" ? profile.devices.netapp : {};
  const addressPlan: LabAddressPlan = {
    ...profile.address_plan,
    ansible_control_host: vcenterHost,
    cisco_management: cleanNetworkNullable(edit.ciscoManagement),
    esxi_management: cleanNetworkNullable(edit.esxiManagement),
    ilo: cleanNetworkNullable(edit.ilo),
    ilo_initial: cleanNetworkNullable(edit.iloInitial),
    netapp_cluster_mgmt: cleanNetworkNullable(edit.netappClusterMgmt),
    netapp_controller_a_sp: cleanNetworkNullable(edit.netappControllerASp),
    netapp_controller_b_sp: cleanNetworkNullable(edit.netappControllerBSp),
    netapp_iscsi_lifs: splitNetworkList(edit.iscsiLifs),
    netapp_nfs_lifs: splitNetworkList(edit.nfsLifs),
    netapp_node_a_mgmt: cleanNetworkNullable(edit.netappNodeAMgmt),
    netapp_node_b_mgmt: cleanNetworkNullable(edit.netappNodeBMgmt),
    netapp_svm_mgmt: cleanNetworkNullable(edit.netappSvmMgmt),
    server_embedded_nic: cleanNetworkNullable(edit.serverEmbeddedNic),
    subnet
  };
  const features: LabProfileFeatures = {
    ...profile.features,
    enable_dns: edit.enableDns,
    enable_ntp: edit.enableNtp,
    enable_snmp: edit.enableSnmp,
    storage_protocol: storageProtocol,
    vcenter_disabled_reason: edit.enableVcenter ? null : "vCenter is disabled by the active lab setup.",
    vcenter_enabled: edit.enableVcenter
  };
  const globalSettings = {
    ...profile.global_settings,
    dns_servers: dnsServers,
    gateway,
    mtu,
    ntp_servers: ntpServers,
    subnet_prefix: subnetPrefix,
    vcenter_enabled: edit.enableVcenter,
    vlan_id: cleanNetworkNullable(edit.vlanId)
  };
  return {
    address_plan: addressPlan,
    description: profile.description,
    devices: {
      ...(profile.devices ?? {}),
      cisco: addressPlan.cisco_management,
      esxi: addressPlan.esxi_management,
      gateway,
      ilo: addressPlan.ilo,
      netapp: {
        ...netappDevice,
        cluster_mgmt: addressPlan.netapp_cluster_mgmt,
        controller_a_sp: addressPlan.netapp_controller_a_sp,
        controller_b_sp: addressPlan.netapp_controller_b_sp,
        datastore_target: cleanNetworkNullable(edit.datastoreTarget),
        iscsi_lifs: addressPlan.netapp_iscsi_lifs,
        nfs_lifs: addressPlan.netapp_nfs_lifs,
        node_a_mgmt: addressPlan.netapp_node_a_mgmt,
        node_b_mgmt: addressPlan.netapp_node_b_mgmt,
        svm_mgmt: addressPlan.netapp_svm_mgmt
      },
      switch_primary: addressPlan.cisco_management,
      utility_vm: addressPlan.ansible_control_host,
      vcenter: edit.enableVcenter ? vcenterTarget : null
    },
    dns: dnsServers,
    features,
    gateway,
    global_settings: globalSettings,
    mtu,
    name: profile.source === "saved" ? profile.name : "Local lab setup",
    ntp: ntpServers,
    profile_topology: profile.profile_topology,
    subnet_cidr: subnet,
    vlan_id: cleanNetworkNullable(edit.vlanId)
  };
}

function systemSetupProfilePayload({
  address,
  name,
  scenario,
  sourceProfile
}: {
  address: LabAddressPlan;
  name: string;
  scenario: TopologyDesignScenario;
  sourceProfile: LabProfile;
}): LabProfileWrite {
  const netappInScope = scenario !== "single_server_local_storage";
  const vcenterInScope = scenario === "server_netapp_vcenter";
  const subnet = cleanNetworkNullable(address.subnet ?? sourceProfile.address_plan.subnet ?? sourceProfile.subnet_cidr);
  const subnetPrefix = networkPrefixFromCidr(subnet) ?? sourceProfile.global_settings.subnet_prefix ?? 24;
  const profileTopology = systemSetupProfileTopologyForSubnet(subnet);
  const gateway = topologyGatewayFromSubnet(subnet);
  const addressPlan: LabAddressPlan = {
    ...address,
    ansible_control_host: vcenterInScope ? cleanNetworkNullable(address.ansible_control_host) : null,
    cisco_management: cleanNetworkNullable(address.cisco_management),
    esxi_management: cleanNetworkNullable(address.esxi_management),
    ilo: cleanNetworkNullable(address.ilo),
    ilo_initial: cleanNetworkNullable(address.ilo_initial),
    netapp_cluster_mgmt: netappInScope ? cleanNetworkNullable(address.netapp_cluster_mgmt) : null,
    netapp_controller_a_sp: netappInScope ? cleanNetworkNullable(address.netapp_controller_a_sp) : null,
    netapp_controller_b_sp: netappInScope ? cleanNetworkNullable(address.netapp_controller_b_sp) : null,
    netapp_iscsi_lifs: netappInScope ? address.netapp_iscsi_lifs : [],
    netapp_nfs_lifs: netappInScope ? address.netapp_nfs_lifs : [],
    netapp_node_a_mgmt: netappInScope ? cleanNetworkNullable(address.netapp_node_a_mgmt) : null,
    netapp_node_b_mgmt: netappInScope ? cleanNetworkNullable(address.netapp_node_b_mgmt) : null,
    netapp_svm_mgmt: netappInScope ? cleanNetworkNullable(address.netapp_svm_mgmt) : null,
    server_embedded_nic: cleanNetworkNullable(address.server_embedded_nic),
    subnet
  };
  const storageProtocol = netappInScope ? (sourceProfile.features.storage_protocol === "iscsi" ? "iscsi" : "nfs") : "local";
  const features: LabProfileFeatures = {
    ...sourceProfile.features,
    deployment_label: topologyScenarioLabel(scenario),
    deployment_mode: scenario,
    deployment_supported: true,
    netapp_disabled_reason: netappInScope ? null : "Single-server profile uses server-local storage.",
    netapp_enabled: netappInScope,
    storage_location: netappInScope ? "netapp_shared" : "server_local",
    storage_protocol: storageProtocol,
    vcenter_disabled_reason: vcenterInScope ? null : "vCenter is out of scope for this setup.",
    vcenter_enabled: vcenterInScope
  };
  const globalSettings = {
    ...sourceProfile.global_settings,
    gateway,
    netapp_disabled_reason: features.netapp_disabled_reason,
    netapp_enabled: netappInScope,
    subnet_prefix: subnetPrefix,
    vcenter_enabled: vcenterInScope
  };
  return {
    address_plan: addressPlan,
    description: `Created from ${sourceProfile.name}. Profile/IP planning only; no hardware action was run.`,
    devices: {
      ...(sourceProfile.devices ?? {}),
      cisco: addressPlan.cisco_management,
      esxi: addressPlan.esxi_management,
      gateway,
      ilo: addressPlan.ilo,
      netapp: netappInScope
        ? {
            cluster_mgmt: addressPlan.netapp_cluster_mgmt,
            controller_a_sp: addressPlan.netapp_controller_a_sp,
            controller_b_sp: addressPlan.netapp_controller_b_sp,
            iscsi_lifs: addressPlan.netapp_iscsi_lifs,
            nfs_lifs: addressPlan.netapp_nfs_lifs
          }
        : null,
      switch_primary: addressPlan.cisco_management,
      utility_vm: addressPlan.ansible_control_host,
      vcenter: vcenterInScope ? addressPlan.ansible_control_host : null
    },
    dns: sourceProfile.dns,
    features,
    gateway,
    global_settings: globalSettings,
    mtu: sourceProfile.mtu,
    name: name.trim(),
    ntp: sourceProfile.ntp,
    profile_topology: profileTopology,
    subnet_cidr: subnet,
    vlan_id: sourceProfile.vlan_id
  };
}

function systemSetupProfileTopologyForSubnet(subnet: string | null): string {
  const prefix = networkPrefixFromCidr(subnet);
  return prefix && prefix > 24 ? "compact_edge_lab" : "high_address_lab";
}

function topologyWorkspaceIconKind(partId: DesignPartId): "datastore" | "hypervisor" | "ilo" | "netapp" | "server" | "switch" | "vcenter" {
  if (partId === "switch") return "switch";
  if (partId === "ilo") return "ilo";
  if (partId === "netapp") return "netapp";
  if (partId === "vcenter") return "vcenter";
  if (partId === "windows") return "hypervisor";
  return "server";
}

function topologyIndustryIcon(kind: "datastore" | "hypervisor" | "ilo" | "netapp" | "server" | "switch" | "vcenter") {
  const className = `topology-industry-symbol topology-industry-symbol-${kind}`;
  if (kind === "switch") {
    return (
      <span className={className} aria-hidden="true">
        <svg viewBox="0 0 32 32">
          <rect x="5" y="10" width="22" height="12" rx="3" />
          <path d="M10 16h12M16 8v16M11 8l5-4 5 4M11 24l5 4 5-4" />
        </svg>
      </span>
    );
  }
  if (kind === "server") {
    return (
      <span className={className} aria-hidden="true">
        <svg viewBox="0 0 32 32">
          <rect x="5" y="7" width="22" height="18" rx="3" />
          <path d="M9 12h4M15 12h4M21 12h2M9 17h4M15 17h4M21 17h2M9 22h14" />
        </svg>
      </span>
    );
  }
  if (kind === "netapp") {
    return (
      <span className={className} aria-hidden="true">
        <svg viewBox="0 0 32 32">
          <rect x="5" y="7" width="22" height="7" rx="2" />
          <rect x="5" y="18" width="22" height="7" rx="2" />
          <path d="M10 10h3M10 21h3M19 10h3M19 21h3" />
        </svg>
      </span>
    );
  }
  if (kind === "datastore") {
    return (
      <span className={className} aria-hidden="true">
        <svg viewBox="0 0 32 32">
          <ellipse cx="16" cy="8" rx="9" ry="4" />
          <path d="M7 8v15c0 2.2 4 4 9 4s9-1.8 9-4V8M7 15c0 2.2 4 4 9 4s9-1.8 9-4" />
        </svg>
      </span>
    );
  }
  if (kind === "ilo") {
    return (
      <span className={className} aria-hidden="true">
        <svg viewBox="0 0 32 32">
          <rect x="9" y="9" width="14" height="14" rx="3" />
          <path d="M12 4v5M20 4v5M12 23v5M20 23v5M4 12h5M4 20h5M23 12h5M23 20h5" />
        </svg>
      </span>
    );
  }
  return (
    <span className={className} aria-hidden="true">
      <svg viewBox="0 0 32 32">
        <path d="M16 5l9 5-9 5-9-5 9-5Z" />
        <path d="M7 16l9 5 9-5M7 22l9 5 9-5" />
      </svg>
    </span>
  );
}

function TopologyMapNodeCard({
  className = "",
  node,
  onOpenWorkspace,
  selected
}: {
  className?: string;
  node: TopologyNode;
  onOpenWorkspace: (nodeId: string) => void;
  selected: boolean;
}) {
  const stableNodeLabel = topologyStableNodeLabel(node.id);
  return (
    <div className={`topology-node-wrap topology-node-zone-${node.zone} ${className} ${selected ? "is-selected" : ""}`}>
      <button
        aria-current={selected ? "true" : undefined}
        aria-label={`Open ${stableNodeLabel} workspace`}
        className={`topology-node topology-node-${node.tone}`}
        onClick={() => onOpenWorkspace(node.id)}
        type="button"
      >
        <span className="topology-node-title">{node.icon}<strong>{node.title}</strong></span>
        <span className="topology-node-details">{node.details}</span>
        <span className="topology-node-status-row">
          <span className="topology-node-dot" aria-hidden="true" />
          <span className="topology-node-state">{topologyNodeStateLabel(node.tone)}</span>
          {node.meta && <span className="topology-node-meta">{node.meta}</span>}
        </span>
      </button>
    </div>
  );
}

function topologyNodeStateLabel(tone: TopologyNodeTone): string {
  if (tone === "ready") return "Ready";
  if (tone === "warning") return "Blocked";
  return "Not checked";
}

function TopologyCoreButton({
  node,
  onOpenWorkspace,
  selected
}: {
  node: TopologyNode;
  onOpenWorkspace: (nodeId: string) => void;
  selected: boolean;
}) {
  const stableNodeLabel = topologyStableNodeLabel(node.id);
  return (
    <div className={`topology-core-wrap ${selected ? "is-selected" : ""}`}>
      <button
        aria-current={selected ? "true" : undefined}
        aria-label={`Open ${stableNodeLabel} workspace`}
        className={`topology-core-button topology-node-${node.tone}`}
        onClick={() => onOpenWorkspace(node.id)}
        type="button"
      >
        <span className="topology-core-label">{node.title}</span>
        <span className="topology-core-orb" aria-hidden="true">
          <span className="topology-core-tile">{node.icon}</span>
        </span>
        <span className="topology-core-status" aria-hidden="true" />
      </button>
    </div>
  );
}

function topologyStableNodeLabel(nodeId: string): string {
  if (nodeId === "cisco") return "Cisco switch";
  if (nodeId === "ilo") return "HPE iLO";
  if (nodeId === "server") return "HPE DL360 Gen10";
  if (nodeId === "netapp") return "NetApp ONTAP";
  if (nodeId === "vcenter") return "vCenter VCSA";
  return "Topology node";
}

function topologyNodeFaceplatePart(nodeId: string, netappInScope: boolean): DesignPartId {
  if (nodeId === "cisco") return "switch";
  if (nodeId === "ilo") return "ilo";
  if (nodeId === "netapp") return "netapp";
  if (nodeId === "vcenter") return "vcenter";
  if (nodeId === "datastore") return netappInScope ? "netapp" : "server-gen10";
  return "server-gen10";
}

function LabDesignComposer({
  activeProfile,
  address,
  features,
  firmwareSummaries,
  health,
  initialSelectedDevice,
  onReload,
  subnetState,
  workspaceOnly = false,
  workflowActions
}: {
  activeProfile: LabProfile | null;
  address: LabAddressPlan;
  features: LabProfileFeatures | null;
  firmwareSummaries: FirmwareSummary[];
  health?: HealthLike;
  initialSelectedDevice?: DesignPartId;
  onReload: () => Promise<void> | void;
  subnetState: TopologySubnetState;
  workspaceOnly?: boolean;
  workflowActions: WorkflowAction[];
}) {
  const committedScenario = topologyScenarioFromProfile(activeProfile, features);
  const [draftScenario, setDraftScenario] = useState<TopologyDesignScenario>(committedScenario);
  const netappInScope = draftScenario !== "single_server_local_storage";
  const vcenterInScope = draftScenario === "server_netapp_vcenter";
  const committedStorageProtocol = asString(features?.storage_protocol).toLowerCase() === "iscsi" ? "iscsi" : "nfs";
  const [draftStorageProtocol, setDraftStorageProtocol] = useState<"nfs" | "iscsi">(committedStorageProtocol);
  const storageProtocol = draftScenario === "single_server_local_storage"
    ? "local"
    : draftStorageProtocol;
  const defaultPlacements = useMemo(
    () => topologyDefaultPlacements(netappInScope, vcenterInScope, activeProfile?.devices?.server_model),
    [activeProfile?.devices?.server_model, netappInScope, vcenterInScope]
  );
  const [draftSubnetInput, setDraftSubnetInput] = useState(asString(address.subnet));
  const [draftSubnetOverride, setDraftSubnetOverride] = useState(asString(address.subnet));
  const draftSubnet = cleanNetworkNullable(draftSubnetOverride) || asString(address.subnet);
  const draftSubnetValidation = topologySubnetDraftValidation(draftSubnetInput);
  const hostNetworkPlan = useMemo(() => topologyHostNetworkPlan(health, address.subnet), [address.subnet, health]);
  const designAddress = useMemo(
    () => topologyAddressPlanForSubnet(address, draftSubnet),
    [address, draftSubnet]
  );
  const subnetPresets = useMemo(() => topologySubnetPresetOptions(address.subnet), [address.subnet]);
  const defaultDeviceSettings = useMemo(
    () => topologyDefaultDeviceSettings({ address: designAddress, netappInScope, storageProtocol, vcenterInScope }),
    [designAddress, netappInScope, storageProtocol, vcenterInScope]
  );
  const defaultLaneSettings = useMemo(
    () => topologyDefaultLaneSettings({ netappInScope, storageProtocol, vcenterInScope }),
    [netappInScope, storageProtocol, vcenterInScope]
  );
  const defaultConnectionSettings = useMemo(
    () => topologyDefaultConnectionSettings({ address: designAddress, netappInScope, storageProtocol, vcenterInScope }),
    [designAddress, netappInScope, storageProtocol, vcenterInScope]
  );
  const draftKey = topologyDesignDraftKey(activeProfile, designAddress, features, draftScenario);
  const draftProfileId = activeProfile?.id ?? "runtime";
  const [placements, setPlacements] = useState<Record<RackSlotId, DesignPartId | null>>(() =>
    topologyReadDesignDraft(draftKey, defaultPlacements)
  );
  const [deviceSettings, setDeviceSettings] = useState<DeviceSettings>(() =>
    topologyReadDeviceSettingsDraft(draftKey, defaultDeviceSettings)
  );
  const [laneSettings, setLaneSettings] = useState<LaneSettings>(() =>
    topologyReadLaneSettingsDraft(draftKey, defaultLaneSettings)
  );
  const [connectionSettings, setConnectionSettings] = useState<ConnectionSettings>(() =>
    topologyReadConnectionSettingsDraft(draftKey, defaultConnectionSettings)
  );
  const [selectedDevice, setSelectedDevice] = useState<DesignPartId>(initialSelectedDevice ?? "switch");
  const [selectedFaceplateElement, setSelectedFaceplateElement] = useState(() => workspaceOnly ? "" : "Switch port 1");
  const [selectedEditGroupId, setSelectedEditGroupId] = useState("");
  const [selectedLane, setSelectedLane] = useState<DesignLaneId>("management");
  const [selectedConnection, setSelectedConnection] = useState<DesignConnectionId>("switch-server");
  const [dropMessage, setDropMessage] = useState("Loading persisted design draft. Commit profile settings before operating hardware.");
  const [draftPersistence, setDraftPersistence] = useState<"loading" | "persisted" | "local" | "error">("loading");
  const [draftDirty, setDraftDirty] = useState(false);
  const pendingRebaseDraftKeyRef = useRef<string | null>(null);
  const [draggingPart, setDraggingPart] = useState<DesignPartId | null>(null);
  const [profileCommitStatus, setProfileCommitStatus] = useState<{ error: string; message: string; running: boolean }>({
    error: "",
    message: "",
    running: false
  });
  const [actionRunStatus, setActionRunStatus] = useState<{ error: string; message: string; runningActionId: string }>({ error: "", message: "", runningActionId: "" });
  const [actionRunsById, setActionRunsById] = useState<Record<string, WorkflowActionRun[]>>({});
  const [diagnosis, setDiagnosis] = useState<WorkflowActionDiagnosis | null>(null);
  const [diagnosisLoading, setDiagnosisLoading] = useState(false);
  const parts = topologyDesignParts({ netappInScope, vcenterInScope });
  const placedIds = new Set(Object.values(placements).filter(Boolean) as DesignPartId[]);
  const shelfParts = parts.filter((part) => !placedIds.has(part.id));
  const blueprintNodes = topologyDesignBlueprintNodes(placements, parts, deviceSettings, designAddress, storageProtocol);
  const blueprintLinks = topologyDesignBlueprintLinks({ connectionSettings, netappInScope, vcenterInScope });
  const selectedPart = parts.find((part) => part.id === selectedDevice) ?? parts[0];
  const selectedSettings = selectedPart ? deviceSettings[selectedPart.id] ?? {} : {};
  const selectedInspectorRows = selectedPart
    ? topologyDeviceInspectorRows(selectedPart.id, selectedSettings, storageProtocol)
    : [];
  const selectedSettingFields = selectedPart ? topologyDeviceSettingFields(selectedPart.id, storageProtocol) : [];
  const selectedWorkspaceSettingFields = selectedPart?.id === "netapp" && !workspaceOnly
    ? selectedSettingFields.filter((field) => field.key !== "protocol")
    : selectedSettingFields;
  const selectedPersistenceRows = selectedPart ? topologyDevicePersistenceRows(selectedPart.id, selectedSettingFields) : [];
  const selectedElementInspector = selectedPart && (!workspaceOnly || selectedFaceplateElement)
    ? topologyFaceplateElementInspector(selectedPart.id, selectedFaceplateElement, selectedSettings, storageProtocol)
    : null;
  const scenario = topologyScenarioLabel(draftScenario);
  const deploymentMode = draftScenario;
  const lanes = topologyDesignLanes({ netappInScope, vcenterInScope });
  const lanePlans = topologyDesignLanePlans({ address: designAddress, laneSettings, netappInScope, storageProtocol, vcenterInScope });
  const selectedConnectionSettings = connectionSettings[selectedConnection] ?? {};
  const addressCount = topologyDesignAddressCount(designAddress, netappInScope, vcenterInScope);
  const selectedServerPart = (Object.values(placements).includes("server-gen10plus") ? "server-gen10plus" : "server-gen10") as DesignPartId;
  const designAddressRows = topologyDesignAddressRows(designAddress, netappInScope, vcenterInScope, selectedServerPart);
  const designCablingRows = topologyDesignCablingRows(deviceSettings, netappInScope, selectedServerPart);
  const profileSyncRows = topologyProfileSyncRows({
    activeProfile,
    address: designAddress,
    deviceSettings,
    draftScenario,
    netappInScope,
    serverModel: topologyServerModelFromPart(selectedServerPart),
    storageProtocol,
    vcenterInScope
  });
  const profileSyncDriftCount = profileSyncRows.filter((row) => row.status === "draft-differs").length;
  const designReadinessRows = topologyDesignReadinessRows({
    addressCount,
    draftPersistence,
    draftSubnetValidation,
    netappInScope,
    profileSyncDriftCount,
    storageProtocol,
    vcenterInScope
  });
  const designReviewPacket = topologyDesignReviewPacket({
    addressRows: designAddressRows,
    draftScenario,
    profileSyncDriftCount,
    readinessRows: designReadinessRows,
    serverModel: topologyServerModelFromPart(selectedServerPart),
    storageProtocol,
    subnet: designAddress.subnet
  });
  const selectedSafeActions = selectedPart
    ? topologyDeviceSafeActions(selectedPart.id, workflowActions, { netappInScope, storageProtocol, vcenterInScope })
    : [];
  const selectedOverviewDetails = selectedPart
    ? topologyWorkspaceMapDetails(selectedPart.id, selectedSettings, draftScenario, storageProtocol)
    : [];
  const selectedWorkspaceSections = selectedPart
    ? topologyDeviceWorkspaceSections(selectedPart.id, selectedWorkspaceSettingFields, draftScenario, storageProtocol)
    : [];
  const selectedDetailWorkspaceSections = workspaceOnly
    ? selectedWorkspaceSections.filter((section) => section.id !== "identity")
    : selectedWorkspaceSections;
  const selectedEditWorkspaceSection = selectedDetailWorkspaceSections.find((section) => section.id === selectedEditGroupId) ?? null;
  const selectedEssentialFields = selectedPart
    ? topologyDeviceEssentialFields(selectedPart.id, selectedWorkspaceSettingFields, draftScenario, storageProtocol)
    : [];
  const selectedElementAction = selectedPart?.id === "switch"
    ? selectedSafeActions.find((action) => action.action_id === "cisco.ssh-readonly-probe") ?? null
    : null;
  const selectedElementCommands = selectedPart?.id === "switch"
    ? topologySwitchElementCommands(selectedFaceplateElement)
    : [];
  const selectedElementRun = selectedElementAction ? actionRunsById[selectedElementAction.action_id]?.[0] ?? null : null;
  const selectedElementOutput = selectedElementRun && selectedElementCommands.length
    ? topologyCommandOutputSummary(selectedElementRun.stdout_summary, selectedElementCommands)
    : [];
  const selectedElementProofState = topologySelectedElementProofState(selectedElementRun, selectedElementOutput);
  const selectedSafeActionIds = selectedSafeActions.map((action) => action.action_id).join("|");
  const profileNeedsCommit = profileSyncDriftCount > 0 || activeProfile?.source !== "saved";
  const canCommitProfileDraft = Boolean(activeProfile) && !profileCommitStatus.running && profileNeedsCommit;

  useEffect(() => {
    setDraftScenario(committedScenario);
  }, [committedScenario]);

  useEffect(() => {
    if (initialSelectedDevice) {
      setSelectedDevice(initialSelectedDevice);
    }
  }, [initialSelectedDevice]);

  useEffect(() => {
    const nextSubnet = asString(address.subnet);
    setDraftSubnetInput(nextSubnet);
    setDraftSubnetOverride(nextSubnet);
  }, [address.subnet]);

  useEffect(() => {
    setDraftStorageProtocol(committedStorageProtocol);
  }, [committedStorageProtocol, activeProfile?.id]);

  useEffect(() => {
    let ignore = false;
    setDraftPersistence("loading");
    setDraftDirty(false);
    setDropMessage("Loading persisted design draft. Commit profile settings before operating hardware.");
    api
      .topologyDesignDraft(draftProfileId, draftScenario, draftSubnet)
      .then((draft) => {
        if (ignore) return;
        const useLocalRebaseDraft = draft.source !== "saved" && pendingRebaseDraftKeyRef.current === draftKey;
        if (useLocalRebaseDraft) {
          pendingRebaseDraftKeyRef.current = null;
        }
        setPlacements(draft.source === "saved" ? topologyNormalizePlacements(draft.placements, defaultPlacements) : useLocalRebaseDraft ? topologyReadDesignDraft(draftKey, defaultPlacements) : defaultPlacements);
        setDeviceSettings(draft.source === "saved" ? topologyNormalizeDeviceSettings(draft.device_settings, defaultDeviceSettings) : useLocalRebaseDraft ? topologyReadDeviceSettingsDraft(draftKey, defaultDeviceSettings) : defaultDeviceSettings);
        setLaneSettings(draft.source === "saved" ? topologyNormalizeLaneSettings(draft.lane_settings, defaultLaneSettings) : useLocalRebaseDraft ? topologyReadLaneSettingsDraft(draftKey, defaultLaneSettings) : defaultLaneSettings);
        setConnectionSettings(draft.source === "saved" ? topologyNormalizeConnectionSettings(draft.connection_settings, defaultConnectionSettings) : useLocalRebaseDraft ? topologyReadConnectionSettingsDraft(draftKey, defaultConnectionSettings) : defaultConnectionSettings);
        setDraftPersistence(draft.source === "saved" ? "persisted" : "local");
        setDropMessage(
          draft.source === "saved"
            ? "Persistent design draft loaded. Commit profile settings before operating hardware."
            : "Scenario defaults loaded. Save a draft change to persist this layout."
        );
      })
      .catch(() => {
        if (ignore) return;
        setPlacements(topologyReadDesignDraft(draftKey, defaultPlacements));
        setDeviceSettings(topologyReadDeviceSettingsDraft(draftKey, defaultDeviceSettings));
        setLaneSettings(topologyReadLaneSettingsDraft(draftKey, defaultLaneSettings));
        setConnectionSettings(topologyReadConnectionSettingsDraft(draftKey, defaultConnectionSettings));
        setDraftPersistence("error");
        setDropMessage("Using browser-local design draft because persistent draft storage is unavailable.");
      });
    return () => {
      ignore = true;
    };
  }, [defaultConnectionSettings, defaultDeviceSettings, defaultLaneSettings, defaultPlacements, draftKey, draftProfileId, draftScenario, draftSubnet]);

  useEffect(() => {
    topologyWriteDesignDraft(draftKey, placements);
    topologyWriteDeviceSettingsDraft(draftKey, deviceSettings);
    topologyWriteLaneSettingsDraft(draftKey, laneSettings);
    topologyWriteConnectionSettingsDraft(draftKey, connectionSettings);
    if (!draftDirty) return;
    let ignore = false;
    api
      .saveTopologyDesignDraft({
        profile_id: draftProfileId,
        scenario: draftScenario,
        subnet: draftSubnet || null,
        placements,
        device_settings: deviceSettings,
        lane_settings: laneSettings,
        connection_settings: connectionSettings
      })
      .then((draft) => {
        if (ignore) return;
        setDraftPersistence("persisted");
        setDraftDirty(false);
        setDropMessage(
          `Persistent design draft saved at ${draft.updated_at ? new Date(draft.updated_at).toLocaleTimeString() : "server"}. Hardware untouched until guarded applies.`
        );
      })
      .catch(() => {
        if (ignore) return;
        setDraftPersistence("error");
        setDropMessage("Draft kept in this browser; persistent draft save failed. Hardware untouched until guarded applies.");
      });
    return () => {
      ignore = true;
    };
  }, [connectionSettings, deviceSettings, draftDirty, draftKey, draftProfileId, draftScenario, draftSubnet, laneSettings, placements]);

  useEffect(() => {
    if (selectedPart) return;
    const nextSelected = (Object.values(placements).find(Boolean) as DesignPartId | undefined) ?? "switch";
    setSelectedDevice(nextSelected);
  }, [placements, selectedPart]);

  useEffect(() => {
    setSelectedFaceplateElement(workspaceOnly ? "" : topologyDefaultFaceplateElement(selectedDevice));
  }, [selectedDevice, workspaceOnly]);

  useEffect(() => {
    setSelectedEditGroupId("");
  }, [selectedDevice, workspaceOnly]);

  useEffect(() => {
    if (blueprintLinks.some((link) => link.id === selectedConnection)) return;
    setSelectedConnection(blueprintLinks[0]?.id ?? "switch-server");
  }, [blueprintLinks, selectedConnection]);

  useEffect(() => {
    let ignore = false;
    const actionIds = selectedSafeActionIds.split("|").filter(Boolean);
    if (!actionIds.length) {
      setActionRunsById({});
      return;
    }
    Promise.all(
      actionIds.map(async (actionId) => [actionId, await safeApi(() => api.workflowActionRuns(actionId), [] as WorkflowActionRun[])] as const)
    ).then((entries) => {
      if (ignore) return;
      setActionRunsById(Object.fromEntries(entries));
    });
    return () => {
      ignore = true;
    };
  }, [selectedSafeActionIds]);

  function placePart(slot: RackSlotId, partId: DesignPartId) {
    if (!topologyCanPlacePart(partId, slot)) {
      setDropMessage(`${topologyPartLabel(partId)} cannot be placed in ${slot === "virtual" ? "VM roles" : "that rack slot"}.`);
      return;
    }
    setPlacements((current) => {
      const next = Object.fromEntries(
        Object.entries(current).map(([key, value]) => [key, value === partId ? null : value])
      ) as Record<RackSlotId, DesignPartId | null>;
      next[slot] = partId;
      return next;
    });
    setDraftDirty(true);
    setSelectedDevice(partId);
    setDropMessage(`${topologyPartLabel(partId)} placed in ${topologySlotLabel(slot)}. Draft saved locally.`);
  }

  function updateDeviceSetting(key: string, value: string) {
    if (!selectedPart) return;
    setDeviceSettings((current) => topologyUpdateDeviceSetting(current, defaultDeviceSettings, selectedPart.id, key, value));
    setDraftDirty(true);
    setDropMessage(workspaceOnly
      ? `${selectedPart.label} setup updated.`
      : `${selectedPart.label} draft updated. Hardware untouched until guarded applies.`);
  }

  function updateLaneSetting(key: string, value: string) {
    setLaneSettings((current) => topologyUpdateLaneSetting(current, defaultLaneSettings, selectedLane, key, value));
    setDraftDirty(true);
    setDropMessage(`${topologyLaneLabel(selectedLane)} draft updated. Hardware untouched until guarded applies.`);
  }

  function updateConnectionSetting(key: string, value: string) {
    setConnectionSettings((current) => topologyUpdateConnectionSetting(current, defaultConnectionSettings, selectedConnection, key, value));
    setDraftDirty(true);
    setDropMessage(`${topologyConnectionLabel(selectedConnection)} draft updated. Hardware untouched until guarded applies.`);
  }

  function resetSelectedDevice() {
    if (!selectedPart) return;
    setDeviceSettings((current) => ({
      ...topologyNormalizeDeviceSettings(current, defaultDeviceSettings),
      [selectedPart.id]: { ...(defaultDeviceSettings[selectedPart.id] ?? {}) }
    }));
    setDraftDirty(true);
    setDropMessage(`${selectedPart.label} reset to scenario defaults. Hardware untouched until guarded applies.`);
  }

  async function loadDeviceActionDiagnosis(actionId: string) {
    setDiagnosisLoading(true);
    try {
      setDiagnosis(await api.workflowActionDiagnosis(actionId));
    } catch {
      setDiagnosis(null);
    } finally {
      setDiagnosisLoading(false);
    }
  }

  async function runDeviceSafeAction(action: WorkflowAction, request?: WorkflowActionRunRequest) {
    if (!["read_only", "report_only"].includes(action.mode)) {
      setActionRunStatus({ error: "Only read-only or report-only actions can run from the visual designer.", message: "", runningActionId: "" });
      return;
    }
    setActionRunStatus({ error: "", message: "", runningActionId: action.action_id });
    setDiagnosis(null);
    try {
      const result = await api.runWorkflowAction(action.action_id, request);
      setActionRunsById((current) => ({
        ...current,
        [action.action_id]: [result, ...(current[action.action_id] ?? [])].slice(0, 5)
      }));
      setActionRunStatus({
        error: "",
        message: `${action.label}: ${displayStatus(result.status)}. ${result.summary || result.next_action}`,
        runningActionId: ""
      });
      if (isProblemRun(result)) {
        await loadDeviceActionDiagnosis(action.action_id);
      }
      await onReload();
    } catch (err) {
      setActionRunStatus({ error: errorMessage(err), message: "", runningActionId: "" });
      await loadDeviceActionDiagnosis(action.action_id);
    }
  }

  function placePartInFirstOpenSlot(partId: DesignPartId) {
    const slot = firstOpenRackSlot(placements, partId);
    if (!slot) {
      setDropMessage(`No compatible open slot for ${topologyPartLabel(partId)}.`);
      return;
    }
    placePart(slot, partId);
  }

  function resetDraft() {
    topologyClearDesignDraft(draftKey);
    topologyClearDeviceSettingsDraft(draftKey);
    topologyClearLaneSettingsDraft(draftKey);
    topologyClearConnectionSettingsDraft(draftKey);
    setPlacements(defaultPlacements);
    setDeviceSettings(defaultDeviceSettings);
    setLaneSettings(defaultLaneSettings);
    setConnectionSettings(defaultConnectionSettings);
    setDraftDirty(true);
    setDropMessage(`${topologyScenarioLabel(draftScenario)} reset to profile-derived defaults. Draft saved locally.`);
  }

  function rebaseDraftSubnet() {
    const subnet = cleanNetworkNullable(draftSubnetInput);
    if (!subnet || draftSubnetValidation.status === "error") {
      setDropMessage(draftSubnetValidation.detail);
      return;
    }
    const nextAddress = topologyAddressPlanForSubnet(address, subnet);
    pendingRebaseDraftKeyRef.current = topologyDesignDraftKey(activeProfile, nextAddress, features, draftScenario);
    setDraftSubnetOverride(subnet);
    setDeviceSettings((current) => topologyRebaseDeviceSettings(current, defaultDeviceSettings, nextAddress, storageProtocol));
    setConnectionSettings((current) => topologyRebaseConnectionSettings(current, defaultConnectionSettings, nextAddress, storageProtocol));
    setDraftDirty(true);
    setDropMessage(`Visual draft rebased to ${subnet}. Commit draft to profile when the plan looks right.`);
  }

  function updateDraftStorageProtocol(protocol: "nfs" | "iscsi") {
    setDraftStorageProtocol(protocol);
    setDeviceSettings((current) => {
      const next = topologyNormalizeDeviceSettings(current, defaultDeviceSettings);
      next.netapp = {
        ...next.netapp,
        protocol: protocol === "iscsi" ? "iSCSI primary, NFS optional" : "NFS primary, iSCSI optional"
      };
      return next;
    });
    setConnectionSettings((current) => topologyRebaseConnectionSettings(current, defaultConnectionSettings, designAddress, protocol));
    setLaneSettings((current) => topologyUpdateLaneSetting(
      current,
      defaultLaneSettings,
      "storage",
      "protocol",
      protocol === "iscsi" ? "iSCSI primary / NFS optional" : "NFS primary / iSCSI optional"
    ));
    setDraftDirty(true);
    setDropMessage(`${protocol.toUpperCase()} selected for this visual draft. Hardware untouched until guarded applies.`);
  }

  async function commitDraftToProfile() {
    if (!activeProfile) {
      setProfileCommitStatus({ error: "No active lab profile is available to update.", message: "", running: false });
      return;
    }
    if (!profileNeedsCommit) {
      setProfileCommitStatus({ error: "", message: "Profile already matches this visual draft.", running: false });
      return;
    }
    setProfileCommitStatus({ error: "", message: "", running: true });
    try {
      const payload = topologyProfilePayloadFromDraft({
        activeProfile,
        address: designAddress,
        connectionSettings,
        deviceSettings,
        draftScenario,
        laneSettings,
        placements,
        storageProtocol
      });
      if (activeProfile.source === "saved") {
        await api.updateLabProfile(activeProfile.id, payload);
      } else {
        const saved = await api.createLabProfile(payload);
        await api.activateLabProfile(saved.id);
      }
      await onReload();
      setProfileCommitStatus({
        error: "",
        message: "Visual draft committed to the saved lab profile. Runtime env and hardware remain untouched.",
        running: false
      });
      setDropMessage("Visual draft now matches saved profile intent. Run runtime apply separately when ready.");
    } catch (err) {
      setProfileCommitStatus({ error: errorMessage(err), message: "", running: false });
    }
  }

  function renderSelectedDeviceSettingRow(field: { key: string; kind?: "textarea"; label: string }, options?: { readOnlyDisplay?: boolean }) {
    if (!selectedPart) return null;
    const profilePath = topologyCommittedProfilePath(selectedPart.id, field.key);
    const profileOwned = Boolean(profilePath);
    const value = deviceSettings[selectedPart.id]?.[field.key] ?? "";
    if (options?.readOnlyDisplay || (workspaceOnly && profileOwned)) {
      return (
        <div className="design-device-setting-row is-profile-owned is-readonly-value" key={field.key}>
          <span>{field.label}</span>
          <strong>{value || "Not planned"}</strong>
        </div>
      );
    }
    return (
      <label className={`design-device-setting-row ${profileOwned ? "is-profile-owned" : "is-draft-owned"}`} key={field.key}>
        <span>{field.label}</span>
        {field.kind === "textarea" ? (
          <textarea
            readOnly={profileOwned}
            rows={2}
            value={value}
            onChange={(event) => {
              if (!profileOwned) updateDeviceSetting(field.key, event.target.value);
            }}
          />
        ) : selectedPart.id === "netapp" && field.key === "protocol" ? (
          <select
            disabled={profileOwned}
            value={storageProtocol === "iscsi" ? "iscsi" : "nfs"}
            onChange={(event) => {
              if (!profileOwned) updateDraftStorageProtocol(event.target.value === "iscsi" ? "iscsi" : "nfs");
            }}
          >
            <option value="nfs">NFS datastore path</option>
            <option value="iscsi">iSCSI block datastore path</option>
          </select>
        ) : (
          <input
            readOnly={profileOwned}
            value={value}
            onChange={(event) => {
              if (!profileOwned) updateDeviceSetting(field.key, event.target.value);
            }}
          />
        )}
        <small>
          <span className="design-provenance-chip">{profileOwned ? "Saved / derived" : "Draft only"}</span>
          {!workspaceOnly && (profileOwned ? " Profile-owned value; edit it in System Setup advanced fields." : " Visual intent only; live unknown.")}
        </small>
      </label>
    );
  }

  return (
    <div className={`lab-design-composer ${workspaceOnly ? "is-workspace-only" : ""}`} aria-label={workspaceOnly ? "Device workspace composer" : "Design mode rack composer"}>
      {!workspaceOnly && (
      <section className="design-scenario-strip" aria-label="Design setup scenarios">
        {topologyDesignScenarios().map((item) => (
          <button
            aria-pressed={draftScenario === item.id}
            className="design-scenario-card"
            key={item.id}
            onClick={() => {
              setDraftScenario(item.id);
              setDraftDirty(false);
              setDropMessage(`${item.label} selected as a local draft. Commit profile settings before operating hardware.`);
            }}
            type="button"
          >
            <strong>{item.label}</strong>
            <span>{item.detail}</span>
            {committedScenario === item.id && <em>Committed profile</em>}
          </button>
        ))}
      </section>
      )}

      {!workspaceOnly && (
      <section className="design-control-strip" aria-label="Topology draft controls">
        <div>
          <span>Scenario</span>
          <strong>{scenario}</strong>
          <small>{storageProtocol.toUpperCase()} / {displayAddress(designAddress.subnet)}</small>
        </div>
        <div>
          <span>Draft state</span>
          <strong>{topologyDraftPersistenceLabel(draftPersistence)}</strong>
          <small>{draftDirty ? "Saving draft changes" : "Persistent draft ready"}</small>
        </div>
        <div>
          <span>Profile sync</span>
          <strong>{profileSyncDriftCount ? `${profileSyncDriftCount} need commit` : "Draft matches profile"}</strong>
          <small>Commit updates saved intent only</small>
        </div>
        <button
          className="design-control-selected"
          onClick={() => {
            if (!selectedPart) return;
            setSelectedDevice(selectedPart.id);
            document.querySelector(".design-device-editor")?.scrollIntoView({ behavior: "smooth", block: "start" });
            setDropMessage(`${selectedPart.label} editor focused. Hardware untouched until guarded applies.`);
          }}
          type="button"
        >
          <span>Selected device</span>
          <strong>{selectedPart?.label ?? "None"}</strong>
          <small>Click any node, lane, address, or faceplate to edit</small>
        </button>
        <button
          className="design-control-commit"
          disabled={!canCommitProfileDraft}
          onClick={() => void commitDraftToProfile()}
          type="button"
        >
          {profileCommitStatus.running ? "Committing" : profileNeedsCommit ? "Commit visual draft" : "Profile current"}
        </button>
      </section>
      )}

      <section className={`design-visual-workbench ${workspaceOnly ? "is-workspace-only" : ""}`} aria-label={workspaceOnly ? "Selected device setup" : "Visual topology workbench"}>
        {!workspaceOnly && (
        <section
          className={`design-blueprint-stage ${selectedPart ? "has-workspace-selection" : ""} ${netappInScope ? "is-shared-storage" : "is-local-storage"}`}
          aria-label="Design topology blueprint"
        >
          <div className="design-canvas-mode-chip" aria-label="Deployment archetype">
            <strong>{draftScenario === "single_server_local_storage" ? "Single server - local RAID" : "Server + NetApp + vCenter"}</strong>
            <span>{draftScenario === "single_server_local_storage" ? "Sparse local mode" : `${storageProtocol.toUpperCase()} storage fabric`}</span>
          </div>
          <div className="design-blueprint-zone design-blueprint-zone-management" aria-hidden="true">
            <span>Management</span>
          </div>
          <div className="design-blueprint-zone design-blueprint-zone-storage" aria-hidden="true">
            <span>{netappInScope ? "Storage fabric" : "Local RAID inside server"}</span>
          </div>
          {!netappInScope && (
            <div className="design-local-raid-hero" aria-label="Local RAID design summary">
              <HardDrive size={16} />
              <div>
                <strong>One-server shipment mode</strong>
                <span>Drive bays, Smart Array, and ESXi datastore stay with the server.</span>
              </div>
            </div>
          )}
          <svg className="design-blueprint-links" viewBox="0 0 1000 380" role="img" aria-label="Draft design connections">
            {blueprintLinks.map((link) => (
              <g
                aria-label={`${link.label} connection`}
                aria-pressed={selectedConnection === link.id}
                className={`design-blueprint-link design-blueprint-link-${link.tone}`}
                key={link.id}
                onClick={() => {
                  setSelectedConnection(link.id);
                  setSelectedLane(topologyLaneFromConnection(link.id));
                }}
                onKeyDown={(event) => {
                  if (event.key !== "Enter" && event.key !== " ") return;
                  event.preventDefault();
                  setSelectedConnection(link.id);
                  setSelectedLane(topologyLaneFromConnection(link.id));
                }}
                role="button"
                tabIndex={0}
              >
                <path d={link.path} />
                <text x={link.labelX} y={link.labelY}>{link.label}</text>
              </g>
            ))}
          </svg>
          {blueprintNodes.map((node) => (
            <button
              aria-pressed={selectedDevice === node.id}
              className={`design-blueprint-node design-blueprint-node-${node.id} ${selectedDevice !== node.id ? "is-receded" : "is-selected"}`}
              draggable
              key={node.id}
              onClick={() => {
                setSelectedDevice(node.id);
                setDropMessage(`${topologyPartLabel(node.id)} workspace opened. Hardware untouched until guarded applies.`);
              }}
              onDragEnd={() => setDraggingPart(null)}
              onDragStart={(event) => {
                event.dataTransfer.effectAllowed = "move";
                event.dataTransfer.setData("text/plain", node.id);
                setDraggingPart(node.id);
              }}
              type="button"
            >
              <span className="design-blueprint-dot" aria-hidden="true" />
              <strong>{node.label}</strong>
              <small>{node.meta}</small>
              <em>{node.detail}</em>
              <span className="design-blueprint-edit-hint">Open workspace</span>
            </button>
          ))}
        </section>
        )}

        {selectedPart && (
          <section className={`design-device-workspace design-device-workspace-${selectedPart.id}`} aria-label={`${selectedPart.label} workspace`}>
            <div className="design-device-identity">
              <div className="design-device-identity-main">
                {topologyIndustryIcon(topologyWorkspaceIconKind(selectedPart.id))}
                <div>
                  <p className="operator-kicker">{workspaceOnly ? topologyDeviceWorkspaceKicker(selectedPart.id) : "Device workspace"}</p>
                  <h3>{selectedSettings.name || selectedPart.label}</h3>
                  <span>{topologyDeviceModelLabel(selectedPart.id)} / {topologyDeviceRoleLabel(selectedPart.id, draftScenario, storageProtocol)}</span>
                </div>
              </div>
              <div className="design-device-state-stack" aria-label={`${selectedPart.label} state`}>
                {workspaceOnly ? (
                  <span>
                    <strong className={`design-state-chip ${topologyWorkspaceReachabilityTone(selectedSafeActions, actionRunsById)}`}>
                      {topologyWorkspaceOperatorStateLabel(selectedSafeActions, actionRunsById)}
                    </strong>
                    <small>{topologyWorkspaceOperatorStateSource(selectedSafeActions, actionRunsById)}</small>
                  </span>
                ) : (
                  <>
                    <span>
                      <strong className={`design-state-chip ${topologyWorkspaceStateTone(draftDirty, profileSyncDriftCount, draftPersistence)}`}>
                        {topologyWorkspaceStateLabel(draftDirty, profileSyncDriftCount, draftPersistence)}
                      </strong>
                      <small>{topologyWorkspaceStateSource(draftDirty, profileSyncDriftCount, draftPersistence)}</small>
                    </span>
                    <span>
                      <strong className={`design-state-chip ${topologyWorkspaceReachabilityTone(selectedSafeActions, actionRunsById)}`}>
                        {topologyWorkspaceReachabilityLabel(selectedSafeActions, actionRunsById)}
                      </strong>
                      <small>{topologyWorkspaceReachabilitySource(selectedSafeActions, actionRunsById)}</small>
                    </span>
                  </>
                )}
              </div>
            </div>

            {!workspaceOnly && (
              <div className="design-device-hero" aria-label={`${selectedPart.label} interactive faceplate`}>
                <DesignFaceplateVisual
                  interactive
                  onElementClick={(elementLabel) => {
                    setSelectedFaceplateElement(elementLabel);
                    setDropMessage(`${selectedPart.label} ${elementLabel} selected. Inspect mapped params below; hardware untouched.`);
                  }}
                  partId={selectedPart.id}
                  selectedElement={selectedFaceplateElement}
                  settings={selectedSettings}
                  storageProtocol={storageProtocol}
                />
              </div>
            )}

            {workspaceOnly && (
              <p className="design-workspace-boundary">Checks here are read-only. Apply steps stay behind confirmations.</p>
            )}

            {!workspaceOnly && selectedOverviewDetails.length > 0 && (
              <div className="design-workspace-map-details" aria-label={`${selectedPart.label} map details`}>
                {selectedOverviewDetails.map((detail) => <span key={detail}>{detail}</span>)}
              </div>
            )}

            {!workspaceOnly && selectedPart.id === "netapp" && (
              <section className="design-primary-setting" aria-label="NetApp storage protocol">
                <div>
                  <p className="operator-kicker">Storage mode</p>
                  <h4>{storageProtocol === "iscsi" ? "iSCSI block datastore path" : "NFS datastore path"}</h4>
                  <span>Changes the LIFs, port plan, and datastore fields shown below. Draft only until committed.</span>
                </div>
                <select
                  value={storageProtocol === "iscsi" ? "iscsi" : "nfs"}
                  onChange={(event) => updateDraftStorageProtocol(event.target.value === "iscsi" ? "iscsi" : "nfs")}
                >
                  <option value="nfs">NFS datastore path</option>
                  <option value="iscsi">iSCSI block datastore path</option>
                </select>
              </section>
            )}

            {!workspaceOnly && selectedPart.id === "netapp" && (
              <NetAppWorkspaceStorageControls
                activeProfile={activeProfile}
                address={designAddress}
                onReload={onReload}
                storageProtocol={storageProtocol}
              />
            )}

            {!workspaceOnly && selectedPart.id === "switch" && (
              <CiscoWorkspaceNetworkControls
                address={designAddress}
                firmwareSummaries={firmwareSummaries}
                onReload={onReload}
                workflowActions={workflowActions}
              />
            )}

            {!workspaceOnly && (selectedPart.id === "ilo" || selectedPart.id === "server-gen10" || selectedPart.id === "server-gen10plus") && (
              <ServerWorkspaceControls
                activeProfile={activeProfile}
                address={designAddress}
                localStorageMode={draftScenario === "single_server_local_storage"}
                onReload={onReload}
                scope={selectedPart.id === "ilo" ? "ilo" : "server"}
                workflowActions={workflowActions}
              />
            )}

            {!workspaceOnly && selectedPart.id === "vcenter" && (
              <VirtualizationWorkspaceControls
                activeProfile={activeProfile}
                address={designAddress}
                features={features}
                onReload={onReload}
                workflowActions={workflowActions}
              />
            )}

            {!workspaceOnly && selectedElementInspector && (
              <section className="design-element-inspector" aria-label={`${selectedPart.label} ${selectedElementInspector.label} inspector`}>
                <div>
                  <p className="operator-kicker">Selected element</p>
                  <h4>{selectedElementInspector.label}</h4>
                  <span>{selectedElementInspector.summary}</span>
                </div>
                <div className="design-element-inspector-grid">
                  {selectedPart.id === "switch" && (
                    <div>
                      <span>Selected port state</span>
                      <strong>{selectedElementProofState.label}</strong>
                      <small>{selectedElementProofState.source}</small>
                    </div>
                  )}
                  {selectedElementInspector.rows.map((row) => (
                    <div key={row.label}>
                      <span>{row.label}</span>
                      <strong>{row.value}</strong>
                      <small>{row.source}</small>
                    </div>
                  ))}
                </div>
                <p>{selectedElementInspector.guardrail}</p>
                {selectedElementAction && selectedElementCommands.length > 0 && (
                  <div className="design-element-live-proof" aria-label={`${selectedPart.label} ${selectedElementInspector.label} read-only command output`}>
                    <div>
                      <span>Read-only command</span>
                      <strong>{selectedElementCommands.join(" | ")}</strong>
                    </div>
                    <button
                      className="design-plan-action"
                      disabled={actionRunStatus.runningActionId === selectedElementAction.action_id}
                      onClick={() => void runDeviceSafeAction(selectedElementAction, { cisco_commands: selectedElementCommands })}
                      type="button"
                    >
                      {actionRunStatus.runningActionId === selectedElementAction.action_id ? "Running show interface" : "Show interface"}
                    </button>
                    <pre className="design-terminal-output" aria-label={`${selectedPart.label} ${selectedElementInspector.label} terminal output`}>
                      {selectedElementOutput.length ? selectedElementOutput.join("\n") : "Not checked yet. Run Show interface to verify this port."}
                    </pre>
                  </div>
                )}
              </section>
            )}

            <div className="design-device-primary-action">
              {selectedSafeActions[0] ? (
                <button
                  className="design-plan-action"
                  disabled={actionRunStatus.runningActionId === selectedSafeActions[0].action_id}
                  onClick={() => void runDeviceSafeAction(selectedSafeActions[0])}
                  type="button"
                >
                  {actionRunStatus.runningActionId === selectedSafeActions[0].action_id ? "Running check" : topologyPrimaryActionLabel(selectedPart.id, selectedSafeActions[0])}
                </button>
              ) : workspaceOnly ? (
                <Link className="design-plan-action" to="/lab-defaults">Fix setup first</Link>
              ) : (
                <button className="design-plan-action" disabled type="button">No read-only test registered</button>
              )}
              <span>{workspaceOnly
                ? topologyWorkspaceOperatorHint(selectedSafeActions, designReadinessRows)
                : topologyWorkspaceNextAction(selectedSafeActions, designReadinessRows)}</span>
            </div>

            {workspaceOnly && selectedEssentialFields.length > 0 && (
              <section className="design-device-essentials" aria-label={`${selectedPart.label} essentials`}>
                <div>
                  <p className="operator-kicker">Setup</p>
                  <h4>Main settings</h4>
                </div>
                <div className="design-device-setting-rows compact">
                  {selectedEssentialFields.map((field) => renderSelectedDeviceSettingRow(field, { readOnlyDisplay: true }))}
                </div>
              </section>
            )}

            {!workspaceOnly && (
            <div className="design-device-param-sections" aria-label={`${selectedPart.label} editable parameters`}>
              {selectedWorkspaceSections.map((section) => (
                <section className="design-device-param-section" key={section.id} aria-label={`${selectedPart.label} ${section.label}`}>
                  <div>
                    <p className="operator-kicker">{section.label}</p>
                    <h4>{section.summary}</h4>
                  </div>
                  <div className="design-device-setting-rows">
                    {section.fields.map((field) => renderSelectedDeviceSettingRow(field))}
                  </div>
                </section>
              ))}
            </div>
            )}

            {workspaceOnly && (
              <details className="design-workspace-details design-workspace-details-combined" aria-label={`${selectedPart.label} details`}>
                <summary>
                  <span>Device details</span>
                </summary>
                <section className="design-device-details-inspector" aria-label={`${selectedPart.label} port and bay inspector`}>
                  <div className="design-device-hero design-device-hero-after-setup" aria-label={`${selectedPart.label} interactive faceplate`}>
                    <DesignFaceplateVisual
                      interactive
                      onElementClick={(elementLabel) => {
                        setSelectedFaceplateElement(elementLabel);
                        setDropMessage(`${selectedPart.label} ${elementLabel} selected. Inspect mapped params below; hardware untouched.`);
                      }}
                      partId={selectedPart.id}
                      selectedElement={selectedFaceplateElement}
                      settings={selectedSettings}
                      storageProtocol={storageProtocol}
                    />
                  </div>
                  {selectedElementInspector && (
                    <p className="design-selected-element-note">
                      <strong>{selectedElementInspector.label}</strong>
                      <span>{selectedElementInspector.summary}</span>
                    </p>
                  )}
                </section>

                {selectedDetailWorkspaceSections.length > 0 && (
                  <details className="design-workspace-edit-settings" aria-label={`${selectedPart.label} edit settings`}>
                    <summary>
                      <span>Edit settings</span>
                      <strong>{selectedDetailWorkspaceSections.length} setup groups</strong>
                    </summary>
                    <div className="design-device-edit-group-picker" aria-label={`${selectedPart.label} edit groups`}>
                      {selectedDetailWorkspaceSections.map((section) => (
                        <button
                          aria-pressed={selectedEditWorkspaceSection?.id === section.id}
                          className={`design-device-edit-group-button ${selectedEditWorkspaceSection?.id === section.id ? "is-selected" : ""}`}
                          key={section.id}
                          onClick={() => setSelectedEditGroupId((current) => current === section.id ? "" : section.id)}
                          type="button"
                        >
                          <span>{section.label}</span>
                          <strong>{section.fields.length} values</strong>
                        </button>
                      ))}
                    </div>
                    {selectedEditWorkspaceSection ? (
                      <section className="design-device-param-section design-device-param-panel" aria-label={`${selectedPart.label} ${selectedEditWorkspaceSection.label}`}>
                        <p>{selectedEditWorkspaceSection.summary}</p>
                        <div className="design-device-setting-rows">
                          {selectedEditWorkspaceSection.fields.map((field) => renderSelectedDeviceSettingRow(field))}
                        </div>
                      </section>
                    ) : (
                      <p className="design-device-edit-empty">Choose one setup group to edit. Saved values stay untouched until a field changes.</p>
                    )}
                  </details>
                )}

                <details className="design-workspace-advanced" aria-label={`${selectedPart.label} advanced checks and proof`}>
                  <summary>
                    <span>Advanced proof</span>
                    <strong>Read-only checks, schema homes, and diagnostics</strong>
                  </summary>

                  {selectedPart.id === "netapp" && (
                    <NetAppWorkspaceStorageControls
                      activeProfile={activeProfile}
                      address={designAddress}
                      onReload={onReload}
                      storageProtocol={storageProtocol}
                    />
                  )}

                  {selectedPart.id === "switch" && (
                    <CiscoWorkspaceNetworkControls
                      address={designAddress}
                      firmwareSummaries={firmwareSummaries}
                      onReload={onReload}
                      workflowActions={workflowActions}
                    />
                  )}

                  {(selectedPart.id === "ilo" || selectedPart.id === "server-gen10" || selectedPart.id === "server-gen10plus") && (
                    <ServerWorkspaceControls
                      activeProfile={activeProfile}
                      address={designAddress}
                      localStorageMode={draftScenario === "single_server_local_storage"}
                      onReload={onReload}
                      scope={selectedPart.id === "ilo" ? "ilo" : "server"}
                      workflowActions={workflowActions}
                    />
                  )}

                  {selectedPart.id === "vcenter" && (
                    <VirtualizationWorkspaceControls
                      activeProfile={activeProfile}
                      address={designAddress}
                      features={features}
                      onReload={onReload}
                      workflowActions={workflowActions}
                    />
                  )}

                  <section className="design-workspace-safe-strip" aria-label={`${selectedPart.label} safe checks and next actions`}>
                    <div>
                      <p className="operator-kicker">Safe checks & next actions</p>
                      <h4>Scoped to {selectedPart.label}</h4>
                    </div>
                    <div className="design-readiness-list compact">
                      <div>
                        {designReadinessRows.slice(0, 4).map((row) => (
                          <span className={`design-readiness-pill ${row.status}`} key={row.label}>
                            <strong>{row.label}</strong>
                            <small>{row.detail}</small>
                          </span>
                        ))}
                      </div>
                    </div>
                    {selectedSafeActions.length ? (
                      <div className="design-device-action-list compact">
                        {selectedSafeActions.map((action) => {
                          const running = actionRunStatus.runningActionId === action.action_id;
                          const latestRun = actionRunsById[action.action_id]?.[0] ?? null;
                          return (
                            <button
                              disabled={running}
                              key={action.action_id}
                              onClick={() => void runDeviceSafeAction(action)}
                              type="button"
                            >
                              <Play size={14} />
                              <span>{running ? "Running" : action.label}</span>
                              <small>{latestRun ? `Last: ${displayStatus(latestRun.status)}` : "Read-only check"}</small>
                            </button>
                          );
                        })}
                      </div>
                    ) : (
                      <p className="operator-action-message">No read-only check is registered for this device yet.</p>
                    )}
                    {(actionRunStatus.message || actionRunStatus.error) && (
                      <p className={actionRunStatus.error ? "operator-action-message error" : "operator-action-message success"}>
                        {actionRunStatus.error || actionRunStatus.message}
                      </p>
                    )}
                    {diagnosisLoading && <p className="operator-action-message">Preparing advisory diagnosis...</p>}
                    {diagnosis && <WorkflowDiagnosisCard diagnosis={diagnosis} />}
                  </section>

                  <details className="design-schema-inventory">
                    <summary>
                      <span>Schema homes</span>
                      <strong>{selectedPersistenceRows.length} mapped parameters</strong>
                    </summary>
                    <div className="design-schema-list" aria-label={`${selectedPart.label} schema inventory`}>
                      {selectedPersistenceRows.map((row) => (
                        <div className={`design-schema-row design-schema-row-${row.commitState}`} key={row.id}>
                          <span>{row.label}</span>
                          <strong>{row.persistsTo}</strong>
                          <small>{row.commitLabel}</small>
                        </div>
                      ))}
                    </div>
                  </details>
                </details>
              </details>
            )}

            {!workspaceOnly && (
            <section className="design-workspace-safe-strip" aria-label={`${selectedPart.label} safe checks and next actions`}>
              <div>
                <p className="operator-kicker">Safe checks & next actions</p>
                <h4>Scoped to {selectedPart.label}</h4>
              </div>
              <div className="design-readiness-list compact">
                <div>
                  {designReadinessRows.slice(0, 4).map((row) => (
                    <span className={`design-readiness-pill ${row.status}`} key={row.label}>
                      <strong>{row.label}</strong>
                      <small>{row.detail}</small>
                    </span>
                  ))}
                </div>
              </div>
              {selectedSafeActions.length ? (
                <div className="design-device-action-list compact">
                  {selectedSafeActions.map((action) => {
                    const running = actionRunStatus.runningActionId === action.action_id;
                    const latestRun = actionRunsById[action.action_id]?.[0] ?? null;
                    return (
                      <button
                        disabled={running}
                        key={action.action_id}
                        onClick={() => void runDeviceSafeAction(action)}
                        type="button"
                      >
                        <Play size={14} />
                        <span>{running ? "Running" : action.label}</span>
                        <small>{latestRun ? `Last: ${displayStatus(latestRun.status)}` : "Read-only check"}</small>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <p className="operator-action-message">No read-only check is registered for this device yet.</p>
              )}
              {(actionRunStatus.message || actionRunStatus.error) && (
                <p className={actionRunStatus.error ? "operator-action-message error" : "operator-action-message success"}>
                  {actionRunStatus.error || actionRunStatus.message}
                </p>
              )}
              {diagnosisLoading && <p className="operator-action-message">Preparing advisory diagnosis...</p>}
              {diagnosis && <WorkflowDiagnosisCard diagnosis={diagnosis} />}
            </section>
            )}

            {!workspaceOnly && (
            <details className="design-schema-inventory" open>
              <summary>
                <span>Schema homes</span>
                <strong>{selectedPersistenceRows.length} mapped parameters</strong>
              </summary>
              <div className="design-schema-list" aria-label={`${selectedPart.label} schema inventory`}>
                {selectedPersistenceRows.map((row) => (
                  <div className={`design-schema-row design-schema-row-${row.commitState}`} key={row.id}>
                    <span>{row.label}</span>
                    <strong>{row.persistsTo}</strong>
                    <small>{row.commitLabel}</small>
                  </div>
                ))}
              </div>
            </details>
            )}
          </section>
        )}
      </section>

      {!workspaceOnly && (
      <aside className="design-parts-shelf" aria-label="Parts shelf">
        <div>
          <p className="operator-kicker">Parts shelf</p>
          <h3>System pieces</h3>
        </div>
        <div className="design-part-list">
          {shelfParts.map((part) => (
            <button
              className={`design-part design-part-${part.state}`}
              draggable
              key={part.id}
              aria-label={`Add ${part.label} to topology`}
              onClick={() => {
                setSelectedDevice(part.id);
                placePartInFirstOpenSlot(part.id);
              }}
              onDragEnd={() => setDraggingPart(null)}
              onDragStart={(event) => {
                event.dataTransfer.effectAllowed = "move";
                event.dataTransfer.setData("text/plain", part.id);
                setDraggingPart(part.id);
              }}
              type="button"
            >
              <DesignFaceplateVisual
                compact
                partId={part.id}
                settings={deviceSettings[part.id] ?? {}}
                storageProtocol={storageProtocol}
              />
              <strong>{part.label}</strong>
              <small>{part.rackUnits} - {part.meta}</small>
              <em>{part.state}</em>
            </button>
          ))}
        </div>
      </aside>
      )}

      {!workspaceOnly && (
      <div className="design-rack-stage">
        <div className="design-rack-head">
          <div>
            <p className="operator-kicker">Rack A</p>
            <h3>{activeProfile?.name ?? "Draft lab"} - {displayAddress(designAddress.subnet)}</h3>
          </div>
          <StatusBadge label="Intent only" status="plan-only" />
        </div>
        <div className="design-rack" aria-label="Rack elevation">
          {topologyRackSlots().map((slot) => {
            const part = parts.find((item) => item.id === placements[slot.id]);
            const canDropDraggingPart = draggingPart ? topologyCanPlacePart(draggingPart, slot.id) : false;
            return (
              <div
                className={`design-rack-slot ${part ? "has-part" : ""} ${draggingPart ? "drag-active" : ""} ${canDropDraggingPart ? "can-drop" : ""}`}
                key={slot.id}
                onDragOver={(event) => {
                  event.preventDefault();
                  event.dataTransfer.dropEffect = canDropDraggingPart ? "move" : "none";
                }}
                onDrop={(event) => {
                  event.preventDefault();
                  const partId = event.dataTransfer.getData("text/plain") as DesignPartId;
                  if (parts.some((item) => item.id === partId) && topologyCanPlacePart(partId, slot.id)) {
                    placePart(slot.id, partId);
                  } else if (partId) {
                    setDropMessage(`${topologyPartLabel(partId)} cannot be placed in ${topologySlotLabel(slot.id)}.`);
                  }
                  setDraggingPart(null);
                }}
              >
                <span>{slot.label}</span>
                {part ? (
                  <button
                    className={`design-faceplate design-faceplate-${part.id}`}
                    draggable
                    onClick={() => setSelectedDevice(part.id)}
                    onDragEnd={() => setDraggingPart(null)}
                    onDragStart={(event) => {
                      event.dataTransfer.effectAllowed = "move";
                      event.dataTransfer.setData("text/plain", part.id);
                      setDraggingPart(part.id);
                    }}
                    type="button"
                  >
                    <DesignFaceplateVisual
                      partId={part.id}
                      settings={deviceSettings[part.id] ?? {}}
                      storageProtocol={storageProtocol}
                    />
                    <strong>{part.label}</strong>
                    <small>{designPartPrimaryDetail(part.id, deviceSettings[part.id] ?? {}, designAddress, storageProtocol)}</small>
                    <em>{part.state}</em>
                  </button>
                ) : (
                  <div className="design-empty-slot">
                    <strong>{canDropDraggingPart && draggingPart ? `Drop ${topologyPartLabel(draggingPart)} here` : slot.note}</strong>
                  </div>
                )}
              </div>
            );
          })}
        </div>
        <div className="design-lane-map" aria-label="Planned cabling lanes">
          {lanePlans.map((lane) => (
            <button
              aria-pressed={selectedLane === lane.id}
              className={`design-lane design-lane-${lane.tone}`}
              key={lane.id}
              onClick={() => setSelectedLane(lane.id)}
              type="button"
            >
              <strong>{lane.label}</strong>
              <span>{lane.path}</span>
              <small>{lane.detail}</small>
            </button>
          ))}
        </div>
      </div>
      )}

      {!workspaceOnly && (
      <aside className="design-plan-panel" aria-label="Design plan summary">
        <div>
          <p className="operator-kicker">Plan check</p>
          <h3>{scenario}</h3>
        </div>
        <dl>
          <div>
            <dt>Storage</dt>
            <dd>{storageProtocol.toUpperCase()}</dd>
          </div>
          <div>
            <dt>Mode</dt>
            <dd>{deploymentMode}</dd>
          </div>
          <div>
            <dt>Lanes</dt>
            <dd>{lanes.join(" / ")}</dd>
          </div>
          <div>
            <dt>Addresses</dt>
            <dd>{addressCount} from subnet plan</dd>
          </div>
          <div>
            <dt>Subnet</dt>
            <dd>{displayAddress(designAddress.subnet)} / {subnetState.label}</dd>
          </div>
          <div>
            <dt>Draft</dt>
            <dd>{topologyDraftPersistenceLabel(draftPersistence)}</dd>
          </div>
        </dl>
        <button
          className="design-plan-action"
          disabled={!canCommitProfileDraft}
          onClick={() => void commitDraftToProfile()}
          type="button"
        >
          {profileCommitStatus.running ? "Committing" : profileNeedsCommit ? "Commit draft to profile" : "Profile current"}
        </button>
        {netappInScope && (
          <section className="design-protocol-toggle" aria-label="Storage protocol draft">
            <span>Storage protocol</span>
            <div>
              {(["nfs", "iscsi"] as const).map((protocol) => (
                <button
                  aria-pressed={storageProtocol === protocol}
                  key={protocol}
                  onClick={() => updateDraftStorageProtocol(protocol)}
                  type="button"
                >
                  Use {protocol === "iscsi" ? "iSCSI" : "NFS"}
                </button>
              ))}
            </div>
          </section>
        )}
        <Link className="design-plan-secondary" to="/overview#system-setup">Edit system setup</Link>
        <button className="design-plan-secondary" onClick={resetDraft} type="button">Reset draft</button>
        <section className="design-subnet-rebase" aria-label="Subnet rebase">
          <label>
            <span>Draft subnet</span>
            <input
              aria-describedby="design-subnet-validation"
              value={draftSubnetInput}
              onChange={(event) => setDraftSubnetInput(event.target.value)}
              placeholder="192.168.200.0/24"
            />
          </label>
          <p
            className={`design-subnet-validation ${draftSubnetValidation.status}`}
            id="design-subnet-validation"
          >
            {draftSubnetValidation.detail}
          </p>
          <div className="design-subnet-presets" aria-label="Subnet presets">
            {subnetPresets.map((preset) => (
              <button
                key={`${preset.label}-${preset.subnet}`}
                className="design-subnet-preset"
                onClick={() => setDraftSubnetInput(preset.subnet)}
                type="button"
              >
                <strong>{preset.label}</strong>
                <span>{preset.subnet}</span>
              </button>
            ))}
          </div>
          <button className="design-plan-secondary" onClick={rebaseDraftSubnet} type="button">
            Rebase addresses
          </button>
          <div className={`design-host-network design-host-network-${subnetState.status}`} aria-label="Host network check">
            <span>{subnetState.label}</span>
            <strong>{hostNetworkPlan.hostLabel}</strong>
            <small>{subnetState.detail}</small>
            {hostNetworkPlan.suggestedSubnet && (
              <button
                className="design-plan-secondary"
                onClick={() => {
                  const nextSubnet = hostNetworkPlan.suggestedSubnet;
                  if (!nextSubnet) return;
                  setDraftSubnetInput(nextSubnet);
                  setDropMessage(`Host subnet ${nextSubnet} staged as a draft. Rebase and commit before treating it as live.`);
                }}
                type="button"
              >
                Stage host subnet
              </button>
            )}
          </div>
        </section>
        <section className="design-address-map" aria-label="Design address map">
          <div className="design-sync-head">
            <div>
              <p className="operator-kicker">Address map</p>
              <h3>Planned endpoints</h3>
            </div>
          </div>
          <div className="design-address-map-list">
            {designAddressRows.map((row) => (
              <button
                key={row.label}
                onClick={() => {
                  setSelectedDevice(row.target);
                  setDropMessage(`${row.label} selected in the device editor. Hardware untouched.`);
                }}
                type="button"
              >
                <span>{row.label}</span>
                <strong>{row.value}</strong>
              </button>
            ))}
          </div>
        </section>
        <section className="design-cabling-map" aria-label="Design cabling map">
          <div className="design-sync-head">
            <div>
              <p className="operator-kicker">Cabling map</p>
              <h3>Ports and lanes</h3>
            </div>
          </div>
          <div>
            {designCablingRows.map((row) => (
              <button
                key={row.label}
                onClick={() => {
                  setSelectedDevice(row.target);
                  setDropMessage(`${row.label} selected in the device editor. Hardware untouched.`);
                }}
                type="button"
              >
                <span>{row.label}</span>
                <strong>{row.value}</strong>
              </button>
            ))}
          </div>
        </section>
        <section className="design-readiness-list" aria-label="Design readiness checklist">
          <div className="design-sync-head">
            <div>
              <p className="operator-kicker">Readiness</p>
              <h3>Before live actions</h3>
            </div>
          </div>
          <div>
            {designReadinessRows.map((row) => (
              <span className={`design-readiness-pill ${row.status}`} key={row.label}>
                <strong>{row.label}</strong>
                <small>{row.detail}</small>
              </span>
            ))}
          </div>
        </section>
        <details className="design-review-packet">
          <summary>Review packet</summary>
          <textarea
            aria-label="Design review packet"
            readOnly
            value={designReviewPacket}
          />
        </details>
        {(profileCommitStatus.message || profileCommitStatus.error) && (
          <p className={profileCommitStatus.error ? "operator-action-message error" : "operator-action-message success"}>
            {profileCommitStatus.error || profileCommitStatus.message}
          </p>
        )}
        <section className="design-sync-preview" aria-label="Profile sync preview">
          <div className="design-sync-head">
            <div>
              <p className="operator-kicker">Profile sync</p>
              <h3>{profileSyncDriftCount ? `${profileSyncDriftCount} draft value${profileSyncDriftCount === 1 ? "" : "s"} differ` : "Draft matches profile"}</h3>
            </div>
            <StatusBadge label="No apply" status={profileSyncDriftCount ? "plan-only" : "ready"} />
          </div>
          <div className="design-sync-list">
            {profileSyncRows.map((row) => (
              <div className={`design-sync-row design-sync-row-${row.status}`} key={row.id}>
                <span>{row.label}</span>
                <strong>Draft: {row.draftValue}</strong>
                <small>Saved: {row.savedValue}</small>
              </div>
            ))}
          </div>
        </section>
        <p>{dropMessage} Hardware untouched until guarded applies.</p>
        <section className="design-connection-editor" aria-label={`${topologyConnectionLabel(selectedConnection)} editor`}>
          <div className="design-device-editor-head">
            <div>
              <p className="operator-kicker">Connection inspector</p>
              <h3>{topologyConnectionLabel(selectedConnection)}</h3>
            </div>
            <StatusBadge label="Draft only" status="plan-only" />
          </div>
          <div className="design-device-summary" aria-label={`${topologyConnectionLabel(selectedConnection)} draft summary`}>
            <div>
              <span>Lane</span>
              <strong>{selectedConnectionSettings.lane || topologyLaneFromConnection(selectedConnection)}</strong>
            </div>
            <div>
              <span>VLAN</span>
              <strong>{selectedConnectionSettings.vlan || "planned"}</strong>
            </div>
            <div>
              <span>Status</span>
              <strong>{selectedConnectionSettings.status || "planned"}</strong>
            </div>
          </div>
          <div className="design-device-fields">
            {topologyConnectionSettingFields().map((field) => (
              <label key={field.key}>
                <span>{field.label}</span>
                {field.kind === "textarea" ? (
                  <textarea
                    rows={3}
                    value={connectionSettings[selectedConnection]?.[field.key] ?? ""}
                    onChange={(event) => updateConnectionSetting(field.key, event.target.value)}
                  />
                ) : (
                  <input
                    value={connectionSettings[selectedConnection]?.[field.key] ?? ""}
                    onChange={(event) => updateConnectionSetting(field.key, event.target.value)}
                  />
                )}
              </label>
            ))}
          </div>
        </section>
        <section className="design-lane-editor" aria-label={`${topologyLaneLabel(selectedLane)} editor`}>
          <div className="design-device-editor-head">
            <div>
              <p className="operator-kicker">Lane inspector</p>
              <h3>{topologyLaneLabel(selectedLane)}</h3>
            </div>
            <StatusBadge label="Draft only" status="plan-only" />
          </div>
          <div className="design-device-fields">
            {topologyLaneSettingFields().map((field) => (
              <label key={field.key}>
                <span>{field.label}</span>
                {field.kind === "textarea" ? (
                  <textarea
                    rows={3}
                    value={laneSettings[selectedLane]?.[field.key] ?? ""}
                    onChange={(event) => updateLaneSetting(field.key, event.target.value)}
                  />
                ) : (
                  <input
                    value={laneSettings[selectedLane]?.[field.key] ?? ""}
                    onChange={(event) => updateLaneSetting(field.key, event.target.value)}
                  />
                )}
              </label>
            ))}
          </div>
        </section>
        {selectedPart && (
          <section className="design-device-editor" aria-label={`${selectedPart.label} editor`}>
            <div className="design-device-editor-head">
              <div>
                <p className="operator-kicker">Device inspector</p>
                <h3>{selectedSettings.name || selectedPart.label}</h3>
              </div>
              <StatusBadge label="Draft only" status="plan-only" />
            </div>
            <div className="design-device-summary" aria-label={`${selectedPart.label} draft summary`}>
              {selectedInspectorRows.map((row) => (
                <div key={row.label}>
                  <span>{row.label}</span>
                  <strong>{row.value}</strong>
                </div>
              ))}
            </div>
            <div className="design-device-fields">
              {selectedSettingFields.map((field) => (
                <label key={field.key}>
                  <span>{field.label}</span>
                  {field.kind === "textarea" ? (
                    <textarea
                      rows={3}
                      value={deviceSettings[selectedPart.id]?.[field.key] ?? ""}
                      onChange={(event) => updateDeviceSetting(field.key, event.target.value)}
                    />
                  ) : (
                    <input
                      value={deviceSettings[selectedPart.id]?.[field.key] ?? ""}
                      onChange={(event) => updateDeviceSetting(field.key, event.target.value)}
                    />
                  )}
                </label>
              ))}
            </div>
            <details className="design-schema-inventory" open>
              <summary>
                <span>Schema homes</span>
                <strong>{selectedPersistenceRows.length} draft parameters mapped</strong>
              </summary>
              <div className="design-schema-list" aria-label={`${selectedPart.label} schema inventory`}>
                {selectedPersistenceRows.map((row) => (
                  <div className={`design-schema-row design-schema-row-${row.commitState}`} key={row.id}>
                    <span>{row.label}</span>
                    <strong>{row.persistsTo}</strong>
                    <small>{row.commitLabel}</small>
                  </div>
                ))}
              </div>
            </details>
            <button className="design-plan-secondary" onClick={resetSelectedDevice} type="button">
              Reset this device
            </button>
            <section className="design-device-actions" aria-label={`${selectedPart.label} safe actions`}>
              <div className="design-device-actions-head">
                <div>
                  <p className="operator-kicker">Safe actions</p>
                  <h3>Validate from this device</h3>
                </div>
                <StatusBadge label="Read-only" status="ready" />
              </div>
              {selectedSafeActions.length ? (
                <div className="design-device-action-list">
                  {selectedSafeActions.map((action) => {
                    const running = actionRunStatus.runningActionId === action.action_id;
                    const latestRun = actionRunsById[action.action_id]?.[0] ?? null;
                    return (
                      <button
                        disabled={running}
                        key={action.action_id}
                        onClick={() => void runDeviceSafeAction(action)}
                        type="button"
                      >
                        <Play size={14} />
                        <span>{running ? "Running" : action.label}</span>
                        <small>{action.description}</small>
                        <em>{latestRun ? `Last: ${displayStatus(latestRun.status)} - ${formatDateTime(latestRun.finished_at || latestRun.checked_at)}` : "No run captured yet"}</em>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <p className="operator-action-message">No read-only action is registered for this visual device yet.</p>
              )}
              {(actionRunStatus.message || actionRunStatus.error) && (
                <p className={actionRunStatus.error ? "operator-action-message error" : "operator-action-message success"}>
                  {actionRunStatus.error || actionRunStatus.message}
                </p>
              )}
              {diagnosisLoading && <p className="operator-action-message">Preparing advisory diagnosis...</p>}
              {diagnosis && <WorkflowDiagnosisCard diagnosis={diagnosis} />}
            </section>
          </section>
        )}
      </aside>
      )}
    </div>
  );
}

function topologyLinks({
  datastoreStatus,
  iloStatus,
  netappInScope,
  netappStatus,
  serverStatus,
  storageProtocol,
  vmInScope,
  vmStatus
}: {
  datastoreStatus: string;
  iloStatus: string;
  netappInScope: boolean;
  netappStatus: string;
  serverStatus: string;
  storageProtocol: string;
  vmInScope: boolean;
  vmStatus: string;
}): TopologyLink[] {
  const links: TopologyLink[] = [
    {
      from: "cisco",
      id: "link-cisco-server",
      label: "mgmt 1G",
      labelX: 330,
      labelY: 392,
      path: "M 500 322 C 420 358 332 396 220 448",
      status: topologyLinkStatus(serverStatus),
      to: "server"
    },
    {
      from: "cisco",
      id: "link-cisco-ilo",
      label: "OOB / BMC",
      labelX: 635,
      labelY: 218,
      path: "M 512 286 C 566 232 628 178 725 138",
      status: topologyLinkStatus(iloStatus),
      to: "ilo"
    }
  ];
  if (vmInScope) {
    links.push({
      from: "vcenter",
      id: "link-vcenter-cisco",
      label: "vSphere API",
      labelX: 360,
      labelY: 218,
      path: "M 488 286 C 430 230 365 174 275 138",
      status: topologyLinkStatus(vmStatus, "created"),
      to: "cisco"
    });
  }
  if (netappInScope) {
    links.push(
      {
        from: "cisco",
        id: "link-cisco-netapp",
        label: "storage VLAN",
        labelX: 560,
        labelY: 508,
        path: "M 500 365 C 500 410 500 450 500 500",
        status: topologyLinkStatus(netappStatus),
        to: "netapp"
      },
      {
        from: "cisco",
        id: "link-cisco-storage-path",
        label: storageProtocol === "iscsi" ? "iSCSI 10G planned" : "NFS 10G path",
        labelX: 670,
        labelY: 384,
        path: "M 524 325 C 610 362 695 402 785 448",
        status: topologyLinkStatus(datastoreStatus, "warning"),
        to: "datastore"
      }
    );
  }
  return links;
}

function topologyDesignScenarios(): Array<{ detail: string; id: TopologyDesignScenario; label: string }> {
  return [
    {
      detail: "Shared NetApp storage, vCenter inventory, portable VM handoff.",
      id: "server_netapp_vcenter",
      label: "Server + NetApp + vCenter"
    },
    {
      detail: "ESXi talks directly to NetApp storage without vCenter in scope.",
      id: "server_netapp_direct",
      label: "Server + NetApp direct"
    },
    {
      detail: "One server ships with local ESXi datastore; NetApp out of scope.",
      id: "single_server_local_storage",
      label: "Single server local"
    }
  ];
}

function topologyScenarioFromProfile(
  activeProfile: LabProfile | null,
  features: LabProfileFeatures | null
): TopologyDesignScenario {
  const raw = asString(features?.deployment_mode) || asString(activeProfile?.profile_topology);
  if (raw === "single_server_local_storage") return "single_server_local_storage";
  if (raw === "server_netapp_direct") return "server_netapp_direct";
  return features?.vcenter_enabled === false ? "server_netapp_direct" : "server_netapp_vcenter";
}

function topologyScenarioLabel(scenario: TopologyDesignScenario): string {
  return topologyDesignScenarios().find((item) => item.id === scenario)?.label ?? scenario;
}

function topologyScenarioShortLabel(scenario: TopologyDesignScenario): string {
  if (scenario === "single_server_local_storage") return "LOCAL RAID";
  if (scenario === "server_netapp_direct") return "SRV+NETAPP";
  return "SRV+NETAPP+VCENTER";
}

function topologyDesignParts({
  netappInScope,
  vcenterInScope
}: {
  netappInScope: boolean;
  vcenterInScope: boolean;
}): DesignPart[] {
  return [
    { id: "switch", label: "Cisco switch", meta: "network control", rackUnits: "1U", state: "placed" },
    { id: "ilo", label: "HPE iLO", meta: "out-of-band mgmt", rackUnits: "BMC", state: "placed" },
    { id: "server-gen10", label: "DL360 Gen10", meta: "8 SFF bays", rackUnits: "1U", state: "placed" },
    { id: "server-gen10plus", label: "DL360 Gen10+", meta: "alternate server", rackUnits: "1U", state: "available" },
    { id: "netapp", label: "NetApp ONTAP", meta: "SAN / NAS", rackUnits: "2U", state: netappInScope ? "placed" : "draft" },
    { id: "vcenter", label: "vCenter VCSA", meta: "virtual appliance", rackUnits: "VM", state: vcenterInScope ? "placed" : "available" },
    { id: "windows", label: "Windows Server", meta: "guest role", rackUnits: "VM", state: "soon" }
  ];
}

function topologyRackSlots(): RackSlot[] {
  return [
    { id: "u1", label: "U1", note: "network shelf" },
    { id: "u2", label: "U2", note: "compute shelf" },
    { id: "u3", label: "U3-U4", note: "SAN shelf" },
    { id: "u4", label: "U5", note: "1U available" },
    { id: "virtual", label: "VM", note: "virtual roles" }
  ];
}

function topologyDefaultPlacements(
  netappInScope: boolean,
  vcenterInScope: boolean,
  serverModel?: unknown
): Record<RackSlotId, DesignPartId | null> {
  const serverPart: DesignPartId = asString(serverModel).toLowerCase() === "gen10plus" ? "server-gen10plus" : "server-gen10";
  return {
    u1: "switch",
    u2: serverPart,
    u3: netappInScope ? "netapp" : null,
    u4: null,
    virtual: vcenterInScope ? "vcenter" : null
  };
}

function topologyDefaultDeviceSettings({
  address,
  netappInScope,
  storageProtocol,
  vcenterInScope
}: {
  address: LabAddressPlan;
  netappInScope: boolean;
  storageProtocol: string;
  vcenterInScope: boolean;
}): DeviceSettings {
  const gateway = topologyGatewayFromSubnet(address.subnet);
  return {
    switch: {
      name: "Cisco C9300",
      management_ip: displayAddress(address.cisco_management),
      gateway,
      mgmt_vlan: "100",
      storage_vlan: "220",
      ports: "server mgmt, storage uplinks, NetApp e0a/e0b",
      bpdu_guard: "enabled on edge access ports",
      blackhole_vlan: "999",
      acl_lanes: "MGMT-IN, STORAGE-NFS-IN, DROP-ALL",
      port_profiles: "trunk uplinks, access mgmt, storage VLAN tagged",
      san_ports: netappInScope ? "storage ports tagged for NFS/iSCSI" : "not in scope"
    },
    ilo: {
      name: "HPE iLO",
      management_ip: displayAddress(address.ilo),
      gateway,
      credential_state: "unknown until iLO Auth Live Check runs",
      reachability: "unknown until iLO Live Check runs",
      firmware: "read by iLO Inventory",
      power_state: "read-only inventory only",
      notes: "No power, firmware flash, virtual media, RAID, or reset action is exposed here."
    },
    "server-gen10": {
      name: "HPE DL360 Gen10",
      management_ip: displayAddress(address.ilo),
      gateway,
      drive_bays: "discover with iLO / Smart Array",
      raid_controller: "Smart Array discovered",
      raid_boot: "RAID1",
      raid_data: netappInScope ? "boot/staging only; VM data on shared storage" : "RAID6 local datastore",
      storage_vlan: netappInScope ? "220" : "local",
      ports: netappInScope ? "iLO, ESXi management, storage vmkernel" : "iLO, ESXi management, local datastore"
    },
    "server-gen10plus": {
      name: "HPE DL360 Gen10+",
      management_ip: displayAddress(address.ilo),
      gateway,
      drive_bays: "discover with iLO / Smart Array",
      raid_controller: "Smart Array discovered",
      raid_boot: "RAID1",
      raid_data: netappInScope ? "boot/staging only; VM data on shared storage" : "RAID6 local datastore",
      storage_vlan: netappInScope ? "220" : "local",
      ports: netappInScope ? "iLO, ESXi management, storage vmkernel" : "iLO, ESXi management, local datastore"
    },
    netapp: {
      name: "NetApp ONTAP",
      management_ip: displayAddress(address.netapp_cluster_mgmt),
      gateway,
      storage_vlan: "220",
      protocol: storageProtocol === "iscsi" ? "iSCSI primary, NFS optional" : "NFS primary, iSCSI optional",
      nfs_lifs: address.netapp_nfs_lifs.map(displayAddress).join(", "),
      iscsi_lifs: address.netapp_iscsi_lifs.map(displayAddress).join(", "),
      controller_ports: "e0a/e0b on both controllers",
      ports: netappInScope ? "e0a/e0b on both controllers to Cisco storage VLAN" : "not in scope"
    },
    vcenter: {
      name: "vCenter VCSA",
      management_ip: displayAddress(address.ansible_control_host),
      gateway,
      datastore: netappInScope ? "NetApp datastore" : "server-local datastore",
      vm_network: "management VLAN 100",
      role: vcenterInScope ? "inventory, portability, templates" : "optional inventory"
    },
    windows: {
      name: "Windows Server",
      vm_network: "management or workload VLAN",
      role: "guest workload"
    }
  };
}

function topologyGatewayFromSubnet(subnet: string | null): string {
  const raw = asString(subnet);
  if (!raw.includes(".")) return "Not set up yet";
  const base = raw.split("/", 1)[0].split(".").slice(0, 3).join(".");
  return base ? `${base}.1` : "Not set up yet";
}

function topologyAddressPlanForSubnet(address: LabAddressPlan, subnet: string | null): LabAddressPlan {
  const base = topologySubnetBase(subnet);
  if (!base) {
    return { ...address, subnet: cleanNetworkNullable(subnet) ?? address.subnet };
  }
  return {
    ...address,
    ansible_control_host: topologyRebaseIp(address.ansible_control_host, base),
    cisco_management: topologyRebaseIp(address.cisco_management, base),
    esxi_management: topologyRebaseIp(address.esxi_management, base),
    ilo: topologyRebaseIp(address.ilo, base),
    ilo_initial: topologyRebaseIp(address.ilo_initial, base),
    netapp_cluster_mgmt: topologyRebaseIp(address.netapp_cluster_mgmt, base),
    netapp_controller_a_sp: topologyRebaseIp(address.netapp_controller_a_sp, base),
    netapp_controller_b_sp: topologyRebaseIp(address.netapp_controller_b_sp, base),
    netapp_iscsi_lifs: address.netapp_iscsi_lifs.map((value) => topologyRebaseIp(value, base)).filter(Boolean) as string[],
    netapp_nfs_lifs: address.netapp_nfs_lifs.map((value) => topologyRebaseIp(value, base)).filter(Boolean) as string[],
    netapp_node_a_mgmt: topologyRebaseIp(address.netapp_node_a_mgmt, base),
    netapp_node_b_mgmt: topologyRebaseIp(address.netapp_node_b_mgmt, base),
    netapp_svm_mgmt: topologyRebaseIp(address.netapp_svm_mgmt, base),
    server_embedded_nic: topologyRebaseIp(address.server_embedded_nic, base),
    subnet
  };
}

function topologySubnetPresetOptions(currentSubnet: string | null): Array<{ label: string; subnet: string }> {
  const candidates = [
    { label: "Current", subnet: cleanNetworkNullable(currentSubnet) || "192.168.1.0/24" },
    { label: "High 200s", subnet: "192.168.200.0/24" },
    { label: "Bench 10", subnet: "10.10.8.0/24" },
    { label: "Isolated 172", subnet: "172.16.20.0/24" }
  ];
  const seen = new Set<string>();
  return candidates.filter((candidate) => {
    const subnet = cleanNetworkNullable(candidate.subnet);
    if (!subnet || seen.has(subnet)) return false;
    seen.add(subnet);
    candidate.subnet = subnet;
    return true;
  });
}

function topologyHostNetworkPlan(health: HealthLike | undefined, currentSubnet: string | null): { hostLabel: string; suggestedSubnet: string | null } {
  const hostIps = (health?.host_ipv4_addresses ?? []).map((item) => asString(item)).filter(Boolean);
  const current = cleanNetworkNullable(currentSubnet);
  const candidateIp = hostIps.find((ip) => current ? !ipv4InCidr(ip, current) : true) ?? hostIps[0] ?? "";
  const octets = candidateIp.split(".");
  const suggestedSubnet = octets.length === 4 && octets.every((part) => /^\d+$/.test(part) && Number(part) >= 0 && Number(part) <= 255)
    ? `${octets[0]}.${octets[1]}.${octets[2]}.0/24`
    : null;
  return {
    hostLabel: hostIps.length ? hostIps.join(", ") : "No host IPv4 reported",
    suggestedSubnet
  };
}

function topologySubnetDraftValidation(value: string): { detail: string; status: "ok" | "warning" | "error" } {
  const raw = value.trim();
  if (!raw) {
    return { detail: "Enter a subnet like 192.168.200.0/24 before rebasing the visual draft.", status: "error" };
  }
  const match = raw.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\/(\d{1,2})$/);
  if (!match) {
    return { detail: "Use IPv4 CIDR notation, for example 192.168.200.0/24.", status: "error" };
  }
  const octets = match.slice(1, 5).map(Number);
  const prefix = Number(match[5]);
  if (octets.some((octet) => !Number.isInteger(octet) || octet < 0 || octet > 255)) {
    return { detail: "Each subnet octet must be between 0 and 255.", status: "error" };
  }
  if (!Number.isInteger(prefix) || prefix < 16 || prefix > 30) {
    return { detail: "Use a lab-sized IPv4 prefix from /16 through /30.", status: "error" };
  }
  if (prefix !== 24) {
    return { detail: `Valid subnet. /${prefix} is allowed, but this visual planner preserves last-octet addresses best with /24.`, status: "warning" };
  }
  return { detail: "Valid /24 subnet. Rebasing preserves the device host octets.", status: "ok" };
}

function topologyRebaseDeviceSettings(
  current: DeviceSettings,
  fallback: DeviceSettings,
  address: LabAddressPlan,
  storageProtocol: string
): DeviceSettings {
  const next = topologyNormalizeDeviceSettings(current, fallback);
  next.switch = {
    ...next.switch,
    gateway: topologyGatewayFromSubnet(address.subnet),
    management_ip: displayAddress(address.cisco_management)
  };
  for (const server of ["server-gen10", "server-gen10plus"] as const) {
    next[server] = {
      ...next[server],
      gateway: topologyGatewayFromSubnet(address.subnet),
      management_ip: displayAddress(address.ilo)
    };
  }
  next.netapp = {
    ...next.netapp,
    gateway: topologyGatewayFromSubnet(address.subnet),
    iscsi_lifs: address.netapp_iscsi_lifs.map(displayAddress).join(", "),
    management_ip: displayAddress(address.netapp_cluster_mgmt),
    nfs_lifs: address.netapp_nfs_lifs.map(displayAddress).join(", "),
    protocol: storageProtocol === "iscsi" ? "iSCSI primary, NFS optional" : "NFS primary, iSCSI optional"
  };
  next.vcenter = {
    ...next.vcenter,
    gateway: topologyGatewayFromSubnet(address.subnet),
    management_ip: displayAddress(address.ansible_control_host)
  };
  return next;
}

function topologyRebaseConnectionSettings(
  current: ConnectionSettings,
  fallback: ConnectionSettings,
  address: LabAddressPlan,
  storageProtocol: string
): ConnectionSettings {
  const next = topologyNormalizeConnectionSettings(current, fallback);
  if (next["switch-server"]) {
    next["switch-server"] = {
      ...next["switch-server"],
      source: `Cisco ${displayAddress(address.cisco_management)}`,
      target: `ESXi/iLO ${displayAddress(address.ilo)}`
    };
  }
  if (next["switch-netapp"]) {
    next["switch-netapp"] = {
      ...next["switch-netapp"],
      source: `Cisco ${displayAddress(address.cisco_management)}`,
      target: `NetApp e0a/e0b via ${displayAddress(address.netapp_cluster_mgmt)}`,
      protocol: `${storageProtocol.toUpperCase()} VLAN path`
    };
  }
  if (next["server-netapp"]) {
    const lifs = storageProtocol === "iscsi" ? address.netapp_iscsi_lifs : address.netapp_nfs_lifs;
    next["server-netapp"] = {
      ...next["server-netapp"],
      source: `ESXi vmkernel ${displayAddress(address.esxi_management)}`,
      target: `NetApp ${lifs.map(displayAddress).join(", ") || "datastore LIFs"}`,
      protocol: storageProtocol === "iscsi" ? "iSCSI datastore path" : "NFS datastore path"
    };
  }
  if (next["server-vm"]) {
    next["server-vm"] = {
      ...next["server-vm"],
      source: displayAddress(address.ansible_control_host) === "Not set up yet" ? next["server-vm"].source : `vCenter ${displayAddress(address.ansible_control_host)}`,
      target: "VM inventory"
    };
  }
  return next;
}

function topologySubnetBase(subnet: string | null): string | null {
  const raw = asString(subnet);
  if (!raw.includes(".")) return null;
  const base = raw.split("/", 1)[0].split(".").slice(0, 3).join(".");
  return base.split(".").length === 3 ? base : null;
}

function topologyRebaseIp(value: string | null, base: string): string | null {
  const raw = asString(value);
  const lastOctet = raw.split(".").pop();
  if (!lastOctet || !/^\d+$/.test(lastOctet)) return raw || null;
  const parsed = Number(lastOctet);
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 254) return raw || null;
  return `${base}.${parsed}`;
}

function topologyDefaultLaneSettings({
  netappInScope,
  storageProtocol,
  vcenterInScope
}: {
  netappInScope: boolean;
  storageProtocol: string;
  vcenterInScope: boolean;
}): LaneSettings {
  return {
    management: {
      purpose: "Device access and control plane",
      source: "Operator workstation / Cisco",
      target: vcenterInScope ? "iLO, ESXi, NetApp, vCenter" : "iLO, ESXi, NetApp",
      vlan: "100",
      mtu: "1500",
      protocol: "HTTPS, SSH, Redfish, ONTAP REST"
    },
    storage: {
      purpose: netappInScope ? "VM datastore traffic" : "Local datastore control",
      source: netappInScope ? "ESXi vmkernel" : "HPE RAID / ESXi local disks",
      target: netappInScope ? "NetApp SVM datastore LIFs" : "server-local RAID datastore",
      vlan: netappInScope ? "220" : "local",
      mtu: netappInScope ? "9000" : "1500",
      protocol: netappInScope ? (storageProtocol === "iscsi" ? "iSCSI primary / NFS optional" : "NFS primary / iSCSI optional") : "local datastore"
    },
    virtualization: {
      purpose: "Inventory, templates, and VM handoff",
      source: vcenterInScope ? "vCenter" : "direct ESXi",
      target: "VM networks and datastore inventory",
      vlan: "100",
      mtu: "1500",
      protocol: vcenterInScope ? "vSphere API, VM networks" : "ESXi host client, VM networks"
    }
  };
}

function topologyDefaultConnectionSettings({
  address,
  netappInScope,
  storageProtocol,
  vcenterInScope
}: {
  address: LabAddressPlan;
  netappInScope: boolean;
  storageProtocol: string;
  vcenterInScope: boolean;
}): ConnectionSettings {
  const storageLifs = storageProtocol === "iscsi" ? address.netapp_iscsi_lifs : address.netapp_nfs_lifs;
  const settings: Partial<ConnectionSettings> = {
    "switch-server": {
      source: `Cisco ${displayAddress(address.cisco_management)}`,
      target: `ESXi/iLO ${displayAddress(address.ilo)}`,
      lane: "management",
      vlan: "100",
      mtu: "1500",
      protocol: "management + vmkernel",
      status: "planned"
    },
    "server-vm": {
      source: vcenterInScope ? `vCenter ${displayAddress(address.ansible_control_host)}` : `ESXi ${displayAddress(address.esxi_management)}`,
      target: "VM inventory",
      lane: "virtualization",
      vlan: "100",
      mtu: "1500",
      protocol: vcenterInScope ? "vSphere API / VM network" : "direct ESXi VM network",
      status: "planned"
    }
  };
  if (netappInScope) {
    settings["switch-netapp"] = {
      source: `Cisco ${displayAddress(address.cisco_management)}`,
      target: `NetApp e0a/e0b via ${displayAddress(address.netapp_cluster_mgmt)}`,
      lane: "storage",
      vlan: "220",
      mtu: "9000",
      protocol: `${storageProtocol.toUpperCase()} VLAN path`,
      status: "planned"
    };
    settings["server-netapp"] = {
      source: `ESXi vmkernel ${displayAddress(address.esxi_management)}`,
      target: `NetApp ${storageLifs.map(displayAddress).join(", ") || "datastore LIFs"}`,
      lane: "storage",
      vlan: "220",
      mtu: "9000",
      protocol: storageProtocol === "iscsi" ? "iSCSI datastore path" : "NFS datastore path",
      status: "planned"
    };
  }
  return settings as ConnectionSettings;
}

function topologyDesignDraftKey(
  activeProfile: LabProfile | null,
  address: LabAddressPlan,
  features: LabProfileFeatures | null,
  scenario: TopologyDesignScenario
): string {
  const profileId = activeProfile?.id ?? "unsaved";
  const mode = scenario || asString(features?.deployment_mode) || asString(activeProfile?.profile_topology) || "not_set";
  return `infra-config-portal:topology-design:${profileId}:${mode}:${asString(address.subnet) || "no-subnet"}`;
}

function topologyReadDesignDraft(
  key: string,
  fallback: Record<RackSlotId, DesignPartId | null>
): Record<RackSlotId, DesignPartId | null> {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<Record<RackSlotId, DesignPartId | null>>;
    return topologyNormalizePlacements(parsed, fallback);
  } catch {
    return fallback;
  }
}

function topologyReadDeviceSettingsDraft(key: string, fallback: DeviceSettings): DeviceSettings {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(`${key}:device-settings`);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<DeviceSettings>;
    return topologyNormalizeDeviceSettings(parsed, fallback);
  } catch {
    return fallback;
  }
}

function topologyReadLaneSettingsDraft(key: string, fallback: LaneSettings): LaneSettings {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(`${key}:lane-settings`);
    if (!raw) return fallback;
    return topologyNormalizeLaneSettings(JSON.parse(raw), fallback);
  } catch {
    return fallback;
  }
}

function topologyReadConnectionSettingsDraft(key: string, fallback: ConnectionSettings): ConnectionSettings {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(`${key}:connection-settings`);
    if (!raw) return fallback;
    return topologyNormalizeConnectionSettings(JSON.parse(raw), fallback);
  } catch {
    return fallback;
  }
}

function topologyWriteDesignDraft(key: string, placements: Record<RackSlotId, DesignPartId | null>) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, JSON.stringify(placements));
  } catch {
    // Local draft persistence is a convenience; the guarded profile remains the source of truth.
  }
}

function topologyWriteLaneSettingsDraft(key: string, settings: LaneSettings) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(`${key}:lane-settings`, JSON.stringify(settings));
  } catch {
    // Local draft persistence is a convenience; the guarded profile remains the source of truth.
  }
}

function topologyWriteConnectionSettingsDraft(key: string, settings: ConnectionSettings) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(`${key}:connection-settings`, JSON.stringify(settings));
  } catch {
    // Local draft persistence is a convenience; the guarded profile remains the source of truth.
  }
}

function topologyWriteDeviceSettingsDraft(key: string, settings: DeviceSettings) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(`${key}:device-settings`, JSON.stringify(settings));
  } catch {
    // Local draft persistence is a convenience; the guarded profile remains the source of truth.
  }
}

function topologyClearDesignDraft(key: string) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    // Local draft persistence is a convenience; the guarded profile remains the source of truth.
  }
}

function topologyClearDeviceSettingsDraft(key: string) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(`${key}:device-settings`);
  } catch {
    // Local draft persistence is a convenience; the guarded profile remains the source of truth.
  }
}

function topologyClearLaneSettingsDraft(key: string) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(`${key}:lane-settings`);
  } catch {
    // Local draft persistence is a convenience; the guarded profile remains the source of truth.
  }
}

function topologyClearConnectionSettingsDraft(key: string) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(`${key}:connection-settings`);
  } catch {
    // Local draft persistence is a convenience; the guarded profile remains the source of truth.
  }
}

function topologyNormalizePlacements(
  draft: Partial<Record<RackSlotId, DesignPartId | null>>,
  fallback: Record<RackSlotId, DesignPartId | null>
): Record<RackSlotId, DesignPartId | null> {
  const next: Record<RackSlotId, DesignPartId | null> = {
    u1: null,
    u2: null,
    u3: null,
    u4: null,
    virtual: null
  };
  const seen = new Set<DesignPartId>();
  for (const slot of topologyRackSlots()) {
    const partId = draft[slot.id];
    if (partId && topologyKnownDesignPart(partId) && topologyCanPlacePart(partId, slot.id) && !seen.has(partId)) {
      next[slot.id] = partId;
      seen.add(partId);
    } else if (partId === null) {
      next[slot.id] = null;
    }
  }
  for (const slot of topologyRackSlots()) {
    const fallbackPart = fallback[slot.id];
    if (!next[slot.id] && fallbackPart && !seen.has(fallbackPart) && topologyCanPlacePart(fallbackPart, slot.id)) {
      next[slot.id] = fallbackPart;
      seen.add(fallbackPart);
    }
  }
  return next;
}

function topologyNormalizeDeviceSettings(
  draft: Partial<DeviceSettings> | Record<string, Record<string, string>> | undefined,
  fallback: DeviceSettings
): DeviceSettings {
  const next = structuredClone(fallback) as DeviceSettings;
  if (!draft || typeof draft !== "object") return next;
  for (const part of topologyKnownDeviceParts()) {
    const rawSettings = draft[part];
    if (!rawSettings || typeof rawSettings !== "object") continue;
    for (const field of topologyDeviceSettingFields(part, "nfs")) {
      const value = rawSettings[field.key];
      if (typeof value === "string") {
        next[part][field.key] = value.slice(0, field.kind === "textarea" ? 240 : 160);
      }
    }
  }
  return next;
}

function topologyNormalizeLaneSettings(
  draft: Partial<LaneSettings> | Record<string, Record<string, string>> | undefined,
  fallback: LaneSettings
): LaneSettings {
  const next = structuredClone(fallback) as LaneSettings;
  if (!draft || typeof draft !== "object") return next;
  for (const lane of topologyKnownLanes()) {
    const rawSettings = draft[lane];
    if (!rawSettings || typeof rawSettings !== "object") continue;
    for (const field of topologyLaneSettingFields()) {
      const value = rawSettings[field.key];
      if (typeof value === "string") {
        next[lane][field.key] = value.slice(0, field.kind === "textarea" ? 240 : 160);
      }
    }
  }
  return next;
}

function topologyNormalizeConnectionSettings(
  draft: Partial<ConnectionSettings> | Record<string, Record<string, string>> | undefined,
  fallback: ConnectionSettings
): ConnectionSettings {
  const next = structuredClone(fallback) as ConnectionSettings;
  if (!draft || typeof draft !== "object") return next;
  for (const connection of topologyKnownConnections()) {
    if (!(connection in fallback)) continue;
    const rawSettings = draft[connection];
    if (!rawSettings || typeof rawSettings !== "object") continue;
    for (const field of topologyConnectionSettingFields()) {
      const value = rawSettings[field.key];
      if (typeof value === "string") {
        next[connection][field.key] = value.slice(0, field.kind === "textarea" ? 240 : 160);
      }
    }
  }
  return next;
}

function topologyUpdateLaneSetting(
  current: LaneSettings,
  fallback: LaneSettings,
  laneId: DesignLaneId,
  key: string,
  value: string
): LaneSettings {
  const next = topologyNormalizeLaneSettings(current, fallback);
  next[laneId] = { ...next[laneId], [key]: value.slice(0, key === "notes" ? 240 : 160) };
  return next;
}

function topologyUpdateConnectionSetting(
  current: ConnectionSettings,
  fallback: ConnectionSettings,
  connectionId: DesignConnectionId,
  key: string,
  value: string
): ConnectionSettings {
  const next = topologyNormalizeConnectionSettings(current, fallback);
  next[connectionId] = { ...next[connectionId], [key]: value.slice(0, key === "notes" ? 240 : 160) };
  return next;
}

function topologyUpdateDeviceSetting(
  current: DeviceSettings,
  fallback: DeviceSettings,
  partId: DesignPartId,
  key: string,
  value: string
): DeviceSettings {
  const next = topologyNormalizeDeviceSettings(current, fallback);
  next[partId] = { ...next[partId], [key]: value.slice(0, key === "notes" ? 240 : 160) };
  return next;
}

function firstOpenRackSlot(placements: Record<RackSlotId, DesignPartId | null>, partId: DesignPartId): RackSlotId | null {
  return topologyRackSlots().find((slot) => topologyCanPlacePart(partId, slot.id) && !placements[slot.id])?.id ?? null;
}

function topologyCanPlacePart(partId: DesignPartId, slot: RackSlotId): boolean {
  if (partId === "vcenter" || partId === "windows") return slot === "virtual";
  if (slot === "virtual") return false;
  if (partId === "ilo") return slot === "u1";
  if (partId === "netapp") return slot === "u3";
  return true;
}

function topologyKnownDesignPart(value: string): value is DesignPartId {
  return ["switch", "ilo", "server-gen10", "server-gen10plus", "netapp", "vcenter", "windows"].includes(value);
}

function topologyKnownDeviceParts(): DesignPartId[] {
  return ["switch", "ilo", "server-gen10", "server-gen10plus", "netapp", "vcenter", "windows"];
}

function topologyKnownLanes(): DesignLaneId[] {
  return ["management", "storage", "virtualization"];
}

function topologyKnownConnections(): DesignConnectionId[] {
  return ["switch-server", "switch-netapp", "server-netapp", "server-vm"];
}

function topologyLaneSettingFields(): Array<{ key: string; kind?: "textarea"; label: string }> {
  return [
    { key: "purpose", label: "Purpose" },
    { key: "source", label: "Source" },
    { key: "target", label: "Target" },
    { key: "vlan", label: "VLAN" },
    { key: "mtu", label: "MTU" },
    { key: "protocol", label: "Protocol" },
    { key: "notes", kind: "textarea", label: "Notes" }
  ];
}

function topologyConnectionSettingFields(): Array<{ key: string; kind?: "textarea"; label: string }> {
  return [
    { key: "source", label: "Source" },
    { key: "target", label: "Target" },
    { key: "lane", label: "Lane" },
    { key: "vlan", label: "VLAN" },
    { key: "mtu", label: "MTU" },
    { key: "protocol", label: "Protocol" },
    { key: "status", label: "Status" },
    { key: "notes", kind: "textarea", label: "Notes" }
  ];
}

function topologyPartLabel(partId: DesignPartId): string {
  return topologyDesignParts({ netappInScope: true, vcenterInScope: true }).find((part) => part.id === partId)?.label ?? partId;
}

function topologySlotLabel(slot: RackSlotId): string {
  return topologyRackSlots().find((item) => item.id === slot)?.label ?? slot;
}

function topologyLaneLabel(lane: DesignLaneId): string {
  if (lane === "management") return "Management lane";
  if (lane === "storage") return "Storage / SAN lane";
  return "Virtualization lane";
}

function topologyConnectionLabel(connection: DesignConnectionId): string {
  if (connection === "switch-server") return "Switch to server";
  if (connection === "switch-netapp") return "Switch to NetApp";
  if (connection === "server-netapp") return "Server to NetApp";
  return "Server to VM layer";
}

function topologyLaneFromConnection(connection: DesignConnectionId): DesignLaneId {
  if (connection === "switch-netapp" || connection === "server-netapp") return "storage";
  if (connection === "server-vm") return "virtualization";
  return "management";
}

function topologyDraftPersistenceLabel(value: "loading" | "persisted" | "local" | "error"): string {
  if (value === "persisted") return "Persisted draft";
  if (value === "local") return "Local defaults";
  if (value === "error") return "Browser fallback";
  return "Loading draft";
}

function topologyWorkspaceStateLabel(
  draftDirty: boolean,
  profileSyncDriftCount: number,
  persistence: "loading" | "persisted" | "local" | "error"
): string {
  if (draftDirty) return "Draft";
  if (profileSyncDriftCount > 0) return "Draft differs";
  if (persistence === "persisted") return "Saved";
  return "Draft";
}

function topologyWorkspaceStateTone(
  draftDirty: boolean,
  profileSyncDriftCount: number,
  persistence: "loading" | "persisted" | "local" | "error"
): string {
  if (draftDirty || profileSyncDriftCount > 0 || persistence !== "persisted") return "draft";
  return "saved";
}

function topologyWorkspaceStateSource(
  draftDirty: boolean,
  profileSyncDriftCount: number,
  persistence: "loading" | "persisted" | "local" | "error"
): string {
  if (draftDirty) return "source: unsaved browser edit";
  if (profileSyncDriftCount > 0) return "source: profile drift";
  if (persistence === "persisted") return "source: persisted design draft";
  if (persistence === "loading") return "source: loading draft store";
  if (persistence === "error") return "source: browser fallback";
  return "source: local draft defaults";
}

function topologyWorkspaceReachabilityLabel(
  actions: WorkflowAction[],
  runsById: Record<string, WorkflowActionRun[]>
): string {
  const latestRun = actions.map((action) => runsById[action.action_id]?.[0]).find(Boolean);
  if (!latestRun) return "Reachability unknown";
  const status = displayStatus(latestRun.status).toLowerCase();
  return /ready|ok|success|passed|completed/.test(status) ? "Reachable by last test" : "Reachability needs review";
}

function topologyWorkspaceReachabilitySource(
  actions: WorkflowAction[],
  runsById: Record<string, WorkflowActionRun[]>
): string {
  const latestAction = actions.find((action) => runsById[action.action_id]?.[0]);
  if (latestAction) return `source: last ${latestAction.label}`;
  if (!actions.length) return "source: no registered proof";
  return "source: no read-only run yet";
}

function topologyWorkspaceOperatorStateLabel(
  actions: WorkflowAction[],
  runsById: Record<string, WorkflowActionRun[]>
): string {
  const latestRun = actions.map((action) => runsById[action.action_id]?.[0]).find(Boolean);
  if (!latestRun) return "Not checked";
  const status = displayStatus(latestRun.status).toLowerCase();
  return /ready|ok|success|passed|completed/.test(status) ? "Reachable" : "Needs review";
}

function topologyWorkspaceOperatorStateSource(
  actions: WorkflowAction[],
  runsById: Record<string, WorkflowActionRun[]>
): string {
  const latestAction = actions.find((action) => runsById[action.action_id]?.[0]);
  if (latestAction) return `Last check: ${latestAction.label}`;
  if (!actions.length) return "No read-only check yet";
  return "Run a check to verify";
}

function topologyWorkspaceReachabilityTone(
  actions: WorkflowAction[],
  runsById: Record<string, WorkflowActionRun[]>
): string {
  const label = topologyWorkspaceReachabilityLabel(actions, runsById);
  if (label.includes("Reachable")) return "live";
  if (label.includes("review")) return "warning";
  return "unknown";
}

function topologyWorkspaceNextAction(actions: WorkflowAction[], readinessRows: Array<{ detail: string; label: string; status: string }>): string {
  if (actions[0]) return `${actions[0].label} is the next read-only check.`;
  const issue = readinessRows.find((row) => row.status !== "ready");
  return issue ? `${issue.label}: ${issue.detail}` : "Review profile sync, then run Validation.";
}

function topologyWorkspaceOperatorHint(actions: WorkflowAction[], readinessRows: Array<{ detail: string; label: string; status: string }>): string {
  if (actions[0]) return "Run this check when ready.";
  const issue = readinessRows.find((row) => row.status !== "ready");
  if (!issue) return "Open Validation when setup looks right.";
  if (/draft store/i.test(issue.label)) {
    return /loading/i.test(issue.detail) ? "Loading setup." : "Finish setup first.";
  }
  if (/profile sync/i.test(issue.label)) return "Save setup before checks.";
  return "Finish setup first.";
}

function topologyDeviceModelLabel(partId: DesignPartId): string {
  if (partId === "ilo") return "HPE iLO";
  if (partId === "server-gen10") return "HPE DL360 Gen10";
  if (partId === "server-gen10plus") return "HPE DL360 Gen10+";
  if (partId === "switch") return "Cisco Catalyst";
  if (partId === "netapp") return "NetApp ONTAP";
  if (partId === "vcenter") return "VMware VCSA";
  return "Windows Server";
}

function topologyDeviceRoleLabel(partId: DesignPartId, scenario: TopologyDesignScenario, storageProtocol: string): string {
  if (partId === "switch") return "fabric and VLAN control";
  if (partId === "ilo") return "out-of-band server management";
  if (partId === "server-gen10" || partId === "server-gen10plus") {
    return scenario === "single_server_local_storage" ? "ESXi with local RAID" : `ESXi ${storageProtocol.toUpperCase()} consumer`;
  }
  if (partId === "netapp") return `${storageProtocol.toUpperCase()} shared storage`;
  if (partId === "vcenter") return "inventory and portability";
  return "guest workload";
}

function topologyDeviceWorkspaceKicker(partId: DesignPartId): string {
  if (partId === "switch") return "Network";
  if (partId === "ilo") return "Server access";
  if (partId === "server-gen10" || partId === "server-gen10plus") return "Compute";
  if (partId === "netapp") return "Storage";
  if (partId === "vcenter") return "Virtualization";
  return "Device";
}

function topologyWorkspaceMapDetails(
  partId: DesignPartId,
  settings: Record<string, string>,
  scenario: TopologyDesignScenario,
  storageProtocol: string
): string[] {
  if (partId === "switch") {
    return [
      "L3 core switch",
      `VLAN ${settings.storage_vlan || "220"}`
    ];
  }
  if (partId === "ilo") return ["BMC read-only checks"];
  if (partId === "vcenter") {
    return scenario === "single_server_local_storage"
      ? ["Direct host management", "direct host path"]
      : ["NetApp datastore", `${storageProtocol.toUpperCase()} storage path`];
  }
  if (partId === "netapp") return ["NetApp datastore", `${storageProtocol.toUpperCase()} fabric`];
  return [];
}

function topologyDeviceWorkspaceSections(
  partId: DesignPartId,
  fields: Array<{ key: string; kind?: "textarea"; label: string }>,
  scenario: TopologyDesignScenario,
  storageProtocol: string
): Array<{ fields: Array<{ key: string; kind?: "textarea"; label: string }>; id: string; label: string; summary: string }> {
  const pick = (keys: string[]) => fields.filter((field) => keys.includes(field.key));
  const sections = [
    { id: "identity", label: "Identity", summary: "Name, model, and role", keys: ["name", "role"] },
    { id: "network", label: "Network", summary: "IP, gateway, VLANs, and ports", keys: ["management_ip", "gateway", "mgmt_vlan", "storage_vlan", "ports", "port_profiles", "san_ports", "controller_ports", "vm_network"] },
    { id: "storage", label: "Storage", summary: scenario === "single_server_local_storage" ? "Local RAID and drive layout" : `${storageProtocol.toUpperCase()} datastore path`, keys: ["drive_bays", "raid_controller", "raid_boot", "raid_data", "protocol", "nfs_lifs", "iscsi_lifs", "datastore"] },
    { id: "access", label: "Access", summary: "Credential state and guardrail notes", keys: ["credential_state", "reachability", "firmware", "power_state", "bpdu_guard", "blackhole_vlan", "acl_lanes", "notes"] }
  ];
  return sections
    .map((section) => ({
      fields: pick(section.keys),
      id: section.id,
      label: section.label,
      summary: section.summary
    }))
    .filter((section) => section.fields.length > 0);
}

function topologyDeviceEssentialFields(
  partId: DesignPartId,
  fields: Array<{ key: string; kind?: "textarea"; label: string }>,
  scenario: TopologyDesignScenario,
  storageProtocol: string
): Array<{ key: string; kind?: "textarea"; label: string }> {
  const preferredKeys: Partial<Record<DesignPartId, string[]>> = {
    switch: ["management_ip", "mgmt_vlan", "storage_vlan"],
    ilo: ["management_ip"],
    "server-gen10": scenario === "single_server_local_storage"
      ? ["management_ip", "raid_controller", "raid_data"]
      : ["management_ip", "storage_vlan"],
    "server-gen10plus": scenario === "single_server_local_storage"
      ? ["management_ip", "raid_controller", "raid_data"]
      : ["management_ip", "storage_vlan"],
    netapp: storageProtocol === "iscsi"
      ? ["management_ip", "protocol", "iscsi_lifs"]
      : ["management_ip", "protocol", "nfs_lifs"],
    vcenter: ["management_ip", "datastore"],
    windows: ["vm_network", "role"]
  };
  const priority = preferredKeys[partId] ?? [];
  const picked = priority
    .map((key) => fields.find((field) => field.key === key))
    .filter((field): field is { key: string; kind?: "textarea"; label: string } => Boolean(field));
  return (picked.length ? picked : fields).slice(0, 5);
}

function topologyDefaultFaceplateElement(partId: DesignPartId): string {
  if (partId === "switch") return "Switch port 1";
  if (partId === "ilo") return "Management NIC";
  if (partId === "server-gen10" || partId === "server-gen10plus") return "Drive bay 1";
  if (partId === "netapp") return "controller ports";
  if (partId === "vcenter") return "vCenter appliance";
  return "Windows VM";
}

function topologySwitchElementCommands(elementLabel: string): string[] {
  const match = asString(elementLabel).match(/port\s+(\d+)/i);
  const portNumber = match ? Number(match[1]) : NaN;
  if (!Number.isInteger(portNumber) || portNumber < 1 || portNumber > 48) return [];
  const interfaceName = `Gi1/0/${portNumber}`;
  return [`show interface ${interfaceName}`, `show running-config interface ${interfaceName}`, "show interfaces status"];
}

function topologyCommandOutputSummary(stdoutSummary: string | null | undefined, commands: string[]): string[] {
  const raw = asString(stdoutSummary);
  if (!raw) return [];
  const wanted = new Set(commands.map((command) => command.toLowerCase()));
  try {
    const parsed = JSON.parse(raw) as { command_evidence?: Record<string, { captured?: boolean; stdout_summary?: unknown }> };
    const evidence = parsed.command_evidence && typeof parsed.command_evidence === "object" ? parsed.command_evidence : {};
    const lines: string[] = [];
    const fallbackLines: string[] = [];
    for (const [command, result] of Object.entries(evidence)) {
      const target = wanted.has(command.toLowerCase()) ? lines : fallbackLines;
      target.push(`$ ${command}`);
      const summaryLines = Array.isArray(result.stdout_summary) ? result.stdout_summary.map((line) => asString(line)).filter(Boolean) : [];
      target.push(...(summaryLines.length ? summaryLines : [result.captured ? "Captured; command summary unavailable." : "No connection - port output not captured."]));
    }
    return lines.length ? lines : fallbackLines.length ? fallbackLines : ["No connection or configured port state captured for this port."];
  } catch {
    const lines = raw.split(/\r?\n/).filter(Boolean).slice(0, 16);
    return lines.length ? lines : ["No connection or configured port state captured for this port."];
  }
}

function topologySelectedElementProofState(
  run: WorkflowActionRun | null,
  output: string[]
): { label: string; source: string } {
  if (!run) {
    return {
      label: "Not checked yet",
      source: "read-only proof pending"
    };
  }
  if (isProblemRun(run)) {
    return {
      label: `Check failed - ${displayStatus(run.status)}`,
      source: run.summary || run.next_action || "workflow action result"
    };
  }
  const hasCapturedOutput = output.some((line) => {
    const normalized = line.toLowerCase();
    return Boolean(normalized) &&
      !normalized.startsWith("$ ") &&
      !normalized.includes("no connection") &&
      !normalized.includes("not captured");
  });
  return hasCapturedOutput
    ? { label: "Read-only state captured", source: "workflow action result" }
    : { label: "No connection detected", source: "read-only command returned no port state" };
}

function topologyPrimaryActionLabel(partId: DesignPartId, action: WorkflowAction): string {
  if (partId === "switch" && action.action_id === "cisco.ssh-readonly-probe") return "Run Cisco read-only check";
  if (partId === "ilo") return "Run iLO read-only check";
  if (partId === "netapp") return "Run NetApp read-only check";
  return `Test ${topologyPartLabel(partId)}`;
}

function topologyFaceplateElementInspector(
  partId: DesignPartId,
  elementLabel: string,
  settings: Record<string, string>,
  storageProtocol: string
): {
  guardrail: string;
  label: string;
  rows: Array<{ label: string; source: string; value: string }>;
  summary: string;
} {
  const label = elementLabel || topologyDefaultFaceplateElement(partId);
  if (partId === "switch") {
    return {
      guardrail: "Read-only Cisco checks can prove port/VLAN state. Any config apply remains outside this workspace.",
      label,
      rows: [
        { label: "Port plan", value: settings.ports || "server mgmt, storage uplinks, NetApp e0a/e0b", source: "device_settings.switch.ports" },
        { label: "Port profiles", value: settings.port_profiles || "trunk uplinks, access mgmt, storage VLAN tagged", source: "device_settings.switch.port_profiles" },
        { label: "VLAN intent", value: `mgmt ${settings.mgmt_vlan || "100"} / storage ${settings.storage_vlan || "220"}`, source: "device_settings.switch.mgmt_vlan + storage_vlan" },
        { label: "Live proof", value: "Cisco SSH read-only probe or firmware inventory", source: "workflow action result" }
      ],
      summary: "Shows what this port should carry and which VLAN lane it belongs to."
    };
  }
  if (partId === "ilo") {
    return {
      guardrail: "iLO power, virtual media, firmware flash, RAID configuration, and reset actions are not exposed here. This workspace only runs read-only checks.",
      label,
      rows: [
        { label: "iLO IP", value: settings.management_ip || "not planned", source: "address_plan.ilo" },
        { label: "Credential status", value: settings.credential_state || "unknown until iLO Auth Live Check runs", source: "secret-safe credential check" },
        { label: "Reachability", value: settings.reachability || "unknown until iLO Live Check runs", source: "workflow action result" },
        { label: "Inventory proof", value: settings.firmware || "read by iLO Inventory", source: "ilo.inventory" }
      ],
      summary: "Shows the management address and whether sign-in still needs attention."
    };
  }
  if (partId === "server-gen10" || partId === "server-gen10plus") {
    return {
      guardrail: "RAID apply and server reset are not exposed here. This inspector only maps the visible bay to saved RAID intent and read-only iLO proof.",
      label,
      rows: [
        { label: "Drive inventory", value: settings.drive_bays || "discover with iLO / Smart Array", source: `device_settings.${partId}.drive_bays` },
        { label: "RAID controller", value: settings.raid_controller || "Smart Array discovered", source: `device_settings.${partId}.raid_controller` },
        { label: "Boot RAID", value: settings.raid_boot || "RAID1", source: `device_settings.${partId}.raid_boot` },
        { label: "Data RAID", value: settings.raid_data || "RAID6 local datastore", source: `device_settings.${partId}.raid_data` }
      ],
      summary: "Shows this bay's saved RAID role and local datastore plan."
    };
  }
  if (partId === "netapp") {
    return {
      guardrail: "ONTAP setup, NFS/iSCSI creation, and factory reset stay behind their existing guarded flows.",
      label,
      rows: [
        { label: "Controller ports", value: settings.controller_ports || "e0a/e0b on both controllers", source: "device_settings.netapp.controller_ports" },
        { label: "Protocol", value: settings.protocol || `${storageProtocol.toUpperCase()} primary`, source: "device_settings.netapp.protocol + profile features" },
        { label: "NFS LIFs", value: settings.nfs_lifs || "not planned", source: "address_plan.netapp_nfs_lifs" },
        { label: "iSCSI LIFs", value: settings.iscsi_lifs || "not planned", source: "address_plan.netapp_iscsi_lifs" }
      ],
      summary: "Shows how this controller port fits the shared storage path."
    };
  }
  if (partId === "vcenter") {
    return {
      guardrail: "vCenter install and attach actions remain guarded workflows; this element only inspects saved VM and datastore intent.",
      label,
      rows: [
        { label: "Datastore", value: settings.datastore || "NetApp datastore", source: "device_settings.vcenter.datastore" },
        { label: "VM network", value: settings.vm_network || "management VLAN 100", source: "device_settings.vcenter.vm_network" },
        { label: "Role", value: settings.role || "inventory and portability", source: "device_settings.vcenter.role" }
      ],
      summary: "Shows where this appliance should live and which network it uses."
    };
  }
  return {
    guardrail: "Guest deployment remains a planned intent until the existing validation workflow proves readiness.",
    label,
    rows: [
      { label: "VM network", value: settings.vm_network || "management or workload VLAN", source: "device_settings.windows.vm_network" },
      { label: "Role", value: settings.role || "guest workload", source: "device_settings.windows.role" }
    ],
    summary: "Shows the guest network and workload role."
  };
}

function DesignFaceplateVisual({
  compact = false,
  interactive = false,
  onElementClick,
  partId,
  selectedElement = "",
  settings,
  storageProtocol
}: {
  compact?: boolean;
  interactive?: boolean;
  onElementClick?: (elementLabel: string) => void;
  partId: DesignPartId;
  selectedElement?: string;
  settings: Record<string, string>;
  storageProtocol: string;
}) {
  if (partId === "switch") {
    const portPlan = settings.ports || "management, server, storage uplinks";
    const storageVlan = settings.storage_vlan || "storage";
    const ports = Array.from({ length: compact ? 8 : 16 }, (_, index) => index + 1);
    return (
      <span className="design-faceplate-art design-faceplate-switch-art" aria-hidden={interactive ? undefined : true} title={portPlan}>
        <span className="design-led-strip">
          <span className="design-led design-led-unknown" />
          <span className="design-led design-led-plan" />
        </span>
        <span className="design-switch-ports">
          {ports.map((port) => (
            interactive ? (
              <button
                className={`design-switch-port ${selectedElement === `port ${port}` || selectedElement === `Switch port ${port}` ? "selected" : ""}`}
                key={port}
                onClick={() => onElementClick?.(`port ${port}`)}
                type="button"
                aria-label={`Switch port ${port}`}
              >
                <span>{port}</span>
              </button>
            ) : (
              <span className="design-switch-port" key={port}><span>{port}</span></span>
            )
          ))}
        </span>
        <span className="design-faceplate-chip">VLAN {storageVlan}</span>
      </span>
    );
  }
  if (partId === "server-gen10" || partId === "server-gen10plus") {
    const bayCount = clampNumber(parseFirstInteger(settings.drive_bays), 4, compact ? 8 : 12, 8);
    const bayLabels = Array.from({ length: bayCount }, (_, index) => index + 1);
    return (
      <span className="design-faceplate-art design-faceplate-server-art" aria-hidden={interactive ? undefined : true} title={settings.drive_bays || "Drive bay plan"}>
        <span className="design-led-strip">
          <span className="design-led design-led-unknown" />
          <span className="design-led design-led-plan" />
          <span className="design-led design-led-draft" />
        </span>
        <span className="design-drive-bays">
          {bayLabels.map((bay) => (
            interactive ? (
              <button className="design-faceplate-bay" key={bay} onClick={() => onElementClick?.(`drive bay ${bay}`)} type="button" aria-label={`Drive bay ${bay}`} />
            ) : (
              <span className="design-faceplate-bay" key={bay} />
            )
          ))}
        </span>
        <span className="design-faceplate-chip">{settings.raid_boot || "RAID1"} / {settings.raid_data || "data"}</span>
      </span>
    );
  }
  if (partId === "netapp") {
    const ports = splitFaceplateTokens(settings.controller_ports || "e0a, e0b").slice(0, compact ? 2 : 4);
    const portLabels = ports.length ? ports : ["e0a", "e0b"];
    return (
      <span className="design-faceplate-art design-faceplate-netapp-art" aria-hidden={interactive ? undefined : true} title={settings.controller_ports || "Controller ports"}>
        {["A", "B"].map((controller) => (
          <span className="design-controller-face" key={controller}>
            <span className="design-led design-led-unknown" />
            <strong>{controller}</strong>
            {portLabels.map((port) => (
              interactive ? (
                <button className="design-faceplate-chip" key={`${controller}-${port}`} onClick={() => onElementClick?.(`controller ${controller} ${port}`)} type="button">{port}</button>
              ) : (
                <span className="design-faceplate-chip" key={`${controller}-${port}`}>{port}</span>
              )
            ))}
          </span>
        ))}
        <span className="design-faceplate-chip">{storageProtocol.toUpperCase()}</span>
      </span>
    );
  }
  if (partId === "ilo") {
    const iloIp = settings.management_ip || "iLO IP not planned";
    return (
      <span className="design-faceplate-art design-faceplate-ilo-art" aria-hidden={interactive ? undefined : true} title={iloIp}>
        <span className="design-led-strip">
          <span className="design-led design-led-unknown" />
          <span className="design-led design-led-plan" />
        </span>
        <span className="design-ilo-module">
          <strong>HPE iLO</strong>
          <small>Out-of-band BMC</small>
          {interactive ? (
            <button className="design-ilo-port" onClick={() => onElementClick?.("Management NIC")} type="button" aria-label="iLO management NIC">
              <span />
              mgmt
            </button>
          ) : (
            <span className="design-ilo-port"><span />mgmt</span>
          )}
        </span>
        <span className="design-faceplate-chip">{iloIp}</span>
        <span className="design-faceplate-chip">read-only checks</span>
        <span className="design-faceplate-chip">{settings.reachability || "unknown"}</span>
      </span>
    );
  }
  return (
    <span className="design-faceplate-art design-faceplate-vm-art" aria-hidden="true">
      <span className="design-led design-led-plan" />
      <span className="design-faceplate-chip">{partId === "vcenter" ? "VCSA" : "WIN"}</span>
      <span className="design-faceplate-chip">{settings.datastore || settings.role || "draft"}</span>
    </span>
  );
}

function parseFirstInteger(value: string | undefined): number | null {
  const match = asString(value).match(/\d+/);
  if (!match) return null;
  const parsed = Number(match[0]);
  return Number.isFinite(parsed) ? parsed : null;
}

function clampNumber(value: number | null, minimum: number, maximum: number, fallback: number): number {
  const candidate = value ?? fallback;
  return Math.min(maximum, Math.max(minimum, candidate));
}

function splitFaceplateTokens(value: string): string[] {
  return asString(value)
    .split(/[\s,/]+/)
    .map((item) => item.trim())
    .filter((item) => /^(?:e\d+[a-z]?|p\d+|\d+)$/i.test(item));
}

function designFaceplateDetail(partId: DesignPartId, address: LabAddressPlan, storageProtocol: string): string {
  if (partId === "switch") return `${displayAddress(address.cisco_management)} - vlan path`;
  if (partId === "ilo") return `iLO ${displayAddress(address.ilo)} - BMC read-only checks`;
  if (partId === "server-gen10" || partId === "server-gen10plus") {
    return `iLO ${displayAddress(address.ilo)} - ESXi ${displayAddress(address.esxi_management)}`;
  }
  if (partId === "netapp") {
    return `cluster ${displayAddress(address.netapp_cluster_mgmt)} - ${storageProtocol.toUpperCase()} ready plan`;
  }
  if (partId === "vcenter") return "inventory and VM placement";
  return "guest workload role";
}

function designPartPrimaryDetail(
  partId: DesignPartId,
  settings: Record<string, string>,
  address: LabAddressPlan,
  storageProtocol: string
): string {
  if (partId === "switch") {
    return `${settings.management_ip || displayAddress(address.cisco_management)} - mgmt ${settings.mgmt_vlan || "?"} / storage ${settings.storage_vlan || "?"}`;
  }
  if (partId === "ilo") {
    return `${settings.management_ip || displayAddress(address.ilo)} - ${settings.reachability || "reachability unknown"}`;
  }
  if (partId === "server-gen10" || partId === "server-gen10plus") {
    return `iLO ${settings.management_ip || displayAddress(address.ilo)} - ${settings.raid_data || "storage plan"}`;
  }
  if (partId === "netapp") {
    const lifs = storageProtocol === "iscsi" ? settings.iscsi_lifs : settings.nfs_lifs;
    return `cluster ${settings.management_ip || displayAddress(address.netapp_cluster_mgmt)} - ${lifs || storageProtocol.toUpperCase()}`;
  }
  if (partId === "vcenter") {
    return `${settings.management_ip || displayAddress(address.ansible_control_host)} - ${settings.datastore || "datastore plan"}`;
  }
  return settings.vm_network || settings.role || "guest workload role";
}

function topologyDeviceSettingFields(partId: DesignPartId, storageProtocol: string): Array<{ key: string; kind?: "textarea"; label: string }> {
  if (partId === "switch") {
    return [
      { key: "name", label: "Name" },
      { key: "management_ip", label: "Management IP" },
      { key: "gateway", label: "Gateway" },
      { key: "mgmt_vlan", label: "Management VLAN" },
      { key: "storage_vlan", label: "Storage VLAN" },
      { key: "bpdu_guard", label: "BPDU guard" },
      { key: "blackhole_vlan", label: "Black-hole VLAN" },
      { key: "acl_lanes", kind: "textarea", label: "ACL lanes" },
      { key: "port_profiles", kind: "textarea", label: "Port profiles" },
      { key: "ports", kind: "textarea", label: "Port plan" },
      { key: "san_ports", kind: "textarea", label: "SAN ports" },
      { key: "notes", kind: "textarea", label: "Notes" }
    ];
  }
  if (partId === "ilo") {
    return [
      { key: "name", label: "Name" },
      { key: "management_ip", label: "iLO IP" },
      { key: "gateway", label: "Gateway" },
      { key: "credential_state", label: "Credential status" },
      { key: "reachability", label: "Reachability" },
      { key: "firmware", label: "Firmware evidence" },
      { key: "power_state", label: "Power-state evidence" },
      { key: "notes", kind: "textarea", label: "Guardrail notes" }
    ];
  }
  if (partId === "server-gen10" || partId === "server-gen10plus") {
    return [
      { key: "name", label: "Name" },
      { key: "management_ip", label: "iLO IP" },
      { key: "gateway", label: "Gateway" },
      { key: "drive_bays", label: "Drive bays" },
      { key: "raid_controller", label: "RAID controller" },
      { key: "raid_boot", label: "Boot RAID" },
      { key: "raid_data", label: "Data RAID" },
      { key: "storage_vlan", label: "Storage VLAN" },
      { key: "ports", kind: "textarea", label: "NIC plan" },
      { key: "notes", kind: "textarea", label: "Notes" }
    ];
  }
  if (partId === "netapp") {
    const protocolFields = storageProtocol === "iscsi"
      ? [{ key: "iscsi_lifs", label: "Primary iSCSI LIFs" }]
      : [{ key: "nfs_lifs", label: "Primary NFS LIFs" }];
    return [
      { key: "name", label: "Name" },
      { key: "management_ip", label: "Cluster IP" },
      { key: "gateway", label: "Gateway" },
      { key: "storage_vlan", label: "Storage VLAN" },
      { key: "protocol", label: "Storage mode" },
      ...protocolFields,
      { key: "controller_ports", label: "Controller ports" },
      { key: "ports", kind: "textarea", label: storageProtocol === "iscsi" ? "iSCSI port plan" : "NFS port plan" },
      { key: "notes", kind: "textarea", label: "Notes" }
    ];
  }
  if (partId === "vcenter") {
    return [
      { key: "name", label: "Name" },
      { key: "management_ip", label: "Management IP" },
      { key: "gateway", label: "Gateway" },
      { key: "datastore", label: "Datastore" },
      { key: "vm_network", label: "VM network" },
      { key: "role", kind: "textarea", label: "Role" },
      { key: "notes", kind: "textarea", label: "Notes" }
    ];
  }
  return [
    { key: "name", label: "Name" },
    { key: "vm_network", label: "VM network" },
    { key: "role", kind: "textarea", label: "Role" },
    { key: "notes", kind: "textarea", label: "Notes" }
  ];
}

function topologyDevicePersistenceRows(
  partId: DesignPartId,
  fields: Array<{ key: string; label: string }>
): Array<{ commitLabel: string; commitState: "profile" | "draft"; id: string; label: string; persistsTo: string }> {
  const partPath = `device_settings.${partId}`;
  const rows = fields.map((field) => {
    const profilePath = topologyCommittedProfilePath(partId, field.key);
    return {
      commitLabel: profilePath ? "Commit writes profile" : "Draft-only visual intent",
      commitState: profilePath ? "profile" as const : "draft" as const,
      id: `${partId}-${field.key}`,
      label: field.label,
      persistsTo: profilePath ? `${partPath}.${field.key} -> ${profilePath}` : `${partPath}.${field.key}`
    };
  });
  if (partId === "server-gen10" || partId === "server-gen10plus") {
    rows.unshift({
      commitLabel: "Commit writes profile",
      commitState: "profile",
      id: `${partId}-server-model`,
      label: "Server model",
      persistsTo: `rack placement -> devices.server_model (${topologyServerModelFromPart(partId)})`
    });
  }
  return rows;
}

function topologyCommittedProfilePath(partId: DesignPartId, key: string): string | null {
  if (key === "management_ip") {
    if (partId === "switch") return "address_plan.cisco_management";
    if (partId === "ilo") return "address_plan.ilo";
    if (partId === "server-gen10" || partId === "server-gen10plus") return "address_plan.ilo";
    if (partId === "netapp") return "address_plan.netapp_cluster_mgmt";
    if (partId === "vcenter") return "address_plan.ansible_control_host";
  }
  if (key === "gateway") return "global_settings.gateway";
  if (partId === "switch" && key === "mgmt_vlan") return "global_settings.vlan_id";
  if (partId === "netapp" && key === "nfs_lifs") return "address_plan.netapp_nfs_lifs";
  if (partId === "netapp" && key === "iscsi_lifs") return "address_plan.netapp_iscsi_lifs";
  if (partId === "netapp" && key === "protocol") return "features.storage_protocol";
  if (partId === "vcenter" && key === "datastore") return "devices.vcenter";
  return null;
}

function topologyDesignBlueprintNodes(
  placements: Record<RackSlotId, DesignPartId | null>,
  parts: DesignPart[],
  deviceSettings: DeviceSettings,
  address: LabAddressPlan,
  storageProtocol: string
): Array<{ detail: string; id: DesignPartId; label: string; meta: string }> {
  const placed = new Set(Object.values(placements).filter(Boolean) as DesignPartId[]);
  return parts
    .filter((part) => placed.has(part.id))
    .map((part) => ({
      detail: designPartPrimaryDetail(part.id, deviceSettings[part.id] ?? {}, address, storageProtocol),
      id: part.id,
      label: deviceSettings[part.id]?.name || part.label,
      meta: topologyDeviceMeta(part.id, deviceSettings[part.id] ?? {}, part.meta)
    }));
}

function topologyDeviceMeta(partId: DesignPartId, settings: Record<string, string>, fallback: string): string {
  if (partId === "switch") {
    return `mgmt VLAN ${settings.mgmt_vlan || "planned"} / storage VLAN ${settings.storage_vlan || "planned"}`;
  }
  if (partId === "ilo") {
    return settings.reachability || "reachability unknown";
  }
  if (partId === "server-gen10" || partId === "server-gen10plus") {
    return `${settings.raid_boot || "boot RAID"} / ${settings.raid_data || "data RAID"}`;
  }
  if (partId === "netapp") {
    return `${settings.protocol || "storage protocol"} / VLAN ${settings.storage_vlan || "planned"}`;
  }
  return settings.role || settings.vm_network || fallback;
}

function topologyDeviceInspectorRows(
  partId: DesignPartId,
  settings: Record<string, string>,
  storageProtocol: string
): Array<{ label: string; value: string }> {
  if (partId === "switch") {
    return [
      { label: "Mgmt", value: settings.management_ip || "not planned" },
      { label: "Gateway", value: settings.gateway || "not planned" },
      { label: "VLANs", value: `${settings.mgmt_vlan || "mgmt ?"} / ${settings.storage_vlan || "storage ?"}` }
    ];
  }
  if (partId === "ilo") {
    return [
      { label: "iLO", value: settings.management_ip || "not planned" },
      { label: "Credentials", value: settings.credential_state || "unknown until iLO Auth Live Check runs" },
      { label: "Proof", value: settings.reachability || "unknown until live check" }
    ];
  }
  if (partId === "server-gen10" || partId === "server-gen10plus") {
    return [
      { label: "iLO", value: settings.management_ip || "not planned" },
      { label: "RAID", value: `${settings.raid_boot || "boot ?"} / ${settings.raid_data || "data ?"}` },
      { label: "Storage", value: settings.storage_vlan || (storageProtocol === "local" ? "local datastore" : "storage VLAN ?") }
    ];
  }
  if (partId === "netapp") {
    return [
      { label: "Cluster", value: settings.management_ip || "not planned" },
      { label: "Protocol", value: settings.protocol || storageProtocol.toUpperCase() },
      { label: "LIFs", value: storageProtocol === "iscsi" ? settings.iscsi_lifs || "not planned" : settings.nfs_lifs || "not planned" }
    ];
  }
  return [
    { label: "Mgmt", value: settings.management_ip || "not planned" },
    { label: "Network", value: settings.vm_network || "not planned" },
    { label: "Role", value: settings.role || "not planned" }
  ];
}

function topologyProfileSyncRows({
  activeProfile,
  address,
  deviceSettings,
  draftScenario,
  netappInScope,
  serverModel,
  storageProtocol,
  vcenterInScope
}: {
  activeProfile: LabProfile | null;
  address: LabAddressPlan;
  deviceSettings: DeviceSettings;
  draftScenario: TopologyDesignScenario;
  netappInScope: boolean;
  serverModel: "gen10" | "gen10plus";
  storageProtocol: string;
  vcenterInScope: boolean;
}): Array<{ draftValue: string; id: string; label: string; savedValue: string; status: "matches" | "draft-differs" }> {
  const gateway = displayAddress(activeProfile?.global_settings?.gateway ?? activeProfile?.gateway ?? topologyGatewayFromSubnet(address.subnet));
  const rows = [
    topologySyncRow("scenario", "Scenario", topologyScenarioLabel(draftScenario), topologyScenarioLabel(topologyScenarioFromProfile(activeProfile, activeProfile?.features ?? null))),
    topologySyncRow("server-model", "Server model", topologyServerModelLabel(serverModel), topologyServerModelLabel(activeProfile?.devices?.server_model)),
    topologySyncRow("switch-ip", "Cisco mgmt", deviceSettings.switch?.management_ip, displayAddress(address.cisco_management)),
    topologySyncRow("switch-gateway", "Gateway", deviceSettings.switch?.gateway, gateway),
    topologySyncRow("switch-mgmt-vlan", "Mgmt VLAN", deviceSettings.switch?.mgmt_vlan, activeProfile?.global_settings?.vlan_id ?? activeProfile?.vlan_id ?? "100"),
    topologySyncRow("switch-storage-vlan", "Storage VLAN", deviceSettings.switch?.storage_vlan, "220"),
    topologySyncRow("ilo-ip", "iLO IP", deviceSettings.ilo?.management_ip || deviceSettings["server-gen10"]?.management_ip || deviceSettings["server-gen10plus"]?.management_ip, displayAddress(address.ilo)),
    topologySyncRow("storage-mode", "Storage mode", netappInScope ? storageProtocol.toUpperCase() : "LOCAL", activeProfile?.features?.storage_protocol?.toUpperCase() ?? "NFS"),
  ];
  if (netappInScope) {
    rows.push(
      topologySyncRow("netapp-cluster", "NetApp cluster", deviceSettings.netapp?.management_ip, displayAddress(address.netapp_cluster_mgmt)),
      topologySyncRow("netapp-nfs", "NFS LIFs", deviceSettings.netapp?.nfs_lifs, address.netapp_nfs_lifs.map(displayAddress).join(", ") || "Not set up yet"),
      topologySyncRow("netapp-iscsi", "iSCSI LIFs", deviceSettings.netapp?.iscsi_lifs, address.netapp_iscsi_lifs.map(displayAddress).join(", ") || "Not set up yet")
    );
  }
  if (vcenterInScope) {
    rows.push(
      topologySyncRow("vcenter-ip", "vCenter/control", deviceSettings.vcenter?.management_ip, displayAddress(address.ansible_control_host))
    );
  }
  return rows;
}

function topologyProfilePayloadFromDraft({
  activeProfile,
  address,
  connectionSettings,
  deviceSettings,
  draftScenario,
  laneSettings,
  placements,
  storageProtocol
}: {
  activeProfile: LabProfile;
  address: LabAddressPlan;
  connectionSettings: ConnectionSettings;
  deviceSettings: DeviceSettings;
  draftScenario: TopologyDesignScenario;
  laneSettings: LaneSettings;
  placements: Record<RackSlotId, DesignPartId | null>;
  storageProtocol: string;
}): LabProfileWrite {
  const netappInScope = draftScenario !== "single_server_local_storage";
  const vcenterInScope = draftScenario === "server_netapp_vcenter";
  const switchSettings = deviceSettings.switch ?? {};
  const iloSettings = deviceSettings.ilo ?? {};
  const serverPart: DesignPartId = Object.values(placements).includes("server-gen10plus") ? "server-gen10plus" : "server-gen10";
  const serverModel = serverPart === "server-gen10plus" ? "gen10plus" : "gen10";
  const serverSettings = deviceSettings[serverPart] ?? {};
  const netappSettings = deviceSettings.netapp ?? {};
  const vcenterSettings = deviceSettings.vcenter ?? {};
  const managementLane = laneSettings.management ?? {};
  const storageLane = laneSettings.storage ?? {};
  const virtualizationLane = laneSettings.virtualization ?? {};
  const subnet = cleanNetworkNullable(address.subnet ?? activeProfile.address_plan.subnet ?? activeProfile.subnet_cidr);
  const gateway = cleanNetworkNullable(switchSettings.gateway || activeProfile.global_settings.gateway || activeProfile.gateway);
  const vlanId = cleanNetworkNullable(switchSettings.mgmt_vlan || managementLane.vlan || activeProfile.vlan_id);
  const mtu = parseNetworkMtu(asString(managementLane.mtu || activeProfile.mtu || ""));
  const subnetPrefix = networkPrefixFromCidr(subnet) ?? activeProfile.global_settings.subnet_prefix ?? 24;
  const nfsLifs = netappInScope ? splitNetworkList(netappSettings.nfs_lifs || "") : [];
  const iscsiLifs = netappInScope ? splitNetworkList(netappSettings.iscsi_lifs || "") : [];
  const protocol = netappInScope ? (storageProtocol === "iscsi" ? "iscsi" : "nfs") : "local";
  const addressPlan: LabAddressPlan = {
    ...address,
    ansible_control_host: vcenterInScope ? cleanNetworkNullable(vcenterSettings.management_ip) : null,
    cisco_management: cleanNetworkNullable(switchSettings.management_ip),
    ilo: cleanNetworkNullable(iloSettings.management_ip) || cleanNetworkNullable(serverSettings.management_ip),
    netapp_cluster_mgmt: netappInScope ? cleanNetworkNullable(netappSettings.management_ip) : null,
    netapp_iscsi_lifs: iscsiLifs,
    netapp_nfs_lifs: nfsLifs,
    subnet
  };
  const features: LabProfileFeatures = {
    ...activeProfile.features,
    deployment_label: topologyScenarioLabel(draftScenario),
    deployment_mode: draftScenario,
    deployment_supported: true,
    netapp_disabled_reason: netappInScope ? null : "Single-server profile uses server-local storage.",
    netapp_enabled: netappInScope,
    storage_location: netappInScope ? "netapp_shared" : "server_local",
    storage_protocol: protocol,
    vcenter_disabled_reason: vcenterInScope ? null : "vCenter is out of scope for this visual setup.",
    vcenter_enabled: vcenterInScope
  };
  const globalSettings = {
    ...activeProfile.global_settings,
    gateway,
    mtu,
    netapp_disabled_reason: features.netapp_disabled_reason,
    netapp_enabled: netappInScope,
    subnet_prefix: subnetPrefix,
    vlan_id: vlanId,
    vcenter_enabled: vcenterInScope
  };
  return {
    address_plan: addressPlan,
    description: activeProfile.description,
    devices: {
      ...(activeProfile.devices ?? {}),
      cisco: addressPlan.cisco_management,
      esxi: activeProfile.devices?.esxi ?? activeProfile.address_plan.esxi_management,
      gateway,
      ilo: addressPlan.ilo,
      server_model: serverModel,
      netapp: netappInScope
        ? {
            ...((activeProfile.devices?.netapp && typeof activeProfile.devices.netapp === "object") ? activeProfile.devices.netapp : {}),
            acl_lanes: switchSettings.acl_lanes,
            blackhole_vlan: switchSettings.blackhole_vlan,
            bpdu_guard: switchSettings.bpdu_guard,
            cluster_mgmt: addressPlan.netapp_cluster_mgmt,
            connection_protocol: connectionSettings["server-netapp"]?.protocol,
            controller_ports: netappSettings.controller_ports,
            iscsi_lifs: addressPlan.netapp_iscsi_lifs,
            nfs_lifs: addressPlan.netapp_nfs_lifs,
            protocol,
            storage_lane_mtu: storageLane.mtu,
            storage_vlan: switchSettings.storage_vlan || storageLane.vlan
          }
        : null,
      switch_primary: addressPlan.cisco_management,
      utility_vm: placements.virtual === "windows" ? deviceSettings.windows?.name || "Windows Server" : activeProfile.devices?.utility_vm ?? null,
      vcenter: vcenterInScope ? addressPlan.ansible_control_host : null
    },
    dns: activeProfile.dns,
    features,
    gateway,
    global_settings: globalSettings,
    mtu,
    name: activeProfile.source === "saved" ? activeProfile.name : "Visual lab setup",
    ntp: activeProfile.ntp,
    profile_topology: draftScenario,
    subnet_cidr: subnet,
    vlan_id: vlanId,
    // Keep the visualization intent attached to profile history through known profile fields.
    // Hardware remains untouched until the separate guarded workflow actions are run.
  };
}

function topologyServerModelFromPart(partId: DesignPartId): "gen10" | "gen10plus" {
  return partId === "server-gen10plus" ? "gen10plus" : "gen10";
}

function topologyServerModelLabel(value: unknown): string {
  return asString(value).toLowerCase() === "gen10plus" ? "DL360 Gen10+" : "DL360 Gen10";
}

function topologyDeviceSafeActions(
  partId: DesignPartId,
  actions: WorkflowAction[],
  scope: { netappInScope: boolean; storageProtocol: string; vcenterInScope: boolean }
): WorkflowAction[] {
  const safe = actions.filter((action) => ["read_only", "report_only"].includes(action.mode) && action.ui_run_supported !== false);
  const preferredIds = topologyDevicePreferredActionIds(partId, scope);
  const byId = new Map(safe.map((action) => [action.action_id, action]));
  const selected = preferredIds
    .map((id) => byId.get(id) ?? topologyFallbackReadOnlyAction(id))
    .filter((action): action is WorkflowAction => Boolean(action));
  if (selected.length) return selected.slice(0, 3);
  const hints = topologyDeviceProviderHints(partId);
  return safe
    .filter((action) => hints.some((hint) =>
      action.provider.toLowerCase().includes(hint) ||
      action.stage.toLowerCase().includes(hint) ||
      action.action_id.toLowerCase().includes(hint)
    ))
    .slice(0, 3);
}

function topologyFallbackReadOnlyAction(actionId: string): WorkflowAction | null {
  const labels: Record<string, { description: string; label: string; provider: string; stage: string; stage_label: string }> = {
    "cisco.ssh-readonly-probe": {
      description: "Run approved Cisco show commands through the existing read-only workflow endpoint.",
      label: "Cisco SSH read-only probe",
      provider: "cisco",
      stage: "network",
      stage_label: "Network"
    },
    "ilo.reachability": {
      description: "Check iLO reachability through the existing read-only workflow endpoint.",
      label: "iLO reachability",
      provider: "ilo",
      stage: "server",
      stage_label: "Server"
    },
    "ilo.auth": {
      description: "Check iLO credentials without exposing secrets through the existing read-only workflow endpoint.",
      label: "iLO auth check",
      provider: "ilo",
      stage: "server",
      stage_label: "Server"
    },
    "ilo.inventory": {
      description: "Read iLO inventory through the existing read-only workflow endpoint.",
      label: "iLO inventory",
      provider: "ilo",
      stage: "server",
      stage_label: "Server"
    }
  };
  const item = labels[actionId];
  if (!item) return null;
  return {
    action_id: actionId,
    api_endpoint: null,
    api_method: null,
    blockers: [],
    category: "discover",
    command: null,
    current_availability: "unknown",
    description: item.description,
    evidence_artifacts: [],
    guarded_run_blockers: [],
    guarded_run_supported: false,
    inputs: [],
    label: item.label,
    last_run_report: null,
    last_run_status: "not_checked",
    last_run_trace: {
      action_id: actionId,
      blockers: [],
      command: null,
      finished_at: null,
      freshness: "not_checked",
      next_action: "Run this read-only check to collect proof.",
      report_artifacts: [],
      run_id: "",
      source_type: "not_checked",
      stage_id: item.stage,
      started_at: null,
      status: "not_checked",
      summary: "No run recorded for this workspace action.",
      warnings: []
    },
    mode: "read_only",
    next_action: "Run this read-only check to collect proof.",
    outputs: [],
    provider: item.provider,
    reports: [],
    required_confirmations: [],
    required_credentials: [],
    required_gates: [],
    required_mode: "real_lab",
    run_endpoint: `/api/v1/workflows/actions/${actionId}/run`,
    runs_endpoint: `/api/v1/workflows/actions/${actionId}/runs`,
    safety_notes: ["Read-only proof only. No configuration, power, firmware, RAID, reset, or rebuild actions are exposed here."],
    source_type: "api_endpoint",
    stage: item.stage,
    stage_label: item.stage_label,
    stale_after_seconds: 300,
    ui_run_blockers: [],
    ui_run_supported: true
  };
}

function topologyDevicePreferredActionIds(
  partId: DesignPartId,
  scope: { netappInScope: boolean; storageProtocol: string; vcenterInScope: boolean }
): string[] {
  if (partId === "switch") {
    return ["cisco.ssh-readonly-probe", "cisco.validate-ssh-scp", "cisco.firmware-inventory", "cisco.current-intent-diff"];
  }
  if (partId === "ilo") {
    return ["ilo.reachability", "ilo.auth", "ilo.inventory"];
  }
  if (partId === "server-gen10" || partId === "server-gen10plus") {
    return ["esxi.management-validation", "raid.validate", "build-verification.toolchain-check"];
  }
  if (partId === "netapp") {
    return scope.storageProtocol === "iscsi"
      ? ["netapp.setup-preview", "netapp.iscsi-setup-preview", "esxi.iscsi-datastore-preview"]
      : ["netapp.setup-preview", "netapp.nfs-vcenter-readiness", "netapp.ontap-upgrade-inventory"];
  }
  if (partId === "vcenter") {
    return scope.vcenterInScope
      ? ["vcenter-netapp.readiness", "vcenter.install-readiness", "vcenter.post-attach-validation"]
      : ["esxi.management-validation"];
  }
  return ["esxi.vm-deploy-validate", "operator-readonly-sweep.real-lab"];
}

function topologyDeviceProviderHints(partId: DesignPartId): string[] {
  if (partId === "switch") return ["cisco"];
  if (partId === "ilo") return ["ilo"];
  if (partId === "server-gen10" || partId === "server-gen10plus") return ["esxi", "raid"];
  if (partId === "netapp") return ["netapp"];
  if (partId === "vcenter") return ["vcenter"];
  return ["vm", "operator"];
}

function topologySyncRow(id: string, label: string, draftValue: unknown, savedValue: unknown) {
  const draft = displayAddress(draftValue);
  const saved = displayAddress(savedValue);
  return {
    draftValue: draft,
    id,
    label,
    savedValue: saved,
    status: topologyComparableValue(draft) === topologyComparableValue(saved) ? "matches" as const : "draft-differs" as const
  };
}

function topologyComparableValue(value: string): string {
  return value
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean)
    .sort()
    .join(",");
}

function topologyDesignBlueprintLinks({
  connectionSettings,
  netappInScope,
  vcenterInScope
}: {
  connectionSettings: ConnectionSettings;
  netappInScope: boolean;
  vcenterInScope: boolean;
}): Array<{ id: DesignConnectionId; label: string; labelX: number; labelY: number; path: string; tone: "network" | "storage" | "virtual" }> {
  const links: Array<{ id: DesignConnectionId; label: string; labelX: number; labelY: number; path: string; tone: "network" | "storage" | "virtual" }> = [
    {
      id: "switch-server",
      label: connectionSettings["switch-server"]?.protocol || "mgmt + vmkernel",
      labelX: 330,
      labelY: 132,
      path: "M500 90 C430 115 360 140 280 190",
      tone: "network"
    }
  ];
  if (netappInScope) {
    links.push({
      id: "switch-netapp",
      label: connectionSettings["switch-netapp"]?.protocol || "NFS / iSCSI VLANs",
      labelX: 560,
      labelY: 132,
      path: "M500 90 C575 115 650 140 720 190",
      tone: "storage"
    });
    links.push({
      id: "server-netapp",
      label: connectionSettings["server-netapp"]?.protocol || "datastore path",
      labelX: 425,
      labelY: 232,
      path: "M280 220 C405 250 595 250 720 220",
      tone: "storage"
    });
  }
  links.push({
    id: "server-vm",
    label: connectionSettings["server-vm"]?.protocol || (vcenterInScope ? "inventory + VM placement" : "direct ESXi inventory"),
    labelX: 410,
    labelY: 326,
    path: netappInScope ? "M500 300 C500 260 500 245 500 222" : "M500 300 C430 270 350 245 280 222",
    tone: "virtual"
  });
  return links;
}

function topologyDesignLanes({
  netappInScope,
  vcenterInScope
}: {
  netappInScope: boolean;
  vcenterInScope: boolean;
}): string[] {
  return ["network", "server", netappInScope ? "storage" : "local storage", vcenterInScope ? "virtualization" : ""].filter(Boolean);
}

function topologyDesignLanePlans({
  address,
  laneSettings,
  netappInScope,
  storageProtocol,
  vcenterInScope
}: {
  address: LabAddressPlan;
  laneSettings: LaneSettings;
  netappInScope: boolean;
  storageProtocol: string;
  vcenterInScope: boolean;
}): Array<{ detail: string; id: DesignLaneId; label: string; path: string; tone: "plan" | "optional" }> {
  const management = laneSettings.management;
  const storage = laneSettings.storage;
  const virtualization = laneSettings.virtualization;
  const lanes: Array<{ detail: string; id: DesignLaneId; label: string; path: string; tone: "plan" | "optional" }> = [
    {
      detail: `${management.protocol || "management protocols"} on VLAN ${management.vlan || "planned"} / MTU ${management.mtu || "planned"}`,
      id: "management",
      label: "Management lane",
      path: `${management.source || "Cisco"} -> ${management.target || "devices"}`,
      tone: "plan" as const
    }
  ];
  if (netappInScope) {
    lanes.push({
      detail: `${storage.protocol || storageProtocol.toUpperCase()} on VLAN ${storage.vlan || "planned"} / MTU ${storage.mtu || "planned"}`,
      id: "storage",
      label: storageProtocol === "iscsi" ? "SAN lane" : "NFS lane",
      path: `${storage.source || "ESXi"} -> ${storage.target || "NetApp"}`,
      tone: "plan" as const
    });
  } else {
    lanes.push({
      detail: `${storage.protocol || "local datastore"} / MTU ${storage.mtu || "planned"}`,
      id: "storage",
      label: "Local storage lane",
      path: `${storage.source || "ESXi"} -> ${storage.target || "local RAID/datastore"}`,
      tone: "plan" as const
    });
  }
  lanes.push({
    detail: `${virtualization.protocol || "virtualization APIs"} on VLAN ${virtualization.vlan || "planned"} / MTU ${virtualization.mtu || "planned"}`,
    id: "virtualization",
    label: "Virtualization lane",
    path: `${virtualization.source || "ESXi"} -> ${virtualization.target || "VM inventory"}`,
    tone: vcenterInScope ? "plan" as const : "optional" as const
  });
  return lanes;
}

function topologyDesignAddressCount(address: LabAddressPlan, netappInScope: boolean, vcenterInScope: boolean): number {
  const values = [
    address.cisco_management,
    address.ilo,
    address.esxi_management,
    netappInScope ? address.netapp_cluster_mgmt : null,
    netappInScope ? address.netapp_node_a_mgmt : null,
    netappInScope ? address.netapp_node_b_mgmt : null,
    ...(netappInScope ? address.netapp_nfs_lifs : []),
    ...(netappInScope ? address.netapp_iscsi_lifs : []),
    vcenterInScope ? asString(address.ansible_control_host) : null
  ];
  return values.filter(Boolean).length;
}

function topologyDesignAddressRows(
  address: LabAddressPlan,
  netappInScope: boolean,
  vcenterInScope: boolean,
  serverPart: DesignPartId
): Array<{ label: string; target: DesignPartId; value: string }> {
  const rows = [
    { label: "Cisco", target: "switch" as DesignPartId, value: displayAddress(address.cisco_management) },
    { label: "Server iLO", target: serverPart, value: displayAddress(address.ilo) },
    { label: "ESXi", target: serverPart, value: displayAddress(address.esxi_management) }
  ];
  if (netappInScope) {
    rows.push(
      { label: "NetApp cluster", target: "netapp" as DesignPartId, value: displayAddress(address.netapp_cluster_mgmt) },
      { label: "NFS LIFs", target: "netapp" as DesignPartId, value: address.netapp_nfs_lifs.map(displayAddress).join(", ") || "Not set up yet" },
      { label: "iSCSI LIFs", target: "netapp" as DesignPartId, value: address.netapp_iscsi_lifs.map(displayAddress).join(", ") || "Not set up yet" }
    );
  }
  if (vcenterInScope) {
    rows.push({ label: "vCenter", target: "vcenter" as DesignPartId, value: displayAddress(address.ansible_control_host) });
  }
  return rows;
}

function topologyDesignCablingRows(
  deviceSettings: DeviceSettings,
  netappInScope: boolean,
  serverPart: DesignPartId
): Array<{ label: string; target: DesignPartId; value: string }> {
  const rows = [
    {
      label: "Cisco ports",
      target: "switch" as DesignPartId,
      value: asString(deviceSettings.switch?.ports) || "Switch ports not planned"
    },
    {
      label: "Server NICs",
      target: serverPart,
      value: asString(deviceSettings[serverPart]?.ports) || "Server NICs not planned"
    },
    {
      label: "Port profiles",
      target: "switch" as DesignPartId,
      value: asString(deviceSettings.switch?.port_profiles) || "Port profiles not planned"
    }
  ];
  if (netappInScope) {
    rows.push(
      {
        label: "NetApp ports",
        target: "netapp" as DesignPartId,
        value: asString(deviceSettings.netapp?.controller_ports || deviceSettings.netapp?.ports) || "NetApp ports not planned"
      },
      {
        label: "SAN ports",
        target: "switch" as DesignPartId,
        value: asString(deviceSettings.switch?.san_ports) || "SAN ports not planned"
      }
    );
  }
  return rows;
}

function topologyDesignReadinessRows({
  addressCount,
  draftPersistence,
  draftSubnetValidation,
  netappInScope,
  profileSyncDriftCount,
  storageProtocol,
  vcenterInScope
}: {
  addressCount: number;
  draftPersistence: "loading" | "persisted" | "local" | "error";
  draftSubnetValidation: { detail: string; status: "ok" | "warning" | "error" };
  netappInScope: boolean;
  profileSyncDriftCount: number;
  storageProtocol: string;
  vcenterInScope: boolean;
}): Array<{ detail: string; label: string; status: "ready" | "warning" | "blocked" | "plan" }> {
  return [
    {
      detail: draftSubnetValidation.status === "error" ? "Fix subnet before rebase" : draftSubnetValidation.status === "warning" ? "Valid with caution" : "Subnet can rebase",
      label: "Subnet",
      status: draftSubnetValidation.status === "error" ? "blocked" : draftSubnetValidation.status === "warning" ? "warning" : "ready"
    },
    {
      detail: profileSyncDriftCount ? `${profileSyncDriftCount} draft value${profileSyncDriftCount === 1 ? "" : "s"} to commit` : "Draft matches profile",
      label: "Profile sync",
      status: profileSyncDriftCount ? "warning" : "ready"
    },
    {
      detail: draftPersistence === "persisted" ? "Server draft saved" : draftPersistence === "loading" ? "Loading draft" : draftPersistence === "error" ? "Browser fallback" : "Local defaults",
      label: "Draft store",
      status: draftPersistence === "error" ? "warning" : draftPersistence === "persisted" ? "ready" : "plan"
    },
    {
      detail: netappInScope ? `${storageProtocol.toUpperCase()} shared path${vcenterInScope ? " with vCenter" : ""}` : "Server-local datastore",
      label: "Storage path",
      status: netappInScope ? "ready" : "plan"
    },
    {
      detail: `${addressCount} planned endpoint${addressCount === 1 ? "" : "s"}`,
      label: "Addresses",
      status: addressCount ? "ready" : "blocked"
    }
  ];
}

function topologyDesignReviewPacket({
  addressRows,
  draftScenario,
  profileSyncDriftCount,
  readinessRows,
  serverModel,
  storageProtocol,
  subnet
}: {
  addressRows: Array<{ label: string; target: DesignPartId; value: string }>;
  draftScenario: TopologyDesignScenario;
  profileSyncDriftCount: number;
  readinessRows: Array<{ detail: string; label: string; status: "ready" | "warning" | "blocked" | "plan" }>;
  serverModel: "gen10" | "gen10plus";
  storageProtocol: string;
  subnet: string | null;
}): string {
  const packet = {
    scenario: draftScenario,
    server_model: serverModel,
    subnet: displayAddress(subnet),
    storage_protocol: storageProtocol.toUpperCase(),
    profile_sync: profileSyncDriftCount ? `${profileSyncDriftCount} draft value(s) differ` : "draft matches profile",
    readiness: readinessRows.map((row) => `${row.label}: ${row.status} - ${row.detail}`),
    endpoints: addressRows.map((row) => `${row.label}: ${row.value}`),
    safety: "Intent-only visual draft. Hardware remains untouched until guarded workflow actions run."
  };
  return JSON.stringify(packet, null, 2);
}

function topologySubnetState(subnet: string | null, health?: HealthLike): TopologySubnetState {
  const plannedSubnet = asString(subnet);
  if (!health) {
    return {
      detail: plannedSubnet
        ? `Active setup targets ${plannedSubnet}. Waiting for host network details before comparing it to this computer.`
        : "Waiting for host network details before comparing the active setup to this computer.",
      label: "Subnet checking",
      status: "unknown"
    };
  }
  const hostIps = (health?.host_ipv4_addresses ?? []).map((item) => asString(item)).filter(Boolean);
  if (!plannedSubnet) {
    return {
      detail: "No active lab subnet is saved. Open system setup and save the subnet before trusting topology status.",
      label: "Subnet missing",
      status: "unknown"
    };
  }
  if (!hostIps.length) {
    return {
      detail: `Active setup targets ${plannedSubnet}. This computer has not reported a local IPv4 address yet, so live reachability still depends on node checks.`,
      label: "Subnet unverified",
      status: "unknown"
    };
  }
  const matchingIp = hostIps.find((ip) => ipv4InCidr(ip, plannedSubnet));
  if (matchingIp) {
    return {
      detail: `This computer reports ${matchingIp} inside ${plannedSubnet}. Device nodes still need live checks before they are considered reachable.`,
      label: "Subnet matches host",
      status: "matches"
    };
  }
  return {
    detail: `Active setup targets ${plannedSubnet}, but this computer reports ${hostIps.join(", ")}. Update the Network profile before treating this topology as live.`,
    label: "Subnet mismatch",
    status: "mismatch"
  };
}

function ipv4InCidr(ip: string, cidr: string): boolean {
  const ipNumber = ipv4ToNumber(ip);
  const [baseRaw, prefixRaw = "32"] = cidr.split("/");
  const baseNumber = ipv4ToNumber(baseRaw);
  const prefix = Number(prefixRaw);
  if (ipNumber === null || baseNumber === null || !Number.isInteger(prefix) || prefix < 0 || prefix > 32) {
    return false;
  }
  const mask = prefix === 0 ? 0 : (0xffffffff << (32 - prefix)) >>> 0;
  return ((ipNumber & mask) >>> 0) === ((baseNumber & mask) >>> 0);
}

function ipv4ToNumber(value: string): number | null {
  const parts = value.trim().split(".");
  if (parts.length !== 4) return null;
  let result = 0;
  for (const part of parts) {
    if (!/^\d+$/.test(part)) return null;
    const octet = Number(part);
    if (!Number.isInteger(octet) || octet < 0 || octet > 255) return null;
    result = (result * 256) + octet;
  }
  return result >>> 0;
}

function topologyStatusFromAccess(rows: AccessRow[], item: string): string {
  return rows.find((row) => row.item.toLowerCase() === item.toLowerCase())?.status || "not_checked";
}

function topologyWorstStatus(values: string[]): string {
  if (values.some((value) => topologyTone(value) === "offline")) return "offline";
  if (values.some((value) => topologyTone(value) === "warning")) return "warning";
  if (values.some((value) => topologyTone(value) === "ready")) return "ready";
  return values.find(Boolean) || "not_checked";
}

function topologyTone(status: string, readyTone: TopologyNodeTone = "ready"): TopologyNodeTone {
  const normalized = status.toLowerCase();
  if (["ready", "ok", "passed", "completed", "current", "accessible"].includes(normalized)) return readyTone;
  if (["offline", "unreachable", "not_accessible", "not_checked", "not_setup", "not_configured_yet"].includes(normalized)) return "offline";
  if (["warning", "warn", "needs_review", "needs_attention", "outdated", "partial", "pending", "blocked", "failed"].includes(normalized)) return "warning";
  return "unknown";
}

function topologyLinkStatus(status: string, readyStatus: TopologyLink["status"] = "ready"): TopologyLink["status"] {
  const tone = topologyTone(status);
  if (tone === "ready") return readyStatus;
  if (tone === "warning") return "warning";
  return "unknown";
}

function topologyNetappMeta(address: LabAddressPlan, storageProtocol: string): string {
  const nfs = address.netapp_nfs_lifs?.length ? `nfs ${address.netapp_nfs_lifs.map((item) => `.${item.split(".").pop()}`).join(" / ")}` : "";
  const iscsi = address.netapp_iscsi_lifs?.length ? `iscsi x${address.netapp_iscsi_lifs.length}` : "";
  return [nfs, iscsi, storageProtocol === "iscsi" ? "block ready path" : ""].filter(Boolean).join(" - ") || "storage targets planned";
}

function topologyVmMapTarget(probe: ProviderProbeResult | null, vcenterInScope: boolean, address: LabAddressPlan): string {
  const checks = objectValue(probe?.checks);
  const inventory = objectValue(checks.vm_inventory_visible);
  if (asBoolean(inventory.visible)) return `${asString(inventory.count) || "some"} visible`;
  return vcenterInScope ? displayAddress(address.ansible_control_host) : displayAddress(address.esxi_management);
}

function OverviewReferencePanel({
  accessRows,
  currentView,
  firmwareSummaries,
  inventoryRows,
  workspaceRows
}: {
  accessRows: AccessRow[];
  currentView: CurrentViewModel;
  firmwareSummaries: FirmwareSummary[];
  inventoryRows: InventoryRow[];
  workspaceRows: OperatorObjectRow[];
}) {
  const counts = workspaceCounts(workspaceRows);
  const activeIssues = overviewIssues(currentView);
  const providerCards = overviewProviderCards({ accessRows, inventoryRows, workspaceRows });
  const firmwareRows = overviewFirmwareRows(firmwareSummaries, inventoryRows);
  const safeActions = overviewSafeActions(currentView, providerCards);

  return (
    <section className="overview-reference" aria-label="Overview reference">
      <div className="overview-reference-head">
        <div>
          <p className="operator-kicker">Operator console</p>
          <h2>Readiness at a glance</h2>
        </div>
        <StatusBadge label="Redesigned view" status="safe-to-run" />
      </div>
      <div className="overview-stat-grid" aria-label="Readiness summary">
        <OverviewStatCard
          label="Active blockers"
          meta={`${currentView.warnings.length} warnings`}
          status={currentView.blockers.length ? "blocked" : currentView.warnings.length ? "needs-attention" : "ready"}
          value={String(currentView.blockers.length)}
        />
        <OverviewStatCard
          label="Server ready"
          meta={`${counts.warning} need review`}
          status={counts.blocked ? "blocked" : counts.warning ? "needs-attention" : "ready"}
          value={`${counts.ready}/${workspaceRows.length}`}
        />
        <OverviewStatCard
          label="Firmware compliance"
          meta={firmwareRows.length ? `${firmwareRows.length} components tracked` : "No scan loaded"}
          status={firmwareRows.some((row) => statusTone(row.status) === "blocked") ? "blocked" : firmwareRows.some((row) => statusTone(row.status) === "warning") ? "needs-attention" : firmwareRows.length ? "ready" : "not-configured"}
          value={firmwareRows.length ? `${firmwareRows.filter((row) => statusTone(row.status) === "ready").length}/${firmwareRows.length}` : "Not checked"}
        />
        <OverviewStatCard
          label="VM requests"
          meta={currentView.source}
          status={statusBadgeStatus(currentView.status)}
          value="0"
        />
      </div>

      <div className="overview-panel-head">
        <div>
          <p className="operator-kicker">Provider status</p>
          <h2>Hardware and access</h2>
        </div>
        <StatusBadge label={`${providerCards.length} targets`} status="plan-only" />
      </div>
      <div className="overview-provider-grid">
        {providerCards.map((provider) => (
          <Card className="overview-provider-card" key={provider.name}>
            <CardHeader>
              <div>
                <p className="operator-kicker">{provider.role}</p>
                <h3>{provider.name}</h3>
              </div>
              <StatusBadge label={displayStatus(provider.status)} status={statusBadgeStatus(provider.status)} />
            </CardHeader>
            <CardContent>
              <dl className="overview-fact-list">
                <div>
                  <dt>{provider.primaryLabel}</dt>
                  <dd>{provider.target}</dd>
                </div>
                <div>
                  <dt>{provider.secondaryLabel}</dt>
                  <dd>{provider.version}</dd>
                </div>
                <div>
                  <dt>Setup</dt>
                  <dd>{provider.setupState}</dd>
                </div>
              </dl>
              <div className="overview-current-state-box">
                <p><strong>Current State:</strong> {provider.currentState}</p>
                <p><strong>Target:</strong> {provider.targetState}</p>
                <p><strong>Gap:</strong> {provider.gap}</p>
                <p><strong>Blocked by:</strong> {provider.blockedBy}</p>
              </div>
            </CardContent>
            {provider.to && (
              <CardFooter>
                <ActionLink to={provider.to}>{provider.actionLabel}</ActionLink>
              </CardFooter>
            )}
          </Card>
        ))}
      </div>

      <SetupLanesPanel
        accessRows={accessRows}
        currentView={currentView}
        firmwareRows={firmwareRows}
        workspaceRows={workspaceRows}
      />

      <section className="overview-safe-actions" aria-label="Next safe actions">
        <p className="operator-kicker">Next safe actions</p>
        <ul>
          {safeActions.map((action) => (
            <li key={action}>{action}</li>
          ))}
        </ul>
      </section>

      <div className="overview-bottom-grid">
        <Card className="overview-firmware-panel" hover={false}>
          <CardHeader>
            <div>
              <h2>Firmware Compliance</h2>
            </div>
            <span>{firmwareRows.filter((row) => statusTone(row.status) !== "ready").length} of {firmwareRows.length} devices outdated</span>
          </CardHeader>
          <CompactTable>
            <CompactTableHeader>
              <CompactTableCell>Device</CompactTableCell>
              <CompactTableCell>Current</CompactTableCell>
              <CompactTableCell>Target</CompactTableCell>
              <CompactTableCell>Status</CompactTableCell>
            </CompactTableHeader>
            <tbody>
              {firmwareRows.map((row) => (
                <CompactTableRow key={row.device}>
                  <CompactTableCell><strong>{row.device}</strong></CompactTableCell>
                  <CompactTableCell>{row.version}</CompactTableCell>
                  <CompactTableCell>{row.target}</CompactTableCell>
                  <CompactTableCell><StatusBadge label={displayStatus(row.status)} status={statusBadgeStatus(row.status)} /></CompactTableCell>
                </CompactTableRow>
              ))}
            </tbody>
          </CompactTable>
        </Card>

        <Card className="overview-blockers-panel" hover={false}>
          <CardHeader>
            <div>
              <h2>Active Blockers</h2>
            </div>
            <span>{activeIssues.length} open</span>
          </CardHeader>
          <CardContent>
            <div className="overview-blocker-list">
              {activeIssues.length ? (
                activeIssues.slice(0, 3).map((issue) => (
                  <BlockerItem
                    code={issue.code}
                    key={`${issue.code}-${issue.message}`}
                    message={issue.message}
                    severity={issue.severity}
                  />
                ))
              ) : (
                <div className="overview-clear-state">
                  <StatusBadge status="ready" />
                  <span>No active blockers are loaded for the current view.</span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}

type SetupLane = {
  actionLabel: string;
  advanced: ConfigValue[];
  basics: ConfigValue[];
  current: string;
  id: string;
  intended: string;
  need: string;
  nextAction: string;
  status: string;
  title: string;
  to: string;
  validation: string;
};

function SetupLanesPanel({
  accessRows,
  currentView,
  firmwareRows,
  workspaceRows
}: {
  accessRows: AccessRow[];
  currentView: CurrentViewModel;
  firmwareRows: OverviewFirmwareRow[];
  workspaceRows: OperatorObjectRow[];
}) {
  const activeSetup = workspaceRows.find((row) => row.id === "active-setup");
  const labValues = activeSetup?.details ?? [];
  const scenario = configValue(labValues, "Deployment scenario", "No active setup");
  const storageLocation = configValue(labValues, "Storage location", "Not set up yet");
  const storageProtocol = configValue(labValues, "Feature toggles", "Not set up yet");
  const isSingleServer = /single server|server local/i.test(`${scenario} ${storageLocation}`);
  const cisco = accessByItem(accessRows, "Cisco");
  const ilo = accessByItem(accessRows, "iLO");
  const esxi = accessByItem(accessRows, "ESXi");
  const netapp = accessByItem(accessRows, "NetApp");
  const vcenter = accessByItem(accessRows, "vCenter");
  const datastore = accessByItem(accessRows, "Datastore");
  const firmwareStatus = firmwareRows.length && firmwareRows.every((row) => statusTone(row.status) === "ready")
    ? "ready"
    : firmwareRows.length
      ? "needs_attention"
      : "not_checked";
  const firstBlocker = currentView.blockers[0] || currentView.warnings[0] || "";
  const lanes: SetupLane[] = [
    setupLane({
      access: ilo,
      actionLabel: "Open map workspace",
      advanced: valuesForLabels(labValues, ["iLO IP", "Subnet", "Gateway", "DNS", "NTP"]),
      basics: [
        { label: "Access", value: targetOrUnset(ilo) },
        { label: "Firmware gate", value: displayStatus(firmwareStatus), status: firmwareStatus },
        { label: "Credentials", value: ilo?.needs === "Nothing right now" ? "Available" : "Needed" }
      ],
      current: ilo?.appSees ?? "Not checked",
      intended: "iLO reachable, credentials saved, firmware evidence current.",
      need: "Server management access before destructive setup or firmware work.",
      nextAction: laneNextAction(ilo, "Open the iLO or server workspace from the map and run read-only checks."),
      title: "Server Access",
      to: "/overview#topology-map",
      validation: firstBlocker || "Validation will confirm iLO access and firmware evidence."
    }),
    setupLane({
      actionLabel: "Open map workspace",
      advanced: [
        { label: "Local storage mode", value: isSingleServer ? "Primary datastore path" : "Boot and staging only" },
        { label: "Drive count", value: "Detected by RAID preview" },
        { label: "Controller", value: "Detected by iLO/SSA when available" },
        { label: "VM portability", value: isSingleServer ? "Export or replicate before shipping" : "Shared datastore via NetApp" }
      ],
      basics: [
        { label: "Recommended", value: isSingleServer ? "RAID for local ESXi datastore" : "RAID1 boot, shared VMs on NetApp" },
        { label: "Scenario", value: storageLocation },
        { label: "Dependency", value: "Finish before ESXi install" }
      ],
      current: "RAID readiness is checked from the server workspace and Validation.",
      intended: isSingleServer ? "Local datastore sized for the VM payload." : "Reliable boot volume plus shared storage handoff.",
      need: "Pick a storage posture that matches whether the server ships alone or stays attached to NetApp.",
      nextAction: "Open the server workspace for read-only RAID checks; apply remains guarded in Validation.",
      status: isSingleServer ? statusForAccess(esxi) : statusBadgeForTone(firmwareStatus),
      title: "RAID And Local Storage",
      to: "/overview#topology-map",
      validation: "Server page validates controller, drive count, and destructive safety acknowledgement."
    }),
    setupLane({
      access: cisco,
      actionLabel: "Open map workspace",
      advanced: valuesForLabels(labValues, ["Cisco IP", "VLAN", "MTU", "Gateway"]),
      basics: [
        { label: "Management", value: targetOrUnset(cisco) },
        { label: "Port policy", value: "Access VLANs, BPDU guard, black-hole VLAN options" },
        { label: "Dependency", value: "Required before ESXi and ONTAP LIFs" }
      ],
      current: cisco?.appSees ?? "Not checked",
      intended: "Switch reachable with management, VLANs, and safe edge-port defaults.",
      need: "Network needs to be predictable before hosts and storage attach to it.",
      nextAction: laneNextAction(cisco, "Open the Cisco workspace from the map and run Live Switch Check."),
      title: "Cisco Network",
      to: "/overview#topology-map",
      validation: "Network validation checks management IP, console path, and saved switch intent."
    }),
    setupLane({
      access: esxi,
      actionLabel: "Open map workspace",
      advanced: valuesForLabels(labValues, ["ESXi IP", "Datastore name", "NTP", "DNS"]),
      basics: [
        { label: "Management", value: targetOrUnset(esxi) },
        { label: "Storage target", value: isSingleServer ? "Local datastore" : "NetApp NFS or iSCSI" },
        { label: "Dependency", value: "Wait for RAID and Cisco" }
      ],
      current: esxi?.appSees ?? "Not checked",
      intended: "ESXi reachable, licensed, networked, and pointed at the chosen datastore.",
      need: "Hypervisor setup must match the deployment scenario.",
      nextAction: laneNextAction(esxi, "Open the ESXi or vCenter workspace from the map and run live checks."),
      title: "ESXi Host",
      to: "/overview#topology-map",
      validation: datastore?.status === "accessible" ? "Datastore is visible." : "Validation will check host access and datastore visibility."
    }),
    setupLane({
      access: netapp,
      actionLabel: "Open map workspace",
      advanced: valuesForLabels(labValues, ["NetApp cluster IP", "NetApp NFS LIF", "NetApp console", "Datastore name"]),
      basics: [
        { label: "Mode", value: isSingleServer ? "Not required for single-server local storage" : "Shared storage" },
        { label: "NFS", value: "Default shared datastore path" },
        { label: "iSCSI", value: "Available option when block storage is preferred" }
      ],
      current: isSingleServer ? "Out of scope for this scenario." : netapp?.appSees ?? "Not checked",
      intended: isSingleServer ? "Skipped unless operator chooses shared storage." : "ONTAP licensed, LIFs reachable, export or iSCSI path ready.",
      need: isSingleServer ? "No NetApp step is needed for the single-server build." : "Shared datastore must be ready before VM placement.",
      nextAction: isSingleServer ? "No action required for local-storage scenario." : laneNextAction(netapp, "Open the NetApp workspace from the map and run NetApp Live Check."),
      status: isSingleServer ? "plan_only" : statusForAccess(netapp),
      title: "ONTAP Storage",
      to: "/overview#topology-map",
      validation: isSingleServer ? "Marked not applicable by scenario." : "Storage validation checks management, NFS, iSCSI, and datastore mount state."
    }),
    setupLane({
      access: vcenter,
      actionLabel: "Open map workspace",
      advanced: valuesForLabels(labValues, ["vCenter IP", "Datastore name", "Feature toggles"]),
      basics: [
        { label: "Mode", value: isSingleServer ? "Optional" : "Shared lab control plane" },
        { label: "Inventory", value: vcenter?.appSees ?? "Not checked" },
        { label: "VM handoff", value: isSingleServer ? "Export from host when ready" : "Move between hosts on shared datastore" }
      ],
      current: isSingleServer ? "Optional for this scenario." : vcenter?.appSees ?? "Not checked",
      intended: isSingleServer ? "Only configure if the build needs centralized management." : "vCenter sees host, datastore, and VM inventory.",
      need: isSingleServer ? "Keep hidden unless this server needs vCenter before shipment." : "vCenter is the cleanest place to validate VM portability.",
      nextAction: isSingleServer ? "No action required unless vCenter is selected." : laneNextAction(vcenter, "Open the vCenter workspace from the map and run vCenter Live Check."),
      status: isSingleServer ? "plan_only" : statusForAccess(vcenter),
      title: "vCenter And VM Handoff",
      to: "/overview#topology-map",
      validation: "Validation confirms inventory visibility and datastore attachment."
    })
  ];
  const nextLane = lanes.find((lane) => statusBadgeStatus(lane.status) !== "ready" && statusBadgeStatus(lane.status) !== "plan-only") ?? lanes[0];

  return (
    <section className="setup-lanes" aria-label="Scenario setup lanes">
      <div className="overview-panel-head">
        <div>
          <p className="operator-kicker">Setup lanes</p>
          <h2>{scenario}</h2>
        </div>
        <StatusBadge label={`Next: ${nextLane.title}`} status={statusBadgeStatus(nextLane.status)} />
      </div>
      <p className="setup-lanes-summary">
        {storageLocation}. Basic choices stay visible; fine details live under Additional options for each lane.
      </p>
      <div className="setup-lane-grid">
        {lanes.map((lane) => (
          <Card className="setup-lane-card" hover={false} key={lane.id}>
            <CardHeader>
              <div>
                <p className="operator-kicker">{lane.need}</p>
                <h3>{lane.title}</h3>
              </div>
              <StatusBadge label={displayStatus(lane.status)} status={statusBadgeStatus(lane.status)} />
            </CardHeader>
            <CardContent>
              <div className="setup-lane-state">
                <p><strong>Current:</strong> {lane.current}</p>
                <p><strong>Intended:</strong> {lane.intended}</p>
              </div>
              <ConfigValueList values={lane.basics} />
              <details className="setup-lane-details">
                <summary>Additional options</summary>
                <ConfigValueList values={lane.advanced} />
              </details>
              <p className="setup-lane-validation">{lane.validation}</p>
            </CardContent>
            <CardFooter>
              <ActionLink to={lane.to}>{lane.actionLabel}</ActionLink>
              <span>{lane.nextAction}</span>
            </CardFooter>
          </Card>
        ))}
      </div>
    </section>
  );
}

function setupLane(lane: Omit<SetupLane, "id" | "status"> & { access?: AccessRow; status?: string }): SetupLane {
  return {
    ...lane,
    id: lane.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""),
    status: lane.status || statusForAccess(lane.access)
  };
}

function accessByItem(rows: AccessRow[], item: string): AccessRow | undefined {
  return rows.find((row) => row.item.toLowerCase() === item.toLowerCase());
}

function configValue(values: ConfigValue[], label: string, fallback: string): string {
  return values.find((value) => value.label === label)?.value || fallback;
}

function valuesForLabels(values: ConfigValue[], labels: string[]): ConfigValue[] {
  return labels.map((label) => values.find((value) => value.label === label) ?? { label, value: "Not set up yet" });
}

function targetOrUnset(access: AccessRow | undefined): string {
  return access?.target || "Not set up yet";
}

function laneNextAction(access: AccessRow | undefined, fallback: string): string {
  if (!access) return fallback;
  return access.needs === "Nothing right now" ? "No action required." : access.needs;
}

function statusForAccess(access: AccessRow | undefined): string {
  if (!access) return "not_checked";
  if (access.status === "accessible") return "ready";
  return access.status;
}

function statusBadgeForTone(status: string): string {
  const tone = statusTone(status);
  if (tone === "ready") return "ready";
  if (tone === "blocked") return "blocked";
  return "needs_attention";
}

function OverviewStatCard({
  label,
  meta,
  status,
  value
}: {
  label: string;
  meta: string;
  status: StatusBadgeStatus;
  value: string;
}) {
  return (
    <Card className="overview-stat-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <div>
        <StatusBadge status={status} />
        <small>{meta}</small>
      </div>
    </Card>
  );
}

function NetworkReferencePanel({
  address,
  activeProfile,
  ciscoReadiness,
  ciscoIntentDiff,
  ciscoSshProbe,
  consoleState,
  currentView,
  features,
  firmwareSummaries,
  global,
  labSafety,
  networkRows,
  onCiscoSshRefresh,
  onLabProfileSaved,
  onLabSafetyUpdated
}: {
  address: LabAddressPlan;
  activeProfile: LabProfile | null;
  ciscoReadiness: ProviderProbeResult | null;
  ciscoIntentDiff: ProviderProbeResult | null;
  ciscoSshProbe: ProviderProbeResult | null;
  consoleState: Record<string, unknown>;
  currentView: CurrentViewModel;
  features: LabProfileFeatures | null;
  firmwareSummaries: FirmwareSummary[];
  global: LabProfile["global_settings"] | null;
  labSafety: LabSafetySettings | null;
  networkRows: OperatorObjectRow[];
  onCiscoSshRefresh: () => Promise<void>;
  onLabProfileSaved: () => Promise<void>;
  onLabSafetyUpdated: () => Promise<void>;
}) {
  const counts = workspaceCounts(networkRows);
  const networkStatus = asString(ciscoReadiness?.status) || (address.cisco_management ? "ready" : "not_configured_yet");
  const managementConfigured = asBoolean(ciscoReadiness?.management_configured);
  const consoleStatus = asString(consoleState.status) || "not_checked";
  const ciscoFirmware = firmwareVersion(firmwareSummaries, "cisco");
  const settingsRows = networkSettingsRows({ ciscoFirmware, features, global });
  const issues = networkIssues(currentView, ciscoReadiness);
  const prerequisites = realLabPrerequisites(ciscoReadiness, consoleState, currentView, labSafety);
  const nextSafeAction = humanize(asString(ciscoReadiness?.next_safe_action) || "Run Live Switch Check.");
  const ciscoDriver = ciscoDriverPlan({ address, activeProfile, ciscoIntentDiff, ciscoReadiness, ciscoSshProbe, features, global });

  const providerCards = [
    {
      actionLabel: "Open workspace",
      blockedBy: currentView.blockers[0] || currentView.warnings[0] || nextSafeAction,
      facts: [
        ["Mgmt IP", displayAddress(address.cisco_management)],
        ["Readiness", displayStatus(networkStatus)],
        ["Firmware", ciscoFirmware]
      ],
      gap: nextSafeAction,
      name: "Cisco Switch",
      role: "Switch management",
      status: networkStatus,
      targetState: displayAddress(address.cisco_management),
      to: "/overview#topology-map",
      currentState: asString(ciscoReadiness?.message) || currentView.summary
    },
    {
      actionLabel: "Saved setups",
      blockedBy: consoleStatus === "ready" ? "No console blocker loaded" : "Console path needs confirmation",
      facts: [
        ["Selected path", displayValue(asString(consoleState.selected_path))],
        ["Effective path", displayValue(asString(consoleState.effective_path))],
        ["Status", displayStatus(consoleStatus)]
      ],
      gap: "Review saved setup details if the console path is wrong.",
      name: "Console",
      role: "First contact",
      status: consoleStatus,
      targetState: displayValue(asString(consoleState.selected_path) || asString(consoleState.effective_path)),
      to: "/lab-profiles",
      currentState: displayStatus(consoleStatus)
    },
    {
      actionLabel: "Open workspace",
      blockedBy: managementConfigured ? "No SSH blocker loaded" : "Management access has not been confirmed",
      facts: [
        ["SSH/SCP", boolStateLabel(managementConfigured)],
        ["Secrets", "Configured or missing only"],
        ["Target", displayAddress(address.cisco_management)]
      ],
      gap: "Run Live Switch Check after fixing connectivity or credentials.",
      name: "SSH / SCP",
      role: "Access guard",
      status: managementConfigured ? "ready" : "not_checked",
      targetState: displayAddress(address.cisco_management),
      to: "/overview#topology-map",
      currentState: boolStateLabel(managementConfigured)
    }
  ];

  return (
    <section className="overview-reference" aria-label="Network reference">
      <div className="overview-reference-head">
        <div>
          <p className="operator-kicker">Operator console</p>
          <h2>Network readiness at a glance</h2>
        </div>
        <StatusBadge label="Redesigned view" status="safe-to-run" />
      </div>
      <div className="overview-stat-grid" aria-label="Network summary">
        <OverviewStatCard
          label="Switch status"
          meta={displayAddress(address.cisco_management)}
          status={statusBadgeStatus(networkStatus)}
          value={displayStatus(networkStatus)}
        />
        <OverviewStatCard
          label="Access paths"
          meta={`${counts.ready} ready, ${counts.warning + counts.blocked} need review`}
          status={counts.blocked ? "blocked" : counts.warning ? "needs-attention" : counts.ready ? "ready" : "not-configured"}
          value={`${counts.ready}/${networkRows.length}`}
        />
        <OverviewStatCard
          label="DNS / NTP"
          meta={`NTP ${enabledLabel(features?.enable_ntp)}`}
          status={featureStatus(features, "enable_dns") === "ready" && featureStatus(features, "enable_ntp") === "ready" ? "ready" : "needs-attention"}
          value={features?.enable_dns || features?.enable_ntp ? "Enabled" : "Review"}
        />
        <OverviewStatCard
          label="Cisco firmware"
          meta="Firmware evidence"
          status={ciscoFirmware === "Not checked" ? "needs-attention" : "ready"}
          value={ciscoFirmware}
        />
      </div>

      <div className="overview-panel-head">
        <div>
          <p className="operator-kicker">Network status</p>
          <h2>Switch access and saved settings</h2>
        </div>
        <StatusBadge label={`${issues.length} open`} status={issues.length ? "needs-attention" : "ready"} />
      </div>
      <div className="overview-provider-grid">
        {providerCards.map((provider) => (
          <Card className="overview-provider-card" key={provider.name}>
            <CardHeader>
              <div>
                <p className="operator-kicker">{provider.role}</p>
                <h3>{provider.name}</h3>
              </div>
              <StatusBadge label={displayStatus(provider.status)} status={statusBadgeStatus(provider.status)} />
            </CardHeader>
            <CardContent>
              <dl className="overview-fact-list">
                {provider.facts.map(([label, value]) => (
                  <div key={`${provider.name}-${label}`}>
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
              <div className="overview-current-state-box">
                <p><strong>Current State:</strong> {provider.currentState}</p>
                <p><strong>Target:</strong> {provider.targetState}</p>
                <p><strong>Gap:</strong> {provider.gap}</p>
                <p><strong>Blocked by:</strong> {provider.blockedBy}</p>
              </div>
            </CardContent>
            {provider.to && (
              <CardFooter>
                <ActionLink to={provider.to}>{provider.actionLabel}</ActionLink>
              </CardFooter>
            )}
          </Card>
        ))}
      </div>

      <CiscoDriverPanel plan={ciscoDriver} onRefresh={onCiscoSshRefresh} />

      <section className="overview-safe-actions" aria-label="Next safe actions">
        <NetworkConfigurePanel
          activeProfile={activeProfile}
          address={address}
          features={features}
          global={global}
          onSaved={onLabProfileSaved}
        />
      </section>

      <section className="overview-safe-actions" aria-label="Next safe actions">
        <RealLabPrerequisitesPanel
          items={prerequisites}
        />
      </section>

      <section className="overview-safe-actions" aria-label="Next safe actions">
        <p className="operator-kicker">Next safe actions</p>
        <ul>
          <li>{nextSafeAction}</li>
          <li>Use Network Configure or Saved Setups if the console path or saved network defaults are wrong.</li>
          <li>Open Firmware Upgrades for Cisco firmware evidence before risky changes.</li>
        </ul>
      </section>

      <div className="overview-bottom-grid">
        <Card className="overview-firmware-panel" hover={false}>
          <CardHeader>
            <div>
              <h2>Network Settings</h2>
            </div>
            <span>{settingsRows.length} tracked</span>
          </CardHeader>
          <CompactTable>
            <CompactTableHeader>
              <CompactTableCell>Item</CompactTableCell>
              <CompactTableCell>Current</CompactTableCell>
              <CompactTableCell>Status</CompactTableCell>
              <CompactTableCell>Source</CompactTableCell>
            </CompactTableHeader>
            <tbody>
              {settingsRows.map((row) => (
                <CompactTableRow key={row.item}>
                  <CompactTableCell><strong>{row.item}</strong></CompactTableCell>
                  <CompactTableCell>{row.current}</CompactTableCell>
                  <CompactTableCell><StatusBadge label={displayStatus(row.status)} status={statusBadgeStatus(row.status)} /></CompactTableCell>
                  <CompactTableCell>{row.source}</CompactTableCell>
                </CompactTableRow>
              ))}
            </tbody>
          </CompactTable>
        </Card>

        <Card className="overview-blockers-panel" hover={false}>
          <CardHeader>
            <div>
              <h2>Active Blockers</h2>
            </div>
            <span>{issues.length} open</span>
          </CardHeader>
          <CardContent>
            <div className="overview-blocker-list">
              {issues.length ? (
                issues.slice(0, 4).map((issue) => (
                  <BlockerItem
                    code={issue.code}
                    key={`${issue.code}-${issue.message}`}
                    message={issue.message}
                    severity={issue.severity}
                  />
                ))
              ) : (
                <div className="overview-clear-state">
                  <StatusBadge status="ready" />
                  <span>No active network blockers are loaded for the current view.</span>
                </div>
              )}
            </div>
          </CardContent>
          <CardFooter>
            <ActionLink to="/validation">Open validation</ActionLink>
          </CardFooter>
        </Card>
      </div>
    </section>
  );
}

function RealLabPrerequisitesPanel({
  items
}: {
  items: RealLabPrerequisite[];
}) {
  const missing = items.filter((item) => item.status !== "ready").length;
  return (
    <Card className="network-prereq-panel" hover={false}>
      <CardHeader>
        <div>
          <p className="operator-kicker">Real lab prerequisites</p>
          <h2>Hardware contact gates</h2>
        </div>
        <StatusBadge label={missing ? `${missing} missing` : "Ready"} status={missing ? "blocked" : "ready"} />
      </CardHeader>
      <CardContent>
        <div className="network-prereq-list">
          {items.map((item) => (
            <div className="network-prereq-item" key={item.id}>
              <div>
                <strong>{item.label}</strong>
                <span>{item.detail}</span>
              </div>
              <StatusBadge label={item.value} status={item.status} />
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

type NetworkProfileEditState = {
  ciscoManagement: string;
  dnsServers: string;
  enableDns: boolean;
  enableNtp: boolean;
  enableSnmp: boolean;
  gateway: string;
  mtu: string;
  ntpServers: string;
  subnet: string;
  vlanId: string;
};

type ServerProfileEditState = {
  dnsServers: string;
  esxiManagement: string;
  gateway: string;
  ilo: string;
  iloInitial: string;
  mtu: string;
  ntpServers: string;
  serverEmbeddedNic: string;
  subnet: string;
};

type StorageProfileEditState = {
  clusterMgmt: string;
  controllerASp: string;
  controllerBSp: string;
  gateway: string;
  iscsiLifs: string;
  mtu: string;
  nfsLifs: string;
  nodeAMgmt: string;
  nodeBMgmt: string;
  storageProtocol: string;
  subnet: string;
  svmMgmt: string;
};

type VirtualizationProfileEditState = {
  datastoreTarget: string;
  dnsServers: string;
  enableVcenter: boolean;
  esxiTarget: string;
  gateway: string;
  ntpServers: string;
  subnet: string;
  vcenterTarget: string;
};

function VirtualizationConfigurePanel({
  activeProfile,
  address,
  features,
  global,
  onSaved
}: {
  activeProfile: LabProfile | null;
  address: LabAddressPlan;
  features: LabProfileFeatures | null;
  global: LabProfile["global_settings"] | null;
  onSaved: () => Promise<void>;
}) {
  const [edit, setEdit] = useState<VirtualizationProfileEditState>(() =>
    virtualizationProfileEditStateFrom(activeProfile, address, features, global)
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const profileKey = `${activeProfile?.id ?? "none"}:${activeProfile?.version ?? 0}`;

  useEffect(() => {
    setEdit(virtualizationProfileEditStateFrom(activeProfile, address, features, global));
    setError("");
    setMessage("");
  }, [profileKey, activeProfile, address, features, global]);

  function update<K extends keyof VirtualizationProfileEditState>(key: K, value: VirtualizationProfileEditState[K]) {
    setEdit((current) => ({ ...current, [key]: value }));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!activeProfile) {
      setError("Load the active lab setup before editing virtualization values.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const payload = virtualizationProfilePayload(activeProfile, edit);
      if (activeProfile.source === "saved") {
        await api.updateLabProfile(activeProfile.id, payload);
      } else {
        const saved = await api.createLabProfile(payload);
        await api.activateLabProfile(saved.id);
      }
      await onSaved();
      setMessage("Virtualization config saved.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="network-config-panel" hover={false}>
      <CardHeader>
        <div>
          <p className="operator-kicker">Configure</p>
          <h2>Virtualization lab profile</h2>
        </div>
        <StatusBadge label={edit.enableVcenter ? "In scope" : "Plan only"} status={edit.enableVcenter ? "ready" : "not-configured"} />
      </CardHeader>
      <CardContent>
        <form className="network-config-form" onSubmit={save}>
          <Field label="vCenter target">
            <input value={edit.vcenterTarget} onChange={(event) => update("vcenterTarget", event.target.value)} />
          </Field>
          <Field label="ESXi attach target">
            <input value={edit.esxiTarget} onChange={(event) => update("esxiTarget", event.target.value)} />
          </Field>
          <Field label="Datastore target">
            <input value={edit.datastoreTarget} onChange={(event) => update("datastoreTarget", event.target.value)} />
          </Field>
          <Field label="Subnet">
            <input value={edit.subnet} onChange={(event) => update("subnet", event.target.value)} />
          </Field>
          <Field label="Gateway">
            <input value={edit.gateway} onChange={(event) => update("gateway", event.target.value)} />
          </Field>
          <Field label="DNS servers">
            <input value={edit.dnsServers} onChange={(event) => update("dnsServers", event.target.value)} />
          </Field>
          <Field label="NTP servers">
            <input value={edit.ntpServers} onChange={(event) => update("ntpServers", event.target.value)} />
          </Field>
          <div className="network-config-toggles" aria-label="Virtualization feature toggles">
            <label>
              <input
                checked={edit.enableVcenter}
                onChange={(event) => update("enableVcenter", event.target.checked)}
                type="checkbox"
              />
              <span>vCenter in scope</span>
            </label>
          </div>
          <div className="network-config-actions">
            <button className="operator-primary-button" disabled={busy || !activeProfile} type="submit">
              {busy ? "Saving..." : activeProfile?.source === "saved" ? "Save Virtualization" : "Save As Lab Setup"}
            </button>
            {message && <span className="operator-success-text">{message}</span>}
            {error && <span className="operator-error-text">{error}</span>}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function StorageConfigurePanel({
  activeProfile,
  address,
  features,
  global,
  onSaved
}: {
  activeProfile: LabProfile | null;
  address: LabAddressPlan;
  features: LabProfileFeatures | null;
  global: LabProfile["global_settings"] | null;
  onSaved: () => Promise<void>;
}) {
  const [edit, setEdit] = useState<StorageProfileEditState>(() =>
    storageProfileEditStateFrom(activeProfile, address, features, global)
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const profileKey = `${activeProfile?.id ?? "none"}:${activeProfile?.version ?? 0}`;

  useEffect(() => {
    setEdit(storageProfileEditStateFrom(activeProfile, address, features, global));
    setError("");
    setMessage("");
  }, [profileKey, activeProfile, address, features, global]);

  function update<K extends keyof StorageProfileEditState>(key: K, value: StorageProfileEditState[K]) {
    setEdit((current) => ({ ...current, [key]: value }));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!activeProfile) {
      setError("Load the active lab setup before editing storage values.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const payload = storageProfilePayload(activeProfile, edit);
      if (activeProfile.source === "saved") {
        await api.updateLabProfile(activeProfile.id, payload);
      } else {
        const saved = await api.createLabProfile(payload);
        await api.activateLabProfile(saved.id);
      }
      await onSaved();
      setMessage("Storage config saved.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="network-config-panel" hover={false} id="storage-profile">
      <CardHeader>
        <div>
          <p className="operator-kicker">Configure</p>
          <h2>Storage lab profile</h2>
        </div>
        <StatusBadge label={edit.storageProtocol.toUpperCase()} status="ready" />
      </CardHeader>
      <CardContent>
        <form className="network-config-form" onSubmit={save}>
          <Field label="Active protocol">
            <select value={edit.storageProtocol} onChange={(event) => update("storageProtocol", event.target.value)}>
              <option value="nfs">NFS</option>
              <option value="iscsi">iSCSI</option>
            </select>
          </Field>
          <Field label="Cluster mgmt">
            <input value={edit.clusterMgmt} onChange={(event) => update("clusterMgmt", event.target.value)} />
          </Field>
          <Field label="SVM mgmt">
            <input value={edit.svmMgmt} onChange={(event) => update("svmMgmt", event.target.value)} />
          </Field>
          <Field label="Node A mgmt">
            <input value={edit.nodeAMgmt} onChange={(event) => update("nodeAMgmt", event.target.value)} />
          </Field>
          <Field label="Node B mgmt">
            <input value={edit.nodeBMgmt} onChange={(event) => update("nodeBMgmt", event.target.value)} />
          </Field>
          <Field label="Controller A SP">
            <input value={edit.controllerASp} onChange={(event) => update("controllerASp", event.target.value)} />
          </Field>
          <Field label="Controller B SP">
            <input value={edit.controllerBSp} onChange={(event) => update("controllerBSp", event.target.value)} />
          </Field>
          <Field label="NFS LIFs">
            <input value={edit.nfsLifs} onChange={(event) => update("nfsLifs", event.target.value)} />
          </Field>
          <Field label="iSCSI LIFs">
            <input value={edit.iscsiLifs} onChange={(event) => update("iscsiLifs", event.target.value)} />
          </Field>
          <Field label="Subnet">
            <input value={edit.subnet} onChange={(event) => update("subnet", event.target.value)} />
          </Field>
          <Field label="Gateway">
            <input value={edit.gateway} onChange={(event) => update("gateway", event.target.value)} />
          </Field>
          <Field label="MTU">
            <input inputMode="numeric" value={edit.mtu} onChange={(event) => update("mtu", event.target.value)} />
          </Field>
          <div className="network-config-actions">
            <button className="operator-primary-button" disabled={busy || !activeProfile} type="submit">
              {busy ? "Saving..." : activeProfile?.source === "saved" ? "Save Storage" : "Save As Lab Setup"}
            </button>
            {message && <span className="operator-success-text">{message}</span>}
            {error && <span className="operator-error-text">{error}</span>}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function ServerConfigurePanel({
  activeProfile,
  address,
  global,
  onSaved
}: {
  activeProfile: LabProfile | null;
  address: LabAddressPlan;
  global: LabProfile["global_settings"] | null;
  onSaved: () => Promise<void>;
}) {
  const [edit, setEdit] = useState<ServerProfileEditState>(() =>
    serverProfileEditStateFrom(activeProfile, address, global)
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const profileKey = `${activeProfile?.id ?? "none"}:${activeProfile?.version ?? 0}`;

  useEffect(() => {
    setEdit(serverProfileEditStateFrom(activeProfile, address, global));
    setError("");
    setMessage("");
  }, [profileKey, activeProfile, address, global]);

  function update<K extends keyof ServerProfileEditState>(key: K, value: ServerProfileEditState[K]) {
    setEdit((current) => ({ ...current, [key]: value }));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!activeProfile) {
      setError("Load the active lab setup before editing server values.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const payload = serverProfilePayload(activeProfile, edit);
      if (activeProfile.source === "saved") {
        await api.updateLabProfile(activeProfile.id, payload);
      } else {
        const saved = await api.createLabProfile(payload);
        await api.activateLabProfile(saved.id);
      }
      await onSaved();
      setMessage("Server config saved.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="network-config-panel" hover={false}>
      <CardHeader>
        <div>
          <p className="operator-kicker">Configure</p>
          <h2>Server lab profile</h2>
        </div>
        <StatusBadge
          label={activeProfile?.source === "saved" ? "Saved profile" : "Save as profile"}
          status={activeProfile ? "ready" : "not-configured"}
        />
      </CardHeader>
      <CardContent>
        <form className="network-config-form" onSubmit={save}>
          <Field label="iLO IP">
            <input value={edit.ilo} onChange={(event) => update("ilo", event.target.value)} />
          </Field>
          <Field label="Initial iLO IP">
            <input value={edit.iloInitial} onChange={(event) => update("iloInitial", event.target.value)} />
          </Field>
          <Field label="Embedded NIC">
            <input value={edit.serverEmbeddedNic} onChange={(event) => update("serverEmbeddedNic", event.target.value)} />
          </Field>
          <Field label="ESXi mgmt IP">
            <input value={edit.esxiManagement} onChange={(event) => update("esxiManagement", event.target.value)} />
          </Field>
          <Field label="Subnet">
            <input value={edit.subnet} onChange={(event) => update("subnet", event.target.value)} />
          </Field>
          <Field label="Gateway">
            <input value={edit.gateway} onChange={(event) => update("gateway", event.target.value)} />
          </Field>
          <Field label="DNS servers">
            <input value={edit.dnsServers} onChange={(event) => update("dnsServers", event.target.value)} />
          </Field>
          <Field label="NTP servers">
            <input value={edit.ntpServers} onChange={(event) => update("ntpServers", event.target.value)} />
          </Field>
          <Field label="MTU">
            <input inputMode="numeric" value={edit.mtu} onChange={(event) => update("mtu", event.target.value)} />
          </Field>
          <div className="network-config-actions">
            <button className="operator-primary-button" disabled={busy || !activeProfile} type="submit">
              {busy ? "Saving..." : activeProfile?.source === "saved" ? "Save Server" : "Save As Lab Setup"}
            </button>
            {message && <span className="operator-success-text">{message}</span>}
            {error && <span className="operator-error-text">{error}</span>}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

type CiscoVlanPlan = {
  id: string;
  name: string;
  gateway: string;
  role: string;
  status: StatusBadgeStatus;
};

type CiscoPortPlan = {
  accessVlan: string;
  acl: string;
  bpduGuard: boolean;
  description: string;
  mode: "access" | "trunk" | "disabled";
  port: string;
  role: string;
  status: StatusBadgeStatus;
  trunkVlans: string;
};

type CiscoGuardrailPlan = {
  detail: string;
  label: string;
  status: StatusBadgeStatus;
};

type CiscoDriftItem = {
  current: string;
  desired: string;
  label: string;
  status: StatusBadgeStatus;
  statusLabel?: string;
};

type CiscoPortDrift = {
  current: string;
  intended: string;
  port: string;
  reason: string;
  status: StatusBadgeStatus;
};

type CiscoRemediationStep = {
  detail: string;
  label: string;
  nextAction: string;
  status: StatusBadgeStatus;
};

type CiscoDriverPlan = {
  aclLanes: CiscoGuardrailPlan[];
  blackHoleVlan: string;
  commandPreviewStatus: StatusBadgeStatus;
  commandPreviewStatusLabel: string;
  commandPreviewSummary: string;
  commands: string[];
  commandNotes: string[];
  drift: CiscoDriftItem[];
  guardrails: CiscoGuardrailPlan[];
  liveEvidence: string;
  liveStatus: StatusBadgeStatus;
  liveStatusLabel: string;
  nextReadAction: string;
  portDrift: CiscoPortDrift[];
  ports: CiscoPortPlan[];
  probeStatus: string;
  probeSummary: string;
  remediationSteps: CiscoRemediationStep[];
  remediationSummary: string;
  remediationStatus: StatusBadgeStatus;
  vlans: CiscoVlanPlan[];
};

function CiscoDriverPanel({ plan, onRefresh }: { plan: CiscoDriverPlan; onRefresh: () => Promise<void> }) {
  const activePorts = plan.ports.filter((port) => port.mode !== "disabled").length;
  const protectedPorts = plan.ports.filter((port) => port.bpduGuard).length;
  const driftOpen = plan.drift.filter((item) => item.status !== "ready").length;
  const refreshRunning = plan.probeStatus === "running";

  return (
    <section className="cisco-driver-panel" aria-label="Cisco switch driver">
      <div className="cisco-driver-head">
        <div>
          <p className="operator-kicker">Cisco driver</p>
          <h2>Switch configuration cockpit</h2>
          <p>Compare live switch state with intended VLANs, ports, guardrails, and candidate config before any guarded apply.</p>
        </div>
        <StatusBadge label={plan.liveStatusLabel} status={plan.liveStatus} />
      </div>

      <div className="cisco-sync-strip" aria-label="Cisco current intent drift">
        <div>
          <p className="operator-kicker">Current to intent</p>
          <h3>{driftOpen ? `${driftOpen} drift checks` : "Switch matches intended profile"}</h3>
          <span>{plan.nextReadAction}</span>
        </div>
        <div>
          <p className="operator-kicker">Live SSH probe</p>
          <h3>{displayStatus(plan.probeStatus)}</h3>
          <span>{plan.probeSummary}</span>
          <button
            type="button"
            className="cisco-live-refresh-button"
            disabled={refreshRunning}
            onClick={() => {
              void onRefresh();
            }}
          >
            <RefreshCw size={15} />
            <span>{refreshRunning ? "Running" : "Refresh live evidence"}</span>
          </button>
        </div>
        <div className="cisco-sync-flow" aria-label="Cisco driver flow">
          <span>Current</span>
          <strong>Intent</strong>
          <strong>Drift</strong>
          <strong>Candidate config</strong>
        </div>
      </div>

      <div className="cisco-driver-metrics" aria-label="Cisco switch plan summary">
        <CiscoDriverMetric icon={<Layers size={18} />} label="VLANs" value={String(plan.vlans.length)} />
        <CiscoDriverMetric icon={<EthernetPort size={18} />} label="Active ports" value={`${activePorts}/${plan.ports.length}`} />
        <CiscoDriverMetric icon={<ShieldCheck size={18} />} label="BPDU guard" value={`${protectedPorts} ports`} />
        <CiscoDriverMetric icon={<Ban size={18} />} label="Black-hole VLAN" value={plan.blackHoleVlan} />
      </div>

      <div className="cisco-driver-grid">
        <Card className="cisco-driver-card cisco-vlan-card" hover={false}>
          <CardHeader>
            <div>
              <p className="operator-kicker">Layer 3</p>
              <h3>VLANs and gateways</h3>
            </div>
            <StatusBadge label="SVI plan" status="safe-to-run" />
          </CardHeader>
          <CompactTable className="cisco-driver-table">
            <CompactTableHeader>
              <CompactTableCell>VLAN</CompactTableCell>
              <CompactTableCell>Name</CompactTableCell>
              <CompactTableCell>Gateway</CompactTableCell>
              <CompactTableCell>Status</CompactTableCell>
            </CompactTableHeader>
            <tbody>
              {plan.vlans.map((vlan) => (
                <CompactTableRow key={vlan.id}>
                  <CompactTableCell><strong>{vlan.id}</strong></CompactTableCell>
                  <CompactTableCell>{vlan.name}</CompactTableCell>
                  <CompactTableCell>{vlan.gateway}</CompactTableCell>
                  <CompactTableCell><StatusBadge label={vlan.role} status={vlan.status} /></CompactTableCell>
                </CompactTableRow>
              ))}
            </tbody>
          </CompactTable>
        </Card>

        <Card className="cisco-driver-card" hover={false}>
          <CardHeader>
            <div>
              <p className="operator-kicker">Drift</p>
              <h3>Current versus intent</h3>
            </div>
            <StatusBadge label={driftOpen ? `${driftOpen} open` : "In sync"} status={driftOpen ? "needs-attention" : "ready"} />
          </CardHeader>
          <CardContent>
            <div className="cisco-drift-list">
              {plan.drift.map((item) => (
                <div key={item.label}>
                  <span>{item.label}</span>
                  <strong>{item.current}</strong>
                  <small>{item.desired}</small>
                  <StatusBadge label={item.statusLabel} status={item.status} />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <details className="cisco-driver-details" open={plan.portDrift.length > 0}>
        <summary>
          <span>
            <strong>Live port drift</strong>
            <small>
              {plan.portDrift.length
                ? `${plan.portDrift.length} live interface ${plan.portDrift.length === 1 ? "mismatch needs" : "mismatches need"} review before apply.`
                : "No live interface mismatches were detected from the parsed SSH output."}{" "}
              {plan.liveEvidence}
            </small>
          </span>
          <StatusBadge
            label={plan.portDrift.length ? `${plan.portDrift.length} mismatches` : "No drift"}
            status={plan.portDrift.length ? "needs-attention" : "ready"}
          />
        </summary>
        <CompactTable className="cisco-port-drift-table">
          <CompactTableHeader>
            <CompactTableCell>Port</CompactTableCell>
            <CompactTableCell>Live current</CompactTableCell>
            <CompactTableCell>Intended</CompactTableCell>
            <CompactTableCell>Reason</CompactTableCell>
            <CompactTableCell>Status</CompactTableCell>
          </CompactTableHeader>
          <tbody>
            {plan.portDrift.length ? (
              plan.portDrift.map((item) => (
                <CompactTableRow key={`${item.port}-${item.reason}`}>
                  <CompactTableCell><strong>{item.port}</strong></CompactTableCell>
                  <CompactTableCell>{item.current}</CompactTableCell>
                  <CompactTableCell>{item.intended}</CompactTableCell>
                  <CompactTableCell>{item.reason}</CompactTableCell>
                  <CompactTableCell><StatusBadge status={item.status} /></CompactTableCell>
                </CompactTableRow>
              ))
            ) : (
              <CompactTableRow>
                <CompactTableCell><strong>Parsed ports</strong></CompactTableCell>
                <CompactTableCell>No mismatches detected</CompactTableCell>
                <CompactTableCell>Intent matched where live rows existed</CompactTableCell>
                <CompactTableCell>Ready for guarded apply review</CompactTableCell>
                <CompactTableCell><StatusBadge status="ready" /></CompactTableCell>
              </CompactTableRow>
            )}
          </tbody>
        </CompactTable>
      </details>

      <details className="cisco-driver-details">
        <summary>
          <span>
            <strong>Port policy matrix</strong>
            <small>{plan.ports.length} intended interface policies, including parking controls.</small>
          </span>
          <StatusBadge label={`${plan.ports.length} ports`} status="plan-only" />
        </summary>
        <CompactTable className="cisco-port-table">
          <CompactTableHeader>
            <CompactTableCell>Port</CompactTableCell>
            <CompactTableCell>Role</CompactTableCell>
            <CompactTableCell>Mode</CompactTableCell>
            <CompactTableCell>VLANs</CompactTableCell>
            <CompactTableCell>BPDU</CompactTableCell>
            <CompactTableCell>ACL</CompactTableCell>
            <CompactTableCell>Status</CompactTableCell>
          </CompactTableHeader>
          <tbody>
            {plan.ports.map((port) => (
              <CompactTableRow key={port.port}>
                <CompactTableCell>
                  <strong>{port.port}</strong>
                  <span>{port.description}</span>
                </CompactTableCell>
                <CompactTableCell>{port.role}</CompactTableCell>
                <CompactTableCell>{port.mode}</CompactTableCell>
                <CompactTableCell>{port.mode === "trunk" ? port.trunkVlans : port.accessVlan}</CompactTableCell>
                <CompactTableCell>{port.bpduGuard ? "Enabled" : "Off"}</CompactTableCell>
                <CompactTableCell>{port.acl}</CompactTableCell>
                <CompactTableCell><StatusBadge status={port.status} /></CompactTableCell>
              </CompactTableRow>
            ))}
          </tbody>
        </CompactTable>
      </details>

      <details className="cisco-driver-details">
        <summary>
          <span>
            <strong>Guardrails and ACL lanes</strong>
            <small>Loop protection, parking VLAN, and traffic-control lanes before apply.</small>
          </span>
          <StatusBadge label="Attended apply" status="needs-attention" />
        </summary>
        <CardContent>
          <div className="cisco-guardrail-list">
            {[...plan.guardrails, ...plan.aclLanes].map((item) => (
                <div key={`${item.label}-${item.detail}`}>
                  <span>{item.label}</span>
                  <strong>{item.detail}</strong>
                  <StatusBadge status={item.status} />
                </div>
            ))}
          </div>
        </CardContent>
      </details>

      <RemediationLadder
        className="cisco-remediation-panel"
        defaultOpen={plan.remediationStatus !== "ready"}
        emptyStep={{
          detail: "Run live Cisco diff before remediation can be reviewed.",
          label: "Load live switch evidence",
          nextAction: plan.nextReadAction,
          status: "not-configured"
        }}
        status={plan.remediationStatus}
        statusLabel={displayStatus(plan.remediationStatus)}
        steps={plan.remediationSteps.map((item) => ({
          detail: item.detail,
          label: item.label,
          nextAction: item.nextAction,
          status: item.status
        }))}
        summary={plan.remediationSummary}
        title="Remediation review"
      />

      <details className="cisco-command-preview">
        <summary>
          <span>
            <strong>Intent config preview</strong>
            <small>{plan.commandPreviewSummary}</small>
          </span>
          <StatusBadge label={plan.commandPreviewStatusLabel} status={plan.commandPreviewStatus} />
        </summary>
        <pre>{plan.commands.join("\n")}</pre>
        {plan.commandNotes.length > 0 && (
          <div className="cisco-command-notes">
            {plan.commandNotes.map((note) => (
              <span key={note}>{note}</span>
            ))}
          </div>
        )}
      </details>
    </section>
  );
}

function CiscoDriverMetric({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="cisco-driver-metric">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ciscoDriverPlan({
  address,
  activeProfile,
  ciscoIntentDiff,
  ciscoReadiness,
  ciscoSshProbe,
  features,
  global
}: {
  address: LabAddressPlan;
  activeProfile: LabProfile | null;
  ciscoIntentDiff: ProviderProbeResult | null;
  ciscoReadiness: ProviderProbeResult | null;
  ciscoSshProbe: ProviderProbeResult | null;
  features: LabProfileFeatures | null;
  global: LabProfile["global_settings"] | null;
}): CiscoDriverPlan {
  const managementVlan = displayValue(asString(global?.vlan_id) || asString(activeProfile?.vlan_id) || "10");
  const gateway = displayAddress(global?.gateway ?? activeProfile?.gateway);
  const esxiVlan = managementVlan === "20" ? "30" : "20";
  const storageVlan = managementVlan === "30" ? "40" : "30";
  const blackHoleVlan = "999";
  const nativeVlan = "4094";
  const managementName = `LAB-MGMT-${managementVlan}`;
  const vlans: CiscoVlanPlan[] = [
    {
      gateway,
      id: managementVlan,
      name: managementName,
      role: "Management",
      status: gateway === "Not set up yet" ? "needs-attention" : "ready"
    },
    {
      gateway: gatewayForSiblingVlan(gateway, esxiVlan),
      id: esxiVlan,
      name: "ESXI-HOSTS",
      role: "Compute",
      status: "plan-only"
    },
    {
      gateway: gatewayForSiblingVlan(gateway, storageVlan),
      id: storageVlan,
      name: "STORAGE-NFS",
      role: "Storage",
      status: "plan-only"
    },
    {
      gateway: "none",
      id: blackHoleVlan,
      name: "BLACKHOLE-PARKING",
      role: "No L3",
      status: "blocked"
    }
  ];
  const ports: CiscoPortPlan[] = [
    {
      accessVlan: managementVlan,
      acl: "MGMT-IN",
      bpduGuard: true,
      description: "App host / jump box",
      mode: "access",
      port: "Gi1/0/1",
      role: "Operator access",
      status: "ready",
      trunkVlans: "-"
    },
    {
      accessVlan: managementVlan,
      acl: "LAB-MGMT-IN",
      bpduGuard: true,
      description: "HPE iLO",
      mode: "access",
      port: "Gi1/0/2",
      role: "Server mgmt",
      status: "ready",
      trunkVlans: "-"
    },
    {
      accessVlan: "-",
      acl: "TRUNK-FILTER",
      bpduGuard: false,
      description: "ESXi vmnic uplink A",
      mode: "trunk",
      port: "Gi1/0/3",
      role: "ESXi trunk",
      status: "plan-only",
      trunkVlans: `${managementVlan},${esxiVlan},${storageVlan}`
    },
    {
      accessVlan: "-",
      acl: "TRUNK-FILTER",
      bpduGuard: false,
      description: "ESXi vmnic uplink B",
      mode: "trunk",
      port: "Gi1/0/4",
      role: "ESXi trunk",
      status: "plan-only",
      trunkVlans: `${managementVlan},${esxiVlan},${storageVlan}`
    },
    {
      accessVlan: storageVlan,
      acl: "STORAGE-NFS-IN",
      bpduGuard: true,
      description: "NetApp data path A",
      mode: "access",
      port: "Gi1/0/5",
      role: "Storage",
      status: "needs-attention",
      trunkVlans: "-"
    },
    {
      accessVlan: storageVlan,
      acl: "STORAGE-NFS-IN",
      bpduGuard: true,
      description: "NetApp data path B",
      mode: "access",
      port: "Gi1/0/6",
      role: "Storage",
      status: "needs-attention",
      trunkVlans: "-"
    },
    {
      accessVlan: blackHoleVlan,
      acl: "DROP-ALL",
      bpduGuard: true,
      description: "Unused ports",
      mode: "disabled",
      port: "Gi1/0/7-24",
      role: "Parking",
      status: "blocked",
      trunkVlans: "-"
    }
  ];

  const dnsState = enabledLabel(features?.enable_dns);
  const ntpState = enabledLabel(features?.enable_ntp);
  const intentCurrent = objectValue(ciscoIntentDiff?.current);
  const intentDiff = objectValue(ciscoIntentDiff?.diff);
  const intentGuardrails = objectValue(intentDiff.guardrails);
  const candidatePreview = objectValue(ciscoIntentDiff?.candidate_config_preview);
  const remediationPlan = objectValue(ciscoIntentDiff?.remediation_plan);
  const sshResults = objectValue(ciscoSshProbe?.command_results);
  const versionResult = objectValue(sshResults["show version"]);
  const vlanResult = objectValue(sshResults["show vlan brief"]);
  const interfaceResult = objectValue(sshResults["show interfaces status"]);
  const versionHint = asString(versionResult.version_hint);
  const currentVlans = ciscoCurrentVlans(intentCurrent.vlans, stringArray(vlanResult.stdout_summary));
  const currentPorts = ciscoCurrentPorts(intentCurrent.ports, stringArray(interfaceResult.stdout_summary));
  const backendPortDrift = ciscoBackendPortDrift(intentDiff.ports);
  const parsedReadReady = (
    asString(ciscoIntentDiff?.source_type) === "live_probe" ||
    asString(ciscoSshProbe?.status) === "ok"
  ) && currentVlans.length > 0;
  const guardrails = ciscoGuardrailRows(intentGuardrails, [
    { detail: `Default native VLAN ${nativeVlan}`, label: "Trunk native", status: "safe-to-run" },
    { detail: `Parking VLAN ${blackHoleVlan} with shutdown`, label: "Unused ports", status: "blocked" },
    { detail: "portfast + bpduguard on edge access", label: "Loop guard", status: "ready" },
    { detail: `DNS ${dnsState}, NTP ${ntpState}`, label: "Services", status: features?.enable_dns || features?.enable_ntp ? "ready" : "needs-attention" }
  ]);
  const aclLanes = ciscoAclLaneRows(intentGuardrails, [
    { detail: "Allow app host to SSH/SCP/SNMP targets", label: "MGMT-IN", status: "plan-only" },
    { detail: "Allow ESXi to NFS LIFs, deny lateral noise", label: "STORAGE-NFS-IN", status: "needs-attention" },
    { detail: "Deny any unused or unknown endpoint", label: "DROP-ALL", status: "blocked" }
  ]);
  const liveEvidence = parsedReadReady
    ? `Evidence: current-intent diff, ${currentPorts.length} interface rows, ${currentVlans.length} VLAN rows parsed at ${formatDateTime(asString(ciscoIntentDiff?.checked_at) || asString(ciscoSshProbe?.checked_at))}.`
    : "Evidence: run Refresh live SSH to parse show-command output.";
  const liveReady = parsedReadReady || asBoolean(ciscoReadiness?.management_configured) || asString(ciscoReadiness?.status) === "ready";
  const desiredVlanIds = vlans.map((vlan) => vlan.id);
  const missingVlans = desiredVlanIds.filter((id) => !currentVlans.some((vlan) => vlan.id === id));
  const activeCurrentPorts = currentPorts.filter((port) => port.status === "connected");
  const portDrift = parsedReadReady ? (backendPortDrift.length ? backendPortDrift : ciscoPortDrift(ports, currentPorts)) : [];
  const trunkOrStorageDrift = portDrift.filter((item) => item.status === "blocked");
  const liveStatus: StatusBadgeStatus = parsedReadReady ? "ready" : liveReady ? "safe-to-run" : "needs-attention";
  const liveStatusLabel = parsedReadReady ? "Live intent parsed" : liveReady ? "Read sync ready" : "Read sync needed";
  const nextReadAction = parsedReadReady
    ? "Live show version, interfaces, and VLAN state parsed. Review drift before any guarded apply."
    : liveReady
      ? "Run read-only Cisco show commands next. Unknown parsed sections must stay unknown, not in sync."
      : "Prove read-only Cisco access first: show vlan, show running-config, and show spanning-tree.";
  const drift: CiscoDriftItem[] = [
    {
      current: parsedReadReady
        ? `IOS XE ${versionHint || "unknown"}; VLANs ${currentVlans.map((vlan) => `${vlan.id} ${vlan.name}`).join(", ")}`
        : liveReady ? "Unknown: reachability proven, show-command parse pending" : "Unknown: no parsed show-command state yet",
      desired: `${planLabel(vlans.length)} intended VLANs, native ${nativeVlan}, parking ${blackHoleVlan}`,
      label: "Switch state",
      status: parsedReadReady ? (missingVlans.length ? "needs-attention" : "ready") : liveReady ? "plan-only" : "needs-attention",
      statusLabel: parsedReadReady ? (missingVlans.length ? `Missing ${missingVlans.join(", ")}` : "In sync") : "Unknown"
    },
    {
      current: parsedReadReady
        ? portDrift.length
          ? `${activeCurrentPorts.length} connected ports parsed; ${portDrift.slice(0, 3).map((item) => `${item.port}: ${item.reason}`).join("; ")}`
          : `${activeCurrentPorts.length} connected ports parsed; ${currentPorts.length} ports reported`
        : "Unknown: port running-config not loaded",
      desired: `${planLabel(activePortCount(ports))} active policies, ${protectedPortCount(ports)} BPDU-guarded edge ports`,
      label: "Interfaces",
      status: parsedReadReady ? (trunkOrStorageDrift.length ? "blocked" : portDrift.length ? "needs-attention" : "ready") : "needs-attention",
      statusLabel: parsedReadReady ? (portDrift.length ? `${portDrift.length} mismatches` : "In sync") : "Unknown"
    },
    {
      current: ciscoGuardrailCurrentSummary(objectValue(intentGuardrails.acl_lanes), "ACL lines not loaded"),
      desired: "MGMT-IN, STORAGE-NFS-IN, DROP-ALL lanes",
      label: "ACL lanes",
      status: ciscoEvidenceStatus(objectValue(intentGuardrails.acl_lanes)),
      statusLabel: ciscoGuardrailStatusLabel(objectValue(intentGuardrails.acl_lanes))
    }
  ];
  const candidateCommands = stringArray(candidatePreview.commands);
  const candidateStatus = asString(candidatePreview.status);
  const candidateSummary = asString(candidatePreview.summary);
  const commands = candidateCommands.length
    ? candidateCommands
    : [
        candidateStatus === "ready_no_changes"
          ? "# No candidate config lines are needed from the parsed live drift."
          : "# Candidate config is withheld until the live Cisco current-to-intent diff returns backend-generated commands."
      ];
  const commandPreviewStatus = candidateStatus === "ready_no_changes"
    ? "ready"
    : ciscoDiffStatus(candidateStatus || (parsedReadReady ? "warning" : "not_checked"));
  const commandPreviewStatusLabel = candidateStatus === "ready_no_changes"
    ? "No changes"
    : candidateCommands.length
      ? `${candidateCommands.length} lines`
      : parsedReadReady ? "Review only" : "Awaiting live diff";
  const remediationStatus = ciscoDiffStatus(asString(remediationPlan.status) || (parsedReadReady ? "warning" : "not_checked"));
  const remediationSteps = ciscoRemediationSteps(remediationPlan.steps, [
    {
      detail: parsedReadReady
        ? missingVlans.length ? missingVlans.join(", ") : "No intended VLANs are missing."
        : "Run live diff to identify missing VLANs.",
      label: "Create missing VLANs",
      nextAction: "Review generated VLAN commands before guarded apply.",
      status: parsedReadReady ? missingVlans.length ? "needs-attention" : "ready" : "plan-only"
    },
    {
      detail: portDrift.length ? `${portDrift.length} port drift item(s).` : "No port drift parsed yet.",
      label: "Align intended ports",
      nextAction: "Review access/trunk mode against cabling.",
      status: portDrift.length ? "needs-attention" : parsedReadReady ? "ready" : "plan-only"
    },
    {
      detail: "ACL lanes stay review-only until exact source/destination policy is approved.",
      label: "Review guardrails",
      nextAction: "Do not synthesize ACL rules from partial evidence.",
      status: guardrails.some((item) => item.status !== "ready") || aclLanes.some((item) => item.status !== "ready") ? "needs-attention" : "ready"
    }
  ]);

  return {
    aclLanes,
    blackHoleVlan,
    commandNotes: stringArray(candidatePreview.notes).concat(stringArray(candidatePreview.not_attempted).map((item) => `Not attempted: ${item}`)),
    commandPreviewStatus,
    commandPreviewStatusLabel,
    commandPreviewSummary: candidateSummary || (
      parsedReadReady
        ? "Candidate preview is based on parsed live drift and still requires attended review before any apply."
        : "Candidate generation stays blocked until read-only Cisco output is parsed."
    ),
    commands,
    drift,
    guardrails,
    liveEvidence,
    liveStatus,
    liveStatusLabel,
    nextReadAction,
    portDrift,
    ports,
    probeStatus: asString(ciscoIntentDiff?.status) || asString(ciscoSshProbe?.status) || "not_checked",
    probeSummary: asString(ciscoIntentDiff?.message) || asString(ciscoSshProbe?.message) || "Live Cisco evidence has not returned yet.",
    remediationSteps,
    remediationSummary: asString(remediationPlan.summary) || (
      parsedReadReady
        ? "Review drift, guardrails, and generated candidate lines before any guarded apply."
        : "Run live Cisco diff before remediation can be reviewed."
    ),
    remediationStatus,
    vlans
  };
}

function ciscoRemediationSteps(value: unknown, fallback: CiscoRemediationStep[]): CiscoRemediationStep[] {
  const rows = recordArray(value).flatMap((row) => {
    const label = asString(row.label);
    if (!label) return [];
    return [{
      detail: asString(row.detail) || "Review required.",
      label,
      nextAction: asString(row.next_action) || asString(row.nextAction) || "Review before apply.",
      status: ciscoDiffStatus(asString(row.status) || "not_checked")
    }];
  });
  return rows.length ? rows : fallback;
}

function ciscoCurrentVlans(value: unknown, fallbackLines: string[]) {
  const rows = recordArray(value)
    .map((row) => ({ id: asString(row.id), name: asString(row.name) }))
    .filter((row) => row.id);
  return rows.length ? rows : parsedCiscoVlans(fallbackLines);
}

function ciscoCurrentPorts(value: unknown, fallbackLines: string[]) {
  const rows = recordArray(value)
    .map((row) => ({
      port: asString(row.port),
      status: asString(row.status),
      vlan: asString(row.vlan) || "unknown"
    }))
    .filter((row) => row.port);
  return rows.length ? rows : parsedCiscoPorts(fallbackLines);
}

function ciscoBackendPortDrift(value: unknown): CiscoPortDrift[] {
  return recordArray(value).flatMap((row) => {
    const port = asString(row.port);
    if (!port) return [];
    const current = objectValue(row.current);
    return [{
      current: `${asString(current.status) || "unknown"} ${asString(current.vlan) || "unknown"}`,
      intended: asString(row.expected) || "Configured Cisco intent",
      port,
      reason: asString(row.reason) || "Live state does not match intent.",
      status: ciscoDiffStatus(row.status)
    }];
  });
}

function ciscoGuardrailRows(guardrails: Record<string, unknown>, fallback: CiscoGuardrailPlan[]): CiscoGuardrailPlan[] {
  const rows = [
    ciscoGuardrailRow("bpdu_guard", "Loop guard", guardrails.bpdu_guard),
    ciscoGuardrailRow("blackhole_vlan", "Black-hole VLAN", guardrails.blackhole_vlan)
  ].filter(Boolean) as CiscoGuardrailPlan[];
  return rows.length ? rows : fallback;
}

function ciscoAclLaneRows(guardrails: Record<string, unknown>, fallback: CiscoGuardrailPlan[]): CiscoGuardrailPlan[] {
  const acl = objectValue(guardrails.acl_lanes);
  if (!Object.keys(acl).length) return fallback;
  const missing = stringArray(acl.missing);
  const matched = stringArray(acl.matched);
  const rows = [...matched.map((label) => ({ detail: "Found in live running-config include output", label, status: "ready" as StatusBadgeStatus }))]
    .concat(missing.map((label) => ({ detail: "Missing from live running-config include output", label, status: "needs-attention" as StatusBadgeStatus })));
  return rows.length ? rows : [{
    detail: asString(acl.reason) || "ACL lane evidence was checked but no lane details were returned.",
    label: "ACL lanes",
    status: ciscoEvidenceStatus(acl)
  }];
}

function ciscoGuardrailRow(key: string, label: string, value: unknown): CiscoGuardrailPlan | null {
  const evidence = objectValue(value);
  if (!Object.keys(evidence).length) return null;
  const missing = stringArray(evidence.missing);
  const matched = stringArray(evidence.matched);
  return {
    detail: matched.length
      ? `Found: ${matched.join(", ")}`
      : missing.length
        ? `Missing: ${missing.join(", ")}`
        : asString(evidence.reason) || `${key} checked`,
    label,
    status: ciscoEvidenceStatus(evidence)
  };
}

function ciscoGuardrailCurrentSummary(evidence: Record<string, unknown>, emptyLabel: string) {
  const matched = stringArray(evidence.matched);
  const missing = stringArray(evidence.missing);
  if (matched.length) return `Found ${matched.join(", ")}`;
  if (missing.length) return `Missing ${missing.join(", ")}`;
  return `Unknown: ${emptyLabel}`;
}

function ciscoGuardrailStatusLabel(evidence: Record<string, unknown>) {
  return displayStatus(asString(evidence.status) || "not_checked");
}

function ciscoEvidenceStatus(evidence: Record<string, unknown>): StatusBadgeStatus {
  return ciscoDiffStatus(asString(evidence.status));
}

function ciscoDiffStatus(value: unknown): StatusBadgeStatus {
  const status = asString(value);
  if (["ready", "ok", "current", "compliant"].includes(status)) return "ready";
  if (["blocked", "failed", "hard_fail"].includes(status)) return "blocked";
  if (["warning", "drift", "partial", "needs_attention"].includes(status)) return "needs-attention";
  if (["not_checked", "unknown", "plan_only"].includes(status)) return "plan-only";
  return status ? "needs-attention" : "plan-only";
}

function activePortCount(ports: CiscoPortPlan[]) {
  return ports.filter((port) => port.mode !== "disabled").length;
}

function protectedPortCount(ports: CiscoPortPlan[]) {
  return ports.filter((port) => port.bpduGuard).length;
}

function planLabel(count: number) {
  return String(count);
}

function parsedCiscoVlans(lines: string[]) {
  return lines.flatMap((line) => {
    const match = line.trim().match(/^(\d{1,4})\s+([A-Za-z0-9_.:-]+)/);
    if (!match) return [];
    return [{ id: match[1], name: match[2] }];
  });
}

function parsedCiscoPorts(lines: string[]) {
  return lines.flatMap((line) => {
    const parts = line.trim().split(/\s+/);
    const statusIndex = parts.findIndex((part) => ["connected", "notconnect", "disabled", "err-disabled"].includes(part));
    if (!parts[0]?.startsWith("Gi") || statusIndex < 0) return [];
    return [{ port: parts[0], status: parts[statusIndex], vlan: parts[statusIndex + 1] || "unknown" }];
  });
}

function ciscoPortDrift(
  intendedPorts: CiscoPortPlan[],
  currentPorts: Array<{ port: string; status: string; vlan: string }>
): CiscoPortDrift[] {
  const currentByPort = new Map(currentPorts.map((port) => [normalizeCiscoPort(port.port), port]));
  return intendedPorts.flatMap((policy) =>
    expandCiscoPortRange(policy.port).flatMap((port) => {
      const current = currentByPort.get(normalizeCiscoPort(port));
      if (!current) {
        return [];
      }
      const live = `${current.status} ${current.vlan}`;
      const intended = intendedCiscoPortSummary(policy);
      if (policy.mode === "trunk") {
        const isTrunk = current.vlan.toLowerCase() === "trunk";
        return isTrunk
          ? []
          : [{
              current: live,
              intended,
              port,
              reason: `Expected trunk ${policy.trunkVlans}, live mode is access VLAN ${current.vlan}`,
              status: "blocked" as StatusBadgeStatus
            }];
      }
      if (policy.mode === "access") {
        return current.vlan === policy.accessVlan
          ? []
          : [{
              current: live,
              intended,
              port,
              reason: `Expected access VLAN ${policy.accessVlan}`,
              status: policy.role === "Storage" ? "blocked" as StatusBadgeStatus : "needs-attention" as StatusBadgeStatus
            }];
      }
      const parked = current.status !== "connected" && current.vlan === policy.accessVlan;
      return parked
        ? []
        : [{
            current: live,
            intended,
            port,
            reason: current.status === "connected"
              ? `Unused port is connected on VLAN ${current.vlan}`
              : `Unused port should be parked in VLAN ${policy.accessVlan}`,
            status: current.status === "connected" ? "blocked" as StatusBadgeStatus : "needs-attention" as StatusBadgeStatus
          }];
    })
  );
}

function intendedCiscoPortSummary(policy: CiscoPortPlan) {
  if (policy.mode === "trunk") {
    return `trunk ${policy.trunkVlans}`;
  }
  if (policy.mode === "disabled") {
    return `shutdown access ${policy.accessVlan}`;
  }
  return `access ${policy.accessVlan}`;
}

function expandCiscoPortRange(port: string) {
  const match = port.match(/^(Gi\d+\/\d+\/)(\d+)-(\d+)$/);
  if (!match) {
    return [port];
  }
  const [, prefix, startRaw, endRaw] = match;
  const start = Number.parseInt(startRaw, 10);
  const end = Number.parseInt(endRaw, 10);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) {
    return [port];
  }
  return Array.from({ length: end - start + 1 }, (_, index) => `${prefix}${start + index}`);
}

function normalizeCiscoPort(port: string) {
  return port.trim().toLowerCase();
}

function gatewayForSiblingVlan(gateway: string, vlan: string) {
  if (!gateway || gateway === "Not set up yet") {
    return "plan after subnet";
  }
  const parts = gateway.split(".");
  if (parts.length !== 4) {
    return "plan after subnet";
  }
  const thirdOctet = Number.parseInt(vlan, 10);
  if (!Number.isFinite(thirdOctet)) {
    return "plan after subnet";
  }
  return `${parts[0]}.${parts[1]}.${thirdOctet}.1`;
}

function NetworkConfigurePanel({
  activeProfile,
  address,
  features,
  global,
  onSaved
}: {
  activeProfile: LabProfile | null;
  address: LabAddressPlan;
  features: LabProfileFeatures | null;
  global: LabProfile["global_settings"] | null;
  onSaved: () => Promise<void>;
}) {
  const [edit, setEdit] = useState<NetworkProfileEditState>(() =>
    networkProfileEditStateFrom(activeProfile, address, features, global)
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const profileKey = `${activeProfile?.id ?? "none"}:${activeProfile?.version ?? 0}`;

  useEffect(() => {
    setEdit(networkProfileEditStateFrom(activeProfile, address, features, global));
    setError("");
    setMessage("");
  }, [profileKey, activeProfile, address, features, global]);

  function update<K extends keyof NetworkProfileEditState>(key: K, value: NetworkProfileEditState[K]) {
    setEdit((current) => ({ ...current, [key]: value }));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!activeProfile) {
      setError("Load the active lab setup before editing network values.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const payload = networkProfilePayload(activeProfile, edit);
      if (activeProfile.source === "saved") {
        await api.updateLabProfile(activeProfile.id, payload);
      } else {
        const saved = await api.createLabProfile(payload);
        await api.activateLabProfile(saved.id);
      }
      await onSaved();
      setMessage("Network config saved.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="network-config-panel" hover={false} id="network-profile">
      <CardHeader>
        <div>
          <p className="operator-kicker">Configure</p>
          <h2>Network lab profile</h2>
        </div>
        <StatusBadge
          label={activeProfile?.source === "saved" ? "Saved profile" : "Save as profile"}
          status={activeProfile ? "ready" : "not-configured"}
        />
      </CardHeader>
      <CardContent>
        <form className="network-config-form" onSubmit={save}>
          <Field label="Cisco mgmt IP">
            <input
              value={edit.ciscoManagement}
              onChange={(event) => update("ciscoManagement", event.target.value)}
              placeholder="192.168.1.204"
            />
          </Field>
          <Field label="Subnet">
            <input
              value={edit.subnet}
              onChange={(event) => update("subnet", event.target.value)}
              placeholder="192.168.1.0/24"
            />
          </Field>
          <Field label="Gateway">
            <input
              value={edit.gateway}
              onChange={(event) => update("gateway", event.target.value)}
              placeholder="192.168.1.1"
            />
          </Field>
          <Field label="VLAN">
            <input
              value={edit.vlanId}
              onChange={(event) => update("vlanId", event.target.value)}
              placeholder="optional"
            />
          </Field>
          <Field label="DNS servers">
            <input
              value={edit.dnsServers}
              onChange={(event) => update("dnsServers", event.target.value)}
              placeholder="comma separated"
            />
          </Field>
          <Field label="NTP servers">
            <input
              value={edit.ntpServers}
              onChange={(event) => update("ntpServers", event.target.value)}
              placeholder="comma separated"
            />
          </Field>
          <Field label="MTU">
            <input
              inputMode="numeric"
              value={edit.mtu}
              onChange={(event) => update("mtu", event.target.value)}
              placeholder="optional"
            />
          </Field>
          <div className="network-config-toggles" aria-label="Network feature toggles">
            <label>
              <input
                checked={edit.enableDns}
                onChange={(event) => update("enableDns", event.target.checked)}
                type="checkbox"
              />
              <span>DNS</span>
            </label>
            <label>
              <input
                checked={edit.enableNtp}
                onChange={(event) => update("enableNtp", event.target.checked)}
                type="checkbox"
              />
              <span>NTP</span>
            </label>
            <label>
              <input
                checked={edit.enableSnmp}
                onChange={(event) => update("enableSnmp", event.target.checked)}
                type="checkbox"
              />
              <span>SNMP</span>
            </label>
          </div>
          {error && <div className="operator-feedback error">{error}</div>}
          {message && <div className="operator-feedback">{message}</div>}
          <div className="network-config-actions">
            <button className="secondary-button" disabled={busy || !activeProfile} type="submit">
              {busy ? "Saving" : activeProfile?.source === "saved" ? "Save Network Config" : "Save As Lab Setup"}
            </button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function settingsProfileEditStateFrom(activeProfile: LabProfile | null): SettingsProfileEditState {
  const features = activeProfile?.features ?? null;
  const global = activeProfile?.global_settings ?? null;
  return {
    blockLegacyProtocols: features?.block_legacy_protocols ?? true,
    description: activeProfile?.description ?? "",
    disableIpv6: features?.disable_ipv6 ?? true,
    domainName: global?.domain_name ?? "",
    enableDns: features?.enable_dns ?? true,
    enableNtp: features?.enable_ntp ?? true,
    enableSnmp: features?.enable_snmp ?? false,
    enableVcenter: features?.vcenter_enabled ?? global?.vcenter_enabled ?? false,
    name: activeProfile?.name ?? "",
    storageProtocol: features?.storage_protocol ?? "nfs",
    timezone: global?.timezone ?? ""
  };
}

function settingsProfilePayload(profile: LabProfile, edit: SettingsProfileEditState): LabProfileWrite {
  const name = edit.name.trim() || (profile.source === "saved" ? profile.name : "Local lab setup");
  const storageProtocol = edit.storageProtocol || profile.features.storage_protocol || "nfs";
  const features: LabProfileFeatures = {
    ...profile.features,
    block_legacy_protocols: edit.blockLegacyProtocols,
    disable_ipv6: edit.disableIpv6,
    enable_dns: edit.enableDns,
    enable_ntp: edit.enableNtp,
    enable_snmp: edit.enableSnmp,
    storage_protocol: storageProtocol,
    vcenter_disabled_reason: edit.enableVcenter ? null : "vCenter is disabled by the active lab setup.",
    vcenter_enabled: edit.enableVcenter
  };
  const globalSettings = {
    ...profile.global_settings,
    domain_name: cleanNetworkNullable(edit.domainName),
    timezone: cleanNetworkNullable(edit.timezone),
    vcenter_enabled: edit.enableVcenter
  };
  return {
    address_plan: profile.address_plan,
    description: cleanNetworkNullable(edit.description),
    devices: profile.devices,
    dns: profile.dns,
    features,
    gateway: profile.gateway,
    global_settings: globalSettings,
    mtu: profile.mtu,
    name,
    ntp: profile.ntp,
    profile_topology: profile.profile_topology,
    subnet_cidr: profile.subnet_cidr,
    vlan_id: profile.vlan_id
  };
}

function networkProfileEditStateFrom(
  activeProfile: LabProfile | null,
  address: LabAddressPlan,
  features: LabProfileFeatures | null,
  global: LabProfile["global_settings"] | null
): NetworkProfileEditState {
  return {
    ciscoManagement: address.cisco_management ?? "",
    dnsServers: (global?.dns_servers ?? activeProfile?.dns ?? []).join(", "),
    enableDns: Boolean(features?.enable_dns),
    enableNtp: Boolean(features?.enable_ntp),
    enableSnmp: Boolean(features?.enable_snmp),
    gateway: global?.gateway ?? activeProfile?.gateway ?? "",
    mtu: global?.mtu !== null && global?.mtu !== undefined ? String(global.mtu) : activeProfile?.mtu ? String(activeProfile.mtu) : "",
    ntpServers: (global?.ntp_servers ?? activeProfile?.ntp ?? []).join(", "),
    subnet: address.subnet ?? activeProfile?.subnet_cidr ?? "",
    vlanId: global?.vlan_id ?? activeProfile?.vlan_id ?? ""
  };
}

function serverProfileEditStateFrom(
  activeProfile: LabProfile | null,
  address: LabAddressPlan,
  global: LabProfile["global_settings"] | null
): ServerProfileEditState {
  return {
    dnsServers: (global?.dns_servers ?? activeProfile?.dns ?? []).join(", "),
    esxiManagement: address.esxi_management ?? "",
    gateway: global?.gateway ?? activeProfile?.gateway ?? "",
    ilo: address.ilo ?? "",
    iloInitial: address.ilo_initial ?? "",
    mtu: global?.mtu !== null && global?.mtu !== undefined ? String(global.mtu) : activeProfile?.mtu ? String(activeProfile.mtu) : "",
    ntpServers: (global?.ntp_servers ?? activeProfile?.ntp ?? []).join(", "),
    serverEmbeddedNic: address.server_embedded_nic ?? "",
    subnet: address.subnet ?? activeProfile?.subnet_cidr ?? ""
  };
}

function storageProfileEditStateFrom(
  activeProfile: LabProfile | null,
  address: LabAddressPlan,
  features: LabProfileFeatures | null,
  global: LabProfile["global_settings"] | null
): StorageProfileEditState {
  const storageProtocol = features?.storage_protocol === "iscsi" ? "iscsi" : "nfs";
  return {
    clusterMgmt: address.netapp_cluster_mgmt ?? "",
    controllerASp: address.netapp_controller_a_sp ?? "",
    controllerBSp: address.netapp_controller_b_sp ?? "",
    gateway: global?.gateway ?? activeProfile?.gateway ?? "",
    iscsiLifs: address.netapp_iscsi_lifs.join(", "),
    mtu: global?.mtu !== null && global?.mtu !== undefined ? String(global.mtu) : activeProfile?.mtu ? String(activeProfile.mtu) : "",
    nfsLifs: address.netapp_nfs_lifs.join(", "),
    nodeAMgmt: address.netapp_node_a_mgmt ?? "",
    nodeBMgmt: address.netapp_node_b_mgmt ?? "",
    storageProtocol,
    subnet: address.subnet ?? activeProfile?.subnet_cidr ?? "",
    svmMgmt: address.netapp_svm_mgmt ?? ""
  };
}

function virtualizationProfileEditStateFrom(
  activeProfile: LabProfile | null,
  address: LabAddressPlan,
  features: LabProfileFeatures | null,
  global: LabProfile["global_settings"] | null
): VirtualizationProfileEditState {
  const devices = activeProfile?.devices ?? {};
  const netapp = devices.netapp && typeof devices.netapp === "object" ? devices.netapp : {};
  return {
    datastoreTarget: asString(netapp.datastore_target) || asString(netapp.datastore) || "",
    dnsServers: (global?.dns_servers ?? activeProfile?.dns ?? []).join(", "),
    enableVcenter: Boolean(features?.vcenter_enabled),
    esxiTarget: asString(devices.esxi) || (address.esxi_management ?? ""),
    gateway: global?.gateway ?? activeProfile?.gateway ?? "",
    ntpServers: (global?.ntp_servers ?? activeProfile?.ntp ?? []).join(", "),
    subnet: address.subnet ?? activeProfile?.subnet_cidr ?? "",
    vcenterTarget: asString(devices.vcenter)
  };
}

function virtualizationProfilePayload(profile: LabProfile, edit: VirtualizationProfileEditState): LabProfileWrite {
  const dnsServers = splitNetworkList(edit.dnsServers);
  const esxiTarget = cleanNetworkNullable(edit.esxiTarget);
  const gateway = cleanNetworkNullable(edit.gateway);
  const ntpServers = splitNetworkList(edit.ntpServers);
  const subnet = cleanNetworkNullable(edit.subnet);
  const subnetPrefix = networkPrefixFromCidr(subnet) ?? profile.global_settings.subnet_prefix ?? 24;
  const vcenterTarget = cleanNetworkNullable(edit.vcenterTarget);
  const addressPlan: LabAddressPlan = {
    ...profile.address_plan,
    esxi_management: esxiTarget,
    subnet
  };
  const netappDevice = profile.devices?.netapp && typeof profile.devices.netapp === "object" ? profile.devices.netapp : {};
  const features = {
    ...profile.features,
    vcenter_disabled_reason: edit.enableVcenter ? null : "vCenter is disabled by the active lab setup.",
    vcenter_enabled: edit.enableVcenter
  };
  const globalSettings = {
    ...profile.global_settings,
    dns_servers: dnsServers,
    gateway,
    ntp_servers: ntpServers,
    subnet_prefix: subnetPrefix,
    vcenter_enabled: edit.enableVcenter
  };
  return {
    address_plan: addressPlan,
    description: profile.description,
    devices: {
      ...(profile.devices ?? {}),
      esxi: esxiTarget,
      netapp: {
        ...netappDevice,
        datastore_target: cleanNetworkNullable(edit.datastoreTarget)
      },
      vcenter: vcenterTarget
    },
    dns: dnsServers,
    features,
    gateway,
    global_settings: globalSettings,
    mtu: profile.mtu,
    name: profile.source === "saved" ? profile.name : "Local lab setup",
    ntp: ntpServers,
    profile_topology: profile.profile_topology,
    subnet_cidr: subnet,
    vlan_id: profile.vlan_id
  };
}

function storageProfilePayload(profile: LabProfile, edit: StorageProfileEditState): LabProfileWrite {
  const gateway = cleanNetworkNullable(edit.gateway);
  const mtu = parseNetworkMtu(edit.mtu);
  const subnet = cleanNetworkNullable(edit.subnet);
  const subnetPrefix = networkPrefixFromCidr(subnet) ?? profile.global_settings.subnet_prefix ?? 24;
  const addressPlan: LabAddressPlan = {
    ...profile.address_plan,
    netapp_cluster_mgmt: cleanNetworkNullable(edit.clusterMgmt),
    netapp_controller_a_sp: cleanNetworkNullable(edit.controllerASp),
    netapp_controller_b_sp: cleanNetworkNullable(edit.controllerBSp),
    netapp_iscsi_lifs: splitNetworkList(edit.iscsiLifs),
    netapp_nfs_lifs: splitNetworkList(edit.nfsLifs),
    netapp_node_a_mgmt: cleanNetworkNullable(edit.nodeAMgmt),
    netapp_node_b_mgmt: cleanNetworkNullable(edit.nodeBMgmt),
    netapp_svm_mgmt: cleanNetworkNullable(edit.svmMgmt),
    subnet
  };
  const globalSettings = {
    ...profile.global_settings,
    gateway,
    mtu,
    subnet_prefix: subnetPrefix
  };
  const features: LabProfileFeatures = {
    ...profile.features,
    storage_protocol: edit.storageProtocol === "iscsi" ? "iscsi" : "nfs"
  };
  return {
    address_plan: addressPlan,
    description: profile.description,
    devices: {
      ...(profile.devices ?? {}),
      netapp: {
        ...((profile.devices?.netapp && typeof profile.devices.netapp === "object") ? profile.devices.netapp : {}),
        cluster_mgmt: addressPlan.netapp_cluster_mgmt,
        controller_a_sp: addressPlan.netapp_controller_a_sp,
        controller_b_sp: addressPlan.netapp_controller_b_sp,
        iscsi_lifs: addressPlan.netapp_iscsi_lifs,
        nfs_lifs: addressPlan.netapp_nfs_lifs,
        node_a_mgmt: addressPlan.netapp_node_a_mgmt,
        node_b_mgmt: addressPlan.netapp_node_b_mgmt,
        svm_mgmt: addressPlan.netapp_svm_mgmt
      }
    },
    dns: profile.dns,
    features,
    gateway,
    global_settings: globalSettings,
    mtu,
    name: profile.source === "saved" ? profile.name : "Local lab setup",
    ntp: profile.ntp,
    profile_topology: profile.profile_topology,
    subnet_cidr: subnet,
    vlan_id: profile.vlan_id
  };
}

function serverProfilePayload(profile: LabProfile, edit: ServerProfileEditState): LabProfileWrite {
  const dnsServers = splitNetworkList(edit.dnsServers);
  const esxiManagement = cleanNetworkNullable(edit.esxiManagement);
  const gateway = cleanNetworkNullable(edit.gateway);
  const ilo = cleanNetworkNullable(edit.ilo);
  const iloInitial = cleanNetworkNullable(edit.iloInitial);
  const mtu = parseNetworkMtu(edit.mtu);
  const ntpServers = splitNetworkList(edit.ntpServers);
  const serverEmbeddedNic = cleanNetworkNullable(edit.serverEmbeddedNic);
  const subnet = cleanNetworkNullable(edit.subnet);
  const subnetPrefix = networkPrefixFromCidr(subnet) ?? profile.global_settings.subnet_prefix ?? 24;
  const addressPlan: LabAddressPlan = {
    ...profile.address_plan,
    esxi_management: esxiManagement,
    ilo,
    ilo_initial: iloInitial,
    server_embedded_nic: serverEmbeddedNic,
    subnet
  };
  const globalSettings = {
    ...profile.global_settings,
    dns_servers: dnsServers,
    gateway,
    mtu,
    ntp_servers: ntpServers,
    subnet_prefix: subnetPrefix
  };
  return {
    address_plan: addressPlan,
    description: profile.description,
    devices: {
      ...(profile.devices ?? {}),
      esxi: esxiManagement,
      ilo
    },
    dns: dnsServers,
    features: profile.features,
    gateway,
    global_settings: globalSettings,
    mtu,
    name: profile.source === "saved" ? profile.name : "Local lab setup",
    ntp: ntpServers,
    profile_topology: profile.profile_topology,
    subnet_cidr: subnet,
    vlan_id: profile.vlan_id
  };
}

function networkProfilePayload(profile: LabProfile, edit: NetworkProfileEditState): LabProfileWrite {
  const ciscoManagement = cleanNetworkNullable(edit.ciscoManagement);
  const gateway = cleanNetworkNullable(edit.gateway);
  const subnet = cleanNetworkNullable(edit.subnet);
  const mtu = parseNetworkMtu(edit.mtu);
  const dnsServers = splitNetworkList(edit.dnsServers);
  const ntpServers = splitNetworkList(edit.ntpServers);
  const vlanId = cleanNetworkNullable(edit.vlanId);
  const subnetPrefix = networkPrefixFromCidr(subnet) ?? profile.global_settings.subnet_prefix ?? 24;
  const addressPlan: LabAddressPlan = {
    ...profile.address_plan,
    cisco_management: ciscoManagement,
    subnet
  };
  const globalSettings = {
    ...profile.global_settings,
    dns_servers: dnsServers,
    gateway,
    mtu,
    ntp_servers: ntpServers,
    subnet_prefix: subnetPrefix,
    vlan_id: vlanId
  };
  const features = {
    ...profile.features,
    enable_dns: edit.enableDns,
    enable_ntp: edit.enableNtp,
    enable_snmp: edit.enableSnmp
  };
  return {
    address_plan: addressPlan,
    description: profile.description,
    devices: {
      ...(profile.devices ?? {}),
      cisco: ciscoManagement,
      gateway,
      switch_primary: ciscoManagement
    },
    dns: dnsServers,
    features,
    gateway,
    global_settings: globalSettings,
    mtu,
    name: profile.source === "saved" ? profile.name : "Local lab setup",
    ntp: ntpServers,
    profile_topology: profile.profile_topology,
    subnet_cidr: subnet,
    vlan_id: vlanId
  };
}

function cleanNetworkNullable(value: string | null | undefined): string | null {
  const trimmed = asString(value).trim();
  return trimmed ? trimmed : null;
}

function splitNetworkList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseNetworkMtu(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    throw new Error("MTU must be a positive number.");
  }
  return parsed;
}

function networkPrefixFromCidr(value: string | null): number | null {
  if (!value?.includes("/")) return null;
  const parsed = Number(value.split("/").pop());
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function LabSafetySettingsSection({
  auditEvents,
  labSafety
}: {
  auditEvents: AuditEvent[];
  labSafety: LabSafetySettings | null;
}) {
  const safetyEvents = auditEvents.filter((event) => event.event_type === "settings.lab_safety.updated").slice(0, 5);
  return (
    <section className="lab-safety-section" aria-label="Lab safety settings">
      <div className="overview-panel-head">
        <div>
          <p className="operator-kicker">Global safety</p>
          <h2>Real lab gate state and audit trail</h2>
        </div>
        <StatusBadge
          label={labSafetyReady(labSafety) ? "Ready" : labSafety ? "Complete gates" : "Unavailable"}
          status={labSafetyReady(labSafety) ? "ready" : "blocked"}
        />
      </div>
      <div className="lab-safety-grid">
        <Card className="network-prereq-panel" hover={false}>
          <CardHeader>
            <div>
              <h3>System-scope gate state</h3>
              <p>{labSafety?.updated_at ? `Updated ${formatDateTime(labSafety.updated_at)}` : "Using boot environment defaults."}</p>
            </div>
          </CardHeader>
          <CardContent>
            <div className="overview-clear-state">
              <StatusBadge
                label={labSafetyReady(labSafety) ? "Ready" : labSafety ? "Gated" : "Unavailable"}
                status={labSafetyReady(labSafety) ? "ready" : "blocked"}
              />
              <span>Change gates only from Lab safety in the map. This audit view reads the same saved gate state.</span>
            </div>
          </CardContent>
        </Card>
        <LabSafetyAuditList events={safetyEvents} />
      </div>
    </section>
  );
}

function LabSafetyControls({
  labSafety,
  onUpdated
}: {
  labSafety: LabSafetySettings | null;
  onUpdated: () => Promise<void>;
}) {
  const [busyFlag, setBusyFlag] = useState("");
  const [error, setError] = useState("");
  const [confirmationPhrases, setConfirmationPhrases] = useState<Record<string, string>>({});
  const flags = labSafety?.flags ?? [];

  async function updateSafety(flagName: string, enabled: boolean) {
    if (!labSafety) return;
    setError("");
    setBusyFlag(flagName);
    const payload: LabSafetySettingsWrite = {};
    switch (flagName) {
      case "lab_environment":
        payload.lab_environment = "isolated-real-lab";
        break;
      case "lab_acknowledge_real_hardware":
        payload.lab_acknowledge_real_hardware = enabled;
        break;
      case "lab_acknowledge_device_reconfiguration":
        payload.lab_acknowledge_device_reconfiguration = enabled;
        break;
      case "lab_acknowledge_data_loss_risk":
        payload.lab_acknowledge_data_loss_risk = enabled;
        break;
      case "lab_acknowledge_lab_only":
        payload.lab_acknowledge_lab_only = enabled;
        break;
      default:
        return;
    }
    if (flagName === "lab_acknowledge_data_loss_risk" && enabled) {
      payload.confirmation_phrase = confirmationPhrases[flagName] ?? "";
    }
    if (flagName === "lab_acknowledge_device_reconfiguration" && enabled) {
      payload.device_reconfiguration_confirmation_phrase = confirmationPhrases[flagName] ?? "";
    }
    try {
      await api.updateLabSafetySettings(payload);
      if (confirmationPhraseForFlag(labSafety, flagName)) {
        setConfirmationPhrases((current) => ({ ...current, [flagName]: "" }));
      }
      await onUpdated();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusyFlag("");
    }
  }

  if (!labSafety) {
    return (
      <div className="lab-safety-unavailable">
        <div className="operator-feedback error">Lab safety settings are unavailable.</div>
        <button className="secondary-button" onClick={() => void onUpdated()} type="button">
          Refresh Gates
        </button>
      </div>
    );
  }

  return (
    <div className="lab-safety-controls">
      {error && <div className="operator-feedback error">{error}</div>}
      {flags.map((flag) => {
        const isEnvironment = flag.name === "lab_environment";
        const requiredPhrase = confirmationPhraseForFlag(labSafety, flag.name);
        const needsPhrase = Boolean(requiredPhrase) && !flag.enabled;
        const typedPhrase = confirmationPhrases[flag.name] ?? "";
        const phraseReady = typedPhrase.trim() === requiredPhrase;
        const canEnable = !needsPhrase || phraseReady;
        return (
          <div className="lab-safety-control" key={flag.name}>
            <div>
              <strong>{flag.label}</strong>
              <span>{flag.description}</span>
              <small>Source: {displayStatus(flag.source)}</small>
            </div>
            <div className="lab-safety-control-actions">
              <StatusBadge label={flag.enabled ? "Enabled" : "Missing"} status={flag.enabled ? "ready" : "blocked"} />
              {isEnvironment ? (
                <button
                  className="secondary-button"
                  disabled={flag.enabled || busyFlag === flag.name}
                  onClick={() => void updateSafety(flag.name, true)}
                  type="button"
                >
                  {flag.enabled ? "Set" : busyFlag === flag.name ? "Setting" : "Set lab"}
                </button>
              ) : flag.enabled ? (
                <button
                  className="secondary-button"
                  disabled={busyFlag === flag.name}
                  onClick={() => void updateSafety(flag.name, false)}
                  type="button"
                >
                  {busyFlag === flag.name ? "Revoking" : "Revoke"}
                </button>
              ) : (
                <button
                  className="secondary-button"
                  disabled={!canEnable || busyFlag === flag.name}
                  onClick={() => void updateSafety(flag.name, true)}
                  type="button"
                >
                  {busyFlag === flag.name ? "Enabling" : "Enable"}
                </button>
              )}
            </div>
            {needsPhrase && (
              <label className="lab-safety-confirm">
                <span>Type {requiredPhrase}</span>
                <input
                  onChange={(event) =>
                    setConfirmationPhrases((current) => ({ ...current, [flag.name]: event.target.value }))
                  }
                  placeholder={requiredPhrase}
                  value={typedPhrase}
                />
              </label>
            )}
          </div>
        );
      })}
    </div>
  );
}

function confirmationPhraseForFlag(labSafety: LabSafetySettings, flagName: string): string {
  if (flagName === "lab_acknowledge_data_loss_risk") {
    return labSafety.confirmation_phrase;
  }
  if (flagName === "lab_acknowledge_device_reconfiguration") {
    return labSafety.device_reconfiguration_confirmation_phrase;
  }
  return "";
}

function LabSafetyAuditList({ events }: { events: AuditEvent[] }) {
  return (
    <Card className="lab-safety-audit" hover={false}>
      <CardHeader>
        <div>
          <h3>Recent safety audit</h3>
          <p>{events.length ? `${events.length} recent gate change${events.length === 1 ? "" : "s"} recorded.` : "No recent gate changes recorded."}</p>
        </div>
      </CardHeader>
      <CardContent>
        <div className="overview-clear-state">
          <StatusBadge status={events.length ? "ready" : "not-configured"} />
          <span>{events.length ? "Open the audit log for actor, timestamp, and changed field details." : "Audit details will appear after safety gates are changed."}</span>
        </div>
      </CardContent>
      <CardFooter>
        <ActionLink to="/audit-events">Open audit log</ActionLink>
      </CardFooter>
    </Card>
  );
}

type RealLabPrerequisite = {
  detail: string;
  id: string;
  label: string;
  status: "ready" | "blocked";
  value: string;
};

function labSafetyReady(labSafety: LabSafetySettings | null): boolean {
  return Boolean(labSafety?.flags.length) && (labSafety?.flags ?? []).every((flag) => !flag.required || flag.enabled);
}

function realLabPrerequisites(
  ciscoReadiness: ProviderProbeResult | null,
  consoleState: Record<string, unknown>,
  currentView: CurrentViewModel,
  labSafety: LabSafetySettings | null
): RealLabPrerequisite[] {
  const blockers = uniqueStrings([...currentView.blockers, ...stringArray(ciscoReadiness?.blockers)]);
  const hasBlocker = (token: string) => blockers.some((message) => message.includes(token));
  const readinessLoaded = Boolean(ciscoReadiness);
  const isMissing = (token: string) => !readinessLoaded || hasBlocker(token);
  const safetyByName = new Map((labSafety?.flags ?? []).map((flag) => [flag.name, flag]));
  const safetyItem = (
    id: string,
    label: string,
    detail: string,
    blockerToken: string,
    enabledValue: string,
    missingValue: string
  ): RealLabPrerequisite => {
    const flag = safetyByName.get(id);
    const missing = flag ? !flag.enabled : isMissing(blockerToken);
    return {
      detail,
      id,
      label: flag?.label ?? label,
      status: missing ? "blocked" : "ready",
      value: missing ? missingValue : enabledValue
    };
  };
  const consoleStatus = asString(consoleState.status);
  const consoleDetected = consoleStatus && !["missing", "missing-console", "not_checked", "unknown"].includes(consoleStatus);
  return [
    {
      detail: "Cisco USB serial path",
      id: "console-adapter",
      label: "Console adapter",
      status: consoleDetected && !hasBlocker("No Cisco serial console adapter") ? "ready" : "blocked",
      value: consoleDetected ? displayStatus(consoleStatus) : "Not detected"
    },
    {
      detail: "Global lab environment",
      id: "lab-environment",
      label: "Isolated real lab",
      status: safetyByName.get("lab_environment")?.enabled ? "ready" : isMissing("LAB_ENVIRONMENT") ? "blocked" : "ready",
      value: safetyByName.get("lab_environment")?.enabled ? "Present" : isMissing("LAB_ENVIRONMENT") ? "Missing" : "Present"
    },
    safetyItem("lab_acknowledge_real_hardware", "Real hardware acknowledgement", "Consent to contact real devices", "LAB_ACKNOWLEDGE_REAL_HARDWARE", "Enabled", "Missing"),
    safetyItem("lab_acknowledge_device_reconfiguration", "Device reconfiguration acknowledgement", "Consent to make lab device changes", "LAB_ACKNOWLEDGE_DEVICE_RECONFIGURATION", "Enabled", "Missing"),
    safetyItem("lab_acknowledge_data_loss_risk", "Data loss risk acknowledgement", "Consent for rebuild and data-loss workflows", "LAB_ACKNOWLEDGE_DATA_LOSS_RISK", "Enabled", "Missing"),
    safetyItem("lab_acknowledge_lab_only", "Lab-only acknowledgement", "Local lab only confirmation", "LAB_ACKNOWLEDGE_LAB_ONLY", "Enabled", "Missing")
  ];
}

function networkSettingsRows({
  ciscoFirmware,
  features,
  global
}: {
  ciscoFirmware: string;
  features: LabProfileFeatures | null;
  global: LabProfile["global_settings"] | null;
}) {
  return [
    { current: displayValue(global?.vlan_id), item: "VLAN", source: "Saved setup", status: global?.vlan_id ? "ready" : "not_checked" },
    { current: listLabel(global?.dns_servers), item: "DNS", source: "Saved setup", status: featureStatus(features, "enable_dns") },
    { current: listLabel(global?.ntp_servers), item: "NTP", source: "Saved setup", status: featureStatus(features, "enable_ntp") },
    { current: enabledLabel(features?.enable_snmp), item: "SNMP", source: "Saved setup", status: featureStatus(features, "enable_snmp") },
    { current: displayValue(global?.mtu), item: "MTU", source: "Saved setup", status: global?.mtu ? "ready" : "not_checked" },
    { current: ciscoFirmware, item: "Cisco Firmware", source: "Firmware files", status: ciscoFirmware === "Not checked" ? "not_checked" : "ready" }
  ];
}

function networkIssues(currentView: CurrentViewModel, ciscoReadiness: ProviderProbeResult | null) {
  const blockers = [...currentView.blockers, ...stringArray(ciscoReadiness?.blockers)];
  const warnings = [...currentView.warnings, ...stringArray(ciscoReadiness?.warnings)];
  const unique = new Set<string>();
  const issues: Array<{ code: string; message: string; severity: "critical" | "warning" }> = [];
  blockers.forEach((message) => {
    const text = humanize(message);
    const key = `critical-${text}`;
    if (text && !unique.has(key)) {
      unique.add(key);
      issues.push({ code: "NETWORK_BLOCKER", message: text, severity: "critical" });
    }
  });
  warnings.forEach((message) => {
    const text = humanize(message);
    const key = `warning-${text}`;
    if (text && !unique.has(key)) {
      unique.add(key);
      issues.push({ code: "NETWORK_WARNING", message: text, severity: "warning" });
    }
  });
  return issues;
}

function operatorReferenceActions(currentView: CurrentViewModel, rows: OperatorObjectRow[]): string[] {
  const actions = [
    ...currentView.fixSteps,
    ...rows.map((row) => row.nextAction)
  ]
    .map((action) => humanize(action))
    .filter((action) => action && action !== "Not set up yet");
  return Array.from(new Set(actions)).slice(0, 3).length
    ? Array.from(new Set(actions)).slice(0, 3)
    : ["Refresh this page, then review the advanced proof if the state still looks wrong."];
}

function operatorReferenceFacts(row: OperatorObjectRow, currentView: CurrentViewModel): ConfigValue[] {
  const facts = row.details.length
    ? row.details.slice(0, 6)
    : [
        { label: "Target", value: row.target },
        { label: "Source", value: row.source || currentView.source },
        { label: "Checked", value: row.checkedAt || currentView.checkedAt }
      ];
  return facts.map((fact) => ({
    ...fact,
    value: fact.value || "Not set up yet"
  }));
}

function operatorReferenceIssueLine(row: OperatorObjectRow, currentView: CurrentViewModel): { label: string; message: string } {
  const rowIsProblem = statusTone(row.status) === "blocked";
  const blocker = row.blockers?.[0] || (rowIsProblem ? currentView.blockers[0] : "");
  if (blocker) {
    return { label: "Blocked by", message: blocker };
  }
  const rowNeedsReview = rowIsProblem || statusTone(row.status) === "warning";
  const warning = row.warnings?.[0] || (rowNeedsReview ? currentView.warnings[0] : "");
  if (warning) {
    return { label: "Watch", message: warning };
  }
  return { label: "State", message: "No active blocker." };
}

function operatorReferenceIssues(currentView: CurrentViewModel, rows: OperatorObjectRow[]) {
  const blockers = [
    ...currentView.blockers,
    ...rows.flatMap((row) => row.blockers ?? [])
  ];
  const warnings = [
    ...currentView.warnings,
    ...rows.flatMap((row) => row.warnings ?? [])
  ];
  const unique = new Set<string>();
  const issues: Array<{ code: string; message: string; severity: "critical" | "warning" }> = [];
  blockers.forEach((message) => {
    const text = humanize(message);
    const key = `critical-${text}`;
    if (text && !unique.has(key)) {
      unique.add(key);
      issues.push({ code: "ACTIVE_BLOCKER", message: text, severity: "critical" });
    }
  });
  warnings.forEach((message) => {
    const text = humanize(message);
    const key = `warning-${text}`;
    if (text && !unique.has(key)) {
      unique.add(key);
      issues.push({ code: "WARNING", message: text, severity: "warning" });
    }
  });
  return issues;
}

function overviewProviderCards({
  accessRows,
  inventoryRows,
  workspaceRows
}: {
  accessRows: AccessRow[];
  inventoryRows: InventoryRow[];
  workspaceRows: OperatorObjectRow[];
}): Array<{
  actionLabel: string;
  blockedBy: string;
  currentState: string;
  gap: string;
  name: string;
  nextAction: string;
  primaryLabel: string;
  role: string;
  secondaryLabel: string;
  setupState: string;
  status: string;
  target: string;
  targetState: string;
  to: string;
  version: string;
}> {
  const byAccessName = new Map(accessRows.map((row) => [row.item.toLowerCase(), row]));
  const byInventoryName = new Map(inventoryRows.map((row) => [row.item.toLowerCase(), row]));
  const byWorkspaceName = new Map(workspaceRows.map((row) => [row.title.toLowerCase(), row]));
  return [
    overviewProviderCard("HPE iLO", "Server management", "/overview#topology-map", "Open workspace", byAccessName, byInventoryName, byWorkspaceName, "hpe ilo", "ilo"),
    overviewProviderCard("Cisco Switch", "Network", "/overview#topology-map", "Open workspace", byAccessName, byInventoryName, byWorkspaceName, "cisco switch", "cisco"),
    overviewProviderCard("NetApp ONTAP", "Storage", "/overview#topology-map", "Open workspace", byAccessName, byInventoryName, byWorkspaceName, "netapp ontap", "netapp")
  ];
}

function overviewProviderCard(
  name: string,
  role: string,
  to: string,
  actionLabel: string,
  accessRows: Map<string, AccessRow>,
  inventoryRows: Map<string, InventoryRow>,
  workspaceRows: Map<string, OperatorObjectRow>,
  inventoryKey = name.toLowerCase(),
  accessKey = name.toLowerCase()
) {
  const access = accessRows.get(accessKey);
  const inventory = inventoryRows.get(inventoryKey);
  const workspace = workspaceRows.get(name.toLowerCase()) ?? workspaceRows.get(accessKey) ?? workspaceRows.get(name.replace(/ switch| ontap/i, "").toLowerCase());
  const detailValue = (label: string) => workspace?.details.find((detail) => detail.label.toLowerCase() === label.toLowerCase())?.value;
  const status = access?.status || inventory?.status || workspace?.status || "not_checked";
  const target = access?.target || inventory?.accessTarget || workspace?.target || "Not set up yet";
  const version = inventory?.version || "Not checked";
  const setupState = access?.appSees || workspace?.source || "Not verified";
  const currentState = `${displayStatus(status)}${version && version !== "Not checked" ? `, ${version}` : ""}`;
  const targetState = detailValue("Target") || target;
  const gap = access?.needs || workspace?.nextAction || "Review current state";
  return {
    actionLabel,
    blockedBy: gap === "Nothing right now" ? "No blocker loaded" : gap,
    currentState,
    gap,
    name,
    nextAction: access?.needs || workspace?.nextAction || "Review current state",
    primaryLabel: name.includes("Cisco") ? "Console" : name.includes("NetApp") ? "Cluster Mgmt" : "Host",
    role,
    secondaryLabel: name.includes("Cisco") ? "Mgmt IP" : name.includes("NetApp") ? "ONTAP Version" : "iLO Version",
    setupState,
    status,
    target,
    targetState,
    to,
    version
  };
}

function overviewFirmwareRows(firmwareSummaries: FirmwareSummary[], inventoryRows: InventoryRow[]): OverviewFirmwareRow[] {
  const firmwareByKey = new Map(
    firmwareSummaries.flatMap((summary) =>
      [summary.device_id, summary.label, summary.component_type]
        .map((value) => asString(value).toLowerCase())
        .filter(Boolean)
        .map((key) => [key, summary] as const)
    )
  );
  return inventoryRows.map((row) => {
    const key = row.item.toLowerCase();
    const summary = firmwareByKey.get(key) || firmwareByKey.get(row.role.toLowerCase()) || firmwareSummaries.find((candidate) => row.item.toLowerCase().includes(candidate.component_type.toLowerCase()));
    const status = asString(summary?.compliance_status) || asString(summary?.path_status) || row.status || "not_checked";
    return {
      action: statusTone(status) === "ready" ? "Review" : "Plan",
      device: row.item,
      status,
      target: summary?.target_version || "Not set up yet",
      version: row.version
    };
  });
}

function overviewSafeActions(
  currentView: CurrentViewModel,
  providerCards: Array<{ blockedBy: string; name: string; to: string }>
): string[] {
  return uniqueStrings([
    ...providerCards.map((provider) => provider.blockedBy).filter((text) => text && text !== "No blocker loaded"),
    currentView.fixSteps[0],
    currentView.summary
  ])
    .slice(0, 3)
    .map((text) => humanize(text));
}

function overviewIssues(currentView: CurrentViewModel): Array<{ code: string; message: string; severity: "critical" | "warning" }> {
  const blockers = uniqueStrings(currentView.blockers.map((message) => humanize(message)).filter(Boolean));
  const warnings = uniqueStrings(currentView.warnings.map((message) => humanize(message)).filter(Boolean))
    .filter((message) => !blockers.includes(message));
  return [
    ...blockers.map((message, index) => ({
      code: `BLOCKER_${index + 1}`,
      message,
      severity: "critical" as const
    })),
    ...warnings.map((message, index) => ({
      code: `WARNING_${index + 1}`,
      message,
      severity: "warning" as const
    }))
  ];
}

function firstMeaningfulText(values: Array<string | null | undefined>): string {
  return values.map((value) => (value ?? "").trim()).find(Boolean) ?? "Review current state.";
}

function SummaryMetric({ label, status, value }: { label: string; status?: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
      {status && <SimpleStatusPill status={status} />}
    </div>
  );
}

function IssueList({ blockers, warnings }: { blockers: string[]; warnings: string[] }) {
  const issues = [
    ...blockers.map((text) => ({ status: "blocked", text })),
    ...warnings.map((text) => ({ status: "warning", text }))
  ].filter((issue) => issue.text);
  if (!issues.length) {
    return null;
  }
  return (
    <div className="operator-issue-list">
      <strong>Needs attention</strong>
      {issues.map((issue) => (
        <BlockerItem
          code={issue.status}
          key={`${issue.status}-${issue.text}`}
          message={humanize(issue.text)}
          severity={issue.status === "blocked" ? "critical" : "warning"}
        />
      ))}
    </div>
  );
}

function workspaceCounts(rows: OperatorObjectRow[]): { blocked: number; neutral: number; ready: number; warning: number } {
  return rows.reduce(
    (counts, row) => {
      const tone = statusTone(row.status);
      if (tone === "ready") counts.ready += 1;
      else if (tone === "warning") counts.warning += 1;
      else if (tone === "blocked") counts.blocked += 1;
      else counts.neutral += 1;
      return counts;
    },
    { blocked: 0, neutral: 0, ready: 0, warning: 0 }
  );
}

function Field({ children, label }: { children: ReactNode; label: string }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

function ConfigValueList({ values }: { values: ConfigValue[] }) {
  return (
    <dl className="config-value-list">
      {values.map((value, index) => (
        <div key={`${value.label}-${value.value}-${index}`}>
          <dt>{value.label}</dt>
          <dd>
            <strong>{value.value}</strong>
            {value.source && <span>{value.source}</span>}
          </dd>
          {value.status && <SimpleStatusPill status={value.status} />}
        </div>
      ))}
    </dl>
  );
}

function AdditionalTabActions({
  actions,
  buttons,
  defaultOpen = false,
  description,
  onReload,
  title
}: {
  actions: WorkflowAction[];
  buttons: RunButtonDefinition[];
  defaultOpen?: boolean;
  description: string;
  onReload: () => Promise<void> | void;
  title: string;
}) {
  const [runState, setRunState] = useState<WorkflowRunState>(emptyRunState);
  const [diagnosis, setDiagnosis] = useState<WorkflowActionDiagnosis | null>(null);
  const [diagnosisLoading, setDiagnosisLoading] = useState(false);
  const [recoveredActions, setRecoveredActions] = useState<WorkflowAction[]>([]);
  const effectiveActions = actions.length ? actions : recoveredActions;
  const byId = useMemo(() => new Map(effectiveActions.map((action) => [action.action_id, action])), [effectiveActions]);
  const actionRegistryLoading = effectiveActions.length === 0;

  useEffect(() => {
    if (actions.length || recoveredActions.length) return;
    let ignore = false;
    void api.workflowActions()
      .then((nextActions) => {
        if (!ignore) {
          setRecoveredActions(Array.isArray(nextActions) ? nextActions : []);
        }
      })
      .catch(() => {
        if (!ignore) {
          setRecoveredActions([]);
        }
      });
    return () => {
      ignore = true;
    };
  }, [actions.length, recoveredActions.length]);

  async function runAction(action: WorkflowAction, request?: WorkflowActionRunRequest) {
    setRunState({ error: "", message: "", runningActionId: action.action_id });
    setDiagnosis(null);
    try {
      const result = await api.runWorkflowAction(action.action_id, request);
      setRunState({
        error: "",
        message: workflowRunMessage(action, result),
        runningActionId: ""
      });
      if (isProblemRun(result)) {
        await loadWorkflowDiagnosis(action.action_id);
      }
      await onReload();
    } catch (err) {
      setRunState({ error: errorMessage(err), message: "", runningActionId: "" });
    }
  }

  async function runActionById(actionId: string, label: string) {
    setRunState({ error: "", message: "", runningActionId: actionId });
    setDiagnosis(null);
    try {
      const result = await api.runWorkflowAction(actionId);
      setRunState({
        error: "",
        message: workflowRunResultMessage(label, result),
        runningActionId: ""
      });
      if (isProblemRun(result)) {
        await loadWorkflowDiagnosis(actionId);
      }
      await onReload();
    } catch (err) {
      setRunState({ error: errorMessage(err), message: "", runningActionId: "" });
    }
  }

  async function runCustomAction(label: string, onClick: () => Promise<void> | void) {
    setRunState({ error: "", message: "", runningActionId: label });
    setDiagnosis(null);
    try {
      await onClick();
      setRunState({ error: "", message: `${label} completed.`, runningActionId: "" });
      void onReload();
    } catch (err) {
      setRunState({ error: errorMessage(err), message: "", runningActionId: "" });
    }
  }

  async function loadWorkflowDiagnosis(actionId: string) {
    setDiagnosisLoading(true);
    try {
      setDiagnosis(await api.workflowActionDiagnosis(actionId));
    } catch {
      setDiagnosis(null);
    } finally {
      setDiagnosisLoading(false);
    }
  }

  return (
    <details className="operator-section additional-actions" aria-label={title} open={defaultOpen}>
      <summary>
        <span>
          <span className="operator-kicker">Additional actions</span>
          <strong>{title}</strong>
          <small>{description}</small>
        </span>
      </summary>
      <div className="page-run-buttons">
        {buttons.map((button) => {
          if (button.to) {
            return (
              <Link className={button.primary ? "button-link primary" : "button-link"} key={button.label} to={button.to}>
                {button.icon ?? <Play size={16} />}
                {button.label}
              </Link>
            );
          }
          const action = firstAction(byId, button.actionIds ?? []);
          const fallbackActionId = !action && button.kind === "read" ? button.actionIds?.[0] ?? "" : "";
          const guardedFallbackReason = !action && (button.kind === "write" || button.kind === "apply")
            ? "Needs guarded confirmation before changes are allowed."
            : "";
          const reason = button.disabledReason || guardedFallbackReason || (button.onClick || fallbackActionId ? "" : actionRegistryLoading ? "Loading action registry..." : disabledReasonFor(button, action));
          const enabled = !reason && (Boolean(button.onClick) || Boolean(action) || Boolean(fallbackActionId));
          const running = action
            ? runState.runningActionId === action.action_id
            : fallbackActionId
              ? runState.runningActionId === fallbackActionId
              : runState.runningActionId === button.label;
          const safetyNote = action?.safety_notes[0] ?? "";
          return (
            <div className="run-button-wrap" key={button.label}>
              <button
                className={button.primary ? "primary" : ""}
                disabled={!enabled || running}
                onClick={() => {
                  if (button.onClick) {
                    void runCustomAction(button.label, button.onClick);
                    return;
                  }
                  if (action) {
                    void runAction(action);
                  } else if (fallbackActionId) {
                    void runActionById(fallbackActionId, button.label);
                  }
                }}
                title={reason || button.label}
                type="button"
              >
                {button.icon ?? (reason ? <Ban size={16} /> : <Play size={16} />)}
                {running ? "Running" : button.label}
              </button>
              {reason && <span>{reason}</span>}
              {!reason && safetyNote && <span className="run-button-safety-note">{humanize(safetyNote)}</span>}
            </div>
          );
        })}
      </div>
      {(runState.message || runState.error) && (
        <p className={runState.error ? "operator-action-message error" : "operator-action-message"}>
          {runState.error || runState.message}
        </p>
      )}
      {diagnosisLoading && <p className="operator-action-message">Preparing advisory diagnosis...</p>}
      {diagnosis && <WorkflowDiagnosisCard diagnosis={diagnosis} />}
    </details>
  );
}

function WorkflowDiagnosisCard({ diagnosis }: { diagnosis: WorkflowActionDiagnosis }) {
  return (
    <section className="workflow-diagnosis-card" aria-label="Advisory diagnosis">
      <div className="workflow-diagnosis-head">
        <div>
          <p className="operator-kicker">Advisory diagnosis</p>
          <h3>{diagnosis.probable_cause}</h3>
        </div>
        <StatusBadge label={`${diagnosis.confidence} confidence`} status={diagnosis.confidence === "high" ? "needs-attention" : "plan-only"} />
      </div>
      <p>{diagnosis.explanation}</p>
      <dl>
        <div>
          <dt>Source</dt>
          <dd>{diagnosis.ai_enabled ? "AI assisted" : "Local rules"}</dd>
        </div>
        <div>
          <dt>Safe next action</dt>
          <dd>{diagnosis.suggested_next_action}</dd>
        </div>
      </dl>
      {diagnosis.evidence.length > 0 && (
        <div className="workflow-diagnosis-evidence" aria-label="Diagnosis evidence">
          {diagnosis.evidence.slice(0, 4).map((item, index) => (
            <div key={`${item.label}-${index}`}>
              <strong>{item.label}</strong>
              <span>{item.detail}</span>
            </div>
          ))}
        </div>
      )}
      {diagnosis.recent_runs.length > 0 && (
        <div className="workflow-diagnosis-runs" aria-label="Recent run context">
          {diagnosis.recent_runs.slice(0, 3).map((run) => (
            <span key={run.run_id}>{run.status} - {run.blocker_count} blockers - {run.warning_count} warnings</span>
          ))}
        </div>
      )}
      <small>{diagnosis.safety_notes[0] || "Diagnosis is advisory and does not execute workflow actions."}</small>
    </section>
  );
}

function InventoryTable({ rows }: { rows: InventoryRow[] }) {
  return (
    <Card aria-label="Hardware and software inventory" className="operator-section" hover={false}>
      <div className="operator-section-head">
        <div>
          <p className="operator-kicker">Inventory</p>
          <h2>Hardware and software</h2>
        </div>
        <span>{rows.length} items</span>
      </div>
      <CompactTable className="inventory-table">
        <CompactTableHeader>
          <CompactTableCell>Item</CompactTableCell>
          <CompactTableCell>Role</CompactTableCell>
          <CompactTableCell>Access target</CompactTableCell>
          <CompactTableCell>Version</CompactTableCell>
          <CompactTableCell>Status</CompactTableCell>
          <CompactTableCell>Source</CompactTableCell>
        </CompactTableHeader>
        <tbody>
          {rows.map((row) => (
            <CompactTableRow key={row.item}>
              <CompactTableCell><strong>{row.item}</strong></CompactTableCell>
              <CompactTableCell>{row.role}</CompactTableCell>
              <CompactTableCell>{row.accessTarget}</CompactTableCell>
              <CompactTableCell>{row.version}</CompactTableCell>
              <CompactTableCell><SimpleStatusPill status={row.status} /></CompactTableCell>
              <CompactTableCell>{row.source}</CompactTableCell>
            </CompactTableRow>
          ))}
        </tbody>
      </CompactTable>
    </Card>
  );
}

type FirmwareTableRow = {
  action: string;
  applyEnabled: boolean;
  candidateFiles: FirmwareFileCandidate[];
  component: string;
  componentId: string;
  current: string;
  disabledReason: string;
  equipment: string;
  evidenceArtifacts: string[];
  estimatedImpact: string;
  missingEvidence: string[];
  pathStatus: string;
  prechecksRequired: string[];
  rebootRequired: boolean;
  selectedFileName: string;
  selectionSource: string;
  target: string;
};

function isUnknownFirmwareValue(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  return !normalized || ["unknown", "not checked", "not probed", "not set up yet", "review required", "none"].includes(normalized);
}

function ValidationProofList({
  items,
  proofLinks
}: {
  items: LabValidationItem[];
  proofLinks: number;
}) {
  return (
    <section className="operator-section" aria-label="Validation proof">
      <div className="operator-section-head">
        <div>
          <p className="operator-kicker">Proof</p>
          <h2>Validation summary</h2>
        </div>
        <span>{proofLinks} proof links</span>
      </div>
      {items.length ? (
        <div className="validation-proof-list">
          {items.map((item) => (
            <article key={item.id}>
              <div>
                <strong>{item.label}</strong>
                <span>{item.setup_summary || item.current_state}</span>
              </div>
              <SimpleStatusPill status={item.status} />
            </article>
          ))}
        </div>
      ) : (
        <p className="operator-muted">No validation rows are loaded yet.</p>
      )}
    </section>
  );
}

function AdvancedDrawer({
  children,
  summary,
  title
}: {
  children: ReactNode;
  summary: string;
  title: string;
}) {
  return (
    <details className="advanced-drawer">
      <summary>
        <Wrench size={16} />
        <span>{title}</span>
        <small>{summary}</small>
      </summary>
      <div>{children}</div>
    </details>
  );
}

function SimpleStatusPill({ status }: { status: string }) {
  return <StatusBadge className="simple-status-pill" label={displayStatus(status)} status={statusBadgeStatus(status)} />;
}

function statusBadgeStatus(status: string): StatusBadgeStatus {
  const normalized = status.toLowerCase();
  if (["ready", "success", "completed", "current", "configured", "enabled", "valid", "safe_to_run", "ready_to_upgrade"].includes(normalized)) {
    return normalized === "safe_to_run" ? "safe-to-run" : "ready";
  }
  if (["blocked", "failed", "error", "critical", "not_accessible"].includes(normalized)) {
    return "blocked";
  }
  if (["warning", "warn", "needs_review", "needs_attention", "outdated", "partial", "pending"].includes(normalized)) {
    return "needs-attention";
  }
  if (["offline", "unreachable"].includes(normalized)) {
    return "offline";
  }
  if (["plan_only", "planned"].includes(normalized)) {
    return "plan-only";
  }
  return "not-configured";
}

function statusIsReady(status: string): boolean {
  return statusBadgeStatus(status) === "ready";
}

function Feedback({ error, loading }: { error?: string; loading?: boolean }) {
  if (loading) {
    return <div className="operator-feedback">Loading</div>;
  }
  if (error) {
    return <div className="operator-feedback error">{error}</div>;
  }
  return null;
}

async function safeApi<T>(loader: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await loader();
  } catch {
    return fallback;
  }
}

function activeLabProfile(state: LabProfileList | null): LabProfile | null {
  return state?.active_profile ?? state?.runtime_profile ?? null;
}

function activeAddressPlan(profile: LabProfile | null): LabAddressPlan {
  return profile?.resolved_address_plan ?? profile?.address_plan ?? {
    ansible_control_host: null,
    cisco_management: null,
    esxi_management: null,
    ilo: null,
    ilo_initial: null,
    netapp_cluster_mgmt: null,
    netapp_controller_a_sp: null,
    netapp_controller_b_sp: null,
    netapp_iscsi_lifs: [],
    netapp_nfs_lifs: [],
    netapp_node_a_mgmt: null,
    netapp_node_b_mgmt: null,
    netapp_svm_mgmt: null,
    server_embedded_nic: null,
    subnet: null
  };
}

function buildInventoryRows({
  address,
  firmwareSummaries,
  providers,
  validation,
  vcenterNetapp
}: {
  address: LabAddressPlan;
  firmwareSummaries: FirmwareSummary[];
  providers: ProviderStatus[];
  validation: LabValidationSummary | null;
  vcenterNetapp: ProviderProbeResult | null;
}): InventoryRow[] {
  const itemStatus = (tokens: string[], fallback = "not_checked") =>
    validationStatus(validation, tokens) || providerStatus(providers, tokens) || fallback;
  return [
    {
      accessTarget: displayAddress(address.cisco_management),
      item: "Cisco switch",
      role: "Network",
      source: sourceFromValidation(validation, ["cisco"]),
      status: itemStatus(["cisco"]),
      version: firmwareVersion(firmwareSummaries, "cisco")
    },
    {
      accessTarget: address.ilo ? `https://${address.ilo}` : "Not set up yet",
      item: "HPE iLO",
      role: "Server management",
      source: sourceFromValidation(validation, ["ilo", "hpe"]),
      status: itemStatus(["ilo", "hpe"]),
      version: firmwareVersion(firmwareSummaries, "ilo")
    },
    {
      accessTarget: displayAddress(address.esxi_management),
      item: "ESXi host",
      role: "Virtualization",
      source: sourceFromValidation(validation, ["esxi"]),
      status: itemStatus(["esxi"]),
      version: firmwareVersion(firmwareSummaries, "esxi")
    },
    {
      accessTarget: displayAddress(address.netapp_cluster_mgmt),
      item: "NetApp ONTAP",
      role: "Storage",
      source: sourceFromValidation(validation, ["netapp", "ontap"]),
      status: itemStatus(["netapp", "storage"], asString(vcenterNetapp?.status) || "not_checked"),
      version: firmwareVersion(firmwareSummaries, "netapp")
    },
    {
      accessTarget: vcenterTarget(vcenterNetapp, null),
      item: "vCenter",
      role: "Virtualization control",
      source: sourceLabel(vcenterNetapp),
      status: asString(vcenterNetapp?.status) || validationStatus(validation, ["vcenter"]) || "not_checked",
      version: vcenterVersion(vcenterNetapp)
    }
  ];
}

function overviewLabValues({
  address,
  ciscoReadiness,
  features,
  global,
  netappConsole,
  profile,
  vcenterNetapp
}: {
  address: LabAddressPlan;
  ciscoReadiness: ProviderProbeResult | null;
  features: LabProfileFeatures | null;
  global: LabProfile["global_settings"] | null;
  netappConsole: ProviderProbeResult | null;
  profile: LabProfile | null;
  vcenterNetapp: ProviderProbeResult | null;
}): ConfigValue[] {
  return [
    { label: "Lab name", value: profile?.name ?? "No active setup", source: "Active setup" },
    {
      label: "Deployment scenario",
      source: "Saved setup",
      status: features?.deployment_supported === false ? "warning" : "ready",
      value: deploymentScenarioLabel(features)
    },
    {
      label: "Storage location",
      source: "Saved setup",
      value: storageLocationLabel(features)
    },
    { label: "Subnet", value: displayAddress(address.subnet), source: "Saved setup" },
    { label: "Topology", value: labelize(profile?.profile_topology ?? "not set up yet"), source: "Saved setup" },
    { label: "Gateway", value: displayAddress(global?.gateway ?? profile?.gateway), source: "Saved setup" },
    { label: "DNS", value: listLabel(global?.dns_servers ?? profile?.dns), source: "Saved setup" },
    { label: "NTP", value: listLabel(global?.ntp_servers ?? profile?.ntp), source: "Saved setup" },
    { label: "VLAN", value: displayValue(global?.vlan_id ?? profile?.vlan_id), source: "Saved setup" },
    { label: "MTU", value: displayValue(global?.mtu ?? profile?.mtu), source: "Saved setup" },
    { label: "Cisco IP", value: displayAddress(address.cisco_management), source: "Saved setup" },
    { label: "iLO IP", value: displayAddress(address.ilo), source: "Saved setup" },
    { label: "ESXi IP", value: displayAddress(address.esxi_management), source: "Saved setup" },
    { label: "NetApp cluster IP", value: displayAddress(address.netapp_cluster_mgmt), source: "Saved setup" },
    { label: "NetApp NFS LIF", value: listLabel(address.netapp_nfs_lifs), source: "Saved setup" },
    { label: "vCenter IP", value: vcenterAddress(vcenterNetapp, profile), source: "Saved or discovered" },
    { label: "Datastore name", value: datastoreName(vcenterNetapp), source: "Saved or discovered" },
    { label: "Cisco console", value: consolePathFromCisco(ciscoReadiness), source: "Discovered when available" },
    { label: "NetApp console", value: consolePathFromNetapp(netappConsole), source: "Discovered when available" },
    { label: "Feature toggles", value: featureToggleSummary(features), source: "Saved setup" }
  ];
}

function overviewAccessRows({
  address,
  ciscoReadiness,
  providers,
  validation,
  vcenterNetapp
}: {
  address: LabAddressPlan;
  ciscoReadiness: ProviderProbeResult | null;
  providers: ProviderStatus[];
  validation: LabValidationSummary | null;
  vcenterNetapp: ProviderProbeResult | null;
}): AccessRow[] {
  const statusFor = (tokens: string[], fallback = "not_checked") =>
    validationStatus(validation, tokens) || providerStatus(providers, tokens) || fallback;
  const checks = objectValue(vcenterNetapp?.checks);
  const vmInventory = objectValue(checks.vm_inventory_visible);
  const vmCount = asString(vmInventory.count);
  return [
    accessRow({
      appSees: sourceLabelFromStatus(statusFor(["cisco"])),
      item: "Cisco",
      need: consolePathFromCisco(ciscoReadiness) === "Not set up yet" ? "Need console connection" : "Need credentials",
      status: statusFor(["cisco"]),
      target: displayAddress(address.cisco_management)
    }),
    accessRow({
      appSees: sourceLabelFromStatus(statusFor(["ilo", "hpe"])),
      item: "iLO",
      need: "Need credentials",
      status: statusFor(["ilo", "hpe"]),
      target: address.ilo ? `https://${address.ilo}` : "Not set up yet"
    }),
    accessRow({
      appSees: sourceLabelFromStatus(statusFor(["esxi"])),
      item: "ESXi",
      need: "Need credentials",
      status: statusFor(["esxi"]),
      target: displayAddress(address.esxi_management)
    }),
    accessRow({
      appSees: sourceLabelFromStatus(statusFor(["netapp", "storage"], asString(vcenterNetapp?.status) || "not_checked")),
      item: "NetApp",
      need: "Need NetApp API reachable",
      status: statusFor(["netapp", "storage"], asString(vcenterNetapp?.status) || "not_checked"),
      target: displayAddress(address.netapp_cluster_mgmt)
    }),
    accessRow({
      appSees: sourceLabel(vcenterNetapp),
      item: "vCenter",
      need: "Need vCenter attached",
      status: asString(vcenterNetapp?.status) || validationStatus(validation, ["vcenter"]) || "not_checked",
      target: vcenterTarget(vcenterNetapp, null)
    }),
    accessRow({
      appSees: datastoreVisibleStatus(vcenterNetapp) === "ready" ? "Datastore visible" : "Not visible yet",
      item: "Datastore",
      need: "Need vCenter attached",
      status: datastoreVisibleStatus(vcenterNetapp),
      target: datastoreName(vcenterNetapp)
    }),
    accessRow({
      appSees: asBoolean(vmInventory.visible) ? `${vmCount || "Some"} VMs visible` : "VM inventory not visible yet",
      item: "VM inventory",
      need: "Need vCenter attached",
      status: asBoolean(vmInventory.visible) ? "ready" : "not_checked",
      target: "vCenter inventory"
    })
  ];
}

function accessRow({
  appSees,
  item,
  need,
  status,
  target
}: {
  appSees: string;
  item: string;
  need: string;
  status: string;
  target: string;
}): AccessRow {
  if (!target || target === "Not set up yet") {
    return { appSees: "No value set", item, needs: "Need IP value", status: "not_setup", target: "Not set up yet" };
  }
  if (["ready", "ok", "passed", "completed", "current"].includes(status)) {
    return { appSees, item, needs: "Nothing right now", status: "accessible", target };
  }
  if (need === "Need console connection") {
    return { appSees: "No console connection selected", item, needs: need, status: "needs_console", target };
  }
  if (need === "Need credentials") {
    return { appSees, item, needs: need, status: "needs_credentials", target };
  }
  return { appSees, item, needs: need, status: "not_accessible", target };
}

function vcenterVersion(vcenterNetapp: ProviderProbeResult | null): string {
  const current = objectValue(vcenterNetapp?.current_state);
  const postAttach = objectValue(vcenterNetapp?.post_attach_validation);
  return displayValue(asString(current.vcenter_version) || asString(postAttach.vcenter_version));
}

function validationStatus(validation: LabValidationSummary | null, tokens: string[]): string {
  const item = validation?.validation_items.find((candidate) => textIncludes(candidateText(candidate), tokens));
  return item?.status ?? "";
}

function sourceFromValidation(validation: LabValidationSummary | null, tokens: string[]): string {
  const item = validation?.validation_items.find((candidate) => textIncludes(candidateText(candidate), tokens));
  return sourceLabel(item ?? validation);
}

function candidateText(item: LabValidationItem): string {
  return `${item.id} ${item.label} ${item.category} ${item.stage}`.toLowerCase();
}

function providerStatus(providers: ProviderStatus[], tokens: string[]): string {
  const provider = providers.find((candidate) =>
    textIncludes(`${candidate.id} ${candidate.name} ${candidate.kind}`.toLowerCase(), tokens)
  );
  return provider?.status ?? "";
}

function textIncludes(text: string, tokens: string[]): boolean {
  return tokens.some((token) => text.includes(token.toLowerCase()));
}

function firstAction(byId: Map<string, WorkflowAction>, ids: string[]): WorkflowAction | null {
  for (const id of ids) {
    const action = byId.get(id);
    if (action) return action;
  }
  return null;
}

function firstRunnableAction(byId: Map<string, WorkflowAction>, ids: string[], config: TabRunConfig): WorkflowAction | null {
  const candidates = ids.map((id) => byId.get(id)).filter((action): action is WorkflowAction => Boolean(action));
  return candidates.find((action) => !disabledReasonForRunConfig(config, action)) ?? candidates[0] ?? null;
}

function deploymentScenarioLabel(features: LabProfileFeatures | null): string {
  const label = asString(features?.deployment_label);
  if (label) return label;
  if (features?.netapp_enabled && features?.vcenter_enabled) return "Server + NetApp + vCenter";
  if (!features?.netapp_enabled && !features?.vcenter_enabled) return "Single server + local ESXi storage";
  if (features?.netapp_enabled) return "Server + NetApp direct attach";
  return "vCenter without NetApp shared storage";
}

function storageLocationLabel(features: LabProfileFeatures | null): string {
  const location = asString(features?.storage_location);
  if (location === "netapp_shared") return "NetApp shared storage";
  if (location === "server_local") return "Server local datastore";
  return features?.netapp_enabled ? "NetApp shared storage" : "Server local datastore";
}

function fallbackRunActionId(config: TabRunConfig, action: WorkflowAction | null): string {
  if (action || config.kind === "write" || config.kind === "apply" || config.onRun) {
    return "";
  }
  return config.actionIds?.[0] ?? "";
}

function disabledReasonFor(button: RunButtonDefinition, action: WorkflowAction | null): string {
  if (button.kind === "custom" && !button.onClick) {
    return button.disabledReason || "This action is not ready yet.";
  }
  if (!action) {
    if (button.kind === "write" || button.kind === "apply") {
      return "Protected action requires guarded workflow registration before changes are allowed.";
    }
    return "Action is not registered yet.";
  }
  if (button.allowBlockedRun) {
    return "";
  }
  if (isChangingAction(action) || button.kind === "write" || button.kind === "apply") {
    return "Needs guarded confirmation before changes are allowed.";
  }
  const blocker = action.ui_run_blockers[0] || action.blockers[0];
  if (blocker) return humanize(blocker);
  if (!action.ui_run_supported) {
    return humanize(action.next_action || "This action is not available from the page yet.");
  }
  if (["blocked", "not_in_scope", "manual_command_required", "missing_config"].includes(action.current_availability)) {
    return humanize(action.next_action || action.current_availability);
  }
  return "";
}

function disabledReasonForRunConfig(config: TabRunConfig, action: WorkflowAction | null): string {
  if (config.kind === "custom" && !config.onRun) {
    return config.disabledReason || "This action is not ready yet.";
  }
  if (!action) {
    return config.onRun ? "" : "Action is not registered yet.";
  }
  if (config.allowBlockedRun) {
    return "";
  }
  if (isChangingAction(action) || config.kind === "write" || config.kind === "apply") {
    return "Needs guarded confirmation before changes are allowed.";
  }
  const blocker = action.ui_run_blockers[0] || action.blockers[0];
  if (blocker) return humanize(blocker);
  if (!action.ui_run_supported) {
    return humanize(action.next_action || "This action is not available from the page yet.");
  }
  if (["blocked", "not_in_scope", "manual_command_required", "missing_config"].includes(action.current_availability)) {
    return humanize(action.next_action || action.current_availability);
  }
  return "";
}

function isChangingAction(action: WorkflowAction): boolean {
  return ["write", "destructive", "upgrade"].includes(action.mode);
}

function humanWorkflowActionLabel(action: WorkflowAction): string {
  return humanize(action.label || action.action_id);
}

function workflowRunMessage(action: WorkflowAction, result: WorkflowActionRun): string {
  const detail = isProblemRun(result)
    ? result.blockers[0] || result.stderr_summary || result.next_action || result.summary || displayStatus(result.status)
    : result.warnings[0] || result.summary || result.next_action || displayStatus(result.status);
  return `${humanWorkflowActionLabel(action)}: ${humanize(detail)}`;
}

function workflowRunResultMessage(label: string, result: WorkflowActionRun): string {
  const detail = isProblemRun(result)
    ? result.blockers[0] || result.stderr_summary || result.next_action || result.summary || displayStatus(result.status)
    : result.warnings[0] || result.summary || result.next_action || displayStatus(result.status);
  return `${label}: ${humanize(detail)}`;
}

function isProblemRun(result: WorkflowActionRun): boolean {
  return ["blocked", "error", "failed"].includes(result.status.toLowerCase());
}

function firmwareRows(
  summaries: FirmwareSummary[],
  compliance: ProviderProbeResult | null,
  selectedFiles: Record<string, string>
): FirmwareTableRow[] {
  const paths = firmwareUpgradePaths(summaries, compliance);
  const byComponent = new Map<string, { path: FirmwareUpgradePath; summary: FirmwareSummary | null }>();
  for (const { path, summary } of paths) {
    if (!byComponent.has(path.component_id)) {
      byComponent.set(path.component_id, { path, summary });
    }
  }
  const orderedIds = [
    "cisco_ios_xe_version",
    "hpe_ilo_firmware",
    "hpe_bios_version",
    "hpe_smart_array_firmware",
    "esxi_version",
    "netapp_ontap_version",
    "vcenter_vcsa_version",
    "netapp_disk_firmware",
    "netapp_shelf_firmware",
    "netapp_sp_bmc_firmware"
  ];
  return orderedIds.flatMap((componentId) => {
    const entry = byComponent.get(componentId);
    if (!entry) return [];
    if (isOptionalUndetectedFirmwareComponent(componentId, entry.path)) return [];
    const { path, summary } = entry;
    const candidateFiles = path.candidate_files ?? [];
    const selectedOverride = selectedFiles[path.component_id];
    const selectedFileName = selectedOverride ?? path.selected_file_name ?? path.package_name ?? "";
    return [{
      action: simpleFirmwareAction(path),
      applyEnabled: Boolean(path.apply_enabled),
      candidateFiles,
      component: firmwareComponentLabel(path),
      componentId: path.component_id,
      current: displayValue(path.current_version),
      disabledReason: path.disabled_reason ?? "",
      equipment: path.equipment_label || path.device_label || summary?.label || "Equipment",
      estimatedImpact: path.estimated_impact ?? "Review required",
      evidenceArtifacts: path.evidence_artifacts ?? [],
      pathStatus: simpleFirmwareStatus(path, selectedFileName),
      missingEvidence: path.missing_evidence ?? [],
      prechecksRequired: path.prechecks_required ?? [],
      rebootRequired: Boolean(path.reboot_required),
      selectedFileName,
      selectionSource: selectedOverride !== undefined ? "user" : path.selection_source ?? (selectedFileName ? "auto" : "none"),
      target: cleanFirmwareTargetVersion(path.target_version, selectedFileName || path.package_name || "")
    }];
  });
}

function firmwareDecisionSummary(rows: FirmwareTableRow[]): string {
  const upgrades = rows.filter((row) => row.pathStatus !== "current" && row.pathStatus !== "scan_needed" && row.target !== "Not set").length;
  const current = rows.filter((row) => row.pathStatus === "current").length;
  const notChecked = rows.filter((row) => row.pathStatus === "scan_needed").length;
  return `${upgrades} upgrades available - ${current} current - ${notChecked} not checked`;
}

function cleanFirmwareTargetVersion(target: unknown, packageName: string): string {
  const rawTarget = displayValue(target);
  if (/^\d+(?:\.\d+){1,4}$/.test(rawTarget)) return rawTarget;
  const rawVersion = rawTarget.match(/\d+(?:\.\d+){1,3}/)?.[0];
  if (rawVersion) return rawVersion;
  const versionSource = packageName || rawTarget;
  const match = versionSource.match(/[_-](\d+\.\d+(?:\.\d+){1,3})(?=[._-]|$)/) || versionSource.match(/\d+\.\d+(?:\.\d+){1,3}/);
  return match?.[1] ?? "Not set";
}

function firmwareUpgradePaths(
  summaries: FirmwareSummary[],
  compliance: ProviderProbeResult | null
): Array<{ path: FirmwareUpgradePath; summary: FirmwareSummary | null }> {
  const compliancePaths = recordArray(compliance?.upgrade_paths)
    .map((path) => path as FirmwareUpgradePath)
    .filter((path) => path.component_id);
  if (compliancePaths.length) {
    return compliancePaths.map((path) => ({
      path,
      summary: summaries.find((summary) => summary.upgrade_paths.some((candidate) => candidate.component_id === path.component_id)) ?? null
    }));
  }
  return summaries.flatMap((summary) => {
    const paths = summary.upgrade_paths?.length ? summary.upgrade_paths : [legacyPath(summary)];
    return paths.map((path) => ({ path, summary }));
  });
}

function isOptionalUndetectedFirmwareComponent(componentId: string, path: FirmwareUpgradePath): boolean {
  if (!["netapp_disk_firmware", "netapp_shelf_firmware", "netapp_sp_bmc_firmware"].includes(componentId)) return false;
  return !path.current_version && !path.target_version && !(path.candidate_files?.length);
}

function firmwareComponentLabel(path: FirmwareUpgradePath): string {
  if (path.component_id === "cisco_ios_xe_version") return "IOS XE";
  if (path.component_id === "hpe_ilo_firmware") return "iLO firmware";
  if (path.component_id === "hpe_bios_version") return "Service Pack / BIOS";
  if (path.component_id === "hpe_smart_array_firmware") return "Service Pack / Smart Array";
  if (path.component_id === "esxi_version") return "ESXi image";
  if (path.component_id === "netapp_ontap_version") return "ONTAP";
  if (path.component_id === "vcenter_vcsa_version") return "VCSA";
  return path.component_label;
}

function simpleFirmwareStatus(path: FirmwareUpgradePath, selectedFileName: string): string {
  if (path.path_status === "current") return "current";
  if (!path.current_version) return "scan_needed";
  if (!selectedFileName && path.package_available === false) return "file_needed";
  if (path.path_status === "blocked") return "file_needed";
  if (path.path_status === "manual_review") return "manual_review";
  if (path.path_status === "direct" || path.path_status === "staged") return "ready_to_upgrade";
  if (path.target_version && path.current_version !== path.target_version) return "upgrade_available";
  return "not_setup";
}

function simpleFirmwareAction(path: FirmwareUpgradePath): string {
  if (path.path_status === "current") return "No upgrade needed.";
  if (!path.current_version) return "Scan firmware.";
  if (path.path_status === "blocked") return "Choose a matching file.";
  if (path.path_status === "manual_review") return "Review baseline.";
  return humanize(path.next_action || "Validate upgrade path.");
}

function selectionSourceLabel(source: string): string {
  if (source === "auto") return "Auto-selected";
  if (source === "user") return "Selected by user";
  return "No file selected";
}

function nextFirmwareFileSelections(
  current: Record<string, string>,
  componentId: string,
  fileName: string
): Record<string, string> {
  const nextSelections = { ...current };
  const cleanFileName = fileName.trim();
  if (cleanFileName) {
    nextSelections[componentId] = cleanFileName;
  } else {
    delete nextSelections[componentId];
  }
  return nextSelections;
}

function selectionStatusLabel(fileSelections: FirmwareFileSelections | null, saving: boolean): string {
  if (saving) return "Saving";
  const count = Object.keys(fileSelections?.selected_files ?? {}).length;
  return count ? `${count} saved` : "Not saved";
}

function legacyPath(summary: FirmwareSummary): FirmwareUpgradePath {
  return {
    apply_enabled: Boolean(summary.apply_enabled),
    baseline_source: null,
    component_id: summary.device_id,
    component_label: summary.label,
    current_version: currentVersion(summary) || null,
    device_label: summary.label,
    disabled_reason: summary.disabled_reason ?? "",
    equipment_type: summary.component_type ?? "unknown",
    estimated_impact: summary.estimated_impact ?? "None",
    evidence_artifacts: summary.evidence_artifacts,
    freshness: summary.freshness,
    last_checked: summary.last_scanned,
    missing_evidence: [],
    next_action: summary.next_action,
    package_available: Boolean(summary.package_available),
    package_name: summary.package_name ?? null,
    package_version: null,
    path_status: summary.path_status || summary.compliance_status,
    prechecks_required: summary.prechecks_required ?? [],
    reboot_required: Boolean(summary.reboot_required),
    required_intermediate_versions: summary.required_intermediate_versions ?? [],
    scan_action_id: summary.scan_action_id,
    source_type: summary.source_type,
    target_version: summary.target_version
  };
}

function currentVersion(summary: FirmwareSummary | null): string {
  return summary?.current_versions.map((version) => version.version).filter(Boolean).join(", ") ?? "";
}

function firmwareVersion(summaries: FirmwareSummary[], device: string): string {
  const summary = summaries.find((candidate) =>
    candidate.device_id === device ||
    candidate.label.toLowerCase().includes(device.toLowerCase()) ||
    candidate.component_type.toLowerCase().includes(device.toLowerCase())
  );
  if (!summary) return "Not checked";
  return currentVersion(summary) || summary.target_version || "Not checked";
}

function vcenterTarget(probe: ProviderProbeResult | null, profile: LabProfile | null): string {
  const targets = objectValue(probe?.targets);
  const deployment = objectValue(probe?.deployment_values);
  const devices = objectValue(profile?.devices);
  const explicit =
    asString(targets.vcenter) ||
    asString(targets.vcenter_target) ||
    asString(deployment.vcenter_target) ||
    asString(devices.vcenter);
  const managementIp =
    asString(targets.vcenter_management_ip) ||
    asString(deployment.management_ip) ||
    asString(deployment.vcenter_management_ip);
  if (explicit) return explicit.startsWith("http") ? explicit : `https://${explicit}/sdk`;
  if (managementIp) return `https://${managementIp}/sdk`;
  return "Not set up yet";
}

function vcenterAddress(probe: ProviderProbeResult | null, profile: LabProfile | null): string {
  const target = vcenterTarget(probe, profile);
  if (target === "Not set up yet") return target;
  try {
    return new URL(target).hostname || target;
  } catch {
    return target.replace(/^https?:\/\//, "").replace(/\/sdk\/?$/, "");
  }
}

function consolePathFromCisco(probe: ProviderProbeResult | null): string {
  const consoleState = objectValue(probe?.console);
  return displayValue(
    asString(consoleState.selected_path) ||
    asString(consoleState.effective_path) ||
    asString(consoleState.path)
  );
}

function consolePathFromNetapp(probe: ProviderProbeResult | null): string {
  const consoleState = objectValue(probe?.console);
  const runtimeConsole = objectValue(objectValue(probe?.runtime_state).console);
  const selected = objectValue(probe?.selected_console);
  return displayValue(
    asString(consoleState.selected_path) ||
    asString(consoleState.effective_path) ||
    asString(runtimeConsole.discovered_port) ||
    asString(runtimeConsole.selected_port) ||
    asString(selected.path) ||
    asString(probe?.selected_port) ||
    asString(probe?.console_port)
  );
}

function datastoreName(probe: ProviderProbeResult | null): string {
  const targets = objectValue(probe?.targets);
  const deployment = objectValue(probe?.deployment_values);
  const current = objectValue(probe?.current_state);
  const targetState = objectValue(probe?.target_state);
  return (
    asString(targets.datastore_name) ||
    asString(targets.datastore) ||
    asString(deployment.datastore_target) ||
    asString(current.netapp_datastore) ||
    asString(targetState.datastore) ||
    "netapp_nfs_ds01"
  );
}

function datastoreVisibleStatus(probe: ProviderProbeResult | null): string {
  const checks = objectValue(probe?.checks);
  const postAttach = objectValue(probe?.post_attach_state);
  const mounted = objectValue(checks.datastore_mounted);
  const visible = objectValue(checks.netapp_datastore_visible);
  if (asBoolean(mounted.visible) || asBoolean(visible.visible) || asBoolean(postAttach.ready)) return "ready";
  return asString(probe?.status) || "not_checked";
}

function attachStateLabel(readiness: ProviderProbeResult | null, postAttach: ProviderProbeResult | null): string {
  const post = objectValue(postAttach?.post_attach_state);
  if (asBoolean(post.ready) || asString(postAttach?.status) === "ready") return "Attached";
  if (asString(readiness?.status) === "ready") return "Ready";
  return "Not checked";
}

function visibilityLabel(value: unknown): string {
  const item = objectValue(value);
  if (asBoolean(item.visible)) return "Visible";
  if (asString(item.status) === "ready") return "Visible";
  if (asString(item.status)) return displayStatus(asString(item.status));
  return "Not checked";
}

function visibilityStatus(value: unknown): string {
  const item = objectValue(value);
  if (asBoolean(item.visible) || asString(item.status) === "ready") return "ready";
  return asString(item.status) || "not_checked";
}

function credentialSummary(probe: ProviderProbeResult | null): string {
  const credentialState = objectValue(probe?.credential_state);
  const configured = [
    credentialState.vcenter_credentials_configured,
    credentialState.netapp_credentials_configured
  ].filter(Boolean).length;
  if (configured === 2) return "Configured";
  if (configured === 1) return "Partly configured";
  return "Missing or not checked";
}

function raidLayoutLabel(probe: unknown): string {
  const evidence = objectValue(probe);
  const desired = objectValue(evidence.desired_intent);
  const volumes = Array.isArray(desired.volumes) ? desired.volumes : [];
  if (volumes.length) return `${volumes.length} volume${volumes.length === 1 ? "" : "s"} planned`;
  return displayStatus(asString(evidence.status) || "not_checked");
}

function raidControllerModels(probe: unknown): string {
  const currentLayout = objectValue(objectValue(probe).current_layout);
  const controllers = recordArray(currentLayout.controllers);
  const models = controllers
    .map((controller) => asString(controller.Model) || asString(controller.model) || asString(controller.Name) || asString(controller.name))
    .filter(Boolean);
  return models.length ? Array.from(new Set(models)).join(", ") : "Not discovered yet";
}

function servicePackSummary(summaries: FirmwareSummary[]): string {
  const hpePaths = summaries.flatMap((summary) =>
    summary.upgrade_paths.filter((path) => ["hpe_ilo_firmware", "hpe_bios_version", "hpe_smart_array_firmware"].includes(path.component_id))
  );
  const fileNames = hpePaths
    .map((path) => path.selected_file_name || path.package_name)
    .filter((name): name is string => Boolean(name));
  if (fileNames.length) return Array.from(new Set(fileNames)).join(", ");
  const hasHpeRows = hpePaths.length || summaries.some((summary) => ["ilo", "raid"].includes(summary.device_id));
  return hasHpeRows ? "No service pack selected" : "Scan needed";
}

function offsetSummary(address: LabAddressPlan): string {
  const values = [
    address.ilo && `iLO ${lastOctet(address.ilo)}`,
    address.esxi_management && `ESXi ${lastOctet(address.esxi_management)}`,
    address.cisco_management && `Cisco ${lastOctet(address.cisco_management)}`
  ].filter(Boolean);
  return values.join(", ") || "Not set up yet";
}

function netappAddressSummary(address: LabAddressPlan): string {
  const values = [
    address.netapp_cluster_mgmt && `Cluster ${address.netapp_cluster_mgmt}`,
    address.netapp_svm_mgmt && `SVM ${address.netapp_svm_mgmt}`,
    address.netapp_nfs_lifs.length && `NFS ${address.netapp_nfs_lifs.join(", ")}`
  ].filter(Boolean);
  return values.join(" / ") || "Not set up yet";
}

function lastOctet(value: string): string {
  return value.split(".").pop() || value;
}

function featureToggleSummary(features: LabProfileFeatures | null): string {
  if (!features) return "Not set up yet";
  const enabled = [
    features.enable_dns && "DNS",
    features.enable_ntp && "NTP",
    features.enable_snmp && "SNMP",
    features.disable_ipv6 && "IPv6 disabled",
    features.block_legacy_protocols && "Legacy protocols blocked"
  ].filter(Boolean);
  return enabled.join(", ") || "No toggles enabled";
}

function featureStatus(features: LabProfileFeatures | null, key: keyof LabProfileFeatures): string {
  return features && Boolean(features[key]) ? "ready" : "not_checked";
}

function enabledLabel(value: boolean | undefined): string {
  return value ? "Enabled" : "Disabled";
}

function boolStateLabel(value: boolean): string {
  return value ? "Configured" : "Not checked";
}

function listLabel(value: unknown): string {
  if (Array.isArray(value)) {
    return value.length ? value.map((item) => asString(item)).filter(Boolean).join(", ") : "Not set up yet";
  }
  return displayValue(asString(value));
}

function displayAddress(value: unknown): string {
  return displayValue(asString(value));
}

function displayValue(value: unknown): string {
  const text = asString(value);
  return text ? humanize(text) : "Not set up yet";
}

function runtimeStatus(health: HealthLike): string {
  return health?.provider_mode ?? health?.operator_runtime_mode ?? "not_checked";
}

function sourceLabel(value: unknown): string {
  const item = objectValue(value);
  const source = asString(item.source_type);
  const freshness = asString(item.freshness);
  if (source === "live_probe" || source === "live_cached" || source === "cached_live") return "Live";
  if (source === "historical_artifact" || freshness === "historical" || freshness === "stale") return "Previous proof";
  if (source === "not_checked" || freshness === "not_checked") return "Not checked";
  if (source) return displayStatus(source);
  return "Not checked";
}

function sourceLabelFromStatus(status: string): string {
  if (status === "ready") return "Ready";
  if (status === "not_checked") return "Not checked";
  return displayStatus(status);
}

function storageProtocolLabel(features: LabProfileFeatures | null): string {
  return labelize(features?.storage_protocol || "none");
}

function overviewCurrentView({
  buildVerification,
  providers,
  validation
}: {
  buildVerification: ProviderProbeResult | null;
  providers: ProviderStatus[];
  validation: LabValidationSummary | null;
}): CurrentViewModel {
  const readyProviders = providers.filter((provider) => ["ready", "ok", "passed"].includes(provider.status)).length;
  const status = validation?.overall_status || strongestStatus([buildVerification?.status ?? "not_checked", ...providers.map((provider) => provider.status)]);
  return currentViewModel({
    available: Boolean(validation || buildVerification || providers.length),
    details: [
      { label: "Provider checks", value: providers.length ? `${readyProviders} ready / ${providers.length} loaded` : "Not checked" },
      { label: "Validation rows", value: String(validation?.validation_items.length ?? 0) },
      { label: "Build verification", value: displayStatus(buildVerification?.status ?? "not_checked"), status: buildVerification?.status ?? "not_checked" }
    ],
    fixSteps: [
      validation?.next_action,
      "Run Validation to refresh the lab-wide current view.",
      "Open Saved Setups if targets are missing; credentials stay in local secret files."
    ],
    recheckCommand: "make provider-lab-build-verification",
    scanDetail: "Run Validation refreshes the current view across the lab and records the next blocker if one exists.",
    scanLabel: "Run Validation",
    signals: [validation, buildVerification, ...providers],
    status,
    summary: validation?.top_blocker?.problem || validation?.next_action || "The overview uses validation and device status as its current view."
  });
}

function networkCurrentView({
  address,
  ciscoReadiness
}: {
  address: LabAddressPlan;
  ciscoReadiness: ProviderProbeResult | null;
}): CurrentViewModel {
  const consoleState = objectValue(ciscoReadiness?.console);
  const status = asString(ciscoReadiness?.status) || (address.cisco_management ? "not_checked" : "not_configured_yet");
  return currentViewModel({
    available: Boolean(ciscoReadiness?.checked_at || ciscoReadiness?.status),
    details: [
      { label: "Cisco target", value: displayAddress(address.cisco_management), source: "Saved setup" },
      { label: "Console", value: displayValue(asString(consoleState.selected_path) || asString(consoleState.effective_path)), status: asString(consoleState.status) || "not_checked" },
      { label: "SSH access", value: boolStateLabel(asBoolean(ciscoReadiness?.management_configured)), status: asBoolean(ciscoReadiness?.management_configured) ? "ready" : "not_checked" }
    ],
    fixSteps: [
      asString(ciscoReadiness?.next_safe_action),
      "Confirm the Cisco management IP and console path in Network Configure or Saved Setups.",
      "Run Live Switch Check after fixing connectivity or credentials."
    ],
    recheckCommand: "make provider-lab-cisco-setup-readiness",
    scanDetail: "Live Switch Check reads Cisco reachability, console readiness, credential state, and current-to-intent drift without printing secrets.",
    scanLabel: "Live Switch Check",
    signals: [ciscoReadiness],
    status,
    summary: asString(ciscoReadiness?.message) || asString(ciscoReadiness?.next_safe_action) || "No Cisco current view has been loaded yet."
  });
}

function serverCurrentView({
  address,
  esxiReadiness,
  iloStatus,
  raidPlan,
  raidStatus
}: {
  address: LabAddressPlan;
  esxiReadiness: ProviderProbeResult | null;
  iloStatus: string;
  raidPlan: ProviderProbeResult | null;
  raidStatus: string;
}): CurrentViewModel {
  const status = strongestStatus([iloStatus, esxiReadiness?.status ?? "not_checked", raidStatus]);
  return currentViewModel({
    available: Boolean(esxiReadiness?.checked_at || raidPlan?.checked_at || iloStatus !== "not_checked" || raidStatus !== "not_checked"),
    details: [
      { label: "iLO", value: address.ilo ? `https://${address.ilo}` : "Not set up yet", status: iloStatus },
      { label: "ESXi", value: displayAddress(address.esxi_management), status: esxiReadiness?.status ?? "not_checked" },
      { label: "RAID", value: raidLayoutLabel(raidPlan), status: raidStatus }
    ],
    fixSteps: [
      asString(esxiReadiness?.next_safe_action),
      "Run iLO Live Check before inventory or firmware work.",
      "Run ESXi Live Check after iLO and management networking are reachable."
    ],
    recheckCommand: "make provider-lab-ilo-reachability",
    scanDetail: "iLO and ESXi live checks refresh the current server view; Validate RAID refreshes the storage controller plan.",
    scanLabel: "Server Live Check",
    signals: [esxiReadiness, raidPlan],
    status,
    summary: asString(esxiReadiness?.message) || asString(raidPlan?.message) || "No server current view has been loaded yet."
  });
}

function storageCurrentView({
  address,
  consoleReadiness,
  netappPlan,
  nfsReadiness,
  vcenterNetapp
}: {
  address: LabAddressPlan;
  consoleReadiness: ProviderProbeResult | null;
  netappPlan: ProviderProbeResult | null;
  nfsReadiness: ProviderProbeResult | null;
  vcenterNetapp: ProviderProbeResult | null;
}): CurrentViewModel {
  const status = storagePageStatus({ netappPlan, nfsReadiness, vcenterNetapp });
  return currentViewModel({
    available: Boolean(vcenterNetapp?.checked_at || nfsReadiness?.checked_at || netappPlan?.checked_at || consoleReadiness?.checked_at),
    details: [
      { label: "Cluster", value: displayAddress(address.netapp_cluster_mgmt), status },
      { label: "Console", value: displayValue(asString(objectValue(consoleReadiness?.runtime_state).console)), status: asString(consoleReadiness?.status) || "not_checked" },
      { label: "Datastore", value: datastoreName(vcenterNetapp), status: datastoreVisibleStatus(vcenterNetapp) }
    ],
    fixSteps: [
      storagePageNextAction({ netappPlan, nfsReadiness, vcenterNetapp }),
      "Run NetApp Live Check to refresh ONTAP access and setup readiness.",
      "Run Validate NFS before any datastore mount action."
    ],
    recheckCommand: "make provider-lab-netapp-live-state",
    scanDetail: "NetApp Live Check refreshes ONTAP access; Validate NFS explains which storage or vCenter prerequisite is missing.",
    scanLabel: "NetApp Live Check",
    signals: [vcenterNetapp, nfsReadiness, netappPlan, consoleReadiness],
    status,
    summary: asString(nfsReadiness?.message) || asString(netappPlan?.message) || asString(vcenterNetapp?.message) || "No storage current view has been loaded yet."
  });
}

function storagePageStatus({
  netappPlan,
  nfsReadiness,
  vcenterNetapp
}: {
  netappPlan: ProviderProbeResult | null;
  nfsReadiness: ProviderProbeResult | null;
  vcenterNetapp: ProviderProbeResult | null;
}) {
  const candidates = [asString(nfsReadiness?.status), asString(netappPlan?.status), asString(vcenterNetapp?.status)].filter(Boolean);
  return candidates.find((status) => !isOutOfScopeStatus(status)) || candidates[0] || "not_checked";
}

function storagePageNextAction({
  netappPlan,
  nfsReadiness,
  vcenterNetapp
}: {
  netappPlan: ProviderProbeResult | null;
  nfsReadiness: ProviderProbeResult | null;
  vcenterNetapp: ProviderProbeResult | null;
}) {
  const pairs = [
    { action: asString(nfsReadiness?.next_safe_action), status: asString(nfsReadiness?.status) },
    { action: asString(netappPlan?.next_safe_action), status: asString(netappPlan?.status) },
    { action: asString(vcenterNetapp?.next_safe_action), status: asString(vcenterNetapp?.status) }
  ];
  return pairs.find((pair) => pair.action && !isOutOfScopeStatus(pair.status))?.action || pairs.find((pair) => pair.action)?.action || "";
}

function isOutOfScopeStatus(status: string) {
  return ["not_in_scope", "not_in_this_setup"].includes(status);
}

function virtualizationCurrentView({
  activeProfile,
  features,
  installReadiness,
  postAttach,
  vcenterNetapp
}: {
  activeProfile: LabProfile | null;
  features: LabProfileFeatures | null;
  installReadiness: ProviderProbeResult | null;
  postAttach: ProviderProbeResult | null;
  vcenterNetapp: ProviderProbeResult | null;
}): CurrentViewModel {
  const vcenterEnabled = features?.vcenter_enabled !== false;
  const scenarioLabel = deploymentScenarioLabel(features);
  const storageLabel = storageLocationLabel(features);
  const postChecks = objectValue(postAttach?.checks);
  const status = vcenterEnabled
    ? strongestStatus([
        asString(postAttach?.status) || "not_checked",
        asString(vcenterNetapp?.status) || "not_checked",
        asString(installReadiness?.status) || "not_checked"
      ])
    : "not_checked";
  return currentViewModel({
    available: Boolean(postAttach?.checked_at || vcenterNetapp?.checked_at || installReadiness?.checked_at),
    details: vcenterEnabled
      ? [
          { label: "vCenter", value: vcenterTarget(vcenterNetapp || installReadiness, activeProfile), status },
          { label: "Datastore", value: datastoreName(vcenterNetapp), status: datastoreVisibleStatus(vcenterNetapp || postAttach) },
          { label: "VM inventory", value: visibilityLabel(postChecks.vm_inventory_visible), status: visibilityStatus(postChecks.vm_inventory_visible) }
        ]
      : [
          { label: "Scenario", value: scenarioLabel, status },
          { label: "ESXi", value: displayAddress(activeAddressPlan(activeProfile).esxi_management), status },
          { label: "Storage", value: storageLabel, status }
        ],
    fixSteps: vcenterEnabled
      ? [
          asString(vcenterNetapp?.next_safe_action) || asString(installReadiness?.next_safe_action),
          "Run vCenter Live Check to refresh the current virtualization view.",
          "Run Validate Inventory after datastore and vCenter access are ready."
        ]
      : ["Run ESXi Live Check to refresh the direct host view.", "Validate datastore visibility from ESXi.", "Run VM deployment validation after ESXi storage is ready."],
    recheckCommand: vcenterEnabled ? "make provider-lab-vcenter-netapp-readiness" : "make provider-lab-esxi-management-validation",
    scanDetail: vcenterEnabled
      ? "vCenter Live Check checks the vCenter target, ESXi attach readiness, datastore visibility, and credential state."
      : "ESXi Live Check checks direct host management for setups that do not use vCenter.",
    scanLabel: vcenterEnabled ? "vCenter Live Check" : "ESXi Live Check",
    signals: [postAttach, vcenterNetapp, installReadiness],
    status,
    summary: vcenterEnabled
      ? asString(postAttach?.message) || asString(vcenterNetapp?.message) || asString(installReadiness?.message) || "No virtualization current view has been loaded yet."
      : `${scenarioLabel}: vCenter is out of scope; use the direct ESXi validation path.`
  });
}

function firmwareCurrentView({
  compliance,
  files,
  rows
}: {
  compliance: ProviderProbeResult | null;
  files: { lastScanned: string; packageCount: number };
  rows: FirmwareTableRow[];
}): CurrentViewModel {
  const status = strongestStatus([asString(compliance?.status) || "not_checked", ...rows.map((row) => row.pathStatus)]);
  const needsReview = rows.filter((row) => !["ready", "current", "ready_to_upgrade"].includes(row.pathStatus)).length;
  return currentViewModel({
    available: Boolean(compliance?.checked_at || rows.length || files.packageCount),
    details: [
      { label: "Media files", value: String(files.packageCount), status: files.packageCount ? "ready" : "not_checked" },
      { label: "Firmware rows", value: String(rows.length), status: rows.length ? status : "not_checked" },
      { label: "Needs review", value: String(needsReview), status: needsReview ? "warning" : "ready" }
    ],
    fixSteps: [
      asString(compliance?.next_safe_action),
      "Put firmware media in artifacts/Media, then run Scan Firmware.",
      "Select the correct file for each row before any guarded upgrade workflow."
    ],
    recheckCommand: "make provider-lab-firmware-compliance",
    scanDetail: "Scan Firmware refreshes inventory, media matching, and compliance guidance before any guarded upgrade action.",
    scanLabel: "Scan Firmware",
    signals: [compliance],
    status,
    summary: asString(compliance?.message) || (rows.length ? "Firmware current view is based on inventory, media matching, and selected files." : "No firmware current view has been loaded yet.")
  });
}

function validationCurrentView({
  buildVerification,
  validation,
  vcenterNetapp
}: {
  buildVerification: ProviderProbeResult | null;
  validation: LabValidationSummary | null;
  vcenterNetapp: ProviderProbeResult | null;
}): CurrentViewModel {
  const differentFromExpected = validation?.validation_items.filter((item) => item.status !== "ready").length ?? 0;
  return currentViewModel({
    available: Boolean(validation || buildVerification || vcenterNetapp),
    details: [
      { label: "Different from expected", value: String(differentFromExpected), status: differentFromExpected ? "warning" : "ready" },
      { label: "Build verification", value: displayStatus(buildVerification?.status ?? "not_checked"), status: buildVerification?.status ?? "not_checked" },
      { label: "vCenter-NetApp", value: displayStatus(vcenterNetapp?.status ?? "not_checked"), status: vcenterNetapp?.status ?? "not_checked" }
    ],
    fixSteps: [
      validation?.top_blocker?.recommended_action || validation?.next_action,
      "Run Validation to refresh current blockers and proof links.",
      "Use the top blocker as the first fix before generating handoff."
    ],
    recheckCommand: "make provider-lab-build-verification",
    scanDetail: "Run Validation refreshes the current blocker list and prepares the final report view.",
    scanLabel: "Run Validation",
    signals: [validation, buildVerification, vcenterNetapp],
    status: validation?.overall_status ?? "not_checked",
    summary: validation?.top_blocker?.problem || validation?.next_action || "No validation current view has been loaded yet."
  });
}

function currentViewModel({
  available,
  blockers = [],
  checkedAt,
  details,
  fixSteps,
  freshness,
  recheckCommand,
  scanDetail,
  scanLabel,
  signals = [],
  source,
  status,
  summary,
  warnings = []
}: CurrentViewModelInput): CurrentViewModel {
  return {
    available,
    blockers: uniqueStrings([...blockers, ...signalMessages(signals, "blockers")]),
    checkedAt: checkedAt ? formatDateTime(checkedAt) : firstCheckedAt(signals),
    details,
    fixSteps: uniqueStrings(fixSteps),
    freshness: displayStatus(freshness || firstMetadataValue(signals, ["freshness"]) || firstMetadataValue(signals, ["source_type"]) || "not_checked"),
    recheckCommand: recheckCommand || firstMetadataValue(signals, ["recheck_command"]),
    scanDetail,
    scanLabel,
    source: source || firstSource(signals),
    status: status || "not_checked",
    summary: humanize(summary),
    warnings: uniqueStrings([...warnings, ...signalMessages(signals, "warnings")])
  };
}

function firstSource(signals: unknown[]): string {
  for (const signal of signals) {
    const label = sourceLabel(signal);
    if (label && label !== "Not checked") return label;
  }
  return "Not checked";
}

function firstCheckedAt(signals: unknown[]): string {
  const raw = firstMetadataValue(signals, ["checked_at", "generated_at", "last_checked", "last_scanned", "updated_at"]);
  return raw ? formatDateTime(raw) : "Not checked";
}

function firstMetadataValue(signals: unknown[], keys: string[]): string {
  for (const signal of signals) {
    const record = objectValue(signal);
    for (const key of keys) {
      const value = asString(record[key]);
      if (value) return value;
    }
  }
  return "";
}

function signalMessages(signals: unknown[], key: "blockers" | "warnings"): string[] {
  return signals.flatMap((signal) => stringArray(objectValue(signal)[key]));
}

function isOperatorStorageWarning(value: string): boolean {
  const normalized = value.toLowerCase();
  if (!normalized) return false;
  return ![
    "manual env flag not required",
    "live checks are read-only",
    "preview-only",
    "vcenter is disabled",
    "only newline and carriage return",
    "no netapp credentials",
    "serial auto-discovery"
  ].some((token) => normalized.includes(token));
}

function uniqueStrings(values: Array<string | undefined | null>): string[] {
  return Array.from(new Set(values.map((value) => asString(value).trim()).filter(Boolean)));
}

function freshnessStatus(value: string): string {
  const normalized = value.toLowerCase();
  if (normalized.includes("live") || normalized.includes("recent") || normalized.includes("operator config") || normalized.includes("saved")) return "ready";
  if (normalized.includes("old") || normalized.includes("previous") || normalized.includes("stale")) return "warning";
  return "not_checked";
}

function strongestStatus(statuses: string[]): string {
  const normalized = statuses.map((status) => status || "not_checked");
  if (normalized.some((status) => ["blocked", "failed", "critical", "hard_fail"].includes(status))) return "blocked";
  if (normalized.some((status) => ["warning", "partial", "manual_review", "cannot_verify"].includes(status))) return "warning";
  if (normalized.some((status) => ["not_configured", "not_configured_yet", "not_checked", "not_in_scope"].includes(status))) {
    return normalized.find((status) => ["ready", "ok", "completed", "passed"].includes(status)) ? "warning" : "not_checked";
  }
  if (normalized.some((status) => ["ready", "ok", "completed", "passed"].includes(status))) return "ready";
  return normalized[0] ?? "not_checked";
}

function statusTone(status: string): string {
  const normalized = status || "not_checked";
  if (["accessible", "ready", "ok", "completed", "passed", "success", "current"].includes(normalized)) return "ready";
  if (["blocked", "failed", "critical", "hard_fail", "error"].includes(normalized)) return "blocked";
  if (["needs_console", "needs_credentials", "not_accessible", "warning", "partial", "manual_review", "cannot_verify", "stale"].includes(normalized)) return "warning";
  return "neutral";
}

function displayStatus(status: string): string {
  const labels: Record<string, string> = {
    accessible: "Accessible",
    blocked: "Blocked",
    cannot_verify: "Needs review",
    completed: "Ready",
    configured: "Configured",
    current: "Current",
    failed: "Needs attention",
    file_needed: "File needed",
    hard_fail: "Blocked",
    historical: "Previous proof",
    historical_artifact: "Previous proof",
    cached_live: "Recent live check",
    live: "Live",
    live_cached: "Recent live check",
    live_probe: "Live check",
    "local-lab-readwrite": "Real lab",
    "local-readonly": "Read-only lab",
    manual_review: "Needs review",
    missing: "Missing",
    mock: "Fixture mode",
    not_checked: "Not checked",
    not_configured: "Not set up yet",
    not_configured_yet: "Not set up yet",
    not_accessible: "Not accessible",
    not_setup: "Not set up",
    not_in_scope: "Not in this setup",
    ok: "Ready",
    operator_config: "Operator config",
    partial: "Partly ready",
    passed: "Ready",
    ready: "Ready",
    ready_to_upgrade: "Ready to upgrade",
    scan_needed: "Scan needed",
    stale: "Old proof",
    success: "Ready",
    unavailable: "Not available",
    upgrade_available: "Upgrade available",
    warning: "Needs review",
    needs_console: "Needs console",
    needs_credentials: "Needs credentials",
    needs_firmware_scan: "Needs scan"
  };
  return labels[status] ?? labelize(status || "not_checked");
}

function humanize(value: string): string {
  if (!value) return "";
  return value
    .replace(/Cisco SSH is not reachable\.?/gi, "Cisco switch cannot be reached over SSH.")
    .replace(/Cisco read-only output missing:\s*show vlan brief\.?/gi, "Cisco VLAN check needs a reachable SSH session.")
    .replace(/Cisco read-only output missing:\s*show interfaces status\.?/gi, "Cisco port check needs a reachable SSH session.")
    .replace(/PROVIDER MODE=Read-only lab or PROVIDER_MODE=local-lab-readwrite is required before opening a real NetApp console\.?/gi, "Choose Read-only lab or Real lab before checking NetApp storage.")
    .replace(/NetApp cluster management REST is not reachable\.?/gi, "NetApp management is not reachable.")
    .replace(/Cluster management REST is not reachable\.?/gi, "NetApp management is not reachable.")
    .replace(/NFS LIF `([^`]+)` is not accepting TCP\/2049\.?/gi, "NFS address $1 is not reachable.")
    .replace(/iSCSI LIF `([^`]+)` is not accepting TCP\/3260\.?/gi, "iSCSI address $1 is not reachable.")
    .replace(/NetApp API authentication is required to verify protocol service licensing\.?/gi, "NetApp sign-in is needed to verify protocol licensing.")
    .replace(/No live NetApp configured state exists yet; run Validate NetApp Setup\.?/gi, "Run NetApp validation after management is reachable.")
    .replace(/NetApp ONTAP cluster is not live-configured yet; iSCSI setup is blocked by prior cluster setup\.?/gi, "Finish NetApp setup before iSCSI checks.")
    .replace(/ONTAP [^.;]+ inventory returned HTTP None\.?/gi, "NetApp inventory is not available yet.")
    .replace(/ESXi VMFS datastore `([^`]+)` is not visible\.?/gi, "ESXi cannot see datastore $1 yet.")
    .replace(/Saved intent requests destructive wipe\/delete planning\.?/gi, "A saved RAID change needs review.")
    .replace(/Execution remains disabled\.?/gi, "Applying it is locked until you explicitly approve it.")
    .replace(/\bPROVIDER[_ ]MODE\s*=\s*/gi, "")
    .replace(/[A-Z0-9]+(?:_[A-Z0-9]+){2,}/g, (match) => labelize(match.toLowerCase()))
    .replace(/not_configured_yet/g, "Not set up yet")
    .replace(/not_configured/g, "Not set up yet")
    .replace(/manual_review/g, "Needs review")
    .replace(/local-lab-readwrite/g, "Real lab")
    .replace(/local-readonly/g, "Read-only lab")
    .replace(/\bprovider mode\b/gi, "lab mode")
    .replace(/\bprovider\b/gi, "device")
    .replace(/\bruntime\b/gi, "lab")
    .replace(/Artifact/g, "Proof")
    .replace(/artifact/g, "proof")
    .replace(/Workflow action/g, "Action")
    .replace(/workflow action/g, "action")
    .replace(/Drift/g, "Different from expected")
    .replace(/drift/g, "different from expected")
    .replace(/_/g, " ");
}

function labelize(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function asString(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function asBoolean(value: unknown): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") return ["true", "ready", "configured", "yes"].includes(value.toLowerCase());
  return Boolean(value);
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => asString(item)).filter(Boolean) : [];
}

function recordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item)) : [];
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}
