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
  Settings as SettingsIcon,
  ShieldCheck,
  SlidersHorizontal,
  TerminalSquare,
  UploadCloud,
  Wrench,
  XCircle
} from "lucide-react";
import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";

import {
  backendAdapter,
  configAdapter,
  createLocalOperationResult,
  defaultCredentialDraft,
  defaultFirmwareRuntimeStatus,
  firmwareAdapter,
  firmwareSelectionAdapter,
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
  FirmwareRuntimeStatus,
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
  { icon: <SettingsIcon size={18} />, label: "Settings", to: "/settings" }
];

type ControlCenterContext = {
  actions: WorkflowAction[];
  auditEvents: AuditEvent[];
  backendLogs: ControlLogEntry[];
  checkFirmware: () => Promise<void>;
  config: ControlConfig;
  configErrors: string[];
  configMessage: string;
  configSaving: boolean;
  connectionStatus: string;
  credentialDraft: CredentialDraft;
  expectedUpgradePhrase: string;
  firmware: FirmwareState;
  firmwareCheckStatus: OperationStatus;
  firmwareRuntime: FirmwareRuntimeStatus;
  firmwareValidationBlockers: string[];
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
  saveConfig: () => Promise<boolean>;
  saveSettings: () => Promise<boolean>;
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
  settingsErrors: string[];
  settingsMessage: string;
  settingsSaving: boolean;
  startFirmwareUpgrade: () => Promise<void>;
  targetSummary: string;
  upgradeConfirmationAccepted: boolean;
  upgradeConfirmationPhrase: string;
  upgradeStatus: UpgradeStatus;
  validateFirmware: () => Promise<void>;
  setUpgradeConfirmationAccepted: (value: boolean) => void;
  setUpgradeConfirmationPhrase: (value: string) => void;
};

export default function ControlCenter() {
  const [health, setHealth] = useState<HealthState | null>(null);
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [actions, setActions] = useState<WorkflowAction[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [backendLogs, setBackendLogs] = useState<ControlLogEntry[]>([]);
  const [firmware, setFirmware] = useState<FirmwareState>({ fileSelections: null, summaries: [] });
  const [firmwareRuntime, setFirmwareRuntime] = useState<FirmwareRuntimeStatus>(defaultFirmwareRuntimeStatus);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [config, setConfig] = useState<ControlConfig>(() => configAdapter.load());
  const [credentialDraft, setCredentialDraft] = useState<CredentialDraft>(defaultCredentialDraft);
  const [configErrors, setConfigErrors] = useState<string[]>([]);
  const [configMessage, setConfigMessage] = useState("");
  const [configSaving, setConfigSaving] = useState(false);

  const [settings, setSettings] = useState<ControlSettings>(() => settingsAdapter.load());
  const [settingsErrors, setSettingsErrors] = useState<string[]>([]);
  const [settingsMessage, setSettingsMessage] = useState("");
  const [settingsSaving, setSettingsSaving] = useState(false);

  const [logs, setLogs] = useState<ControlLogEntry[]>(() => logsAdapter.load());
  const [latestRun, setLatestRun] = useState<OperationResult | null>(() => resultsAdapter.loadRun());
  const [latestFirmwareCheck, setLatestFirmwareCheck] = useState<OperationResult | null>(() =>
    resultsAdapter.loadFirmwareCheck()
  );
  const [latestFirmwareValidation, setLatestFirmwareValidation] = useState<OperationResult | null>(() =>
    resultsAdapter.loadFirmwareValidation()
  );
  const [latestFirmwareUpgrade, setLatestFirmwareUpgrade] = useState<OperationResult | null>(() =>
    resultsAdapter.loadFirmwareUpgrade()
  );

  const [runStatus, setRunStatus] = useState<OperationStatus>(() => latestRun?.status ?? "idle");
  const [runError, setRunError] = useState("");
  const [firmwareCheckStatus, setFirmwareCheckStatus] = useState<OperationStatus>(() => latestFirmwareCheck?.status ?? "idle");
  const [upgradeStatus, setUpgradeStatus] = useState<UpgradeStatus>(() => upgradeStatusFromResult(latestFirmwareUpgrade));
  const [selectedPathId, setSelectedPathIdState] = useState(() => firmwareSelectionAdapter.load()?.selectedPathId ?? "");
  const [selectedFirmware, setSelectedFirmware] = useState(() => firmwareSelectionAdapter.load()?.selectedFirmware ?? "");
  const [upgradeConfirmationAccepted, setUpgradeConfirmationAccepted] = useState(false);
  const [upgradeConfirmationPhraseState, setUpgradeConfirmationPhrase] = useState("");

  const configEditedRef = useRef(false);
  const settingsEditedRef = useRef(false);
  const firmwareSelectionEditedRef = useRef(false);
  const configSaveInFlightRef = useRef(false);
  const settingsSaveInFlightRef = useRef(false);
  const runInFlightRef = useRef(false);
  const firmwareCheckInFlightRef = useRef(false);
  const firmwareGateInFlightRef = useRef(false);

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
  const firmwareValidationBlockers = firmwareValidateBlockers({ config, selectedFirmware, selectedPath });
  const firmwareUpgradeBlockers = firmwareStartBlockers({
    accepted: upgradeConfirmationAccepted,
    config,
    phrase: upgradeConfirmationPhraseState,
    selectedFirmware,
    selectedPath,
    selectedUpgradeAction,
    validation: latestFirmwareValidation
  });

  useEffect(() => {
    void refreshControlCenter();
  }, []);

  useEffect(() => {
    if (firmwareSelectionEditedRef.current || selectedPathId || selectedFirmware.trim()) return;
    const savedSelection = savedFirmwareSelection(firmware, firmwarePaths);
    if (!savedSelection) return;
    setSelectedPathIdState(savedSelection.pathId);
    setSelectedFirmware(savedSelection.selectedFirmware);
    firmwareSelectionAdapter.save({
      selectedFirmware: savedSelection.selectedFirmware,
      selectedPathId: savedSelection.pathId
    });
  }, [firmware, firmwarePaths, selectedFirmware, selectedPathId]);

  useEffect(() => {
    if (!selectedPathId || firmwarePaths.length === 0) return;
    const selectedPathStillExists = firmwarePaths.some((path) => firmwarePathId(path) === selectedPathId);
    if (selectedPathStillExists) return;
    setSelectedPathIdState("");
    setSelectedFirmware("");
    firmwareSelectionAdapter.clear();
    clearFirmwareGateResults();
    setUpgradeConfirmationAccepted(false);
    setUpgradeConfirmationPhrase("");
    setUpgradeStatus("idle");
  }, [firmwarePaths, selectedPathId]);

  async function refreshControlCenter() {
    setLoading(true);
    setLoadError("");
    try {
      const snapshot = await backendAdapter.loadSnapshot();
      setHealth(snapshot.health);
      setProviders(snapshot.providers);
      setActions(snapshot.actions);
      setAuditEvents(snapshot.auditEvents);
      setBackendLogs(snapshot.backendLogs);
      setFirmware(snapshot.firmware);
      setFirmwareRuntime(snapshot.firmwareRuntime);
      if (snapshot.controlConfig && !configEditedRef.current) {
        const backendConfig = configWithSettingsDefaults(
          snapshot.controlConfig,
          snapshot.controlSettings ?? settings
        );
        setConfig((current) =>
          shouldAdoptBackendConfig(current, backendConfig) ? backendConfig : current
        );
      }
      if (snapshot.controlSettings && !settingsEditedRef.current) {
        setSettings((current) =>
          shouldAdoptBackendSettings(current, snapshot.controlSettings!) ? snapshot.controlSettings! : current
        );
      }
    } catch (error) {
      setLoadError(errorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  function addLog(entry: Omit<ControlLogEntry, "id" | "timestamp">) {
    setLogs((current) => logsAdapter.add(current, entry));
    void logsAdapter.persist(entry);
  }

  function updateConfig(value: ControlConfig | ((current: ControlConfig) => ControlConfig)) {
    if (!configEditedRef.current) clearStoredResults();
    configEditedRef.current = true;
    setConfig(value);
    setConfigMessage("");
  }

  function updateCredentialDraft(value: CredentialDraft | ((current: CredentialDraft) => CredentialDraft)) {
    if (!configEditedRef.current) clearStoredResults();
    configEditedRef.current = true;
    setCredentialDraft(value);
    setConfigMessage("");
  }

  function updateSettings(value: ControlSettings | ((current: ControlSettings) => ControlSettings)) {
    settingsEditedRef.current = true;
    setSettings(value);
    setSettingsMessage("");
  }

  async function saveConfig(): Promise<boolean> {
    if (configSaveInFlightRef.current) return false;
    configSaveInFlightRef.current = true;
    setConfigSaving(true);
    try {
      const result = await configAdapter.save(config, credentialDraft);
      setConfig(result.config);
      setConfigErrors(result.errors);
      configEditedRef.current = result.errors.length > 0 || result.savedVia !== "backend";
      setConfigMessage(
        result.errors.length
          ? ""
          : result.savedVia === "backend"
            ? "Configuration saved to backend runtime state"
            : "Configuration saved locally; backend apply is pending"
      );
      if (result.errors.length) {
        addLog({ detail: result.errors.join(" "), message: "Config save failed", status: "blocked", type: "config" });
        return false;
      }
      if (shouldClearResultsForConfig(result.config, [latestRun, latestFirmwareCheck, latestFirmwareValidation, latestFirmwareUpgrade])) {
        clearStoredResults();
      }
      setCredentialDraft(defaultCredentialDraft);
      addLog({
        detail: `${result.config.target}; ${ipModeLabel(result.config.ipMode)}; ${snmpVersionLabel(result.config.snmpVersion)}.`,
        message: "Config saved",
        status: "saved",
        type: "config"
      });
      if (result.savedVia === "backend") await refreshControlCenter();
      return true;
    } finally {
      configSaveInFlightRef.current = false;
      setConfigSaving(false);
    }
  }

  async function saveSettings(): Promise<boolean> {
    if (settingsSaveInFlightRef.current) return false;
    settingsSaveInFlightRef.current = true;
    setSettingsSaving(true);
    try {
      const result = await settingsAdapter.save(settings);
      setSettingsErrors(result.errors);
      settingsEditedRef.current = result.errors.length > 0 || result.savedVia !== "backend";
      if (result.errors.length) {
        setSettingsMessage("");
        addLog({ detail: result.errors.join(" "), message: "Settings change failed", status: "blocked", type: "settings" });
        return false;
      }
      setSettings(result.settings);
      setConfig((current) => configWithSettingsDefaults(current, result.settings));
      setSettingsMessage(
        result.savedVia === "backend"
          ? "Settings saved to backend runtime state"
          : "Settings saved locally; backend apply is pending"
      );
      addLog({
        detail: `Default ${ipModeLabel(result.settings.defaultIpMode)}, ${snmpVersionLabel(result.settings.defaultSnmpVersion)}, timeout ${result.settings.defaultTimeoutSeconds}s.`,
        message: "Settings changed",
        status: "saved",
        type: "settings"
      });
      if (result.savedVia === "backend") await refreshControlCenter();
      return true;
    } finally {
      settingsSaveInFlightRef.current = false;
      setSettingsSaving(false);
    }
  }

  async function syncConfigForAction(): Promise<{
    config: ControlConfig;
    configChanged: boolean;
    errors: string[];
    savedVia: "backend" | "local_fallback";
  }> {
    if (configSaveInFlightRef.current) {
      return {
        config,
        configChanged: false,
        errors: ["Configuration save is already in progress."],
        savedVia: "local_fallback"
      };
    }
    configSaveInFlightRef.current = true;
    setConfigSaving(true);
    const hadPendingConfig = configEditedRef.current || credentialDraftHasValues(credentialDraft);
    try {
      const result = await configAdapter.save(config, credentialDraft);
      setConfig(result.config);
      setConfigErrors(result.errors);
      configEditedRef.current = result.errors.length > 0 || result.savedVia !== "backend";
      if (result.errors.length === 0) setCredentialDraft(defaultCredentialDraft);
      return { ...result, configChanged: hadPendingConfig && result.errors.length === 0 };
    } finally {
      configSaveInFlightRef.current = false;
      setConfigSaving(false);
    }
  }

  async function runSelectedAction() {
    if (runInFlightRef.current || runStatus === "running") return;
    runInFlightRef.current = true;
    try {
      setRunError("");
      setRunStatus("running");
      const syncResult = await syncConfigForAction();
      const currentConfig = syncResult.config;
      if (syncResult.configChanged) clearStoredResults();
      if (syncResult.errors.length > 0 || syncResult.savedVia !== "backend") {
        const result = createLocalOperationResult({
          blockers: syncResult.errors.length
            ? syncResult.errors
            : ["Current config could not be saved to backend runtime state before Run."],
          message: syncResult.errors.length
            ? "Run blocked until the current configuration is valid."
            : "Run blocked so the backend cannot use stale configuration.",
          raw: { config_snapshot: configSnapshot(currentConfig) },
          status: "blocked",
          title: "Run blocked",
          type: "run"
        });
        setLatestRun(result);
        resultsAdapter.saveRun(result);
        setRunStatus("blocked");
        setRunError(result.message);
        addLog({ detail: result.blockers.join(" "), message: "Run blocked", status: "blocked", type: "run" });
        return;
      }

      addLog({
        detail: `${selectedAction?.label ?? "Safe placeholder"} for ${currentConfig.target}.`,
        message: "Run started",
        status: "running",
        type: "run"
      });

      try {
        const result = await runAdapter.run(currentConfig, selectedAction);
        setLatestRun(result);
        resultsAdapter.saveRun(result);
        setRunStatus(result.status);
        setRunError(["failed", "blocked"].includes(result.status) ? result.message : "");
        addLog({ detail: result.message, message: operationLogMessage("Run", result.status), status: result.status, type: "run" });
        await refreshControlCenter();
      } catch (error) {
        const message = errorMessage(error);
        const result = createLocalOperationResult({
          blockers: [message],
          message,
          raw: { config_snapshot: configSnapshot(currentConfig) },
          status: "failed",
          title: "Run failed",
          type: "run"
        });
        setLatestRun(result);
        resultsAdapter.saveRun(result);
        setRunStatus("failed");
        setRunError(message);
        addLog({ detail: message, message: "Run failed", status: "failed", type: "run" });
      }
    } finally {
      runInFlightRef.current = false;
    }
  }

  async function checkFirmware() {
    if (firmwareCheckInFlightRef.current || firmwareCheckStatus === "running") return;
    firmwareCheckInFlightRef.current = true;
    try {
      setFirmwareCheckStatus("running");
      const syncResult = await syncConfigForAction();
      const currentConfig = syncResult.config;
      if (syncResult.configChanged) clearStoredResults();
      if (syncResult.errors.length > 0 || syncResult.savedVia !== "backend") {
        const result = createLocalOperationResult({
          blockers: syncResult.errors.length
            ? syncResult.errors
            : ["Current config could not be saved to backend runtime state before Firmware Check."],
          message: syncResult.errors.length
            ? "Firmware check blocked until the current configuration is valid."
            : "Firmware check blocked so the backend cannot use stale configuration.",
          raw: { config_snapshot: configSnapshot(currentConfig) },
          status: "blocked",
          title: "Firmware check blocked",
          type: "firmware-check"
        });
        setLatestFirmwareCheck(result);
        resultsAdapter.saveFirmwareCheck(result);
        setFirmwareCheckStatus("blocked");
        addLog({ detail: result.blockers.join(" "), message: "Firmware check blocked", status: "blocked", type: "firmware" });
        return;
      }

      addLog({
        detail: `Firmware visibility check started for ${currentConfig.target}. No upgrade action is triggered.`,
        message: "Firmware check started",
        status: "running",
        type: "firmware"
      });

      try {
        const response = await firmwareAdapter.check(currentConfig);
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
        await refreshControlCenter();
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
        addLog({ detail: message, message: "Firmware check failed", status: "failed", type: "firmware" });
      }
    } finally {
      firmwareCheckInFlightRef.current = false;
    }
  }

  async function validateFirmware() {
    if (firmwareGateInFlightRef.current || upgradeStatus === "validating" || upgradeStatus === "upgrading") return;
    firmwareGateInFlightRef.current = true;
    try {
      clearFirmwareGateResults();
      const preflightBlockers = firmwareValidateBlockers({ config, selectedFirmware, selectedPath });
      if (preflightBlockers.length > 0) {
        const result = createLocalOperationResult({
          blockers: preflightBlockers,
          message: "Firmware validation blocked until the current config and firmware selection are complete.",
          raw: firmwareSelectionSnapshot(config, selectedPath, selectedFirmware),
          status: "blocked",
          title: "Firmware validation blocked",
          type: "firmware-validation"
        });
        setLatestFirmwareValidation(result);
        resultsAdapter.saveFirmwareValidation(result);
        setUpgradeStatus("blocked");
        addLog({ detail: result.blockers.join(" "), message: "Firmware validation blocked", status: "blocked", type: "firmware" });
        return;
      }

      setUpgradeStatus("validating");
      const syncResult = await syncConfigForAction();
      const currentConfig = syncResult.config;
      if (syncResult.configChanged) clearStoredResults();
      if (syncResult.errors.length > 0 || syncResult.savedVia !== "backend") {
        const result = createLocalOperationResult({
          blockers: syncResult.errors.length
            ? syncResult.errors
            : ["Current config could not be saved to backend runtime state before Firmware Validate."],
          message: syncResult.errors.length
            ? "Firmware validation blocked until the current configuration is valid."
            : "Firmware validation blocked so the backend cannot use stale configuration.",
          raw: firmwareSelectionSnapshot(currentConfig, selectedPath, selectedFirmware),
          status: "blocked",
          title: "Firmware validation blocked",
          type: "firmware-validation"
        });
        setLatestFirmwareValidation(result);
        resultsAdapter.saveFirmwareValidation(result);
        setUpgradeStatus("blocked");
        addLog({ detail: result.blockers.join(" "), message: "Firmware validation blocked", status: "blocked", type: "firmware" });
        return;
      }

      addLog({
        detail: selectedPath ? firmwarePathLabel(selectedPath) : "No firmware path selected.",
        message: "Firmware validation started",
        status: "running",
        type: "firmware"
      });

      try {
        const response = await firmwareAdapter.validate({ config: currentConfig, selectedFirmware, selectedPath });
        setFirmware(response.firmware);
        setLatestFirmwareValidation(response.result);
        resultsAdapter.saveFirmwareValidation(response.result);
        setUpgradeStatus(firmwareValidationPassed(response.result) ? "ready" : response.result.status === "blocked" ? "blocked" : "failed");
        addLog({
          detail: response.result.message,
          message: operationLogMessage("Firmware validation", response.result.status),
          status: response.result.status,
          type: "firmware"
        });
        await refreshControlCenter();
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
        addLog({ detail: message, message: "Firmware validation failed", status: "failed", type: "firmware" });
      }
    } finally {
      firmwareGateInFlightRef.current = false;
    }
  }

  async function startFirmwareUpgrade() {
    if (firmwareGateInFlightRef.current || upgradeStatus === "upgrading" || upgradeStatus === "validating") return;
    firmwareGateInFlightRef.current = true;
    try {
      const preflightBlockers = firmwareStartBlockers({
        accepted: upgradeConfirmationAccepted,
        config,
        phrase: upgradeConfirmationPhraseState,
        selectedFirmware,
        selectedPath,
        selectedUpgradeAction,
        validation: latestFirmwareValidation
      });
      if (preflightBlockers.length > 0) {
        const result = createLocalOperationResult({
          blockers: preflightBlockers,
          message: "Firmware upgrade was not started.",
          raw: firmwareSelectionSnapshot(config, selectedPath, selectedFirmware),
          status: "blocked",
          title: "Firmware upgrade blocked",
          type: "firmware-upgrade"
        });
        setLatestFirmwareUpgrade(result);
        resultsAdapter.saveFirmwareUpgrade(result);
        setUpgradeStatus("blocked");
        addLog({ detail: preflightBlockers.join(" "), message: "Firmware upgrade blocked", status: "blocked", type: "firmware" });
        return;
      }

      const syncResult = await syncConfigForAction();
      const currentConfig = syncResult.config;
      if (syncResult.configChanged) clearStoredResults();
      const validationForUpgrade = syncResult.configChanged ? null : latestFirmwareValidation;
      const confirmationAcceptedForUpgrade = syncResult.configChanged ? false : upgradeConfirmationAccepted;
      const confirmationPhraseForUpgrade = syncResult.configChanged ? "" : upgradeConfirmationPhraseState;
      const currentBlockers =
        syncResult.errors.length > 0
          ? syncResult.errors
          : syncResult.savedVia === "backend"
            ? firmwareStartBlockers({
                accepted: confirmationAcceptedForUpgrade,
                config: currentConfig,
                phrase: confirmationPhraseForUpgrade,
                selectedFirmware,
                selectedPath,
                selectedUpgradeAction,
                validation: validationForUpgrade
              })
            : ["Current config could not be saved to backend runtime state before Firmware Upgrade."];

      if (currentBlockers.length > 0) {
        const result = createLocalOperationResult({
          blockers: currentBlockers,
          message: "Firmware upgrade was not started.",
          raw: firmwareSelectionSnapshot(currentConfig, selectedPath, selectedFirmware),
          status: "blocked",
          title: "Firmware upgrade blocked",
          type: "firmware-upgrade"
        });
        setLatestFirmwareUpgrade(result);
        resultsAdapter.saveFirmwareUpgrade(result);
        setUpgradeStatus("blocked");
        addLog({ detail: currentBlockers.join(" "), message: "Firmware upgrade blocked", status: "blocked", type: "firmware" });
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
          confirmationAccepted: confirmationAcceptedForUpgrade,
          confirmationPhrase: confirmationPhraseForUpgrade,
          selectedFirmware,
          selectedPath,
          validationResult: validationForUpgrade
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
        addLog({ detail: message, message: "Firmware upgrade failed", status: "failed", type: "firmware" });
      }
    } finally {
      firmwareGateInFlightRef.current = false;
    }
  }

  function setSelectedPathId(value: string) {
    firmwareSelectionEditedRef.current = true;
    setSelectedPathIdState(value);
    const path = firmwarePaths.find((candidate) => firmwarePathId(candidate) === value) ?? null;
    const nextFirmware = defaultFirmwareSelection(path);
    setSelectedFirmware(nextFirmware);
    if (value) {
      firmwareSelectionAdapter.save({ selectedFirmware: nextFirmware, selectedPathId: value });
    } else {
      firmwareSelectionAdapter.clear();
    }
    clearFirmwareGateResults();
    setUpgradeConfirmationAccepted(false);
    setUpgradeConfirmationPhrase("");
    setUpgradeStatus("idle");
  }

  function updateSelectedFirmware(value: string) {
    firmwareSelectionEditedRef.current = true;
    setSelectedFirmware(value);
    if (selectedPathId) {
      firmwareSelectionAdapter.save({ selectedFirmware: value, selectedPathId });
    }
    clearFirmwareGateResults();
    setUpgradeConfirmationAccepted(false);
    setUpgradeConfirmationPhrase("");
    if (upgradeStatus !== "upgrading") setUpgradeStatus("idle");
  }

  function updateUpgradeConfirmationAccepted(value: boolean) {
    setUpgradeConfirmationAccepted(value);
    updateUpgradeDraftStatus(value, upgradeConfirmationPhraseState);
  }

  function updateUpgradeConfirmationPhrase(value: string) {
    setUpgradeConfirmationPhrase(value);
    updateUpgradeDraftStatus(upgradeConfirmationAccepted, value);
  }

  function updateUpgradeDraftStatus(accepted: boolean, phrase: string) {
    if (upgradeStatus === "validating" || upgradeStatus === "upgrading") return;
    if (!latestFirmwareValidation) {
      setUpgradeStatus("idle");
      return;
    }
    const blockers = firmwareStartBlockers({
      accepted,
      config,
      phrase,
      selectedFirmware,
      selectedPath,
      selectedUpgradeAction,
      validation: latestFirmwareValidation
    });
    if (blockers.length === 0) {
      setUpgradeStatus("ready");
      return;
    }
    if (firmwareValidationMatchesSelection(latestFirmwareValidation, selectedPath, selectedFirmware, config)) {
      setUpgradeStatus("blocked");
    } else {
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
    backendLogs,
    checkFirmware,
    config,
    configErrors,
    configMessage,
    configSaving,
    connectionStatus,
    credentialDraft,
    expectedUpgradePhrase,
    firmware,
    firmwareCheckStatus,
    firmwareRuntime,
    firmwareValidationBlockers,
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
    setConfig: updateConfig,
    setCredentialDraft: updateCredentialDraft,
    setSelectedFirmware: updateSelectedFirmware,
    setSelectedPathId,
    setSettings: updateSettings,
    settings,
    settingsErrors,
    settingsMessage,
    settingsSaving,
    startFirmwareUpgrade,
    targetSummary,
    upgradeConfirmationAccepted,
    upgradeConfirmationPhrase: upgradeConfirmationPhraseState,
    upgradeStatus,
    validateFirmware,
    setUpgradeConfirmationAccepted: updateUpgradeConfirmationAccepted,
    setUpgradeConfirmationPhrase: updateUpgradeConfirmationPhrase
  };

  return (
    <div className="cc-shell">
      <aside className="cc-sidebar control-sidebar" aria-label="Main navigation">
        <Link className="cc-brand" to="/dashboard">
          <Wrench size={22} />
          <span>
            WebUIs Control Center
            <small>Configure. Run. Review.</small>
          </span>
        </Link>
        <nav className="cc-nav control-nav">
          {navItems.map((item) => (
            <NavLink className="cc-nav-link control-nav-link" key={item.to} to={item.to}>
              {item.icon}
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="cc-sidebar-status">
          <span>Current target</span>
          <strong>{targetSummary}</strong>
          <small>{context.connectionStatus}</small>
        </div>
      </aside>

      <main className="cc-main">
        <TopBar context={context} />
        {loadError && <Banner tone="bad">{loadError}</Banner>}
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
          <Route path="/control-center/*" element={<LegacyControlCenterRedirect />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </main>
    </div>
  );
}

function LegacyControlCenterRedirect() {
  const location = useLocation();
  const target = routeTargetFromLegacyPath(location.pathname, location.search);
  return <Navigate to={target} replace />;
}

function TopBar({ context }: { context: ControlCenterContext }) {
  const location = useLocation();
  const activePage = navItems.find((item) => location.pathname.startsWith(item.to))?.label ?? "Dashboard";
  return (
    <header className="cc-topbar">
      <div>
        <p>WebUIs Control Center</p>
        <h1>{activePage}</h1>
      </div>
      <div className="cc-status-strip" aria-label="Control Center status">
        <StatusTile label="Target" value={context.targetSummary} />
        <StatusTile label="API" value={context.connectionStatus} />
        <StatusTile label="Run" value={resultStatusLabel(context.latestRun, context.runStatus)} />
        <StatusTile label="Firmware" value={firmwareStatusLabel(context)} />
      </div>
    </header>
  );
}

function DashboardPage({ context }: { context: ControlCenterContext }) {
  const firmwareUpgrade = firmwareUpgradeSummaryResult(context);
  return (
    <Page title="Dashboard">
      <section className="cc-panel cc-dashboard">
        <div>
          <SectionTitle icon={<Gauge size={18} />} title="Control Overview" />
          <FactList
            facts={[
              ["Current target", context.targetSummary],
              ["API / connection", context.connectionStatus],
              ["IP mode", ipModeLabel(context.config.ipMode)],
              ["SNMP version", snmpVersionLabel(context.config.snmpVersion)],
              ["Device / target detection", providerDetectionText(context.providers)],
              ["Detected firmware", firmwareSummaryText(context.firmware.summaries)],
              ["Last run", resultStatusLabel(context.latestRun, context.runStatus)],
              ["Last firmware check", context.latestFirmwareCheck ? statusLabel(context.latestFirmwareCheck.status) : "Not checked"],
              ["Last firmware upgrade", firmwareUpgrade ? statusLabel(firmwareUpgrade.status) : "No upgrade attempt"]
            ]}
          />
        </div>
        <div className="cc-quick-links control-next-actions" aria-label="Primary workflow shortcuts">
          <WorkflowLink icon={<SlidersHorizontal size={18} />} label="Configure" text={context.config.target || "Set target and SNMP"} to="/configure" />
          <WorkflowLink icon={<Play size={18} />} label="Run" text={context.selectedAction?.label ?? "Backend run pending"} to="/run" />
          <WorkflowLink icon={<UploadCloud size={18} />} label="Firmware" text={firmwareStatusLabel(context)} to="/firmware" />
        </div>
      </section>

      <section className="cc-panel">
        <SectionTitle icon={<Activity size={18} />} title="Primary Workflow" />
        <ol className="cc-workflow-rail" aria-label="Primary workflow">
          <WorkflowStep label="Configure" state={context.config.target ? "Ready" : "Missing target"} to="/configure" />
          <WorkflowStep label="Run" state={resultStatusLabel(context.latestRun, context.runStatus)} to="/run" />
          <WorkflowStep label="Results" state={context.latestRun || context.latestFirmwareCheck ? "Updated" : "Empty"} to="/results" />
          <WorkflowStep label="Logs" state={combinedLogs(context).length ? "Activity recorded" : "No activity"} to="/logs" />
        </ol>
      </section>

      <section className="cc-panel">
        <SectionTitle icon={<History size={18} />} title="Recent Activity" />
        <ActivityList logs={combinedLogs(context).slice(0, 6)} />
      </section>
    </Page>
  );
}

function ConfigurePage({ context }: { context: ControlCenterContext }) {
  return (
    <Page title="Configure">
      <section className="cc-panel">
        <SectionTitle icon={<SlidersHorizontal size={18} />} title="Target and SNMP" />
        <div className="cc-form-grid">
          <label className="cc-field cc-span-2">
            <span>Target host, IP, or range</span>
            <input
              onChange={(event) => context.setConfig((current) => ({ ...current, target: event.target.value }))}
              placeholder="192.0.2.203 or 192.0.2.0/24"
              type="text"
              value={context.config.target}
            />
          </label>
          <SegmentedControl
            label="IP mode"
            onChange={(value) => context.setConfig((current) => ({ ...current, ipMode: value as ControlConfig["ipMode"] }))}
            options={[
              ["ipv4", "IPv4"],
              ["ipv6", "IPv6"],
              ["both", "Both"]
            ]}
            value={context.config.ipMode}
          />
          <SegmentedControl
            label="SNMP version"
            onChange={(value) => context.setConfig((current) => ({ ...current, snmpVersion: value as ControlConfig["snmpVersion"] }))}
            options={[
              ["v2", "SNMPv2"],
              ["v3", "SNMPv3"]
            ]}
            value={context.config.snmpVersion}
          />
        </div>

        {context.config.snmpVersion === "v2" ? (
          <label className="cc-field">
            <span>SNMPv2 community</span>
            <input
              autoComplete="off"
              onChange={(event) => context.setCredentialDraft((current) => ({ ...current, snmpV2Community: event.target.value }))}
              placeholder="Presence is saved; value is not stored"
              type="password"
              value={context.credentialDraft.snmpV2Community}
            />
          </label>
        ) : (
          <div className="cc-form-grid">
            <label className="cc-field">
              <span>SNMPv3 username</span>
              <input
                autoComplete="off"
                onChange={(event) => context.setCredentialDraft((current) => ({ ...current, snmpV3Username: event.target.value }))}
                type="text"
                value={context.credentialDraft.snmpV3Username}
              />
            </label>
            <label className="cc-field">
              <span>SNMPv3 auth password</span>
              <input
                autoComplete="off"
                onChange={(event) => context.setCredentialDraft((current) => ({ ...current, snmpV3AuthPassword: event.target.value }))}
                type="password"
                value={context.credentialDraft.snmpV3AuthPassword}
              />
            </label>
            <label className="cc-field">
              <span>SNMPv3 privacy password</span>
              <input
                autoComplete="off"
                onChange={(event) => context.setCredentialDraft((current) => ({ ...current, snmpV3PrivacyPassword: event.target.value }))}
                type="password"
                value={context.credentialDraft.snmpV3PrivacyPassword}
              />
            </label>
          </div>
        )}

        <FactList
          facts={[
            ["Credential state", credentialConfigLabel(context.config)],
            ["Config adapter", configAdapter.backendStatus],
            ["Last saved", context.config.updatedAt ? formatDateTime(context.config.updatedAt) : "Not saved"]
          ]}
        />
      </section>

      <details className="cc-panel cc-details">
        <summary>Advanced</summary>
        <div className="cc-form-grid">
          <label className="cc-field">
            <span>Timeout seconds</span>
            <input
              max={120}
              min={1}
              onChange={(event) => context.setConfig((current) => ({ ...current, timeoutSeconds: Number(event.target.value) }))}
              type="number"
              value={context.config.timeoutSeconds}
            />
          </label>
          <label className="cc-field">
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
        <FactList facts={[["Provider mode", context.health?.provider_mode ?? "Unknown"]]} />
      </details>

      {context.configErrors.length > 0 && <IssueList title="Validation errors" items={context.configErrors} />}
      <ActionRow>
        <button className="primary" disabled={context.configSaving} onClick={() => void context.saveConfig()} type="button">
          <Save size={16} />
          {context.configSaving ? "Saving config" : "Save / apply config"}
        </button>
      </ActionRow>
      {context.configMessage && <Banner tone="good">{context.configMessage}</Banner>}
    </Page>
  );
}

function RunPage({ context }: { context: ControlCenterContext }) {
  const running = context.runStatus === "running";
  const runDisabled = running || context.configSaving;
  return (
    <Page title="Run">
      <section className="cc-panel cc-run-panel">
        <div>
          <SectionTitle icon={<Play size={18} />} title="Current Config" />
          <FactList
            facts={[
              ["Target", context.config.target || "Not configured"],
              ["IP mode", ipModeLabel(context.config.ipMode)],
              ["SNMP", snmpVersionLabel(context.config.snmpVersion)],
              ["Credentials", credentialConfigLabel(context.config)],
              ["Timeout / retry", `${context.config.timeoutSeconds}s / ${context.config.retryCount}`],
              ["Backend action", context.selectedAction?.label ?? "Safe placeholder"],
              ["Action source", context.selectedAction?.source_type ?? "todo_placeholder"]
            ]}
          />
        </div>
        <button className="cc-big-run primary" disabled={runDisabled} onClick={() => void context.runSelectedAction()} type="button">
          <Play size={20} />
          {running ? "Running" : context.configSaving ? "Saving config" : "Run"}
        </button>
      </section>

      {!context.selectedAction && <Banner tone="warn">Backend run integration is pending. The placeholder does not contact providers.</Banner>}
      {context.runError && <Banner tone="bad">{context.runError}</Banner>}

      <section className="cc-panel">
        <SectionTitle icon={<FileText size={18} />} title="Latest Result Preview" />
        {running ? <LoadingState text="Running selected action" /> : context.latestRun ? <ResultDetails compact result={context.latestRun} /> : <EmptyState title="No result yet" detail="Run uses the current config snapshot." />}
      </section>

      <section className="cc-panel">
        <SectionTitle icon={<History size={18} />} title="Run Activity" />
        <ActivityList logs={runEventLogs(context)} />
      </section>
    </Page>
  );
}

function FirmwarePage({ context }: { context: ControlCenterContext }) {
  return (
    <Page title="Firmware">
      <FirmwareVisibilitySection context={context} />
      <FirmwareUpgradeSection context={context} />
      <section className="cc-panel">
        <SectionTitle icon={<History size={18} />} title="Firmware Events" />
        <ActivityList logs={firmwareEventLogs(context)} />
      </section>
    </Page>
  );
}

function FirmwareVisibilitySection({ context }: { context: ControlCenterContext }) {
  const checkRunning = context.firmwareCheckStatus === "running";
  const checkDisabled = checkRunning || context.configSaving;
  return (
    <section className="cc-panel">
      <div className="cc-panel-head">
        <SectionTitle icon={<Cpu size={18} />} title="Firmware Visibility" />
        <button disabled={checkDisabled} onClick={() => void context.checkFirmware()} type="button">
          <RefreshCw size={16} />
          {checkRunning ? "Checking" : context.configSaving ? "Saving config" : "Check Firmware"}
        </button>
      </div>
      {context.firmware.summaries.length ? (
        <div className="cc-firmware-list">
          {context.firmware.summaries.map((summary) => (
            <FirmwareVisibilityRow key={summary.device_id} summary={summary} />
          ))}
        </div>
      ) : (
        <FirmwareVisibilityEmpty />
      )}
    </section>
  );
}

function FirmwareUpgradeSection({ context }: { context: ControlCenterContext }) {
  const firmwarePaths = collectFirmwarePaths(context.firmware.summaries);
  const supportedActionId = supportedUpgradeActionId(context.selectedPath);
  const backendPending = Boolean(context.selectedPath && (!supportedActionId || !context.selectedUpgradeAction));
  const validateDisabled =
    context.configSaving ||
    context.upgradeStatus === "validating" ||
    context.upgradeStatus === "upgrading" ||
    !context.selectedPath ||
    !context.selectedFirmware.trim();
  const startDisabled =
    context.configSaving ||
    context.firmwareUpgradeBlockers.length > 0 ||
    context.upgradeStatus === "upgrading" ||
    context.upgradeStatus === "validating";

  return (
    <section className="cc-panel">
      <div className="cc-panel-head">
        <SectionTitle icon={<UploadCloud size={18} />} title="Firmware Upgrade" />
        <StatusPill status={context.upgradeStatus} />
      </div>

      <FactList
        facts={[
          ["Target", context.targetSummary],
          ["Current firmware", context.selectedPath ? displayValue(context.selectedPath.current_version) : "Select firmware path"],
          ["Selected firmware/image/version", context.selectedFirmware || "Missing"],
          ["Compatibility check", validationStatusLabel(context)],
          ["Readiness status", firmwareReadinessLabel(context)],
          ["Progress", firmwareProgressLabel(context)],
          ["Backend status/progress", context.firmwareRuntime.message],
          ["Next safe action", context.firmwareRuntime.nextSafeAction],
          ["Backend action", context.selectedUpgradeAction?.label ?? (context.selectedPath ? "Integration pending" : "Select firmware path")],
          ["Backend gates", firmwareBackendGateLabel(context)],
          ["Status source", firmwareRuntimeSourceLabel(context.firmwareRuntime)]
        ]}
      />
      {context.firmwareRuntime.blockers.length > 0 && (
        <IssueList title="Backend firmware status blockers" items={context.firmwareRuntime.blockers} />
      )}
      {context.firmwareRuntime.warnings.length > 0 && (
        <IssueList title="Backend firmware status warnings" items={context.firmwareRuntime.warnings} tone="warn" />
      )}

      <FirmwareStateRail status={context.upgradeStatus} />

      <div className="cc-form-grid">
        <label className="cc-field cc-span-2">
          <span>Firmware path</span>
          <select onChange={(event) => context.setSelectedPathId(event.target.value)} value={context.selectedPathId}>
            <option value="">Select firmware path</option>
            {firmwarePaths.map((path) => (
              <option key={firmwarePathId(path)} value={firmwarePathId(path)}>
                {firmwarePathLabel(path)}
              </option>
            ))}
          </select>
        </label>
        <label className="cc-field cc-span-2">
          <span>Selected firmware, image, or version</span>
          <input
            list="firmware-candidates"
            onChange={(event) => context.setSelectedFirmware(event.target.value)}
            placeholder="Select a path or enter a target firmware/image reference"
            type="text"
            value={context.selectedFirmware}
          />
          <datalist id="firmware-candidates">
            {firmwareCandidateOptions(context.selectedPath).map((candidate) => (
              <option key={candidate} value={candidate} />
            ))}
          </datalist>
        </label>
      </div>

      {!firmwarePaths.length && <Banner tone="warn">Firmware summary backend has not exposed upgrade paths yet.</Banner>}
      {backendPending && <Banner tone="warn">Upgrade backend integration is pending for this selected firmware path.</Banner>}
      {context.selectedPath && <FirmwarePathSummary path={context.selectedPath} />}

      <ActionRow>
        <button disabled={validateDisabled} onClick={() => void context.validateFirmware()} type="button">
          <ShieldCheck size={16} />
          {context.upgradeStatus === "validating" ? "Validating" : context.configSaving ? "Saving config" : "Validate Firmware"}
        </button>
      </ActionRow>
      {context.firmwareValidationBlockers.length > 0 && <IssueList title="Validation blockers" items={context.firmwareValidationBlockers} />}

      <div className="cc-confirm-box">
        <div>
          <strong>Confirmation Required</strong>
          <p>Start Firmware Upgrade stays blocked until validation matches the current config, firmware selection, confirmation phrase, and backend gates.</p>
        </div>
        <label className="cc-check-field">
          <input
            aria-label="Require explicit operator confirmation before any firmware upgrade request is sent."
            checked={context.upgradeConfirmationAccepted}
            onChange={(event) => context.setUpgradeConfirmationAccepted(event.target.checked)}
            type="checkbox"
          />
          <span>I confirm this firmware upgrade request is intentional and the listed backend gates are satisfied.</span>
        </label>
        <p>
          Required phrase: <code>{context.expectedUpgradePhrase}</code>
        </p>
        <label className="cc-field">
          <span>Confirmation phrase</span>
          <input
            onChange={(event) => context.setUpgradeConfirmationPhrase(event.target.value)}
            placeholder={context.expectedUpgradePhrase}
            type="text"
            value={context.upgradeConfirmationPhrase}
          />
        </label>
        {context.firmwareUpgradeBlockers.length > 0 && <IssueList title="Upgrade blockers" items={context.firmwareUpgradeBlockers} />}
        <button className="primary danger-action" disabled={startDisabled} onClick={() => void context.startFirmwareUpgrade()} type="button">
          <UploadCloud size={16} />
          {context.upgradeStatus === "upgrading" ? "Upgrade Running" : context.configSaving ? "Saving config" : "Start Firmware Upgrade"}
        </button>
      </div>
    </section>
  );
}

function ResultsPage({ context }: { context: ControlCenterContext }) {
  const latestFirmwareUpgrade = firmwareUpgradeSummaryResult(context);
  return (
    <Page title="Results">
      <section className="cc-panel">
        <SectionTitle icon={<Play size={18} />} title="Latest Run Result" />
        {context.latestRun ? <ResultDetails result={context.latestRun} /> : <EmptyState title="No run result" detail="Run an action to populate this panel." />}
      </section>
      <section className="cc-panel">
        <SectionTitle icon={<ShieldCheck size={18} />} title="Latest Firmware Check Summary" />
        {context.latestFirmwareCheck ? <ResultDetails result={context.latestFirmwareCheck} /> : <EmptyState title="No firmware check" detail="Use Check Firmware on the Firmware page." />}
      </section>
      <section className="cc-panel">
        <SectionTitle icon={<ShieldCheck size={18} />} title="Latest Firmware Validation Summary" />
        {context.latestFirmwareValidation ? <ResultDetails result={context.latestFirmwareValidation} /> : <EmptyState title="No firmware validation" detail="Validate a selected firmware path before upgrade." />}
      </section>
      <section className="cc-panel">
        <SectionTitle icon={<UploadCloud size={18} />} title="Latest Firmware Upgrade Summary" />
        {latestFirmwareUpgrade ? <ResultDetails result={latestFirmwareUpgrade} /> : <EmptyState title="No firmware upgrade" detail="Upgrade attempts appear here after confirmation." />}
      </section>
    </Page>
  );
}

function LogsPage({ context }: { context: ControlCenterContext }) {
  return (
    <Page title="Logs">
      <section className="cc-panel">
        <SectionTitle icon={<History size={18} />} title="Activity Timeline" />
        <ActivityList logs={allLogSources(context)} />
      </section>
    </Page>
  );
}

function SettingsPage({ context }: { context: ControlCenterContext }) {
  return (
    <Page title="Settings">
      <section className="cc-panel">
        <SectionTitle icon={<SettingsIcon size={18} />} title="Global Defaults" />
        <div className="cc-form-grid">
          <label className="cc-field">
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
          <label className="cc-field">
            <span>Default SNMP version</span>
            <select
              onChange={(event) => context.setSettings((current) => ({ ...current, defaultSnmpVersion: event.target.value as ControlSettings["defaultSnmpVersion"] }))}
              value={context.settings.defaultSnmpVersion}
            >
              <option value="v2">SNMPv2</option>
              <option value="v3">SNMPv3</option>
            </select>
          </label>
          <label className="cc-field">
            <span>Timeout default</span>
            <input
              max={120}
              min={1}
              onChange={(event) => context.setSettings((current) => ({ ...current, defaultTimeoutSeconds: Number(event.target.value) }))}
              type="number"
              value={context.settings.defaultTimeoutSeconds}
            />
          </label>
          <label className="cc-field">
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
      <section className="cc-panel">
        <SectionTitle icon={<TerminalSquare size={18} />} title="Advanced Settings" />
        <div className="cc-form-grid">
          <label className="cc-field cc-span-2">
            <span>API/server URL</span>
            <input
              onChange={(event) => context.setSettings((current) => ({ ...current, apiBaseUrl: event.target.value }))}
              type="text"
              value={context.settings.apiBaseUrl}
            />
          </label>
          <label className="cc-field cc-span-2">
            <span>Firmware repository/source</span>
            <input
              onChange={(event) => context.setSettings((current) => ({ ...current, firmwareRepository: event.target.value }))}
              type="text"
              value={context.settings.firmwareRepository}
            />
          </label>
          <label className="cc-field">
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
      <ActionRow>
        <button className="primary" disabled={context.settingsSaving} onClick={() => void context.saveSettings()} type="button">
          <Save size={16} />
          {context.settingsSaving ? "Saving settings" : "Save settings"}
        </button>
      </ActionRow>
      {context.settingsErrors.length > 0 && <IssueList title="Settings validation errors" items={context.settingsErrors} />}
      {context.settingsMessage && <Banner tone="good">{context.settingsMessage}</Banner>}
    </Page>
  );
}

function Page({ children, title }: { children: ReactNode; title: string }) {
  return (
    <div aria-label={title} className="cc-page">
      {children}
    </div>
  );
}

function SectionTitle({ icon, title }: { icon?: ReactNode; title: string }) {
  return (
    <h2 className="cc-section-title">
      {icon}
      {title}
    </h2>
  );
}

function StatusTile({ label, value }: { label: string; value: string }) {
  return (
    <div className={`cc-status-tile ${toneClass(value)}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  return <span className={`cc-pill ${toneClass(status)}`}>{statusLabel(status)}</span>;
}

function FactList({ facts }: { facts: Array<[string, string]> }) {
  return (
    <dl className="cc-facts">
      {facts.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function SegmentedControl({
  label,
  onChange,
  options,
  value
}: {
  label: string;
  onChange: (value: string) => void;
  options: Array<[string, string]>;
  value: string;
}) {
  return (
    <div className="cc-field">
      <span>{label}</span>
      <div className="cc-segmented" role="group" aria-label={label}>
        {options.map(([optionValue, optionLabel]) => (
          <button
            aria-pressed={value === optionValue}
            className={value === optionValue ? "is-selected" : ""}
            key={optionValue}
            onClick={() => onChange(optionValue)}
            type="button"
          >
            {optionLabel}
          </button>
        ))}
      </div>
    </div>
  );
}

function WorkflowLink({ icon, label, text, to }: { icon: ReactNode; label: string; text: string; to: string }) {
  return (
    <Link className="cc-workflow-link" to={to}>
      {icon}
      <strong>{label}</strong>
      <span>{text}</span>
    </Link>
  );
}

function WorkflowStep({ label, state, to }: { label: string; state: string; to: string }) {
  return (
    <li>
      <Link to={to}>
        <strong>{label}</strong>
        <span>{state}</span>
      </Link>
    </li>
  );
}

function ActionRow({ children }: { children: ReactNode }) {
  return <div className="cc-actions">{children}</div>;
}

function Banner({ children, tone }: { children: ReactNode; tone: "good" | "warn" | "bad" | "info" }) {
  return <div className={`cc-banner is-${tone}`}>{children}</div>;
}

function IssueList({ items, title, tone = "bad" }: { items: string[]; title: string; tone?: "bad" | "warn" }) {
  if (!items.length) return null;
  return (
    <div className={`cc-issues is-${tone}`}>
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
  const visible = uniqueLogs(logs)
    .sort((first, second) => Date.parse(second.timestamp) - Date.parse(first.timestamp))
    .slice(0, 80);
  if (!visible.length) return <EmptyState title="No logs yet" detail="Major config, run, firmware, and settings events appear here." />;
  return (
    <ol className="cc-activity">
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
    <div className="cc-empty">
      <TerminalSquare size={22} />
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  );
}

function LoadingState({ text }: { text: string }) {
  return (
    <div className="cc-loading">
      <RefreshCw size={18} />
      {text}
    </div>
  );
}

function FirmwareVisibilityRow({ summary }: { summary: FirmwareSummary }) {
  const facts: Array<[string, string]> = [
    ["Detected device/model", `${summary.label} / ${summary.component_type}`],
    ["Current firmware version", firmwareCurrentVersion(summary)],
    ["Available firmware version", displayValue(summary.target_version || firstApprovedVersion(summary))],
    ["Build/date", firmwareBuildDate(summary)],
    ["Bootloader/version", firmwareBootloaderVersion(summary)],
    ["Hardware revision", firmwareHardwareRevision(summary)],
    ["Compatibility status", statusLabel(summary.path_status || summary.compliance_status)],
    ["Last check time", summary.last_scanned ? formatDateTime(summary.last_scanned) : "Not checked"],
    ["Detection source", `${sourceLabel(summary.source_type)} / ${statusLabel(summary.freshness)}`]
  ];
  return (
    <article className="cc-firmware-row">
      <div className="cc-firmware-row-head">
        <div>
          <strong>{summary.label}</strong>
          <span>{summary.component_type}</span>
        </div>
        <StatusPill status={summary.path_status || summary.compliance_status} />
      </div>
      <FactList facts={facts} />
      {summary.blocker && <Banner tone="warn">{summary.blocker}</Banner>}
    </article>
  );
}

function FirmwareVisibilityEmpty() {
  return (
    <div className="cc-firmware-empty">
      <FactList
        facts={[
          ["Detected device/model", "Not checked"],
          ["Current firmware version", "Not reported"],
          ["Available firmware version", "Backend integration pending"],
          ["Build/date", "Not reported"],
          ["Bootloader/version", "Not reported"],
          ["Hardware revision", "Not reported"],
          ["Compatibility status", "Not checked"],
          ["Last check time", "Not checked"],
          ["Detection source", "Backend firmware summary pending"]
        ]}
      />
    </div>
  );
}

function FirmwarePathSummary({ path }: { path: FirmwareUpgradePath }) {
  return (
    <div className="cc-subpanel">
      <FactList
        facts={[
          ["Component", path.component_label],
          ["Package available", path.package_available ? "Yes" : "No"],
          ["Prechecks", path.prechecks_required.length ? path.prechecks_required.join(", ") : "None reported"],
          ["Impact", path.estimated_impact],
          ["Next safe action", path.next_action]
        ]}
      />
    </div>
  );
}

function FirmwareStateRail({ status }: { status: UpgradeStatus }) {
  const states: UpgradeStatus[] = ["idle", "validating", "ready", "upgrading", "success", "failed"];
  return (
    <ol className="cc-state-rail" aria-label="Firmware upgrade state">
      {states.map((state) => (
        <li className={state === status ? "is-active" : ""} key={state}>
          {statusLabel(state)}
        </li>
      ))}
      {["blocked", "pending"].includes(status) && <li className="is-active">{statusLabel(status)}</li>}
    </ol>
  );
}

function ResultDetails({ compact = false, result }: { compact?: boolean; result: OperationResult }) {
  return (
    <div className="cc-result">
      <div className="cc-result-head control-result-summary">
        {statusIcon(result.status)}
        <div>
          <strong>{result.title}</strong>
          <p>{result.message}</p>
        </div>
        <StatusPill status={result.status} />
      </div>
      <FactList
        facts={[
          ["Checked", formatDateTime(result.checkedAt)],
          ["Source", sourceLabel(result.sourceType)],
          ["Freshness", statusLabel(result.freshness)],
          ["Executed", result.executed ? "Yes" : "No"],
          ...resultConfigFacts(result)
        ]}
      />
      <IssueList title="Blockers" items={result.blockers} />
      <IssueList title="Warnings" items={result.warnings} tone="warn" />
      {result.artifacts.length > 0 && (
        <div className="cc-artifacts">
          <strong>Artifacts</strong>
          {result.artifacts.map((artifact) => (
            <code key={artifact}>{artifact}</code>
          ))}
        </div>
      )}
      {!compact && (
        <details className="cc-details">
          <summary>Raw result</summary>
          <pre className="cc-code control-code">{JSON.stringify(result.raw, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}

function statusIcon(status: string) {
  const normalized = status.toLowerCase();
  if (/(success|ready|completed|ok|passed)/.test(normalized)) return <CheckCircle2 className="cc-icon-good" size={20} />;
  if (/(failed|error)/.test(normalized)) return <XCircle className="cc-icon-bad" size={20} />;
  if (/blocked/.test(normalized)) return <XCircle className="cc-icon-bad" size={20} />;
  if (/(pending|missing|not_checked)/.test(normalized)) return <AlertTriangle className="cc-icon-warn" size={20} />;
  return <Activity className="cc-icon-info" size={20} />;
}

function collectFirmwarePaths(summaries: FirmwareSummary[]): FirmwareUpgradePath[] {
  return summaries.flatMap((summary) => summary.upgrade_paths ?? []);
}

function savedFirmwareSelection(firmware: FirmwareState, paths: FirmwareUpgradePath[]): { pathId: string; selectedFirmware: string } | null {
  const selectedFiles = firmware.fileSelections?.selected_files ?? {};
  for (const path of paths) {
    const selectedFirmware = selectedFiles[path.component_id]?.trim();
    if (selectedFirmware) return { pathId: firmwarePathId(path), selectedFirmware };
  }
  return null;
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

function firmwareCandidateOptions(path: FirmwareUpgradePath | null): string[] {
  if (!path) return [];
  return Array.from(
    new Set(
      [
        path.selected_file_name,
        path.package_name,
        path.package_version,
        path.target_version,
        ...(path.candidate_files ?? []).map((candidate) => candidate.file_name),
        ...(path.candidate_files ?? []).map((candidate) => candidate.detected_version)
      ].filter((value): value is string => Boolean(value && value.trim()))
    )
  );
}

function runEventLogs(context: ControlCenterContext): ControlLogEntry[] {
  return [...context.logs.filter((log) => log.type === "run"), ...context.backendLogs.filter((log) => log.type === "run")];
}

function firmwareEventLogs(context: ControlCenterContext): ControlLogEntry[] {
  const backendFirmwareLogs = context.backendLogs.filter((log) => log.type === "firmware");
  return [
    ...context.logs.filter((log) => log.type === "firmware"),
    ...(backendFirmwareLogs.length ? backendFirmwareLogs : firmwareRuntimeLogs(context.firmwareRuntime.history))
  ];
}

function firmwareRuntimeLogs(results: OperationResult[]): ControlLogEntry[] {
  return results.map((result) => ({
    detail: result.message,
    id: `firmware-runtime-${result.id}`,
    message: firmwareEventMessage(result),
    status: result.status,
    timestamp: result.checkedAt,
    type: "firmware"
  }));
}

function firmwareEventMessage(result: OperationResult): string {
  const label = result.type === "firmware-upgrade" ? "Firmware upgrade" : result.type === "firmware-validation" ? "Firmware validation" : "Firmware check";
  if (result.status === "success" || result.status === "ready") return `${label} succeeded`;
  if (result.status === "failed") return `${label} failed`;
  if (result.status === "blocked") return `${label} blocked`;
  if (result.status === "running") return `${label} started`;
  if (result.status === "pending") return `${label} pending`;
  return `${label} recorded`;
}

function combinedLogs(context: ControlCenterContext): ControlLogEntry[] {
  return [...context.logs, ...context.backendLogs];
}

function allLogSources(context: ControlCenterContext): ControlLogEntry[] {
  const fallbackAuditLogs = context.backendLogs.length ? [] : logsAdapter.fromAuditEvents(context.auditEvents);
  const fallbackFirmwareLogs = context.backendLogs.some((log) => log.type === "firmware") ? [] : firmwareRuntimeLogs(context.firmwareRuntime.history);
  return [...context.logs, ...context.backendLogs, ...fallbackFirmwareLogs, ...fallbackAuditLogs];
}

function uniqueLogs(logs: ControlLogEntry[]): ControlLogEntry[] {
  const seen = new Set<string>();
  return logs.filter((log) => {
    const timestamp = Date.parse(log.timestamp);
    const bucket = Number.isNaN(timestamp) ? log.timestamp : String(Math.floor(timestamp / 5000));
    const key = `${log.type}:${log.message}:${log.status ?? ""}:${normalizeLogDetail(log.detail)}:${bucket}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function normalizeLogDetail(detail: string | undefined): string {
  return (detail ?? "").replace(/\s+/g, " ").trim();
}

function firmwareUpgradeSummaryResult(context: ControlCenterContext): OperationResult | null {
  if (context.latestFirmwareUpgrade && operationResultUsesConfig(context.latestFirmwareUpgrade, context.config)) {
    return context.latestFirmwareUpgrade;
  }
  if (context.firmwareRuntime.latestUpgrade && operationResultUsesConfig(context.firmwareRuntime.latestUpgrade, context.config)) {
    return context.firmwareRuntime.latestUpgrade;
  }
  return null;
}

function firmwareSummaryText(summaries: FirmwareSummary[]): string {
  if (!summaries.length) return "Not checked";
  const needsUpgrade = summaries.filter((summary) => summary.compliance_status === "needs_upgrade").length;
  return `${summaries.length} surfaces detected; ${needsUpgrade} need review`;
}

function providerDetectionText(providers: ProviderStatus[]): string {
  const visible = providers.filter((provider) => provider.is_operator_visible !== false);
  if (!visible.length) return "Not checked";
  const ready = visible.filter((provider) => /ready|ok|available|connected|current/i.test(provider.status)).length;
  const blocked = visible.filter((provider) => provider.blockers.length || /blocked|failed|unavailable|missing/i.test(provider.status)).length;
  return `${visible.length} adapters visible; ${ready} ready; ${blocked} blocked or missing`;
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

function firmwareBuildDate(summary: FirmwareSummary): string {
  return firmwareVersionByLabel(summary, /build|date|release/i);
}

function firmwareHardwareRevision(summary: FirmwareSummary): string {
  return firmwareVersionByLabel(summary, /hardware|revision|rev\b/i);
}

function firmwareVersionByLabel(summary: FirmwareSummary, pattern: RegExp): string {
  const match = summary.current_versions.find((item) => pattern.test(item.label));
  return displayValue(match?.version ?? null);
}

function firmwareReadinessLabel(context: ControlCenterContext): string {
  if (context.upgradeStatus === "validating") return "Validation running";
  if (!context.selectedPath) return "Missing firmware path";
  if (!context.selectedFirmware) return "Missing selected firmware";
  if (!context.latestFirmwareValidation) return "Validation required";
  if (!firmwareValidationMatchesSelection(context.latestFirmwareValidation, context.selectedPath, context.selectedFirmware, context.config)) {
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
  const upgradeActionBlocker = firmwareUpgradeActionBlocker(input.selectedPath, input.selectedUpgradeAction);
  if (upgradeActionBlocker) blockers.push(upgradeActionBlocker);
  if (!input.validation) {
    blockers.push("Validate firmware before starting an upgrade.");
  } else if (!firmwareValidationMatchesSelection(input.validation, input.selectedPath, input.selectedFirmware, input.config)) {
    blockers.push("Validate the current config and selected firmware path before starting an upgrade.");
  } else if (!firmwareValidationPassed(input.validation)) {
    blockers.push("Firmware validation failed or is blocked. No override is supported.");
  }
  const expected = upgradeConfirmationPhrase(input.selectedPath, input.selectedUpgradeAction);
  if (!input.accepted || input.phrase.trim() !== expected) {
    blockers.push(`Type ${expected} and check the confirmation box acknowledging backend gates.`);
  }
  return blockers;
}

function firmwareUpgradeActionBlocker(selectedPath: FirmwareUpgradePath | null, selectedUpgradeAction: WorkflowAction | null): string | null {
  if (!selectedPath) return null;
  const actionId = supportedUpgradeActionId(selectedPath);
  if (!actionId) return "Backend firmware upgrade integration is pending for this selected firmware path.";
  if (!selectedUpgradeAction) return `Backend action ${actionId} is not available in the workflow catalog.`;
  if (["blocked", "missing_config", "not_in_scope"].includes(selectedUpgradeAction.current_availability)) {
    return (
      selectedUpgradeAction.blockers[0] ||
      selectedUpgradeAction.next_action ||
      `Backend action ${actionId} is not ready.`
    );
  }
  if (selectedUpgradeAction.action_id === "firmware.upgrade-apply-placeholder") {
    return "Backend firmware upgrade execution is still a guarded placeholder for this selected firmware path.";
  }
  return null;
}

function firmwareValidateBlockers(input: { config: ControlConfig; selectedFirmware: string; selectedPath: FirmwareUpgradePath | null }): string[] {
  const blockers = [...configAdapter.validate(input.config)];
  if (!input.selectedPath) blockers.push("Select a firmware path before validation.");
  if (!input.selectedFirmware.trim()) blockers.push("Selected firmware, image, or target version is required before validation.");
  return blockers;
}

function resultConfigFacts(result: OperationResult): Array<[string, string]> {
  const snapshot = operationConfigSnapshot(result);
  if (!snapshot) return [];
  return [
    ["Target", stringFact(snapshot.target, "Not recorded")],
    ["IP mode used", ipModeLabel(stringFact(snapshot.ip_mode, "ipv4"))],
    ["SNMP used", snmpVersionLabel(stringFact(snapshot.snmp_version, "v2"))],
    ["SNMP credential state", statusLabel(stringFact(snapshot.snmp_credentials ?? snapshot.snmp_credential_status, "missing"))],
    ["Timeout / retry used", `${stringFact(snapshot.timeout_seconds, "Not recorded")}s / ${stringFact(snapshot.retry_count, "Not recorded")}`]
  ];
}

function operationConfigSnapshot(result: OperationResult): Record<string, unknown> | null {
  const candidate = result.raw.config_snapshot ?? result.raw.control_center_config;
  return candidate && typeof candidate === "object" ? (candidate as Record<string, unknown>) : null;
}

function configSnapshot(config: ControlConfig): Record<string, unknown> {
  return {
    ip_mode: config.ipMode,
    retry_count: config.retryCount,
    snmp_credentials: config.snmpCredentialStatus,
    snmp_credential_version: config.snmpCredentialVersion,
    snmp_version: config.snmpVersion,
    target: config.target,
    timeout_seconds: config.timeoutSeconds
  };
}

function shouldClearResultsForConfig(config: ControlConfig, results: Array<OperationResult | null>): boolean {
  return results.some((result) => Boolean(result && !operationResultUsesConfig(result, config)));
}

function operationResultUsesConfig(result: OperationResult, config: ControlConfig): boolean {
  const snapshot = operationConfigSnapshot(result);
  if (!snapshot) return false;
  const expected = configSnapshot(config);
  const actual = comparableConfigSnapshot(snapshot);
  return Object.entries(expected).every(([key, value]) => actual[key] === value);
}

function comparableConfigSnapshot(snapshot: Record<string, unknown>): Record<string, unknown> {
  return {
    ip_mode: snapshot.ip_mode,
    retry_count: snapshot.retry_count,
    snmp_credentials: snapshot.snmp_credentials ?? snapshot.snmp_credential_status,
    snmp_credential_version: snapshot.snmp_credential_version ?? null,
    snmp_version: snapshot.snmp_version,
    target: snapshot.target,
    timeout_seconds: snapshot.timeout_seconds
  };
}

function shouldAdoptBackendConfig(current: ControlConfig, backend: ControlConfig): boolean {
  if (!hasLocalConfigState(current)) return true;
  return backendStateIsAtLeastAsFresh(current.updatedAt, backend.updatedAt);
}

function shouldAdoptBackendSettings(current: ControlSettings, backend: ControlSettings): boolean {
  if (!current.updatedAt) return true;
  return backendStateIsAtLeastAsFresh(current.updatedAt, backend.updatedAt);
}

function configWithSettingsDefaults(config: ControlConfig, settings: ControlSettings): ControlConfig {
  if (hasLocalConfigState(config)) return config;
  return {
    ...config,
    ipMode: settings.defaultIpMode,
    retryCount: settings.defaultRetryCount,
    snmpVersion: settings.defaultSnmpVersion,
    timeoutSeconds: settings.defaultTimeoutSeconds
  };
}

function hasLocalConfigState(config: ControlConfig): boolean {
  return Boolean(
    config.updatedAt ||
      config.target.trim() ||
      config.snmpCredentialStatus === "configured" ||
      config.snmpCredentialVersion
  );
}

function backendStateIsAtLeastAsFresh(currentUpdatedAt: string | null, backendUpdatedAt: string | null): boolean {
  if (!currentUpdatedAt) return true;
  if (!backendUpdatedAt) return false;
  const currentTime = Date.parse(currentUpdatedAt);
  const backendTime = Date.parse(backendUpdatedAt);
  if (Number.isNaN(currentTime)) return true;
  if (Number.isNaN(backendTime)) return false;
  return backendTime >= currentTime;
}

function firmwareSelectionSnapshot(config: ControlConfig, selectedPath: FirmwareUpgradePath | null, selectedFirmware: string): Record<string, unknown> {
  return {
    config_snapshot: configSnapshot(config),
    selected_component: selectedPath?.component_id ?? null,
    selected_device: selectedPath?.device_label ?? null,
    selected_firmware: selectedFirmware.trim(),
    selected_target: selectedPath ? selectedFirmwareTarget(selectedPath) : null
  };
}

function selectedFirmwareTarget(path: FirmwareUpgradePath): string {
  return path.target_version || path.package_name || path.selected_file_name || "unknown";
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
  if (status === "blocked") return `${prefix} blocked`;
  if (status === "pending") return `${prefix} pending`;
  if (status === "running") return `${prefix} started`;
  return `${prefix} failed`;
}

function resultStatusLabel(result: OperationResult | null, fallback: OperationStatus): string {
  if (fallback === "running") return "Running";
  return result ? statusLabel(result.status) : "Not run";
}

function firmwareStatusLabel(context: ControlCenterContext): string {
  if (context.upgradeStatus === "upgrading") return "Upgrade running";
  if (context.upgradeStatus === "validating") return "Validation running";
  const latestUpgrade = firmwareUpgradeSummaryResult(context);
  if (latestUpgrade) return `Upgrade ${statusLabel(latestUpgrade.status)}`;
  if (context.latestFirmwareCheck) return statusLabel(context.latestFirmwareCheck.status);
  if (context.firmwareRuntime.history.some((result) => operationResultUsesConfig(result, context.config))) {
    return statusLabel(context.firmwareRuntime.status);
  }
  if (context.firmwareRuntime.history.length) return "Historical firmware activity";
  return context.firmware.summaries.length ? "Summary loaded" : "Not checked";
}

function firmwareProgressLabel(context: ControlCenterContext): string {
  if (context.upgradeStatus === "upgrading") return "Backend request in progress";
  if (context.upgradeStatus === "validating") return "Validation in progress";
  const latestUpgrade = firmwareUpgradeSummaryResult(context);
  if (latestUpgrade) {
    if (latestUpgrade.status === "success") return "Completed";
    if (latestUpgrade.status === "blocked") return "Blocked before execution";
    if (latestUpgrade.status === "pending") return "Backend integration pending";
    if (latestUpgrade.status === "failed") return "Failed";
    return statusLabel(latestUpgrade.status);
  }
  if (context.firmwareRuntime.history.length) return statusLabel(context.firmwareRuntime.status);
  if (context.firmwareRuntime.sourceType === "todo_placeholder") return "Backend integration pending";
  return "Not started";
}

function firmwareRuntimeSourceLabel(runtime: FirmwareRuntimeStatus): string {
  const checked = runtime.checkedAt ? formatDateTime(runtime.checkedAt) : "Not checked";
  return `${sourceLabel(runtime.sourceType)} / ${statusLabel(runtime.freshness)} / ${checked}`;
}

function firmwareBackendGateLabel(context: ControlCenterContext): string {
  if (!context.selectedPath) return "Select firmware path";
  if (!context.selectedUpgradeAction) return "Backend integration pending";
  const gates = context.selectedUpgradeAction.required_gates ?? [];
  return gates.length ? gates.join(", ") : "No backend gates reported";
}

function validationStatusLabel(context: ControlCenterContext): string {
  if (context.upgradeStatus === "validating") return "Validation running";
  if (!context.latestFirmwareValidation) return "Not validated";
  if (!firmwareValidationMatchesSelection(context.latestFirmwareValidation, context.selectedPath, context.selectedFirmware, context.config)) {
    return "Not validated for current config and selection";
  }
  return statusLabel(context.latestFirmwareValidation.status);
}

function routeTargetFromLegacyPath(pathname: string, search: string): string {
  const params = new URLSearchParams(search);
  const section = `${pathname} ${params.get("section") ?? ""} ${params.get("action") ?? ""} ${
    params.get("device") ?? ""
  }`.toLowerCase();
  if (/(configure|config|setup|target)/.test(section)) return "/configure";
  if (/(firmware|upgrade|ontap)/.test(section)) return "/firmware";
  if (/(report|result|evidence|artifact)/.test(section)) return "/results";
  if (/(^|[\s/])(logs?|audit)([\s/]|$)/.test(section)) return "/logs";
  if (/(setting|provider-mode|runtime)/.test(section)) return "/settings";
  if (/(^|[\s/])run([\s/]|$)/.test(section) || /(action|cisco|ilo|raid|esxi|netapp|serial|lab_profile)/.test(section)) return "/run";
  return "/dashboard";
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

function credentialDraftHasValues(draft: CredentialDraft): boolean {
  return Object.values(draft).some((value) => value.trim().length > 0);
}

function formatDateTime(value: string): string {
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return value;
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(parsed);
}

function displayValue(value: string | null | undefined): string {
  return value && value.trim() ? value : "Not reported";
}

function stringFact(value: unknown, fallback: string): string {
  if (typeof value === "string") return value.trim() || fallback;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function sourceLabel(value: string): string {
  return value.replace(/[_-]+/g, " ");
}

function statusLabel(value: string): string {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function toneClass(value: string): string {
  const normalized = value.toLowerCase();
  if (/(success|ready|completed|connected|visible|current|saved|ok|passed)/.test(normalized)) return "is-good";
  if (/(running|checking|validating|summary|loaded)/.test(normalized)) return "is-info";
  if (/(failed|error|blocked|disconnected)/.test(normalized)) return "is-bad";
  if (/(warning|pending|missing|not configured|unavailable|not checked|not run|attention)/.test(normalized)) return "is-warn";
  return "is-neutral";
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
