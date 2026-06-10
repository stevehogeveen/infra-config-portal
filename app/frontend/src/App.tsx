import {
  Activity,
  AlertTriangle,
  Ban,
  CheckCircle2,
  ClipboardList,
  Copy,
  FileText,
  Pencil,
  Gauge,
  HardDrive,
  History,
  Layers,
  Menu,
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
import { createContext, FormEvent, ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { Link, Navigate, NavLink, Route as RouterRoute, Routes, useLocation, useNavigate, useParams } from "react-router-dom";

import { api } from "./api";
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
  HpeRaidIntent,
  HpeRaidIntentWrite,
  HpeRaidPlanPreview,
  HpeRaidVolumeIntent,
  HpeStorageDiscovery,
  IloSetupIntent,
  IloSetupIntentWrite,
  IloSetupPlanPreview,
  IloUpgradeReadiness,
  LabValidationItem,
  LabValidationSummary,
  LabAddressPlan,
  LabGlobalSettings,
  LabProfile,
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
type ControlCenterSectionId = "lab-profile" | "cisco" | "ilo" | "raid" | "esxi" | "netapp" | "action-catalog";
type FirmwareSectionId = "compliance" | "inventory" | "packages" | "waivers" | "upgrade-plans";
type VerificationSectionId =
  | "summary"
  | "network"
  | "storage"
  | "firmware"
  | "credentials"
  | "mtu-protocols"
  | "certification-report";
type LabValidationSectionId = "overview" | "vcenter-netapp" | "handoff";
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

type LabAddressScalarKey = Exclude<keyof LabAddressPlan, "netapp_iscsi_lifs">;
type LabAddressInputKey = Exclude<LabAddressScalarKey, "subnet">;
type LabGlobalSettingsFormState = {
  subnetPrefix: string;
  gateway: string;
  domainName: string;
  dnsServers: string;
  ntpServers: string;
  timezone: string;
};

type LabProfileFormState = {
  name: string;
  description: string;
  addresses: Record<LabAddressScalarKey, string>;
  globalSettings: LabGlobalSettingsFormState;
  netappIscsiLifs: string;
};

const labSubnetField: { key: "subnet"; label: string } = { key: "subnet", label: "Subnet CIDR" };

const labCoreAddressFields: Array<{ key: LabAddressInputKey; label: string }> = [
  { key: "ilo", label: "iLO" },
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
  "NetApp capabilities require a /24 or larger lab subnet. They are disabled for /25 through /29 lab profiles.";
const labBuilderCoreOffsets: Partial<Record<LabAddressInputKey, number>> = {
  ilo: 201,
  server_embedded_nic: 202,
  esxi_management: 203,
  cisco_management: 204,
  ansible_control_host: 205
};
const compactCoreOffsets: Partial<Record<LabAddressInputKey, number>> = {
  cisco_management: 2,
  ilo: 3,
  server_embedded_nic: 4,
  esxi_management: 5,
  ansible_control_host: 6
};
const labBuilderNetAppOffsets: Partial<Record<LabAddressInputKey, number>> = {
  netapp_controller_a_sp: 210,
  netapp_controller_b_sp: 211,
  netapp_cluster_mgmt: 220,
  netapp_node_a_mgmt: 221,
  netapp_node_b_mgmt: 222,
  netapp_svm_mgmt: 223
};
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
    empty: "No approved requests are waiting for a dry-run plan."
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
    setLabProfileLoading(true);
    try {
      setLabProfileState(await api.activateLabProfile(profileId));
    } catch (err) {
      setLabProfileError((err as Error).message);
    } finally {
      setLabProfileLoading(false);
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

  useEffect(() => {
    loadLabProfileState();
    loadReportIssues();
  }, []);

  useEffect(() => {
    api
      .health()
      .then((nextHealth) => {
        setHealth(nextHealth);
        setHealthError("");
      })
      .catch((err: Error) => {
        setHealth(null);
        setHealthError(err.message);
      });
  }, []);

  useEffect(() => {
    window.localStorage.setItem("infra-config-operator-ui-mode", uiMode);
  }, [uiMode]);

  return (
    <UiModeContext.Provider value={{ isAdvancedMode: uiMode === "advanced", setUiMode, uiMode }}>
      <ReportIssuesContext.Provider
        value={{ reportIssues, reportIssuesError, reportIssuesLoading, reloadReportIssues: loadReportIssues }}
      >
        <AppShell
          health={health}
          healthError={healthError}
          labProfileError={labProfileError}
          labProfileLoading={labProfileLoading}
          labProfileState={labProfileState}
        >
          <Routes>
            <RouterRoute path="/" element={<Navigate to="/dashboard" replace />} />
            <RouterRoute path="/dashboard" element={<Dashboard />} />
            <RouterRoute path="/lab-setup" element={<LabSetupPage />} />
            <RouterRoute path="/run-center" element={<RunCenter />} />
            <RouterRoute path="/control-center" element={<ControlCenterPage />} />
            <RouterRoute path="/firmware" element={<FirmwarePage />} />
            <RouterRoute path="/verification" element={<BuildVerificationPage />} />
            <RouterRoute path="/lab-validation" element={<LabValidationPage />} />
            <RouterRoute path="/reports" element={<ReportsPage />} />
            <RouterRoute
              path="/settings"
              element={
                <SettingsPage
                  health={health}
                  labProfileError={labProfileError}
                  labProfileLoading={labProfileLoading}
                  onReload={loadLabProfileState}
                  state={labProfileState}
                />
              }
            />
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
            <RouterRoute path="/artifacts" element={<Navigate to="/reports" replace />} />
            <RouterRoute path="/media" element={<MediaInventoryPage />} />
            <RouterRoute path="/providers" element={<Navigate to="/lab-setup" replace />} />
          </Routes>
        </AppShell>
      </ReportIssuesContext.Provider>
    </UiModeContext.Provider>
  );
}

function AppShell({
  children,
  health,
  healthError,
  labProfileError,
  labProfileLoading,
  labProfileState
}: {
  children: ReactNode;
  health: HealthStatus | null;
  healthError: string;
  labProfileError: string;
  labProfileLoading: boolean;
  labProfileState: LabProfileList | null;
}) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname, location.search]);

  return (
    <div className="app-shell">
      <SidebarNav
        drawerOpen={drawerOpen}
        health={health}
        healthError={healthError}
        labProfileError={labProfileError}
        labProfileLoading={labProfileLoading}
        labProfileState={labProfileState}
        onClose={() => setDrawerOpen(false)}
      />
      {drawerOpen && <button className="sidebar-scrim" aria-label="Close navigation" onClick={() => setDrawerOpen(false)} type="button" />}
      <main className="content">
        <div className="mobile-shell-bar">
          <button aria-label="Open navigation" onClick={() => setDrawerOpen(true)} type="button">
            <Menu size={18} />
            Menu
          </button>
          <span>Lab Builder</span>
        </div>
        {health?.dev_test_banner && <DevTestBanner message={health.dev_test_banner} />}
        <div className="operator-mode-bar">
          <ModeToggle />
        </div>
        {children}
      </main>
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

function SidebarNav({
  drawerOpen,
  health,
  healthError,
  labProfileError,
  labProfileLoading,
  labProfileState,
  onClose
}: {
  drawerOpen: boolean;
  health: HealthStatus | null;
  healthError: string;
  labProfileError: string;
  labProfileLoading: boolean;
  labProfileState: LabProfileList | null;
  onClose: () => void;
}) {
  const activeProfile = labProfileState?.active_profile ?? null;
  const providerMode = health?.provider_mode ?? (healthError ? "unverified" : "checking");
  const modeLabel = displayModeLabel(providerMode);
  const modeStatus = providerMode === "mock" ? "test_fixture" : healthError ? "unavailable" : providerMode;
  const { reportIssues } = useReportIssues();
  const pageBadges = reportIssues?.page_badges ?? {};

  return (
    <aside className={drawerOpen ? "sidebar open" : "sidebar"} aria-label="Primary navigation">
      <div className="sidebar-top">
        <Link className="brand" to="/dashboard">
          <Server size={22} />
          <span>
            Lab Builder
            <small>Infra Config Portal</small>
          </span>
        </Link>
        <button className="sidebar-close" aria-label="Close navigation" onClick={onClose} type="button">
          <X size={18} />
        </button>
      </div>
      <nav>
        <NavItem to="/dashboard" icon={<Gauge size={18} />} label="Dashboard" issueBadge={pageBadges.dashboard} />
        <NavItem to="/lab-setup" icon={<Layers size={18} />} label="Lab Setup" />
        <NavItem to="/run-center" icon={<Workflow size={18} />} label="Run Center" issueBadge={pageBadges["run-center"]} />
        <NavItem to="/control-center" icon={<Wrench size={18} />} label="Control" issueBadge={pageBadges["control-center"]} />
        <NavItem to="/firmware" icon={<ShieldCheck size={18} />} label="Firmware" issueBadge={pageBadges.firmware} />
        <NavItem to="/verification" icon={<CheckCircle2 size={18} />} label="Verification" issueBadge={pageBadges.verification} />
        <NavItem to="/lab-validation" icon={<ClipboardList size={18} />} label="Lab Validation" />
        <NavItem to="/reports" icon={<FileText size={18} />} label="Reports" issueBadge={pageBadges.reports} />
        <NavItem to="/settings" icon={<Settings size={18} />} label="Settings" issueBadge={pageBadges.settings} />
      </nav>
      <div className="sidebar-profile">
        <div className="sidebar-profile-head">
          <span>{modeLabel}</span>
          <StatusBadge status={modeStatus} />
        </div>
        <strong>{activeProfile?.name ?? (labProfileLoading ? "Loading profile" : "No active profile")}</strong>
        <dl>
          <div>
            <dt>Subnet</dt>
            <dd>{displayAddress(activeProfile?.address_plan.subnet)}</dd>
          </div>
          <div>
            <dt>Profile</dt>
            <dd>{activeProfile ? labelize(activeProfile.source) : "Unavailable"}</dd>
          </div>
        </dl>
        {(labProfileError || healthError) && (
          <p>{labProfileError ? "Profile status unavailable." : "Backend health unavailable."}</p>
        )}
      </div>
    </aside>
  );
}

function NavItem({
  to,
  icon,
  label,
  issueBadge
}: {
  to: string;
  icon: ReactNode;
  label: string;
  issueBadge?: ReportPageBadge;
}) {
  return (
    <NavLink to={to} className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}>
      {icon}
      <span className="nav-item-label">{label}</span>
      <IssueNavBadge badge={issueBadge} />
    </NavLink>
  );
}

function IssueNavBadge({ badge }: { badge?: ReportPageBadge }) {
  if (!badge) return null;
  const className = `issue-nav-badge issue-tone-${badge.status}`;
  const label =
    badge.status === "critical"
      ? `Blocked ${badge.critical || badge.count}`
      : badge.status === "warning"
        ? `Review ${badge.warning || badge.count}`
        : badge.status === "success"
          ? "Ready"
          : badge.status === "not_configured_yet"
            ? "Not configured"
            : badge.label;
  return <span className={className}>{label}</span>;
}

function ActiveLabSelector({
  error,
  loading,
  onActivate,
  state
}: {
  error: string;
  loading: boolean;
  onActivate: (profileId: string) => Promise<void>;
  state: LabProfileList | null;
}) {
  const activeProfile = state?.active_profile ?? null;
  const options = state ? [state.runtime_profile, ...state.profiles] : [];

  return (
    <section className="active-lab-strip" aria-label="Active lab profile">
      <div className="active-lab-main">
        <Layers size={18} />
        <div>
          <span>Active Lab</span>
          <strong>{activeProfile?.name ?? (loading ? "Loading" : "Unavailable")}</strong>
        </div>
      </div>
      <div className="active-lab-controls">
        <select
          aria-label="Active lab profile"
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
        <Link className="button-link" to="/lab-profiles">
          <Pencil size={16} />
          Manage
        </Link>
      </div>
      {activeProfile && (
        <div className="active-lab-meta">
          <span>{labelize(activeProfile.source)}</span>
          <span>{displayAddress(activeProfile.address_plan.subnet)}</span>
          <span>{state?.profiles.length ?? 0} saved</span>
        </div>
      )}
      {error && <p className="active-lab-error">{error}</p>}
    </section>
  );
}

function Dashboard() {
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
  const readyToApprove = requests.filter((request) => readinessByRequest[request.id]?.ready_for_approval).length;
  const readyToPlan = requests.filter((request) => readinessByRequest[request.id]?.ready_for_plan).length;
  const readyToExecute = requests.filter((request) => readinessByRequest[request.id]?.ready_for_execute).length;
  const latestRun = [...runs].sort((left, right) => right.updated_at.localeCompare(left.updated_at))[0] ?? null;
  const dashboardSections: SectionOption<DashboardSectionId>[] = [
    { id: "overview", label: "Overview" },
    { id: "blockers", label: "Current Blockers", status: blockedItems.length ? "blocked" : "ready" },
    { id: "last-run", label: "Last Run", status: latestRun?.status ?? "not_run" },
    { id: "next-actions", label: "Next Actions", status: nextActionItems.length ? "ready" : "not_run" }
  ];

  return (
    <Page
      activeSection={activeSection}
      description="A quiet operating summary for the current lab and workflow queue."
      issueArea="dashboard"
      onSectionChange={(sectionId) => setActiveSection(sectionId as DashboardSectionId)}
      primaryAction={{ icon: <Workflow size={16} />, label: "Open Run Center", to: "/run-center" }}
      sections={dashboardSections}
      title="Dashboard"
      actions={<ButtonLink to="/requests/new" icon={<Plus size={16} />} label="New VM" />}
    >
      <Feedback loading={loading} error={error} />
      {activeSection === "overview" && (
        <div className="calm-section-grid">
          <StatusSummaryCard
            message={`${nextActionItems.length} active operator action${nextActionItems.length === 1 ? "" : "s"} across ${requests.length} request${requests.length === 1 ? "" : "s"}.`}
            status={blockedItems.length ? "blocked" : nextActionItems.length ? "ready" : "completed"}
            title={blockedItems.length ? "Attention needed" : "Workflow queue is calm"}
            items={[
              { label: "Ready To Approve", value: String(readyToApprove) },
              { label: "Ready To Plan", value: String(readyToPlan) },
              { label: "Ready To Execute", value: String(readyToExecute) },
              { label: "Completed", value: String(counts.completed ?? 0) }
            ]}
          />
          <NextActionCard
            detail={nextActionItems[0]?.actionLabel ?? "Open Run Center when the next request is ready."}
            to="/run-center"
          />
          <BlockerSummary blockers={blockedItems.map((item) => item.reason)} />
        </div>
      )}
      {activeSection === "blockers" && (
        <section className="panel">
          <PanelTitle icon={<AlertTriangle size={18} />} title="Current Blockers" />
          <BlockerSummary blockers={blockedItems.map((item) => `${item.title}: ${item.reason}`)} />
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
    navigate(`/lab-setup?stage=${encodeURIComponent(stageId)}`);
  }

  async function runWorkflowAction(action: WorkflowAction) {
    setError("");
    setRunningWorkflowActionId(action.action_id);
    try {
      const result = await api.runWorkflowAction(action.action_id);
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
      description="A compact setup checklist with one next action per lab stage."
      primaryAction={{ icon: <RefreshCw size={16} />, label: "Refresh", onClick: load, disabled: loading }}
      title="Lab Setup"
      actions={
        isAdvancedMode ? (
          <>
            <Link className="button-link" to="/run-center">
              <Workflow size={16} />
              Run Center
            </Link>
            <Link className="button-link" to="/reports">
              <FileText size={16} />
              Reports
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
        <section className="panel">
          <EmptyState title="No workflow registry data" detail="Refresh after the backend registry endpoint is available." />
        </section>
      )}
    </Page>
  );
}

function RunCenter() {
  const { isAdvancedMode } = useUiMode();
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
  const [netappNfsVcenterReadiness, setNetappNfsVcenterReadiness] = useState<ProviderProbeResult | null>(null);
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
        nextNfsVcenterReadiness,
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
        api.netappNfsVcenterReadiness(),
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
      setNetappNfsVcenterReadiness(nextNfsVcenterReadiness);
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

  async function runWorkflowAction(action: WorkflowAction) {
    setError("");
    setRunningWorkflowActionId(action.action_id);
    try {
      const result = await api.runWorkflowAction(action.action_id);
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
  });
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
    {
      id: "netapp",
      label: "NetApp",
      status:
        registryStageBySection.netapp?.current_state ??
        ((netappPlanPreview?.blockers.length ?? 0) > 0 || (focusChoiceBySection.netapp?.blockers.length ?? 0) > 0
          ? "blocked"
          : "ready")
    }
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
                  artifacts={netappArtifacts}
                  consoleDiscovery={netappConsoleDiscovery}
                  consoleReadiness={netappConsoleReadiness}
                  consoleState={netappConsoleState}
                  error={netappError}
                  loading={netappLoading}
                  liveState={netappLiveState}
                  nfsVcenterReadiness={netappNfsVcenterReadiness}
                  netappAction={netappAction}
                  onRunConsoleDiscovery={runNetAppConsoleDiscovery}
                  onRunConsoleReadState={runNetAppConsoleReadState}
                  onRunLiveState={runNetAppLiveState}
                  onRunSetupApply={runNetAppSetupApply}
                  onRunSetupPreview={runNetAppSetupPreview}
                  onRunUpgradeApply={runNetAppUpgradeApply}
                  onRunUpgradeInventory={runNetAppUpgradeInventory}
                  onRunUpgradePlan={runNetAppUpgradePlan}
                  onValidateUpgrade={validateNetAppUpgrade}
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
              artifacts={netappArtifacts}
              consoleDiscovery={netappConsoleDiscovery}
              consoleReadiness={netappConsoleReadiness}
              consoleState={netappConsoleState}
              error={netappError}
              loading={netappLoading}
              liveState={netappLiveState}
              nfsVcenterReadiness={netappNfsVcenterReadiness}
              netappAction={netappAction}
              onRunSetupPreview={runNetAppSetupPreview}
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
  onRun?: (action: WorkflowAction) => void;
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
      {artifacts.map((artifact) => (
        <li key={artifact}>
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
  onRun?: (action: WorkflowAction) => void;
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
  onRun?: (action: WorkflowAction) => void;
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
  onRun?: (action: WorkflowAction) => void;
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
  onRun?: (action: WorkflowAction) => void;
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
      <span className="guarded-workflow-label">
        <Ban size={compact ? 14 : 16} />
        Requires guarded workflow
      </span>
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
  onRun?: (action: WorkflowAction) => void;
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
      <span className="guarded-workflow-label">
        <Ban size={14} />
        Requires guarded workflow
      </span>
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
  return (
    <div className="workflow-action-command">
      <span>{workflowActionRequiresGuard(action) ? "Guarded" : "Copy command"}</span>
      {workflowActionRequiresGuard(action) ? (
        <strong>Requires guarded workflow</strong>
      ) : (
        <code>{workflowActionCopyText(action)}</code>
      )}
    </div>
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
          <dt>Not Mock</dt>
          <dd>{latestRun ? (latestRun.not_mock ? "true" : "false") : trace.source_type === "live_probe" ? "true" : "not checked"}</dd>
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
      description: "Request approval, dry-run plan, audit events, and reports.",
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
              <p>{review?.message ?? "Review the dry-run plan before execution."}</p>
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
  artifacts,
  consoleDiscovery,
  consoleReadiness,
  consoleState,
  error,
  loading,
  liveState,
  nfsVcenterReadiness,
  netappAction,
  onRunSetupPreview,
  onRefresh,
  preview,
  setupPreview,
  upgradeInventory,
  upgradePlan,
  upgradeReadiness,
  upgradeValidation
}: {
  artifacts: NetAppProviderArtifact[];
  consoleDiscovery: ProviderProbeResult | null;
  consoleReadiness: NetAppConsoleReadiness | null;
  consoleState: ProviderProbeResult | null;
  error: string;
  loading: boolean;
  liveState: ProviderProbeResult | null;
  nfsVcenterReadiness: ProviderProbeResult | null;
  netappAction: string;
  onRunSetupPreview: () => void;
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
      status: configuredByLiveCheck ? "ready" : "not_configured_yet",
      summary: configuredByLiveCheck ? "Configured" : "Not configured"
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
    workflowProbeEvidenceCount(nfsVcenterReadiness) +
    workflowProbeEvidenceCount(setupPreview) +
    workflowProbeEvidenceCount(upgradePlan);
  const evidencePaths = uniqueStrings([
    ...probeEvidencePaths(consoleDiscovery),
    ...probeEvidencePaths(consoleState),
    ...probeEvidencePaths(liveState),
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
        <button className="primary" onClick={onRunSetupPreview} disabled={busy || loading} type="button">
          <ClipboardList size={16} />
          {netappAction === "setup-preview" ? "Previewing" : "Preview Setup"}
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
  artifacts,
  consoleDiscovery,
  consoleReadiness,
  consoleState,
  error,
  loading,
  liveState,
  nfsVcenterReadiness,
  netappAction,
  onRunConsoleDiscovery,
  onRunConsoleReadState,
  onRunLiveState,
  onRunSetupApply,
  onRunSetupPreview,
  onRunUpgradeApply,
  onRunUpgradeInventory,
  onRunUpgradePlan,
  onValidateUpgrade,
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
  artifacts: NetAppProviderArtifact[];
  consoleDiscovery: ProviderProbeResult | null;
  consoleReadiness: NetAppConsoleReadiness | null;
  consoleState: ProviderProbeResult | null;
  error: string;
  loading: boolean;
  liveState: ProviderProbeResult | null;
  nfsVcenterReadiness: ProviderProbeResult | null;
  netappAction: string;
  onRunConsoleDiscovery: () => void;
  onRunConsoleReadState: () => void;
  onRunLiveState: () => void;
  onRunSetupApply: () => void;
  onRunSetupPreview: () => void;
  onRunUpgradeApply: () => void;
  onRunUpgradeInventory: () => void;
  onRunUpgradePlan: () => void;
  onValidateUpgrade: () => void;
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
            onRefresh={onRefresh}
            onRunConsoleDiscovery={onRunConsoleDiscovery}
            onRunConsoleReadState={onRunConsoleReadState}
            onRunLiveState={onRunLiveState}
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
  onRefresh,
  onRunConsoleDiscovery,
  onRunConsoleReadState,
  onRunLiveState,
  onValidateSetup
}: {
  consoleDiscovery: ProviderProbeResult | null;
  consoleReadiness: NetAppConsoleReadiness | null;
  consoleState: ProviderProbeResult | null;
  liveState: ProviderProbeResult | null;
  loading: boolean;
  netappAction: string;
  nfsVcenterReadiness: ProviderProbeResult | null;
  onRefresh: () => void;
  onRunConsoleDiscovery: () => void;
  onRunConsoleReadState: () => void;
  onRunLiveState: () => void;
  onValidateSetup: () => void;
}) {
  const probeEnabled = asBoolean(consoleReadiness?.console_probe_enabled);
  const discoveryArtifacts = objectValue(consoleDiscovery?.artifacts);
  const stateArtifacts = objectValue(consoleState?.artifacts);
  const liveArtifacts = objectValue(liveState?.artifacts);
  const nfsArtifacts = objectValue(nfsVcenterReadiness?.artifacts);
  const nfsTopology = objectValue(nfsVcenterReadiness?.management_topology);
  const nfsTargets = objectValue(nfsVcenterReadiness?.targets);
  const plannedNfs = objectValue(nfsVcenterReadiness?.planned_nfs);
  const connectedPorts = stringArray(nfsTopology.connected_management_ports);
  const nfsLifs = stringArray(plannedNfs.nfs_lifs);
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
        <p>Console discovery is newline-only. NFS/vCenter remains readiness preview with no apply control.</p>
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
          ...(nfsVcenterReadiness?.blockers ?? [])
        ]}
        removableWarnings={[]}
        warnings={[
          ...(consoleDiscovery?.warnings ?? []),
          ...(consoleState?.warnings ?? []),
          ...(liveState?.warnings ?? []),
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
        <ProviderFact label="Stored Locally" value={observations?.mock_only ? "Test fixture store" : "Local evidence"} />
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
            <ProviderFact label="Source" value={artifact.mock_only ? "Test fixture" : "Historical evidence"} />
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
        <ProviderFact label="Source" value={artifact.mock_only ? "Test fixture" : "Historical evidence"} />
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
              Media inventory shows redacted placeholder names, extensions, sizes, categories, and source labels only.
              It does not copy, mount, parse, deploy, or expose local media filenames.
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
                    <th>Placeholder</th>
                    <th>Category</th>
                    <th>Extension</th>
                    <th>Size</th>
                    <th>Source</th>
                    <th>Redacted</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={`${item.placeholder_name}-${item.source}`}>
                      <td>{item.placeholder_name}</td>
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

  function updateGlobalSetting(key: keyof LabGlobalSettingsFormState, value: string) {
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
      onStateChange(await api.activateLabProfile(profileId));
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setBusyAction("");
    }
  }

  return (
    <Page
      title="Lab Profiles"
      actions={
        <>
          <button onClick={onReload} disabled={loading}>
            <RefreshCw size={16} />
            Refresh
          </button>
          <button onClick={startNewProfile} type="button">
            <Plus size={16} />
            New Lab
          </button>
        </>
      }
    >
      <Feedback loading={loading && !state} error={error} />
      {state && activeProfile && (
        <>
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
                        <span>{displayAddress(profile.address_plan.subnet)}</span>
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
                <p className="muted">No saved lab profiles.</p>
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
                      <StatusBadge status="blocked" />
                      <strong>NetApp unavailable for /{form.globalSettings.subnetPrefix}</strong>
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
    </Page>
  );
}

function LabAddressSummary({ profile }: { profile: LabProfile }) {
  return (
    <div className="provider-fact-grid compact lab-address-summary">
      <ProviderFact label="Subnet Size" value={`/${profile.global_settings.subnet_prefix}`} />
      <ProviderFact label="Gateway" value={displayAddress(profile.global_settings.gateway)} />
      <ProviderFact
        label="NetApp Capability"
        value={
          profile.global_settings.netapp_enabled
            ? "Available"
            : profile.global_settings.netapp_disabled_reason ?? "Disabled"
        }
      />
      {labAddressFields.map((field) => (
        <ProviderFact
          key={field.key}
          label={field.label}
          value={displayAddress(profile.address_plan[field.key])}
        />
      ))}
      <ProviderFact
        label="NetApp iSCSI LIFs"
        value={profile.address_plan.netapp_iscsi_lifs.join(", ") || "Not set"}
      />
    </div>
  );
}

function ControlCenterPage() {
  const { isAdvancedMode } = useUiMode();
  const [catalog, setCatalog] = useState<ControlActionCatalog | null>(null);
  const [workflowActions, setWorkflowActions] = useState<WorkflowAction[]>([]);
  const [activeSectionId, setActiveSectionId] = useState<ControlCenterSectionId>("action-catalog");
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
    try {
      const nextWorkflowActions = await api.workflowActions();
      setWorkflowActions(nextWorkflowActions);
      setLoading(false);
      api.controlActions()
        .then(setCatalog)
        .catch((err: Error) => setError((current) => current || err.message));
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
    const querySection = new URLSearchParams(location.search).get("section");
    const allowed: ControlCenterSectionId[] = ["lab-profile", "cisco", "ilo", "raid", "esxi", "netapp", "action-catalog"];
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

  async function runWorkflowAction(action: WorkflowAction) {
    setError("");
    setRunningWorkflowActionId(action.action_id);
    try {
      const result = await api.runWorkflowAction(action.action_id);
      setWorkflowActionRunResults((current) => ({ ...current, [action.action_id]: result }));
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunningWorkflowActionId("");
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
  const visibleSections: ControlCenterSectionId[] = ["lab-profile", "cisco", "ilo", "raid", "esxi", "netapp", "action-catalog"];
  const activeRegistryStageId = workflowStageIdForControlSection(activeSectionId);
  const scopedWorkflowActions =
    activeSectionId === "action-catalog"
      ? workflowActions
      : workflowActions.filter((action) => action.stage === activeRegistryStageId);
  const selectedSection =
    activeSectionId === "action-catalog"
      ? null
      : sections.find((section) => section.id === activeSectionId) ?? sections[0] ?? null;
  const selectedActions = selectedSection?.actions ?? actions;
  const selectedBlockers = selectedActions.flatMap((action) => (action.blocker ? [action.blocker] : []));
  const selectedWorkflowAction =
    scopedWorkflowActions.find((action) => action.action_id === selectedWorkflowActionId) ??
    scopedWorkflowActions[0] ??
    null;
  const selectedCatalogBlockers =
    scopedWorkflowActions.length
      ? scopedWorkflowActions.flatMap((action) => action.blockers.slice(0, 1))
      : selectedBlockers;
  const generatedLabel = catalog?.generated_at ? formatDateTime(catalog.generated_at) : "Registry";
  const scopedActionKeySignature = scopedWorkflowActions.map((action) => action.action_id).join("|");

  useEffect(() => {
    if (!scopedWorkflowActions.length) {
      return;
    }
    setSelectedWorkflowActionId((current) =>
      scopedWorkflowActions.some((action) => action.action_id === current)
        ? current
        : scopedWorkflowActions[0].action_id
    );
  }, [activeSectionId, scopedActionKeySignature]);

  const controlSectionOptions: SectionOption<ControlCenterSectionId>[] = visibleSections.map((sectionId) => {
    if (sectionId === "action-catalog") {
      return { id: sectionId, label: "Action Catalog", status: registryBlockedActions ? "blocked" : "ready" };
    }
    const section = sections.find((item) => item.id === sectionId);
    const label =
      sectionId === "ilo"
        ? "HPE / iLO Control"
        : sectionId === "raid"
          ? "RAID Control"
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
      description="Plan, copy, and inspect safe control actions without exposing every provider detail at once."
      issueArea="control-center"
      onSectionChange={(sectionId) => setActiveSectionId(sectionId as ControlCenterSectionId)}
      primaryAction={{ icon: <Workflow size={16} />, label: "Guided View", to: "/run-center" }}
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
      <Feedback loading={loading && !catalog && !workflowActions.length} error={error} />
      {(catalog || activeSectionId === "action-catalog") && (
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
                { label: "Actions", value: String(scopedWorkflowActions.length || selectedActions.length) },
                { label: "Blocked", value: String(scopedWorkflowActions.length ? selectedCatalogBlockers.length : selectedBlockers.length) },
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

          {activeSectionId !== "action-catalog" && selectedSection?.access_config && (
            <ControlAccessConfigTile
              busy={busyAccessSection === selectedSection.id}
              config={selectedSection.access_config}
              error={busyAccessSection === selectedSection.id ? "" : accessError}
              onSave={saveAccessConfig}
            />
          )}

          {activeSectionId !== "action-catalog" && selectedSection && (
            <>
              <ActionCatalogTable
                actions={scopedWorkflowActions}
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
              <AdvancedDetails
                className="section-details"
                summary="Legacy current state, desired state, plan diff, report links, and diagnostics"
                title={`${selectedSection.title} evidence`}
              >
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
              </AdvancedDetails>
            </>
          )}

          {activeSectionId === "action-catalog" && (
            <>
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
              <ActionCatalogTable
                actions={scopedWorkflowActions}
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
  const [passwordReferenceLabel, setPasswordReferenceLabel] = useState(
    config.password_reference_label ?? ""
  );

  useEffect(() => {
    setFirstTimeConfiguring(config.first_time_configuring);
    setOriginalDhcpIp(config.original_dhcp_ip ?? "");
    setUsernameReference(config.username_reference ?? "");
    setPasswordConfigured(config.password_configured);
    setPasswordReferenceLabel(config.password_reference_label ?? "");
  }, [config]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    await onSave(config.section_id, {
      first_time_configuring: firstTimeConfiguring,
      original_dhcp_ip: cleanNullable(originalDhcpIp),
      username_reference: cleanNullable(usernameReference),
      password_configured: passwordConfigured,
      password_reference_label: cleanNullable(passwordReferenceLabel)
    });
  }

  const ready = config.blockers.length === 0;

  return (
    <section className="control-access-tile">
      <div className="readiness-head">
        <div>
          <p className="summary-kicker">Access & IP Config</p>
          <h3>{config.title}</h3>
          <p>{firstTimeConfiguring ? config.first_time_note : "Existing access is recorded; final IP settings remain editable from the lab profile."}</p>
        </div>
        <StatusBadge status={ready ? "ready" : "blocked"} />
      </div>
      <div className="control-access-layout">
        <form className="control-access-form" onSubmit={submit}>
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
              placeholder="Reference only, no plaintext password"
              value={passwordReferenceLabel}
            />
          </Field>
          <Feedback error={error} />
          <div className="action-row">
            <button disabled={busy} type="submit">
              <Save size={16} />
              {busy ? "Saving" : "Save Access Config"}
            </button>
            <Link className="button-link" to="/lab-profiles">
              <Pencil size={16} />
              Edit IP Profile
            </Link>
          </div>
        </form>
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
              <div key={`${config.section_id}-${field.label}`}>
                <span>{field.label}</span>
                <strong>{field.value}</strong>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
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
        <ProviderFact label="Subnet Size" value={`/${profile.global_settings.subnet_prefix}`} />
        <ProviderFact
          label="NetApp Capability"
          value={
            profile.global_settings.netapp_enabled
              ? "Available"
              : profile.global_settings.netapp_disabled_reason ?? "Disabled"
          }
        />
        {labAddressFields.map((field) => (
          <ProviderFact
            key={`control-profile-${field.key}`}
            label={field.label}
            value={displayAddress(profile.address_plan[field.key])}
          />
        ))}
        <ProviderFact
          label="NetApp iSCSI LIFs"
          value={profile.address_plan.netapp_iscsi_lifs.join(", ") || "Not set"}
        />
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
        <p className="success">No stale or invalid core lab profile values are reported.</p>
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
  onRun?: (action: WorkflowAction) => void;
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
  onRun?: (action: WorkflowAction) => void;
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
  onRun?: (action: WorkflowAction) => void;
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
  devices,
  packages,
  reports
}: {
  compliance: ProviderProbeResult | null;
  components: Record<string, unknown>[];
  devices: Record<string, unknown>;
  packages: Record<string, unknown>[];
  reports: ReportLink[];
}) {
  const rows = [
    firmwareMinimalRow("iLO", devices, components, ["ilo", "hpe"]),
    firmwareMinimalRow("Cisco", devices, components, ["cisco"]),
    firmwareMinimalRow("ONTAP", devices, components, ["netapp", "ontap"]),
    {
      label: "Packages",
      status: packages.length ? "available" : "missing-config",
      summary: packages.length ? "Available" : "Missing"
    }
  ];
  const blockers = stringArray(compliance?.blockers);
  const warnings = stringArray(compliance?.warnings);
  const simpleBlockers = blockers.length ? [firmwareSimpleBlocker(blockers[0])] : [];
  const simpleWarnings = blockers.length || !warnings.length ? [] : [firmwareSimpleBlocker(warnings[0])];
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
      <NextActionCard detail={firmwareSimpleNextAction(asString(compliance?.next_safe_action) || "Refresh firmware compliance.")} />
      <BlockerSummary blockers={simpleBlockers} warnings={simpleWarnings} empty="No firmware blocker is reported." />
      <EvidenceDrawer count={reports.length} title="Firmware Proof">
        <ReportLinkList reports={reports} />
      </EvidenceDrawer>
    </section>
  );
}

function firmwareSimpleBlocker(value: string): string {
  const normalized = value.toLowerCase();
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

function FirmwarePage() {
  const { isAdvancedMode } = useUiMode();
  const [activeSection, setActiveSection] = useState<FirmwareSectionId>("compliance");
  const [inventory, setInventory] = useState<ProviderProbeResult | null>(null);
  const [compliance, setCompliance] = useState<ProviderProbeResult | null>(null);
  const [waiver, setWaiver] = useState<ProviderProbeResult | null>(null);
  const [catalog, setCatalog] = useState<ControlActionCatalog | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setError("");
    setLoading(true);
    try {
      const [nextInventory, nextCompliance, nextWaiver, nextCatalog] = await Promise.all([
        api.firmwareInventory(),
        api.firmwareCompliance(),
        api.firmwareWaiverCheck(),
        api.controlActions()
      ]);
      setInventory(nextInventory);
      setCompliance(nextCompliance);
      setWaiver(nextWaiver);
      setCatalog(nextCatalog);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const components = recordArray(compliance?.components);
  const packages = [
    ...recordArray(inventory?.packages),
    ...recordArray(inventory?.firmware_packages),
    ...recordArray(inventory?.media_candidates)
  ];
  const inventoryDevices = objectValue(compliance?.devices);
  const firmwareSection = catalog?.sections.find((section) => section.id === "firmware-upgrade") ?? null;
  const firmwareActions = catalog?.actions.filter((action) => action.section_id === "firmware-upgrade") ?? [];
  const reports = [
    ...reportLinksFromProbe("Inventory", inventory),
    ...reportLinksFromProbe("Compliance", compliance),
    ...reportLinksFromProbe("Waiver", waiver),
    ...reportLinksFromActions(firmwareActions)
  ];
  const sections: SectionOption<FirmwareSectionId>[] = [
    { id: "compliance", label: "Compliance", status: compliance?.status ?? "not_run" },
    { id: "inventory", label: "Inventory", status: inventory?.status ?? "not_run" },
    { id: "packages", label: "Packages", status: packages.length ? "available" : "not_run" },
    { id: "waivers", label: "Waivers", status: waiver?.status ?? "not_run" },
    { id: "upgrade-plans", label: "Upgrade Plans", status: firmwareSection?.status ?? "not_run" }
  ];

  return (
    <Page
      activeSection={activeSection}
      description="Firmware compliance, inventory, waivers, and upgrade planning without exposing execution controls."
      issueArea="firmware"
      onSectionChange={(sectionId) => setActiveSection(sectionId as FirmwareSectionId)}
      primaryAction={{ icon: <RefreshCw size={16} />, label: "Refresh", onClick: load, disabled: loading }}
      sections={sections}
      title="Firmware / Upgrades"
    >
      <Feedback loading={loading && !compliance} error={error} />
      {activeSection === "compliance" && (
        isAdvancedMode ? (
          <div className="calm-section-grid">
            <StatusSummaryCard
              message={asString(compliance?.message) || "Firmware compliance has not loaded yet."}
              status={compliance?.status ?? "not_run"}
              title="Firmware compliance"
              items={[
                { label: "Components", value: String(components.length) },
                { label: "Blockers", value: String(stringArray(compliance?.blockers).length) },
                { label: "Warnings", value: String(stringArray(compliance?.warnings).length) },
                { label: "Checked", value: compliance?.checked_at ? formatDateTime(compliance.checked_at) : "Not run" }
              ]}
            />
            <NextActionCard detail={humanizeAction(asString(compliance?.next_safe_action) || "Refresh compliance evidence.")} />
            <BlockerSummary blockers={stringArray(compliance?.blockers)} warnings={stringArray(compliance?.warnings)} />
            <AdvancedDetails className="section-details span-3" summary="Component matrix and report links" title="Compliance details">
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
                        <td>{asString(item.required_version) || stringArray(item.approved_versions).join(", ") || "Manual"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <EmptyState title="No component matrix" detail="Compliance evidence did not include per-component rows." />
              )}
              <ReportLinkList reports={reports} />
            </AdvancedDetails>
          </div>
        ) : (
          <FirmwareMinimalOverview
            compliance={compliance}
            components={components}
            devices={inventoryDevices}
            packages={packages}
            reports={reports}
          />
        )
      )}
      {activeSection === "inventory" && (
        <section className="panel">
          <StatusSummaryCard
            message={asString(inventory?.message) || "Firmware inventory has not loaded yet."}
            status={inventory?.status ?? "not_run"}
            title="Firmware inventory"
            items={Object.entries(inventoryDevices).slice(0, 4).map(([label, value]) => ({
              label: labelize(label),
              value: labelize(asString(objectValue(value).status) || "unknown")
            }))}
          />
          <AdvancedDetails className="section-details" summary="Raw redacted firmware inventory payload" title="Inventory details">
            <JsonDetails title="Firmware inventory" data={inventory ?? {}} />
          </AdvancedDetails>
        </section>
      )}
      {activeSection === "packages" && (
        <section className="panel">
          <StatusSummaryCard
            message="Local media/package metadata is shown as redacted candidates only."
            status={packages.length ? "available" : "not_run"}
            title="Firmware packages"
            items={[
              { label: "Candidates", value: String(packages.length) },
              { label: "Source", value: asString(inventory?.media_inventory_mode) || "Local metadata" }
            ]}
          />
          <AdvancedDetails className="section-details" summary="Package candidate metadata" title="Package candidates">
            {packages.length ? <KeyValueTable rows={packages} labelKey="redacted_label" valueKey="version" empty="No packages found." /> : <EmptyState title="No packages" detail="No firmware package metadata is available." />}
          </AdvancedDetails>
        </section>
      )}
      {activeSection === "waivers" && (
        <div className="calm-section-grid">
          <StatusSummaryCard
            message={asString(waiver?.message) || "Firmware waiver status has not loaded yet."}
            status={waiver?.status ?? "not_run"}
            title="Waiver status"
            items={[
              { label: "Blockers", value: String(stringArray(waiver?.blockers).length) },
              { label: "Warnings", value: String(stringArray(waiver?.warnings).length) },
              { label: "Checked", value: waiver?.checked_at ? formatDateTime(waiver.checked_at) : "Not run" }
            ]}
          />
          <NextActionCard detail={humanizeAction(asString(waiver?.next_safe_action) || "Review waiver policy before upgrades.")} />
          <BlockerSummary blockers={stringArray(waiver?.blockers)} warnings={stringArray(waiver?.warnings)} />
        </div>
      )}
      {activeSection === "upgrade-plans" && (
        <section className="panel">
          <StatusSummaryCard
            message={firmwareSection?.description ?? "Upgrade execution remains gated and unavailable from this overview."}
            status={firmwareSection?.status ?? "not_run"}
            title="Upgrade plans"
            items={[
              { label: "Actions", value: String(firmwareActions.length) },
              { label: "Blocked", value: String(firmwareActions.filter((action) => action.availability === "blocked").length) },
              { label: "Reports", value: String(firmwareActions.filter((action) => action.last_report).length) }
            ]}
          />
          {!isAdvancedMode && (
            <NextActionCard detail="Review firmware readiness first; upgrade execution remains disabled." />
          )}
          {firmwareSection && isAdvancedMode && <FirmwareUpgradeCenter section={firmwareSection} />}
          <AdvancedDetails className="section-details" summary="Plan/copy actions and report links" title="Upgrade action catalog">
            <ActionCatalogReadonly actions={firmwareActions} />
          </AdvancedDetails>
        </section>
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
              <td>{item.status === "ready" ? "Ready for handoff" : item.next_action}</td>
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
    navigate(nextSection === "all" ? "/reports" : `/reports?filter=${encodeURIComponent(nextSection)}`);
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
    { id: "lab_profile", label: "Lab Profile", status: filteredStatusForSource(issues, "lab_profile") }
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
              <Link to={`/lab-setup?stage=${encodeURIComponent(issue.source_stage_id)}`}>
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
    "lab-profile": "Lab Profile",
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
      primaryAction={{ icon: <Pencil size={16} />, label: "Manage Profile", to: "/lab-profiles" }}
      sections={sections}
      title="Settings / Lab Profile"
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
            message={activeProfile?.description || "Active lab profile controls the address plan shown throughout the shell."}
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
            <EmptyState title="No active lab profile" detail="Load or create a lab profile from the profile manager." />
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
          <th>Placeholder</th>
          <th>Category</th>
          <th>Extension</th>
          <th>Size</th>
        </tr>
      </thead>
      <tbody>
        {inventory.items.map((item) => (
          <tr key={`${item.placeholder_name}-${item.source}`}>
            <td>{item.placeholder_name}</td>
            <td>{item.category}</td>
            <td>{item.extension || "-"}</td>
            <td>{formatBytes(item.size_bytes)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
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
    "provider-lab-netapp-ontap-upgrade-validate": "Validate ONTAP upgrade"
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

function workflowRunButtonLabel(action: WorkflowAction): string {
  const id = action.action_id;
  if (id.includes("console-read-state")) return "Read Console State";
  if (id.includes("build-verification")) return "Run Verification";
  if (id.includes("firmware")) return "Check Firmware";
  if (id.includes("toolchain")) return "Check Toolchain";
  if (id.includes("live-status") || action.mode === "report_only") return "Refresh Status";
  return "Run Check";
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

  async function load() {
    setError("");
    setLoading(true);
    try {
      const [
        providerStatuses,
        ciscoReadiness,
        setupWizardPlan,
        bootstrapRequirements,
        consoleBootstrapPlan,
        firmwareGate,
        fullRebuild,
        certification
      ] = await Promise.all([
        api.providers(),
        api.ciscoSetupReadiness(),
        api.ciscoSetupWizardPlan(),
        api.ciscoBootstrapRequirements(),
        api.ciscoConsoleBootstrapPlan(),
        api.firmwareCompliance(),
        api.fullRebuildSummary(),
        api.buildVerification()
      ]);
      setProviders(providerStatuses);
      setCiscoSetupReadiness(ciscoReadiness);
      setCiscoSetupWizardPlan(setupWizardPlan);
      setCiscoBootstrapRequirements(bootstrapRequirements);
      setCiscoConsoleBootstrapPlan(consoleBootstrapPlan);
      setFirmwareCompliance(firmwareGate);
      setFullRebuildSummary(fullRebuild);
      setBuildVerification(certification);
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

  return (
    <Page
      title="Lab Builder"
      actions={
        <button onClick={load} disabled={loading || Boolean(busyProvider)}>
          <RefreshCw size={16} />
          Refresh Status
        </button>
      }
    >
      <Feedback loading={loading && !providers.length} error={error} />
      <section className="lab-builder-surface">
        <BuildOverviewCard overview={buildOverview} />
        <GuidedWorkflowLane stages={buildStages} />
        <section className="build-stage-grid" aria-label="Build stages">
          {buildStages.map((stage) => (
            <BuildStageCard key={stage.id} stage={stage} />
          ))}
        </section>
        <AdvancedDetails
          className="provider-global-evidence advanced-diagnostics"
          summary="Raw reports, provider evidence, protected actions, command text, and redacted payloads"
          title="Advanced diagnostics"
        >
          <FullRebuildSummaryPanel summary={fullRebuildSummary} />
          <BuildVerificationPanel verification={buildVerification} />
          {ciscoSetupReadiness && (
            <CiscoSetupReadinessPanel
              bootstrapRequirements={ciscoBootstrapRequirements}
              busyBootstrapRequirements={busyBootstrapRequirements}
              consoleBootstrapPlan={ciscoConsoleBootstrapPlan}
              onSaveBootstrapRequirements={saveBootstrapRequirements}
              readiness={ciscoSetupReadiness}
              setupWizardPlan={ciscoSetupWizardPlan}
            />
          )}
          {orderedProviders.map((provider) => (
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
      title: "Lab Profile",
      step: "Step 1: Confirm lab profile",
      status: asString(labProfile.status) || asString(labProfile.classification) || "not-configured",
      message: "Confirms the active lab address plan and groups older report references as evidence.",
      nextAction: humanizeAction(asString(labProfile.next_action) || "Confirm the lab profile before running provider stages."),
      metricLabel: "Evidence",
      metricValue: staleArtifacts.length ? "Stale evidence" : "Current profile",
      blocker: labProfileCurrentBlocker,
      detailSummary: "Lab profile, historical evidence, and address plan",
      details: (
        <div className="stage-detail-grid">
          <ProviderFact label="Lab Profile" value={labelize(asString(labProfile.status) || "unknown")} />
          <ProviderFact label="Expected Subnet" value={asString(expectedProfile.subnet) || "Not loaded"} />
          <ProviderFact label="Historical Evidence" value={staleArtifacts.length ? String(staleArtifacts.length) : "None detected"} />
          <ProviderFact label="Source" value={resultSourceLabel(labProfile)} />
          <ProviderFact label="Next Action" value={humanizeAction(asString(labProfile.next_action) || "Confirm the lab profile.")} />
          <JsonDetails title="Advanced lab profile evidence" data={labProfile} />
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
        <ProviderFact label="Lab Subnet" value={asString(expectedProfile.subnet) || "192.168.1.0/24"} />
        <ProviderFact label="iLO" value={asString(expectedProfile.ilo) || "192.168.1.201"} />
        <ProviderFact label="ESXi" value={asString(expectedProfile.esxi_management) || "192.168.1.203"} />
        <ProviderFact label="Cisco" value={asString(expectedProfile.cisco_management) || "192.168.1.204"} />
        <ProviderFact label="Control Host" value={asString(expectedProfile.ansible_control_host) || "192.168.1.205"} />
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
          value={`${asString(target.required_ip) || "192.168.1.220"}${asString(target.required_prefix) || "/24"}`}
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
    Promise.all([
      api.iloUpgradeReadiness(),
      api.iloSetupIntent(),
      api.iloSetupPlanPreview(),
      api.hpeStorageDiscovery(),
      api.hpeRaidIntent(),
      api.hpeRaidPlanPreview(),
      api.hpeRaidApplyPlan(),
      api.hpeRaidPending(),
      api.hpeRaidResetPlan(),
      api.esxiInstallReadiness()
    ])
      .then(([readinessPayload, intentPayload, planPayload, storagePayload, raidIntentPayload, raidPlanPayload, raidApplyPayload, raidPendingPayload, raidResetPayload, esxiInstallPayload]) => {
        if (!cancelled) {
          setReadiness(readinessPayload);
          setSetupIntent(intentPayload);
          setSetupPlan(planPayload);
          setRaidDiscovery(storagePayload);
          setRaidIntent(raidIntentPayload);
          setRaidPlan(raidPlanPayload);
          setRaidApplyPlan(raidApplyPayload);
          setRaidPending(raidPendingPayload);
          setRaidResetPlan(raidResetPayload);
          setEsxiInstallReadiness(esxiInstallPayload);
          setError("");
          setSetupError("");
          setRaidError("");
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setError(err.message);
        }
      });
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
      </div>
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
      <AdvancedDetails
        className="provider-workflow-details"
        summary="Current drives, desired RAID layout, pending reset, and validation after reset"
        title="HPE Storage / RAID"
      >
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
      </AdvancedDetails>
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
        <div className="span-2 hpe-raid-volume-list">
          {form.volumes.length === 0 && <p className="muted">No RAID volumes planned.</p>}
          {form.volumes.map((volume, index) => (
            <HpeRaidVolumeEditor
              drives={drives}
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
  drives,
  onChange,
  onRemove,
  volume
}: {
  drives: Array<Record<string, unknown>>;
  onChange: (volume: HpeRaidVolumeIntent) => void;
  onRemove: () => void;
  volume: HpeRaidVolumeIntent;
}) {
  function update<K extends keyof HpeRaidVolumeIntent>(field: K, value: HpeRaidVolumeIntent[K]) {
    onChange({ ...volume, [field]: value });
  }

  function toggleBay(bay: string) {
    const nextBays = volume.drive_bays.includes(bay)
      ? volume.drive_bays.filter((item) => item !== bay)
      : [...volume.drive_bays, bay];
    update("drive_bays", nextBays);
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
      <div className="hpe-drive-selector">
        {drives.map((drive) => {
          const bay = asString(drive.bay_id);
          return (
            <label className="hpe-drive-choice" key={bay || asString(drive.display_label)}>
              <input
                checked={Boolean(bay && volume.drive_bays.includes(bay))}
                disabled={!bay}
                onChange={() => toggleBay(bay)}
                type="checkbox"
              />
              <span>
                <strong>{asString(drive.display_label) || "Drive"}</strong>
                {asString(drive.capacity_label)} {asString(drive.media_type)} {labelize(asString(drive.health) || "unknown")}
              </span>
            </label>
          );
        })}
      </div>
    </div>
  );
}

type Dl360BayRole = "unused" | "os" | "datastore" | "spare";

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

  function bayRole(bay: string): Dl360BayRole {
    if (osBays.has(bay)) return "os";
    if (datastoreBays.has(bay)) return "datastore";
    if (spareBays.has(bay)) return "spare";
    return "unused";
  }

  function setBayRole(bay: string, role: Dl360BayRole) {
    const nextOs = new Set(osBays);
    const nextDatastore = new Set(datastoreBays);
    const nextSpare = new Set(spareBays);
    nextOs.delete(bay);
    nextDatastore.delete(bay);
    nextSpare.delete(bay);
    if (role === "os") nextOs.add(bay);
    if (role === "datastore") nextDatastore.add(bay);
    if (role === "spare") {
      nextSpare.clear();
      nextSpare.add(bay);
    }
    onChange(dl360ProfileVolumes([...nextOs], datastoreRaid, [...nextDatastore], [...nextSpare]));
  }

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
      <table className="provider-candidate-table hpe-raid-table">
        <thead>
          <tr>
            <th>Bay</th>
            <th>Capacity</th>
            <th>Media</th>
            <th>Assignment</th>
          </tr>
        </thead>
        <tbody>
          {drives.map((drive) => {
            const bay = asString(drive.bay_id);
            return (
              <tr key={bay || asString(drive.display_label)}>
                <td>{asString(drive.display_label) || bay || "-"}</td>
                <td>{asString(drive.capacity_label) || "-"}</td>
                <td>{asString(drive.media_type) || "-"}</td>
                <td>
                  <select
                    disabled={!bay}
                    value={bay ? bayRole(bay) : "unused"}
                    onChange={(event) => setBayRole(bay, event.target.value as Dl360BayRole)}
                  >
                    <option value="unused">Unused</option>
                    <option value="os">OS RAID</option>
                    <option value="datastore">Datastore</option>
                    <option value="spare">Dedicated spare</option>
                  </select>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="provider-redaction-note">
        OS bays: {[...osBays].join(", ") || "none"}; datastore bays: {[...datastoreBays].join(", ") || "none"}; spare: {[...spareBays].join(", ") || "none"}.
      </p>
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
  return ["ready", "ok", "available", "completed", "passed"].includes(status);
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
    "local-lab-readwrite": "Real Lab Mode",
    "local-readonly": "Read-only Lab Mode",
    "missing-config": "Not configured yet",
    "missing-console": "Console not found",
    mock: "Test Mode",
    "needs-attention": "Needs attention",
    "needs-selection": "Needs selection",
    not_configured_yet: "Not configured yet",
    not_checked: "Not checked",
    "not-configured": "Not configured yet",
    "not-run": "Not run",
    ok: "Ready",
    operator_action_required: "Needs action",
    passed: "Ready",
    "pending_restart": "Restart required",
    "planned-target": "Planned",
    ready: "Ready",
    "read_only": "Read only",
    "report_only": "Report only",
    "safe_default": "Safe default",
    "setup_intent_missing": "Setup details missing",
    stale: "Stale",
    stale_config: "Old config needs review",
    success: "Ready",
    test_fixture: "Test fixture",
    "upgrade_disabled": "Upgrade disabled",
    unverified: "Unverified",
    unavailable: "Not available",
    waiting: "Waiting"
  };
  return labels[normalized] ?? labelize(normalized);
}

function displayModeLabel(mode: string): string {
  if (mode === "local-lab-readwrite") return "Real Lab Mode";
  if (mode === "local-readonly") return "Read-only Lab Mode";
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
      asString(objectValue(items.planned_management_ip).value) || "192.168.1.220",
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
        <PanelTitle icon={<ShieldCheck size={18} />} title="Local Dry-Run Safety" />
        <p>
          This run uses provider <strong>{run.provider}</strong>. The plan and result are local dry-run data;
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
          <Info label="Dry-Run Task" value={result.mockTaskId} />
          <Info label="Dry-Run VM" value={result.mockVmId} />
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
        {artifact.mock_only && <span>Test fixture</span>}
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
    metadataSummaryItem("Dry-run task", metadata.mock_task_id),
    metadataSummaryItem("Dry-run VM", metadata.mock_vm_id),
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
        <p className="eyebrow">Lab Builder</p>
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
  const label =
    badge.status === "critical"
      ? `Blocked: ${badge.critical || badge.count} critical`
      : badge.status === "warning"
        ? `Needs review: ${badge.warning || badge.count} warning`
        : badge.status === "success"
          ? "Ready: no open issues"
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
      <Link to={`/reports?filter=${encodeURIComponent(badge.default_filter || "all")}`}>View issue</Link>
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
              {rest.map((item) => (
                <li key={item}>{item}</li>
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
  return <span className={`status status-${status}`}>{displayStatusLabel(status)}</span>;
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
      label: "Create dry-run plan",
      reason: "Approval is recorded; the next safe step is dry-run planning."
    };
  }
  if (sectionId === "planned_ready_to_execute") {
    return {
      label: "Launch dry-run execution",
      reason: "A persisted dry-run plan is ready for explicit local execution."
    };
  }
  if (sectionId === "executing") {
    return {
      label: "Monitor run",
      reason: "Dry-run execution is in progress; watch stages, logs, and audit events."
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
    return "Validation passed; approving records the decision and unlocks dry-run planning.";
  }
  if (action === "plan") {
    return "Approval is recorded; planning will create a dry-run plan.";
  }
  if (action === "execute") {
    return "A valid persisted dry-run plan exists; execution remains local dry-run only.";
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
    return "Execute is available after a valid dry-run plan is created and still matches the request.";
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
    summary: stringFromUnknown(plan.summary) || "Mock dry-run plan summary is not available.",
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
    addresses,
    globalSettings: blankLabGlobalSettings(24),
    netappIscsiLifs: ""
  };
  return applyLabSubnetChoice(form, defaultLabSubnet, "24");
}

function labProfileFormFrom(profile: {
  name: string;
  description: string | null;
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
    addresses,
    globalSettings: labGlobalSettingsFormFrom(profile.global_settings, profile.address_plan, prefix),
    netappIscsiLifs: profile.address_plan.netapp_iscsi_lifs.join(", ")
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
  addressPlan.netapp_iscsi_lifs = netappEnabled ? splitCsv(form.netappIscsiLifs) : [];
  return {
    name: form.name.trim(),
    description: cleanNullable(form.description),
    global_settings: {
      subnet_prefix: subnetPrefix,
      gateway: cleanNullable(form.globalSettings.gateway),
      domain_name: cleanNullable(form.globalSettings.domainName),
      dns_servers: splitCsv(form.globalSettings.dnsServers),
      ntp_servers: splitCsv(form.globalSettings.ntpServers),
      timezone: cleanNullable(form.globalSettings.timezone),
      netapp_enabled: netappEnabled,
      netapp_disabled_reason: netappEnabled ? null : netappDisabledForSubnetReason
    },
    address_plan: addressPlan
  };
}

function blankLabAddressPlan(): LabAddressPlan {
  return {
    subnet: null,
    ilo: null,
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
    timezone: ""
  };
}

function labGlobalSettingsFormFrom(
  settings: LabGlobalSettings | undefined,
  addressPlan: LabAddressPlan,
  prefix: number
): LabGlobalSettingsFormState {
  const generated = generateLabAddressPlan(addressPlan.subnet ?? defaultLabSubnet, prefix);
  return {
    subnetPrefix: String(prefix),
    gateway: settings?.gateway ?? generated.gateway ?? "",
    domainName: settings?.domain_name ?? "",
    dnsServers: settings?.dns_servers.join(", ") ?? "",
    ntpServers: settings?.ntp_servers.join(", ") ?? "",
    timezone: settings?.timezone ?? ""
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
    addresses[field.key] = generated.addresses[field.key] ?? "";
  });
  nextForm.globalSettings.gateway = generated.gateway ?? nextForm.globalSettings.gateway;

  if (!labNetAppSupported(prefix)) {
    return clearNetAppAddresses(nextForm);
  }

  labNetAppAddressFields.forEach((field) => {
    addresses[field.key] = generated.addresses[field.key] ?? "";
  });
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
    netappIscsiLifs: ""
  };
}

function generateLabAddressPlan(subnet: string, prefix: number) {
  const normalizedSubnet = normalizeIpv4Subnet(subnet, prefix);
  const network = normalizedSubnet ? networkBaseFromCidr(normalizedSubnet) : null;
  const addresses: Partial<Record<LabAddressInputKey, string>> = {};
  const coreOffsets = labNetAppSupported(prefix) ? labBuilderCoreOffsets : compactCoreOffsets;
  if (network === null) {
    return { addresses, gateway: "", netappIscsiLifs: [] };
  }

  Object.entries(coreOffsets).forEach(([key, offset]) => {
    const address = addressAtOffset(network, prefix, offset);
    if (address) {
      addresses[key as LabAddressInputKey] = address;
    }
  });

  if (!labNetAppSupported(prefix)) {
    return { addresses, gateway: addressAtOffset(network, prefix, 1) ?? "", netappIscsiLifs: [] };
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
    netapp_disabled_reason: labNetAppSupported(prefix) ? null : netappDisabledForSubnetReason
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
        : "Review the dry-run plan before execution."
  };
}

function reviewStateForRun(run: WorkflowRun): { status: string; message: string } {
  if (run.status === "completed") {
    return {
      status: "completed",
      message: "Dry-run execution completed; review the result summary, audit trail, and report placeholders."
    };
  }
  if (run.status === "executing") {
    return {
      status: "executing",
      message: "Dry-run execution is in progress; monitor stage events and audit records."
    };
  }
  if (run.status === "failed") {
    return {
      status: "failed",
      message: run.error_message ?? "Dry-run execution failed; review blockers and audit details."
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
      message: "Review the dry-run plan before launching local execution."
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
