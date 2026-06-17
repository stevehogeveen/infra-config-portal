import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  Cpu,
  FileText,
  Gauge,
  History,
  Play,
  RefreshCw,
  Save,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  TerminalSquare,
  UploadCloud,
  Wrench,
  XCircle
} from "lucide-react";
import { ReactNode, useEffect, useMemo, useState } from "react";
import { Link, Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";

import {
  backendAdapter,
  configAdapter,
  createLocalOperationResult,
  defaultCredentialDraft,
  firmwareAdapter,
  firmwareValidationMatchesSelection,
  firmwareValidationPassed,
  logsAdapter,
  resultsAdapter,
  runAdapter,
  settingsAdapter,
  supportedUpgradeActionId,
  upgradeConfirmationPhrase
} from "./controlCenterAdapters";
import type {
  ControlConfig,
  ControlLogEntry,
  ControlSettings,
  CredentialDraft,
  FirmwareState,
  HealthState,
  OperationResult,
  OperationStatus,
  ProviderModeSummary,
  UpgradeStatus
} from "./controlCenterAdapters";
import type { AuditEvent, FirmwareSummary, FirmwareUpgradePath, ProviderStatus, WorkflowAction } from "./types";

const navItems = [
  { icon: <Gauge size={18} />, label: "Dashboard", to: "/dashboard" },
  { icon: <SlidersHorizontal size={18} />, label: "Configure", to: "/configure" },
  { icon: <Play size={18} />, label: "Run", to: "/run" },
  { icon: <UploadCloud size={18} />, label: "Firmware", to: "/firmware" },
  { icon: <ClipboardList size={18} />, label: "Results", to: "/results" },
  { icon: <History size={18} />, label: "Logs", to: "/logs" },
  { icon: <Settings size={18} />, label: "Settings", to: "/settings" }
];

type ControlCenterContext = {
  actions: WorkflowAction[];
  auditEvents: AuditEvent[];
  config: ControlConfig;
  configErrors: string[];
  configMessage: string;
  connectionStatus: string;
  credentialDraft: CredentialDraft;
  expectedUpgradePhrase: string;
  firmware: FirmwareState;
  firmwareCheckStatus: OperationStatus;
  firmwareUpgradeBlockers: string[];
  health: HealthState | null;
  latestFirmwareCheck: OperationResult | null;
  latestFirmwareUpgrade: OperationResult | null;
  latestFirmwareValidation: OperationResult | null;
  latestRun: OperationResult | null;
  loadError: string;
  loading: boolean;
  logs: ControlLogEntry[];
  providerMode: ProviderModeSummary | null;
  providers: ProviderStatus[];
  refreshControlCenter: () => Promise<void>;
  runError: string;
  runSelectedAction: () => Promise<void>;
  runStatus: OperationStatus;
  saveConfig: () => void;
  saveSettings: () => void;
  selectedAction: WorkflowAction | null;
  selectedFirmware: string;
  selectedPath: FirmwareUpgradePath | null;
  selectedPathId: string;
  selectedUpgradeAction: WorkflowAction | null;
  setConfig: (value: ControlConfig | ((current: ControlConfig) => ControlConfig)) => void;
  setCredentialDraft: (value: CredentialDraft | ((current: CredentialDraft) => CredentialDraft)) => void;
  setSelectedFirmware: (value: string) => void;
  setSelectedPathId: (value: string) => void;
  setSettings: (value: ControlSettings | ((current: ControlSettings) => ControlSettings)) => void;
  settings: ControlSettings;
  settingsMessage: string;
  startFirmwareUpgrade: () => Promise<void>;
  targetSummary: string;
  upgradeConfirmationAccepted: boolean;
  upgradeConfirmationPhrase: string;
  upgradeStatus: UpgradeStatus;
  validateFirmware: () => Promise<void>;
  checkFirmware: () => Promise<void>;
  setUpgradeConfirmationAccepted: (value: boolean) => void;
  setUpgradeConfirmationPhrase: (value: string) => void;
};

export default function ControlCenter() {
  const [health, setHealth] = useState<HealthState | null>(null);
  const [providerMode, setProviderMode] = useState<ProviderModeSummary | null>(null);
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [actions, setActions] = useState<WorkflowAction[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [firmware, setFirmware] = useState<FirmwareState>({ fileSelections: null, summaries: [] });
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [config, setConfig] = useState<ControlConfig>(() => configAdapter.load());
  const [settings, setSettings] = useState<ControlSettings>(() => settingsAdapter.load());
  const [credentialDraft, setCredentialDraft] = useState<CredentialDraft>(defaultCredentialDraft);
  const [configErrors, setConfigErrors] = useState<string[]>([]);
  const [configMessage, setConfigMessage] = useState("");
  const [settingsMessage, setSettingsMessage] = useState("");

  const [logs, setLogs] = useState<ControlLogEntry[]>(() => logsAdapter.load());
  const [latestRun, setLatestRun] = useState<OperationResult | null>(() => resultsAdapter.loadRun());
  const [latestFirmwareCheck, setLatestFirmwareCheck] = useState<OperationResult | null>(() => resultsAdapter.loadFirmwareCheck());
  const [latestFirmwareValidation, setLatestFirmwareValidation] = useState<OperationResult | null>(() => resultsAdapter.loadFirmwareValidation());
  const [latestFirmwareUpgrade, setLatestFirmwareUpgrade] = useState<OperationResult | null>(() => resultsAdapter.loadFirmwareUpgrade());

  const [runStatus, setRunStatus] = useState<OperationStatus>(() => latestRun?.status ?? "idle");
  const [runError, setRunError] = useState("");
  const [firmwareCheckStatus, setFirmwareCheckStatus] = useState<OperationStatus>(() => latestFirmwareCheck?.status ?? "idle");
  const [upgradeStatus, setUpgradeStatus] = useState<UpgradeStatus>(() => upgradeStatusFromResult(latestFirmwareUpgrade));
  const [selectedPathId, setSelectedPathIdState] = useState("");
  const [selectedFirmware, setSelectedFirmware] = useState("");
  const [upgradeConfirmationAccepted, setUpgradeConfirmationAccepted] = useState(false);
  const [upgradeConfirmationPhraseState, setUpgradeConfirmationPhrase] = useState("");

  const selectedAction = useMemo(() => runAdapter.selectAction(actions), [actions]);
  const firmwarePaths = useMemo(() => collectFirmwarePaths(firmware.summaries), [firmware.summaries]);
  const selectedPath = useMemo(
    () => firmwarePaths.find((path) => firmwarePathId(path) === selectedPathId) ?? null,
    [firmwarePaths, selectedPathId]
  );
  const selectedUpgradeAction = useMemo(() => {
    const actionId = supportedUpgradeActionId(selectedPath);
    return actions.find((action) => action.action_id === actionId) ?? null;
  }, [actions, selectedPath]);
  const targetSummary = config.target || "Not configured";
  const connectionStatus = health?.status === "ok" ? "Connected" : loading ? "Checking" : "Unavailable";
  const expectedUpgradePhrase = upgradeConfirmationPhrase(selectedPath, selectedUpgradeAction);
  const firmwareUpgradeBlockers = firmwareStartBlockers({
    accepted: upgradeConfirmationAccepted,
    config,
    phrase: upgradeConfirmationPhraseState,
    selectedFirmware,
    selectedUpgradeAction,
    selectedPath,
    validation: latestFirmwareValidation
  });

  useEffect(() => {
    void refreshControlCenter();
  }, []);

  async function refreshControlCenter() {
    setLoading(true);
    setLoadError("");
    try {
      const snapshot = await backendAdapter.loadSnapshot();
      setHealth(snapshot.health);
      setProviderMode(snapshot.providerMode);
      setProviders(snapshot.providers);
      setActions(snapshot.actions);
      setAuditEvents(snapshot.auditEvents);
      setFirmware(snapshot.firmware);
    } catch (error) {
      setLoadError(errorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  function addLog(entry: Omit<ControlLogEntry, "id" | "timestamp">) {
    setLogs((current) => logsAdapter.add(current, entry));
  }

  function saveConfig() {
    const result = configAdapter.save(config, credentialDraft);
    setConfig(result.config);
    setConfigErrors(result.errors);
    setConfigMessage(result.errors.length ? "" : "Configuration saved");
    if (result.errors.length) {
      addLog({
        detail: result.errors.join(" "),
        message: "Config save failed",
        status: "blocked",
        type: "config"
      });
      return;
    }
    setCredentialDraft(defaultCredentialDraft);
    addLog({
      detail: `${result.config.target}; ${ipModeLabel(result.config.ipMode)}; ${snmpVersionLabel(result.config.snmpVersion)}.`,
      message: "Config saved",
      status: "saved",
      type: "config"
    });
  }

  function saveSettings() {
    const next = settingsAdapter.save(settings);
    setSettings(next);
    setSettingsMessage("Settings saved");
    addLog({
      detail: `Default ${ipModeLabel(next.defaultIpMode)}, ${snmpVersionLabel(next.defaultSnmpVersion)}, timeout ${next.defaultTimeoutSeconds}s.`,
      message: "Settings changed",
      status: "saved",
      type: "settings"
    });
  }

  async function runSelectedAction() {
    if (runStatus === "running") return;
    setRunError("");
    setRunStatus("running");
    addLog({
      detail: `${selectedAction?.label ?? "Safe placeholder"} for ${targetSummary}.`,
      message: "Run started",
      status: "running",
      type: "run"
    });
    try {
      const result = await runAdapter.run(config, selectedAction);
      setLatestRun(result);
      resultsAdapter.saveRun(result);
      setRunStatus(result.status);
      setRunError(["failed", "blocked"].includes(result.status) ? result.message : "");
      addLog({
        detail: result.message,
        message: operationLogMessage("Run", result.status),
        status: result.status,
        type: "run"
      });
      await refreshControlCenter();
    } catch (error) {
      const message = errorMessage(error);
      const result = createLocalOperationResult({
        blockers: [message],
        message,
        raw: {
          config_snapshot: {
            ip_mode: config.ipMode,
            retry_count: config.retryCount,
            snmp_credentials: config.snmpCredentialStatus,
            snmp_version: config.snmpVersion,
            target: config.target,
            timeout_seconds: config.timeoutSeconds
          }
        },
        status: "failed",
        title: "Run failed",
        type: "run"
      });
      setLatestRun(result);
      resultsAdapter.saveRun(result);
      setRunStatus("failed");
      setRunError(message);
      addLog({
        detail: message,
        message: "Run failed",
        status: "failed",
        type: "run"
      });
    }
  }

  async function checkFirmware() {
    setFirmwareCheckStatus("running");
    addLog({
      detail: `Firmware visibility check started for ${targetSummary}. No upgrade action is triggered.`,
      message: "Firmware check started",
      status: "running",
      type: "firmware"
    });
    try {
      const response = await firmwareAdapter.check(config);
      setFirmware(response.firmware);
      setLatestFirmwareCheck(response.result);
      resultsAdapter.saveFirmwareCheck(response.result);
      setFirmwareCheckStatus(response.result.status);
      addLog({
        detail: response.result.message,
        message: operationLogMessage("Firmware check", response.result.status),
        status: response.result.status,
        type: "firmware"
      });
    } catch (error) {
      const message = errorMessage(error);
      const result = createLocalOperationResult({
        blockers: [message],
        message,
        status: "failed",
        title: "Firmware check failed",
        type: "firmware-check"
      });
      setLatestFirmwareCheck(result);
      resultsAdapter.saveFirmwareCheck(result);
      setFirmwareCheckStatus("failed");
      addLog({
        detail: message,
        message: "Firmware check failed",
        status: "failed",
        type: "firmware"
      });
    }
  }

  async function validateFirmware() {
    setUpgradeStatus("validating");
    addLog({
      detail: selectedPath ? firmwarePathLabel(selectedPath) : "No firmware path selected.",
      message: "Firmware validation started",
      status: "running",
      type: "firmware"
    });
    try {
      const response = await firmwareAdapter.validate({
        config,
        selectedFirmware,
        selectedPath
      });
      setFirmware(response.firmware);
      setLatestFirmwareValidation(response.result);
      resultsAdapter.saveFirmwareValidation(response.result);
      setUpgradeStatus(response.result.status === "success" ? "ready" : "failed");
      addLog({
        detail: response.result.message,
        message: operationLogMessage("Firmware validation", response.result.status),
        status: response.result.status,
        type: "firmware"
      });
    } catch (error) {
      const message = errorMessage(error);
      const result = createLocalOperationResult({
        blockers: [message],
        message,
        status: "failed",
        title: "Firmware validation failed",
        type: "firmware-validation"
      });
      setLatestFirmwareValidation(result);
      resultsAdapter.saveFirmwareValidation(result);
      setUpgradeStatus("failed");
      addLog({
        detail: message,
        message: "Firmware validation failed",
        status: "failed",
        type: "firmware"
      });
    }
  }

  async function startFirmwareUpgrade() {
    if (upgradeStatus === "upgrading") return;
    if (firmwareUpgradeBlockers.length > 0) {
      const result = createLocalOperationResult({
        blockers: firmwareUpgradeBlockers,
        message: "Firmware upgrade was not started.",
        status: "blocked",
        title: "Firmware upgrade blocked",
        type: "firmware-upgrade"
      });
      setLatestFirmwareUpgrade(result);
      resultsAdapter.saveFirmwareUpgrade(result);
      setUpgradeStatus("blocked");
      addLog({
        detail: firmwareUpgradeBlockers.join(" "),
        message: "Firmware upgrade blocked",
        status: "blocked",
        type: "firmware"
      });
      return;
    }
    setUpgradeStatus("upgrading");
    addLog({
      detail: selectedPath ? firmwarePathLabel(selectedPath) : "Missing selected firmware path.",
      message: "Firmware upgrade started",
      status: "running",
      type: "firmware"
    });
    try {
      const result = await firmwareAdapter.upgrade({
        actions,
        config,
        confirmationAccepted: upgradeConfirmationAccepted,
        confirmationPhrase: upgradeConfirmationPhraseState,
        selectedFirmware,
        selectedPath,
        validationResult: latestFirmwareValidation
      });
      setLatestFirmwareUpgrade(result);
      resultsAdapter.saveFirmwareUpgrade(result);
      setUpgradeStatus(upgradeStatusAfterResult(result));
      addLog({
        detail: result.message,
        message: operationLogMessage("Firmware upgrade", result.status),
        status: result.status,
        type: "firmware"
      });
      await refreshControlCenter();
    } catch (error) {
      const message = errorMessage(error);
      const result = createLocalOperationResult({
        blockers: [message],
        message,
        status: "failed",
        title: "Firmware upgrade failed",
        type: "firmware-upgrade"
      });
      setLatestFirmwareUpgrade(result);
      resultsAdapter.saveFirmwareUpgrade(result);
      setUpgradeStatus("failed");
      addLog({
        detail: message,
        message: "Firmware upgrade failed",
        status: "failed",
        type: "firmware"
      });
    }
  }

  function setSelectedPathId(value: string) {
    setSelectedPathIdState(value);
    const path = firmwarePaths.find((candidate) => firmwarePathId(candidate) === value) ?? null;
    setSelectedFirmware(defaultFirmwareSelection(path));
    setUpgradeConfirmationAccepted(false);
    setUpgradeConfirmationPhrase("");
    setUpgradeStatus("idle");
  }

  function updateSelectedFirmware(value: string) {
    setSelectedFirmware(value);
    setUpgradeConfirmationAccepted(false);
    setUpgradeConfirmationPhrase("");
    if (upgradeStatus !== "upgrading") {
      setUpgradeStatus("idle");
    }
  }

  const context: ControlCenterContext = {
    actions,
    auditEvents,
    checkFirmware,
    config,
    configErrors,
    configMessage,
    connectionStatus,
    credentialDraft,
    expectedUpgradePhrase,
    firmware,
    firmwareCheckStatus,
    firmwareUpgradeBlockers,
    health,
    latestFirmwareCheck,
    latestFirmwareUpgrade,
    latestFirmwareValidation,
    latestRun,
    loadError,
    loading,
    logs,
    providerMode,
    providers,
    refreshControlCenter,
    runError,
    runSelectedAction,
    runStatus,
    saveConfig,
    saveSettings,
    selectedAction,
    selectedFirmware,
    selectedPath,
    selectedPathId,
    selectedUpgradeAction,
    setConfig,
    setCredentialDraft,
    setSelectedFirmware: updateSelectedFirmware,
    setSelectedPathId,
    setSettings,
    settings,
    settingsMessage,
    startFirmwareUpgrade,
    targetSummary,
    upgradeConfirmationAccepted,
    upgradeConfirmationPhrase: upgradeConfirmationPhraseState,
    upgradeStatus,
    validateFirmware,
    setUpgradeConfirmationAccepted,
    setUpgradeConfirmationPhrase
  };

  return (
    <div className="control-center-shell">
      <aside className="control-sidebar" aria-label="Main navigation">
        <Link className="control-brand" to="/dashboard">
          <Wrench size={22} />
          <span>
            WebUIs Control Center
            <small>Admin control plane</small>
          </span>
        </Link>
        <nav className="control-nav">
          {navItems.map((item) => (
            <NavLink className="control-nav-link" key={item.to} to={item.to}>
              {item.icon}
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="control-sidebar-foot">
          <span>Current target</span>
          <strong>{targetSummary}</strong>
          <small>{context.connectionStatus}</small>
        </div>
      </aside>
      <main className="control-main">
        <TopHeader context={context} />
        {loadError && <div className="control-alert error">{loadError}</div>}
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage context={context} />} />
          <Route path="/configure" element={<ConfigurePage context={context} />} />
          <Route path="/run" element={<RunPage context={context} />} />
          <Route path="/firmware" element={<FirmwarePage context={context} />} />
          <Route path="/results" element={<ResultsPage context={context} />} />
          <Route path="/logs" element={<LogsPage context={context} />} />
          <Route path="/settings" element={<SettingsPage context={context} />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </main>
    </div>
  );
}

function TopHeader({ context }: { context: ControlCenterContext }) {
  const location = useLocation();
  const activePage = navItems.find((item) => location.pathname.startsWith(item.to))?.label ?? "Dashboard";
  return (
    <header className="control-topbar">
      <div>
        <p className="control-kicker">Control Center</p>
        <h1>WebUIs Control Center</h1>
        <span>{activePage}</span>
      </div>
      <div className="control-status-strip" aria-label="System status">
        <StatusChip label="API" value={context.connectionStatus} />
        <StatusChip label="Last Run" value={resultStatusLabel(context.latestRun, context.runStatus)} />
        <StatusChip label="Firmware" value={firmwareStatusLabel(context)} />
      </div>
    </header>
  );
}

function DashboardPage({ context }: { context: ControlCenterContext }) {
  return (
    <Page title="Dashboard" subtitle="Current target, status, firmware signal, and the next workflow links.">
      <div className="control-dashboard-grid">
        <section className="control-panel">
          <PanelTitle icon={<Gauge size={18} />} title="Current Target" />
          <FactGrid
            facts={[
              ["Target", context.targetSummary],
              ["API status", context.connectionStatus],
              ["Provider mode", context.health?.provider_mode ?? "Unknown"],
              ["Runtime", context.health?.operator_runtime_mode ?? "Unknown"]
            ]}
          />
        </section>
        <section className="control-panel">
          <PanelTitle icon={<SlidersHorizontal size={18} />} title="Configured Defaults" />
          <FactGrid
            facts={[
              ["IP mode", ipModeLabel(context.config.ipMode)],
              ["SNMP version", snmpVersionLabel(context.config.snmpVersion)],
              ["SNMP credentials", credentialStatusLabel(context.config.snmpCredentialStatus)],
              ["Timeout / retry", `${context.config.timeoutSeconds}s / ${context.config.retryCount}`]
            ]}
          />
        </section>
        <section className="control-panel">
          <PanelTitle icon={<UploadCloud size={18} />} title="Firmware Summary" />
          <FirmwareRollup summaries={context.firmware.summaries} />
        </section>
      </div>
      <div className="control-dashboard-grid compact">
        <section className="control-panel">
          <PanelTitle icon={<Play size={18} />} title="Last Run" />
          {context.latestRun ? <ResultSummary result={context.latestRun} /> : <EmptyState title="No run yet" detail="Configure a target, then run the selected action." />}
        </section>
        <section className="control-panel">
          <PanelTitle icon={<ShieldCheck size={18} />} title="Last Firmware Check" />
          {context.latestFirmwareCheck ? <ResultSummary result={context.latestFirmwareCheck} /> : <EmptyState title="No firmware check yet" detail="Open Firmware and run Check Firmware." />}
        </section>
        <section className="control-panel">
          <PanelTitle icon={<Activity size={18} />} title="Last Firmware Upgrade" />
          {context.latestFirmwareUpgrade ? <ResultSummary result={context.latestFirmwareUpgrade} /> : <EmptyState title="No upgrade attempt" detail="Firmware upgrades require validation and confirmation." />}
        </section>
      </div>
      <section className="control-panel">
        <PanelTitle icon={<ClipboardList size={18} />} title="Workflow" />
        <div className="quick-link-row">
          <Link className="button-link primary" to="/configure">
            <SlidersHorizontal size={16} />
            Configure
          </Link>
          <Link className="button-link" to="/run">
            <Play size={16} />
            Run
          </Link>
          <Link className="button-link" to="/firmware">
            <UploadCloud size={16} />
            Firmware
          </Link>
        </div>
      </section>
    </Page>
  );
}

function ConfigurePage({ context }: { context: ControlCenterContext }) {
  return (
    <Page title="Configure" subtitle="Set the target and protocol defaults used by Run and Firmware workflows.">
      <section className="control-panel">
        <PanelTitle icon={<SlidersHorizontal size={18} />} title="Target and SNMP" />
        <div className="control-form-grid">
          <label className="control-field control-field-wide">
            <span>Target host, IP, or range</span>
            <input
              onChange={(event) => context.setConfig((current) => ({ ...current, target: event.target.value }))}
              placeholder="192.0.2.203 or 192.0.2.0/24"
              type="text"
              value={context.config.target}
            />
          </label>
          <label className="control-field">
            <span>IP mode</span>
            <select
              onChange={(event) => context.setConfig((current) => ({ ...current, ipMode: event.target.value as ControlConfig["ipMode"] }))}
              value={context.config.ipMode}
            >
              <option value="ipv4">IPv4</option>
              <option value="ipv6">IPv6</option>
              <option value="both">Both</option>
            </select>
          </label>
          <label className="control-field">
            <span>SNMP version</span>
            <select
              onChange={(event) => context.setConfig((current) => ({ ...current, snmpVersion: event.target.value as ControlConfig["snmpVersion"] }))}
              value={context.config.snmpVersion}
            >
              <option value="v2">SNMPv2</option>
              <option value="v3">SNMPv3</option>
            </select>
          </label>
          <label className="control-field">
            <span>Timeout seconds</span>
            <input
              max={120}
              min={1}
              onChange={(event) => context.setConfig((current) => ({ ...current, timeoutSeconds: Number(event.target.value) }))}
              type="number"
              value={context.config.timeoutSeconds}
            />
          </label>
          <label className="control-field">
            <span>Retry count</span>
            <input
              max={5}
              min={0}
              onChange={(event) => context.setConfig((current) => ({ ...current, retryCount: Number(event.target.value) }))}
              type="number"
              value={context.config.retryCount}
            />
          </label>
        </div>
      </section>

      <section className="control-panel">
        <PanelTitle icon={<ShieldCheck size={18} />} title="SNMP Credentials" />
        {context.config.snmpVersion === "v2" ? (
          <label className="control-field control-field-wide">
            <span>SNMPv2 community</span>
            <input
              autoComplete="off"
              onChange={(event) =>
                context.setCredentialDraft((current) => ({ ...current, snmpV2Community: event.target.value }))
              }
              placeholder="Not saved; marks credentials configured when saved"
              type="password"
              value={context.credentialDraft.snmpV2Community}
            />
          </label>
        ) : (
          <div className="control-form-grid">
            <label className="control-field">
              <span>SNMPv3 username</span>
              <input
                autoComplete="off"
                onChange={(event) =>
                  context.setCredentialDraft((current) => ({ ...current, snmpV3Username: event.target.value }))
                }
                placeholder="Not saved"
                type="text"
                value={context.credentialDraft.snmpV3Username}
              />
            </label>
            <label className="control-field">
              <span>SNMPv3 auth password</span>
              <input
                autoComplete="off"
                onChange={(event) =>
                  context.setCredentialDraft((current) => ({ ...current, snmpV3AuthPassword: event.target.value }))
                }
                placeholder="Not saved"
                type="password"
                value={context.credentialDraft.snmpV3AuthPassword}
              />
            </label>
            <label className="control-field">
              <span>SNMPv3 privacy password</span>
              <input
                autoComplete="off"
                onChange={(event) =>
                  context.setCredentialDraft((current) => ({ ...current, snmpV3PrivacyPassword: event.target.value }))
                }
                placeholder="Not saved"
                type="password"
                value={context.credentialDraft.snmpV3PrivacyPassword}
              />
            </label>
          </div>
        )}
        <p className="control-note">Credential values are never persisted. Saving stores only configured or missing state.</p>
      </section>

      <details className="control-panel control-details">
        <summary>Advanced</summary>
        <FactGrid
          facts={[
            ["Config adapter", "Local non-secret storage"],
            ["Backend config endpoint", "Integration pending"],
            ["Provider mode", context.health?.provider_mode ?? "Unknown"],
            ["Last saved", context.config.updatedAt ? formatDateTime(context.config.updatedAt) : "Not saved"]
          ]}
        />
      </details>

      {context.configErrors.length > 0 && <IssueGroup title="Validation errors" items={context.configErrors} />}
      <div className="control-actions">
        <button className="primary" onClick={context.saveConfig} type="button">
          <Save size={16} />
          Save / apply config
        </button>
        <Link className="button-link" to="/run">
          <Play size={16} />
          Continue to Run
        </Link>
      </div>
      {context.configMessage && <p className="control-action-message success">{context.configMessage}</p>}
    </Page>
  );
}

function RunPage({ context }: { context: ControlCenterContext }) {
  const running = context.runStatus === "running";
  return (
    <Page title="Run" subtitle="Review the current configuration, then run one selected backend action.">
      <section className="control-panel control-run-panel">
        <div>
          <PanelTitle icon={<Play size={18} />} title="Current Config Summary" />
          <FactGrid
            facts={[
              ["Target", context.config.target || "Not configured"],
              ["IP mode", ipModeLabel(context.config.ipMode)],
              ["SNMP", snmpVersionLabel(context.config.snmpVersion)],
              ["Timeout / retry", `${context.config.timeoutSeconds}s / ${context.config.retryCount}`],
              ["Backend action", context.selectedAction?.label ?? "Safe placeholder"],
              ["Action source", context.selectedAction?.source_type ?? "todo_placeholder"]
            ]}
          />
        </div>
        <button className="control-run-button primary" disabled={running} onClick={() => void context.runSelectedAction()} type="button">
          <Play size={20} />
          {running ? "Running" : "Run"}
        </button>
      </section>
      {!context.selectedAction && (
        <div className="control-alert warning">
          Backend action catalog is unavailable. Run returns a safe placeholder and does not contact providers.
        </div>
      )}
      {context.runError && <div className="control-alert error">{context.runError}</div>}
      <section className="control-panel">
        <PanelTitle icon={<FileText size={18} />} title="Latest Result Preview" />
        {running ? (
          <div className="control-loading">Running selected action...</div>
        ) : context.latestRun ? (
          <ResultDetails compact result={context.latestRun} />
        ) : (
          <EmptyState title="No result yet" detail="Press Run to execute the current action." />
        )}
      </section>
      <section className="control-panel">
        <PanelTitle icon={<History size={18} />} title="Run Activity" />
        <ActivityList logs={context.logs.filter((log) => log.type === "run")} />
      </section>
    </Page>
  );
}

function FirmwarePage({ context }: { context: ControlCenterContext }) {
  const supportedAction = context.selectedUpgradeAction?.label ?? supportedUpgradeActionId(context.selectedPath);
  const backendPending = Boolean(context.selectedPath && !supportedAction);
  const startDisabled = context.firmwareUpgradeBlockers.length > 0 || context.upgradeStatus === "upgrading";
  const validateDisabled =
    context.upgradeStatus === "validating" || !context.selectedPath || !context.selectedFirmware.trim();
  const requiredGates = context.selectedUpgradeAction?.required_gates ?? [];
  return (
    <Page title="Firmware" subtitle="Firmware visibility, validation, upgrade gating, and events.">
      <section className="control-panel">
        <div className="control-panel-head">
          <PanelTitle icon={<Cpu size={18} />} title="Firmware Visibility" />
          <button disabled={context.firmwareCheckStatus === "running"} onClick={() => void context.checkFirmware()} type="button">
            <RefreshCw size={16} />
            {context.firmwareCheckStatus === "running" ? "Checking" : "Check Firmware"}
          </button>
        </div>
        {context.firmware.summaries.length ? (
          <div className="firmware-visibility-grid">
            {context.firmware.summaries.map((summary) => (
              <FirmwareVisibilityCard key={summary.device_id} summary={summary} />
            ))}
          </div>
        ) : (
          <EmptyState title="No firmware summary" detail="Run Check Firmware or confirm the backend firmware summary endpoint is available." />
        )}
      </section>

      <section className="control-panel">
        <div className="control-panel-head">
          <PanelTitle icon={<UploadCloud size={18} />} title="Firmware Upgrade" />
          <StatusPill status={context.upgradeStatus} />
        </div>
        <FactGrid
          facts={[
            ["Target", context.targetSummary],
            ["Current firmware", context.selectedPath ? displayValue(context.selectedPath.current_version) : "Select a firmware path"],
            ["Selected firmware/image/version", context.selectedFirmware || "Missing"],
            ["Compatibility check", validationStatusLabel(context)],
            ["Readiness", firmwareReadinessLabel(context)],
            ["Backend apply", supportedAction ?? "Integration pending"],
            ["Required gates", requiredGates.length ? requiredGates.join(", ") : "None reported"]
          ]}
        />
        <div className="control-form-grid">
          <label className="control-field control-field-wide">
            <span>Firmware path</span>
            <select onChange={(event) => context.setSelectedPathId(event.target.value)} value={context.selectedPathId}>
              <option value="">Select firmware path</option>
              {collectFirmwarePaths(context.firmware.summaries).map((path) => (
                <option key={firmwarePathId(path)} value={firmwarePathId(path)}>
                  {firmwarePathLabel(path)}
                </option>
              ))}
            </select>
          </label>
          <label className="control-field control-field-wide">
            <span>Selected firmware, image, or version</span>
            <input
              onChange={(event) => context.setSelectedFirmware(event.target.value)}
              placeholder="Select a path or enter a target firmware/image reference"
              type="text"
              value={context.selectedFirmware}
            />
          </label>
        </div>
        {backendPending && (
          <div className="control-alert warning">
            Backend upgrade integration is pending for this firmware path. Starting upgrade will return a safe TODO result and will not run a provider update.
          </div>
        )}
        <div className="control-actions">
          <button disabled={validateDisabled} onClick={() => void context.validateFirmware()} type="button">
            <ShieldCheck size={16} />
            {context.upgradeStatus === "validating" ? "Validating" : "Validate Firmware"}
          </button>
        </div>
        <div className="firmware-confirm-box">
          <label className="control-check-field">
            <input
              checked={context.upgradeConfirmationAccepted}
              onChange={(event) => context.setUpgradeConfirmationAccepted(event.target.checked)}
              type="checkbox"
            />
            <span>Require explicit operator confirmation before any firmware upgrade request is sent.</span>
          </label>
          <label className="control-field">
            <span>Confirmation phrase</span>
            <input
              onChange={(event) => context.setUpgradeConfirmationPhrase(event.target.value)}
              placeholder={context.expectedUpgradePhrase}
              type="text"
              value={context.upgradeConfirmationPhrase}
            />
          </label>
          {context.firmwareUpgradeBlockers.length > 0 && <IssueGroup title="Upgrade blockers" items={context.firmwareUpgradeBlockers} />}
          <button className="primary" disabled={startDisabled} onClick={() => void context.startFirmwareUpgrade()} type="button">
            <UploadCloud size={16} />
            {context.upgradeStatus === "upgrading" ? "Upgrade Running" : "Start Firmware Upgrade"}
          </button>
        </div>
        {context.upgradeStatus === "upgrading" && (
          <div className="control-loading">Upgrade request is with the backend guard runner. Progress is shown when the backend returns it.</div>
        )}
      </section>

      <section className="control-panel">
        <PanelTitle icon={<History size={18} />} title="Firmware Events" />
        <ActivityList logs={context.logs.filter((log) => log.type === "firmware")} />
      </section>
    </Page>
  );
}

function ResultsPage({ context }: { context: ControlCenterContext }) {
  return (
    <Page title="Results" subtitle="Latest run, firmware check, validation, and firmware upgrade outcomes.">
      <div className="result-panel-grid">
        <section className="control-panel">
          <PanelTitle icon={<Play size={18} />} title="Latest Run Result" />
          {context.latestRun ? <ResultDetails result={context.latestRun} /> : <EmptyState title="No run result" detail="Run an action to populate this panel." />}
        </section>
        <section className="control-panel">
          <PanelTitle icon={<ShieldCheck size={18} />} title="Latest Firmware Check Summary" />
          {context.latestFirmwareCheck ? <ResultDetails result={context.latestFirmwareCheck} /> : <EmptyState title="No firmware check" detail="Use Check Firmware on the Firmware page." />}
        </section>
        <section className="control-panel">
          <PanelTitle icon={<ShieldCheck size={18} />} title="Latest Firmware Validation Summary" />
          {context.latestFirmwareValidation ? <ResultDetails result={context.latestFirmwareValidation} /> : <EmptyState title="No firmware validation" detail="Select firmware, then validate before upgrade." />}
        </section>
        <section className="control-panel">
          <PanelTitle icon={<UploadCloud size={18} />} title="Latest Firmware Upgrade Summary" />
          {context.latestFirmwareUpgrade ? <ResultDetails result={context.latestFirmwareUpgrade} /> : <EmptyState title="No firmware upgrade" detail="Upgrade attempts appear here after confirmation." />}
        </section>
      </div>
    </Page>
  );
}

function LogsPage({ context }: { context: ControlCenterContext }) {
  const backendLogs = logsAdapter.fromAuditEvents(context.auditEvents);
  return (
    <Page title="Logs" subtitle="Config, run, firmware, settings, and backend audit activity.">
      <section className="control-panel">
        <PanelTitle icon={<History size={18} />} title="Activity Timeline" />
        <ActivityList logs={[...context.logs, ...backendLogs]} />
      </section>
    </Page>
  );
}

function SettingsPage({ context }: { context: ControlCenterContext }) {
  return (
    <Page title="Settings" subtitle="Global and advanced defaults only. Target-specific values stay in Configure.">
      <section className="control-panel">
        <PanelTitle icon={<Settings size={18} />} title="Global Defaults" />
        <div className="control-form-grid">
          <label className="control-field">
            <span>Default IP mode</span>
            <select
              onChange={(event) => context.setSettings((current) => ({ ...current, defaultIpMode: event.target.value as ControlSettings["defaultIpMode"] }))}
              value={context.settings.defaultIpMode}
            >
              <option value="ipv4">IPv4</option>
              <option value="ipv6">IPv6</option>
              <option value="both">Both</option>
            </select>
          </label>
          <label className="control-field">
            <span>Default SNMP version</span>
            <select
              onChange={(event) => context.setSettings((current) => ({ ...current, defaultSnmpVersion: event.target.value as ControlSettings["defaultSnmpVersion"] }))}
              value={context.settings.defaultSnmpVersion}
            >
              <option value="v2">SNMPv2</option>
              <option value="v3">SNMPv3</option>
            </select>
          </label>
          <label className="control-field">
            <span>Timeout default</span>
            <input
              max={120}
              min={1}
              onChange={(event) => context.setSettings((current) => ({ ...current, defaultTimeoutSeconds: Number(event.target.value) }))}
              type="number"
              value={context.settings.defaultTimeoutSeconds}
            />
          </label>
          <label className="control-field">
            <span>Retry default</span>
            <input
              max={5}
              min={0}
              onChange={(event) => context.setSettings((current) => ({ ...current, defaultRetryCount: Number(event.target.value) }))}
              type="number"
              value={context.settings.defaultRetryCount}
            />
          </label>
        </div>
      </section>
      <section className="control-panel">
        <PanelTitle icon={<TerminalSquare size={18} />} title="Advanced Backend Settings" />
        <div className="control-form-grid">
          <label className="control-field control-field-wide">
            <span>API/server URL</span>
            <input
              onChange={(event) => context.setSettings((current) => ({ ...current, apiBaseUrl: event.target.value }))}
              type="text"
              value={context.settings.apiBaseUrl}
            />
          </label>
          <label className="control-field control-field-wide">
            <span>Firmware repository/source</span>
            <input
              onChange={(event) => context.setSettings((current) => ({ ...current, firmwareRepository: event.target.value }))}
              type="text"
              value={context.settings.firmwareRepository}
            />
          </label>
          <label className="control-field">
            <span>Logging verbosity</span>
            <select
              onChange={(event) => context.setSettings((current) => ({ ...current, loggingVerbosity: event.target.value as ControlSettings["loggingVerbosity"] }))}
              value={context.settings.loggingVerbosity}
            >
              <option value="errors">Errors only</option>
              <option value="normal">Normal</option>
              <option value="debug">Debug</option>
            </select>
          </label>
        </div>
      </section>
      <section className="control-panel">
        <PanelTitle icon={<ShieldCheck size={18} />} title="Runtime" />
        <FactGrid
          facts={[
            ["Provider mode", context.providerMode?.current_mode ?? context.health?.provider_mode ?? "Unknown"],
            ["Desired mode", context.providerMode?.desired_mode ?? "Unknown"],
            ["Pending restart", context.providerMode?.pending_restart ? "Yes" : "No"],
            ["Restart command", context.providerMode?.restart_command ?? "Not reported"]
          ]}
        />
        {context.providerMode?.next_safe_action && <p className="control-note">{context.providerMode.next_safe_action}</p>}
      </section>
      <div className="control-actions">
        <button className="primary" onClick={context.saveSettings} type="button">
          <Save size={16} />
          Save settings
        </button>
      </div>
      {context.settingsMessage && <p className="control-action-message success">{context.settingsMessage}</p>}
    </Page>
  );
}

function Page({ children, subtitle, title }: { children: ReactNode; subtitle: string; title: string }) {
  return (
    <div className="control-page">
      <div className="control-page-head">
        <p className="control-kicker">WebUIs</p>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
      {children}
    </div>
  );
}

function PanelTitle({ icon, title }: { icon?: ReactNode; title: string }) {
  return (
    <h3 className="control-panel-title">
      {icon}
      {title}
    </h3>
  );
}

function StatusChip({ label, value }: { label: string; value: string }) {
  return (
    <div className={`control-status-chip ${statusClass(value)}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  return <span className={`control-inline-status ${statusClass(status)}`}>{statusLabel(status)}</span>;
}

function FactGrid({ facts }: { facts: Array<[string, string]> }) {
  return (
    <dl className="control-fact-grid">
      {facts.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function FirmwareVisibilityCard({ summary }: { summary: FirmwareSummary }) {
  return (
    <article className="firmware-card">
      <div className="firmware-card-head">
        <strong>{summary.label}</strong>
        <StatusPill status={summary.compliance_status} />
      </div>
      <FactGrid
        facts={[
          ["Detected device/model", summary.label],
          ["Current firmware version", firmwareCurrentVersion(summary)],
          ["Available firmware version", displayValue(summary.target_version || firstApprovedVersion(summary))],
          ["Build/date", "Not reported by backend"],
          ["Bootloader/version", firmwareBootloaderVersion(summary)],
          ["Hardware revision", "Not reported by backend"],
          ["Compatibility status", statusLabel(summary.path_status || summary.compliance_status)],
          ["Last check time", summary.last_scanned ? formatDateTime(summary.last_scanned) : "Not checked"],
          ["Detection source", `${sourceLabel(summary.source_type)} / ${statusLabel(summary.freshness)}`]
        ]}
      />
      {summary.blocker && <div className="control-alert warning">{summary.blocker}</div>}
    </article>
  );
}

function FirmwareRollup({ summaries }: { summaries: FirmwareSummary[] }) {
  if (!summaries.length) {
    return <EmptyState title="Not checked" detail="Firmware summary is not available yet." />;
  }
  const blocked = summaries.filter((summary) => ["blocked", "cannot_verify", "not_configured"].includes(summary.compliance_status)).length;
  const needsUpgrade = summaries.filter((summary) => summary.compliance_status === "needs_upgrade").length;
  const sortedScanTimes = summaries
    .map((summary) => summary.last_scanned)
    .filter((value): value is string => Boolean(value))
    .sort();
  const latest = sortedScanTimes[sortedScanTimes.length - 1];
  return (
    <div className="control-result-summary">
      <span className={`control-inline-status ${blocked ? "is-warn" : "is-good"}`}>
        {blocked ? "Needs attention" : "Visible"}
      </span>
      <strong>{summaries.length} firmware surfaces detected</strong>
      <p>
        {needsUpgrade} need upgrade review. {blocked} are blocked or not configured. Last check {latest ? formatDateTime(latest) : "not reported"}.
      </p>
    </div>
  );
}

function ResultSummary({ result }: { result: OperationResult }) {
  return (
    <div className="control-result-summary">
      <StatusPill status={result.status} />
      <strong>{result.title}</strong>
      <p>{result.message}</p>
    </div>
  );
}

function ResultDetails({ compact = false, result }: { compact?: boolean; result: OperationResult }) {
  return (
    <div className="control-result-details">
      <ResultSummary result={result} />
      <FactGrid
        facts={[
          ["Checked", formatDateTime(result.checkedAt)],
          ["Source", sourceLabel(result.sourceType)],
          ["Freshness", statusLabel(result.freshness)],
          ["Executed", result.executed ? "Yes" : "No"]
        ]}
      />
      <IssueGroup title="Blockers" items={result.blockers} />
      <IssueGroup title="Warnings" items={result.warnings} />
      {result.artifacts.length > 0 && (
        <div className="control-artifacts">
          <strong>Artifacts</strong>
          {result.artifacts.map((artifact) => (
            <code key={artifact}>{artifact}</code>
          ))}
        </div>
      )}
      {!compact && (
        <details className="control-details">
          <summary>Raw result</summary>
          <pre className="control-code">{JSON.stringify(result.raw, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}

function IssueGroup({ items, title }: { items: string[]; title: string }) {
  if (!items.length) return null;
  return (
    <div className="control-issue-group">
      <strong>{title}</strong>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function ActivityList({ logs }: { logs: ControlLogEntry[] }) {
  const visible = [...logs].sort((first, second) => Date.parse(second.timestamp) - Date.parse(first.timestamp));
  if (!visible.length) {
    return <EmptyState title="No logs yet" detail="Config, run, firmware, settings, and backend events will appear here." />;
  }
  return (
    <ol className="control-log-list">
      {visible.map((entry) => (
        <li key={entry.id}>
          <Activity size={16} />
          <div>
            <time>{formatDateTime(entry.timestamp)}</time>
            <strong>{entry.message}</strong>
            {entry.detail && <p>{entry.detail}</p>}
          </div>
          {entry.status && <StatusPill status={entry.status} />}
        </li>
      ))}
    </ol>
  );
}

function EmptyState({ detail, title }: { detail: string; title: string }) {
  return (
    <div className="control-empty">
      <TerminalSquare size={22} />
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  );
}

function collectFirmwarePaths(summaries: FirmwareSummary[]): FirmwareUpgradePath[] {
  return summaries.flatMap((summary) => summary.upgrade_paths ?? []);
}

function firmwarePathId(path: FirmwareUpgradePath): string {
  return `${path.device_label}:${path.component_id}:${path.target_version ?? path.package_name ?? "unknown"}`;
}

function firmwarePathLabel(path: FirmwareUpgradePath): string {
  const target = path.target_version || path.package_name || path.selected_file_name || "target pending";
  return `${path.device_label} - ${path.component_label} -> ${target}`;
}

function defaultFirmwareSelection(path: FirmwareUpgradePath | null): string {
  return path?.selected_file_name || path?.package_name || path?.target_version || "";
}

function firmwareCurrentVersion(summary: FirmwareSummary): string {
  return displayValue(summary.current_versions.find((item) => item.version)?.version ?? null);
}

function firstApprovedVersion(summary: FirmwareSummary): string | null {
  return summary.approved_versions.find((item) => item.version)?.version ?? null;
}

function firmwareBootloaderVersion(summary: FirmwareSummary): string {
  const bootloader = summary.current_versions.find((item) => /boot|rommon/i.test(item.label));
  return displayValue(bootloader?.version ?? null);
}

function firmwareReadinessLabel(context: ControlCenterContext): string {
  if (!context.selectedPath) return "Missing firmware path";
  if (!context.selectedFirmware) return "Missing selected firmware";
  if (!context.latestFirmwareValidation) return "Validation required";
  if (!firmwareValidationMatchesSelection(context.latestFirmwareValidation, context.selectedPath, context.selectedFirmware)) {
    return "Validation required for selection";
  }
  if (!firmwareValidationPassed(context.latestFirmwareValidation)) return "Blocked by validation";
  if (!context.selectedUpgradeAction) return "Backend integration pending";
  return "Ready for guarded backend request";
}

function firmwareStartBlockers(input: {
  accepted: boolean;
  config: ControlConfig;
  phrase: string;
  selectedFirmware: string;
  selectedPath: FirmwareUpgradePath | null;
  selectedUpgradeAction: WorkflowAction | null;
  validation: OperationResult | null;
}): string[] {
  const blockers: string[] = [];
  blockers.push(...configAdapter.validate(input.config));
  if (!input.selectedPath) blockers.push("Select a firmware path before starting an upgrade.");
  if (!input.selectedFirmware.trim()) blockers.push("Selected firmware, image, or target version is required.");
  if (!input.validation) {
    blockers.push("Validate firmware before starting an upgrade.");
  } else if (!firmwareValidationMatchesSelection(input.validation, input.selectedPath, input.selectedFirmware)) {
    blockers.push("Validate the currently selected firmware path before starting an upgrade.");
  } else if (!firmwareValidationPassed(input.validation)) {
    blockers.push("Firmware validation failed or is blocked. No override is supported.");
  }
  const expected = upgradeConfirmationPhrase(input.selectedPath, input.selectedUpgradeAction);
  if (!input.accepted || input.phrase.trim() !== expected) {
    blockers.push(`Type ${expected} and check the confirmation box.`);
  }
  return blockers;
}

function upgradeStatusFromResult(result: OperationResult | null): UpgradeStatus {
  if (!result) return "idle";
  return upgradeStatusAfterResult(result);
}

function upgradeStatusAfterResult(result: OperationResult): UpgradeStatus {
  if (result.status === "success") return "success";
  if (result.status === "blocked") return "blocked";
  if (result.status === "pending") return "pending";
  return "failed";
}

function operationLogMessage(prefix: string, status: string): string {
  if (["success", "ready"].includes(status)) return `${prefix} succeeded`;
  if (["blocked", "pending"].includes(status)) return `${prefix} blocked`;
  return `${prefix} failed`;
}

function resultStatusLabel(result: OperationResult | null, fallback: OperationStatus): string {
  if (fallback === "running") return "Running";
  return result ? statusLabel(result.status) : "Not run";
}

function firmwareStatusLabel(context: ControlCenterContext): string {
  if (context.upgradeStatus === "upgrading") return "Upgrade running";
  if (context.latestFirmwareUpgrade) return `Upgrade ${statusLabel(context.latestFirmwareUpgrade.status)}`;
  if (context.latestFirmwareCheck) return statusLabel(context.latestFirmwareCheck.status);
  return context.firmware.summaries.length ? "Summary loaded" : "Not checked";
}

function validationStatusLabel(context: ControlCenterContext): string {
  if (!context.latestFirmwareValidation) return "Not validated";
  if (!firmwareValidationMatchesSelection(context.latestFirmwareValidation, context.selectedPath, context.selectedFirmware)) {
    return "Not validated for selection";
  }
  return statusLabel(context.latestFirmwareValidation.status);
}

function ipModeLabel(value: string): string {
  if (value === "ipv6") return "IPv6";
  if (value === "both") return "IPv4 and IPv6";
  return "IPv4";
}

function snmpVersionLabel(value: string): string {
  return value === "v3" ? "SNMPv3" : "SNMPv2";
}

function credentialStatusLabel(value: string): string {
  return value === "configured" ? "Configured" : "Missing";
}

function formatDateTime(value: string): string {
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return value;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(parsed);
}

function displayValue(value: string | null | undefined): string {
  return value && value.trim() ? value : "Not reported";
}

function sourceLabel(value: string): string {
  return value.replace(/[_-]+/g, " ");
}

function statusLabel(value: string): string {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function statusClass(value: string): string {
  const normalized = value.toLowerCase();
  if (/(success|ready|completed|connected|visible|current|saved|ok|passed)/.test(normalized)) return "is-good";
  if (/(running|checking|validating|summary|loaded)/.test(normalized)) return "is-info";
  if (/(warning|blocked|pending|missing|not configured|unavailable|not checked|not run|attention)/.test(normalized)) return "is-warn";
  if (/(failed|error|disconnected)/.test(normalized)) return "is-bad";
  return "is-neutral";
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
