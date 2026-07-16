import {
  Activity,
  AlertTriangle,
  Ban,
  CheckCircle2,
  ClipboardList,
  Copy,
  FileText,
  Pencil,
  HardDrive,
  History,
  Layers,
  Play,
  Plus,
  RefreshCw,
  Route,
  Save,
  Server,
  ShieldCheck,
  Send,
  Settings,
  Wrench,
  Workflow,
  X,
  XCircle
} from "lucide-react";
import { createContext, FormEvent, ReactNode, SetStateAction, useContext, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Link, Navigate, Route as RouterRoute, Routes, useLocation, useNavigate, useParams } from "react-router-dom";

import { api } from "./api";
import {
  OperatorFirmwareUpgradesPage,
  OperatorOverviewPage,
  OperatorTabStateProvider,
  OperatorValidationPage,
  SettingsGlobalProfilePanel
} from "./operatorPages";
import type {
  ArtifactRecord,
  AuditEvent,
  Catalog,
  CiscoBootstrapRequirements,
  CiscoBootstrapRequirementsUpdate,
  CiscoConsoleBootstrapPlan,
  CiscoSetupReadiness,
  CiscoSetupWizardPlan,
  ConsoleCandidate,
  ControlAction,
  ControlAccessConfig,
  ControlAccessConfigWrite,
  ControlActionCatalog,
  ControlActionPlan,
  ControlLabProfile,
  ControlPlanDiffItem,
  ControlSectionRecord,
  ControlStateItem,
  FirmwareSummary,
  FirmwareUpgradePath,
  HpeRaidIntent,
  HpeRaidIntentWrite,
  HpeRaidPlanPreview,
  HpeRaidVolumeIntent,
  HpeStorageDiscovery,
  IloBaselinePreview,
  IloBaselineReadiness,
  IloSetupIntent,
  IloSetupIntentWrite,
  IloSetupPlanPreview,
  IloUpgradeReadiness,
  LabValidationItem,
  LabValidationSummary,
  LabAddressPlan,
  LabGlobalSettings,
  LabProfile,
  LabProfileContext as ActiveLabProfileContext,
  LabProfileFeatures,
  LabProfileList,
  LabProfileWrite,
  LabSubnetOption,
  MediaInventory,
  MinimalStageSummary,
  NetAppConsoleReadiness,
  NetAppObservationUpdate,
  NetAppProviderArtifact,
  NetAppPlanPreview,
  NetAppReadinessComparison,
  NetAppUpgradeReadiness,
  OperatorIssuePacket,
  ProviderModeSettings,
  ProviderModeSettingsWrite,
  ProviderAction,
  ProviderProbeResult,
  ProviderStatus,
  ReadinessIssue,
  ReportCenter,
  ReportIssue,
  ReportSourceSummary,
  ReportPageBadge,
  RequestReadiness,
  RequestRecord,
  RequestStatus,
  UiDisplayMode,
  VMDeploymentCreate,
  VMDeploymentUpdate,
  WorkflowAction,
  WorkflowActionRunRequest,
  WorkflowActionRun,
  WorkflowRun,
  WorkflowStage
} from "./types";

const statusOrder: RequestStatus[] = [
  "draft",
  "submitted",
  "validating",
  "needs_approval",
  "approved",
  "planned",
  "executing",
  "completed",
  "failed",
  "cancelled",
  "rejected"
];

type RunWorkflowActionHandler = (action: WorkflowAction, request?: WorkflowActionRunRequest) => void;

const cancellableStatuses: RequestStatus[] = [
  "draft",
  "submitted",
  "validating",
  "needs_approval",
  "approved",
  "planned"
];

type StageEvent = {
  stage: string;
  status: string;
  message: string;
};

type ProviderSection = {
  id: string;
  label: string;
  providerIds: string[];
  status: string;
};

type WorkflowSummaryItem = {
  label: string;
  value: string;
};

type ReadinessMap = Record<string, RequestReadiness>;

type QueueSectionId =
  | "needs_approval"
  | "approved_ready_to_plan"
  | "planned_ready_to_execute"
  | "executing"
  | "blocked_failed"
  | "completed";

type QueueItem = {
  key: string;
  sectionId: QueueSectionId;
  request: RequestRecord | null;
  run: WorkflowRun | null;
  title: string;
  subtitle: string;
  status: string;
  actionLabel: string;
  reason: string;
};

type QueueSection = {
  id: QueueSectionId;
  title: string;
  empty: string;
  items: QueueItem[];
};

type PlanStep = {
  name: string;
  status: string;
  target: string;
};

type RunCenterView = "choose" | "queue" | "selected" | "netapp";
type RunCenterSectionId = "guided" | "cisco" | "ilo" | "raid" | "esxi" | "netapp";
type DashboardSectionId = "overview" | "blockers" | "last-run" | "next-actions";
type ControlCenterSectionId =
  | "lab-profile"
  | "cisco"
  | "ilo"
  | "raid"
  | "esxi"
  | "netapp"
  | "vcenter"
  | "firmware-upgrade"
  | "verification"
  | "reports"
  | "action-catalog";
type FirmwareSectionId = "upgrade" | "evidence";
type FirmwareDeviceFilter = "all" | "cisco" | "ilo" | "raid" | "esxi" | "netapp" | "vcenter";
type VerificationSectionId =
  | "summary"
  | "network"
  | "storage"
  | "firmware"
  | "credentials"
  | "mtu-protocols"
  | "certification-report";
type GoldenStateSectionId = "dashboard" | "drift" | "credentials" | "vcenter";
type LabValidationSectionId = "overview" | "vcenter-netapp" | "handoff";
type ValidationReportsSectionId = "summary" | "issues" | "validation" | "proof" | "evidence";
type ReportsSectionId =
  | "all"
  | "critical"
  | "warnings"
  | "stale_config"
  | "cisco"
  | "esxi"
  | "netapp"
  | "firmware"
  | "lab_profile";
type ReportIssueAreaId =
  | "dashboard"
  | "run-center"
  | "control-center"
  | "firmware"
  | "verification"
  | "reports"
  | "settings";
type SettingsSectionId =
  | "mode"
  | "ip-profile"
  | "credentials"
  | "media-paths"
  | "toolchain"
  | "feature-flags"
  | "waivers";

type HealthStatus = {
  app?: string;
  provider_mode: string;
  operator_runtime_mode?: string;
  expected_runtime_mode?: string;
  lab_subnet_cidr?: string | null;
  host_ipv4_addresses?: string[];
  dev_test_banner?: string | null;
  status: string;
};

type SectionOption<T extends string = string> = {
  id: T;
  label: string;
  status?: string;
};

type PrimaryAction = {
  disabled?: boolean;
  icon?: ReactNode;
  label: string;
  onClick?: () => void;
  to?: string;
};

type ReportLink = {
  label: string;
  path: string;
  status?: string;
};

type MinimalStageItem = MinimalStageSummary & {
  disabled_reason?: string;
  id: string;
  primary_action?: WorkflowAction | null;
};

type LegacyReportSectionId =
  | "latest"
  | "cisco"
  | "ilo"
  | "raid"
  | "esxi"
  | "netapp"
  | "firmware"
  | "verification";

type ConfigOptionEffect = "read_only" | "config_change" | "destructive" | "upgrade";

type ConfigOptionSupport =
  | "api"
  | "cli"
  | "console"
  | "redfish"
  | "ontap_rest"
  | "ansible"
  | "govc"
  | "manual";

type ControlConfigOption = {
  option_id: string;
  label: string;
  device_stage: string;
  description: string;
  current_value: string;
  desired_value: string;
  supported_by: ConfigOptionSupport[];
  availability: string;
  effect: ConfigOptionEffect;
  requires_confirmation: boolean;
  recommended_default: boolean;
  validation_status: string;
  linked_action_id: string | null;
};

type AccessButton = {
  disabled?: boolean;
  label: string;
  onClick?: () => void;
  to?: string;
};

type RunChoice = {
  id: string;
  title: string;
  category: string;
  status: string;
  description: string;
  blockers: string[];
  primaryLabel: string;
  primaryTo?: string;
  onPrimary?: () => void;
  secondaryLabel?: string;
  secondaryTo?: string;
  command?: string;
  icon: ReactNode;
};

type BuildStage = {
  id: string;
  title: string;
  step: string;
  status: string;
  message: string;
  nextAction: string;
  metricLabel: string;
  metricValue: string;
  quickFacts?: Array<[string, string]>;
  blocker: string;
  detailSummary: string;
  details: ReactNode;
};

type BuildOverview = {
  overallState: string;
  currentPhase: string;
  nextAction: string;
  topBlocker: string;
  lastMilestone: string;
  mode: string;
};

type HardwareInventoryRow = {
  id: string;
  equipment: string;
  type: string;
  role: string;
  osFirmware: string;
  access: string;
  target: string;
  usernameField: string;
  status: string;
  lastChecked: string | null;
  actions: string[];
  evidence: string[];
};

type LabAddressScalarKey = Exclude<keyof LabAddressPlan, "netapp_nfs_lifs" | "netapp_iscsi_lifs">;
type LabAddressInputKey = Exclude<LabAddressScalarKey, "subnet">;
type LabGlobalSettingsFormState = {
  subnetPrefix: string;
  gateway: string;
  domainName: string;
  dnsServers: string;
  ntpServers: string;
  timezone: string;
  vlanId: string;
  mtu: string;
  vcenterEnabled: boolean;
  storageProtocol: string;
  disableIpv6: boolean;
  blockLegacyProtocols: boolean;
  enableSnmp: boolean;
  enableNtp: boolean;
  enableDns: boolean;
};

type LabProfileFormState = {
  name: string;
  description: string;
  profileTopology: string;
  addresses: Record<LabAddressScalarKey, string>;
  globalSettings: LabGlobalSettingsFormState;
  netappNfsLifs: string;
  netappIscsiLifs: string;
};

type ConfigEditorSectionId = "setup" | "network" | "devices" | "netapp";

type GlobalConfigEditState = Pick<
  LabGlobalSettingsFormState,
  | "domainName"
  | "dnsServers"
  | "ntpServers"
  | "timezone"
  | "vlanId"
  | "mtu"
  | "storageProtocol"
  | "disableIpv6"
  | "blockLegacyProtocols"
  | "enableSnmp"
  | "enableNtp"
  | "enableDns"
>;

type ControlProfileEditField =
  | {
      kind: "profile";
      key: "name" | "description";
      label: string;
    }
  | {
      kind: "address";
      key: LabAddressScalarKey;
      label: string;
    }
  | {
      kind: "global";
      key: keyof LabGlobalSettingsFormState;
      label: string;
      options?: Array<{ label: string; value: string }>;
      valueType?: "boolean" | "number" | "select" | "text";
    }
  | {
      kind: "netapp-list";
      key: "netappNfsLifs" | "netappIscsiLifs";
      label: string;
    };

const labSubnetField: { key: "subnet"; label: string } = { key: "subnet", label: "Subnet CIDR" };

const labCoreAddressFields: Array<{ key: LabAddressInputKey; label: string }> = [
  { key: "ilo", label: "Permanent iLO IP" },
  { key: "ilo_initial", label: "Initial iLO Login IP" },
  { key: "server_embedded_nic", label: "Server NIC" },
  { key: "esxi_management", label: "ESXi Management" },
  { key: "cisco_management", label: "Cisco Management" },
  { key: "ansible_control_host", label: "Control Host" }
];

const labNetAppAddressFields: Array<{ key: LabAddressInputKey; label: string }> = [
  { key: "netapp_controller_a_sp", label: "NetApp Controller A SP" },
  { key: "netapp_controller_b_sp", label: "NetApp Controller B SP" },
  { key: "netapp_cluster_mgmt", label: "NetApp Cluster Mgmt" },
  { key: "netapp_node_a_mgmt", label: "NetApp Node A Mgmt" },
  { key: "netapp_node_b_mgmt", label: "NetApp Node B Mgmt" },
  { key: "netapp_svm_mgmt", label: "NetApp SVM Mgmt" }
];

const labAddressFields: Array<{ key: LabAddressScalarKey; label: string }> = [
  { key: "subnet", label: "Subnet CIDR" },
  ...labCoreAddressFields,
  ...labNetAppAddressFields
];

const defaultLabSubnet = "192.168.1.0/24";
const netappDisabledForSubnetReason =
  "NetApp and vCenter are outside the normal scope for compact lab setups. Use a /24 high-address setup, or manually enable them with custom in-subnet addresses.";
const labBuilderCoreOffsets: Partial<Record<LabAddressInputKey, number>> = {
  ilo: 201,
  server_embedded_nic: 202,
  esxi_management: 203,
  cisco_management: 204,
  ansible_control_host: 205
};
const compactCoreOffsets: Partial<Record<LabAddressInputKey, number>> = {
  cisco_management: 2,
  ansible_control_host: 9,
  esxi_management: 10,
  ilo: 11
};
const labBuilderNetAppOffsets: Partial<Record<LabAddressInputKey, number>> = {
  netapp_controller_a_sp: 210,
  netapp_controller_b_sp: 211,
  netapp_cluster_mgmt: 220,
  netapp_node_a_mgmt: 221,
  netapp_node_b_mgmt: 222,
  netapp_svm_mgmt: 223
};
const labBuilderNetAppNfsOffsets = [230, 231];
const labBuilderNetAppIscsiOffsets = [240, 241, 242, 243];

const queueSectionMeta: Array<Omit<QueueSection, "items">> = [
  {
    id: "needs_approval",
    title: "Needs Approval",
    empty: "No requests are waiting for approval."
  },
  {
    id: "approved_ready_to_plan",
    title: "Approved Ready To Plan",
    empty: "No approved requests are waiting for a preview plan."
  },
  {
    id: "planned_ready_to_execute",
    title: "Planned Ready To Execute",
    empty: "No planned requests are ready to execute."
  },
  {
    id: "executing",
    title: "Executing",
    empty: "No workflow is executing."
  },
  {
    id: "blocked_failed",
    title: "Blocked / Failed",
    empty: "No blocked or failed work needs review."
  },
  {
    id: "completed",
    title: "Completed",
    empty: "No completed runs yet."
  }
];

type ReportIssuesContextValue = {
  reportIssues: ReportCenter | null;
  reportIssuesError: string;
  reportIssuesLoading: boolean;
  reloadReportIssues: () => Promise<void>;
};

const ReportIssuesContext = createContext<ReportIssuesContextValue>({
  reportIssues: null,
  reportIssuesError: "",
  reportIssuesLoading: false,
  reloadReportIssues: async () => {}
});

function useReportIssues() {
  return useContext(ReportIssuesContext);
}

type UiModeContextValue = {
  isAdvancedMode: boolean;
  setUiMode: (mode: UiDisplayMode) => void;
  uiMode: UiDisplayMode;
};

const UiModeContext = createContext<UiModeContextValue>({
  isAdvancedMode: false,
  setUiMode: () => {},
  uiMode: "simple"
});

function useUiMode() {
  return useContext(UiModeContext);
}

type LabProfileContextValue = {
  activeContext: ActiveLabProfileContext | null;
  activeProfile: LabProfile | null;
  error: string;
  loading: boolean;
  onActivate: (profileId: string) => Promise<void>;
  onCreate: (kitName: string) => Promise<void>;
  onApplyRuntimeEnv: () => Promise<void>;
  onReload: () => Promise<void>;
  runtimeApplyLoading: boolean;
  runtimeApplyMessage: string;
  state: LabProfileList | null;
};

const LabProfileContext = createContext<LabProfileContextValue>({
  activeContext: null,
  activeProfile: null,
  error: "",
  loading: false,
  onActivate: async () => {},
  onCreate: async () => {},
  onApplyRuntimeEnv: async () => {},
  onReload: async () => {},
  runtimeApplyLoading: false,
  runtimeApplyMessage: "",
  state: null
});

function useLabProfileContext() {
  return useContext(LabProfileContext);
}

function initialUiMode(): UiDisplayMode {
  if (typeof window === "undefined") {
    return "simple";
  }
  return window.localStorage.getItem("infra-config-operator-ui-mode") === "advanced" ? "advanced" : "simple";
}

function App() {
  const [labProfileState, setLabProfileState] = useState<LabProfileList | null>(null);
  const [labProfileError, setLabProfileError] = useState("");
  const [labProfileLoading, setLabProfileLoading] = useState(true);
  const [runtimeApplyLoading, setRuntimeApplyLoading] = useState(false);
  const [runtimeApplyMessage, setRuntimeApplyMessage] = useState("");
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [healthError, setHealthError] = useState("");
  const [reportIssues, setReportIssues] = useState<ReportCenter | null>(null);
  const [reportIssuesError, setReportIssuesError] = useState("");
  const [reportIssuesLoading, setReportIssuesLoading] = useState(true);
  const [uiMode, setUiMode] = useState<UiDisplayMode>(initialUiMode);

  async function loadLabProfileState() {
    setLabProfileError("");
    setLabProfileLoading(true);
    try {
      setLabProfileState(await api.labProfiles());
    } catch (err) {
      setLabProfileError((err as Error).message);
    } finally {
      setLabProfileLoading(false);
    }
  }

  async function activateLabProfile(profileId: string) {
    setLabProfileError("");
    setRuntimeApplyMessage("");
    setLabProfileLoading(true);
    try {
      setLabProfileState(await api.activateLabProfile(profileId));
    } catch (err) {
      setLabProfileError((err as Error).message);
    } finally {
      setLabProfileLoading(false);
    }
  }

  async function applyActiveLabProfileRuntimeEnv() {
    setLabProfileError("");
    setRuntimeApplyMessage("");
    setRuntimeApplyLoading(true);
    try {
      const result = await api.applyActiveLabProfileRuntimeEnv();
      setLabProfileState(result.lab_profiles);
      setRuntimeApplyMessage(`${result.message} ${result.next_action}`);
    } catch (err) {
      setLabProfileError((err as Error).message);
    } finally {
      setRuntimeApplyLoading(false);
    }
  }

  async function loadReportIssues() {
    setReportIssuesError("");
    setReportIssuesLoading(true);
    try {
      setReportIssues(await api.reportIssues());
    } catch (err) {
      setReportIssues(null);
      setReportIssuesError((err as Error).message);
    } finally {
      setReportIssuesLoading(false);
    }
  }

  async function createLabKit(kitName: string) {
    const name = kitName.trim();
    if (!name) {
      setLabProfileError("Enter a kit name before creating it.");
      return;
    }
    setLabProfileError("");
    setRuntimeApplyMessage("");
    setLabProfileLoading(true);
    try {
      const form = blankLabProfileForm();
      form.name = name;
      const created = await api.createLabProfile(labProfilePayload(form));
      setLabProfileState(await api.activateLabProfile(created.id));
    } catch (err) {
      setLabProfileError((err as Error).message);
    } finally {
      setLabProfileLoading(false);
    }
  }

  async function loadHealth() {
    try {
      const nextHealth = await api.health();
      setHealth(nextHealth);
      setHealthError("");
    } catch (err) {
      setHealth(null);
      setHealthError((err as Error).message);
    }
  }

  useEffect(() => {
    let ignore = false;
    async function loadStartup() {
      await loadLabProfileState();
      if (ignore) return;
      await loadHealth();
      if (ignore) return;
      window.setTimeout(() => {
        if (!ignore) {
          void loadReportIssues();
        }
      }, 500);
    }
    void loadStartup();
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    window.localStorage.setItem("infra-config-operator-ui-mode", uiMode);
  }, [uiMode]);

  return (
    <UiModeContext.Provider value={{ isAdvancedMode: uiMode === "advanced", setUiMode, uiMode }}>
      <LabProfileContext.Provider
        value={{
          activeContext: labProfileState?.active_context ?? null,
          activeProfile: labProfileState?.active_profile ?? null,
          error: labProfileError,
          loading: labProfileLoading,
          onActivate: activateLabProfile,
          onCreate: createLabKit,
          onApplyRuntimeEnv: applyActiveLabProfileRuntimeEnv,
          onReload: loadLabProfileState,
          runtimeApplyLoading,
          runtimeApplyMessage,
          state: labProfileState
        }}
      >
      <ReportIssuesContext.Provider
        value={{ reportIssues, reportIssuesError, reportIssuesLoading, reloadReportIssues: loadReportIssues }}
      >
        <AppShell health={health}>
          <OperatorTabStateProvider>
            <Routes>
              <RouterRoute path="/" element={<Navigate to="/overview" replace />} />
              <RouterRoute
                path="/overview"
                element={
                  <OperatorOverviewPage
                    health={health}
                    labProfileError={labProfileError}
                    labProfileLoading={labProfileLoading}
                    labProfileState={labProfileState}
                    onReloadLabProfile={loadLabProfileState}
                  />
                }
              />
              <RouterRoute path="/network" element={<Navigate to="/overview" replace />} />
              <RouterRoute path="/server" element={<Navigate to="/overview" replace />} />
              <RouterRoute path="/storage" element={<Navigate to="/overview" replace />} />
              <RouterRoute path="/virtualization" element={<Navigate to="/overview" replace />} />
              <RouterRoute path="/firmware-upgrades" element={<OperatorFirmwareUpgradesPage labProfileState={labProfileState} />} />
              <RouterRoute path="/validation" element={<OperatorValidationPage labProfileState={labProfileState} />} />
              <RouterRoute path="/config" element={<Navigate to="/overview" replace />} />
              <RouterRoute path="/dashboard" element={<Navigate to="/overview" replace />} />
              <RouterRoute path="/lab-setup" element={<Navigate to="/overview" replace />} />
              <RouterRoute path="/hardware" element={<Navigate to="/overview" replace />} />
              <RouterRoute path="/run-center" element={<Navigate to="/overview" replace />} />
              <RouterRoute path="/control-center" element={<Navigate to="/overview" replace />} />
              <RouterRoute path="/firmware" element={<Navigate to="/firmware-upgrades" replace />} />
              <RouterRoute path="/golden-state" element={<Navigate to="/validation" replace />} />
              <RouterRoute path="/validation-reports" element={<Navigate to="/validation" replace />} />
              <RouterRoute path="/verification" element={<Navigate to="/validation" replace />} />
              <RouterRoute path="/lab-validation" element={<Navigate to="/validation" replace />} />
              <RouterRoute path="/reports" element={<Navigate to="/validation" replace />} />
              <RouterRoute path="/settings" element={<Navigate to="/overview" replace />} />
              <RouterRoute path="/requests" element={<RequestListPage />} />
              <RouterRoute path="/requests/new" element={<NewRequest />} />
              <RouterRoute path="/requests/:id" element={<RequestDetail />} />
              <RouterRoute path="/workflow-runs/:id" element={<WorkflowRunDetail />} />
              <RouterRoute
                path="/lab-profiles"
                element={
                  <LabProfilesPage
                    error={labProfileError}
                    loading={labProfileLoading}
                    onReload={loadLabProfileState}
                    onStateChange={setLabProfileState}
                    state={labProfileState}
                  />
                }
              />
              <RouterRoute path="/audit-events" element={<AuditEvents />} />
              <RouterRoute path="/artifacts" element={<Navigate to="/validation" replace />} />
              <RouterRoute path="/media" element={<MediaInventoryPage />} />
              <RouterRoute path="/providers" element={<Navigate to="/overview" replace />} />
            </Routes>
          </OperatorTabStateProvider>
        </AppShell>
      </ReportIssuesContext.Provider>
      </LabProfileContext.Provider>
    </UiModeContext.Provider>
  );
}

function AppShell({
  children,
  health
}: {
  children: ReactNode;
  health: HealthStatus | null;
}) {
  const { uiMode } = useUiMode();
  return (
    <div className={`app-shell app-shell-${uiMode}`}>
      <NavigationSpine />
      <main className="content">
        {health?.dev_test_banner && <DevTestBanner message={health.dev_test_banner} />}
        {children}
      </main>
      <OperatorIssueReporter />
    </div>
  );
}

function DevTestBanner({ message }: { message: string }) {
  return (
    <section className="dev-test-banner" aria-label="Development test mode warning">
      <AlertTriangle size={18} />
      <div>
        <strong>Dev/Test Mode</strong>
        <p>{humanizeDevTestBanner(message)}</p>
      </div>
    </section>
  );
}

function humanizeDevTestBanner(message: string): string {
  if (message.includes("PROVIDER_MODE=mock")) {
    return "Test mode is on. Real lab status, reports, and certification require Real Lab Mode.";
  }
  return humanizeAction(message);
}

function ModeToggle() {
  const { setUiMode, uiMode } = useUiMode();
  return (
    <div className="mode-toggle" role="group" aria-label="Display mode">
      <button
        aria-pressed={uiMode === "simple"}
        className={uiMode === "simple" ? "active" : ""}
        onClick={() => setUiMode("simple")}
        type="button"
      >
        <ClipboardList size={16} />
        Operator
      </button>
      <button
        aria-pressed={uiMode === "advanced"}
        className={uiMode === "advanced" ? "active" : ""}
        onClick={() => setUiMode("advanced")}
        type="button"
      >
        <Wrench size={16} />
        Advanced
      </button>
    </div>
  );
}

function OperatorIssueReporter() {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [copying, setCopying] = useState(false);
  const [error, setError] = useState("");
  const [packet, setPacket] = useState<OperatorIssuePacket | null>(null);
  const route = `${location.pathname}${location.search}`;
  const pageTitle = pageTitleForRoute(location.pathname);

  useEffect(() => {
    setOpen(false);
    setError("");
    setPacket(null);
  }, [route]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setPacket(null);
    try {
      setPacket(await api.createOperatorIssuePacket({
        operator_note: note,
        page_title: pageTitle,
        route,
        ui_context: {
          page: pageTitle,
          path: location.pathname,
          query: location.search || "none",
          viewport: `${window.innerWidth}x${window.innerHeight}`
        }
      }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  async function copyPrompt() {
    if (!packet) return;
    setCopying(true);
    try {
      await navigator.clipboard.writeText(packet.copy_prompt);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      window.setTimeout(() => setCopying(false), 600);
    }
  }

  return (
    <>
      <button className="operator-issue-trigger" onClick={() => setOpen(true)} type="button">
        <AlertTriangle size={16} />
        Report issue
      </button>
      {open && createPortal(
        <div className="operator-issue-overlay" role="dialog" aria-modal="true" aria-label="Report testing issue">
          <form className="operator-issue-panel" onSubmit={submit}>
            <div className="operator-issue-head">
              <div>
                <p className="operator-kicker">Testing feedback</p>
                <h2>Report what broke</h2>
              </div>
              <button aria-label="Close issue reporter" onClick={() => setOpen(false)} type="button">
                <X size={18} />
              </button>
            </div>
            <div className="operator-issue-route">
              <span>{pageTitle}</span>
              <code>{route}</code>
            </div>
            <label className="operator-issue-note">
              <span>What went wrong?</span>
              <textarea
                maxLength={1600}
                onChange={(event) => setNote(event.target.value)}
                placeholder="Example: I clicked Run Validation, it said done, but the storage check still looks blocked."
                value={note}
              />
            </label>
            {error && <p className="operator-feedback error">{error}</p>}
            {packet && (
              <div className="operator-issue-result" aria-label="Generated issue packet">
                <strong>{packet.summary}</strong>
                <span>Packet: {packet.artifact}</span>
                <span>Markdown: {packet.markdown_artifact}</span>
                <ul>
                  {packet.suggested_next_steps.slice(0, 3).map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ul>
                <button className="secondary-button" onClick={() => void copyPrompt()} type="button">
                  <Copy size={15} />
                  {copying ? "Copied" : "Copy AI prompt"}
                </button>
              </div>
            )}
            <div className="operator-issue-actions">
              <button className="secondary-button" onClick={() => setOpen(false)} type="button">
                Cancel
              </button>
              <button disabled={submitting} type="submit">
                <Send size={15} />
                {submitting ? "Building packet" : "Create packet"}
              </button>
            </div>
          </form>
        </div>,
        document.body
      )}
    </>
  );
}

function pageTitleForRoute(pathname: string) {
  const segment = pathname.split("/").filter(Boolean)[0] || "overview";
  const labels: Record<string, string> = {
    "firmware-upgrades": "Firmware Upgrades",
    "lab-profiles": "Lab Profiles",
    "audit-events": "Audit Events",
    media: "Media",
    network: "Network",
    overview: "Overview",
    requests: "Requests",
    server: "Server",
    storage: "Storage",
    validation: "Validation",
    virtualization: "Virtualization"
  };
  return labels[segment] ?? labelize(segment);
}

const setupSpineItems = [
  { label: "iLO", to: "/overview#topology-map" },
  { label: "Storage", to: "/overview#topology-map" },
  { label: "ESXi", to: "/overview#topology-map" },
  { label: "Windows", to: "/overview#topology-map" },
  { label: "Cisco", to: "/overview#topology-map" },
  { label: "NetApp", to: "/overview#topology-map" },
  { label: "OVF", to: "/overview#topology-map" },
  { label: "Firmware", to: "/firmware-upgrades" },
  { label: "Global", to: "/lab-profiles" }
];

function NavigationSpine() {
  const location = useLocation();
  const { activeProfile, error, loading, onActivate, onCreate, state } = useLabProfileContext();
  const [newKitName, setNewKitName] = useState("");
  const runSelected = location.pathname === "/overview" && new URLSearchParams(location.search).get("view") === "run";
  const setupSelected = ["/firmware-upgrades", "/lab-profiles"].includes(location.pathname) || (
    location.pathname === "/overview" && location.hash === "#topology-map"
  );
  const overviewSelected = location.pathname === "/overview" && !runSelected && !setupSelected;
  const options = state ? [state.runtime_profile, ...state.profiles] : [];

  async function createKit(event: FormEvent) {
    event.preventDefault();
    const name = newKitName.trim();
    if (!name) return;
    await onCreate(name);
    setNewKitName("");
  }

  return (
    <aside className="navigation-spine" aria-label="Lab Builder navigation">
      <header className="navigation-spine-header">
        <Link className="brand" to="/overview">
          <Server size={22} />
          <span>
            Lab Builder
            <small>Infrastructure setup</small>
          </span>
        </Link>
        <section className="spine-kit-manager" aria-label="Kit management">
          <p>Selected kit</p>
          <strong data-testid="spine-selected-kit">{activeProfile?.name ?? (loading ? "Loading kit" : "No selected kit")}</strong>
          <label>
            <span>Switch kit</span>
            <select
              aria-label="Switch kit"
              disabled={loading || options.length === 0}
              onChange={(event) => void onActivate(event.target.value)}
              value={activeProfile?.id ?? ""}
            >
              {options.map((profile) => (
                <option key={profile.id} value={profile.id}>{profile.name}</option>
              ))}
            </select>
          </label>
          <form onSubmit={createKit}>
            <label>
              <span>New kit name</span>
              <input
                aria-label="New kit name"
                disabled={loading}
                maxLength={80}
                onChange={(event) => setNewKitName(event.target.value)}
                placeholder="New kit name"
                value={newKitName}
              />
            </label>
            <button disabled={loading || !newKitName.trim()} type="submit">
              <Plus size={15} />
              Create kit
            </button>
          </form>
          {error && <small role="alert">{error}</small>}
        </section>
      </header>

      <nav className="spine-phases" aria-label="Build phases">
        <section className={overviewSelected ? "spine-phase active" : "spine-phase"} data-spine-phase="overview">
          <Link aria-current={overviewSelected ? "page" : undefined} className="spine-phase-link" to="/overview">
            <Layers size={18} />
            <span><strong>Overview</strong><small>Current kit status</small></span>
          </Link>
        </section>
        <section className={setupSelected ? "spine-phase active" : "spine-phase"} data-spine-phase="setup">
          <div className="spine-phase-label">
            <Wrench size={18} />
            <span><strong>Setup</strong><small>Equipment and defaults</small></span>
          </div>
          <ul className="spine-setup-links" aria-label="Setup modules">
            {setupSpineItems.map((item) => (
              <li key={item.label}><Link to={item.to}>{item.label}</Link></li>
            ))}
          </ul>
        </section>
        <section className={runSelected ? "spine-phase active" : "spine-phase"} data-spine-phase="run">
          <Link aria-current={runSelected ? "page" : undefined} className="spine-phase-link" to="/overview?view=run">
            <Play size={18} />
            <span><strong>Run</strong><small>Build journey</small></span>
          </Link>
        </section>
      </nav>

      <footer className="navigation-spine-footer"><ModeToggle /></footer>
    </aside>
  );
}

function ActiveLabSelector({
  error,
  loading,
  onActivate,
  onApplyRuntimeEnv,
  runtimeApplyLoading,
  runtimeApplyMessage,
  state
}: {
  error: string;
  loading: boolean;
  onActivate: (profileId: string) => Promise<void>;
  onApplyRuntimeEnv: () => Promise<void>;
  runtimeApplyLoading: boolean;
  runtimeApplyMessage: string;
  state: LabProfileList | null;
}) {
  const activeProfile = state?.active_profile ?? null;
  const activeContext = state?.active_context ?? null;
  const options = state ? [state.runtime_profile, ...state.profiles] : [];
  const mismatchCount = profileMismatchItems(state).length;
  const canApplyRuntimeIps = Boolean(activeProfile && activeProfile.source === "saved" && mismatchCount > 0);

  return (
    <section className="active-lab-strip" aria-label="Active lab setup">
      <div className="active-lab-main">
        <Layers size={18} />
        <div>
          <span>Active Lab Setup</span>
          <strong>{activeProfile?.name ?? (loading ? "Loading" : "Unavailable")}</strong>
        </div>
      </div>
      <div className="active-lab-controls">
        <select
          aria-label="Active lab setup"
          disabled={loading || !state}
          onChange={(event) => onActivate(event.target.value)}
          value={activeProfile?.id ?? "runtime"}
        >
          {options.map((profile) => (
            <option key={profile.id} value={profile.id}>
              {profile.name}{profile.source === "runtime_env" ? " (runtime)" : ` v${profile.version}`}
            </option>
          ))}
        </select>
        {canApplyRuntimeIps && (
          <button
            className="primary"
            disabled={loading || runtimeApplyLoading}
            onClick={onApplyRuntimeEnv}
            title="Write active profile IPs to repo-root .env.local.real-lab"
            type="button"
          >
            <Save size={16} />
            {runtimeApplyLoading ? "Applying" : "Apply Runtime IPs"}
          </button>
        )}
      </div>
      {activeProfile && (
        <div className="active-lab-meta">
          <span>{labelize(activeContext?.topology ?? activeProfile.profile_topology)}</span>
          <span>{labelize(activeProfile.source)}</span>
          <span>{displayAddress(activeContext?.resolved_address_plan.subnet ?? activeProfile.address_plan.subnet)}</span>
          <span>{featureScopeLabel(activeContext?.enabled_features ?? activeProfile.features)}</span>
          <span>{state?.profiles.length ?? 0} saved</span>
        </div>
      )}
      {error && <p className="active-lab-error">{error}</p>}
      {runtimeApplyMessage && <p className="active-lab-success">{runtimeApplyMessage}</p>}
    </section>
  );
}

function LabProfileSummaryCard({
  context,
  profile
}: {
  context?: ActiveLabProfileContext | null;
  profile: LabProfile;
}) {
  const plan = context?.resolved_address_plan ?? profile.resolved_address_plan ?? profile.address_plan;
  const features = context?.enabled_features ?? profile.features;
  const disabled = context?.disabled_features ?? disabledFeaturesFromProfile(profile);
  const devices = profile.devices ?? {};
  return (
    <section className="status-summary-card profile-summary-card">
      <div className="status-summary-head">
        <div>
          <span className="summary-kicker">Active Lab Setup</span>
          <h2>{profile.name}</h2>
          <p>{profile.description || "Saved lab setup values drive addresses shown on setup and control pages."}</p>
        </div>
        <StatusBadge status={profile.source === "runtime_env" ? "runtime" : "current"} />
      </div>
      <div className="profile-value-strip">
        <ProviderFact label="Topology" value={labelize(context?.topology ?? profile.profile_topology)} />
        <ProviderFact label="Subnet" value={displayAddress(plan.subnet)} />
        <ProviderFact label="Gateway" value={displayAddress(profile.global_settings.gateway)} />
        <ProviderFact label="iLO" value={displayAddress(plan.ilo)} />
        <ProviderFact label="Cisco" value={displayAddress(plan.cisco_management)} />
        <ProviderFact label="ESXi" value={displayAddress(plan.esxi_management)} />
        <ProviderFact
          label="NetApp"
          value={features.netapp_enabled ? displayAddress(plan.netapp_cluster_mgmt) : disabled.netapp ?? "Not in scope"}
        />
        <ProviderFact
          label="vCenter"
          value={features.vcenter_enabled ? displayAddress(devices.vcenter) : disabled.vcenter ?? "Not in scope"}
        />
        <ProviderFact label="Control Host" value={displayAddress(plan.ansible_control_host)} />
        {devices.ups && <ProviderFact label="UPS" value={displayAddress(devices.ups)} />}
        {devices.backup_storage && <ProviderFact label="Backup Storage" value={displayAddress(devices.backup_storage)} />}
        {devices.utility_vm && <ProviderFact label="Utility VM" value={displayAddress(devices.utility_vm)} />}
      </div>
      {context?.not_in_scope_stages.length ? (
        <div className="tag-row">
          {context.not_in_scope_stages.slice(0, 6).map((stage) => (
            <span className="classification-tag read-only" key={`profile-not-in-scope-${stage}`}>
              {labelize(stage)} not in scope
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function featureScopeLabel(features: Partial<LabProfileFeatures> | null | undefined): string {
  if (!features) {
    return "Scope unknown";
  }
  const disabled = disabledFeatureLabels(features);
  return disabled.length ? `${disabled.join(", ")} not in scope` : "All configured stages in scope";
}

function disabledFeaturesFromProfile(profile: LabProfile): Record<string, string> {
  const features = profile.features ?? {};
  const disabled: Record<string, string> = {};
  if (features.netapp_enabled === false) {
    disabled.netapp = features.netapp_disabled_reason || "NetApp disabled by active profile.";
  }
  if (features.vcenter_enabled === false) {
    disabled.vcenter = features.vcenter_disabled_reason || "vCenter disabled by active profile.";
  }
  return disabled;
}

function disabledFeatureLabels(features: Partial<LabProfileFeatures>): string[] {
  const labels: string[] = [];
  if (features.netapp_enabled === false) {
    labels.push("NetApp");
  }
  if (features.vcenter_enabled === false) {
    labels.push("vCenter");
  }
  return labels;
}

function ProfileMismatchWarning({ state }: { state: LabProfileList | null }) {
  const mismatches = profileMismatchItems(state);
  if (!mismatches.length) {
    return null;
  }

  return (
    <section className="profile-mismatch-warning" aria-label="Setup mismatch warning">
      <AlertTriangle size={18} />
      <div>
        <strong>Setup mismatch: live runtime uses different values</strong>
        <p>
          Normal setup switching does not require editing `.env`. For live checks only, align the runtime
          values with the selected lab setup, then restart the backend.
        </p>
        <ul>
          {mismatches.slice(0, 4).map((item) => (
            <li key={item.label}>
              <span>{item.label}</span>
              <strong>{item.active || "Not set"}</strong>
              <em>runtime {item.runtime || "not set"}</em>
            </li>
          ))}
        </ul>
        <Link className="button-link" to="/lab-profiles">
          <Layers size={16} />
          Open Saved Setups
        </Link>
      </div>
    </section>
  );
}

function profileMismatchItems(state: LabProfileList | null): Array<{ active: string; label: string; runtime: string }> {
  const warnings = state?.active_context?.mismatch_warnings ?? [];
  if (!warnings.length) {
    return [];
  }
  return warnings.flatMap((warning) => {
    const label = asString(warning.env_field) || asString(warning.field);
    if (!label) return [];
    return [{
      active: asString(warning.expected_value) || "Not set",
      label,
      runtime: asString(warning.current_value) || "not set"
    }];
  });
}

function Dashboard() {
  const { reportIssues } = useReportIssues();
  const {
    activeContext,
    activeProfile,
    error: labProfileError,
    loading: labProfileLoading,
    onActivate: activateLabProfile,
    onApplyRuntimeEnv: applyRuntimeEnv,
    runtimeApplyLoading,
    runtimeApplyMessage,
    state: labProfileState
  } = useLabProfileContext();
  const [requests, setRequests] = useState<RequestRecord[]>([]);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [readinessByRequest, setReadinessByRequest] = useState<ReadinessMap>({});
  const [activeSection, setActiveSection] = useState<DashboardSectionId>("overview");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setError("");
      setLoading(true);
      try {
        const [nextRequests, nextRuns] = await Promise.all([api.requests(), api.workflowRuns()]);
        setRequests(nextRequests);
        setRuns(nextRuns);
        setReadinessByRequest(await loadReadinessMap(nextRequests));
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setLoading(false);
      }
    }

    load();
  }, []);

  const counts = useMemo(() => {
    return statusOrder.reduce<Record<string, number>>((acc, status) => {
      acc[status] = requests.filter((request) => request.status === status).length;
      return acc;
    }, {});
  }, [requests]);

  const queueSections = useMemo(
    () => buildRunCenterSections(requests, runs, readinessByRequest),
    [requests, runs, readinessByRequest]
  );
  const nextActionItems = queueSections
    .flatMap((section) => section.items)
    .filter((item) => item.sectionId !== "completed")
    .slice(0, 5);
  const blockedItems = queueSections.find((section) => section.id === "blocked_failed")?.items ?? [];
  const reportCriticalCount = reportIssues?.counts.critical ?? 0;
  const reportWarningCount = reportIssues?.counts.warning ?? 0;
  const reportBlockerIssues = (reportIssues?.top_issues ?? reportIssues?.issues ?? [])
    .filter((issue) => ["critical", "warning"].includes(issue.severity))
    .slice(0, 5);
  const reportBlockers = reportBlockerIssues.map(
    (issue) => `${humanizeIssueTitle(issue.title)}: ${humanizeAction(issue.next_action)}`
  );
  const blockerMessages = [...blockedItems.map((item) => item.reason), ...reportBlockers];
  const hasCurrentBlockers = blockedItems.length > 0 || reportCriticalCount > 0;
  const readyToApprove = requests.filter((request) => readinessByRequest[request.id]?.ready_for_approval).length;
  const readyToPlan = requests.filter((request) => readinessByRequest[request.id]?.ready_for_plan).length;
  const readyToExecute = requests.filter((request) => readinessByRequest[request.id]?.ready_for_execute).length;
  const latestRun = [...runs].sort((left, right) => right.updated_at.localeCompare(left.updated_at))[0] ?? null;
  const dashboardSections: SectionOption<DashboardSectionId>[] = [
    { id: "overview", label: "Overview" },
    { id: "blockers", label: "Current Blockers", status: hasCurrentBlockers ? "blocked" : reportWarningCount ? "warning" : "ready" },
    { id: "last-run", label: "Last Run", status: latestRun?.status ?? "not_run" },
    { id: "next-actions", label: "Next Actions", status: nextActionItems.length ? "ready" : "not_run" }
  ];

  return (
    <Page
      activeSection={activeSection}
      description="A quiet operating summary for the current lab and workflow queue."
      issueArea="dashboard"
      onSectionChange={(sectionId) => setActiveSection(sectionId as DashboardSectionId)}
      primaryAction={{ icon: <Layers size={16} />, label: "Open Overview", to: "/overview" }}
      sections={dashboardSections}
      title="Dashboard"
      actions={<ButtonLink to="/requests/new" icon={<Plus size={16} />} label="New VM" />}
    >
      <Feedback loading={loading} error={error} />
      <ActiveLabSelector
        error={labProfileError}
        loading={labProfileLoading}
        onActivate={activateLabProfile}
        onApplyRuntimeEnv={applyRuntimeEnv}
        runtimeApplyLoading={runtimeApplyLoading}
        runtimeApplyMessage={runtimeApplyMessage}
        state={labProfileState}
      />
      <ProfileMismatchWarning state={labProfileState} />
      {activeSection === "overview" && (
        <div className="calm-section-grid">
          {activeProfile && <LabProfileSummaryCard context={activeContext} profile={activeProfile} />}
          <StatusSummaryCard
            message={
              hasCurrentBlockers
                ? `${reportCriticalCount || blockedItems.length} current lab blocker${(reportCriticalCount || blockedItems.length) === 1 ? "" : "s"}; ${nextActionItems.length} active operator action${nextActionItems.length === 1 ? "" : "s"} across ${requests.length} request${requests.length === 1 ? "" : "s"}.`
                : `${nextActionItems.length} active operator action${nextActionItems.length === 1 ? "" : "s"} across ${requests.length} request${requests.length === 1 ? "" : "s"}.`
            }
            status={hasCurrentBlockers ? "blocked" : reportWarningCount ? "warning" : nextActionItems.length ? "ready" : "completed"}
            title={hasCurrentBlockers ? "Attention needed" : "Workflow queue is calm"}
            items={[
              { label: "Ready To Approve", value: String(readyToApprove) },
              { label: "Ready To Plan", value: String(readyToPlan) },
              { label: "Ready To Execute", value: String(readyToExecute) },
              { label: "Completed", value: String(counts.completed ?? 0) }
            ]}
          />
          <NextActionCard
            detail={nextActionItems[0]?.actionLabel ?? "Open Overview to review the active lab values."}
            to="/overview"
          />
          <BlockerSummary blockers={blockerMessages} />
        </div>
      )}
      {activeSection === "blockers" && (
        <section className="panel">
          <PanelTitle icon={<AlertTriangle size={18} />} title="Current Blockers" />
          <BlockerSummary
            blockers={[
              ...blockedItems.map((item) => `${item.title}: ${item.reason}`),
              ...reportBlockers
            ]}
          />
          <AdvancedDetails
            className="section-details"
            summary="Blocked and failed queue items"
            title="Blocked work list"
          >
            <QueueItemList
              empty="No blocked or failed work needs review."
              items={blockedItems}
            />
          </AdvancedDetails>
        </section>
      )}
      {activeSection === "last-run" && (
        <section className="panel">
          <PanelTitle icon={<History size={18} />} title="Last Run" />
          {latestRun ? (
            <>
              <StatusSummaryCard
                message={latestRun.error_message || `Last updated ${formatDateTime(latestRun.updated_at)}.`}
                status={latestRun.status}
                title={latestRun.workflow_slug}
                items={[
                  { label: "Run", value: latestRun.id },
                  { label: "Request", value: latestRun.request_id },
                  { label: "Provider", value: latestRun.provider },
                  { label: "Updated", value: formatDateTime(latestRun.updated_at) }
                ]}
              />
              <NextActionCard detail={reviewStateForRun(latestRun).message} to={`/workflow-runs/${latestRun.id}`} />
            </>
          ) : (
            <EmptyState title="No run history" detail="Workflow runs will appear here after a request is planned or executed." />
          )}
        </section>
      )}
      {activeSection === "next-actions" && (
        <section className="panel">
          <PanelTitle icon={<Route size={18} />} title="Next Actions" />
          <QueueItemList
            empty="No operator action is waiting. Completed work is available in Run Center."
            items={nextActionItems}
          />
          <AdvancedDetails className="section-details" summary="Recent requests and queue counts" title="Request details">
            <div className="handoff-summary">
              <Info label="Total Requests" value={String(requests.length)} />
              <Info label="Planned" value={String(counts.planned ?? 0)} />
              <Info label="Executing" value={String(counts.executing ?? 0)} />
              <Info label="Completed" value={String(counts.completed ?? 0)} />
            </div>
            <RequestTable readinessByRequest={readinessByRequest} requests={requests.slice(0, 10)} showNextAction />
          </AdvancedDetails>
        </section>
      )}
    </Page>
  );
}

function RequestListPage() {
  const [requests, setRequests] = useState<RequestRecord[]>([]);
  const [readinessByRequest, setReadinessByRequest] = useState<ReadinessMap>({});
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("all");
  const [environmentFilter, setEnvironmentFilter] = useState("all");
  const [siteFilter, setSiteFilter] = useState("all");
  const [ownerFilter, setOwnerFilter] = useState("all");
  const [search, setSearch] = useState("");

  async function load() {
    setError("");
    setLoading(true);
    try {
      const nextRequests = await api.requests();
      setRequests(nextRequests);
      setReadinessByRequest(await loadReadinessMap(nextRequests));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const filteredRequests = useMemo(
    () =>
      requests.filter((request) => {
        const normalizedSearch = search.trim().toLowerCase();
        if (statusFilter !== "all" && request.status !== statusFilter) return false;
        if (environmentFilter !== "all" && request.environment !== environmentFilter) return false;
        if (siteFilter !== "all" && request.site !== siteFilter) return false;
        if (ownerFilter !== "all" && request.owner !== ownerFilter) return false;
        if (!normalizedSearch) return true;
        return (
          request.id.toLowerCase().includes(normalizedSearch) ||
          request.vm_deploy.vm_name.toLowerCase().includes(normalizedSearch)
        );
      }),
    [environmentFilter, ownerFilter, requests, search, siteFilter, statusFilter]
  );
  const statusOptions = uniqueOptions(requests.map((request) => request.status));
  const environmentOptions = uniqueOptions(requests.map((request) => request.environment));
  const siteOptions = uniqueOptions(requests.map((request) => request.site));
  const ownerOptions = uniqueOptions(requests.map((request) => request.owner));

  return (
    <Page
      title="VM Requests"
      actions={
        <>
          <button onClick={load} disabled={loading}>
            <RefreshCw size={16} />
            Refresh
          </button>
          <ButtonLink to="/requests/new" icon={<Plus size={16} />} label="New VM" />
        </>
      }
    >
      <Feedback loading={loading && !requests.length} error={error} />
      <section className="panel">
        <PanelTitle icon={<ClipboardList size={18} />} title="Request Filters" />
        <div className="request-filter-grid">
          <Field label="Search">
            <input
              placeholder="VM name or request ID"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </Field>
          <Field label="Status">
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="all">All statuses</option>
              {statusOptions.map((status) => (
                <option key={status} value={status}>
                  {labelize(status)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Environment">
            <select value={environmentFilter} onChange={(event) => setEnvironmentFilter(event.target.value)}>
              <option value="all">All environments</option>
              {environmentOptions.map((environment) => (
                <option key={environment} value={environment}>
                  {environment}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Site">
            <select value={siteFilter} onChange={(event) => setSiteFilter(event.target.value)}>
              <option value="all">All sites</option>
              {siteOptions.map((site) => (
                <option key={site} value={site}>
                  {site}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Owner">
            <select value={ownerFilter} onChange={(event) => setOwnerFilter(event.target.value)}>
              <option value="all">All owners</option>
              {ownerOptions.map((owner) => (
                <option key={owner} value={owner}>
                  {owner}
                </option>
              ))}
            </select>
          </Field>
        </div>
      </section>
      <section className="panel">
        <PanelTitle icon={<Layers size={18} />} title={`Requests (${filteredRequests.length})`} />
        <RequestTable
          readinessByRequest={readinessByRequest}
          requests={filteredRequests}
          showBlocked
          showNextAction
        />
      </section>
    </Page>
  );
}

function LabSetupPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { reportIssues } = useReportIssues();
  const {
    error: labProfileError,
    loading: labProfileLoading,
    onActivate: activateLabProfile,
    onApplyRuntimeEnv: applyRuntimeEnv,
    onReload: reloadLabProfiles,
    runtimeApplyLoading,
    runtimeApplyMessage,
    state: labProfileState
  } = useLabProfileContext();
  const { isAdvancedMode } = useUiMode();
  const [stages, setStages] = useState<WorkflowStage[]>([]);
  const [selectedStageId, setSelectedStageId] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [runningWorkflowActionId, setRunningWorkflowActionId] = useState("");
  const [workflowActionRunResults, setWorkflowActionRunResults] = useState<Record<string, WorkflowActionRun>>({});

  async function load() {
    setError("");
    setLoading(true);
    try {
      const nextStages = await api.workflowStages();
      setStages(nextStages);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    const queryStage = new URLSearchParams(location.search).get("stage") ?? "";
    if (queryStage && stages.some((stage) => stage.stage_id === queryStage)) {
      setSelectedStageId(queryStage);
    } else if (!selectedStageId && stages.length) {
      setSelectedStageId(stages[0].stage_id);
    }
  }, [location.search, selectedStageId, stages]);

  function selectStage(stageId: string) {
    setSelectedStageId(stageId);
    navigate(`/overview?stage=${encodeURIComponent(stageId)}`);
  }

  async function refreshSetup() {
    await Promise.all([load(), reloadLabProfiles()]);
  }

  async function runWorkflowAction(action: WorkflowAction, request?: WorkflowActionRunRequest) {
    setError("");
    setRunningWorkflowActionId(action.action_id);
    try {
      const result = await api.runWorkflowAction(action.action_id, request);
      setWorkflowActionRunResults((current) => ({ ...current, [action.action_id]: result }));
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunningWorkflowActionId("");
    }
  }

  const issues = reportIssues?.issues ?? [];
  const issueCountsByStage = workflowIssueCountsByStage(stages, issues);
  const issueCountsByAction = workflowIssueCountsByAction(issues);
  const selectedStage = stages.find((stage) => stage.stage_id === selectedStageId) ?? stages[0] ?? null;
  const selectedStageIssues = selectedStage ? issues.filter((issue) => reportIssueMatchesStageId(issue, selectedStage.stage_id)) : [];
  const stageSnapshot = selectedStage ? workflowStageSnapshot(selectedStage) : null;
  const primary = selectedStage ? primaryWorkflowAction(selectedStage) : null;
  const minimalStageItems = stages.map((stage) =>
    minimalStageItemFromWorkflowStage(stage, issueCountsByStage[stage.stage_id] ?? stage.blocked_count)
  );

  return (
    <Page
      description="Set the active lab name, IP plan, and shared defaults before running registry checks."
      primaryAction={{ icon: <RefreshCw size={16} />, label: "Refresh", onClick: refreshSetup, disabled: loading || labProfileLoading }}
      title="Lab Setup"
      actions={
        isAdvancedMode ? (
          <>
            <Link className="button-link" to="/run-center">
              <Workflow size={16} />
              Run Center
            </Link>
            <Link className="button-link" to="/validation-reports">
              <FileText size={16} />
              Validation & Reports
            </Link>
          </>
        ) : (
          <Link className="button-link" to="/run-center">
            <Workflow size={16} />
            Run Center
          </Link>
        )
      }
    >
      <ActiveLabSelector
        error={labProfileError}
        loading={labProfileLoading}
        onActivate={activateLabProfile}
        onApplyRuntimeEnv={applyRuntimeEnv}
        runtimeApplyLoading={runtimeApplyLoading}
        runtimeApplyMessage={runtimeApplyMessage}
        state={labProfileState}
      />
      <ProfileMismatchWarning state={labProfileState} />
      <ActiveLabSetupOverview state={labProfileState} />
      <section className="panel lab-setup-workflow-section">
        <div className="readiness-head">
          <div>
            <PanelTitle icon={<Workflow size={18} />} title="Readiness Workflow" />
            <p className="muted">Registry-backed checks remain below the saved lab setup so live runs use the selected profile.</p>
          </div>
        </div>
      <Feedback loading={loading && !stages.length} error={error} />
      {stages.length ? (
        <>
          <div className="calm-section-grid">
            <StatusSummaryCard
              message={
                selectedStage
                  ? isAdvancedMode
                    ? `${selectedStage.label}: ${workflowStageRowSummary(selectedStage)}`
                    : minimalStageItemFromWorkflowStage(selectedStage, issueCountsByStage[selectedStage.stage_id] ?? selectedStage.blocked_count).one_line_summary
                  : "Registry stages are loading."
              }
              status={selectedStage?.current_state ?? "not_checked"}
              title={selectedStage ? minimalStageLabel(selectedStage.stage_id, selectedStage.label) : "Lab setup"}
              items={
                isAdvancedMode
                  ? [
                      { label: "Stages", value: String(stages.length) },
                      { label: "Actions", value: String(stages.reduce((total, stage) => total + stage.action_count, 0)) },
                      { label: "Issues", value: String(Object.values(issueCountsByStage).reduce((total, count) => total + count, 0)) },
                      { label: "Freshness", value: labelize(stageSnapshot?.freshness ?? "unknown") }
                    ]
                  : [
                      { label: "Stages", value: String(stages.length) },
                      { label: "Blockers", value: String(Object.values(issueCountsByStage).reduce((total, count) => total + count, 0)) },
                      { label: "Proof", value: selectedStage ? String(workflowStageEvidenceArtifacts(selectedStage).length) : "0" },
                      { label: "Checked", value: stageSnapshot?.lastChecked ? formatDateTime(stageSnapshot.lastChecked) : "Not checked" }
                    ]
              }
            />
            <NextActionCard
              detail={primary?.next_action ?? "Select a registry stage to see available actions."}
              to={primary ? `/control-center?section=action-catalog&action=${encodeURIComponent(primary.action_id)}` : undefined}
            />
            <BlockerSummary
              blockers={selectedStage ? stageBlockers(selectedStage) : []}
              warnings={selectedStage ? stageWarnings(selectedStage) : []}
              empty={isAdvancedMode ? "No current registry blocker is reported for the selected stage." : "No current blocker is reported for this step."}
            />
          </div>
          {isAdvancedMode ? (
            <section className="registry-setup-layout">
              <WorkflowStageList
                issuesByStage={issueCountsByStage}
                onCopy={copyWorkflowActionToClipboard}
                onSelect={selectStage}
                selectedStageId={selectedStage?.stage_id ?? ""}
                stages={stages}
              />
              <StageDetailPanel
                actionIssueCounts={issueCountsByAction}
                onCopy={copyWorkflowActionToClipboard}
                onRun={runWorkflowAction}
                runningActionId={runningWorkflowActionId}
                stage={selectedStage ?? undefined}
                stageIssues={selectedStageIssues}
                runResults={workflowActionRunResults}
              />
            </section>
          ) : (
            <section className="minimal-setup-layout">
              <MinimalStageList
                items={minimalStageItems}
                onSelect={selectStage}
                selectedId={selectedStage?.stage_id ?? ""}
              />
              <MinimalWorkflowStageDetail
                actionIssueCounts={issueCountsByAction}
                onCopy={copyWorkflowActionToClipboard}
                onRun={runWorkflowAction}
                runningActionId={runningWorkflowActionId}
                stage={selectedStage ?? undefined}
                stageIssues={selectedStageIssues}
                runResults={workflowActionRunResults}
              />
            </section>
          )}
        </>
      ) : (
        <section>
          <EmptyState title="No workflow registry data" detail="Refresh after the backend registry endpoint is available." />
        </section>
      )}
      </section>
    </Page>
  );
}

function ActiveLabSetupOverview({ state }: { state: LabProfileList | null }) {
  const active = state?.active_profile ?? null;
  const address = active?.resolved_address_plan ?? active?.address_plan ?? blankLabAddressPlan();
  const global = active?.global_settings;
  const features = active?.features;
  if (!active) {
    return <EmptyState title="No active lab setup" detail="Choose an active lab setup before running device checks." />;
  }
  const rows: WorkflowSummaryItem[] = [
    { label: "Subnet", value: displayAddress(address.subnet) },
    { label: "Gateway", value: displayAddress(global?.gateway) },
    { label: "DNS", value: global?.dns_servers.join(", ") || "Not set" },
    { label: "NTP", value: global?.ntp_servers.join(", ") || "Not set" },
    { label: "VLAN", value: global?.vlan_id || "Not set" },
    { label: "MTU", value: global?.mtu ? String(global.mtu) : "Not set" },
    { label: "Storage", value: features?.storage_protocol?.toUpperCase() || "Not set" },
    { label: "IPv6", value: features?.disable_ipv6 ? "Disabled" : "Allowed" },
    { label: "Legacy Protocols", value: features?.block_legacy_protocols ? "Blocked" : "Allowed" },
    { label: "iLO", value: displayAddress(address.ilo) },
    { label: "Server NIC", value: displayAddress(address.server_embedded_nic) },
    { label: "ESXi", value: displayAddress(address.esxi_management) },
    { label: "Cisco", value: displayAddress(address.cisco_management) },
    { label: "Control Host", value: displayAddress(address.ansible_control_host) },
    ...(features?.netapp_enabled
      ? [
          { label: "NetApp Cluster", value: displayAddress(address.netapp_cluster_mgmt) },
          { label: "NetApp Node A", value: displayAddress(address.netapp_node_a_mgmt) },
          { label: "NetApp Node B", value: displayAddress(address.netapp_node_b_mgmt) },
          { label: "NetApp SVM", value: displayAddress(address.netapp_svm_mgmt) }
        ]
      : [])
  ];
  return (
    <section className="panel lab-setup-overview">
      <div className="readiness-head">
        <div>
          <PanelTitle icon={<Layers size={18} />} title="Active Lab Setup" />
          <p className="muted">{active.description || "Saved values drive device defaults across the app."}</p>
        </div>
        <StatusBadge status={active.source === "saved" ? "current" : "not_checked"} />
      </div>
      <div className="config-compact-table lab-setup-config-table">
        {rows.map((row) => (
          <div key={`setup-overview-${row.label}`}>
            <span>{row.label}</span>
            <strong>{row.value}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

function RunCenter() {
  const { isAdvancedMode } = useUiMode();
  const { activeContext, activeProfile } = useLabProfileContext();
  const netappInScope = activeContext?.enabled_features.netapp_enabled ?? activeProfile?.features.netapp_enabled ?? true;
  const [requests, setRequests] = useState<RequestRecord[]>([]);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [workflowStages, setWorkflowStages] = useState<WorkflowStage[]>([]);
  const [readinessByRequest, setReadinessByRequest] = useState<ReadinessMap>({});
  const [netappPlanPreview, setNetappPlanPreview] = useState<NetAppPlanPreview | null>(null);
  const [netappArtifacts, setNetappArtifacts] = useState<NetAppProviderArtifact[]>([]);
  const [netappConsoleReadiness, setNetappConsoleReadiness] = useState<NetAppConsoleReadiness | null>(null);
  const [netappConsoleDiscovery, setNetappConsoleDiscovery] = useState<ProviderProbeResult | null>(null);
  const [netappConsoleState, setNetappConsoleState] = useState<ProviderProbeResult | null>(null);
  const [netappLiveState, setNetappLiveState] = useState<ProviderProbeResult | null>(null);
  const [netappAddressPlan, setNetappAddressPlan] = useState<ProviderProbeResult | null>(null);
  const [netappNfsVcenterReadiness, setNetappNfsVcenterReadiness] = useState<ProviderProbeResult | null>(null);
  const [netappNfsSetupPreview, setNetappNfsSetupPreview] = useState<ProviderProbeResult | null>(null);
  const [netappNfsSetupApply, setNetappNfsSetupApply] = useState<ProviderProbeResult | null>(null);
  const [netappNfsSetupValidation, setNetappNfsSetupValidation] = useState<ProviderProbeResult | null>(null);
  const [netappSetupPreview, setNetappSetupPreview] = useState<ProviderProbeResult | null>(null);
  const [netappSetupApply, setNetappSetupApply] = useState<ProviderProbeResult | null>(null);
  const [netappUpgradeInventory, setNetappUpgradeInventory] = useState<ProviderProbeResult | null>(null);
  const [netappUpgradePlan, setNetappUpgradePlan] = useState<ProviderProbeResult | null>(null);
  const [netappUpgradeValidation, setNetappUpgradeValidation] = useState<ProviderProbeResult | null>(null);
  const [netappUpgradeApply, setNetappUpgradeApply] = useState<ProviderProbeResult | null>(null);
  const [netappReadinessComparison, setNetappReadinessComparison] = useState<NetAppReadinessComparison | null>(null);
  const [netappUpgradeReadiness, setNetappUpgradeReadiness] = useState<NetAppUpgradeReadiness | null>(null);
  const [netappAction, setNetappAction] = useState<string>("");
  const [activeSection, setActiveSection] = useState<RunCenterSectionId>("guided");
  const [activeQueueSection, setActiveQueueSection] = useState<QueueSectionId>("needs_approval");
  const [selectedRunChoiceIds, setSelectedRunChoiceIds] = useState<string[]>([
    "ilo",
    "storage",
    "esxi",
    "cisco",
    "netapp",
    "verification"
  ]);
  const [selectedQueueKey, setSelectedQueueKey] = useState("");
  const [error, setError] = useState("");
  const [netappError, setNetappError] = useState("");
  const [loading, setLoading] = useState(true);
  const [netappLoading, setNetappLoading] = useState(false);
  const [runningWorkflowActionId, setRunningWorkflowActionId] = useState("");
  const [workflowActionRunResults, setWorkflowActionRunResults] = useState<Record<string, WorkflowActionRun>>({});

  async function load() {
    setError("");
    setLoading(true);
    try {
      const [nextRequests, nextRuns, nextWorkflowStages] = await Promise.all([
        api.requests(),
        api.workflowRuns(),
        api.workflowStages()
      ]);
      setRequests(nextRequests);
      setRuns(nextRuns);
      setWorkflowStages(nextWorkflowStages);
      setLoading(false);
      api.providers()
        .then(setProviders)
        .catch((err: Error) => setError((current) => current || err.message));
      setReadinessByRequest(await loadReadinessMap(nextRequests));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function loadNetAppPlanPreview() {
    setNetappError("");
    setNetappLoading(true);
    try {
      const [
        nextPreview,
        nextConsoleReadiness,
        nextConsoleDiscovery,
        nextConsoleState,
        nextLiveState,
        nextAddressPlan,
        nextNfsVcenterReadiness,
        nextNfsSetupPreview,
        nextSetupPreview,
        nextUpgradeInventory,
        nextUpgradePlan,
        nextReadinessComparison,
        nextUpgradeReadiness,
        nextArtifacts
      ] = await Promise.all([
        api.netappPlanPreview(),
        api.netappConsoleReadiness(),
        api.netappConsoleDiscovery(),
        api.netappConsoleReadState(),
        api.netappLiveState(),
        api.netappAddressPlan(),
        api.netappNfsVcenterReadiness(),
        api.netappNfsSetupPreview(),
        api.netappSetupPreview(),
        api.netappOntapUpgradeInventory(),
        api.netappOntapUpgradePlan(),
        api.netappReadinessComparison(),
        api.netappUpgradeReadiness(),
        api.netappArtifacts()
      ]);
      setNetappPlanPreview(nextPreview);
      setNetappConsoleReadiness(nextConsoleReadiness);
      setNetappConsoleDiscovery(nextConsoleDiscovery);
      setNetappConsoleState(nextConsoleState);
      setNetappLiveState(nextLiveState);
      setNetappAddressPlan(nextAddressPlan);
      setNetappNfsVcenterReadiness(nextNfsVcenterReadiness);
      setNetappNfsSetupPreview(nextNfsSetupPreview);
      setNetappSetupPreview(nextSetupPreview);
      setNetappUpgradeInventory(nextUpgradeInventory);
      setNetappUpgradePlan(nextUpgradePlan);
      setNetappReadinessComparison(nextReadinessComparison);
      setNetappUpgradeReadiness(nextUpgradeReadiness);
      setNetappArtifacts(nextArtifacts);
    } catch (err) {
      setNetappError((err as Error).message);
    } finally {
      setNetappLoading(false);
    }
  }

  async function runNetAppConsoleDiscovery() {
    setNetappError("");
    setNetappAction("console-discovery");
    try {
      const result = await api.runNetappConsoleDiscovery();
      setNetappConsoleDiscovery(result);
      await loadNetAppPlanPreview();
    } catch (err) {
      setNetappError((err as Error).message);
    } finally {
      setNetappAction("");
    }
  }

  async function runNetAppConsoleReadState() {
    setNetappError("");
    setNetappAction("console-read-state");
    try {
      const result = await api.runNetappConsoleReadState();
      setNetappConsoleState(result);
      await loadNetAppPlanPreview();
    } catch (err) {
      setNetappError((err as Error).message);
    } finally {
      setNetappAction("");
    }
  }

  async function runNetAppLiveState() {
    setNetappError("");
    setNetappAction("live-state");
    try {
      const result = await api.runNetappLiveState();
      setNetappLiveState(result);
      await loadNetAppPlanPreview();
    } catch (err) {
      setNetappError((err as Error).message);
    } finally {
      setNetappAction("");
    }
  }

  async function validateNetAppSetup() {
    setNetappError("");
    setNetappAction("validate-setup");
    try {
      const result = await api.validateNetappSetup();
      setNetappLiveState(result);
      await loadNetAppPlanPreview();
    } catch (err) {
      setNetappError((err as Error).message);
    } finally {
      setNetappAction("");
    }
  }

  async function runNetAppAddressPlan() {
    setNetappError("");
    setNetappAction("address-plan");
    try {
      const result = await api.runNetappAddressPlan();
      setNetappAddressPlan(result);
      await loadNetAppPlanPreview();
    } catch (err) {
      setNetappError((err as Error).message);
    } finally {
      setNetappAction("");
    }
  }

  async function runNetAppSetupPreview() {
    setNetappError("");
    setNetappAction("setup-preview");
    try {
      const result = await api.netappSetupPreview();
      setNetappSetupPreview(result);
      await loadNetAppPlanPreview();
    } catch (err) {
      setNetappError((err as Error).message);
    } finally {
      setNetappAction("");
    }
  }

  async function runNetAppSetupApply() {
    setNetappError("");
    setNetappAction("setup-apply");
    try {
      const result = await api.runNetappSetupApply();
      setNetappSetupApply(result);
      await loadNetAppPlanPreview();
    } catch (err) {
      setNetappError((err as Error).message);
    } finally {
      setNetappAction("");
    }
  }

  async function runNetAppNfsSetupPreview() {
    setNetappError("");
    setNetappAction("nfs-setup-preview");
    try {
      const result = await api.netappNfsSetupPreview();
      setNetappNfsSetupPreview(result);
      await loadNetAppPlanPreview();
    } catch (err) {
      setNetappError((err as Error).message);
    } finally {
      setNetappAction("");
    }
  }

  async function runNetAppNfsSetupApply() {
    setNetappError("");
    setNetappAction("nfs-setup-apply");
    try {
      const result = await api.runNetappNfsSetupApply();
      setNetappNfsSetupApply(result);
      await loadNetAppPlanPreview();
    } catch (err) {
      setNetappError((err as Error).message);
    } finally {
      setNetappAction("");
    }
  }

  async function validateNetAppNfsSetup() {
    setNetappError("");
    setNetappAction("nfs-setup-validate");
    try {
      const result = await api.validateNetappNfsSetup();
      setNetappNfsSetupValidation(result);
      await loadNetAppPlanPreview();
    } catch (err) {
      setNetappError((err as Error).message);
    } finally {
      setNetappAction("");
    }
  }

  async function runNetAppUpgradeInventory() {
    setNetappError("");
    setNetappAction("upgrade-inventory");
    try {
      const result = await api.netappOntapUpgradeInventory();
      setNetappUpgradeInventory(result);
    } catch (err) {
      setNetappError((err as Error).message);
    } finally {
      setNetappAction("");
    }
  }

  async function runNetAppUpgradePlan() {
    setNetappError("");
    setNetappAction("upgrade-plan");
    try {
      const result = await api.netappOntapUpgradePlan();
      setNetappUpgradePlan(result);
    } catch (err) {
      setNetappError((err as Error).message);
    } finally {
      setNetappAction("");
    }
  }

  async function validateNetAppUpgrade() {
    setNetappError("");
    setNetappAction("upgrade-validate");
    try {
      const result = await api.validateNetappOntapUpgrade();
      setNetappUpgradeValidation(result);
      await runNetAppUpgradePlan();
    } catch (err) {
      setNetappError((err as Error).message);
    } finally {
      setNetappAction("");
    }
  }

  async function runNetAppUpgradeApply() {
    setNetappError("");
    setNetappAction("upgrade-apply");
    try {
      const result = await api.runNetappOntapUpgradeApply();
      setNetappUpgradeApply(result);
      await runNetAppUpgradePlan();
    } catch (err) {
      setNetappError((err as Error).message);
    } finally {
      setNetappAction("");
    }
  }

  async function runWorkflowAction(action: WorkflowAction, request?: WorkflowActionRunRequest) {
    setError("");
    setRunningWorkflowActionId(action.action_id);
    try {
      const result = await api.runWorkflowAction(action.action_id, request);
      setWorkflowActionRunResults((current) => ({ ...current, [action.action_id]: result }));
      await load();
      if (activeSection === "netapp") {
        await loadNetAppPlanPreview();
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunningWorkflowActionId("");
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (netappInScope) {
      return;
    }
    setSelectedRunChoiceIds((current) => current.filter((id) => id !== "netapp"));
    if (activeSection === "netapp" && !isAdvancedMode) {
      setActiveSection("guided");
    }
  }, [activeSection, isAdvancedMode, netappInScope]);

  useEffect(() => {
    if (activeSection === "netapp" && !netappPlanPreview && !netappLoading) {
      loadNetAppPlanPreview();
    }
  }, [activeSection, netappPlanPreview, netappLoading]);

  const queueSections = useMemo(
    () => buildRunCenterSections(requests, runs, readinessByRequest),
    [requests, runs, readinessByRequest]
  );
  const queueItems = queueSections.flatMap((section) => section.items);
  const queueItemKeySignature = queueItems.map((item) => item.key).join("|");
  const firstActionableKey =
    queueItems.find((item) => item.sectionId !== "completed")?.key ?? queueItems[0]?.key ?? "";

  useEffect(() => {
    if (!firstActionableKey) {
      setSelectedQueueKey("");
      return;
    }

    setSelectedQueueKey((current) => {
      const currentItem = queueItems.find((item) => item.key === current);
      if (!currentItem || (currentItem.sectionId === "completed" && firstActionableKey)) {
        return firstActionableKey;
      }
      return current;
    });
    const preferredItem = queueItems.find((item) => item.key === firstActionableKey);
    if (preferredItem) {
      setActiveQueueSection(preferredItem.sectionId);
    }
  }, [firstActionableKey, queueItemKeySignature]);

  const selectedItem = queueItems.find((item) => item.key === selectedQueueKey) ?? queueItems[0] ?? null;
  const selectedQueueSection = selectedItem?.sectionId ?? "needs_approval";
  const selectedRun = selectedItem?.run ?? null;
  const selectedRequest = selectedItem?.request ?? null;
  const stageEvents = selectedRun ? stageEventsForRun(selectedRun) : [];
  const review = selectedRun ? reviewStateForRun(selectedRun) : null;
  const needsApproval = queueSections.find((section) => section.id === "needs_approval")?.items.length ?? 0;
  const readyToPlan = queueSections.find((section) => section.id === "approved_ready_to_plan")?.items.length ?? 0;
  const readyToExecute = queueSections.find((section) => section.id === "planned_ready_to_execute")?.items.length ?? 0;
  const executing = queueSections.find((section) => section.id === "executing")?.items.length ?? 0;
  const blocked = queueSections.find((section) => section.id === "blocked_failed")?.items.length ?? 0;
  const completed = queueSections.find((section) => section.id === "completed")?.items.length ?? 0;
  const activeQueue = queueSections.find((section) => section.id === activeQueueSection) ?? queueSections[0];
  const totalActiveWork = needsApproval + readyToPlan + readyToExecute + executing + blocked;
  const runChoices = buildRunChoices({
    onOpenNetapp: () => setActiveSection("netapp"),
    onOpenQueue: () => setActiveSection("guided"),
    onOpenSelected: () => setActiveSection("guided"),
    providers,
    selectedItem,
    totalWork: totalActiveWork
  }).filter((choice) => choice.id !== "netapp" || netappInScope || isAdvancedMode);
  const stageById = new Map(workflowStages.map((stage) => [stage.stage_id, stage]));
  const selectedChoices = runChoices.filter((choice) => selectedRunChoiceIds.includes(choice.id));
  const selectedBlockers = selectedChoices.flatMap((choice) =>
    choice.blockers.map((blocker) => `${choice.title}: ${blocker}`)
  );
  const focusChoiceBySection: Partial<Record<RunCenterSectionId, RunChoice>> = {
    cisco: runChoices.find((choice) => choice.id === "cisco"),
    ilo: runChoices.find((choice) => choice.id === "ilo"),
    raid: runChoices.find((choice) => choice.id === "storage"),
    esxi: runChoices.find((choice) => choice.id === "esxi"),
    netapp: runChoices.find((choice) => choice.id === "netapp")
  };
  const registryStageBySection: Partial<Record<RunCenterSectionId, WorkflowStage | undefined>> = {
    cisco: stageById.get("cisco"),
    ilo: stageById.get("ilo"),
    raid: stageById.get("raid"),
    esxi: stageById.get("esxi"),
    netapp: stageById.get("netapp")
  };
  const runCenterSections: SectionOption<RunCenterSectionId>[] = [
    { id: "guided", label: "Guided Build", status: totalActiveWork ? "ready" : "not_run" },
    { id: "cisco", label: "Cisco", status: registryStageBySection.cisco?.current_state ?? (focusChoiceBySection.cisco?.blockers.length ? "blocked" : "ready") },
    { id: "ilo", label: "HPE / iLO", status: registryStageBySection.ilo?.current_state ?? (focusChoiceBySection.ilo?.blockers.length ? "blocked" : "ready") },
    { id: "raid", label: "RAID", status: registryStageBySection.raid?.current_state ?? (focusChoiceBySection.raid?.blockers.length ? "blocked" : "ready") },
    { id: "esxi", label: "ESXi", status: registryStageBySection.esxi?.current_state ?? (focusChoiceBySection.esxi?.blockers.length ? "blocked" : "ready") },
    ...(netappInScope || isAdvancedMode ? [{
      id: "netapp",
      label: "NetApp",
      status:
        registryStageBySection.netapp?.current_state ??
        ((netappPlanPreview?.blockers.length ?? 0) > 0 || (focusChoiceBySection.netapp?.blockers.length ?? 0) > 0
          ? "blocked"
          : "ready")
    } as SectionOption<RunCenterSectionId>] : [])
  ];
  const minimalRunStageItems = workflowStages.map((stage) =>
    minimalStageItemFromWorkflowStage(stage, stage.blocked_count)
  );

  return (
    <Page
      activeSection={activeSection}
      description="A guided live-lab run surface. Provider-specific detail is available by section."
      issueArea="run-center"
      onSectionChange={(sectionId) => setActiveSection(sectionId as RunCenterSectionId)}
      primaryAction={{ icon: <Route size={16} />, label: selectedItem?.actionLabel ?? "Review Guided Build", onClick: () => setActiveSection("guided") }}
      sections={runCenterSections}
      title="Run Center"
      actions={
        <>
          <button onClick={activeSection === "netapp" ? loadNetAppPlanPreview : load} disabled={activeSection === "netapp" ? netappLoading : loading}>
            <RefreshCw size={16} />
            Refresh
          </button>
        </>
      }
    >
      <Feedback loading={loading} error={error} />
      {activeSection === "guided" && (
        <>
          <div className="calm-section-grid">
            <StatusSummaryCard
              message={`${selectedChoices.length} build step${selectedChoices.length === 1 ? "" : "s"} selected. ${totalActiveWork} queue item${totalActiveWork === 1 ? "" : "s"} need attention.`}
              status={selectedBlockers.length ? "blocked" : totalActiveWork ? "ready" : "not_run"}
              title="Guided build"
              items={[
                { label: "Needs Approval", value: String(needsApproval) },
                { label: "Ready To Plan", value: String(readyToPlan) },
                { label: "Ready To Execute", value: String(readyToExecute) },
                { label: "Completed", value: String(completed) }
              ]}
            />
            <NextActionCard
              detail={selectedItem?.actionLabel ?? "Choose build stages or create a VM request."}
              to={selectedItem ? queueItemLink(selectedItem) : "/requests/new"}
            />
            <BlockerSummary blockers={selectedBlockers} />
          </div>
          {isAdvancedMode ? (
            <WorkflowStageList
              onCopy={copyWorkflowActionToClipboard}
              onSelect={(stageId) => {
                const nextSection = stageId === "ilo" ? "ilo" : stageId;
                if (["cisco", "ilo", "raid", "esxi", "netapp"].includes(nextSection)) {
                  setActiveSection(nextSection as RunCenterSectionId);
                }
              }}
              stages={workflowStages}
            />
          ) : (
            <MinimalStageList
              items={minimalRunStageItems.filter((item) => item.id !== "reports")}
              onSelect={(stageId) => {
                const nextSection = stageId === "ilo" ? "ilo" : stageId;
                if (["cisco", "ilo", "raid", "esxi", "netapp"].includes(nextSection)) {
                  setActiveSection(nextSection as RunCenterSectionId);
                }
              }}
              selectedId=""
            />
          )}
          <AdvancedDetails
            className="section-details"
            summary="Stage picker, work queue, and selected request detail"
            title="Guided build details"
          >
            <RunCenterRunChooser
              onOpenQueue={() => setActiveQueueSection(selectedQueueSection)}
              onOpenNetapp={() => setActiveSection("netapp")}
              onOpenSelected={() => setActiveQueueSection(selectedQueueSection)}
              providers={providers}
              selectedItem={selectedItem}
              selectedRunChoiceIds={selectedRunChoiceIds}
              setSelectedRunChoiceIds={setSelectedRunChoiceIds}
              totalWork={totalActiveWork}
            />
            <section className="run-center-pipeline">
              {queueSections.map((section) => (
                <button
                  className={section.id === activeQueueSection ? "active" : ""}
                  key={section.id}
                  onClick={() => setActiveQueueSection(section.id)}
                  type="button"
                >
                  <span>{section.title}</span>
                  <strong>{section.items.length}</strong>
                </button>
              ))}
            </section>
            <section className="panel run-center-focus-panel">
              <div className="readiness-head">
                <PanelTitle icon={<ClipboardList size={18} />} title={activeQueue.title} />
                <span className="muted">{activeQueue.items.length} item{activeQueue.items.length === 1 ? "" : "s"}</span>
              </div>
              <QueueItemList
                empty={activeQueue.empty}
                items={activeQueue.items}
                onSelect={(key) => setSelectedQueueKey(key)}
                selectedKey={selectedItem?.key ?? ""}
              />
            </section>
            <RunCenterSelectedWork
              review={review}
              selectedItem={selectedItem}
              selectedRequest={selectedRequest}
              selectedRun={selectedRun}
              stageEvents={stageEvents}
            />
          </AdvancedDetails>
        </>
      )}
      {["cisco", "ilo", "raid", "esxi"].includes(activeSection) && (
        <>
          <RunCenterSectionFocus choice={focusChoiceBySection[activeSection]} />
          {isAdvancedMode ? (
            <StageDetailPanel
              onCopy={copyWorkflowActionToClipboard}
              onRun={runWorkflowAction}
              runningActionId={runningWorkflowActionId}
              runResults={workflowActionRunResults}
              stage={registryStageBySection[activeSection]}
            />
          ) : (
            <MinimalWorkflowStageDetail
              onCopy={copyWorkflowActionToClipboard}
              onRun={runWorkflowAction}
              runningActionId={runningWorkflowActionId}
              runResults={workflowActionRunResults}
              stage={registryStageBySection[activeSection]}
            />
          )}
        </>
      )}
      {activeSection === "netapp" && (
        <>
          {isAdvancedMode && <RunCenterSectionFocus choice={focusChoiceBySection.netapp} />}
          {isAdvancedMode ? (
            <>
              <StageDetailPanel
                onCopy={copyWorkflowActionToClipboard}
                onRun={runWorkflowAction}
                runningActionId={runningWorkflowActionId}
                runResults={workflowActionRunResults}
                stage={registryStageBySection.netapp}
              />
              <AdvancedDetails
                className="section-details"
                summary="NetApp planned targets, live readiness comparison, console result, and artifacts"
                title="NetApp live readiness details"
              >
                <NetAppRunCenterPreview
                  addressPlan={netappAddressPlan}
                  artifacts={netappArtifacts}
                  consoleDiscovery={netappConsoleDiscovery}
                  consoleReadiness={netappConsoleReadiness}
                  consoleState={netappConsoleState}
                  error={netappError}
                  loading={netappLoading}
                  liveState={netappLiveState}
                  nfsVcenterReadiness={netappNfsVcenterReadiness}
                  nfsSetupApply={netappNfsSetupApply}
                  nfsSetupPreview={netappNfsSetupPreview}
                  nfsSetupValidation={netappNfsSetupValidation}
                  netappAction={netappAction}
                  onRunConsoleDiscovery={runNetAppConsoleDiscovery}
                  onRunConsoleReadState={runNetAppConsoleReadState}
                  onRunAddressPlan={runNetAppAddressPlan}
                  onRunLiveState={runNetAppLiveState}
                  onRunNfsSetupApply={runNetAppNfsSetupApply}
                  onRunNfsSetupPreview={runNetAppNfsSetupPreview}
                  onRunSetupApply={runNetAppSetupApply}
                  onRunSetupPreview={runNetAppSetupPreview}
                  onRunUpgradeApply={runNetAppUpgradeApply}
                  onRunUpgradeInventory={runNetAppUpgradeInventory}
                  onRunUpgradePlan={runNetAppUpgradePlan}
                  onValidateUpgrade={validateNetAppUpgrade}
                  onValidateNfsSetup={validateNetAppNfsSetup}
                  onValidateSetup={validateNetAppSetup}
                  onRefresh={loadNetAppPlanPreview}
                  preview={netappPlanPreview}
                  readinessComparison={netappReadinessComparison}
                  setupApply={netappSetupApply}
                  setupPreview={netappSetupPreview}
                  upgradeApply={netappUpgradeApply}
                  upgradeInventory={netappUpgradeInventory}
                  upgradePlan={netappUpgradePlan}
                  upgradeReadiness={netappUpgradeReadiness}
                  upgradeValidation={netappUpgradeValidation}
                />
              </AdvancedDetails>
            </>
          ) : (
            <MinimalNetAppPanel
              addressPlan={netappAddressPlan}
              artifacts={netappArtifacts}
              consoleDiscovery={netappConsoleDiscovery}
              consoleReadiness={netappConsoleReadiness}
              consoleState={netappConsoleState}
              error={netappError}
              loading={netappLoading}
              liveState={netappLiveState}
              nfsVcenterReadiness={netappNfsVcenterReadiness}
              netappAction={netappAction}
              onRunAddressPlan={runNetAppAddressPlan}
              onRunLiveState={runNetAppLiveState}
              onRunNfsSetupPreview={runNetAppNfsSetupPreview}
              onRunSetupPreview={runNetAppSetupPreview}
              onRunUpgradeInventory={runNetAppUpgradeInventory}
              onRunUpgradePlan={runNetAppUpgradePlan}
              onValidateNfsSetup={validateNetAppNfsSetup}
              onValidateSetup={validateNetAppSetup}
              onValidateUpgrade={validateNetAppUpgrade}
              onRefresh={loadNetAppPlanPreview}
              preview={netappPlanPreview}
              setupPreview={netappSetupPreview}
              upgradeInventory={netappUpgradeInventory}
              upgradePlan={netappUpgradePlan}
              upgradeReadiness={netappUpgradeReadiness}
              upgradeValidation={netappUpgradeValidation}
            />
          )}
        </>
      )}
    </Page>
  );
}

function HumanStatusPill({ status }: { status: string }) {
  if (isLowSignalStatusBubble(status)) return null;
  return <span className={`status-pillow ${statusTone(status)}`}>{displayStatusLabel(status)}</span>;
}

function MinimalStageList({
  items,
  onSelect,
  selectedId
}: {
  items: MinimalStageItem[];
  onSelect: (id: string) => void;
  selectedId: string;
}) {
  return (
    <section className="panel minimal-stage-list">
      <div className="readiness-head">
        <PanelTitle icon={<Workflow size={18} />} title="Setup Steps" />
        <span className="muted">{items.length} steps</span>
      </div>
      <div className="minimal-stage-rows">
        {items.map((item) => (
          <MinimalStageRow
            item={item}
            key={item.id}
            onSelect={() => onSelect(item.id)}
            selected={item.id === selectedId}
          />
        ))}
      </div>
    </section>
  );
}

function MinimalStageRow({
  item,
  onSelect,
  selected
}: {
  item: MinimalStageItem;
  onSelect: () => void;
  selected: boolean;
}) {
  return (
    <article className={selected ? "minimal-stage-row selected" : "minimal-stage-row"}>
      <button className="minimal-stage-row-main" onClick={onSelect} type="button">
        <div>
          <strong>{item.label}</strong>
          <p>{item.one_line_summary}</p>
        </div>
        <HumanStatusPill status={item.status} />
      </button>
      <div className="minimal-stage-next">
        <span>Next action</span>
        <strong>{item.next_action}</strong>
      </div>
      <div className="minimal-stage-action">
        {item.primary_button_enabled ? (
          <button className="small-button" onClick={onSelect} type="button">
            <Route size={14} />
            {item.primary_button_label}
          </button>
        ) : (
          <span>{item.disabled_reason || "Waiting on earlier step"}</span>
        )}
      </div>
    </article>
  );
}

function MinimalWorkflowStageDetail({
  actionIssueCounts = {},
  onCopy,
  onRun,
  runningActionId = "",
  runResults = {},
  stage,
  stageIssues = []
}: {
  actionIssueCounts?: Record<string, number>;
  onCopy: (action: WorkflowAction) => void;
  onRun?: RunWorkflowActionHandler;
  runningActionId?: string;
  runResults?: Record<string, WorkflowActionRun>;
  stage: WorkflowStage | undefined;
  stageIssues?: ReportIssue[];
}) {
  const { isAdvancedMode } = useUiMode();
  if (!stage) {
    return (
      <section className="panel">
        <EmptyState title="No setup step" detail="Select a setup step to see its current state and next action." />
      </section>
    );
  }
  const item = minimalStageItemFromWorkflowStage(stage, stageIssues.length || stage.blocked_count);
  const primary = primaryWorkflowAction(stage);
  const blockers = stageBlockers(stage);
  const warnings = stageWarnings(stage);
  const artifacts = workflowStageEvidenceArtifacts(stage);

  return (
    <MinimalDetailPanel
      currentState={stageCurrentSimpleSummary(stage)}
      desiredState={stage.desired_state}
      item={item}
      primaryAction={
        primary ? (
          isAdvancedMode ? (
            <WorkflowActionRunControl
              action={primary}
              compact
              onCopy={onCopy}
              onRun={onRun}
              running={runningActionId === primary.action_id}
            />
          ) : (
            <SimpleWorkflowActionControl
              action={primary}
              onRun={onRun}
              running={runningActionId === primary.action_id}
            />
          )
        ) : null
      }
    >
      <BlockerSummary blockers={blockers.slice(0, 1)} warnings={blockers.length ? [] : warnings.slice(0, 1)} empty="No current blocker is reported for this step." />
      <EvidenceDrawer count={artifacts.length} title={`${item.label} Proof`}>
        <EvidenceList artifacts={artifacts} empty="No proof links are available for this step yet." />
      </EvidenceDrawer>
      {isAdvancedMode && (
        <StageDetailPanel
          actionIssueCounts={actionIssueCounts}
          onCopy={onCopy}
          onRun={onRun}
          runningActionId={runningActionId}
          runResults={runResults}
          stage={stage}
          stageIssues={stageIssues}
        />
      )}
    </MinimalDetailPanel>
  );
}

function MinimalDetailPanel({
  children,
  currentState,
  desiredState,
  item,
  primaryAction
}: {
  children?: ReactNode;
  currentState: string;
  desiredState: string;
  item: MinimalStageItem;
  primaryAction?: ReactNode;
}) {
  return (
    <section className="panel minimal-detail-panel">
      <div className="minimal-detail-head">
        <div>
          <span className="summary-kicker">Selected step</span>
          <h2>{item.label}</h2>
          <p>{item.one_line_summary}</p>
        </div>
        <HumanStatusPill status={item.status} />
      </div>
      <div className="minimal-detail-grid">
        <div>
          <span>Current state</span>
          <strong>{currentState}</strong>
        </div>
        <div>
          <span>Desired state</span>
          <strong>{desiredState}</strong>
        </div>
        <div>
          <span>Next action</span>
          <strong>{item.next_action}</strong>
        </div>
      </div>
      <div className="minimal-primary-action">
        <span>Move forward</span>
        {primaryAction || <strong>{item.disabled_reason || "No action is available yet."}</strong>}
      </div>
      {children}
    </section>
  );
}

function EvidenceDrawer({
  children,
  count,
  title
}: {
  children: ReactNode;
  count: number;
  title: string;
}) {
  return (
    <AdvancedDetails
      className="evidence-drawer"
      summary={`${count} proof item${count === 1 ? "" : "s"}`}
      title={title}
    >
      {children}
    </AdvancedDetails>
  );
}

function EvidenceList({ artifacts, empty }: { artifacts: string[]; empty: string }) {
  if (!artifacts.length) {
    return <EmptyState title="No proof yet" detail={empty} />;
  }
  return (
    <ul className="issue-evidence-list">
      {artifacts.map((artifact, index) => (
        <li key={`${artifact}-${index}`}>
          <code>{artifact}</code>
        </li>
      ))}
    </ul>
  );
}

function WorkflowStageList({
  issuesByStage = {},
  onCopy,
  onSelect,
  selectedStageId = "",
  stages
}: {
  issuesByStage?: Record<string, number>;
  onCopy?: (action: WorkflowAction) => void;
  onSelect: (stageId: string) => void;
  selectedStageId?: string;
  stages: WorkflowStage[];
}) {
  return (
    <section className="panel workflow-stage-list">
      <div className="readiness-head">
        <PanelTitle icon={<Workflow size={18} />} title="Workflow Stages" />
        <span className="muted">{stages.length} registry stages</span>
      </div>
      {stages.length ? (
        <div className="workflow-stage-rows">
          {stages.map((stage) => {
            const snapshot = workflowStageSnapshot(stage);
            const primary = primaryWorkflowAction(stage);
            const issueCount = issuesByStage[stage.stage_id] ?? stage.blocked_count;
            return (
              <article className={stage.stage_id === selectedStageId ? "workflow-stage-row selected" : "workflow-stage-row"} key={stage.stage_id}>
                <div className="workflow-stage-row-head">
                  <div>
                    <strong>{stage.label}</strong>
                    <span>{stage.stage_id}</span>
                  </div>
                  <StatusBadge status={stage.current_state} />
                </div>
                <p>{workflowStageRowSummary(stage)}</p>
                <dl className="workflow-stage-row-meta">
                  <div>
                    <dt>Next action</dt>
                    <dd>
                      <strong>{primary?.label ?? "No action"}</strong>
                      <span>{primary?.next_action ?? "No registry action is available."}</span>
                    </dd>
                  </div>
                  <div>
                    <dt>Source</dt>
                    <dd><SourceFreshnessInline freshness={snapshot.freshness} sourceType={snapshot.sourceType} /></dd>
                  </div>
                  <div>
                    <dt>Last checked</dt>
                    <dd>{snapshot.lastChecked ? formatDateTime(snapshot.lastChecked) : "Not checked"}</dd>
                  </div>
                  <div>
                    <dt>Issues</dt>
                    <dd>{issueCount ? `${issueCount}` : "0"}</dd>
                  </div>
                </dl>
                <div className="workflow-stage-recheck">
                  <span>Recheck</span>
                  <code>{snapshot.recheckCommand || "No command registered"}</code>
                </div>
                <button className="small-button" onClick={() => onSelect(stage.stage_id)} type="button">
                  <Route size={14} />
                  Open
                </button>
                {primary && onCopy && (
                  <button className="small-button" onClick={() => onCopy(primary)} type="button">
                    <Copy size={14} />
                    Copy recheck
                  </button>
                )}
              </article>
            );
          })}
        </div>
      ) : (
        <EmptyState title="No workflow registry data" detail="Refresh Run Center after the backend registry endpoint is available." />
      )}
    </section>
  );
}

function StageDetailPanel({
  actionIssueCounts = {},
  onCopy,
  onRun,
  runningActionId = "",
  runResults = {},
  stageIssues = [],
  stage
}: {
  actionIssueCounts?: Record<string, number>;
  onCopy: (action: WorkflowAction) => void;
  onRun?: RunWorkflowActionHandler;
  runningActionId?: string;
  runResults?: Record<string, WorkflowActionRun>;
  stageIssues?: ReportIssue[];
  stage: WorkflowStage | undefined;
}) {
  const [selectedActionId, setSelectedActionId] = useState("");

  useEffect(() => {
    if (!stage) {
      setSelectedActionId("");
      return;
    }
    setSelectedActionId((current) =>
      stage.actions.some((action) => action.action_id === current)
        ? current
        : stage.primary_action ?? stage.actions[0]?.action_id ?? ""
    );
  }, [stage]);

  if (!stage) {
    return (
      <section className="panel">
        <EmptyState title="No registry stage" detail="This section has no workflow registry stage yet." />
      </section>
    );
  }

  const selectedAction =
    stage.actions.find((action) => action.action_id === selectedActionId) ?? stage.actions[0] ?? null;
  const primary = primaryWorkflowAction(stage);
  const snapshot = workflowStageSnapshot(stage);
  const blockers = stageBlockers(stage);
  const warnings = stageWarnings(stage);

  return (
    <section className="panel stage-detail-panel">
      <div className="readiness-head">
        <div>
          <PanelTitle icon={<Route size={18} />} title={`${stage.label} Setup`} />
          <p>{workflowStageRowSummary(stage)}</p>
        </div>
        <StatusBadge status={stage.current_state} />
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Actions" value={String(stage.action_count)} />
        <ProviderFact label="Issues" value={String(stageIssues.length || stage.blocked_count)} />
        <ProviderFact label="Source" value={labelize(snapshot.sourceType)} />
        <ProviderFact label="Freshness" value={labelize(snapshot.freshness)} />
        <ProviderFact label="Last Checked" value={snapshot.lastChecked ? formatDateTime(snapshot.lastChecked) : "Not checked"} />
        <ProviderFact label="Recheck" value={snapshot.recheckCommand || "No command registered"} />
      </div>
      <div className="stage-state-grid">
        <section>
          <strong>Current state</strong>
          <p>{stageCurrentSummary(stage)}</p>
        </section>
        <section>
          <strong>Desired state</strong>
          <p>{stage.desired_state}</p>
        </section>
        <section>
          <strong>Next action</strong>
          <p>{primary?.next_action ?? "No registry action is available for this stage."}</p>
        </section>
      </div>
      {primary && (
        <div className="registry-command-strip">
          <div>
            <span>{workflowActionCanRun(primary) ? "Primary check" : "Primary handoff"}</span>
            {workflowActionCanRun(primary) ? (
              <strong>{workflowRunButtonLabel(primary)}</strong>
            ) : (
              <code>{workflowActionCopyText(primary)}</code>
            )}
          </div>
          <WorkflowActionRunControl
            action={primary}
            compact
            onCopy={onCopy}
            onRun={onRun}
            running={runningActionId === primary.action_id}
          />
          <Link
            className="button-link"
            to={`/control-center?section=action-catalog&action=${encodeURIComponent(primary.action_id)}`}
          >
            <Route size={14} />
            Open action
          </Link>
        </div>
      )}
      <BlockerSummary blockers={blockers} warnings={warnings} empty="No current registry blocker is reported. Historical evidence remains collapsed below." />
      <WorkflowActionList
        actionIssueCounts={actionIssueCounts}
        actions={stage.actions}
        onCopy={onCopy}
        onRun={onRun}
        onSelect={setSelectedActionId}
        runningActionId={runningActionId}
        selectedActionId={selectedAction?.action_id ?? ""}
      />
      {selectedAction && (
        <WorkflowActionDetail
          action={selectedAction}
          latestRun={runResults[selectedAction.action_id]}
          onCopy={onCopy}
          onRun={onRun}
          running={runningActionId === selectedAction.action_id}
        />
      )}
      <StageEvidenceDetails stage={stage} />
    </section>
  );
}

function WorkflowActionList({
  actionIssueCounts = {},
  actions,
  onCopy,
  onRun,
  onSelect,
  runningActionId = "",
  selectedActionId
}: {
  actionIssueCounts?: Record<string, number>;
  actions: WorkflowAction[];
  onCopy: (action: WorkflowAction) => void;
  onRun?: RunWorkflowActionHandler;
  onSelect: (actionId: string) => void;
  runningActionId?: string;
  selectedActionId: string;
}) {
  if (!actions.length) {
    return <EmptyState title="No actions" detail="No registry actions are defined for this stage." />;
  }
  return (
    <div className="workflow-action-rows">
      {actions.map((action) => {
        const trace = action.last_run_trace;
        const issueCount = actionIssueCounts[action.action_id] ?? action.blockers.length;
        return (
          <article className={action.action_id === selectedActionId ? "workflow-action-row selected" : "workflow-action-row"} key={action.action_id}>
            <div className="workflow-action-row-head">
              <div>
                <strong>{action.label}</strong>
                <span>{action.action_id}</span>
              </div>
              <div className="classification-tags">
                <span className={`classification-tag ${workflowModeClass(action.mode)}`}>{workflowModeLabel(action.mode)}</span>
                <StatusBadge status={action.current_availability} />
              </div>
            </div>
            <p>{action.next_action}</p>
            {action.blockers[0] && <p className="control-table-note">{action.blockers[0]}</p>}
            <WorkflowActionHandoff action={action} />
            <dl className="workflow-action-row-meta">
              <div>
                <dt>Type</dt>
                <dd>{labelize(action.category)}</dd>
              </div>
              <div>
                <dt>Source</dt>
                <dd><SourceFreshnessInline freshness={trace.freshness} sourceType={trace.source_type} /></dd>
              </div>
              <div>
                <dt>Last run</dt>
                <dd>{trace.finished_at ? formatDateTime(trace.finished_at) : "Not checked"}</dd>
              </div>
              <div>
                <dt>Issues</dt>
                <dd>{issueCount ? String(issueCount) : "0"}</dd>
              </div>
            </dl>
            <div className="action-row">
              <WorkflowActionRunControl
                action={action}
                compact
                onCopy={onCopy}
                onRun={onRun}
                running={runningActionId === action.action_id}
              />
              <button className="small-button" onClick={() => onSelect(action.action_id)} type="button">
                <Route size={14} />
                Detail
              </button>
            </div>
          </article>
        );
      })}
    </div>
  );
}

function WorkflowActionDetail({
  action,
  latestRun,
  onCopy,
  onRun,
  running = false
}: {
  action: WorkflowAction;
  latestRun?: WorkflowActionRun;
  onCopy: (action: WorkflowAction) => void;
  onRun?: RunWorkflowActionHandler;
  running?: boolean;
}) {
  const trace = latestRun ? workflowRunToTrace(latestRun) : action.last_run_trace;
  return (
    <AdvancedDetails
      className="section-details workflow-action-detail"
      summary={`${action.category} / ${action.mode} / ${trace.source_type} / ${trace.freshness}`}
      title={action.label}
    >
      <div className="workflow-action-detail-grid">
        <div>
          <h3>Definition</h3>
          <dl className="issue-meta-grid">
            <div>
              <dt>Action ID</dt>
              <dd>{action.action_id}</dd>
            </div>
            <div>
              <dt>Provider</dt>
              <dd>{labelize(action.provider)}</dd>
            </div>
            <div>
              <dt>Required mode</dt>
              <dd>{action.required_mode}</dd>
            </div>
            <div>
              <dt>Source</dt>
              <dd>{labelize(action.source_type)}</dd>
            </div>
            <div>
              <dt>Status source</dt>
              <dd>{labelize(trace.source_type)}</dd>
            </div>
            <div>
              <dt>Freshness</dt>
              <dd>{labelize(trace.freshness)}</dd>
            </div>
            {workflowActionCanRun(action) ? (
              <div>
                <dt>Runner</dt>
                <dd>{action.run_endpoint}</dd>
              </div>
            ) : (
              <div>
                <dt>Copy command</dt>
                <dd><code>{workflowActionCopyText(action)}</code></dd>
              </div>
            )}
          </dl>
          <p>{action.description}</p>
          <div className="action-row">
            <WorkflowActionRunControl
              action={action}
              onCopy={onCopy}
              onRun={onRun}
              running={running}
            />
          </div>
          {!workflowActionCanRun(action) && <code>{workflowActionCopyText(action)}</code>}
        </div>
        <RunTraceSummary latestRun={latestRun} trace={trace} />
      </div>
      <RequirementList title="Required gates" items={action.required_gates} />
      <RequirementList title="Confirmations" items={action.required_confirmations} />
      <RequirementList title="Safety notes" items={action.safety_notes} />
      <WorkflowEvidenceDetails action={action} />
    </AdvancedDetails>
  );
}

function WorkflowActionRunControl({
  action,
  compact = false,
  onCopy,
  onRun,
  running
}: {
  action: WorkflowAction;
  compact?: boolean;
  onCopy: (action: WorkflowAction) => void;
  onRun?: RunWorkflowActionHandler;
  running: boolean;
}) {
  if (workflowActionCanRun(action) && onRun) {
    return (
      <button
        className={compact ? "small-button primary" : "primary"}
        disabled={running}
        onClick={() => onRun(action)}
        type="button"
      >
        {running ? <RefreshCw className="spin-icon" size={compact ? 14 : 16} /> : <Play size={compact ? 14 : 16} />}
        {running ? "Running" : workflowRunButtonLabel(action)}
      </button>
    );
  }

  if (workflowActionRequiresGuard(action)) {
    return (
      <GuardedWorkflowActionButton
        action={action}
        compact={compact}
        onRun={onRun}
        running={running}
      />
    );
  }

  return (
    <button className={compact ? "small-button" : ""} onClick={() => onCopy(action)} type="button">
      <Copy size={compact ? 14 : 16} />
      Copy command
    </button>
  );
}

function SimpleWorkflowActionControl({
  action,
  onRun,
  running
}: {
  action: WorkflowAction;
  onRun?: RunWorkflowActionHandler;
  running: boolean;
}) {
  const { setUiMode } = useUiMode();

  if (workflowActionCanRun(action) && onRun) {
    return (
      <button
        className="small-button primary"
        disabled={running}
        onClick={() => onRun(action)}
        type="button"
      >
        {running ? <RefreshCw className="spin-icon" size={14} /> : <Play size={14} />}
        {running ? "Running" : workflowRunButtonLabel(action)}
      </button>
    );
  }

  if (workflowActionRequiresGuard(action)) {
    return (
      <GuardedWorkflowActionButton
        action={action}
        compact
        onRun={onRun}
        running={running}
      />
    );
  }

  return (
    <button className="small-button" onClick={() => setUiMode("advanced")} type="button">
      <Settings size={14} />
      Open Advanced
    </button>
  );
}

function WorkflowActionHandoff({ action }: { action: WorkflowAction }) {
  if (workflowActionCanRun(action)) {
    return (
      <div className="workflow-action-command runnable">
        <span>UI check</span>
        <strong>{workflowRunButtonLabel(action)}</strong>
      </div>
    );
  }
  if (workflowActionRequiresGuard(action) && workflowActionCanStartGuarded(action)) {
    return (
      <div className="workflow-action-command runnable guarded">
        <span>Guarded UI action</span>
        <strong>{guardedWorkflowRunButtonLabel(action)}</strong>
      </div>
    );
  }
  return (
    <div className="workflow-action-command">
      <span>{workflowActionRequiresGuard(action) ? "Guarded" : "Copy command"}</span>
      {workflowActionRequiresGuard(action) ? (
        <strong>{workflowGuardedDisabledReason(action)}</strong>
      ) : (
        <code>{workflowActionCopyText(action)}</code>
      )}
    </div>
  );
}

function GuardedWorkflowActionButton({
  action,
  compact = false,
  enabled = true,
  disabledReasonOverride,
  label,
  onRun,
  running
}: {
  action: WorkflowAction;
  compact?: boolean;
  enabled?: boolean;
  disabledReasonOverride?: string;
  label?: string;
  onRun?: RunWorkflowActionHandler;
  running: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [confirmedGates, setConfirmedGates] = useState<Record<string, boolean>>({});
  const requiredPhrase = action.required_confirmations[0] ?? "";
  const canStart = enabled && workflowActionCanStartGuarded(action) && Boolean(onRun);
  const phraseMatches = confirmation === requiredPhrase;
  const gatesMatch = action.required_gates.every((gate) => confirmedGates[gate]);
  const ready = canStart && phraseMatches && gatesMatch && !running;
  const disabledReason = disabledReasonOverride || workflowGuardedDisabledReason(action);

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  function toggleGate(gate: string) {
    setConfirmedGates((current) => ({ ...current, [gate]: !current[gate] }));
  }

  function startGuardedAction() {
    if (!ready || !onRun) return;
    onRun(action, {
      confirmation_phrase: confirmation,
      confirmed_gates: action.required_gates.filter((gate) => confirmedGates[gate])
    });
    setOpen(false);
    setConfirmation("");
    setConfirmedGates({});
  }

  return (
    <span className="guarded-action-control">
      <button
        className={`${compact ? "small-button" : ""} guarded-action-button ${action.mode === "destructive" ? "destructive" : "primary"}`}
        disabled={!canStart || running}
        onClick={() => setOpen(true)}
        title={canStart ? "Open guarded confirmation." : disabledReason}
        type="button"
      >
        {running ? <RefreshCw className="spin-icon" size={compact ? 14 : 16} /> : <Play size={compact ? 14 : 16} />}
        {running ? "Running" : label ?? guardedWorkflowRunButtonLabel(action)}
      </button>
      {open && createPortal(
        <div className="guarded-action-dialog-layer" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setOpen(false);
        }}>
          <div className="guarded-action-dialog" role="dialog" aria-label={`${action.label} confirmation`} aria-modal="true">
            <div className="guarded-action-dialog-head">
              <strong>{humanWorkflowActionLabel(action)}</strong>
              <button className="icon-button" onClick={() => setOpen(false)} type="button" aria-label="Close guarded action">
                <X size={16} />
              </button>
            </div>
            <div className="guarded-action-dialog-body">
              <div className="guarded-action-warning">
                <AlertTriangle size={16} />
                <span>{workflowModeLabel(action.mode)} action against local lab hardware.</span>
              </div>
              {action.required_gates.length > 0 && (
                <div className="guarded-gate-list">
                  {action.required_gates.map((gate) => (
                    <label key={`${action.action_id}-${gate}`}>
                      <input
                        checked={Boolean(confirmedGates[gate])}
                        onChange={() => toggleGate(gate)}
                        type="checkbox"
                      />
                      <span>{gate}</span>
                    </label>
                  ))}
                </div>
              )}
              <Field label="Confirmation">
                <input
                  autoComplete="off"
                  onChange={(event) => setConfirmation(event.target.value)}
                  placeholder={requiredPhrase}
                  value={confirmation}
                />
              </Field>
            </div>
            <div className="guarded-action-dialog-actions">
              <button className="small-button" onClick={() => setOpen(false)} type="button">
                Cancel
              </button>
              <button className="small-button primary" disabled={!ready} onClick={startGuardedAction} type="button">
                <Play size={14} />
                {label ?? guardedWorkflowRunButtonLabel(action)}
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </span>
  );
}

function RunTraceSummary({
  latestRun,
  trace
}: {
  latestRun?: WorkflowActionRun;
  trace: WorkflowAction["last_run_trace"];
}) {
  return (
    <section className="run-trace-summary">
      <div className="readiness-head">
        <strong>Run Trace</strong>
        <StatusBadge status={trace.status} />
      </div>
      <dl>
        <div>
          <dt>Source</dt>
          <dd>{labelize(trace.source_type)}</dd>
        </div>
        <div>
          <dt>Freshness</dt>
          <dd>{labelize(trace.freshness)}</dd>
        </div>
        <div>
          <dt>Finished</dt>
          <dd>{trace.finished_at ? formatDateTime(trace.finished_at) : "Not checked"}</dd>
        </div>
        <div>
          <dt>Real Source</dt>
          <dd>{latestRun ? (latestRun.not_mock ? "yes" : "test mode") : trace.source_type === "live_probe" ? "yes" : "not checked"}</dd>
        </div>
        {latestRun && (
          <div>
            <dt>Return Code</dt>
            <dd>{latestRun.return_code === null ? "None" : String(latestRun.return_code)}</dd>
          </div>
        )}
      </dl>
      <p>{trace.summary}</p>
      {latestRun && (
        <div className="action-run-output-grid">
          <div>
            <strong>stdout redacted summary</strong>
            <pre>{latestRun.stdout_summary || "No stdout captured."}</pre>
          </div>
          <div>
            <strong>stderr redacted summary</strong>
            <pre>{latestRun.stderr_summary || "No stderr captured."}</pre>
          </div>
        </div>
      )}
      {trace.command && (
        <div className="recheck-command-row">
          <span>Recheck</span>
          <code>{trace.command}</code>
        </div>
      )}
      {latestRun?.trace_artifact && (
        <div className="recheck-command-row">
          <span>Trace artifact</span>
          <code>{latestRun.trace_artifact}</code>
        </div>
      )}
      {trace.warnings.length > 0 && <BlockerSummary blockers={[]} warnings={trace.warnings} />}
      {trace.blockers.length > 0 && <BlockerSummary blockers={trace.blockers} warnings={[]} />}
    </section>
  );
}

function SourceFreshnessInline({
  freshness,
  sourceType
}: {
  freshness: string;
  sourceType: string;
}) {
  return (
    <span className={`source-freshness source-${statusClassName(sourceType)} freshness-${statusClassName(freshness)}`}>
      <strong>{displayStatusLabel(sourceType || "not_checked")}</strong>
      <span>{displayStatusLabel(freshness || "unknown")}</span>
    </span>
  );
}

function StageEvidenceDetails({ stage }: { stage: WorkflowStage }) {
  const artifacts = uniqueStrings([
    ...stage.reports,
    ...stage.actions.flatMap((action) => [
      ...action.reports,
      ...action.evidence_artifacts,
      ...(action.last_run_report ? [action.last_run_report] : []),
      ...action.last_run_trace.report_artifacts
    ])
  ]);
  return (
    <AdvancedDetails
      className="section-details report-evidence-details"
      summary={`${artifacts.length} evidence artifact${artifacts.length === 1 ? "" : "s"}`}
      title={`${stage.label} evidence`}
    >
      {artifacts.length ? (
        <ul className="issue-evidence-list">
          {artifacts.map((artifact) => (
            <li key={`stage-evidence-${stage.stage_id}-${artifact}`}>
              <code>{artifact}</code>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState title="No evidence paths" detail="This registry stage has no report artifact paths yet." />
      )}
    </AdvancedDetails>
  );
}

function WorkflowEvidenceDetails({ action }: { action: WorkflowAction }) {
  const artifacts = uniqueStrings([
    ...action.evidence_artifacts,
    ...(action.last_run_report ? [action.last_run_report] : []),
    ...action.last_run_trace.report_artifacts,
    ...action.reports
  ]);
  return (
    <AdvancedDetails
      className="issue-evidence-details"
      summary={`${artifacts.length} evidence artifact${artifacts.length === 1 ? "" : "s"}`}
      title="Evidence"
    >
      {artifacts.length ? (
        <ul className="issue-evidence-list">
          {artifacts.map((artifact) => (
            <li key={`action-evidence-${action.action_id}-${artifact}`}>
              <code>{artifact}</code>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState title="No evidence paths" detail="This action has not produced report evidence in the registry." />
      )}
    </AdvancedDetails>
  );
}

function RequirementList({
  code = false,
  items,
  title
}: {
  code?: boolean;
  items: string[];
  title: string;
}) {
  if (!items.length) {
    return null;
  }
  return (
    <div className="workflow-requirement-list">
      <strong>{title}</strong>
      <ul>
        {items.map((item) => (
          <li key={`${title}-${item}`}>{code ? <code>{item}</code> : item}</li>
        ))}
      </ul>
    </div>
  );
}

function RunCenterTabs({
  activeView,
  netappIssueCount,
  onChange,
  selectedLabel,
  totalWork
}: {
  activeView: RunCenterView;
  netappIssueCount: number;
  onChange: (view: RunCenterView) => void;
  selectedLabel: string;
  totalWork: number;
}) {
  const tabs: Array<{ id: RunCenterView; label: string; detail: string; icon: ReactNode }> = [
    { id: "choose", label: "Choose Run", detail: "Start here", icon: <Route size={16} /> },
    { id: "queue", label: "Work Queue", detail: `${totalWork} active`, icon: <ClipboardList size={16} /> },
    { id: "selected", label: "Selected Work", detail: selectedLabel, icon: <ShieldCheck size={16} /> },
    { id: "netapp", label: "NetApp", detail: `${netappIssueCount} issues`, icon: <HardDrive size={16} /> }
  ];

  return (
    <section className="run-center-tabs">
      {tabs.map((tab) => (
        <button
          className={tab.id === activeView ? "active" : ""}
          key={tab.id}
          onClick={() => onChange(tab.id)}
          type="button"
        >
          {tab.icon}
          <span>{tab.label}</span>
          <small>{tab.detail}</small>
        </button>
      ))}
    </section>
  );
}

function buildRunChoices({
  onOpenNetapp,
  onOpenQueue,
  onOpenSelected,
  providers,
  selectedItem,
  totalWork
}: {
  onOpenNetapp: () => void;
  onOpenQueue: () => void;
  onOpenSelected: () => void;
  providers: ProviderStatus[];
  selectedItem: QueueItem | null;
  totalWork: number;
}): RunChoice[] {
  return [
    {
      id: "ilo",
      title: "iLO Server Config",
      category: "Hardware setup",
      status: "real_lab_gated",
      description: "Inventory, firmware, BIOS/boot discovery, and iLO setup readiness.",
      blockers: providerBlockers(providers, ["ilo-redfish"]),
      primaryLabel: "Open iLO Controls",
      primaryTo: "/control-center?section=ilo",
      command: "make provider-lab-ilo-inventory",
      icon: <Server size={18} />
    },
    {
      id: "storage",
      title: "Storage / RAID Config",
      category: "Disk layout",
      status: "apply_capable",
      description: "Drive discovery, RAID layout selection, apply plan, reset, and validation.",
      blockers: providerBlockers(providers, ["ilo-redfish"]),
      primaryLabel: "Open RAID Controls",
      primaryTo: "/control-center?section=raid",
      command: "make provider-lab-hpe-raid-plan",
      icon: <HardDrive size={18} />
    },
    {
      id: "esxi",
      title: "ESXi Install",
      category: "OS install",
      status: "readiness_workflow",
      description: "ISO readiness, virtual media, one-time boot, reset, and installer detection.",
      blockers: providerBlockers(providers, ["ilo-redfish"]),
      primaryLabel: "Open ESXi Controls",
      primaryTo: "/control-center?section=esxi",
      command: "make provider-lab-esxi-install-readiness",
      icon: <Play size={18} />
    },
    {
      id: "cisco",
      title: "Cisco Bootstrap",
      category: "Network setup",
      status: "console_first",
      description: "Console discovery, prompt readiness, bootstrap requirements, and SSH validation.",
      blockers: providerBlockers(providers, ["cisco-console", "cisco-ansible"]),
      primaryLabel: "Open Cisco Controls",
      primaryTo: "/control-center?section=cisco",
      command: "make provider-lab-cisco-console-ethernet-readiness",
      icon: <Activity size={18} />
    },
    {
      id: "netapp",
      title: "NetApp ONTAP",
      category: "Shared storage",
      status: "live_readiness",
      description: "Live/cached console state, planned SP, cluster, node, SVM, iSCSI LIF, and upgrade readiness.",
      blockers: providerBlockers(providers, ["netapp-ontap"]),
      primaryLabel: "Open NetApp",
      onPrimary: onOpenNetapp,
      command: "make provider-lab-refresh-live-state",
      icon: <HardDrive size={18} />
    },
    {
      id: "verification",
      title: "Build Verification",
      category: "Validation",
      status: "report_only",
      description: "Lab IP profile, readiness checks, post-build checklist, and redacted report.",
      blockers: [],
      primaryLabel: "Open Verification",
      primaryTo: "/verification",
      command: "make provider-lab-build-verification-live",
      icon: <ShieldCheck size={18} />
    },
    {
      id: "vm",
      title: "VM Request Lifecycle",
      category: "Portal workflow",
      status: `${totalWork} active`,
      description: "Request approval, preview plan, audit events, and reports.",
      blockers: [],
      primaryLabel: "Open Work Queue",
      onPrimary: onOpenQueue,
      secondaryLabel: selectedItem ? "Review Selected" : undefined,
      icon: <Workflow size={18} />
    }
  ];
}

function RunCenterSectionFocus({ choice }: { choice: RunChoice | undefined }) {
  const { isAdvancedMode } = useUiMode();

  if (!choice) {
    return <EmptyState title="Section unavailable" detail="Refresh Run Center to reload provider status for this section." />;
  }

  const summaryItems = [
    { label: "Category", value: choice.category },
    { label: "Status", value: displayStatusLabel(choice.status) },
    { label: "Blockers", value: choice.blockers.length ? String(choice.blockers.length) : "None" }
  ];
  if (isAdvancedMode) {
    summaryItems.push({ label: "Command", value: choice.command ?? "UI only" });
  }

  return (
    <div className="calm-section-grid">
      <StatusSummaryCard
        message={isAdvancedMode ? choice.description : simpleRunChoiceSummary(choice)}
        status={choice.blockers.length ? "blocked" : choice.status}
        title={choice.title}
        items={summaryItems}
      />
      <NextActionCard
        detail={choice.primaryLabel}
        icon={choice.icon}
        to={choice.primaryTo}
      />
      <BlockerSummary blockers={choice.blockers} />
    </div>
  );
}

function simpleRunChoiceSummary(choice: RunChoice): string {
  if (choice.blockers.length) {
    return choice.blockers[0];
  }
  const summaries: Record<string, string> = {
    cisco: "Switch readiness is summarized here.",
    firmware: "Firmware status and the next check are summarized here.",
    ilo: "Server access and iLO readiness are summarized here.",
    lab: "Lab profile readiness and the next setup step are summarized here.",
    netapp: "Console, ONTAP setup, storage, and upgrade readiness are summarized below.",
    verification: "Build verification status and proof are summarized here.",
    vm: "Request workflow status and the next operator action are summarized here."
  };
  return summaries[choice.id] ?? "Current status and the next action are summarized here.";
}

function RunCenterRunChooser({
  onOpenQueue,
  onOpenNetapp,
  onOpenSelected,
  providers,
  selectedItem,
  selectedRunChoiceIds,
  setSelectedRunChoiceIds,
  totalWork
}: {
  onOpenQueue: () => void;
  onOpenNetapp: () => void;
  onOpenSelected: () => void;
  providers: ProviderStatus[];
  selectedItem: QueueItem | null;
  selectedRunChoiceIds: string[];
  setSelectedRunChoiceIds: (ids: string[]) => void;
  totalWork: number;
}) {
  const choices = buildRunChoices({
    onOpenNetapp,
    onOpenQueue,
    onOpenSelected,
    providers,
    selectedItem,
    totalWork
  });
  const selectedChoices = choices.filter((choice) => selectedRunChoiceIds.includes(choice.id));
  const selectedBlockers = selectedChoices.flatMap((choice) =>
    choice.blockers.map((blocker) => `${choice.title}: ${blocker}`)
  );

  function toggleChoice(choiceId: string) {
    setSelectedRunChoiceIds(
      selectedRunChoiceIds.includes(choiceId)
        ? selectedRunChoiceIds.filter((id) => id !== choiceId)
        : [...selectedRunChoiceIds, choiceId]
    );
  }

  return (
    <>
      <section className="panel run-build-summary">
        <PanelTitle icon={<Route size={18} />} title="Run Builder" />
        <div className="run-build-layout">
          <div>
            <strong>{selectedChoices.length ? `${selectedChoices.length} step${selectedChoices.length === 1 ? "" : "s"} selected` : "No steps selected"}</strong>
            <p>{selectedChoices.map((choice) => choice.title).join(" -> ") || "Select the parts of the run you want to include."}</p>
          </div>
          <div className="action-row">
            <button onClick={() => setSelectedRunChoiceIds(choices.map((choice) => choice.id))} type="button">
              Select All
            </button>
            <button onClick={() => setSelectedRunChoiceIds([])} type="button">
              Clear
            </button>
          </div>
        </div>
        {selectedBlockers.length > 0 && (
          <div className="run-blocker-box">
            <strong>{selectedBlockers.length} blocker{selectedBlockers.length === 1 ? "" : "s"}</strong>
            <ul>
              {selectedBlockers.slice(0, 5).map((blocker) => (
                <li key={blocker}>{blocker}</li>
              ))}
            </ul>
          </div>
        )}
      </section>
      <section className="run-choice-list">
        {choices.map((choice) => {
          const selected = selectedRunChoiceIds.includes(choice.id);
          return (
            <article className={selected ? "run-choice-card selected" : "run-choice-card"} key={choice.id}>
              <label className="run-choice-select">
                <input
                  checked={selected}
                  onChange={() => toggleChoice(choice.id)}
                  type="checkbox"
                />
                <span className="run-choice-icon">{choice.icon}</span>
                <span>
                  <small>{choice.category}</small>
                  <strong>{choice.title}</strong>
                </span>
              </label>
              <StatusBadge status={choice.blockers.length ? "blocked" : choice.status} />
              <p>{choice.description}</p>
              {choice.blockers.length > 0 && (
                <div className="run-choice-blockers">
                  <strong>{choice.blockers.length} blocker{choice.blockers.length === 1 ? "" : "s"}</strong>
                  <ul>
                    {choice.blockers.slice(0, 3).map((blocker) => (
                      <li key={blocker}>{blocker}</li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="action-row">
                {choice.primaryTo ? (
                  <Link className="button-link" to={choice.primaryTo}>
                    {choice.icon}
                    {choice.primaryLabel}
                  </Link>
                ) : (
                  <button onClick={choice.onPrimary} type="button">
                    {choice.icon}
                    {choice.primaryLabel}
                  </button>
                )}
                {choice.secondaryLabel && (
                  <button onClick={onOpenSelected} type="button">
                    <ShieldCheck size={16} />
                    {choice.secondaryLabel}
                  </button>
                )}
              </div>
            </article>
          );
        })}
      </section>
    </>
  );
}

function RunCenterSelectedWork({
  review,
  selectedItem,
  selectedRequest,
  selectedRun,
  stageEvents
}: {
  review: { status: string; message: string } | null;
  selectedItem: QueueItem | null;
  selectedRequest: RequestRecord | null;
  selectedRun: WorkflowRun | null;
  stageEvents: StageEvent[];
}) {
  return (
    <section className="panel">
      <PanelTitle icon={<ShieldCheck size={18} />} title="Selected Work" />
      {selectedItem && (
        <div className="selected-work-banner">
          <strong>{selectedItem.actionLabel}</strong>
          <p>{selectedItem.reason}</p>
        </div>
      )}
      {selectedRequest ? (
        <>
          <div className="detail-grid">
            <Info label="Selected Request" value={selectedRequest.vm_deploy.vm_name} />
            <Info label="Request Status" value={labelize(selectedRequest.status)} />
            <Info label="Environment" value={selectedRequest.environment} />
            <Info label="Owner" value={selectedRequest.owner} />
            {selectedRun && <Info label="Workflow Run" value={selectedRun.id} />}
            {selectedRun && <Info label="Run Status" value={labelize(selectedRun.status)} />}
          </div>
          <div className="action-row review-actions">
            <Link className="button-link" to={`/requests/${selectedRequest.id}`}>
              <ClipboardList size={16} />
              Request
            </Link>
            {selectedRun && (
              <Link className="button-link" to={`/workflow-runs/${selectedRun.id}`}>
                <Workflow size={16} />
                Run
              </Link>
            )}
            {selectedRun ? (
              <Link className="button-link" to={`/workflow-runs/${selectedRun.id}#artifacts`}>
                <HardDrive size={16} />
                Reports
              </Link>
            ) : (
              <Link className="button-link" to={`/requests/${selectedRequest.id}#artifacts`}>
                <HardDrive size={16} />
                Reports
              </Link>
            )}
          </div>
        </>
      ) : (
        <p className="muted">No request selected.</p>
      )}
      {selectedRun ? (
        <>
          <div className="review-banner">
            {selectedRun.status === "completed" ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
            <div>
              <strong>{review?.status ?? "review"}</strong>
              <p>{review?.message ?? "Review the preview plan before execution."}</p>
            </div>
          </div>
          <StageList events={stageEvents} />
        </>
      ) : (
        <p className="muted">This queue item does not have a workflow run yet.</p>
      )}
    </section>
  );
}

function providerBlockers(providers: ProviderStatus[], providerIds: string[]): string[] {
  return providers
    .filter((provider) => providerIds.includes(provider.id))
    .flatMap((provider) => provider.blockers.map((blocker) => `${provider.name}: ${blocker}`));
}

function MinimalNetAppPanel({
  addressPlan,
  artifacts,
  consoleDiscovery,
  consoleReadiness,
  consoleState,
  error,
  loading,
  liveState,
  nfsVcenterReadiness,
  netappAction,
  onRunAddressPlan,
  onRunLiveState,
  onRunNfsSetupPreview,
  onRunSetupPreview,
  onRunUpgradeInventory,
  onRunUpgradePlan,
  onValidateNfsSetup,
  onValidateSetup,
  onValidateUpgrade,
  onRefresh,
  preview,
  setupPreview,
  upgradeInventory,
  upgradePlan,
  upgradeReadiness,
  upgradeValidation
}: {
  addressPlan: ProviderProbeResult | null;
  artifacts: NetAppProviderArtifact[];
  consoleDiscovery: ProviderProbeResult | null;
  consoleReadiness: NetAppConsoleReadiness | null;
  consoleState: ProviderProbeResult | null;
  error: string;
  loading: boolean;
  liveState: ProviderProbeResult | null;
  nfsVcenterReadiness: ProviderProbeResult | null;
  netappAction: string;
  onRunAddressPlan: () => void;
  onRunLiveState: () => void;
  onRunNfsSetupPreview: () => void;
  onRunSetupPreview: () => void;
  onRunUpgradeInventory: () => void;
  onRunUpgradePlan: () => void;
  onValidateNfsSetup: () => void;
  onValidateSetup: () => void;
  onValidateUpgrade: () => void;
  onRefresh: () => void;
  preview: NetAppPlanPreview | null;
  setupPreview: ProviderProbeResult | null;
  upgradeInventory: ProviderProbeResult | null;
  upgradePlan: ProviderProbeResult | null;
  upgradeReadiness: NetAppUpgradeReadiness | null;
  upgradeValidation: ProviderProbeResult | null;
}) {
  const runtimeState = objectValue(
    liveState?.runtime_state ?? consoleState?.runtime_state ?? consoleDiscovery?.runtime_state ?? consoleReadiness?.runtime_state
  );
  const runtimeConsole = objectValue(runtimeState.console);
  const selectedPort =
    asString(runtimeConsole.discovered_port) || asString(consoleState?.selected_port) || asString(consoleDiscovery?.selected_port);
  const selectedBaud =
    asString(runtimeConsole.baud) || asString(consoleState?.selected_baud) || asString(consoleDiscovery?.selected_baud);
  const consoleDetected = Boolean(selectedPort);
  const setupDetectedState = asString(setupPreview?.detected_state);
  const configuredByLiveCheck = asBoolean(liveState?.configured ?? runtimeState.configured ?? preview?.netapp_configured);
  const setupMissingFields = stringArray(setupPreview?.missing_fields);
  const nfsBlockers = stringArray(nfsVcenterReadiness?.blockers);
  const addressBlockers = stringArray(addressPlan?.blockers);
  const addressComparisons = recordArray(addressPlan?.address_comparisons);
  const addressMismatchCount = addressComparisons.filter((item) =>
    ["mismatch", "missing_current"].includes(asString(item.status))
  ).length;
  const upgradeButtonState = netappUpgradeButtonState({
    action: netappAction,
    apply: null,
    inventory: upgradeInventory,
    plan: upgradePlan,
    validation: upgradeValidation
  });
  const upgradeBlocked = stringArray(upgradePlan?.blockers).length || (upgradeReadiness?.blockers.length ?? 0);
  const upgradeStatus = upgradeBlocked
    ? "blocked"
    : upgradeReadiness?.upgrade_enabled || upgradeButtonState === "Ready to upgrade"
      ? "ready"
      : "disabled";
  const netappBlockers = uniqueStrings([
    ...stringArray(preview?.blockers),
    ...stringArray(setupPreview?.blockers),
    ...stringArray(consoleDiscovery?.blockers),
    ...stringArray(consoleState?.blockers),
    ...stringArray(liveState?.blockers),
    ...addressBlockers,
    ...nfsBlockers,
    ...stringArray(upgradePlan?.blockers),
    ...(upgradeReadiness?.blockers ?? [])
  ]);
  const nextAction =
    setupMissingFields.length > 0
      ? "Complete NetApp setup details."
      : upgradeStatus === "disabled" && !configuredByLiveCheck
        ? "Finish ONTAP setup before planning an upgrade."
        : humanizeAction(
            asString(setupPreview?.next_safe_action) ||
              asString(preview?.next_safe_action) ||
              asString(liveState?.next_safe_action) ||
              "Refresh NetApp readiness."
          );
  const rows = [
    {
      label: "Console",
      status: consoleDetected ? "ready" : "not_checked",
      summary: consoleDetected
        ? selectedBaud === "115200"
          ? "Console detected"
          : "Console detected"
        : "Console not detected"
    },
    {
      label: "ONTAP state",
      status: configuredByLiveCheck ? "ready" : setupDetectedState || "not_checked",
      summary: configuredByLiveCheck
        ? "Configured"
        : setupDetectedState === "cluster_setup_wizard"
          ? "Setup wizard detected"
          : "Unknown"
    },
    {
      label: "Management",
      status: configuredByLiveCheck ? "ready" : addressMismatchCount ? "blocked" : "not_configured_yet",
      summary: configuredByLiveCheck
        ? "Configured"
        : addressMismatchCount
          ? "Address mismatch"
          : "Not configured"
    },
    {
      label: "NFS datastore",
      status: nfsBlockers.length ? "blocked" : nfsVcenterReadiness?.status ?? "not_checked",
      summary: nfsBlockers.length
        ? "Blocked"
        : asString(nfsVcenterReadiness?.status) === "ready"
          ? "Ready"
          : "Not created"
    },
    {
      label: "Upgrade",
      status: upgradeStatus,
      summary:
        upgradeStatus === "ready"
          ? "Ready"
          : upgradeStatus === "blocked"
            ? "Blocked"
            : "Upgrade disabled until ONTAP setup is complete."
    }
  ];
  const proofCount =
    artifacts.length +
    workflowProbeEvidenceCount(consoleDiscovery) +
    workflowProbeEvidenceCount(consoleState) +
    workflowProbeEvidenceCount(liveState) +
    workflowProbeEvidenceCount(addressPlan) +
    workflowProbeEvidenceCount(nfsVcenterReadiness) +
    workflowProbeEvidenceCount(setupPreview) +
    workflowProbeEvidenceCount(upgradePlan);
  const evidencePaths = uniqueStrings([
    ...probeEvidencePaths(consoleDiscovery),
    ...probeEvidencePaths(consoleState),
    ...probeEvidencePaths(liveState),
    ...probeEvidencePaths(addressPlan),
    ...probeEvidencePaths(nfsVcenterReadiness),
    ...probeEvidencePaths(setupPreview),
    ...probeEvidencePaths(upgradePlan),
    ...artifacts.map((artifact) => artifact.title)
  ]);
  const busy = Boolean(netappAction);

  return (
    <section className="panel minimal-netapp-panel">
      <div className="minimal-detail-head">
        <div>
          <span className="summary-kicker">NetApp</span>
          <h2>ONTAP Setup</h2>
          <p>{setupMissingFields.length ? "Setup details missing" : nextAction}</p>
        </div>
        <HumanStatusPill status={netappBlockers.length ? "blocked" : configuredByLiveCheck ? "ready" : "not_configured_yet"} />
      </div>
      <Feedback loading={loading && !preview} error={error} />
      <div className="minimal-netapp-grid">
        {rows.map((row) => (
          <article key={row.label}>
            <span>{row.label}</span>
            <strong>{row.summary}</strong>
            <HumanStatusPill status={row.status} />
          </article>
        ))}
      </div>
      <NextActionCard detail={nextAction} />
      <BlockerSummary blockers={netappBlockers.slice(0, 1)} empty="No current NetApp blocker is reported." />
      <div className="action-row">
        <button onClick={onRunLiveState} disabled={busy || loading} type="button">
          <RefreshCw size={16} />
          {netappAction === "live-state" ? "Checking" : "Check State"}
        </button>
        <button className="primary" onClick={onRunSetupPreview} disabled={busy || loading} type="button">
          <ClipboardList size={16} />
          {netappAction === "setup-preview" ? "Previewing" : "Preview Setup"}
        </button>
        <button onClick={onRunAddressPlan} disabled={busy || loading} type="button">
          <Route size={16} />
          {netappAction === "address-plan" ? "Planning" : "Address Plan"}
        </button>
        <button onClick={onValidateSetup} disabled={busy || loading} type="button">
          <ShieldCheck size={16} />
          {netappAction === "validate-setup" ? "Validating" : "Validate Setup"}
        </button>
        <button onClick={onRunNfsSetupPreview} disabled={busy || loading} type="button">
          <HardDrive size={16} />
          {netappAction === "nfs-setup-preview" ? "Previewing" : "Preview NFS"}
        </button>
        <button onClick={onValidateNfsSetup} disabled={busy || loading} type="button">
          <ShieldCheck size={16} />
          {netappAction === "nfs-setup-validate" ? "Validating" : "Validate NFS"}
        </button>
        <button onClick={onRunUpgradeInventory} disabled={busy || loading} type="button">
          <RefreshCw size={16} />
          {netappAction === "upgrade-inventory" ? "Checking" : "Check ONTAP"}
        </button>
        <button onClick={onRunUpgradePlan} disabled={busy || loading} type="button">
          <ClipboardList size={16} />
          {netappAction === "upgrade-plan" ? "Planning" : "Plan Upgrade"}
        </button>
        <button onClick={onValidateUpgrade} disabled={busy || loading} type="button">
          <ShieldCheck size={16} />
          {netappAction === "upgrade-validate" ? "Validating" : "Validate Upgrade"}
        </button>
        <button onClick={onRefresh} disabled={busy || loading} type="button">
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>
      <EvidenceDrawer count={proofCount} title="NetApp Proof">
        <EvidenceList artifacts={evidencePaths} empty="No NetApp proof links are available yet." />
      </EvidenceDrawer>
    </section>
  );
}

function NetAppRunCenterPreview({
  addressPlan,
  artifacts,
  consoleDiscovery,
  consoleReadiness,
  consoleState,
  error,
  loading,
  liveState,
  nfsVcenterReadiness,
  nfsSetupApply,
  nfsSetupPreview,
  nfsSetupValidation,
  netappAction,
  onRunConsoleDiscovery,
  onRunConsoleReadState,
  onRunAddressPlan,
  onRunLiveState,
  onRunNfsSetupApply,
  onRunNfsSetupPreview,
  onRunSetupApply,
  onRunSetupPreview,
  onRunUpgradeApply,
  onRunUpgradeInventory,
  onRunUpgradePlan,
  onValidateUpgrade,
  onValidateNfsSetup,
  onValidateSetup,
  onRefresh,
  preview,
  readinessComparison,
  setupApply,
  setupPreview,
  upgradeApply,
  upgradeInventory,
  upgradePlan,
  upgradeReadiness,
  upgradeValidation
}: {
  addressPlan: ProviderProbeResult | null;
  artifacts: NetAppProviderArtifact[];
  consoleDiscovery: ProviderProbeResult | null;
  consoleReadiness: NetAppConsoleReadiness | null;
  consoleState: ProviderProbeResult | null;
  error: string;
  loading: boolean;
  liveState: ProviderProbeResult | null;
  nfsVcenterReadiness: ProviderProbeResult | null;
  nfsSetupApply: ProviderProbeResult | null;
  nfsSetupPreview: ProviderProbeResult | null;
  nfsSetupValidation: ProviderProbeResult | null;
  netappAction: string;
  onRunConsoleDiscovery: () => void;
  onRunConsoleReadState: () => void;
  onRunAddressPlan: () => void;
  onRunLiveState: () => void;
  onRunNfsSetupApply: () => void;
  onRunNfsSetupPreview: () => void;
  onRunSetupApply: () => void;
  onRunSetupPreview: () => void;
  onRunUpgradeApply: () => void;
  onRunUpgradeInventory: () => void;
  onRunUpgradePlan: () => void;
  onValidateUpgrade: () => void;
  onValidateNfsSetup: () => void;
  onValidateSetup: () => void;
  onRefresh: () => void;
  preview: NetAppPlanPreview | null;
  readinessComparison: NetAppReadinessComparison | null;
  setupApply: ProviderProbeResult | null;
  setupPreview: ProviderProbeResult | null;
  upgradeApply: ProviderProbeResult | null;
  upgradeInventory: ProviderProbeResult | null;
  upgradePlan: ProviderProbeResult | null;
  upgradeReadiness: NetAppUpgradeReadiness | null;
  upgradeValidation: ProviderProbeResult | null;
}) {
  const plannedTargets = objectValue(preview?.planned_targets);
  const currentDiscoveredTargets = objectValue(preview?.current_discovered_targets);
  const targetAddressing = recordArray(plannedTargets.target_addressing);
  const currentAddressing = netappCurrentAddressRows(currentDiscoveredTargets);
  const readinessSummary = preview?.readiness_summary ?? {};
  const setupReadiness = preview?.setup_readiness ?? {};
  const upgradeReadinessSummary = preview?.upgrade_readiness ?? {};
  const cluster = preview?.cluster_intent_preview ?? {};
  const svm = preview?.svm_intent_preview ?? {};
  const lifIntent = preview?.lif_intent_preview ?? {};
  const storagePreview = preview?.storage_iscsi_plan_preview ?? {};
  const upgradePreview = preview?.upgrade_readiness_preview ?? {};
  const disabledActions = preview?.disabled_actions ?? [];
  const addressComparisons = recordArray(addressPlan?.address_comparisons);

  return (
    <section className="panel netapp-run-center-preview">
      <div className="readiness-head">
        <PanelTitle icon={<HardDrive size={18} />} title="NetApp ONTAP Live Readiness" />
        <button onClick={onRefresh} disabled={loading}>
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>
      <div className="provider-callout netapp-apply-disabled">
        <strong>Live readiness / Apply disabled</strong>
        <p>
          Current and cached evidence is shown for the lab. ONTAP write actions,
          cluster creation, SVM/LIF/volume creation, upgrade, reboot, and wipe controls are disabled.
        </p>
      </div>
      <Feedback loading={loading && !preview} error={error} />
      {preview ? (
        <>
          <div className="provider-fact-grid compact">
            <ProviderFact label="Provider" value={preview.provider_id} />
            <ProviderFact label="Runtime" value={displayModeLabel(preview.mode)} />
            <ProviderFact label="Apply Enabled" value={preview.apply_enabled ? "Enabled" : "Disabled"} />
            <ProviderFact label="Configured State" value={preview.netapp_configured ? "Verified by live check" : "Not verified"} />
            <ProviderFact label="Manual Env Flag" value="Not required" />
            <ProviderFact label="Readiness Status" value={labelize(asString(readinessSummary.status) || "unknown")} />
            <ProviderFact label="Not Ready" value={asString(readinessSummary.not_ready_count) || "-"} />
            <ProviderFact label="Buckets" value={asString(readinessSummary.bucket_count) || "-"} />
            <ProviderFact label="Next Safe Action" value={preview.next_safe_action} />
          </div>
          <h3>Planned Targets</h3>
          <KeyValueTable rows={targetAddressing} labelKey="label" valueKey="address" empty="No NetApp target addresses are planned." />
          <h3>Current / Discovered Targets</h3>
          <KeyValueTable rows={currentAddressing} labelKey="label" valueKey="address" empty="No NetApp current targets have been discovered." />
          <h3>Address Remediation</h3>
          <NetAppAddressPlanPanel
            addressPlan={addressPlan}
            busy={Boolean(netappAction)}
            comparisons={addressComparisons}
            onRunAddressPlan={onRunAddressPlan}
          />
          <div className="provider-callout">
            <strong>Setup vs upgrade readiness</strong>
            <p>Setup: {operatorReadinessLabel(asString(setupReadiness.status) || "blocked_until_live_setup_ready")}. Upgrade: {operatorReadinessLabel(asString(upgradeReadinessSummary.status) || "blocked_until_setup_ready")}.</p>
          </div>
          <NetAppSetupUpgradeCenterPanel
            netappAction={netappAction}
            onRunSetupApply={onRunSetupApply}
            onRunSetupPreview={onRunSetupPreview}
            onRunUpgradeApply={onRunUpgradeApply}
            onRunUpgradeInventory={onRunUpgradeInventory}
            onRunUpgradePlan={onRunUpgradePlan}
            onValidateUpgrade={onValidateUpgrade}
            setupApply={setupApply}
            setupPreview={setupPreview}
            upgradeApply={upgradeApply}
            upgradeInventory={upgradeInventory}
            upgradePlan={upgradePlan}
            upgradeValidation={upgradeValidation}
          />
          <h3>Readiness Sections</h3>
          <NetAppReadinessGrid readiness={preview.readiness_buckets} />
          <h3>Blockers / Warnings</h3>
          <NetAppRunCenterIssues
            blockers={preview.blockers}
            removableWarnings={preview.removable_warnings}
            warnings={preview.warnings}
          />
          <h3>Planned vs Observed</h3>
          <details className="stage-details">
            <summary>Manual planned-vs-observed comparison</summary>
            <NetAppReadinessComparisonPanel comparison={readinessComparison} />
          </details>
          <h3>Console / Bootstrap Readiness</h3>
          <NetAppRealLabPanel
            consoleDiscovery={consoleDiscovery}
            consoleReadiness={consoleReadiness}
            consoleState={consoleState}
            liveState={liveState}
            loading={loading}
            netappAction={netappAction}
            nfsVcenterReadiness={nfsVcenterReadiness}
            nfsSetupApply={nfsSetupApply}
            nfsSetupPreview={nfsSetupPreview}
            nfsSetupValidation={nfsSetupValidation}
            onRefresh={onRefresh}
            onRunConsoleDiscovery={onRunConsoleDiscovery}
            onRunConsoleReadState={onRunConsoleReadState}
            onRunLiveState={onRunLiveState}
            onRunNfsSetupApply={onRunNfsSetupApply}
            onRunNfsSetupPreview={onRunNfsSetupPreview}
            onValidateNfsSetup={onValidateNfsSetup}
            onValidateSetup={onValidateSetup}
          />
          <details className="stage-details">
            <summary>Manual readiness checklist and local observations</summary>
            <NetAppConsoleReadinessPanel onRefresh={onRefresh} readiness={consoleReadiness} />
          </details>
          <details className="stage-details">
            <summary>Cluster, SVM, and LIF intent</summary>
            <div className="provider-fact-grid compact">
              <ProviderFact label="Cluster Management IP" value={asString(cluster.management_ip) || "-"} />
              <ProviderFact label="SVM Management IP" value={asString(svm.management_ip) || "-"} />
            </div>
            <KeyValueTable rows={recordArray(cluster.nodes)} labelKey="name" valueKey="management_ip" empty="No node management intent is planned." />
            <KeyValueTable rows={recordArray(lifIntent.iscsi_lifs)} labelKey="name" valueKey="address" empty="No iSCSI LIF intent is planned." />
          </details>
          <div className="run-center-preview-grid">
            <div>
              <h3>Storage / iSCSI Readiness</h3>
              <PreviewNoteBlock payload={storagePreview} fallback="Storage/iSCSI readiness is not checked yet. No volumes, LUNs, igroups, or LIFs are created." />
            </div>
            <div>
              <h3>Upgrade Readiness</h3>
              <NetAppUpgradeReadinessPanel readiness={upgradeReadiness} fallbackPreview={upgradePreview} />
            </div>
          </div>
          <h3>Artifact / Report Placeholders</h3>
          <div className="tag-row netapp-artifact-row">
            {preview.artifact_placeholders.map((artifact) => (
              <span key={artifact}>{artifact}</span>
            ))}
          </div>
          <h3>Historical Artifact Metadata</h3>
          <NetAppProviderArtifactList artifacts={artifacts} />
          <details className="stage-details">
            <summary>Disabled dangerous actions</summary>
            <DisabledActionList actions={disabledActions} />
          </details>
        </>
      ) : (
        !loading && !error && <p className="muted">No NetApp plan-preview payload is available.</p>
      )}
    </section>
  );
}

function NetAppAddressPlanPanel({
  addressPlan,
  busy,
  comparisons,
  onRunAddressPlan
}: {
  addressPlan: ProviderProbeResult | null;
  busy: boolean;
  comparisons: Record<string, unknown>[];
  onRunAddressPlan: () => void;
}) {
  if (!addressPlan) {
    return (
      <div className="provider-callout">
        <strong>Address plan not checked</strong>
        <p>Run Address Plan to compare console-discovered ONTAP addresses with the active lab profile.</p>
        <button onClick={onRunAddressPlan} disabled={busy} type="button">
          <Route size={16} />
          Run Address Plan
        </button>
      </div>
    );
  }
  const artifacts = objectValue(addressPlan.artifacts);
  const operatorPaths = recordArray(addressPlan.operator_paths);
  return (
    <div className="netapp-address-plan-panel">
      <div className="provider-fact-grid compact">
        <ProviderFact label="Status" value={labelize(asString(addressPlan.status) || "unknown")} />
        <ProviderFact label="Apply" value={asBoolean(addressPlan.apply_enabled) ? "Enabled" : "Disabled"} />
        <ProviderFact label="Next Action" value={humanizeAction(asString(addressPlan.next_safe_action) || "Review address blockers.")} />
        <ProviderFact label="Report" value={asString(artifacts.report) || "Not written"} />
      </div>
      <div className="action-row">
        <button onClick={onRunAddressPlan} disabled={busy} type="button">
          <Route size={16} />
          Run Address Plan
        </button>
      </div>
      <NetAppRunCenterIssues
        blockers={stringArray(addressPlan.blockers)}
        removableWarnings={[]}
        warnings={stringArray(addressPlan.warnings)}
      />
      <KeyValueTable
        rows={comparisons}
        labelKey="label"
        valueKey="status"
        empty="No address comparison rows are available."
      />
      <div className="tag-row netapp-artifact-row">
        {operatorPaths.map((path) => (
          <span key={asString(path.id) || asString(path.label)}>
            {asString(path.label)}: {labelize(asString(path.status) || "unknown")}
          </span>
        ))}
      </div>
    </div>
  );
}

function NetAppReadinessComparisonPanel({
  comparison
}: {
  comparison: NetAppReadinessComparison | null;
}) {
  if (!comparison) {
    return (
      <div className="provider-callout">
        <strong>Manual observations only</strong>
        <p>Planned-vs-observed comparison is loading. No live NetApp discovery is run.</p>
      </div>
    );
  }

  return (
    <div className="netapp-comparison-preview">
      <div className="provider-callout netapp-apply-disabled">
        <strong>Manual observations only / No live NetApp discovery</strong>
        <p>
          This compares local planned targets with operator observations. Discovery,
          probes, console access, and apply remain disabled.
        </p>
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Provider" value={comparison.provider_id} />
        <ProviderFact label="Mode" value={comparison.mode} />
        <ProviderFact label="Comparison" value={comparison.comparison_enabled ? "Enabled" : "Disabled"} />
        <ProviderFact label="Discovery" value={comparison.discovery_enabled ? "Enabled" : "Disabled"} />
        <ProviderFact label="Apply" value={comparison.apply_enabled ? "Enabled" : "Disabled"} />
        <ProviderFact label="Matched" value={`${comparison.matched_items.length} / ${comparison.comparison_items.length}`} />
        <ProviderFact label="Unknown" value={String(comparison.unknown_items.length)} />
        <ProviderFact label="Warnings" value={String(comparison.warning_items.length)} />
        <ProviderFact label="Blockers" value={String(comparison.blocker_items.length)} />
        <ProviderFact label="Console State" value={labelize(comparison.observations.observed_console_state)} />
      </div>
      <NetAppRunCenterIssues
        blockers={comparison.blockers}
        removableWarnings={comparison.removable_warnings}
        warnings={comparison.warnings}
      />
      <table className="netapp-comparison-table">
        <thead>
          <tr>
            <th>Item</th>
            <th>Planned / Expected</th>
            <th>Observed</th>
            <th>Status</th>
            <th>Next Action</th>
          </tr>
        </thead>
        <tbody>
          {comparison.comparison_items.map((item) => (
            <tr key={item.id}>
              <td>{item.label}</td>
              <td>{item.planned}</td>
              <td>{item.observed}</td>
              <td>
                <span className={`comparison-status ${item.status}`}>{labelize(item.status)}</span>
              </td>
              <td>{item.next_action}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="provider-callout">
        <strong>Next safe action</strong>
        <p>{comparison.next_safe_action}</p>
      </div>
    </div>
  );
}

function NetAppUpgradeReadinessPanel({
  fallbackPreview,
  readiness
}: {
  fallbackPreview: Record<string, unknown>;
  readiness: NetAppUpgradeReadiness | null;
}) {
  if (!readiness) {
    return (
      <PreviewNoteBlock
        payload={fallbackPreview}
        fallback="Upgrade preview placeholder only. No ONTAP image upload, upgrade, takeover, giveback, or reboot is run."
      />
    );
  }

  return (
    <div className="netapp-upgrade-preview">
      <div className="provider-callout">
        <strong>Offline media readiness / Apply disabled</strong>
        <p>No ONTAP write calls are made. Upgrade and apply remain disabled.</p>
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Current Source" value={labelize(readiness.current_version_source)} />
        <ProviderFact label="Current Version" value={readiness.current_version ?? "Unknown"} />
        <ProviderFact label="Confidence" value={labelize(readiness.current_version_confidence)} />
        <ProviderFact label="Media Inventory" value={labelize(readiness.media_inventory_mode)} />
        <ProviderFact label="Recommended Target" value={readiness.recommended_target ?? "None"} />
        <ProviderFact label="Upgrade Enabled" value={readiness.upgrade_enabled ? "Enabled" : "Disabled"} />
        <ProviderFact label="Setup Ready" value={readiness.setup_ready ? "Yes" : "No"} />
        <ProviderFact label="Scope" value={labelize(readiness.readiness_scope)} />
      </div>
      <NetAppRunCenterIssues
        blockers={readiness.blockers}
        removableWarnings={readiness.removable_warnings}
        warnings={readiness.warnings}
      />
      <h3>ONTAP Media Candidates</h3>
      <NetAppUpgradeCandidateTable candidates={readiness.candidates} />
      <h3>Upgrade Chain</h3>
      <NetAppUpgradeCandidateTable candidates={readiness.upgrade_chain} empty="No upgrade chain is available." />
      <h3>Disabled Upgrade Actions</h3>
      <DisabledActionList actions={readiness.disabled_actions} />
    </div>
  );
}

function NetAppSetupUpgradeCenterPanel({
  netappAction,
  onRunSetupApply,
  onRunSetupPreview,
  onRunUpgradeApply,
  onRunUpgradeInventory,
  onRunUpgradePlan,
  onValidateUpgrade,
  setupApply,
  setupPreview,
  upgradeApply,
  upgradeInventory,
  upgradePlan,
  upgradeValidation
}: {
  netappAction: string;
  onRunSetupApply: () => void;
  onRunSetupPreview: () => void;
  onRunUpgradeApply: () => void;
  onRunUpgradeInventory: () => void;
  onRunUpgradePlan: () => void;
  onValidateUpgrade: () => void;
  setupApply: ProviderProbeResult | null;
  setupPreview: ProviderProbeResult | null;
  upgradeApply: ProviderProbeResult | null;
  upgradeInventory: ProviderProbeResult | null;
  upgradePlan: ProviderProbeResult | null;
  upgradeValidation: ProviderProbeResult | null;
}) {
  const setupIntent = objectValue(setupPreview?.setup_intent);
  const setupArtifacts = objectValue(setupPreview?.artifacts);
  const setupApplyArtifacts = objectValue(setupApply?.artifacts);
  const setupApplyReady = asBoolean(setupPreview?.apply_enabled);
  const setupMissingFields = stringArray(setupPreview?.missing_fields);
  const upgradeInventoryArtifacts = objectValue(upgradeInventory?.artifacts);
  const upgradePlanArtifacts = objectValue(upgradePlan?.artifacts);
  const upgradeValidationArtifacts = objectValue(upgradeValidation?.artifacts);
  const upgradeApplyArtifacts = objectValue(upgradeApply?.artifacts);
  const selectedPackage = objectValue(upgradePlan?.selected_package);
  const upgradeButtonState = netappUpgradeButtonState({
    action: netappAction,
    apply: upgradeApply,
    inventory: upgradeInventory,
    plan: upgradePlan,
    validation: upgradeValidation
  });
  const upgradeReady = upgradeButtonState === "Ready to upgrade";
  const busy = Boolean(netappAction);

  return (
    <section className="netapp-upgrade-center">
      <div className="readiness-head">
        <PanelTitle icon={<HardDrive size={18} />} title="NetApp Setup / ONTAP Upgrade Center" />
        <span className={`status-pill status-${slugStatus(upgradeButtonState)}`}>{upgradeButtonState}</span>
      </div>
      <div className="netapp-upgrade-center-grid">
        <div className="setup-preview-block">
          <div className="readiness-head">
            <h3>Setup Wizard</h3>
            <StatusBadge status={asString(setupPreview?.detected_state) || "not_checked"} />
          </div>
          <div className="provider-fact-grid compact">
            <ProviderFact label="Detected State" value={labelize(asString(setupPreview?.detected_state) || "not_checked")} />
            <ProviderFact label="Cluster" value={asString(setupIntent.cluster_name) || "Missing"} />
            <ProviderFact label="Cluster Mgmt" value={asString(setupIntent.cluster_mgmt_ip) || "Not set"} />
            <ProviderFact label="SVM" value={asString(setupIntent.svm_name) || "Missing"} />
            <ProviderFact label="NFS Volume" value={asString(setupIntent.nfs_volume) || "Not set"} />
            <ProviderFact label="Missing Fields" value={setupMissingFields.length ? String(setupMissingFields.length) : "None"} />
          </div>
          <div className="action-row">
            <button onClick={onRunSetupPreview} disabled={busy}>
              <RefreshCw size={16} />
              {netappAction === "setup-preview" ? "Previewing" : "Setup Preview"}
            </button>
            <button onClick={onRunSetupApply} disabled={busy || !setupApplyReady} title={setupApplyReady ? "Run guarded setup apply" : "Disabled until flags and setup intent are ready"}>
              <Play size={16} />
              {netappAction === "setup-apply" ? "Applying" : "Setup Apply"}
            </button>
          </div>
          <NetAppRunCenterIssues
            blockers={stringArray(setupPreview?.blockers)}
            removableWarnings={[]}
            warnings={stringArray(setupPreview?.warnings)}
          />
          <NetAppReportLinkRow
            reports={[
              asString(setupArtifacts.report),
              asString(setupArtifacts.json),
              asString(setupApplyArtifacts.report)
            ]}
          />
        </div>
        <div className="setup-preview-block">
          <div className="readiness-head">
            <h3>ONTAP Upgrade</h3>
            <StatusBadge status={slugStatus(upgradeButtonState)} />
          </div>
          <div className="provider-fact-grid compact">
            <ProviderFact label="Current Version" value={asString(upgradePlan?.current_version) || asString(upgradeInventory?.current_ontap_version) || "Unknown"} />
            <ProviderFact label="Target Version" value={asString(upgradePlan?.target_version) || "Not selected"} />
            <ProviderFact label="Image / Package" value={asString(selectedPackage.redacted_label) || "None"} />
            <ProviderFact label="Package Loaded" value={asBoolean(upgradePlan?.package_loaded) ? "Yes" : "No"} />
            <ProviderFact label="Validation" value={asString(upgradeValidation?.status) || asString(objectValue(upgradePlan?.pre_upgrade_validation).status) || "Not run"} />
            <ProviderFact label="Path" value={labelize(asString(upgradePlan?.supported_path_state) || asString(upgradeInventory?.supported_path_state) || "unknown")} />
          </div>
          <div className="action-row">
            <button onClick={onRunUpgradeInventory} disabled={busy}>
              <RefreshCw size={16} />
              {netappAction === "upgrade-inventory" ? "Inventorying" : "Upgrade Inventory"}
            </button>
            <button onClick={onRunUpgradePlan} disabled={busy}>
              <ClipboardList size={16} />
              {netappAction === "upgrade-plan" ? "Planning" : "Upgrade Plan"}
            </button>
            <button onClick={onValidateUpgrade} disabled={busy}>
              <ShieldCheck size={16} />
              {netappAction === "upgrade-validate" ? "Validating" : "Validate Upgrade"}
            </button>
            <button onClick={onRunUpgradeApply} disabled={busy || !upgradeReady} title={upgradeReady ? "Run guarded ONTAP upgrade" : upgradeButtonState}>
              <Play size={16} />
              {netappAction === "upgrade-apply" ? "Upgrading" : "Upgrade"}
            </button>
          </div>
          <NetAppRunCenterIssues
            blockers={stringArray(upgradePlan?.blockers)}
            removableWarnings={[]}
            warnings={stringArray(upgradePlan?.warnings)}
          />
          <NetAppReportLinkRow
            reports={[
              asString(upgradeInventoryArtifacts.report),
              asString(upgradePlanArtifacts.report),
              asString(upgradeValidationArtifacts.report),
              asString(upgradeApplyArtifacts.report)
            ]}
          />
        </div>
      </div>
    </section>
  );
}

function NetAppReportLinkRow({ reports }: { reports: Array<string | null> }) {
  const filtered = reports.filter((report): report is string => Boolean(report));
  if (!filtered.length) {
    return <p className="muted">No report links are available yet.</p>;
  }
  return (
    <div className="tag-row netapp-artifact-row">
      {filtered.map((report) => (
        <span key={report}>{report}</span>
      ))}
    </div>
  );
}

function netappUpgradeButtonState({
  action,
  apply,
  inventory,
  plan,
  validation
}: {
  action: string;
  apply: ProviderProbeResult | null;
  inventory: ProviderProbeResult | null;
  plan: ProviderProbeResult | null;
  validation: ProviderProbeResult | null;
}): string {
  if (action === "upgrade-apply") return "Upgrade running";
  if (apply?.status === "ready" || apply?.status === "completed") return "Upgrade completed";
  if (apply?.status === "failed") return "Upgrade failed";
  if (asString(plan?.button_state)) return asString(plan?.button_state);
  if (!asBoolean(inventory?.cluster_management_configured)) return "Disabled: NetApp not configured";
  if (!objectValue(plan?.selected_package).id) return "Disabled: no ONTAP image/package";
  if (!validation || validation.status === "not_run") return "Disabled: validation not run";
  if (validation.status !== "passed") return "Disabled: validation failed";
  return "Ready to upgrade";
}

function slugStatus(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "unknown";
}

const netappConsoleStateOptions: Array<{ value: NetAppObservationUpdate["observed_console_state"]; label: string }> = [
  { value: "unknown", label: "Unknown / unverified" },
  { value: "loader_prompt", label: "LOADER prompt" },
  { value: "boot_menu", label: "Boot menu" },
  { value: "cluster_setup_prompt", label: "Cluster setup prompt" },
  { value: "existing_cluster_login", label: "Existing cluster login" },
  { value: "other", label: "Other" }
];

const netappObservationChecks: Array<{ key: keyof Omit<NetAppObservationUpdate, "observed_console_state" | "operator_notes">; label: string }> = [
  { key: "controller_a_console_seen", label: "Controller A console seen" },
  { key: "controller_b_console_seen", label: "Controller B console seen" },
  { key: "controller_a_sp_cabled", label: "Controller A SP cabled" },
  { key: "controller_b_sp_cabled", label: "Controller B SP cabled" },
  { key: "management_network_reviewed", label: "Management network reviewed" },
  { key: "planned_targets_reviewed", label: "Planned targets reviewed" },
  { key: "existing_data_risk_acknowledged", label: "Existing data risk acknowledged" }
];

const forbiddenNetAppNoteFragments = [
  "authorization",
  "cookie",
  "credential",
  "password",
  "secret",
  "token"
];

function emptyNetAppObservationForm(): NetAppObservationUpdate {
  return {
    observed_console_state: "unknown",
    controller_a_console_seen: false,
    controller_b_console_seen: false,
    controller_a_sp_cabled: false,
    controller_b_sp_cabled: false,
    management_network_reviewed: false,
    planned_targets_reviewed: false,
    existing_data_risk_acknowledged: false,
    operator_notes: ""
  };
}

function observationFormFromReadiness(readiness: NetAppConsoleReadiness | null): NetAppObservationUpdate {
  const observations = readiness?.observations;
  if (!observations) {
    return emptyNetAppObservationForm();
  }
  return {
    observed_console_state: observations.observed_console_state,
    controller_a_console_seen: observations.controller_a_console_seen,
    controller_b_console_seen: observations.controller_b_console_seen,
    controller_a_sp_cabled: observations.controller_a_sp_cabled,
    controller_b_sp_cabled: observations.controller_b_sp_cabled,
    management_network_reviewed: observations.management_network_reviewed,
    planned_targets_reviewed: observations.planned_targets_reviewed,
    existing_data_risk_acknowledged: observations.existing_data_risk_acknowledged,
    operator_notes: observations.operator_notes
  };
}

function NetAppRealLabPanel({
  consoleDiscovery,
  consoleReadiness,
  consoleState,
  liveState,
  loading,
  netappAction,
  nfsVcenterReadiness,
  nfsSetupApply,
  nfsSetupPreview,
  nfsSetupValidation,
  onRefresh,
  onRunConsoleDiscovery,
  onRunConsoleReadState,
  onRunLiveState,
  onRunNfsSetupApply,
  onRunNfsSetupPreview,
  onValidateNfsSetup,
  onValidateSetup
}: {
  consoleDiscovery: ProviderProbeResult | null;
  consoleReadiness: NetAppConsoleReadiness | null;
  consoleState: ProviderProbeResult | null;
  liveState: ProviderProbeResult | null;
  loading: boolean;
  netappAction: string;
  nfsVcenterReadiness: ProviderProbeResult | null;
  nfsSetupApply: ProviderProbeResult | null;
  nfsSetupPreview: ProviderProbeResult | null;
  nfsSetupValidation: ProviderProbeResult | null;
  onRefresh: () => void;
  onRunConsoleDiscovery: () => void;
  onRunConsoleReadState: () => void;
  onRunLiveState: () => void;
  onRunNfsSetupApply: () => void;
  onRunNfsSetupPreview: () => void;
  onValidateNfsSetup: () => void;
  onValidateSetup: () => void;
}) {
  const probeEnabled = asBoolean(consoleReadiness?.console_probe_enabled);
  const discoveryArtifacts = objectValue(consoleDiscovery?.artifacts);
  const stateArtifacts = objectValue(consoleState?.artifacts);
  const liveArtifacts = objectValue(liveState?.artifacts);
  const nfsArtifacts = objectValue(nfsVcenterReadiness?.artifacts);
  const nfsSetupArtifacts = objectValue(nfsSetupPreview?.artifacts);
  const nfsApplyArtifacts = objectValue(nfsSetupApply?.artifacts);
  const nfsValidationArtifacts = objectValue(nfsSetupValidation?.artifacts);
  const nfsTopology = objectValue(nfsVcenterReadiness?.management_topology);
  const nfsTargets = objectValue(nfsVcenterReadiness?.targets);
  const plannedNfs = objectValue(nfsVcenterReadiness?.planned_nfs);
  const plannedNfsSetup = objectValue(nfsSetupPreview?.nfs_plan);
  const connectedPorts = stringArray(nfsTopology.connected_management_ports);
  const nfsLifs = stringArray(plannedNfs.nfs_lifs);
  const nfsSetupBlockers = stringArray(nfsSetupPreview?.blockers);
  const nfsSetupApplyReady = asBoolean(nfsSetupPreview?.apply_enabled);
  const busy = Boolean(netappAction);
  const discoveryCandidateCounts = objectValue(consoleDiscovery?.candidate_counts);
  const discoveryCandidates = recordArray(consoleDiscovery?.candidates);
  const runtimeState = objectValue(
    liveState?.runtime_state ?? consoleState?.runtime_state ?? consoleDiscovery?.runtime_state ?? consoleReadiness?.runtime_state
  );
  const runtimeConsole = objectValue(runtimeState.console);
  const selectedPort =
    asString(runtimeConsole.discovered_port) || asString(consoleState?.selected_port) || asString(consoleDiscovery?.selected_port);
  const selectedBaud =
    asString(runtimeConsole.baud) || asString(consoleState?.selected_baud) || asString(consoleDiscovery?.selected_baud);
  const selectedPromptState =
    asString(runtimeConsole.prompt_state) ||
    asString(consoleState?.selected_prompt_state) ||
    asString(consoleDiscovery?.selected_prompt_state);
  const selectionConfidence =
    asString(runtimeConsole.confidence) ||
    asString(consoleState?.selection_confidence) ||
    asString(consoleDiscovery?.selection_confidence);
  const selectionSource =
    asString(runtimeConsole.source) ||
    asString(consoleState?.selection_origin) ||
    asString(consoleDiscovery?.selection_origin);
  const lastSeen = asString(runtimeConsole.last_seen) || asString(liveState?.last_successful_probe_at);
  const selectionReason =
    asString(consoleState?.selection_reason) || asString(consoleDiscovery?.selection_reason);
  const promptDetected =
    asString(consoleState?.prompt_detected) || asString(consoleDiscovery?.prompt_detected);
  const nextConsoleAction =
    asString(consoleState?.next_safe_action) || asString(consoleDiscovery?.next_safe_action);
  const consoleCandidateCount =
    asString(consoleDiscovery?.candidate_count) || asString(discoveryCandidateCounts.total) || "0";
  const probedCandidateCount =
    asString(consoleState?.probed_candidate_count) || asString(consoleDiscovery?.probed_candidate_count) || "0";
  const skippedCandidateCount =
    asString(consoleState?.skipped_candidate_count) || asString(consoleDiscovery?.skipped_candidate_count) || "0";
  const consoleAttemptCount =
    asString(consoleState?.attempt_count) || asString(consoleDiscovery?.attempt_count) || "0";
  const configuredState = asString(liveState?.configured_state ?? runtimeState.configured_state) || "not_detected";
  const configuredByLiveCheck = asBoolean(liveState?.configured ?? runtimeState.configured);
  const legacyEnv = objectValue(liveState?.legacy_env ?? runtimeState.legacy_env);

  return (
    <div className="netapp-real-lab-panel">
      <div className="provider-callout">
        <strong>Real-lab read-only path</strong>
        <p>Console discovery is newline-only. NFS setup has preview, guarded apply, and validation controls; apply stays disabled until live setup, access, and confirmation gates pass.</p>
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Console Probe" value={probeEnabled ? "Available" : "Blocked"} />
        <ProviderFact label="Port Hint" value={asString(consoleDiscovery?.configured_port_hint) || "Not set"} />
        <ProviderFact label="Detected Automatically" value={selectedPort ? "Yes" : "Not yet"} />
        <ProviderFact label="Discovered Port" value={selectedPort || "Not selected"} />
        <ProviderFact label="Baud" value={selectedBaud || "Not selected"} />
        <ProviderFact label="Source" value={labelize(selectionSource || "none")} />
        <ProviderFact label="Last Seen" value={lastSeen ? formatDateTime(lastSeen) : "Not seen"} />
        <ProviderFact label="Prompt State" value={labelize(selectedPromptState || "not run")} />
        <ProviderFact label="Prompt Detected" value={promptDetected || "false"} />
        <ProviderFact label="Confidence" value={labelize(selectionConfidence || "none")} />
        <ProviderFact label="Configured State" value={configuredByLiveCheck ? "Verified by live check" : labelize(configuredState)} />
        <ProviderFact label="Manual Env Flag" value="Not required" />
        <ProviderFact label="Legacy Env" value={asBoolean(legacyEnv.netapp_configured_env) ? "Set true" : "Not authoritative"} />
        <ProviderFact label="Candidates" value={consoleCandidateCount} />
        <ProviderFact label="Probed / Skipped" value={`${probedCandidateCount} / ${skippedCandidateCount}`} />
        <ProviderFact label="Probe Attempts" value={consoleAttemptCount} />
        <ProviderFact label="Why Selected" value={selectionReason || "No selection evidence yet."} />
        <ProviderFact label="Next Console Action" value={nextConsoleAction || "Run console autodiscovery."} />
        <ProviderFact label="Last Console Blocker" value={asString(consoleState?.last_console_blocker) || asString(consoleDiscovery?.last_console_blocker) || "None"} />
        <ProviderFact label="Management Ports" value={connectedPorts.length ? connectedPorts.join(", ") : "One connected path expected"} />
        <ProviderFact label="NFS Readiness" value={operatorReadinessLabel(asString(nfsVcenterReadiness?.status) || "not run")} />
        <ProviderFact label="NFS LIFs" value={nfsLifs.length ? nfsLifs.join(", ") : "Not planned"} />
        <ProviderFact label="Datastore" value={asString(plannedNfs.datastore_name) || "Not planned"} />
        <ProviderFact label="NFS Setup" value={operatorReadinessLabel(asString(nfsSetupPreview?.status) || "not run")} />
        <ProviderFact label="NFS Apply" value={nfsSetupApplyReady ? "Ready" : "Disabled"} />
        <ProviderFact label="NFS Volume" value={asString(plannedNfsSetup.volume) || asString(plannedNfs.volume) || "Not planned"} />
        <ProviderFact label="Export Policy" value={asString(plannedNfsSetup.export_policy) || asString(plannedNfs.export_policy) || "Not planned"} />
        <ProviderFact label="vCenter" value={asBoolean(nfsTargets.vcenter_configured) ? "Configured" : "Not configured"} />
        <ProviderFact label="govc" value={asBoolean(nfsTargets.govc_available) ? "Available" : "Missing"} />
      </div>
      {promptDetected !== "true" && (
        <div className="provider-callout">
          <strong>{selectedPort ? "No NetApp prompt confirmed" : "No selected console candidate"}</strong>
          <p>{nextConsoleAction || "Check cable placement, adapter ownership, permissions, power state, and baud before rerunning discovery."}</p>
        </div>
      )}
      <div className="action-row">
        <button onClick={onRunConsoleDiscovery} disabled={!probeEnabled || busy || loading} type="button">
          <RefreshCw size={16} />
          {netappAction === "console-discovery" ? "Discovering" : "Discover NetApp Console"}
        </button>
        <button onClick={onRunLiveState} disabled={!probeEnabled || busy || loading} type="button">
          <Activity size={16} />
          {netappAction === "live-state" ? "Reading" : "Read NetApp State"}
        </button>
        <button onClick={onValidateSetup} disabled={!probeEnabled || busy || loading} type="button">
          <ShieldCheck size={16} />
          {netappAction === "validate-setup" ? "Validating" : "Validate NetApp Setup"}
        </button>
        <button onClick={onRunNfsSetupPreview} disabled={busy || loading} type="button">
          <ClipboardList size={16} />
          {netappAction === "nfs-setup-preview" ? "Previewing" : "Preview NFS Setup"}
        </button>
        <button onClick={onRunNfsSetupApply} disabled={busy || loading || !nfsSetupApplyReady} title={nfsSetupApplyReady ? "Run guarded NFS setup apply" : "Disabled until NFS setup gates pass"} type="button">
          <Play size={16} />
          {netappAction === "nfs-setup-apply" ? "Applying" : "Apply NFS Setup"}
        </button>
        <button onClick={onValidateNfsSetup} disabled={busy || loading} type="button">
          <ShieldCheck size={16} />
          {netappAction === "nfs-setup-validate" ? "Validating" : "Validate NFS"}
        </button>
        <button onClick={onRunConsoleReadState} disabled={!probeEnabled || busy || loading} type="button">
          <Activity size={16} />
          {netappAction === "console-read-state" ? "Reading" : "Read Console State"}
        </button>
        <button onClick={onRefresh} disabled={busy || loading} type="button">
          <RefreshCw size={16} />
          Refresh Readiness
        </button>
      </div>
      <div className="run-center-preview-grid">
        <NetAppEvidenceTile
          lines={[
            asString(consoleDiscovery?.message) || "Console discovery has not run.",
            `Report: ${asString(discoveryArtifacts.report) || "artifacts/codex-runs/netapp-console-autodiscovery-report.md"}`,
            `Candidate count: ${asString(consoleDiscovery?.candidate_count) || "0"}.`,
            `Probed/skipped: ${asString(consoleDiscovery?.probed_candidate_count) || "0"}/${asString(consoleDiscovery?.skipped_candidate_count) || "0"}.`
          ]}
          tag={labelize(asString(consoleDiscovery?.status) || "not run")}
          title="Console discovery"
        />
        <NetAppEvidenceTile
          lines={[
            asString(consoleState?.message) || "Console state has not been read.",
            `Report: ${asString(stateArtifacts.report) || "artifacts/codex-runs/netapp-console-state-report.md"}`,
            `Selected baud: ${asString(consoleState?.selected_baud) || "not selected"}.`
          ]}
          tag={labelize(asString(consoleState?.status) || "not run")}
          title="Console state"
        />
        <NetAppEvidenceTile
          lines={[
            asString(liveState?.message) || "NetApp live state has not been read.",
            `Report: ${asString(liveArtifacts.state_report) || asString(liveArtifacts.report) || "artifacts/codex-runs/netapp-live-state-report.md"}`,
            `Configured state: ${labelize(configuredState)}.`,
            "Manual env flag not required."
          ]}
          tag={labelize(asString(liveState?.status) || "not run")}
          title="Live state"
        />
        <NetAppEvidenceTile
          lines={[
            asString(nfsSetupPreview?.message) || "NFS setup preview has not loaded.",
            `Preview report: ${asString(nfsSetupArtifacts.report) || "artifacts/codex-runs/netapp-nfs-setup-preview-report.md"}`,
            `Apply report: ${asString(nfsApplyArtifacts.report) || "artifacts/codex-runs/netapp-nfs-setup-apply-report.md"}`,
            `Validation report: ${asString(nfsValidationArtifacts.report) || "artifacts/codex-runs/netapp-nfs-setup-validation-report.md"}`,
            nfsSetupBlockers[0] || "No NFS setup blocker reported."
          ]}
          tag={labelize(asString(nfsSetupPreview?.status) || "not run")}
          title="NFS setup"
        />
        <NetAppEvidenceTile
          lines={[
            asString(nfsVcenterReadiness?.message) || "NFS/vCenter readiness has not loaded.",
            `Report: ${asString(nfsArtifacts.report) || "artifacts/codex-runs/netapp-nfs-vcenter-readiness-report.md"}`,
            asString(nfsTopology.note) || "Only one management path is expected right now."
          ]}
          tag={labelize(asString(nfsVcenterReadiness?.status) || "not run")}
          title="NFS / vCenter"
        />
      </div>
      <NetAppRunCenterIssues
        blockers={[
          ...(consoleDiscovery?.blockers ?? []),
          ...(consoleState?.blockers ?? []),
          ...(liveState?.blockers ?? []),
          ...(nfsSetupPreview?.blockers ?? []),
          ...(nfsSetupApply?.blockers ?? []),
          ...(nfsSetupValidation?.blockers ?? []),
          ...(nfsVcenterReadiness?.blockers ?? [])
        ]}
        removableWarnings={[]}
        warnings={[
          ...(consoleDiscovery?.warnings ?? []),
          ...(consoleState?.warnings ?? []),
          ...(liveState?.warnings ?? []),
          ...(nfsSetupPreview?.warnings ?? []),
          ...(nfsSetupApply?.warnings ?? []),
          ...(nfsSetupValidation?.warnings ?? []),
          ...(nfsVcenterReadiness?.warnings ?? [])
        ]}
      />
      <AdvancedDetails
        className="provider-workflow-details"
        summary="Serial candidates, ranking evidence, and redacted probe payload"
        title="Raw console discovery details"
      >
        <h3>Serial Candidates</h3>
        {discoveryCandidates.length ? (
          <table className="provider-candidate-table">
            <thead>
              <tr>
                <th>Path</th>
                <th>Type</th>
                <th>Access</th>
                <th>In Use</th>
                <th>Rank</th>
                <th>Confidence</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {discoveryCandidates.map((candidate) => {
                const path = asString(candidate.display_path) || asString(candidate.path) || "unknown";
                return (
                  <tr className={path === selectedPort ? "selected-candidate-row" : ""} key={path}>
                    <td>{path}</td>
                    <td>{asString(candidate.path_type) || "-"}</td>
                    <td>{`${asString(candidate.readable) || "false"} / ${asString(candidate.writable) || "false"}`}</td>
                    <td>{asString(candidate.in_use) || "false"}</td>
                    <td>{asString(candidate.rank) || "-"}</td>
                    <td>{labelize(asString(candidate.confidence) || "none")}</td>
                    <td>{stringArray(candidate.selection_reasons).join("; ") || asString(candidate.recommendation) || "-"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <p className="muted">No serial candidates are available in the latest discovery payload.</p>
        )}
        {consoleDiscovery && <JsonDetails title="Raw redacted console discovery result" data={consoleDiscovery} />}
        {consoleState && <JsonDetails title="Raw redacted console state result" data={consoleState} />}
        {liveState && <JsonDetails title="Raw redacted NetApp live state" data={liveState} />}
      </AdvancedDetails>
    </div>
  );
}

function NetAppEvidenceTile({ lines, tag, title }: { lines: string[]; tag: string; title: string }) {
  return (
    <div className="provider-callout">
      <strong>{title}: {tag}</strong>
      {lines.map((line) => (
        <p key={line}>{line}</p>
      ))}
    </div>
  );
}

function NetAppConsoleReadinessPanel({
  onRefresh,
  readiness
}: {
  onRefresh: () => Promise<void> | void;
  readiness: NetAppConsoleReadiness | null;
}) {
  const [form, setForm] = useState<NetAppObservationUpdate>(() => observationFormFromReadiness(readiness));
  const [saveError, setSaveError] = useState("");
  const [saveMessage, setSaveMessage] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setForm(observationFormFromReadiness(readiness));
    setSaveError("");
    setSaveMessage("");
  }, [readiness?.observations?.updated_at]);

  if (!readiness) {
    return (
      <div className="provider-callout">
        <strong>Manual/offline preview</strong>
        <p>Console/bootstrap readiness is loading. No serial ports are opened.</p>
      </div>
    );
  }

  const targets = objectValue(readiness.planned_targets);
  const spTargets = objectValue(targets.controller_sp);
  const managementTargets = objectValue(targets.management_ips);
  const lifRange = objectValue(targets.iscsi_lif_range);
  const observations = readiness.observations;
  const observationSummary = readiness.observation_summary ?? {};

  async function saveObservations(event: FormEvent) {
    event.preventDefault();
    setSaveError("");
    setSaveMessage("");
    if (hasForbiddenNetAppNoteText(form.operator_notes)) {
      setSaveError("Operator notes must not include password, secret, token, credential, authorization, or cookie text.");
      return;
    }
    setSaving(true);
    try {
      await api.saveNetappObservations(form);
      await onRefresh();
      setSaveMessage("Saved locally as operator evidence. Nothing was sent to NetApp.");
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="netapp-console-preview">
      <div className="provider-callout netapp-apply-disabled">
        <strong>Manual/offline only</strong>
        <p>No serial port is opened. No console command, boot interruption, bootstrap, or configuration action is available.</p>
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Bootstrap" value={readiness.bootstrap_enabled ? "Enabled" : "Disabled"} />
        <ProviderFact label="Console Probe" value={readiness.console_probe_enabled ? "Enabled" : "Disabled"} />
        <ProviderFact label="Apply" value={readiness.apply_enabled ? "Enabled" : "Disabled"} />
        <ProviderFact label="Configured State" value={readiness.netapp_configured ? "Verified by live check" : "Not verified"} />
        <ProviderFact label="Manual Env Flag" value="Not required" />
        <ProviderFact label="Controller A SP" value={asString(spTargets.controller_a) || "-"} />
        <ProviderFact label="Controller B SP" value={asString(spTargets.controller_b) || "-"} />
        <ProviderFact label="Cluster Mgmt" value={asString(managementTargets.cluster) || "-"} />
        <ProviderFact label="iSCSI LIFs" value={`${asString(lifRange.start) || "-"} to ${asString(lifRange.end) || "-"}`} />
      </div>
      <h3>Prerequisites</h3>
      <KeyValueTable rows={readiness.prerequisites} labelKey="label" valueKey="status" empty="No console prerequisites are available." />
      <h3>Manual Steps</h3>
      <ol className="netapp-manual-step-list">
        {readiness.manual_steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
      <h3>Expected Prompts / States</h3>
      <KeyValueTable rows={readiness.expected_prompts_or_states} labelKey="label" valueKey="safe_meaning" empty="No expected console states are available." />
      <h3>Readiness Buckets</h3>
      <NetAppReadinessGrid readiness={readiness.readiness_buckets} />
      <h3>Operator Observations</h3>
      <div className="provider-callout">
        <strong>Local evidence capture</strong>
        <p>No serial port is opened, no console command is sent, and these observations are not sent to NetApp.</p>
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Stored Locally" value={observations?.mock_only ? "Test mode store" : "Local evidence"} />
        <ProviderFact label="Sent To NetApp" value={observations?.sent_to_netapp ? "Yes" : "No"} />
        <ProviderFact label="Updated By" value={observations?.updated_by ?? "system"} />
        <ProviderFact label="Updated At" value={observations?.updated_at ? formatDateTime(observations.updated_at) : "-"} />
        <ProviderFact label="Observation Status" value={labelize(asString(observationSummary.status) || "not_recorded")} />
        <ProviderFact label="Manual Checks" value={`${asString(observationSummary.completed_check_count) || "0"} / ${asString(observationSummary.required_check_count) || "0"}`} />
        <ProviderFact label="Optional Checks" value={`${asString(observationSummary.completed_optional_check_count) || "0"} / ${asString(observationSummary.optional_check_count) || "0"}`} />
      </div>
      <form className="netapp-observation-form" onSubmit={saveObservations}>
        <label>
          Observed console state
          <select
            value={form.observed_console_state}
            onChange={(event) =>
              setForm((current) => ({
                ...current,
                observed_console_state: event.target.value as NetAppObservationUpdate["observed_console_state"]
              }))
            }
          >
            {netappConsoleStateOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <div className="netapp-observation-checks">
          {netappObservationChecks.map((check) => (
            <label key={check.key} className="check-row">
              <input
                type="checkbox"
                checked={Boolean(form[check.key])}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    [check.key]: event.target.checked
                  }))
                }
              />
              <span>{check.label}</span>
            </label>
          ))}
        </div>
        <label>
          Operator notes
          <textarea
            maxLength={1200}
            rows={4}
            value={form.operator_notes}
            onChange={(event) =>
              setForm((current) => ({
                ...current,
                operator_notes: event.target.value
              }))
            }
          />
        </label>
        <p className="muted">Do not paste passwords, tokens, or raw configs. Notes are local evidence only and bounded to 1200 characters.</p>
        {saveError && <div className="error">{saveError}</div>}
        {saveMessage && <div className="success">{saveMessage}</div>}
        <div className="form-actions">
          <button type="submit" disabled={saving}>
            <Save size={16} />
            Save Observations
          </button>
          <button type="button" onClick={onRefresh} disabled={saving}>
            <RefreshCw size={16} />
            Refresh Observations
          </button>
        </div>
      </form>
      {readiness.observation_blockers.length > 0 && (
        <>
          <h3>Observation Follow-Up</h3>
          <ul className="issue-list">
            {readiness.observation_blockers.map((blocker) => (
              <li key={blocker}>{blocker}</li>
            ))}
          </ul>
        </>
      )}
      <h3>Console / Bootstrap Blockers</h3>
      <NetAppRunCenterIssues
        blockers={readiness.blockers}
        removableWarnings={readiness.removable_warnings}
        warnings={readiness.warnings}
      />
      <h3>Disabled Console / Bootstrap Actions</h3>
      <DisabledActionList actions={readiness.disabled_actions} />
      <div className="provider-callout">
        <strong>Next safe action</strong>
        <p>{readiness.next_safe_action}</p>
      </div>
    </div>
  );
}

function hasForbiddenNetAppNoteText(value: string): boolean {
  const lowerValue = value.toLowerCase();
  return forbiddenNetAppNoteFragments.some((fragment) => lowerValue.includes(fragment));
}

function NetAppUpgradeCandidateTable({
  candidates,
  empty = "No ONTAP media candidates were found."
}: {
  candidates: NetAppUpgradeReadiness["candidates"];
  empty?: string;
}) {
  if (!candidates.length) {
    return <p className="muted">{empty}</p>;
  }

  return (
    <table className="provider-candidate-table">
      <thead>
        <tr>
          <th>Media</th>
          <th>Version</th>
          <th>Product</th>
          <th>Confidence</th>
        </tr>
      </thead>
      <tbody>
        {candidates.map((candidate) => (
          <tr key={candidate.id}>
            <td>
              <strong>{candidate.redacted_label}</strong>
              <span>{candidate.source}</span>
              {candidate.warnings.length > 0 && <span>{candidate.warnings.join(" ")}</span>}
            </td>
            <td>{candidate.version ?? "-"}</td>
            <td>{candidate.product_hint ?? "-"}</td>
            <td>
              <span className={`candidate-tag ${candidate.match_confidence}`}>
                {labelize(candidate.match_confidence)}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function NetAppProviderArtifactList({ artifacts }: { artifacts: NetAppProviderArtifact[] }) {
  if (!artifacts.length) {
    return <p className="muted">No provider artifact placeholders are available.</p>;
  }

  return (
    <div className="provider-artifact-list">
      {artifacts.map((artifact) => (
        <article className="provider-artifact-item" key={artifact.id}>
          <div className="provider-artifact-head">
            <div>
              <strong>{artifact.title}</strong>
              <p>{artifact.description}</p>
            </div>
            <StatusBadge status={artifact.status} />
          </div>
          <div className="provider-fact-grid compact">
            <ProviderFact label="Provider" value={artifact.provider_id} />
            <ProviderFact label="Kind" value={artifact.kind} />
            <ProviderFact label="Generated" value={formatDateTime(artifact.generated_at)} />
            <ProviderFact label="Download" value={artifact.downloadable ? "Available" : "Unavailable"} />
            <ProviderFact label="Source" value={artifact.mock_only ? "Test mode" : "Historical evidence"} />
            <ProviderFact label="Redacted" value={artifact.redacted ? "true" : "false"} />
          </div>
          <div className="provider-callout">
            <strong>Non-downloadable placeholder</strong>
            <p>
              This metadata points to {asString(artifact.metadata.source_endpoint) || "the plan-preview endpoint"}.
              No report file is written and no archive is available.
            </p>
          </div>
          <div className="tag-row netapp-artifact-row">
            {Object.entries(artifact.metadata).map(([key, value]) => (
              <span key={key}>{labelize(key)}: {asString(value)}</span>
            ))}
          </div>
        </article>
      ))}
    </div>
  );
}

function NetAppRunCenterIssues({
  blockers,
  removableWarnings,
  warnings
}: {
  blockers: string[];
  removableWarnings: string[];
  warnings: string[];
}) {
  if (!blockers.length && !warnings.length && !removableWarnings.length) {
    return <p className="muted">No NetApp blockers or warnings are reported.</p>;
  }

  return (
    <div className="provider-issue-rows">
      {blockers.map((blocker) => (
        <div className="provider-issue blocker" key={blocker}>
          <Ban size={16} />
          <span>{blocker}</span>
        </div>
      ))}
      {warnings.map((warning) => (
        <div className="provider-issue warning" key={warning}>
          <AlertTriangle size={16} />
          <span>{warning}</span>
        </div>
      ))}
      {removableWarnings.map((warning) => (
        <div className="provider-issue warning removable" key={warning}>
          <AlertTriangle size={16} />
          <span>Removable warning: {warning}</span>
        </div>
      ))}
    </div>
  );
}

function PreviewNoteBlock({ fallback, payload }: { fallback: string; payload: Record<string, unknown> }) {
  const notes = stringArray(payload.notes);
  const details = stringArray(payload.details);
  return (
    <div className="provider-callout">
      <strong>{labelize(asString(payload.status) || "placeholder")}</strong>
      {(notes.length ? notes : details).map((item) => (
        <p key={item}>{item}</p>
      ))}
      {!notes.length && !details.length && <p>{fallback}</p>}
    </div>
  );
}

function DisabledActionList({ actions }: { actions: ProviderAction[] }) {
  if (!actions.length) {
    return <p className="muted">No disabled NetApp actions are reported.</p>;
  }

  return (
    <div className="disabled-action-list">
      {actions.map((action) => (
        <div className="disabled-action-row" key={action.id}>
          <Ban size={16} />
          <strong>{action.label}</strong>
          <span>{action.enabled ? "Enabled" : "Disabled"}</span>
          <p>{action.reason}</p>
        </div>
      ))}
    </div>
  );
}

function NewRequest() {
  const navigate = useNavigate();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const tomorrow = new Date(Date.now() + 1000 * 60 * 60 * 24 * 30).toISOString().slice(0, 10);
  const [form, setForm] = useState<VMDeploymentCreate>({
    requester: "local-dev-user",
    environment: "dev",
    site: "lab-a",
    cluster: "compute-a",
    vm_name: "app-dev-001",
    template: "ubuntu-24.04",
    cpu: 2,
    memory_gb: 8,
    disk_gb: 80,
    network: "dev-vlan-100",
    storage_tier: "silver",
    datastore: "",
    owner: "platform-team",
    expiry_date: tomorrow,
    notes: ""
  });

  useEffect(() => {
    api.catalog().then(setCatalog).catch((err: Error) => setError(err.message));
  }, []);

  const clusters = catalog?.clusters_by_site[form.site] ?? [];
  const networks = catalog?.networks.filter((network) => network.environments.includes(form.environment)) ?? [];

  function update<K extends keyof VMDeploymentCreate>(field: K, value: VMDeploymentCreate[K]) {
    setForm((current) => {
      const next = { ...current, [field]: value };
      if (field === "site") {
        const site = String(value);
        next.cluster = catalog?.clusters_by_site[site]?.[0] ?? "";
      }
      if (field === "environment") {
        const env = String(value);
        next.network =
          catalog?.networks.find((network) => network.environments.includes(env))?.name ?? "";
      }
      return next;
    });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    const payload = {
      ...form,
      datastore: form.datastore || null,
      storage_tier: form.storage_tier || null,
      notes: form.notes || null
    };

    try {
      const created = await api.createVmRequest(payload);
      navigate(`/requests/${created.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Page title="New VM Request">
      <Feedback error={error} />
      <form className="form-grid" onSubmit={submit}>
        <Field label="Requester">
          <input value={form.requester} onChange={(event) => update("requester", event.target.value)} />
        </Field>
        <Field label="Environment">
          <select value={form.environment} onChange={(event) => update("environment", event.target.value as VMDeploymentCreate["environment"])}>
            {(catalog?.environments ?? ["dev", "test", "prod"]).map((environment) => (
              <option key={environment} value={environment}>
                {environment}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Site">
          <select value={form.site} onChange={(event) => update("site", event.target.value)}>
            {(catalog?.sites ?? ["lab-a"]).map((site) => (
              <option key={site} value={site}>
                {site}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Cluster">
          <select value={form.cluster} onChange={(event) => update("cluster", event.target.value)}>
            {(clusters.length ? clusters : [form.cluster]).map((cluster) => (
              <option key={cluster} value={cluster}>
                {cluster}
              </option>
            ))}
          </select>
        </Field>
        <Field label="VM Name">
          <input value={form.vm_name} onChange={(event) => update("vm_name", event.target.value)} />
        </Field>
        <Field label="OS/Template">
          <select value={form.template} onChange={(event) => update("template", event.target.value)}>
            {(catalog?.templates ?? ["ubuntu-24.04"]).map((template) => (
              <option key={template} value={template}>
                {template}
              </option>
            ))}
          </select>
        </Field>
        <Field label="CPU">
          <input type="number" min={1} max={64} value={form.cpu} onChange={(event) => update("cpu", Number(event.target.value))} />
        </Field>
        <Field label="Memory GB">
          <input type="number" min={1} max={1024} value={form.memory_gb} onChange={(event) => update("memory_gb", Number(event.target.value))} />
        </Field>
        <Field label="Disk GB">
          <input type="number" min={10} max={65536} value={form.disk_gb} onChange={(event) => update("disk_gb", Number(event.target.value))} />
        </Field>
        <Field label="Network/VLAN">
          <select value={form.network} onChange={(event) => update("network", event.target.value)}>
            {(networks.length ? networks : catalog?.networks ?? []).map((network) => (
              <option key={network.name} value={network.name}>
                {network.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Datastore">
          <select value={form.datastore ?? ""} onChange={(event) => update("datastore", event.target.value)}>
            <option value="">Use storage tier</option>
            {(catalog?.datastores ?? []).map((datastore) => (
              <option key={datastore} value={datastore}>
                {datastore}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Storage Tier">
          <select value={form.storage_tier ?? ""} onChange={(event) => update("storage_tier", event.target.value)}>
            <option value="">Use datastore</option>
            {(catalog?.storage_tiers ?? ["silver"]).map((tier) => (
              <option key={tier} value={tier}>
                {tier}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Owner">
          <input value={form.owner} onChange={(event) => update("owner", event.target.value)} />
        </Field>
        <Field label="Expiry Date">
          <input type="date" value={form.expiry_date} onChange={(event) => update("expiry_date", event.target.value)} />
        </Field>
        <label className="field span-2">
          <span>Notes</span>
          <textarea value={form.notes ?? ""} onChange={(event) => update("notes", event.target.value)} />
        </label>
        <div className="form-actions span-2">
          <button className="primary" type="submit" disabled={submitting}>
            <Plus size={16} />
            Create Request
          </button>
        </div>
      </form>
    </Page>
  );
}

function RequestDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [request, setRequest] = useState<RequestRecord | null>(null);
  const [readiness, setReadiness] = useState<RequestReadiness | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [artifacts, setArtifacts] = useState<ArtifactRecord[]>([]);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [editForm, setEditForm] = useState<VMDeploymentCreate | null>(null);
  const [error, setError] = useState("");
  const [approval, setApproval] = useState({ approver: "change.manager", notes: "" });
  const [busy, setBusy] = useState("");
  const [lastRunId, setLastRunId] = useState("");

  async function load() {
    if (!id) return;
    setError("");
    try {
      const [nextRequest, nextReadiness, auditEvents, nextArtifacts] = await Promise.all([
        api.request(id),
        api.readiness(id),
        api.auditEvents(),
        api.requestArtifacts(id)
      ]);
      setRequest(nextRequest);
      setReadiness(nextReadiness);
      setEditForm(requestToEditForm(nextRequest));
      setEvents(auditEvents.filter((event) => event.request_id === id).slice(0, 8));
      setArtifacts(nextArtifacts);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  useEffect(() => {
    load();
  }, [id]);

  useEffect(() => {
    api.catalog().then(setCatalog).catch((err: Error) => setError(err.message));
  }, []);

  async function runAction(name: string, action: () => Promise<RequestRecord | WorkflowRun>) {
    setBusy(name);
    setError("");
    try {
      const result = await action();
      if ("workflow_slug" in result) {
        setLastRunId(result.id);
        if (name === "execute") {
          navigate(`/workflow-runs/${result.id}`);
        } else {
          await load();
        }
      } else {
        await load();
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy("");
    }
  }

  function updateEdit<K extends keyof VMDeploymentCreate>(field: K, value: VMDeploymentCreate[K]) {
    setEditForm((current) => {
      if (!current) return current;
      const next = { ...current, [field]: value };
      if (field === "site") {
        const site = String(value);
        next.cluster = catalog?.clusters_by_site[site]?.[0] ?? "";
      }
      if (field === "environment") {
        const env = String(value);
        next.network =
          catalog?.networks.find((network) => network.environments.includes(env))?.name ?? "";
      }
      return next;
    });
  }

  async function saveEdit(event: FormEvent) {
    event.preventDefault();
    if (!request || !editForm) return;
    await runAction("save", () => api.updateVmRequest(request.id, buildUpdatePayload(request, editForm)));
  }

  if (!request) {
    return (
      <Page title="Request Detail">
        <Feedback loading={!error} error={error} />
      </Page>
    );
  }

  const canCancel = cancellableStatuses.includes(request.status);
  const canEdit = cancellableStatuses.includes(request.status);
  const canEditIntent = request.status === "draft";
  const lifecycleActions = [
    lifecycleActionState({
      action: "submit",
      busy,
      icon: <Send size={16} />,
      isReady: Boolean(readiness?.ready_for_submit),
      label: "Submit",
      onClick: () => runAction("submit", () => api.submit(request.id)),
      readiness,
      request
    }),
    lifecycleActionState({
      action: "plan",
      busy,
      icon: <Workflow size={16} />,
      isReady: Boolean(readiness?.ready_for_plan),
      label: "Plan",
      onClick: () => runAction("plan", () => api.plan(request.id)),
      readiness,
      request
    }),
    lifecycleActionState({
      action: "execute",
      busy,
      icon: <Play size={16} />,
      isReady: Boolean(readiness?.ready_for_execute),
      label: "Execute",
      onClick: () => runAction("execute", () => api.execute(request.id)),
      readiness,
      request
    }),
    lifecycleActionState({
      action: "cancel",
      busy,
      icon: <XCircle size={16} />,
      isReady: canCancel,
      label: "Cancel",
      onClick: () => runAction("cancel", () => api.cancel(request.id)),
      readiness,
      request
    })
  ];
  const approvalAction = lifecycleActionState({
    action: "approve",
    busy,
    icon: <CheckCircle2 size={16} />,
    isReady: Boolean(readiness?.ready_for_approval),
    label: "Approve",
    onClick: () => runAction("approve", () => api.approve(request.id, approval.approver, approval.notes)),
    readiness,
    request
  });

  return (
    <Page
      title={request.vm_deploy.vm_name}
      actions={
        <>
          <StatusBadge status={request.status} />
          {lastRunId && (
            <ButtonLink to={`/workflow-runs/${lastRunId}`} icon={<Workflow size={16} />} label="Run" />
          )}
        </>
      }
    >
      <Feedback error={error} />
      <ReadinessPanel readiness={readiness} />
      <LifecycleGuardrails readiness={readiness} request={request} />
      <section className="detail-grid">
        <Info label="Request ID" value={request.id} />
        <Info label="Requester" value={request.requester} />
        <Info label="Owner" value={request.owner} />
        <Info label="Environment" value={request.environment} />
        <Info label="Site" value={request.site} />
        <Info label="Cluster" value={request.vm_deploy.cluster} />
        <Info label="Template" value={request.vm_deploy.template} />
        <Info label="CPU" value={String(request.vm_deploy.cpu)} />
        <Info label="Memory" value={`${request.vm_deploy.memory_gb} GB`} />
        <Info label="Disk" value={`${request.vm_deploy.disk_gb} GB`} />
        <Info label="Network" value={request.vm_deploy.network} />
        <Info label="Storage" value={request.vm_deploy.datastore ?? request.vm_deploy.storage_tier ?? ""} />
        <Info label="Expiry" value={formatDate(request.expiry_date)} />
        <Info label="Notes" value={request.notes ?? "-"} />
      </section>
      <section className="panel">
        <PanelTitle icon={<Route size={18} />} title="Lifecycle" />
        <div className="step-row">
          {statusOrder.slice(0, 8).map((status) => (
            <span key={status} className={status === request.status ? "step active" : "step"}>
              {labelize(status)}
            </span>
          ))}
        </div>
        <div className="lifecycle-action-grid">
          {lifecycleActions.map((action) => (
            <LifecycleAction action={action} key={action.label} />
          ))}
          <div className="lifecycle-action">
            <button onClick={load} disabled={Boolean(busy)}>
              <RefreshCw size={16} />
              Refresh
            </button>
            <p>Refresh readiness, lifecycle state, and request audit events.</p>
          </div>
        </div>
      </section>
      <section className="panel">
        <PanelTitle icon={<ShieldCheck size={18} />} title="Approval" />
        <div className="approval-row">
          <input value={approval.approver} onChange={(event) => setApproval({ ...approval, approver: event.target.value })} />
          <input value={approval.notes} placeholder="Notes" onChange={(event) => setApproval({ ...approval, notes: event.target.value })} />
          <button
            className="primary"
            disabled={approvalAction.disabled}
            onClick={approvalAction.onClick}
          >
            {approvalAction.icon}
            {approvalAction.label}
          </button>
        </div>
        <p className={approvalAction.disabled ? "action-reason blocked" : "action-reason ready"}>
          {approvalAction.reason}
        </p>
      </section>
      <section className="panel">
        <PanelTitle icon={<Pencil size={18} />} title={canEditIntent ? "Edit Draft" : "Notes"} />
        {editForm && (
          <EditRequestForm
            catalog={catalog}
            canEdit={canEdit}
            canEditIntent={canEditIntent}
            form={editForm}
            onChange={updateEdit}
            onSubmit={saveEdit}
            saving={busy === "save"}
          />
        )}
      </section>
      <section className="panel" id="artifacts">
        <PanelTitle icon={<HardDrive size={18} />} title="Artifacts And Reports" />
        <ArtifactGrid artifacts={artifacts} empty="No artifact metadata is available for this request yet." />
      </section>
      <section className="panel">
        <PanelTitle icon={<History size={18} />} title="Request Audit Events" />
        <RequestAuditEvents events={events} />
      </section>
    </Page>
  );
}

function ReadinessPanel({ readiness }: { readiness: RequestReadiness | null }) {
  if (!readiness) {
    return (
      <section className="panel">
        <PanelTitle icon={<AlertTriangle size={18} />} title="Readiness" />
        <Feedback loading />
      </section>
    );
  }

  const flags = [
    { label: "Submit", ready: readiness.ready_for_submit },
    { label: "Approval", ready: readiness.ready_for_approval },
    { label: "Plan", ready: readiness.ready_for_plan },
    { label: "Execute", ready: readiness.ready_for_execute }
  ];

  return (
    <section className="panel readiness-panel">
      <div className="readiness-head">
        <PanelTitle icon={<AlertTriangle size={18} />} title="Readiness" />
        <div className="tag-row">
          <span>{readiness.next_action}</span>
          <StatusBadge status={readiness.current_status} />
        </div>
      </div>
      <p className="readiness-summary">{readiness.summary}</p>
      <div className="readiness-flags">
        {flags.map((flag) => (
          <span className={flag.ready ? "ready-flag ready" : "ready-flag"} key={flag.label}>
            {flag.label}
          </span>
        ))}
      </div>
      <div className="issue-grid">
        <IssueList empty="No blockers." issues={readiness.blockers} title="Blockers" />
        <IssueList empty="No warnings." issues={readiness.warnings} title="Warnings" />
      </div>
    </section>
  );
}

function LifecycleGuardrails({
  readiness,
  request
}: {
  readiness: RequestReadiness | null;
  request: RequestRecord;
}) {
  const nextAction = readiness?.next_action && readiness.next_action !== "none"
    ? readiness.next_action
    : nextActionForStatus(request.status);
  const gates = [
    {
      detail: "Locks the draft intent for lifecycle validation.",
      label: "Submit",
      ready: Boolean(readiness?.ready_for_submit)
    },
    {
      detail: "Records a human approval decision before planning.",
      label: "Approval",
      ready: Boolean(readiness?.ready_for_approval)
    },
    {
      detail: "Creates a mock-only dry-run plan for operator review.",
      label: "Plan",
      ready: Boolean(readiness?.ready_for_plan)
    },
    {
      detail: "Requires a persisted preview plan that still matches the request.",
      label: "Execute",
      ready: Boolean(readiness?.ready_for_execute)
    }
  ];

  return (
    <section className="panel lifecycle-guardrail-panel" aria-label="VM request lifecycle guardrails">
      <PanelTitle icon={<ShieldCheck size={18} />} title="Lifecycle Guardrails" />
      <div className="lifecycle-guardrail-summary">
        <div>
          <span>Current state</span>
          <strong>{labelize(request.status)}</strong>
        </div>
        <div>
          <span>Next safe action</span>
          <strong>{labelize(nextAction)}</strong>
        </div>
        <div>
          <span>Mock-only boundary</span>
          <strong>No provider changes</strong>
        </div>
      </div>
      <p>
        VM requests must move through submit, approval, and mock dry-run planning before execute is available.
        These controls stay on the mocked lifecycle API and do not call vCenter, ESXi, storage, network, IPAM, or provider endpoints.
      </p>
      <div className="lifecycle-guardrail-steps">
        {gates.map((gate) => (
          <article className={gate.ready ? "ready" : ""} key={gate.label}>
            <span>{gate.label}</span>
            <strong>{gate.ready ? "Ready" : "Waiting"}</strong>
            <small>{gate.detail}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

function IssueList({
  empty,
  issues,
  title
}: {
  empty: string;
  issues: ReadinessIssue[];
  title: string;
}) {
  return (
    <div className="issue-list">
      <h3>{title}</h3>
      {issues.length ? (
        issues.map((issue) => (
          <article className={`issue issue-${issue.severity}`} key={issue.code}>
            <div>
              {issue.severity === "blocking" ? <Ban size={16} /> : <AlertTriangle size={16} />}
              <strong>{issue.code}</strong>
            </div>
            <p>{issue.message}</p>
            <span>{issue.action}</span>
          </article>
        ))
      ) : (
        <p className="muted">{empty}</p>
      )}
    </div>
  );
}

function EditRequestForm({
  canEdit,
  canEditIntent,
  catalog,
  form,
  onChange,
  onSubmit,
  saving
}: {
  canEdit: boolean;
  canEditIntent: boolean;
  catalog: Catalog | null;
  form: VMDeploymentCreate;
  onChange: <K extends keyof VMDeploymentCreate>(field: K, value: VMDeploymentCreate[K]) => void;
  onSubmit: (event: FormEvent) => void;
  saving: boolean;
}) {
  const clusters = catalog?.clusters_by_site[form.site] ?? [];
  const networks = catalog?.networks.filter((network) => network.environments.includes(form.environment)) ?? [];
  const intentDisabled = !canEdit || !canEditIntent;

  return (
    <form className="form-grid compact-form" onSubmit={onSubmit}>
      <Field label="Requester">
        <input disabled={intentDisabled} value={form.requester} onChange={(event) => onChange("requester", event.target.value)} />
      </Field>
      <Field label="Environment">
        <select
          disabled={intentDisabled}
          value={form.environment}
          onChange={(event) => onChange("environment", event.target.value as VMDeploymentCreate["environment"])}
        >
          {(catalog?.environments ?? ["dev", "test", "prod"]).map((environment) => (
            <option key={environment} value={environment}>
              {environment}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Site">
        <select disabled={intentDisabled} value={form.site} onChange={(event) => onChange("site", event.target.value)}>
          {(catalog?.sites ?? [form.site]).map((site) => (
            <option key={site} value={site}>
              {site}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Cluster">
        <select disabled={intentDisabled} value={form.cluster} onChange={(event) => onChange("cluster", event.target.value)}>
          {(clusters.length ? clusters : [form.cluster]).map((cluster) => (
            <option key={cluster} value={cluster}>
              {cluster}
            </option>
          ))}
        </select>
      </Field>
      <Field label="VM Name">
        <input disabled={intentDisabled} value={form.vm_name} onChange={(event) => onChange("vm_name", event.target.value)} />
      </Field>
      <Field label="OS/Template">
        <select disabled={intentDisabled} value={form.template} onChange={(event) => onChange("template", event.target.value)}>
          {(catalog?.templates ?? [form.template]).map((template) => (
            <option key={template} value={template}>
              {template}
            </option>
          ))}
        </select>
      </Field>
      <Field label="CPU">
        <input disabled={intentDisabled} min={1} max={64} type="number" value={form.cpu} onChange={(event) => onChange("cpu", Number(event.target.value))} />
      </Field>
      <Field label="Memory GB">
        <input disabled={intentDisabled} min={1} max={1024} type="number" value={form.memory_gb} onChange={(event) => onChange("memory_gb", Number(event.target.value))} />
      </Field>
      <Field label="Disk GB">
        <input disabled={intentDisabled} min={10} max={65536} type="number" value={form.disk_gb} onChange={(event) => onChange("disk_gb", Number(event.target.value))} />
      </Field>
      <Field label="Network/VLAN">
        <select disabled={intentDisabled} value={form.network} onChange={(event) => onChange("network", event.target.value)}>
          {(networks.length ? networks : [{ name: form.network }]).map((network) => (
            <option key={network.name} value={network.name}>
              {network.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Datastore">
        <select disabled={intentDisabled} value={form.datastore ?? ""} onChange={(event) => onChange("datastore", event.target.value)}>
          <option value="">Use storage tier</option>
          {(catalog?.datastores ?? []).map((datastore) => (
            <option key={datastore} value={datastore}>
              {datastore}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Storage Tier">
        <select disabled={intentDisabled} value={form.storage_tier ?? ""} onChange={(event) => onChange("storage_tier", event.target.value)}>
          <option value="">Use datastore</option>
          {(catalog?.storage_tiers ?? [String(form.storage_tier ?? "")]).filter(Boolean).map((tier) => (
            <option key={tier} value={tier}>
              {tier}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Owner">
        <input disabled={intentDisabled} value={form.owner} onChange={(event) => onChange("owner", event.target.value)} />
      </Field>
      <Field label="Expiry Date">
        <input disabled={intentDisabled} type="date" value={form.expiry_date} onChange={(event) => onChange("expiry_date", event.target.value)} />
      </Field>
      <label className="field span-2">
        <span>Notes</span>
        <textarea disabled={!canEdit} value={form.notes ?? ""} onChange={(event) => onChange("notes", event.target.value)} />
      </label>
      <div className="form-actions span-2">
        <button className="primary" disabled={!canEdit || saving} type="submit">
          <Save size={16} />
          Save
        </button>
      </div>
    </form>
  );
}

function RequestAuditEvents({ events }: { events: AuditEvent[] }) {
  if (!events.length) {
    return <p className="muted">No audit events for this request.</p>;
  }

  return <AuditEventTable events={events} compact />;
}

function requestToEditForm(request: RequestRecord): VMDeploymentCreate {
  return {
    requester: request.requester,
    environment: request.environment,
    site: request.site,
    cluster: request.vm_deploy.cluster,
    vm_name: request.vm_deploy.vm_name,
    template: request.vm_deploy.template,
    cpu: request.vm_deploy.cpu,
    memory_gb: request.vm_deploy.memory_gb,
    disk_gb: request.vm_deploy.disk_gb,
    network: request.vm_deploy.network,
    datastore: request.vm_deploy.datastore ?? "",
    storage_tier: request.vm_deploy.storage_tier ?? "",
    owner: request.owner,
    expiry_date: request.expiry_date,
    notes: request.notes ?? ""
  };
}

function buildUpdatePayload(request: RequestRecord, form: VMDeploymentCreate): VMDeploymentUpdate {
  const notes = form.notes || null;
  if (request.status !== "draft") {
    return { notes };
  }

  return {
    requester: form.requester,
    environment: form.environment,
    site: form.site,
    cluster: form.cluster,
    vm_name: form.vm_name,
    template: form.template,
    cpu: form.cpu,
    memory_gb: form.memory_gb,
    disk_gb: form.disk_gb,
    network: form.network,
    datastore: form.datastore || null,
    storage_tier: form.storage_tier || null,
    owner: form.owner,
    expiry_date: form.expiry_date,
    notes
  };
}

function WorkflowRunDetail() {
  const { id } = useParams();
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [artifacts, setArtifacts] = useState<ArtifactRecord[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;
    async function load() {
      if (!id) return;
      try {
        const [nextRun, auditEvents, nextArtifacts] = await Promise.all([
          api.workflowRun(id),
          api.auditEvents(),
          api.workflowRunArtifacts(id)
        ]);
        setRun(nextRun);
        setEvents(
          auditEvents.filter((event) => event.workflow_run_id === id || event.request_id === nextRun.request_id)
        );
        setArtifacts(nextArtifacts);
      } catch (err) {
        setError((err as Error).message);
      }
    }

    load();
  }, [id]);

  return (
    <Page
      title="Workflow Run"
      actions={
        run ? (
          <>
            <ButtonLink to={`/requests/${run.request_id}`} icon={<ClipboardList size={16} />} label="Request" />
            <StatusBadge status={run.status} />
          </>
        ) : null
      }
    >
      <Feedback loading={!run && !error} error={error} />
      {run && (
        <>
          <section className="detail-grid">
            <Info label="Run ID" value={run.id} />
            <Info label="Request ID" value={run.request_id} />
            <Info label="Workflow" value={run.workflow_slug} />
            <Info label="Provider" value={run.provider} />
            <Info label="Created" value={formatDateTime(run.created_at)} />
            <Info label="Updated" value={formatDateTime(run.updated_at)} />
          </section>
          <WorkflowRunStructuredView artifacts={artifacts} events={events} run={run} />
        </>
      )}
    </Page>
  );
}

function AuditEvents() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [linkFilter, setLinkFilter] = useState("all");
  const [eventTypeFilter, setEventTypeFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [requestFilter, setRequestFilter] = useState("");
  const [runFilter, setRunFilter] = useState("");
  const [textFilter, setTextFilter] = useState("");

  async function load() {
    setError("");
    setLoading(true);
    try {
      setEvents(await api.auditEvents());
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const eventTypeOptions = uniqueOptions(events.map((event) => event.event_type));
  const statusOptions = uniqueOptions(
    events.flatMap((event) => [event.from_status, event.to_status].filter(isString))
  );
  const filteredEvents = events.filter((event) =>
    auditEventMatchesFilters(event, {
      eventTypeFilter,
      linkFilter,
      requestFilter,
      runFilter,
      statusFilter,
      textFilter
    })
  );

  return (
    <Page
      title="Audit Events"
      actions={
        <button onClick={load} disabled={loading}>
          <RefreshCw size={16} />
          Refresh
        </button>
      }
    >
      <Feedback loading={loading && !events.length} error={error} />
      <section className="panel">
        <PanelTitle icon={<History size={18} />} title="Audit Filters" />
        <div className="audit-filter-grid">
          <Field label="Request ID">
            <input
              placeholder="Request UUID"
              value={requestFilter}
              onChange={(event) => setRequestFilter(event.target.value)}
            />
          </Field>
          <Field label="Run ID">
            <input
              placeholder="Workflow run UUID"
              value={runFilter}
              onChange={(event) => setRunFilter(event.target.value)}
            />
          </Field>
          <Field label="Event Type">
            <select value={eventTypeFilter} onChange={(event) => setEventTypeFilter(event.target.value)}>
              <option value="all">All event types</option>
              {eventTypeOptions.map((eventType) => (
                <option key={eventType} value={eventType}>
                  {eventType}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Status">
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="all">All statuses</option>
              {statusOptions.map((status) => (
                <option key={status} value={status}>
                  {labelize(status)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Links">
            <select value={linkFilter} onChange={(event) => setLinkFilter(event.target.value)}>
              <option value="all">All links</option>
              <option value="requests">Request-linked</option>
              <option value="workflow-runs">Run-linked</option>
              <option value="unlinked">Unlinked</option>
            </select>
          </Field>
          <Field label="Search">
            <input
              placeholder="Message, actor, or payload"
              value={textFilter}
              onChange={(event) => setTextFilter(event.target.value)}
            />
          </Field>
        </div>
      </section>
      <section className="panel">
        <PanelTitle icon={<History size={18} />} title={`Events (${filteredEvents.length})`} />
        <AuditEventTable events={filteredEvents} />
      </section>
    </Page>
  );
}

function ProviderArtifactsPage() {
  const [artifacts, setArtifacts] = useState<NetAppProviderArtifact[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [providerFilter, setProviderFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [kindFilter, setKindFilter] = useState("all");

  async function load() {
    setError("");
    setLoading(true);
    try {
      setArtifacts(await api.providerArtifacts());
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const providerOptions = uniqueOptions(artifacts.map((artifact) => artifact.provider_id));
  const statusOptions = uniqueOptions(artifacts.map((artifact) => artifact.status));
  const kindOptions = uniqueOptions(artifacts.map((artifact) => artifact.kind));
  const filteredArtifacts = artifacts.filter((artifact) => {
    return (
      (providerFilter === "all" || artifact.provider_id === providerFilter) &&
      (statusFilter === "all" || artifact.status === statusFilter) &&
      (kindFilter === "all" || artifact.kind === kindFilter)
    );
  });

  return (
    <Page
      title="Reports / Artifacts"
      actions={
        <button onClick={load} disabled={loading}>
          <RefreshCw size={16} />
          Refresh
        </button>
      }
    >
      <Feedback loading={loading && !artifacts.length} error={error} />
      <section className="panel">
        <PanelTitle icon={<HardDrive size={18} />} title="Provider Artifact Filters" />
        <div className="artifact-filter-grid">
          <Field label="Provider">
            <select value={providerFilter} onChange={(event) => setProviderFilter(event.target.value)}>
              <option value="all">All providers</option>
              {providerOptions.map((provider) => (
                <option key={provider} value={provider}>
                  {provider === "netapp-ontap" ? "NetApp ONTAP" : provider}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Kind">
            <select value={kindFilter} onChange={(event) => setKindFilter(event.target.value)}>
              <option value="all">All kinds</option>
              {kindOptions.map((kind) => (
                <option key={kind} value={kind}>
                  {labelize(kind)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Status">
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="all">All statuses</option>
              {statusOptions.map((status) => (
                <option key={status} value={status}>
                  {labelize(status)}
                </option>
              ))}
            </select>
          </Field>
        </div>
      </section>
      <section className="panel">
        <PanelTitle icon={<HardDrive size={18} />} title={`Provider Artifacts (${filteredArtifacts.length})`} />
        <ProviderArtifactsList artifacts={filteredArtifacts} />
      </section>
    </Page>
  );
}

function ProviderArtifactsList({ artifacts }: { artifacts: NetAppProviderArtifact[] }) {
  if (!artifacts.length) {
    return (
      <p className="muted">
        No provider artifact metadata matches the current filters. Historical provider evidence appears here when a report records artifact metadata.
      </p>
    );
  }

  return (
    <div className="provider-artifact-list">
      {artifacts.map((artifact) => (
        <ProviderArtifactCard artifact={artifact} key={artifact.id} />
      ))}
    </div>
  );
}

function ProviderArtifactCard({ artifact }: { artifact: NetAppProviderArtifact }) {
  return (
    <article className="provider-artifact-item">
      <div className="provider-artifact-head">
        <div>
          <strong>{artifact.title}</strong>
          <p>{artifact.description}</p>
        </div>
        <StatusBadge status={artifact.status} />
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Provider" value={artifact.provider_id} />
        <ProviderFact label="Kind" value={labelize(artifact.kind)} />
        <ProviderFact label="Generated" value={formatDateTime(artifact.generated_at)} />
        <ProviderFact label="Source" value={artifact.mock_only ? "Test mode" : "Historical evidence"} />
        <ProviderFact label="Redacted" value={artifact.redacted ? "true" : "false"} />
        <ProviderFact label="Downloadable" value={artifact.downloadable ? "true" : "false"} />
        <ProviderFact label="Source Endpoint" value={asString(artifact.metadata.source_endpoint) || "-"} />
        <ProviderFact label="No ONTAP Calls" value={asBoolean(artifact.metadata.no_ontap_calls) ? "true" : "false"} />
      </div>
      <div className="artifact-download-row">
        <button disabled>
          <Ban size={16} />
          Download unavailable
        </button>
        <span className="action-tag disabled">Placeholder</span>
        <p>No file, report archive, raw config, or provider bundle is generated.</p>
      </div>
      <div className="tag-row netapp-artifact-row">
        {Object.entries(artifact.metadata).map(([key, value]) => (
          <span key={key}>{labelize(key)}: {asString(value)}</span>
        ))}
      </div>
    </article>
  );
}

function MediaInventoryPage() {
  const [inventory, setInventory] = useState<MediaInventory | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.mediaInventory().then(setInventory).catch((err: Error) => setError(err.message));
  }, []);

  const items = inventory?.items ?? [];

  return (
    <Page title="Media Inventory" actions={inventory ? <StatusBadge status={inventory.mode} /> : null}>
      <Feedback loading={!inventory && !error} error={error} />
      {inventory && (
        <>
          <section className="metric-grid">
            <Metric label="Items" value={items.length} icon={<HardDrive size={18} />} />
            <Metric label="ISO" value={items.filter((item) => item.category === "iso").length} icon={<ClipboardList size={18} />} />
            <Metric label="OVF/OVA" value={items.filter((item) => ["ovf", "ova"].includes(item.category)).length} icon={<Layers size={18} />} />
            <Metric label="Firmware" value={items.filter((item) => item.category === "firmware").length} icon={<ShieldCheck size={18} />} />
          </section>
          <section className="panel safety-note">
            <PanelTitle icon={<ShieldCheck size={18} />} title="Metadata-Only Safety" />
            <p>
              Media inventory shows local media filenames when the backend can safely expose them, and redacts names for
              sources that require privacy. It does not copy, mount, parse, or deploy local media.
            </p>
          </section>
          {inventory.warnings.length > 0 && (
            <section className="panel">
              <PanelTitle icon={<AlertTriangle size={18} />} title="Warnings" />
              <div className="issue-list">
                {inventory.warnings.map((warning) => (
                  <article className="issue issue-warning" key={warning}>
                    <div>
                      <AlertTriangle size={16} />
                      <strong>media_inventory</strong>
                    </div>
                    <p>{warning}</p>
                  </article>
                ))}
              </div>
            </section>
          )}
          <section className="panel">
            <PanelTitle icon={<HardDrive size={18} />} title="Local Metadata" />
            {items.length ? (
              <table>
                <thead>
                  <tr>
                    <th>File</th>
                    <th>Category</th>
                    <th>Extension</th>
                    <th>Size</th>
                    <th>Source</th>
                    <th>Redacted</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={`${mediaInventoryItemName(item)}-${item.placeholder_name}-${item.source}`}>
                      <td>{mediaInventoryItemName(item)}</td>
                      <td>{item.category}</td>
                      <td>{item.extension || "-"}</td>
                      <td>{formatBytes(item.size_bytes)}</td>
                      <td>{item.source}</td>
                      <td>{yesNo(item.actual_name_redacted)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="muted">No media metadata found.</p>
            )}
          </section>
        </>
      )}
    </Page>
  );
}

function LabProfilesPage({
  error,
  loading,
  onReload,
  onStateChange,
  state
}: {
  error: string;
  loading: boolean;
  onReload: () => Promise<void>;
  onStateChange: (state: LabProfileList) => void;
  state: LabProfileList | null;
}) {
  async function activateProfile(profileId: string) {
    onStateChange(await api.activateLabProfile(profileId));
  }

  return (
    <Page
      title="Saved Lab Setups"
      actions={
        <>
          <button onClick={onReload} disabled={loading}>
            <RefreshCw size={16} />
            Refresh
          </button>
        </>
      }
    >
      <LabProfileManager
        error={error}
        loading={loading}
        onActivateProfile={activateProfile}
        onReload={onReload}
        state={state}
      />
      <SettingsGlobalProfilePanel
        activeProfile={state?.active_profile ?? null}
        onSaved={onReload}
      />
    </Page>
  );
}

function LabProfileManager({
  error,
  loading,
  onActivateProfile,
  onReload,
  showMetrics = true,
  state
}: {
  error: string;
  loading: boolean;
  onActivateProfile: (profileId: string) => Promise<void>;
  onReload: () => Promise<void>;
  showMetrics?: boolean;
  state: LabProfileList | null;
}) {
  const [selectedProfileId, setSelectedProfileId] = useState("");
  const [formInitialized, setFormInitialized] = useState(false);
  const [form, setForm] = useState<LabProfileFormState>(() => blankLabProfileForm());
  const [saveError, setSaveError] = useState("");
  const [busyAction, setBusyAction] = useState("");
  const activeProfile = state?.active_profile ?? null;
  const selectedProfile =
    state?.profiles.find((profile) => profile.id === selectedProfileId) ?? null;
  const subnetOptions = state?.subnet_options.length
    ? state.subnet_options
    : defaultLabSubnetOptions();
  const selectedSubnetPrefix = parseSubnetPrefix(form.globalSettings.subnetPrefix);
  const selectedSubnetOption =
    subnetOptions.find((option) => option.prefix === selectedSubnetPrefix) ?? null;
  const netappSupported = labNetAppSupported(selectedSubnetPrefix);
  const netappDisabledReason =
    selectedSubnetOption?.netapp_disabled_reason ??
    "NetApp capabilities are disabled for this subnet size.";

  useEffect(() => {
    if (!state || formInitialized) return;
    const initialProfile =
      state.active_profile.source === "saved" ? state.active_profile : state.profiles[0] ?? null;
    if (initialProfile) {
      setSelectedProfileId(initialProfile.id);
      setForm(labProfileFormFrom(initialProfile));
    }
    setFormInitialized(true);
  }, [formInitialized, state]);

  function startNewProfile() {
    setSelectedProfileId("");
    setForm(blankLabProfileForm());
    setFormInitialized(true);
    setSaveError("");
  }

  function loadProfile(profile: LabProfile) {
    setSelectedProfileId(profile.id);
    setForm(labProfileFormFrom(profile));
    setFormInitialized(true);
    setSaveError("");
  }

  function loadRuntimeProfile() {
    if (!state) return;
    setSelectedProfileId("");
    setForm(labProfileFormFrom(state.runtime_profile));
    setFormInitialized(true);
    setSaveError("");
  }

  function updateSubnetPrefix(prefix: string) {
    setForm((current) => applyLabSubnetChoice(current, current.addresses.subnet, prefix));
  }

  function updateSubnetNetwork(subnet: string) {
    setForm((current) => applyLabSubnetChoice(current, subnet, current.globalSettings.subnetPrefix));
  }

  function updateGlobalSetting<K extends keyof LabGlobalSettingsFormState>(
    key: K,
    value: LabGlobalSettingsFormState[K]
  ) {
    setForm((current) => ({
      ...current,
      globalSettings: {
        ...current.globalSettings,
        [key]: value
      }
    }));
  }

  function updateAddress(key: LabAddressInputKey, value: string) {
    setForm((current) => ({
      ...current,
      addresses: {
        ...current.addresses,
        [key]: value
      }
    }));
  }

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    setSaveError("");
    const action = selectedProfile ? "update" : "create";
    setBusyAction(action);
    try {
      const payload = labProfilePayload(form);
      const saved = selectedProfile
        ? await api.updateLabProfile(selectedProfile.id, payload)
        : await api.createLabProfile(payload);
      setSelectedProfileId(saved.id);
      setForm(labProfileFormFrom(saved));
      setFormInitialized(true);
      await onReload();
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setBusyAction("");
    }
  }

  async function saveAsNew() {
    setSaveError("");
    setBusyAction("create");
    try {
      const saved = await api.createLabProfile(labProfilePayload(form));
      setSelectedProfileId(saved.id);
      setForm(labProfileFormFrom(saved));
      setFormInitialized(true);
      await onReload();
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setBusyAction("");
    }
  }

  async function activateProfile(profileId: string) {
    setSaveError("");
    setBusyAction(`activate-${profileId}`);
    try {
      await onActivateProfile(profileId);
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setBusyAction("");
    }
  }

  return (
    <>
      <Feedback loading={loading && !state} error={error} />
      {state && activeProfile && (
        <>
          {showMetrics && (
            <section className="metric-grid lab-profile-metrics">
              <Metric label="Saved Labs" value={state.profiles.length} icon={<Layers size={18} />} />
              <Metric
                label="Active Version"
                value={activeProfile.version}
                icon={<History size={18} />}
              />
              <Metric
                label="Active History"
                value={activeProfile.history.length}
                icon={<ClipboardList size={18} />}
              />
              <Metric
                label="Address Fields"
                value={labAddressFields.length + 1}
                icon={<Route size={18} />}
              />
              <Metric label="Subnet Sizes" value={subnetOptions.length} icon={<Route size={18} />} />
            </section>
          )}

          <section className="panel active-lab-panel">
            <div className="readiness-head">
              <PanelTitle icon={<Layers size={18} />} title="Active Lab" />
              <StatusBadge status={activeProfile.source === "runtime_env" ? "local" : "current"} />
            </div>
            <div className="provider-fact-grid compact">
              <ProviderFact label="Name" value={activeProfile.name} />
              <ProviderFact label="Source" value={labelize(activeProfile.source)} />
              <ProviderFact label="Version" value={`v${activeProfile.version}`} />
              <ProviderFact label="Store" value={state.store_path} />
            </div>
            <LabAddressSummary profile={activeProfile} />
            <div className="action-row">
              <button
                disabled={busyAction === "activate-runtime" || activeProfile.id === "runtime"}
                onClick={() => activateProfile("runtime")}
                type="button"
              >
                <Server size={16} />
                Runtime
              </button>
              <button onClick={loadRuntimeProfile} type="button">
                <Pencil size={16} />
                Load Runtime
              </button>
            </div>
          </section>

          <div className="lab-profile-layout">
            <section className="panel">
              <PanelTitle icon={<Layers size={18} />} title="Saved Labs" />
              <div className="action-row">
                <button onClick={startNewProfile} type="button">
                  <Plus size={16} />
                  New Lab
                </button>
              </div>
              {state.profiles.length ? (
                <div className="lab-profile-list">
                  {state.profiles.map((profile) => (
                    <article
                      className={
                        profile.id === selectedProfileId
                          ? "lab-profile-row selected"
                          : "lab-profile-row"
                      }
                      key={profile.id}
                    >
                      <div>
                        <strong>{profile.name}</strong>
                        <span>{labelize(profile.profile_topology)} · {displayAddress(profile.address_plan.subnet)}</span>
                      </div>
                      <StatusBadge status={profile.active ? "current" : "available"} />
                      <div className="lab-profile-row-actions">
                        <button onClick={() => loadProfile(profile)} type="button">
                          <Pencil size={16} />
                          Edit
                        </button>
                        <button
                          disabled={profile.active || busyAction === `activate-${profile.id}`}
                          onClick={() => activateProfile(profile.id)}
                          type="button"
                        >
                          <CheckCircle2 size={16} />
                          Activate
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="muted">No saved lab setups.</p>
              )}
            </section>

            <section className="panel">
              <PanelTitle
                icon={<Save size={18} />}
                title={selectedProfile ? `Edit ${selectedProfile.name}` : "Create Lab"}
              />
              <form className="lab-profile-form" onSubmit={saveProfile}>
                <section className="lab-profile-form-section">
                  <div className="lab-profile-form-grid">
                    <Field label="Name">
                      <input
                        minLength={2}
                        onChange={(event) => setForm({ ...form, name: event.target.value })}
                        required
                        value={form.name}
                      />
                    </Field>
                    <Field label="Description">
                      <textarea
                        onChange={(event) =>
                          setForm({ ...form, description: event.target.value })
                        }
                        value={form.description}
                      />
                    </Field>
                  </div>
                </section>

                <section className="lab-profile-form-section">
                  <div className="readiness-head compact-head">
                    <strong>Global Settings</strong>
                    <StatusBadge status={netappSupported ? "available" : "blocked"} />
                  </div>
                  <div className="lab-profile-form-grid">
                    <Field label="Subnet Size">
                      <select
                        onChange={(event) => updateSubnetPrefix(event.target.value)}
                        value={form.globalSettings.subnetPrefix}
                      >
                        {subnetOptions.map((option) => (
                          <option key={option.prefix} value={option.prefix}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Topology">
                      <select
                        onChange={(event) => setForm({ ...form, profileTopology: event.target.value })}
                        value={form.profileTopology}
                      >
                        <option value="high_address_lab">High-address /24</option>
                        <option value="compact_edge_lab">Compact edge</option>
                        <option value="custom">Custom</option>
                      </select>
                    </Field>
                    <Field label={labSubnetField.label}>
                      <input
                        inputMode="decimal"
                        onChange={(event) => updateSubnetNetwork(event.target.value)}
                        value={form.addresses.subnet}
                      />
                    </Field>
                    <Field label="Gateway">
                      <input
                        inputMode="decimal"
                        onChange={(event) => updateGlobalSetting("gateway", event.target.value)}
                        value={form.globalSettings.gateway}
                      />
                    </Field>
                    <Field label="Domain">
                      <input
                        onChange={(event) => updateGlobalSetting("domainName", event.target.value)}
                        value={form.globalSettings.domainName}
                      />
                    </Field>
                    <Field label="DNS Servers">
                      <input
                        inputMode="decimal"
                        onChange={(event) => updateGlobalSetting("dnsServers", event.target.value)}
                        value={form.globalSettings.dnsServers}
                      />
                    </Field>
                    <Field label="NTP Servers">
                      <input
                        inputMode="decimal"
                        onChange={(event) => updateGlobalSetting("ntpServers", event.target.value)}
                        value={form.globalSettings.ntpServers}
                      />
                    </Field>
                    <Field label="Timezone">
                      <input
                        onChange={(event) => updateGlobalSetting("timezone", event.target.value)}
                        value={form.globalSettings.timezone}
                      />
                    </Field>
                    <Field label="VLAN ID">
                      <input
                        inputMode="numeric"
                        onChange={(event) => updateGlobalSetting("vlanId", event.target.value)}
                        value={form.globalSettings.vlanId}
                      />
                    </Field>
                    <Field label="MTU">
                      <input
                        inputMode="numeric"
                        onChange={(event) => updateGlobalSetting("mtu", event.target.value)}
                        value={form.globalSettings.mtu}
                      />
                    </Field>
                    <Field label="vCenter">
                      <label className="checkbox-line">
                        <input
                          checked={form.globalSettings.vcenterEnabled && netappSupported}
                          disabled={!netappSupported}
                          onChange={(event) => updateGlobalSetting("vcenterEnabled", event.target.checked)}
                          type="checkbox"
                        />
                        <span>{netappSupported ? "Include vCenter readiness" : "Not in scope for compact profile"}</span>
                      </label>
                    </Field>
                    <Field label="Storage Protocol">
                      <select
                        disabled={!netappSupported}
                        onChange={(event) => updateGlobalSetting("storageProtocol", event.target.value)}
                        value={form.globalSettings.storageProtocol}
                      >
                        <option value="nfs">NFS</option>
                        <option value="iscsi">iSCSI</option>
                        <option value="none">Local only</option>
                      </select>
                    </Field>
                  </div>
                  <div className="global-policy-grid">
                    <label className="checkbox-line">
                      <input
                        checked={form.globalSettings.enableDns}
                        onChange={(event) => updateGlobalSetting("enableDns", event.target.checked)}
                        type="checkbox"
                      />
                      <span>DNS assigned globally</span>
                    </label>
                    <label className="checkbox-line">
                      <input
                        checked={form.globalSettings.enableNtp}
                        onChange={(event) => updateGlobalSetting("enableNtp", event.target.checked)}
                        type="checkbox"
                      />
                      <span>NTP assigned globally</span>
                    </label>
                    <label className="checkbox-line">
                      <input
                        checked={form.globalSettings.enableSnmp}
                        onChange={(event) => updateGlobalSetting("enableSnmp", event.target.checked)}
                        type="checkbox"
                      />
                      <span>SNMP assigned globally</span>
                    </label>
                    <label className="checkbox-line">
                      <input
                        checked={form.globalSettings.disableIpv6}
                        onChange={(event) => updateGlobalSetting("disableIpv6", event.target.checked)}
                        type="checkbox"
                      />
                      <span>Disable IPv6 globally</span>
                    </label>
                  </div>
                </section>

                <section className="lab-profile-form-section">
                  <div className="readiness-head compact-head">
                    <strong>Core Addresses</strong>
                    <StatusBadge status="intent_only" />
                  </div>
                  <div className="lab-profile-form-grid">
                    {labCoreAddressFields.map((field) => (
                      <Field key={field.key} label={field.label}>
                        <input
                          inputMode="decimal"
                          onChange={(event) => updateAddress(field.key, event.target.value)}
                          value={form.addresses[field.key]}
                        />
                      </Field>
                    ))}
                  </div>
                </section>

                <section className="lab-profile-form-section">
                  <div className="readiness-head compact-head">
                    <strong>NetApp Capabilities</strong>
                    <StatusBadge status={netappSupported ? "available" : "blocked"} />
                  </div>
                  {netappSupported ? (
                    <div className="lab-profile-form-grid">
                      {labNetAppAddressFields.map((field) => (
                        <Field key={field.key} label={field.label}>
                          <input
                            inputMode="decimal"
                            onChange={(event) => updateAddress(field.key, event.target.value)}
                            value={form.addresses[field.key]}
                          />
                        </Field>
                      ))}
                      <Field label="NetApp NFS LIFs">
                        <input
                          inputMode="decimal"
                          onChange={(event) =>
                            setForm({ ...form, netappNfsLifs: event.target.value })
                          }
                          value={form.netappNfsLifs}
                        />
                      </Field>
                      <Field label="NetApp iSCSI LIFs">
                        <input
                          inputMode="decimal"
                          onChange={(event) =>
                            setForm({ ...form, netappIscsiLifs: event.target.value })
                          }
                          value={form.netappIscsiLifs}
                        />
                      </Field>
                    </div>
                  ) : (
                    <div className="provider-callout netapp-capability-disabled">
                      <StatusBadge status="not_in_scope" />
                      <strong>NetApp and vCenter not in scope for /{form.globalSettings.subnetPrefix}</strong>
                      <p>{netappDisabledReason}</p>
                    </div>
                  )}
                </section>
                <Feedback error={saveError} />
                <div className="form-actions">
                  {selectedProfile && (
                    <button
                      disabled={Boolean(busyAction)}
                      onClick={saveAsNew}
                      type="button"
                    >
                      <Plus size={16} />
                      Save New
                    </button>
                  )}
                  <button className="primary" disabled={Boolean(busyAction)} type="submit">
                    <Save size={16} />
                    {selectedProfile ? "Update Profile" : "Create Profile"}
                  </button>
                </div>
              </form>
            </section>
          </div>

          <section className="panel">
            <PanelTitle icon={<History size={18} />} title="Version History" />
            {selectedProfile && selectedProfile.history.length ? (
              <table>
                <thead>
                  <tr>
                    <th>Version</th>
                    <th>Saved</th>
                    <th>Name</th>
                    <th>Subnet</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedProfile.history.map((revision) => (
                    <tr key={`${selectedProfile.id}-${revision.version}-${revision.saved_at}`}>
                      <td>v{revision.version}</td>
                      <td>{formatDateTime(revision.saved_at)}</td>
                      <td>{revision.name}</td>
                      <td>{displayAddress(revision.address_plan.subnet)}</td>
                      <td>
                        <button
                          className="small-button"
                          onClick={() => setForm(labProfileFormFrom(revision))}
                          type="button"
                        >
                          Load
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="muted">No previous versions for the selected saved lab.</p>
            )}
          </section>
        </>
      )}
    </>
  );
}

function LabAddressSummary({ profile }: { profile: LabProfile }) {
  const plan = profile.resolved_address_plan ?? profile.address_plan;
  const features = profile.features;
  const disabled = disabledFeaturesFromProfile(profile);
  return (
    <div className="provider-fact-grid compact lab-address-summary">
      <ProviderFact label="Topology" value={labelize(profile.profile_topology)} />
      <ProviderFact label="Subnet Size" value={`/${profile.global_settings.subnet_prefix}`} />
      <ProviderFact label="Gateway" value={displayAddress(profile.global_settings.gateway)} />
      <ProviderFact
        label="NetApp Capability"
        value={
          features.netapp_enabled
            ? "Available"
            : disabled.netapp ?? profile.global_settings.netapp_disabled_reason ?? "Not in scope"
        }
      />
      <ProviderFact
        label="vCenter"
        value={features.vcenter_enabled ? "In scope" : disabled.vcenter ?? "Not in scope"}
      />
      <ProviderFact
        label="Storage Protocol"
        value={features.storage_protocol ? String(features.storage_protocol).toUpperCase() : "None"}
      />
      {labAddressFields.map((field) => (
        <ProviderFact
          key={field.key}
          label={field.label}
          value={displayAddress(plan[field.key])}
        />
      ))}
      <ProviderFact
        label="NetApp NFS LIFs"
        value={plan.netapp_nfs_lifs.join(", ") || "Not in scope"}
      />
      <ProviderFact
        label="NetApp iSCSI LIFs"
        value={plan.netapp_iscsi_lifs.join(", ") || "Not in scope"}
      />
      {profile.devices.switch_secondary && (
        <ProviderFact label="Second Switch" value={displayAddress(profile.devices.switch_secondary)} />
      )}
      {profile.devices.ups && <ProviderFact label="UPS" value={displayAddress(profile.devices.ups)} />}
      {profile.devices.backup_storage && (
        <ProviderFact label="Backup Storage" value={displayAddress(profile.devices.backup_storage)} />
      )}
      {profile.devices.utility_vm && <ProviderFact label="Utility VM" value={displayAddress(profile.devices.utility_vm)} />}
      {profile.not_in_scope_stages.length > 0 && (
        <ProviderFact label="Not In Scope" value={profile.not_in_scope_stages.map(labelize).slice(0, 6).join(", ")} />
      )}
    </div>
  );
}

function ControlCenterPage() {
  const { isAdvancedMode } = useUiMode();
  const { activeContext, activeProfile, onReload: reloadLabProfiles } = useLabProfileContext();
  const { reloadReportIssues } = useReportIssues();
  const [catalog, setCatalog] = useState<ControlActionCatalog | null>(null);
  const [workflowActions, setWorkflowActions] = useState<WorkflowAction[]>([]);
  const [activeSectionId, setActiveSectionId] = useState<ControlCenterSectionId>("lab-profile");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState("");
  const [busyAccessSection, setBusyAccessSection] = useState("");
  const [accessError, setAccessError] = useState("");
  const [planResult, setPlanResult] = useState<ControlActionPlan | null>(null);
  const [selectedWorkflowActionId, setSelectedWorkflowActionId] = useState("");
  const [runningWorkflowActionId, setRunningWorkflowActionId] = useState("");
  const [workflowActionRunResults, setWorkflowActionRunResults] = useState<Record<string, WorkflowActionRun>>({});
  const [copyMessage, setCopyMessage] = useState("");
  const location = useLocation();

  async function load() {
    setError("");
    setLoading(true);
    const loadErrors: string[] = [];
    await Promise.all([
      api.workflowActions()
        .then(setWorkflowActions)
        .catch((err: Error) => loadErrors.push(`Workflow actions: ${err.message}`)),
      api.controlActions()
        .then(setCatalog)
        .catch((err: Error) => loadErrors.push(`Control catalog: ${err.message}`))
    ]);
    if (loadErrors.length) {
      setError(loadErrors.join(" "));
    }
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    const querySection = new URLSearchParams(location.search).get("section");
    const allowed: ControlCenterSectionId[] = [
      "lab-profile",
      "cisco",
      "ilo",
      "raid",
      "esxi",
      "netapp",
      "vcenter",
      "firmware-upgrade",
      "verification",
      "reports",
      "action-catalog"
    ];
    if (querySection && allowed.includes(querySection as ControlCenterSectionId)) {
      setActiveSectionId(querySection as ControlCenterSectionId);
    }
    const queryAction = new URLSearchParams(location.search).get("action");
    if (queryAction) {
      setSelectedWorkflowActionId(queryAction);
    }
  }, [location.search]);

  async function planAction(action: ControlAction) {
    setBusyAction(action.id);
    setError("");
    try {
      setPlanResult(await api.planControlAction(action.id));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyAction("");
    }
  }

  async function copyText(text: string, label: string) {
    setCopyMessage("");
    try {
      await navigator.clipboard.writeText(text);
      setCopyMessage(`${label} copied.`);
    } catch {
      setCopyMessage("Copy is unavailable in this browser session.");
    }
  }

  function copyAction(action: ControlAction) {
    const text =
      action.suggested_command ||
      (action.api_endpoint ? `${action.method ?? "GET"} ${action.api_endpoint}` : action.plan_endpoint);
    copyText(text, action.label);
  }

  function copyWorkflowAction(action: WorkflowAction) {
    copyText(workflowActionCopyText(action), action.label);
  }

  async function runWorkflowAction(action: WorkflowAction, request?: WorkflowActionRunRequest) {
    setError("");
    setRunningWorkflowActionId(action.action_id);
    try {
      const result = await api.runWorkflowAction(action.action_id, request);
      setWorkflowActionRunResults((current) => ({ ...current, [action.action_id]: result }));
      await load();
      await reloadReportIssues();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunningWorkflowActionId("");
    }
  }

  async function saveGlobalConfig(values: GlobalConfigEditState) {
    if (!activeProfile || activeProfile.source !== "saved") {
      throw new Error("Save the active runtime values as a saved lab setup before editing global config here.");
    }
    setBusyAction("global-config");
    setError("");
    try {
      const form = labProfileFormFrom(activeProfile);
      form.globalSettings = {
        ...form.globalSettings,
        ...values
      };
      await api.updateLabProfile(activeProfile.id, labProfilePayload(form));
      await reloadLabProfiles();
      await load();
      await reloadReportIssues();
    } finally {
      setBusyAction("");
    }
  }

  async function saveProfileConfig(form: LabProfileFormState) {
    if (!activeProfile) {
      throw new Error("Load the active lab setup before editing values here.");
    }
    setBusyAction("profile-config");
    setError("");
    try {
      const nextForm = controlProfileFormForSave(form, activeProfile);
      const payload = labProfilePayload(nextForm);
      if (activeProfile.source === "saved") {
        await api.updateLabProfile(activeProfile.id, payload);
      } else {
        await api.createLabProfile(payload);
      }
      await reloadLabProfiles();
      await load();
      await reloadReportIssues();
    } catch (err) {
      setError((err as Error).message);
      throw err;
    } finally {
      setBusyAction("");
    }
  }

  async function saveAccessConfig(sectionId: string, payload: ControlAccessConfigWrite) {
    setBusyAccessSection(sectionId);
    setAccessError("");
    try {
      const updated = await api.updateControlAccessConfig(sectionId, payload);
      setCatalog((current) => {
        if (!current) return current;
        return {
          ...current,
          sections: current.sections.map((section) =>
            section.id === sectionId ? { ...section, access_config: updated } : section
          )
        };
      });
    } catch (err) {
      setAccessError((err as Error).message);
    } finally {
      setBusyAccessSection("");
    }
  }

  const sections = catalog?.sections ?? [];
  const actions = catalog?.actions ?? [];
  const registryBlockedActions = workflowActions.filter((action) => action.current_availability === "blocked").length;
  const upgradeActions = actions.filter((action) => action.classification === "upgrade").length;
  const registryUpgradeActions = workflowActions.filter((action) => action.mode === "upgrade").length;
  const commanderActions = actions.filter((action) => action.id.startsWith("commander."));
  const netappInScope = activeContext?.enabled_features.netapp_enabled ?? activeProfile?.features.netapp_enabled ?? true;
  const visibleSections: ControlCenterSectionId[] = [
    "lab-profile",
    "cisco",
    "ilo",
    "raid",
    "esxi",
    ...(netappInScope || isAdvancedMode ? (["netapp"] as ControlCenterSectionId[]) : []),
    "vcenter",
    "firmware-upgrade",
    "verification",
    "reports",
    "action-catalog"
  ];
  const activeRegistryStageId = workflowStageIdForControlSection(activeSectionId);
  const scopedWorkflowActions =
    activeSectionId === "action-catalog"
      ? workflowActions
      : workflowActions.filter((action) => action.stage === activeRegistryStageId);
  const visibleScopedWorkflowActions = isAdvancedMode ? scopedWorkflowActions : operatorVisibleWorkflowActions(scopedWorkflowActions);
  const selectedSection =
    activeSectionId === "action-catalog"
      ? null
      : sections.find((section) => section.id === activeSectionId) ?? null;
  const selectedActions = selectedSection?.actions ?? actions;
  const selectedBlockers = uniqueStrings(selectedActions.flatMap((action) => (action.blocker ? [action.blocker] : [])));
  const selectedWorkflowAction =
    visibleScopedWorkflowActions.find((action) => action.action_id === selectedWorkflowActionId) ??
    visibleScopedWorkflowActions[0] ??
    null;
  const selectedCatalogBlockers =
    visibleScopedWorkflowActions.length
      ? uniqueStrings([
          ...selectedBlockers,
          ...visibleScopedWorkflowActions.flatMap((action) => action.blockers.slice(0, 1))
        ])
      : selectedBlockers;
  const generatedLabel = catalog?.generated_at ? formatDateTime(catalog.generated_at) : "Registry";
  const scopedActionKeySignature = visibleScopedWorkflowActions.map((action) => action.action_id).join("|");
  const waitingForControlCatalog = activeSectionId !== "action-catalog" && !catalog;
  const waitingForActionCatalog = activeSectionId === "action-catalog" && !workflowActions.length;
  const showControlCenterLoading = loading && (waitingForControlCatalog || waitingForActionCatalog);
  const canRenderControlSurface = Boolean(catalog) || activeSectionId === "action-catalog";

  useEffect(() => {
    if (!visibleSections.includes(activeSectionId)) {
      setActiveSectionId(visibleSections[0] ?? "lab-profile");
    }
  }, [activeSectionId, isAdvancedMode, netappInScope]);

  useEffect(() => {
    if (!visibleScopedWorkflowActions.length) {
      return;
    }
    setSelectedWorkflowActionId((current) =>
      visibleScopedWorkflowActions.some((action) => action.action_id === current)
        ? current
        : visibleScopedWorkflowActions[0].action_id
    );
  }, [activeSectionId, scopedActionKeySignature]);

  const controlSectionOptions: SectionOption<ControlCenterSectionId>[] = visibleSections.map((sectionId) => {
    if (sectionId === "action-catalog") {
      return { id: sectionId, label: "Action Catalog", status: registryBlockedActions ? "blocked" : "ready" };
    }
    const section = sections.find((item) => item.id === sectionId);
    const label =
      sectionId === "lab-profile"
        ? "Lab Setup"
        : sectionId === "ilo"
        ? "HPE / iLO Control"
        : sectionId === "raid"
          ? "RAID Control"
          : sectionId === "vcenter"
            ? "vCenter Control"
          : sectionId === "firmware-upgrade"
            ? "Firmware / Upgrade"
            : sectionId === "verification"
              ? "Verification"
              : sectionId === "reports"
                ? "Reports"
              : section?.title ?? labelize(sectionId);
    return {
      id: sectionId,
      label,
      status: section?.status ?? "not_run"
    };
  });

  return (
    <Page
      activeSection={activeSectionId}
      description="Operate each lab device from compact controls. Detailed reports and raw command metadata stay collapsed."
      issueArea="control-center"
      onSectionChange={(sectionId) => setActiveSectionId(sectionId as ControlCenterSectionId)}
      primaryAction={{ icon: <Activity size={16} />, label: "Hardware List", to: "/hardware" }}
      sections={controlSectionOptions}
      title="Control Center"
      actions={
        <>
          <button disabled={loading} onClick={load} type="button">
            <RefreshCw size={16} />
            Refresh
          </button>
        </>
      }
    >
      <Feedback loading={showControlCenterLoading} error={error} />
      {!loading && !catalog && activeSectionId !== "action-catalog" && !error && (
        <EmptyState
          detail="The control catalog did not load. Refresh this page or run make app-check, then retry the selected section."
          title="Control catalog unavailable"
        />
      )}
      {canRenderControlSurface && (
        <section className="control-center-surface">
          <div className="calm-section-grid">
            <StatusSummaryCard
              message={
                selectedSection
                  ? selectedSection.description
                  : `${workflowActions.length} registry actions across shared workflow stages.`
              }
              status={selectedSection?.status ?? (registryBlockedActions ? "blocked" : "ready")}
              title={selectedSection?.title ?? "Action Catalog"}
              items={[
                { label: "Actions", value: String(visibleScopedWorkflowActions.length || selectedActions.length) },
                { label: "Blocked", value: String(visibleScopedWorkflowActions.length ? selectedCatalogBlockers.length : selectedBlockers.length) },
                { label: "Upgrade", value: String(activeSectionId === "action-catalog" ? registryUpgradeActions : upgradeActions) },
                { label: "Generated", value: generatedLabel }
              ]}
            />
            <NextActionCard
              detail={
                selectedWorkflowAction?.next_action ??
                "Use Detail or Copy from the registry-backed action catalog."
              }
            />
            <BlockerSummary blockers={selectedCatalogBlockers} />
          </div>
          {copyMessage && <div className="feedback">{copyMessage}</div>}

          {activeSectionId !== "action-catalog" && selectedSection && (
            <StandardControlSectionLayout
              accessError={accessError}
              activeProfile={activeProfile}
              allWorkflowActions={workflowActions}
              busyAccessSection={busyAccessSection}
              catalogProfile={catalog?.lab_profile ?? null}
              copyMessage={copyMessage}
              onCopyText={copyText}
              onRefresh={load}
              onRunWorkflowAction={runWorkflowAction}
              onSaveGlobalConfig={saveGlobalConfig}
              onSaveProfileConfig={saveProfileConfig}
              onSaveAccess={saveAccessConfig}
              onCopyWorkflowAction={copyWorkflowAction}
              runningActionId={runningWorkflowActionId}
              runResults={workflowActionRunResults}
              savingGlobalConfig={busyAction === "global-config"}
              savingProfileConfig={busyAction === "profile-config"}
              section={selectedSection}
              workflowActions={visibleScopedWorkflowActions}
            >
              <>
                <ActionCatalogTable
                  actions={visibleScopedWorkflowActions}
                  onCopy={copyWorkflowAction}
                  onRun={runWorkflowAction}
                  onSelect={setSelectedWorkflowActionId}
                  runningActionId={runningWorkflowActionId}
                  selectedActionId={selectedWorkflowAction?.action_id ?? ""}
                />
                {selectedWorkflowAction && (
                  isAdvancedMode ? (
                    <WorkflowActionDetail
                      action={selectedWorkflowAction}
                      latestRun={workflowActionRunResults[selectedWorkflowAction.action_id]}
                      onCopy={copyWorkflowAction}
                      onRun={runWorkflowAction}
                      running={runningWorkflowActionId === selectedWorkflowAction.action_id}
                    />
                  ) : (
                    <CompactWorkflowActionDetails
                      action={selectedWorkflowAction}
                      latestRun={workflowActionRunResults[selectedWorkflowAction.action_id]}
                      onCopy={copyWorkflowAction}
                      onRun={runWorkflowAction}
                      running={runningWorkflowActionId === selectedWorkflowAction.action_id}
                    />
                  )
                )}
                <ControlSection
                  busyAction={busyAction}
                  copyMessage={copyMessage}
                  accessError={accessError}
                  busyAccessSection={busyAccessSection}
                  onCopy={copyAction}
                  onCopyText={copyText}
                  onSaveAccess={saveAccessConfig}
                  onPlan={planAction}
                  planResult={planResult?.action.section_id === selectedSection.id ? planResult : null}
                  section={selectedSection}
                  showAccessConfig={false}
                  showActions={false}
                >
                  {selectedSection.id === "lab-profile" && catalog && (
                    <ControlLabProfilePanel onCopyText={copyText} profile={catalog.lab_profile} />
                  )}
                  {selectedSection.id === "firmware-upgrade" && <FirmwareUpgradeCenter section={selectedSection} />}
                  {selectedSection.id === "reports" && <ActionHistoryReportsPanel actions={actions} />}
                </ControlSection>
              </>
            </StandardControlSectionLayout>
          )}

          {activeSectionId === "action-catalog" && (
            <>
              {isAdvancedMode && (
                <AdvancedDetails
                  className="section-details"
                  summary="Manual command helpers stay collapsed until needed"
                  title="Commander mode"
                >
                  <CommanderModePanel
                    actions={commanderActions}
                    busyAction={busyAction}
                    onCopy={copyAction}
                    onPlan={planAction}
                  />
                </AdvancedDetails>
              )}
              <ActionCatalogTable
                actions={visibleScopedWorkflowActions}
                onCopy={copyWorkflowAction}
                onRun={runWorkflowAction}
                onSelect={setSelectedWorkflowActionId}
                runningActionId={runningWorkflowActionId}
                selectedActionId={selectedWorkflowAction?.action_id ?? ""}
              />
              {selectedWorkflowAction && (
                isAdvancedMode ? (
                  <WorkflowActionDetail
                    action={selectedWorkflowAction}
                    latestRun={workflowActionRunResults[selectedWorkflowAction.action_id]}
                    onCopy={copyWorkflowAction}
                    onRun={runWorkflowAction}
                    running={runningWorkflowActionId === selectedWorkflowAction.action_id}
                  />
                ) : (
                  <CompactWorkflowActionDetails
                    action={selectedWorkflowAction}
                    latestRun={workflowActionRunResults[selectedWorkflowAction.action_id]}
                    onCopy={copyWorkflowAction}
                    onRun={runWorkflowAction}
                    running={runningWorkflowActionId === selectedWorkflowAction.action_id}
                  />
                )
              )}
            </>
          )}
        </section>
      )}
    </Page>
  );
}

function operatorVisibleWorkflowActions(actions: WorkflowAction[]): WorkflowAction[] {
  const byId = new Map<string, WorkflowAction>();
  actions
    .filter((action) => !action.action_id.startsWith("commander."))
    .filter((action) => action.current_availability !== "not_available")
    .filter((action) => !/placeholder|future|create-waiver/i.test(`${action.action_id} ${action.label} ${action.description}`))
    .filter((action) => workflowActionCanRun(action) || workflowActionRequiresGuard(action))
    .forEach((action) => {
      if (!byId.has(action.action_id)) {
        byId.set(action.action_id, action);
      }
    });
  return Array.from(byId.values()).sort(workflowActionOperatorSort);
}

function workflowActionOperatorSort(left: WorkflowAction, right: WorkflowAction): number {
  const runnableDelta = Number(workflowActionCanRun(right)) - Number(workflowActionCanRun(left));
  if (runnableDelta !== 0) return runnableDelta;
  const leftGuarded = workflowActionRequiresGuard(left) ? 1 : 0;
  const rightGuarded = workflowActionRequiresGuard(right) ? 1 : 0;
  if (leftGuarded !== rightGuarded) return leftGuarded - rightGuarded;
  const leftOrder = setupActionCategoryOrder(left);
  const rightOrder = setupActionCategoryOrder(right);
  if (leftOrder !== rightOrder) return leftOrder - rightOrder;
  return humanWorkflowActionLabel(left).localeCompare(humanWorkflowActionLabel(right));
}

const standardInlineAccessSectionIds = new Set<string>();
const currentAccessSectionIds = new Set<string>(["cisco", "ilo", "raid", "esxi", "netapp"]);

function StandardControlSectionLayout({
  accessError,
  activeProfile,
  allWorkflowActions,
  busyAccessSection,
  catalogProfile,
  children,
  copyMessage,
  onCopyText,
  onRefresh,
  onRunWorkflowAction,
  onSaveGlobalConfig,
  onSaveProfileConfig,
  onSaveAccess,
  onCopyWorkflowAction,
  runningActionId,
  runResults,
  savingGlobalConfig,
  savingProfileConfig,
  section,
  workflowActions
}: {
  accessError: string;
  activeProfile: LabProfile | null;
  allWorkflowActions: WorkflowAction[];
  busyAccessSection: string;
  catalogProfile: ControlLabProfile | null;
  children: ReactNode;
  copyMessage: string;
  onCopyText: (text: string, label: string) => void;
  onRefresh: () => void;
  onRunWorkflowAction: RunWorkflowActionHandler;
  onSaveGlobalConfig: (values: GlobalConfigEditState) => Promise<void>;
  onSaveProfileConfig: (form: LabProfileFormState) => Promise<void>;
  onSaveAccess: (sectionId: string, payload: ControlAccessConfigWrite) => Promise<void>;
  onCopyWorkflowAction: (action: WorkflowAction) => void;
  runningActionId: string;
  runResults: Record<string, WorkflowActionRun>;
  savingGlobalConfig: boolean;
  savingProfileConfig: boolean;
  section: ControlSectionRecord;
  workflowActions: WorkflowAction[];
}) {
  const access = standardAccessForSection(section, activeProfile, workflowActions, onRunWorkflowAction, onRefresh, onCopyText, runningActionId);
  const configRows = standardConfigForSection(section.id, activeProfile, catalogProfile);
  const options = controlConfigOptionsForSection(section.id, workflowActions, activeProfile);
  const warning = firmwareWarningForSection(section);
  const useInlineAccessConfig = standardInlineAccessSectionIds.has(section.id);

  return (
    <section className="standard-control-section" id={`standard-control-${section.id}`}>
      <div className="standard-control-head">
        <div>
          <p className="summary-kicker">{section.stage}</p>
          <h2>{section.title}</h2>
          <p>{section.description}</p>
        </div>
        <StatusPill status={section.status} />
      </div>

      {section.firmware_summary ? (
        <FirmwareSummaryStrip
          onRunWorkflowAction={onRunWorkflowAction}
          runningActionId={runningActionId}
          summary={section.firmware_summary}
          workflowActions={allWorkflowActions}
        />
      ) : (
        <div className={`firmware-warning-strip ${warning.tone}`}>
          <span>{warning.message}</span>
          <StatusBadge status={warning.tone === "ready" ? "current" : warning.tone === "blocked" ? "blocked" : "not_checked"} />
        </div>
      )}

      <section className="standard-block access-block">
        <div className="standard-block-head">
          <div>
            <span className="summary-kicker">Access</span>
            <h3>{access.title}</h3>
          </div>
          <StatusBadge status={access.liveStatus} />
        </div>
        <div className="access-fact-grid">
          <ProviderFact label="Permanent management IP" value={displayAddress(access.managementIp)} />
          {(section.access_config?.original_dhcp_ip || (section.id === "ilo" ? activeProfile?.address_plan.ilo_initial : null)) && (
            <ProviderFact
              label="Current login IP"
              value={displayAddress(section.access_config?.original_dhcp_ip || activeProfile?.address_plan.ilo_initial)}
            />
          )}
          {access.url && <ProviderFact label="URL" value={access.url} />}
          {access.sshTarget && <ProviderFact label="SSH Target" value={access.sshTarget} />}
          {access.consolePort && <ProviderFact label="Console Port" value={access.consolePort} />}
          <ProviderFact label="UID / Username Field" value={access.usernameField} />
          <ProviderFact label="Live Status" value={displayStatusLabel(access.liveStatus)} />
        </div>
        <div className="standard-action-row">
          {access.buttons.map((button) =>
            button.to ? (
              <a className="button-link small-button" href={button.to} key={button.label} rel="noreferrer" target="_blank">
                {button.label}
              </a>
            ) : (
              <button
                className="small-button"
                disabled={button.disabled}
                key={button.label}
                onClick={button.onClick}
                type="button"
              >
                {button.label}
              </button>
            )
          )}
        </div>
        {section.access_config && currentAccessSectionIds.has(section.id) && (
          <CurrentAccessConfigInline
            busy={busyAccessSection === section.id}
            config={section.access_config}
            error={busyAccessSection === section.id ? "" : accessError}
            onSave={onSaveAccess}
          />
        )}
      </section>

      <SectionProfileConfigEditor
        activeProfile={activeProfile}
        configRows={configRows}
        onSave={onSaveProfileConfig}
        saving={savingProfileConfig}
        sectionId={section.id}
      />

      <SetupExecutionOptionsPanel
        actions={workflowActions}
        onCopy={onCopyWorkflowAction}
        onRun={onRunWorkflowAction}
        runResults={runResults}
        runningActionId={runningActionId}
        sectionId={section.id}
      />

      {section.id === "firmware-upgrade" && (
        <FirmwareGuardedControlsPanel
          actions={firmwareGuardedControls(allWorkflowActions)}
          onRunWorkflowAction={onRunWorkflowAction}
          runningActionId={runningActionId}
        />
      )}

      <details className="actions-config-dropdown">
        <summary>
          <span>Actions / Configs</span>
          <small>{options.length} available options</small>
        </summary>
        <div className="actions-config-table" role="table" aria-label={`${section.title} actions and config options`}>
          <div className="actions-config-table-head" role="row">
            <span>Option</span>
            <span>Desired</span>
            <span>Status</span>
            <span>Path</span>
          </div>
          {options.map((option) => (
            <div className="actions-config-row" key={option.option_id} role="row">
              <div className="actions-config-option-cell">
                <strong>{option.label}</strong>
                <span>{option.description}</span>
              </div>
              <div>
                <strong>{option.desired_value}</strong>
                <span className="muted-mini">Current: {option.current_value}</span>
              </div>
              <div className="actions-config-status-cell">
                <StatusBadge status={option.availability} />
                <span className={`classification-tag ${option.effect}`}>{displayStatusLabel(option.effect)}</span>
                {option.requires_confirmation && <span className="classification-tag destructive">Confirmation required</span>}
                {option.recommended_default && <span className="classification-tag read-only">Recommended</span>}
              </div>
              <div>
                <strong>{option.supported_by.map(labelize).join(", ")}</strong>
                <span className="muted-mini">{option.linked_action_id ?? "Profile only"}</span>
              </div>
            </div>
          ))}
        </div>
      </details>

      <AdvancedDetails
        className="section-details standard-evidence-details"
        summary="Raw reports, artifact paths, registry IDs, commands, run traces, and JSON"
        title="Advanced / Evidence"
      >
        {copyMessage && <div className="feedback">{copyMessage}</div>}
        {children}
      </AdvancedDetails>
    </section>
  );
}

function ConfigSummaryBlock({
  configRows,
  sectionId
}: {
  configRows: WorkflowSummaryItem[];
  sectionId: string;
}) {
  return (
    <section className="standard-block config-block">
      <div className="standard-block-head">
        <div>
          <span className="summary-kicker">Config</span>
          <h3>Saved setup values</h3>
        </div>
        <StatusBadge status={configRows.length ? "current" : "not_checked"} />
      </div>
      <div className="config-compact-table" aria-label={`${labelize(sectionId)} applied config values`}>
        {configRows.map((row) => (
          <div key={`${sectionId}-${row.label}`}>
            <span>{row.label}</span>
            <strong>{row.value}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

function FirmwareSummaryStrip({
  onRunWorkflowAction,
  runningActionId,
  summary,
  workflowActions
}: {
  onRunWorkflowAction: RunWorkflowActionHandler;
  runningActionId: string;
  summary: FirmwareSummary;
  workflowActions: WorkflowAction[];
}) {
  const scanAction = summary.scan_action_id
    ? workflowActions.find((action) => action.action_id === summary.scan_action_id) ?? null
    : null;
  const running = Boolean(scanAction && runningActionId === scanAction.action_id);
  const canRunScan = Boolean(scanAction && workflowActionCanRun(scanAction));
  const disabledReason = scanAction
    ? firmwareReasonText(scanAction.blockers[0] || scanAction.ui_run_blockers[0] || summary.blocker || "Prerequisites missing.")
    : "No safe scan action is registered for this device.";
  const upgradeLink = summary.upgrade_center_link || `/firmware?device=${summary.device_id}`;
  const primaryPath = firmwarePrimaryPath(summary);

  return (
    <section className={`firmware-summary-strip ${firmwareSummaryTone(summary)}`}>
      <div className="firmware-summary-head">
        <div>
          <span className="summary-kicker">Firmware / Software</span>
          <h3>{summary.label}</h3>
          <p>{firmwareSummaryLine(summary)}</p>
        </div>
        <div className="standard-action-row firmware-summary-actions">
          <button
            className="small-button primary"
            disabled={!canRunScan || running}
            onClick={() => {
              if (scanAction && canRunScan) onRunWorkflowAction(scanAction);
            }}
            title={canRunScan ? "Run the registered read-only firmware scan." : disabledReason}
            type="button"
          >
            {running ? <RefreshCw className="spin-icon" size={14} /> : <ShieldCheck size={14} />}
            {running ? "Scanning" : "Scan Firmware"}
          </button>
          <Link className="button-link small-button" to={upgradeLink}>
            <Route size={14} />
            Open Firmware Upgrades
          </Link>
        </div>
      </div>
      <div className="firmware-summary-grid">
        <ProviderFact label="Status" value={firmwareComplianceLabel(summary.compliance_status)} />
        <ProviderFact label="Current" value={firmwareVersionList(summary.current_versions, "Unknown")} />
        <ProviderFact label="Baseline" value={firmwareBaselineList(summary.approved_versions)} />
        <ProviderFact label="Path" value={firmwarePathStatusLabel(summary.path_status || primaryPath?.path_status || summary.compliance_status)} />
        <ProviderFact label="Package" value={summary.package_name || primaryPath?.package_name || (summary.package_available ? "Available" : "Not available")} />
        <ProviderFact label="Last scanned" value={summary.last_scanned ? formatDateTime(summary.last_scanned) : "Not checked"} />
        <ProviderFact label="Source" value={firmwareSourceLabel(summary.source_type)} />
        <ProviderFact label="Freshness" value={firmwareFreshnessLabel(summary.freshness)} />
      </div>
      {summary.blocker && (
        <div className="firmware-summary-reason">
          <AlertTriangle size={16} />
          <span>{firmwareReasonText(summary.blocker)}</span>
        </div>
      )}
      {!canRunScan && (
        <p className="firmware-summary-disabled">Scan disabled: {disabledReason}</p>
      )}
      {summary.evidence_artifacts.length > 0 && (
        <AdvancedDetails
          className="firmware-summary-evidence"
          summary={`${summary.evidence_artifacts.length} firmware evidence link${summary.evidence_artifacts.length === 1 ? "" : "s"}`}
          title="Firmware evidence"
        >
          <EvidenceList artifacts={summary.evidence_artifacts} empty="No firmware evidence links are available yet." />
        </AdvancedDetails>
      )}
    </section>
  );
}

function firmwareSummaryTone(summary: FirmwareSummary): string {
  if (summary.severity === "red") return "blocked";
  if (summary.severity === "yellow") return "warning";
  if (summary.severity === "gray") return "neutral";
  return "ready";
}

function firmwareSummaryLine(summary: FirmwareSummary): string {
  const displayPath = firmwareDisplayPath(summary);
  if (displayPath?.current_version) {
    return `${displayPath.component_label}: ${displayPath.current_version}, ${firmwarePathStatusLabel(displayPath.path_status).toLowerCase()}.`;
  }
  const status = firmwareComplianceLabel(summary.compliance_status);
  if (summary.blocker) {
    return `${status}: ${firmwareReasonText(summary.blocker)}.`;
  }
  return `${status}: ${firmwareVersionList(summary.current_versions, "versions available")}.`;
}

function firmwareDisplayPath(summary: FirmwareSummary): FirmwareUpgradePath | null {
  const paths = summary.upgrade_paths ?? [];
  return paths.find((path) => path.current_version && path.path_status === "current") ?? paths.find((path) => path.current_version) ?? firmwarePrimaryPath(summary);
}

function firmwarePrimaryPath(summary: FirmwareSummary): FirmwareUpgradePath | null {
  const paths = summary.upgrade_paths ?? [];
  return paths.find((path) => path.path_status !== "current") ?? paths[0] ?? null;
}

function firmwareReasonText(value: string): string {
  const text = humanizeBlocker(value);
  return text ? `${text.charAt(0).toUpperCase()}${text.slice(1)}` : text;
}

function firmwareComplianceLabel(status: string): string {
  if (status === "current") return "Current";
  if (status === "needs_upgrade") return "Needs upgrade";
  if (status === "cannot_verify") return "Cannot verify";
  if (status === "not_configured") return "Not configured";
  return displayStatusLabel(status);
}

function firmwarePathStatusLabel(status: string): string {
  if (status === "current") return "Current";
  if (status === "direct") return "Direct upgrade available";
  if (status === "staged") return "Staged upgrade required";
  if (status === "blocked") return "Blocked";
  if (status === "unknown") return "Scan needed";
  if (status === "manual_review") return "Manual review";
  return displayStatusLabel(status);
}

function firmwareVersionList(values: Array<{ label: string; version: string | null; status?: string | null }>, empty: string): string {
  if (!values.length) return empty;
  return values
    .slice(0, 4)
    .map((item) => `${item.label}: ${item.version || "Unknown"}`)
    .join("; ");
}

function firmwareBaselineList(values: Array<{ label: string; version: string | null; status?: string | null }>): string {
  if (!values.length) return "Not set";
  return values
    .slice(0, 4)
    .map((item) =>
      item.version
        ? `${item.label}: ${item.version}`
        : `${item.label}: ${displayStatusLabel(item.status || "manual_review")}`
    )
    .join("; ");
}

function firmwareSourceLabel(sourceType: string): string {
  if (sourceType === "live_check") return "live check";
  if (sourceType === "cached_live") return "cached live";
  if (sourceType === "historical_evidence") return "historical evidence";
  if (sourceType === "not_checked") return "not checked";
  return displayStatusLabel(sourceType).toLowerCase();
}

function firmwareFreshnessLabel(freshness: string): string {
  if (freshness === "not_checked") return "not checked";
  return displayStatusLabel(freshness).toLowerCase();
}

function SectionProfileConfigEditor({
  activeProfile,
  configRows,
  onSave,
  saving,
  sectionId
}: {
  activeProfile: LabProfile | null;
  configRows: WorkflowSummaryItem[];
  onSave: (form: LabProfileFormState) => Promise<void>;
  saving: boolean;
  sectionId: string;
}) {
  const [form, setForm] = useState<LabProfileFormState>(() =>
    activeProfile ? labProfileFormFrom(activeProfile) : blankLabProfileForm()
  );
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const profileKey = `${sectionId}:${activeProfile?.id ?? "none"}:${activeProfile?.version ?? "0"}:${activeProfile?.source ?? "missing"}`;
  const subnetPrefix = parseSubnetPrefix(form.globalSettings.subnetPrefix);
  const fields = controlProfileFieldsForSection(sectionId, labNetAppSupported(subnetPrefix));
  const editable = Boolean(activeProfile);
  const saveMode =
    activeProfile?.source === "saved"
      ? "Updates the active saved lab setup."
      : "Creates a saved lab setup from the current runtime values.";

  useEffect(() => {
    setForm(activeProfile ? labProfileFormFrom(activeProfile) : blankLabProfileForm());
    setMessage("");
    setError("");
  }, [profileKey, activeProfile]);

  function updateProfileField(key: "name" | "description", value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function updateAddress(key: LabAddressScalarKey, value: string) {
    if (key === "subnet") {
      setForm((current) => applyLabSubnetChoice(current, value, current.globalSettings.subnetPrefix));
      return;
    }
    setForm((current) => ({
      ...current,
      addresses: {
        ...current.addresses,
        [key]: value
      }
    }));
  }

  function updateGlobal<K extends keyof LabGlobalSettingsFormState>(key: K, value: LabGlobalSettingsFormState[K]) {
    setForm((current) => ({
      ...current,
      globalSettings: {
        ...current.globalSettings,
        [key]: value
      }
    }));
  }

  function updateNetAppList(key: "netappNfsLifs" | "netappIscsiLifs", value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    setError("");
    try {
      await onSave(form);
      setMessage("Setup values saved.");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <section className="standard-block config-block control-profile-editor-block">
      <div className="standard-block-head">
        <div>
          <span className="summary-kicker">Config</span>
          <h3>Saved setup values</h3>
          <p>{editable ? saveMode : "Load the active lab setup before editing values."}</p>
        </div>
        <StatusBadge status={activeProfile?.source === "saved" ? "current" : editable ? "not_checked" : "blocked"} />
      </div>
      <form className="control-profile-editor" onSubmit={submit}>
        <div className="control-profile-editor-grid">
          {fields.map((field) => {
            if (field.kind === "profile") {
              return (
                <Field key={`${sectionId}-${field.kind}-${field.key}`} label={field.label}>
                  <input
                    disabled={!editable || saving}
                    onChange={(event) => updateProfileField(field.key, event.target.value)}
                    value={form[field.key]}
                  />
                </Field>
              );
            }
            if (field.kind === "address") {
              return (
                <Field key={`${sectionId}-${field.kind}-${field.key}`} label={field.label}>
                  <input
                    disabled={!editable || saving}
                    inputMode="decimal"
                    onChange={(event) => updateAddress(field.key, event.target.value)}
                    placeholder={
                      field.key === "ilo_initial"
                        ? "192.168.1.11"
                        : field.key === "ilo"
                          ? "192.168.1.201"
                          : undefined
                    }
                    value={form.addresses[field.key]}
                  />
                </Field>
              );
            }
            if (field.kind === "netapp-list") {
              return (
                <Field key={`${sectionId}-${field.kind}-${field.key}`} label={field.label}>
                  <input
                    disabled={!editable || saving}
                    inputMode="decimal"
                    onChange={(event) => updateNetAppList(field.key, event.target.value)}
                    placeholder="Comma-separated IPs"
                    value={form[field.key]}
                  />
                </Field>
              );
            }
            if (field.valueType === "boolean") {
              return (
                <label className="checkbox-line control-profile-checkbox" key={`${sectionId}-${field.kind}-${field.key}`}>
                  <input
                    checked={Boolean(form.globalSettings[field.key])}
                    disabled={!editable || saving}
                    onChange={(event) => updateGlobal(field.key, event.target.checked as LabGlobalSettingsFormState[typeof field.key])}
                    type="checkbox"
                  />
                  <span>{field.label}</span>
                </label>
              );
            }
            if (field.valueType === "select") {
              return (
                <Field key={`${sectionId}-${field.kind}-${field.key}`} label={field.label}>
                  <select
                    disabled={!editable || saving}
                    onChange={(event) => updateGlobal(field.key, event.target.value as LabGlobalSettingsFormState[typeof field.key])}
                    value={String(form.globalSettings[field.key] ?? "")}
                  >
                    {(field.options ?? []).map((option) => (
                      <option key={`${field.key}-${option.value}`} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </Field>
              );
            }
            return (
              <Field key={`${sectionId}-${field.kind}-${field.key}`} label={field.label}>
                <input
                  disabled={!editable || saving}
                  inputMode={field.valueType === "number" ? "numeric" : undefined}
                  onChange={(event) => updateGlobal(field.key, event.target.value as LabGlobalSettingsFormState[typeof field.key])}
                  value={String(form.globalSettings[field.key] ?? "")}
                />
              </Field>
            );
          })}
        </div>
        <p className="muted-mini">
          Saving these values updates local setup state only. It does not contact hardware, change provider mode, or enable apply actions.
        </p>
        {(message || error) && <p className={error ? "form-error" : "success"}>{error || message}</p>}
        <div className="standard-action-row">
          <button className="small-button primary" disabled={!editable || saving} type="submit">
            <Save size={14} />
            {saving ? "Saving" : activeProfile?.source === "saved" ? "Save setup values" : "Create saved setup"}
          </button>
          <Link className="button-link small-button" to="/lab-profiles">
            <Pencil size={14} />
            Saved setups
          </Link>
        </div>
      </form>
      <div className="config-compact-table" aria-label={`${labelize(sectionId)} applied config values`}>
        {configRows.map((row) => (
          <div key={`${sectionId}-${row.label}`}>
            <span>{row.label}</span>
            <strong>{row.value}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

function SetupExecutionOptionsPanel({
  actions,
  onCopy,
  onRun,
  runResults,
  runningActionId,
  sectionId
}: {
  actions: WorkflowAction[];
  onCopy: (action: WorkflowAction) => void;
  onRun: (action: WorkflowAction) => void;
  runResults: Record<string, WorkflowActionRun>;
  runningActionId: string;
  sectionId: string;
}) {
  const setupActions = setupExecutionActionsForSection(sectionId, actions);
  const runnableCount = setupActions.filter((action) => workflowActionCanRun(action)).length;
  const guardedCount = setupActions.filter((action) => workflowActionRequiresGuard(action)).length;
  const status = runnableCount ? "available" : setupActions.length ? "manual_command_required" : "not_available";

  return (
    <section className="standard-block setup-run-options-block">
      <div className="standard-block-head">
        <div>
          <span className="summary-kicker">Run</span>
          <h3>Run options</h3>
          <p>Checks, previews, and reports can run from the UI. Apply, reset, install, and upgrade actions stay gated.</p>
        </div>
        <StatusBadge status={status} />
      </div>
      {setupActions.length ? (
        <div className="setup-run-option-list">
          {setupActions.map((action) => {
            const latestRun = runResults[action.action_id];
            const trace = latestRun ? workflowRunToTrace(latestRun) : action.last_run_trace;
            const blocker = action.blockers[0] || action.ui_run_blockers[0] || latestRun?.blockers[0] || "";
            return (
              <div className="setup-run-option-row" key={`${sectionId}-${action.action_id}`}>
                <div className="setup-run-option-main">
                  <strong>{humanWorkflowActionLabel(action)}</strong>
                  <span>{humanizeAction(action.description || action.next_action)}</span>
                  {blocker && <p>{humanizeBlocker(blocker)}</p>}
                </div>
                <div className="setup-run-option-meta">
                  <span className={`classification-tag ${workflowModeClass(action.mode)}`}>{workflowModeLabel(action.mode)}</span>
                  <StatusBadge status={action.current_availability} />
                  <SourceFreshnessInline freshness={trace.freshness} sourceType={trace.source_type} />
                </div>
                <div className="setup-run-option-action">
                  <WorkflowActionRunControl
                    action={action}
                    compact
                    onCopy={onCopy}
                    onRun={onRun}
                    running={runningActionId === action.action_id}
                  />
                </div>
                <div className="setup-run-option-last">
                  <span>{trace.finished_at ? formatDateTime(trace.finished_at) : "Not checked"}</span>
                  {latestRun && <strong>{displayStatusLabel(latestRun.status)}</strong>}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <EmptyState title="No run options" detail="This section does not expose direct run options yet." />
      )}
      <div className="setup-run-option-summary">
        <span>{runnableCount} runnable</span>
        <span>{guardedCount} gated</span>
        <span>{setupActions.length} total</span>
      </div>
    </section>
  );
}

function GlobalConfigEditor({
  activeProfile,
  configRows,
  onSave,
  saving,
  sectionId
}: {
  activeProfile: LabProfile | null;
  configRows: WorkflowSummaryItem[];
  onSave: (values: GlobalConfigEditState) => Promise<void>;
  saving: boolean;
  sectionId: string;
}) {
  const [form, setForm] = useState<GlobalConfigEditState>(() => globalConfigEditStateFromProfile(activeProfile));
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const profileKey = `${activeProfile?.id ?? "none"}:${activeProfile?.version ?? "0"}`;
  const editable = Boolean(activeProfile && activeProfile.source === "saved");

  useEffect(() => {
    setForm(globalConfigEditStateFromProfile(activeProfile));
    setMessage("");
    setError("");
  }, [profileKey]);

  function update<K extends keyof GlobalConfigEditState>(key: K, value: GlobalConfigEditState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    setError("");
    try {
      await onSave(form);
      setMessage("Global config saved.");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <section className="standard-block config-block compact-global-config">
      <div className="standard-block-head">
        <div>
          <span className="summary-kicker">Config</span>
          <h3>Global device defaults</h3>
        </div>
        <StatusBadge status={configRows.length ? "current" : "not_checked"} />
      </div>
      <form className="global-config-editor" onSubmit={submit}>
        <div className="global-config-editor-grid">
          <Field label="DNS">
            <input
              disabled={!editable}
              onChange={(event) => update("dnsServers", event.target.value)}
              value={form.dnsServers}
            />
          </Field>
          <Field label="NTP">
            <input
              disabled={!editable}
              onChange={(event) => update("ntpServers", event.target.value)}
              value={form.ntpServers}
            />
          </Field>
          <Field label="Domain">
            <input
              disabled={!editable}
              onChange={(event) => update("domainName", event.target.value)}
              value={form.domainName}
            />
          </Field>
          <Field label="VLAN">
            <input
              disabled={!editable}
              inputMode="numeric"
              onChange={(event) => update("vlanId", event.target.value)}
              value={form.vlanId}
            />
          </Field>
          <Field label="MTU">
            <input
              disabled={!editable}
              inputMode="numeric"
              onChange={(event) => update("mtu", event.target.value)}
              value={form.mtu}
            />
          </Field>
          <Field label="Storage">
            <select
              disabled={!editable}
              onChange={(event) => update("storageProtocol", event.target.value)}
              value={form.storageProtocol}
            >
              <option value="nfs">NFS</option>
              <option value="iscsi">iSCSI</option>
              <option value="none">Local only</option>
            </select>
          </Field>
        </div>
        <div className="global-policy-grid compact">
          <label className="checkbox-line">
            <input
              checked={form.enableDns}
              disabled={!editable}
              onChange={(event) => update("enableDns", event.target.checked)}
              type="checkbox"
            />
            <span>DNS</span>
          </label>
          <label className="checkbox-line">
            <input
              checked={form.enableNtp}
              disabled={!editable}
              onChange={(event) => update("enableNtp", event.target.checked)}
              type="checkbox"
            />
            <span>NTP</span>
          </label>
          <label className="checkbox-line">
            <input
              checked={form.enableSnmp}
              disabled={!editable}
              onChange={(event) => update("enableSnmp", event.target.checked)}
              type="checkbox"
            />
            <span>SNMP</span>
          </label>
          <label className="checkbox-line">
            <input
              checked={form.disableIpv6}
              disabled={!editable}
              onChange={(event) => update("disableIpv6", event.target.checked)}
              type="checkbox"
            />
            <span>Disable IPv6</span>
          </label>
        </div>
        {(message || error || !editable) && (
          <p className={error ? "form-error" : "muted"}>
            {error || message || "Load a saved active profile to edit global defaults from this page."}
          </p>
        )}
        <div className="standard-action-row">
          <button className="small-button primary" disabled={!editable || saving} type="submit">
            <Save size={14} />
            {saving ? "Saving" : "Save global config"}
          </button>
          <Link className="button-link small-button" to="/lab-profiles">
            <Pencil size={14} />
            Saved setups
          </Link>
        </div>
      </form>
      <div className="config-compact-table" aria-label={`${labelize(sectionId)} applied config values`}>
        {configRows.map((row) => (
          <div key={`${sectionId}-${row.label}`}>
            <span>{row.label}</span>
            <strong>{row.value}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

function InlineFirmwarePanel({
  checkSummary,
  onRunWorkflowAction,
  runningActionId,
  section,
  workflowActions
}: {
  checkSummary: { actionLabel: string; message: string; tone: string };
  onRunWorkflowAction: RunWorkflowActionHandler;
  runningActionId: string;
  section: ControlSectionRecord;
  workflowActions: WorkflowAction[];
}) {
  const firmwareItems = firmwareItemsForSection(section);
  const checkAction = firmwareCheckActionForSection(section.id, workflowActions);
  const upgradeAction = firmwareUpgradeActionForSection(section.id, workflowActions);
  const checking = Boolean(checkAction && runningActionId === checkAction.action_id);
  const checkRunnable = Boolean(checkAction && workflowActionCanRun(checkAction));
  const upgradeRunnable = Boolean(
    upgradeAction && workflowActionCanRun(upgradeAction) && !workflowActionRequiresGuard(upgradeAction)
  );
  const traceBlockers = checkAction?.last_run_trace.blockers ?? [];
  const traceWarnings = checkAction?.last_run_trace.warnings ?? [];
  const checkTitle = checkAction
    ? checkRunnable
      ? "Run the registered read-only firmware inventory check."
      : humanizeAction(checkAction.blockers[0] || checkAction.ui_run_blockers[0] || checkAction.next_action)
    : "No read-only firmware inventory action is registered for this section.";
  const upgradeTitle = upgradeAction
    ? upgradeRunnable
      ? "Run the registered upgrade workflow."
      : "Upgrade requires guarded workflow approval and explicit future gates."
    : "No upgrade workflow is registered for this section.";

  return (
    <section className={`inline-firmware-panel ${checkSummary.tone}`}>
      <div className="inline-firmware-head">
        <div>
          <p className="summary-kicker">Firmware</p>
          <h3>{section.id === "netapp" ? "ONTAP / component firmware" : "Firmware check"}</h3>
          <p>{checkSummary.message}</p>
        </div>
        <div className="standard-action-row">
          <button
            className="small-button primary"
            disabled={!checkRunnable || checking}
            onClick={() => {
              if (checkAction && checkRunnable) onRunWorkflowAction(checkAction);
            }}
            title={checkTitle}
            type="button"
          >
            {checking ? <RefreshCw className="spin-icon" size={14} /> : <ShieldCheck size={14} />}
            {checking ? "Checking" : "Check Firmware"}
          </button>
          <button
            className="small-button"
            disabled={!upgradeRunnable}
            onClick={() => {
              if (upgradeAction && upgradeRunnable) onRunWorkflowAction(upgradeAction);
            }}
            title={upgradeTitle}
            type="button"
          >
            <Play size={14} />
            Upgrade Now
          </button>
        </div>
      </div>
      {firmwareItems.length > 0 ? (
        <div className="firmware-inline-grid">
          {firmwareItems.map((item) => (
            <div key={`${section.id}-firmware-${item.label}`}>
              <span>{item.label}</span>
              <strong>{item.value || "Unknown"}</strong>
              {item.status && <StatusBadge status={item.status} />}
            </div>
          ))}
        </div>
      ) : (
        <p className="muted">Firmware state is not checked yet.</p>
      )}
      {checkAction?.last_run_trace.summary && (
        <p className="firmware-inline-note">{humanizeAction(checkAction.last_run_trace.summary)}</p>
      )}
      {(traceBlockers.length > 0 || traceWarnings.length > 0) && (
        <div className="firmware-inline-issues">
          {traceBlockers.slice(0, 2).map((blocker) => (
            <div className="provider-issue warning" key={`${section.id}-firmware-blocker-${blocker}`}>
              <AlertTriangle size={16} />
              <span>{humanizeAction(blocker)}</span>
            </div>
          ))}
          {traceWarnings.slice(0, 2).map((warning) => (
            <div className="provider-issue" key={`${section.id}-firmware-warning-${warning}`}>
              <AlertTriangle size={16} />
              <span>{humanizeAction(warning)}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function firmwareItemsForSection(section: ControlSectionRecord): ControlStateItem[] {
  const matches = section.current_state.filter((item) =>
    /firmware|bios|ios xe|ontap|rommon|smart array|bmc|sp version|version|iso/i.test(item.label)
  );
  return matches.slice(0, 8);
}

function firmwareCheckActionForSection(sectionId: string, actions: WorkflowAction[]): WorkflowAction | null {
  const tokensBySection: Record<string, string[]> = {
    cisco: ["cisco.firmware-inventory", "firmware"],
    ilo: ["ilo.firmware-inventory", "firmware", "ilo.inventory"],
    netapp: ["netapp.component-firmware-inventory", "netapp.ontap-upgrade-inventory", "firmware", "upgrade-inventory"]
  };
  return firstWorkflowActionByTokens(
    actions,
    tokensBySection[sectionId] ?? ["firmware", "inventory"],
    (action) => action.mode === "read_only"
  );
}

function firmwareUpgradeActionForSection(sectionId: string, actions: WorkflowAction[]): WorkflowAction | null {
  const tokensBySection: Record<string, string[]> = {
    cisco: ["cisco.firmware-upgrade", "upgrade"],
    ilo: ["ilo.firmware-upgrade", "upgrade"],
    netapp: ["netapp.ontap-upgrade-apply", "upgrade-apply"]
  };
  return firstWorkflowActionByTokens(
    actions,
    tokensBySection[sectionId] ?? ["upgrade"],
    (action) => action.mode === "upgrade"
  );
}

function firstWorkflowActionByTokens(
  actions: WorkflowAction[],
  tokens: string[],
  predicate: (action: WorkflowAction) => boolean
): WorkflowAction | null {
  const normalizedTokens = tokens.map((token) => token.toLowerCase());
  for (const token of normalizedTokens) {
    const match = actions.find(
      (action) =>
        predicate(action) &&
        (action.action_id.toLowerCase().includes(token) || action.label.toLowerCase().includes(token))
    );
    if (match) return match;
  }
  return null;
}

function firmwareWarningForSection(section: ControlSectionRecord): { actionLabel: string; message: string; tone: string } {
  const firmwareItems = section.current_state.filter((item) => /firmware|bios|ios xe|ontap|smart array|version|iso/i.test(item.label));
  const statuses = firmwareItems.map((item) => `${item.status ?? ""} ${item.value}`.toLowerCase());
  const hasUnknown = statuses.some((status) => /unknown|not checked|not_checked|timeout/.test(status));
  const hasBlocked = statuses.some(
    (status) => /below|fail|critical/.test(status) || (/blocked/.test(status) && !/unknown|not checked|not_checked|timeout/.test(status))
  );
  const hasReady = firmwareItems.length > 0 && statuses.every((status) => /ready|passed|current|compliant|available/.test(status));
  const actionLabel = section.id === "firmware-upgrade" ? "View upgrade" : "Check firmware";
  if (section.id === "lab-profile") {
    return { actionLabel, message: "Active lab setup selected.", tone: "ready" };
  }
  if (hasBlocked) {
    return {
      actionLabel,
      message: "Firmware is below the approved baseline.",
      tone: "blocked"
    };
  }
  if (hasUnknown) {
    return { actionLabel, message: firmwareUnknownMessageForSection(section.id), tone: "warning" };
  }
  if (hasReady) {
    return { actionLabel, message: "Firmware is current.", tone: "ready" };
  }
  if (section.id === "raid") {
    return { actionLabel, message: "Smart Array firmware is unknown.", tone: "warning" };
  }
  if (section.id === "esxi") {
    return { actionLabel, message: "ESXi version or ISO is not verified.", tone: "warning" };
  }
  if (section.id === "netapp") {
    return { actionLabel, message: "ONTAP version is unknown.", tone: "warning" };
  }
  if (section.id === "ilo") {
    return { actionLabel, message: "iLO, BIOS, or Smart Array firmware is unknown.", tone: "warning" };
  }
  if (section.id === "cisco") {
    return { actionLabel, message: "IOS XE firmware is unknown.", tone: "warning" };
  }
  return { actionLabel, message: "Not configured yet: firmware unavailable until device setup", tone: "neutral" };
}

function firmwareUnknownMessageForSection(sectionId: string): string {
  if (sectionId === "raid") return "Smart Array firmware is unknown.";
  if (sectionId === "esxi") return "ESXi version or ISO is not verified.";
  if (sectionId === "netapp") return "ONTAP version is unknown.";
  if (sectionId === "ilo") return "iLO, BIOS, or Smart Array firmware is unknown.";
  if (sectionId === "cisco") return "IOS XE firmware is unknown.";
  return "Firmware inventory did not return current versions.";
}

function standardAccessForSection(
  section: ControlSectionRecord,
  profile: LabProfile | null,
  workflowActions: WorkflowAction[],
  onRunWorkflowAction: RunWorkflowActionHandler,
  onRefresh: () => void,
  onCopyText: (text: string, label: string) => void,
  runningActionId: string
) {
  const address = profile?.resolved_address_plan ?? profile?.address_plan ?? blankLabAddressPlan();
  const stateValue = (label: string) => findControlStateValue(section, label);
  const readOnlyAction = firstReadOnlyWorkflowAction(workflowActions, ["reachability", "readiness", "validate", "live-state", "privilege", "inventory"]);
  const consoleAction = firstReadOnlyWorkflowAction(workflowActions, ["console", "discovery"]);
  const managementIp =
    section.id === "cisco"
      ? address.cisco_management
      : section.id === "ilo" || section.id === "raid"
        ? address.ilo
        : section.id === "esxi"
          ? address.esxi_management
          : section.id === "netapp"
            ? address.netapp_cluster_mgmt
            : section.id === "vcenter"
              ? "Not configured"
            : address.subnet;
  const url =
    section.id === "ilo" && managementIp
      ? `https://${managementIp}`
      : section.id === "esxi" && managementIp
        ? `https://${managementIp}`
        : section.id === "netapp" && managementIp
          ? `https://${managementIp}`
          : null;
  const sshTarget =
    section.id === "cisco" && managementIp
      ? `<username>@${managementIp}`
      : section.id === "esxi" && managementIp
        ? `<username>@${managementIp}`
        : section.id === "netapp" && managementIp
          ? `<username>@${managementIp}`
          : null;
  const consolePort =
    section.id === "cisco" || section.id === "netapp"
      ? stateValue("Selected path") || stateValue("Console") || "Autodiscover"
      : section.id === "raid"
        ? "Through iLO"
        : null;
  const usernameField =
    section.id === "cisco"
      ? "CISCO_USERNAME"
      : section.id === "ilo" || section.id === "raid"
        ? "ILO_USERNAME"
        : section.id === "esxi"
          ? "ESXI_USERNAME"
          : section.id === "netapp"
            ? "NETAPP_USERNAME"
            : "Credential reference";
  const liveStatus = stateValue("Status") || stateValue("Provider status") || section.status || "not_checked";
  const buttons: AccessButton[] = [
    {
      disabled: !readOnlyAction || runningActionId === readOnlyAction.action_id,
      label: runningActionId === readOnlyAction?.action_id ? "Testing" : "Test access",
      onClick: readOnlyAction ? () => onRunWorkflowAction(readOnlyAction) : undefined
    },
    { label: "Refresh", onClick: onRefresh },
    ...(url ? [{ label: "Open URL", to: url }] : []),
    ...(sshTarget
      ? [{
          label: "Copy SSH command",
          onClick: () => onCopyText(`ssh ${sshTarget}`, "SSH command")
        }]
      : []),
    ...(section.id === "cisco" || section.id === "netapp"
      ? [{
          disabled: !consoleAction || runningActionId === consoleAction.action_id,
          label: runningActionId === consoleAction?.action_id ? "Discovering" : "Run console discovery",
          onClick: consoleAction ? () => onRunWorkflowAction(consoleAction) : undefined
        }]
      : [])
  ];

  return {
    buttons,
    consolePort,
    liveStatus,
    managementIp,
    sshTarget,
    title: `${section.title} access`,
    url,
    usernameField
  };
}

function standardConfigForSection(
  sectionId: string,
  profile: LabProfile | null,
  catalogProfile: ControlLabProfile | null
): WorkflowSummaryItem[] {
  const address = profile?.resolved_address_plan ?? profile?.address_plan ?? blankLabAddressPlan();
  const global = profile?.global_settings;
  const features = profile?.features;
  const network = catalogProfile?.network ?? {};
  const dns = global?.dns_servers.length ? global.dns_servers.join(", ") : asString(network.dns) || "Not set";
  const ntp = global?.ntp_servers.length ? global.ntp_servers.join(", ") : asString(network.ntp) || "Not set";
  const gateway = global?.gateway || asString(network.gateway) || "Not set";
  const mtu = global?.mtu ? String(global.mtu) : asString(network.mtu) || "Not set";
  const vlan = global?.vlan_id || asString(objectValue(network.vlan_ids).cisco_management) || "Not set";
  const dnsPolicy = profilePolicyValue(features?.enable_dns, dns, "servers");
  const ntpPolicy = profilePolicyValue(features?.enable_ntp, ntp, "servers");
  const snmpPolicy = profileSnmpValue(features);
  const ipv6Policy = features?.disable_ipv6 === false ? "Allowed by lab setup" : "Disabled by lab setup";
  const legacyProtocolPolicy = features?.block_legacy_protocols === false ? "Allowed by lab setup" : "Blocked by lab setup";

  if (sectionId === "cisco") {
    return [
      { label: "IP Address", value: displayAddress(address.cisco_management) },
      { label: "Subnet / Gateway", value: `${displayAddress(address.subnet)} / ${gateway}` },
      { label: "DNS", value: dnsPolicy },
      { label: "NTP", value: ntpPolicy },
      { label: "SNMP", value: snmpPolicy },
      { label: "MTU", value: mtu },
      { label: "VLAN", value: vlan },
      { label: "IPv6", value: ipv6Policy },
      { label: "Legacy Protocols", value: legacyProtocolPolicy },
      { label: "Hostname", value: "Cisco switch" },
      { label: "Protocols", value: "SSH/SCP after validation" }
    ];
  }
  if (sectionId === "ilo") {
    return [
      { label: "Permanent IP", value: displayAddress(address.ilo) },
      { label: "Initial login IP", value: displayAddress(address.ilo_initial) },
      { label: "Subnet / Gateway", value: `${displayAddress(address.subnet)} / ${gateway}` },
      { label: "DNS", value: dnsPolicy },
      { label: "NTP", value: ntpPolicy },
      { label: "SNMP", value: snmpPolicy },
      { label: "Legacy Protocols", value: legacyProtocolPolicy },
      { label: "Hostname", value: "iLO host" },
      { label: "Boot Options", value: "One-time boot gated" },
      { label: "Virtual Media", value: "Plan before mount" },
      { label: "Power Policy", value: "Reset disabled until confirmed" }
    ];
  }
  if (sectionId === "raid") {
    return [
      { label: "Controller Access", value: "Through iLO" },
      { label: "OS RAID", value: "Saved desired intent" },
      { label: "Datastore RAID", value: "Saved desired intent" },
      { label: "Spare", value: "Controlled option" },
      { label: "Boot Priority", value: "Validate after apply" },
      { label: "Apply", value: "Destructive gate required" }
    ];
  }
  if (sectionId === "esxi") {
    return [
      { label: "Management IP", value: displayAddress(address.esxi_management) },
      { label: "Subnet / Gateway", value: `${displayAddress(address.subnet)} / ${gateway}` },
      { label: "Hostname", value: "ESXi host" },
      { label: "DNS", value: dnsPolicy },
      { label: "NTP", value: ntpPolicy },
      { label: "Legacy Protocols", value: legacyProtocolPolicy },
      { label: "SSH", value: "Disabled until enabled" },
      { label: "vSwitch", value: "Management network" },
      { label: "Datastore", value: features?.netapp_enabled ? "NFS/iSCSI after NetApp readiness" : "Local storage by profile" }
    ];
  }
  if (sectionId === "netapp") {
    if (features?.netapp_enabled === false) {
      return [
        { label: "Scope", value: profile?.features.netapp_disabled_reason ?? "NetApp is not in scope for the active lab setup." },
        { label: "Subnet", value: displayAddress(address.subnet) },
        { label: "Topology", value: profile ? labelize(profile.profile_topology) : "Not set" },
        { label: "Normal Validation", value: "Skipped" },
        { label: "Advanced", value: "Available for manual review only" }
      ];
    }
    return [
      { label: "Cluster Name", value: "Configured in setup intent" },
      { label: "Cluster Mgmt", value: displayAddress(address.netapp_cluster_mgmt) },
      { label: "Node A Mgmt", value: displayAddress(address.netapp_node_a_mgmt) },
      { label: "Node B Mgmt", value: displayAddress(address.netapp_node_b_mgmt) },
      { label: "SVM Mgmt", value: displayAddress(address.netapp_svm_mgmt) },
      { label: "NFS LIFs", value: address.netapp_nfs_lifs.join(", ") || "Not set" },
      { label: "iSCSI LIFs", value: address.netapp_iscsi_lifs.join(", ") || "Not set" },
      { label: "DNS / NTP", value: `${dnsPolicy} / ${ntpPolicy}` },
      { label: "SNMP / MTU", value: `${snmpPolicy} / ${mtu}` },
      { label: "Legacy Protocols", value: legacyProtocolPolicy },
      { label: "Protocols", value: profile?.features.storage_protocol?.toUpperCase() ?? "NFS or iSCSI" }
    ];
  }
  if (sectionId === "vcenter") {
    return [
      { label: "Install State", value: "Not installed / not configured" },
      { label: "Deployment Target", value: displayAddress(address.esxi_management) },
      { label: "Datastore", value: "netapp_nfs_ds01" },
      { label: "Storage Protocol", value: profile?.features.storage_protocol?.toUpperCase() ?? "NFS" },
      { label: "VCSA Media", value: "Required under artifacts/Media" },
      { label: "DNS", value: dnsPolicy },
      { label: "NTP", value: ntpPolicy },
      { label: "Gateway", value: gateway },
      { label: "Apply", value: "Install disabled until ESXi and NetApp are ready" }
    ];
  }
  return [
    { label: "Subnet", value: displayAddress(address.subnet) },
    { label: "iLO", value: displayAddress(address.ilo) },
    { label: "Cisco", value: displayAddress(address.cisco_management) },
    { label: "ESXi", value: displayAddress(address.esxi_management) },
    { label: "NetApp Cluster", value: displayAddress(address.netapp_cluster_mgmt) },
    { label: "Gateway", value: gateway }
  ];
}

function controlProfileFieldsForSection(sectionId: string, netappEnabled: boolean): ControlProfileEditField[] {
  const profileFields: ControlProfileEditField[] = [
    { kind: "profile", key: "name", label: "Setup Name" },
    { kind: "profile", key: "description", label: "Notes" }
  ];
  const commonNetworkFields: ControlProfileEditField[] = [
    { kind: "address", key: "subnet", label: "Subnet CIDR" },
    { kind: "global", key: "gateway", label: "Gateway" },
    { kind: "global", key: "dnsServers", label: "DNS Servers" },
    { kind: "global", key: "ntpServers", label: "NTP Servers" }
  ];
  const policyFields: ControlProfileEditField[] = [
    { kind: "global", key: "enableDns", label: "Use DNS", valueType: "boolean" },
    { kind: "global", key: "enableNtp", label: "Use NTP", valueType: "boolean" },
    { kind: "global", key: "enableSnmp", label: "Use SNMP", valueType: "boolean" },
    { kind: "global", key: "disableIpv6", label: "Disable IPv6", valueType: "boolean" },
    { kind: "global", key: "blockLegacyProtocols", label: "Block Legacy Protocols", valueType: "boolean" }
  ];
  const globalDeviceFields: ControlProfileEditField[] = [
    { kind: "global", key: "domainName", label: "Domain" },
    { kind: "global", key: "vlanId", label: "VLAN", valueType: "number" },
    { kind: "global", key: "mtu", label: "MTU", valueType: "number" }
  ];
  const netappFields: ControlProfileEditField[] = [
    { kind: "address", key: "netapp_controller_a_sp", label: "Controller A SP" },
    { kind: "address", key: "netapp_controller_b_sp", label: "Controller B SP" },
    { kind: "address", key: "netapp_cluster_mgmt", label: "Cluster Mgmt" },
    { kind: "address", key: "netapp_node_a_mgmt", label: "Node A Mgmt" },
    { kind: "address", key: "netapp_node_b_mgmt", label: "Node B Mgmt" },
    { kind: "address", key: "netapp_svm_mgmt", label: "SVM Mgmt" },
    { kind: "netapp-list", key: "netappNfsLifs", label: "NFS LIFs" },
    { kind: "netapp-list", key: "netappIscsiLifs", label: "iSCSI LIFs" },
    {
      kind: "global",
      key: "storageProtocol",
      label: "Storage Protocol",
      options: [
        { label: "NFS", value: "nfs" },
        { label: "iSCSI", value: "iscsi" },
        { label: "Local only", value: "none" }
      ],
      valueType: "select"
    }
  ];

  if (sectionId === "lab-profile") {
    return [
      ...profileFields,
      { kind: "address", key: "subnet", label: "Subnet CIDR" },
      { kind: "address", key: "ilo", label: "Permanent iLO IP" },
      { kind: "address", key: "ilo_initial", label: "Initial iLO Login IP" },
      { kind: "address", key: "server_embedded_nic", label: "Server Embedded NIC" },
      { kind: "address", key: "esxi_management", label: "ESXi Management IP" },
      { kind: "address", key: "cisco_management", label: "Cisco Management IP" },
      { kind: "address", key: "ansible_control_host", label: "Control Host IP" },
      ...globalDeviceFields,
      ...commonNetworkFields.filter((field) => field.kind !== "address"),
      ...policyFields,
      ...(netappEnabled ? netappFields : [])
    ];
  }
  if (sectionId === "ilo") {
    return [
      { kind: "address", key: "ilo", label: "Permanent iLO IP" },
      { kind: "address", key: "ilo_initial", label: "Initial iLO Login IP" },
      ...commonNetworkFields,
      { kind: "global", key: "domainName", label: "Domain" },
      ...policyFields.filter((field) => field.key !== "disableIpv6")
    ];
  }
  if (sectionId === "cisco") {
    return [
      { kind: "address", key: "cisco_management", label: "Cisco Management IP" },
      { kind: "address", key: "ansible_control_host", label: "Control Host IP" },
      ...commonNetworkFields,
      ...globalDeviceFields,
      ...policyFields
    ];
  }
  if (sectionId === "raid") {
    return [
      { kind: "address", key: "ilo", label: "Permanent iLO IP" },
      { kind: "address", key: "server_embedded_nic", label: "Server Embedded NIC" },
      ...commonNetworkFields
    ];
  }
  if (sectionId === "esxi") {
    return [
      { kind: "address", key: "esxi_management", label: "ESXi Management IP" },
      ...commonNetworkFields,
      ...globalDeviceFields,
      ...policyFields.filter((field) => field.key !== "enableSnmp")
    ];
  }
  if (sectionId === "netapp") {
    return [
      ...netappFields,
      ...commonNetworkFields,
      ...policyFields.filter((field) => field.key !== "disableIpv6")
    ];
  }
  return [
    { kind: "address", key: "ilo", label: "Permanent iLO IP" },
    { kind: "address", key: "cisco_management", label: "Cisco Management IP" },
    { kind: "address", key: "esxi_management", label: "ESXi Management IP" },
    ...commonNetworkFields
  ];
}

function setupExecutionActionsForSection(sectionId: string, actions: WorkflowAction[]): WorkflowAction[] {
  const stageId = sectionId === "firmware-upgrade" ? "firmware" : sectionId === "verification" ? "build-verification" : sectionId;
  const byId = new Map<string, WorkflowAction>();
  actions
    .filter((action) => action.stage === stageId)
    .filter((action) => !action.action_id.startsWith("commander."))
    .forEach((action) => {
      if (!byId.has(action.action_id)) {
        byId.set(action.action_id, action);
      }
    });
  return Array.from(byId.values()).sort((left, right) => {
    const runnableDelta = Number(workflowActionCanRun(right)) - Number(workflowActionCanRun(left));
    if (runnableDelta !== 0) return runnableDelta;
    const leftOrder = setupActionCategoryOrder(left);
    const rightOrder = setupActionCategoryOrder(right);
    if (leftOrder !== rightOrder) return leftOrder - rightOrder;
    return left.label.localeCompare(right.label);
  });
}

function setupActionCategoryOrder(action: WorkflowAction): number {
  const categoryOrder: Partial<Record<WorkflowAction["category"], number>> = {
    discover: 10,
    inventory: 20,
    verify: 30,
    plan: 40,
    report: 50,
    apply: 70,
    reset: 80,
    upgrade: 90,
    reclaim: 95,
    waive: 100
  };
  if (action.mode === "write") return 70;
  if (action.mode === "destructive") return 80;
  if (action.mode === "upgrade") return 90;
  return categoryOrder[action.category] ?? 60;
}

function controlConfigOptionsForSection(
  sectionId: string,
  workflowActions: WorkflowAction[],
  profile: LabProfile | null
): ControlConfigOption[] {
  const actionFor = (tokens: string[]) => workflowActions.find((action) =>
    tokens.some((token) => action.action_id.includes(token) || action.label.toLowerCase().includes(token))
  );
  const availabilityFor = (tokens: string[]) => actionFor(tokens)?.current_availability ?? "not_configured";
  const linkedActionFor = (tokens: string[]) => actionFor(tokens)?.action_id ?? null;
  const address = profile?.resolved_address_plan ?? profile?.address_plan ?? blankLabAddressPlan();
  const global = profile?.global_settings;
  const features = profile?.features;
  const dns = global?.dns_servers.length ? global.dns_servers.join(", ") : "Not set";
  const ntp = global?.ntp_servers.length ? global.ntp_servers.join(", ") : "Not set";
  const mtu = global?.mtu ? String(global.mtu) : "Not set";
  const vlan = global?.vlan_id || "Not set";
  const dnsPolicy = profilePolicyValue(features?.enable_dns, dns, "servers");
  const ntpPolicy = profilePolicyValue(features?.enable_ntp, ntp, "servers");
  const snmpPolicy = profileSnmpValue(features);
  const ipv6Policy = features?.disable_ipv6 === false ? "Allowed" : "Disabled";
  const legacyProtocolPolicy = features?.block_legacy_protocols === false ? "Allowed" : "Blocked";
  const storageProtocol = features?.storage_protocol?.toUpperCase() || "NFS";
  const option = (
    option_id: string,
    label: string,
    description: string,
    supported_by: ConfigOptionSupport[],
    effect: ConfigOptionEffect,
    tokens: string[],
    desired_value = "Enabled",
    requires_confirmation = effect !== "read_only"
  ): ControlConfigOption => ({
    option_id,
    label,
    device_stage: sectionId,
    description,
    current_value: "Not checked",
    desired_value,
    supported_by,
    availability: availabilityFor(tokens),
    effect,
    requires_confirmation,
    recommended_default: effect === "read_only" || ["disable_ipv6", "block_legacy_protocols", "configure_ntp", "configure_dns"].includes(option_id),
    validation_status: "not_checked",
    linked_action_id: linkedActionFor(tokens)
  });

  if (sectionId === "cisco") {
    return [
      option("disable_ipv6", "Disable IPv6", "Disable unused IPv6 paths after console access is confirmed.", ["console", "ansible"], "config_change", ["bootstrap"], ipv6Policy),
      option("enable_snmp", "Enable / Disable SNMP", "Set SNMP state through the saved Cisco bootstrap plan.", ["console", "ansible"], "config_change", ["bootstrap"], snmpPolicy),
      option("configure_ntp", "Configure NTP", "Apply NTP servers from the active lab setup.", ["console", "ansible"], "config_change", ["bootstrap"], ntpPolicy),
      option("configure_dns", "Configure DNS", "Apply DNS servers from the active lab setup.", ["console", "ansible"], "config_change", ["bootstrap"], dnsPolicy),
      option("configure_mtu", "Configure MTU", "Set management MTU for the lab network.", ["console", "ansible"], "config_change", ["bootstrap"], mtu),
      option("block_legacy_protocols", "Block Legacy Protocols", "Disable older management protocols after SSH is ready.", ["console", "ansible"], "config_change", ["bootstrap"], legacyProtocolPolicy),
      option("enable_ssh", "Enable SSH", "Enable SSH for management validation.", ["console", "ansible"], "config_change", ["validate-ssh"], "Enabled"),
      option("enable_scp", "Enable SCP", "Enable SCP for image/config transfer after access is validated.", ["console", "ansible"], "config_change", ["validate-ssh"], "Enabled"),
      option("configure_vlan10", "Configure VLAN", "Configure the active profile management VLAN and access ports.", ["console", "ansible"], "config_change", ["apply-bootstrap"], vlan),
      option("run_validation", "Run Validation", "Validate console, privilege, SSH, and SCP readiness.", ["console", "ansible"], "read_only", ["validate", "privilege"], "Validated", false)
    ];
  }
  if (sectionId === "ilo") {
    return [
      option("configure_ntp", "Configure NTP", "Apply iLO NTP settings from the active lab setup.", ["redfish"], "config_change", ["ilo", "setup"], ntpPolicy),
      option("configure_dns", "Configure DNS", "Apply iLO DNS and hostname settings.", ["redfish"], "config_change", ["ilo", "setup"], dnsPolicy),
      option("configure_snmp", "Configure SNMP", "Apply iLO SNMP intent from the active global policy.", ["redfish"], "config_change", ["ilo", "setup"], snmpPolicy),
      option("configure_ilo_virtual_media", "Configure iLO Virtual Media", "Mount or unmount installer media through a guarded Redfish path.", ["redfish"], "config_change", ["virtual-media"], "Selected ISO"),
      option("set_one_time_boot", "Set One-Time Boot", "Set the next boot target after media readiness passes.", ["redfish"], "config_change", ["one-time-boot"], "Installer media"),
      option("refresh_inventory", "Refresh Inventory", "Read server, manager, firmware, and storage inventory.", ["redfish"], "read_only", ["inventory"], "Current inventory", false),
      option("reset_server", "Reset Server", "Guarded server reset only after confirmation gates pass.", ["redfish"], "destructive", ["reset"], "Reset if required"),
      option("check_firmware", "Check Firmware", "Collect iLO, BIOS, and Smart Array firmware inventory.", ["redfish"], "read_only", ["firmware"], "Current", false)
    ];
  }
  if (sectionId === "raid") {
    return [
      option("raid_discover", "Discover", "Read Smart Array controller and drive inventory.", ["redfish"], "read_only", ["discovery"], "Discovered", false),
      option("raid_plan", "Plan", "Build a RAID plan from saved desired intent.", ["redfish"], "read_only", ["plan"], "Planned", false),
      option("raid_apply", "Apply", "Apply saved RAID plan only after destructive gates pass.", ["redfish"], "destructive", ["apply"], "Apply desired RAID"),
      option("raid_pending", "Pending", "Check pending RAID and reset state.", ["redfish"], "read_only", ["pending"], "No pending change", false),
      option("raid_reset", "Reset", "Reset server only if required to commit RAID changes.", ["redfish"], "destructive", ["reset"], "Reset if required"),
      option("raid_validate", "Validate", "Validate storage layout after reset.", ["redfish"], "read_only", ["validate"], "Validated", false)
    ];
  }
  if (sectionId === "esxi") {
    return [
      option("esxi_install_rebuild", "Install / Rebuild", "Run guarded ESXi install/rebuild workflow after readiness passes.", ["redfish", "govc"], "destructive", ["rebuild", "install"], "Install selected ISO"),
      option("esxi_recover_management", "Recover Management", "Recover ESXi management reachability through the guarded iLO path when power state is verified.", ["redfish", "govc"], "destructive", ["recover-management"], displayAddress(address.esxi_management)),
      option("enable_ssh", "Enable SSH", "Enable SSH for management validation when policy allows.", ["govc", "manual"], "config_change", ["ssh"], "Enabled"),
      option("configure_ntp", "Configure NTP", "Apply NTP servers from the active lab setup.", ["govc"], "config_change", ["management"], ntpPolicy),
      option("configure_dns", "Configure DNS", "Apply DNS servers from the active lab setup.", ["govc"], "config_change", ["management"], dnsPolicy),
      option("validate_api", "Validate API", "Validate ESXi management API readiness.", ["govc"], "read_only", ["management", "api"], "Validated", false),
      option("validate_ssh", "Validate SSH", "Validate ESXi SSH readiness.", ["cli"], "read_only", ["ssh"], "Validated", false),
      option("configure_esxi_nfs_datastore", "Add NFS Datastore", "Add the NetApp NFS datastore after NetApp readiness passes.", ["govc"], "config_change", ["netapp-datastore"], "Mounted")
    ];
  }
  if (sectionId === "netapp") {
    return [
      option("setup_preview", "Setup Preview", "Preview cluster, node, SVM, LIF, and storage setup intent.", ["ontap_rest", "console"], "read_only", ["setup-preview"], "Preview ready", false),
      option("setup_apply", "Setup Apply", "Guarded NetApp setup apply path after explicit gates pass.", ["ontap_rest", "console"], "config_change", ["setup-apply"], "Apply setup"),
      option("upgrade_inventory", "Upgrade Inventory", "Inventory ONTAP image and component firmware readiness.", ["ontap_rest", "cli"], "read_only", ["upgrade-inventory", "inventory"], "Inventory current", false),
      option("upgrade_plan", "Upgrade Plan", "Plan ONTAP upgrade package, target, and validation blockers.", ["ontap_rest"], "read_only", ["upgrade-plan", "plan"], "Plan ready", false),
      option("upgrade_validate", "Upgrade Validate", "Run pre-upgrade validation gates.", ["ontap_rest"], "read_only", ["upgrade-validate", "validate"], "Validated", false),
      option("upgrade_apply", "Upgrade Apply", "Guarded ONTAP upgrade apply path after exact confirmation.", ["ontap_rest"], "upgrade", ["upgrade-apply"], "Upgrade ONTAP"),
      option("configure_dns", "Configure DNS", "Apply DNS servers from the active lab setup.", ["ontap_rest"], "config_change", ["setup"], dnsPolicy),
      option("configure_ntp", "Configure NTP", "Apply NTP servers from the active lab setup.", ["ontap_rest"], "config_change", ["setup"], ntpPolicy),
      option("configure_snmp", "Configure SNMP", "Apply SNMP policy from the active lab setup.", ["ontap_rest"], "config_change", ["setup"], snmpPolicy),
      option("configure_netapp_nfs", "Configure NetApp NFS", "Configure NFS export path and datastore readiness.", ["ontap_rest", "ansible"], "config_change", ["nfs"], `${storageProtocol} / ${address.netapp_nfs_lifs.join(", ") || "No LIFs"}`),
      option("choose_storage_protocol", "Choose Storage Protocol", "Select NFS or iSCSI for the build handoff.", ["manual", "ontap_rest"], "config_change", ["nfs", "iscsi"], storageProtocol),
      option("nfs_vcenter_readiness", "NFS / vCenter Readiness", "Validate datastore handoff before vCenter use.", ["govc", "ontap_rest"], "read_only", ["vcenter", "nfs"], "Ready", false)
    ];
  }
  if (sectionId === "vcenter") {
    return [
      option("vcenter_install_readiness", "Install Readiness", "Check VCSA media, ESXi reachability, NetApp datastore readiness, and missing values.", ["manual", "govc"], "read_only", ["install-readiness"], "Ready", false),
      option("vcenter_install_plan", "Install Plan", "Build the preview-only VCSA deployment plan after prerequisites are ready.", ["manual", "govc"], "read_only", ["install-plan"], "Plan ready", false),
      option("vcenter_install_preview", "Preview Deploy", "Generate the redacted VCSA deploy preview without starting deployment.", ["manual", "govc"], "read_only", ["install-preview"], "Preview ready", false),
      option("vcenter_install_apply", "Deploy vCenter", "Run the guarded vcsa-deploy install workflow after readiness and preview are ready.", ["manual", "govc"], "config_change", ["install-apply"], "Deploy vCenter"),
      option("vcenter_attach_esxi_preview", "Attach ESXi Preview", "Preview datacenter, cluster, host attach, datastore, and VM inventory checks.", ["govc"], "read_only", ["attach-preview"], "Preview ready", false),
      option("vcenter_attach_esxi_apply", "Attach ESXi", "Run the guarded govc host attach workflow after preview is ready.", ["govc"], "config_change", ["attach-apply"], "Attach ESXi"),
      option("vcenter_post_attach_validation", "Post-Attach Validation", "Validate vCenter host, datastore, and VM inventory visibility.", ["govc"], "read_only", ["attach-validation"], "Ready", false),
      option("vcenter_netapp_readiness", "NetApp Readiness", "Validate vCenter/govc handoff against the NetApp NFS datastore plan.", ["govc", "ontap_rest"], "read_only", ["netapp-readiness"], "Ready", false),
      option("vcenter_datastore_plan", "Datastore Plan", "Preview datastore attach commands without mounting storage.", ["govc"], "read_only", ["datastore-plan"], "Plan ready", false)
    ];
  }
  return [
    option("configure_dns", "Configure DNS", "Apply profile DNS values.", ["manual"], "config_change", ["dns"], dnsPolicy),
    option("configure_ntp", "Configure NTP", "Apply profile NTP values.", ["manual"], "config_change", ["ntp"], ntpPolicy),
    option("configure_mtu", "Configure MTU", "Apply profile MTU value.", ["manual"], "config_change", ["mtu"], mtu)
  ];
}

function firstReadOnlyWorkflowAction(actions: WorkflowAction[], tokens: string[]): WorkflowAction | null {
  return (
    actions.find((action) =>
      action.mode === "read_only" &&
      action.ui_run_supported &&
      tokens.some((token) => action.action_id.includes(token) || action.label.toLowerCase().includes(token))
    ) ??
    actions.find((action) =>
      action.mode === "read_only" &&
      tokens.some((token) => action.action_id.includes(token) || action.label.toLowerCase().includes(token))
    ) ??
    null
  );
}

function findControlStateValue(section: ControlSectionRecord, token: string): string | null {
  const normalized = token.toLowerCase();
  const match = section.current_state.find((item) => item.label.toLowerCase().includes(normalized));
  return match?.value && match.value !== "Not set" ? match.value : null;
}

function globalConfigEditStateFromProfile(profile: LabProfile | null): GlobalConfigEditState {
  const source = profile ? labProfileFormFrom(profile).globalSettings : blankLabGlobalSettings(24);
  return {
    domainName: source.domainName,
    dnsServers: source.dnsServers,
    ntpServers: source.ntpServers,
    timezone: source.timezone,
    vlanId: source.vlanId,
    mtu: source.mtu,
    storageProtocol: source.storageProtocol,
    disableIpv6: source.disableIpv6,
    blockLegacyProtocols: source.blockLegacyProtocols,
    enableSnmp: source.enableSnmp,
    enableNtp: source.enableNtp,
    enableDns: source.enableDns
  };
}

function profilePolicyValue(enabled: boolean | undefined, value: string, missingLabel: string): string {
  if (enabled === false) return "Disabled by lab setup";
  return value && value !== "Not set" ? value : `Enabled, ${missingLabel} not set`;
}

function profileSnmpValue(features: Partial<LabProfileFeatures> | null | undefined): string {
  return features?.enable_snmp ? "Enabled by lab setup" : "Disabled by lab setup";
}

function CommanderModePanel({
  actions,
  busyAction,
  onCopy,
  onPlan
}: {
  actions: ControlAction[];
  busyAction: string;
  onCopy: (action: ControlAction) => void;
  onPlan: (action: ControlAction) => void;
}) {
  if (!actions.length) {
    return null;
  }

  return (
    <section className="panel commander-panel">
      <div className="readiness-head">
        <PanelTitle icon={<Wrench size={18} />} title="Commander Mode" />
        <StatusBadge status="manual_command_required" />
      </div>
      <ActionButtonRow
        actions={actions}
        busyAction={busyAction}
        onCopy={onCopy}
        onPlan={onPlan}
      />
    </section>
  );
}

function ControlSection({
  accessError,
  busyAction,
  busyAccessSection,
  children,
  onCopy,
  onCopyText,
  onSaveAccess,
  onPlan,
  planResult,
  section,
  showActions = true,
  showAccessConfig = true
}: {
  accessError: string;
  busyAction: string;
  busyAccessSection: string;
  children?: ReactNode;
  copyMessage: string;
  onCopy: (action: ControlAction) => void;
  onCopyText: (text: string, label: string) => void;
  onSaveAccess: (sectionId: string, payload: ControlAccessConfigWrite) => Promise<void>;
  onPlan: (action: ControlAction) => void;
  planResult: ControlActionPlan | null;
  section: ControlSectionRecord;
  showActions?: boolean;
  showAccessConfig?: boolean;
}) {
  const resultStatus = asString(section.last_result.status) || "not_run";
  const resultLabel = asString(section.last_result.label) || "No result";
  const resultReport = asString(section.last_result.report);

  return (
    <section className="control-section" id={`control-${section.id}`}>
      <div className="control-section-head">
        <div>
          <p className="summary-kicker">{section.stage}</p>
          <h2>{section.title}</h2>
          <p>{section.description}</p>
        </div>
        <StatusPill status={section.status} />
      </div>
      {showAccessConfig && section.access_config && (
        <ControlAccessConfigTile
          busy={busyAccessSection === section.id}
          config={section.access_config}
          error={busyAccessSection === section.id ? "" : accessError}
          onSave={onSaveAccess}
        />
      )}
      <div className="control-state-grid">
        <CurrentStateBlock items={section.current_state} />
        <DesiredStateBlock items={section.desired_state} />
        <PlanDiffBlock items={section.plan_diff} />
      </div>
      {children}
      {showActions && section.actions.length > 0 && (
        <ActionButtonRow
          actions={section.actions}
          busyAction={busyAction}
          onCopy={onCopy}
          onPlan={onPlan}
        />
      )}
      {planResult && <ControlPlanResult plan={planResult} />}
      <div className="control-result-grid">
        <div>
          <span>Last result</span>
          <strong>{displayStatusLabel(resultStatus)}</strong>
          <p>{resultLabel}</p>
        </div>
        <div>
          <span>Report</span>
          <strong>{resultReport || "No report yet"}</strong>
          {resultReport && (
            <button
              className="small-button"
              onClick={() => onCopyText(resultReport, "Report path")}
              type="button"
            >
              <Copy size={14} />
              Copy
            </button>
          )}
        </div>
      </div>
      {section.report_links.length > 0 && (
        <AdvancedDetails
          className="section-details"
          summary={`${section.report_links.length} report link${section.report_links.length === 1 ? "" : "s"}`}
          title="Report links"
        >
          <ReportLinkList reports={section.report_links.slice(0, 8)} />
          <div className="action-row report-copy-row">
            {section.report_links.slice(0, 3).map((report) => (
              <button
                className="small-button"
                key={`${section.id}-copy-${report.label}-${report.path}`}
                onClick={() => onCopyText(report.path, report.label)}
                type="button"
              >
                <Copy size={14} />
                Copy {report.label}
              </button>
            ))}
          </div>
        </AdvancedDetails>
      )}
      <AdvancedDetails
        className="control-diagnostics"
        summary="Raw catalog state, provider diagnostics, blockers, reports, and generated command metadata"
        title="Advanced diagnostics"
      >
        <JsonDetails title={`${section.title} diagnostics`} data={section.advanced_diagnostics} />
      </AdvancedDetails>
    </section>
  );
}

function CurrentAccessConfigInline({
  busy,
  config,
  error,
  onSave
}: {
  busy: boolean;
  config: ControlAccessConfig;
  error: string;
  onSave: (sectionId: string, payload: ControlAccessConfigWrite) => Promise<void>;
}) {
  const [currentIp, setCurrentIp] = useState(config.original_dhcp_ip ?? "");
  const [message, setMessage] = useState("");
  const [localError, setLocalError] = useState("");
  const configKey = `${config.section_id}:${config.original_dhcp_ip ?? ""}:${config.updated_at ?? ""}`;
  const finalIp = displayAddress(config.desired_management_ip);

  useEffect(() => {
    setCurrentIp(config.original_dhcp_ip ?? "");
    setMessage("");
    setLocalError("");
  }, [configKey, config]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    setLocalError("");
    try {
      await onSave(config.section_id, {
        first_time_configuring: config.first_time_configuring,
        original_dhcp_ip: cleanNullable(currentIp),
        username_reference: config.username_reference,
        password_configured: config.password_configured,
        password_reference_label: config.password_reference_label
      });
      setMessage("Current login IP saved.");
    } catch (err) {
      setLocalError((err as Error).message);
    }
  }

  return (
    <form className="current-access-inline" onSubmit={submit}>
      <Field label="Current login IP">
        <input
          disabled={busy}
          inputMode="decimal"
          onChange={(event) => setCurrentIp(event.target.value)}
          placeholder="Temporary DHCP or existing address"
          value={currentIp}
        />
        <small>Use this when the device is still reachable at a temporary address.</small>
      </Field>
      <div className="current-access-final">
        <span>Permanent IP</span>
        <strong>{finalIp}</strong>
        <small>{config.desired_address_label}</small>
      </div>
      <div className="current-access-actions">
        <button className="small-button" disabled={busy} type="submit">
          <Save size={14} />
          {busy ? "Saving" : "Save current IP"}
        </button>
      </div>
      {(message || localError || error) && (
        <p className={localError || error ? "form-error" : "success"}>{localError || error || message}</p>
      )}
    </form>
  );
}

function ControlAccessConfigTile({
  busy,
  config,
  error,
  onSave
}: {
  busy: boolean;
  config: ControlAccessConfig;
  error: string;
  onSave: (sectionId: string, payload: ControlAccessConfigWrite) => Promise<void>;
}) {
  const [firstTimeConfiguring, setFirstTimeConfiguring] = useState(config.first_time_configuring);
  const [originalDhcpIp, setOriginalDhcpIp] = useState(config.original_dhcp_ip ?? "");
  const [usernameReference, setUsernameReference] = useState(config.username_reference ?? "");
  const [passwordConfigured, setPasswordConfigured] = useState(config.password_configured);
  const [passwordReferenceLabel, setPasswordReferenceLabel] = useState("");
  const [editableFieldValues, setEditableFieldValues] = useState<Record<string, string>>(
    controlEditableFieldValues(config)
  );

  useEffect(() => {
    setFirstTimeConfiguring(config.first_time_configuring);
    setOriginalDhcpIp(config.original_dhcp_ip ?? "");
    setUsernameReference(config.username_reference ?? "");
    setPasswordConfigured(config.password_configured);
    setPasswordReferenceLabel("");
    setEditableFieldValues(controlEditableFieldValues(config));
  }, [config]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    await onSave(config.section_id, {
      first_time_configuring: firstTimeConfiguring,
      original_dhcp_ip: cleanNullable(originalDhcpIp),
      username_reference: cleanNullable(usernameReference),
      password_configured: passwordConfigured,
      password_reference_label: cleanNullable(passwordReferenceLabel),
      editable_fields: config.editable_fields.map((field) => ({
        label: field.label,
        value: cleanNullable(editableFieldValues[field.label] ?? "")
      }))
    });
  }

  const ready = config.blockers.length === 0;

  return (
    <section className="control-access-tile">
      <div className="readiness-head">
        <div>
          <p className="summary-kicker">Access & IP Config</p>
          <h3>{config.title}</h3>
          <p>{firstTimeConfiguring ? config.first_time_note : "Existing access is recorded; final IP settings remain editable from the lab setup."}</p>
        </div>
        <StatusBadge status={ready ? "ready" : "blocked"} />
      </div>
      <form className="control-access-layout" onSubmit={submit}>
        <div className="control-access-form">
          <label className="checkbox-line">
            <input
              checked={firstTimeConfiguring}
              onChange={(event) => setFirstTimeConfiguring(event.target.checked)}
              type="checkbox"
            />
            <span>First-time configuration path</span>
          </label>
          <Field label="Original DHCP / Current IP">
            <input
              inputMode="decimal"
              onChange={(event) => setOriginalDhcpIp(event.target.value)}
              placeholder="Current DHCP address"
              value={originalDhcpIp}
            />
          </Field>
          <Field label="Access Username">
            <input
              onChange={(event) => setUsernameReference(event.target.value)}
              placeholder="Username or local reference"
              value={usernameReference}
            />
          </Field>
          <label className="checkbox-line">
            <input
              checked={passwordConfigured}
              onChange={(event) => setPasswordConfigured(event.target.checked)}
              type="checkbox"
            />
            <span>Password is available from the local credential path</span>
          </label>
          <Field label="Password Reference">
            <input
              onChange={(event) => setPasswordReferenceLabel(event.target.value)}
              placeholder={config.password_configured ? "Configured; enter new reference to replace" : "Reference only, no plaintext password"}
              value={passwordReferenceLabel}
            />
            <small>
              {config.password_configured
                ? "Saved credential reference is hidden."
                : "Do not enter a plaintext password."}
            </small>
          </Field>
          <Feedback error={error} />
          <div className="action-row">
            <button disabled={busy} type="submit">
              <Save size={16} />
              {busy ? "Saving" : "Save Access & IP Config"}
            </button>
            <Link className="button-link" to="/lab-profiles">
              <Pencil size={16} />
              Edit saved setup
            </Link>
          </div>
        </div>
        <div className="control-access-facts">
          <div className="provider-fact-grid compact">
            <ProviderFact label={config.desired_address_label} value={displayAddress(config.desired_management_ip)} />
            <ProviderFact label="Access Method" value={config.access_method} />
            <ProviderFact label="Password" value={config.password_configured ? "Configured" : "Missing"} />
            <ProviderFact
              label="Updated"
              value={config.updated_at ? formatDateTime(config.updated_at) : "Not saved"}
            />
          </div>
          {config.blockers.length > 0 && (
            <div className="provider-issue-rows">
              {config.blockers.map((blocker) => (
                <div className="provider-issue warning" key={`${config.section_id}-${blocker}`}>
                  <AlertTriangle size={16} />
                  <span>{blocker}</span>
                </div>
              ))}
            </div>
          )}
          <div className="control-config-field-list">
            {config.editable_fields.map((field) => (
              <Field key={`${config.section_id}-${field.label}`} label={field.label}>
                <input
                  onChange={(event) =>
                    setEditableFieldValues((current) => ({
                      ...current,
                      [field.label]: event.target.value
                    }))
                  }
                  placeholder={field.value || "Not set"}
                  value={editableFieldValues[field.label] ?? ""}
                />
                <small>{field.source === "saved_override" ? "Saved override" : "Default from active lab setup"}</small>
              </Field>
            ))}
          </div>
        </div>
      </form>
    </section>
  );
}

function controlEditableFieldValues(config: ControlAccessConfig): Record<string, string> {
  return config.editable_fields.reduce<Record<string, string>>((values, field) => {
    values[field.label] = field.value === "Not set" ? "" : field.value;
    return values;
  }, {});
}

function CurrentStateBlock({ items }: { items: ControlStateItem[] }) {
  return <ControlStateBlock icon={<Activity size={17} />} items={items} title="Current State" />;
}

function DesiredStateBlock({ items }: { items: ControlStateItem[] }) {
  return <ControlStateBlock icon={<ShieldCheck size={17} />} items={items} title="Desired State" />;
}

function ControlStateBlock({
  icon,
  items,
  title
}: {
  icon: ReactNode;
  items: ControlStateItem[];
  title: string;
}) {
  return (
    <section className="control-state-block">
      <div className="control-block-title">
        {icon}
        <h3>{title}</h3>
      </div>
      {items.length ? (
        <dl>
          {items.map((item) => (
            <div key={`${title}-${item.label}`}>
              <dt>{item.label}</dt>
              <dd>
                <strong>{item.value}</strong>
                {item.status && <StatusBadge status={item.status} />}
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="muted">No state values are exposed yet.</p>
      )}
    </section>
  );
}

function PlanDiffBlock({ items }: { items: ControlPlanDiffItem[] }) {
  return (
    <section className="control-state-block plan-diff-block">
      <div className="control-block-title">
        <Route size={17} />
        <h3>Plan / Diff</h3>
      </div>
      {items.length ? (
        <table>
          <thead>
            <tr>
              <th>Item</th>
              <th>Current</th>
              <th>Desired</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={`${item.label}-${item.current}-${item.desired}`}>
                <td>{item.label}</td>
                <td>{item.current}</td>
                <td>{item.desired}</td>
                <td>
                  <StatusBadge status={item.status} />
                  {item.note && <p className="control-table-note">{item.note}</p>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">No diff is available for this section.</p>
      )}
    </section>
  );
}

function ActionButtonRow({
  actions,
  busyAction,
  onCopy,
  onPlan
}: {
  actions: ControlAction[];
  busyAction: string;
  onCopy: (action: ControlAction) => void;
  onPlan: (action: ControlAction) => void;
}) {
  return (
    <div className="control-action-list">
      {actions.map((action) => (
        <article className={`control-action ${action.classification}`} key={action.id}>
          <div className="control-action-head">
            <div>
              <strong>{action.label}</strong>
              <span>{action.device_stage}</span>
            </div>
            <div className="classification-tags">
              <span className={`classification-tag ${action.classification}`}>
                {classificationLabel(action.classification)}
              </span>
              <StatusBadge status={action.availability} />
            </div>
          </div>
          <p>{action.description}</p>
          {action.blocker && <p className="control-action-blocker">{action.blocker}</p>}
          <ControlRequirementList action={action} />
          <div className="action-row">
            <button disabled={busyAction === action.id} onClick={() => onPlan(action)} type="button">
              <Route size={16} />
              {busyAction === action.id ? "Planning" : "Plan"}
            </button>
            <button onClick={() => onCopy(action)} type="button">
              <Copy size={16} />
              Copy
            </button>
            <button disabled title="Direct run is disabled in this pass." type="button">
              <Ban size={16} />
              Run
            </button>
          </div>
          <code>{action.suggested_command || action.api_endpoint || action.plan_endpoint}</code>
        </article>
      ))}
    </div>
  );
}

function ControlRequirementList({ action }: { action: ControlAction }) {
  const items = [
    ...action.required_inputs.map((input) => `${input.label}${input.required ? " required" : ""}`),
    ...action.required_flags,
    ...action.required_confirmations.map((confirmation) => `Confirm: ${confirmation}`)
  ];
  if (!items.length) {
    return null;
  }
  return (
    <ul className="control-requirements">
      {items.slice(0, 5).map((item) => (
        <li key={`${action.id}-${item}`}>{item}</li>
      ))}
    </ul>
  );
}

function ControlPlanResult({ plan }: { plan: ControlActionPlan }) {
  return (
    <section className="control-plan-result">
      <div className="readiness-head">
        <div>
          <strong>{plan.action.label} plan</strong>
          <p>{plan.message}</p>
        </div>
        <StatusBadge status={plan.status} />
      </div>
      <div className="stage-list control-plan-steps">
        {plan.plan_steps.map((step) => (
          <div className="stage-item" key={`${plan.action.id}-${step.label}`}>
            <div>
              <strong>{step.label}</strong>
              <StatusBadge status={step.status} />
            </div>
            <p>{step.detail}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function ControlLabProfilePanel({
  onCopyText,
  profile
}: {
  onCopyText: (text: string, label: string) => void;
  profile: ControlLabProfile;
}) {
  const networkEntries = Object.entries(profile.network);
  const flagEntries = Object.entries(profile.configured_flags);

  return (
    <section className="control-extra-panel lab-profile-control-panel">
      <div className="readiness-head">
        <div>
          <strong>{profile.active_profile_name}</strong>
          <p>{labelize(profile.source)} v{profile.version}</p>
        </div>
        <Link className="button-link" to={profile.edit_profile_path}>
          <Pencil size={16} />
          Edit Profile
        </Link>
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Topology" value={labelize(profile.topology ?? "unknown")} />
        <ProviderFact label="Subnet Size" value={`/${profile.global_settings.subnet_prefix}`} />
        <ProviderFact
          label="NetApp Capability"
          value={
            profile.features.netapp_enabled
              ? "Available"
              : asString(profile.features.netapp_disabled_reason) || profile.global_settings.netapp_disabled_reason || "Not in scope"
          }
        />
        <ProviderFact
          label="vCenter"
          value={profile.features.vcenter_enabled ? "In scope" : asString(profile.features.vcenter_disabled_reason) || "Not in scope"}
        />
        {labAddressFields.map((field) => (
          <ProviderFact
            key={`control-profile-${field.key}`}
            label={field.label}
            value={displayAddress(profile.address_plan[field.key])}
          />
        ))}
        <ProviderFact
          label="NetApp NFS LIFs"
          value={profile.address_plan.netapp_nfs_lifs.join(", ") || "Not in scope"}
        />
        <ProviderFact
          label="NetApp iSCSI LIFs"
          value={profile.address_plan.netapp_iscsi_lifs.join(", ") || "Not in scope"}
        />
        {profile.not_in_scope_stages.length > 0 && (
          <ProviderFact label="Not In Scope" value={profile.not_in_scope_stages.map(labelize).slice(0, 6).join(", ")} />
        )}
      </div>
      <div className="control-profile-grid">
        <div>
          <h3>Network</h3>
          {networkEntries.map(([key, value]) => (
            <ProviderFact key={`network-${key}`} label={labelize(key)} value={asString(value)} />
          ))}
        </div>
        <div>
          <h3>Configured Flags</h3>
          {flagEntries.map(([key, value]) => (
            <ProviderFact key={key} label={key} value={value ? "true" : "false"} />
          ))}
        </div>
      </div>
      {profile.stale_or_invalid_values.length > 0 ? (
        <div className="provider-issue-rows">
          {profile.stale_or_invalid_values.map((issue) => (
            <div className="provider-issue warning" key={issue}>
              <AlertTriangle size={16} />
              <span>{issue}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="success">No stale or invalid core lab setup values are reported.</p>
      )}
      {profile.mismatch_warnings.length > 0 && (
        <div className="provider-issue-rows">
          {profile.mismatch_warnings.slice(0, 4).map((issue) => (
            <div className="provider-issue warning" key={`${asString(issue.env_field)}-${asString(issue.expected_value)}`}>
              <AlertTriangle size={16} />
              <span>
                {asString(issue.env_field) || asString(issue.field)} currently {asString(issue.current_value) || "not set"}; expected {asString(issue.expected_value) || "not set"}.
              </span>
            </div>
          ))}
        </div>
      )}
      <div className="control-command-box">
        <div className="readiness-head">
          <strong>Env update command</strong>
          <button
            className="small-button"
            onClick={() => onCopyText(profile.env_update_command, "Env update command")}
            type="button"
          >
            <Copy size={14} />
            Copy
          </button>
        </div>
        <pre>{profile.env_update_command}</pre>
      </div>
    </section>
  );
}

function FirmwareGuardedControlsPanel({
  actions,
  onRunWorkflowAction,
  runningActionId
}: {
  actions: WorkflowAction[];
  onRunWorkflowAction: RunWorkflowActionHandler;
  runningActionId: string;
}) {
  if (!actions.length) {
    return null;
  }
  return (
    <section className="control-extra-panel firmware-guarded-controls">
      <div className="readiness-head">
        <div>
          <strong>Guarded Controls</strong>
          <p>Configuration, install, and upgrade actions with exact confirmation gates.</p>
        </div>
        <StatusBadge status="manual_command_required" />
      </div>
      <div className="firmware-guarded-control-grid">
        {actions.map((action) => (
          <article className="firmware-guarded-control" key={`firmware-guarded-${action.action_id}`}>
            <div>
              <strong>{firmwareRelatedActionTitle(action)}</strong>
              <span>{minimalStageLabel(action.stage, action.stage_label)}</span>
            </div>
            <GuardedWorkflowActionButton
              action={action}
              compact
              label={firmwareRelatedActionLabel(action)}
              onRun={onRunWorkflowAction}
              running={runningActionId === action.action_id}
            />
          </article>
        ))}
      </div>
    </section>
  );
}

function FirmwareUpgradeCenter({ section }: { section: ControlSectionRecord }) {
  return (
    <section className="control-extra-panel upgrade-center-panel">
      <div className="readiness-head">
        <div>
          <strong>Upgrade Center</strong>
          <p>Inventory and compliance are visible here; upgrade execution remains gated.</p>
        </div>
        <StatusBadge status={section.status} />
      </div>
      <table className="provider-candidate-table">
        <thead>
          <tr>
            <th>Component</th>
            <th>Current</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {section.current_state.map((item) => (
            <tr key={`upgrade-${item.label}`}>
              <td>{item.label}</td>
              <td>{item.value}</td>
              <td>{item.status ? <StatusBadge status={item.status} /> : "Unknown"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function ActionHistoryReportsPanel({ actions }: { actions: ControlAction[] }) {
  const reportActions = actions.filter((action) => action.last_report);
  return (
    <section className="control-extra-panel">
      <div className="readiness-head">
        <div>
          <strong>Action History / Reports</strong>
          <p>{reportActions.length} actions have report paths.</p>
        </div>
        <StatusBadge status="report_available" />
      </div>
      <table className="provider-candidate-table control-report-table">
        <thead>
          <tr>
            <th>Action</th>
            <th>Status</th>
            <th>Report</th>
          </tr>
        </thead>
        <tbody>
          {reportActions.slice(0, 20).map((action) => (
            <tr key={`history-${action.id}`}>
              <td>{action.label}</td>
              <td><StatusBadge status={action.last_run_status} /></td>
              <td><code>{action.last_report}</code></td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function CompactActionRow({
  action,
  onCopy,
  onRun,
  onSelect,
  running,
  selected
}: {
  action: WorkflowAction;
  onCopy: (action: WorkflowAction) => void;
  onRun?: RunWorkflowActionHandler;
  onSelect: (actionId: string) => void;
  running: boolean;
  selected: boolean;
}) {
  return (
    <tr className={selected ? "selected-row" : ""}>
      <td>
        <button className="table-row-button" onClick={() => onSelect(action.action_id)} type="button">
          <strong>{humanWorkflowActionLabel(action)}</strong>
          <span>{humanizeAction(action.next_action)}</span>
        </button>
      </td>
      <td>{minimalStageLabel(action.stage, action.stage_label)}</td>
      <td>{workflowModeLabel(action.mode)}</td>
      <td>
        <StatusBadge status={action.current_availability} />
        {action.blockers[0] && <p className="control-table-note">{humanizeBlocker(action.blockers[0])}</p>}
      </td>
      <td>
        <div className="action-row">
          <WorkflowActionRunControl
            action={action}
            compact
            onCopy={onCopy}
            onRun={onRun}
            running={running}
          />
          <button className="small-button" onClick={() => onSelect(action.action_id)} type="button">
            <Route size={14} />
            Details
          </button>
        </div>
      </td>
    </tr>
  );
}

function CompactWorkflowActionDetails({
  action,
  latestRun,
  onCopy,
  onRun,
  running
}: {
  action: WorkflowAction;
  latestRun?: WorkflowActionRun;
  onCopy: (action: WorkflowAction) => void;
  onRun?: RunWorkflowActionHandler;
  running: boolean;
}) {
  const trace = latestRun ? workflowRunToTrace(latestRun) : action.last_run_trace;
  const artifacts = uniqueStrings([
    ...action.evidence_artifacts,
    ...action.reports,
    ...(action.last_run_report ? [action.last_run_report] : []),
    ...trace.report_artifacts
  ]);
  return (
    <section className="panel compact-action-detail">
      <div className="minimal-detail-head">
        <div>
          <span className="summary-kicker">{minimalStageLabel(action.stage, action.stage_label)}</span>
          <h2>{humanWorkflowActionLabel(action)}</h2>
          <p>{humanizeAction(action.next_action)}</p>
        </div>
        <HumanStatusPill status={action.current_availability} />
      </div>
      <BlockerSummary blockers={action.blockers.slice(0, 1)} empty="No current blocker is reported for this action." />
      <div className="minimal-primary-action">
        <span>Move forward</span>
        <WorkflowActionRunControl
          action={action}
          compact
          onCopy={onCopy}
          onRun={onRun}
          running={running}
        />
      </div>
      <EvidenceDrawer count={artifacts.length} title="Action Proof">
        <EvidenceList artifacts={artifacts} empty="No proof links are available for this action yet." />
      </EvidenceDrawer>
    </section>
  );
}

function ActionCatalogTable({
  actions,
  onCopy,
  onRun,
  onSelect,
  runningActionId = "",
  selectedActionId
}: {
  actions: WorkflowAction[];
  onCopy: (action: WorkflowAction) => void;
  onRun?: RunWorkflowActionHandler;
  onSelect: (actionId: string) => void;
  runningActionId?: string;
  selectedActionId: string;
}) {
  const { isAdvancedMode } = useUiMode();
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState("all");
  const [stage, setStage] = useState("all");
  const stages = Array.from(new Set(actions.map((action) => action.stage_label))).sort();
  const filtered = actions.filter((action) => {
    const text = `${action.action_id} ${action.label} ${action.stage_label} ${action.category}`.toLowerCase();
    const queryMatch = !query || text.includes(query.toLowerCase());
    const modeMatch = mode === "all" || action.mode === mode;
    const stageMatch = stage === "all" || action.stage_label === stage;
    return queryMatch && modeMatch && stageMatch;
  });

  if (!isAdvancedMode) {
    return (
      <section className="panel action-catalog-panel compact-action-panel">
        <div className="readiness-head">
          <PanelTitle icon={<ClipboardList size={18} />} title="Actions" />
          <span className="muted">{filtered.length} of {actions.length}</span>
        </div>
        <div className="control-catalog-filters compact">
          <Field label="Search">
            <input value={query} onChange={(event) => setQuery(event.target.value)} />
          </Field>
          <Field label="Type">
            <select value={mode} onChange={(event) => setMode(event.target.value)}>
              <option value="all">All</option>
              <option value="read_only">Read only</option>
              <option value="report_only">Report only</option>
              <option value="write">Write</option>
              <option value="destructive">Destructive</option>
              <option value="upgrade">Upgrade</option>
            </select>
          </Field>
          <Field label="Stage">
            <select value={stage} onChange={(event) => setStage(event.target.value)}>
              <option value="all">All</option>
              {stages.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
          </Field>
        </div>
        <table className="provider-candidate-table compact-action-table">
          <thead>
            <tr>
              <th>Action</th>
              <th>Stage</th>
              <th>Type</th>
              <th>Status</th>
              <th>Run / Copy</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((action) => (
              <CompactActionRow
                action={action}
                key={`compact-catalog-${action.action_id}`}
                onCopy={onCopy}
                onRun={onRun}
                onSelect={onSelect}
                running={runningActionId === action.action_id}
                selected={action.action_id === selectedActionId}
              />
            ))}
          </tbody>
        </table>
      </section>
    );
  }

  return (
    <section className="panel action-catalog-panel">
      <div className="readiness-head">
        <PanelTitle icon={<ClipboardList size={18} />} title="Action Catalog" />
        <span className="muted">{filtered.length} of {actions.length}</span>
      </div>
      <div className="control-catalog-filters">
        <Field label="Search">
          <input value={query} onChange={(event) => setQuery(event.target.value)} />
        </Field>
        <Field label="Mode">
          <select value={mode} onChange={(event) => setMode(event.target.value)}>
            <option value="all">All</option>
            <option value="read_only">Read only</option>
            <option value="report_only">Report only</option>
            <option value="write">Write</option>
            <option value="destructive">Destructive</option>
            <option value="upgrade">Upgrade</option>
          </select>
        </Field>
        <Field label="Stage">
          <select value={stage} onChange={(event) => setStage(event.target.value)}>
            <option value="all">All</option>
            {stages.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </Field>
      </div>
      <table className="provider-candidate-table action-catalog-table">
        <thead>
          <tr>
            <th>Action</th>
            <th>Stage</th>
            <th>Device / Provider</th>
            <th>Mode</th>
            <th>Availability</th>
            <th>Last Run</th>
            <th>Command / Details</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((action) => (
            <tr className={action.action_id === selectedActionId ? "selected-row" : ""} key={`catalog-${action.action_id}`}>
              <td>
                <strong>{action.label}</strong>
                <span>{action.action_id}</span>
              </td>
              <td>{action.stage_label}</td>
              <td>{labelize(action.provider)}</td>
              <td>
                <span className={`classification-tag ${workflowModeClass(action.mode)}`}>
                  {workflowModeLabel(action.mode)}
                </span>
              </td>
              <td>
                <StatusBadge status={action.current_availability} />
                {action.blockers[0] && <p className="control-table-note">{action.blockers[0]}</p>}
              </td>
              <td>
                <StatusBadge status={action.last_run_status} />
                <SourceFreshnessInline
                  freshness={action.last_run_trace.freshness}
                  sourceType={action.last_run_trace.source_type}
                />
                <span className="control-table-note">
                  {action.last_run_trace.finished_at ? formatDateTime(action.last_run_trace.finished_at) : "Not checked"}
                </span>
              </td>
              <td>
                <WorkflowActionHandoff action={action} />
                <div className="action-row">
                  <WorkflowActionRunControl
                    action={action}
                    compact
                    onCopy={onCopy}
                    onRun={onRun}
                    running={runningActionId === action.action_id}
                  />
                  <button
                    className="small-button"
                    onClick={() => onSelect(action.action_id)}
                    type="button"
                  >
                    <Route size={14} />
                    Details
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function FirmwareMinimalOverview({
  compliance,
  components,
  deviceFilter,
  devices,
  focusedSummary,
  packages,
  reports
}: {
  compliance: ProviderProbeResult | null;
  components: Record<string, unknown>[];
  deviceFilter: FirmwareDeviceFilter;
  devices: Record<string, unknown>;
  focusedSummary: FirmwareSummary | null;
  packages: Record<string, unknown>[];
  reports: ReportLink[];
}) {
  const { activeContext, activeProfile } = useLabProfileContext();
  const netappInScope = activeContext?.enabled_features.netapp_enabled ?? activeProfile?.features.netapp_enabled ?? true;
  const rows = [
    firmwareMinimalRow("iLO", devices, components, ["ilo", "hpe"]),
    firmwareMinimalRow("Cisco", devices, components, ["cisco"]),
    ...(netappInScope ? [firmwareMinimalRow("ONTAP", devices, components, ["netapp", "ontap"])] : []),
    firmwareMinimalRow("ESXi", devices, components, ["esxi", "vmware"]),
    firmwareMinimalRow("BIOS", devices, components, ["bios"]),
    firmwareMinimalRow("Smart Array", devices, components, ["smart array", "array"]),
    {
      label: "Packages",
      status: packages.length ? "available" : "missing-config",
      summary: packages.length ? "Available" : "Missing"
    }
  ].filter((row) => deviceFilter === "all" || firmwareRowMatchesDevice(row.label, deviceFilter));
  const focusedIssue = deviceFilter !== "all" && focusedSummary?.blocker ? firmwareReasonText(focusedSummary.blocker) : "";
  const focusedIsBlocking = focusedSummary?.compliance_status === "needs_upgrade";
  const blockers = stringArray(compliance?.blockers);
  const warnings = stringArray(compliance?.warnings);
  const simpleBlockers = focusedIssue && focusedIsBlocking ? [focusedIssue] : blockers.length ? [firmwareSimpleBlocker(blockers[0])] : [];
  const simpleWarnings = focusedIssue && !focusedIsBlocking ? [focusedIssue] : simpleBlockers.length || !warnings.length ? [] : [firmwareSimpleBlocker(warnings[0])];
  const nextAction = focusedSummary && deviceFilter !== "all"
    ? focusedSummary.next_action
    : asString(compliance?.next_safe_action) || "Refresh firmware compliance.";
  return (
    <section className="panel minimal-firmware-panel">
      <div className="minimal-detail-head">
        <div>
          <span className="summary-kicker">Firmware</span>
          <h2>{displayStatusLabel(compliance?.status ?? "not_run")}</h2>
          <p>{asString(compliance?.message) || "Firmware status has not loaded yet."}</p>
        </div>
        <HumanStatusPill status={compliance?.status ?? "not_run"} />
      </div>
      <div className="minimal-netapp-grid">
        {rows.map((row) => (
          <article key={row.label}>
            <span>{row.label}</span>
            <strong>{row.summary}</strong>
            <HumanStatusPill status={row.status} />
          </article>
        ))}
      </div>
      <NextActionCard detail={firmwareSimpleNextAction(nextAction)} />
      <BlockerSummary blockers={simpleBlockers} warnings={simpleWarnings} empty="No firmware blocker is reported." />
      <EvidenceDrawer count={reports.length} title="Firmware Proof">
        <ReportLinkList reports={reports} />
      </EvidenceDrawer>
    </section>
  );
}

function firmwareSimpleBlocker(value: string): string {
  const normalized = value.toLowerCase();
  if (normalized.includes("baseline missing/manual review")) {
    return value.split(";")[0]?.trim() || "Firmware baseline missing/manual review.";
  }
  if (normalized.includes("manual approval") && (normalized.includes("bios") || normalized.includes("smart array"))) {
    return "HPE firmware baseline missing/manual review.";
  }
  if (normalized.includes("ilo") || normalized.includes("hpe")) {
    return "iLO firmware needs a live inventory check.";
  }
  if (normalized.includes("cisco")) {
    return "Cisco firmware needs a live inventory check.";
  }
  if (normalized.includes("netapp") || normalized.includes("ontap")) {
    return "ONTAP version is not configured yet.";
  }
  if (normalized.includes("package") || normalized.includes("media")) {
    return "Required firmware package is missing.";
  }
  return humanizeBlocker(value.split(";")[0] || value);
}

function firmwareSimpleNextAction(value: string): string {
  const normalized = value.toLowerCase();
  if (normalized.includes("manual baseline") || normalized.includes("baseline missing/manual review")) {
    return "Open Firmware Upgrades and record the manual baseline decision.";
  }
  if (normalized.includes("ilo") || normalized.includes("hpe")) {
    return "Check iLO firmware inventory.";
  }
  if (normalized.includes("cisco")) {
    return "Check Cisco firmware inventory.";
  }
  if (normalized.includes("netapp") || normalized.includes("ontap")) {
    return "Configure ONTAP version information.";
  }
  if (normalized.includes("package") || normalized.includes("media")) {
    return "Add the required firmware package.";
  }
  return humanizeAction(value);
}

function firmwareMinimalRow(
  label: string,
  devices: Record<string, unknown>,
  components: Record<string, unknown>[],
  tokens: string[]
): { label: string; status: string; summary: string } {
  const matchingDevice = Object.entries(devices).find(([key]) =>
    tokens.some((token) => key.toLowerCase().includes(token))
  );
  const deviceStatus = asString(objectValue(matchingDevice?.[1]).status);
  const matchingComponent = components.find((component) => {
    const text = `${asString(component.device)} ${asString(component.label)} ${asString(component.id)}`.toLowerCase();
    return tokens.some((token) => text.includes(token));
  });
  const status = deviceStatus || asString(matchingComponent?.status) || "unknown";
  const version = asString(matchingComponent?.current_version);
  return {
    label,
    status,
    summary: version ? `${displayStatusLabel(status)} / ${version}` : displayStatusLabel(status)
  };
}

function firmwareRowMatchesDevice(label: string, deviceFilter: FirmwareDeviceFilter): boolean {
  const normalized = label.toLowerCase();
  if (deviceFilter === "cisco") return normalized.includes("cisco");
  if (deviceFilter === "ilo") return normalized.includes("ilo") || normalized.includes("bios");
  if (deviceFilter === "raid") return normalized.includes("smart array");
  if (deviceFilter === "esxi") return normalized.includes("esxi");
  if (deviceFilter === "netapp") return normalized.includes("ontap") || normalized.includes("netapp");
  if (deviceFilter === "vcenter") return normalized.includes("vcenter");
  return true;
}

function filterFirmwareComponents(
  components: Record<string, unknown>[],
  deviceFilter: FirmwareDeviceFilter
): Record<string, unknown>[] {
  if (deviceFilter === "all") return components;
  return components.filter((component) => {
    const text = `${asString(component.device)} ${asString(component.label)} ${asString(component.id)}`.toLowerCase();
    if (deviceFilter === "cisco") return text.includes("cisco");
    if (deviceFilter === "ilo") return text.includes("ilo") || text.includes("bios");
    if (deviceFilter === "raid") return text.includes("smart array") || text.includes("raid");
    if (deviceFilter === "esxi") return text.includes("esxi") || text.includes("vmware");
    if (deviceFilter === "netapp") return text.includes("netapp") || text.includes("ontap");
    if (deviceFilter === "vcenter") return text.includes("vcenter");
    return true;
  });
}

type FirmwareUpgradeRow = {
  summary: FirmwareSummary;
  path: FirmwareUpgradePath;
  current: string;
  target: string;
  packageItem: MediaInventory["items"][number] | null;
  scanAction: WorkflowAction | null;
  planAction: WorkflowAction | null;
  upgradeAction: WorkflowAction | null;
  relatedAction: WorkflowAction | null;
};

function FirmwareUpgradePanel({
  actionMessage,
  deviceFilter,
  media,
  onRunWorkflowAction,
  reports,
  runningActionId,
  summaries,
  workflowActions
}: {
  actionMessage: string;
  deviceFilter: FirmwareDeviceFilter;
  media: MediaInventory | null;
  onRunWorkflowAction: RunWorkflowActionHandler;
  reports: ReportLink[];
  runningActionId: string;
  summaries: FirmwareSummary[];
  workflowActions: WorkflowAction[];
}) {
  const rows = firmwareUpgradeRows(summaries, media?.items ?? [], workflowActions)
    .filter((row) => firmwareSummaryMatchesDevice(row.summary, deviceFilter));
  const [selectedRowKey, setSelectedRowKey] = useState("");
  const selectedRow = rows.find((row) => firmwareUpgradeRowKey(row) === selectedRowKey) ?? rows[0] ?? null;
  const needsUpgradeCount = rows.filter((row) => ["direct", "staged"].includes(row.path.path_status)).length;
  const cannotVerifyCount = rows.filter((row) => ["manual_review", "unknown"].includes(row.path.path_status)).length;
  const availablePackageCount = rows.filter((row) => row.path.package_available || row.packageItem).length;

  return (
    <section className="panel firmware-upgrade-panel">
      <div className="firmware-upgrade-head">
        <div>
          <span className="summary-kicker">Upgrade</span>
          <h2>Firmware Upgrade Queue</h2>
          <p>Current version, required version, available package, and the next action are shown in one row.</p>
        </div>
        <div className="firmware-upgrade-counts">
          <div><span>Devices</span><strong>{rows.length}</strong></div>
          <div><span>Packages</span><strong>{availablePackageCount}</strong></div>
          <div><span>Needs Upgrade</span><strong>{needsUpgradeCount}</strong></div>
          <div><span>Review</span><strong>{cannotVerifyCount}</strong></div>
        </div>
      </div>
      {actionMessage && (
        <div className="firmware-run-note">
          <CheckCircle2 size={16} />
          <span>{actionMessage}</span>
        </div>
      )}
      {rows.length ? (
        <div className="firmware-upgrade-table-wrap">
          <table className="firmware-upgrade-table">
            <thead>
              <tr>
                <th>Device</th>
                <th>Component</th>
                <th>Current</th>
                <th>Target</th>
                <th>Path</th>
                <th>Package</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <FirmwareUpgradeRowView
                  key={firmwareUpgradeRowKey(row)}
                  onRunWorkflowAction={onRunWorkflowAction}
                  row={row}
                  runningActionId={runningActionId}
                  selected={selectedRow ? firmwareUpgradeRowKey(row) === firmwareUpgradeRowKey(selectedRow) : false}
                  setSelected={() => setSelectedRowKey(firmwareUpgradeRowKey(row))}
                />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState title="No firmware rows" detail="No firmware summaries match the selected device." />
      )}
      <div className="firmware-upgrade-footer">
        <span>{reports.length} evidence item{reports.length === 1 ? "" : "s"} available.</span>
        <span>Upgrade actions open a guarded confirmation when a runner exists; unsupported rows stay disabled.</span>
      </div>
      {selectedRow && <FirmwareUpgradePathDetail row={selectedRow} />}
    </section>
  );
}

function FirmwareUpgradeRowView({
  onRunWorkflowAction,
  row,
  runningActionId,
  selected,
  setSelected
}: {
  onRunWorkflowAction: RunWorkflowActionHandler;
  row: FirmwareUpgradeRow;
  runningActionId: string;
  selected: boolean;
  setSelected: () => void;
}) {
  const scanRunning = Boolean(row.scanAction && runningActionId === row.scanAction.action_id);
  const planRunning = Boolean(row.planAction && runningActionId === row.planAction.action_id);
  const upgradeRunning = Boolean(row.upgradeAction && runningActionId === row.upgradeAction.action_id);
  const relatedRunning = Boolean(row.relatedAction && runningActionId === row.relatedAction.action_id);
  const canRunScan = Boolean(row.scanAction && workflowActionCanRun(row.scanAction));
  const canRunPlan = Boolean(row.planAction && workflowActionCanRun(row.planAction));
  const canStartGuardedUpgrade = Boolean(row.upgradeAction && workflowActionCanStartGuarded(row.upgradeAction));
  const canRunUpgrade = Boolean(
    row.upgradeAction && workflowActionCanRun(row.upgradeAction) && !workflowActionRequiresGuard(row.upgradeAction)
  );
  const canStartRelatedAction = Boolean(row.relatedAction && workflowActionCanStartGuarded(row.relatedAction));
  const scanDisabledReason = firmwareActionDisabledReason(row.scanAction, "No safe scan action is registered.");
  const planDisabledReason = firmwareActionDisabledReason(row.planAction, "No upgrade plan action is registered.");
  const upgradeDisabledReason = firmwareUpgradeDisabledReason(row.upgradeAction);
  const showGuardedUpgrade = Boolean(
    row.upgradeAction && workflowActionRequiresGuard(row.upgradeAction) && (canStartGuardedUpgrade || !row.relatedAction)
  );

  const tone = firmwarePathTone(row.path.path_status);

  return (
    <tr
      className={`firmware-upgrade-row ${tone} ${selected ? "selected" : ""}`}
      onClick={setSelected}
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") setSelected();
      }}
    >
      <td>
        <strong>{row.path.device_label}</strong>
        <span>{labelize(row.path.equipment_type)}</span>
      </td>
      <td>
        <strong>{row.path.component_label}</strong>
        <span>{labelize(row.path.equipment_type)}</span>
      </td>
      <td>{row.current}</td>
      <td>{row.target}</td>
      <td>
        <StatusBadge status={row.path.path_status} />
        <p>{firmwarePathStatusLabel(row.path.path_status)}</p>
        {row.path.required_intermediate_versions.length > 0 && (
          <p>via {row.path.required_intermediate_versions.join(", ")}</p>
        )}
      </td>
      <td>
        {row.path.package_available || row.packageItem ? (
          <div className="firmware-package-cell">
            <strong>{row.path.package_name || mediaInventoryItemName(row.packageItem)}</strong>
            <span>
              {row.path.package_version || row.packageItem?.version_hint
                ? `Version ${row.path.package_version || row.packageItem?.version_hint}`
                : labelize(row.packageItem?.category || "package")}
            </span>
          </div>
        ) : (
          <span className="muted">No matching package detected</span>
        )}
      </td>
      <td>
        <div className="firmware-upgrade-actions">
          <button
            className="small-button"
            disabled={!canRunScan || scanRunning}
            onClick={(event) => {
              event.stopPropagation();
              if (row.scanAction && canRunScan) onRunWorkflowAction(row.scanAction);
            }}
            title={canRunScan ? "Run the safe firmware inventory action." : scanDisabledReason}
            type="button"
          >
            {scanRunning ? <RefreshCw className="spin-icon" size={14} /> : <ShieldCheck size={14} />}
            {scanRunning ? "Scanning" : "Scan"}
          </button>
          <button
            className="small-button primary"
            disabled={!canRunPlan || planRunning}
            onClick={(event) => {
              event.stopPropagation();
              if (row.planAction && canRunPlan) onRunWorkflowAction(row.planAction);
            }}
            title={canRunPlan ? "Build or refresh the firmware upgrade plan." : planDisabledReason}
            type="button"
          >
            {planRunning ? <RefreshCw className="spin-icon" size={14} /> : <ClipboardList size={14} />}
            {planRunning ? "Planning" : "Plan Upgrade"}
          </button>
          {showGuardedUpgrade && row.upgradeAction ? (
            <GuardedWorkflowActionButton
              action={row.upgradeAction}
              compact
              label="Upgrade"
              onRun={onRunWorkflowAction}
              running={upgradeRunning}
            />
          ) : !row.relatedAction ? (
            <button
              className="small-button firmware-upgrade-apply-button"
              disabled={!canRunUpgrade || upgradeRunning}
              onClick={(event) => {
                event.stopPropagation();
                if (row.upgradeAction && canRunUpgrade) onRunWorkflowAction(row.upgradeAction);
              }}
              title={canRunUpgrade ? "Start the approved firmware upgrade action." : upgradeDisabledReason}
              type="button"
            >
              {upgradeRunning ? <RefreshCw className="spin-icon" size={14} /> : <Play size={14} />}
              {upgradeRunning ? "Upgrading" : "Upgrade"}
            </button>
          ) : null}
          {row.relatedAction && (
            <GuardedWorkflowActionButton
              action={row.relatedAction}
              compact
              label={firmwareRelatedActionLabel(row.relatedAction)}
              onRun={onRunWorkflowAction}
              running={relatedRunning}
            />
          )}
        </div>
        <p className="firmware-action-reason">{row.path.next_action}</p>
        {!canRunUpgrade && !canStartGuardedUpgrade && !row.relatedAction && <p className="firmware-action-reason">{row.path.disabled_reason || upgradeDisabledReason}</p>}
        {row.relatedAction && !canStartRelatedAction && <p className="firmware-action-reason">{workflowGuardedDisabledReason(row.relatedAction)}</p>}
      </td>
    </tr>
  );
}

function FirmwareUpgradePathDetail({ row }: { row: FirmwareUpgradeRow }) {
  const path = row.path;
  return (
    <section className="firmware-path-detail" aria-label="Firmware upgrade path detail">
      <div className="validation-detail-head">
        <div>
          <span className="summary-kicker">Selected Path</span>
          <h3>{path.device_label} / {path.component_label}</h3>
          <p>{path.next_action}</p>
        </div>
        <StatusBadge status={path.path_status} />
      </div>
      <div className="detail-grid">
        <Info label="Current" value={path.current_version || "Scan needed"} />
        <Info label="Target" value={path.target_version || "Manual review"} />
        <Info label="Path" value={firmwarePathStatusLabel(path.path_status)} />
        <Info label="Package" value={path.package_name || (path.package_available ? "Available" : "Not available")} />
        <Info label="Reboot / Impact" value={`${path.reboot_required ? "Reboot required" : "No reboot marked"}; ${path.estimated_impact}`} />
        <Info label="Apply" value={path.apply_enabled ? "Enabled" : `Disabled: ${path.disabled_reason}`} />
      </div>
      <div className="firmware-path-detail-grid">
        <div>
          <strong>Prechecks</strong>
          <ul>
            {(path.prechecks_required.length ? path.prechecks_required : ["No precheck metadata available."]).map((item) => (
              <li key={`${path.component_id}-precheck-${item}`}>{item}</li>
            ))}
          </ul>
        </div>
        <div>
          <strong>Missing Evidence</strong>
          <ul>
            {(path.missing_evidence.length ? path.missing_evidence : ["No missing evidence is reported."]).map((item) => (
              <li key={`${path.component_id}-missing-${item}`}>{item}</li>
            ))}
          </ul>
        </div>
        <div>
          <strong>Package Details</strong>
          <ul>
            <li>{path.package_name || "No matching package detected."}</li>
            <li>{path.package_version ? `Version ${path.package_version}` : "Package version unavailable."}</li>
            <li>{path.baseline_source || "Baseline source unavailable."}</li>
          </ul>
        </div>
      </div>
      <AdvancedDetails
        className="firmware-summary-evidence"
        summary={`${path.evidence_artifacts.length} evidence link${path.evidence_artifacts.length === 1 ? "" : "s"}`}
        title="Path Evidence"
      >
        <EvidenceList artifacts={path.evidence_artifacts} empty="No firmware evidence links are available yet." />
      </AdvancedDetails>
    </section>
  );
}

function firmwareUpgradeRowKey(row: FirmwareUpgradeRow): string {
  return `${row.summary.device_id}-${row.path.component_id}`;
}

function firmwarePathTone(status: string): string {
  if (status === "blocked") return "blocked";
  if (status === "manual_review" || status === "unknown" || status === "direct" || status === "staged") return "warning";
  return "ready";
}

function FirmwareEvidencePanel({
  compliance,
  components,
  firmwareActions,
  inventory,
  media,
  reports,
  waiver
}: {
  compliance: ProviderProbeResult | null;
  components: Record<string, unknown>[];
  firmwareActions: ControlAction[];
  inventory: ProviderProbeResult | null;
  media: MediaInventory | null;
  reports: ReportLink[];
  waiver: ProviderProbeResult | null;
}) {
  const upgradePaths = recordArray(compliance?.upgrade_paths);
  return (
    <section className="panel firmware-evidence-panel">
      <StatusSummaryCard
        message={asString(compliance?.message) || "Firmware evidence has not loaded yet."}
        status={compliance?.status ?? "not_run"}
        title="Evidence"
        items={[
          { label: "Components", value: String(components.length) },
          { label: "Packages", value: String(media?.items.length ?? 0) },
          { label: "Reports", value: String(reports.length) },
          { label: "Waiver", value: displayStatusLabel(waiver?.status ?? "not_run") }
        ]}
      />
      <BlockerSummary blockers={stringArray(compliance?.blockers)} warnings={stringArray(compliance?.warnings)} />
      <AdvancedDetails className="section-details" summary="Normalized upgrade path rows" title="Upgrade Path Model">
        {upgradePaths.length ? (
          <table className="provider-candidate-table">
            <thead>
              <tr>
                <th>Device</th>
                <th>Component</th>
                <th>Current</th>
                <th>Target</th>
                <th>Path</th>
                <th>Package</th>
              </tr>
            </thead>
            <tbody>
              {upgradePaths.map((path, index) => (
                <tr key={`${asString(path.component_id) || index}`}>
                  <td>{asString(path.device_label) || "-"}</td>
                  <td>{asString(path.component_label) || asString(path.component_id) || "-"}</td>
                  <td>{asString(path.current_version) || "Unknown"}</td>
                  <td>{asString(path.target_version) || "Manual review"}</td>
                  <td><StatusBadge status={asString(path.path_status) || "unknown"} /></td>
                  <td>{asString(path.package_name) || (asBoolean(path.package_available) ? "Available" : "Not available")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState title="No upgrade path model" detail="Firmware compliance did not include normalized path rows." />
        )}
      </AdvancedDetails>
      <AdvancedDetails className="section-details" summary="Component versions" title="Current and required versions">
        {components.length ? (
          <table className="provider-candidate-table">
            <thead>
              <tr>
                <th>Device</th>
                <th>Component</th>
                <th>Status</th>
                <th>Current</th>
                <th>Required</th>
              </tr>
            </thead>
            <tbody>
              {components.map((item, index) => (
                <tr key={`${asString(item.id) || index}`}>
                  <td>{asString(item.device) || "-"}</td>
                  <td>{asString(item.label) || asString(item.id) || "-"}</td>
                  <td><StatusBadge status={asString(item.status) || "unknown"} /></td>
                  <td>{asString(item.current_version) || "Unknown"}</td>
                  <td>{asString(item.required_version) || stringArray(item.approved_versions).join(", ") || "Manual review"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState title="No component evidence" detail="Compliance evidence did not include per-component rows." />
        )}
      </AdvancedDetails>
      <AdvancedDetails className="section-details" summary="Available media metadata" title="Firmware packages">
        {media ? <MediaInventoryCompact inventory={media} /> : <EmptyState title="No media inventory" detail="Media metadata has not loaded." />}
      </AdvancedDetails>
      <AdvancedDetails className="section-details" summary="Reports and action catalog" title="Reports">
        <ReportLinkList reports={reports} />
        <ActionCatalogReadonly actions={firmwareActions} />
      </AdvancedDetails>
      <AdvancedDetails className="section-details" summary="Inventory and waiver payloads" title="Raw evidence">
        <JsonDetails title="Firmware inventory" data={inventory ?? {}} />
        <JsonDetails title="Waiver status" data={waiver ?? {}} />
      </AdvancedDetails>
    </section>
  );
}

function firmwareUpgradeRows(
  summaries: FirmwareSummary[],
  mediaItems: MediaInventory["items"],
  workflowActions: WorkflowAction[]
): FirmwareUpgradeRow[] {
  return summaries.flatMap((summary) => {
    const paths = summary.upgrade_paths?.length ? summary.upgrade_paths : [legacyFirmwarePathForSummary(summary)];
    return paths.map((path) => ({
      summary,
      path,
      current: path.current_version || "Unknown",
      target: path.target_version || "Manual review",
      packageItem: firmwarePackageForPath(path, summary, mediaItems),
      scanAction: (path.scan_action_id || summary.scan_action_id)
        ? workflowActions.find((action) => action.action_id === (path.scan_action_id || summary.scan_action_id)) ?? null
        : null,
      planAction: firmwarePlanActionForSummary(summary, workflowActions),
      upgradeAction: ["direct", "staged"].includes(path.path_status) ? firmwareApplyActionForSummary(summary, workflowActions) : null,
      relatedAction: path.apply_enabled ? firmwareRelatedActionForSummary(summary, workflowActions) : null
    }));
  });
}

function legacyFirmwarePathForSummary(summary: FirmwareSummary): FirmwareUpgradePath {
  return {
    component_id: summary.device_id,
    component_label: summary.label,
    device_label: summary.label,
    equipment_type: summary.component_type,
    current_version: firmwareVersionList(summary.current_versions, "Unknown"),
    target_version: firmwareBaselineList(summary.approved_versions),
    baseline_source: null,
    package_available: summary.package_available,
    package_name: summary.package_name,
    package_version: null,
    path_status: summary.path_status || summary.compliance_status,
    required_intermediate_versions: summary.required_intermediate_versions ?? [],
    prechecks_required: summary.prechecks_required ?? [],
    reboot_required: summary.reboot_required ?? false,
    estimated_impact: summary.estimated_impact || "Unknown until firmware/software path is classified.",
    apply_enabled: summary.apply_enabled ?? false,
    disabled_reason: summary.disabled_reason || summary.blocker || "No upgrade path details are available.",
    next_action: summary.next_action,
    evidence_artifacts: summary.evidence_artifacts,
    missing_evidence: [],
    scan_action_id: summary.scan_action_id,
    last_checked: summary.last_scanned,
    source_type: summary.source_type,
    freshness: summary.freshness
  };
}

function firmwareSummaryMatchesDevice(summary: FirmwareSummary, deviceFilter: FirmwareDeviceFilter): boolean {
  if (deviceFilter === "all") return true;
  if (deviceFilter === "ilo") return summary.device_id === "ilo" || summary.device_id === "raid";
  return summary.device_id === deviceFilter;
}

function firmwarePlanActionForSummary(summary: FirmwareSummary, actions: WorkflowAction[]): WorkflowAction | null {
  const preferred = summary.device_id === "netapp" ? "netapp.ontap-upgrade-plan" : "firmware.upgrade-plan";
  return actions.find((action) => action.action_id === preferred) ?? null;
}

function firmwareApplyActionForSummary(summary: FirmwareSummary, actions: WorkflowAction[]): WorkflowAction | null {
  const preferred = summary.device_id === "netapp" ? "netapp.ontap-upgrade-apply" : "firmware.upgrade-apply-placeholder";
  return actions.find((action) => action.action_id === preferred) ?? null;
}

function firmwareRelatedActionForSummary(summary: FirmwareSummary, actions: WorkflowAction[]): WorkflowAction | null {
  const relatedByDevice: Record<string, string> = {
    cisco: "cisco.apply-bootstrap",
    esxi: "esxi.rebuild-install",
    ilo: "ilo.virtual-media-insert",
    netapp: "netapp.setup-apply",
    raid: "raid.apply"
  };
  const actionId = relatedByDevice[summary.device_id];
  if (!actionId) return null;
  return actions.find((action) => action.action_id === actionId) ?? null;
}

const firmwareGuardedControlActionIds = [
  "cisco.apply-bootstrap",
  "ilo.virtual-media-insert",
  "raid.apply",
  "esxi.rebuild-install",
  "netapp.setup-apply",
  "netapp.ontap-upgrade-apply"
];

function firmwareGuardedControls(actions: WorkflowAction[]): WorkflowAction[] {
  const byId = new Map(actions.map((action) => [action.action_id, action]));
  return firmwareGuardedControlActionIds
    .map((actionId) => byId.get(actionId) ?? null)
    .filter((action): action is WorkflowAction => Boolean(action));
}

function firmwareRelatedActionLabel(action: WorkflowAction): string {
  const labels: Record<string, string> = {
    "cisco.apply-bootstrap": "Configure",
    "esxi.rebuild-install": "Rebuild",
    "ilo.virtual-media-insert": "Insert Media",
    "netapp.ontap-upgrade-apply": "Upgrade",
    "netapp.setup-apply": "Apply Setup",
    "raid.apply": "Apply RAID"
  };
  return labels[action.action_id] ?? guardedWorkflowRunButtonLabel(action);
}

function firmwareRelatedActionTitle(action: WorkflowAction): string {
  const labels: Record<string, string> = {
    "cisco.apply-bootstrap": "Cisco Configure",
    "esxi.rebuild-install": "ESXi Rebuild",
    "ilo.virtual-media-insert": "iLO Virtual Media",
    "netapp.ontap-upgrade-apply": "NetApp ONTAP Upgrade",
    "netapp.setup-apply": "NetApp Setup",
    "raid.apply": "RAID Apply"
  };
  return labels[action.action_id] ?? humanWorkflowActionLabel(action);
}

function firmwarePackageForSummary(
  summary: FirmwareSummary,
  mediaItems: MediaInventory["items"]
): MediaInventory["items"][number] | null {
  const tokensByDevice: Record<string, string[]> = {
    cisco: ["cisco", "ios", "ios-xe", "rommon"],
    esxi: ["esxi", "vmware"],
    ilo: ["ilo", "hpe", "spp", "fwpkg"],
    netapp: ["netapp", "ontap"],
    raid: ["raid", "smart array", "hpe", "spp"],
    vcenter: ["vcenter", "vcsa", "vmware"]
  };
  const tokens = tokensByDevice[summary.device_id] ?? [summary.device_id];
  const scored = mediaItems
    .map((item) => ({
      item,
      score: firmwarePackageScore(item, tokens)
    }))
    .filter(({ score }) => score > 0)
    .sort((left, right) => right.score - left.score);
  return scored[0]?.item ?? null;
}

function firmwarePackageForPath(
  path: FirmwareUpgradePath,
  summary: FirmwareSummary,
  mediaItems: MediaInventory["items"]
): MediaInventory["items"][number] | null {
  if (path.package_name) {
    const matched = mediaItems.find((item) => item.placeholder_name === path.package_name || item.file_name === path.package_name);
    if (matched) return matched;
  }
  if (path.package_available) return firmwarePackageForSummary(summary, mediaItems);
  return path.component_id === summary.device_id ? firmwarePackageForSummary(summary, mediaItems) : null;
}

function firmwarePackageScore(item: MediaInventory["items"][number], tokens: string[]): number {
  const text = [
    item.placeholder_name,
    item.file_name,
    item.category,
    item.extension,
    item.version_hint,
    ...item.product_hints,
    ...item.generation_hints
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  let score = item.category === "firmware" ? 2 : 0;
  for (const token of tokens) {
    if (text.includes(token.toLowerCase())) score += 2;
  }
  if (item.version_hint) score += 1;
  return score;
}

function firmwareActionDisabledReason(action: WorkflowAction | null, fallback: string): string {
  if (!action) return fallback;
  const reason = action.ui_run_blockers[0] || action.blockers[0] || action.next_action;
  return reason ? firmwareReasonText(reason) : "Action is not available from this page.";
}

function firmwareUpgradeDisabledReason(action: WorkflowAction | null): string {
  if (!action) return "No upgrade action is registered.";
  if (workflowActionRequiresGuard(action)) {
    return workflowActionCanStartGuarded(action) ? "Guarded confirmation required." : workflowGuardedDisabledReason(action);
  }
  if (!workflowActionCanRun(action)) return firmwareActionDisabledReason(action, "Upgrade action is not available.");
  return "";
}

function FirmwarePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [activeSection, setActiveSection] = useState<FirmwareSectionId>("upgrade");
  const [deviceFilter, setDeviceFilter] = useState<FirmwareDeviceFilter>("all");
  const [inventory, setInventory] = useState<ProviderProbeResult | null>(null);
  const [compliance, setCompliance] = useState<ProviderProbeResult | null>(null);
  const [waiver, setWaiver] = useState<ProviderProbeResult | null>(null);
  const [catalog, setCatalog] = useState<ControlActionCatalog | null>(null);
  const [media, setMedia] = useState<MediaInventory | null>(null);
  const [firmwareSummaries, setFirmwareSummaries] = useState<FirmwareSummary[]>([]);
  const [workflowActions, setWorkflowActions] = useState<WorkflowAction[]>([]);
  const [runningActionId, setRunningActionId] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setError("");
    setLoading(true);
    try {
      const [nextInventory, nextCompliance, nextWaiver, nextCatalog, nextSummaries, nextMedia, nextWorkflowActions] = await Promise.all([
        api.firmwareInventory(),
        api.firmwareCompliance(),
        api.firmwareWaiverCheck(),
        api.controlActions(),
        api.firmwareSummary(),
        api.mediaInventory(),
        api.workflowActions()
      ]);
      setInventory(nextInventory);
      setCompliance(nextCompliance);
      setWaiver(nextWaiver);
      setCatalog(nextCatalog);
      setFirmwareSummaries(nextSummaries);
      setMedia(nextMedia);
      setWorkflowActions(nextWorkflowActions);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function runWorkflowAction(action: WorkflowAction, request?: WorkflowActionRunRequest) {
    setError("");
    setActionMessage("");
    setRunningActionId(action.action_id);
    try {
      const result = await api.runWorkflowAction(action.action_id, request);
      const resultSummary = result.summary || result.next_action || displayStatusLabel(result.status);
      setActionMessage(`${humanWorkflowActionLabel(action)}: ${resultSummary}`);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunningActionId("");
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    const requestedDevice = new URLSearchParams(location.search).get("device");
    const allowed: FirmwareDeviceFilter[] = ["all", "cisco", "ilo", "raid", "esxi", "netapp", "vcenter"];
    setDeviceFilter(allowed.includes(requestedDevice as FirmwareDeviceFilter) ? requestedDevice as FirmwareDeviceFilter : "all");
  }, [location.search]);

  const components = recordArray(compliance?.components);
  const filteredComponents = filterFirmwareComponents(components, deviceFilter);
  const firmwareSection = catalog?.sections.find((section) => section.id === "firmware-upgrade") ?? null;
  const firmwareActions = catalog?.actions.filter((action) => action.section_id === "firmware-upgrade") ?? [];
  const focusedSummary = firmwareSummaries.find((summary) => summary.device_id === deviceFilter) ?? null;
  const reports = [
    ...reportLinksFromProbe("Inventory", inventory),
    ...reportLinksFromProbe("Compliance", compliance),
    ...reportLinksFromProbe("Waiver", waiver),
    ...reportLinksFromActions(firmwareActions)
  ];
  const sections: SectionOption<FirmwareSectionId>[] = [
    { id: "upgrade", label: "Upgrade", status: compliance?.status ?? "not_run" },
    { id: "evidence", label: "Evidence", status: reports.length ? "report_available" : firmwareSection?.status ?? "not_run" }
  ];

  return (
    <Page
      activeSection={activeSection}
      description="Current version, target version, package availability, and guarded upgrade controls for lab firmware."
      issueArea="firmware"
      onSectionChange={(sectionId) => setActiveSection(sectionId as FirmwareSectionId)}
      primaryAction={{ icon: <RefreshCw size={16} />, label: "Refresh", onClick: load, disabled: loading }}
      sections={sections}
      title="Firmware Upgrades"
    >
      <Feedback loading={loading && !compliance} error={error} />
      <section className="firmware-focus-strip" aria-label="Firmware device focus">
        <Field label="Focused device">
          <select
            onChange={(event) => {
              const value = event.target.value as FirmwareDeviceFilter;
              setDeviceFilter(value);
              navigate(value === "all" ? "/firmware" : `/firmware?device=${encodeURIComponent(value)}`, { replace: true });
            }}
            value={deviceFilter}
          >
            <option value="all">All devices</option>
            <option value="cisco">Cisco</option>
            <option value="ilo">iLO / HPE</option>
            <option value="raid">RAID / Smart Array</option>
            <option value="esxi">ESXi</option>
            <option value="netapp">NetApp</option>
            <option value="vcenter">vCenter</option>
          </select>
        </Field>
        <div>
          <span className="summary-kicker">Focus status</span>
          <strong>{focusedSummary ? firmwareComplianceLabel(focusedSummary.compliance_status) : "All firmware"}</strong>
          <p>{focusedSummary ? firmwareSummaryLine(focusedSummary) : "Showing every firmware row with current, target, package, and action controls."}</p>
        </div>
        {focusedSummary && <StatusBadge status={focusedSummary.compliance_status} />}
      </section>
      {activeSection === "upgrade" && (
        <FirmwareUpgradePanel
          actionMessage={actionMessage}
          deviceFilter={deviceFilter}
          media={media}
          onRunWorkflowAction={runWorkflowAction}
          reports={reports}
          runningActionId={runningActionId}
          summaries={firmwareSummaries}
          workflowActions={workflowActions}
        />
      )}
      {activeSection === "evidence" && (
        <FirmwareEvidencePanel
          compliance={compliance}
          components={filteredComponents}
          firmwareActions={firmwareActions}
          inventory={inventory}
          media={media}
          reports={reports}
          waiver={waiver}
        />
      )}
    </Page>
  );
}

function BuildVerificationPage() {
  const [activeSection, setActiveSection] = useState<VerificationSectionId>("summary");
  const [verification, setVerification] = useState<ProviderProbeResult | null>(null);
  const [summary, setSummary] = useState<ProviderProbeResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setError("");
    setLoading(true);
    try {
      const [nextVerification, nextSummary] = await Promise.all([
        api.buildVerification(),
        api.fullRebuildSummary()
      ]);
      setVerification(nextVerification);
      setSummary(nextSummary);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const artifacts = objectValue(verification?.artifacts);
  const labProfile = objectValue(verification?.lab_ip_profile);
  const expectedProfile = objectValue(labProfile.expected);
  const credentials = objectValue(verification?.credentials);
  const credentialChecks = recordArray(credentials.checks);
  const mtu = objectValue(verification?.mtu);
  const protocols = objectValue(verification?.protocols);
  const protocolChecks = recordArray(protocols.checks);
  const failures = recordArray(verification?.failures);
  const storageStage = objectValue(objectValue(summary?.stages).raid || objectValue(summary?.stages).storage);
  const firmwareStrategy = objectValue(verification?.firmware_strategy);
  const sections: SectionOption<VerificationSectionId>[] = [
    { id: "summary", label: "Summary", status: verification?.status ?? "not_run" },
    { id: "network", label: "Network", status: asString(labProfile.status) || "not_run" },
    { id: "storage", label: "Storage", status: asString(storageStage.status) || "not_run" },
    { id: "firmware", label: "Firmware", status: asString(firmwareStrategy.status) || "not_run" },
    { id: "credentials", label: "Credentials", status: asString(credentials.status) || asString(credentials.classification) || "not_run" },
    { id: "mtu-protocols", label: "MTU / Protocols", status: asString(protocols.status) || asString(mtu.status) || "not_run" },
    { id: "certification-report", label: "Certification Report", status: asString(verification?.certification_state) || verification?.status || "not_run" }
  ];

  return (
    <Page
      activeSection={activeSection}
      description="Build verification is split into product certification sections with diagnostics collapsed."
      issueArea="verification"
      onSectionChange={(sectionId) => setActiveSection(sectionId as VerificationSectionId)}
      primaryAction={{ icon: <RefreshCw size={16} />, label: "Refresh", onClick: load, disabled: loading }}
      sections={sections}
      title="Build Verification"
    >
      <Feedback loading={loading && !verification} error={error} />
      {activeSection === "summary" && (
        <div className="calm-section-grid">
          <StatusSummaryCard
            message={asString(verification?.message) || "Build verification has not loaded yet."}
            status={verification?.status ?? "not_run"}
            title={labelize(asString(verification?.certification_state) || verification?.status || "Not run")}
            items={[
              { label: "Failures", value: String(failures.length) },
              { label: "Blockers", value: String(stringArray(verification?.blockers).length) },
              { label: "Warnings", value: String(stringArray(verification?.warnings).length) },
              { label: "Checked", value: verification?.checked_at ? formatDateTime(verification.checked_at) : "Not run" }
            ]}
          />
          <NextActionCard detail={humanizeAction(asString(verification?.next_safe_action) || "Resolve blockers, then regenerate verification.")} />
          <BlockerSummary blockers={stringArray(verification?.blockers)} warnings={stringArray(verification?.warnings)} />
        </div>
      )}
      {activeSection === "network" && (
        <section className="panel">
          <StatusSummaryCard
            message="Expected lab addressing is shown without repeating provider diagnostics."
            status={asString(labProfile.status) || "not_run"}
            title="Network profile"
            items={[
              { label: "Subnet", value: asString(expectedProfile.subnet) || "Not loaded" },
              { label: "iLO", value: displayAddress(asString(expectedProfile.ilo)) },
              { label: "ESXi", value: displayAddress(asString(expectedProfile.esxi_management)) },
              { label: "Cisco", value: displayAddress(asString(expectedProfile.cisco_management)) }
            ]}
          />
          <AdvancedDetails className="section-details" summary="Expected profile and historical evidence" title="Network details">
            <JsonDetails title="Lab IP profile" data={labProfile} />
          </AdvancedDetails>
        </section>
      )}
      {activeSection === "storage" && (
        <VerificationSimpleSection
          details={storageStage}
          status={asString(storageStage.status) || "not_run"}
          title="Storage verification"
        />
      )}
      {activeSection === "firmware" && (
        <VerificationSimpleSection
          details={firmwareStrategy}
          status={asString(firmwareStrategy.status) || "not_run"}
          title="Firmware verification"
        />
      )}
      {activeSection === "credentials" && (
        <section className="panel">
          <StatusSummaryCard
            message={asString(credentials.summary) || "Credential compatibility is reported as status metadata only."}
            status={asString(credentials.status) || asString(credentials.classification) || "not_run"}
            title="Credentials status"
            items={[
              { label: "Checks", value: String(credentialChecks.length) },
              { label: "Classification", value: labelize(asString(credentials.classification) || "unknown") }
            ]}
          />
          <AdvancedDetails className="section-details" summary="Credential status rows without secret values" title="Credential checks">
            {credentialChecks.length ? <KeyValueTable rows={credentialChecks} labelKey="field" valueKey="classification" empty="No credential checks." /> : <EmptyState title="No credential checks" detail="Verification did not include credential compatibility rows." />}
          </AdvancedDetails>
        </section>
      )}
      {activeSection === "mtu-protocols" && (
        <section className="panel">
          <StatusSummaryCard
            message={asString(protocols.summary) || asString(mtu.summary) || "MTU and protocol checks are grouped here."}
            status={asString(protocols.status) || asString(mtu.status) || "not_run"}
            title="MTU / protocols"
            items={[
              { label: "Protocol Checks", value: String(protocolChecks.length) },
              { label: "MTU Invalid", value: String(Object.keys(objectValue(mtu.invalid)).length) },
              { label: "MTU Mismatch", value: String(Array.isArray(mtu.mismatches) ? mtu.mismatches.length : 0) }
            ]}
          />
          <AdvancedDetails className="section-details" summary="MTU mismatches and protocol readiness rows" title="MTU and protocol details">
            {protocolChecks.length ? <KeyValueTable rows={protocolChecks} labelKey="protocol" valueKey="classification" empty="No protocol checks." /> : <EmptyState title="No protocol checks" detail="Verification did not include protocol rows." />}
            <JsonDetails title="MTU details" data={mtu} />
          </AdvancedDetails>
        </section>
      )}
      {activeSection === "certification-report" && (
        <section className="panel">
          <StatusSummaryCard
            message="Report links and raw certification evidence stay collapsed unless needed."
            status={asString(verification?.certification_state) || verification?.status || "not_run"}
            title="Certification report"
            items={[
              { label: "Report", value: asString(artifacts.report) || "Not generated" },
              { label: "Final", value: asString(artifacts.final) || "Not generated" }
            ]}
          />
          <ReportLinkList reports={reportLinksFromProbe("Verification", verification)} />
          <AdvancedDetails className="section-details" summary="Raw redacted build verification payload" title="Raw verification evidence">
            <JsonDetails title="Build verification" data={verification ?? {}} />
          </AdvancedDetails>
        </section>
      )}
    </Page>
  );
}

function VerificationSimpleSection({
  details,
  status,
  title
}: {
  details: Record<string, unknown>;
  status: string;
  title: string;
}) {
  return (
    <section className="panel">
      <StatusSummaryCard
        message={asString(details.message) || asString(details.summary) || `${title} has not reported detailed status yet.`}
        status={status}
        title={title}
        items={[
          { label: "Blockers", value: String(stringArray(details.blockers).length) },
          { label: "Warnings", value: String(stringArray(details.warnings).length) },
          { label: "Next", value: humanizeAction(asString(details.next_action) || "Review this section.") }
        ]}
      />
      <BlockerSummary blockers={stringArray(details.blockers)} warnings={stringArray(details.warnings)} />
      <AdvancedDetails className="section-details" summary="Section evidence" title={`${title} details`}>
        <JsonDetails title={title} data={details} />
      </AdvancedDetails>
    </section>
  );
}

function GoldenStatePage() {
  const [activeSection, setActiveSection] = useState<GoldenStateSectionId>("dashboard");
  const [goldenState, setGoldenState] = useState<ProviderProbeResult | null>(null);
  const [workflowActionCatalog, setWorkflowActionCatalog] = useState<WorkflowAction[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [runningAction, setRunningAction] = useState("");
  const [runMessage, setRunMessage] = useState("");

  async function load() {
    setError("");
    setLoading(true);
    try {
      const [nextGoldenState, nextWorkflowActions] = await Promise.all([
        api.goldenState(),
        api.workflowActions()
      ]);
      setGoldenState(nextGoldenState);
      setWorkflowActionCatalog(nextWorkflowActions);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function runGoldenAction(actionId: string, request?: WorkflowActionRunRequest) {
    setError("");
    setRunMessage("");
    setRunningAction(actionId);
    try {
      const result = await api.runWorkflowAction(actionId, request);
      setRunMessage(`${result.action_label}: ${displayStatusLabel(result.status)}`);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunningAction("");
    }
  }

  useEffect(() => {
    load();
  }, []);

  const rows = recordArray(goldenState?.rows);
  const driftRows = recordArray(goldenState?.drift_rows);
  const credentials = objectValue(goldenState?.credentials);
  const credentialRows = recordArray(credentials.rows);
  const vcenter = objectValue(goldenState?.vcenter_readiness);
  const workflowActions = recordArray(goldenState?.workflow_actions);
  const sections: SectionOption<GoldenStateSectionId>[] = [
    { id: "dashboard", label: "Dashboard", status: goldenState?.status ?? "not_checked" },
    { id: "drift", label: "Drift", status: driftRows.length ? "warning" : "ready" },
    { id: "credentials", label: "Credentials", status: asString(credentials.status) || "not_checked" },
    { id: "vcenter", label: "vCenter", status: asString(vcenter.status) || "not_configured" }
  ];

  return (
    <Page
      activeSection={activeSection}
      description="Golden-state, current-state, drift, credentials, vCenter readiness, and handoff actions."
      issueArea="reports"
      onSectionChange={(sectionId) => setActiveSection(sectionId as GoldenStateSectionId)}
      primaryAction={{
        icon: <FileText size={16} />,
        label: "Generate Handoff Report",
        onClick: () => runGoldenAction("full-lab.handoff-report"),
        disabled: loading || Boolean(runningAction)
      }}
      sections={sections}
      title="Golden State"
    >
      <Feedback loading={loading && !goldenState} error={error} />
      {runMessage && <div className="feedback success">{runMessage}</div>}
      {goldenState && (
        <>
          {activeSection === "dashboard" && (
            <GoldenStateDashboard
              goldenState={goldenState}
              onRunAction={runGoldenAction}
              rows={rows}
              runningAction={runningAction}
              workflowActions={workflowActions}
            />
          )}
          {activeSection === "drift" && (
            <section className="golden-state-stack">
              <GoldenStateTable
                emptyDetail="No drift is reported for the golden-state rows."
                onRunAction={runGoldenAction}
                rows={driftRows}
                runningAction={runningAction}
                title="Drift"
              />
              <BlockerSummary
                blockers={stringArray(goldenState.blockers)}
                warnings={stringArray(goldenState.warnings)}
                empty="No current blocker is reported for the golden-state surface."
              />
            </section>
          )}
          {activeSection === "credentials" && (
            <GoldenCredentialStatus rows={credentialRows} status={asString(credentials.status) || "not_checked"} />
          )}
          {activeSection === "vcenter" && (
            <GoldenVcenterReadiness
              onRunAction={runGoldenAction}
              readiness={vcenter}
              runningAction={runningAction}
              workflowActions={workflowActionCatalog}
            />
          )}
        </>
      )}
    </Page>
  );
}

function GoldenStateDashboard({
  goldenState,
  onRunAction,
  rows,
  runningAction,
  workflowActions
}: {
  goldenState: ProviderProbeResult;
  onRunAction: (actionId: string) => void;
  rows: Record<string, unknown>[];
  runningAction: string;
  workflowActions: Record<string, unknown>[];
}) {
  const readyCount = rows.filter((row) => asString(row.status) === "ready").length;
  const driftCount = rows.filter((row) => asString(row.drift) !== "none").length;
  const artifacts = objectValue(goldenState.artifacts);
  return (
    <section className="golden-state-stack">
      <div className="calm-section-grid">
        <StatusSummaryCard
          message={goldenState.message}
          status={goldenState.status}
          title="Golden state"
          items={[
            { label: "Rows Ready", value: `${readyCount}/${rows.length}` },
            { label: "Drift Rows", value: String(driftCount) },
            { label: "Blockers", value: String(stringArray(goldenState.blockers).length) },
            { label: "Checked", value: goldenState.checked_at ? formatDateTime(goldenState.checked_at) : "Not checked" }
          ]}
        />
        <NextActionCard detail={humanizeAction(asString(goldenState.next_safe_action) || "Review drift rows.")} />
        <StatusSummaryCard
          message="Handoff report and redacted summary are generated by the golden-state make target."
          status={goldenState.handoff_report ? "report_available" : "not_checked"}
          title="Handoff"
          items={[
            { label: "Report", value: asString(artifacts.report) || "Not generated" },
            { label: "Summary", value: asString(artifacts.summary_json) || "Not generated" }
          ]}
        />
      </div>
      <GoldenStateTable
        emptyDetail="No golden-state rows have been reported."
        onRunAction={onRunAction}
        rows={rows}
        runningAction={runningAction}
        title="Current State"
      />
      <GoldenWorkflowActions
        actions={workflowActions}
        onRunAction={onRunAction}
        runningAction={runningAction}
      />
      <AdvancedDetails className="section-details" summary="Golden-state proof links" title="Evidence">
        <ReportLinkList reports={reportLinksFromGoldenState(rows)} />
      </AdvancedDetails>
    </section>
  );
}

function GoldenStateTable({
  emptyDetail,
  onRunAction,
  rows,
  runningAction,
  title
}: {
  emptyDetail: string;
  onRunAction: (actionId: string) => void;
  rows: Record<string, unknown>[];
  runningAction: string;
  title: string;
}) {
  return (
    <section className="panel golden-state-table-panel">
      <div className="issue-list-head">
        <PanelTitle icon={<CheckCircle2 size={18} />} title={title} />
        <span>{rows.length} rows</span>
      </div>
      {rows.length ? (
        <table className="provider-candidate-table golden-state-table">
          <thead>
            <tr>
              <th>Component</th>
              <th>Golden State</th>
              <th>Current State</th>
              <th>Drift</th>
              <th>Repair Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const repairAction = objectValue(row.repair_action);
              const actionId = asString(repairAction.action_id);
              const drift = asString(row.drift) || "none";
              return (
                <tr key={asString(row.id) || asString(row.label)}>
                  <td>
                    <div className="golden-component-cell">
                      <strong>{asString(row.label)}</strong>
                      <StatusBadge status={asString(row.status) || "not_checked"} />
                      <SourceFreshnessInline
                        freshness={asString(row.freshness) || "not_checked"}
                        sourceType={asString(row.source_type) || "not_checked"}
                      />
                      {row.checked_at ? <span className="golden-source-note">{formatDateTime(asString(row.checked_at))}</span> : null}
                    </div>
                  </td>
                  <td>{asString(row.golden_state)}</td>
                  <td>
                    {asString(row.current_state)}
                    <GoldenFirmwareComponentDetail row={row} />
                  </td>
                  <td>{drift === "none" ? "None" : <StatusBadge status={drift} />}</td>
                  <td>
                    <div className="golden-repair-cell">
                      {actionId ? (
                        <button
                          className="small-button"
                          disabled={Boolean(runningAction)}
                          onClick={() => onRunAction(actionId)}
                          type="button"
                        >
                          <RefreshCw size={14} />
                          {runningAction === actionId ? "Running" : asString(repairAction.label) || "Run"}
                        </button>
                      ) : (
                        <span>{asString(repairAction.label) || "Manual"}</span>
                      )}
                      <code>{asString(repairAction.command)}</code>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <EmptyState title="No rows" detail={emptyDetail} />
      )}
    </section>
  );
}

function GoldenFirmwareComponentDetail({ row }: { row: Record<string, unknown> }) {
  const components = recordArray(row.firmware_components);
  if (!components.length) return null;
  return (
    <div className="golden-firmware-detail">
      {components.slice(0, 6).map((component) => (
        <div key={asString(component.component_id) || asString(component.component_label)}>
          <strong>{asString(component.device_label)} - {asString(component.component_label)}</strong>
          <span>
            {asString(component.current_version) || "unknown"} to {asString(component.target_version) || "manual review"}
          </span>
          <StatusBadge status={asString(component.path_status) || "manual_review"} />
        </div>
      ))}
    </div>
  );
}

function GoldenWorkflowActions({
  actions,
  onRunAction,
  runningAction
}: {
  actions: Record<string, unknown>[];
  onRunAction: (actionId: string) => void;
  runningAction: string;
}) {
  return (
    <section className="panel golden-workflow-panel">
      <div className="issue-list-head">
        <PanelTitle icon={<Workflow size={18} />} title="Full Lab Workflows" />
        <span>{actions.length} actions</span>
      </div>
      <div className="golden-workflow-grid">
        {actions.map((action) => {
          const actionId = asString(action.id);
          return (
            <article key={actionId}>
              <div>
                <strong>{asString(action.label)}</strong>
                <p>{asString(action.description)}</p>
                <code>{asString(action.command)}</code>
              </div>
              <button
                className="small-button"
                disabled={Boolean(runningAction)}
                onClick={() => onRunAction(actionId)}
                type="button"
              >
                <Play size={14} />
                {runningAction === actionId ? "Running" : "Run"}
              </button>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function GoldenCredentialStatus({
  rows,
  status
}: {
  rows: Record<string, unknown>[];
  status: string;
}) {
  return (
    <section className="panel golden-state-table-panel">
      <div className="validation-detail-head">
        <div>
          <span className="summary-kicker">Local</span>
          <h2>Credential Status</h2>
        </div>
        <StatusBadge status={status} />
      </div>
      <table className="provider-candidate-table golden-credential-table">
        <thead>
          <tr>
            <th>Provider</th>
            <th>Configured</th>
            <th>Tested</th>
            <th>Next Action</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={asString(row.id) || asString(row.label)}>
              <td>
                <div className="golden-component-cell">
                  <strong>{asString(row.label)}</strong>
                  <SourceFreshnessInline
                    freshness={asString(row.freshness) || "not_checked"}
                    sourceType={asString(row.source_type) || "not_checked"}
                  />
                </div>
              </td>
              <td><StatusBadge status={asBoolean(row.configured) ? "configured" : "missing"} /></td>
              <td><StatusBadge status={asBoolean(row.tested) ? "tested" : "not_checked"} /></td>
              <td>{asString(row.next_action)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function GoldenVcenterReadiness({
  onRunAction,
  readiness,
  runningAction,
  workflowActions
}: {
  onRunAction: (actionId: string, request?: WorkflowActionRunRequest) => void;
  readiness: Record<string, unknown>;
  runningAction: string;
  workflowActions: WorkflowAction[];
}) {
  const deploymentValues = objectValue(readiness.deployment_values);
  const valueChecks = objectValue(readiness.value_checks);
  const checks = objectValue(readiness.checks);
  const vcsaDeployCheck = objectValue(checks.vcsa_deploy_available);
  const managementIpCheck = objectValue(checks.vcenter_management_ip_available);
  const credentialDetail = objectValue(readiness.credential_detail);
  const previewActionId = asString(readiness.preview_action_id) || "vcenter.install-preview";
  const deployActionId = asString(readiness.deploy_action_id) || "vcenter.install-apply";
  const attachPreviewActionId = asString(readiness.attach_preview_action_id) || "vcenter.attach-esxi-preview";
  const attachApplyActionId = asString(readiness.attach_apply_action_id) || "vcenter.attach-esxi-apply";
  const attachValidationActionId = asString(readiness.post_attach_validation_action_id) || "vcenter.post-attach-validation";
  const deployAction = workflowActions.find((action) => action.action_id === deployActionId) ?? null;
  const attachApplyAction = workflowActions.find((action) => action.action_id === attachApplyActionId) ?? null;
  const previewBusy = runningAction === previewActionId;
  const deployBusy = runningAction === deployActionId;
  const attachPreviewBusy = runningAction === attachPreviewActionId;
  const attachApplyBusy = runningAction === attachApplyActionId;
  const attachValidationBusy = runningAction === attachValidationActionId;
  const deployEnabled = asBoolean(readiness.deploy_enabled);
  const managed = asBoolean(readiness.post_attach_ready) || asString(readiness.attach_state) === "managed" || asString(readiness.vcenter_config) === "managed";
  const deployed = managed || asString(readiness.deploy_state) === "deployed" || asString(readiness.vcenter_config) === "deployed";
  const readyForPreview = asBoolean(readiness.ready_for_preview) || asString(readiness.preview_state) === "ready_for_preview";
  const readyForDeploy = asBoolean(readiness.ready_for_deploy) || deployEnabled;
  const attachPreviewReady = asBoolean(readiness.attach_preview_ready);
  const attachReady = deployed && !managed;
  const installLaneStatus = managed ? "managed" : deployed ? "deployed" : readyForDeploy ? "ready_for_deploy" : readyForPreview ? "ready_for_preview" : asString(readiness.status) || "not_configured";
  const deployState = deployed ? "deployed" : readyForDeploy ? "ready_for_deploy" : asString(readiness.deploy_state) || "deploy_disabled";
  const deployDisabledReason =
    deployed
      ? "vCenter is deployed and post-install validation is ready."
      : asString(readiness.deploy_disabled_reason) ||
    (!readyForPreview
      ? "vCenter install readiness is not ready."
      : !asBoolean(readiness.preview_ready)
        ? "Preview Deploy must be ready before install apply."
        : deployAction
          ? workflowGuardedDisabledReason(deployAction)
          : "vcenter.install-apply is not available in the workflow registry.");
  const attachDisabledReason = managed
    ? "vCenter already manages ESXi and sees the NetApp datastore."
    : !deployed
      ? "vCenter must be deployed before ESXi attach."
      : !attachPreviewReady
        ? "Attach preview must be ready before guarded attach apply."
        : attachApplyAction
          ? workflowGuardedDisabledReason(attachApplyAction)
          : "vcenter.attach-esxi-apply is not available in the workflow registry.";
  const credentialsConfigured =
    (asString(readiness.credentials) || asString(readiness.vcenter_credentials)) === "configured" ||
    asBoolean(credentialDetail.deployment_credentials_configured);
  const requirements = [
    {
      label: "VCSA ISO Found",
      status: asString(readiness.vcsa_iso) === "found" ? "ready" : "not_configured",
      value: labelize(asString(readiness.vcsa_iso) || "not_found")
    },
    {
      label: "vcsa-deploy Found",
      status: asString(readiness.vcsa_deploy) === "ready" || asString(vcsaDeployCheck.status) === "ready" ? "ready" : "not_configured",
      value: displayStatusLabel(asString(readiness.vcsa_deploy) || asString(vcsaDeployCheck.status) || "not_checked")
    },
    {
      label: "ESXi Ready",
      status: asString(readiness.esxi) === "ready" ? "ready" : "not_checked",
      value: labelize(asString(readiness.esxi) || "not_ready")
    },
    {
      label: "NetApp Datastore Ready",
      status: asString(readiness.netapp_datastore) === "ready" ? "ready" : "not_checked",
      value: labelize(asString(readiness.netapp_datastore) || "not_ready")
    },
    {
      label: "Management IP Available",
      status:
        deployed || asString(readiness.management_ip_available) === "available" || asString(managementIpCheck.status) === "ready"
          ? "ready"
          : "not_checked",
      value: deployed ? "In use by deployed vCenter" : labelize(asString(readiness.management_ip_available) || asString(managementIpCheck.status) || "not_checked")
    },
    {
      label: "vCenter Values",
      status: asBoolean(readiness.values_complete) || asString(readiness.vcenter_values) === "complete" ? "ready" : "not_configured",
      value: labelize(asString(readiness.vcenter_values) || "incomplete")
    },
    {
      label: "Credentials",
      status: credentialsConfigured ? "ready" : "not_configured",
      value: credentialsConfigured ? "Configured" : "Missing"
    },
    {
      label: "ESXi Attached",
      status: asBoolean(readiness.esxi_attached) ? "ready" : deployed ? "warning" : "not_checked",
      value: asBoolean(readiness.esxi_attached) ? "Visible" : deployed ? "Pending" : "Not checked"
    },
    {
      label: "Datastore Visible",
      status: asBoolean(readiness.datastore_visible) ? "ready" : deployed ? "warning" : "not_checked",
      value: asBoolean(readiness.datastore_visible) ? "Visible" : deployed ? "Pending" : "Not checked"
    },
    {
      label: "VM Inventory",
      status: asBoolean(readiness.vm_inventory_visible) ? "ready" : deployed ? "warning" : "not_checked",
      value: asBoolean(readiness.vm_inventory_visible) ? "Visible" : deployed ? "Pending" : "Not checked"
    }
  ];
  const valueRows = [
    { label: "Appliance Name", value: asString(deploymentValues.appliance_name) || "Missing", status: vcenterValueStatus(valueChecks, "appliance_name") },
    { label: "Management IP", value: asString(deploymentValues.management_ip) || "Missing", status: vcenterValueStatus(valueChecks, "management_ip") },
    { label: "Subnet", value: asString(deploymentValues.subnet_cidr) || "Missing", status: vcenterValueStatus(valueChecks, "subnet_cidr") },
    { label: "Gateway", value: asString(deploymentValues.gateway) || "Missing", status: vcenterValueStatus(valueChecks, "gateway") },
    { label: "DNS", value: stringArray(deploymentValues.dns_servers).join(", ") || "Missing", status: vcenterValueStatus(valueChecks, "dns_servers") },
    {
      label: "Time Sync",
      value:
        asString(deploymentValues.time_sync_mode) === "tools"
          ? "VMware Tools"
          : stringArray(deploymentValues.ntp_servers).join(", ") || "Missing",
      status: vcenterValueStatus(valueChecks, "time_sync")
    },
    { label: "SSO Domain", value: asString(deploymentValues.sso_domain) || "Missing", status: vcenterValueStatus(valueChecks, "sso_domain") },
    {
      label: "SSO Admin Username",
      value: labelize(asString(deploymentValues.sso_admin_username_status) || "missing"),
      status: vcenterValueStatus(valueChecks, "sso_admin_username")
    },
    { label: "ESXi Target", value: asString(deploymentValues.esxi_target) || "Missing", status: vcenterValueStatus(valueChecks, "esxi_target") },
    { label: "Datastore Target", value: asString(deploymentValues.datastore_target) || "Missing", status: vcenterValueStatus(valueChecks, "datastore_target") },
    { label: "VCSA ISO Path", value: asString(deploymentValues.vcsa_iso_path) || "Missing", status: vcenterValueStatus(valueChecks, "vcsa_iso_path") },
    { label: "Deployment Size", value: asString(deploymentValues.deployment_size) || "Missing", status: vcenterValueStatus(valueChecks, "deployment_size") },
    {
      label: "Network / Portgroup",
      value: asString(deploymentValues.network) || asString(deploymentValues.portgroup) || "Missing",
      status: vcenterValueStatus(valueChecks, "network_portgroup")
    }
  ];
  return (
    <section className="panel golden-vcenter-panel">
      <div className="validation-detail-head">
        <div>
          <span className="summary-kicker">vCenter</span>
          <h2>Readiness</h2>
        </div>
        <StatusBadge status={installLaneStatus} />
      </div>
      <div className="vcenter-deploy-state">
        <div>
          <span className="summary-kicker">Install lane</span>
          <strong>{displayStatusLabel(installLaneStatus)}</strong>
          <p>{managed ? "vCenter manages ESXi and sees the NetApp datastore." : deployed ? "vCenter is deployed; ESXi attach is the next managed-state step." : readyForPreview ? "Preview can be generated from current readiness evidence." : "Preview is waiting on readiness evidence."}</p>
        </div>
        <VisibleStatusBadge status={deployState} />
      </div>
      <div className="vcenter-readiness-list">
        {requirements.map((requirement) => (
          <div className="vcenter-readiness-row" key={requirement.label}>
            <span>{requirement.label}</span>
            <strong>{requirement.value}</strong>
            <VisibleStatusBadge status={requirement.status} />
          </div>
        ))}
      </div>
      <div className="golden-vcenter-actions">
        <button
          className="small-button primary"
          disabled={!readyForPreview || Boolean(runningAction)}
          title={readyForPreview ? "Generate the redacted VCSA deploy preview." : "vCenter install readiness must be ready before preview."}
          onClick={() => onRunAction(previewActionId)}
          type="button"
        >
          <Play size={14} />
          {previewBusy ? "Previewing" : "Preview Deploy"}
        </button>
        {deployAction ? (
          <GuardedWorkflowActionButton
            action={deployAction}
            compact
            disabledReasonOverride={deployEnabled ? undefined : deployDisabledReason}
            enabled={deployEnabled && !Boolean(runningAction)}
            label="Deploy vCenter"
            onRun={(action, request) => onRunAction(action.action_id, request)}
            running={deployBusy}
          />
        ) : (
          <button className="small-button" disabled title={deployDisabledReason} type="button">
            <Ban size={14} />
            Deploy vCenter
          </button>
        )}
      </div>
      {!deployEnabled && <p className="vcenter-deploy-disabled-reason">{deployDisabledReason}</p>}
      <div className="vcenter-deploy-state">
        <div>
          <span className="summary-kicker">Attach lane</span>
          <strong>{displayStatusLabel(asString(readiness.attach_state) || "not_checked")}</strong>
          <p>{managed ? "Host, datastore, and VM inventory are visible through vCenter." : deployed ? "Attach preview and guarded apply manage the ESXi host in vCenter." : "Attach waits for deployed vCenter evidence."}</p>
        </div>
        <VisibleStatusBadge status={asString(readiness.attach_state) || "not_checked"} />
      </div>
      <div className="golden-vcenter-actions">
        <button
          className="small-button primary"
          disabled={!deployed || managed || Boolean(runningAction)}
          title={deployed ? "Generate the redacted ESXi attach preview." : "vCenter must be deployed before attach preview."}
          onClick={() => onRunAction(attachPreviewActionId)}
          type="button"
        >
          <Play size={14} />
          {attachPreviewBusy ? "Previewing" : "Preview Attach"}
        </button>
        {attachApplyAction ? (
          <GuardedWorkflowActionButton
            action={attachApplyAction}
            compact
            disabledReasonOverride={attachPreviewReady && attachReady ? undefined : attachDisabledReason}
            enabled={attachPreviewReady && attachReady && !Boolean(runningAction)}
            label="Attach ESXi"
            onRun={(action, request) => onRunAction(action.action_id, request)}
            running={attachApplyBusy}
          />
        ) : (
          <button className="small-button" disabled title={attachDisabledReason} type="button">
            <Ban size={14} />
            Attach ESXi
          </button>
        )}
        <button
          className="small-button"
          disabled={!deployed || Boolean(runningAction)}
          onClick={() => onRunAction(attachValidationActionId)}
          title={deployed ? "Validate vCenter host, datastore, and VM inventory visibility." : "vCenter must be deployed before post-attach validation."}
          type="button"
        >
          <RefreshCw size={14} />
          {attachValidationBusy ? "Validating" : "Validate Attach"}
        </button>
      </div>
      {!managed && deployed && <p className="vcenter-deploy-disabled-reason">{attachDisabledReason}</p>}
      <div className="vcenter-values-section">
        <div className="issue-list-head">
          <PanelTitle icon={<ClipboardList size={18} />} title="Install Values" />
          <VisibleStatusBadge status={asBoolean(readiness.values_complete) ? "ready" : "not_configured"} />
        </div>
        <table className="provider-candidate-table vcenter-values-table">
          <thead>
            <tr>
              <th>Value</th>
              <th>Configured Value</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {valueRows.map((row) => (
              <tr key={row.label}>
                <td>{row.label}</td>
                <td>{row.value}</td>
                <td><VisibleStatusBadge status={row.status} /></td>
              </tr>
            ))}
            <tr>
              <td>SSO Admin Password</td>
              <td>{asBoolean(credentialDetail.sso_admin_password_configured) ? "Configured" : "Missing"}</td>
              <td><VisibleStatusBadge status={asBoolean(credentialDetail.sso_admin_password_configured) ? "ready" : "not_configured"} /></td>
            </tr>
            <tr>
              <td>Appliance Root Password</td>
              <td>{asBoolean(credentialDetail.appliance_root_password_configured) ? "Configured" : "Missing"}</td>
              <td><VisibleStatusBadge status={asBoolean(credentialDetail.appliance_root_password_configured) ? "ready" : "not_configured"} /></td>
            </tr>
            <tr>
              <td>ESXi Credentials</td>
              <td>{asBoolean(credentialDetail.esxi_credentials_configured) ? "Configured" : "Missing"}</td>
              <td><VisibleStatusBadge status={asBoolean(credentialDetail.esxi_credentials_configured) ? "ready" : "not_configured"} /></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div className="detail-grid">
        <Info label="vCenter Config" value={labelize(asString(readiness.vcenter_config) || "expected_partial")} />
        <Info label="Source" value={labelize(asString(readiness.source_type) || "not_checked")} />
        <Info label="Freshness" value={labelize(asString(readiness.freshness) || "not_checked")} />
        <Info label="Checked" value={readiness.checked_at ? formatDateTime(asString(readiness.checked_at)) : "Not checked"} />
        <Info label="Recheck" value={asString(readiness.recheck_command) || "make provider-lab-vcenter-install-readiness"} />
      </div>
      <NextActionCard detail={humanizeAction(asString(readiness.next_action) || "Configure vCenter deployment values.")} />
      <AdvancedDetails className="section-details" summary="vCenter readiness evidence" title="Evidence">
        <ReportLinkList reports={reportLinksFromPaths("vCenter", stringArray(readiness.evidence_artifacts), asString(readiness.status) || "not_configured")} />
      </AdvancedDetails>
    </section>
  );
}

function vcenterValueStatus(checks: Record<string, unknown>, key: string): string {
  const check = objectValue(checks[key]);
  return asString(check.status) || "not_configured";
}

function VisibleStatusBadge({ status }: { status: string }) {
  return <span className={`status status-${status}`}>{displayStatusLabel(status)}</span>;
}

function reportLinksFromGoldenState(rows: Record<string, unknown>[]): ReportLink[] {
  return rows.flatMap((row) =>
    stringArray(row.evidence_artifacts).map((path) => ({
      label: asString(row.label) || "Golden State",
      path,
      status: asString(row.status) || "historical"
    }))
  );
}

function reportLinksFromPaths(label: string, paths: string[], status: string): ReportLink[] {
  return paths.map((path) => ({ label, path, status }));
}

function LabValidationPage() {
  const [activeSection, setActiveSection] = useState<LabValidationSectionId>("overview");
  const [validation, setValidation] = useState<LabValidationSummary | null>(null);
  const [vcenterNetapp, setVcenterNetapp] = useState<ProviderProbeResult | null>(null);
  const [selectedId, setSelectedId] = useState("lab-profile");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setError("");
    setLoading(true);
    try {
      const [nextValidation, nextVcenterNetapp] = await Promise.all([
        api.labValidation(),
        api.vcenterNetappReadiness()
      ]);
      setValidation(nextValidation);
      setVcenterNetapp(nextVcenterNetapp);
      if (!nextValidation.validation_items.some((item) => item.id === selectedId)) {
        setSelectedId(nextValidation.validation_items[0]?.id ?? "lab-profile");
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (activeSection === "vcenter-netapp") {
      setSelectedId("vcenter-netapp-datastore");
    }
  }, [activeSection]);

  const items = validation?.validation_items ?? [];
  const selectedItem = items.find((item) => item.id === selectedId) ?? items[0] ?? null;
  const vcenterItem = items.find((item) => item.id === "vcenter-netapp-datastore") ?? selectedItem;
  const vcenterRows = items.filter((item) => item.id.includes("vcenter") || item.id.includes("netapp"));
  const vcenterSelectedItem = vcenterRows.find((item) => item.id === selectedId) ?? vcenterItem;
  const sections: SectionOption<LabValidationSectionId>[] = [
    { id: "overview", label: "Overview", status: validation?.overall_status ?? "not_checked" },
    { id: "vcenter-netapp", label: "vCenter-NetApp", status: vcenterItem?.status ?? "not_checked" },
    { id: "handoff", label: "Handoff", status: validation?.handoff_report ? "report_available" : "not_checked" }
  ];

  return (
    <Page
      activeSection={activeSection}
      description="Handoff view for setup state, login targets, proof links, and next actions across the lab."
      onSectionChange={(sectionId) => setActiveSection(sectionId as LabValidationSectionId)}
      primaryAction={{ icon: <RefreshCw size={16} />, label: "Refresh", onClick: load, disabled: loading }}
      sections={sections}
      title="Lab Validation / Handoff"
    >
      <Feedback loading={loading && !validation} error={error} />
      {validation && (
        <>
          <LabValidationSummaryStrip summary={validation} />
          {activeSection === "overview" && (
            <section className="lab-validation-layout">
              <LabValidationTable items={items} onSelect={setSelectedId} selectedId={selectedItem?.id ?? ""} />
              {selectedItem && <LabValidationDetail item={selectedItem} vcenterNetapp={vcenterNetapp} />}
            </section>
          )}
          {activeSection === "vcenter-netapp" && vcenterSelectedItem && (
            <section className="lab-validation-layout">
              <LabValidationTable items={vcenterRows} onSelect={setSelectedId} selectedId={vcenterSelectedItem.id} />
              <LabValidationDetail item={vcenterSelectedItem} vcenterNetapp={vcenterNetapp} />
            </section>
          )}
          {activeSection === "handoff" && <LabValidationHandoff summary={validation} />}
        </>
      )}
    </Page>
  );
}

function LabValidationSummaryStrip({ summary }: { summary: LabValidationSummary }) {
  const counts = summary.progress_counts;
  return (
    <section className="validation-summary-strip" aria-label="Lab validation summary counts">
      <ValidationCount label="Ready" status="ready" value={counts.ready ?? 0} />
      <ValidationCount label="Partial" status="partial" value={counts.partial ?? 0} />
      <ValidationCount label="Blocked" status="blocked" value={counts.blocked ?? 0} />
      <ValidationCount label="Not configured" status="not_configured" value={counts.not_configured ?? 0} />
      <div className="validation-next-action">
        <span>Next action</span>
        <strong>{summary.next_action}</strong>
      </div>
    </section>
  );
}

function ValidationCount({ label, status, value }: { label: string; status: string; value: number }) {
  return (
    <article className={`validation-count validation-count-${statusClassName(status)}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <StatusBadge status={status} />
    </article>
  );
}

function LabValidationTable({
  items,
  onSelect,
  selectedId
}: {
  items: LabValidationItem[];
  onSelect: (id: string) => void;
  selectedId: string;
}) {
  return (
    <section className="panel lab-validation-table-panel">
      <div className="issue-list-head">
        <PanelTitle icon={<ClipboardList size={18} />} title="Validation Items" />
        <span>{items.length} components</span>
      </div>
      <table className="provider-candidate-table lab-validation-table lab-validation-overview-table">
        <thead>
          <tr>
            <th>Component</th>
            <th>Status</th>
            <th>Setup summary</th>
            <th>Login / Proof</th>
            <th>Next action</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr className={item.id === selectedId ? "selected-row" : ""} key={item.id}>
              <td>
                <button className="table-row-button" onClick={() => onSelect(item.id)} type="button">
                  <strong>{item.label}</strong>
                  <span>{item.category}</span>
                </button>
              </td>
              <td>
                <StatusBadge status={item.status} />
              </td>
              <td>{item.setup_summary}</td>
              <td>
                <span>{item.login_hint}</span>
                {item.evidence_artifacts.length > 0 && <small>{item.evidence_artifacts.length} proof link{item.evidence_artifacts.length === 1 ? "" : "s"}</small>}
              </td>
              <td>{item.next_action}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function LabValidationDetail({
  item,
  vcenterNetapp
}: {
  item: LabValidationItem;
  vcenterNetapp: ProviderProbeResult | null;
}) {
  const { isAdvancedMode } = useUiMode();
  const isVcenterNetapp = item.id === "vcenter-netapp-datastore";
  const preview = objectValue(vcenterNetapp?.datastore_add_preview);
  const blockers = item.blockers.map((blocker) => blocker.problem);
  const reports: ReportLink[] = item.evidence_artifacts.map((path) => ({
    label: item.label,
    path,
    status: item.source_type === "historical_artifact" ? "stale" : item.status
  }));

  return (
    <section className="panel lab-validation-detail-panel">
      <div className="validation-detail-head">
        <div>
          <span className="summary-kicker">{item.category}</span>
          <h2>{item.label}</h2>
        </div>
        <StatusBadge status={item.status} />
      </div>
      <div className="detail-grid">
        <Info label="Current state" value={item.current_state} />
        <Info label="Desired state" value={item.desired_state} />
        <Info label="Last checked" value={item.last_checked ? formatDateTime(item.last_checked) : "Not checked" } />
        {isAdvancedMode && <Info label="Source" value={`${labelize(item.source_type)} / ${labelize(item.freshness)}`} />}
      </div>
      <div className="validation-login-proof">
        <strong>Login / proof</strong>
        <p>{item.login_hint}</p>
        {item.management_url && <code>{item.management_url}</code>}
        {item.ssh_target && <code>{item.ssh_target}</code>}
      </div>
      <BlockerSummary blockers={blockers} warnings={item.warnings} empty="No current blocker is reported for this validation item." />
      <AdvancedDetails
        className="section-details"
        summary="Recheck command, linked workflow, source, and command preview"
        title="Advanced validation details"
      >
        <div className="validation-command-row">
          <span>Recheck command</span>
          <code>{item.recheck_command}</code>
        </div>
        {item.linked_workflow_action && (
          <div className="validation-command-row">
            <span>Linked workflow</span>
            <Link to={`/control-center?section=action-catalog&action=${encodeURIComponent(item.linked_workflow_action.action_id)}`}>
              {item.linked_workflow_action.label ?? item.linked_workflow_action.action_id}
            </Link>
          </div>
        )}
        {isVcenterNetapp && (
          <div className="validation-plan-preview">
            <strong>Datastore command preview</strong>
            <code>{asString(preview.govc) || "govc preview unavailable until readiness loads"}</code>
            <code>{asString(preview.esxi_fallback) || "ESXi fallback preview unavailable until readiness loads"}</code>
          </div>
        )}
      </AdvancedDetails>
      <AdvancedDetails
        className="section-details"
        summary={`${item.proof_points.length} proof point${item.proof_points.length === 1 ? "" : "s"}`}
        title="Proof Points"
      >
        {item.proof_points.length ? (
          <ul className="compact-list">
            {item.proof_points.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No proof points" detail="Proof points will appear after a validation source reports them." />
        )}
      </AdvancedDetails>
      <AdvancedDetails
        className="section-details"
        summary={`${item.evidence_artifacts.length} artifact${item.evidence_artifacts.length === 1 ? "" : "s"}`}
        title="Evidence"
      >
        <ReportLinkList reports={reports} />
      </AdvancedDetails>
    </section>
  );
}

function LabValidationHandoff({ summary }: { summary: LabValidationSummary }) {
  return (
    <section className="panel lab-validation-handoff">
      <div className="validation-detail-head">
        <div>
          <span className="summary-kicker">Handoff</span>
          <h2>Operator Handoff</h2>
        </div>
        <StatusBadge status={summary.overall_status} />
      </div>
      <div className="detail-grid">
        <Info label="Generated" value={formatDateTime(summary.generated_at)} />
        <Info label="Report" value={summary.handoff_report} />
        <Info label="Proof links" value={String(summary.proof_links.length)} />
        <Info label="Top blocker" value={summary.top_blocker?.problem ?? "None"} />
      </div>
      <table className="provider-candidate-table lab-validation-table lab-validation-handoff-table">
        <thead>
          <tr>
            <th>Component</th>
            <th>Status</th>
            <th>Login / target</th>
            <th>What remains</th>
          </tr>
        </thead>
        <tbody>
          {summary.validation_items.map((item) => (
            <tr key={item.id}>
              <td>{item.label}</td>
              <td><StatusBadge status={item.status} /></td>
              <td>{item.login_hint}</td>
              <td><LabValidationRemainderCell item={item} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <AdvancedDetails
        className="section-details"
        summary={`${summary.proof_links.length} proof link${summary.proof_links.length === 1 ? "" : "s"}`}
        title="Evidence Links"
      >
        {summary.proof_links.length ? (
          <ul className="issue-evidence-list">
            {summary.proof_links.map((link) => (
              <li key={`${link.component_id}-${link.path}`}>
                <strong>{link.component_label}</strong>
                <code>{link.path}</code>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No proof links" detail="Proof links will appear after validation reports are generated." />
        )}
      </AdvancedDetails>
    </section>
  );
}

function LabValidationRemainderCell({ item }: { item: LabValidationItem }) {
  if (item.status === "ready") return <>Ready for handoff</>;
  if (item.id !== "firmware-compliance") return <>{item.next_action}</>;
  const points = item.proof_points.filter((point) => /current|target|path|package/i.test(point)).slice(0, 4);
  if (!points.length) return <>{item.next_action}</>;
  return (
    <div className="handoff-firmware-points">
      <strong>{item.next_action}</strong>
      {points.map((point) => (
        <span key={point}>{point}</span>
      ))}
    </div>
  );
}

function ValidationReportsPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { reportIssues, reportIssuesError, reportIssuesLoading, reloadReportIssues } = useReportIssues();
  const { isAdvancedMode, setUiMode } = useUiMode();
  const [activeSection, setActiveSection] = useState<ValidationReportsSectionId>("summary");
  const [reportFilter, setReportFilter] = useState<ReportsSectionId>("all");
  const [verification, setVerification] = useState<ProviderProbeResult | null>(null);
  const [validation, setValidation] = useState<LabValidationSummary | null>(null);
  const [vcenterNetapp, setVcenterNetapp] = useState<ProviderProbeResult | null>(null);
  const [selectedValidationId, setSelectedValidationId] = useState("lab-profile");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setError("");
    setLoading(true);
    try {
      const [nextVerification, nextValidation, nextVcenterNetapp] = await Promise.all([
        api.buildVerification(),
        api.labValidation(),
        api.vcenterNetappReadiness()
      ]);
      setVerification(nextVerification);
      setValidation(nextValidation);
      setVcenterNetapp(nextVcenterNetapp);
      if (!nextValidation.validation_items.some((item) => item.id === selectedValidationId)) {
        setSelectedValidationId(nextValidation.validation_items[0]?.id ?? "lab-profile");
      }
      await reloadReportIssues();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const section = params.get("section");
    const filter = params.get("filter");
    const allowedSections: ValidationReportsSectionId[] = ["summary", "issues", "validation", "proof", "evidence"];
    const allowedFilters: ReportsSectionId[] = [
      "all",
      "critical",
      "warnings",
      "stale_config",
      "cisco",
      "esxi",
      "netapp",
      "firmware",
      "lab_profile"
    ];
    if (section && allowedSections.includes(section as ValidationReportsSectionId)) {
      setActiveSection(section as ValidationReportsSectionId);
    }
    if (filter && allowedFilters.includes(filter as ReportsSectionId)) {
      setReportFilter(filter as ReportsSectionId);
      setActiveSection("issues");
    }
  }, [location.search]);

  function changeSection(sectionId: string) {
    const nextSection = sectionId as ValidationReportsSectionId;
    setActiveSection(nextSection);
    navigate(nextSection === "summary" ? "/validation-reports" : `/validation-reports?section=${nextSection}`);
  }

  function changeReportFilter(sectionId: string) {
    const nextFilter = sectionId as ReportsSectionId;
    setReportFilter(nextFilter);
    navigate(
      nextFilter === "all"
        ? "/validation-reports?section=issues"
        : `/validation-reports?section=issues&filter=${encodeURIComponent(nextFilter)}`
    );
  }

  const issues = reportIssues?.issues ?? [];
  const filteredIssues = filterReportIssuesForSection(reportFilter, issues);
  const validationItems = validation?.validation_items ?? [];
  const selectedValidationItem =
    validationItems.find((item) => item.id === selectedValidationId) ?? validationItems[0] ?? null;
  const proofLinks = validation?.proof_links ?? [];
  const verificationBlockerCount = stringArray(verification?.blockers).length;
  const criticalCount = Math.max(reportIssues?.counts.critical ?? 0, verificationBlockerCount);
  const warningCount = Math.max(reportIssues?.counts.warning ?? 0, (validation?.warnings ?? stringArray(verification?.warnings)).length);
  const notConfiguredCount = Math.max(
    reportIssues?.classification_counts.not_configured_yet ?? 0,
    validation?.progress_counts.not_configured ?? 0
  );
  const passedCount = Math.max(reportIssues?.counts.success ?? 0, validation?.progress_counts.ready ?? 0);
  const sections: SectionOption<ValidationReportsSectionId>[] = [
    { id: "summary", label: "Summary", status: reportIssues?.overall_status ?? validation?.overall_status ?? "not_checked" },
    { id: "issues", label: "Issues", status: criticalCount ? "critical" : warningCount ? "warning" : "ready" },
    { id: "validation", label: "Validation", status: validation?.overall_status ?? "not_checked" },
    { id: "proof", label: "Proof / Handoff", status: validation?.handoff_report ? "report_available" : "not_checked" },
    { id: "evidence", label: "Evidence", status: proofLinks.length || reportIssues?.evidence_artifacts.length ? "available" : "not_checked" }
  ];
  const reportFilterSections: SectionOption<ReportsSectionId>[] = [
    { id: "all", label: "All", status: reportIssues?.overall_status ?? "not_run" },
    { id: "critical", label: "Critical", status: criticalCount ? "critical" : "passed" },
    { id: "warnings", label: "Warnings", status: warningCount ? "warning" : "passed" },
    { id: "stale_config", label: "Stale Config", status: filteredStatusForClass(issues, "stale_config") },
    { id: "cisco", label: "Cisco", status: filteredStatusForSource(issues, "cisco") },
    { id: "esxi", label: "ESXi", status: filteredStatusForSource(issues, "esxi") },
    { id: "netapp", label: "NetApp", status: filteredStatusForSource(issues, "netapp") },
    { id: "firmware", label: "Firmware", status: filteredStatusForSource(issues, "firmware") },
    { id: "lab_profile", label: "Lab Setup", status: filteredStatusForSource(issues, "lab_profile") }
  ];

  return (
    <Page
      activeSection={activeSection}
      description="Readiness, lab validation, handoff proof, issue triage, and evidence in one place."
      issueArea="reports"
      onSectionChange={changeSection}
      primaryAction={{ icon: <RefreshCw size={16} />, label: "Refresh", onClick: load, disabled: loading || reportIssuesLoading }}
      sections={sections}
      title="Validation & Reports"
    >
      <Feedback loading={(loading || reportIssuesLoading) && !verification && !validation && !reportIssues} error={error || reportIssuesError} />
      {activeSection === "summary" && (
        <>
          <section className="issue-summary-grid" aria-label="Validation and report summary counts">
            <IssueSummaryTile icon={<XCircle size={18} />} label="Current Blockers" status="critical" value={criticalCount} />
            <IssueSummaryTile icon={<AlertTriangle size={18} />} label="Needs Review" status="warning" value={warningCount} />
            <IssueSummaryTile icon={<Activity size={18} />} label="Not Configured" status="not_configured_yet" value={notConfiguredCount} />
            <IssueSummaryTile icon={<CheckCircle2 size={18} />} label="Passed" status="success" value={passedCount} />
          </section>
          <div className="calm-section-grid">
            <StatusSummaryCard
              message={asString(verification?.message) || "Build verification has not loaded yet."}
              status={asString(verification?.certification_state) || verification?.status || "not_checked"}
              title="Readiness / Certification"
              items={[
                { label: "Certification", value: displayStatusLabel(asString(verification?.certification_state) || verification?.status || "Not checked") },
                { label: "Blockers", value: String(stringArray(verification?.blockers).length) },
                { label: "Warnings", value: String(stringArray(verification?.warnings).length) },
                { label: "Checked", value: verification?.checked_at ? formatDateTime(verification.checked_at) : "Not checked" }
              ]}
            />
            <NextActionCard detail={humanizeAction(validation?.next_action || asString(verification?.next_safe_action) || "Run validation after setup steps are ready.")} />
            <BlockerSummary blockers={stringArray(verification?.blockers)} warnings={validation?.warnings ?? stringArray(verification?.warnings)} />
          </div>
          {validation && <LabValidationSummaryStrip summary={validation} />}
          {reportIssues && <TopFixesPanel issues={reportIssues.top_issues.slice(0, 3)} />}
        </>
      )}
      {activeSection === "issues" && reportIssues && (
        <>
          <SectionSwitch activeId={reportFilter} onChange={changeReportFilter} sections={reportFilterSections} />
          <TopFixesPanel issues={reportIssues.top_issues.slice(0, 3)} />
          <section className="panel issue-list-panel">
            <div className="issue-list-head">
              <PanelTitle icon={<ClipboardList size={18} />} title="Issue List" />
              <span>{filteredIssues.length} shown</span>
            </div>
            {isAdvancedMode ? (
              filteredIssues.length ? (
                <div className="issue-card-grid">
                  {filteredIssues.map((issue) => (
                    <ReportIssueCard issue={issue} key={issue.id} />
                  ))}
                </div>
              ) : (
                <EmptyState title="No issues for this filter" detail="This filter has no findings in the current report snapshot." />
              )
            ) : (
              <CompactReportIssueList issues={filteredIssues} onShowAdvanced={() => setUiMode("advanced")} />
            )}
          </section>
        </>
      )}
      {activeSection === "validation" && validation && (
        <section className="lab-validation-layout">
          <LabValidationTable items={validationItems} onSelect={setSelectedValidationId} selectedId={selectedValidationItem?.id ?? ""} />
          {selectedValidationItem && <LabValidationDetail item={selectedValidationItem} vcenterNetapp={vcenterNetapp} />}
        </section>
      )}
      {activeSection === "proof" && validation && (
        <ValidationProofHandoff summary={validation} />
      )}
      {activeSection === "evidence" && (
        <>
          {reportIssues && <ReportEvidenceGroups reportCenter={reportIssues} />}
          {validation && (
            <EvidenceDrawer count={proofLinks.length} title="Validation Proof Links">
              {proofLinks.length ? (
                <ul className="issue-evidence-list">
                  {proofLinks.map((link) => (
                    <li key={`${link.component_id}-${link.path}`}>
                      <strong>{link.component_label}</strong>
                      <code>{link.path}</code>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState title="No validation proof links" detail="Proof links appear after validation reports are generated." />
              )}
            </EvidenceDrawer>
          )}
          {reportIssues && <ReportActionGroups issues={issues} />}
        </>
      )}
    </Page>
  );
}

function CompactReportIssueList({
  issues,
  onShowAdvanced
}: {
  issues: ReportIssue[];
  onShowAdvanced: () => void;
}) {
  if (!issues.length) {
    return <EmptyState title="No issues for this filter" detail="This filter has no findings in the current report snapshot." />;
  }
  return (
    <div className="compact-issue-list">
      {issues.slice(0, 8).map((issue) => (
        <article key={issue.id}>
          <div>
            <strong>{humanizeReportTitle(issue.title || issue.problem)}</strong>
            <p>{humanizeAction(issue.next_action || issue.summary || "Review this finding.")}</p>
          </div>
          <StatusBadge status={issue.severity || issue.status} />
        </article>
      ))}
      <div className="simple-more-row">
        <span>Source metadata, commands, raw evidence, and full issue cards are hidden by default.</span>
        <button className="small-button" onClick={onShowAdvanced} type="button">
          <Settings size={14} />
          Show details
        </button>
      </div>
    </div>
  );
}

function ValidationProofHandoff({ summary }: { summary: LabValidationSummary }) {
  return (
    <section className="panel validation-proof-panel">
      <div className="validation-detail-head">
        <div>
          <span className="summary-kicker">Proof / Handoff</span>
          <h2>Operator Handoff</h2>
          <p>{summary.next_action}</p>
        </div>
        <StatusBadge status={summary.overall_status} />
      </div>
      <div className="detail-grid">
        <Info label="Generated" value={formatDateTime(summary.generated_at)} />
        <Info label="Proof Links" value={String(summary.proof_links.length)} />
        <Info label="Top Blocker" value={summary.top_blocker?.problem ?? "None"} />
        <Info label="Source" value={`${labelize(summary.source_type)} / ${labelize(summary.freshness)}`} />
      </div>
      <table className="provider-candidate-table lab-validation-table lab-validation-handoff-table">
        <thead>
          <tr>
            <th>Component</th>
            <th>Status</th>
            <th>Access</th>
            <th>What remains</th>
          </tr>
        </thead>
        <tbody>
          {summary.validation_items.map((item) => (
            <tr key={item.id}>
              <td>{item.label}</td>
              <td><StatusBadge status={item.status} /></td>
              <td>{item.login_hint}</td>
              <td><LabValidationRemainderCell item={item} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <AdvancedDetails className="section-details" summary="Handoff report path and proof links" title="Handoff Evidence">
        <ProviderFact label="Handoff Report" value={summary.handoff_report || "Not generated"} />
        {summary.proof_links.length ? (
          <ul className="issue-evidence-list">
            {summary.proof_links.map((link) => (
              <li key={`${link.component_id}-${link.path}`}>
                <strong>{link.component_label}</strong>
                <code>{link.path}</code>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No proof links" detail="Proof links will appear after validation reports are generated." />
        )}
      </AdvancedDetails>
    </section>
  );
}

function ReportsPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { reportIssues, reportIssuesError, reportIssuesLoading, reloadReportIssues } = useReportIssues();
  const { isAdvancedMode, setUiMode } = useUiMode();
  const [activeSection, setActiveSection] = useState<ReportsSectionId>("all");

  useEffect(() => {
    const filter = new URLSearchParams(location.search).get("filter");
    const allowed: ReportsSectionId[] = [
      "all",
      "critical",
      "warnings",
      "stale_config",
      "cisco",
      "esxi",
      "netapp",
      "firmware",
      "lab_profile"
    ];
    if (filter && allowed.includes(filter as ReportsSectionId)) {
      setActiveSection(filter as ReportsSectionId);
    } else if (!filter) {
      setActiveSection("all");
    }
  }, [location.search]);

  function setReportFilter(sectionId: string) {
    const nextSection = sectionId as ReportsSectionId;
    setActiveSection(nextSection);
    navigate(nextSection === "all" ? "/validation-reports?section=issues" : `/validation-reports?section=issues&filter=${encodeURIComponent(nextSection)}`);
  }

  const issues = reportIssues?.issues ?? [];
  const filteredIssues = filterReportIssuesForSection(activeSection, issues);
  const criticalCount = reportIssues?.counts.critical ?? 0;
  const warningCount = reportIssues?.counts.warning ?? 0;
  const notConfiguredCount = reportIssues?.classification_counts.not_configured_yet ?? 0;
  const passedCount = reportIssues?.counts.success ?? 0;
  const sections: SectionOption<ReportsSectionId>[] = [
    { id: "all", label: "All", status: reportIssues?.overall_status ?? "not_run" },
    { id: "critical", label: "Critical", status: criticalCount ? "critical" : "passed" },
    { id: "warnings", label: "Warnings", status: warningCount ? "warning" : "passed" },
    { id: "stale_config", label: "Stale Config", status: filteredStatusForClass(issues, "stale_config") },
    { id: "cisco", label: "Cisco", status: filteredStatusForSource(issues, "cisco") },
    { id: "esxi", label: "ESXi", status: filteredStatusForSource(issues, "esxi") },
    { id: "netapp", label: "NetApp", status: filteredStatusForSource(issues, "netapp") },
    { id: "firmware", label: "Firmware", status: filteredStatusForSource(issues, "firmware") },
    { id: "lab_profile", label: "Lab Setup", status: filteredStatusForSource(issues, "lab_profile") }
  ];

  return (
    <Page
      activeSection={activeSection}
      description="One report center for blocked, review, not-configured, and ready findings across lab workflows."
      issueArea="reports"
      onSectionChange={setReportFilter}
      primaryAction={{ icon: <RefreshCw size={16} />, label: "Refresh", onClick: reloadReportIssues, disabled: reportIssuesLoading }}
      sections={sections}
      title="Reports & Issues"
    >
      <Feedback loading={reportIssuesLoading && !reportIssues} error={reportIssuesError} />
      {reportIssues && (
        <>
          <section className="issue-summary-grid" aria-label="Report center summary counts">
            <IssueSummaryTile
              icon={<XCircle size={18} />}
              label="Live Blockers"
              status="critical"
              value={criticalCount}
            />
            <IssueSummaryTile
              icon={<AlertTriangle size={18} />}
              label="Stale / Review"
              status="warning"
              value={warningCount}
            />
            <IssueSummaryTile
              icon={<Activity size={18} />}
              label="Not Configured Yet"
              status="not_configured_yet"
              value={notConfiguredCount}
            />
            <IssueSummaryTile
              icon={<CheckCircle2 size={18} />}
              label="Passed"
              status="success"
              value={passedCount}
            />
          </section>

          <TopFixesPanel issues={reportIssues.top_issues.slice(0, 3)} />

          {isAdvancedMode ? (
            <section className="panel issue-list-panel">
              <div className="issue-list-head">
                <PanelTitle icon={<ClipboardList size={18} />} title="Issue List" />
                <span>{filteredIssues.length} shown</span>
              </div>
              {filteredIssues.length ? (
                <div className="issue-card-grid">
                  {filteredIssues.map((issue) => (
                    <ReportIssueCard issue={issue} key={issue.id} />
                  ))}
                </div>
              ) : (
                <EmptyState
                  title="No issues for this filter"
                  detail="This filter has no open, review, not-configured, or passed findings in the current report snapshot."
                />
              )}
            </section>
          ) : (
            <section className="panel issue-list-panel">
              <div className="issue-list-head">
                <PanelTitle icon={<ClipboardList size={18} />} title="Issue Details" />
                <span>{filteredIssues.length} available</span>
              </div>
              <div className="simple-more-row">
                <span>Top fixes are shown above. Full issue rows, source links, and raw evidence are available in Advanced.</span>
                <button className="small-button" onClick={() => setUiMode("advanced")} type="button">
                  <Settings size={14} />
                  Show details
                </button>
              </div>
            </section>
          )}

          <ReportActionGroups issues={issues} />
          <ReportEvidenceGroups reportCenter={reportIssues} />
        </>
      )}
    </Page>
  );
}

function IssueSummaryTile({
  icon,
  label,
  status,
  value
}: {
  icon: ReactNode;
  label: string;
  status: string;
  value: number;
}) {
  return (
    <article className={`issue-summary-tile issue-tone-${status}`}>
      <div>
        {icon}
        <span>{label}</span>
      </div>
      <strong>{value}</strong>
    </article>
  );
}

function TopFixesPanel({ issues }: { issues: ReportIssue[] }) {
  return (
    <section className="top-fixes-panel" aria-labelledby="top-fixes-title">
      <div className="top-fixes-head">
        <div>
          <p className="eyebrow">What To Fix Next</p>
          <h2 id="top-fixes-title">Top Fixes</h2>
        </div>
        <StatusBadge status={issues.length ? issues[0].severity : "passed"} />
      </div>
      {issues.length ? (
        <TopFixesList issues={issues} />
      ) : (
        <EmptyState title="No critical fixes" detail="No critical or warning issues are open in the current report snapshot." />
      )}
    </section>
  );
}

function TopFixesList({ issues }: { issues: ReportIssue[] }) {
  return (
    <div className="top-fix-list">
      {issues.map((issue, index) => (
        <article className={`top-fix-item issue-tone-${issue.severity}`} key={issue.id}>
          <span>{index + 1}</span>
          <div>
            <strong>{humanizeIssueTitle(issue.title)}</strong>
            <p>{humanizeAction(issue.next_action)}</p>
            <Link to={issue.linked_page || "/reports"}>Open source page</Link>
          </div>
        </article>
      ))}
    </div>
  );
}

function humanizeIssueTitle(value: string): string {
  return humanizeAction(value)
    .replace(/ is hard_fail\./g, " is not reachable.")
    .replace(/hard_fail/g, "not reachable")
    .replace(/_/g, " ");
}

function ReportIssueCard({ issue }: { issue: ReportIssue }) {
  return (
    <article className={`report-issue-card issue-tone-${issue.severity}`} id={issue.id}>
      <div className="report-issue-head">
        <IssueSeverityLabel issue={issue} />
        <StatusBadge status={issue.classification} />
      </div>
      <h3>{issue.title}</h3>
      <p>{issue.problem || issue.summary}</p>
      <div className="issue-next-action">
        <span>Next action</span>
        <strong>{issue.next_action}</strong>
      </div>
      {issue.classification === "stale_config" && <StaleConfigDetails issue={issue} />}
      <dl className="issue-meta-grid">
        <div>
          <dt>Source</dt>
          <dd>{issueSourceLabel(issue)}</dd>
        </div>
        <div>
          <dt>Source stage</dt>
          <dd>
            {issue.source_stage_id ? (
              <Link to="/overview">
                {issue.source_stage_label || issue.source_stage_id}
              </Link>
            ) : (
              issue.source_stage_label || issue.source_stage
            )}
          </dd>
        </div>
        <div>
          <dt>Source action</dt>
          <dd>
            {issue.source_action_link ? (
              <Link to={issue.source_action_link}>{issue.source_action_label || issue.source_action_id}</Link>
            ) : (
              issue.source_action_label || "Not linked"
            )}
          </dd>
        </div>
        <div>
          <dt>Last checked</dt>
          <dd>{issue.last_checked ? formatDateTime(issue.last_checked) : "Not checked"}</dd>
        </div>
        <div>
          <dt>Freshness</dt>
          <dd>{labelize(issue.freshness || "unknown")}</dd>
        </div>
        <div>
          <dt>Recheck command</dt>
          <dd>
            <code>{issue.recheck_command || "Refresh report center"}</code>
          </dd>
        </div>
        <div>
          <dt>Source page</dt>
          <dd>
            <Link to={issue.linked_page || "/reports"}>Open page</Link>
          </dd>
        </div>
      </dl>
      <IssueEvidenceDetails issue={issue} />
    </article>
  );
}

function IssueSeverityLabel({ issue }: { issue: ReportIssue }) {
  const label =
    issue.severity === "critical"
      ? "Live blocker"
      : issue.severity === "warning"
        ? issueSourceLabel(issue) === "stale" ? "Stale evidence" : "Needs review"
        : issue.severity === "success"
          ? "Live check passed"
          : issue.classification === "not_configured_yet"
            ? "Not configured yet"
            : issueSourceLabel(issue) === "not checked" ? "Not checked" : "Info";
  const icon =
    issue.severity === "critical" ? (
      <XCircle size={16} />
    ) : issue.severity === "warning" ? (
      <AlertTriangle size={16} />
    ) : issue.severity === "success" ? (
      <CheckCircle2 size={16} />
    ) : (
      <Activity size={16} />
    );
  return (
    <span className={`issue-severity-label issue-tone-${issue.severity}`}>
      {icon}
      {label}
    </span>
  );
}

function issueSourceLabel(issue: ReportIssue): string {
  if (issue.source_type === "test_fixture") return "test";
  if (issue.source_type === "not_checked") return "not checked";
  if (issue.source_type === "historical_artifact" || issue.freshness === "stale" || !issue.is_current) return "stale";
  if (issue.source_type === "live_probe" || issue.source_type === "live_cached") return "live";
  return labelize(issue.source_type || issue.freshness || "unknown").toLowerCase();
}

function StaleConfigDetails({ issue }: { issue: ReportIssue }) {
  const details = objectValue(issue.details);
  const rows = [
    ["Field", asString(details.field)],
    ["Current value", asString(details.current_value)],
    ["Expected value", asString(details.expected_value)],
    ["Came from", asString(details.where_it_came_from) || asString(details.source)],
    ["Fix in", asString(details.where_to_fix)],
    ["Suggested patch", asString(details.suggested_patch)],
    ["Copy command", asString(details.suggested_copy_command)]
  ].filter(([, value]) => value);
  return (
    <div className="stale-config-details">
      <strong>Stale config details</strong>
      <dl>
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>
              <code>{value}</code>
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function IssueEvidenceDetails({ issue }: { issue: ReportIssue }) {
  const evidence = [
    ...(issue.source_report ? [issue.source_report] : []),
    ...issue.evidence_artifacts
  ].filter(Boolean);
  return (
    <AdvancedDetails
      className="issue-evidence-details"
      summary={`${evidence.length} evidence artifact${evidence.length === 1 ? "" : "s"}`}
      title="Evidence"
    >
      {evidence.length ? (
        <ul className="issue-evidence-list">
          {evidence.map((artifact) => (
            <li key={artifact}>
              <code>{artifact}</code>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState title="No evidence path" detail="This issue was generated from the current API payload." />
      )}
    </AdvancedDetails>
  );
}

function ReportEvidenceGroups({ reportCenter }: { reportCenter: ReportCenter }) {
  const artifactSet = new Set(reportCenter.evidence_artifacts);
  Object.values(reportCenter.last_reports).forEach((path) => {
    if (path) artifactSet.add(path);
  });
  const allArtifacts = Array.from(artifactSet);
  return (
    <AdvancedDetails
      className="section-details report-evidence-details"
      summary={`${allArtifacts.length} raw report link${allArtifacts.length === 1 ? "" : "s"} grouped under Evidence`}
      title="Evidence"
    >
      <div className="report-evidence-groups">
        {reportCenter.sources.map((source) => (
          <article key={source.id}>
            <div>
              <strong>{source.label}</strong>
              <StatusBadge status={source.status} />
            </div>
            <dl>
              <div>
                <dt>Source</dt>
                <dd>{sourceSummaryLabel(source)}</dd>
              </div>
              <div>
                <dt>Last checked</dt>
                <dd>{source.checked_at ? formatDateTime(source.checked_at) : "Not checked"}</dd>
              </div>
              <div>
                <dt>Recheck</dt>
                <dd>
                  <code>{source.recheck_command || "Refresh report center"}</code>
                </dd>
              </div>
              <div>
                <dt>Last report</dt>
                <dd>{source.last_report ? <code>{source.last_report}</code> : "Not run"}</dd>
              </div>
              <div>
                <dt>Source page</dt>
                <dd>
                  <Link to={source.linked_page || "/reports"}>Open page</Link>
                </dd>
              </div>
            </dl>
          </article>
        ))}
      </div>
    </AdvancedDetails>
  );
}

function ReportActionGroups({ issues }: { issues: ReportIssue[] }) {
  const grouped = new Map<string, { actionLabel: string; stageLabel: string; issues: ReportIssue[]; link: string | null }>();
  issues.forEach((issue) => {
    const key = issue.source_action_id || `${issue.source}:${issue.source_stage}`;
    const current = grouped.get(key) ?? {
      actionLabel: issue.source_action_label || issue.source_action_id || "Unlinked issue source",
      stageLabel: issue.source_stage_label || issue.source_stage,
      issues: [],
      link: issue.source_action_link
    };
    current.issues.push(issue);
    grouped.set(key, current);
  });
  const rows = Array.from(grouped.entries()).sort((left, right) => left[1].stageLabel.localeCompare(right[1].stageLabel));

  return (
    <AdvancedDetails
      className="section-details report-action-groups"
      summary={`${rows.length} source action group${rows.length === 1 ? "" : "s"}`}
      title="Action Links"
    >
      {rows.length ? (
        <table className="provider-candidate-table workflow-registry-table">
          <thead>
            <tr>
              <th>Stage</th>
              <th>Action</th>
              <th>Issues</th>
              <th>Open</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([key, row]) => (
              <tr key={key}>
                <td>{row.stageLabel}</td>
                <td>{row.actionLabel}</td>
                <td>{row.issues.length}</td>
                <td>
                  {row.link ? <Link to={row.link}>Open action</Link> : <span className="muted">No action link</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <EmptyState title="No action links" detail="Report issues have not been linked to registry actions yet." />
      )}
    </AdvancedDetails>
  );
}

function sourceSummaryLabel(source: ReportSourceSummary): string {
  if (source.source_type === "test_fixture") return "test";
  if (source.source_type === "not_checked") return "not checked";
  if (source.source_type === "historical_artifact" || source.freshness === "stale" || !source.is_current) return "stale";
  if (source.source_type === "live_probe" || source.source_type === "live_cached") return "live";
  return labelize(source.source_type || source.freshness || "unknown").toLowerCase();
}

function filterReportIssuesForSection(section: ReportsSectionId, issues: ReportIssue[]): ReportIssue[] {
  if (section === "all") return issues;
  if (section === "critical") return issues.filter((issue) => issue.severity === "critical");
  if (section === "warnings") return issues.filter((issue) => issue.severity === "warning");
  if (section === "stale_config") return issues.filter((issue) => issue.classification === "stale_config");
  return issues.filter((issue) => reportIssueMatchesSource(issue, section));
}

function filteredStatusForClass(issues: ReportIssue[], classification: string): string {
  return aggregateIssueStatus(issues.filter((issue) => issue.classification === classification));
}

function filteredStatusForSource(issues: ReportIssue[], source: ReportsSectionId): string {
  return aggregateIssueStatus(issues.filter((issue) => reportIssueMatchesSource(issue, source)));
}

function aggregateIssueStatus(issues: ReportIssue[]): string {
  if (!issues.length) return "not_configured_yet";
  if (issues.some((issue) => issue.severity === "critical")) return "critical";
  if (issues.some((issue) => issue.severity === "warning")) return "warning";
  if (issues.some((issue) => issue.classification === "not_configured_yet")) return "not_configured_yet";
  if (issues.some((issue) => issue.severity === "success")) return "passed";
  return "info";
}

function reportIssueMatchesSource(issue: ReportIssue, source: ReportsSectionId): boolean {
  const text = `${issue.source} ${issue.source_stage} ${issue.title}`.toLowerCase();
  const tokensBySource: Partial<Record<ReportsSectionId, string[]>> = {
    cisco: ["cisco"],
    esxi: ["esxi"],
    netapp: ["netapp", "ontap"],
    firmware: ["firmware"],
    lab_profile: ["lab-profile", "lab_profile", "lab profile", "toolchain", "serial"]
  };
  return (tokensBySource[source] ?? []).some((token) => text.includes(token));
}

type WorkflowStageSnapshot = {
  freshness: string;
  lastChecked: string | null;
  recheckCommand: string;
  sourceType: string;
};

function primaryWorkflowAction(stage: WorkflowStage): WorkflowAction | null {
  return stage.actions.find((action) => action.action_id === stage.primary_action) ?? stage.actions[0] ?? null;
}

function workflowStageSnapshot(stage: WorkflowStage): WorkflowStageSnapshot {
  const traces = stage.actions.map((action) => action.last_run_trace);
  const currentTrace = traces.find((trace) =>
    ["live_probe", "live_cached"].includes(trace.source_type) && trace.freshness === "current"
  );
  const historicalTrace = traces.find((trace) => trace.source_type === "historical_artifact" || trace.freshness === "historical");
  const testTrace = traces.find((trace) => trace.source_type === "test_fixture");
  const selectedTrace = currentTrace ?? historicalTrace ?? testTrace ?? traces[0] ?? null;
  const checkedAtValues = traces
    .map((trace) => trace.finished_at)
    .filter((value): value is string => Boolean(value))
    .sort();
  const lastChecked = checkedAtValues.length ? checkedAtValues[checkedAtValues.length - 1] : null;
  const primary = primaryWorkflowAction(stage);
  return {
    freshness: selectedTrace?.freshness ?? "unknown",
    lastChecked,
    recheckCommand: primary ? workflowActionCopyText(primary) : "",
    sourceType: selectedTrace?.source_type ?? "not_checked"
  };
}

function workflowStageRowSummary(stage: WorkflowStage): string {
  const historical = stage.actions.filter((action) => action.last_run_trace.source_type === "historical_artifact").length;
  const notChecked = stage.actions.filter((action) => action.last_run_trace.source_type === "not_checked").length;
  const parts = [
    `${stage.action_count} action${stage.action_count === 1 ? "" : "s"}`,
    stage.blocked_count ? `${stage.blocked_count} blocked` : "no current registry blocker",
    historical ? `${historical} historical trace${historical === 1 ? "" : "s"}` : "",
    notChecked ? `${notChecked} not checked` : ""
  ].filter(Boolean);
  return parts.join(", ");
}

function minimalStageItemFromWorkflowStage(stage: WorkflowStage, issueCount = 0): MinimalStageItem {
  const primary = primaryWorkflowAction(stage);
  const snapshot = workflowStageSnapshot(stage);
  const blockers = stageBlockers(stage);
  const warnings = stageWarnings(stage);
  const artifacts = workflowStageEvidenceArtifacts(stage);
  const primaryLabel = primary ? minimalWorkflowActionButtonLabel(primary) : "No action";
  const primaryEnabled = primary ? !workflowActionRequiresGuard(primary) : false;
  return {
    advanced_available: true,
    blocker_count: blockers.length || issueCount,
    disabled_reason: primary ? humanizeBlocker(primary.blockers[0] || primary.ui_run_blockers[0] || "Requires guarded workflow") : "No action registered",
    id: stage.stage_id,
    label: minimalStageLabel(stage.stage_id, stage.label),
    last_checked: snapshot.lastChecked,
    next_action: humanizeAction(primary?.next_action || stage.desired_state || "Review this step."),
    one_line_summary: minimalStageSummaryText(stage, blockers, warnings),
    primary_action: primary,
    primary_button_enabled: primaryEnabled,
    primary_button_label: primaryLabel,
    proof_count: artifacts.length,
    secondary_action_label: artifacts.length ? "View proof" : undefined,
    status: stage.current_state
  };
}

function minimalStageLabel(stageId: string, fallback: string): string {
  const labels: Record<string, string> = {
    "build-verification": "Build Verification",
    cisco: "Cisco",
    esxi: "ESXi",
    firmware: "Firmware",
    ilo: "HPE / iLO",
    "lab-profile": "Lab Setup",
    netapp: "NetApp",
    raid: "RAID / Storage"
  };
  return labels[stageId] ?? fallback;
}

function minimalStageSummaryText(stage: WorkflowStage, blockers: string[], warnings: string[]): string {
  if (blockers.length) {
    return humanizeBlocker(blockers[0]);
  }
  if (warnings.length) {
    return humanizeBlocker(warnings[0]);
  }
  if (isReadyStatus(stage.current_state)) {
    return `${minimalStageLabel(stage.stage_id, stage.label)} is ready for the next step.`;
  }
  if (isWaitingStatus(stage.current_state)) {
    return `${minimalStageLabel(stage.stage_id, stage.label)} is waiting on required setup.`;
  }
  return stage.desired_state || "No current blocker is reported.";
}

function stageCurrentSimpleSummary(stage: WorkflowStage): string {
  if (stage.blocked_count) {
    return `${stage.blocked_count} blocker${stage.blocked_count === 1 ? "" : "s"} need attention.`;
  }
  if (isReadyStatus(stage.current_state)) {
    return "Ready.";
  }
  if (isWaitingStatus(stage.current_state)) {
    return "Waiting on setup.";
  }
  return displayStatusLabel(stage.current_state);
}

function minimalWorkflowActionButtonLabel(action: WorkflowAction): string {
  if (workflowActionCanRun(action)) return workflowRunButtonLabel(action);
  if (workflowActionRequiresGuard(action)) return "Guarded workflow";
  return "Review details";
}

function workflowStageEvidenceArtifacts(stage: WorkflowStage): string[] {
  return uniqueStrings([
    ...stage.reports,
    ...stage.actions.flatMap((action) => [
      ...action.reports,
      ...action.evidence_artifacts,
      ...(action.last_run_report ? [action.last_run_report] : []),
      ...action.last_run_trace.report_artifacts
    ])
  ]);
}

function stageCurrentSummary(stage: WorkflowStage): string {
  const snapshot = workflowStageSnapshot(stage);
  const issueText = stage.blocked_count
    ? `${stage.blocked_count} action${stage.blocked_count === 1 ? "" : "s"} have current registry blockers.`
    : "No current registry blocker is reported.";
  const evidenceText =
    snapshot.sourceType === "historical_artifact"
      ? "Last run evidence is historical and requires a recheck before it can be treated as current state."
      : snapshot.sourceType === "not_checked"
        ? "This stage has not been checked in the registry trace."
        : `Latest source is ${labelize(snapshot.sourceType)} with ${labelize(snapshot.freshness)} freshness.`;
  return `${issueText} ${evidenceText}`;
}

function stageBlockers(stage: WorkflowStage): string[] {
  return uniqueStrings(stage.actions.flatMap((action) => [...action.blockers, ...action.last_run_trace.blockers]));
}

function stageWarnings(stage: WorkflowStage): string[] {
  const historicalWarnings = stage.actions
    .filter((action) => action.last_run_trace.source_type === "historical_artifact")
    .map((action) => `${action.label}: historical evidence only; run the recheck command before treating this as current.`);
  return uniqueStrings([
    ...stage.actions.flatMap((action) => action.last_run_trace.warnings),
    ...historicalWarnings
  ]);
}

function workflowIssueCountsByStage(stages: WorkflowStage[], issues: ReportIssue[]): Record<string, number> {
  return stages.reduce<Record<string, number>>((acc, stage) => {
    acc[stage.stage_id] = issues.filter((issue) => reportIssueMatchesStageId(issue, stage.stage_id)).length;
    return acc;
  }, {});
}

function workflowIssueCountsByAction(issues: ReportIssue[]): Record<string, number> {
  return issues.reduce<Record<string, number>>((acc, issue) => {
    if (issue.source_action_id) {
      acc[issue.source_action_id] = (acc[issue.source_action_id] ?? 0) + 1;
    }
    if (issue.auto_fix_action_id && issue.auto_fix_action_id !== issue.source_action_id) {
      acc[issue.auto_fix_action_id] = (acc[issue.auto_fix_action_id] ?? 0) + 1;
    }
    return acc;
  }, {});
}

function reportIssueMatchesStageId(issue: ReportIssue, stageId: string): boolean {
  const normalizedStage = normalizeRegistryKey(stageId);
  return [
    issue.source_stage_id,
    issue.source_stage,
    issue.source,
    issue.source_stage_label
  ]
    .filter(Boolean)
    .some((value) => normalizeRegistryKey(value) === normalizedStage);
}

function normalizeRegistryKey(value: string | null | undefined): string {
  return (value ?? "").toLowerCase().replace(/_/g, "-").replace(/\s+/g, "-");
}

function uniqueStrings(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}

function statusClassName(value: string): string {
  return normalizeRegistryKey(value || "unknown").replace(/[^a-z0-9-]/g, "-");
}

function workflowStageIdForControlSection(sectionId: ControlCenterSectionId): string {
  if (sectionId === "ilo") return "ilo";
  if (sectionId === "raid") return "raid";
  if (sectionId === "esxi") return "esxi";
  if (sectionId === "netapp") return "netapp";
  if (sectionId === "vcenter") return "vcenter";
  if (sectionId === "firmware-upgrade") return "firmware";
  if (sectionId === "verification") return "build-verification";
  if (sectionId === "reports") return "reports";
  if (sectionId === "cisco") return "cisco";
  if (sectionId === "lab-profile") return "lab-profile";
  return "";
}

function SettingsPage({
  health,
  labProfileError,
  labProfileLoading,
  onReload,
  state
}: {
  health: HealthStatus | null;
  labProfileError: string;
  labProfileLoading: boolean;
  onReload: () => Promise<void>;
  state: LabProfileList | null;
}) {
  const [activeSection, setActiveSection] = useState<SettingsSectionId>("mode");
  const [media, setMedia] = useState<MediaInventory | null>(null);
  const [verification, setVerification] = useState<ProviderProbeResult | null>(null);
  const [waiver, setWaiver] = useState<ProviderProbeResult | null>(null);
  const [catalog, setCatalog] = useState<ControlActionCatalog | null>(null);
  const [providerModeSettings, setProviderModeSettings] = useState<ProviderModeSettings | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [modeSaving, setModeSaving] = useState(false);
  const [modeMessage, setModeMessage] = useState("");

  async function load() {
    setError("");
    setLoading(true);
    try {
      const [nextMedia, nextVerification, nextWaiver, nextCatalog, nextProviderModeSettings] = await Promise.all([
        api.mediaInventory(),
        api.buildVerification(),
        api.firmwareWaiverCheck(),
        api.controlActions(),
        api.providerModeSettings()
      ]);
      setMedia(nextMedia);
      setVerification(nextVerification);
      setWaiver(nextWaiver);
      setCatalog(nextCatalog);
      setProviderModeSettings(nextProviderModeSettings);
      await onReload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function saveProviderMode(payload: ProviderModeSettingsWrite) {
    setModeSaving(true);
    setModeMessage("");
    setError("");
    try {
      const nextSettings = await api.updateProviderModeSettings(payload);
      setProviderModeSettings(nextSettings);
      setModeMessage(
        nextSettings.pending_restart
          ? "Provider mode saved. Restart the app for it to take effect."
          : "Provider mode saved and already active."
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setModeSaving(false);
    }
  }

  const activeProfile = state?.active_profile ?? null;
  const credentials = objectValue(verification?.credentials);
  const credentialChecks = recordArray(credentials.checks);
  const toolchain = objectValue(verification?.toolchain);
  const toolchainTools = recordArray(toolchain.tools);
  const flags = Object.entries(catalog?.lab_profile.configured_flags ?? {});
  const mediaItems = media?.items ?? [];
  const sections: SectionOption<SettingsSectionId>[] = [
    { id: "mode", label: "Mode", status: providerModeSettings?.pending_restart ? "pending_restart" : providerModeSettings?.current_mode ?? health?.provider_mode ?? "not_run" },
    { id: "ip-profile", label: "IP Profile", status: activeProfile ? "current" : "not_run" },
    { id: "credentials", label: "Credentials Status", status: asString(credentials.status) || asString(credentials.classification) || "not_run" },
    { id: "media-paths", label: "Media Paths", status: media?.mode ?? "not_run" },
    { id: "toolchain", label: "Toolchain", status: asString(toolchain.status) || "not_run" },
    { id: "feature-flags", label: "Feature Flags", status: flags.length ? "available" : "not_run" },
    { id: "waivers", label: "Waivers", status: waiver?.status ?? "not_run" }
  ];

  return (
    <Page
      activeSection={activeSection}
      description="Lab profile, local settings, and safety metadata without repeating provider diagnostics."
      issueArea="settings"
      onSectionChange={(sectionId) => setActiveSection(sectionId as SettingsSectionId)}
      primaryAction={{ icon: <Layers size={16} />, label: "Open Overview", to: "/overview" }}
      sections={sections}
      title="Settings"
      actions={
        <button onClick={load} disabled={loading || labProfileLoading} type="button">
          <RefreshCw size={16} />
          Refresh
        </button>
      }
    >
      <Feedback loading={loading && !state} error={error || labProfileError} />
      {activeSection === "mode" && (
        <ProviderModeSettingsPanel
          health={health}
          message={modeMessage}
          onSave={saveProviderMode}
          saving={modeSaving}
          settings={providerModeSettings}
        />
      )}
      {activeSection === "ip-profile" && (
        <section className="panel">
          <StatusSummaryCard
            message={activeProfile?.description || "Active lab setup controls the address plan shown throughout the shell."}
            status={activeProfile ? "current" : "not_run"}
            title={activeProfile?.name ?? "No active profile"}
            items={[
              { label: "Mode", value: displayModeLabel(health?.provider_mode ?? "unknown") },
              { label: "Subnet", value: displayAddress(activeProfile?.address_plan.subnet) },
              { label: "Source", value: activeProfile ? labelize(activeProfile.source) : "Unavailable" },
              { label: "Version", value: activeProfile ? `v${activeProfile.version}` : "-" }
            ]}
          />
          {activeProfile ? (
            <AdvancedDetails className="section-details" summary="Address plan and saved profile facts" title="IP profile details">
              <LabAddressSummary profile={activeProfile} />
            </AdvancedDetails>
          ) : (
            <EmptyState title="No active lab setup" detail="Load or create a saved lab setup from Saved Lab Setups." />
          )}
        </section>
      )}
      {activeSection === "credentials" && (
        <section className="panel">
          <StatusSummaryCard
            message={asString(credentials.summary) || "Only configured/missing status is shown. Secret values are never displayed."}
            status={asString(credentials.status) || asString(credentials.classification) || "not_run"}
            title="Credentials status"
            items={[
              { label: "Checks", value: String(credentialChecks.length) },
              { label: "Classification", value: labelize(asString(credentials.classification) || "unknown") }
            ]}
          />
          <AdvancedDetails className="section-details" summary="Presence-only credential check rows" title="Credential checks">
            {credentialChecks.length ? <KeyValueTable rows={credentialChecks} labelKey="field" valueKey="classification" empty="No checks." /> : <EmptyState title="No credential checks" detail="Verification did not include credential status rows." />}
          </AdvancedDetails>
        </section>
      )}
      {activeSection === "media-paths" && (
        <section className="panel">
          <StatusSummaryCard
            message="Media inventory uses redacted metadata only and does not expose local filenames."
            status={media?.mode ?? "not_run"}
            title="Media paths"
            items={[
              { label: "Items", value: String(mediaItems.length) },
              { label: "Firmware", value: String(mediaItems.filter((item) => item.category === "firmware").length) },
              { label: "ISO", value: String(mediaItems.filter((item) => item.category === "iso").length) }
            ]}
          />
          <AdvancedDetails className="section-details" summary="Redacted local media metadata" title="Media inventory">
            {media ? <MediaInventoryCompact inventory={media} /> : <EmptyState title="No media inventory" detail="Media metadata has not loaded." />}
          </AdvancedDetails>
        </section>
      )}
      {activeSection === "toolchain" && (
        <section className="panel">
          <StatusSummaryCard
            message={asString(toolchain.next_safe_action) || "Local tool availability is reported from verification metadata."}
            status={asString(toolchain.status) || "not_run"}
            title="Toolchain"
            items={[
              { label: "Tools", value: String(toolchainTools.length) },
              { label: "Required Missing", value: String(stringArray(toolchain.required_missing).length) },
              { label: "Optional Missing", value: String(stringArray(toolchain.optional_missing).length) }
            ]}
          />
          <AdvancedDetails className="section-details" summary="Tool availability rows" title="Toolchain details">
            {toolchainTools.length ? <KeyValueTable rows={toolchainTools} labelKey="name" valueKey="available" empty="No tools." /> : <EmptyState title="No toolchain report" detail="Run verification to generate local tool availability metadata." />}
          </AdvancedDetails>
        </section>
      )}
      {activeSection === "feature-flags" && (
        <section className="panel">
          <StatusSummaryCard
            message="Feature flags are presence and safety flags from the control catalog."
            status={flags.length ? "available" : "not_run"}
            title="Feature flags"
            items={[
              { label: "Flags", value: String(flags.length) },
              { label: "Enabled", value: String(flags.filter(([, value]) => value).length) },
              { label: "Runtime", value: health?.operator_runtime_mode ? labelize(health.operator_runtime_mode) : "unknown" }
            ]}
          />
          <AdvancedDetails className="section-details" summary="Configured flag values" title="Feature flag details">
            {flags.length ? (
              <div className="provider-fact-grid compact">
                {flags.map(([key, value]) => (
                  <ProviderFact key={key} label={key} value={value ? "true" : "false"} />
                ))}
              </div>
            ) : (
              <EmptyState title="No flags" detail="Control catalog feature flags have not loaded." />
            )}
          </AdvancedDetails>
        </section>
      )}
      {activeSection === "waivers" && (
        <section className="panel">
          <StatusSummaryCard
            message={asString(waiver?.message) || "No waiver metadata has loaded yet."}
            status={waiver?.status ?? "not_run"}
            title="Waivers"
            items={[
              { label: "Blockers", value: String(stringArray(waiver?.blockers).length) },
              { label: "Warnings", value: String(stringArray(waiver?.warnings).length) }
            ]}
          />
          <BlockerSummary blockers={stringArray(waiver?.blockers)} warnings={stringArray(waiver?.warnings)} />
        </section>
      )}
    </Page>
  );
}

function ProviderModeSettingsPanel({
  health,
  message,
  onSave,
  saving,
  settings
}: {
  health: HealthStatus | null;
  message: string;
  onSave: (payload: ProviderModeSettingsWrite) => Promise<void>;
  saving: boolean;
  settings: ProviderModeSettings | null;
}) {
  const [desiredMode, setDesiredMode] = useState<ProviderModeSettingsWrite["desired_mode"]>(
    settings?.desired_mode ?? "local-readonly"
  );
  const [copyMessage, setCopyMessage] = useState("");

  useEffect(() => {
    if (settings?.desired_mode) {
      setDesiredMode(settings.desired_mode);
    }
  }, [settings]);

  const selectedOption = settings?.options.find((option) => option.mode === desiredMode);
  const currentMode = settings?.current_mode ?? health?.provider_mode ?? "unknown";
  const restartCommand = selectedOption?.restart_command ?? settings?.restart_command ?? "";
  const pendingRestart = Boolean(settings?.pending_restart);

  async function copyRestartCommand() {
    setCopyMessage("");
    try {
      await navigator.clipboard.writeText(restartCommand);
      setCopyMessage("Restart command copied.");
    } catch {
      setCopyMessage("Copy is unavailable in this browser session.");
    }
  }

  return (
    <section className="panel provider-mode-panel">
      <StatusSummaryCard
        message={settings?.next_safe_action ?? "Select a provider mode and restart the app."}
        status={pendingRestart ? "pending_restart" : currentMode}
        title="Operational mode"
        items={[
          { label: "Current", value: displayModeLabel(currentMode) },
          { label: "Desired", value: selectedOption?.label ?? displayModeLabel(desiredMode) },
          { label: "Restart", value: pendingRestart ? "Required" : "Not required" },
          { label: "Config", value: settings?.mode_env_path ?? ".local/app-mode.env" }
        ]}
      />
      {settings ? (
        <>
          <div className="provider-mode-option-grid" role="radiogroup" aria-label="Provider mode">
            {settings.options.map((option) => (
              <label
                className={
                  option.mode === desiredMode
                    ? "provider-mode-option selected"
                    : "provider-mode-option"
                }
                key={option.mode}
              >
                <input
                  checked={option.mode === desiredMode}
                  name="provider-mode"
                  onChange={() => setDesiredMode(option.mode)}
                  type="radio"
                />
                <span>
                  <strong>{option.label}</strong>
                  <StatusBadge status={option.status} />
                </span>
                <p>{option.description}</p>
              </label>
            ))}
          </div>
          {selectedOption && selectedOption.requirements.length > 0 && (
            <div className="provider-mode-requirements">
              {selectedOption.requirements.map((requirement) => (
                <div className="provider-issue warning" key={requirement}>
                  <AlertTriangle size={16} />
                  <span>{requirement}</span>
                </div>
              ))}
            </div>
          )}
          <div className="control-command-box">
            <div className="readiness-head">
              <strong>Restart command</strong>
              <button className="small-button" onClick={copyRestartCommand} type="button">
                <Copy size={14} />
                Copy
              </button>
            </div>
            <pre>{restartCommand || "Select a provider mode."}</pre>
          </div>
          {(message || copyMessage) && <div className="feedback">{message || copyMessage}</div>}
          <div className="form-actions">
            <button
              className="primary"
              disabled={saving || desiredMode === settings.desired_mode}
              onClick={() => onSave({ desired_mode: desiredMode })}
              type="button"
            >
              <Save size={16} />
              {saving ? "Saving" : "Save Mode"}
            </button>
          </div>
        </>
      ) : (
        <EmptyState title="Mode settings unavailable" detail="Provider mode settings have not loaded." />
      )}
    </section>
  );
}

function ActionCatalogReadonly({ actions }: { actions: ControlAction[] }) {
  if (!actions.length) {
    return <EmptyState title="No actions" detail="No actions are registered for this section." />;
  }
  return (
    <table className="provider-candidate-table action-catalog-table">
      <thead>
        <tr>
          <th>Action</th>
          <th>Class</th>
          <th>Status</th>
          <th>Report</th>
        </tr>
      </thead>
      <tbody>
        {actions.map((action) => (
          <tr key={`readonly-${action.id}`}>
            <td>
              <strong>{action.label}</strong>
              <span>{action.id}</span>
            </td>
            <td>{classificationLabel(action.classification)}</td>
            <td><StatusBadge status={action.availability} /></td>
            <td>{action.last_report ? <code>{action.last_report}</code> : "No report"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function MediaInventoryCompact({ inventory }: { inventory: MediaInventory }) {
  if (!inventory.items.length) {
    return <EmptyState title="No media metadata" detail="No media metadata was found." />;
  }
  return (
    <table>
      <thead>
        <tr>
          <th>File</th>
          <th>Category</th>
          <th>Extension</th>
          <th>Size</th>
        </tr>
      </thead>
      <tbody>
        {inventory.items.map((item) => (
          <tr key={`${mediaInventoryItemName(item)}-${item.placeholder_name}-${item.source}`}>
            <td>{mediaInventoryItemName(item)}</td>
            <td>{item.category}</td>
            <td>{item.extension || "-"}</td>
            <td>{formatBytes(item.size_bytes)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function mediaInventoryItemName(item: MediaInventory["items"][number] | null | undefined): string {
  return item?.file_name || item?.placeholder_name || "";
}

function classificationLabel(value: ControlAction["classification"]): string {
  if (value === "read-only") return "Read only";
  return labelize(value);
}

function workflowModeLabel(value: WorkflowAction["mode"]): string {
  if (value === "read_only") return "Read only";
  if (value === "report_only") return "Report only";
  return labelize(value);
}

function humanWorkflowActionLabel(action: WorkflowAction): string {
  const mapped: Record<string, string> = {
    "netapp.ontap-upgrade-inventory": "Check ONTAP upgrade package",
    "netapp.ontap-upgrade-plan": "Plan ONTAP upgrade",
    "netapp.ontap-upgrade-validate": "Validate ONTAP upgrade",
    "netapp.setup-apply": "Apply NetApp setup",
    "netapp.setup-preview": "Preview NetApp setup",
    "provider-lab-netapp-ontap-upgrade-validate": "Validate ONTAP upgrade",
    "vcenter.install-apply": "Deploy vCenter",
    "vcenter.attach-esxi-preview": "Preview ESXi attach",
    "vcenter.attach-esxi-apply": "Attach ESXi",
    "vcenter.post-attach-validation": "Validate ESXi attach"
  };
  return mapped[action.action_id] ?? humanizeAction(action.label);
}

function workflowModeClass(value: WorkflowAction["mode"]): string {
  if (value === "read_only" || value === "report_only") return "read-only";
  return value;
}

function workflowActionCanRun(action: WorkflowAction): boolean {
  return action.ui_run_supported && action.current_availability === "available" && action.ui_run_blockers.length === 0;
}

function workflowActionRequiresGuard(action: WorkflowAction): boolean {
  return ["write", "destructive", "upgrade"].includes(action.mode);
}

function workflowActionCanStartGuarded(action: WorkflowAction): boolean {
  return workflowActionRequiresGuard(action) && Boolean(action.guarded_run_supported) && action.guarded_run_blockers.length === 0;
}

function workflowGuardedDisabledReason(action: WorkflowAction): string {
  const reason = action.guarded_run_blockers[0] || action.blockers[0] || action.next_action || "No guarded runner is registered for this action.";
  if (reason.includes("No guarded UI runner allowlist")) {
    return "No guarded runner is implemented for this action yet.";
  }
  return reason;
}

function workflowRunButtonLabel(action: WorkflowAction): string {
  const id = action.action_id;
  if (id.includes("view-active")) return "View Profile";
  if (id.includes("validate-ip-profile")) return "Validate Profile";
  if (id.includes("setup-readiness")) return "Check Setup";
  if (id.includes("setup-plan-preview")) return "Preview Setup";
  if (id.includes("package-inventory")) return "View Packages";
  if (id.includes("waiver-check")) return "Check Waiver";
  if (id.includes("iso-media")) return "Check ISO";
  if (id.includes("installer-boot")) return "Detect Installer";
  if (id.includes("management-validation")) return "Validate Management";
  if (id.includes("ssh-api")) return "Check SSH/API";
  if (id === "raid.discovery") return "Discover RAID";
  if (id === "raid.plan") return "Preview RAID";
  if (id.includes("pending-check")) return "Check Pending";
  if (id.includes("raid.validate")) return "Validate RAID";
  if (id.includes("debug")) return "Collect Debug";
  if (id.includes("post-setup")) return "Validate Setup";
  if (id.includes("nfs-setup-preview")) return "Preview NFS";
  if (id.includes("nfs-setup-validate")) return "Validate NFS";
  if (id.includes("upgrade-inventory")) return "Check Upgrade";
  if (id.includes("upgrade-plan")) return "Plan Upgrade";
  if (id === "firmware.compliance-check") return "Check Compliance";
  if (id.includes("firmware")) return "Check Firmware";
  if (id.includes("reachability")) return "Test Reachability";
  if (id.includes("auth")) return "Check Auth";
  if (id.includes("discover-console") || id.includes("console-autodiscovery") || id.includes("serial-console-discovery")) {
    return "Discover Console";
  }
  if (id.includes("console-read-state")) return "Read Console State";
  if (id.includes("console-login-state")) return "Check Login State";
  if (id.includes("live-state")) return "Read State";
  if (id.includes("inventory")) return "Read Inventory";
  if (id.includes("baseline-preview")) return "Preview Baseline";
  if (id.includes("setup-preview")) return "Preview Setup";
  if (id.includes("vm-deploy-preview")) return "Preview Deploy";
  if (id.includes("datastore-plan")) return "Plan Datastore";
  if (id.includes("privilege")) return "Check Privilege";
  if (id.includes("ssh-scp")) return "Validate SSH/SCP";
  if (id.includes("readiness")) return "Check Readiness";
  if (id.includes("validation") || id.includes("validate")) return "Validate";
  if (id.includes("build-verification")) return "Run Verification";
  if (id.includes("toolchain")) return "Check Toolchain";
  if (id.includes("live-status") || action.mode === "report_only") return "Refresh Status";
  return "Run Check";
}

function guardedWorkflowRunButtonLabel(action: WorkflowAction): string {
  const id = action.action_id;
  if (id.includes("upgrade")) return "Start Upgrade";
  if (id.includes("reset") || id.includes("reload")) return "Reset";
  if (id.includes("rebuild") || id.includes("install")) return "Rebuild";
  if (id.includes("virtual-media")) return "Insert Media";
  if (id.includes("one-time-boot")) return "Set Boot";
  if (id.includes("deploy-apply")) return "Deploy";
  if (id.includes("apply") || id.includes("bootstrap")) return "Apply";
  return action.mode === "destructive" ? "Start" : "Apply";
}

function workflowRunToTrace(run: WorkflowActionRun): WorkflowAction["last_run_trace"] {
  return {
    run_id: run.run_id,
    action_id: run.action_id,
    stage_id: run.stage_id,
    started_at: run.started_at,
    finished_at: run.finished_at,
    status: run.status,
    source_type: run.source_type,
    freshness: run.freshness,
    command: run.command,
    report_artifacts: uniqueStrings([
      ...run.report_artifacts,
      ...(run.trace_artifact ? [run.trace_artifact] : [])
    ]),
    summary: run.summary,
    blockers: run.blockers,
    warnings: run.warnings,
    next_action: run.next_action
  };
}

function workflowActionCopyText(action: WorkflowAction): string {
  if (action.command) return action.command;
  if (action.api_endpoint) return `${action.api_method ?? "GET"} ${action.api_endpoint}`;
  return action.next_action;
}

async function copyWorkflowActionToClipboard(action: WorkflowAction) {
  try {
    await navigator.clipboard.writeText(workflowActionCopyText(action));
  } catch {
    // Copy support depends on browser permissions; the visible command remains available.
  }
}

function ProviderStatusPage() {
  const { activeContext, activeProfile } = useLabProfileContext();
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [ciscoSetupReadiness, setCiscoSetupReadiness] = useState<CiscoSetupReadiness | null>(null);
  const [ciscoSetupWizardPlan, setCiscoSetupWizardPlan] = useState<CiscoSetupWizardPlan | null>(null);
  const [ciscoBootstrapRequirements, setCiscoBootstrapRequirements] = useState<CiscoBootstrapRequirements | null>(null);
  const [ciscoConsoleBootstrapPlan, setCiscoConsoleBootstrapPlan] = useState<CiscoConsoleBootstrapPlan | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyProvider, setBusyProvider] = useState("");
  const [busyPromptReadiness, setBusyPromptReadiness] = useState(false);
  const [busyBootstrapRequirements, setBusyBootstrapRequirements] = useState(false);
  const [probeResults, setProbeResults] = useState<Record<string, ProviderProbeResult>>({});
  const [promptReadinessResult, setPromptReadinessResult] = useState<ProviderProbeResult | null>(null);
  const [firmwareCompliance, setFirmwareCompliance] = useState<ProviderProbeResult | null>(null);
  const [fullRebuildSummary, setFullRebuildSummary] = useState<ProviderProbeResult | null>(null);
  const [buildVerification, setBuildVerification] = useState<ProviderProbeResult | null>(null);
  const [activeProviderSectionId, setActiveProviderSectionId] = useState("ilo");

  async function load() {
    setError("");
    setLoading(true);
    try {
      const [providerStatuses, firmwareGate, fullRebuild, certification] = await Promise.all([
        api.providers(),
        api.firmwareCompliance(),
        api.fullRebuildSummary(),
        api.buildVerification()
      ]);
      setProviders(providerStatuses);
      setFirmwareCompliance(firmwareGate);
      setFullRebuildSummary(fullRebuild);
      setBuildVerification(certification);
      void Promise.allSettled([
        api.ciscoSetupReadiness().then(setCiscoSetupReadiness),
        api.ciscoSetupWizardPlan().then(setCiscoSetupWizardPlan),
        api.ciscoBootstrapRequirements().then(setCiscoBootstrapRequirements),
        api.ciscoConsoleBootstrapPlan().then(setCiscoConsoleBootstrapPlan)
      ]);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function runProbe(provider: ProviderStatus) {
    setBusyProvider(provider.id);
    setError("");
    try {
      const result = await api.probeProvider(provider.id);
      setProbeResults((current) => ({ ...current, [provider.id]: result }));
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyProvider("");
    }
  }

  async function runPromptReadiness() {
    setBusyPromptReadiness(true);
    setError("");
    try {
      const result = await api.ciscoConsolePromptReadiness();
      setPromptReadinessResult(result);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyPromptReadiness(false);
    }
  }

  async function saveBootstrapRequirements(payload: CiscoBootstrapRequirementsUpdate) {
    setBusyBootstrapRequirements(true);
    setError("");
    try {
      const result = await api.saveCiscoBootstrapRequirements(payload);
      setCiscoBootstrapRequirements(result);
      const [providerStatuses, ciscoReadiness, setupWizardPlan, consoleBootstrapPlan] = await Promise.all([
        api.providers(),
        api.ciscoSetupReadiness(),
        api.ciscoSetupWizardPlan(),
        api.ciscoConsoleBootstrapPlan()
      ]);
      setProviders(providerStatuses);
      setCiscoSetupReadiness(ciscoReadiness);
      setCiscoSetupWizardPlan(setupWizardPlan);
      setCiscoConsoleBootstrapPlan(consoleBootstrapPlan);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyBootstrapRequirements(false);
    }
  }

  const orderedProviders = [...providers].sort((left, right) => {
    return providerOrder(left.id) - providerOrder(right.id);
  });
  const ciscoProviders = orderedProviders.filter((provider) =>
    ["cisco-console", "cisco-ansible"].includes(provider.id)
  );
  const iloProvider = orderedProviders.find((provider) => provider.id === "ilo-redfish") ?? null;
  const esxiProvider = orderedProviders.find((provider) => provider.id === "esxi-readonly") ?? null;
  const netappProvider = orderedProviders.find((provider) => provider.id === "netapp-ontap") ?? null;
  const providerSections = useMemo(() => buildProviderSections(orderedProviders), [orderedProviders]);
  const providerSectionIdSignature = providerSections.map((section) => section.id).join("|");
  const selectedProviderSection =
    providerSections.find((section) => section.id === activeProviderSectionId) ??
    providerSections[0] ??
    null;
  const selectedProviders = selectedProviderSection
    ? orderedProviders.filter((provider) => selectedProviderSection.providerIds.includes(provider.id))
    : [];
  const buildStages = useMemo(
    () =>
      buildLabBuildStages({
        buildVerification,
        ciscoBootstrapRequirements,
        ciscoProviders,
        ciscoSetupReadiness,
        esxiProvider,
        firmwareCompliance,
        fullRebuildSummary,
        iloProvider,
        netappProvider
      }),
    [
      buildVerification,
      ciscoBootstrapRequirements,
      ciscoProviders,
      ciscoSetupReadiness,
      esxiProvider,
      firmwareCompliance,
      fullRebuildSummary,
      iloProvider,
      netappProvider
    ]
  );
  const buildOverview = useMemo(
    () => buildLabOverview(buildStages, buildVerification, providers),
    [buildStages, buildVerification, providers]
  );
  const hardwareRows = useMemo(
    () =>
      buildHardwareInventoryRows({
        activeProfile,
        buildVerification,
        ciscoSetupReadiness,
        esxiProvider,
        firmwareCompliance,
        fullRebuildSummary,
        iloProvider,
        netappEnabled: activeContext?.enabled_features.netapp_enabled ?? activeProfile?.features.netapp_enabled ?? true,
        netappProvider,
        orderedProviders
      }),
    [
      activeContext,
      activeProfile,
      buildVerification,
      ciscoSetupReadiness,
      esxiProvider,
      firmwareCompliance,
      fullRebuildSummary,
      iloProvider,
      netappProvider,
      orderedProviders
    ]
  );

  useEffect(() => {
    if (providerSections.length && !providerSections.some((section) => section.id === activeProviderSectionId)) {
      setActiveProviderSectionId(providerSections[0].id);
    }
  }, [activeProviderSectionId, providerSectionIdSignature, providerSections]);

  return (
    <Page
      description="Compact inventory for the active lab setup, live discovery, and current readiness."
      primaryAction={{ icon: <RefreshCw size={16} />, label: "Refresh", onClick: load, disabled: loading || Boolean(busyProvider) }}
      title="Hardware"
      actions={
        <Link className="button-link" to="/control-center">
          <Wrench size={16} />
          Control Center
        </Link>
      }
    >
      <Feedback loading={loading && !providers.length} error={error} />
      <section className="lab-builder-surface">
        <HardwareInventorySummary overview={buildOverview} rows={hardwareRows} />
        <HardwareInventoryTable rows={hardwareRows} />
        {providers.length > 0 ? (
          <AdvancedDetails className="section-details provider-global-evidence" summary="Provider workflow details and proof" title="Provider Proof">
            <BuildOverviewCard overview={buildOverview} />
            <GuidedWorkflowLane stages={buildStages} />
            <section className="build-stage-grid" aria-label="Build stages">
              {buildStages.map((stage) => (
                <BuildStageCard key={stage.id} stage={stage} />
              ))}
            </section>
            <section className="provider-workspace" aria-label="Hardware provider workspace">
              <div className="readiness-head">
                <div>
                  <PanelTitle icon={<Activity size={18} />} title="Provider Workflows" />
                  <p className="muted">Read-only checks, saved intent, and guarded apply paths.</p>
                </div>
              </div>
              <ProviderSectionTabs
                activeSectionId={selectedProviderSection?.id ?? ""}
                busy={Boolean(busyProvider) || busyPromptReadiness || busyBootstrapRequirements}
                onSelect={setActiveProviderSectionId}
                sections={providerSections}
              />
              <div className="provider-status-stack">
                {selectedProviderSection?.id === "cisco" && ciscoSetupReadiness && (
                  <CiscoSetupReadinessPanel
                    bootstrapRequirements={ciscoBootstrapRequirements}
                    busyBootstrapRequirements={busyBootstrapRequirements}
                    consoleBootstrapPlan={ciscoConsoleBootstrapPlan}
                    onSaveBootstrapRequirements={saveBootstrapRequirements}
                    readiness={ciscoSetupReadiness}
                    setupWizardPlan={ciscoSetupWizardPlan}
                  />
                )}
                {selectedProviders.map((provider) => (
                  <ProviderDetailCard
                    busy={busyProvider === provider.id}
                    busyPromptReadiness={busyPromptReadiness}
                    key={provider.id}
                    onProbe={() => runProbe(provider)}
                    onPromptReadiness={runPromptReadiness}
                    promptReadinessResult={promptReadinessResult}
                    provider={provider}
                    probeResult={probeResults[provider.id] ?? null}
                  />
                ))}
              </div>
            </section>
          </AdvancedDetails>
        ) : (
          !loading && <EmptyState title="No hardware providers" detail="Refresh after provider status is available from the backend." />
        )}
        <AdvancedDetails
          className="provider-global-evidence advanced-diagnostics"
          summary="Raw reports, protected actions, command text, and redacted payloads"
          title="Advanced diagnostics"
        >
          <FullRebuildSummaryPanel summary={fullRebuildSummary} />
          <BuildVerificationPanel verification={buildVerification} />
        </AdvancedDetails>
      </section>
    </Page>
  );
}

function BuildOverviewCard({ overview }: { overview: BuildOverview }) {
  return (
    <section className="build-overview-card" aria-labelledby="build-overview-title">
      <div className="build-overview-main">
        <div>
          <p className="eyebrow">Build Overview</p>
          <h2 id="build-overview-title">{displayStatusLabel(overview.overallState)}</h2>
          <p>{overview.currentPhase}</p>
        </div>
        <StatusPill status={overview.overallState} />
      </div>
      <div className="build-overview-grid">
        <NextActionPanel title="Next action" value={overview.nextAction} />
        <NextActionPanel title="Needs attention" value={overview.topBlocker} muted={overview.topBlocker === "No blocker reported."} />
        <NextActionPanel title="Last milestone" value={overview.lastMilestone} />
        <NextActionPanel title="Source" value={overview.mode} />
      </div>
    </section>
  );
}

function NextActionPanel({
  muted = false,
  title,
  value
}: {
  muted?: boolean;
  title: string;
  value: string;
}) {
  return (
    <div className={muted ? "next-action-panel muted-panel" : "next-action-panel"}>
      <span>{title}</span>
      <strong>{value}</strong>
    </div>
  );
}

function GuidedWorkflowLane({ stages }: { stages: BuildStage[] }) {
  return (
    <nav className="guided-workflow-lane" aria-label="Guided build workflow">
      {stages.map((stage, index) => (
        <a className="workflow-step" href={`#stage-${stage.id}`} key={stage.id}>
          <span>{index + 1}</span>
          <strong>{stage.step}</strong>
          <StatusPill status={stage.status} />
        </a>
      ))}
    </nav>
  );
}

function BuildStageCard({ stage }: { stage: BuildStage }) {
  return (
    <article className="build-stage-card" id={`stage-${stage.id}`}>
      <div className="build-stage-head">
        <div>
          <p className="summary-kicker">{stage.step}</p>
          <h2>{stage.title}</h2>
        </div>
        <StatusPill status={stage.status} />
      </div>
      <p className="stage-message">{stage.message}</p>
      <div className="stage-card-grid">
        <NextActionPanel title="Next action" value={stage.nextAction} />
        <NextActionPanel title={stage.metricLabel} value={stage.metricValue} />
      </div>
      {stage.quickFacts && stage.quickFacts.length > 0 && (
        <div className="provider-fact-grid compact">
          {stage.quickFacts.map(([label, value]) => (
            <ProviderFact key={label} label={label} value={value} />
          ))}
        </div>
      )}
      <div className={stage.blocker === "No blocker reported." ? "stage-blocker is-clear" : "stage-blocker"}>
        <strong>{stage.blocker === "No blocker reported." ? "Ready signal" : "Highest-priority blocker"}</strong>
        <p>{stage.blocker}</p>
      </div>
      <details className="stage-details">
        <summary>View details</summary>
        <div>{stage.details}</div>
      </details>
    </article>
  );
}

function StatusPill({ status }: { status: string }) {
  if (isLowSignalStatusBubble(status)) return null;
  return <span className={`status-pillow ${statusTone(status)}`}>{displayStatusLabel(status)}</span>;
}

function buildLabOverview(
  stages: BuildStage[],
  verification: ProviderProbeResult | null,
  providers: ProviderStatus[]
): BuildOverview {
  const firstBlocked = stages.find((stage) => isAttentionStatus(stage.status));
  const firstWaiting = stages.find((stage) => isWaitingStatus(stage.status));
  const currentStage = firstBlocked ?? firstWaiting ?? stages.find((stage) => !isReadyStatus(stage.status)) ?? stages[stages.length - 1];
  const readyStages = stages.filter((stage) => isReadyStatus(stage.status));
  const mode = verification ? resultSourceLabel(verification) : providerSourceOverview(providers);

  return {
    overallState: firstBlocked ? "needs-attention" : firstWaiting ? "waiting" : "ready",
    currentPhase: currentStage ? currentStage.title : "No build stages are loaded yet.",
    nextAction: currentStage?.nextAction || "Refresh status to load the build workflow.",
    topBlocker:
      currentStage?.blocker && currentStage.blocker !== "No blocker reported."
        ? currentStage.blocker
        : currentStage && !isReadyStatus(currentStage.status)
          ? `${currentStage.title} is waiting for its next prerequisite.`
          : "No blocker reported.",
    lastMilestone: readyStages.length ? readyStages[readyStages.length - 1].title : "No completed milestone reported yet.",
    mode
  };
}

function buildLabBuildStages({
  buildVerification,
  ciscoBootstrapRequirements,
  ciscoProviders,
  ciscoSetupReadiness,
  esxiProvider,
  firmwareCompliance,
  fullRebuildSummary,
  iloProvider,
  netappProvider
}: {
  buildVerification: ProviderProbeResult | null;
  ciscoBootstrapRequirements: CiscoBootstrapRequirements | null;
  ciscoProviders: ProviderStatus[];
  ciscoSetupReadiness: CiscoSetupReadiness | null;
  esxiProvider: ProviderStatus | null;
  firmwareCompliance: ProviderProbeResult | null;
  fullRebuildSummary: ProviderProbeResult | null;
  iloProvider: ProviderStatus | null;
  netappProvider: ProviderStatus | null;
}): BuildStage[] {
  const labProfile = objectValue(buildVerification?.lab_ip_profile);
  const expectedProfile = objectValue(labProfile.expected);
  const staleArtifacts = Array.isArray(labProfile.stale_artifact_evidence) ? labProfile.stale_artifact_evidence : [];
  const stages = objectValue(fullRebuildSummary?.stages);
  const firmwareDevices = objectValue(firmwareCompliance?.devices);
  const firmwareComponents = recordArray(firmwareCompliance?.components);
  const firmwareWaiver = objectValue(firmwareCompliance?.waiver);
  const firmwareInventory = objectValue(firmwareCompliance?.inventory);
  const firmwareLiveInventory = objectValue(firmwareInventory.live_inventory);
  const firmwareCiscoInventory = objectValue(firmwareLiveInventory.cisco);
  const firmwareScope = asString(firmwareCompliance?.scope) || "full";
  const raidStage = objectValue(stages.raid || stages.hpe_raid || stages.storage);
  const esxiStage = objectValue(stages.esxi || stages.esxi_install);
  const verificationBlocker = stringArray(buildVerification?.blockers)[0];
  const ciscoBlockers = [
    ...(ciscoSetupReadiness?.blockers ?? []),
    ...ciscoProviders.flatMap((provider) => provider.blockers)
  ];
  const ciscoWarnings = [
    ...(ciscoSetupReadiness?.warnings ?? []),
    ...ciscoProviders.flatMap((provider) => provider.warnings)
  ];
  const ciscoStatus = ciscoSetupReadiness?.phase || providerSectionStatus(ciscoProviders);
  const ciscoConsole = objectValue(ciscoSetupReadiness?.console);
  const ciscoLastPrompt = objectValue(ciscoConsole.last_prompt_readiness);
  const ciscoPromptClassification = objectValue(ciscoLastPrompt.prompt_classification);
  const ciscoPasswordRecovery = objectValue(ciscoSetupReadiness?.password_recovery);
  const ciscoPromptState = asString(ciscoLastPrompt.prompt_state) || asString(ciscoSetupReadiness?.real_lab_run?.prompt_state) || "unknown";
  const ciscoLastClassification =
    asString(ciscoPromptClassification.classification) ||
    asString(ciscoSetupReadiness?.real_lab_run?.prompt_classification) ||
    "unknown";
  const netappConfigured = asBoolean(netappProvider?.configuration.netapp_configured);
  const netappRuntimeState = objectValue(netappProvider?.configuration.runtime_state);
  const netappRuntimeConsole = objectValue(netappRuntimeState.console);
  const labProfileClassification = asString(labProfile.classification);
  const labProfileCurrentBlocker =
    asBoolean(labProfile.is_current) &&
    ["hard_fail", "stale_config", "operator_action_required"].includes(labProfileClassification)
      ? humanizeAction(asString(labProfile.next_action) || labProfileClassification)
      : "No blocker reported.";

  return [
    {
      id: "lab-profile",
      title: "Lab Setup",
      step: "Step 1: Confirm lab setup",
      status: asString(labProfile.status) || asString(labProfile.classification) || "not-configured",
      message: "Confirms the active lab address plan and groups older report references as evidence.",
      nextAction: humanizeAction(asString(labProfile.next_action) || "Confirm the lab setup before running provider stages."),
      metricLabel: "Evidence",
      metricValue: staleArtifacts.length ? "Stale evidence" : "Current profile",
      blocker: labProfileCurrentBlocker,
      detailSummary: "Lab profile, historical evidence, and address plan",
      details: (
        <div className="stage-detail-grid">
          <ProviderFact label="Lab Setup" value={labelize(asString(labProfile.status) || "unknown")} />
          <ProviderFact label="Expected Subnet" value={asString(expectedProfile.subnet) || "Not loaded"} />
          <ProviderFact label="Historical Evidence" value={staleArtifacts.length ? String(staleArtifacts.length) : "None detected"} />
          <ProviderFact label="Source" value={resultSourceLabel(labProfile)} />
          <ProviderFact label="Next Action" value={humanizeAction(asString(labProfile.next_action) || "Confirm the lab setup.")} />
          <JsonDetails title="Advanced lab setup evidence" data={labProfile} />
        </div>
      )
    },
    {
      id: "firmware-compliance",
      title: "Firmware Compliance",
      step: "Step 2: Validate firmware gate",
      status: firmwareCompliance?.status || "not-run",
      message: asString(firmwareCompliance?.message) || "Firmware gate status has not loaded yet.",
      nextAction: humanizeAction(asString(firmwareCompliance?.next_safe_action) || "Run firmware compliance before configuration workflows."),
      metricLabel: "Gate",
      metricValue: displayStatusLabel(firmwareCompliance?.status || "Not run"),
      blocker: humanizeBlocker(stringArray(firmwareCompliance?.blockers)[0] || stringArray(firmwareCompliance?.warnings)[0] || "No blocker reported."),
      detailSummary: "iLO, Cisco, NetApp firmware/OS compliance, waiver, and local media evidence",
      details: (
        <div className="stage-detail-grid">
          <ProviderFact label="iLO" value={displayStatusLabel(asString(objectValue(firmwareDevices.ilo).status) || "unknown")} />
          <ProviderFact label="Cisco" value={displayStatusLabel(asString(objectValue(firmwareDevices.cisco).status) || "unknown")} />
          <ProviderFact label="Cisco Source" value={asString(firmwareCiscoInventory.source) || "unknown"} />
          <ProviderFact label="NetApp" value={displayStatusLabel(asString(objectValue(firmwareDevices.netapp).status) || "unknown")} />
          <ProviderFact label="Scope" value={displayStatusLabel(firmwareScope)} />
          <ProviderFact label="Waiver" value={asBoolean(firmwareWaiver.active) ? "Active" : asBoolean(firmwareWaiver.configured) ? "Invalid" : "None"} />
          <table className="provider-candidate-table span-2">
            <thead>
              <tr>
                <th>Device</th>
                <th>Component</th>
                <th>Status</th>
                <th>Current</th>
                <th>Required</th>
                <th>Next Action</th>
              </tr>
            </thead>
            <tbody>
              {firmwareComponents.slice(0, 9).map((item) => (
                <tr key={asString(item.id)}>
                  <td>{asString(item.device) || "-"}</td>
                  <td>{asString(item.label) || asString(item.id) || "-"}</td>
                  <td>{displayStatusLabel(asString(item.status) || "unknown")}</td>
                  <td>{asString(item.current_version) || "Unknown"}</td>
                  <td>{asString(item.required_version) || stringArray(item.approved_versions).join(", ") || "Manual"}</td>
                  <td>{humanizeAction(asString(item.next_action) || "Review firmware baseline.")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <JsonDetails title="Advanced firmware gate details" data={firmwareCompliance ?? {}} />
        </div>
      )
    },
    {
      id: "cisco",
      title: "Cisco Network",
      step: "Step 3: Recover/configure Cisco",
      status: ciscoStatus,
      message: ciscoSetupReadiness
        ? "Console, bootstrap, and management readiness are grouped here."
        : "Cisco readiness has not loaded yet.",
      nextAction: humanizeAction(
        ciscoSetupReadiness?.next_safe_action ||
          (ciscoProviders[0] ? safeNextAction(ciscoProviders[0]) : "Load Cisco readiness.")
      ),
      metricLabel: "Console",
      metricValue: ciscoSetupReadiness ? displayStatusLabel(ciscoSetupReadiness.console.status) : "Not loaded",
      quickFacts: [
        ["Console Port", asString(ciscoConsole.selected_path) || asString(ciscoConsole.effective_path) || "Not selected"],
        ["Baud", asString(ciscoConsole.baud) || "Not selected"],
        ["Prompt State", labelize(ciscoPromptState)],
        ["Classification", labelize(ciscoLastClassification)],
        ["Password Recovery", asBoolean(ciscoPasswordRecovery.needed) ? "Needed" : "Not indicated"]
      ],
      blocker: humanizeBlocker(ciscoBlockers[0] || ciscoWarnings[0] || "No blocker reported."),
      detailSummary: "Cisco readiness, bootstrap requirements, and provider evidence",
      details: (
        <StageSummaryDetails
          rows={[
            ["Console Port", asString(ciscoConsole.selected_path) || asString(ciscoConsole.effective_path) || "Not selected"],
            ["Baud", asString(ciscoConsole.baud) || "Not selected"],
            ["Prompt State", labelize(ciscoPromptState)],
            ["Classification", labelize(ciscoLastClassification)],
            ["Password Recovery", asBoolean(ciscoPasswordRecovery.needed) ? "Needed" : "Not indicated"],
            ["Next Action", humanizeAction(asString(ciscoPasswordRecovery.next_action) || ciscoSetupReadiness?.next_safe_action || "Load Cisco readiness.")],
            ["Management", ciscoSetupReadiness?.management_configured ? "Configured" : "Not configured yet"],
            ["Planned IP", ciscoSetupReadiness?.planned_management_ip ?? "Not set"],
            ["Bootstrap Requirements", ciscoBootstrapRequirements ? displayStatusLabel(ciscoBootstrapRequirements.status) : "Not loaded"]
          ]}
        />
      )
    },
    {
      id: "hpe-server",
      title: "HPE Server",
      step: "Step 4: Validate iLO/server",
      status: iloProvider?.status || "not-configured",
      message: "Shows whether the server management path is ready before storage and install checks.",
      nextAction: humanizeAction(iloProvider ? safeNextAction(iloProvider) : "Configure the iLO provider settings."),
      metricLabel: "Connection",
      metricValue: iloProvider ? presenceLabel(iloProvider.configuration.host_configured) : "Not loaded",
      blocker: humanizeBlocker(iloProvider?.blockers[0] || iloProvider?.warnings[0] || "No blocker reported."),
      detailSummary: "iLO configuration presence and server readiness",
      details: (
        <StageSummaryDetails
          rows={[
            ["Host", presenceLabel(iloProvider?.configuration.host_configured)],
            ["Username", presenceLabel(iloProvider?.configuration.username_configured)],
            ["Password", presenceLabel(iloProvider?.configuration.password_configured)],
            ["Mode", displayModeLabel(iloProvider?.mode || "unknown")]
          ]}
        />
      )
    },
    {
      id: "raid",
      title: "RAID / Storage",
      step: "Step 5: Validate RAID",
      status: asString(raidStage.status) || stageStatusFromVerification(buildVerification, "RAID"),
      message: "Keeps storage layout and reset evidence behind details until the operator needs it.",
      nextAction: humanizeAction(asString(raidStage.next_action) || asString(raidStage.message) || "Review RAID readiness after server validation."),
      metricLabel: "Result",
      metricValue: displayStatusLabel(asString(raidStage.status) || "Not loaded"),
      blocker: humanizeBlocker(stringArray(raidStage.blockers)[0] || "No blocker reported."),
      detailSummary: "RAID plan, drive inventory, reset state, and validation evidence",
      details: (
        <StageSummaryDetails
          rows={[
            ["Stage", displayStatusLabel(asString(raidStage.status) || "Not loaded")],
            ["Message", humanizeAction(asString(raidStage.message) || "No RAID summary loaded.")],
            ["Blockers", stringArray(raidStage.blockers).length ? String(stringArray(raidStage.blockers).length) : "None reported"]
          ]}
        />
      )
    },
    {
      id: "esxi",
      title: "ESXi Install",
      step: "Step 6: Boot/install ESXi",
      status: asString(esxiStage.status) || esxiProvider?.status || stageStatusFromVerification(buildVerification, "ESXi"),
      message: "Shows install readiness without exposing virtual media and boot internals by default.",
      nextAction: humanizeAction(asString(esxiStage.next_action) || (esxiProvider ? safeNextAction(esxiProvider) : "Review ESXi install readiness.")),
      metricLabel: "Target",
      metricValue: displayStatusLabel(esxiProvider?.status || asString(esxiStage.status) || "Not loaded"),
      blocker: humanizeBlocker(
        stringArray(esxiStage.blockers)[0] ||
          esxiProvider?.blockers[0] ||
          (isWaitingStatus(asString(esxiStage.status) || esxiProvider?.status || "")
            ? "ESXi management is not configured yet."
            : "No blocker reported.")
      ),
      detailSummary: "ESXi target, media, virtual media, and boot readiness evidence",
      details: (
        <StageSummaryDetails
          rows={[
            ["Stage", displayStatusLabel(asString(esxiStage.status) || esxiProvider?.status || "Not loaded")],
            ["Provider", esxiProvider?.name || "ESXi provider not loaded"],
            ["Message", humanizeAction(asString(esxiStage.message) || esxiProvider?.message || "No ESXi summary loaded.")]
          ]}
        />
      )
    },
    {
      id: "netapp",
      title: "NetApp",
      step: "Step 7: Configure NetApp",
      status: netappConfigured ? netappProvider?.status || "ready" : "not-configured",
      message: netappConfigured
        ? "NetApp configured state is verified by live check."
        : "NetApp is not verified yet. Discover the console, read state, then validate setup.",
      nextAction: humanizeAction(netappProvider ? safeNextAction(netappProvider) : "Run NetApp console discovery when this stage is in scope."),
      metricLabel: "Setup",
      metricValue: netappConfigured ? "Verified" : labelize(asString(netappRuntimeState.configured_state) || "Not verified"),
      blocker: humanizeBlocker(
        netappConfigured
          ? netappProvider?.blockers[0] || "No blocker reported."
          : netappProvider?.blockers[0] || "Waiting for NetApp live verification."
      ),
      detailSummary: "NetApp planned targets, readiness buckets, and artifact evidence",
      details: (
        <StageSummaryDetails
          rows={[
            ["Configured", netappConfigured ? "Yes" : "Not configured yet"],
            ["Source", asString(netappProvider?.configuration.netapp_configured_source) || "none"],
            ["Console", asString(netappRuntimeConsole.discovered_port) || "Not detected"],
            ["Manual Env Flag", "Not required"],
            ["Status", displayStatusLabel(netappProvider?.status || "not-configured")],
            ["Next Action", humanizeAction(netappProvider ? safeNextAction(netappProvider) : "Run NetApp console discovery.")]
          ]}
        />
      )
    },
    {
      id: "verification",
      title: "Build Verification",
      step: "Step 8: Run Build Verification",
      status: asString(buildVerification?.certification_state) || buildVerification?.status || "not-run",
      message: "Final certification waits for earlier stages and shows only the top blocker here.",
      nextAction: verificationBlocker
        ? "Resolve the earlier stage blocker, then run Build Verification again."
        : "Run Build Verification after all build stages are ready.",
      metricLabel: "Certification",
      metricValue: displayStatusLabel(asString(buildVerification?.certification_state) || buildVerification?.status || "Not run"),
      blocker: humanizeBlocker(verificationBlocker || "No blocker reported."),
      detailSummary: "Certification result, blockers, checklist, and redacted report evidence",
      details: (
        <StageSummaryDetails
          rows={[
            ["Certification", displayStatusLabel(asString(buildVerification?.certification_state) || buildVerification?.status || "Not run")],
            ["Checked", buildVerification?.checked_at ? formatDateTime(buildVerification.checked_at) : "Not run"],
            ["Blockers", verificationBlocker ? String(stringArray(buildVerification?.blockers).length) : "None reported"]
          ]}
        />
      )
    }
  ];
}

function StageSummaryDetails({ rows }: { rows: Array<[string, string]> }) {
  return (
    <div className="stage-detail-grid">
      {rows.map(([label, value]) => (
        <ProviderFact key={label} label={label} value={value} />
      ))}
      <p className="provider-redaction-note span-2">
        More raw reports, payloads, protected actions, and command details are available in Advanced diagnostics.
      </p>
    </div>
  );
}

function HardwareInventorySummary({
  overview,
  rows
}: {
  overview: BuildOverview;
  rows: HardwareInventoryRow[];
}) {
  const blocked = rows.filter((row) => isAttentionStatus(row.status)).length;
  const notChecked = rows.filter((row) => ["not_checked", "not-configured", "not_configured_yet", "missing-config"].includes(row.status)).length;
  const ready = rows.filter((row) => isReadyStatus(row.status)).length;
  return (
    <section className="hardware-summary-strip" aria-label="Hardware inventory summary">
      <StatusSummaryCard
        message={overview.currentPhase}
        status={blocked ? "blocked" : ready ? "ready" : "not_checked"}
        title="Lab Hardware Inventory"
        items={[
          { label: "Equipment", value: String(rows.length) },
          { label: "Ready", value: String(ready) },
          { label: "Needs Attention", value: String(blocked) },
          { label: "Not Checked", value: String(notChecked) }
        ]}
      />
      <NextActionCard detail={overview.nextAction} />
      <BlockerSummary blockers={blocked ? rows.filter((row) => isAttentionStatus(row.status)).map((row) => `${row.equipment}: ${displayStatusLabel(row.status)}`).slice(0, 3) : []} />
    </section>
  );
}

function HardwareInventoryTable({ rows }: { rows: HardwareInventoryRow[] }) {
  return (
    <section className="panel hardware-inventory-panel" aria-label="Hardware inventory">
      <div className="issue-list-head">
        <PanelTitle icon={<ClipboardList size={18} />} title="Hardware Inventory" />
        <span>{rows.length} rows</span>
      </div>
      <div className="hardware-table-wrap">
        <table className="provider-candidate-table hardware-inventory-table">
          <thead>
            <tr>
              <th>Equipment</th>
              <th>Type</th>
              <th>Role</th>
              <th>OS / Firmware</th>
              <th>Access</th>
              <th>IP / Console</th>
              <th>UID / Username Field</th>
              <th>Status</th>
              <th>Last Checked</th>
              <th>Actions / Configs</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>
                  <strong>{row.equipment}</strong>
                </td>
                <td>{row.type}</td>
                <td>{row.role}</td>
                <td>{row.osFirmware}</td>
                <td>{row.access}</td>
                <td>{row.target}</td>
                <td>{row.usernameField}</td>
                <td><StatusBadge status={row.status} /></td>
                <td>{row.lastChecked ? formatDateTime(row.lastChecked) : "Not checked"}</td>
                <td><HardwareActionsDropdown row={row} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function HardwareActionsDropdown({ row }: { row: HardwareInventoryRow }) {
  return (
    <details className="row-actions-dropdown">
      <summary>Actions</summary>
      <div>
        <ul>
          {row.actions.map((action, index) => (
            <li key={`${row.id}-${action}-${index}`}>{action}</li>
          ))}
        </ul>
        <AdvancedDetails
          className="inline-advanced row-proof-details"
          summary={`${row.evidence.length} proof link${row.evidence.length === 1 ? "" : "s"}`}
          title="Proof"
        >
          <EvidenceList artifacts={row.evidence} empty="No proof artifact is linked to this row yet." />
        </AdvancedDetails>
      </div>
    </details>
  );
}

function buildHardwareInventoryRows({
  activeProfile,
  buildVerification,
  ciscoSetupReadiness,
  esxiProvider,
  firmwareCompliance,
  fullRebuildSummary,
  iloProvider,
  netappEnabled,
  netappProvider,
  orderedProviders
}: {
  activeProfile: LabProfile | null;
  buildVerification: ProviderProbeResult | null;
  ciscoSetupReadiness: CiscoSetupReadiness | null;
  esxiProvider: ProviderStatus | null;
  firmwareCompliance: ProviderProbeResult | null;
  fullRebuildSummary: ProviderProbeResult | null;
  iloProvider: ProviderStatus | null;
  netappEnabled: boolean;
  netappProvider: ProviderStatus | null;
  orderedProviders: ProviderStatus[];
}): HardwareInventoryRow[] {
  const address = activeProfile?.resolved_address_plan ?? activeProfile?.address_plan ?? blankLabAddressPlan();
  const devices = activeProfile?.devices ?? {};
  const ciscoProviders = orderedProviders.filter((provider) => provider.id.startsWith("cisco-"));
  const ciscoConsole = objectValue(ciscoSetupReadiness?.console);
  const ciscoTarget = displayAddress(address.cisco_management);
  const netappRuntimeState = objectValue(netappProvider?.configuration.runtime_state);
  const netappConsole = objectValue(netappRuntimeState.console);
  const stages = objectValue(fullRebuildSummary?.stages);
  const raidStage = objectValue(stages.raid || stages.hpe_raid || stages.storage);
  const rows: HardwareInventoryRow[] = [
    {
      id: "cisco-switch",
      equipment: "Cisco switch",
      type: "Network",
      role: "Management switch",
      osFirmware: firmwareSummary(firmwareCompliance, ["cisco", "ios xe"]) || "IOS XE unknown",
      access: asString(ciscoConsole.selected_path) ? "Console" : "Console / SSH",
      target: asString(ciscoConsole.selected_path) || ciscoTarget,
      usernameField: "CISCO_USERNAME",
      status: providerSectionStatus(ciscoProviders),
      lastChecked: latestCheckedAt(...ciscoProviders.map((provider) => provider.checked_at)),
      actions: hardwareActionsFor("cisco"),
      evidence: uniqueStrings(ciscoProviders.flatMap((provider) => provider.evidence_artifacts))
    },
    {
      id: "hpe-ilo",
      equipment: "HPE iLO",
      type: "Management",
      role: "Server out-of-band",
      osFirmware: firmwareSummary(firmwareCompliance, ["ilo", "hpe ilo"]) || "iLO firmware unknown",
      access: "Redfish HTTPS",
      target: displayAddress(address.ilo),
      usernameField: "ILO_USERNAME",
      status: operatorHardwareStatus(iloProvider?.status, iloProvider),
      lastChecked: latestCheckedAt(iloProvider?.checked_at ?? null, firmwareCompliance?.checked_at ?? null),
      actions: hardwareActionsFor("ilo"),
      evidence: uniqueStrings([...(iloProvider?.evidence_artifacts ?? []), ...probeEvidencePaths(firmwareCompliance)])
    },
    {
      id: "dl360-server",
      equipment: "DL360 server",
      type: "Server",
      role: "ESXi host hardware",
      osFirmware: firmwareSummary(firmwareCompliance, ["bios", "server"]) || "BIOS unknown",
      access: "Through iLO",
      target: displayAddress(address.server_embedded_nic || address.ilo),
      usernameField: "ILO_USERNAME",
      status: operatorHardwareStatus(iloProvider?.status, iloProvider),
      lastChecked: latestCheckedAt(iloProvider?.checked_at ?? null, buildVerification?.checked_at ?? null),
      actions: hardwareActionsFor("server"),
      evidence: uniqueStrings([...(iloProvider?.evidence_artifacts ?? []), ...probeEvidencePaths(buildVerification)])
    },
    {
      id: "smart-array",
      equipment: "Smart Array / RAID",
      type: "Storage controller",
      role: "ESXi boot and datastore layout",
      osFirmware: firmwareSummary(firmwareCompliance, ["smart array", "array"]) || "Smart Array firmware unknown",
      access: "Through iLO",
      target: displayAddress(address.ilo),
      usernameField: "ILO_USERNAME",
      status: asString(raidStage.status) || "not_checked",
      lastChecked: latestCheckedAt(asString(raidStage.checked_at) || null, buildVerification?.checked_at ?? null),
      actions: hardwareActionsFor("raid"),
      evidence: uniqueStrings(probeEvidencePaths(buildVerification))
    },
    {
      id: "esxi-host",
      equipment: "ESXi host",
      type: "Virtualization",
      role: "Compute runtime",
      osFirmware: firmwareSummary(firmwareCompliance, ["esxi", "vmware"]) || "ESXi version unknown",
      access: "HTTPS / SSH / API",
      target: displayAddress(address.esxi_management),
      usernameField: "ESXI_USERNAME",
      status: operatorHardwareStatus(esxiProvider?.status, esxiProvider),
      lastChecked: latestCheckedAt(esxiProvider?.checked_at ?? null, buildVerification?.checked_at ?? null),
      actions: hardwareActionsFor("esxi"),
      evidence: uniqueStrings([...(esxiProvider?.evidence_artifacts ?? []), ...probeEvidencePaths(buildVerification)])
    },
    {
      id: "netapp-controller",
      equipment: "NetApp controller",
      type: "Storage",
      role: "Console bootstrap",
      osFirmware: firmwareSummary(firmwareCompliance, ["netapp", "sp", "bmc"]) || "Controller firmware unknown",
      access: "Serial console",
      target: asString(netappConsole.discovered_port) || displayAddress(address.netapp_controller_a_sp),
      usernameField: "NETAPP_USERNAME",
      status: netappEnabled ? operatorHardwareStatus(netappProvider?.status, netappProvider) : "not_configured_yet",
      lastChecked: latestCheckedAt(netappProvider?.checked_at ?? null, firmwareCompliance?.checked_at ?? null),
      actions: hardwareActionsFor("netapp-controller"),
      evidence: uniqueStrings([...(netappProvider?.evidence_artifacts ?? []), ...probeEvidencePaths(firmwareCompliance)])
    },
    {
      id: "netapp-cluster",
      equipment: "NetApp cluster",
      type: "Storage",
      role: "NFS / iSCSI services",
      osFirmware: firmwareSummary(firmwareCompliance, ["ontap", "netapp"]) || "ONTAP unknown",
      access: "ONTAP REST / SSH",
      target: displayAddress(address.netapp_cluster_mgmt),
      usernameField: "NETAPP_USERNAME",
      status: netappEnabled ? operatorHardwareStatus(netappProvider?.status, netappProvider) : "not_configured_yet",
      lastChecked: latestCheckedAt(netappProvider?.checked_at ?? null, buildVerification?.checked_at ?? null),
      actions: hardwareActionsFor("netapp-cluster"),
      evidence: uniqueStrings([...(netappProvider?.evidence_artifacts ?? []), ...probeEvidencePaths(buildVerification)])
    },
    {
      id: "ups",
      equipment: "UPS",
      type: "Power",
      role: "Power protection",
      osFirmware: "Not inventoried",
      access: "Management / manual",
      target: displayAddress(devices.ups),
      usernameField: "UPS_USERNAME",
      status: devices.ups ? "not_checked" : "not_configured_yet",
      lastChecked: null,
      actions: hardwareActionsFor("ups"),
      evidence: []
    },
    {
      id: "backup-storage",
      equipment: "backup storage",
      type: "Storage",
      role: "Backup target",
      osFirmware: "Not inventoried",
      access: "Management / SMB / NFS",
      target: displayAddress(devices.backup_storage),
      usernameField: "BACKUP_STORAGE_USERNAME",
      status: devices.backup_storage ? "not_checked" : "not_configured_yet",
      lastChecked: null,
      actions: hardwareActionsFor("backup-storage"),
      evidence: []
    },
    {
      id: "utility-vm",
      equipment: "utility VM",
      type: "Utility",
      role: "Control host services",
      osFirmware: "Guest OS unknown",
      access: "SSH",
      target: displayAddress(address.ansible_control_host || devices.utility_vm),
      usernameField: "CONTROL_HOST_USERNAME",
      status: address.ansible_control_host || devices.utility_vm ? "not_checked" : "not_configured_yet",
      lastChecked: buildVerification?.checked_at ?? null,
      actions: hardwareActionsFor("utility-vm"),
      evidence: probeEvidencePaths(buildVerification)
    }
  ];
  return rows;
}

function hardwareActionsFor(kind: string): string[] {
  const shared = ["test access", "refresh inventory", "validation / proof"];
  const networkConfig = ["configure IP", "configure DNS", "configure NTP", "configure SNMP", "configure MTU", "disable IPv6", "block legacy protocols"];
  if (kind === "cisco") return [...shared, "check firmware", ...networkConfig, "enable SSH/SCP", "configure VLAN", "setup preview"];
  if (kind === "ilo") return [...shared, "check firmware", ...networkConfig, "configure virtual media", "setup preview"];
  if (kind === "server") return [...shared, "check firmware", "configure virtual media", "validation / proof"];
  if (kind === "raid") return ["refresh inventory", "setup preview", "validation / proof"];
  if (kind === "esxi") return [...shared, "check firmware", ...networkConfig, "enable SSH/SCP", "setup preview"];
  if (kind === "netapp-controller") return [...shared, "check firmware", "setup preview", "upgrade inventory", "validation / proof"];
  if (kind === "netapp-cluster") return [...shared, "check firmware", ...networkConfig, "choose storage protocol", "setup preview", "upgrade inventory", "upgrade plan", "validation / proof"];
  return [...shared, "configure IP"];
}

function firmwareSummary(probe: ProviderProbeResult | null, tokens: string[]): string {
  const components = recordArray(probe?.components);
  const normalizedTokens = tokens.map((token) => token.toLowerCase());
  const match = components.find((component) => {
    const text = `${asString(component.device)} ${asString(component.label)} ${asString(component.id)}`.toLowerCase();
    return normalizedTokens.some((token) => text.includes(token));
  });
  if (!match) return "";
  const version = asString(match.current_version);
  const status = asString(match.status) || "unknown";
  return version ? `${version} / ${displayStatusLabel(status)}` : displayStatusLabel(status);
}

function operatorHardwareStatus(status: string | undefined, provider?: ProviderStatus | null): string {
  if (!status) return "not_checked";
  if (provider?.source_type === "test_fixture" || provider?.mode === "mock") return "not_checked";
  return status;
}

function latestCheckedAt(...values: Array<string | null | undefined>): string | null {
  const checked = values.filter((value): value is string => Boolean(value));
  if (!checked.length) return null;
  return checked.sort((left, right) => right.localeCompare(left))[0];
}

function FullRebuildSummaryPanel({ summary }: { summary: ProviderProbeResult | null }) {
  const stages = objectValue(summary?.stages);
  const artifacts = objectValue(summary?.artifacts);
  const stageEntries = Object.entries(stages).filter(([, value]) => typeof value === "object" && value !== null);
  return (
    <section className="provider-card provider-card-wide full-rebuild-summary">
      <div className="provider-head">
        <Workflow size={18} />
        <div>
          <h2>Full Lab Rebuild Run</h2>
          <p>{asString(summary?.message) || "No full rebuild summary has been generated yet."}</p>
        </div>
        <StatusBadge status={summary?.status ?? "not-run"} />
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Source" value={resultSourceLabel(summary)} />
        <ProviderFact label="Freshness" value={resultFreshnessLabel(summary)} />
        <ProviderFact label="Checked" value={summary?.checked_at ? formatDateTime(summary.checked_at) : "Not run"} />
        <ProviderFact label="Final Report" value={asString(artifacts.final) || "artifacts/codex-runs/full-device-rebuild-4h-report.md"} />
      </div>
      <ProviderIssueRows blockers={stringArray(summary?.blockers)} warnings={stringArray(summary?.warnings)} />
      {stageEntries.length > 0 && (
        <div className="setup-preview-grid">
          {stageEntries.map(([key, value]) => {
            const stage = objectValue(value);
            return (
              <SetupPreviewBlock
                key={key}
                title={labelize(key)}
                tag={labelize(asString(stage.status) || "unknown")}
                lines={[
                  asString(stage.message) || "No stage message recorded.",
                  ...stringArray(stage.blockers).slice(0, 2)
                ]}
              />
            );
          })}
        </div>
      )}
    </section>
  );
}

function BuildVerificationPanel({ verification }: { verification: ProviderProbeResult | null }) {
  const artifacts = objectValue(verification?.artifacts);
  const failures = Array.isArray(verification?.failures) ? verification.failures : [];
  const checklist = Array.isArray(verification?.post_build_checklist) ? verification.post_build_checklist : [];
  const labProfile = objectValue(verification?.lab_ip_profile);
  const expectedProfile = objectValue(labProfile.expected);
  const staleValues = Array.isArray(labProfile.stale_10_10_8_values) ? labProfile.stale_10_10_8_values : [];
  const staleArtifacts = Array.isArray(labProfile.stale_artifact_evidence) ? labProfile.stale_artifact_evidence : [];
  const credentialChecks = recordArray(objectValue(verification?.credentials).checks);
  const mtu = objectValue(verification?.mtu);
  const protocolChecks = recordArray(objectValue(verification?.protocols).checks);
  const toolchain = objectValue(verification?.toolchain);
  const stagedBlockers = protocolChecks.filter((item) =>
    ["blocked_by_prior_stage", "not_configured_yet", "operator_action_required"].includes(asString(item.classification))
  );
  return (
    <section className="provider-card provider-card-wide full-rebuild-summary">
      <div className="provider-head">
        <ShieldCheck size={18} />
        <div>
          <h2>Build Verification / Product Certification</h2>
          <p>{asString(verification?.message) || "No build verification report has been generated yet."}</p>
        </div>
        <StatusBadge status={verification?.status ?? "not-run"} />
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Source" value={resultSourceLabel(verification)} />
        <ProviderFact label="Freshness" value={resultFreshnessLabel(verification)} />
        <ProviderFact label="Checked" value={verification?.checked_at ? formatDateTime(verification.checked_at) : "Not run"} />
        <ProviderFact label="Certification" value={labelize(asString(verification?.certification_state) || asString(verification?.status) || "not run")} />
        <ProviderFact label="Current Report" value={asString(artifacts.current_state_report) || "artifacts/codex-runs/build-verification-current-state-report.md"} />
        <ProviderFact label="Evidence Report" value={asString(artifacts.evidence_report) || "artifacts/codex-runs/build-verification-evidence-report.md"} />
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Lab Subnet" value={displayAddress(asString(expectedProfile.subnet))} />
        <ProviderFact label="iLO" value={displayAddress(asString(expectedProfile.ilo))} />
        <ProviderFact label="ESXi" value={displayAddress(asString(expectedProfile.esxi_management))} />
        <ProviderFact label="Cisco" value={displayAddress(asString(expectedProfile.cisco_management))} />
        <ProviderFact label="Control Host" value={displayAddress(asString(expectedProfile.ansible_control_host))} />
        <ProviderFact
          label="Stale Evidence"
          value={staleValues.length || staleArtifacts.length ? `${staleValues.length} live, ${staleArtifacts.length} evidence` : "None detected"}
        />
      </div>
      <ProviderIssueRows blockers={stringArray(verification?.blockers)} warnings={stringArray(verification?.warnings)} />
      <ToolchainReadinessPanel toolchain={toolchain} />
      {stagedBlockers.length > 0 && (
        <SetupPreviewBlock
          title="Staged Blockers"
          tag="Ordered"
          lines={stagedBlockers.slice(0, 6).map((item) =>
            `${asString(item.protocol) || "Protocol"}: ${humanizeAction(asString(item.next_action) || asString(item.classification) || "Review stage.")}`
          )}
        />
      )}
      {(failures.length > 0 || checklist.length > 0) && (
        <div className="setup-preview-grid">
          {failures.slice(0, 8).map((item, index) => {
            const failure = objectValue(item);
            return (
              <SetupPreviewBlock
                key={`failure-${index}`}
                title={labelize(asString(failure.category) || "failure")}
                tag={labelize(asString(failure.classification) || "blocked")}
                lines={[
                  asString(failure.ui_message) || "Review certification failure.",
                  asString(failure.report_detail) || "",
                  asString(failure.next_action) || ""
                ].filter(Boolean)}
              />
            );
          })}
          <SetupPreviewBlock
            title="Credential compatibility"
            tag={labelize(asString(objectValue(verification?.credentials).classification) || "unknown")}
            lines={credentialChecks.slice(0, 5).map((item) => {
              const check = objectValue(item);
              return `${asString(check.field) || asString(check.name) || "credential"}: ${labelize(asString(check.classification) || asString(check.status) || "unknown")}`;
            })}
          />
          <SetupPreviewBlock
            title="MTU consistency"
            tag={labelize(asString(mtu.classification) || asString(mtu.status) || "unknown")}
            lines={[
              `Invalid values: ${Object.keys(objectValue(mtu.invalid)).length}`,
              `Path mismatches: ${Array.isArray(mtu.mismatches) ? mtu.mismatches.length : 0}`,
              asString(mtu.next_action) || "Review MTU consistency."
            ]}
          />
          <SetupPreviewBlock
            title="Protocol readiness"
            tag={labelize(asString(objectValue(verification?.protocols).classification) || "unknown")}
            lines={protocolChecks.slice(0, 6).map((item) => {
              const check = objectValue(item);
              return `${asString(check.protocol) || "protocol"}: ${labelize(asString(check.classification) || asString(check.status) || "unknown")}`;
            })}
          />
          {checklist.slice(0, 4).map((item, index) => {
            const check = objectValue(item);
            return (
              <SetupPreviewBlock
                key={`check-${index}`}
                title={asString(check.item) || "Checklist item"}
                tag={labelize(asString(check.status) || "unknown")}
                lines={["Product certification checklist item."]}
              />
            );
          })}
        </div>
      )}
    </section>
  );
}

function ToolchainReadinessPanel({ toolchain }: { toolchain: Record<string, unknown> }) {
  const tools = recordArray(toolchain.tools);
  const managedState = objectValue(toolchain.managed_state);
  const ciscoPlan = objectValue(managedState.cisco);
  const esxiPlan = objectValue(managedState.esxi_vsphere);
  const netappPlan = objectValue(managedState.netapp);
  const hpePlan = objectValue(managedState.hpe_ilo);
  return (
    <div className="toolchain-readiness-panel">
      <div className="provider-head compact-head">
        <Wrench size={18} />
        <div>
          <h3>Toolchain Readiness</h3>
          <p>{asString(toolchain.next_safe_action) || "Run provider-lab-toolchain-check to generate local tool availability."}</p>
        </div>
        <StatusBadge status={asString(toolchain.status) || "not-run"} />
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Required Missing" value={stringArray(toolchain.required_missing).join(", ") || "None"} />
        <ProviderFact label="Optional Missing" value={stringArray(toolchain.optional_missing).join(", ") || "None"} />
        <ProviderFact label="Report" value={asString(objectValue(toolchain.artifacts).report) || "artifacts/codex-runs/toolchain-availability-report.md"} />
      </div>
      <div className="setup-preview-grid">
        <SetupPreviewBlock
          title="Cisco managed state"
          tag="Console first"
          lines={stringArray(ciscoPlan.sequence).slice(0, 4)}
        />
        <SetupPreviewBlock
          title="HPE / iLO managed state"
          tag="Redfish first"
          lines={stringArray(hpePlan.sequence).slice(0, 4)}
        />
        <SetupPreviewBlock
          title="ESXi managed state"
          tag="Kickstart then govc"
          lines={stringArray(esxiPlan.sequence).slice(0, 4)}
        />
        <SetupPreviewBlock
          title="NetApp managed state"
          tag="REST primary"
          lines={stringArray(netappPlan.sequence).slice(0, 4)}
        />
      </div>
      <AdvancedDetails
        className="provider-workflow-details"
        summary="Local tool availability"
        title="Tool availability"
      >
        {tools.length ? (
          <table>
            <thead>
              <tr>
                <th>Tool</th>
                <th>Status</th>
                <th>Required</th>
                <th>Check</th>
              </tr>
            </thead>
            <tbody>
              {tools.map((tool) => (
                <tr key={asString(tool.name)}>
                  <td>{asString(tool.name)}</td>
                  <td>{asBoolean(tool.available) ? "Available" : "Missing"}</td>
                  <td>{asBoolean(tool.required) ? "Yes" : "No"}</td>
                  <td>{asString(tool.check)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">No toolchain report has been generated yet.</p>
        )}
      </AdvancedDetails>
    </div>
  );
}

function ProviderSectionTabs({
  activeSectionId,
  busy,
  onSelect,
  sections
}: {
  activeSectionId: string;
  busy: boolean;
  onSelect: (sectionId: string) => void;
  sections: ProviderSection[];
}) {
  return (
    <div className="provider-section-tabs" role="tablist" aria-label="Provider sections">
      {sections.map((section) => (
        <button
          aria-selected={section.id === activeSectionId}
          className={section.id === activeSectionId ? "active" : ""}
          disabled={busy}
          key={section.id}
          onClick={() => onSelect(section.id)}
          role="tab"
          type="button"
        >
          <span>{section.label}</span>
          <StatusBadge status={section.status} />
        </button>
      ))}
    </div>
  );
}

function CiscoSetupReadinessPanel({
  bootstrapRequirements,
  busyBootstrapRequirements,
  consoleBootstrapPlan,
  onSaveBootstrapRequirements,
  readiness,
  setupWizardPlan
}: {
  bootstrapRequirements: CiscoBootstrapRequirements | null;
  busyBootstrapRequirements: boolean;
  consoleBootstrapPlan: CiscoConsoleBootstrapPlan | null;
  onSaveBootstrapRequirements: (payload: CiscoBootstrapRequirementsUpdate) => Promise<void>;
  readiness: CiscoSetupReadiness;
  setupWizardPlan: CiscoSetupWizardPlan | null;
}) {
  const setupWizardDetected = Boolean(
    setupWizardPlan?.setup_wizard_detected || readiness.setup_wizard_plan?.detected
  );
  const displayedNextAction = setupWizardDetected
    ? "Review setup wizard readiness plan."
    : readiness.next_safe_action;
  const stateBoundaries = objectValue(readiness.state_boundaries);
  const discoveredState = objectValue(stateBoundaries.discovered_current_device_state);
  const savedPlanningState = objectValue(stateBoundaries.saved_kit_config_values);
  const readyToApplyState = objectValue(stateBoundaries.values_ready_to_apply);
  const lastActionState = objectValue(stateBoundaries.last_action_logs_artifacts);
  const lastPrompt = objectValue(readiness.console.last_prompt_readiness);
  const promptClassification = objectValue(lastPrompt.prompt_classification);
  const readTiming = objectValue(readiness.console.read_timing);
  const ethernetReadiness = objectValue(readiness.ethernet_readiness);
  const realLabRun = objectValue(readiness.real_lab_run);
  const ciscoRecoveryAction = needsCiscoPasswordRecoveryAction(realLabRun)
    ? "Recover Cisco password from console."
    : "";

  return (
    <section className="provider-card provider-card-wide cisco-setup-readiness">
      <div className="provider-head">
        <Route size={18} />
        <div>
          <h2>Cisco Setup Readiness</h2>
          <p>Bootstrap preview and SSH/Ansible readiness plan</p>
        </div>
        <StatusBadge status={readiness.phase} />
      </div>
      <div className="provider-callout">
        <strong>{setupWizardDetected ? "Setup wizard detected" : labelize(readiness.phase)}</strong>
        <p>{displayedNextAction}</p>
      </div>
      <div className="provider-fact-grid">
        <ProviderFact label="Planned Management IP" value={readiness.planned_management_ip ?? "-"} />
        <ProviderFact
          label="Management Configured"
          value={readiness.management_configured ? "true" : "false"}
        />
        <ProviderFact label="Console State" value={labelize(readiness.console.status)} />
        <ProviderFact
          label="Prompt Captured"
          value={presenceLabel(lastPrompt.captured ?? discoveredState.prompt_captured)}
        />
        <ProviderFact label="Ansible Path" value={readiness.ansible.enabled ? "Enabled" : "Blocked"} />
      </div>
      <AdvancedDetails
        className="provider-workflow-details"
        summary="Console discovery, bootstrap requirements, command previews, and protected actions"
        title="Cisco workflow details"
      >
      <div className="provider-fact-grid compact">
        <ProviderFact label="Recommended Console" value={readiness.console.recommended_path ?? "-"} />
        <ProviderFact label="Selected Console" value={readiness.console.selected_path ?? readiness.console.effective_path ?? "-"} />
        <ProviderFact label="Baud" value={String(readiness.console.baud ?? "-")} />
        <ProviderFact
          label="Read Timing"
          value={`${asString(readTiming.settle_seconds) || "-"}s settle, ${asString(readTiming.read_window_seconds) || "-"}s read`}
        />
        <ProviderFact
          label="Console Candidates"
          value={`${readiness.console.candidate_count} total, ${readiness.console.stable_candidate_count} stable, ${readiness.console.fallback_candidate_count} fallback`}
        />
        <ProviderFact label="Prompt Readiness" value={readiness.console.safe_next_action} />
      </div>
      <SetupPreviewBlock
        title="Cisco Real-Lab Run"
        tag={labelize(asString(realLabRun.status) || "not-run")}
        lines={[
          `Console adapter detected: ${presenceLabel(realLabRun.console_adapter_detected)}.`,
          `Adapter: ${asString(realLabRun.console_adapter) || "Missing"}.`,
          `Prompt: ${labelize(asString(realLabRun.prompt_state) || "unknown")}, detected: ${presenceLabel(realLabRun.prompt_detected)}.`,
          `Selected baud: ${asString(realLabRun.selected_baud) || "Missing"}.`,
          `Switch identity: ${labelize(asString(realLabRun.switch_identity_status) || "not-captured")}.`,
          `Bootstrap plan: ${labelize(asString(realLabRun.bootstrap_plan_status) || "not-built")}.`,
          `Apply: ${labelize(asString(realLabRun.apply_status) || "not-attempted")}.`,
          `Save/reload: ${asString(realLabRun.save_reload_status) || "not-attempted"}.`,
          `Ethernet management: ${labelize(asString(realLabRun.ethernet_management_status) || "not-attempted")}.`,
          `SSH: ${presenceLabel(realLabRun.ssh_status)}; SCP: ${labelize(asString(realLabRun.scp_status) || "not-attempted")}.`,
          `Last blocker: ${asString(realLabRun.last_blocker) || "None"}.`,
          ciscoRecoveryAction ? `Next action: ${ciscoRecoveryAction}` : ""
        ].filter(Boolean)}
      />
      <div className="setup-preview-grid">
        <SetupPreviewBlock
          title="Current Discovery"
          tag="Observed"
          lines={[
            asString(discoveredState.summary) || "Console discovery state.",
            `Console: ${labelize(asString(discoveredState.console_status) || readiness.console.status)}.`,
            `Selected path: ${asString(discoveredState.selected_path) || "None"}.`,
            `Prompt: ${labelize(asString(discoveredState.prompt_state) || "unknown")}, captured: ${presenceLabel(discoveredState.prompt_captured)}.`,
            `Classification: ${asString(promptClassification.label) || "Unknown prompt"}.`
          ]}
        />
        <SetupPreviewBlock
          title="Saved Planning"
          tag="Planned"
          lines={[
            asString(savedPlanningState.summary) || "Saved planning values are local only.",
            `Management IP: ${asString(savedPlanningState.planned_management_ip) || readiness.planned_management_ip || "Missing"}.`,
            `Prefix: ${asString(savedPlanningState.planned_prefix) || "Missing"}.`,
            "Reachability is not confirmed by planning values."
          ]}
        />
        <SetupPreviewBlock
          title="Ready To Apply"
          tag="Blocked"
          lines={[
            asString(readyToApplyState.summary) || "Apply is disabled.",
            `Ready: ${asBoolean(readyToApplyState.ready) ? "true" : "false"}.`,
            asString(readyToApplyState.reason) || "Guarded apply remains blocked."
          ]}
        />
        <SetupPreviewBlock
          title="Last Action"
          tag="Redacted"
          lines={[
            asString(lastActionState.summary) || "Last action details are redacted.",
            `Last action present: ${presenceLabel(lastActionState.last_action_present)}.`,
            `Checked at: ${asString(lastActionState.checked_at) || "Not recorded"}.`,
            `Prompt state: ${labelize(asString(lastPrompt.prompt_state) || "unknown")}.`,
            `Captured text: ${presenceLabel(lastPrompt.captured)}.`,
            asString(lastPrompt.next_safe_action) || "Prompt readiness has not run in this backend process."
          ]}
        />
      </div>
      {stringArray(lastPrompt.troubleshooting_checklist).length > 0 && (
        <SetupPreviewBlock
          title="No-Output Troubleshooting"
          tag="Read only"
          lines={stringArray(lastPrompt.troubleshooting_checklist)}
        />
      )}
      <div className="setup-preview-grid">
        <SetupPreviewBlock
          title="Bootstrap Preview"
          tag="Plan only"
          lines={readiness.bootstrap_preview.summary}
        />
        <SetupPreviewBlock
          title="Missing Requirements"
          tag="Blocked"
          lines={readiness.bootstrap_preview.missing_requirements}
        />
        <SetupPreviewBlock
          title="Redacted Command Summary"
          tag="Preview"
          lines={readiness.bootstrap_preview.redacted_command_summary}
        />
        <SetupPreviewBlock
          title="SSH/SCP Readiness"
          tag={asBoolean(ethernetReadiness.ready) ? "Ready" : "Blocked"}
          lines={[
            readiness.ssh_scp_readiness.summary,
            `Management configured: ${presenceLabel(ethernetReadiness.management_configured)}.`,
            `Planned IP: ${asString(ethernetReadiness.planned_management_ip) || readiness.planned_management_ip || "Missing"}.`,
            `Prefix: ${asString(ethernetReadiness.planned_prefix) || "Missing"}.`,
            `Gateway configured: ${presenceLabel(ethernetReadiness.planned_gateway)}.`,
            `VLAN: ${asString(ethernetReadiness.management_vlan) || "Missing"}.`,
            `Interface: ${asString(ethernetReadiness.management_interface) || "Missing"}.`,
            `SSH probe: ${labelize(asString(ethernetReadiness.ssh_probe_status) || "skipped")}.`,
            asString(ethernetReadiness.next_safe_action) || "Use console bootstrap before SSH."
          ]}
        />
        <SetupPreviewBlock
          title="Ansible Path"
          tag="Blocked"
          lines={[`Status: ${labelize(readiness.ansible.status)}.`, readiness.ansible.reason]}
        />
        <SetupPreviewBlock
          title="Backup / Report"
          tag="Placeholder"
          lines={[readiness.backup_report.summary]}
        />
      </div>
      {setupWizardPlan && <CiscoSetupWizardPlanPanel plan={setupWizardPlan} />}
      {bootstrapRequirements && (
        <CiscoBootstrapRequirementsPanel
          busy={busyBootstrapRequirements}
          onSave={onSaveBootstrapRequirements}
          requirements={bootstrapRequirements}
        />
      )}
      {consoleBootstrapPlan && <CiscoConsoleBootstrapPlanPanel plan={consoleBootstrapPlan} />}
      <ProviderIssueRows blockers={readiness.blockers} warnings={readiness.warnings} />
      <div className="provider-action-layout">
        <div>
          <h3>Disabled Dangerous Actions</h3>
          <div className="disabled-action-list">
            {readiness.disabled_actions.map((action) => (
              <span className="action-tag disabled" key={action}>
                {action}
              </span>
            ))}
          </div>
        </div>
      </div>
      </AdvancedDetails>
    </section>
  );
}

function CiscoBootstrapRequirementsPanel({
  busy,
  onSave,
  requirements
}: {
  busy: boolean;
  onSave: (payload: CiscoBootstrapRequirementsUpdate) => Promise<void>;
  requirements: CiscoBootstrapRequirements;
}) {
  const items = objectValue(requirements.requirements);
  const managementStrategy = objectValue(items.management_vlan_interface_strategy);
  const domainDns = objectValue(items.domain_dns);
  const localAdmin = objectValue(items.local_admin_username);
  const sshScpPolicy = objectValue(items.ssh_scp_policy);
  const saveBehavior = objectValue(items.save_behavior);
  const confirmations = objectValue(items.confirmation_requirements);
  const [form, setForm] = useState<CiscoBootstrapRequirementsUpdate>(() =>
    bootstrapRequirementsForm(requirements)
  );

  useEffect(() => {
    setForm(bootstrapRequirementsForm(requirements));
  }, [requirements]);

  function update<K extends keyof CiscoBootstrapRequirementsUpdate>(
    field: K,
    value: CiscoBootstrapRequirementsUpdate[K],
  ) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    await onSave({
      ...form,
      management_vlan: form.management_vlan || null,
      management_interface: form.management_interface || null,
      local_admin_username_reference: form.local_admin_username_reference || null,
      operator_notes: form.operator_notes || null,
      dns_servers: form.dns_servers.map((server) => server.trim()).filter(Boolean)
    });
  }

  return (
    <div className="provider-detail-section">
      <div className="provider-callout">
        <strong>Cisco bootstrap requirements</strong>
        <p>{requirements.next_safe_action}</p>
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Status" value={labelize(requirements.status)} />
        <ProviderFact label="Apply Enabled" value={requirements.apply_enabled ? "true" : "false"} />
        <ProviderFact
          label="Management Configured"
          value={requirements.management_configured ? "true" : "false"}
        />
        <ProviderFact label="Save Behavior" value={asBoolean(saveBehavior.enabled) ? "Enabled" : "Disabled"} />
      </div>
      <div className="setup-preview-grid">
        <SetupPreviewBlock
          title="Management Network"
          tag="Requirements"
          lines={[
            requirementLine("Management IP", objectValue(items.planned_management_ip)),
            requirementLine("Subnet / Prefix", objectValue(items.subnet_prefix)),
            requirementLine("Gateway", objectValue(items.gateway)),
            `Management strategy: ${presenceLabel(managementStrategy.configured)}`,
            `VLAN: ${asString(managementStrategy.vlan) || "Missing"}`,
            `Interface: ${asString(managementStrategy.interface) || "Missing"}`
          ]}
        />
        <SetupPreviewBlock
          title="Identity / DNS"
          tag="Requirements"
          lines={[
            requirementLine("Hostname", objectValue(items.hostname)),
            `Domain/DNS: ${presenceLabel(domainDns.configured)}`,
            `Domain: ${asString(domainDns.domain_name) || "Missing"}`,
            `DNS servers: ${stringArray(domainDns.dns_servers).join(", ") || "Missing"}`,
            `Local admin username: ${presenceLabel(localAdmin.configured)} (presence only)`
          ]}
        />
        <SetupPreviewBlock
          title="SSH/SCP And Save"
          tag="Planned only"
          lines={[
            asString(sshScpPolicy.summary) || "SSH/SCP policy is planned only.",
            asString(saveBehavior.summary) || "Save behavior is disabled for now."
          ]}
        />
        <SetupPreviewBlock
          title="Confirmations"
          tag="Required"
          lines={stringArray(confirmations.required)}
        />
      </div>
      <SetupPreviewBlock
        title="Not Attempted"
        tag="Disabled"
        lines={requirements.not_attempted}
      />
      <ProviderIssueRows blockers={requirements.blockers} warnings={requirements.warnings} />
      <form className="form-grid bootstrap-requirements-form" onSubmit={submit}>
        <Field label="Planned Management IP">
          <input
            value={form.planned_management_ip}
            onChange={(event) => update("planned_management_ip", event.target.value)}
          />
        </Field>
        <Field label="Subnet / Prefix">
          <input
            placeholder="/24"
            value={form.subnet_prefix}
            onChange={(event) => update("subnet_prefix", event.target.value)}
          />
        </Field>
        <Field label="Gateway">
          <input value={form.gateway} onChange={(event) => update("gateway", event.target.value)} />
        </Field>
        <Field label="Management VLAN">
          <input
            value={form.management_vlan ?? ""}
            onChange={(event) => update("management_vlan", event.target.value)}
          />
        </Field>
        <Field label="Management Interface">
          <input
            value={form.management_interface ?? ""}
            onChange={(event) => update("management_interface", event.target.value)}
          />
        </Field>
        <Field label="Management Strategy">
          <input
            value={form.management_strategy}
            onChange={(event) => update("management_strategy", event.target.value)}
          />
        </Field>
        <Field label="Hostname">
          <input value={form.hostname} onChange={(event) => update("hostname", event.target.value)} />
        </Field>
        <Field label="Domain">
          <input value={form.domain_name} onChange={(event) => update("domain_name", event.target.value)} />
        </Field>
        <Field label="DNS Servers">
          <input
            value={form.dns_servers.join(", ")}
            onChange={(event) => update("dns_servers", splitCsvInput(event.target.value))}
          />
        </Field>
        <Field label="Username Reference">
          <input
            value={form.local_admin_username_reference ?? ""}
            onChange={(event) => update("local_admin_username_reference", event.target.value)}
          />
        </Field>
        <label className="checkbox-row span-2">
          <input
            checked={form.local_admin_username_configured}
            onChange={(event) => update("local_admin_username_configured", event.target.checked)}
            type="checkbox"
          />
          <span>Local admin username is available as a non-secret reference. Passwords are not collected.</span>
        </label>
        <label className="field span-2">
          <span>Operator Notes</span>
          <textarea
            value={form.operator_notes ?? ""}
            onChange={(event) => update("operator_notes", event.target.value)}
          />
        </label>
        <div className="provider-callout span-2">
          <strong>Apply disabled</strong>
          <p>
            No commands will be generated or sent. Apply disabled. SSH/SCP planned only.
            Save/write memory disabled.
          </p>
        </div>
        <div className="form-actions span-2">
          <button className="primary" disabled={busy} type="submit">
            <Save size={16} />
            {busy ? "Saving" : "Save Bootstrap Requirements"}
          </button>
        </div>
      </form>
    </div>
  );
}

function CiscoSetupWizardPlanPanel({ plan }: { plan: CiscoSetupWizardPlan }) {
  return (
    <div className="provider-detail-section">
      <div className="provider-callout">
        <strong>
          {plan.setup_wizard_detected
            ? "Setup wizard/default prompt planning"
            : "Setup wizard/default prompt readiness plan"}
        </strong>
        <p>{plan.message}</p>
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Detected Prompt State" value={labelize(plan.detected_prompt_state)} />
        <ProviderFact label="Apply Enabled" value={plan.apply_enabled ? "true" : "false"} />
        <ProviderFact label="Status" value={labelize(plan.status)} />
        <ProviderFact label="Next Safe Action" value={plan.next_safe_action} />
      </div>
      <div className="setup-preview-grid">
        <SetupPreviewBlock title="Why Blocked" tag="Apply disabled" lines={plan.why_blocked} />
        <SetupPreviewBlock
          title="Future Guarded Workflow"
          tag="Readiness plan"
          lines={plan.future_guarded_plan_preview}
        />
        <SetupPreviewBlock title="Not Attempted" tag="Disabled" lines={plan.not_attempted} />
        <SetupPreviewBlock title="Disabled Actions" tag="Disabled" lines={plan.disabled_actions} />
      </div>
      <ProviderIssueRows blockers={plan.blockers} warnings={plan.warnings} />
    </div>
  );
}

function SetupPreviewBlock({
  lines,
  tag,
  title
}: {
  lines: string[];
  tag: string;
  title: string;
}) {
  const visibleLines = lines.filter((line) => line.trim().length > 0);
  return (
    <div className="setup-preview-block">
      <div>
        <h3>{title}</h3>
        <span className="action-tag disabled">{tag}</span>
      </div>
      {visibleLines.length > 0 ? (
        visibleLines.map((line) => (
          <p key={line}>{line}</p>
        ))
      ) : (
        <p>No items recorded.</p>
      )}
    </div>
  );
}

function CiscoConsoleBootstrapPlanPanel({ plan }: { plan: CiscoConsoleBootstrapPlan }) {
  const target = objectValue(plan.target);
  const blockerSummary = objectValue(plan.blocker_summary);
  const artifactPreview = objectValue(plan.artifact_preview);
  const [confirmation, setConfirmation] = useState("");
  const confirmationMatches = confirmation === plan.confirmation_phrase;
  const applyDisabled = !confirmationMatches || !plan.execution_supported || !plan.apply_enabled;

  return (
    <div className="provider-detail-section">
      <div className="provider-callout">
        <strong>Guarded Cisco console bootstrap preview</strong>
        <p>{plan.next_safe_action}</p>
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact
          label="Target For This Run"
          value={`${displayAddress(asString(target.required_ip))}${asString(target.required_prefix) || ""}`}
        />
        <ProviderFact label="Netmask" value={asString(target.netmask) || "255.255.255.0"} />
        <ProviderFact label="Prompt State" value={labelize(plan.prompt_state)} />
        <ProviderFact label="Prompt Detail" value={labelize(plan.prompt_detail)} />
        <ProviderFact label="Flow" value={labelize(plan.flow)} />
        <ProviderFact label="Apply Enabled" value={plan.apply_enabled ? "true" : "false"} />
        <ProviderFact label="Execution Supported" value={plan.execution_supported ? "true" : "false"} />
        <ProviderFact label="Serial Writes" value={plan.serial_writes_attempted ? "attempted" : "not attempted"} />
      </div>
      <div className="setup-preview-grid">
        <SetupPreviewBlock title="Summary" tag="Preview" lines={plan.summary} />
        <SetupPreviewBlock title="Intended Steps" tag="Guarded" lines={plan.intended_steps} />
        <SetupPreviewBlock title="Redacted Command Summary" tag="Redacted" lines={plan.redacted_command_summary} />
        <SetupPreviewBlock
          title="Blocker Summary"
          tag="Review"
          lines={[
            `Count: ${asString(blockerSummary.count) || "0"}.`,
            `Prompt blocker: ${presenceLabel(blockerSummary.has_prompt_blocker)}.`,
            `Target blocker: ${presenceLabel(blockerSummary.has_target_blocker)}.`,
            `Requirement blocker: ${presenceLabel(blockerSummary.has_requirement_blocker)}.`
          ]}
        />
        <SetupPreviewBlock
          title="Artifacts"
          tag="Placeholder"
          lines={[
            `Redacted: ${presenceLabel(artifactPreview.redacted)}.`,
            `Raw console log saved: ${presenceLabel(artifactPreview.raw_console_log_saved)}.`,
            asString(artifactPreview.last_action_metadata) || "",
            asString(artifactPreview.missing_artifacts_message) || ""
          ]}
        />
        <SetupPreviewBlock title="Command Preview" tag="Not executed" lines={plan.command_preview} />
        <SetupPreviewBlock
          title="Destructive Actions"
          tag="Disabled"
          lines={plan.destructive_actions_disabled}
        />
      </div>
      <ProviderIssueRows blockers={plan.blockers} warnings={plan.warnings} />
      <div className="form-grid bootstrap-requirements-form">
        <Field label="Exact Confirmation Phrase">
          <input
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
          />
        </Field>
        <div className="provider-callout">
          <strong>Real lab guarded apply</strong>
          <p>
            Disabled unless the exact phrase matches and backend apply support is explicitly enabled.
            No destructive wipe/reset actions are part of this workflow.
          </p>
        </div>
        <div className="form-actions span-2">
          <button className="primary" disabled={applyDisabled} type="button">
            <ShieldCheck size={16} />
            Guarded Apply Disabled
          </button>
        </div>
      </div>
    </div>
  );
}

function ProviderDetailCard({
  busy,
  busyPromptReadiness,
  onProbe,
  onPromptReadiness,
  probeResult,
  promptReadinessResult,
  provider
}: {
  busy: boolean;
  busyPromptReadiness: boolean;
  onProbe: () => void;
  onPromptReadiness: () => void;
  probeResult: ProviderProbeResult | null;
  promptReadinessResult: ProviderProbeResult | null;
  provider: ProviderStatus;
}) {
  const lastResult = (probeResult ?? provider.last_probe_result ?? null) as ProviderProbeResult | null;
  const summary = providerWorkflowSummary(provider, lastResult);

  return (
    <article className="provider-card provider-card-wide">
      <div className="provider-head">
        {providerIcon(provider)}
        <div>
          <h2>{provider.name}</h2>
          <p>{provider.kind}</p>
        </div>
        <StatusBadge status={provider.status} />
      </div>
      <WorkflowSummary
        items={summary.items}
        message={summary.message}
        nextAction={summary.nextAction}
        status={provider.status}
        title={summary.title}
      />
      {provider.id === "cisco-console" && (
        <CiscoConsoleDetails
          busyPromptReadiness={busyPromptReadiness}
          onPromptReadiness={onPromptReadiness}
          promptReadinessResult={promptReadinessResult}
          provider={provider}
        />
      )}
      {provider.id === "ilo-redfish" && <IloRedfishDetails provider={provider} />}
      {provider.id === "netapp-ontap" && <NetAppOntapDetails provider={provider} />}
      {["cisco-ansible", "esxi-readonly"].includes(provider.id) && (
        <ManagementTargetDetails provider={provider} />
      )}
      {!["cisco-console", "ilo-redfish", "netapp-ontap", "cisco-ansible", "esxi-readonly"].includes(provider.id) && (
        <GenericProviderDetails provider={provider} />
      )}
      <ProviderActionRows
        busy={busy}
        disabledActions={provider.disabled_actions}
        onProbe={onProbe}
        safeActions={provider.safe_actions}
      />
      <AdvancedDetails
        className="provider-evidence-panel"
        summary="Configuration facts, blockers, warnings, disabled actions, and raw redacted probe payloads"
        title="Advanced provider evidence"
      >
        <ProviderFactGrid provider={provider} />
        {provider.id !== "netapp-ontap" && (
          <ProviderIssueRows blockers={provider.blockers} warnings={provider.warnings} />
        )}
        {lastResult && (
          <div className="provider-raw-result">
            <div className="provider-fact-grid compact">
              <ProviderFact
                label="Last Probe"
                value={provider.last_probe_time ? formatDateTime(provider.last_probe_time) : "Just now"}
              />
              <ProviderFact label="Result" value={asString(lastResult.status) || "unknown"} />
            </div>
            <p className="provider-redaction-note">
              Probe payloads are shown only after an explicit action; configured endpoints, users, passwords,
              tokens, and cookies are redacted by the backend.
            </p>
            <JsonDetails title="Raw redacted probe result" data={lastResult} />
          </div>
        )}
      </AdvancedDetails>
    </article>
  );
}

function WorkflowSummary({
  items,
  message,
  nextAction,
  status,
  title
}: {
  items: WorkflowSummaryItem[];
  message: string;
  nextAction: string;
  status: string;
  title: string;
}) {
  return (
    <section className="workflow-summary">
      <div className="workflow-summary-main">
        <div>
          <span className="summary-kicker">Current step</span>
          <h3>{title}</h3>
          <p>{message}</p>
        </div>
        <StatusBadge status={status} />
      </div>
      <div className="workflow-summary-grid">
        {items.map((item) => (
          <ProviderFact key={`${item.label}-${item.value}`} label={item.label} value={item.value} />
        ))}
      </div>
      <div className="workflow-next-action">
        <strong>Next recommended action</strong>
        <p>{nextAction}</p>
      </div>
    </section>
  );
}

function AdvancedDetails({
  children,
  className = "",
  summary,
  title
}: {
  children: ReactNode;
  className?: string;
  summary: string;
  title: string;
}) {
  const { isAdvancedMode } = useUiMode();
  return (
    <details className={`advanced-details ${className}`.trim()} open={isAdvancedMode ? true : undefined}>
      <summary>
        <span>{title}</span>
        <small>{summary}</small>
      </summary>
      <div className="advanced-details-body">{children}</div>
    </details>
  );
}

function providerWorkflowSummary(
  provider: ProviderStatus,
  lastResult: ProviderProbeResult | null,
): {
  items: WorkflowSummaryItem[];
  message: string;
  nextAction: string;
  title: string;
} {
  const blocker = provider.blockers[0];
  const warning = provider.warnings[0];
  const lastResultStatus = asString(lastResult?.status);
  const config = provider.configuration;
  const discovery = provider.discovery ?? {};
  const items: WorkflowSummaryItem[] = [
    { label: "Mode", value: labelize(provider.mode) },
    { label: "Status", value: labelize(provider.status) },
    { label: "Last Check", value: lastResultStatus ? labelize(lastResultStatus) : "Not run" },
    { label: "Issue", value: blocker ? "Blocked" : warning ? "Warning" : "None" }
  ];

  if (provider.id === "ilo-redfish") {
    items.push(
      { label: "Connection", value: presenceLabel(config.host_configured) },
      { label: "Hardware", value: asString(discovery.server_model) || asString(discovery.model) || "Not loaded" }
    );
    return {
      items: items.slice(0, 6),
      message: "Use this workflow to confirm iLO, RAID, and ESXi install readiness.",
      nextAction: safeNextAction(provider),
      title: providerSummaryTitle(provider.status, "Server setup workflow is ready to review.")
    };
  }

  if (provider.id === "cisco-console") {
    const counts = objectValue(discovery.candidate_counts);
    items.push(
      { label: "Console", value: asString(discovery.effective_path) ? "Detected" : "Missing" },
      { label: "Candidates", value: asString(counts.total) || "0" }
    );
    return {
      items: items.slice(0, 6),
      message: "Use this workflow to find the console, classify the prompt, and prepare bootstrap safely.",
      nextAction: safeNextAction(provider),
      title: providerSummaryTitle(provider.status, "Cisco console is ready for the next check.")
    };
  }

  if (provider.id === "esxi-readonly") {
    return {
      items,
      message: "Use this workflow to confirm ESXi target readiness without changing the host.",
      nextAction: safeNextAction(provider),
      title: providerSummaryTitle(provider.status, "ESXi checks are available.")
    };
  }

  if (provider.id === "netapp-ontap") {
    return {
      items,
      message: "Use this workflow to review NetApp intent, readiness, and report evidence.",
      nextAction: safeNextAction(provider),
      title: providerSummaryTitle(provider.status, "NetApp readiness can be reviewed.")
    };
  }

  return {
    items,
    message: provider.message,
    nextAction: safeNextAction(provider),
    title: providerSummaryTitle(provider.status, "Provider is ready to review.")
  };
}

function providerSummaryTitle(status: string, readyTitle: string): string {
  if (["blocked", "failed", "unavailable"].includes(status)) {
    return "Needs attention before the next action.";
  }
  if (["missing-config", "missing-console", "needs-selection", "planned-target", "awaiting-bootstrap"].includes(status)) {
    return "Setup is incomplete.";
  }
  return readyTitle;
}

function ProviderFactGrid({ provider }: { provider: ProviderStatus }) {
  return (
    <div className="provider-fact-grid">
      <ProviderFact label="Mode" value={provider.mode} />
      <ProviderFact label="Type" value={provider.kind} />
      <ProviderFact label="Capabilities" value={provider.capabilities.join(", ") || "-"} />
      <ProviderFact label="Safe Next Action" value={safeNextAction(provider)} />
    </div>
  );
}

function ProviderFact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function CiscoConsoleDetails({
  busyPromptReadiness,
  onPromptReadiness,
  promptReadinessResult,
  provider
}: {
  busyPromptReadiness: boolean;
  onPromptReadiness: () => void;
  promptReadinessResult: ProviderProbeResult | null;
  provider: ProviderStatus;
}) {
  const discovery = provider.discovery ?? {};
  const envOverride = objectValue(discovery.env_override);
  const candidates = consoleCandidates(discovery.candidates);
  const candidateCounts = objectValue(discovery.candidate_counts);
  const configuredPortHint = asString(discovery.configured_port_hint) || asString(envOverride.path);
  const effectivePath = asString(discovery.effective_path);
  const selectedPath = asString(promptReadinessResult?.selected_path) || effectivePath;
  const selectedBaud =
    asString(promptReadinessResult?.selected_baud) ||
    asString(promptReadinessResult?.baud) ||
    asString(provider.configuration.baud) ||
    "9600";
  const recommendedPath = asString(discovery.recommended_path);
  const lastConsoleBlocker =
    stringArray(promptReadinessResult?.blockers).slice(-1)[0] ||
    asString(discovery.last_console_blocker) ||
    stringArray(discovery.blockers).slice(-1)[0];
  const operatorMessage = asString(discovery.operator_message);
  const operatorChecklist = stringArray(discovery.operator_checklist);
  const permissionGuidance = asString(discovery.permission_guidance);
  const missingConsole = candidates.length === 0 || asString(discovery.status) === "missing-console";
  const stableCandidates = candidates.filter((candidate) => candidate.stable_path && candidate.exists);
  const fallbackCandidates = candidates.filter((candidate) => !candidate.stable_path && candidate.exists);
  const hasPermissionIssue = candidates.some(
    (candidate) => candidate.exists && (candidate.readable === false || candidate.writable === false)
  );
  const promptReadinessEnabled =
    (provider.mode === "local-readonly" || provider.mode === "local-lab-readwrite") &&
    provider.status === "ready";

  return (
    <div className="provider-detail-section">
      <div className="provider-callout">
        <strong>{labelize(asString(discovery.selection_source) || asString(discovery.status) || "discovery")}</strong>
        <p>{operatorMessage || asString(discovery.safe_next_action) || "Review local console discovery before probing."}</p>
      </div>
      {missingConsole && operatorChecklist.length > 0 && (
        <SetupPreviewBlock
          title="No serial console adapter detected"
          tag="Checklist"
          lines={operatorChecklist}
        />
      )}
      {recommendedPath && (
        <div className="provider-callout">
          <strong>Stable path recommendation</strong>
          <p>Preferred console path: {recommendedPath}. Use this stable path for CISCO_CONSOLE_PORT instead of /dev/ttyUSB0 when possible.</p>
        </div>
      )}
      {!stableCandidates.length && fallbackCandidates.length > 0 && (
        <div className="provider-callout">
          <strong>Fallback serial adapter detected</strong>
          <p>Prefer a stable /dev/serial/by-id path if available. If only fallback paths exist, select the intended adapter before probing.</p>
        </div>
      )}
      {hasPermissionIssue && (
        <div className="provider-callout">
          <strong>Console path permissions</strong>
          <p>{permissionGuidance || "Check dialout group membership and device permissions, then restart the backend shell/session."}</p>
        </div>
      )}
      <div className="provider-fact-grid">
        <ProviderFact
          label="Configured Port Hint"
          value={configuredPortHint || "Not configured"}
        />
        <ProviderFact label="Auto Selected Port" value={selectedPath || "-"} />
        <ProviderFact label="Selected Baud" value={selectedBaud} />
        <ProviderFact label="Candidate Count" value={`${asNumber(candidateCounts.total, candidates.length)}`} />
        <ProviderFact label="Last Console Blocker" value={lastConsoleBlocker || "None"} />
        <ProviderFact label="Recommended Path" value={recommendedPath || "-"} />
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Existing Candidates" value={`${asNumber(candidateCounts.existing, candidates.filter((candidate) => candidate.exists).length)}`} />
        <ProviderFact
          label="Stable / Fallback"
          value={`${asNumber(candidateCounts.stable_existing, candidates.filter((candidate) => candidate.stable_path && candidate.exists).length)} / ${asNumber(candidateCounts.fallback_existing, candidates.filter((candidate) => !candidate.stable_path && candidate.exists).length)}`}
        />
      </div>
      <div className="provider-action-layout">
        <div>
          <h3>Prompt Readiness</h3>
          <div className="provider-action-row">
            <div className="provider-action-item">
              <button
                className={promptReadinessEnabled ? "primary" : ""}
                disabled={!promptReadinessEnabled || busyPromptReadiness}
                onClick={onPromptReadiness}
              >
                <Play size={16} />
                {busyPromptReadiness ? "Checking" : "Prompt Readiness"}
              </button>
              <span className="action-tag read-only">Wake + classify only</span>
              <p>
                Tries discovered console adapters and common Cisco baud rates, then reads the redacted prompt state. No show commands are run by this check.
              </p>
              {!promptReadinessEnabled && (
                <p>
                  Requires PROVIDER_MODE=local-readonly or local-lab-readwrite, lab acknowledgements, and one ready console path.
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
      <AdvancedDetails
        className="provider-workflow-details"
        summary="Discovered adapters, selection ranking, and redacted prompt-readiness payload"
        title="Console evidence"
      >
        <h3>Console Candidates</h3>
        {candidates.length ? (
          <table className="provider-candidate-table">
            <thead>
              <tr>
                <th>Path</th>
                <th>Stable</th>
                <th>Exists</th>
                <th>Access</th>
                <th>Recommendation</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((candidate) => (
                <tr className={candidate.path === effectivePath ? "selected-candidate-row" : ""} key={candidate.path}>
                  <td>
                    <strong>{candidate.path}</strong>
                    {candidate.label && <span>{candidate.label}</span>}
                    <span className="candidate-tags">
                      {candidate.path === effectivePath && <span className="candidate-tag selected">Effective</span>}
                      {candidate.path === recommendedPath && <span className="candidate-tag recommended">Recommended</span>}
                    </span>
                  </td>
                  <td>{yesNo(candidate.stable_path)}</td>
                  <td>{yesNo(candidate.exists)}</td>
                  <td>{accessLabel(candidate)}</td>
                  <td>{labelize(candidate.recommendation)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">No serial console adapter detected. Connect the USB serial adapter and refresh Provider Status.</p>
        )}
      {promptReadinessResult && (
        <div className="provider-raw-result">
          <div className="provider-fact-grid compact">
            <ProviderFact label="Prompt State" value={labelize(asString(promptReadinessResult.prompt_state) || "unknown")} />
            <ProviderFact
              label="Prompt Ready"
              value={asBoolean(promptReadinessResult.prompt_ready) ? "true" : "false"}
            />
            <ProviderFact
              label="Show Commands Allowed"
              value={asBoolean(promptReadinessResult.safe_show_commands_allowed) ? "true" : "false"}
            />
            <ProviderFact label="Selected Port" value={asString(promptReadinessResult.selected_path) || "-"} />
            <ProviderFact
              label="Selected Baud"
              value={asString(promptReadinessResult.selected_baud) || asString(promptReadinessResult.baud) || "-"}
            />
            <ProviderFact
              label="Candidates"
              value={asString(promptReadinessResult.candidate_count) || `${asNumber(candidateCounts.total, candidates.length)}`}
            />
          </div>
          <p className="provider-redaction-note">
            {promptReadinessMessage(promptReadinessResult)}
          </p>
          {stringArray(promptReadinessResult.troubleshooting_checklist).length > 0 && (
            <SetupPreviewBlock
              title="Console port opened, but no prompt text was captured"
              tag="Troubleshooting"
              lines={stringArray(promptReadinessResult.troubleshooting_checklist)}
            />
          )}
          <JsonDetails title="Raw redacted prompt readiness result" data={promptReadinessResult} />
        </div>
      )}
      </AdvancedDetails>
    </div>
  );
}

function IloRedfishDetails({ provider }: { provider: ProviderStatus }) {
  const [readiness, setReadiness] = useState<IloUpgradeReadiness | null>(null);
  const [baselinePreview, setBaselinePreview] = useState<IloBaselinePreview | null>(null);
  const [baselineReadiness, setBaselineReadiness] = useState<IloBaselineReadiness | null>(null);
  const [setupIntent, setSetupIntent] = useState<IloSetupIntent | null>(null);
  const [setupPlan, setSetupPlan] = useState<IloSetupPlanPreview | null>(null);
  const [raidDiscovery, setRaidDiscovery] = useState<HpeStorageDiscovery | null>(null);
  const [raidIntent, setRaidIntent] = useState<HpeRaidIntent | null>(null);
  const [raidPlan, setRaidPlan] = useState<HpeRaidPlanPreview | null>(null);
  const [raidApplyPlan, setRaidApplyPlan] = useState<ProviderProbeResult | null>(null);
  const [raidPending, setRaidPending] = useState<ProviderProbeResult | null>(null);
  const [raidResetPlan, setRaidResetPlan] = useState<ProviderProbeResult | null>(null);
  const [raidAfterResetValidation, setRaidAfterResetValidation] = useState<ProviderProbeResult | null>(null);
  const [esxiInstallReadiness, setEsxiInstallReadiness] = useState<ProviderProbeResult | null>(null);
  const [error, setError] = useState("");
  const [setupError, setSetupError] = useState("");
  const [setupSavedMessage, setSetupSavedMessage] = useState("");
  const [setupBusy, setSetupBusy] = useState(false);
  const [raidError, setRaidError] = useState("");
  const [raidSavedMessage, setRaidSavedMessage] = useState("");
  const [raidBusy, setRaidBusy] = useState(false);
  const [raidPostApplyBusy, setRaidPostApplyBusy] = useState(false);
  const config = provider.configuration;
  const missingFields = stringArray(config.missing_fields);
  const raidPendingState = objectValue(raidPending?.pending);
  const esxiInventory = objectValue(esxiInstallReadiness?.inventory);
  const esxiIso = objectValue(esxiInstallReadiness?.iso);
  const esxiVirtualMedia = objectValue(esxiInstallReadiness?.virtual_media);
  const esxiBoot = objectValue(esxiInstallReadiness?.boot_control);

  useEffect(() => {
    let cancelled = false;
    setError("");
    setSetupError("");
    setRaidError("");
    const appendError = (setter: (value: SetStateAction<string>) => void, message: string) => {
      setter((current) => (current ? `${current}; ${message}` : message));
    };
    const loadPart = <T,>(
      label: string,
      promise: Promise<T>,
      onValue: (value: T) => void,
      onError: (message: string) => void
    ) => {
      promise
        .then((value) => {
          if (!cancelled) {
            onValue(value);
          }
        })
        .catch((err: Error) => {
          if (!cancelled) {
            const message = err instanceof Error ? err.message : String(err);
            onError(`${label}: ${message}`);
          }
        });
    };

    loadPart("iLO upgrade readiness", api.iloUpgradeReadiness(), setReadiness, (message) => appendError(setError, message));
    loadPart("iLO baseline preview", api.iloBaselinePreview(), setBaselinePreview, (message) => appendError(setError, message));
    loadPart("iLO baseline readiness", api.iloBaselineReadiness(), setBaselineReadiness, (message) => appendError(setError, message));
    loadPart("iLO setup intent", api.iloSetupIntent(), setSetupIntent, (message) => appendError(setSetupError, message));
    loadPart("iLO setup plan", api.iloSetupPlanPreview(), setSetupPlan, (message) => appendError(setSetupError, message));
    loadPart("HPE storage discovery", api.hpeStorageDiscovery(), setRaidDiscovery, (message) => appendError(setRaidError, message));
    loadPart("HPE RAID intent", api.hpeRaidIntent(), setRaidIntent, (message) => appendError(setRaidError, message));
    loadPart("HPE RAID plan", api.hpeRaidPlanPreview(), setRaidPlan, (message) => appendError(setRaidError, message));
    loadPart("HPE RAID apply plan", api.hpeRaidApplyPlan(), setRaidApplyPlan, (message) => appendError(setRaidError, message));
    loadPart("HPE RAID pending check", api.hpeRaidPending(), setRaidPending, (message) => appendError(setRaidError, message));
    loadPart("HPE RAID reset plan", api.hpeRaidResetPlan(), setRaidResetPlan, (message) => appendError(setRaidError, message));
    loadPart("ESXi install readiness", api.esxiInstallReadiness(), setEsxiInstallReadiness, (message) => appendError(setRaidError, message));
    return () => {
      cancelled = true;
    };
  }, [provider.last_probe_time, provider.status]);

  async function saveSetupIntent(payload: IloSetupIntentWrite) {
    setSetupBusy(true);
    setSetupError("");
    setSetupSavedMessage("");
    try {
      const saved = await api.saveIloSetupIntent(payload);
      const plan = await api.iloSetupPlanPreview();
      setSetupIntent(saved);
      setSetupPlan(plan);
      setSetupSavedMessage("Saved desired iLO setup intent. Apply remains disabled.");
    } catch (err) {
      setSetupError((err as Error).message);
    } finally {
      setSetupBusy(false);
    }
  }

  async function saveRaidIntent(payload: HpeRaidIntentWrite) {
    setRaidBusy(true);
    setRaidError("");
    setRaidSavedMessage("");
    try {
      const saved = await api.saveHpeRaidIntent(payload);
      const [discovery, plan] = await Promise.all([
        api.hpeStorageDiscovery(),
        api.hpeRaidPlanPreview()
      ]);
      const applyPlan = await api.hpeRaidApplyPlan();
      const [pending, resetPlan] = await Promise.all([
        api.hpeRaidPending(),
        api.hpeRaidResetPlan()
      ]);
      setRaidIntent(saved);
      setRaidDiscovery(discovery);
      setRaidPlan(plan);
      setRaidApplyPlan(applyPlan);
      setRaidPending(pending);
      setRaidResetPlan(resetPlan);
      setRaidSavedMessage("Saved desired RAID layout. Wipe and RAID apply remain disabled.");
    } catch (err) {
      setRaidError((err as Error).message);
    } finally {
      setRaidBusy(false);
    }
  }

  async function refreshRaidPostApply() {
    setRaidPostApplyBusy(true);
    setRaidError("");
    try {
      const [pending, resetPlan] = await Promise.all([
        api.hpeRaidPending(),
        api.hpeRaidResetPlan()
      ]);
      setRaidPending(pending);
      setRaidResetPlan(resetPlan);
    } catch (err) {
      setRaidError((err as Error).message);
    } finally {
      setRaidPostApplyBusy(false);
    }
  }

  async function validateRaidAfterReset() {
    setRaidPostApplyBusy(true);
    setRaidError("");
    try {
      const validation = await api.validateHpeRaidAfterReset();
      const [discovery, pending, esxiReadiness] = await Promise.all([
        api.hpeStorageDiscovery(),
        api.hpeRaidPending(),
        api.esxiInstallReadiness()
      ]);
      setRaidAfterResetValidation(validation);
      setRaidDiscovery(discovery);
      setRaidPending(pending);
      setEsxiInstallReadiness(esxiReadiness);
    } catch (err) {
      setRaidError((err as Error).message);
    } finally {
      setRaidPostApplyBusy(false);
    }
  }

  async function refreshEsxiInstallReadiness() {
    setRaidPostApplyBusy(true);
    setRaidError("");
    try {
      setEsxiInstallReadiness(await api.esxiInstallReadiness());
    } catch (err) {
      setRaidError((err as Error).message);
    } finally {
      setRaidPostApplyBusy(false);
    }
  }

  return (
    <div className="provider-detail-section">
      <div className="provider-callout">
        <strong>{missingFields.length ? "Configuration missing" : "Configuration present"}</strong>
        <p>
          iLO host, username, and password values are stored only in local environment configuration and
          are exposed here as presence flags.
        </p>
      </div>
      <div className="provider-fact-grid">
        <ProviderFact label="Host" value={presenceLabel(config.host_configured)} />
        <ProviderFact label="Username" value={presenceLabel(config.username_configured)} />
        <ProviderFact
          label="Password"
          value={presenceLabel(config.password_configured)}
        />
        <ProviderFact
          label="TLS Verify"
          value={asBoolean(config.tls_verify) ? "Enabled" : "Disabled"}
        />
      </div>
      {missingFields.length > 0 && (
        <p className="provider-missing-fields">
          Missing local settings: {missingFields.join(", ")}
        </p>
      )}
      <div className="beginner-checklist">
        <SetupPreviewBlock
          title="Server"
          tag={provider.status === "ready" ? "Detected" : labelize(provider.status)}
          lines={[
            `Model: ${asString(esxiInventory.model) || "Checking through iLO"}.`,
            `Power: ${asString(esxiInventory.power_state) || "Unknown"}.`,
            `Connection settings: ${missingFields.length ? "missing fields" : "present"}.`
          ]}
        />
        <SetupPreviewBlock
          title="RAID"
          tag={labelize(asString(raidPlan?.status) || "not loaded")}
          lines={[
            `Drives: ${String(raidDiscovery?.physical_drives.length ?? 0)}.`,
            `Logical drives: ${String(raidDiscovery?.logical_drives.length ?? 0)}.`,
            `Pending reset: ${presenceLabel(raidPendingState.reset_required)}.`
          ]}
        />
        <SetupPreviewBlock
          title="ESXi Install"
          tag={labelize(asString(esxiInstallReadiness?.status) || "not loaded")}
          lines={[
            `ISO ready: ${presenceLabel(esxiIso.ready)}.`,
            `Virtual media: ${presenceLabel(esxiVirtualMedia.supported)}.`,
            `One-time boot: ${presenceLabel(esxiBoot.one_time_boot_supported)}.`
          ]}
        />
        <SetupPreviewBlock
          title="iLO Baseline"
          tag={baselinePreview?.apply_enabled ? "Apply enabled" : "Preview only"}
          lines={[
            `Kit: ${baselinePreview?.kit_profile.kit_id ?? "Not loaded"}.`,
            `Discovery: ${baselinePreview ? `${baselinePreview.discovery_range.default_start_host} to ${baselinePreview.discovery_range.default_end_host}` : "Not loaded"}.`,
            `Reset required: ${baselinePreview ? yesNo(baselinePreview.reset_required) : "Not loaded"}.`
          ]}
        />
      </div>
      <AdvancedDetails
        className="provider-workflow-details"
        summary="Kit profile, discovery range, readiness, expected baseline, and compare plan"
        title="iLO Baseline Configuration"
      >
      <IloBaselinePreviewPanel
        error={error}
        preview={baselinePreview}
        readiness={baselineReadiness}
      />
      </AdvancedDetails>
      <AdvancedDetails
        className="provider-workflow-details"
        summary="Desired iLO hostname, IP, DNS, NTP, SNMP, and local user references"
        title="iLO settings"
      >
      <IloSetupIntentPanel
        busy={setupBusy}
        error={setupError}
        intent={setupIntent}
        onSave={saveSetupIntent}
        plan={setupPlan}
        savedMessage={setupSavedMessage}
      />
      </AdvancedDetails>
      <section className="provider-core-workflow">
        <div className="readiness-head">
          <PanelTitle icon={<HardDrive size={18} />} title="HPE Storage / RAID" />
          <StatusBadge status={asString(raidPlan?.status) || "not_loaded"} />
        </div>
      <HpeRaidSetupPanel
        busy={raidBusy}
        applyPlan={raidApplyPlan}
        afterResetValidation={raidAfterResetValidation}
        discovery={raidDiscovery}
        error={raidError}
        intent={raidIntent}
        onSave={saveRaidIntent}
        onRefreshPostApply={refreshRaidPostApply}
        onValidateAfterReset={validateRaidAfterReset}
        pending={raidPending}
        plan={raidPlan}
        postApplyBusy={raidPostApplyBusy}
        resetPlan={raidResetPlan}
        savedMessage={raidSavedMessage}
      />
      </section>
      <AdvancedDetails
        className="provider-workflow-details"
        summary="Virtual media, ISO, one-time boot, BIOS, and installer readiness"
        title="ESXi install readiness"
      >
      <EsxiInstallReadinessPanel
        busy={raidPostApplyBusy}
        onRefresh={refreshEsxiInstallReadiness}
        readiness={esxiInstallReadiness}
      />
      </AdvancedDetails>
      <AdvancedDetails
        className="provider-workflow-details"
        summary="Firmware, upgrade readiness, and protected iLO actions"
        title="Firmware and advanced iLO checks"
      >
      <IloUpgradeDecisionPanel error={error} readiness={readiness} />
      </AdvancedDetails>
    </div>
  );
}

function IloBaselinePreviewPanel({
  error,
  preview,
  readiness
}: {
  error: string;
  preview: IloBaselinePreview | null;
  readiness: IloBaselineReadiness | null;
}) {
  if (!preview) {
    return (
      <div className="provider-detail-section ilo-baseline-preview">
        <div className="provider-callout">
          <strong>iLO Baseline Configuration</strong>
          <p>{error || "Baseline preview has not loaded yet."}</p>
        </div>
      </div>
    );
  }

  const kit = preview.kit_profile;
  const discovery = preview.discovery_range;
  const checks = readiness?.connection_readiness ?? preview.connection_readiness;
  const sectionTitles = preview.expected_baseline_sections.map((section) => section.title);
  const blockers = preview.blockers.map((blocker) => blocker.problem);
  const warningLines = [...preview.warnings, ...blockers];
  const sectionById = new Map(preview.expected_baseline_sections.map((section) => [section.id, section]));
  const users = objectValue(sectionById.get("users")?.items);
  const snmp = objectValue(sectionById.get("snmp")?.items);
  const snmpv3 = objectValue(sectionById.get("snmpv3")?.items);
  const alerts = objectValue(sectionById.get("alert_destinations")?.items);
  const ipv6 = objectValue(sectionById.get("ipv6_dedicated")?.items);
  const time = objectValue(sectionById.get("sntp_time")?.items);

  return (
    <div className="provider-detail-section ilo-baseline-preview">
      <div className="provider-callout">
        <strong>Apply disabled</strong>
        <p>{preview.apply_reason}</p>
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Provider" value={`${preview.provider_id} via ${preview.source_provider_id}`} />
        <ProviderFact label="Mode" value={displayModeLabel(preview.provider_mode)} />
        <ProviderFact label="Source" value={`${labelize(preview.source_type)} / ${labelize(preview.freshness)}`} />
        <ProviderFact label="Generated" value={formatDateTime(preview.generated_at)} />
      </div>
      <div className="setup-preview-grid ilo-baseline-grid">
        <SetupPreviewBlock
          title="Kit Profile"
          tag={labelize(kit.freshness)}
          lines={[
            `KitID: ${kit.kit_id}.`,
            `SupportUnit: ${kit.support_unit}.`,
            `SubnetMask: ${kit.subnet_mask}.`,
            `Gateway: ${kit.gateway}.`,
            `DomDC: ${kit.dom_dc}.`,
            `Derived subnet: ${kit.derived_subnet}.`
          ]}
        />
        <SetupPreviewBlock
          title="Discovery"
          tag={discovery.override_supported ? "Override ready" : "Default only"}
          lines={[
            `Default range: ${discovery.default_start_host} through ${discovery.default_end_host}.`,
            `${discovery.addresses.length} addresses: ${discovery.addresses.join(", ") || "not available"}.`,
            "Ping alone is not treated as ready."
          ]}
        />
        <SetupPreviewBlock
          title="Connection Readiness"
          tag={labelize(preview.freshness)}
          lines={checks.map((check) => `${check.name}: ${labelize(check.current)} -> ${check.desired}.`)}
        />
        <SetupPreviewBlock
          title="Expected Baseline"
          tag="Preview only"
          lines={sectionTitles}
        />
        <SetupPreviewBlock
          title="Users / License"
          tag="Secret refs"
          lines={[
            `Admin: ${baselineDisplayValue(users.admin_account)}.`,
            `Operator: ${baselineDisplayValue(users.operator_account)}.`,
            `Service: ${baselineDisplayValue(users.service_admin_account)}.`,
            `License: ${baselineDisplayValue(preview.current_state.license_status)}.`
          ]}
        />
        <SetupPreviewBlock
          title="SNMP / Alerts"
          tag="Reconcile"
          lines={[
            `Contact: ${baselineDisplayValue(snmp.system_contact)}.`,
            `Location: ${baselineDisplayValue(snmp.system_location)}.`,
            `SNMPv3: ${baselineDisplayValue(snmpv3.user)} / SHA / AES.`,
            `Destinations: ${baselineDisplayValue(alerts.desired_destinations)}.`,
            `Protocol: ${baselineDisplayValue(alerts.alert_protocol)}.`
          ]}
        />
        <SetupPreviewBlock
          title="IPv6 / Time"
          tag="Dedicated"
          lines={[
            `DHCPv6 DNS/domain/rapid/SNTP/stateful/stateless: ${baselineDisplayValue(ipv6.dhcpv6_dns_server)}.`,
            `SNTP server: ${baselineDisplayValue(time.sntp_server)}.`,
            `Timezone: ${baselineDisplayValue(time.timezone)}.`,
            `Interface: ${baselineDisplayValue(time.interface_type)}.`
          ]}
        />
        <SetupPreviewBlock
          title="Reset Handling"
          tag="Guarded"
          lines={[
            `Reset required: ${yesNo(preview.reset_required)}.`,
            "No auto-reset in this preview.",
            "Future reset requires explicit approval."
          ]}
        />
      </div>
      {warningLines.length > 0 && (
        <div className="provider-issue-rows">
          {warningLines.map((warning) => (
            <div className="provider-issue warning" key={warning}>
              <AlertTriangle size={16} />
              <span>{warning}</span>
            </div>
          ))}
        </div>
      )}
      <div className="ilo-baseline-plan">
        <h3>Compare / Preview Plan</h3>
        <table className="provider-candidate-table baseline-plan-table">
          <thead>
            <tr>
              <th>Section</th>
              <th>Item</th>
              <th>Current</th>
              <th>Desired</th>
              <th>Action</th>
              <th>Severity</th>
            </tr>
          </thead>
          <tbody>
            {preview.comparison_rows.map((row) => (
              <tr key={`${row.section}-${row.item}`}>
                <td><strong>{row.section}</strong><span>{row.message}</span></td>
                <td>{row.item}</td>
                <td>{baselineDisplayValue(row.current)}</td>
                <td>{baselineDisplayValue(row.desired)}</td>
                <td><StatusBadge status={row.action} /></td>
                <td><StatusBadge status={row.severity} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <AdvancedDetails
        className="section-details"
        summary="Baseline readiness payload, report placeholders, and redacted current state"
        title="Baseline evidence"
      >
        <div className="provider-fact-grid compact">
          <ProviderFact label="Next Action" value={preview.next_action} />
          <ProviderFact label="Reports" value={String(preview.reports_artifacts.length)} />
          <ProviderFact label="Apply" value={preview.apply_enabled ? "Enabled" : "Disabled"} />
          <ProviderFact label="Reset Required" value={yesNo(preview.reset_required)} />
        </div>
        <JsonDetails title="Raw baseline preview" data={preview as unknown as Record<string, unknown>} />
      </AdvancedDetails>
    </div>
  );
}

function IloSetupIntentPanel({
  busy,
  error,
  intent,
  onSave,
  plan,
  savedMessage
}: {
  busy: boolean;
  error: string;
  intent: IloSetupIntent | null;
  onSave: (payload: IloSetupIntentWrite) => Promise<void>;
  plan: IloSetupPlanPreview | null;
  savedMessage: string;
}) {
  const [form, setForm] = useState<IloSetupIntentWrite>(() => iloSetupIntentForm(intent));

  useEffect(() => {
    setForm(iloSetupIntentForm(intent));
  }, [intent]);

  function updateNetwork<K extends keyof IloSetupIntentWrite["network"]>(
    field: K,
    value: IloSetupIntentWrite["network"][K],
  ) {
    setForm((current) => ({
      ...current,
      network: { ...current.network, [field]: value }
    }));
  }

  function updateSnmp<K extends keyof IloSetupIntentWrite["snmp"]>(
    field: K,
    value: IloSetupIntentWrite["snmp"][K],
  ) {
    setForm((current) => ({
      ...current,
      snmp: { ...current.snmp, [field]: value }
    }));
  }

  function updateTime<K extends keyof IloSetupIntentWrite["time"]>(
    field: K,
    value: IloSetupIntentWrite["time"][K],
  ) {
    setForm((current) => ({
      ...current,
      time: { ...current.time, [field]: value }
    }));
  }

  function updateDns<K extends keyof IloSetupIntentWrite["dns_domain"]>(
    field: K,
    value: IloSetupIntentWrite["dns_domain"][K],
  ) {
    setForm((current) => ({
      ...current,
      dns_domain: { ...current.dns_domain, [field]: value }
    }));
  }

  function updateUser(index: number, field: "username_label" | "role", value: string) {
    setForm((current) => ({
      ...current,
      users: current.users.map((user, userIndex) =>
        userIndex === index ? { ...user, [field]: value } : user
      )
    }));
  }

  function addUser() {
    setForm((current) => ({
      ...current,
      users: [...current.users, { username_label: "", role: "Administrator" }]
    }));
  }

  function removeUser(index: number) {
    setForm((current) => ({
      ...current,
      users: current.users.filter((_, userIndex) => userIndex !== index)
    }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    await onSave(cleanIloSetupIntent(form));
  }

  return (
    <div className="provider-detail-section ilo-setup-intent">
      <div className="provider-callout">
        <strong>iLO setup intent</strong>
        <p>
          Desired IP, DNS, NTP, SNMP, and user-reference values are saved locally for planning.
          Password changes use references only; no plaintext password is stored here.
        </p>
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Saved" value={intent?.updated_at ? formatDateTime(intent.updated_at) : "Not saved"} />
        <ProviderFact label="Apply" value={plan?.apply_enabled ? "Enabled" : "Disabled"} />
        <ProviderFact label="Plan Mode" value={plan?.plan_only ? "Plan only" : "Unknown"} />
        <ProviderFact label="Sections" value={String(plan?.sections.length ?? 0)} />
      </div>
      {savedMessage && <p className="provider-redaction-note">{savedMessage}</p>}
      {error && (
        <div className="provider-issue-rows">
          <div className="provider-issue blocker">
            <Ban size={16} />
            <span>{error}</span>
          </div>
        </div>
      )}
      <form className="form-grid ilo-setup-form" onSubmit={submit}>
        <Field label="iLO Hostname">
          <input
            value={form.network.hostname ?? ""}
            onChange={(event) => updateNetwork("hostname", event.target.value)}
          />
        </Field>
        <Field label="Management IP">
          <input
            value={form.network.management_ip ?? ""}
            onChange={(event) => updateNetwork("management_ip", event.target.value)}
          />
        </Field>
        <Field label="Subnet / Prefix">
          <input
            value={form.network.subnet_mask_or_prefix ?? ""}
            onChange={(event) => updateNetwork("subnet_mask_or_prefix", event.target.value)}
          />
        </Field>
        <Field label="Gateway">
          <input
            value={form.network.gateway ?? ""}
            onChange={(event) => updateNetwork("gateway", event.target.value)}
          />
        </Field>
        <Field label="Management VLAN">
          <input
            value={form.network.vlan ?? ""}
            onChange={(event) => updateNetwork("vlan", event.target.value)}
          />
        </Field>
        <Field label="DNS Domain">
          <input
            value={form.dns_domain.domain_name ?? ""}
            onChange={(event) => updateDns("domain_name", event.target.value)}
          />
        </Field>
        <Field label="DNS Servers">
          <input
            value={form.dns_domain.dns_servers.join(", ")}
            onChange={(event) => updateDns("dns_servers", splitCsvInput(event.target.value))}
          />
        </Field>
        <Field label="Timezone">
          <input
            value={form.time.timezone ?? ""}
            onChange={(event) => updateTime("timezone", event.target.value)}
          />
        </Field>
        <Field label="NTP Servers">
          <input
            value={form.time.ntp_servers.join(", ")}
            onChange={(event) => updateTime("ntp_servers", splitCsvInput(event.target.value))}
          />
        </Field>
        <label className="checkbox-row ilo-checkbox-row">
          <input
            checked={form.snmp.enabled}
            onChange={(event) => updateSnmp("enabled", event.target.checked)}
            type="checkbox"
          />
          <span>SNMP enabled in desired state</span>
        </label>
        <Field label="SNMP Destinations">
          <input
            value={form.snmp.destinations.join(", ")}
            onChange={(event) => updateSnmp("destinations", splitCsvInput(event.target.value))}
          />
        </Field>
        <Field label="SNMP Community/User References">
          <input
            value={form.snmp.community_or_user_ref_labels.join(", ")}
            onChange={(event) =>
              updateSnmp("community_or_user_ref_labels", splitCsvInput(event.target.value))
            }
          />
        </Field>
        <div className="span-2 ilo-user-intent-list">
          <div className="ilo-user-intent-head">
            <h3>Local User References</h3>
            <button onClick={addUser} type="button">
              <Plus size={16} />
              Add User Reference
            </button>
          </div>
          {form.users.length === 0 && <p className="muted">No user references saved.</p>}
          {form.users.map((user, index) => (
            <div className="ilo-user-intent-row" key={`${index}-${user.username_label}`}>
              <Field label="Username Label">
                <input
                  value={user.username_label}
                  onChange={(event) => updateUser(index, "username_label", event.target.value)}
                />
              </Field>
              <Field label="Role">
                <input
                  value={user.role}
                  onChange={(event) => updateUser(index, "role", event.target.value)}
                />
              </Field>
              <button onClick={() => removeUser(index)} type="button">
                <XCircle size={16} />
                Remove
              </button>
            </div>
          ))}
        </div>
        <label className="field span-2">
          <span>Notes</span>
          <textarea
            value={form.notes ?? ""}
            onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))}
          />
        </label>
        <div className="provider-callout span-2">
          <strong>Connection credentials</strong>
          <p>
            Current iLO address, username, and login password are read from .env.local.real-lab.
            Desired password rotation belongs in an external secret store and can be named here only as a reference.
          </p>
        </div>
        <div className="form-actions span-2">
          <button className="primary" disabled={busy} type="submit">
            <Save size={16} />
            {busy ? "Saving" : "Save iLO Intent"}
          </button>
        </div>
      </form>
      {plan && (
        <div className="setup-preview-grid ilo-plan-preview-grid">
          {plan.sections.slice(0, 6).map((section) => (
            <SetupPreviewBlock
              key={section.id}
              title={section.title}
              tag={labelize(section.status)}
              lines={[
                section.planned_preview,
                ...section.warnings,
                ...section.blockers
              ]}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function HpeRaidSetupPanel({
  applyPlan,
  afterResetValidation,
  busy,
  discovery,
  error,
  intent,
  onSave,
  onRefreshPostApply,
  onValidateAfterReset,
  pending,
  plan,
  postApplyBusy,
  resetPlan,
  savedMessage
}: {
  applyPlan: ProviderProbeResult | null;
  afterResetValidation: ProviderProbeResult | null;
  busy: boolean;
  discovery: HpeStorageDiscovery | null;
  error: string;
  intent: HpeRaidIntent | null;
  onSave: (payload: HpeRaidIntentWrite) => Promise<void>;
  onRefreshPostApply: () => Promise<void>;
  onValidateAfterReset: () => Promise<void>;
  pending: ProviderProbeResult | null;
  plan: HpeRaidPlanPreview | null;
  postApplyBusy: boolean;
  resetPlan: ProviderProbeResult | null;
  savedMessage: string;
}) {
  const [form, setForm] = useState<HpeRaidIntentWrite>(() => hpeRaidIntentForm(intent));
  const drives = discovery?.physical_drives ?? [];
  const controllers = discovery?.controllers ?? [];
  const logicalDrives = discovery?.logical_drives ?? [];
  const plannedVolumes = recordArray(plan?.planned_layout.volumes);
  const impact = plan?.impact ?? {};
  const lastApply = objectValue(applyPlan?.last_apply);
  const applyAvailable = asBoolean(applyPlan?.apply_enabled);
  const applyBlockers = stringArray(applyPlan?.blockers);
  const pendingState = objectValue(pending?.pending);
  const resetRequired = asBoolean(pendingState.reset_required);
  const pendingConfigExists = asBoolean(pendingState.pending_config_exists);
  const liveMatchesExpected = asBoolean(pendingState.live_matches_expected);
  const validationState = objectValue(afterResetValidation?.validation);
  const validationMatches = asBoolean(validationState.matches);
  const resetCommand = asString(resetPlan?.command);

  useEffect(() => {
    setForm(hpeRaidIntentForm(intent));
  }, [intent]);

  function update<K extends keyof HpeRaidIntentWrite>(field: K, value: HpeRaidIntentWrite[K]) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function updateVolume(index: number, next: HpeRaidVolumeIntent) {
    setForm((current) => ({
      ...current,
      volumes: current.volumes.map((volume, volumeIndex) =>
        volumeIndex === index ? next : volume
      )
    }));
  }

  function addVolume() {
    setForm((current) => ({
      ...current,
      volumes: [
        ...current.volumes,
        {
          name: `Logical-${current.volumes.length + 1}`,
          purpose: "VM datastore",
          raid_level: "RAID6",
          drive_bays: [],
          spare_bays: [],
          spare_rebuild_mode: null,
          size_policy: "max",
          bootable: false
        }
      ]
    }));
  }

  function removeVolume(index: number) {
    setForm((current) => ({
      ...current,
      volumes: current.volumes.filter((_, volumeIndex) => volumeIndex !== index)
    }));
  }

  function assignDriveBay(bay: string, target: HpeDriveAssignmentTarget) {
    if (!bay) return;
    setForm((current) => ({
      ...current,
      volumes: current.volumes.map((volume, volumeIndex) => {
        const nextVolume = {
          ...volume,
          drive_bays: sortHpeBays(volume.drive_bays.filter((item) => item !== bay)),
          spare_bays: sortHpeBays((volume.spare_bays ?? []).filter((item) => item !== bay))
        };
        if (target.kind === "data" && target.volumeIndex === volumeIndex) {
          nextVolume.drive_bays = sortHpeBays([...nextVolume.drive_bays, bay]);
        }
        if (target.kind === "spare" && target.volumeIndex === volumeIndex) {
          nextVolume.spare_bays = sortHpeBays([...nextVolume.spare_bays, bay]);
          nextVolume.spare_rebuild_mode = nextVolume.spare_rebuild_mode || "Dedicated";
        }
        if (!nextVolume.spare_bays.length) {
          nextVolume.spare_rebuild_mode = null;
        }
        return nextVolume;
      })
    }));
  }

  function useEsxiLayout() {
    const bays = drives.map((drive) => asString(drive.bay_id)).filter(Boolean);
    const bootBays = bays.slice(0, 2);
    const datastoreBays = bays.slice(2);
    const volumes: HpeRaidVolumeIntent[] = [];
    if (bootBays.length) {
      volumes.push({
        name: "ESXi-OS",
        purpose: "ESXi install",
        raid_level: "RAID1",
        drive_bays: bootBays,
        spare_bays: [],
        spare_rebuild_mode: null,
        size_policy: "max",
        bootable: true
      });
    }
    if (datastoreBays.length) {
      const raid6WithSpare = datastoreBays.length > 5;
      volumes.push({
        name: "VM-Datastore",
        purpose: "VM datastore",
        raid_level: datastoreBays.length >= 4 ? "RAID6" : "RAID5",
        drive_bays: raid6WithSpare ? datastoreBays.slice(0, 5) : datastoreBays,
        spare_bays: raid6WithSpare ? datastoreBays.slice(5) : [],
        spare_rebuild_mode: raid6WithSpare ? "Dedicated" : null,
        size_policy: "max",
        bootable: false
      });
    }
    setForm((current) => ({
      ...current,
      controller_ref: current.controller_ref || controllerValue(controllers[0]),
      volumes
    }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    await onSave(cleanHpeRaidIntent(form));
  }

  return (
    <div className="provider-detail-section hpe-raid-setup">
      <div className="provider-callout">
        <strong>HPE Storage / RAID setup</strong>
        <p>
          Select the Smart Array controller, drive bays, and desired RAID layout for ESXi.
          Discovery and planning are enabled here; destructive apply requires the explicit terminal confirmation path.
        </p>
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Real Hardware Discovery" value={discovery?.storage_inventory_available ? "Enabled" : "Unavailable"} />
        <ProviderFact label="Plan Preview" value={plan ? "Enabled" : "Unavailable"} />
        <ProviderFact label="RAID Apply" value={applyAvailable ? "Available" : "Not available"} />
        <ProviderFact label="Last Real Apply" value={labelize(asString(lastApply.status) || "never")} />
        <ProviderFact label="Controller Count" value={String(controllers.length)} />
        <ProviderFact label="Physical Drives" value={String(drives.length)} />
        <ProviderFact label="Logical Drives" value={String(logicalDrives.length)} />
        <ProviderFact label="Apply Mechanism" value={asString(applyPlan?.apply_mechanism) || "Redfish pending"} />
      </div>
      {savedMessage && <p className="provider-redaction-note">{savedMessage}</p>}
      {error && (
        <div className="provider-issue-rows">
          <div className="provider-issue blocker">
            <Ban size={16} />
            <span>{error}</span>
          </div>
        </div>
      )}
      <ProviderIssueRows blockers={plan?.blockers ?? discovery?.blockers ?? []} warnings={plan?.warnings ?? discovery?.warnings ?? []} />
      <div className="setup-preview-grid">
        <SetupPreviewBlock
          title="Plan Status"
          tag={labelize(plan?.status ?? "not loaded")}
          lines={[
            plan?.next_safe_action ?? discovery?.next_safe_action ?? "Storage discovery has not loaded.",
            `Destructive requested: ${presenceLabel(plan?.destructive_actions_requested)}.`,
            `Destructive enabled: ${presenceLabel(plan?.destructive_actions_enabled)}.`
          ]}
        />
        <SetupPreviewBlock
          title="Impact Preview"
          tag="No apply"
          lines={[
            `Existing logical drives to delete: ${asString(impact.logical_drives_to_delete) || "0"}.`,
            `Selected bays: ${stringArray(impact.physical_drives_selected).join(", ") || "None"}.`,
            `Unselected bays: ${stringArray(impact.physical_drives_not_selected).join(", ") || "None"}.`,
            `No storage write will run: ${presenceLabel(impact.no_storage_write_will_run)}.`
          ]}
        />
        <SetupPreviewBlock
          title="Apply Path"
          tag={applyAvailable ? "Available" : "Blocked"}
          lines={[
            asString(applyPlan?.message) || "Apply plan has not loaded.",
            `Confirmation: ${asString(applyPlan?.confirmation_phrase) || "not available"}.`,
            `Last apply report: ${asString(lastApply.report) || "not recorded"}.`,
            ...applyBlockers.slice(0, 4)
          ]}
        />
        <SetupPreviewBlock
          title="Pending Reset"
          tag={resetRequired ? "Reset required" : "No pending reset"}
          lines={[
            asString(pending?.message) || "Pending RAID state has not loaded.",
            `Pending config exists: ${presenceLabel(pendingConfigExists)}.`,
            `Live matches saved intent: ${presenceLabel(liveMatchesExpected)}.`,
            `Report: ${asString((pending as Record<string, unknown> | null)?.report) || "artifacts/codex-runs/hpe-raid-pending-report.md"}.`
          ]}
        />
        <SetupPreviewBlock
          title="Reset Command"
          tag={asBoolean(resetPlan?.apply_enabled) ? "Available" : "Gated"}
          lines={[
            asString(resetPlan?.message) || "Reset plan has not loaded.",
            resetCommand || "HPE_RAID_ALLOW_RESET=true LAB_ALLOW_POWER_ACTIONS=true HPE_RAID_RESET_CONFIRM=\"RESET SERVER FOR HPE RAID APPLY\" make -C app provider-lab-server-reset-for-raid",
            ...stringArray(resetPlan?.blockers).slice(0, 3)
          ]}
        />
        <SetupPreviewBlock
          title="After Reset Validation"
          tag={afterResetValidation ? labelize(asString(afterResetValidation.status)) : "Not run"}
          lines={[
            asString(afterResetValidation?.message) || "Run validation after iLO/server returns.",
            `Matches saved intent: ${afterResetValidation ? presenceLabel(validationMatches) : "Unknown"}.`,
            `Report: artifacts/codex-runs/hpe-raid-after-reset-validation-report.md.`
          ]}
        />
      </div>
      <div className="form-actions provider-inline-actions">
        <button disabled={postApplyBusy} onClick={onRefreshPostApply} type="button">
          <RefreshCw size={16} />
          {postApplyBusy ? "Refreshing" : "Refresh Pending State"}
        </button>
        <button
          className="primary"
          disabled={postApplyBusy}
          onClick={onValidateAfterReset}
          type="button"
        >
          <ShieldCheck size={16} />
          {postApplyBusy ? "Validating" : "Validate After Reset"}
        </button>
      </div>
      <h3>Current Controllers</h3>
      <HpeControllerTable controllers={controllers} />
      <h3>Current Physical Drives</h3>
      <HpeDriveTable drives={drives} />
      <h3>Current Logical Drives</h3>
      <HpeLogicalDriveTable logicalDrives={logicalDrives} />
      <Dl360RaidProfileEditor
        drives={drives}
        onChange={(volumes) => update("volumes", volumes)}
        volumes={form.volumes}
      />
      <form className="form-grid hpe-raid-form" onSubmit={submit}>
        <Field label="Smart Array Controller">
          <select
            value={form.controller_ref ?? ""}
            onChange={(event) => update("controller_ref", event.target.value || null)}
          >
            <option value="">Auto / single discovered controller</option>
            {controllers.map((controller) => (
              <option key={controllerValue(controller)} value={controllerValue(controller)}>
                {controllerLabel(controller)}
              </option>
            ))}
          </select>
        </Field>
        <label className="checkbox-row hpe-wipe-row">
          <input
            checked={form.wipe_existing_logical_drives}
            onChange={(event) => update("wipe_existing_logical_drives", event.target.checked)}
            type="checkbox"
          />
          <span>Plan deleting existing logical drives before creating this layout</span>
        </label>
        <div className="form-actions span-2">
          <button disabled={!drives.length} onClick={useEsxiLayout} type="button">
            <HardDrive size={16} />
            Use ESXi Layout
          </button>
          <button onClick={addVolume} type="button">
            <Plus size={16} />
            Add RAID Volume
          </button>
        </div>
        <div className="span-2">
          <HpeDriveAssignmentBoard
            drives={drives}
            onAssign={assignDriveBay}
            volumes={form.volumes}
          />
        </div>
        <div className="span-2 hpe-raid-volume-list">
          {form.volumes.length === 0 && <p className="muted">No RAID volumes planned.</p>}
          {form.volumes.map((volume, index) => (
            <HpeRaidVolumeEditor
              key={`${index}-${volume.name}`}
              onChange={(next) => updateVolume(index, next)}
              onRemove={() => removeVolume(index)}
              volume={volume}
            />
          ))}
        </div>
        <label className="field span-2">
          <span>RAID Planning Notes</span>
          <textarea
            value={form.notes ?? ""}
            onChange={(event) => update("notes", event.target.value)}
          />
        </label>
        <div className="provider-callout span-2">
          <strong>{applyAvailable ? "Destructive apply available from terminal" : "Destructive apply gated"}</strong>
          <p>
            {asString(applyPlan?.next_safe_action) ||
              "Save layout intent and review blockers before running the terminal apply target."}
          </p>
        </div>
        <div className="form-actions span-2">
          <button disabled type="button">
            <ShieldCheck size={16} />
            {applyAvailable ? "Use Terminal Apply" : "Apply RAID Plan Blocked"}
          </button>
          <button className="primary" disabled={busy} type="submit">
            <Save size={16} />
            {busy ? "Saving" : "Save RAID Intent"}
          </button>
        </div>
      </form>
      {plannedVolumes.length > 0 && (
        <>
          <h3>Planned Volumes</h3>
          <table className="provider-candidate-table hpe-raid-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>RAID</th>
                <th>Purpose</th>
                <th>Bays</th>
                <th>Est. Usable</th>
              </tr>
            </thead>
            <tbody>
              {plannedVolumes.map((volume) => (
                <tr key={`${asString(volume.name)}-${asString(volume.raid_level)}`}>
                  <td>{asString(volume.name) || "-"}</td>
                  <td>{asString(volume.raid_level) || "-"}</td>
                  <td>{asString(volume.purpose) || "-"}</td>
                  <td>{stringArray(volume.drive_bays).join(", ") || "-"}</td>
                  <td>{formatBytes(asNumber(volume.estimated_usable_capacity_bytes, 0))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

function HpeRaidVolumeEditor({
  onChange,
  onRemove,
  volume
}: {
  onChange: (volume: HpeRaidVolumeIntent) => void;
  onRemove: () => void;
  volume: HpeRaidVolumeIntent;
}) {
  function update<K extends keyof HpeRaidVolumeIntent>(field: K, value: HpeRaidVolumeIntent[K]) {
    onChange({ ...volume, [field]: value });
  }

  return (
    <div className="hpe-raid-volume-editor">
      <div className="hpe-raid-volume-grid">
        <Field label="Volume Name">
          <input value={volume.name} onChange={(event) => update("name", event.target.value)} />
        </Field>
        <Field label="Purpose">
          <input value={volume.purpose} onChange={(event) => update("purpose", event.target.value)} />
        </Field>
        <Field label="RAID Level">
          <select value={volume.raid_level} onChange={(event) => update("raid_level", event.target.value)}>
            <option value="RAID1">RAID1</option>
            <option value="RAID5">RAID5</option>
            <option value="RAID6">RAID6</option>
            <option value="RAID10">RAID10</option>
            <option value="RAID0">RAID0</option>
          </select>
        </Field>
        <Field label="Size Policy">
          <input value={volume.size_policy} onChange={(event) => update("size_policy", event.target.value)} />
        </Field>
        <label className="checkbox-row">
          <input
            checked={volume.bootable}
            onChange={(event) => update("bootable", event.target.checked)}
            type="checkbox"
          />
          <span>Bootable volume</span>
        </label>
        <button onClick={onRemove} type="button">
          <XCircle size={16} />
          Remove Volume
        </button>
      </div>
      <div className="hpe-volume-bay-summary">
        <HpeBayList label="Member bays" bays={volume.drive_bays} />
        <HpeBayList label="Dedicated spares" bays={volume.spare_bays ?? []} />
      </div>
    </div>
  );
}

type HpeDriveAssignmentKind = "unused" | "data" | "spare";
type HpeDriveAssignmentTarget = {
  kind: HpeDriveAssignmentKind;
  volumeIndex: number | null;
};

function HpeDriveAssignmentBoard({
  drives,
  onAssign,
  volumes
}: {
  drives: Array<Record<string, unknown>>;
  onAssign: (bay: string, target: HpeDriveAssignmentTarget) => void;
  volumes: HpeRaidVolumeIntent[];
}) {
  if (!drives.length) {
    return <p className="muted">No physical drive inventory is cached yet.</p>;
  }

  const assignedCount = hpeAssignedBays(volumes).size;
  const usableDriveCount = drives.filter(hpeDriveAssignable).length;

  return (
    <section className="hpe-drive-board" aria-label="RAID drive assignment">
      <div className="hpe-drive-board-head">
        <div>
          <strong>Drive Assignment</strong>
          <p>{assignedCount} of {usableDriveCount} usable bays assigned in the saved intent draft.</p>
        </div>
        <span className="status-pillow tone-neutral">Plan only</span>
      </div>
      {volumes.length === 0 && (
        <p className="provider-redaction-note">Add a RAID volume or load the ESXi layout before assigning bays.</p>
      )}
      <div className="hpe-drive-bay-grid">
        {drives.map((drive) => {
          const bay = asString(drive.bay_id);
          const assignment: HpeDriveAssignmentTarget = bay
            ? hpeDriveAssignment(volumes, bay)
            : { kind: "unused", volumeIndex: null };
          const assignable = Boolean(bay) && hpeDriveAssignable(drive) && volumes.length > 0;
          const assignmentValue = hpeDriveAssignmentValue(assignment);
          const assignmentLabel = hpeDriveAssignmentLabel(volumes, assignment);
          return (
            <div
              className={`hpe-drive-bay role-${assignment.kind}${assignable ? "" : " is-disabled"}`}
              key={bay || asString(drive.display_label)}
            >
              <div className="hpe-drive-bay-top">
                <span>{asString(drive.display_label) || bay || "Drive"}</span>
                <strong>{asString(drive.capacity_label) || "No media"}</strong>
              </div>
              <div className="hpe-drive-bay-meta">
                <span>{asString(drive.media_type) || asString(drive.MediaType) || "-"}</span>
                <span>{asString(drive.Protocol) || asString(drive.InterfaceType) || "-"}</span>
                <span>{labelize(statusHealth(drive))}</span>
              </div>
              <span className="hpe-drive-assignment-badge">{assignmentLabel}</span>
              <label className="hpe-drive-assignment-control">
                <span>Assignment</span>
                <select
                  disabled={!assignable}
                  value={assignmentValue}
                  onChange={(event) => onAssign(bay, parseHpeDriveAssignmentTarget(event.target.value))}
                >
                  <option value="unused">Unused</option>
                  {volumes.map((volume, volumeIndex) => (
                    <option key={`data-${volumeIndex}`} value={`data:${volumeIndex}`}>
                      {(volume.name || `Volume ${volumeIndex + 1}`).trim()} member
                    </option>
                  ))}
                  {volumes.map((volume, volumeIndex) => (
                    <option key={`spare-${volumeIndex}`} value={`spare:${volumeIndex}`}>
                      {(volume.name || `Volume ${volumeIndex + 1}`).trim()} spare
                    </option>
                  ))}
                </select>
              </label>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function HpeBayList({ bays, label }: { bays: string[]; label: string }) {
  return (
    <div>
      <span>{label}</span>
      <p>{sortHpeBays(bays).join(", ") || "None"}</p>
    </div>
  );
}

function Dl360RaidProfileEditor({
  drives,
  onChange,
  volumes
}: {
  drives: Array<Record<string, unknown>>;
  onChange: (volumes: HpeRaidVolumeIntent[]) => void;
  volumes: HpeRaidVolumeIntent[];
}) {
  const bays = drives.map((drive) => asString(drive.bay_id)).filter(Boolean);
  const osVolume = volumes.find((volume) => volume.name === "ESXi-OS") ?? volumes.find((volume) => volume.bootable);
  const datastoreVolume =
    volumes.find((volume) => volume.name === "VM-Datastore") ??
    volumes.find((volume) => !volume.bootable && volume.purpose.toLowerCase().includes("datastore"));
  const osBays = new Set(osVolume?.drive_bays ?? []);
  const datastoreBays = new Set(datastoreVolume?.drive_bays ?? []);
  const spareBays = new Set(datastoreVolume?.spare_bays ?? []);
  const datastoreRaid = datastoreVolume?.raid_level || "RAID6";

  function setDatastoreRaid(raidLevel: string) {
    onChange(dl360ProfileVolumes([...osBays], raidLevel, [...datastoreBays], [...spareBays]));
  }

  function useRecommended() {
    const nextOs = bays.slice(0, 2);
    const data = bays.slice(2, 7);
    const spare = bays.slice(7, 8);
    onChange(dl360ProfileVolumes(nextOs, "RAID6", data, spare));
  }

  return (
    <div className="provider-callout hpe-raid-profile">
      <strong>DL360 RAID profile</strong>
      <p>Choose the OS RAID drives, datastore RAID level, datastore drives, and one dedicated spare.</p>
      <div className="form-actions">
        <button disabled={bays.length < 2} onClick={useRecommended} type="button">
          <HardDrive size={16} />
          DL360 ESXi Profile
        </button>
        <Field label="Datastore RAID">
          <select value={datastoreRaid} onChange={(event) => setDatastoreRaid(event.target.value)}>
            <option value="RAID5">RAID5</option>
            <option value="RAID6">RAID6</option>
            <option value="RAID10">RAID10</option>
            <option value="RAID1">RAID1</option>
            <option value="RAID0">RAID0</option>
          </select>
        </Field>
      </div>
      <div className="hpe-profile-summary">
        <HpeBayList label="OS bays" bays={[...osBays]} />
        <HpeBayList label="Datastore bays" bays={[...datastoreBays]} />
        <HpeBayList label="Dedicated spares" bays={[...spareBays]} />
      </div>
    </div>
  );
}

function dl360ProfileVolumes(
  osBays: string[],
  datastoreRaid: string,
  datastoreBays: string[],
  spareBays: string[],
): HpeRaidVolumeIntent[] {
  const volumes: HpeRaidVolumeIntent[] = [];
  if (osBays.length) {
    volumes.push({
      name: "ESXi-OS",
      purpose: "ESXi install",
      raid_level: "RAID1",
      drive_bays: osBays,
      spare_bays: [],
      spare_rebuild_mode: null,
      size_policy: "max",
      bootable: true
    });
  }
  if (datastoreBays.length) {
    volumes.push({
      name: "VM-Datastore",
      purpose: "VM datastore",
      raid_level: datastoreRaid,
      drive_bays: datastoreBays,
      spare_bays: spareBays,
      spare_rebuild_mode: spareBays.length ? "Dedicated" : null,
      size_policy: "max",
      bootable: false
    });
  }
  return volumes;
}

function parseHpeDriveAssignmentTarget(value: string): HpeDriveAssignmentTarget {
  if (value === "unused") {
    return { kind: "unused", volumeIndex: null };
  }
  const [kind, index] = value.split(":");
  const volumeIndex = Number(index);
  if ((kind === "data" || kind === "spare") && Number.isInteger(volumeIndex) && volumeIndex >= 0) {
    return { kind, volumeIndex };
  }
  return { kind: "unused", volumeIndex: null };
}

function hpeDriveAssignmentValue(target: HpeDriveAssignmentTarget): string {
  if (target.kind === "unused" || target.volumeIndex === null) {
    return "unused";
  }
  return `${target.kind}:${target.volumeIndex}`;
}

function hpeDriveAssignment(volumes: HpeRaidVolumeIntent[], bay: string): HpeDriveAssignmentTarget {
  for (let index = 0; index < volumes.length; index += 1) {
    const volume = volumes[index];
    if (volume.drive_bays.includes(bay)) {
      return { kind: "data", volumeIndex: index };
    }
    if ((volume.spare_bays ?? []).includes(bay)) {
      return { kind: "spare", volumeIndex: index };
    }
  }
  return { kind: "unused", volumeIndex: null };
}

function hpeDriveAssignmentLabel(volumes: HpeRaidVolumeIntent[], target: HpeDriveAssignmentTarget): string {
  if (target.kind === "unused" || target.volumeIndex === null) {
    return "Unused";
  }
  const volume = volumes[target.volumeIndex];
  const name = volume?.name.trim() || `Volume ${target.volumeIndex + 1}`;
  return target.kind === "spare" ? `${name} spare` : `${name} member`;
}

function hpeAssignedBays(volumes: HpeRaidVolumeIntent[]): Set<string> {
  const bays = new Set<string>();
  volumes.forEach((volume) => {
    volume.drive_bays.forEach((bay) => bays.add(bay));
    (volume.spare_bays ?? []).forEach((bay) => bays.add(bay));
  });
  return bays;
}

function hpeDriveAssignable(drive: Record<string, unknown>): boolean {
  const state = asString(objectValue(drive.Status).State || drive.State).toLowerCase();
  const name = asString(drive.Name || drive.display_label).toLowerCase();
  return state !== "absent" && !name.includes("empty bay");
}

function sortHpeBays(bays: string[]): string[] {
  return Array.from(new Set(bays.filter(Boolean))).sort((left, right) => {
    const leftNumber = Number(left);
    const rightNumber = Number(right);
    if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber)) {
      return leftNumber - rightNumber;
    }
    return left.localeCompare(right, undefined, { numeric: true });
  });
}

function EsxiInstallReadinessPanel({
  busy,
  onRefresh,
  readiness
}: {
  busy: boolean;
  onRefresh: () => Promise<void>;
  readiness: ProviderProbeResult | null;
}) {
  const inventory = objectValue(readiness?.inventory);
  const virtualMedia = objectValue(readiness?.virtual_media);
  const boot = objectValue(readiness?.boot_control);
  const bios = objectValue(readiness?.bios);
  const iso = objectValue(readiness?.iso);
  const raidValidation = objectValue(readiness?.raid_validation);
  const bootWorkflow = objectValue(readiness?.boot_workflow);
  const mediaUrlWorkflow = objectValue(bootWorkflow.media_url);
  const virtualMediaWorkflow = objectValue(bootWorkflow.virtual_media);
  const oneTimeBootWorkflow = objectValue(bootWorkflow.one_time_boot);
  const resetBootWorkflow = objectValue(bootWorkflow.reset_boot);
  const milestones = recordArray(readiness?.milestones);

  return (
    <div className="provider-detail-section esxi-install-readiness">
      <div className="provider-callout">
        <strong>iLO build readiness for ESXi</strong>
        <p>
          Inventory, virtual media, one-time boot, BIOS discovery, and ISO readiness are checked before any install workflow.
        </p>
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Status" value={labelize(asString(readiness?.status) || "not loaded")} />
        <ProviderFact label="Server Model" value={asString(inventory.model) || "Unknown"} />
        <ProviderFact label="Power State" value={asString(inventory.power_state) || "Unknown"} />
        <ProviderFact label="RAID Validated" value={presenceLabel(objectValue(raidValidation).matches_saved_intent)} />
        <ProviderFact label="Virtual Media" value={presenceLabel(virtualMedia.supported)} />
        <ProviderFact label="One-Time Boot" value={presenceLabel(boot.one_time_boot_supported)} />
        <ProviderFact label="BIOS Settings" value={presenceLabel(bios.settings_available)} />
        <ProviderFact label="ESXi ISO" value={presenceLabel(iso.ready)} />
        <ProviderFact label="Media URL" value={labelize(asString(mediaUrlWorkflow.status) || "not run")} />
        <ProviderFact label="Virtual Media Insert" value={labelize(asString(virtualMediaWorkflow.status) || "not run")} />
        <ProviderFact label="One-Time Boot Set" value={labelize(asString(oneTimeBootWorkflow.status) || "not run")} />
        <ProviderFact label="Installer Boot" value={labelize(asString(resetBootWorkflow.status) || "not run")} />
      </div>
      <ProviderIssueRows blockers={stringArray(readiness?.blockers)} warnings={stringArray(readiness?.warnings)} />
      <div className="setup-preview-grid">
        <SetupPreviewBlock
          title="Virtual Media"
          tag={asBoolean(virtualMedia.supported) ? "Detected" : "Missing"}
          lines={[
            `ISO capable: ${presenceLabel(virtualMedia.iso_capable)}.`,
            `Device count: ${String(recordArray(virtualMedia.devices).length)}.`,
            `Collection status: ${asString(virtualMedia.collection_status) || "unknown"}.`
          ]}
        />
        <SetupPreviewBlock
          title="Boot Control"
          tag={asBoolean(boot.one_time_boot_supported) ? "Detected" : "Missing"}
          lines={[
            `Current target: ${asString(boot.boot_source_override_target) || "unknown"}.`,
            `Current override: ${asString(boot.boot_source_override_enabled) || "unknown"}.`,
            `Evidence: ${asString(boot.one_time_boot_evidence) || "unknown"}.`,
            `Allowed targets: ${stringArray(boot.target_allowable_values).join(", ") || "unknown"}.`
          ]}
        />
        <SetupPreviewBlock
          title="ISO Readiness"
          tag={asBoolean(iso.ready) ? "Ready" : "Missing"}
          lines={[
            `Media inventory mode: ${asString(iso.media_inventory_mode) || "unknown"}.`,
            `ISO count: ${asString(iso.iso_count) || "0"}.`,
            `Selected placeholder: ${asString(iso.selected_placeholder) || "none"}.`
          ]}
        />
        <SetupPreviewBlock
          title="Media URL"
          tag={labelize(asString(mediaUrlWorkflow.status) || "Not run")}
          lines={[
            asString(mediaUrlWorkflow.message) || "Media URL validation has not run.",
            `Report: ${asString(mediaUrlWorkflow.report) || "artifacts/codex-runs/esxi-media-url-report.md"}`
          ]}
        />
        <SetupPreviewBlock
          title="Inserted Media"
          tag={labelize(asString(virtualMediaWorkflow.status) || "Not run")}
          lines={[
            asString(virtualMediaWorkflow.message) || "Virtual media insert has not run.",
            `Report: ${asString(virtualMediaWorkflow.report) || "artifacts/codex-runs/esxi-virtual-media-report.md"}`
          ]}
        />
        <SetupPreviewBlock
          title="Boot And Installer"
          tag={labelize(asString(resetBootWorkflow.status) || asString(oneTimeBootWorkflow.status) || "Not run")}
          lines={[
            `One-time boot: ${labelize(asString(oneTimeBootWorkflow.status) || "not run")}.`,
            asString(oneTimeBootWorkflow.message) || "One-time boot target has not run.",
            `Reset/boot: ${labelize(asString(resetBootWorkflow.status) || "not run")}.`,
            asString(resetBootWorkflow.message) || "Reset/installer detection has not run.",
            `Report: ${asString(resetBootWorkflow.report) || "artifacts/codex-runs/esxi-installer-boot-report.md"}`
          ]}
        />
        <SetupPreviewBlock
          title="BIOS / Boot Settings"
          tag={asBoolean(bios.settings_available) ? "Readable" : "Unavailable"}
          lines={[
            `BIOS version: ${asString(bios.bios_version) || "unknown"}.`,
            `BIOS status: ${asString(bios.bios_status) || "unknown"}.`,
            `Attribute count: ${asString(bios.attribute_count) || "0"}.`
          ]}
        />
      </div>
      {milestones.length > 0 && (
        <>
          <h3>Build Milestones</h3>
          <div className="setup-preview-grid">
            {milestones.map((milestone) => (
              <SetupPreviewBlock
                key={asString(milestone.id) || asString(milestone.label)}
                title={asString(milestone.label) || "Milestone"}
                tag={labelize(asString(milestone.status) || "unknown")}
                lines={[asString(milestone.id) || ""]}
              />
            ))}
          </div>
        </>
      )}
      <div className="form-actions provider-inline-actions">
        <button disabled={busy} onClick={onRefresh} type="button">
          <RefreshCw size={16} />
          {busy ? "Checking" : "Refresh ESXi Readiness"}
        </button>
      </div>
      <p className="provider-redaction-note">
        Report: {asString(readiness?.report) || "artifacts/codex-runs/esxi-install-readiness-report.md"}
      </p>
    </div>
  );
}

function HpeControllerTable({ controllers }: { controllers: Array<Record<string, unknown>> }) {
  if (!controllers.length) {
    return <p className="muted">No Smart Array controller inventory is cached yet.</p>;
  }
  return (
    <table className="provider-candidate-table hpe-raid-table">
      <thead>
        <tr>
          <th>Controller</th>
          <th>Mode</th>
          <th>Cache</th>
          <th>Health</th>
        </tr>
      </thead>
      <tbody>
        {controllers.map((controller) => (
          <tr key={controllerValue(controller)}>
            <td>{controllerLabel(controller)}</td>
            <td>{asString(controller.CurrentOperatingMode) || "-"}</td>
            <td>{asString(controller.CacheMemorySizeMiB) || "-"}</td>
            <td>{statusHealth(controller)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function HpeDriveTable({ drives }: { drives: Array<Record<string, unknown>> }) {
  if (!drives.length) {
    return <p className="muted">No physical drive inventory is cached yet.</p>;
  }
  return (
    <table className="provider-candidate-table hpe-raid-table">
      <thead>
        <tr>
          <th>Bay</th>
          <th>Capacity</th>
          <th>Media</th>
          <th>Interface</th>
          <th>Health</th>
        </tr>
      </thead>
      <tbody>
        {drives.map((drive) => (
          <tr key={asString(drive.bay_id) || asString(drive.display_label)}>
            <td>{asString(drive.display_label) || "-"}</td>
            <td>{asString(drive.capacity_label) || "-"}</td>
            <td>{asString(drive.media_type) || asString(drive.MediaType) || "-"}</td>
            <td>{asString(drive.InterfaceType) || asString(drive.Protocol) || "-"}</td>
            <td>{asString(drive.health) || statusHealth(drive)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function HpeLogicalDriveTable({ logicalDrives }: { logicalDrives: Array<Record<string, unknown>> }) {
  if (!logicalDrives.length) {
    return <p className="muted">No existing logical drives are cached yet.</p>;
  }
  return (
    <table className="provider-candidate-table hpe-raid-table">
      <thead>
        <tr>
          <th>Name</th>
          <th>RAID</th>
          <th>Capacity</th>
          <th>Bootable</th>
          <th>Health</th>
        </tr>
      </thead>
      <tbody>
        {logicalDrives.map((logicalDrive) => (
          <tr key={asString(logicalDrive.display_label)}>
            <td>{asString(logicalDrive.display_label) || "-"}</td>
            <td>{asString(logicalDrive.raid_level) || "-"}</td>
            <td>{asString(logicalDrive.capacity_label) || "-"}</td>
            <td>{presenceLabel(logicalDrive.Bootable)}</td>
            <td>{asString(logicalDrive.health) || statusHealth(logicalDrive)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function IloUpgradeDecisionPanel({
  error,
  readiness
}: {
  error: string;
  readiness: IloUpgradeReadiness | null;
}) {
  if (error) {
    return (
      <div className="provider-callout upgrade-readiness-callout">
        <strong>Firmware readiness unavailable</strong>
        <p>{error}</p>
      </div>
    );
  }

  if (!readiness) {
    return (
      <div className="provider-callout upgrade-readiness-callout">
        <strong>Firmware readiness</strong>
        <p>Loading planning decision.</p>
      </div>
    );
  }

  const { decision, subject } = readiness;

  return (
    <div className="upgrade-readiness">
      <div className="provider-callout upgrade-readiness-callout">
        <div className="upgrade-readiness-head">
          <div>
            <strong>Firmware upgrade readiness</strong>
            <p>Plan only. No firmware upload, flash, reboot, reset, media mount, or setting change is run.</p>
          </div>
          <StatusBadge status={decision.status} />
        </div>
      </div>
      <div className="provider-fact-grid">
        <ProviderFact label="Current Firmware" value={subject.current_version || "Unknown"} />
        <ProviderFact label="Generation" value={subject.generation || "Unknown"} />
        <ProviderFact label="Server Model" value={subject.model || "Unknown"} />
        <ProviderFact label="Match Confidence" value={labelize(subject.discovery_confidence)} />
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Recommended Target" value={decision.recommended_target || "None"} />
        <ProviderFact
          label="Intermediate Versions"
          value={decision.required_intermediate_versions.join(", ") || "None"}
        />
        <ProviderFact label="Next Safe Action" value={decision.next_safe_action} />
        <ProviderFact label="Apply / Flash" value={decision.apply_enabled ? "Enabled" : "Disabled"} />
      </div>
      <h3>Available Firmware Candidates</h3>
      <UpgradeCandidateTable candidates={readiness.candidates} />
      <h3>Upgrade Chain</h3>
      <UpgradeCandidateTable candidates={readiness.upgrade_chain} empty="No confirmed upgrade chain is available." />
      <UpgradeDecisionIssues readiness={readiness} />
      <div className="provider-action-layout upgrade-action-layout">
        <div className="provider-action-item">
          <button disabled>
            <Ban size={16} />
            Flash disabled
          </button>
          <span className="action-tag disabled">Plan only</span>
          <p>{decision.next_safe_action}</p>
        </div>
      </div>
    </div>
  );
}

function UpgradeCandidateTable({
  candidates,
  empty = "No firmware candidates were found."
}: {
  candidates: IloUpgradeReadiness["candidates"];
  empty?: string;
}) {
  if (!candidates.length) {
    return <p className="muted">{empty}</p>;
  }

  return (
    <table className="provider-candidate-table upgrade-candidate-table">
      <thead>
        <tr>
          <th>Media</th>
          <th>Version</th>
          <th>Product</th>
          <th>Generation</th>
          <th>Confidence</th>
        </tr>
      </thead>
      <tbody>
        {candidates.map((candidate) => (
          <tr key={candidate.id}>
            <td>
              <strong>{candidate.redacted_label}</strong>
              <span>{candidate.source}</span>
              {candidate.warnings.length > 0 && (
                <span>{candidate.warnings.join(" ")}</span>
              )}
            </td>
            <td>{candidate.version || "-"}</td>
            <td>{candidate.product_hint || "-"}</td>
            <td>{candidate.generation_hint || "-"}</td>
            <td>
              <span className={`candidate-tag ${candidate.match_confidence}`}>
                {labelize(candidate.match_confidence)}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function UpgradeDecisionIssues({ readiness }: { readiness: IloUpgradeReadiness }) {
  if (
    !readiness.blockers.length &&
    !readiness.warnings.length &&
    !readiness.removable_warnings.length
  ) {
    return null;
  }

  return (
    <div className="provider-issue-rows upgrade-issue-rows">
      {readiness.blockers.map((blocker) => (
        <div className="provider-issue blocker" key={blocker}>
          <Ban size={16} />
          <span>{blocker}</span>
        </div>
      ))}
      {readiness.warnings.map((warning) => (
        <div className="provider-issue warning" key={warning}>
          <AlertTriangle size={16} />
          <span>{warning}</span>
        </div>
      ))}
      {readiness.removable_warnings.map((warning) => (
        <div className="provider-issue warning removable" key={warning}>
          <AlertTriangle size={16} />
          <span>{warning}</span>
        </div>
      ))}
    </div>
  );
}

function ManagementTargetDetails({ provider }: { provider: ProviderStatus }) {
  const config = provider.configuration;
  const missingFields = stringArray(config.missing_fields);
  const managementConfigured = asBoolean(config.management_configured);
  const plannedTarget = asBoolean(config.planned_target);

  return (
    <div className="provider-detail-section">
      <div className="provider-callout">
        <strong>{managementConfigured ? "Management target configured" : labelize(provider.status)}</strong>
        <p>{asString(config.safe_next_action) || safeNextAction(provider)}</p>
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Management Configured" value={managementConfigured ? "Enabled" : "Disabled"} />
        <ProviderFact label="Planned Target" value={plannedTarget ? "Present" : "Missing"} />
        <ProviderFact label="Host" value={presenceLabel(config.host_configured)} />
        <ProviderFact label="Username" value={presenceLabel(config.username_configured)} />
        <ProviderFact label="Password" value={presenceLabel(config.password_configured)} />
        {"tls_verify" in config && (
          <ProviderFact label="TLS Verify" value={asBoolean(config.tls_verify) ? "Enabled" : "Disabled"} />
        )}
      </div>
      {missingFields.length > 0 && managementConfigured && (
        <p className="provider-missing-fields">
          Missing local settings: {missingFields.join(", ")}
        </p>
      )}
    </div>
  );
}

function NetAppOntapDetails({ provider }: { provider: ProviderStatus }) {
  const [planPreview, setPlanPreview] = useState<NetAppPlanPreview | null>(null);
  const [planError, setPlanError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api
      .netappPlanPreview()
      .then((payload) => {
        if (!cancelled) {
          setPlanPreview(payload);
          setPlanError("");
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setPlanPreview(null);
          setPlanError(err.message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [provider.status]);

  const readiness = planPreview?.readiness_buckets ?? objectValue(provider.discovery?.readiness);
  const intent = objectValue(provider.discovery?.intent_preview);
  const cluster = planPreview?.cluster_intent_preview ?? objectValue(intent.cluster);
  const svm = planPreview?.svm_intent_preview ?? objectValue(intent.svm);
  const lifIntent = planPreview?.lif_intent_preview ?? { iscsi_lifs: objectValue(intent).iscsi_lifs };
  const nodes = recordArray(cluster.nodes);
  const lifs = recordArray(lifIntent.iscsi_lifs);
  const storageIscsiPlan = planPreview?.storage_iscsi_plan_preview ?? objectValue(provider.discovery?.storage_iscsi_plan_preview);
  const plannedTargets = objectValue(planPreview?.planned_targets);
  const currentDiscoveredTargets = objectValue(
    planPreview?.current_discovered_targets ?? provider.configuration.current_discovered_targets
  );
  const apiFlags = objectValue(plannedTargets.api_access_flags ?? provider.configuration.api_configured_flags);
  const targetAddressing = recordArray(plannedTargets.target_addressing).length
    ? recordArray(plannedTargets.target_addressing)
    : recordArray(provider.configuration.target_addressing);
  const currentAddressing = netappCurrentAddressRows(currentDiscoveredTargets);
  const artifactPlaceholders = planPreview?.artifact_placeholders.length
    ? planPreview.artifact_placeholders
    : stringArray(provider.discovery?.reports_artifacts).length
      ? stringArray(provider.discovery?.reports_artifacts)
      : stringArray(provider.configuration.artifact_placeholders);
  const blockers = planPreview?.blockers ?? provider.blockers;
  const removableWarnings = planPreview?.removable_warnings ?? provider.warnings;
  const readinessSummary = planPreview?.readiness_summary ?? {};
  const runtimeState = objectValue(planPreview?.runtime_state ?? provider.configuration.runtime_state);
  const runtimeConsole = objectValue(runtimeState.console);

  return (
    <div className="provider-detail-section netapp-setup">
      <div className="provider-callout netapp-apply-disabled">
        <strong>Live readiness / Apply disabled</strong>
        <p>
          Current and planned target evidence is shown for the lab. Cluster creation, IP changes,
          SVM/LIF creation, volume provisioning, ONTAP upgrades, controller reboots, disk wipes,
          and configuration apply are disabled.
        </p>
      </div>
      <div className="provider-callout">
        <strong>Readiness endpoint</strong>
        <p>
          {planError
            ? `Readiness endpoint unavailable: ${planError}`
            : planPreview
              ? "Loaded from NetApp live readiness data."
              : "Loading structured readiness."}
        </p>
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Configured State" value={asBoolean(planPreview?.netapp_configured ?? provider.configuration.netapp_configured) ? "Verified by live check" : labelize(asString(runtimeState.configured_state) || "not verified")} />
        <ProviderFact label="Manual Env Flag" value="Not required" />
        <ProviderFact label="Console" value={asString(runtimeConsole.discovered_port) || "Not detected"} />
        <ProviderFact label="Console Source" value={labelize(asString(runtimeConsole.source) || "none")} />
        <ProviderFact label="Apply Enabled" value={asBoolean(planPreview?.apply_enabled) ? "Enabled" : "Disabled"} />
        <ProviderFact label="Cluster Management" value={addressFor(targetAddressing, "Cluster management")} />
        <ProviderFact label="Node Management" value={`${addressFor(targetAddressing, "Node A management / e0M")} / ${addressFor(targetAddressing, "Node B management / e0M")}`} />
        <ProviderFact label="SVM Management" value={addressFor(targetAddressing, "SVM management")} />
        <ProviderFact label="API Endpoint" value={presenceLabel(apiFlags.endpoint_configured)} />
        <ProviderFact label="API Username" value={presenceLabel(apiFlags.username_configured)} />
        <ProviderFact label="API Access" value={presenceLabel(apiFlags.access_configured ?? apiFlags.credential_configured)} />
        <ProviderFact label="TLS Verify" value={asBoolean(apiFlags.tls_verify) ? "Enabled" : "Disabled"} />
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Readiness Status" value={labelize(asString(readinessSummary.status) || provider.status)} />
        <ProviderFact label="Buckets" value={asString(readinessSummary.bucket_count) || "-"} />
        <ProviderFact label="Not Ready" value={asString(readinessSummary.not_ready_count) || "-"} />
        <ProviderFact label="Next Safe Action" value={planPreview?.next_safe_action || safeNextAction(provider)} />
      </div>
      <AdvancedDetails
        className="provider-workflow-details"
        summary="Planned targets, readiness buckets, storage readiness, upgrade readiness, and artifacts"
        title="NetApp live evidence"
      >
      <h3>Planned Targets</h3>
      <KeyValueTable rows={targetAddressing} labelKey="label" valueKey="address" empty="No NetApp target addresses are planned." />
      <h3>Current / Discovered Targets</h3>
      <KeyValueTable rows={currentAddressing} labelKey="label" valueKey="address" empty="No NetApp current targets have been discovered." />
      <h3>Readiness Buckets</h3>
      <NetAppReadinessGrid readiness={readiness} />
      <h3>Blockers / Removable Warnings</h3>
      <NetAppIssueSummary blockers={blockers} warnings={removableWarnings} />
      <h3>Cluster / SVM / LIF Intent</h3>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Cluster Management IP" value={asString(cluster.management_ip) || "-"} />
        <ProviderFact label="SVM Management IP" value={asString(svm.management_ip) || "-"} />
      </div>
      <KeyValueTable rows={nodes} labelKey="name" valueKey="management_ip" empty="No node management intent is planned." />
      <KeyValueTable rows={lifs} labelKey="name" valueKey="address" empty="No iSCSI LIF intent is planned." />
      <h3>Storage / iSCSI Readiness</h3>
      <div className="provider-callout">
        <strong>{labelize(asString(storageIscsiPlan.status) || "placeholder")}</strong>
        {stringArray(storageIscsiPlan.notes).map((note) => (
          <p key={note}>{note}</p>
        ))}
        {!stringArray(storageIscsiPlan.notes).length && (
          <p>Placeholder only. No volumes, LIFs, LUNs, or igroups are created.</p>
        )}
      </div>
      <h3>Upgrade Readiness</h3>
      <div className="provider-callout">
        <strong>{operatorReadinessLabel(asString(planPreview?.upgrade_readiness_preview.status) || "not_checked")}</strong>
        {stringArray(planPreview?.upgrade_readiness_preview.details).map((detail) => (
          <p key={detail}>{detail}</p>
        ))}
      </div>
      <h3>Artifact / Report Placeholders</h3>
      {artifactPlaceholders.length ? (
        <div className="tag-row netapp-artifact-row">
          {artifactPlaceholders.map((artifact) => (
            <span key={artifact}>{artifact}</span>
          ))}
        </div>
      ) : (
        <p className="muted">No NetApp artifact placeholders are defined.</p>
      )}
      </AdvancedDetails>
    </div>
  );
}

function NetAppReadinessGrid({ readiness }: { readiness: Record<string, unknown> }) {
  const rows: Array<[string, Record<string, unknown>]> = [
    ["SP Readiness", objectValue(readiness.sp_readiness)],
    ["Cluster Management", objectValue(readiness.cluster_management_readiness)],
    ["Node Management", objectValue(readiness.node_management_readiness)],
    ["SVM", objectValue(readiness.svm_readiness)],
    ["iSCSI LIFs", objectValue(readiness.iscsi_lif_readiness)],
    ["ONTAP API", objectValue(readiness.ontap_api_readiness)],
    ["API Access", objectValue(readiness.api_access_readiness)],
    ["Local Readonly Ack", objectValue(readiness.local_readonly_ack_readiness)],
    ["Console / Bootstrap", objectValue(readiness.console_bootstrap_readiness)],
    ["Upgrade Path", objectValue(readiness.upgrade_readiness_path)],
    ["Storage / iSCSI", objectValue(readiness.storage_iscsi_plan_preview)],
    ["Reports / Artifacts", objectValue(readiness.reports_artifacts)]
  ];

  return (
    <div className="netapp-readiness-grid">
      {rows.map(([label, value]) => {
        const details = stringArray(value.details);
        return (
          <div className="provider-callout" key={label}>
            <strong>{label}: {labelize(asString(value.status) || "unknown")}</strong>
            <p>{asBoolean(value.ready) ? "Ready for read-only review." : "Not ready for execution."}</p>
            {details.length > 0 && (
              <ul>
                {details.map((detail) => (
                  <li key={detail}>{detail}</li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}

function NetAppIssueSummary({ blockers, warnings }: { blockers: string[]; warnings: string[] }) {
  if (!blockers.length && !warnings.length) {
    return <p className="muted">No NetApp blockers or removable warnings are reported.</p>;
  }

  return (
    <div className="provider-issue-rows">
      {blockers.map((blocker) => (
        <div className="provider-issue blocker" key={blocker}>
          <Ban size={16} />
          <span>{blocker}</span>
        </div>
      ))}
      {warnings.map((warning) => (
        <div className="provider-issue warning removable" key={warning}>
          <AlertTriangle size={16} />
          <span>Removable warning: {warning}</span>
        </div>
      ))}
    </div>
  );
}

function KeyValueTable({
  empty,
  labelKey,
  rows,
  valueKey
}: {
  empty: string;
  labelKey: string;
  rows: Array<Record<string, unknown>>;
  valueKey: string;
}) {
  if (!rows.length) {
    return <p className="muted">{empty}</p>;
  }

  return (
    <table className="provider-candidate-table netapp-intent-table">
      <thead>
        <tr>
          <th>Item</th>
          <th>Planned Value</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const label = asString(row[labelKey]);
          const value = asString(row[valueKey]);
          return (
            <tr key={`${label}-${value}`}>
              <td>
                <strong>{label || "-"}</strong>
              </td>
              <td>{value || "-"}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function GenericProviderDetails({ provider }: { provider: ProviderStatus }) {
  const configFacts = Object.entries(provider.configuration)
    .filter(([key, value]) => key.endsWith("_configured") && typeof value === "boolean")
    .slice(0, 6);
  const toolFacts = Object.entries(provider.configuration)
    .filter(([key, value]) => key.endsWith("_available") && typeof value === "boolean")
    .slice(0, 6);

  return (
    <div className="provider-detail-section">
      <div className="provider-fact-grid compact">
        <ProviderFact label="Provider" value={provider.name} />
        <ProviderFact label="Status" value={labelize(provider.status)} />
        {configFacts.map(([key, value]) => (
          <ProviderFact key={key} label={labelize(key)} value={presenceLabel(value)} />
        ))}
        {toolFacts.map(([key, value]) => (
          <ProviderFact key={key} label={labelize(key)} value={asBoolean(value) ? "Available" : "Missing"} />
        ))}
      </div>
    </div>
  );
}

function ProviderIssueRows({ blockers, warnings }: { blockers: string[]; warnings: string[] }) {
  if (!blockers.length && !warnings.length) {
    return null;
  }

  return (
    <div className="provider-issue-rows">
      {blockers.map((blocker) => (
        <div className="provider-issue blocker" key={blocker}>
          <Ban size={16} />
          <span>{blocker}</span>
        </div>
      ))}
      {warnings.map((warning) => (
        <div className="provider-issue warning" key={warning}>
          <AlertTriangle size={16} />
          <span>{warning}</span>
        </div>
      ))}
    </div>
  );
}

function ProviderActionRows({
  busy,
  disabledActions,
  onProbe,
  safeActions
}: {
  busy: boolean;
  disabledActions: ProviderAction[];
  onProbe: () => void;
  safeActions: ProviderAction[];
}) {
  return (
    <div className="provider-action-layout">
      {safeActions.length > 0 && (
        <div>
          <h3>Read-Only Actions</h3>
          <div className="provider-action-row">
            {safeActions.map((action) => (
              <div className="provider-action-item" key={action.id}>
                <button
                  className={action.enabled ? "primary" : ""}
                  disabled={!action.enabled || busy}
                  onClick={onProbe}
                >
                  <Play size={16} />
                  {busy ? "Running" : action.label}
                </button>
                <span className="action-tag read-only">Read only</span>
                <p>{action.reason}</p>
              </div>
            ))}
          </div>
        </div>
      )}
      {disabledActions.length > 0 && (
        <AdvancedDetails
          className="disabled-actions-details"
          summary={`${disabledActions.length} protected action${disabledActions.length === 1 ? "" : "s"} remain unavailable`}
          title="Protected actions"
        >
          <div className="provider-action-row">
            {disabledActions.map((action) => (
              <div className="provider-action-item" key={action.id}>
                <button disabled>
                  <Ban size={16} />
                  {action.label}
                </button>
                <span className="action-tag disabled">Disabled</span>
                <p>{action.reason}</p>
              </div>
            ))}
          </div>
        </AdvancedDetails>
      )}
    </div>
  );
}

function providerIcon(provider: ProviderStatus) {
  if (provider.id === "ilo-redfish") return <ShieldCheck size={18} />;
  if (provider.id === "cisco-console") return <Activity size={18} />;
  if (provider.id === "cisco-ansible") return <Route size={18} />;
  if (provider.id === "esxi-readonly") return <Server size={18} />;
  if (provider.kind === "virtualization") return <Server size={18} />;
  return <HardDrive size={18} />;
}

function buildProviderSections(providers: ProviderStatus[]): ProviderSection[] {
  const sectionDefinitions: Array<Omit<ProviderSection, "providerIds" | "status"> & { ids: string[] }> = [
    { id: "ilo", label: "iLO", ids: ["ilo-redfish"] },
    { id: "cisco", label: "Cisco", ids: ["cisco-console", "cisco-ansible"] },
    { id: "esxi", label: "ESXi", ids: ["esxi-readonly"] },
    { id: "netapp", label: "NetApp", ids: ["netapp-ontap"] }
  ];
  const assignedIds = new Set(sectionDefinitions.flatMap((section) => section.ids));
  const sections = sectionDefinitions
    .map((section) => {
      const sectionProviders = providers.filter((provider) => section.ids.includes(provider.id));
      return {
        id: section.id,
        label: section.label,
        providerIds: sectionProviders.map((provider) => provider.id),
        status: providerSectionStatus(sectionProviders)
      };
    })
    .filter((section) => section.providerIds.length > 0);
  const otherProviders = providers.filter((provider) => !assignedIds.has(provider.id));
  if (otherProviders.length > 0) {
    sections.push({
      id: "other",
      label: "Other",
      providerIds: otherProviders.map((provider) => provider.id),
      status: providerSectionStatus(otherProviders)
    });
  }
  return sections;
}

function providerSectionStatus(providers: ProviderStatus[]): string {
  if (!providers.length) return "missing-config";
  const statuses = providers.map((provider) => provider.status);
  if (statuses.some((status) => ["failed", "blocked", "unavailable"].includes(status))) {
    return statuses.find((status) => ["failed", "blocked", "unavailable"].includes(status)) ?? "blocked";
  }
  if (statuses.some((status) => ["missing-config", "missing-console", "needs-selection", "planned-target", "awaiting-bootstrap"].includes(status))) {
    return statuses.find((status) => ["missing-config", "missing-console", "needs-selection", "planned-target", "awaiting-bootstrap"].includes(status)) ?? "warning";
  }
  if (statuses.some((status) => status === "ready" || status === "ok" || status === "available")) {
    return "ready";
  }
  return statuses[0] ?? "configured";
}

function isReadyStatus(status: string): boolean {
  return ["ready", "ok", "available", "completed", "passed", "ready_for_preview", "ready_for_deploy"].includes(status);
}

function isAttentionStatus(status: string): boolean {
  return ["blocked", "failed", "unavailable", "needs-attention", "error"].includes(status);
}

function isWaitingStatus(status: string): boolean {
  return [
    "awaiting-bootstrap",
    "blocked_by_prior_stage",
    "missing-config",
    "missing-console",
    "needs-selection",
    "not-configured",
    "planned-target",
    "pending",
    "waiting"
  ].includes(status);
}

function statusTone(status: string): string {
  if (isReadyStatus(status)) return "tone-ready";
  if (isAttentionStatus(status)) return "tone-attention";
  if (isWaitingStatus(status)) return "tone-waiting";
  return "tone-neutral";
}

function displayStatusLabel(status: string): string {
  const normalized = status || "unknown";
  const labels: Record<string, string> = {
    "api_access_present": "Management access configured",
    "awaiting-bootstrap": "Waiting",
    "blocked_by_prior_stage": "Waiting on earlier step",
    blocked: "Needs attention",
    checking: "Checking",
    "cluster_setup_wizard": "Setup wizard detected",
    "console bootstrap required": "Console bootstrap required",
    "console_bootstrap_required": "Console bootstrap required",
    completed: "Ready",
    disabled: "Disabled",
    critical: "Blocked",
    failed: "Needs attention",
    "guarded_write": "Guarded write",
    hard_fail: "Blocked",
    historical: "Previous evidence",
    historical_artifact: "Previous evidence",
    info: "Info",
    live_cached: "Recent live check",
    live_probe: "Live check",
    "live_readiness": "Readiness check",
    "local-lab-readwrite": "Real lab",
    "local-readonly": "Read-only lab",
    manual_review: "Needs review",
    "missing-config": "Not configured yet",
    "missing-console": "Console not found",
    mock: "Test Mode",
    "needs-attention": "Needs attention",
    "needs-selection": "Needs selection",
    not_configured_yet: "Not set up yet",
    not_checked: "Not checked",
    "not-configured": "Not configured yet",
    "not-run": "Not run",
    ok: "Ready",
    operator_action_required: "Needs action",
    passed: "Ready",
    "pending_restart": "Restart required",
    "planned-target": "Planned",
    ready: "Ready",
    ready_for_deploy: "Ready for deploy",
    ready_for_preview: "Ready for preview",
    "read_only": "Read only",
    "report_only": "Report only",
    "safe_default": "Safe default",
    "setup_intent_missing": "Setup details missing",
    deploy_disabled: "Deploy disabled",
    stale: "Stale",
    stale_config: "Old config needs review",
    success: "Ready",
    test_fixture: "Test mode",
    "upgrade_disabled": "Upgrade disabled",
    unverified: "Unverified",
    unavailable: "Not available",
    waiting: "Waiting"
  };
  return labels[normalized] ?? labelize(normalized);
}

function displayModeLabel(mode: string): string {
  if (mode === "local-lab-readwrite") return "Real lab";
  if (mode === "local-readonly") return "Read-only lab";
  if (mode === "mock") return "Test Mode";
  return displayStatusLabel(mode);
}

function resultSourceLabel(payload: unknown): string {
  if (!payload) return "not checked";
  const item = objectValue(payload);
  const sourceType = asString(item.source_type);
  const freshness = asString(item.freshness);
  const checkedAt = asString(item.checked_at);
  if (sourceType === "test_fixture" || asString(item.provider_mode) === "mock") return "test";
  if (sourceType === "not_checked" || (!sourceType && !checkedAt)) return "not checked";
  if (sourceType === "historical_artifact" || freshness === "stale" || (sourceType && !asBoolean(item.is_current))) {
    return "stale";
  }
  if (sourceType === "live_probe") return "live check";
  if (sourceType === "live_cached" || checkedAt) return "last live result";
  return labelize(sourceType || freshness || "unknown").toLowerCase();
}

function resultFreshnessLabel(payload: unknown): string {
  const item = objectValue(payload);
  return labelize(asString(item.freshness) || (asString(item.checked_at) ? "current" : "unknown"));
}

function providerSourceOverview(providers: ProviderStatus[]): string {
  if (!providers.length) return "not checked";
  if (providers.some((provider) => provider.source_type === "test_fixture")) return "test";
  if (providers.some((provider) => provider.is_current && ["live_probe", "live_cached"].includes(provider.source_type))) {
    return "last live result";
  }
  if (providers.some((provider) => provider.source_type === "not_checked")) return "not checked";
  return "stale";
}

function humanizeAction(value: string): string {
  if (!value) return "Review this stage.";
  return [
    ["provider-lab-netapp-ontap-upgrade-validate", "Validate ONTAP upgrade"],
    ["provider-lab-netapp-ontap-upgrade-plan", "Plan ONTAP upgrade"],
    ["provider-lab-netapp-ontap-upgrade-inventory", "Check ONTAP upgrade package"],
    ["provider-lab-netapp-setup-preview", "Preview NetApp setup"],
    ["provider-lab-netapp-setup-apply", "Apply NetApp setup"],
    ["make provider-lab-build-verification-live", "Run Build Verification"],
    ["provider-lab-build-verification", "Run Build Verification"],
    ["blocked_by_prior_stage", "waiting on earlier step"],
    ["stale_config", "old lab IP detected"],
    ["operator_action_required", "needs your action"],
    ["local-lab-readwrite", "Real Lab Mode"],
    ["historical_artifact", "previous evidence"],
    ["live_probe", "live check"],
    ["cluster_setup_wizard", "Setup wizard detected"],
    ["not_configured_yet", "Not configured yet"],
    ["NETAPP_SETUP_APPLY missing", "Setup apply not enabled"],
    ["NETAPP_CONFIGURED=false", "NetApp is not verified by live check yet"],
    ["NETAPP_CONFIGURED=true", "legacy NetApp env flag"],
    ["Redfish PATCH accepted", "iLO accepted the storage change"],
    ["GET-only", "read-only"],
    ["GET-Only", "Read-only"]
  ].reduce((current, [from, to]) => current.split(from).join(to), value)
    .replace(/active lab profile/g, "active lab setup")
    .replace(/Active lab profile/g, "Active lab setup")
    .replace(/lab profile/g, "lab setup")
    .replace(/Lab Profile/g, "Lab Setup")
    .replace(/Review gates, then copy [`'"]?[^`'"]*make [^`'"]+[`'"]? when this stage is in scope\./g, "Open Advanced when this step is in scope.")
    .replace(/Run [`'"]?Run Build Verification[`'"]? with PROVIDER_MODE=local-lab-readwrite\.?/g, "Run Build Verification in Real Lab Mode.")
    .replace(/PROVIDER_MODE=local-lab-readwrite/g, "Real Lab Mode")
    .replace(/Run [`'"]?Run Build Verification[`'"]? with (?:PROVIDER_MODE=)?Real Lab Mode\.?/g, "Run Build Verification in Real Lab Mode.")
    .replace(/PROVIDER_MODE=mock cannot contact or modify real devices for [a-z0-9._-]+\.?/gi, "Test mode cannot check hardware for this step.");
}

function humanizeBlocker(value: string): string {
  if (!value || value === "No blocker reported.") return "No blocker reported.";
  return humanizeAction(value)
    .replace("Complete or confirm Cisco console bootstrap", "Finish Cisco console bootstrap")
    .replace("Install/configure ESXi management", "Install or configure ESXi management");
}

function humanizeReportTitle(value: string): string {
  return displayStatusLabel(humanizeAction(value || "Report finding"));
}

function reportLinksFromProbe(prefix: string, probe: ProviderProbeResult | null): ReportLink[] {
  const artifacts = objectValue(probe?.artifacts);
  return Object.entries(artifacts)
    .map(([key, value]) => ({
      label: `${prefix} ${labelize(key)}`,
      path: asString(value),
      status: probe?.status ?? "report_available"
    }))
    .filter((report) => report.path.length > 0);
}

function workflowProbeEvidenceCount(probe: ProviderProbeResult | null): number {
  const artifacts = objectValue(probe?.artifacts);
  return Object.values(artifacts).filter((value) => Boolean(asString(value))).length;
}

function probeEvidencePaths(probe: ProviderProbeResult | null): string[] {
  const artifacts = objectValue(probe?.artifacts);
  return Object.values(artifacts)
    .map((value) => asString(value))
    .filter(Boolean);
}

function reportLinksFromActions(actions: ControlAction[]): ReportLink[] {
  return actions
    .filter((action) => action.last_report)
    .map((action) => ({
      label: action.label,
      path: action.last_report ?? "",
      status: action.last_run_status
    }));
}

function filterReportLinks(section: LegacyReportSectionId, reports: ReportLink[]): ReportLink[] {
  if (section === "latest") return reports.slice(0, 16);
  const tokensBySection: Record<LegacyReportSectionId, string[]> = {
    latest: [],
    cisco: ["cisco"],
    ilo: ["ilo", "hpe", "redfish", "server"],
    raid: ["raid", "storage"],
    esxi: ["esxi"],
    netapp: ["netapp", "ontap"],
    firmware: ["firmware", "upgrade", "waiver"],
    verification: ["verification", "certification", "rebuild"]
  };
  const tokens = tokensBySection[section];
  return reports.filter((report) => {
    const text = `${report.label} ${report.path}`.toLowerCase();
    return tokens.some((token) => text.includes(token));
  });
}

function filterProviderArtifacts(section: LegacyReportSectionId, artifacts: NetAppProviderArtifact[]): NetAppProviderArtifact[] {
  if (section === "latest") return artifacts.slice(0, 8);
  const tokensBySection: Record<LegacyReportSectionId, string[]> = {
    latest: [],
    cisco: ["cisco"],
    ilo: ["ilo", "hpe"],
    raid: ["raid", "storage"],
    esxi: ["esxi"],
    netapp: ["netapp", "ontap"],
    firmware: ["firmware", "upgrade", "waiver"],
    verification: ["verification", "certification", "rebuild"]
  };
  const tokens = tokensBySection[section];
  return artifacts.filter((artifact) => {
    const text = `${artifact.provider_id} ${artifact.title} ${artifact.kind} ${artifact.description}`.toLowerCase();
    return tokens.some((token) => text.includes(token));
  });
}

function needsCiscoPasswordRecoveryAction(realLabRun: Record<string, unknown>): boolean {
  const promptState = asString(realLabRun.prompt_state);
  const lastBlocker = asString(realLabRun.last_blocker).toLowerCase();
  return (
    ["login-required", "exec", "rommon-bootloader", "password-recovery-ready"].includes(promptState) &&
    lastBlocker.includes("privileged exec")
  ) || lastBlocker.includes("password recovery");
}

function stageStatusFromVerification(
  verification: ProviderProbeResult | null,
  keyword: string
): string {
  const blocker = stringArray(verification?.blockers).find((item) =>
    item.toLowerCase().includes(keyword.toLowerCase())
  );
  return blocker ? "blocked_by_prior_stage" : "not-run";
}

function providerOrder(id: string): number {
  const order = [
    "ilo-redfish",
    "cisco-console",
    "cisco-ansible",
    "esxi-readonly",
    "mock-vsphere",
    "netapp-ontap",
    "mock-network-switch",
    "mock-opentofu",
    "mock-awx",
    "mock-source-of-truth"
  ];
  const index = order.indexOf(id);
  return index === -1 ? order.length : index;
}

function safeNextAction(provider: ProviderStatus): string {
  const discoveryNextAction = asString(provider.discovery?.safe_next_action);
  if (discoveryNextAction) return discoveryNextAction;
  const configuredNextAction = asString(provider.configuration.safe_next_action);
  if (configuredNextAction) return configuredNextAction;
  const enabledAction = provider.safe_actions.find((action) => action.enabled);
  if (enabledAction) return enabledAction.reason;
  if (provider.blockers.length > 0) return provider.blockers[0];
  if (provider.safe_actions.length > 0) return provider.safe_actions[0].reason;
  return "Review status only; no runnable action is exposed.";
}

function promptReadinessMessage(result: ProviderProbeResult): string {
  const promptState = asString(result.prompt_state);
  const promptSample = objectValue(result.prompt_sample);
  if (promptState === "unknown" && !asBoolean(promptSample.captured)) {
    return "Console port opened, but no prompt text was captured.";
  }
  if (promptState === "exec") {
    return "Prompt is ready for future safe show-command checks.";
  }
  if (promptState === "setup-wizard") {
    return "Console is at an initial setup wizard prompt; no answers or commands were sent.";
  }
  return asString(result.message) || "Prompt readiness result is redacted.";
}

function requirementLine(label: string, requirement: Record<string, unknown>): string {
  const value = asString(requirement.value);
  return `${label}: ${value || "Missing"}`;
}

function bootstrapRequirementsForm(
  requirements: CiscoBootstrapRequirements
): CiscoBootstrapRequirementsUpdate {
  const items = objectValue(requirements.requirements);
  const managementStrategy = objectValue(items.management_vlan_interface_strategy);
  const domainDns = objectValue(items.domain_dns);
  const localAdmin = objectValue(items.local_admin_username);
  const operatorNotes = objectValue(items.operator_notes);

  return {
    planned_management_ip:
      asString(objectValue(items.planned_management_ip).value),
    subnet_prefix: asString(objectValue(items.subnet_prefix).value),
    gateway: asString(objectValue(items.gateway).value),
    management_vlan: asString(managementStrategy.vlan) || null,
    management_interface: asString(managementStrategy.interface) || null,
    management_strategy: asString(managementStrategy.strategy),
    hostname: asString(objectValue(items.hostname).value),
    domain_name: asString(domainDns.domain_name),
    dns_servers: stringArray(domainDns.dns_servers),
    local_admin_username_configured: asBoolean(localAdmin.configured),
    local_admin_username_reference: asString(localAdmin.reference) || null,
    operator_notes: asString(operatorNotes.value) || null
  };
}

function iloSetupIntentForm(intent: IloSetupIntent | null): IloSetupIntentWrite {
  return {
    network: {
      hostname: intent?.network.hostname ?? "",
      management_ip: intent?.network.management_ip ?? "",
      subnet_mask_or_prefix: intent?.network.subnet_mask_or_prefix ?? "",
      gateway: intent?.network.gateway ?? "",
      vlan: intent?.network.vlan ?? ""
    },
    users: intent?.users.length
      ? intent.users.map((user) => ({
          username_label: user.username_label,
          role: user.role
        }))
      : [],
    snmp: {
      enabled: intent?.snmp.enabled ?? false,
      destinations: intent?.snmp.destinations ?? [],
      community_or_user_ref_labels: intent?.snmp.community_or_user_ref_labels ?? []
    },
    time: {
      timezone: intent?.time.timezone ?? "",
      ntp_servers: intent?.time.ntp_servers ?? []
    },
    dns_domain: {
      domain_name: intent?.dns_domain.domain_name ?? "",
      dns_servers: intent?.dns_domain.dns_servers ?? []
    },
    notes: intent?.notes ?? ""
  };
}

function cleanIloSetupIntent(form: IloSetupIntentWrite): IloSetupIntentWrite {
  return {
    network: {
      hostname: blankToNull(form.network.hostname),
      management_ip: blankToNull(form.network.management_ip),
      subnet_mask_or_prefix: blankToNull(form.network.subnet_mask_or_prefix),
      gateway: blankToNull(form.network.gateway),
      vlan: blankToNull(form.network.vlan)
    },
    users: form.users
      .map((user) => ({
        username_label: user.username_label.trim(),
        role: user.role.trim()
      }))
      .filter((user) => user.username_label && user.role),
    snmp: {
      enabled: form.snmp.enabled,
      destinations: form.snmp.destinations.map((item) => item.trim()).filter(Boolean),
      community_or_user_ref_labels: form.snmp.community_or_user_ref_labels
        .map((item) => item.trim())
        .filter(Boolean)
    },
    time: {
      timezone: blankToNull(form.time.timezone),
      ntp_servers: form.time.ntp_servers.map((item) => item.trim()).filter(Boolean)
    },
    dns_domain: {
      domain_name: blankToNull(form.dns_domain.domain_name),
      dns_servers: form.dns_domain.dns_servers.map((item) => item.trim()).filter(Boolean)
    },
    notes: blankToNull(form.notes)
  };
}

function hpeRaidIntentForm(intent: HpeRaidIntent | null): HpeRaidIntentWrite {
  return {
    controller_ref: intent?.controller_ref ?? "",
    wipe_existing_logical_drives: intent?.wipe_existing_logical_drives ?? false,
    volumes: intent?.volumes.length
      ? intent.volumes.map((volume) => ({
          name: volume.name,
          purpose: volume.purpose,
          raid_level: volume.raid_level,
          drive_bays: volume.drive_bays,
          spare_bays: volume.spare_bays ?? [],
          spare_rebuild_mode: volume.spare_rebuild_mode ?? null,
          size_policy: volume.size_policy,
          bootable: volume.bootable
        }))
      : [],
    notes: intent?.notes ?? ""
  };
}

function cleanHpeRaidIntent(form: HpeRaidIntentWrite): HpeRaidIntentWrite {
  return {
    controller_ref: blankToNull(form.controller_ref),
    wipe_existing_logical_drives: form.wipe_existing_logical_drives,
    volumes: form.volumes
      .map((volume) => ({
        name: volume.name.trim(),
        purpose: volume.purpose.trim(),
        raid_level: volume.raid_level.trim(),
        drive_bays: volume.drive_bays.map((bay) => bay.trim()).filter(Boolean),
        spare_bays: (volume.spare_bays ?? []).map((bay) => bay.trim()).filter(Boolean),
        spare_rebuild_mode: blankToNull(volume.spare_rebuild_mode),
        size_policy: volume.size_policy.trim() || "max",
        bootable: volume.bootable
      }))
      .filter((volume) => volume.name && volume.purpose && volume.raid_level),
    notes: blankToNull(form.notes)
  };
}

function controllerValue(controller: Record<string, unknown> | undefined): string {
  if (!controller) return "";
  return (
    asString(controller["@odata.id"]) ||
    asString(controller.Id) ||
    asString(controller.Name) ||
    controllerLabel(controller)
  );
}

function controllerLabel(controller: Record<string, unknown> | undefined): string {
  if (!controller) return "Controller";
  return (
    asString(controller.Name) ||
    asString(controller.Model) ||
    asString(controller.Id) ||
    "Controller"
  );
}

function statusHealth(item: Record<string, unknown>): string {
  const status = objectValue(item.Status);
  return asString(status.Health) || asString(status.State) || asString(item.health) || "unknown";
}

function blankToNull(value: string | null): string | null {
  const trimmed = (value ?? "").trim();
  return trimmed ? trimmed : null;
}

function splitCsvInput(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function objectValue(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function recordArray(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is Record<string, unknown> =>
      Boolean(item) && typeof item === "object" && !Array.isArray(item)
  );
}

function addressFor(rows: Array<Record<string, unknown>>, label: string): string {
  const row = rows.find((item) => asString(item.label) === label);
  return asString(row?.address) || "-";
}

function netappCurrentAddressRows(targets: Record<string, unknown>): Array<Record<string, unknown>> {
  const spIps = objectValue(targets.sp_ips ?? targets.controller_sp);
  const managementIps = objectValue(targets.management_ips);
  const lifRange = objectValue(targets.iscsi_lif_range);
  const lifAddresses = stringArray(lifRange.addresses);
  return [
    { label: "Controller A SP", address: asString(spIps.controller_a) || "Not discovered" },
    { label: "Controller B SP", address: asString(spIps.controller_b) || "Not discovered" },
    { label: "Cluster management", address: asString(managementIps.cluster) || "Not discovered" },
    { label: "Node A management / e0M", address: asString(managementIps.node_a) || "Not discovered" },
    { label: "Node B management / e0M", address: asString(managementIps.node_b) || "Not discovered" },
    { label: "SVM management", address: asString(managementIps.svm) || "Not discovered" },
    {
      label: "iSCSI LIFs",
      address: lifAddresses.length ? lifAddresses.join(", ") : "Not discovered"
    }
  ];
}

function consoleCandidates(value: unknown): ConsoleCandidate[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isConsoleCandidate);
}

function isConsoleCandidate(value: unknown): value is ConsoleCandidate {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.path === "string" &&
    typeof candidate.stable_path === "boolean" &&
    typeof candidate.exists === "boolean" &&
    typeof candidate.recommendation === "string"
  );
}

function asString(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function asBoolean(value: unknown): boolean {
  return value === true;
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" ? value : fallback;
}

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}

function presenceLabel(value: unknown): string {
  return asBoolean(value) ? "Configured" : "Missing";
}

function yesNo(value: boolean): string {
  return value ? "Yes" : "No";
}

function accessLabel(candidate: ConsoleCandidate): string {
  const readable = candidate.readable === null ? "unknown" : yesNo(candidate.readable);
  const writable = candidate.writable === null ? "unknown" : yesNo(candidate.writable);
  return `read ${readable} / write ${writable} / in use ${yesNo(candidate.in_use)}`;
}

function QueueSectionPanel({
  onSelect,
  section,
  selectedKey
}: {
  onSelect: (key: string) => void;
  section: QueueSection;
  selectedKey: string;
}) {
  return (
    <div className="panel queue-section">
      <PanelTitle icon={<ClipboardList size={18} />} title={section.title} />
      <QueueItemList
        empty={section.empty}
        items={section.items}
        onSelect={onSelect}
        selectedKey={selectedKey}
      />
    </div>
  );
}

function QueueItemList({
  empty,
  items,
  onSelect,
  selectedKey
}: {
  empty: string;
  items: QueueItem[];
  onSelect?: (key: string) => void;
  selectedKey?: string;
}) {
  if (!items.length) {
    return <p className="muted">{empty}</p>;
  }

  return (
    <div className="queue-list">
      {items.map((item) =>
        onSelect ? (
          <button
            className={item.key === selectedKey ? "queue-card selected" : "queue-card"}
            key={item.key}
            onClick={() => onSelect(item.key)}
            type="button"
          >
            <QueueCardContent item={item} />
          </button>
        ) : (
          <Link className="queue-card queue-link" key={item.key} to={queueItemLink(item)}>
            <QueueCardContent item={item} />
          </Link>
        )
      )}
    </div>
  );
}

function QueueCardContent({ item }: { item: QueueItem }) {
  return (
    <>
      <div className="queue-card-head">
        <strong>{item.title}</strong>
        <StatusBadge status={item.status} />
      </div>
      <p>{item.subtitle}</p>
      <span>{item.actionLabel}</span>
    </>
  );
}

type LifecycleActionView = {
  disabled: boolean;
  icon: ReactNode;
  label: string;
  onClick: () => void;
  reason: string;
};

function LifecycleAction({ action }: { action: LifecycleActionView }) {
  return (
    <div className="lifecycle-action">
      <button disabled={action.disabled} onClick={action.onClick}>
        {action.icon}
        {action.label}
      </button>
      <p className={action.disabled ? "action-reason blocked" : "action-reason ready"}>
        {action.reason}
      </p>
    </div>
  );
}

function WorkflowRunStructuredView({
  artifacts,
  events,
  run
}: {
  artifacts: ArtifactRecord[];
  events: AuditEvent[];
  run: WorkflowRun;
}) {
  const planSummary = planSummaryForRun(run);
  const planSteps = planStepsForRun(run);
  const executedSteps = executedStepsForRun(run);
  const stageEvents = stageEventsForRun(run);
  const review = reviewStateForRun(run);
  const result = resultSummaryForRun(run);

  return (
    <>
      <section className="panel safety-note">
        <PanelTitle icon={<ShieldCheck size={18} />} title="Local Preview Safety" />
        <p>
          This run uses provider <strong>{run.provider}</strong>. The plan and result are local preview data;
          no vCenter, ESXi, AWX, Terraform, OpenTofu, Redfish, ONTAP, switch, DNS, IPAM, or storage endpoint is called.
        </p>
      </section>
      <section className="panel">
        <PanelTitle icon={<ClipboardList size={18} />} title="Plan Summary" />
        <p className="structured-summary">{planSummary.summary}</p>
        <div className="detail-grid">
          <Info label="VM" value={planSummary.vmName} />
          <Info label="Template" value={planSummary.template} />
          <Info label="Placement" value={planSummary.placement} />
          <Info label="Storage" value={planSummary.storage} />
          <Info label="Network" value={planSummary.network} />
          <Info label="Sizing" value={planSummary.sizing} />
        </div>
        <div className="review-banner">
          <AlertTriangle size={18} />
          <div>
            <strong>{review.status}</strong>
            <p>{review.message}</p>
          </div>
        </div>
        <StepTable empty="No planned steps were recorded." steps={planSteps} />
      </section>
      <section className="panel">
        <PanelTitle icon={<Route size={18} />} title="Stage Timeline" />
        <StageList events={stageEvents} />
      </section>
      <section className="panel">
        <PanelTitle icon={<Play size={18} />} title="Execution Result" />
        <div className="detail-grid">
          <Info label="Result" value={result.message} />
          <Info label="Preview Task" value={result.mockTaskId} />
          <Info label="Preview VM" value={result.mockVmId} />
          <Info label="Provider" value={result.provider} />
        </div>
        <StepTable empty="Execution has not recorded completed steps yet." steps={executedSteps} />
      </section>
      <section className="panel">
        <PanelTitle icon={<History size={18} />} title="Logs And Events" />
        <AuditEventTable compact events={events} />
      </section>
      <section className="panel" id="artifacts">
        <PanelTitle icon={<HardDrive size={18} />} title="Artifacts And Reports" />
        <ArtifactGrid artifacts={artifacts} empty="No artifact metadata is available for this run yet." />
      </section>
      <section className="panel">
        <PanelTitle icon={<ClipboardList size={18} />} title="Raw Data" />
        <JsonDetails title="Raw plan JSON" data={run.plan_json} />
        {run.result_json && <JsonDetails title="Raw result JSON" data={run.result_json} />}
      </section>
    </>
  );
}

function StepTable({ empty, steps }: { empty: string; steps: PlanStep[] }) {
  if (!steps.length) {
    return <p className="muted">{empty}</p>;
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Step</th>
          <th>Status</th>
          <th>Target</th>
        </tr>
      </thead>
      <tbody>
        {steps.map((step) => (
          <tr key={`${step.name}-${step.target}`}>
            <td>{step.name}</td>
            <td>
              <StatusBadge status={step.status} />
            </td>
            <td>{step.target}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ArtifactGrid({ artifacts, empty }: { artifacts: ArtifactRecord[]; empty: string }) {
  if (!artifacts.length) {
    return <p className="muted">{empty}</p>;
  }

  return (
    <div className="artifact-grid">
      {artifacts.map((artifact) => (
        <ArtifactCard artifact={artifact} key={artifact.id} />
      ))}
    </div>
  );
}

function ArtifactCard({ artifact }: { artifact: ArtifactRecord }) {
  const metadata = artifactMetadataSummary(artifact);

  return (
    <article className="artifact-item">
      <div className="artifact-card-head">
        <strong>{artifact.title}</strong>
        <StatusBadge status={artifact.status} />
      </div>
      <p>{artifact.description}</p>
      <div className="artifact-meta">
        <span>{labelize(artifact.kind)}</span>
        <span>{artifact.downloadable ? "Download available" : "No file generated"}</span>
        {artifact.redacted && <span>Redacted</span>}
        {artifact.mock_only && <span>Test mode</span>}
      </div>
      {metadata.length > 0 && (
        <ul className="artifact-metadata">
          {metadata.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
      <div className="artifact-links">
        <Link to={`/requests/${artifact.request_id}`}>Request {artifact.request_id.slice(0, 8)}</Link>
        {artifact.workflow_run_id && (
          <Link to={`/workflow-runs/${artifact.workflow_run_id}`}>
            Run {artifact.workflow_run_id.slice(0, 8)}
          </Link>
        )}
      </div>
    </article>
  );
}

function artifactMetadataSummary(artifact: ArtifactRecord): string[] {
  const metadata = artifact.metadata ?? {};
  const items = [
    metadataSummaryItem("Provider", metadata.provider),
    metadataSummaryItem("Run status", metadata.run_status),
    metadataSummaryItem("Preview task", metadata.mock_task_id),
    metadataSummaryItem("Preview VM", metadata.mock_vm_id),
    metadataSummaryItem("Events", metadata.event_count),
    metadataSummaryItem("Steps", metadata.step_count)
  ].filter((item): item is string => Boolean(item));

  return items.slice(0, 4);
}

function metadataSummaryItem(label: string, value: unknown): string {
  const formatted = asString(value);
  return formatted ? `${label}: ${formatted}` : "";
}

function AuditEventTable({ compact, events }: { compact?: boolean; events: AuditEvent[] }) {
  if (!events.length) {
    return <p className="muted">No audit events found.</p>;
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Time</th>
          <th>Event</th>
          {!compact && <th>Actor</th>}
          <th>Links</th>
          <th>Status</th>
          <th>Message</th>
        </tr>
      </thead>
      <tbody>
        {events.map((event) => (
          <tr key={event.id}>
            <td>{formatDateTime(event.created_at)}</td>
            <td>{event.event_type}</td>
            {!compact && <td>{event.actor}</td>}
            <td>
              <div className="link-stack">
                {event.request_id && <Link to={`/requests/${event.request_id}`}>Request {event.request_id.slice(0, 8)}</Link>}
                {event.workflow_run_id && <Link to={`/workflow-runs/${event.workflow_run_id}`}>Run {event.workflow_run_id.slice(0, 8)}</Link>}
                {!event.request_id && !event.workflow_run_id && <span className="muted">-</span>}
              </div>
            </td>
            <td>{`${event.from_status ?? "-"} -> ${event.to_status ?? "-"}`}</td>
            <td>
              {event.message}
              {Object.keys(event.data_json ?? {}).length > 0 && (
                <details className="payload-details">
                  <summary>Payload</summary>
                  <pre>{JSON.stringify(event.data_json, null, 2)}</pre>
                </details>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function JsonDetails({ data, title }: { data: Record<string, unknown>; title: string }) {
  return (
    <details className="json-details">
      <summary>{title}</summary>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </details>
  );
}

function WorkflowRunTable({
  onSelect,
  runs,
  selectedRunId
}: {
  onSelect: (id: string) => void;
  runs: WorkflowRun[];
  selectedRunId: string;
}) {
  if (!runs.length) {
    return <p className="muted">No workflow runs yet.</p>;
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Run</th>
          <th>Status</th>
          <th>Provider</th>
          <th>Updated</th>
          <th>Review</th>
        </tr>
      </thead>
      <tbody>
        {runs.map((run) => (
          <tr className={run.id === selectedRunId ? "selected-row" : ""} key={run.id}>
            <td>
              <Link to={`/workflow-runs/${run.id}`}>{run.id.slice(0, 8)}</Link>
            </td>
            <td>
              <StatusBadge status={run.status} />
            </td>
            <td>{run.provider}</td>
            <td>{formatDateTime(run.updated_at)}</td>
            <td>
              <button className="small-button" onClick={() => onSelect(run.id)}>
                Review
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function StageList({ events }: { events: StageEvent[] }) {
  if (!events.length) {
    return <p className="muted">No stage events recorded for this run.</p>;
  }

  return (
    <div className="stage-list">
      {events.map((event) => (
        <article className="stage-item" key={event.stage}>
          <div>
            <strong>{event.stage}</strong>
            <StatusBadge status={event.status} />
          </div>
          <p>{event.message}</p>
        </article>
      ))}
    </div>
  );
}

function RequestTable({
  readinessByRequest,
  requests,
  showBlocked,
  showNextAction
}: {
  readinessByRequest?: ReadinessMap;
  requests: RequestRecord[];
  showBlocked?: boolean;
  showNextAction?: boolean;
}) {
  if (!requests.length) {
    return <p className="muted">No requests yet.</p>;
  }

  return (
    <table>
      <thead>
        <tr>
          <th>VM</th>
          <th>Status</th>
          <th>Environment</th>
          <th>Site</th>
          <th>Owner</th>
          {showBlocked && <th>Readiness</th>}
          {showNextAction && <th>Next Action</th>}
          <th>Updated</th>
        </tr>
      </thead>
      <tbody>
        {requests.map((request) => (
          <tr key={request.id}>
            <td>
              <Link to={`/requests/${request.id}`}>{request.vm_deploy.vm_name}</Link>
            </td>
            <td>
              <StatusBadge status={request.status} />
            </td>
            <td>{request.environment}</td>
            <td>{request.site}</td>
            <td>{request.owner}</td>
            {showBlocked && (
              <td>
                <ReadinessStatus readiness={readinessByRequest?.[request.id]} />
              </td>
            )}
            {showNextAction && (
              <td>{displayNextActionForRequest(request, readinessByRequest?.[request.id])}</td>
            )}
            <td>{formatDateTime(request.updated_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ReadinessStatus({ readiness }: { readiness: RequestReadiness | undefined }) {
  if (!readiness) {
    return <StatusBadge status="pending" />;
  }
  if (readiness.blockers.length > 0) {
    return (
      <div className="table-status-stack">
        <StatusBadge status="blocked" />
        <span>{readiness.blockers[0].code}</span>
      </div>
    );
  }
  if (readiness.warnings.length > 0) {
    return (
      <div className="table-status-stack">
        <StatusBadge status="warning" />
        <span>{readiness.warnings[0].code}</span>
      </div>
    );
  }
  return <StatusBadge status="ready" />;
}

function Page({
  actions,
  activeSection,
  children,
  description,
  issueArea,
  onSectionChange,
  primaryAction,
  sections,
  title
}: {
  actions?: ReactNode;
  activeSection?: string;
  children: ReactNode;
  description?: string;
  issueArea?: ReportIssueAreaId;
  onSectionChange?: (sectionId: string) => void;
  primaryAction?: PrimaryAction;
  sections?: SectionOption[];
  title: string;
}) {
  return (
    <>
      <PageHeader
        actions={actions}
        description={description}
        issueArea={issueArea}
        primaryAction={primaryAction}
        title={title}
      />
      {sections && activeSection && onSectionChange && (
        <SectionSwitch activeId={activeSection} onChange={onSectionChange} sections={sections} />
      )}
      {children}
    </>
  );
}

function PageHeader({
  actions,
  description,
  issueArea,
  primaryAction,
  title
}: {
  actions?: ReactNode;
  description?: string;
  issueArea?: ReportIssueAreaId;
  primaryAction?: PrimaryAction;
  title: string;
}) {
  const { reportIssues } = useReportIssues();
  const issueBadge = issueArea ? reportIssues?.page_badges[issueArea] : undefined;
  const primary = primaryAction?.to ? (
    <Link className="button-link primary" to={primaryAction.to}>
      {primaryAction.icon}
      {primaryAction.label}
    </Link>
  ) : primaryAction ? (
    <button
      className="primary"
      disabled={primaryAction.disabled}
      onClick={primaryAction.onClick}
      type="button"
    >
      {primaryAction.icon}
      {primaryAction.label}
    </button>
  ) : null;

  return (
    <header className="page-header">
      <div className="page-title-block">
        <p className="eyebrow">Infra Config</p>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
        {issueArea && <PageIssueIndicator badge={issueBadge} />}
      </div>
      <div className="page-actions">
        {primary}
        {actions}
      </div>
    </header>
  );
}

function PageIssueIndicator({ badge }: { badge?: ReportPageBadge }) {
  const { isAdvancedMode } = useUiMode();
  if (!badge) {
    return isAdvancedMode ? (
      <div className="page-issue-indicator issue-tone-neutral">
        <Activity size={16} />
        <strong>Report status loading</strong>
        <span>Issue counts will appear when the report center is available.</span>
      </div>
    ) : null;
  }
  if (!isAdvancedMode && badge.status === "success") {
    return null;
  }
  if (badge.status === "success" || badge.status === "warning") {
    return null;
  }
  const label =
    badge.status === "critical"
      ? `Blocked: ${badge.critical || badge.count} critical`
      : badge.status === "not_configured_yet"
        ? `Not configured yet: ${badge.not_configured_yet || badge.count}`
        : badge.label;
  const icon =
    badge.status === "critical" ? (
      <XCircle size={16} />
    ) : badge.status === "warning" ? (
      <AlertTriangle size={16} />
    ) : badge.status === "success" ? (
      <CheckCircle2 size={16} />
    ) : (
      <Activity size={16} />
    );
  return (
    <div className={`page-issue-indicator issue-tone-${badge.status}`}>
      {icon}
      <strong>{label}</strong>
      <Link to={`/validation-reports?section=issues&filter=${encodeURIComponent(badge.default_filter || "all")}`}>View issue</Link>
    </div>
  );
}

function SectionSwitch({
  activeId,
  onChange,
  sections
}: {
  activeId: string;
  onChange: (sectionId: string) => void;
  sections: SectionOption[];
}) {
  return (
    <div className="section-switch" role="tablist">
      {sections.map((section) => (
        <button
          aria-selected={section.id === activeId}
          className={section.id === activeId ? "active" : ""}
          key={section.id}
          onClick={() => onChange(section.id)}
          role="tab"
          type="button"
        >
          <span>{section.label}</span>
          {section.status && <StatusBadge status={section.status} />}
        </button>
      ))}
    </div>
  );
}

function StatusSummaryCard({
  items = [],
  message,
  status,
  title
}: {
  items?: WorkflowSummaryItem[];
  message: string;
  status: string;
  title: string;
}) {
  return (
    <section className="status-summary-card">
      <div className="status-summary-head">
        <div>
          <span className="summary-kicker">Status</span>
          <h2>{title}</h2>
          <p>{message}</p>
        </div>
        <StatusBadge status={status} />
      </div>
      {items.length > 0 && (
        <div className="status-summary-facts">
          {items.slice(0, 4).map((item) => (
            <ProviderFact key={`${item.label}-${item.value}`} label={item.label} value={item.value} />
          ))}
        </div>
      )}
    </section>
  );
}

function NextActionCard({
  detail,
  icon = <Route size={18} />,
  label = "Next action",
  to
}: {
  detail: string;
  icon?: ReactNode;
  label?: string;
  to?: string;
}) {
  const content = (
    <>
      {icon}
      <div>
        <span>{label}</span>
        <strong>{detail}</strong>
      </div>
    </>
  );

  return to ? (
    <Link className="next-action-card next-action-link" to={to}>
      {content}
    </Link>
  ) : (
    <section className="next-action-card">{content}</section>
  );
}

function BlockerSummary({
  blockers,
  empty = "No primary blocker is reported.",
  warnings = []
}: {
  blockers: string[];
  empty?: string;
  warnings?: string[];
}) {
  const primary = blockers[0] ?? warnings[0] ?? "";
  const rest = [...blockers.slice(1), ...warnings.slice(blockers.length ? 0 : 1)];
  if (!primary) {
    return (
      <section className="blocker-summary clear">
        <CheckCircle2 size={18} />
        <div>
          <strong>Primary blocker</strong>
          <p>{empty}</p>
        </div>
      </section>
    );
  }
  return (
    <section className={blockers.length ? "blocker-summary" : "blocker-summary warning"}>
      {blockers.length ? <AlertTriangle size={18} /> : <ShieldCheck size={18} />}
      <div>
        <strong>{blockers.length ? "Primary blocker" : "Primary warning"}</strong>
        <p>{primary}</p>
        {rest.length > 0 && (
          <AdvancedDetails
            className="inline-advanced"
            summary={`${rest.length} additional item${rest.length === 1 ? "" : "s"}`}
            title="More items"
          >
            <ul className="compact-list">
              {rest.map((item, index) => (
                <li key={`${item}-${index}`}>{item}</li>
              ))}
            </ul>
          </AdvancedDetails>
        )}
      </div>
    </section>
  );
}

function ReportLinkList({ reports }: { reports: ReportLink[] }) {
  if (!reports.length) {
    return <EmptyState title="No reports yet" detail="Report links will appear after live checks or verification endpoints produce artifact metadata." />;
  }

  return (
    <div className="report-link-list">
      {reports.map((report) => (
        <div key={`${report.label}-${report.path}`}>
          {report.status && <StatusBadge status={report.status} />}
          <span>{report.label}</span>
          <code>{report.path}</code>
        </div>
      ))}
    </div>
  );
}

function EmptyState({ detail, title }: { detail: string; title: string }) {
  return (
    <section className="empty-state">
      <ClipboardList size={18} />
      <div>
        <strong>{title}</strong>
        <p>{detail}</p>
      </div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

function Metric({ label, value, icon }: { label: string; value: number; icon: ReactNode }) {
  return (
    <article className="metric">
      <div>{icon}</div>
      <p>{label}</p>
      <strong>{value}</strong>
    </article>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="info">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function PanelTitle({ icon, title }: { icon: ReactNode; title: string }) {
  return (
    <div className="panel-title">
      {icon}
      <h2>{title}</h2>
    </div>
  );
}

function JsonPanel({ title, data }: { title: string; data: Record<string, unknown> }) {
  return (
    <section className="panel">
      <PanelTitle icon={<ClipboardList size={18} />} title={title} />
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </section>
  );
}

function Feedback({ loading, error }: { loading?: boolean; error?: string }) {
  if (loading) return <div className="feedback">Loading</div>;
  if (error) return <div className="feedback error">{error}</div>;
  return null;
}

function StatusBadge({ status }: { status: string }) {
  if (isLowSignalStatusBubble(status)) return null;
  return <span className={`status status-${status}`}>{displayStatusLabel(status)}</span>;
}

function isLowSignalStatusBubble(status: string): boolean {
  const label = displayStatusLabel(status).trim().toLowerCase();
  return label === "ready";
}

function ButtonLink({ to, icon, label }: { to: string; icon: ReactNode; label: string }) {
  return (
    <Link className="button-link primary" to={to}>
      {icon}
      {label}
    </Link>
  );
}

async function loadReadinessMap(requests: RequestRecord[]): Promise<ReadinessMap> {
  const entries = await Promise.all(
    requests.map(async (request): Promise<[string, RequestReadiness] | null> => {
      try {
        return [request.id, await api.readiness(request.id)];
      } catch {
        return null;
      }
    })
  );

  return entries.reduce<ReadinessMap>((acc, entry) => {
    if (entry) {
      acc[entry[0]] = entry[1];
    }
    return acc;
  }, {});
}

function uniqueOptions(values: string[]): string[] {
  return [...new Set(values)].sort((left, right) => left.localeCompare(right));
}

type AuditFilterState = {
  eventTypeFilter: string;
  linkFilter: string;
  requestFilter: string;
  runFilter: string;
  statusFilter: string;
  textFilter: string;
};

function auditEventMatchesFilters(event: AuditEvent, filters: AuditFilterState): boolean {
  if (filters.linkFilter === "requests" && !event.request_id) return false;
  if (filters.linkFilter === "workflow-runs" && !event.workflow_run_id) return false;
  if (filters.linkFilter === "unlinked" && (event.request_id || event.workflow_run_id)) {
    return false;
  }
  if (filters.eventTypeFilter !== "all" && event.event_type !== filters.eventTypeFilter) {
    return false;
  }
  if (
    filters.statusFilter !== "all" &&
    event.from_status !== filters.statusFilter &&
    event.to_status !== filters.statusFilter
  ) {
    return false;
  }
  if (!matchesPartialId(event.request_id, filters.requestFilter)) return false;
  if (!matchesPartialId(event.workflow_run_id, filters.runFilter)) return false;

  const search = filters.textFilter.trim().toLowerCase();
  if (!search) return true;
  return auditEventSearchText(event).includes(search);
}

function matchesPartialId(value: string | null, filter: string): boolean {
  const normalizedFilter = filter.trim().toLowerCase();
  if (!normalizedFilter) return true;
  return Boolean(value?.toLowerCase().includes(normalizedFilter));
}

function auditEventSearchText(event: AuditEvent): string {
  return [
    event.actor,
    event.event_type,
    event.message,
    event.from_status ?? "",
    event.to_status ?? "",
    JSON.stringify(event.data_json ?? {})
  ]
    .join(" ")
    .toLowerCase();
}

function isString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function buildRunCenterSections(
  requests: RequestRecord[],
  runs: WorkflowRun[],
  readinessByRequest: ReadinessMap
): QueueSection[] {
  const sections = new Map<QueueSectionId, QueueSection>(
    queueSectionMeta.map((section) => [section.id, { ...section, items: [] }])
  );
  const latestRuns = latestRunByRequest(runs);
  const includedRunIds = new Set<string>();

  sortRequestsByUpdated(requests).forEach((request) => {
    const readiness = readinessByRequest[request.id] ?? null;
    const run = latestRuns.get(request.id) ?? null;
    if (run) {
      includedRunIds.add(run.id);
    }

    const sectionId = queueSectionForRequest(request, run, readiness);
    if (!sectionId) return;
    sections.get(sectionId)?.items.push(queueItemForRequest(sectionId, request, run, readiness));
  });

  runs.forEach((run) => {
    if (includedRunIds.has(run.id)) return;
    const sectionId = queueSectionForRun(run);
    sections.get(sectionId)?.items.push(queueItemForRun(sectionId, run));
  });

  return queueSectionMeta.map((section) => sections.get(section.id) ?? { ...section, items: [] });
}

function latestRunByRequest(runs: WorkflowRun[]): Map<string, WorkflowRun> {
  const latest = new Map<string, WorkflowRun>();
  runs.forEach((run) => {
    const current = latest.get(run.request_id);
    if (!current || new Date(run.created_at).getTime() > new Date(current.created_at).getTime()) {
      latest.set(run.request_id, run);
    }
  });
  return latest;
}

function sortRequestsByUpdated(requests: RequestRecord[]): RequestRecord[] {
  return [...requests].sort(
    (left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime()
  );
}

function queueSectionForRequest(
  request: RequestRecord,
  run: WorkflowRun | null,
  readiness: RequestReadiness | null
): QueueSectionId | null {
  if (request.status === "needs_approval") return "needs_approval";
  if (request.status === "approved") return readiness?.ready_for_plan === false ? "blocked_failed" : "approved_ready_to_plan";
  if (request.status === "planned") {
    return readiness?.ready_for_execute === false ? "blocked_failed" : "planned_ready_to_execute";
  }
  if (request.status === "executing" || run?.status === "executing") return "executing";
  if (["failed", "cancelled", "rejected"].includes(request.status) || run?.status === "failed") return "blocked_failed";
  if (request.status === "completed" || run?.status === "completed") return "completed";
  return null;
}

function queueSectionForRun(run: WorkflowRun): QueueSectionId {
  if (run.status === "planned") return "planned_ready_to_execute";
  if (run.status === "executing") return "executing";
  if (run.status === "completed") return "completed";
  return "blocked_failed";
}

function queueItemForRequest(
  sectionId: QueueSectionId,
  request: RequestRecord,
  run: WorkflowRun | null,
  readiness: RequestReadiness | null
): QueueItem {
  const action = queueActionForSection(sectionId);
  return {
    key: `${sectionId}:${request.id}:${run?.id ?? "request"}`,
    sectionId,
    request,
    run,
    title: request.vm_deploy.vm_name,
    subtitle: `${request.environment} / ${request.site} / ${request.owner}`,
    status: sectionId === "completed" && run ? run.status : request.status,
    actionLabel: action.label,
    reason: readiness?.summary ?? action.reason
  };
}

function queueItemForRun(sectionId: QueueSectionId, run: WorkflowRun): QueueItem {
  const action = queueActionForSection(sectionId);
  return {
    key: `${sectionId}:run:${run.id}`,
    sectionId,
    request: null,
    run,
    title: `Run ${run.id.slice(0, 8)}`,
    subtitle: `${run.workflow_slug} / ${run.provider}`,
    status: run.status,
    actionLabel: action.label,
    reason: action.reason
  };
}

function queueActionForSection(sectionId: QueueSectionId): { label: string; reason: string } {
  if (sectionId === "needs_approval") {
    return {
      label: "Approve request",
      reason: "Validation passed and an approval decision is required."
    };
  }
  if (sectionId === "approved_ready_to_plan") {
    return {
      label: "Create preview plan",
      reason: "Approval is recorded; the next safe step is preview planning."
    };
  }
  if (sectionId === "planned_ready_to_execute") {
    return {
      label: "Launch preview execution",
      reason: "A persisted preview plan is ready for explicit local execution."
    };
  }
  if (sectionId === "executing") {
    return {
      label: "Monitor run",
      reason: "Preview execution is in progress; watch stages, logs, and audit events."
    };
  }
  if (sectionId === "blocked_failed") {
    return {
      label: "Review blocker",
      reason: "The request or workflow needs operator review before more work can continue."
    };
  }
  return {
    label: "Review report",
    reason: "Execution is complete; inspect the result, audit trail, and report placeholders."
  };
}

function queueItemLink(item: QueueItem): string {
  if (item.run && (item.sectionId === "completed" || !item.request)) {
    return `/workflow-runs/${item.run.id}`;
  }
  if (item.request) {
    return `/requests/${item.request.id}`;
  }
  return item.run ? `/workflow-runs/${item.run.id}` : "/run-center";
}

function lifecycleActionState({
  action,
  busy,
  icon,
  isReady,
  label,
  onClick,
  readiness,
  request
}: {
  action: "submit" | "approve" | "plan" | "execute" | "cancel";
  busy: string;
  icon: ReactNode;
  isReady: boolean;
  label: string;
  onClick: () => void;
  readiness: RequestReadiness | null;
  request: RequestRecord;
}): LifecycleActionView {
  const disabled = !isReady || Boolean(busy);
  let reason = readyReasonForAction(action);

  if (busy) {
    reason = busy === action ? `${label} is running.` : `Waiting for ${labelize(busy)} to finish.`;
  } else if (!isReady) {
    reason = disabledReasonForAction(action, request, readiness);
  }

  return {
    disabled,
    icon,
    label,
    onClick,
    reason
  };
}

function readyReasonForAction(action: "submit" | "approve" | "plan" | "execute" | "cancel"): string {
  if (action === "submit") {
    return "Required intent fields are present; submit will run request validation.";
  }
  if (action === "approve") {
    return "Validation passed; approving records the decision and unlocks preview planning.";
  }
  if (action === "plan") {
    return "Approval is recorded; planning will create a preview plan.";
  }
  if (action === "execute") {
    return "A valid persisted preview plan exists; execution remains local preview only.";
  }
  return "This request can still be cancelled before execution starts.";
}

function disabledReasonForAction(
  action: "submit" | "approve" | "plan" | "execute" | "cancel",
  request: RequestRecord,
  readiness: RequestReadiness | null
): string {
  if (!readiness) {
    return "Readiness is loading; refresh if this state does not update.";
  }

  const blockerReason = readiness.blockers[0]
    ? `${readiness.blockers[0].message} ${readiness.blockers[0].action}`
    : "";

  if (action === "submit") {
    if (request.status !== "draft") {
      return `Submit is only available for drafts. Current status is ${labelize(request.status)}.`;
    }
    return blockerReason || "Submit is disabled until required intent fields are complete.";
  }
  if (action === "approve") {
    return `Approve is only available while the request is needs approval. Current status is ${labelize(request.status)}.`;
  }
  if (action === "plan") {
    return `Plan is only available after approval and before a plan exists. Current status is ${labelize(request.status)}.`;
  }
  if (action === "execute") {
    if (blockerReason) return blockerReason;
    return "Execute is available after a valid preview plan is created and still matches the request.";
  }
  return `Cancel is available before execution starts. Current status is ${labelize(request.status)}.`;
}

function displayNextActionForRequest(
  request: RequestRecord,
  readiness: RequestReadiness | undefined
): string {
  if (readiness?.next_action && readiness.next_action !== "none") {
    return readiness.next_action;
  }
  return nextActionForStatus(request.status);
}

function nextActionForStatus(status: RequestStatus): string {
  if (status === "draft") return "submit";
  if (status === "needs_approval") return "approve";
  if (status === "approved") return "plan";
  if (status === "planned") return "execute";
  if (status === "executing") return "monitor";
  if (status === "completed") return "review";
  if (["failed", "cancelled", "rejected"].includes(status)) return "review_blocker";
  return "wait";
}

function planSummaryForRun(run: WorkflowRun) {
  const plan = run.plan_json;
  const intent = isRecord(plan.request_intent) ? plan.request_intent : {};
  const vm = isRecord(intent.vm) ? intent.vm : {};
  const cpu = stringFromUnknown(vm.cpu);
  const memory = stringFromUnknown(vm.memory_gb);
  const disk = stringFromUnknown(vm.disk_gb);
  const datastore = stringFromUnknown(vm.datastore);
  const storageTier = stringFromUnknown(vm.storage_tier);

  return {
    summary: stringFromUnknown(plan.summary) || "Preview plan summary is not available.",
    vmName: stringFromUnknown(plan.vm_name) || stringFromUnknown(vm.vm_name) || "-",
    template: stringFromUnknown(vm.template) || "-",
    placement: `${stringFromUnknown(intent.site) || "-"}/${stringFromUnknown(vm.cluster) || "-"}`,
    storage: datastore || (storageTier ? `tier:${storageTier}` : "-"),
    network: stringFromUnknown(vm.network) || "-",
    sizing: cpu && memory && disk ? `${cpu} CPU, ${memory} GB RAM, ${disk} GB disk` : "-"
  };
}

function planStepsForRun(run: WorkflowRun): PlanStep[] {
  return stepsFromPayload(run.plan_json.steps);
}

function executedStepsForRun(run: WorkflowRun): PlanStep[] {
  if (!run.result_json) return [];
  return stepsFromPayload(run.result_json.executed_steps);
}

function stepsFromPayload(value: unknown): PlanStep[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((step) => {
    if (!isRecord(step)) return [];
    return [
      {
        name: stringFromUnknown(step.name) || "-",
        status: stringFromUnknown(step.status) || "unknown",
        target: stringFromUnknown(step.target) || "-"
      }
    ];
  });
}

function resultSummaryForRun(run: WorkflowRun) {
  const result = run.result_json;
  if (!result) {
    return {
      message: "No execution result yet.",
      mockTaskId: "-",
      mockVmId: "-",
      provider: run.provider
    };
  }

  return {
    message: stringFromUnknown(result.message) || "Execution result recorded.",
    mockTaskId: stringFromUnknown(result.mock_task_id) || "-",
    mockVmId: stringFromUnknown(result.mock_vm_id) || "-",
    provider: stringFromUnknown(result.provider) || run.provider
  };
}

function stringFromUnknown(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  return String(value);
}

function labelize(value: string) {
  return value.replace(/[_-]/g, " ");
}

function operatorReadinessLabel(value: string) {
  return labelize(value)
    .replace(/preview only/g, "apply disabled")
    .replace(/preview/g, "readiness");
}

function blankLabProfileForm(): LabProfileFormState {
  const addresses = {} as Record<LabAddressScalarKey, string>;
  labAddressFields.forEach((field) => {
    addresses[field.key] = "";
  });
  const form = {
    name: "",
    description: "",
    profileTopology: "high_address_lab",
    addresses,
    globalSettings: blankLabGlobalSettings(24),
    netappNfsLifs: "",
    netappIscsiLifs: ""
  };
  return applyLabSubnetChoice(form, defaultLabSubnet, "24");
}

function labProfileFormFrom(profile: {
  name: string;
  description: string | null;
  profile_topology?: string | null;
  features?: Partial<LabProfileFeatures>;
  global_settings?: LabGlobalSettings;
  address_plan: LabAddressPlan;
}): LabProfileFormState {
  const addresses = {} as Record<LabAddressScalarKey, string>;
  labAddressFields.forEach((field) => {
    addresses[field.key] = profile.address_plan[field.key] ?? "";
  });
  const prefix =
    profile.global_settings?.subnet_prefix ??
    prefixFromCidr(profile.address_plan.subnet) ??
    24;
  return {
    name: profile.name,
    description: profile.description ?? "",
    profileTopology: profile.profile_topology ?? topologyForPrefix(prefix),
    addresses,
    globalSettings: labGlobalSettingsFormFrom(profile.global_settings, profile.address_plan, prefix, profile.features),
    netappNfsLifs: profile.address_plan.netapp_nfs_lifs.join(", "),
    netappIscsiLifs: profile.address_plan.netapp_iscsi_lifs.join(", ")
  };
}

function controlProfileFormForSave(
  form: LabProfileFormState,
  activeProfile: LabProfile | null
): LabProfileFormState {
  const fallbackName = activeProfile?.source === "saved" ? activeProfile.name : "Local lab setup";
  const name = form.name.trim() && form.name !== "Runtime environment" ? form.name : fallbackName;
  return {
    ...form,
    name
  };
}

function labProfilePayload(form: LabProfileFormState): LabProfileWrite {
  const addressPlan = blankLabAddressPlan();
  const subnetPrefix = parseSubnetPrefix(form.globalSettings.subnetPrefix);
  const netappEnabled = labNetAppSupported(subnetPrefix);
  labAddressFields.forEach((field) => {
    const isNetAppField = field.key.startsWith("netapp_");
    addressPlan[field.key] =
      isNetAppField && !netappEnabled ? null : cleanNullable(form.addresses[field.key]);
  });
  addressPlan.netapp_nfs_lifs = netappEnabled ? splitCsv(form.netappNfsLifs) : [];
  addressPlan.netapp_iscsi_lifs = netappEnabled ? splitCsv(form.netappIscsiLifs) : [];
  const topology = topologyForPrefix(subnetPrefix);
  return {
    name: form.name.trim(),
    description: cleanNullable(form.description),
    profile_topology: form.profileTopology || topology,
    subnet_cidr: addressPlan.subnet,
    gateway: cleanNullable(form.globalSettings.gateway),
    dns: splitCsv(form.globalSettings.dnsServers),
    ntp: splitCsv(form.globalSettings.ntpServers),
    vlan_id: cleanNullable(form.globalSettings.vlanId),
    mtu: form.globalSettings.mtu.trim() ? Number(form.globalSettings.mtu) : null,
    devices: {
      gateway: cleanNullable(form.globalSettings.gateway),
      switch_primary: addressPlan.cisco_management,
      utility_vm: addressPlan.ansible_control_host,
      esxi: addressPlan.esxi_management,
      ilo: addressPlan.ilo,
      cisco: addressPlan.cisco_management,
      netapp: netappEnabled
        ? {
            controller_a_sp: addressPlan.netapp_controller_a_sp,
            controller_b_sp: addressPlan.netapp_controller_b_sp,
            cluster_mgmt: addressPlan.netapp_cluster_mgmt,
            node_a_mgmt: addressPlan.netapp_node_a_mgmt,
            node_b_mgmt: addressPlan.netapp_node_b_mgmt,
            svm_mgmt: addressPlan.netapp_svm_mgmt,
            nfs_lifs: addressPlan.netapp_nfs_lifs,
            iscsi_lifs: addressPlan.netapp_iscsi_lifs
          }
        : null,
      vcenter: null
    },
    features: {
      netapp_enabled: netappEnabled,
      vcenter_enabled: form.globalSettings.vcenterEnabled && netappEnabled,
      firmware_gate_enabled: true,
      build_verification_enabled: true,
      storage_protocol: netappEnabled ? form.globalSettings.storageProtocol || "nfs" : "none",
      disable_ipv6: form.globalSettings.disableIpv6,
      block_legacy_protocols: form.globalSettings.blockLegacyProtocols,
      enable_snmp: form.globalSettings.enableSnmp,
      enable_ntp: form.globalSettings.enableNtp,
      enable_dns: form.globalSettings.enableDns,
      netapp_disabled_reason: netappEnabled ? null : netappDisabledForSubnetReason,
      vcenter_disabled_reason:
        form.globalSettings.vcenterEnabled && netappEnabled
          ? null
          : "vCenter is disabled by the active lab setup."
    },
    global_settings: {
      subnet_prefix: subnetPrefix,
      gateway: cleanNullable(form.globalSettings.gateway),
      domain_name: cleanNullable(form.globalSettings.domainName),
      dns_servers: splitCsv(form.globalSettings.dnsServers),
      ntp_servers: splitCsv(form.globalSettings.ntpServers),
      timezone: cleanNullable(form.globalSettings.timezone),
      netapp_enabled: netappEnabled,
      netapp_disabled_reason: netappEnabled ? null : netappDisabledForSubnetReason,
      vcenter_enabled: form.globalSettings.vcenterEnabled && netappEnabled,
      vlan_id: cleanNullable(form.globalSettings.vlanId),
      mtu: form.globalSettings.mtu.trim() ? Number(form.globalSettings.mtu) : null
    },
    address_plan: addressPlan
  };
}

function blankLabAddressPlan(): LabAddressPlan {
  return {
    subnet: null,
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
}

function cleanNullable(value: string): string | null {
  const trimmed = value.trim();
  return trimmed || null;
}

function splitCsv(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function blankLabGlobalSettings(prefix: number): LabGlobalSettingsFormState {
  return {
    subnetPrefix: String(prefix),
    gateway: "",
    domainName: "",
    dnsServers: "",
    ntpServers: "",
    timezone: "",
    vlanId: "",
    mtu: "",
    vcenterEnabled: false,
    storageProtocol: "nfs",
    disableIpv6: true,
    blockLegacyProtocols: true,
    enableSnmp: false,
    enableNtp: true,
    enableDns: true
  };
}

function labGlobalSettingsFormFrom(
  settings: LabGlobalSettings | undefined,
  addressPlan: LabAddressPlan,
  prefix: number,
  features?: Partial<LabProfileFeatures>
): LabGlobalSettingsFormState {
  const generated = generateLabAddressPlan(addressPlan.subnet ?? defaultLabSubnet, prefix);
  return {
    subnetPrefix: String(prefix),
    gateway: settings?.gateway ?? generated.gateway ?? "",
    domainName: settings?.domain_name ?? "",
    dnsServers: settings?.dns_servers.join(", ") ?? "",
    ntpServers: settings?.ntp_servers.join(", ") ?? "",
    timezone: settings?.timezone ?? "",
    vlanId: settings?.vlan_id ?? "",
    mtu: settings?.mtu ? String(settings.mtu) : "",
    vcenterEnabled: settings?.vcenter_enabled ?? features?.vcenter_enabled ?? false,
    storageProtocol: features?.storage_protocol ?? "nfs",
    disableIpv6: features?.disable_ipv6 ?? true,
    blockLegacyProtocols: features?.block_legacy_protocols ?? true,
    enableSnmp: features?.enable_snmp ?? false,
    enableNtp: features?.enable_ntp ?? Boolean(settings?.ntp_servers.length),
    enableDns: features?.enable_dns ?? Boolean(settings?.dns_servers.length)
  };
}

function applyLabSubnetChoice(
  form: LabProfileFormState,
  subnetValue: string,
  prefixValue: string
): LabProfileFormState {
  const prefix = parseSubnetPrefix(prefixValue);
  const normalizedSubnet = normalizeIpv4Subnet(subnetValue || defaultLabSubnet, prefix);
  const addresses = {
    ...form.addresses,
    subnet: normalizedSubnet ?? subnetValue
  };
  const nextForm = {
    ...form,
    addresses,
    globalSettings: {
      ...form.globalSettings,
      subnetPrefix: String(prefix)
    }
  };
  if (!normalizedSubnet) {
    return labNetAppSupported(prefix) ? nextForm : clearNetAppAddresses(nextForm);
  }

  const generated = generateLabAddressPlan(normalizedSubnet, prefix);
  labCoreAddressFields.forEach((field) => {
    if (field.key === "ilo_initial") {
      return;
    }
    addresses[field.key] = generated.addresses[field.key] ?? "";
  });
  nextForm.globalSettings.gateway = generated.gateway ?? nextForm.globalSettings.gateway;
  nextForm.profileTopology = topologyForPrefix(prefix);

  if (!labNetAppSupported(prefix)) {
    nextForm.globalSettings.vcenterEnabled = false;
    nextForm.globalSettings.storageProtocol = "none";
    return clearNetAppAddresses(nextForm);
  }
  if (nextForm.globalSettings.storageProtocol === "none") {
    nextForm.globalSettings.storageProtocol = "nfs";
  }

  labNetAppAddressFields.forEach((field) => {
    addresses[field.key] = generated.addresses[field.key] ?? "";
  });
  nextForm.netappNfsLifs = generated.netappNfsLifs.join(", ");
  nextForm.netappIscsiLifs = generated.netappIscsiLifs.join(", ");
  return nextForm;
}

function clearNetAppAddresses(form: LabProfileFormState): LabProfileFormState {
  const addresses = { ...form.addresses };
  labNetAppAddressFields.forEach((field) => {
    addresses[field.key] = "";
  });
  return {
    ...form,
    addresses,
    netappNfsLifs: "",
    netappIscsiLifs: ""
  };
}

function generateLabAddressPlan(subnet: string, prefix: number) {
  const normalizedSubnet = normalizeIpv4Subnet(subnet, prefix);
  const network = normalizedSubnet ? networkBaseFromCidr(normalizedSubnet) : null;
  const addresses: Partial<Record<LabAddressInputKey, string>> = {};
  const coreOffsets = labNetAppSupported(prefix) ? labBuilderCoreOffsets : compactCoreOffsets;
  if (network === null) {
    return { addresses, gateway: "", netappNfsLifs: [], netappIscsiLifs: [] };
  }

  Object.entries(coreOffsets).forEach(([key, offset]) => {
    const address = addressAtOffset(network, prefix, offset);
    if (address) {
      addresses[key as LabAddressInputKey] = address;
    }
  });

  if (!labNetAppSupported(prefix)) {
    return { addresses, gateway: addressAtOffset(network, prefix, 1) ?? "", netappNfsLifs: [], netappIscsiLifs: [] };
  }

  Object.entries(labBuilderNetAppOffsets).forEach(([key, offset]) => {
    const address = addressAtOffset(network, prefix, offset);
    if (address) {
      addresses[key as LabAddressInputKey] = address;
    }
  });
  return {
    addresses,
    gateway: addressAtOffset(network, prefix, 1) ?? "",
    netappNfsLifs: labBuilderNetAppNfsOffsets.flatMap((offset) => {
      const address = addressAtOffset(network, prefix, offset);
      return address ? [address] : [];
    }),
    netappIscsiLifs: labBuilderNetAppIscsiOffsets.flatMap((offset) => {
      const address = addressAtOffset(network, prefix, offset);
      return address ? [address] : [];
    })
  };
}

function defaultLabSubnetOptions(): LabSubnetOption[] {
  return [29, 28, 27, 26, 25, 24, 23].map((prefix) => ({
    prefix,
    cidr_suffix: `/${prefix}`,
    label: `/${prefix} (${usableHostsForPrefix(prefix)} usable IPs)`,
    usable_hosts: usableHostsForPrefix(prefix),
    netapp_supported: labNetAppSupported(prefix),
    netapp_disabled_reason: labNetAppSupported(prefix) ? null : netappDisabledForSubnetReason,
    default_topology: topologyForPrefix(prefix)
  }));
}

function parseSubnetPrefix(value: string | number): number {
  const parsed = Number(String(value).replace("/", ""));
  return parsed >= 23 && parsed <= 29 ? parsed : 24;
}

function prefixFromCidr(value: string | null): number | null {
  if (!value?.includes("/")) return null;
  return parseSubnetPrefix(value.split("/").pop() ?? "24");
}

function labNetAppSupported(prefix: number): boolean {
  return prefix <= 24;
}

function topologyForPrefix(prefix: number): string {
  return prefix <= 24 ? "high_address_lab" : "compact_edge_lab";
}

function normalizeIpv4Subnet(value: string, prefix: number): string | null {
  const address = value.trim().split("/", 1)[0];
  const addressInt = ipv4ToInt(address);
  if (addressInt === null) return null;
  const mask = (0xffffffff << (32 - prefix)) >>> 0;
  const network = (addressInt & mask) >>> 0;
  return `${intToIpv4(network)}/${prefix}`;
}

function networkBaseFromCidr(value: string): number | null {
  return ipv4ToInt(value.split("/", 1)[0]);
}

function addressAtOffset(network: number, prefix: number, offset: number): string | null {
  if (offset < 1 || offset > usableHostsForPrefix(prefix)) return null;
  return intToIpv4(network + offset);
}

function usableHostsForPrefix(prefix: number): number {
  return Math.max(2 ** (32 - prefix) - 2, 0);
}

function ipv4ToInt(value: string): number | null {
  const parts = value.split(".");
  if (parts.length !== 4) return null;
  const octets = parts.map((part) => Number(part));
  if (octets.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) {
    return null;
  }
  return (
    ((octets[0] * 256 ** 3) +
      (octets[1] * 256 ** 2) +
      (octets[2] * 256) +
      octets[3]) >>>
    0
  );
}

function intToIpv4(value: number): string {
  const normalized = value >>> 0;
  return [
    Math.floor(normalized / 256 ** 3) % 256,
    Math.floor(normalized / 256 ** 2) % 256,
    Math.floor(normalized / 256) % 256,
    normalized % 256
  ].join(".");
}

function displayAddress(value: string | null | undefined): string {
  return value?.trim() || "Not set";
}

function displayLabProfileValue(value: string | string[] | null | undefined): string {
  if (Array.isArray(value)) {
    return value.join(", ") || "Not set";
  }
  return displayAddress(value);
}

function baselineDisplayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "Not set";
  }
  if (Array.isArray(value)) {
    return value.map((item) => baselineDisplayValue(item)).join(", ") || "Not set";
  }
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, nested]) => `${labelize(key)}: ${baselineDisplayValue(nested)}`)
      .join("; ") || "Not set";
  }
  return String(value);
}

function stageEventsForRun(run: WorkflowRun): StageEvent[] {
  const resultEvents = extractStageEvents(run.result_json);
  return resultEvents.length ? resultEvents : extractStageEvents(run.plan_json);
}

function extractStageEvents(payload: Record<string, unknown> | null | undefined): StageEvent[] {
  const events = payload?.stage_events;
  if (!Array.isArray(events)) {
    return [];
  }

  return events.flatMap((event) => {
    if (!isRecord(event) || typeof event.stage !== "string" || typeof event.status !== "string") {
      return [];
    }

    return [
      {
        stage: event.stage,
        status: event.status,
        message: typeof event.message === "string" ? event.message : ""
      }
    ];
  });
}

function reviewBeforeExecute(run: WorkflowRun): { status: string; message: string } | null {
  const review = run.plan_json.review_before_execute;
  if (!isRecord(review)) {
    return null;
  }

  return {
    status: typeof review.status === "string" ? review.status : "pending",
    message:
      typeof review.message === "string"
        ? review.message
        : "Review the preview plan before execution."
  };
}

function reviewStateForRun(run: WorkflowRun): { status: string; message: string } {
  if (run.status === "completed") {
    return {
      status: "completed",
      message: "Preview execution completed; review the result summary, audit trail, and report placeholders."
    };
  }
  if (run.status === "executing") {
    return {
      status: "executing",
      message: "Preview execution is in progress; monitor stage events and audit records."
    };
  }
  if (run.status === "failed") {
    return {
      status: "failed",
      message: run.error_message ?? "Preview execution failed; review blockers and audit details."
    };
  }
  if (run.status === "cancelled") {
    return {
      status: "cancelled",
      message: "This workflow run was cancelled before execution completed."
    };
  }
  return (
    reviewBeforeExecute(run) ?? {
      status: "review",
      message: "Review the preview plan before launching local execution."
    }
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function formatBytes(value: number) {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString();
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString();
}

export default App;
