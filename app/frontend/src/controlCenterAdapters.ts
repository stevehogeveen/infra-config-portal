import { api } from "./api";
import type {
  AuditEvent,
  ControlCenterConfigRead,
  ControlCenterConfigWrite,
  ControlCenterSettingsRead,
  ControlCenterSettingsWrite,
  FirmwareFileSelections,
  FirmwareSummary,
  FirmwareUpgradePath,
  ProviderProbeResult,
  ProviderStatus,
  WorkflowAction,
  WorkflowActionRun
} from "./types";

export type IpMode = "ipv4" | "ipv6" | "both";
export type SnmpVersion = "v2" | "v3";
export type OperationStatus = "idle" | "running" | "ready" | "success" | "failed" | "blocked" | "pending";
export type UpgradeStatus = "idle" | "validating" | "ready" | "upgrading" | "success" | "failed" | "blocked" | "pending";

export type ControlConfig = {
  target: string;
  ipMode: IpMode;
  snmpVersion: SnmpVersion;
  snmpCredentialStatus: "missing" | "configured";
  snmpCredentialVersion: SnmpVersion | null;
  timeoutSeconds: number;
  retryCount: number;
  updatedAt: string | null;
};

export type CredentialDraft = {
  snmpV2Community: string;
  snmpV3Username: string;
  snmpV3AuthPassword: string;
  snmpV3PrivacyPassword: string;
};

export type ControlSettings = {
  defaultIpMode: IpMode;
  defaultSnmpVersion: SnmpVersion;
  defaultTimeoutSeconds: number;
  defaultRetryCount: number;
  apiBaseUrl: string;
  firmwareRepository: string;
  loggingVerbosity: "errors" | "normal" | "debug";
  updatedAt: string | null;
};

export type ControlLogEntry = {
  detail?: string;
  id: string;
  message: string;
  status?: string;
  timestamp: string;
  type: "system" | "config" | "run" | "firmware" | "settings";
};

export type OperationResult = {
  id: string;
  type: "run" | "firmware-check" | "firmware-validation" | "firmware-upgrade";
  title: string;
  status: OperationStatus;
  message: string;
  checkedAt: string;
  sourceType: string;
  freshness: string;
  executed: boolean;
  blockers: string[];
  warnings: string[];
  artifacts: string[];
  raw: Record<string, unknown>;
};

export type FirmwareState = {
  summaries: FirmwareSummary[];
  fileSelections: FirmwareFileSelections | null;
};

export type FirmwareRuntimeStatus = {
  actionIds: string[];
  checkedAt: string | null;
  freshness: string;
  history: OperationResult[];
  latestUpgrade: OperationResult | null;
  message: string;
  sourceType: string;
  status: UpgradeStatus;
};

export type FirmwareUpgradeRequest = {
  actions: WorkflowAction[];
  config: ControlConfig;
  confirmationAccepted: boolean;
  confirmationPhrase: string;
  selectedFirmware: string;
  selectedPath: FirmwareUpgradePath | null;
  validationResult: OperationResult | null;
};

export type ControlCenterSnapshot = {
  actions: WorkflowAction[];
  auditEvents: AuditEvent[];
  controlConfig: ControlConfig | null;
  controlSettings: ControlSettings | null;
  firmware: FirmwareState;
  firmwareRuntime: FirmwareRuntimeStatus;
  health: HealthState | null;
  providers: ProviderStatus[];
};

export type HealthState = {
  app?: string;
  dev_test_banner?: string | null;
  expected_runtime_mode?: string;
  operator_runtime_mode?: string;
  provider_mode?: string;
  status: string;
};

const CONFIG_STORAGE_KEY = "webuis-control-center-config-v2";
const SETTINGS_STORAGE_KEY = "webuis-control-center-settings-v2";
const LOG_STORAGE_KEY = "webuis-control-center-logs-v2";
const RESULT_STORAGE_KEY = "webuis-control-center-latest-result-v2";
const FIRMWARE_CHECK_STORAGE_KEY = "webuis-control-center-latest-firmware-check-v2";
const FIRMWARE_VALIDATION_STORAGE_KEY = "webuis-control-center-latest-firmware-validation-v2";
const FIRMWARE_UPGRADE_STORAGE_KEY = "webuis-control-center-latest-firmware-upgrade-v2";
const SECRET_SHAPED_RE = /(password\s*=|token\s*=|secret\s*=|bearer\s+|-----begin|private[_ -]?key)/i;

export const defaultConfig: ControlConfig = {
  target: "",
  ipMode: "ipv4",
  snmpVersion: "v2",
  snmpCredentialStatus: "missing",
  snmpCredentialVersion: null,
  timeoutSeconds: 8,
  retryCount: 1,
  updatedAt: null
};

export const defaultCredentialDraft: CredentialDraft = {
  snmpV2Community: "",
  snmpV3Username: "",
  snmpV3AuthPassword: "",
  snmpV3PrivacyPassword: ""
};

export const defaultSettings: ControlSettings = {
  defaultIpMode: "ipv4",
  defaultSnmpVersion: "v2",
  defaultTimeoutSeconds: 8,
  defaultRetryCount: 1,
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || "same-origin",
  firmwareRepository: "Backend firmware repository integration pending",
  loggingVerbosity: "normal",
  updatedAt: null
};

export const defaultFirmwareRuntimeStatus: FirmwareRuntimeStatus = {
  actionIds: [],
  checkedAt: null,
  freshness: "not_checked",
  history: [],
  latestUpgrade: null,
  message: "Firmware status/progress backend integration is pending.",
  sourceType: "todo_placeholder",
  status: "idle"
};

const preferredRunActionIds = [
  "build-verification.run-full",
  "full-lab.validation",
  "lab-validation.summary",
  "reports.summary",
  "lab-profile.view-active"
];

export const configAdapter = {
  backendStatus:
    "Backend /api/v1/control-center/config stores non-secret target and SNMP state. Credential values remain operator/runtime only.",

  load(): ControlConfig {
    const stored = readStored<Partial<ControlConfig>>(CONFIG_STORAGE_KEY);
    const loaded = { ...defaultConfig, ...stored };
    if (loaded.snmpCredentialStatus === "configured" && !loaded.snmpCredentialVersion) {
      return {
        ...loaded,
        snmpCredentialVersion: loaded.snmpVersion
      };
    }
    return loaded;
  },

  validate(config: ControlConfig): string[] {
    const errors: string[] = [];
    if (!config.target.trim()) {
      errors.push("Target host, IP, or range is required.");
    }
    if (SECRET_SHAPED_RE.test(config.target)) {
      errors.push("Target must not contain secret-shaped values.");
    }
    if (!Number.isFinite(config.timeoutSeconds) || config.timeoutSeconds < 1 || config.timeoutSeconds > 120) {
      errors.push("Timeout must be between 1 and 120 seconds.");
    }
    if (!Number.isFinite(config.retryCount) || config.retryCount < 0 || config.retryCount > 5) {
      errors.push("Retry count must be between 0 and 5.");
    }
    return errors;
  },

  async save(
    config: ControlConfig,
    credentialDraft: CredentialDraft
  ): Promise<{ config: ControlConfig; errors: string[]; savedVia: "backend" | "local_fallback" }> {
    const draftHasCredential = hasCredentialDraftForVersion(credentialDraft, config.snmpVersion);
    const existingCredentialStillApplies =
      config.snmpCredentialStatus === "configured" && config.snmpCredentialVersion === config.snmpVersion;
    const snmpCredentialStatus = draftHasCredential || existingCredentialStillApplies ? "configured" : "missing";
    const normalized: ControlConfig = {
      ...config,
      retryCount: clampNumber(config.retryCount, 0, 5),
      timeoutSeconds: clampNumber(config.timeoutSeconds, 1, 120),
      snmpCredentialStatus,
      snmpCredentialVersion: snmpCredentialStatus === "configured" ? config.snmpVersion : null,
      target: config.target.trim()
    };
    const errors = this.validate(normalized);
    if (errors.length) {
      return { config: { ...normalized, updatedAt: config.updatedAt }, errors, savedVia: "local_fallback" };
    }
    const next: ControlConfig = { ...normalized, updatedAt: new Date().toISOString() };
    try {
      const saved = fromBackendConfig(await api.saveControlCenterConfig(toBackendConfig(next)));
      writeStored(CONFIG_STORAGE_KEY, saved);
      return { config: saved, errors, savedVia: "backend" };
    } catch {
      writeStored(CONFIG_STORAGE_KEY, next);
      return { config: next, errors, savedVia: "local_fallback" };
    }
  }
};

export const settingsAdapter = {
  load(): ControlSettings {
    return { ...defaultSettings, ...readStored<Partial<ControlSettings>>(SETTINGS_STORAGE_KEY) };
  },

  validate(settings: ControlSettings): string[] {
    const errors: string[] = [];
    if (!Number.isFinite(settings.defaultTimeoutSeconds) || settings.defaultTimeoutSeconds < 1 || settings.defaultTimeoutSeconds > 120) {
      errors.push("Default timeout must be between 1 and 120 seconds.");
    }
    if (!Number.isFinite(settings.defaultRetryCount) || settings.defaultRetryCount < 0 || settings.defaultRetryCount > 5) {
      errors.push("Default retry count must be between 0 and 5.");
    }
    if (SECRET_SHAPED_RE.test(settings.apiBaseUrl) || SECRET_SHAPED_RE.test(settings.firmwareRepository)) {
      errors.push("Settings must not contain secret-shaped values.");
    }
    if (!validApiBaseUrl(settings.apiBaseUrl)) {
      errors.push("API/server URL must be same-origin, a relative path, or an http(s) URL.");
    }
    return errors;
  },

  async save(
    settings: ControlSettings
  ): Promise<{ settings: ControlSettings; errors: string[]; savedVia: "backend" | "local_fallback" }> {
    const next: ControlSettings = {
      ...settings,
      apiBaseUrl: settings.apiBaseUrl.trim() || defaultSettings.apiBaseUrl,
      defaultRetryCount: clampNumber(settings.defaultRetryCount, 0, 5),
      defaultTimeoutSeconds: clampNumber(settings.defaultTimeoutSeconds, 1, 120),
      firmwareRepository: settings.firmwareRepository.trim() || defaultSettings.firmwareRepository,
      updatedAt: new Date().toISOString()
    };
    const errors = this.validate(next);
    if (errors.length) {
      return { settings, errors, savedVia: "local_fallback" };
    }
    try {
      const saved = fromBackendSettings(await api.saveControlCenterSettings(toBackendSettings(next)));
      writeStored(SETTINGS_STORAGE_KEY, saved);
      return { settings: saved, errors, savedVia: "backend" };
    } catch {
      writeStored(SETTINGS_STORAGE_KEY, next);
      return { settings: next, errors, savedVia: "local_fallback" };
    }
  }
};

export const logsAdapter = {
  load(): ControlLogEntry[] {
    return readStored<ControlLogEntry[]>(LOG_STORAGE_KEY) ?? [];
  },

  add(logs: ControlLogEntry[], entry: Omit<ControlLogEntry, "id" | "timestamp">): ControlLogEntry[] {
    const next = [
      {
        ...entry,
        id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        timestamp: new Date().toISOString()
      },
      ...logs
    ].slice(0, 80);
    writeStored(LOG_STORAGE_KEY, next);
    return next;
  },

  fromAuditEvents(auditEvents: AuditEvent[]): ControlLogEntry[] {
    return auditEvents.slice(0, 20).map((event) => ({
      detail: event.message,
      id: `audit-${event.id}`,
      message: humanize(event.event_type),
      status: event.to_status ?? event.from_status ?? "recorded",
      timestamp: event.created_at,
      type: "system"
    }));
  }
};

export const resultsAdapter = {
  loadRun(): OperationResult | null {
    return readStored<OperationResult>(RESULT_STORAGE_KEY);
  },

  saveRun(result: OperationResult): void {
    writeStored(RESULT_STORAGE_KEY, result);
  },

  clearRun(): void {
    removeStored(RESULT_STORAGE_KEY);
  },

  loadFirmwareCheck(): OperationResult | null {
    return readStored<OperationResult>(FIRMWARE_CHECK_STORAGE_KEY);
  },

  saveFirmwareCheck(result: OperationResult): void {
    writeStored(FIRMWARE_CHECK_STORAGE_KEY, result);
  },

  clearFirmwareCheck(): void {
    removeStored(FIRMWARE_CHECK_STORAGE_KEY);
  },

  loadFirmwareValidation(): OperationResult | null {
    return readStored<OperationResult>(FIRMWARE_VALIDATION_STORAGE_KEY);
  },

  saveFirmwareValidation(result: OperationResult): void {
    writeStored(FIRMWARE_VALIDATION_STORAGE_KEY, result);
  },

  clearFirmwareValidation(): void {
    removeStored(FIRMWARE_VALIDATION_STORAGE_KEY);
  },

  loadFirmwareUpgrade(): OperationResult | null {
    return readStored<OperationResult>(FIRMWARE_UPGRADE_STORAGE_KEY);
  },

  saveFirmwareUpgrade(result: OperationResult): void {
    writeStored(FIRMWARE_UPGRADE_STORAGE_KEY, result);
  },

  clearFirmwareUpgrade(): void {
    removeStored(FIRMWARE_UPGRADE_STORAGE_KEY);
  }
};

export const runAdapter = {
  selectAction(actions: WorkflowAction[]): WorkflowAction | null {
    const runnable = actions.filter(
      (action) =>
        action.ui_run_supported &&
        ["read_only", "report_only"].includes(action.mode) &&
        !["blocked", "not_in_scope", "missing_config"].includes(action.current_availability)
    );
    for (const actionId of preferredRunActionIds) {
      const match = runnable.find((action) => action.action_id === actionId);
      if (match) return match;
    }
    return runnable[0] ?? null;
  },

  async run(config: ControlConfig, action: WorkflowAction | null): Promise<OperationResult> {
    const validationErrors = configAdapter.validate(config);
    if (validationErrors.length) {
      return placeholderResult({
        blockers: validationErrors,
        message: "Run blocked until the current configuration is valid.",
        raw: {
          config_snapshot: sanitizedConfigSnapshot(config)
        },
        status: "blocked",
        title: "Run blocked",
        type: "run",
        sourceType: "ui_local_state"
      });
    }
    if (!action) {
      return placeholderResult({
        blockers: ["Backend workflow action catalog is unavailable."],
        message: "No provider call was run. Backend run integration is pending.",
        status: "pending",
        title: "Safe run placeholder",
        type: "run"
      });
    }
    const configSnapshot = sanitizedConfigSnapshot(config);
    const result = await api.runWorkflowAction(action.action_id, {
      control_config: configSnapshot
    });
    return normalizeWorkflowRun(result, "run", {
      config_snapshot: configSnapshot
    });
  }
};

export const firmwareAdapter = {
  async load(): Promise<FirmwareState> {
    const [summaries, fileSelections] = await Promise.all([
      safeCall(api.firmwareSummary, [] as FirmwareSummary[]),
      safeCall(api.firmwareFileSelections, null)
    ]);
    return {
      fileSelections,
      summaries: Array.isArray(summaries) ? summaries : []
    };
  },

  async status(actions: WorkflowAction[]): Promise<FirmwareRuntimeStatus> {
    const actionIds = firmwareRuntimeActionIds(actions);
    if (!actionIds.length) {
      return {
        ...defaultFirmwareRuntimeStatus,
        message: "No backend firmware action catalog entries are available yet."
      };
    }

    const runGroups = await Promise.all(
      actionIds.map(async (actionId) => {
        try {
          const runs = await api.workflowActionRuns(actionId);
          return Array.isArray(runs) ? runs : [];
        } catch {
          return [];
        }
      })
    );
    const history = runGroups
      .flat()
      .map((run) => normalizeWorkflowRun(run, firmwareOperationType(run.action_id)))
      .sort((first, second) => Date.parse(second.checkedAt) - Date.parse(first.checkedAt))
      .slice(0, 12);

    if (!history.length) {
      return {
        ...defaultFirmwareRuntimeStatus,
        actionIds,
        message: "No backend firmware checks, validations, or upgrade attempts have been recorded yet.",
        sourceType: "backend_action_runs"
      };
    }

    const latest = history[0];
    const latestUpgrade = history.find((result) => result.type === "firmware-upgrade") ?? null;
    return {
      actionIds,
      checkedAt: latest.checkedAt,
      freshness: latest.freshness,
      history,
      latestUpgrade,
      message: latestUpgrade?.message ?? latest.message,
      sourceType: latest.sourceType,
      status: latestUpgrade ? upgradeStatusFromOperation(latestUpgrade.status) : upgradeStatusFromOperation(latest.status)
    };
  },

  async check(config: ControlConfig): Promise<{ firmware: FirmwareState; result: OperationResult }> {
    const validationErrors = configAdapter.validate(config);
    if (validationErrors.length) {
      return {
        firmware: await this.load(),
        result: placeholderResult({
          blockers: validationErrors,
          message: "Firmware check blocked until the current configuration is valid.",
          raw: {
            config_snapshot: sanitizedConfigSnapshot(config)
          },
          sourceType: "ui_local_state",
          status: "blocked",
          title: "Firmware check blocked",
          type: "firmware-check"
        })
      };
    }
    try {
      const probe = await api.firmwareInventory();
      const firmware = await this.load();
      return {
        firmware,
        result: normalizeProbeResult(probe, "firmware-check", "Firmware check", {
          config_snapshot: sanitizedConfigSnapshot(config)
        })
      };
    } catch (error) {
      return {
        firmware: await this.load(),
        result: placeholderResult({
          blockers: [unknownErrorMessage(error)],
          message: "Firmware check backend integration is unavailable. No firmware action was started.",
          raw: {
            config_snapshot: sanitizedConfigSnapshot(config)
          },
          status: "pending",
          title: "Firmware check pending backend integration",
          type: "firmware-check"
        })
      };
    }
  },

  async validate(input: {
    config: ControlConfig;
    selectedFirmware: string;
    selectedPath: FirmwareUpgradePath | null;
  }): Promise<{ firmware: FirmwareState; result: OperationResult }> {
    const blockers = firmwareSelectionBlockers(input.selectedPath, input.selectedFirmware);
    blockers.unshift(...configAdapter.validate(input.config));
    if (blockers.length) {
      return {
        firmware: await this.load(),
        result: placeholderResult({
          blockers,
          message: "Firmware validation blocked until the current config and firmware selection are complete.",
          raw: firmwareSelectionRaw(input.config, input.selectedPath, input.selectedFirmware),
          sourceType: "ui_local_state",
          status: "blocked",
          title: "Firmware validation blocked",
          type: "firmware-validation"
        })
      };
    }
    const selectedPath = input.selectedPath;
    if (!selectedPath) {
      return {
        firmware: await this.load(),
        result: placeholderResult({
          blockers: ["Select a firmware path before validation or upgrade."],
          message: "Firmware validation blocked until a firmware path is selected.",
          raw: firmwareSelectionRaw(input.config, input.selectedPath, input.selectedFirmware),
          sourceType: "ui_local_state",
          status: "blocked",
          title: "Firmware validation blocked",
          type: "firmware-validation"
        })
      };
    }
    try {
      const saved = await api.saveFirmwareFileSelections({
        selected_files: { [selectedPath.component_id]: input.selectedFirmware.trim() }
      });
      const probe =
        selectedPath.component_id === "netapp_ontap_version"
          ? await api.validateNetappOntapUpgrade()
          : await api.firmwareCompliance(firmwareScopeForPath(selectedPath));
      const firmware = await this.load();
      return {
        firmware: {
          ...firmware,
          fileSelections: saved
        },
        result: normalizeProbeResult(probe, "firmware-validation", "Firmware validation", {
          ...firmwareSelectionRaw(input.config, input.selectedPath, input.selectedFirmware),
          file_selection_saved_at: saved.updated_at
        })
      };
    } catch (error) {
      return {
        firmware: await this.load(),
        result: placeholderResult({
          blockers: [unknownErrorMessage(error)],
          message: "Firmware validation backend integration is unavailable. No upgrade action was started.",
          raw: firmwareSelectionRaw(input.config, input.selectedPath, input.selectedFirmware),
          status: "pending",
          title: "Firmware validation pending backend integration",
          type: "firmware-validation"
        })
      };
    }
  },

  async upgrade(request: FirmwareUpgradeRequest): Promise<OperationResult> {
    const blockers = upgradeRequestBlockers(request);
    if (blockers.length) {
      return placeholderResult({
        blockers,
        message: "Firmware upgrade was not started.",
        status: "blocked",
        title: "Firmware upgrade blocked",
        type: "firmware-upgrade"
      });
    }

    const supportedActionId = supportedUpgradeActionId(request.selectedPath);
    const action = upgradeActionForRequest(request);
    if (!supportedActionId) {
      return placeholderResult({
        blockers: [
          "Backend firmware upgrade integration is pending for this selected firmware path."
        ],
        message: "No firmware update, reboot, or provider write was executed.",
        status: "pending",
        title: "Firmware upgrade pending backend integration",
        type: "firmware-upgrade",
        raw: {
          ...firmwareSelectionRaw(request.config, request.selectedPath, request.selectedFirmware),
          selected_component: request.selectedPath?.component_id ?? null,
          selected_firmware: request.selectedFirmware
        }
      });
    }

    if (!action) {
      return placeholderResult({
        blockers: [`Backend action ${supportedActionId} is not available in the workflow catalog.`],
        message: "Firmware upgrade was not started.",
        status: "pending",
        title: "Firmware upgrade pending backend integration",
        type: "firmware-upgrade"
      });
    }

    const result = await api.runWorkflowAction(supportedActionId, {
      control_config: sanitizedConfigSnapshot(request.config),
      confirmation_phrase: request.confirmationPhrase.trim(),
      confirmed_gates: action.required_gates
    });
    return normalizeWorkflowRun(result, "firmware-upgrade", firmwareSelectionRaw(
      request.config,
      request.selectedPath,
      request.selectedFirmware
    ));
  }
};

export const backendAdapter = {
  async loadSnapshot(): Promise<ControlCenterSnapshot> {
    const [health, providers, actions, auditEvents, controlConfig, controlSettings, firmware] = await Promise.all([
      safeCall(api.health, null),
      safeCall(api.providers, [] as ProviderStatus[]),
      safeCall(api.workflowActions, [] as WorkflowAction[]),
      safeCall(api.auditEvents, [] as AuditEvent[]),
      safeCall(api.controlCenterConfig, null),
      safeCall(api.controlCenterSettings, null),
      firmwareAdapter.load()
    ]);
    const normalizedActions = Array.isArray(actions) ? actions : [];
    const firmwareRuntime = await firmwareAdapter.status(normalizedActions);
    return {
      actions: normalizedActions,
      auditEvents: Array.isArray(auditEvents) ? auditEvents : [],
      controlConfig: controlConfig ? fromBackendConfig(controlConfig) : null,
      controlSettings: controlSettings ? fromBackendSettings(controlSettings) : null,
      firmware,
      firmwareRuntime,
      health,
      providers: Array.isArray(providers) ? providers : []
    };
  }
};

function fromBackendConfig(config: ControlCenterConfigRead): ControlConfig {
  return {
    target: config.target ?? "",
    ipMode: config.ip_mode,
    snmpVersion: config.snmp_version,
    snmpCredentialStatus: config.snmp_credential_status,
    snmpCredentialVersion: config.snmp_credential_version,
    timeoutSeconds: config.timeout_seconds,
    retryCount: config.retry_count,
    updatedAt: config.updated_at
  };
}

function toBackendConfig(config: ControlConfig): ControlCenterConfigWrite {
  return {
    target: config.target,
    ip_mode: config.ipMode,
    snmp_version: config.snmpVersion,
    snmp_credential_status: config.snmpCredentialStatus,
    snmp_credential_version: config.snmpCredentialVersion,
    timeout_seconds: config.timeoutSeconds,
    retry_count: config.retryCount
  };
}

function fromBackendSettings(settings: ControlCenterSettingsRead): ControlSettings {
  return {
    defaultIpMode: settings.default_ip_mode,
    defaultSnmpVersion: settings.default_snmp_version,
    defaultTimeoutSeconds: settings.default_timeout_seconds,
    defaultRetryCount: settings.default_retry_count,
    apiBaseUrl: settings.api_base_url,
    firmwareRepository: settings.firmware_repository,
    loggingVerbosity: settings.logging_verbosity,
    updatedAt: settings.updated_at
  };
}

function toBackendSettings(settings: ControlSettings): ControlCenterSettingsWrite {
  return {
    default_ip_mode: settings.defaultIpMode,
    default_snmp_version: settings.defaultSnmpVersion,
    default_timeout_seconds: settings.defaultTimeoutSeconds,
    default_retry_count: settings.defaultRetryCount,
    api_base_url: settings.apiBaseUrl,
    firmware_repository: settings.firmwareRepository,
    logging_verbosity: settings.loggingVerbosity
  };
}

function normalizeWorkflowRun(
  result: WorkflowActionRun,
  type: OperationResult["type"],
  extraRaw: Record<string, unknown> = {}
): OperationResult {
  return {
    artifacts: result.report_artifacts ?? [],
    blockers: result.blockers ?? [],
    checkedAt: result.checked_at ?? result.finished_at ?? new Date().toISOString(),
    executed: Boolean(result.executed),
    freshness: result.freshness || "not_checked",
    id: result.run_id,
    message: result.summary || result.stdout_summary || result.stderr_summary || result.next_action || "Workflow action finished.",
    raw: {
      ...result,
      ...extraRaw
    } as Record<string, unknown>,
    sourceType: result.source_type || "not_checked",
    status: mapStatus(result.status, result.blockers ?? []),
    title: result.action_label,
    type,
    warnings: result.warnings ?? []
  };
}

function normalizeProbeResult(
  result: ProviderProbeResult,
  type: OperationResult["type"],
  fallbackTitle: string,
  extraRaw: Record<string, unknown> = {}
): OperationResult {
  const blockers = stringList(result.blockers);
  return {
    artifacts: stringList((result as Record<string, unknown>).report_artifacts),
    blockers,
    checkedAt: result.checked_at ?? new Date().toISOString(),
    executed: false,
    freshness: stringValue((result as Record<string, unknown>).freshness, "not_checked"),
    id: `${type}:${Date.now()}`,
    message: result.message || stringValue((result as Record<string, unknown>).next_safe_action, "Backend check completed."),
    raw: {
      ...(result as Record<string, unknown>),
      ...extraRaw
    },
    sourceType: stringValue((result as Record<string, unknown>).source_type, "backend_api"),
    status: mapStatus(result.status, blockers),
    title: fallbackTitle,
    type,
    warnings: stringList(result.warnings)
  };
}

function placeholderResult(input: {
  blockers?: string[];
  executed?: boolean;
  freshness?: string;
  message: string;
  raw?: Record<string, unknown>;
  sourceType?: string;
  status: OperationStatus;
  title: string;
  type: OperationResult["type"];
  warnings?: string[];
}): OperationResult {
  return {
    artifacts: [],
    blockers: input.blockers ?? [],
    checkedAt: new Date().toISOString(),
    executed: input.executed ?? false,
    freshness: input.freshness ?? "not_checked",
    id: `${input.type}:placeholder:${Date.now()}`,
    message: input.message,
    raw: input.raw ?? {},
    sourceType: input.sourceType ?? "todo_placeholder",
    status: input.status,
    title: input.title,
    type: input.type,
    warnings: input.warnings ?? []
  };
}

export function createLocalOperationResult(input: {
  blockers?: string[];
  message: string;
  raw?: Record<string, unknown>;
  status: OperationStatus;
  title: string;
  type: OperationResult["type"];
  warnings?: string[];
}): OperationResult {
  return placeholderResult({
    ...input,
    sourceType: "ui_local_state"
  });
}

function upgradeRequestBlockers(request: FirmwareUpgradeRequest): string[] {
  const blockers: string[] = [];
  blockers.push(...configAdapter.validate(request.config));
  blockers.push(...firmwareSelectionBlockers(request.selectedPath, request.selectedFirmware));
  if (!request.validationResult) {
    blockers.push("Validate firmware before starting an upgrade.");
  } else if (
    !firmwareValidationMatchesSelection(
      request.validationResult,
      request.selectedPath,
      request.selectedFirmware,
      request.config
    )
  ) {
    blockers.push("Validate the current config and selected firmware path before starting an upgrade.");
  } else if (!firmwareValidationPassed(request.validationResult)) {
    blockers.push("Firmware validation failed or is blocked. No override is supported in this UI.");
  }
  const action = upgradeActionForRequest(request);
  if (!request.confirmationAccepted || request.confirmationPhrase.trim() !== upgradeConfirmationPhrase(request.selectedPath, action)) {
    blockers.push(`Type ${upgradeConfirmationPhrase(request.selectedPath, action)} and check the confirmation box.`);
  }
  return blockers;
}

function firmwareSelectionBlockers(selectedPath: FirmwareUpgradePath | null, selectedFirmware: string): string[] {
  const blockers: string[] = [];
  if (!selectedPath) {
    blockers.push("Select a firmware path before validation or upgrade.");
  }
  if (!selectedFirmware.trim()) {
    blockers.push("Selected firmware, image, or target version is required.");
  }
  return blockers;
}

export function supportedUpgradeActionId(path: FirmwareUpgradePath | null): string | null {
  if (path?.component_id === "netapp_ontap_version") {
    return "netapp.ontap-upgrade-apply";
  }
  return null;
}

export function upgradeConfirmationPhrase(path: FirmwareUpgradePath | null, action?: WorkflowAction | null): string {
  const registeredPhrase = action?.required_confirmations.find((phrase) => phrase.trim());
  if (registeredPhrase) return registeredPhrase;
  return supportedUpgradeActionId(path) === "netapp.ontap-upgrade-apply" ? "UPGRADE ONTAP" : "RUN FIRMWARE UPGRADE";
}

export function firmwareValidationMatchesSelection(
  result: OperationResult | null,
  path: FirmwareUpgradePath | null,
  selectedFirmware: string,
  config?: ControlConfig
): boolean {
  if (!result || !path) return false;
  const selectionMatches =
    stringValue(result.raw.selected_component, "") === path.component_id &&
    stringValue(result.raw.selected_target, "") === selectedPathTarget(path) &&
    stringValue(result.raw.selected_firmware, "") === selectedFirmware.trim();
  if (!selectionMatches) return false;
  if (!config) return true;
  return configSnapshotsMatch(result.raw.config_snapshot, sanitizedConfigSnapshot(config));
}

export function firmwareValidationPassed(result: OperationResult | null): boolean {
  return Boolean(result && ["ready", "success"].includes(result.status));
}

function upgradeActionForRequest(request: FirmwareUpgradeRequest): WorkflowAction | null {
  const supportedActionId = supportedUpgradeActionId(request.selectedPath);
  return request.actions.find((candidate) => candidate.action_id === supportedActionId) ?? null;
}

function firmwareSelectionRaw(
  config: ControlConfig,
  selectedPath: FirmwareUpgradePath | null,
  selectedFirmware: string
): Record<string, unknown> {
  return {
    config_snapshot: sanitizedConfigSnapshot(config),
    selected_component: selectedPath?.component_id ?? null,
    selected_device: selectedPath?.device_label ?? null,
    selected_firmware: selectedFirmware.trim(),
    selected_target: selectedPath ? selectedPathTarget(selectedPath) : null
  };
}

function selectedPathTarget(path: FirmwareUpgradePath): string {
  return path.target_version || path.package_name || path.selected_file_name || "unknown";
}

function firmwareScopeForPath(path: FirmwareUpgradePath): "hpe" | "cisco" | "netapp" | "full" {
  if (path.component_id.startsWith("netapp_")) return "netapp";
  if (path.component_id.startsWith("cisco_")) return "cisco";
  if (path.component_id.startsWith("hpe_")) return "hpe";
  return "full";
}

function hasCredentialDraftForVersion(draft: CredentialDraft, version: SnmpVersion): boolean {
  if (version === "v2") {
    return draft.snmpV2Community.trim().length > 0;
  }
  return [draft.snmpV3Username, draft.snmpV3AuthPassword, draft.snmpV3PrivacyPassword].every(
    (value) => value.trim().length > 0
  );
}

function validApiBaseUrl(value: string): boolean {
  const trimmed = value.trim();
  return !trimmed || trimmed === "same-origin" || trimmed.startsWith("/") || /^https?:\/\//i.test(trimmed);
}

function sanitizedConfigSnapshot(config: ControlConfig): Record<string, unknown> {
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

function configSnapshotsMatch(candidate: unknown, expected: Record<string, unknown>): boolean {
  if (!candidate || typeof candidate !== "object") return false;
  const snapshot = candidate as Record<string, unknown>;
  return Object.entries(expected).every(([key, value]) => snapshot[key] === value);
}

function mapStatus(status: string, blockers: string[]): OperationStatus {
  const normalized = String(status || "").toLowerCase();
  if (blockers.length && !["completed", "success", "ok", "passed", "ready", "current"].includes(normalized)) {
    return "blocked";
  }
  if (["completed", "success", "ok", "passed", "ready", "current", "compliant"].includes(normalized)) {
    return "success";
  }
  if (["blocked", "manual_command_required", "not_configured"].includes(normalized)) {
    return "blocked";
  }
  if (["failed", "error", "unavailable"].includes(normalized)) {
    return "failed";
  }
  if (["pending", "not_checked", "unknown"].includes(normalized)) {
    return "pending";
  }
  return blockers.length ? "blocked" : "success";
}

function firmwareRuntimeActionIds(actions: WorkflowAction[]): string[] {
  const ids = actions
    .filter((action) => {
      const id = action.action_id.toLowerCase();
      return (
        action.stage === "firmware" ||
        action.category === "upgrade" ||
        id.includes("firmware") ||
        id.includes("ontap-upgrade")
      );
    })
    .map((action) => action.action_id);
  return Array.from(new Set(ids)).slice(0, 12);
}

function firmwareOperationType(actionId: string): OperationResult["type"] {
  const normalized = actionId.toLowerCase();
  if (/(apply|upgrade-apply)/.test(normalized)) return "firmware-upgrade";
  if (/(validate|compliance|waiver)/.test(normalized)) return "firmware-validation";
  return "firmware-check";
}

function upgradeStatusFromOperation(status: OperationStatus): UpgradeStatus {
  if (status === "running") return "upgrading";
  if (status === "ready") return "ready";
  if (status === "success") return "success";
  if (status === "failed") return "failed";
  if (status === "blocked") return "blocked";
  if (status === "pending") return "pending";
  return "idle";
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
}

function stringValue(value: unknown, fallback: string): string {
  return typeof value === "string" && value ? value : fallback;
}

async function safeCall<T>(fn: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await fn();
  } catch {
    return fallback;
  }
}

function unknownErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function clampNumber(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, value));
}

function readStored<T>(key: string): T | null {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function writeStored(key: string, value: unknown): void {
  window.localStorage.setItem(key, JSON.stringify(value));
}

function removeStored(key: string): void {
  window.localStorage.removeItem(key);
}

function humanize(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
