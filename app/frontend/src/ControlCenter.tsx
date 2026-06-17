import {
  Activity,
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
  Wrench
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
  providers: ProviderStatus[];
  refreshControlCenter: () => Promise<void>;
  runError: string;
  runSelectedAction: () => Promise<void>;
  runStatus: OperationStatus;
  saveConfig: () => Promise<void>;
  saveSettings: () => Promise<void>;
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
      setProviders(snapshot.providers);
      setActions(snapshot.actions);
      setAuditEvents(snapshot.auditEvents);
      setFirmware(snapshot.firmware);
      if (snapshot.controlConfig) {
        setConfig(snapshot.controlConfig);
      }
      if (snapshot.controlSettings) {
        setSettings(snapshot.controlSettings);
      }
    } catch (error) {
      setLoadError(errorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  function addLog(entry: Omit<ControlLogEntry, "id" | "timestamp">) {
    setLogs((current) => logsAdapter.add(current, entry));
  }

  async function saveConfig() {
    const result = await configAdapter.save(config, credentialDraft);
    setConfig(result.config);
    setConfigErrors(result.errors);
    setConfigMessage(
      result.errors.length
        ? ""
        : result.savedVia === "backend"
          ? "Configuration saved to backend runtime state"
          : "Configuration saved locally; backend config endpoint was unavailable"
    );
    if (result.errors.length) {
      addLog({
        detail: result.errors.join(" "),
        message: "Config save failed",
        status: "blocked",
        type: "config"
      });
      return;
    }
    const clearedResults = Boolean(
      latestRun || latestFirmwareCheck || latestFirmwareValidation || latestFirmwareUpgrade
    );
    if (clearedResults) {
      clearStoredResults();
    }
    setCredentialDraft(defaultCredentialDraft);
    addLog({
      detail: `${result.config.target}; ${ipModeLabel(result.config.ipMode)}; ${snmpVersionLabel(result.config.snmpVersion)}.${
        clearedResults ? " Previous results were cleared because they used an older config." : ""
      } ${result.savedVia === "backend" ? "Saved through backend config adapter." : "Saved in browser fallback state."}`,
      message: "Config saved",
      status: "saved",
      type: "config"
    });
  }

  async function saveSettings() {
    const result = await settingsAdapter.save(settings);
    const next = result.settings;
    setSettings(next);
    setSettingsMessage(
      result.savedVia === "backend"
        ? "Settings saved to backend runtime state"
        : "Settings saved locally; backend settings endpoint was unavailable"
    );
    addLog({
      detail: `Default ${ipModeLabel(next.defaultIpMode)}, ${snmpVersionLabel(next.defaultSnmpVersion)}, timeout ${next.defaultTimeoutSeconds}s. ${
        result.savedVia === "backend" ? "Saved through backend settings adapter." : "Saved in browser fallback state."
      }`,
      message: "Settings changed",
      status: "saved",
      type: "settings"
    });
  }

  async function syncConfigForAction(): Promise<{ config: ControlConfig; errors: string[]; savedVia: "backend" | "local_fallback" }> {
    const result = await configAdapter.save(config, defaultCredentialDraft);
    setConfig(result.config);
    setConfigErrors(result.errors);
    return result;
  }

  async function runSelectedAction() {
    if (runStatus === "running") return;
    setRunError("");
    setRunStatus("running");
    const syncResult = await syncConfigForAction();
    const currentConfig = syncResult.config;
    addLog({
      detail: `${selectedAction?.label ?? "Safe placeholder"} for ${currentConfig.target || "Not configured"}.`,
      message: "Run started",
      status: "running",
      type: "run"
    });
    try {
      const result =
        syncResult.errors.length || syncResult.savedVia === "backend"
          ? await runAdapter.run(currentConfig, selectedAction)
          : createLocalOperationResult({
              blockers: ["Current config could not be saved to backend runtime state before Run."],
              message: "Run blocked so the backend cannot use stale configuration.",
              raw: {
                config_snapshot: {
                  ip_mode: currentConfig.ipMode,
                  retry_count: currentConfig.retryCount,
                  snmp_credentials: currentConfig.snmpCredentialStatus,
                  snmp_credential_version: currentConfig.snmpCredentialVersion,
                  snmp_version: currentConfig.snmpVersion,
                  target: currentConfig.target,
                  timeout_seconds: currentConfig.timeoutSeconds
                }
              },
              status: "blocked",
              title: "Run blocked",
              type: "run"
            });
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
            snmp_credential_version: config.snmpCredentialVersion,
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
    const syncResult = await syncConfigForAction();
    const currentConfig = syncResult.config;
    addLog({
      detail: `Firmware visibility check started for ${currentConfig.target || "Not configured"}. No upgrade action is triggered.`,
      message: "Firmware check started",
      status: "running",
      type: "firmware"
    });
    try {
      let nextFirmware: FirmwareState | null = null;
      let result: OperationResult;
      if (syncResult.errors.length || syncResult.savedVia === "backend") {
        const response = await firmwareAdapter.check(currentConfig);
        nextFirmware = response.firmware;
        result = response.result;
      } else {
        result = createLocalOperationResult({
          blockers: ["Current config could not be saved to backend runtime state before Firmware Check."],
          message: "Firmware check blocked so the backend cannot use stale configuration.",
          status: "blocked",
          title: "Firmware check blocked",
          type: "firmware-check"
        });
      }
      if (nextFirmware) {
        setFirmware(nextFirmware);
      }
      setLatestFirmwareCheck(result);
      resultsAdapter.saveFirmwareCheck(result);
      setFirmwareCheckStatus(result.status);
      addLog({
        detail: result.message,
        message: operationLogMessage("Firmware check", result.status),
        status: result.status,
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
    const syncResult = await syncConfigForAction();
    const currentConfig = syncResult.config;
    addLog({
      detail: selectedPath ? firmwarePathLabel(selectedPath) : "No firmware path selected.",
      message: "Firmware validation started",
      status: "running",
      type: "firmware"
    });
    try {
      const response =
        syncResult.errors.length || syncResult.savedVia === "backend"
          ? await firmwareAdapter.validate({
              config: currentConfig,
              selectedFirmware,
              selectedPath
            })
          : {
              firmware,
              result: createLocalOperationResult({
                blockers: ["Current config could not be saved to backend runtime state before Firmware Validate."],
                message: "Firmware validation blocked so the backend cannot use stale configuration.",
                status: "blocked",
                title: "Firmware validation blocked",
                type: "firmware-validation"
              })
            };
      setFirmware(response.firmware);
      setLatestFirmwareValidation(response.result);
      resultsAdapter.saveFirmwareValidation(response.result);
      setUpgradeStatus(
        firmwareValidationPassed(response.result)
          ? "ready"
          : response.result.status === "blocked"
            ? "blocked"
            : "failed"
      );
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
    const syncResult = await syncConfigForAction();
    const currentConfig = syncResult.config;
    const currentBlockers =
      syncResult.savedVia === "backend" || syncResult.errors.length
        ? firmwareStartBlockers({
            accepted: upgradeConfirmationAccepted,
            config: currentConfig,
            phrase: upgradeConfirmationPhraseState,
            selectedFirmware,
            selectedPath,
            selectedUpgradeAction,
            validation: latestFirmwareValidation
          })
        : ["Current config could not be saved to backend runtime state before Firmware Upgrade."];
    if (currentBlockers.length > 0) {
      const result = createLocalOperationResult({
        blockers: currentBlockers,
        message: "Firmware upgrade was not started.",
        status: "blocked",
        title: "Firmware upgrade blocked",
        type: "firmware-upgrade"
      });
      setLatestFirmwareUpgrade(result);
      resultsAdapter.saveFirmwareUpgrade(result);
      setUpgradeStatus("blocked");
      addLog({
        detail: currentBlockers.join(" "),
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
        config: currentConfig,
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
    clearFirmwareGateResults();
    setUpgradeConfirmationAccepted(false);
    setUpgradeConfirmationPhrase("");
    setUpgradeStatus("idle");
  }

  function updateSelectedFirmware(value: string) {
    setSelectedFirmware(value);
    clearFirmwareGateResults();
    setUpgradeConfirmationAccepted(false);
    setUpgradeConfirmationPhrase("");
    if (upgradeStatus !== "upgrading") {
      setUpgradeStatus("idle");
    }
  }

  function clearStoredResults() {
    setLatestRun(null);
    setLatestFirmwareCheck(null);
    clearFirmwareGateResults();
    resultsAdapter.clearRun();
    resultsAdapter.clearFirmwareCheck();
    setRunStatus("idle");
    setFirmwareCheckStatus("idle");
    setUpgradeConfirmationAccepted(false);
    setUpgradeConfirmationPhrase("");
    setUpgradeStatus("idle");
  }

  function clearFirmwareGateResults() {
    setLatestFirmwareValidation(null);
    setLatestFirmwareUpgrade(null);
    resultsAdapter.clearFirmwareValidation();
    resultsAdapter.clearFirmwareUpgrade();
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
          <Route path="/control-center" element={<LegacyControlCenterRedirect />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </main>
    </div>
  );
}

function LegacyControlCenterRedirect() {
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const section = `${params.get("section") ?? ""} ${params.get("action") ?? ""} ${params.get("device") ?? ""}`.toLowerCase();
  let target = "/dashboard";
  if (/(configure|config|setup|target)/.test(section)) {
    target = "/configure";
  } else if (/(firmware|upgrade|ontap)/.test(section)) {
    target = "/firmware";
  } else if (/(report|result|evidence|artifact)/.test(section)) {
    target = "/results";
  } else if (/(^|\s)(logs?|audit)(\s|$)/.test(section)) {
    target = "/logs";
  } else if (/(setting|provider-mode|runtime)/.test(section)) {
    target = "/settings";
  } else if (/(action|cisco|ilo|raid|esxi|netapp|serial|lab_profile)/.test(section)) {
    target = "/run";
  }
  return <Navigate to={target} replace />;
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
  const firmwareCount = context.firmware.summaries.length;
  const firmwareNeedsReview = context.firmware.summaries.filter((summary) =>
    ["needs_upgrade", "blocked", "cannot_verify", "not_configured"].includes(summary.compliance_status)
  ).length;
  return (
    <Page title="Dashboard" subtitle="Control Center overview.">
      <section className="control-panel control-overview-panel">
        <PanelTitle icon={<Gauge size={18} />} title="Current Target" />
        <FactGrid
          facts={[
            ["Current target", context.targetSummary],
            ["API / connection", context.connectionStatus],
            ["IP mode", ipModeLabel(context.config.ipMode)],
            ["SNMP version", snmpVersionLabel(context.config.snmpVersion)],
            [
              "Detected firmware",
              firmwareCount ? `${firmwareCount} surfaces, ${firmwareNeedsReview} need review` : "Not checked"
            ],
            ["Last run", resultStatusLabel(context.latestRun, context.runStatus)],
            ["Last firmware check", context.latestFirmwareCheck ? statusLabel(context.latestFirmwareCheck.status) : "Not checked"],
            [
              "Last firmware upgrade",
              context.latestFirmwareUpgrade ? statusLabel(context.latestFirmwareUpgrade.status) : "Not started"
            ]
          ]}
        />
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
      <section className="control-panel">
        <PanelTitle icon={<UploadCloud size={18} />} title="Firmware Summary" />
        <FirmwareRollup summaries={context.firmware.summaries} />
      </section>
    </Page>
  );
}

function ConfigurePage({ context }: { context: ControlCenterContext }) {
  return (
    <Page title="Configure" subtitle="Target and protocol configuration.">
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
        </div>

        <div className="credential-block">
          <PanelTitle icon={<ShieldCheck size={18} />} title="SNMP Credentials" />
          {context.config.snmpVersion === "v2" ? (
            <label className="control-field control-field-wide">
              <span>SNMPv2 community</span>
              <input
                autoComplete="off"
                onChange={(event) =>
                  context.setCredentialDraft((current) => ({ ...current, snmpV2Community: event.target.value }))
                }
                placeholder="Configured at save time"
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
                  placeholder="Configured at save time"
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
                  placeholder="Configured at save time"
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
                  placeholder="Configured at save time"
                  type="password"
                  value={context.credentialDraft.snmpV3PrivacyPassword}
                />
              </label>
            </div>
          )}
          <p className="control-note">
            Credential values are not stored in Control Center state; only configured/missing status is saved.
          </p>
        </div>
      </section>

      <details className="control-panel control-details">
        <summary>Advanced</summary>
        <div className="control-form-grid">
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
        <FactGrid
          facts={[
            ["Config adapter", "Backend non-secret runtime state with browser fallback"],
            ["Backend config endpoint", "/api/v1/control-center/config"],
            ["Credential state", credentialConfigLabel(context.config)],
            ["Provider mode", context.health?.provider_mode ?? "Unknown"],
            ["Last saved", context.config.updatedAt ? formatDateTime(context.config.updatedAt) : "Not saved"]
          ]}
        />
      </details>

      {context.configErrors.length > 0 && <IssueGroup title="Validation errors" items={context.configErrors} />}
      <div className="control-actions">
        <button className="primary" onClick={() => void context.saveConfig()} type="button">
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
    <Page title="Run" subtitle="Run the configured action.">
      <section className="control-panel control-run-panel">
        <div>
          <PanelTitle icon={<Play size={18} />} title="Current Config Summary" />
          <FactGrid
            facts={[
              ["Target", context.config.target || "Not configured"],
              ["IP mode", ipModeLabel(context.config.ipMode)],
              ["SNMP", snmpVersionLabel(context.config.snmpVersion)],
              ["SNMP credentials", credentialConfigLabel(context.config)],
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
  const supportedActionId = supportedUpgradeActionId(context.selectedPath);
  const backendApply = context.selectedUpgradeAction?.label ?? (supportedActionId ? `${supportedActionId} unavailable` : "Integration pending");
  const backendPending = Boolean(context.selectedPath && (!supportedActionId || !context.selectedUpgradeAction));
  const startDisabled = context.firmwareUpgradeBlockers.length > 0 || context.upgradeStatus === "upgrading";
  const validateDisabled =
    context.upgradeStatus === "validating" || !context.selectedPath || !context.selectedFirmware.trim();
  const requiredGates = context.selectedUpgradeAction?.required_gates ?? [];
  return (
    <Page title="Firmware" subtitle="Visibility, validation, upgrade workflow, and events.">
      <section className="control-panel">
        <div className="control-panel-head">
          <PanelTitle icon={<Cpu size={18} />} title="Firmware Visibility" />
          <button disabled={context.firmwareCheckStatus === "running"} onClick={() => void context.checkFirmware()} type="button">
            <RefreshCw size={16} />
            {context.firmwareCheckStatus === "running" ? "Checking" : "Check Firmware"}
          </button>
        </div>
        {context.firmware.summaries.length ? (
          <FirmwareVisibilityTable summaries={context.firmware.summaries} />
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
            ["Backend apply", backendApply],
            ["Progress", firmwareProgressLabel(context)],
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
            {supportedActionId
              ? `Backend action ${supportedActionId} is not available in the workflow catalog. Starting upgrade will return a safe TODO result and will not run a provider update.`
              : "Backend upgrade integration is pending for this firmware path. Starting upgrade will return a safe TODO result and will not run a provider update."}
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
    <Page title="Results" subtitle="Latest run and firmware outcomes.">
      <div className="result-stack">
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
    <Page title="Settings" subtitle="Global and advanced defaults.">
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
      <div className="control-actions">
        <button className="primary" onClick={() => void context.saveSettings()} type="button">
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

function FirmwareVisibilityTable({ summaries }: { summaries: FirmwareSummary[] }) {
  return (
    <div className="control-table-wrap">
      <table className="control-table">
        <thead>
          <tr>
            <th>Detected device/model</th>
            <th>Current firmware</th>
            <th>Available firmware</th>
            <th>Build/date</th>
            <th>Bootloader/version</th>
            <th>Hardware revision</th>
            <th>Compatibility</th>
            <th>Last check</th>
            <th>Detection source</th>
          </tr>
        </thead>
        <tbody>
          {summaries.map((summary) => (
            <tr key={summary.device_id}>
              <td>
                <strong>{summary.label}</strong>
                <small>{summary.component_type}</small>
              </td>
              <td>{firmwareCurrentVersion(summary)}</td>
              <td>{displayValue(summary.target_version || firstApprovedVersion(summary))}</td>
              <td>Not reported</td>
              <td>{firmwareBootloaderVersion(summary)}</td>
              <td>Not reported</td>
              <td>
                <StatusPill status={summary.path_status || summary.compliance_status} />
                {summary.blocker && <p>{summary.blocker}</p>}
              </td>
              <td>{summary.last_scanned ? formatDateTime(summary.last_scanned) : "Not checked"}</td>
              <td>
                <strong>{sourceLabel(summary.source_type)}</strong>
                <small>{statusLabel(summary.freshness)}</small>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
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
  if (
    !firmwareValidationMatchesSelection(
      context.latestFirmwareValidation,
      context.selectedPath,
      context.selectedFirmware,
      context.config
    )
  ) {
    return "Validation required for current config and selection";
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
  } else if (
    !firmwareValidationMatchesSelection(
      input.validation,
      input.selectedPath,
      input.selectedFirmware,
      input.config
    )
  ) {
    blockers.push("Validate the current config and selected firmware path before starting an upgrade.");
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

function firmwareProgressLabel(context: ControlCenterContext): string {
  if (context.upgradeStatus === "upgrading") return "Backend request in progress";
  if (!context.latestFirmwareUpgrade) return "Not started";
  if (context.latestFirmwareUpgrade.status === "success") return "Completed";
  if (context.latestFirmwareUpgrade.status === "blocked") return "Blocked before execution";
  if (context.latestFirmwareUpgrade.status === "pending") return "Backend integration pending";
  if (context.latestFirmwareUpgrade.status === "failed") return "Failed";
  return statusLabel(context.latestFirmwareUpgrade.status);
}

function validationStatusLabel(context: ControlCenterContext): string {
  if (!context.latestFirmwareValidation) return "Not validated";
  if (
    !firmwareValidationMatchesSelection(
      context.latestFirmwareValidation,
      context.selectedPath,
      context.selectedFirmware,
      context.config
    )
  ) {
    return "Not validated for current config and selection";
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

function credentialConfigLabel(config: ControlConfig): string {
  if (config.snmpCredentialStatus !== "configured") return "Missing";
  if (!config.snmpCredentialVersion) return "Configured";
  return `Configured for ${snmpVersionLabel(config.snmpCredentialVersion)}`;
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
