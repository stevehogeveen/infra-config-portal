import {
  Ban,
  CheckCircle2,
  Gauge,
  HardDrive,
  Layers,
  Play,
  RefreshCw,
  Route,
  Server,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  X,
  Wrench
} from "lucide-react";
import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { api } from "./api";
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
  StatusBadge,
  type StatusBadgeStatus
} from "./components/ui";
import type {
  FirmwareFileCandidate,
  FirmwareFileSelections,
  FirmwareSummary,
  FirmwareUpgradePath,
  LabAddressPlan,
  LabProfile,
  LabProfileFeatures,
  LabProfileList,
  LabValidationItem,
  LabValidationSummary,
  MediaInventory,
  ProviderProbeResult,
  ProviderStatus,
  WorkflowAction,
  WorkflowActionRun,
  WorkflowActionRunRequest
} from "./types";

type HealthLike = {
  expected_runtime_mode?: string;
  operator_runtime_mode?: string;
  provider_mode?: string;
  status?: string;
} | null;

type OperatorPageProps = {
  health?: HealthLike;
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
  | "validation"
  | "config"
  | "settings";

type IpMode = "ipv4" | "ipv6" | "both";
type SnmpVersion = "v2" | "v3";

type OperatorTabSettingsState = {
  advanced: Record<string, boolean | string>;
  ipMode: IpMode;
  snmpVersion: SnmpVersion;
};

type OperatorRunStatus = {
  actionId?: string;
  message: string;
  state: "idle" | "running" | "success" | "error";
};

type OperatorTabStateContextValue = {
  activeTab: OperatorTabId;
  closeSettings: () => void;
  openSettings: (tabId: OperatorTabId) => void;
  runStatus: Record<OperatorTabId, OperatorRunStatus>;
  setRunStatus: (tabId: OperatorTabId, status: OperatorRunStatus) => void;
  settingsOpenFor: OperatorTabId | null;
  tabSettings: Record<OperatorTabId, OperatorTabSettingsState>;
  updateTabSettings: (tabId: OperatorTabId, patch: Partial<OperatorTabSettingsState>) => void;
  updateTabAdvancedSetting: (tabId: OperatorTabId, key: string, value: boolean | string) => void;
};

const operatorTabs: OperatorTabId[] = [
  "overview",
  "network",
  "server",
  "storage",
  "virtualization",
  "firmware",
  "validation",
  "config",
  "settings"
];

const idleRunStatus: OperatorRunStatus = {
  message: "",
  state: "idle"
};

const OperatorTabStateContext = createContext<OperatorTabStateContextValue | null>(null);

export function OperatorTabStateProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const activeTab = tabFromPath(location.pathname);
  const [settingsOpenFor, setSettingsOpenFor] = useState<OperatorTabId | null>(null);
  const [tabSettings, setTabSettings] = useState<Record<OperatorTabId, OperatorTabSettingsState>>(() =>
    operatorTabs.reduce((accumulator, tabId) => {
      accumulator[tabId] = defaultTabSettings(tabId);
      return accumulator;
    }, {} as Record<OperatorTabId, OperatorTabSettingsState>)
  );
  const [runStatus, setRunStatusState] = useState<Record<OperatorTabId, OperatorRunStatus>>(() =>
    operatorTabs.reduce((accumulator, tabId) => {
      accumulator[tabId] = idleRunStatus;
      return accumulator;
    }, {} as Record<OperatorTabId, OperatorRunStatus>)
  );

  useEffect(() => {
    setSettingsOpenFor(null);
  }, [activeTab]);

  function updateTabSettings(tabId: OperatorTabId, patch: Partial<OperatorTabSettingsState>) {
    setTabSettings((current) => ({
      ...current,
      [tabId]: {
        ...current[tabId],
        ...patch
      }
    }));
  }

  function updateTabAdvancedSetting(tabId: OperatorTabId, key: string, value: boolean | string) {
    setTabSettings((current) => ({
      ...current,
      [tabId]: {
        ...current[tabId],
        advanced: {
          ...current[tabId].advanced,
          [key]: value
        }
      }
    }));
  }

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
        closeSettings: () => setSettingsOpenFor(null),
        openSettings: setSettingsOpenFor,
        runStatus,
        setRunStatus,
        settingsOpenFor,
        tabSettings,
        updateTabAdvancedSetting,
        updateTabSettings
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
  if (pathname.startsWith("/network")) return "network";
  if (pathname.startsWith("/server")) return "server";
  if (pathname.startsWith("/storage")) return "storage";
  if (pathname.startsWith("/virtualization")) return "virtualization";
  if (pathname.startsWith("/firmware")) return "firmware";
  if (pathname.startsWith("/validation")) return "validation";
  if (pathname.startsWith("/config")) return "config";
  if (pathname.startsWith("/settings")) return "settings";
  return "overview";
}

function defaultTabSettings(tabId: OperatorTabId): OperatorTabSettingsState {
  return {
    advanced: Object.fromEntries(tabAdvancedSettings(tabId).map((setting) => [setting.key, setting.defaultValue])),
    ipMode: "ipv4",
    snmpVersion: "v2"
  };
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

type AdvancedSettingDefinition = {
  defaultValue: boolean;
  description: string;
  key: string;
  label: string;
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

export function OperatorOverviewPage({
  health,
  labProfileError = "",
  labProfileLoading = false,
  labProfileState
}: OperatorPageProps) {
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    setLoading(true);
    try {
      const [
        nextProviders,
        nextValidation,
        nextFirmware,
        nextVcenterNetapp,
        nextBuildVerification,
        nextCiscoReadiness,
        nextNetappConsole
      ] = await Promise.all([
        safeApi(api.providers, [] as ProviderStatus[]),
        safeApi(api.labValidation, null),
        safeApi(api.firmwareSummary, [] as FirmwareSummary[]),
        safeApi(api.vcenterNetappReadiness, null),
        safeApi(api.buildVerification, null),
        safeApi(api.ciscoSetupReadiness, null),
        safeApi(api.netappConsoleReadiness, null)
      ]);
      setProviders(Array.isArray(nextProviders) ? nextProviders : []);
      setValidation(nextValidation);
      setFirmwareSummaries(Array.isArray(nextFirmware) ? nextFirmware : []);
      setVcenterNetapp(nextVcenterNetapp);
      setBuildVerification(nextBuildVerification);
      setCiscoReadiness(nextCiscoReadiness as ProviderProbeResult | null);
      setNetappConsole(nextNetappConsole as ProviderProbeResult | null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

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
  const workspaceRows = useMemo<OperatorObjectRow[]>(
    () => [
      {
        checkedAt: activeProfile?.updated_at ? formatDateTime(activeProfile.updated_at) : currentView.checkedAt,
        details: labValues,
        freshness: "Operator config",
        id: "active-setup",
        nextAction: "Open Edit Config if any saved lab value is wrong.",
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

  return (
    <OperatorPage title="Overview">
      <PageStatusHeader
        description="A clean operator view of readiness, blockers, and the next safe action."
        helper="Use this page first. Detailed current-state proof stays collapsed unless you need it."
        icon={<Gauge size={26} />}
        runConfig={{
          label: "Refresh Access",
          onRun: async () => {
            await load();
            return "Refresh Access: current view refreshed.";
          }
        }}
        settingsValues={tabSettingsValues("overview", activeProfile)}
        tabId="overview"
        title="Overview"
      />
      <Feedback loading={loading && !workspaceRows.length} error={error || labProfileError} />
      {labProfileLoading && <Feedback loading />}
      <OverviewReferencePanel
        accessRows={accessRows}
        currentView={currentView}
        firmwareSummaries={firmwareSummaries}
        inventoryRows={inventoryRows}
        workspaceRows={workspaceRows}
      />
      <AdvancedDrawer title="Advanced proof" summary={noProofText}>
        <OperatorWorkspace currentView={currentView} rows={workspaceRows} compact />
        <InventoryTable rows={inventoryRows} />
        <ValidationProofList items={validation?.validation_items ?? []} proofLinks={validation?.proof_links.length ?? 0} />
        <ConfigValueList
          values={[
            { label: "Runtime mode", value: displayStatus(runtimeStatus(health ?? null)) },
            { label: "Build verification", value: displayStatus(buildVerification?.status ?? "not_checked") },
            { label: "Validation rows", value: String(validation?.validation_items.length ?? 0) }
          ]}
        />
      </AdvancedDrawer>
    </OperatorPage>
  );
}

export function OperatorNetworkPage({ labProfileState }: OperatorPageProps) {
  const activeProfile = activeLabProfile(labProfileState);
  const address = activeAddressPlan(activeProfile);
  const features = activeProfile?.features ?? null;
  const global = activeProfile?.global_settings ?? null;
  const [actions, setActions] = useState<WorkflowAction[]>([]);
  const [ciscoReadiness, setCiscoReadiness] = useState<ProviderProbeResult | null>(null);
  const [firmwareSummaries, setFirmwareSummaries] = useState<FirmwareSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    setLoading(true);
    try {
      const [nextActions, nextCisco, nextFirmware] = await Promise.all([
        safeApi(api.workflowActions, [] as WorkflowAction[]),
        safeApi(api.ciscoSetupReadiness, null),
        safeApi(api.firmwareSummary, [] as FirmwareSummary[])
      ]);
      setActions(Array.isArray(nextActions) ? nextActions : []);
      setCiscoReadiness(nextCisco as ProviderProbeResult | null);
      setFirmwareSummaries(Array.isArray(nextFirmware) ? nextFirmware : []);
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
        nextAction: humanize(asString(ciscoReadiness?.next_safe_action) || "Run Test Switch."),
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
        nextAction: "Open Settings if the console path is wrong.",
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
        nextAction: "Run Test Switch after fixing connectivity or credentials.",
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
        nextAction: "Open Settings or Edit Config to change this value.",
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

  return (
    <OperatorPage title="Network">
      <PageStatusHeader
        description="Use these buttons to test or change this part of the lab."
        helper="Cisco access, VLAN, subnet, gateway, switch access, DNS, NTP, SNMP, and MTU are grouped here."
        icon={<Route size={26} />}
        nextAction={humanize(asString(ciscoReadiness?.next_safe_action) || "Test Cisco access, then save switch config when ready.")}
        runConfig={{
          actionIds: ["cisco.setup-readiness", "cisco.validate-ssh-scp", "cisco.privilege-check"],
          actions,
          label: "Test Switch",
          onReload: load
        }}
        settingsValues={tabSettingsValues("network", activeProfile)}
        status={networkStatus}
        tabId="network"
        title="Network"
      />
      <Feedback loading={loading && !ciscoReadiness} error={error} />
      <NetworkReferencePanel
        address={address}
        ciscoReadiness={ciscoReadiness}
        consoleState={consoleState}
        currentView={currentView}
        features={features}
        firmwareSummaries={firmwareSummaries}
        global={global}
        networkRows={networkRows}
      />
      <AdvancedDrawer title="Network proof" summary={noProofText}>
        <OperatorWorkspace currentView={currentView} rows={networkRows} compact />
        <ConfigValueList
          values={[
            { label: "Firmware", value: firmwareVersion(firmwareSummaries, "cisco") },
            { label: "Prompt", value: displayValue(asString(objectValue(ciscoReadiness?.real_lab_run).prompt_state)) },
            { label: "Warnings", value: String(stringArray(ciscoReadiness?.warnings).length) }
          ]}
        />
      </AdvancedDrawer>
    </OperatorPage>
  );
}

export function OperatorServerPage({ labProfileState }: OperatorPageProps) {
  const activeProfile = activeLabProfile(labProfileState);
  const address = activeAddressPlan(activeProfile);
  const [actions, setActions] = useState<WorkflowAction[]>([]);
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [firmwareSummaries, setFirmwareSummaries] = useState<FirmwareSummary[]>([]);
  const [raidPlan, setRaidPlan] = useState<ProviderProbeResult | null>(null);
  const [esxiReadiness, setEsxiReadiness] = useState<ProviderProbeResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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
        nextAction: "Run Test Server before inventory or firmware work.",
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
        nextAction: humanize(asString(esxiReadiness?.next_safe_action) || "Run Test Server."),
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

  return (
    <OperatorPage title="Server">
      <PageStatusHeader
        description="Use these buttons to test or change this part of the lab."
        helper="iLO, DL360 server, RAID layout, and ESXi access are grouped here."
        icon={<Server size={26} />}
        nextAction={humanize(asString(esxiReadiness?.next_safe_action) || "Test iLO and ESXi, then validate RAID when storage layout is ready.")}
        runConfig={{
          actionIds: ["ilo.reachability", "ilo.auth", "ilo.inventory", "esxi.management-validation", "raid.validate"],
          actions,
          label: "Test Server",
          onReload: load
        }}
        settingsValues={tabSettingsValues("server", activeProfile)}
        status={strongestStatus([iloStatus, esxiStatus, raidStatus])}
        tabId="server"
        title="Server"
      />
      <Feedback loading={loading && !providers.length} error={error} />
      <OperatorWorkspace currentView={currentView} rows={serverRows} />
      <AdvancedDrawer title="Server proof" summary={noProofText}>
        <ConfigValueList
          values={[
            { label: "RAID warnings", value: String(stringArray(raidPlan?.warnings).length) },
            { label: "RAID controller model", value: raidControllerModels(raidPlan) },
            { label: "ESXi blockers", value: String(stringArray(esxiReadiness?.blockers).length) },
            { label: "Smart Array firmware", value: firmwareVersion(firmwareSummaries, "raid") }
          ]}
        />
      </AdvancedDrawer>
    </OperatorPage>
  );
}

export function OperatorStoragePage({ labProfileState }: OperatorPageProps) {
  const activeProfile = activeLabProfile(labProfileState);
  const address = activeAddressPlan(activeProfile);
  const [actions, setActions] = useState<WorkflowAction[]>([]);
  const [netappPlan, setNetappPlan] = useState<ProviderProbeResult | null>(null);
  const [consoleReadiness, setConsoleReadiness] = useState<ProviderProbeResult | null>(null);
  const [nfsReadiness, setNfsReadiness] = useState<ProviderProbeResult | null>(null);
  const [vcenterNetapp, setVcenterNetapp] = useState<ProviderProbeResult | null>(null);
  const [firmwareSummaries, setFirmwareSummaries] = useState<FirmwareSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    setLoading(true);
    try {
      const [nextActions, nextPlan, nextConsole, nextNfs, nextVcenter, nextFirmware] = await Promise.all([
        safeApi(api.workflowActions, [] as WorkflowAction[]),
        safeApi(api.netappPlanPreview, null),
        safeApi(api.netappConsoleReadiness, null),
        safeApi(api.netappNfsVcenterReadiness, null),
        safeApi(api.vcenterNetappReadiness, null),
        safeApi(api.firmwareSummary, [] as FirmwareSummary[])
      ]);
      setActions(Array.isArray(nextActions) ? nextActions : []);
      setNetappPlan(nextPlan as ProviderProbeResult | null);
      setConsoleReadiness(nextConsole as ProviderProbeResult | null);
      setNfsReadiness(nextNfs);
      setVcenterNetapp(nextVcenter);
      setFirmwareSummaries(Array.isArray(nextFirmware) ? nextFirmware : []);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const plannedNfs = objectValue(nfsReadiness?.planned_nfs);
  const storageStatus = asString(vcenterNetapp?.status) || asString(nfsReadiness?.status) || asString(netappPlan?.status) || "not_checked";
  const currentView = storageCurrentView({ address, consoleReadiness, netappPlan, nfsReadiness, vcenterNetapp });
  const storageRows = useMemo<OperatorObjectRow[]>(
    () => [
      {
        checkedAt: currentView.checkedAt,
        details: [
          { label: "Cluster management", value: displayAddress(address.netapp_cluster_mgmt), source: "Saved setup" },
          { label: "SVM management", value: displayAddress(address.netapp_svm_mgmt), source: "Saved setup" },
          { label: "ONTAP version", value: firmwareVersion(firmwareSummaries, "netapp") }
        ],
        freshness: currentView.freshness,
        id: "cluster",
        nextAction: humanize(asString(netappPlan?.next_safe_action) || "Run Test NetApp."),
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
        nextAction: "Open Settings if the console path is wrong.",
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
    [address.netapp_cluster_mgmt, address.netapp_nfs_lifs, address.netapp_svm_mgmt, consoleReadiness, currentView, firmwareSummaries, netappPlan, nfsReadiness, plannedNfs, storageStatus, vcenterNetapp]
  );

  return (
    <OperatorPage title="Storage">
      <PageStatusHeader
        description="Use these buttons to test or change this part of the lab."
        helper="NetApp access, ONTAP, NFS LIFs, volume, export policy, and datastore readiness are grouped here."
        icon={<HardDrive size={26} />}
        nextAction={humanize(asString(vcenterNetapp?.next_safe_action) || asString(nfsReadiness?.next_safe_action) || "Validate NFS, then mount the datastore when guarded apply is ready.")}
        runConfig={{
          actionIds: ["netapp.live-state", "netapp.validate-setup", "netapp.setup-preview", "netapp.nfs-setup-validate"],
          actions,
          label: "Test NetApp",
          onReload: load
        }}
        settingsValues={tabSettingsValues("storage", activeProfile)}
        status={storageStatus}
        tabId="storage"
        title="Storage"
      />
      <Feedback loading={loading && !netappPlan} error={error} />
      <OperatorWorkspace currentView={currentView} rows={storageRows} />
      <AdvancedDrawer title="Storage proof" summary={noProofText}>
        <ConfigValueList
          values={[
            { label: "NetApp blockers", value: String(stringArray(netappPlan?.blockers).length) },
            { label: "NFS warnings", value: String(stringArray(nfsReadiness?.warnings).length) },
            { label: "vCenter-NetApp source", value: sourceLabel(vcenterNetapp) }
          ]}
        />
      </AdvancedDrawer>
    </OperatorPage>
  );
}

export function OperatorVirtualizationPage({ labProfileState }: OperatorPageProps) {
  const activeProfile = activeLabProfile(labProfileState);
  const address = activeAddressPlan(activeProfile);
  const [actions, setActions] = useState<WorkflowAction[]>([]);
  const [vcenterNetapp, setVcenterNetapp] = useState<ProviderProbeResult | null>(null);
  const [installReadiness, setInstallReadiness] = useState<ProviderProbeResult | null>(null);
  const [postAttach, setPostAttach] = useState<ProviderProbeResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    setLoading(true);
    try {
      const [nextActions, nextVcenterNetapp, nextInstall, nextPostAttach] = await Promise.all([
        safeApi(api.workflowActions, [] as WorkflowAction[]),
        safeApi(api.vcenterNetappReadiness, null),
        safeApi(api.vcenterInstallReadiness, null),
        safeApi(api.vcenterPostAttachValidation, null)
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
  }, []);

  const virtualStatus = asString(postAttach?.status) || asString(vcenterNetapp?.status) || asString(installReadiness?.status) || "not_checked";
  const target = vcenterTarget(vcenterNetapp || installReadiness, activeProfile);
  const postChecks = objectValue(postAttach?.checks);
  const currentView = virtualizationCurrentView({ activeProfile, installReadiness, postAttach, vcenterNetapp });
  const virtualizationRows = useMemo<OperatorObjectRow[]>(
    () => [
      {
        checkedAt: currentView.checkedAt,
        details: [
          { label: "Target", value: target },
          { label: "Credentials", value: credentialSummary(vcenterNetapp) },
          { label: "Source", value: sourceLabel(vcenterNetapp || installReadiness) }
        ],
        freshness: currentView.freshness,
        id: "vcenter",
        nextAction: humanize(asString(vcenterNetapp?.next_safe_action) || "Run Test vCenter."),
        source: sourceLabel(vcenterNetapp || installReadiness),
        status: virtualStatus,
        summary: asString(vcenterNetapp?.message) || asString(installReadiness?.message) || "vCenter endpoint and readiness.",
        target,
        title: "vCenter",
        type: "Control plane"
      },
      {
        checkedAt: currentView.checkedAt,
        details: [
          { label: "ESXi target", value: displayAddress(address.esxi_management), source: "Saved setup" },
          { label: "Attach state", value: attachStateLabel(vcenterNetapp, postAttach), status: virtualStatus }
        ],
        freshness: currentView.freshness,
        id: "esxi-attach",
        nextAction: "Validate attach state after ESXi or vCenter changes.",
        source: currentView.source,
        status: virtualStatus,
        summary: "ESXi attachment and host visibility through vCenter.",
        target: displayAddress(address.esxi_management),
        title: "ESXi Attach",
        type: "Inventory"
      },
      {
        checkedAt: currentView.checkedAt,
        details: [
          { label: "Datastore", value: datastoreName(vcenterNetapp), status: datastoreVisibleStatus(vcenterNetapp || postAttach) },
          { label: "Visibility", value: visibilityLabel(postChecks.netapp_datastore_visible ?? objectValue(vcenterNetapp?.checks).datastore_mounted) }
        ],
        freshness: currentView.freshness,
        id: "datastore",
        nextAction: "Validate datastore visibility after storage changes.",
        source: currentView.source,
        status: datastoreVisibleStatus(vcenterNetapp || postAttach),
        summary: "NetApp datastore visibility through vCenter.",
        target: datastoreName(vcenterNetapp),
        title: "Datastore",
        type: "Storage"
      },
      {
        checkedAt: currentView.checkedAt,
        details: [{ label: "VM inventory", value: visibilityLabel(postChecks.vm_inventory_visible), status: visibilityStatus(postChecks.vm_inventory_visible) }],
        freshness: currentView.freshness,
        id: "vm-inventory",
        nextAction: "Validate inventory after datastore and vCenter access are ready.",
        source: currentView.source,
        status: visibilityStatus(postChecks.vm_inventory_visible),
        summary: "VM inventory visibility for deployment validation.",
        target: "vCenter inventory",
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
    ],
    [activeProfile, address.esxi_management, currentView, installReadiness, postAttach, postChecks, target, vcenterNetapp, virtualStatus]
  );

  return (
    <OperatorPage title="Virtualization">
      <PageStatusHeader
        description="Use these buttons to test or change this part of the lab."
        helper="vCenter, ESXi attach, datastore visibility, VM inventory, and OVF deployment are grouped here."
        icon={<Layers size={26} />}
        nextAction={humanize(asString(vcenterNetapp?.next_safe_action) || "Test vCenter, then validate datastore and VM inventory visibility.")}
        runConfig={{
          actionIds: ["vcenter-netapp.readiness", "vcenter.install-readiness", "vcenter.post-attach-validation", "esxi.vm-deploy-validate"],
          actions,
          label: "Test vCenter",
          onReload: load
        }}
        settingsValues={tabSettingsValues("virtualization", activeProfile)}
        status={virtualStatus}
        tabId="virtualization"
        title="Virtualization"
      />
      <Feedback loading={loading && !vcenterNetapp} error={error} />
      <OperatorWorkspace currentView={currentView} rows={virtualizationRows} />
      <AdvancedDrawer title="Virtualization proof" summary={noProofText}>
        <ConfigValueList
          values={[
            { label: "vCenter source", value: sourceLabel(vcenterNetapp) },
            { label: "Install blockers", value: String(stringArray(installReadiness?.blockers).length) },
            { label: "Post-attach warnings", value: String(stringArray(postAttach?.warnings).length) }
          ]}
        />
      </AdvancedDrawer>
    </OperatorPage>
  );
}

export function OperatorFirmwareUpgradesPage({ labProfileState }: OperatorPageProps) {
  const activeProfile = activeLabProfile(labProfileState);
  const [actions, setActions] = useState<WorkflowAction[]>([]);
  const [firmwareSummaries, setFirmwareSummaries] = useState<FirmwareSummary[]>([]);
  const [media, setMedia] = useState<MediaInventory | null>(null);
  const [compliance, setCompliance] = useState<ProviderProbeResult | null>(null);
  const [fileSelections, setFileSelections] = useState<FirmwareFileSelections | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [savingSelection, setSavingSelection] = useState(false);
  const [error, setError] = useState("");
  const [selectionError, setSelectionError] = useState("");

  async function load() {
    setError("");
    setLoading(true);
    try {
      const [nextActions, nextSummaries, nextMedia, nextCompliance, nextSelections] = await Promise.all([
        safeApi(api.workflowActions, [] as WorkflowAction[]),
        safeApi(api.firmwareSummary, [] as FirmwareSummary[]),
        safeApi(api.mediaInventory, null),
        safeApi(api.firmwareCompliance, null),
        safeApi(api.firmwareFileSelections, null)
      ]);
      setActions(Array.isArray(nextActions) ? nextActions : []);
      setFirmwareSummaries(Array.isArray(nextSummaries) ? nextSummaries : []);
      setMedia(nextMedia);
      setCompliance(nextCompliance);
      setFileSelections(nextSelections);
      setSelectedFiles(nextSelections?.selected_files ?? {});
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function saveFileSelection(componentId: string, fileName: string) {
    const nextSelections = nextFirmwareFileSelections(selectedFiles, componentId, fileName);
    setSelectedFiles(nextSelections);
    setSelectionError("");
    setSavingSelection(true);
    try {
      const saved = await api.saveFirmwareFileSelections({ selected_files: nextSelections });
      setFileSelections(saved);
      setSelectedFiles(saved.selected_files);
    } catch (err) {
      setSelectionError(errorMessage(err));
    } finally {
      setSavingSelection(false);
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
  const files = firmwareFilesInfo(media, compliance);
  const currentView = firmwareCurrentView({ compliance, files, rows });
  const firmwareWorkspaceRows = useMemo<OperatorObjectRow[]>(
    () => rows.map((row) => ({
      checkedAt: currentView.checkedAt,
      details: [
        { label: "Current", value: row.current },
        { label: "Target", value: row.target },
        { label: "Selected file", value: row.selectedFileName || "No file selected", source: selectionSourceLabel(row.selectionSource) },
        { label: "Candidate files", value: String(row.candidateFiles.length) }
      ],
      freshness: currentView.freshness,
      id: `firmware-${row.componentId}`,
      nextAction: row.action,
      source: "Firmware inventory",
      status: row.pathStatus,
      summary: `${row.equipment} / ${row.component}`,
      target: row.target,
      title: row.equipment,
      type: row.component
    })),
    [currentView.checkedAt, currentView.freshness, rows]
  );

  return (
    <OperatorPage title="Firmware Upgrades">
      <PageStatusHeader
        description="Firmware files are read from the local media folder."
        helper="Choose the file for each device. Upgrade stays gated until the path is validated."
        icon={<ShieldCheck size={26} />}
        runConfig={{
          actionIds: ["firmware.inventory", "firmware.compliance-check"],
          actions,
          label: "Scan Firmware",
          onReload: load
        }}
        settingsValues={tabSettingsValues("firmware", activeProfile)}
        status={firmwareStatus}
        tabId="firmware"
        title="Firmware Upgrades"
      />
      <Feedback loading={loading && !firmwareSummaries.length} error={error} />
      <OperatorWorkspace
        currentView={currentView}
        rows={firmwareWorkspaceRows}
        renderDetailExtra={(selected) => {
          const row = rows.find((candidate) => `firmware-${candidate.componentId}` === selected.id);
          if (!row) return null;
          return (
            <div className="firmware-detail-control">
              <Field label="Selected firmware file">
                <select
                  aria-label={`${row.equipment} ${row.component} firmware file`}
                  onChange={(event) => void saveFileSelection(row.componentId, event.target.value)}
                  value={selectedFiles[row.componentId] ?? row.selectedFileName}
                >
                  <option value="">No file selected</option>
                  {selectedFiles[row.componentId] && !row.candidateFiles.some((candidate) => candidate.file_name === selectedFiles[row.componentId]) ? (
                    <option value={selectedFiles[row.componentId]}>{selectedFiles[row.componentId]}</option>
                  ) : null}
                  {row.candidateFiles.map((candidate) => (
                    <option key={`${row.componentId}-${candidate.file_name}-${candidate.file_path ?? ""}`} value={candidate.file_name}>
                      {candidate.file_name}
                    </option>
                  ))}
                </select>
              </Field>
              <p className="operator-muted">
                {row.selectedFileName || "No file selected"} / {selectionSourceLabel(row.selectionSource)}
              </p>
            </div>
          );
        }}
      />
      <AdditionalTabActions
        actions={actions}
        buttons={[
          { actionIds: ["firmware.upgrade-apply-placeholder", "netapp.ontap-upgrade-apply"], allowBlockedRun: true, kind: "apply", label: "Upgrade" }
        ]}
        description="Upgrade remains a protected placeholder until guarded firmware apply is explicitly enabled."
        onReload={load}
        title="Protected firmware action"
      />
      <FirmwareFilesPanel
        directory="/home/administrator/infra-config-portal/artifacts/Media"
        lastScanned={files.lastScanned}
        loading={loading}
        onRescan={() => void load()}
        packageCount={files.packageCount}
        selectionStatus={selectionStatusLabel(fileSelections, savingSelection)}
      />
      <Feedback loading={false} error={selectionError} />
      <AdvancedDrawer title="Firmware proof" summary={noProofText}>
        <ValidationProofList
          items={[]}
          proofLinks={firmwareSummaries.reduce((count, summary) => count + summary.evidence_artifacts.length, 0)}
        />
      </AdvancedDrawer>
    </OperatorPage>
  );
}

export function OperatorValidationPage({ labProfileState }: OperatorPageProps) {
  const activeProfile = activeLabProfile(labProfileState);
  const [actions, setActions] = useState<WorkflowAction[]>([]);
  const [validation, setValidation] = useState<LabValidationSummary | null>(null);
  const [buildVerification, setBuildVerification] = useState<ProviderProbeResult | null>(null);
  const [vcenterNetapp, setVcenterNetapp] = useState<ProviderProbeResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    setLoading(true);
    try {
      const [nextActions, nextValidation, nextBuildVerification, nextVcenterNetapp] = await Promise.all([
        safeApi(api.workflowActions, [] as WorkflowAction[]),
        safeApi(api.labValidation, null),
        safeApi(api.buildVerification, null),
        safeApi(api.vcenterNetappReadiness, null)
      ]);
      setActions(Array.isArray(nextActions) ? nextActions : []);
      setValidation(nextValidation);
      setBuildVerification(nextBuildVerification);
      setVcenterNetapp(nextVcenterNetapp);
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
          { label: "Handoff", value: validation?.handoff_report ? "Ready to generate" : "Not generated", status: validation?.handoff_report ? "ready" : "not_checked" }
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

  return (
    <OperatorPage title="Validation">
      <PageStatusHeader
        description="Use these buttons to test or change this part of the lab."
        helper="Golden State means expected working lab state. Advanced proof is hidden unless you need it."
        icon={<CheckCircle2 size={26} />}
        nextAction={humanize(validation?.next_action || "Run validation, then generate the handoff.")}
        runConfig={{
          actionIds: ["build-verification.run-full", "full-lab.validation", "lab-validation.summary"],
          actions,
          label: "Validation",
          onReload: load
        }}
        settingsValues={tabSettingsValues("validation", activeProfile)}
        status={validation?.overall_status ?? "not_checked"}
        tabId="validation"
        title="Validation"
      />
      <Feedback loading={loading && !validation} error={error} />
      <OperatorWorkspace currentView={currentView} rows={validationRows} />
      <AdditionalTabActions
        actions={actions}
        buttons={[
          { actionIds: ["full-lab.handoff-report"], label: "Generate Handoff", onClick: async () => { await api.labValidationHandoff(); } }
        ]}
        description="Use this after validation has current proof links."
        onReload={load}
        title="Handoff"
      />
      <AdvancedDrawer title="Validation proof" summary={noProofText}>
        <ValidationProofList items={validation?.validation_items ?? []} proofLinks={validation?.proof_links.length ?? 0} />
        <ConfigValueList
          values={[
            { label: "Source", value: sourceLabel(validation) },
            { label: "Warnings", value: String(validation?.warnings.length ?? 0) },
            { label: "Raw proof links", value: String(validation?.proof_links.length ?? 0) }
          ]}
        />
      </AdvancedDrawer>
    </OperatorPage>
  );
}

export function OperatorSettingsPage({
  health,
  labProfileError = "",
  labProfileLoading = false,
  labProfileState,
  onReloadLabProfile
}: OperatorPageProps) {
  const activeProfile = activeLabProfile(labProfileState);
  const address = activeAddressPlan(activeProfile);
  const features = activeProfile?.features ?? null;
  const global = activeProfile?.global_settings ?? null;
  const [vcenterNetapp, setVcenterNetapp] = useState<ProviderProbeResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    setLoading(true);
    try {
      const nextVcenterNetapp = await safeApi(api.vcenterNetappReadiness, null);
      setVcenterNetapp(nextVcenterNetapp);
      if (onReloadLabProfile) {
        await onReloadLabProfile();
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const currentView = settingsCurrentView({ activeProfile, health: health ?? null, labProfileState, vcenterNetapp });
  const settingsRows = useMemo<OperatorObjectRow[]>(
    () => [
      {
        checkedAt: currentView.checkedAt,
        details: [
          { label: "Subnet", value: displayAddress(address.subnet), source: "Saved setup" },
          { label: "Offsets", value: offsetSummary(address), source: "Saved setup" },
          { label: "iLO", value: displayAddress(address.ilo), source: "Saved setup" },
          { label: "Cisco", value: displayAddress(address.cisco_management), source: "Saved setup" },
          { label: "ESXi", value: displayAddress(address.esxi_management), source: "Saved setup" },
          { label: "NetApp", value: displayAddress(address.netapp_cluster_mgmt), source: "Saved setup" },
          { label: "vCenter", value: vcenterTarget(vcenterNetapp, activeProfile), source: "Saved or discovered" }
        ],
        freshness: currentView.freshness,
        id: "active-setup",
        nextAction: "Open Edit Config if the lab values are wrong.",
        source: currentView.source,
        status: activeProfile ? "ready" : "not_configured_yet",
        summary: activeProfile?.name ?? "No active setup.",
        target: displayAddress(address.subnet),
        title: "Active Lab Setup",
        type: "Context"
      },
      {
        checkedAt: currentView.checkedAt,
        details: [
          { label: "Runtime mode", value: displayStatus(runtimeStatus(health ?? null)), status: runtimeStatus(health ?? null) },
          { label: "Provider mode", value: displayStatus(health?.provider_mode ?? "not_checked"), status: health?.provider_mode ?? "not_checked" }
        ],
        freshness: currentView.freshness,
        id: "runtime",
        nextAction: "Run Refresh Settings after runtime changes.",
        source: "Backend health",
        status: runtimeStatus(health ?? null),
        summary: "Runtime and provider mode currently used by the app.",
        target: displayStatus(runtimeStatus(health ?? null)),
        title: "Runtime Mode",
        type: "Runtime"
      },
      {
        checkedAt: currentView.checkedAt,
        details: [
          { label: "Cisco", value: "Configured or missing", status: "not_checked" },
          { label: "iLO", value: "Configured or missing", status: "not_checked" },
          { label: "ESXi", value: "Configured or missing", status: "not_checked" },
          { label: "NetApp", value: netappCredentialStatus(vcenterNetapp), status: netappCredentialStatus(vcenterNetapp) === "Configured" ? "ready" : "not_checked" },
          { label: "vCenter", value: vcenterCredentialStatus(vcenterNetapp), status: vcenterCredentialStatus(vcenterNetapp) === "Configured" ? "ready" : "not_checked" }
        ],
        freshness: currentView.freshness,
        id: "credentials",
        nextAction: "Update local secret files outside the UI if credentials are missing.",
        source: "Configured or missing only",
        status: strongestStatus([
          netappCredentialStatus(vcenterNetapp) === "Configured" ? "ready" : "not_checked",
          vcenterCredentialStatus(vcenterNetapp) === "Configured" ? "ready" : "not_checked"
        ]),
        summary: "Secret values stay hidden; only configured or missing state is shown.",
        target: "Secret-safe status",
        title: "Credentials",
        type: "Safety"
      },
      {
        checkedAt: currentView.checkedAt,
        details: [
          { label: "DNS / NTP / SNMP", value: featureToggleSummary(features), source: "Saved setup" },
          { label: "Gateway", value: displayAddress(global?.gateway ?? activeProfile?.gateway), source: "Saved setup" },
          { label: "Storage protocol", value: storageProtocolLabel(features), source: "Saved setup" }
        ],
        freshness: "Operator config",
        id: "features",
        nextAction: "Open Edit Config to change feature toggles.",
        source: "Saved setup",
        status: activeProfile ? "ready" : "not_configured_yet",
        summary: "Network defaults and feature toggles used by runs.",
        target: featureToggleSummary(features),
        title: "Feature Toggles",
        type: "Config"
      },
      {
        checkedAt: currentView.checkedAt,
        details: [{ label: "Console mappings", value: "Refresh consoles to discover current ports", status: "not_checked" }],
        freshness: currentView.freshness,
        id: "console-mappings",
        nextAction: "Run Refresh Settings after plugging in or changing serial adapters.",
        source: "Runtime discovery",
        status: "not_checked",
        summary: "Console paths used by Cisco and NetApp workflows.",
        target: "Console mappings",
        title: "Console Mappings",
        type: "Access"
      }
    ],
    [activeProfile, address, currentView, features, global, health, vcenterNetapp]
  );

  return (
    <OperatorPage title="Settings">
      <PageStatusHeader
        description="Use these buttons to test or change this part of the lab."
        helper="Active lab setup values, IP layout, console mappings, credential status, and feature toggles are kept here."
        icon={<Settings size={26} />}
        nextAction={labProfileState?.next_safe_action ?? "Review the active lab setup before running validation."}
        runConfig={{
          label: "Refresh Settings",
          onRun: async () => {
            await load();
            return "Refresh Settings: active lab setup and current status refreshed.";
          }
        }}
        settingsValues={tabSettingsValues("settings", activeProfile)}
        status={activeProfile ? "ready" : "not_configured_yet"}
        tabId="settings"
        title="Settings"
      />
      <Feedback loading={loading && !activeProfile} error={error || labProfileError} />
      <OperatorWorkspace currentView={currentView} rows={settingsRows} />
      <AdvancedDrawer title="Settings proof" summary={noProofText}>
        <ConfigValueList
          values={[
            { label: "Feature toggles", value: featureToggleSummary(features) },
            { label: "Storage protocol", value: displayValue(features?.storage_protocol) },
            { label: "Runtime mode", value: displayStatus(health?.provider_mode ?? "not_checked") }
          ]}
        />
      </AdvancedDrawer>
    </OperatorPage>
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
  settingsValues,
  status,
  tabId,
  title
}: {
  description: string;
  helper: string;
  icon: ReactNode;
  nextAction?: string;
  runConfig: TabRunConfig;
  settingsValues: ConfigValue[];
  status?: string;
  tabId: OperatorTabId;
  title: string;
}) {
  const {
    closeSettings,
    openSettings,
    runStatus,
    setRunStatus,
    settingsOpenFor,
    tabSettings,
    updateTabAdvancedSetting,
    updateTabSettings
  } = useOperatorTabState();
  const byId = useMemo(() => new Map((runConfig.actions ?? []).map((action) => [action.action_id, action])), [runConfig.actions]);
  const action = firstRunnableAction(byId, runConfig.actionIds ?? [], runConfig);
  const disabledReason = runConfig.disabledReason || (runConfig.onRun ? "" : disabledReasonForRunConfig(runConfig, action));
  const tabRunStatus = runStatus[tabId] ?? idleRunStatus;
  const running = tabRunStatus.state === "running";
  const drawerOpen = settingsOpenFor === tabId;
  const settings = tabSettings[tabId] ?? defaultTabSettings(tabId);

  async function runActiveTab() {
    if (disabledReason || running) return;
    setRunStatus(tabId, {
      actionId: action?.action_id,
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
      } else {
        // TODO: Replace this safe placeholder once the backend exposes this tab action.
        message = `${runConfig.label}: no backend action is registered yet.`;
      }
      if (runConfig.onReload) {
        await runConfig.onReload();
      }
      setRunStatus(tabId, {
        actionId: action?.action_id,
        message: message || `${runConfig.label} completed.`,
        state: "success"
      });
    } catch (err) {
      setRunStatus(tabId, {
        actionId: action?.action_id,
        message: errorMessage(err),
        state: "error"
      });
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
              aria-expanded={drawerOpen}
              aria-controls={`settings-drawer-${tabId}`}
              onClick={() => openSettings(tabId)}
              type="button"
            >
              <SlidersHorizontal size={16} />
              Settings
            </button>
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
      {drawerOpen && (
        <TabSettingsDrawer
          onAdvancedChange={(key, value) => updateTabAdvancedSetting(tabId, key, value)}
          onChange={(patch) => updateTabSettings(tabId, patch)}
          onClose={closeSettings}
          settings={settings}
          tabId={tabId}
          values={settingsValues}
        />
      )}
      {tabRunStatus.message && (
        <p className={`operator-action-message ${tabRunStatus.state === "error" ? "error" : tabRunStatus.state}`}>
          {tabRunStatus.message}
        </p>
      )}
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
            <span>{rows.length} objects</span>
            <strong>{rows.filter((row) => statusTone(row.status) === "ready").length} ready</strong>
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
            <CardFooter>
              <ActionLink to={provider.to}>{provider.actionLabel}</ActionLink>
            </CardFooter>
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
          <CardFooter>
            <ActionLink to="/validation">Open validation</ActionLink>
          </CardFooter>
        </Card>
      </div>
    </section>
  );
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
  ciscoReadiness,
  consoleState,
  currentView,
  features,
  firmwareSummaries,
  global,
  networkRows
}: {
  address: LabAddressPlan;
  ciscoReadiness: ProviderProbeResult | null;
  consoleState: Record<string, unknown>;
  currentView: CurrentViewModel;
  features: LabProfileFeatures | null;
  firmwareSummaries: FirmwareSummary[];
  global: LabProfile["global_settings"] | null;
  networkRows: OperatorObjectRow[];
}) {
  const counts = workspaceCounts(networkRows);
  const networkStatus = asString(ciscoReadiness?.status) || (address.cisco_management ? "ready" : "not_configured_yet");
  const managementConfigured = asBoolean(ciscoReadiness?.management_configured);
  const consoleStatus = asString(consoleState.status) || "not_checked";
  const ciscoFirmware = firmwareVersion(firmwareSummaries, "cisco");
  const settingsRows = networkSettingsRows({ ciscoFirmware, features, global });
  const issues = networkIssues(currentView, ciscoReadiness);
  const nextSafeAction = humanize(asString(ciscoReadiness?.next_safe_action) || "Run Test Switch.");

  const providerCards = [
    {
      actionLabel: "Test switch",
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
      to: "/network",
      currentState: asString(ciscoReadiness?.message) || currentView.summary
    },
    {
      actionLabel: "Open settings",
      blockedBy: consoleStatus === "ready" ? "No console blocker loaded" : "Console path needs confirmation",
      facts: [
        ["Selected path", displayValue(asString(consoleState.selected_path))],
        ["Effective path", displayValue(asString(consoleState.effective_path))],
        ["Status", displayStatus(consoleStatus)]
      ],
      gap: "Open Settings if the console path is wrong.",
      name: "Console",
      role: "First contact",
      status: consoleStatus,
      targetState: displayValue(asString(consoleState.selected_path) || asString(consoleState.effective_path)),
      to: "/settings",
      currentState: displayStatus(consoleStatus)
    },
    {
      actionLabel: "Validate access",
      blockedBy: managementConfigured ? "No SSH blocker loaded" : "Management access has not been confirmed",
      facts: [
        ["SSH/SCP", boolStateLabel(managementConfigured)],
        ["Secrets", "Configured or missing only"],
        ["Target", displayAddress(address.cisco_management)]
      ],
      gap: "Run Test Switch after fixing connectivity or credentials.",
      name: "SSH / SCP",
      role: "Access guard",
      status: managementConfigured ? "ready" : "not_checked",
      targetState: displayAddress(address.cisco_management),
      to: "/network",
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
            <CardFooter>
              <ActionLink to={provider.to}>{provider.actionLabel}</ActionLink>
            </CardFooter>
          </Card>
        ))}
      </div>

      <section className="overview-safe-actions" aria-label="Next safe actions">
        <p className="operator-kicker">Next safe actions</p>
        <ul>
          <li>{nextSafeAction}</li>
          <li>Open Settings if the console path or saved network defaults are wrong.</li>
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
    overviewProviderCard("HPE iLO", "Server management", "/server", "View details", byAccessName, byInventoryName, byWorkspaceName, "hpe ilo", "ilo"),
    overviewProviderCard("Cisco Switch", "Network", "/network", "Bootstrap", byAccessName, byInventoryName, byWorkspaceName, "cisco switch", "cisco"),
    overviewProviderCard("NetApp ONTAP", "Storage", "/storage", "Setup wizard", byAccessName, byInventoryName, byWorkspaceName, "netapp ontap", "netapp")
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

function overviewFirmwareRows(firmwareSummaries: FirmwareSummary[], inventoryRows: InventoryRow[]) {
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
  return [
    ...currentView.blockers.map((message, index) => ({
      code: `BLOCKER_${index + 1}`,
      message: humanize(message),
      severity: "critical" as const
    })),
    ...currentView.warnings.map((message, index) => ({
      code: `WARNING_${index + 1}`,
      message: humanize(message),
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

function TabSettingsDrawer({
  onAdvancedChange,
  onChange,
  onClose,
  settings,
  tabId,
  values
}: {
  onAdvancedChange: (key: string, value: boolean | string) => void;
  onChange: (patch: Partial<OperatorTabSettingsState>) => void;
  onClose: () => void;
  settings: OperatorTabSettingsState;
  tabId: OperatorTabId;
  values: ConfigValue[];
}) {
  const advancedSettings = tabAdvancedSettings(tabId);
  return (
    <section className="tab-settings-drawer" id={`settings-drawer-${tabId}`} aria-label={`${tabTitle(tabId)} settings`}>
      <div className="tab-settings-drawer-head">
        <div>
          <p className="operator-kicker">Tab Settings</p>
          <h2>{tabTitle(tabId)} Settings</h2>
          <p className="operator-muted">These options apply to this tab's run flow. Saved lab values are edited in Edit Config.</p>
        </div>
        <button className="icon-button" aria-label="Close settings" onClick={onClose} type="button">
          <X size={18} />
        </button>
      </div>
      <div className="tab-settings-controls">
        <Field label="IP mode">
          <select
            aria-label="IP mode"
            onChange={(event) => onChange({ ipMode: event.target.value as IpMode })}
            value={settings.ipMode}
          >
            <option value="ipv4">IPv4</option>
            <option value="ipv6">IPv6</option>
            <option value="both">Both</option>
          </select>
        </Field>
        <Field label="SNMP version">
          <select
            aria-label="SNMP version"
            onChange={(event) => onChange({ snmpVersion: event.target.value as SnmpVersion })}
            value={settings.snmpVersion}
          >
            <option value="v2">SNMPv2</option>
            <option value="v3">SNMPv3</option>
          </select>
        </Field>
      </div>
      <div className="tab-settings-advanced">
        {advancedSettings.map((advanced) => (
          <label className="checkbox-line" key={advanced.key}>
            <input
              checked={Boolean(settings.advanced[advanced.key])}
              onChange={(event) => onAdvancedChange(advanced.key, event.target.checked)}
              type="checkbox"
            />
            <span>
              <strong>{advanced.label}</strong>
              <small>{advanced.description}</small>
            </span>
          </label>
        ))}
      </div>
      <ConfigValueList values={values} />
      <div className="tab-settings-foot">
        <p>
          TODO: persist per-tab IP mode and SNMP version once the workflow run API accepts tab-scoped settings. The current
          selections are safe UI state for this session.
        </p>
        <Link className="button-link" to="/config">
          <Settings size={16} />
          Open Edit Config
        </Link>
      </div>
    </section>
  );
}

function ConfigValueList({ values }: { values: ConfigValue[] }) {
  return (
    <dl className="config-value-list">
      {values.map((value) => (
        <div key={`${value.label}-${value.value}`}>
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
  description,
  onReload,
  title
}: {
  actions: WorkflowAction[];
  buttons: RunButtonDefinition[];
  description: string;
  onReload: () => Promise<void> | void;
  title: string;
}) {
  const [runState, setRunState] = useState<WorkflowRunState>(emptyRunState);
  const byId = useMemo(() => new Map(actions.map((action) => [action.action_id, action])), [actions]);

  async function runAction(action: WorkflowAction, request?: WorkflowActionRunRequest) {
    setRunState({ error: "", message: "", runningActionId: action.action_id });
    try {
      const result = await api.runWorkflowAction(action.action_id, request);
      setRunState({
        error: "",
        message: workflowRunMessage(action, result),
        runningActionId: ""
      });
      await onReload();
    } catch (err) {
      setRunState({ error: errorMessage(err), message: "", runningActionId: "" });
    }
  }

  return (
    <details className="operator-section additional-actions" aria-label={title}>
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
          const reason = button.disabledReason || (button.onClick ? "" : disabledReasonFor(button, action));
          const enabled = !reason && (Boolean(button.onClick) || Boolean(action));
          const running = action ? runState.runningActionId === action.action_id : false;
          return (
            <div className="run-button-wrap" key={button.label}>
              <button
                className={button.primary ? "primary" : ""}
                disabled={!enabled || running}
                onClick={() => {
                  if (button.onClick) {
                    void Promise.resolve(button.onClick()).then(() => onReload());
                    return;
                  }
                  if (action) {
                    void runAction(action);
                  }
                }}
                title={reason || button.label}
                type="button"
              >
                {button.icon ?? (reason ? <Ban size={16} /> : <Play size={16} />)}
                {running ? "Running" : button.label}
              </button>
              {reason && <span>{reason}</span>}
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
  candidateFiles: FirmwareFileCandidate[];
  component: string;
  componentId: string;
  current: string;
  equipment: string;
  pathStatus: string;
  selectedFileName: string;
  selectionSource: string;
  target: string;
};

function FirmwareFilesPanel({
  directory,
  lastScanned,
  loading,
  onRescan,
  packageCount,
  selectionStatus
}: {
  directory: string;
  lastScanned: string;
  loading: boolean;
  onRescan: () => void;
  packageCount: number;
  selectionStatus: string;
}) {
  return (
    <section className="operator-section firmware-files-panel" aria-label="Firmware Files">
      <div className="operator-section-head">
        <div>
          <p className="operator-kicker">Firmware Files</p>
          <h2>Firmware Files</h2>
          <p className="operator-muted">Firmware files are read from this folder. Use the HPE Service Pack for HPE iLO, BIOS, and Smart Array planning, and pick a different file if the app chose the wrong one.</p>
        </div>
      </div>
      <ConfigValueList
        values={[
          { label: "Directory", value: directory, source: "Local folder" },
          { label: "Last scanned", value: lastScanned },
          { label: "Package count", value: String(packageCount) },
          { label: "Selections", value: selectionStatus, source: "Local runtime" }
        ]}
      />
      <div className="page-run-buttons">
        <button disabled={loading} onClick={onRescan} type="button">
          <RefreshCw size={16} />
          Rescan Files
        </button>
        <Link className="button-link" to="/media">
          <HardDrive size={16} />
          Open Media Inventory
        </Link>
      </div>
    </section>
  );
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

function disabledReasonFor(button: RunButtonDefinition, action: WorkflowAction | null): string {
  if (button.kind === "custom" && !button.onClick) {
    return button.disabledReason || "This action is not ready yet.";
  }
  if (!action) {
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
  const detail = result.status === "blocked"
    ? result.blockers[0] || result.next_action || result.summary || displayStatus(result.status)
    : result.summary || result.next_action || displayStatus(result.status);
  return `${humanWorkflowActionLabel(action)}: ${humanize(detail)}`;
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
      candidateFiles,
      component: firmwareComponentLabel(path),
      componentId: path.component_id,
      current: displayValue(path.current_version),
      equipment: path.equipment_label || path.device_label || summary?.label || "Equipment",
      pathStatus: simpleFirmwareStatus(path, selectedFileName),
      selectedFileName,
      selectionSource: selectedOverride !== undefined ? "user" : path.selection_source ?? (selectedFileName ? "auto" : "none"),
      target: displayValue(path.target_version ?? selectedFileName ?? path.package_name ?? "Review required")
    }];
  });
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

function firmwareFilesInfo(media: MediaInventory | null, compliance: ProviderProbeResult | null): { lastScanned: string; packageCount: number } {
  const inventory = objectValue(compliance?.inventory);
  const mediaInventory = objectValue(inventory.media_inventory);
  const candidateCount = Number(mediaInventory.candidate_count ?? NaN);
  const mediaCount = media?.items.filter((item) => item.category === "firmware" || item.category === "iso").length ?? 0;
  return {
    lastScanned: asString(compliance?.checked_at) ? formatDateTime(asString(compliance?.checked_at)) : "Not scanned",
    packageCount: Number.isFinite(candidateCount) ? candidateCount : mediaCount
  };
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
  const selected = objectValue(probe?.selected_console);
  return displayValue(
    asString(consoleState.selected_path) ||
    asString(consoleState.effective_path) ||
    asString(selected.path) ||
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

function netappCredentialStatus(probe: ProviderProbeResult | null): string {
  return asBoolean(objectValue(probe?.credential_state).netapp_credentials_configured) ? "Configured" : "Missing";
}

function vcenterCredentialStatus(probe: ProviderProbeResult | null): string {
  return asBoolean(objectValue(probe?.credential_state).vcenter_credentials_configured) ? "Configured" : "Missing";
}

function raidLayoutLabel(probe: ProviderProbeResult | null): string {
  const desired = objectValue(probe?.desired_intent);
  const volumes = Array.isArray(desired.volumes) ? desired.volumes : [];
  if (volumes.length) return `${volumes.length} volume${volumes.length === 1 ? "" : "s"} planned`;
  return displayStatus(asString(probe?.status) || "not_checked");
}

function raidControllerModels(probe: ProviderProbeResult | null): string {
  const currentLayout = objectValue(probe?.current_layout);
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

function tabTitle(tabId: OperatorTabId): string {
  const labels: Record<OperatorTabId, string> = {
    config: "Edit Config",
    firmware: "Firmware Upgrades",
    network: "Network",
    overview: "Overview",
    server: "Server",
    settings: "Settings",
    storage: "Storage",
    validation: "Validation",
    virtualization: "Virtualization"
  };
  return labels[tabId];
}

function tabAdvancedSettings(tabId: OperatorTabId): AdvancedSettingDefinition[] {
  const shared = [
    {
      defaultValue: true,
      description: "Use the active lab profile targets for this tab.",
      key: "use_saved_targets",
      label: "Use saved targets"
    }
  ];
  const definitions: Record<OperatorTabId, AdvancedSettingDefinition[]> = {
    config: [
      {
        defaultValue: true,
        description: "Keep feature toggles aligned with the saved lab profile.",
        key: "sync_feature_toggles",
        label: "Sync feature toggles"
      },
      {
        defaultValue: false,
        description: "Keep IPv6-only as UI intent until backend persistence exists.",
        key: "allow_ipv6_only_intent",
        label: "Allow IPv6-only intent"
      }
    ],
    firmware: [
      ...shared,
      {
        defaultValue: true,
        description: "Include the HPE Service Pack and selected local files in scan results.",
        key: "include_media_matching",
        label: "Match local media"
      },
      {
        defaultValue: false,
        description: "Show protected upgrade placeholders without enabling firmware apply.",
        key: "show_guarded_upgrade",
        label: "Show guarded upgrade"
      }
    ],
    network: [
      ...shared,
      {
        defaultValue: true,
        description: "Include DNS, NTP, VLAN, SNMP, and MTU checks.",
        key: "include_network_services",
        label: "Check network services"
      },
      {
        defaultValue: false,
        description: "Include firmware inventory evidence in the network view.",
        key: "include_firmware_evidence",
        label: "Include firmware evidence"
      }
    ],
    overview: [
      ...shared,
      {
        defaultValue: true,
        description: "Use validation and provider status as the current view.",
        key: "include_validation_summary",
        label: "Include validation summary"
      },
      {
        defaultValue: true,
        description: "Show saved config values beside discovered status.",
        key: "include_saved_config",
        label: "Include saved config"
      }
    ],
    server: [
      ...shared,
      {
        defaultValue: true,
        description: "Include iLO, ESXi, and RAID readiness in the run.",
        key: "include_raid_and_esxi",
        label: "Check iLO, ESXi, and RAID"
      },
      {
        defaultValue: false,
        description: "Include HPE firmware inventory evidence when present.",
        key: "include_hpe_firmware",
        label: "Include HPE firmware"
      }
    ],
    settings: [
      ...shared,
      {
        defaultValue: true,
        description: "Refresh console mappings when available.",
        key: "include_console_refresh",
        label: "Refresh console mappings"
      },
      {
        defaultValue: true,
        description: "Show configured or missing credential state only.",
        key: "include_credential_status",
        label: "Credential status only"
      }
    ],
    storage: [
      ...shared,
      {
        defaultValue: true,
        description: "Include ONTAP, NFS, and datastore readiness.",
        key: "include_nfs_readiness",
        label: "Check NFS readiness"
      },
      {
        defaultValue: true,
        description: "Include console readiness and selected console path.",
        key: "include_console_readiness",
        label: "Check console readiness"
      }
    ],
    validation: [
      ...shared,
      {
        defaultValue: true,
        description: "Include firmware gate results in Golden State validation.",
        key: "include_firmware_gate",
        label: "Include firmware gate"
      },
      {
        defaultValue: true,
        description: "Prepare proof links for handoff after validation.",
        key: "prepare_handoff",
        label: "Prepare handoff proof"
      }
    ],
    virtualization: [
      ...shared,
      {
        defaultValue: true,
        description: "Include datastore visibility and ESXi attach checks.",
        key: "include_datastore_checks",
        label: "Check datastore visibility"
      },
      {
        defaultValue: true,
        description: "Include VM inventory visibility in the run.",
        key: "include_vm_inventory",
        label: "Check VM inventory"
      }
    ]
  };
  return definitions[tabId];
}

function tabSettingsValues(tab: string, profile: LabProfile | null): ConfigValue[] {
  const features = profile?.features ?? null;
  const global = profile?.global_settings ?? null;
  const address = activeAddressPlan(profile);
  const common: ConfigValue[] = [
    { label: "IP family", value: ipFamilyLabel(features), source: "Edit Config", status: features?.disable_ipv6 === false ? "warning" : "ready" },
    { label: "SNMP", value: snmpPolicyLabel(features), source: "Edit Config", status: features?.enable_snmp ? "ready" : "not_checked" },
    { label: "SNMP version", value: snmpVersionLabel(features), source: "Not persisted yet", status: "not_checked" }
  ];
  if (tab === "network") {
    return [
      ...common,
      { label: "VLAN", value: displayValue(global?.vlan_id ?? profile?.vlan_id), source: "Edit Config" },
      { label: "DNS", value: listLabel(global?.dns_servers ?? profile?.dns), status: featureStatus(features, "enable_dns") },
      { label: "NTP", value: listLabel(global?.ntp_servers ?? profile?.ntp), status: featureStatus(features, "enable_ntp") },
      { label: "MTU", value: displayValue(global?.mtu ?? profile?.mtu), source: "Edit Config" }
    ];
  }
  if (tab === "server") {
    return [
      ...common,
      { label: "iLO target", value: displayAddress(address.ilo), source: "Edit Config" },
      { label: "Initial iLO", value: displayAddress(address.ilo_initial), source: "Edit Config" },
      { label: "ESXi target", value: displayAddress(address.esxi_management), source: "Edit Config" },
      { label: "Legacy protocols", value: legacyProtocolLabel(features), status: features?.block_legacy_protocols === false ? "warning" : "ready" }
    ];
  }
  if (tab === "storage") {
    return [
      ...common,
      { label: "Storage protocol", value: storageProtocolLabel(features), source: "Edit Config", status: features?.storage_protocol === "none" ? "not_checked" : "ready" },
      { label: "NetApp cluster", value: displayAddress(address.netapp_cluster_mgmt), source: "Edit Config" },
      { label: "NFS LIFs", value: listLabel(address.netapp_nfs_lifs), source: "Edit Config" },
      { label: "iSCSI LIFs", value: listLabel(address.netapp_iscsi_lifs), source: "Edit Config" }
    ];
  }
  if (tab === "virtualization") {
    return [
      ...common,
      { label: "vCenter", value: enabledLabel(features?.vcenter_enabled), status: featureStatus(features, "vcenter_enabled") },
      { label: "Storage protocol", value: storageProtocolLabel(features), source: "Edit Config" },
      { label: "ESXi target", value: displayAddress(address.esxi_management), source: "Edit Config" },
      { label: "Datastore source", value: listLabel(address.netapp_nfs_lifs), source: "Edit Config" }
    ];
  }
  if (tab === "firmware") {
    return [
      ...common,
      { label: "Firmware gate", value: enabledLabel(features?.firmware_gate_enabled), status: featureStatus(features, "firmware_gate_enabled") },
      { label: "Media folder", value: "/home/administrator/infra-config-portal/artifacts/Media", source: "Local folder" },
      { label: "Upgrade apply", value: "Guarded confirmation required", status: "not_checked" },
      { label: "Storage protocol", value: storageProtocolLabel(features), source: "Edit Config" }
    ];
  }
  if (tab === "validation") {
    return [
      ...common,
      { label: "Build verification", value: enabledLabel(features?.build_verification_enabled), status: featureStatus(features, "build_verification_enabled") },
      { label: "Firmware gate", value: enabledLabel(features?.firmware_gate_enabled), status: featureStatus(features, "firmware_gate_enabled") },
      { label: "NetApp", value: enabledLabel(features?.netapp_enabled), status: featureStatus(features, "netapp_enabled") },
      { label: "vCenter", value: enabledLabel(features?.vcenter_enabled), status: featureStatus(features, "vcenter_enabled") }
    ];
  }
  return [
    ...common,
    { label: "Active setup", value: profile?.name ?? "No active setup", status: profile ? "ready" : "not_configured_yet" },
    { label: "Subnet", value: displayAddress(address.subnet), source: "Edit Config" },
    { label: "Storage protocol", value: storageProtocolLabel(features), source: "Edit Config" },
    { label: "Legacy protocols", value: legacyProtocolLabel(features), status: features?.block_legacy_protocols === false ? "warning" : "ready" }
  ];
}

function ipFamilyLabel(features: LabProfileFeatures | null): string {
  return features?.disable_ipv6 === false ? "IPv4 and IPv6" : "IPv4 only";
}

function snmpPolicyLabel(features: LabProfileFeatures | null): string {
  return features?.enable_snmp ? "Enabled" : "Disabled";
}

function snmpVersionLabel(features: LabProfileFeatures | null): string {
  if (!features?.enable_snmp) return "Off";
  return "SNMPv2/v3 selection not saved yet";
}

function legacyProtocolLabel(features: LabProfileFeatures | null): string {
  return features?.block_legacy_protocols === false ? "Allowed" : "Blocked";
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
      "Open Settings if targets or credentials are missing."
    ],
    recheckCommand: "make provider-lab-build-verification",
    scanDetail: "Run Validation refreshes the current view across the lab and records the next blocker if one exists.",
    scanLabel: "Run Validation",
    signals: [validation, buildVerification, ...providers],
    status,
    summary: validation?.top_blocker?.problem || validation?.next_action || "The overview uses validation and provider status as its current view."
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
      "Confirm the Cisco management IP and console path in Settings.",
      "Run Test Switch after fixing connectivity or credentials."
    ],
    recheckCommand: "make provider-lab-cisco-setup-readiness",
    scanDetail: "Test Switch checks Cisco reachability, console readiness, and credential state without printing secrets.",
    scanLabel: "Test Switch",
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
      "Run Test iLO before inventory or firmware work.",
      "Run Test ESXi after iLO and management networking are reachable."
    ],
    recheckCommand: "make provider-lab-ilo-reachability",
    scanDetail: "Test iLO and Test ESXi refresh the current server view; Validate RAID refreshes the storage controller plan.",
    scanLabel: "Test iLO",
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
  const status = asString(vcenterNetapp?.status) || asString(nfsReadiness?.status) || asString(netappPlan?.status) || "not_checked";
  return currentViewModel({
    available: Boolean(vcenterNetapp?.checked_at || nfsReadiness?.checked_at || netappPlan?.checked_at || consoleReadiness?.checked_at),
    details: [
      { label: "Cluster", value: displayAddress(address.netapp_cluster_mgmt), status },
      { label: "Console", value: displayValue(asString(objectValue(consoleReadiness?.runtime_state).console)), status: asString(consoleReadiness?.status) || "not_checked" },
      { label: "Datastore", value: datastoreName(vcenterNetapp), status: datastoreVisibleStatus(vcenterNetapp) }
    ],
    fixSteps: [
      asString(vcenterNetapp?.next_safe_action) || asString(nfsReadiness?.next_safe_action),
      "Run Test NetApp to refresh ONTAP access and setup readiness.",
      "Run Validate NFS before any datastore mount action."
    ],
    recheckCommand: "make provider-lab-netapp-live-state",
    scanDetail: "Test NetApp refreshes ONTAP access; Validate NFS explains which storage or vCenter prerequisite is missing.",
    scanLabel: "Test NetApp",
    signals: [vcenterNetapp, nfsReadiness, netappPlan, consoleReadiness],
    status,
    summary: asString(vcenterNetapp?.message) || asString(nfsReadiness?.message) || asString(netappPlan?.message) || "No storage current view has been loaded yet."
  });
}

function virtualizationCurrentView({
  activeProfile,
  installReadiness,
  postAttach,
  vcenterNetapp
}: {
  activeProfile: LabProfile | null;
  installReadiness: ProviderProbeResult | null;
  postAttach: ProviderProbeResult | null;
  vcenterNetapp: ProviderProbeResult | null;
}): CurrentViewModel {
  const postChecks = objectValue(postAttach?.checks);
  const status = asString(postAttach?.status) || asString(vcenterNetapp?.status) || asString(installReadiness?.status) || "not_checked";
  return currentViewModel({
    available: Boolean(postAttach?.checked_at || vcenterNetapp?.checked_at || installReadiness?.checked_at),
    details: [
      { label: "vCenter", value: vcenterTarget(vcenterNetapp || installReadiness, activeProfile), status },
      { label: "Datastore", value: datastoreName(vcenterNetapp), status: datastoreVisibleStatus(vcenterNetapp || postAttach) },
      { label: "VM inventory", value: visibilityLabel(postChecks.vm_inventory_visible), status: visibilityStatus(postChecks.vm_inventory_visible) }
    ],
    fixSteps: [
      asString(vcenterNetapp?.next_safe_action) || asString(installReadiness?.next_safe_action),
      "Run Test vCenter to refresh the current virtualization view.",
      "Run Validate Inventory after datastore and vCenter access are ready."
    ],
    recheckCommand: "make provider-lab-vcenter-netapp-readiness",
    scanDetail: "Test vCenter checks the vCenter target, ESXi attach readiness, datastore visibility, and credential state.",
    scanLabel: "Test vCenter",
    signals: [postAttach, vcenterNetapp, installReadiness],
    status,
    summary: asString(postAttach?.message) || asString(vcenterNetapp?.message) || asString(installReadiness?.message) || "No virtualization current view has been loaded yet."
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
    scanDetail: "Run Validation refreshes the current blocker list and produces a proof-backed handoff view.",
    scanLabel: "Run Validation",
    signals: [validation, buildVerification, vcenterNetapp],
    status: validation?.overall_status ?? "not_checked",
    summary: validation?.top_blocker?.problem || validation?.next_action || "No validation current view has been loaded yet."
  });
}

function settingsCurrentView({
  activeProfile,
  health,
  labProfileState,
  vcenterNetapp
}: {
  activeProfile: LabProfile | null;
  health: HealthLike;
  labProfileState: LabProfileList | null;
  vcenterNetapp: ProviderProbeResult | null;
}): CurrentViewModel {
  return currentViewModel({
    available: Boolean(activeProfile),
    checkedAt: activeProfile?.updated_at ?? labProfileState?.active_profile?.updated_at ?? undefined,
    details: [
      { label: "Active setup", value: activeProfile?.name ?? "No active setup", status: activeProfile ? "ready" : "not_configured_yet" },
      { label: "Runtime mode", value: displayStatus(runtimeStatus(health)), status: runtimeStatus(health) },
      { label: "vCenter target", value: vcenterTarget(vcenterNetapp, activeProfile), status: vcenterNetapp?.status ?? "not_checked" }
    ],
    fixSteps: [
      labProfileState?.next_safe_action,
      "Open Edit Config from Overview if the active lab values are wrong.",
      "Run Refresh Consoles after plugging in or changing serial adapters."
    ],
    freshness: activeProfile ? "operator_config" : "not_checked",
    recheckCommand: "make provider-lab-build-verification",
    scanDetail: "Refresh Consoles and Test Credentials update the current setup view without exposing secret values.",
    scanLabel: "Refresh Consoles",
    signals: [vcenterNetapp],
    source: activeProfile ? "Saved setup" : "Not checked",
    status: activeProfile ? "ready" : "not_configured_yet",
    summary: activeProfile ? "The current setup view is loaded from the active lab profile." : "No active lab setup is loaded."
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
    mock: "Test mode",
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
    .replace(/not_configured_yet/g, "Not set up yet")
    .replace(/not_configured/g, "Not set up yet")
    .replace(/manual_review/g, "Needs review")
    .replace(/local-lab-readwrite/g, "Real lab")
    .replace(/local-readonly/g, "Read-only lab")
    .replace(/Provider mode/g, "Mode")
    .replace(/provider mode/g, "mode")
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
