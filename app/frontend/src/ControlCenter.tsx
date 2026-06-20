import {
  Database,
  Activity,
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  Cpu,
  FileText,
  Gauge,
  History,
  Play,
  Plus,
  RefreshCw,
  Save,
  Settings as SettingsIcon,
  ShieldCheck,
  SlidersHorizontal,
  TerminalSquare,
  Trash2,
  UploadCloud,
  Wrench,
  XCircle
} from "lucide-react";
import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";

import { api } from "./api";
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
import type {
  AuditEvent,
  FirmwareSummary,
  FirmwareUpgradePath,
  LabAddressPlan,
  LabGlobalSettings,
  LabProfile,
  LabProfileDevices,
  LabProfileFeatures,
  LabProfileList,
  LabProfileWrite,
  ProviderStatus,
  WorkflowAction
} from "./types";

const navItems = [
  { icon: <Gauge size={18} />, label: "Dashboard", to: "/dashboard" },
  { icon: <SlidersHorizontal size={18} />, label: "Configure", to: "/configure" },
  { icon: <Play size={18} />, label: "Run", to: "/run" },
  { icon: <UploadCloud size={18} />, label: "Firmware", to: "/firmware" },
  { icon: <ClipboardList size={18} />, label: "Results", to: "/results" },
  { icon: <History size={18} />, label: "Logs", to: "/logs" },
  { icon: <SettingsIcon size={18} />, label: "Settings", to: "/settings" }
];

type ProfileDeviceKey = "cisco" | "server" | "storage" | "esxi" | "netapp" | "vcenter";
type ConfigureTabKey = "lab" | ProfileDeviceKey;
type FirmwareTabKey = "overview" | ProfileDeviceKey;
type ProfileEditorMode = "existing" | "new";

type ProfileDeviceDefinition = {
  addressFields: Array<keyof LabAddressPlan>;
  icon: ReactNode;
  key: ProfileDeviceKey;
  label: string;
  summary: string;
};

type ProfileDeviceSelection = Record<ProfileDeviceKey, boolean>;

type ProfileEditorState = {
  addressPlan: LabAddressPlan;
  description: string;
  devices: LabProfileDevices;
  deviceSelection: ProfileDeviceSelection;
  dnsText: string;
  features: LabProfileFeatures;
  gateway: string;
  id: string | null;
  mode: ProfileEditorMode;
  mtu: string;
  name: string;
  ntpText: string;
  profileTopology: "high_address_lab" | "compact_edge_lab" | "custom";
  subnet: string;
  vlanId: string;
};

type StorageDriveAllocation = {
  controller_path: string;
  drive_bays: string;
  drive_count: string;
  id: string;
  notes: string;
  raid_level: string;
  role: string;
  volume_name: string;
};

type IloControllerInventory = {
  adapterType: string | null;
  firmwareVersion: string | null;
  health: string | null;
  id: string;
  location: string | null;
  model: string | null;
  name: string;
  protocol: string | null;
  state: string | null;
};

type IloFirmwareInventory = {
  biosVersion: string | null;
  controllers: IloControllerInventory[];
  iloFirmware: string | null;
  smartArrayFirmware: string | null;
  status: string;
};

const profileDeviceDefinitions: ProfileDeviceDefinition[] = [
  {
    addressFields: ["cisco_management", "ansible_control_host"],
    icon: <TerminalSquare size={16} />,
    key: "cisco",
    label: "Cisco",
    summary: "Switch management, console bootstrap, VLAN, and SNMP planning."
  },
  {
    addressFields: ["ilo", "ilo_initial", "server_embedded_nic"],
    icon: <Cpu size={16} />,
    key: "server",
    label: "Server / iLO",
    summary: "Server identity, embedded NIC, iLO management, first-boot access, and firmware baseline."
  },
  {
    addressFields: [],
    icon: <Database size={16} />,
    key: "storage",
    label: "Internal Storage",
    summary: "Local controller, RAID volumes, drive groups, spare policy, and apply/reboot planning."
  },
  {
    addressFields: ["esxi_management"],
    icon: <ShieldCheck size={16} />,
    key: "esxi",
    label: "ESXi",
    summary: "ESXi management, datastore, vSwitch, DNS, and NTP defaults."
  },
  {
    addressFields: [
      "netapp_controller_a_sp",
      "netapp_controller_b_sp",
      "netapp_cluster_mgmt",
      "netapp_node_a_mgmt",
      "netapp_node_b_mgmt",
      "netapp_svm_mgmt",
      "netapp_nfs_lifs",
      "netapp_iscsi_lifs"
    ],
    icon: <Database size={16} />,
    key: "netapp",
    label: "NetApp",
    summary: "Cluster, node, SVM, SP, NFS, iSCSI, MTU, and storage defaults."
  },
  {
    addressFields: [],
    icon: <Gauge size={16} />,
    key: "vcenter",
    label: "vCenter",
    summary: "vCenter, datacenter, cluster, datastore, and ESXi attachment defaults."
  }
];

const defaultDeviceSelection: ProfileDeviceSelection = {
  cisco: true,
  esxi: true,
  netapp: true,
  server: true,
  storage: true,
  vcenter: false
};

const emptyAddressPlan: LabAddressPlan = {
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

const defaultProfileFeatures: LabProfileFeatures = {
  block_legacy_protocols: true,
  build_verification_enabled: true,
  disable_ipv6: true,
  enable_dns: true,
  enable_ntp: true,
  enable_snmp: false,
  firmware_gate_enabled: true,
  netapp_disabled_reason: null,
  netapp_enabled: true,
  storage_protocol: "nfs",
  vcenter_disabled_reason: "vCenter is disabled by the active lab setup.",
  vcenter_enabled: false
};

type ControlCenterContext = {
  actions: WorkflowAction[];
  auditEvents: AuditEvent[];
  backendLogs: ControlLogEntry[];
  checkFirmware: (targetOverride?: string, usernameReference?: string) => Promise<void>;
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
  labProfiles: LabProfileList | null;
  loadError: string;
  loading: boolean;
  logs: ControlLogEntry[];
  activateLabProfile: (profileId: string) => Promise<void>;
  deleteLabProfile: (profileId: string) => Promise<void>;
  editLabProfile: (profileId: string) => void;
  profileDeleting: boolean;
  profileActivating: boolean;
  profileEditor: ProfileEditorState;
  profileErrors: string[];
  profileMessage: string;
  profileSaving: boolean;
  recalculateProfileDefaults: () => void;
  saveLabProfile: () => Promise<boolean>;
  setProfileEditor: (value: ProfileEditorState | ((current: ProfileEditorState) => ProfileEditorState)) => void;
  startNewLabProfile: () => void;
  providers: ProviderStatus[];
  refreshControlCenter: () => Promise<void>;
  runError: string;
  runSelectedAction: () => Promise<void>;
  runStatus: OperationStatus;
  saveConfig: () => Promise<boolean>;
  saveSettings: () => Promise<boolean>;
  selectedAction: WorkflowAction | null;
  selectedRunActionId: string;
  selectedFirmware: string;
  selectedPath: FirmwareUpgradePath | null;
  selectedPathId: string;
  selectedUpgradeAction: WorkflowAction | null;
  setConfig: (value: ControlConfig | ((current: ControlConfig) => ControlConfig)) => void;
  setCredentialDraft: (value: CredentialDraft | ((current: CredentialDraft) => CredentialDraft)) => void;
  setSelectedRunActionId: (value: string) => void;
  setSelectedFirmware: (value: string) => void;
  setSelectedPathId: (value: string) => void;
  setSettings: (value: ControlSettings | ((current: ControlSettings) => ControlSettings)) => void;
  settings: ControlSettings;
  settingsErrors: string[];
  settingsMessage: string;
  settingsSaving: boolean;
  startFirmwareUpgrade: (targetOverride?: string) => Promise<void>;
  targetSummary: string;
  upgradeConfirmationAccepted: boolean;
  upgradeConfirmationPhrase: string;
  upgradeStatus: UpgradeStatus;
  validateFirmware: (targetOverride?: string) => Promise<void>;
  setUpgradeConfirmationAccepted: (value: boolean) => void;
  setUpgradeConfirmationPhrase: (value: string) => void;
};

type ActiveOperation = {
  detail: string;
  key: string;
  phases: string[];
  progressCeiling?: number;
  title: string;
};

export default function ControlCenter() {
  const [health, setHealth] = useState<HealthState | null>(null);
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [actions, setActions] = useState<WorkflowAction[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [backendLogs, setBackendLogs] = useState<ControlLogEntry[]>([]);
  const [firmware, setFirmware] = useState<FirmwareState>({ fileSelections: null, latestInventory: null, summaries: [] });
  const [firmwareRuntime, setFirmwareRuntime] = useState<FirmwareRuntimeStatus>(defaultFirmwareRuntimeStatus);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [config, setConfig] = useState<ControlConfig>(() => configAdapter.load());
  const [credentialDraft, setCredentialDraft] = useState<CredentialDraft>(defaultCredentialDraft);
  const [configErrors, setConfigErrors] = useState<string[]>([]);
  const [configMessage, setConfigMessage] = useState("");
  const [configSaving, setConfigSaving] = useState(false);
  const [labProfiles, setLabProfiles] = useState<LabProfileList | null>(null);
  const [profileEditor, setProfileEditorState] = useState<ProfileEditorState>(() => newProfileEditor(config));
  const [profileErrors, setProfileErrors] = useState<string[]>([]);
  const [profileMessage, setProfileMessage] = useState("");
  const [profileActivating, setProfileActivating] = useState(false);
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileDeleting, setProfileDeleting] = useState(false);

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
  const [selectedRunActionId, setSelectedRunActionId] = useState("");

  const configEditedRef = useRef(false);
  const settingsEditedRef = useRef(false);
  const firmwareSelectionEditedRef = useRef(false);
  const configSaveInFlightRef = useRef(false);
  const settingsSaveInFlightRef = useRef(false);
  const profileSaveInFlightRef = useRef(false);
  const profileDeleteInFlightRef = useRef(false);
  const profileEditedRef = useRef(false);
  const runInFlightRef = useRef(false);
  const firmwareCheckInFlightRef = useRef(false);
  const firmwareGateInFlightRef = useRef(false);

  const defaultSelectedAction = useMemo(() => runAdapter.selectAction(actions), [actions]);
  const selectedAction = useMemo(
    () => actions.find((action) => action.action_id === selectedRunActionId) ?? defaultSelectedAction,
    [actions, defaultSelectedAction, selectedRunActionId]
  );
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
    if (!actions.length) return;
    if (selectedRunActionId && actions.some((action) => action.action_id === selectedRunActionId)) return;
    setSelectedRunActionId(defaultSelectedAction?.action_id ?? "");
  }, [actions, defaultSelectedAction?.action_id, selectedRunActionId]);

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
      setFirmware((current) => ({
        ...snapshot.firmware,
        latestInventory: snapshot.firmware.latestInventory ?? current.latestInventory
      }));
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
      try {
        const profileList = await api.labProfiles();
        setLabProfiles(profileList);
        setProfileErrors([]);
        if (!profileEditedRef.current) {
          setProfileEditorState(profileEditorFromProfile(profileList.active_profile, config));
        }
      } catch (profileError) {
        setProfileErrors([`Lab profile API unavailable: ${errorMessage(profileError)}`]);
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

  function updateProfileEditor(value: ProfileEditorState | ((current: ProfileEditorState) => ProfileEditorState)) {
    profileEditedRef.current = true;
    setProfileEditorState(value);
    setProfileMessage("");
    setProfileErrors([]);
  }

  function startNewLabProfile() {
    profileEditedRef.current = true;
    setProfileEditorState(newProfileEditor(config, labProfiles?.active_profile));
    setProfileMessage("New lab profile draft. Save it before running profile-based work.");
    setProfileErrors([]);
  }

  function editLabProfile(profileId: string) {
    const selected = labProfiles?.profiles.find((profile) => profile.id === profileId);
    if (!selected) return;
    profileEditedRef.current = false;
    setProfileEditorState(profileEditorFromProfile(selected, config));
    setProfileMessage(`Editing ${selected.name}.`);
    setProfileErrors([]);
  }

  async function activateLabProfile(profileId: string) {
    if (profileSaveInFlightRef.current || profileDeleteInFlightRef.current || profileActivating) return;
    setProfileActivating(true);
    try {
      setProfileErrors([]);
      const profileList = await api.activateLabProfile(profileId);
      setLabProfiles(profileList);
      profileEditedRef.current = false;
      setProfileEditorState(profileEditorFromProfile(profileList.active_profile, config));
      setProfileMessage(`Active profile changed to ${profileList.active_profile.name}.`);
      addLog({
        detail: profileList.active_profile.subnet_cidr ?? "No subnet recorded.",
        message: "Lab profile selected",
        status: "selected",
        type: "config"
      });
    } catch (error) {
      setProfileErrors([errorMessage(error)]);
    } finally {
      setProfileActivating(false);
    }
  }

  async function saveLabProfile(): Promise<boolean> {
    if (profileSaveInFlightRef.current) return false;
    const errors = validateProfileEditor(profileEditor);
    if (errors.length) {
      setProfileErrors(errors);
      setProfileMessage("");
      return false;
    }

    profileSaveInFlightRef.current = true;
    setProfileSaving(true);
    try {
      setProfileErrors([]);
      const payload = profilePayloadFromEditor(profileEditor);
      const saved =
        profileEditor.mode === "existing" && profileEditor.id
          ? await api.updateLabProfile(profileEditor.id, payload)
          : await api.createLabProfile(payload);
      const profileList = await api.activateLabProfile(saved.id);
      setLabProfiles(profileList);
      profileEditedRef.current = false;
      setProfileEditorState(profileEditorFromProfile(profileList.active_profile, config));
      setProfileMessage(`Lab profile ${saved.name} saved.`);
      addLog({
        detail: `${saved.name}; ${saved.subnet_cidr ?? payload.subnet_cidr ?? "No subnet"}; ${includedDeviceLabels(profileEditor.deviceSelection)}.`,
        message: "Lab profile saved",
        status: "saved",
        type: "config"
      });
      return true;
    } catch (error) {
      setProfileErrors([errorMessage(error)]);
      setProfileMessage("");
      return false;
    } finally {
      profileSaveInFlightRef.current = false;
      setProfileSaving(false);
    }
  }

  async function deleteLabProfile(profileId: string) {
    if (profileDeleteInFlightRef.current) return;
    profileDeleteInFlightRef.current = true;
    setProfileDeleting(true);
    try {
      setProfileErrors([]);
      const profileList = await api.deleteLabProfile(profileId);
      setLabProfiles(profileList);
      profileEditedRef.current = false;
      setProfileEditorState(profileEditorFromProfile(profileList.active_profile, config));
      setProfileMessage("Saved lab profile deleted.");
      addLog({ detail: profileId, message: "Lab profile deleted", status: "deleted", type: "config" });
    } catch (error) {
      setProfileErrors([errorMessage(error)]);
    } finally {
      profileDeleteInFlightRef.current = false;
      setProfileDeleting(false);
    }
  }

  function recalculateProfileDefaults() {
    updateProfileEditor((current) => {
      const defaults = profileDefaultsForSubnet(current.subnet);
      return {
        ...current,
        addressPlan: {
          ...current.addressPlan,
          ...defaults.addressPlan
        },
        deviceSelection: {
          ...current.deviceSelection,
          netapp: current.deviceSelection.netapp && defaults.netappSupported
        },
        features: {
          ...current.features,
          netapp_disabled_reason: defaults.netappSupported ? null : "NetApp high-address defaults require a /24 or larger lab subnet.",
          netapp_enabled: current.deviceSelection.netapp && defaults.netappSupported,
          storage_protocol: current.deviceSelection.netapp && defaults.netappSupported ? current.features.storage_protocol || "nfs" : "none"
        },
        gateway: defaults.gateway,
        profileTopology: defaults.profileTopology
      };
    });
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

  async function syncConfigForAction(configOverride?: ControlConfig): Promise<{
    config: ControlConfig;
    configChanged: boolean;
    errors: string[];
    savedVia: "backend" | "local_fallback";
  }> {
    const actionConfig = configOverride ?? config;
    if (configSaveInFlightRef.current) {
      return {
        config: actionConfig,
        configChanged: false,
        errors: ["Configuration save is already in progress."],
        savedVia: "local_fallback"
      };
    }
    configSaveInFlightRef.current = true;
    setConfigSaving(true);
    const hadPendingConfig =
      configEditedRef.current ||
      credentialDraftHasValues(credentialDraft) ||
      (configOverride ? !sameControlConfig(configOverride, config) : false);
    try {
      const result = await configAdapter.save(actionConfig, credentialDraft);
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

  async function checkFirmware(targetOverride?: string, usernameReference?: string) {
    if (firmwareCheckInFlightRef.current || firmwareCheckStatus === "running") return;
    firmwareCheckInFlightRef.current = true;
    try {
      setFirmwareCheckStatus("running");
      const actionConfig = configWithTargetOverride(config, targetOverride);
      const syncResult = await syncConfigForAction(actionConfig);
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
        const response = await firmwareAdapter.check(currentConfig, { usernameReference });
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

  async function validateFirmware(targetOverride?: string) {
    if (firmwareGateInFlightRef.current || upgradeStatus === "validating" || upgradeStatus === "upgrading") return;
    firmwareGateInFlightRef.current = true;
    const actionConfig = configWithTargetOverride(config, targetOverride);
    try {
      clearFirmwareGateResults();
      const preflightBlockers = firmwareValidateBlockers({ config: actionConfig, selectedFirmware, selectedPath });
      if (preflightBlockers.length > 0) {
        const result = createLocalOperationResult({
          blockers: preflightBlockers,
          message: "Firmware validation blocked until the current config and firmware selection are complete.",
          raw: firmwareSelectionSnapshot(actionConfig, selectedPath, selectedFirmware),
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
      const syncResult = await syncConfigForAction(actionConfig);
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

  async function startFirmwareUpgrade(targetOverride?: string) {
    if (firmwareGateInFlightRef.current || upgradeStatus === "upgrading" || upgradeStatus === "validating") return;
    firmwareGateInFlightRef.current = true;
    const actionConfig = configWithTargetOverride(config, targetOverride);
    try {
      const preflightBlockers = firmwareStartBlockers({
        accepted: upgradeConfirmationAccepted,
        config: actionConfig,
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
          raw: firmwareSelectionSnapshot(actionConfig, selectedPath, selectedFirmware),
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

      const syncResult = await syncConfigForAction(actionConfig);
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
    labProfiles,
    loadError,
    loading,
    logs,
    activateLabProfile,
    deleteLabProfile,
    editLabProfile,
    profileDeleting,
    profileActivating,
    profileEditor,
    profileErrors,
    profileMessage,
    profileSaving,
    recalculateProfileDefaults,
    saveLabProfile,
    setProfileEditor: updateProfileEditor,
    startNewLabProfile,
    providers,
    refreshControlCenter,
    runError,
    runSelectedAction,
    runStatus,
    saveConfig,
    saveSettings,
    selectedAction,
    selectedRunActionId,
    selectedFirmware,
    selectedPath,
    selectedPathId,
    selectedUpgradeAction,
    setConfig: updateConfig,
    setCredentialDraft: updateCredentialDraft,
    setSelectedRunActionId,
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
        <ActiveOperationBar context={context} />
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

function ActiveOperationBar({ context }: { context: ControlCenterContext }) {
  const operation = activeOperationForContext(context);
  const [startedAt, setStartedAt] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!operation) return;
    const timestamp = Date.now();
    setStartedAt(timestamp);
    setNow(timestamp);
    const interval = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [operation?.key]);

  if (!operation) return null;

  const elapsedMs = now - startedAt;
  const phaseIndex = Math.min(operation.phases.length - 1, Math.floor(elapsedMs / 12000));
  const phase = operation.phases[phaseIndex] ?? operation.phases[operation.phases.length - 1] ?? "Monitoring";
  const progressCeiling = operation.progressCeiling ?? 88;
  const progress = Math.min(progressCeiling, 8 + Math.floor(elapsedMs / 1000) * 3);

  return (
    <section className="cc-active-operation" aria-live="polite" aria-label="Active operation">
      <div className="cc-active-operation-copy">
        <strong>{operation.title}</strong>
        <span>{operation.detail}</span>
      </div>
      <div
        className="cc-active-operation-meter"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={progress}
        aria-valuetext={`${phase}, ${progress}%`}
      >
        <span style={{ width: `${progress}%` }} />
      </div>
      <div className="cc-active-operation-phase">
        <span>{phase}</span>
        <time>{elapsedLabel(elapsedMs)}</time>
      </div>
    </section>
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
        <SectionTitle icon={<SlidersHorizontal size={18} />} title="Profile Devices" />
        <ProfileDeviceSummary context={context} />
      </section>

      <section className="cc-panel">
        <SectionTitle icon={<Activity size={18} />} title="Primary Workflow" />
        <ol className="cc-workflow-rail" aria-label="Primary workflow">
          <WorkflowStep label="Configure" state={context.config.target ? "Configured" : "Missing target"} to="/configure" />
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

function ProfileDeviceSummary({ context }: { context: ControlCenterContext }) {
  const profile = context.labProfiles?.active_profile;
  const selection = profile ? deviceSelectionFromProfile(profile, profile.features.netapp_enabled) : context.profileEditor.deviceSelection;
  const addressPlan = profile?.address_plan ?? context.profileEditor.addressPlan;
  const gateway = profile?.gateway ?? context.profileEditor.gateway;
  const rows = profileDeviceDefinitions.map((definition) => ({
    address: profileDeviceAddress(definition.key, addressPlan),
    included: selection[definition.key],
    label: definition.label
  }));

  if (!profile && context.loading) {
    return <LoadingState text="Loading profile devices" />;
  }

  return (
    <div className="cc-device-summary">
      <FactList
        facts={[
          ["Active profile", profile?.name ?? context.profileEditor.name],
          ["Subnet", profile?.subnet_cidr ?? context.profileEditor.subnet],
          ["Gateway", gateway || "Not set"],
          ["Profile state", profile?.source ? sourceLabel(profile.source) : "Draft or unavailable"]
        ]}
      />
      <div className="cc-device-list">
        {rows.map((row) => (
          <div className={row.included ? "" : "is-excluded"} key={row.label}>
            <strong>{row.label}</strong>
            <span>{row.included ? row.address || "Included, IP not set" : "Excluded from this profile"}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ConfigurePage({ context }: { context: ControlCenterContext }) {
  const [activeTab, setActiveTab] = useState<ConfigureTabKey>("lab");
  const activeProfile = context.labProfiles?.active_profile;
  const includedCount = profileDeviceDefinitions.filter((definition) => context.profileEditor.deviceSelection[definition.key]).length;
  const profileSubnetSummary = activeProfile?.subnet_cidr ?? context.profileEditor.subnet ?? "no subnet";

  return (
    <Page title="Configure">
      <section className="cc-panel cc-profile-summary">
        <div>
          <SectionTitle icon={<SlidersHorizontal size={18} />} title="Active Profile" />
          <p className="cc-muted">
            {activeProfile
              ? `${activeProfile.name} uses ${profileSubnetSummary} and includes ${includedCount} hardware tabs.`
              : "Profile data is loading or unavailable."}
          </p>
        </div>
        <FactList
          facts={[
            ["Lab", context.profileEditor.name || "Unnamed lab"],
            ["Subnet", context.profileEditor.subnet || "Not set"],
            ["Included hardware", includedDeviceLabels(context.profileEditor.deviceSelection)],
            ["Profile source", activeProfile?.source ? sourceLabel(activeProfile.source) : "Not loaded"]
          ]}
        />
      </section>

      <div className="cc-configure-tabs" role="tablist" aria-label="Configure sections">
        <button
          aria-selected={activeTab === "lab"}
          className={activeTab === "lab" ? "is-active" : ""}
          onClick={() => setActiveTab("lab")}
          role="tab"
          type="button"
        >
          <SlidersHorizontal size={16} />
          Lab
        </button>
        {profileDeviceDefinitions.map((definition) => {
          const included = context.profileEditor.deviceSelection[definition.key];
          return (
            <button
              aria-selected={activeTab === definition.key}
              className={`${activeTab === definition.key ? "is-active" : ""} ${included ? "" : "is-excluded"}`}
              key={definition.key}
              onClick={() => setActiveTab(definition.key)}
              role="tab"
              type="button"
            >
              {definition.icon}
              {definition.label}
            </button>
          );
        })}
      </div>

      {activeTab === "lab" ? (
        <LabProfileTab context={context} />
      ) : (
        <EquipmentProfileTab context={context} definition={profileDeviceDefinitions.find((definition) => definition.key === activeTab)!} />
      )}

      {context.profileErrors.length > 0 && <IssueList title="Profile errors" items={context.profileErrors} />}
      {context.configMessage && <Banner tone="good">{context.configMessage}</Banner>}
      {context.profileMessage && <Banner tone="info">{context.profileMessage}</Banner>}
    </Page>
  );
}

function LabProfileTab({ context }: { context: ControlCenterContext }) {
  const savedProfiles = context.labProfiles?.profiles ?? [];
  const activeProfileId = context.labProfiles?.active_profile.id ?? "";
  const deleteDisabled = !activeProfileId || activeProfileId === "runtime" || context.profileDeleting || context.profileActivating;
  const profileSelectDisabled = !context.labProfiles || context.profileActivating || context.profileSaving || context.profileDeleting;
  return (
    <>
      <section className="cc-panel">
        <div className="cc-panel-head">
          <SectionTitle icon={<SlidersHorizontal size={18} />} title="Lab Profile" />
          <ActionRow>
            <button onClick={context.startNewLabProfile} type="button">New profile</button>
            <button
              disabled={!activeProfileId || activeProfileId === "runtime" || context.profileActivating}
              onClick={() => context.editLabProfile(activeProfileId)}
              type="button"
            >
              Edit profile
            </button>
            <button
              disabled={deleteDisabled}
              onClick={() => {
                if (activeProfileId && window.confirm("Delete this saved lab profile?")) {
                  void context.deleteLabProfile(activeProfileId);
                }
              }}
              type="button"
            >
              {context.profileDeleting ? "Deleting" : "Delete profile"}
            </button>
          </ActionRow>
        </div>

        <div className="cc-form-grid">
          <label className="cc-field">
            <span>Active lab profile</span>
            <select
              disabled={profileSelectDisabled}
              onChange={(event) => void context.activateLabProfile(event.target.value)}
              value={activeProfileId}
            >
              <option value="runtime">Runtime environment</option>
              {savedProfiles.map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profile.name}
                </option>
              ))}
            </select>
          </label>
          <label className="cc-field">
            <span>Lab name</span>
            <input
              onChange={(event) => updateProfileField(context, "name", event.target.value)}
              placeholder="Lab-Uplands-G10"
              type="text"
              value={context.profileEditor.name}
            />
          </label>
          <label className="cc-field cc-span-2">
            <span>Description</span>
            <textarea
              onChange={(event) => updateProfileField(context, "description", event.target.value)}
              placeholder="Short operator note for this lab profile"
              rows={2}
              value={context.profileEditor.description}
            />
          </label>
          <label className="cc-field">
            <span>Subnet CIDR</span>
            <input
              onChange={(event) => updateProfileSubnet(context, event.target.value)}
              placeholder="192.168.1.0/24"
              type="text"
              value={context.profileEditor.subnet}
            />
          </label>
          <label className="cc-field">
            <span>Gateway</span>
            <input
              onChange={(event) => updateProfileField(context, "gateway", event.target.value)}
              placeholder="192.168.1.1"
              type="text"
              value={context.profileEditor.gateway}
            />
          </label>
          <label className="cc-field">
            <span>DNS servers</span>
            <input
              onChange={(event) => updateProfileField(context, "dnsText", event.target.value)}
              placeholder="192.168.1.1, 1.1.1.1"
              type="text"
              value={context.profileEditor.dnsText}
            />
          </label>
          <label className="cc-field">
            <span>NTP servers</span>
            <input
              onChange={(event) => updateProfileField(context, "ntpText", event.target.value)}
              placeholder="192.168.1.1"
              type="text"
              value={context.profileEditor.ntpText}
            />
          </label>
          <label className="cc-field">
            <span>Management VLAN</span>
            <input
              onChange={(event) => updateProfileField(context, "vlanId", event.target.value)}
              placeholder="1"
              type="text"
              value={context.profileEditor.vlanId}
            />
          </label>
          <label className="cc-field">
            <span>MTU</span>
            <input
              max={9216}
              min={576}
              onChange={(event) => updateProfileField(context, "mtu", event.target.value)}
              placeholder="1500"
              type="number"
              value={context.profileEditor.mtu}
            />
          </label>
        </div>

        <div className="cc-hardware-picker" aria-label="Hardware included in this profile">
          {profileDeviceDefinitions.map((definition) => (
            <label className="cc-check-card" key={definition.key}>
              <input
                checked={context.profileEditor.deviceSelection[definition.key]}
                onChange={(event) => updateProfileDeviceSelection(context, definition.key, event.target.checked)}
                type="checkbox"
              />
              <span>
                <strong>{definition.label}</strong>
                <small>{definition.summary}</small>
              </span>
            </label>
          ))}
        </div>

        <ActionRow>
          <button onClick={context.recalculateProfileDefaults} type="button">
            <RefreshCw size={16} />
            Recalculate IP defaults
          </button>
          <button className="primary" disabled={context.profileSaving || context.profileActivating} onClick={() => void context.saveLabProfile()} type="button">
            <Save size={16} />
            {context.profileSaving ? "Saving profile" : "Save lab profile"}
          </button>
        </ActionRow>
      </section>

      <RunDefaultsPanel context={context} />
    </>
  );
}

function RunDefaultsPanel({ context }: { context: ControlCenterContext }) {
  return (
    <section className="cc-panel">
      <SectionTitle icon={<Play size={18} />} title="Run Defaults" />
      <div className="cc-form-grid">
        <label className="cc-field cc-span-2">
          <span>Target host, IP, or range</span>
          <input
            onChange={(event) => context.setConfig((current) => ({ ...current, target: event.target.value }))}
            placeholder={context.profileEditor.subnet || "192.0.2.203 or 192.0.2.0/24"}
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

      <details className="cc-details">
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

      <FactList
        facts={[
          ["Credential state", credentialConfigLabel(context.config)],
          ["Config adapter", configAdapter.backendStatus],
          ["Last saved", context.config.updatedAt ? formatDateTime(context.config.updatedAt) : "Not saved"]
        ]}
      />
      {context.configErrors.length > 0 && <IssueList title="Validation errors" items={context.configErrors} />}
      <ActionRow>
        <button className="primary" disabled={context.configSaving} onClick={() => void context.saveConfig()} type="button">
          <Save size={16} />
          {context.configSaving ? "Saving config" : "Save / apply config"}
        </button>
      </ActionRow>
    </section>
  );
}

function EquipmentProfileTab({
  context,
  definition
}: {
  context: ControlCenterContext;
  definition: ProfileDeviceDefinition;
}) {
  const included = context.profileEditor.deviceSelection[definition.key];
  return (
    <section className={`cc-panel cc-equipment-panel ${included ? "" : "is-excluded"}`}>
      <div className="cc-panel-head">
        <SectionTitle icon={definition.icon} title={definition.label} />
        <StatusPill status={included ? "included" : "excluded"} />
      </div>
      <p className="cc-muted">{definition.summary}</p>
      {!included ? (
        <Banner tone="info">This hardware is excluded from the active lab profile. Use the Lab tab to include it.</Banner>
      ) : (
        <>
          <FactList
            facts={[
              ["Profile subnet", context.profileEditor.subnet || "Not set"],
              ["Gateway", context.profileEditor.gateway || "Not set"],
              ["IP defaults", "Derived from the lab subnet and editable here"],
              ["Save target", context.profileEditor.mode === "existing" ? "Update saved profile" : "Create saved profile"]
            ]}
          />
          <DeviceAutoFillPanel context={context} definition={definition} />
          <DeviceAddressFields context={context} fields={definition.addressFields} />
          <DeviceSpecificFields context={context} deviceKey={definition.key} />
          <ActionRow>
            <button className="primary" disabled={context.profileSaving} onClick={() => void context.saveLabProfile()} type="button">
              <Save size={16} />
              {context.profileSaving ? "Saving profile" : "Save lab profile"}
            </button>
          </ActionRow>
        </>
      )}
    </section>
  );
}

function DeviceAutoFillPanel({
  context,
  definition
}: {
  context: ControlCenterContext;
  definition: ProfileDeviceDefinition;
}) {
  const facts = detectedDeviceFacts(context, definition.key);
  return (
    <div className="cc-subpanel cc-autofill-panel">
      <div className="cc-panel-head">
        <SectionTitle icon={<RefreshCw size={18} />} title="Detected Defaults" />
        <button onClick={() => applyDetectedProfileDefaults(context, definition.key)} type="button">
          <RefreshCw size={16} />
          Fill missing defaults
        </button>
      </div>
      <FactList facts={facts} />
    </div>
  );
}

function DeviceAddressFields({ context, fields }: { context: ControlCenterContext; fields: Array<keyof LabAddressPlan> }) {
  if (!fields.length) return null;
  return (
    <div className="cc-form-grid">
      {fields.map((field) => {
        const value = context.profileEditor.addressPlan[field];
        const isList = Array.isArray(value);
        return (
          <label className="cc-field" key={field}>
            <span>{addressPlanFieldLabel(field)}</span>
            <input
              onChange={(event) => updateProfileAddressPlan(context, field, event.target.value)}
              placeholder={isList ? "Comma-separated IPs" : "IP address"}
              type="text"
              value={isList ? value.join(", ") : value ?? ""}
            />
          </label>
        );
      })}
    </div>
  );
}

function DeviceSpecificFields({ context, deviceKey }: { context: ControlCenterContext; deviceKey: ProfileDeviceKey }) {
  if (deviceKey === "cisco") {
    return (
      <>
        <div className="cc-form-grid">
          <DeviceCredentialFields context={context} deviceKey={deviceKey} usernameLabel="Switch UID / username" passwordLabel="Switch password" />
          <DeviceDetailField context={context} deviceKey={deviceKey} field="enable_password" label="Enable password" placeholder="Optional enable secret" type="password" />
          <DeviceDetailField context={context} deviceKey={deviceKey} field="hostname" label="Switch hostname" placeholder="lab-switch-01" />
          <DeviceDetailField context={context} deviceKey={deviceKey} field="management_vlan" label="Management VLAN" placeholder={context.profileEditor.vlanId || "10"} />
          <DeviceDetailField context={context} deviceKey={deviceKey} field="console_port" label="Console port" placeholder="/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0" />
          <DeviceDetailField context={context} deviceKey={deviceKey} field="console_baud" label="Console baud" placeholder="9600" />
          <DeviceDetailField context={context} deviceKey={deviceKey} field="bootstrap_access_ports" label="Bootstrap access ports" placeholder="Gi1/0/1, Gi1/0/2" />
          <DeviceDetailField context={context} deviceKey={deviceKey} field="file_transfer_protocol" label="File transfer protocol" placeholder="SCP" />
          <DeviceDetailField context={context} deviceKey={deviceKey} field="ios_image" label="IOS XE image" placeholder="cat9k_iosxe.*.SPA.bin" />
          <DeviceDetailField context={context} deviceKey={deviceKey} field="snmp_location" label="SNMP location" placeholder="Lab rack" />
          <DeviceDetailField context={context} deviceKey={deviceKey} field="snmp_contact" label="SNMP contact" placeholder="Operator reference" />
        </div>
        <CiscoBootstrapFlowPanel context={context} />
      </>
    );
  }
  if (deviceKey === "server") {
    return (
      <div className="cc-form-grid">
        <DeviceCredentialFields context={context} deviceKey={deviceKey} usernameLabel="iLO UID / username" passwordLabel="iLO password" />
        <DeviceDetailField context={context} deviceKey={deviceKey} field="server_hostname" label="Server hostname" placeholder="lab-esxi-01" />
        <DeviceDetailField context={context} deviceKey={deviceKey} field="role" label="Server role" placeholder="ESXi host" />
        <DeviceDetailField context={context} deviceKey={deviceKey} field="install_media" label="Install media" placeholder="ESXi ISO or virtual media reference" />
        <DeviceDetailField context={context} deviceKey={deviceKey} field="rack_slot" label="Rack / slot" placeholder="Rack 1 U10" />
        <DeviceDetailField context={context} deviceKey={deviceKey} field="hostname" label="iLO hostname" placeholder="lab-server-ilo" />
        <DeviceDetailField context={context} deviceKey={deviceKey} field="current_firmware" label="Detected iLO firmware" placeholder="Filled from firmware inventory" />
        <DeviceDetailField context={context} deviceKey={deviceKey} field="bios_version" label="Detected BIOS version" placeholder="Filled from firmware inventory" />
        <DeviceDetailField context={context} deviceKey={deviceKey} field="firmware_baseline" label="Firmware baseline" placeholder="2.91" />
        <DeviceDetailField context={context} deviceKey={deviceKey} field="bios_profile" label="BIOS profile" placeholder="Virtualization host" />
      </div>
    );
  }
  if (deviceKey === "storage") {
    return (
      <>
        <div className="cc-form-grid">
          <DeviceCredentialFields context={context} deviceKey={deviceKey} usernameLabel="Storage UID / username" passwordLabel="Storage password" />
          <DeviceDetailField context={context} deviceKey={deviceKey} field="target_controller" label="Target controller" placeholder="Smart Array P440ar or primary controller" />
          <DeviceDetailField context={context} deviceKey={deviceKey} field="controller_path" label="Controller path" placeholder="/redfish/v1/Systems/1/SmartStorage/ArrayControllers/0" />
          <DeviceDetailField context={context} deviceKey={deviceKey} field="controller_firmware" label="Detected controller firmware" placeholder="Filled from firmware inventory" />
          <DeviceDetailField context={context} deviceKey={deviceKey} field="total_drive_bays" label="Total drive bays" placeholder="8" />
          <DeviceDetailField context={context} deviceKey={deviceKey} field="write_cache_policy" label="Write cache policy" placeholder="Default or disabled until battery health verified" />
          <DeviceDetailField context={context} deviceKey={deviceKey} field="stripe_size" label="Stripe size" placeholder="Default" />
          <DeviceDetailField context={context} deviceKey={deviceKey} field="apply_policy" label="Apply policy" placeholder="Plan and approve before apply" />
        </div>
        <StorageDriveAllocationList context={context} />
      </>
    );
  }
  if (deviceKey === "esxi") {
    return (
      <div className="cc-form-grid">
        <DeviceCredentialFields context={context} deviceKey={deviceKey} usernameLabel="ESXi UID / username" passwordLabel="ESXi password" />
        <DeviceDetailField context={context} deviceKey={deviceKey} field="hostname" label="ESXi hostname" placeholder="esxi01.lab.local" />
        <DeviceDetailField context={context} deviceKey={deviceKey} field="datastore" label="Default datastore" placeholder="datastore1" />
        <DeviceDetailField context={context} deviceKey={deviceKey} field="vswitch" label="vSwitch" placeholder="vSwitch0" />
        <DeviceDetailField context={context} deviceKey={deviceKey} field="vm_network" label="VM network" placeholder="VM Network" />
        <DeviceDetailField context={context} deviceKey={deviceKey} field="dns_domain" label="DNS domain" placeholder="lab.local" />
        <DeviceDetailField context={context} deviceKey={deviceKey} field="ntp_policy" label="NTP policy" placeholder="Use profile NTP servers" />
      </div>
    );
  }
  if (deviceKey === "netapp") {
    return (
      <div className="cc-form-grid">
        <DeviceCredentialFields context={context} deviceKey={deviceKey} usernameLabel="NetApp UID / username" passwordLabel="NetApp password" />
        <DeviceDetailField context={context} deviceKey={deviceKey} field="cluster_name" label="Cluster name" placeholder="lab-ontap" />
        <DeviceDetailField context={context} deviceKey={deviceKey} field="svm_name" label="SVM name" placeholder="svm_lab" />
        <label className="cc-field">
          <span>Storage protocol</span>
          <select
            onChange={(event) => updateProfileFeature(context, "storage_protocol", event.target.value)}
            value={context.profileEditor.features.storage_protocol}
          >
            <option value="nfs">NFS</option>
            <option value="iscsi">iSCSI</option>
            <option value="nfs_iscsi">NFS and iSCSI</option>
          </select>
        </label>
        <DeviceDetailField context={context} deviceKey={deviceKey} field="broadcast_domain" label="Broadcast domain" placeholder="Default" />
        <DeviceDetailField context={context} deviceKey={deviceKey} field="aggregate_name" label="Aggregate" placeholder="aggr1" />
        <DeviceDetailField context={context} deviceKey={deviceKey} field="volume_prefix" label="Volume prefix" placeholder="lab" />
      </div>
    );
  }
  return (
    <div className="cc-form-grid">
      <DeviceCredentialFields context={context} deviceKey={deviceKey} usernameLabel="vCenter UID / username" passwordLabel="vCenter password" />
      <DeviceDetailField context={context} deviceKey={deviceKey} field="endpoint" label="vCenter FQDN/IP" placeholder="vcenter.lab.local" />
      <DeviceDetailField context={context} deviceKey={deviceKey} field="datacenter" label="Datacenter" placeholder="Lab-DC" />
      <DeviceDetailField context={context} deviceKey={deviceKey} field="cluster" label="Cluster" placeholder="Lab-Cluster" />
      <DeviceDetailField context={context} deviceKey={deviceKey} field="datastore" label="Datastore" placeholder="NetApp-NFS" />
      <DeviceDetailField context={context} deviceKey={deviceKey} field="folder" label="VM folder" placeholder="Lab Builds" />
      <DeviceDetailField context={context} deviceKey={deviceKey} field="esxi_attach_policy" label="ESXi attach policy" placeholder="Attach configured ESXi hosts" />
    </div>
  );
}

function CiscoBootstrapFlowPanel({ context }: { context: ControlCenterContext }) {
  const editor = context.profileEditor;
  const consolePort = deviceDetailValue(editor, "cisco", "console_port") || "/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0";
  const baud = deviceDetailValue(editor, "cisco", "console_baud") || "9600";
  const managementIp = editor.addressPlan.cisco_management || "192.168.1.204";
  const vlan = deviceDetailValue(editor, "cisco", "management_vlan") || editor.vlanId || "10";
  const image = deviceDetailValue(editor, "cisco", "ios_image") || "Select IOS XE image";
  const protocol = deviceDetailValue(editor, "cisco", "file_transfer_protocol") || "SCP";
  return (
    <div className="cc-subpanel">
      <div className="cc-panel-head">
        <SectionTitle icon={<TerminalSquare size={18} />} title="Cisco Console Bootstrap" />
        <StatusPill status="planned" />
      </div>
      <FactList
        facts={[
          ["Console", `${consolePort} @ ${baud}`],
          ["First contact", "Prolific serial adapter, newline wakeup, terminal length 0, show version"],
          ["Management SVI", `Vlan${vlan} / ${managementIp}`],
          ["Access path", deviceDetailValue(editor, "cisco", "bootstrap_access_ports") || "Gi1/0/1 plus detected lab ports"],
          ["File transfer", `${protocol.toUpperCase()} over TCP/22 after ip scp server enable`],
          ["Image", image],
          ["Guarded executor", "app/backend/scripts/cisco_real_lab_workflow.py --apply"]
        ]}
      />
      <div className="cc-code" aria-label="Cisco bootstrap sequence">
        {[
          "discover console -> confirm privileged EXEC",
          `configure Vlan${vlan} ${managementIp}/24`,
          "generate SSH host key -> enable SSH v2 -> enable SCP server",
          "validate ping + SSH/SCP TCP/22",
          "copy IOS XE image to flash -> verify file before install planning"
        ].join("\n")}
      </div>
    </div>
  );
}

function DeviceDetailField({
  context,
  deviceKey,
  field,
  label,
  placeholder,
  type = "text"
}: {
  context: ControlCenterContext;
  deviceKey: ProfileDeviceKey;
  field: string;
  label: string;
  placeholder: string;
  type?: "password" | "text";
}) {
  return (
    <label className="cc-field">
      <span>{label}</span>
      <input
        autoComplete={type === "password" ? "current-password" : undefined}
        onChange={(event) => updateProfileDeviceDetail(context, deviceKey, field, event.target.value)}
        placeholder={placeholder}
        type={type}
        value={deviceDetailValue(context.profileEditor, deviceKey, field)}
      />
    </label>
  );
}

function DeviceCredentialFields({
  context,
  deviceKey,
  passwordLabel,
  usernameLabel
}: {
  context: ControlCenterContext;
  deviceKey: ProfileDeviceKey;
  passwordLabel: string;
  usernameLabel: string;
}) {
  return (
    <>
      <DeviceDetailField context={context} deviceKey={deviceKey} field="uid" label={usernameLabel} placeholder="Administrator or admin user" />
      <DeviceDetailField context={context} deviceKey={deviceKey} field="password" label={passwordLabel} placeholder="Enter password" type="password" />
    </>
  );
}

function StorageDriveAllocationList({ context }: { context: ControlCenterContext }) {
  const rows = storageDriveAllocationRows(context.profileEditor);
  return (
    <div className="cc-subpanel cc-storage-plan">
      <div className="cc-panel-head">
        <SectionTitle icon={<Database size={18} />} title="Drive Allocation List" />
        <button onClick={() => addStorageAllocation(context)} type="button">
          <Plus size={16} />
          Add drive group
        </button>
      </div>
      <div className="cc-storage-allocation-list">
        {rows.map((row) => (
          <div className="cc-storage-allocation-row" key={row.id}>
            <label className="cc-field">
              <span>Use</span>
              <select
                aria-label={`${driveAllocationRoleLabel(row.role)} use`}
                onChange={(event) => updateStorageAllocation(context, row.id, "role", event.target.value)}
                value={row.role}
              >
                <option value="esxi">ESXi</option>
                <option value="storage">Storage</option>
                <option value="spare">Hot spare</option>
                <option value="unused">Unused</option>
              </select>
            </label>
            <label className="cc-field">
              <span>Drive count</span>
              <input
                aria-label={`${driveAllocationRoleLabel(row.role)} drive count`}
                min={0}
                onChange={(event) => updateStorageAllocation(context, row.id, "drive_count", event.target.value)}
                type="number"
                value={row.drive_count}
              />
            </label>
            <label className="cc-field">
              <span>Drive bays</span>
              <input
                aria-label={`${driveAllocationRoleLabel(row.role)} drive bays`}
                onChange={(event) => updateStorageAllocation(context, row.id, "drive_bays", event.target.value)}
                placeholder="1, 2"
                type="text"
                value={row.drive_bays}
              />
            </label>
            <label className="cc-field">
              <span>RAID</span>
              <select
                aria-label={`${driveAllocationRoleLabel(row.role)} RAID`}
                onChange={(event) => updateStorageAllocation(context, row.id, "raid_level", event.target.value)}
                value={row.raid_level}
              >
                <option value="">None</option>
                <option value="RAID0">RAID 0</option>
                <option value="RAID1">RAID 1</option>
                <option value="RAID5">RAID 5</option>
                <option value="RAID6">RAID 6</option>
                <option value="RAID10">RAID 10</option>
                <option value="Spare">Spare</option>
              </select>
            </label>
            <label className="cc-field">
              <span>Volume / purpose</span>
              <input
                aria-label={`${driveAllocationRoleLabel(row.role)} volume`}
                onChange={(event) => updateStorageAllocation(context, row.id, "volume_name", event.target.value)}
                placeholder="ESXI_BOOT or DATA"
                type="text"
                value={row.volume_name}
              />
            </label>
            <label className="cc-field">
              <span>Controller</span>
              <input
                aria-label={`${driveAllocationRoleLabel(row.role)} controller`}
                onChange={(event) => updateStorageAllocation(context, row.id, "controller_path", event.target.value)}
                placeholder="Controller path or name"
                type="text"
                value={row.controller_path}
              />
            </label>
            <label className="cc-field cc-storage-notes">
              <span>Notes</span>
              <input
                aria-label={`${driveAllocationRoleLabel(row.role)} notes`}
                onChange={(event) => updateStorageAllocation(context, row.id, "notes", event.target.value)}
                placeholder="Optional"
                type="text"
                value={row.notes}
              />
            </label>
            <button
              aria-label={`Remove ${driveAllocationRoleLabel(row.role)} drive group`}
              disabled={rows.length <= 1}
              onClick={() => removeStorageAllocation(context, row.id)}
              type="button"
            >
              <Trash2 size={16} />
              Remove
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function RunPage({ context }: { context: ControlCenterContext }) {
  const running = context.runStatus === "running";
  const runDisabled = running || context.configSaving;
  const runActions = runCenterActions(context.actions);
  const selectedAction = context.selectedAction;
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
              ["Backend action", selectedAction?.label ?? "Safe placeholder"],
              ["Action source", selectedAction?.source_type ?? "todo_placeholder"]
            ]}
          />
          <ActionRow>
            <Link className="cc-button secondary" to="/configure">
              <SlidersHorizontal size={16} />
              Configure devices
            </Link>
            <Link className="cc-button secondary" to="/firmware">
              <UploadCloud size={16} />
              Firmware
            </Link>
            <Link className="cc-button secondary" to="/results">
              <FileText size={16} />
              Reports
            </Link>
          </ActionRow>
        </div>
        <button className="cc-big-run primary" disabled={runDisabled} onClick={() => void context.runSelectedAction()} type="button">
          <Play size={20} />
          {running ? "Running" : context.configSaving ? "Saving config" : "Run"}
        </button>
      </section>

      {!context.selectedAction && <Banner tone="warn">Backend run integration is pending. The placeholder does not contact providers.</Banner>}
      {context.runError && <Banner tone="bad">{context.runError}</Banner>}

      <section className="cc-panel">
        <SectionTitle icon={<ClipboardList size={18} />} title="Run Queue" />
        <div className="cc-run-action-list">
          {runActions.map((action) => (
            <button
              className={action.action_id === context.selectedRunActionId ? "is-selected" : ""}
              key={action.action_id}
              onClick={() => context.setSelectedRunActionId(action.action_id)}
              type="button"
            >
              <div>
                <strong>{action.label}</strong>
                <span>{action.stage_label} / {action.provider}</span>
              </div>
              <StatusPill status={action.current_availability || action.last_run_status || "not_checked"} />
            </button>
          ))}
        </div>
      </section>

      <section className="cc-panel">
        <SectionTitle icon={<TerminalSquare size={18} />} title="Evidence" />
        <FactList
          facts={[
            ["Selected action", selectedAction?.action_id ?? "none"],
            ["Mode", selectedAction?.mode ?? "not_available"],
            ["Last run", selectedAction?.last_run_status ?? "not_checked"],
            ["Command", selectedAction?.command ?? "not_available"]
          ]}
        />
        <EvidenceList action={selectedAction} />
      </section>

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

const runCenterPreferredActionIds = [
  "netapp.console-autodiscovery",
  "netapp.console-read-state",
  "netapp.console-login-state",
  "netapp.nfs-vcenter-readiness",
  "esxi.netapp-datastore-preview",
  "esxi.netapp-datastore-validate",
  "esxi.vm-deploy-preview",
  "esxi.vm-deploy-validate",
  "vcenter.install-readiness",
  "vcenter.install-plan",
  "vcenter.install-preview",
  "vcenter.attach-esxi-preview",
  "vcenter.post-attach-validation",
  "build-verification.run-full",
  "lab-validation.summary"
];

function runCenterActions(actions: WorkflowAction[]): WorkflowAction[] {
  const byId = new Map(actions.map((action) => [action.action_id, action]));
  const preferred = runCenterPreferredActionIds.map((id) => byId.get(id)).filter((action): action is WorkflowAction => Boolean(action));
  const extra = actions
    .filter(
      (action) =>
        !runCenterPreferredActionIds.includes(action.action_id) &&
        ["netapp-ontap", "esxi-readonly", "vcenter"].includes(action.provider)
    )
    .slice(0, 8);
  return [...preferred, ...extra];
}

function EvidenceList({ action }: { action: WorkflowAction | null }) {
  const artifacts = uniqueStrings([
    ...(action?.reports ?? []),
    ...(action?.evidence_artifacts ?? []),
    ...(action?.last_run_trace?.report_artifacts ?? [])
  ]);
  const consoleArtifacts = [
    "artifacts/codex-runs/netapp-console-autodiscovery-report.md",
    "artifacts/codex-runs/netapp-console-state-report.md",
    "artifacts/codex-runs/netapp-console-login-state-report.md",
    "artifacts/codex-runs/netapp-console-state-redacted.json",
    "artifacts/codex-runs/netapp-console-login-state-redacted.json"
  ];
  const visible = uniqueStrings([...consoleArtifacts, ...artifacts]).slice(0, 10);
  if (!visible.length) return <EmptyState title="No evidence linked" detail="Run a backend action to collect reports and traces." />;
  return (
    <ul className="cc-evidence-list">
      {visible.map((artifact) => (
        <li key={artifact}>
          <FileText size={15} />
          <span>{artifact}</span>
        </li>
      ))}
    </ul>
  );
}

function uniqueStrings(values: string[]): string[] {
  return values.filter((value, index, array) => value && array.indexOf(value) === index);
}

function FirmwarePage({ context }: { context: ControlCenterContext }) {
  const [activeTab, setActiveTab] = useState<FirmwareTabKey>("overview");
  const activeProfile = context.labProfiles?.active_profile;
  const includedCount = profileDeviceDefinitions.filter((definition) => context.profileEditor.deviceSelection[definition.key]).length;

  return (
    <Page title="Firmware">
      <section className="cc-panel cc-profile-summary">
        <div>
          <SectionTitle icon={<UploadCloud size={18} />} title="Firmware Profile" />
          <p className="cc-muted">
            {activeProfile
              ? `${activeProfile.name} controls which firmware tabs are in scope.`
              : "Profile data is loading or unavailable."}
          </p>
        </div>
        <FactList
          facts={[
            ["Lab", context.profileEditor.name || "Unnamed lab"],
            ["Subnet", context.profileEditor.subnet || "Not set"],
            ["Included hardware", `${includedCount} equipment tabs`],
            ["Firmware source", firmwareRuntimeSourceLabel(context.firmwareRuntime)]
          ]}
        />
      </section>

      <div className="cc-configure-tabs cc-firmware-tabs" role="tablist" aria-label="Firmware sections">
        <button
          aria-selected={activeTab === "overview"}
          className={activeTab === "overview" ? "is-active" : ""}
          onClick={() => setActiveTab("overview")}
          role="tab"
          type="button"
        >
          <UploadCloud size={16} />
          Overview
        </button>
        {profileDeviceDefinitions.map((definition) => {
          const included = context.profileEditor.deviceSelection[definition.key];
          return (
            <button
              aria-selected={activeTab === definition.key}
              className={`${activeTab === definition.key ? "is-active" : ""} ${included ? "" : "is-excluded"}`}
              key={definition.key}
              onClick={() => setActiveTab(definition.key)}
              role="tab"
              type="button"
            >
              {definition.icon}
              {definition.label}
            </button>
          );
        })}
      </div>

      {activeTab === "overview" ? (
        <>
          <FirmwareVisibilitySection context={context} />
          <FirmwareUpgradeSection context={context} />
          <section className="cc-panel">
            <SectionTitle icon={<History size={18} />} title="Firmware Events" />
            <ActivityList logs={firmwareEventLogs(context)} />
          </section>
        </>
      ) : (
        <FirmwareDeviceTab context={context} definition={profileDeviceDefinitions.find((definition) => definition.key === activeTab)!} />
      )}
    </Page>
  );
}

function FirmwareDeviceTab({
  context,
  definition
}: {
  context: ControlCenterContext;
  definition: ProfileDeviceDefinition;
}) {
  const included = context.profileEditor.deviceSelection[definition.key];
  const summaries = firmwareSummariesForDevice(context.firmware.summaries, definition.key);
  const paths = firmwarePathsForDevice(collectFirmwarePaths(context.firmware.summaries), definition.key);
  const firmwareTarget = firmwareTargetForDevice(context.profileEditor, definition.key);
  const simpleHpeFirmware = definition.key === "server" || definition.key === "storage";
  return (
    <>
      <section className={`cc-panel cc-equipment-panel ${included ? "" : "is-excluded"}`}>
        <div className="cc-panel-head">
          <SectionTitle icon={definition.icon} title={`${definition.label} Firmware`} />
          <StatusPill status={included ? "included" : "excluded"} />
        </div>
        <FactList
          facts={[
            ["Profile address", profileDeviceAddress(definition.key, context.profileEditor.addressPlan) || "Not set"],
            ["Firmware target", firmwareTarget || context.targetSummary],
            ["Firmware summaries", summaries.length ? `${summaries.length} reported` : "None reported"],
            ["Upgrade paths", paths.length ? `${paths.length} available` : "None reported"],
            ["Scope", included ? "Included by active profile" : "Excluded by active profile"]
          ]}
        />
        {!included && (
          <Banner tone="info">This hardware is excluded from the active lab profile. Use Configure to include it before firmware work.</Banner>
        )}
      </section>
      {included && (
        simpleHpeFirmware ? (
          <>
            <HpeIloFirmwareInventoryPanel context={context} deviceKey={definition.key === "server" ? "server" : "storage"} />
            <FirmwareUpgradeSection context={context} deviceKey={definition.key} />
          </>
        ) : (
          <>
            {definition.key === "cisco" && <CiscoFirmwareTransferPanel context={context} />}
            <FirmwareVisibilitySection context={context} deviceKey={definition.key} />
            <FirmwareUpgradeSection context={context} deviceKey={definition.key} />
          </>
        )
      )}
    </>
  );
}

function CiscoFirmwareTransferPanel({ context }: { context: ControlCenterContext }) {
  const editor = context.profileEditor;
  const paths = firmwarePathsForDevice(collectFirmwarePaths(context.firmware.summaries), "cisco");
  const firstPath = paths[0] ?? null;
  const managementIp = editor.addressPlan.cisco_management || "192.168.1.204";
  const consolePort = deviceDetailValue(editor, "cisco", "console_port") || "/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller_D-if00-port0";
  const baud = deviceDetailValue(editor, "cisco", "console_baud") || "9600";
  const image = deviceDetailValue(editor, "cisco", "ios_image") || firstPath?.selected_file_name || firstPath?.package_name || firstPath?.target_version || "Select IOS XE image";
  const protocol = deviceDetailValue(editor, "cisco", "file_transfer_protocol") || "SCP";
  return (
    <section className="cc-panel">
      <div className="cc-panel-head">
        <SectionTitle icon={<UploadCloud size={18} />} title="Cisco Image Transfer" />
        <StatusPill status={paths.length ? "ready" : "not_checked"} />
      </div>
      <FactList
        facts={[
          ["Console bootstrap", `${consolePort} @ ${baud}`],
          ["Management target", managementIp],
          ["Transfer protocol", `${protocol.toUpperCase()} after SSH/SCP bootstrap`],
          ["Image selection", image],
          ["Upgrade paths", paths.length ? `${paths.length} Cisco path${paths.length === 1 ? "" : "s"} reported` : "No Cisco path reported"],
          ["Verification", "Validate TCP/22, copy to flash, verify file, then plan install/reload separately"]
        ]}
      />
      <Banner tone="info">
        The Cisco transfer path is console bootstrap first, then SSH/SCP to the switch management IP.
      </Banner>
    </section>
  );
}

function HpeIloFirmwareInventoryPanel({
  context,
  deviceKey
}: {
  context: ControlCenterContext;
  deviceKey: "server" | "storage";
}) {
  const result = context.firmware.latestInventory;
  const inventory = hpeIloFirmwareInventory(context.firmware);
  const warnings = hpeIloInventoryWarnings(result);
  const blockers = stringArray(result?.blockers);
  const hasReturnedValues = Boolean(
    inventory.iloFirmware || inventory.biosVersion || inventory.smartArrayFirmware || inventory.controllers.length
  );
  const title = deviceKey === "server" ? "iLO Firmware" : "Internal Controller Firmware";
  const target = firmwareTargetForDevice(context.profileEditor, "server") || context.targetSummary;
  const uid = deviceDetailValue(context.profileEditor, "server", "uid");
  const checkRunning = context.firmwareCheckStatus === "running";
  const checkDisabled = checkRunning || context.configSaving;
  const targetVersions = hpeFirmwareTargetVersions(context.firmware.summaries);
  return (
    <section className="cc-panel">
      <div className="cc-panel-head">
        <SectionTitle icon={<Cpu size={18} />} title={title} />
        <StatusPill status={inventory.status} />
      </div>
      <FactList
        facts={[
          ["IP being used", target || "Not set"],
          ["UID / username", uid || "Not set in Configure"],
          ["Backend credential source", "Local backend iLO credentials; password is never shown"],
          ["Inventory source", firmwareInventorySource(result)],
          ["Last collected", result?.checked_at ? formatDateTime(result.checked_at) : "Not checked"],
          ["Recheck command", "make provider-lab-hpe-firmware-inventory"]
        ]}
      />
      <div className="cc-firmware-compare" role="table" aria-label="iLO firmware current and target versions">
        <div className="cc-firmware-compare-row is-head" role="row">
          <span role="columnheader">State</span>
          <span role="columnheader">iLO</span>
          <span role="columnheader">BIOS</span>
          <span role="columnheader">Controller</span>
        </div>
        <div className="cc-firmware-compare-row" role="row">
          <strong role="cell">Current</strong>
          <span role="cell">{displayValue(inventory.iloFirmware)}</span>
          <span role="cell">{displayValue(inventory.biosVersion)}</span>
          <span role="cell">{displayValue(inventory.smartArrayFirmware)}</span>
        </div>
        <div className="cc-firmware-compare-row" role="row">
          <strong role="cell">Should be</strong>
          <span role="cell">{displayValue(targetVersions.ilo)}</span>
          <span role="cell">{displayValue(targetVersions.bios)}</span>
          <span role="cell">{displayValue(targetVersions.smartArray)}</span>
        </div>
      </div>
      {!hasReturnedValues && (
        <Banner tone="warn">
          No current iLO Redfish firmware, BIOS, or controller versions were returned by the latest inventory.
        </Banner>
      )}
      {blockers.map((blocker) => (
        <Banner key={blocker} tone="bad">
          {blocker}
        </Banner>
      ))}
      {warnings.map((warning) => (
        <Banner key={warning} tone="warn">
          {warning}
        </Banner>
      ))}
      <ActionRow>
        <button
          className="cc-primary"
          disabled={checkDisabled || !target}
          onClick={() => void context.checkFirmware(target, uid)}
          type="button"
        >
          <RefreshCw size={16} />
          {checkRunning ? "Running" : "Run"}
        </button>
      </ActionRow>
    </section>
  );
}

function FirmwareVisibilitySection({ context, deviceKey }: { context: ControlCenterContext; deviceKey?: ProfileDeviceKey }) {
  const checkRunning = context.firmwareCheckStatus === "running";
  const checkDisabled = checkRunning || context.configSaving;
  const summaries = deviceKey ? firmwareSummariesForDevice(context.firmware.summaries, deviceKey) : context.firmware.summaries;
  const firmwareTarget = deviceKey ? firmwareTargetForDevice(context.profileEditor, deviceKey) : "";
  const title = deviceKey ? `${profileDeviceLabel(deviceKey)} Firmware Visibility` : "Firmware Visibility";
  return (
    <section className="cc-panel">
      <div className="cc-panel-head">
        <SectionTitle icon={<Cpu size={18} />} title={title} />
        <button disabled={checkDisabled} onClick={() => void context.checkFirmware(firmwareTarget)} type="button">
          <RefreshCw size={16} />
          {checkRunning ? "Checking" : context.configSaving ? "Saving config" : "Check Firmware"}
        </button>
      </div>
      {summaries.length ? (
        <div className="cc-firmware-list">
          {summaries.map((summary) => (
            <FirmwareVisibilityRow key={summary.device_id} summary={summary} />
          ))}
        </div>
      ) : deviceKey ? (
        <EmptyState title={`No ${profileDeviceLabel(deviceKey)} firmware data`} detail="Run Check Firmware to refresh backend firmware summaries for this profile." />
      ) : (
        <FirmwareVisibilityEmpty />
      )}
    </section>
  );
}

function FirmwareUpgradeSection({ context, deviceKey }: { context: ControlCenterContext; deviceKey?: ProfileDeviceKey }) {
  const allFirmwarePaths = collectFirmwarePaths(context.firmware.summaries);
  const firmwarePaths = deviceKey ? firmwarePathsForDevice(allFirmwarePaths, deviceKey) : allFirmwarePaths;
  const currentNoUpgrade = firmwareDeviceHasNoUpgrade(firmwarePaths, deviceKey);
  const selectedPathInScope = !deviceKey || Boolean(context.selectedPath && firmwarePathMatchesDevice(context.selectedPath, deviceKey));
  const currentPathForPanel = currentNoUpgrade ? firmwarePaths.find((path) => path.path_status === "current") ?? null : null;
  const selectedPathForPanel = selectedPathInScope ? context.selectedPath : currentPathForPanel;
  const firmwareTarget = deviceKey ? firmwareTargetForDevice(context.profileEditor, deviceKey) : "";
  const configForPanel = configWithTargetOverride(context.config, firmwareTarget);
  const supportedActionId = supportedUpgradeActionId(selectedPathForPanel);
  const backendPending = Boolean(selectedPathForPanel && !currentNoUpgrade && (!supportedActionId || !context.selectedUpgradeAction));
  const validationBlockers = selectedPathInScope
    ? firmwareValidateBlockers({ config: configForPanel, selectedFirmware: context.selectedFirmware, selectedPath: selectedPathForPanel })
    : currentNoUpgrade
    ? []
    : [`Select a ${profileDeviceLabel(deviceKey!)} firmware path before validation.`];
  const upgradeBlockers = selectedPathInScope
    ? firmwareStartBlockers({
        accepted: context.upgradeConfirmationAccepted,
        config: configForPanel,
        phrase: context.upgradeConfirmationPhrase,
        selectedFirmware: context.selectedFirmware,
        selectedPath: selectedPathForPanel,
        selectedUpgradeAction: selectedPathForPanel ? context.selectedUpgradeAction : null,
        validation: context.latestFirmwareValidation
      })
    : currentNoUpgrade
    ? []
    : [`Select a ${profileDeviceLabel(deviceKey!)} firmware path before starting an upgrade.`];
  const expectedPhrase = upgradeConfirmationPhrase(selectedPathForPanel, selectedPathForPanel ? context.selectedUpgradeAction : null);
  const validateDisabled =
    context.configSaving ||
    context.upgradeStatus === "validating" ||
    context.upgradeStatus === "upgrading" ||
    !selectedPathForPanel ||
    !context.selectedFirmware.trim();
  const startDisabled =
    context.configSaving ||
    !selectedPathForPanel ||
    upgradeBlockers.length > 0 ||
    context.upgradeStatus === "upgrading" ||
    context.upgradeStatus === "validating";
  const title = deviceKey ? `${profileDeviceLabel(deviceKey)} Firmware Upgrade` : "Firmware Upgrade";
  const selectedPathId = selectedPathForPanel ? context.selectedPathId : "";

  return (
    <section className="cc-panel">
      <div className="cc-panel-head">
        <SectionTitle icon={<UploadCloud size={18} />} title={title} />
        <StatusPill status={context.upgradeStatus} />
      </div>

      <FactList
        facts={[
          ["Target", configForPanel.target || "Not configured"],
          ["Current firmware", selectedPathForPanel ? displayValue(selectedPathForPanel.current_version) : "Select firmware path"],
          ["Selected firmware/image/version", selectedPathForPanel ? context.selectedFirmware || "Missing" : "Missing"],
          ["Compatibility check", validationStatusLabel(context)],
          ["Readiness status", firmwareReadinessLabel(context)],
          ["Progress", firmwareProgressLabel(context)],
          ["Backend status/progress", context.firmwareRuntime.message],
          ["Next safe action", context.firmwareRuntime.nextSafeAction],
          ["Backend action", selectedPathForPanel ? context.selectedUpgradeAction?.label ?? "Integration pending" : "Select firmware path"],
          ["Backend gates", selectedPathForPanel ? firmwareBackendGateLabel(context) : "Select firmware path"],
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
          <select onChange={(event) => context.setSelectedPathId(event.target.value)} value={selectedPathId}>
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
            value={selectedPathForPanel ? context.selectedFirmware : ""}
          />
          <datalist id="firmware-candidates">
            {firmwareCandidateOptions(selectedPathForPanel).map((candidate) => (
              <option key={candidate} value={candidate} />
            ))}
          </datalist>
        </label>
      </div>

      {!firmwarePaths.length && <Banner tone="warn">Firmware summary backend has not exposed upgrade paths for this tab yet.</Banner>}
      {backendPending && <Banner tone="warn">Upgrade backend integration is pending for this selected firmware path.</Banner>}
      {currentNoUpgrade && <Banner tone="good">Firmware is current for this device. No upgrade path needs action.</Banner>}
      {selectedPathForPanel && <FirmwarePathSummary path={selectedPathForPanel} />}

      {!currentNoUpgrade && (
        <>
          <ActionRow>
            <button disabled={validateDisabled} onClick={() => void context.validateFirmware(firmwareTarget)} type="button">
              <ShieldCheck size={16} />
              {context.upgradeStatus === "validating" ? "Validating" : context.configSaving ? "Saving config" : "Validate Firmware"}
            </button>
          </ActionRow>
          {validationBlockers.length > 0 && <IssueList title="Validation blockers" items={validationBlockers} />}

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
              Required phrase: <code>{expectedPhrase}</code>
            </p>
            <label className="cc-field">
              <span>Confirmation phrase</span>
              <input
                onChange={(event) => context.setUpgradeConfirmationPhrase(event.target.value)}
                placeholder={expectedPhrase}
                type="text"
                value={context.upgradeConfirmationPhrase}
              />
            </label>
            {upgradeBlockers.length > 0 && <IssueList title="Upgrade blockers" items={upgradeBlockers} />}
            <button className="primary danger-action" disabled={startDisabled} onClick={() => void context.startFirmwareUpgrade(firmwareTarget)} type="button">
              <UploadCloud size={16} />
              {context.upgradeStatus === "upgrading" ? "Upgrade Running" : context.configSaving ? "Saving config" : "Start Firmware Upgrade"}
            </button>
          </div>
        </>
      )}
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
          ["Selected component", firmwareComponentDisplayLabel(path)],
          ["Current version", displayValue(path.current_version)],
          ["Target version", displayValue(path.target_version)],
          ["Selected package/file", path.selected_file_name || path.package_name || "Not selected"],
          ["Path status", statusLabel(path.path_status)],
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

function firmwareSummariesForDevice(summaries: FirmwareSummary[], deviceKey: ProfileDeviceKey): FirmwareSummary[] {
  return summaries.filter((summary) => firmwareSummaryMatchesDevice(summary, deviceKey));
}

function firmwarePathsForDevice(paths: FirmwareUpgradePath[], deviceKey: ProfileDeviceKey): FirmwareUpgradePath[] {
  return paths.filter((path) => firmwarePathMatchesDevice(path, deviceKey));
}

function firmwareDeviceHasNoUpgrade(paths: FirmwareUpgradePath[], deviceKey?: ProfileDeviceKey): boolean {
  if (!paths.length) return false;
  return paths.every((path) => {
    if (path.path_status === "current") return true;
    return Boolean(deviceKey === "cisco" && path.component_id === "cisco_bootloader_rommon" && path.path_status === "manual_review");
  });
}

function firmwareSummaryMatchesDevice(summary: FirmwareSummary, deviceKey: ProfileDeviceKey): boolean {
  return firmwareTextMatchesDevice(
    [
      summary.device_id,
      summary.label,
      summary.component_type,
      summary.scan_action_id,
      summary.upgrade_center_link,
      ...(summary.upgrade_paths ?? []).map((path) => firmwarePathSearchText(path))
    ].join(" "),
    deviceKey
  );
}

function firmwarePathMatchesDevice(path: FirmwareUpgradePath, deviceKey: ProfileDeviceKey): boolean {
  return firmwareTextMatchesDevice(firmwarePathSearchText(path), deviceKey);
}

function firmwarePathSearchText(path: FirmwareUpgradePath): string {
  return [
    path.device_label,
    path.equipment_label,
    path.equipment_type,
    path.component_id,
    path.component_label,
    path.scan_action_id
  ].join(" ");
}

function firmwareTextMatchesDevice(value: string, deviceKey: ProfileDeviceKey): boolean {
  const text = value.toLowerCase();
  if (deviceKey === "netapp") return /netapp|ontap|cluster|svm/.test(text);
  if (deviceKey === "storage") return /smart array|arraycontroller|raid|storage|disk|drive|controller|logical/.test(text) && !/netapp|ontap/.test(text);
  if (deviceKey === "server") {
    return /\bilo\b|hpe.*ilo|server|bios|management_firmware/.test(text) && !/smart array|raid|storage|disk|drive|controller/.test(text);
  }
  if (deviceKey === "cisco") return /cisco|switch|nx-?os|ios ?xe|iosxe|rommon|(^|[^a-z0-9])ios([^a-z0-9]|$)/.test(text);
  if (deviceKey === "esxi") return /esxi|vmware|hypervisor/.test(text);
  if (deviceKey === "vcenter") return /vcenter|vcentre/.test(text);
  return false;
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
  const current = path.current_version || "current unknown";
  return `${firmwareComponentDisplayLabel(path)}: ${current} -> ${target}`;
}

function firmwareComponentDisplayLabel(path: FirmwareUpgradePath): string {
  if (path.component_id === "hpe_ilo_firmware") return "HPE iLO firmware";
  if (path.component_id === "hpe_bios_version") return "HPE BIOS firmware";
  if (path.component_id === "hpe_smart_array_firmware") return "HPE controller firmware - Smart Array";
  return `${path.device_label} ${path.component_label}`.trim();
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

function activeOperationForContext(context: ControlCenterContext): ActiveOperation | null {
  if (context.upgradeStatus === "upgrading") {
    return {
      detail: "Watching the guarded backend firmware request and waiting for the next status update.",
      key: "firmware-upgrade",
      phases: ["Submitting request", "Staging package", "Applying firmware", "Waiting for reboot or verify"],
      progressCeiling: 95,
      title: "Firmware upgrade monitoring in progress"
    };
  }
  if (context.upgradeStatus === "validating") {
    return {
      detail: "Checking selected firmware evidence against the current target and saved configuration.",
      key: "firmware-validation",
      phases: ["Saving selection", "Checking inventory", "Matching package", "Reviewing blockers"],
      title: "Firmware validation in progress"
    };
  }
  if (context.firmwareCheckStatus === "running") {
    return {
      detail: "Refreshing firmware inventory and waiting for the backend response.",
      key: "firmware-check",
      phases: ["Starting scan", "Reading providers", "Refreshing compliance", "Writing evidence"],
      title: "Firmware check in progress"
    };
  }
  if (context.runStatus === "running") {
    return {
      detail: `Running ${context.selectedAction?.label ?? "the selected backend action"} and collecting result evidence.`,
      key: "safe-run",
      phases: ["Submitting action", "Waiting for backend", "Collecting result", "Refreshing evidence"],
      title: "Safe run in progress"
    };
  }
  if (context.profileSaving) {
    return {
      detail: "Saving the lab profile, activating it, and refreshing profile-backed runtime context.",
      key: "profile-save",
      phases: ["Saving profile", "Activating profile", "Refreshing context"],
      title: "Lab profile save in progress"
    };
  }
  if (context.profileDeleting) {
    return {
      detail: "Deleting the saved lab profile and loading the next active profile.",
      key: "profile-delete",
      phases: ["Deleting profile", "Refreshing profile list", "Reloading context"],
      title: "Lab profile delete in progress"
    };
  }
  if (context.profileActivating) {
    return {
      detail: "Activating the selected lab profile and recalculating visible hardware scope.",
      key: "profile-activate",
      phases: ["Activating profile", "Refreshing hardware scope", "Reloading context"],
      title: "Lab profile activation in progress"
    };
  }
  if (context.configSaving) {
    return {
      detail: "Saving non-secret runtime configuration before the next backend operation.",
      key: "config-save",
      phases: ["Saving config", "Refreshing runtime", "Updating controls"],
      title: "Configuration save in progress"
    };
  }
  if (context.settingsSaving) {
    return {
      detail: "Saving Control Center defaults and refreshing local runtime settings.",
      key: "settings-save",
      phases: ["Saving settings", "Refreshing defaults", "Updating controls"],
      title: "Settings save in progress"
    };
  }
  if (context.loading) {
    return {
      detail: "Loading provider status, action catalog, profiles, firmware summaries, and recent activity.",
      key: "app-load",
      phases: ["Loading status", "Loading actions", "Loading firmware", "Loading activity"],
      title: "Control Center refresh in progress"
    };
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
  const available = visible.filter((provider) => /ready|ok|available|connected|current/i.test(provider.status)).length;
  const blocked = visible.filter((provider) => provider.blockers.length || /blocked|failed|unavailable|missing/i.test(provider.status)).length;
  return `${visible.length} adapters visible; ${available} reporting available; ${blocked} blocked or missing`;
}

function firmwareCurrentVersion(summary: FirmwareSummary): string {
  return displayValue(summary.current_versions.find((item) => item.version)?.version ?? null);
}

function hpeIloFirmwareInventory(firmware: FirmwareState): IloFirmwareInventory {
  const result = firmware.latestInventory;
  const liveInventory = recordFrom(result?.live_inventory);
  const ilo = recordFrom(liveInventory?.ilo);
  return {
    biosVersion: unknownStringOrNull(ilo?.bios_version),
    controllers: hpeIloControllerInventory(ilo?.controllers),
    iloFirmware: unknownStringOrNull(ilo?.ilo_firmware),
    smartArrayFirmware: unknownStringOrNull(ilo?.smart_array_firmware),
    status: stringFact(ilo?.status, stringFact(result?.status, "not_checked"))
  };
}

function hpeIloControllerInventory(value: unknown): IloControllerInventory[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item, index) => {
      const controller = recordFrom(item);
      if (!controller) return null;
      const id = unknownStringOrNull(controller.id) || `controller-${index + 1}`;
      const model = unknownStringOrNull(controller.model);
      const name = unknownStringOrNull(controller.name) || model || `Storage controller ${index + 1}`;
      return {
        adapterType: unknownStringOrNull(controller.adapter_type),
        firmwareVersion: unknownStringOrNull(controller.firmware_version),
        health: unknownStringOrNull(controller.health),
        id,
        location: unknownStringOrNull(controller.location),
        model,
        name,
        protocol: unknownStringOrNull(controller.protocol),
        state: unknownStringOrNull(controller.state)
      };
    })
    .filter((item): item is IloControllerInventory => item !== null);
}

function hpeFirmwareTargetVersions(summaries: FirmwareSummary[]): { bios: string | null; ilo: string | null; smartArray: string | null } {
  const hpeSummaries = summaries.filter((summary) => summary.device_id === "ilo" || summary.device_id === "raid");
  return {
    bios: hpeFirmwareVersionByLabel(hpeSummaries, /bios/i, "target"),
    ilo: hpeFirmwareVersionByLabel(hpeSummaries, /ilo/i, "target"),
    smartArray: hpeFirmwareVersionByLabel(hpeSummaries, /smart array/i, "target")
  };
}

function hpeFirmwareVersionByLabel(summaries: FirmwareSummary[], labelPattern: RegExp, kind: "current" | "target"): string | null {
  const rows = summaries.flatMap((summary) => (kind === "current" ? summary.current_versions : summary.approved_versions));
  const row =
    kind === "target"
      ? rows.find((item) => labelPattern.test(item.label) && item.version && item.status === "approved") ??
        rows.find((item) => labelPattern.test(item.label) && item.version)
      : rows.find((item) => labelPattern.test(item.label) && item.version);
  if (row?.version) return row.version;
  const summary = summaries.find((item) => labelPattern.test(item.label) && item.target_version);
  return summary?.target_version ?? null;
}

function firmwareInventorySource(result: FirmwareState["latestInventory"]): string {
  if (!result) return "Not checked";
  const source = stringFact(result.source_type, "not_checked");
  const freshness = stringFact(result.freshness, "not_checked");
  return `${sourceLabel(source)} / ${statusLabel(freshness)}`;
}

function hpeIloInventoryWarnings(result: FirmwareState["latestInventory"]): string[] {
  return Array.from(
    new Set([
      ...stringArray(result?.warnings).filter(isHpeIloInventoryWarning),
      ...providerWarningsFor(result, "ilo")
    ])
  );
}

function isHpeIloInventoryWarning(warning: string): boolean {
  if (/cisco|netapp/i.test(warning)) return false;
  return /bios|controller|hpe|ilo|redfish|smart array|storage/i.test(warning);
}

function providerWarningsFor(result: FirmwareState["latestInventory"], provider: string): string[] {
  const providerWarnings = recordFrom(result?.provider_warnings);
  return stringArray(providerWarnings?.[provider]);
}

function recordFrom(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)).filter((item) => item.trim()) : [];
}

function unknownStringOrNull(value: unknown): string | null {
  const text = typeof value === "string" || typeof value === "number" || typeof value === "boolean" ? String(value).trim() : "";
  return text || null;
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

function sameControlConfig(first: ControlConfig, second: ControlConfig): boolean {
  return JSON.stringify(configSnapshot(first)) === JSON.stringify(configSnapshot(second));
}

function configWithTargetOverride(config: ControlConfig, targetOverride?: string): ControlConfig {
  const target = targetOverride?.trim();
  return target ? { ...config, target } : config;
}

function newProfileEditor(config: ControlConfig, seed?: LabProfile): ProfileEditorState {
  const seedSubnet = seed?.subnet_cidr || seed?.address_plan?.subnet || cidrFromTarget(config.target) || "192.168.1.0/24";
  const defaults = profileDefaultsForSubnet(seedSubnet);
  return {
    addressPlan: defaults.addressPlan,
    description: "",
    devices: { enabled: { ...defaultDeviceSelection, netapp: defaults.netappSupported } },
    deviceSelection: { ...defaultDeviceSelection, netapp: defaults.netappSupported },
    dnsText: "",
    features: {
      ...defaultProfileFeatures,
      netapp_disabled_reason: defaults.netappSupported ? null : "NetApp high-address defaults require a /24 or larger lab subnet.",
      netapp_enabled: defaults.netappSupported,
      storage_protocol: defaults.netappSupported ? "nfs" : "none"
    },
    gateway: defaults.gateway,
    id: null,
    mode: "new",
    mtu: "1500",
    name: "New lab profile",
    ntpText: "",
    profileTopology: defaults.profileTopology,
    subnet: seedSubnet,
    vlanId: ""
  };
}

function profileEditorFromProfile(profile: LabProfile | null | undefined, config: ControlConfig): ProfileEditorState {
  if (!profile || profile.id === "runtime") return newProfileEditor(config, profile ?? undefined);
  const defaults = profileDefaultsForSubnet(profile.subnet_cidr || profile.address_plan.subnet || "192.168.1.0/24");
  const deviceSelection = deviceSelectionFromProfile(profile, defaults.netappSupported);
  return {
    addressPlan: {
      ...emptyAddressPlan,
      ...defaults.addressPlan,
      ...profile.address_plan,
      netapp_iscsi_lifs: profile.address_plan.netapp_iscsi_lifs ?? [],
      netapp_nfs_lifs: profile.address_plan.netapp_nfs_lifs ?? []
    },
    description: profile.description ?? "",
    devices: profile.devices ?? {},
    deviceSelection,
    dnsText: (profile.global_settings.dns_servers?.length ? profile.global_settings.dns_servers : profile.dns).join(", "),
    features: { ...defaultProfileFeatures, ...profile.features },
    gateway: profile.global_settings.gateway || profile.gateway || defaults.gateway,
    id: profile.id,
    mode: "existing",
    mtu: profile.global_settings.mtu ? String(profile.global_settings.mtu) : profile.mtu ? String(profile.mtu) : "1500",
    name: profile.name,
    ntpText: (profile.global_settings.ntp_servers?.length ? profile.global_settings.ntp_servers : profile.ntp).join(", "),
    profileTopology: (profile.profile_topology || defaults.profileTopology) as ProfileEditorState["profileTopology"],
    subnet: profile.subnet_cidr || profile.address_plan.subnet || defaults.addressPlan.subnet || "192.168.1.0/24",
    vlanId: profile.global_settings.vlan_id || profile.vlan_id || ""
  };
}

function deviceSelectionFromProfile(profile: LabProfile, netappSupported: boolean): ProfileDeviceSelection {
  const enabled = recordValue(profile.devices.enabled);
  const serverIncluded = booleanRecordValue(enabled, "server", booleanRecordValue(enabled, "ilo", true));
  return {
    cisco: booleanRecordValue(enabled, "cisco", true),
    esxi: booleanRecordValue(enabled, "esxi", true),
    netapp: booleanRecordValue(enabled, "netapp", profile.features.netapp_enabled && netappSupported),
    server: serverIncluded,
    storage: booleanRecordValue(enabled, "storage", serverIncluded),
    vcenter: booleanRecordValue(enabled, "vcenter", profile.features.vcenter_enabled)
  };
}

function profileDefaultsForSubnet(subnet: string): {
  addressPlan: LabAddressPlan;
  gateway: string;
  netappSupported: boolean;
  profileTopology: ProfileEditorState["profileTopology"];
} {
  const parsed = parseIpv4Cidr(subnet);
  const prefix = parsed?.prefix ?? 24;
  const profileTopology: ProfileEditorState["profileTopology"] = prefix <= 24 ? "high_address_lab" : "compact_edge_lab";
  const netappSupported = prefix <= 24;
  const addressPlan: LabAddressPlan = {
    ...emptyAddressPlan,
    subnet: parsed?.cidr ?? subnet
  };
  const addressAt = (offset: number) => (parsed ? ipv4FromInt(parsed.base + offset) : null);
  const gateway = addressAt(1) ?? "";

  if (profileTopology === "high_address_lab") {
    addressPlan.ilo = addressAt(201);
    addressPlan.server_embedded_nic = addressAt(202);
    addressPlan.esxi_management = addressAt(203);
    addressPlan.cisco_management = addressAt(204);
    addressPlan.ansible_control_host = addressAt(205);
    addressPlan.netapp_controller_a_sp = addressAt(210);
    addressPlan.netapp_controller_b_sp = addressAt(211);
    addressPlan.netapp_cluster_mgmt = addressAt(220);
    addressPlan.netapp_node_a_mgmt = addressAt(221);
    addressPlan.netapp_node_b_mgmt = addressAt(222);
    addressPlan.netapp_svm_mgmt = addressAt(223);
    addressPlan.netapp_nfs_lifs = [addressAt(230), addressAt(231)].filter((value): value is string => Boolean(value));
    addressPlan.netapp_iscsi_lifs = [addressAt(240), addressAt(241), addressAt(242), addressAt(243)].filter(
      (value): value is string => Boolean(value)
    );
    return { addressPlan, gateway, netappSupported, profileTopology };
  }

  addressPlan.cisco_management = addressAt(2);
  addressPlan.ansible_control_host = addressAt(9);
  addressPlan.esxi_management = addressAt(10);
  addressPlan.ilo = addressAt(11);
  return { addressPlan, gateway, netappSupported, profileTopology };
}

function parseIpv4Cidr(value: string): { base: number; cidr: string; prefix: number } | null {
  const match = value.trim().match(/^(\d{1,3}(?:\.\d{1,3}){3})(?:\/(\d{1,2}))?$/);
  if (!match) return null;
  const ip = ipv4ToInt(match[1]);
  if (ip === null) return null;
  const prefix = match[2] ? Number(match[2]) : 24;
  if (!Number.isInteger(prefix) || prefix < 1 || prefix > 32) return null;
  const mask = prefix === 0 ? 0 : (0xffffffff << (32 - prefix)) >>> 0;
  const base = (ip & mask) >>> 0;
  return { base, cidr: `${ipv4FromInt(base)}/${prefix}`, prefix };
}

function ipv4ToInt(value: string): number | null {
  const parts = value.split(".").map((part) => Number(part));
  if (parts.length !== 4 || parts.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) return null;
  return (((parts[0] << 24) >>> 0) + (parts[1] << 16) + (parts[2] << 8) + parts[3]) >>> 0;
}

function ipv4FromInt(value: number): string {
  return [24, 16, 8, 0].map((shift) => (value >>> shift) & 255).join(".");
}

function cidrFromTarget(target: string): string | null {
  const trimmed = target.trim();
  return trimmed.includes("/") ? trimmed : null;
}

function updateProfileField<K extends keyof ProfileEditorState>(
  context: ControlCenterContext,
  field: K,
  value: ProfileEditorState[K]
) {
  context.setProfileEditor((current) => ({ ...current, [field]: value }));
}

function updateProfileSubnet(context: ControlCenterContext, subnet: string) {
  const defaults = profileDefaultsForSubnet(subnet);
  context.setProfileEditor((current) => ({
    ...current,
    addressPlan: {
      ...current.addressPlan,
      ...defaults.addressPlan,
      subnet
    },
    deviceSelection: {
      ...current.deviceSelection,
      netapp: current.deviceSelection.netapp && defaults.netappSupported
    },
    features: {
      ...current.features,
      netapp_disabled_reason: defaults.netappSupported ? null : "NetApp high-address defaults require a /24 or larger lab subnet.",
      netapp_enabled: current.deviceSelection.netapp && defaults.netappSupported,
      storage_protocol: current.deviceSelection.netapp && defaults.netappSupported ? current.features.storage_protocol || "nfs" : "none"
    },
    gateway: defaults.gateway,
    profileTopology: defaults.profileTopology,
    subnet
  }));
}

function updateProfileDeviceSelection(context: ControlCenterContext, deviceKey: ProfileDeviceKey, included: boolean) {
  context.setProfileEditor((current) => {
    const deviceSelection = { ...current.deviceSelection, [deviceKey]: included };
    const features = {
      ...current.features,
      netapp_enabled: deviceSelection.netapp,
      vcenter_enabled: deviceSelection.vcenter
    };
    features.storage_protocol = features.netapp_enabled ? features.storage_protocol || "nfs" : "none";
    features.netapp_disabled_reason = features.netapp_enabled ? null : "NetApp excluded by lab profile.";
    features.vcenter_disabled_reason = features.vcenter_enabled ? null : "vCenter excluded by lab profile.";
    return {
      ...current,
      devices: {
        ...current.devices,
        enabled: deviceSelection
      },
      deviceSelection,
      features
    };
  });
}

function updateProfileAddressPlan(context: ControlCenterContext, field: keyof LabAddressPlan, value: string) {
  context.setProfileEditor((current) => ({
    ...current,
    addressPlan: {
      ...current.addressPlan,
      [field]: Array.isArray(current.addressPlan[field]) ? splitCsv(value) : value
    }
  }));
}

function updateProfileDeviceDetail(context: ControlCenterContext, deviceKey: ProfileDeviceKey, field: string, value: string) {
  const detailKey = `${deviceKey}_details`;
  context.setProfileEditor((current) => ({
    ...current,
    devices: {
      ...current.devices,
      [detailKey]: {
        ...recordValue(current.devices[detailKey]),
        [field]: value
      }
    }
  }));
}

function setStorageAllocationRows(context: ControlCenterContext, rows: StorageDriveAllocation[]) {
  context.setProfileEditor((current) => ({
    ...current,
    devices: {
      ...current.devices,
      storage_details: {
        ...recordValue(current.devices.storage_details),
        drive_allocations: rows
      }
    }
  }));
}

function updateStorageAllocation(
  context: ControlCenterContext,
  rowId: string,
  field: keyof StorageDriveAllocation,
  value: string
) {
  const rows = storageDriveAllocationRows(context.profileEditor).map((row) =>
    row.id === rowId ? { ...row, [field]: value } : row
  );
  setStorageAllocationRows(context, rows);
}

function addStorageAllocation(context: ControlCenterContext) {
  const rows = storageDriveAllocationRows(context.profileEditor);
  setStorageAllocationRows(context, [
    ...rows,
    {
      controller_path: deviceDetailValue(context.profileEditor, "storage", "controller_path"),
      drive_bays: "",
      drive_count: "0",
      id: `drive-group-${Date.now()}`,
      notes: "",
      raid_level: "",
      role: "storage",
      volume_name: ""
    }
  ]);
}

function removeStorageAllocation(context: ControlCenterContext, rowId: string) {
  const rows = storageDriveAllocationRows(context.profileEditor).filter((row) => row.id !== rowId);
  setStorageAllocationRows(context, rows.length ? rows : defaultStorageDriveAllocations(context.profileEditor));
}

function storageDriveAllocationRows(editor: ProfileEditorState): StorageDriveAllocation[] {
  const details = recordValue(editor.devices.storage_details);
  const saved = details.drive_allocations;
  if (Array.isArray(saved)) {
    const normalized = saved
      .map((row, index) => storageAllocationFromRecord(recordValue(row), index))
      .filter((row): row is StorageDriveAllocation => Boolean(row));
    if (normalized.length) return normalized;
  }
  const legacyRows = legacyStorageAllocations(details);
  return legacyRows.length ? legacyRows : defaultStorageDriveAllocations(editor);
}

function storageAllocationFromRecord(record: Record<string, unknown>, index: number): StorageDriveAllocation | null {
  const role = stringRecordValue(record, "role", index === 0 ? "esxi" : "storage");
  return {
    controller_path: stringRecordValue(record, "controller_path"),
    drive_bays: stringRecordValue(record, "drive_bays"),
    drive_count: stringRecordValue(record, "drive_count"),
    id: stringRecordValue(record, "id", `${role}-${index}`),
    notes: stringRecordValue(record, "notes"),
    raid_level: stringRecordValue(record, "raid_level"),
    role,
    volume_name: stringRecordValue(record, "volume_name")
  };
}

function legacyStorageAllocations(details: Record<string, unknown>): StorageDriveAllocation[] {
  const controller = stringRecordValue(details, "controller_path");
  const osBays = stringRecordValue(details, "os_drive_bays");
  const dataBays = stringRecordValue(details, "data_drive_bays");
  const spareBay = stringRecordValue(details, "hot_spare_bay");
  const rows: StorageDriveAllocation[] = [];
  if (osBays || stringRecordValue(details, "os_raid_level")) {
    rows.push({
      controller_path: controller,
      drive_bays: osBays,
      drive_count: String(splitCsv(osBays).length || 2),
      id: "esxi-boot",
      notes: "",
      raid_level: stringRecordValue(details, "os_raid_level", "RAID1"),
      role: "esxi",
      volume_name: stringRecordValue(details, "boot_volume_name", "ESXI_BOOT")
    });
  }
  if (dataBays || stringRecordValue(details, "data_raid_level")) {
    rows.push({
      controller_path: controller,
      drive_bays: dataBays,
      drive_count: String(splitCsv(dataBays).length || 4),
      id: "storage-data",
      notes: "",
      raid_level: stringRecordValue(details, "data_raid_level", "RAID5"),
      role: "storage",
      volume_name: stringRecordValue(details, "data_volume_name", "DATA")
    });
  }
  if (spareBay) {
    rows.push({
      controller_path: controller,
      drive_bays: spareBay,
      drive_count: "1",
      id: "hot-spare",
      notes: "",
      raid_level: "Spare",
      role: "spare",
      volume_name: "HOT_SPARE"
    });
  }
  return rows;
}

function defaultStorageDriveAllocations(editor: ProfileEditorState): StorageDriveAllocation[] {
  const controller = deviceDetailValue(editor, "storage", "controller_path");
  return [
    {
      controller_path: controller,
      drive_bays: "1, 2",
      drive_count: "2",
      id: "esxi-boot",
      notes: "",
      raid_level: "RAID1",
      role: "esxi",
      volume_name: "ESXI_BOOT"
    },
    {
      controller_path: controller,
      drive_bays: "3, 4, 5, 6",
      drive_count: "4",
      id: "storage-data",
      notes: "",
      raid_level: "RAID5",
      role: "storage",
      volume_name: "DATA"
    },
    {
      controller_path: controller,
      drive_bays: "7",
      drive_count: "1",
      id: "hot-spare",
      notes: "",
      raid_level: "Spare",
      role: "spare",
      volume_name: "HOT_SPARE"
    }
  ];
}

function driveAllocationRoleLabel(role: string): string {
  if (role === "esxi") return "ESXi";
  if (role === "storage") return "Storage";
  if (role === "spare") return "Hot spare";
  if (role === "unused") return "Unused";
  return statusLabel(role);
}

function storageDetailsForProfile(editor: ProfileEditorState): Record<string, unknown> {
  const details = recordValue(editor.devices.storage_details);
  const rows = storageDriveAllocationRows(editor);
  const esxi = rows.find((row) => row.role === "esxi");
  const storage = rows.find((row) => row.role === "storage");
  const spare = rows.find((row) => row.role === "spare");
  return {
    ...details,
    boot_volume_name: esxi?.volume_name ?? stringRecordValue(details, "boot_volume_name"),
    data_drive_bays: storage?.drive_bays ?? stringRecordValue(details, "data_drive_bays"),
    data_raid_level: storage?.raid_level ?? stringRecordValue(details, "data_raid_level"),
    data_volume_name: storage?.volume_name ?? stringRecordValue(details, "data_volume_name"),
    drive_allocations: rows,
    hot_spare_bay: spare?.drive_bays ?? stringRecordValue(details, "hot_spare_bay"),
    os_drive_bays: esxi?.drive_bays ?? stringRecordValue(details, "os_drive_bays"),
    os_raid_level: esxi?.raid_level ?? stringRecordValue(details, "os_raid_level")
  };
}

function detectedDeviceFacts(context: ControlCenterContext, deviceKey: ProfileDeviceKey): Array<[string, string]> {
  const summaries = firmwareSummariesForDevice(context.firmware.summaries, deviceKey);
  const firstSummary = summaries[0] ?? null;
  return [
    ["Profile target", profileDeviceAddress(deviceKey, context.profileEditor.addressPlan) || "Not set"],
    ["Current firmware", deviceCurrentFirmwareText(summaries)],
    ["Approved/target firmware", deviceTargetFirmwareText(summaries)],
    ["Controller / hardware", deviceHardwareText(summaries, deviceKey)],
    ["Inventory source", firstSummary ? `${sourceLabel(firstSummary.source_type)} / ${statusLabel(firstSummary.freshness)}` : "No firmware inventory loaded"]
  ];
}

function applyDetectedProfileDefaults(context: ControlCenterContext, deviceKey: ProfileDeviceKey) {
  const definition = profileDeviceDefinitions.find((item) => item.key === deviceKey);
  if (!definition) return;
  const defaults = profileDefaultsForSubnet(context.profileEditor.subnet);
  const detailDefaults = detectedDeviceDetailDefaults(context, deviceKey);
  context.setProfileEditor((current) => {
    const addressPlan = { ...current.addressPlan };
    definition.addressFields.forEach((field) => {
      const defaultValue = defaults.addressPlan[field];
      if (addressFieldIsEmpty(addressPlan[field]) && !addressFieldIsEmpty(defaultValue)) {
        Object.assign(addressPlan, { [field]: Array.isArray(defaultValue) ? [...defaultValue] : defaultValue });
      }
    });

    const detailKey = `${deviceKey}_details`;
    const existingDetails = recordValue(current.devices[detailKey]);
    const nextDetails: Record<string, unknown> = { ...existingDetails };
    Object.entries(detailDefaults).forEach(([field, value]) => {
      if (!stringRecordValue(nextDetails, field) && value) {
        nextDetails[field] = value;
      }
    });

    if (deviceKey === "storage" && !Array.isArray(existingDetails.drive_allocations)) {
      const editorWithDetails: ProfileEditorState = {
        ...current,
        devices: {
          ...current.devices,
          storage_details: nextDetails
        }
      };
      const controller = stringRecordValue(nextDetails, "controller_path");
      nextDetails.drive_allocations = defaultStorageDriveAllocations(editorWithDetails).map((row) => ({
        ...row,
        controller_path: row.controller_path || controller
      }));
    }

    return {
      ...current,
      addressPlan,
      devices: {
        ...current.devices,
        [detailKey]: nextDetails
      }
    };
  });
}

function detectedDeviceDetailDefaults(context: ControlCenterContext, deviceKey: ProfileDeviceKey): Record<string, string> {
  const summaries = firmwareSummariesForDevice(context.firmware.summaries, deviceKey);
  const summary = summaries[0] ?? null;
  const paths = firmwarePathsForDevice(collectFirmwarePaths(context.firmware.summaries), deviceKey);
  const path = paths[0] ?? null;
  const current = deviceCurrentFirmwareText(summaries);
  const target = path?.target_version || path?.package_version || (summary ? firstApprovedVersion(summary) : null) || "";
  const defaults: Record<string, string> = {};

  if (deviceKey === "server") {
    const iloCurrent = serverIloFirmwareText(summaries);
    if (iloCurrent !== "Not detected") defaults.current_firmware = iloCurrent;
    const bios = summary ? firmwareVersionByLabel(summary, /bios/i) : "";
    if (bios && bios !== "Unknown") defaults.bios_version = bios;
    if (target) defaults.firmware_baseline = target;
  } else if (deviceKey === "storage") {
    const hardware = deviceHardwareText(summaries, deviceKey);
    if (hardware !== "Not detected") defaults.target_controller = hardware;
    if (current !== "Not detected") defaults.controller_firmware = current;
    if (target) defaults.firmware_baseline = target;
    defaults.total_drive_bays = "8";
  } else {
    if (current !== "Not detected") defaults.current_firmware = current;
    if (target) defaults.firmware_baseline = target;
  }

  return defaults;
}

function addressFieldIsEmpty(value: LabAddressPlan[keyof LabAddressPlan]): boolean {
  if (Array.isArray(value)) return value.length === 0;
  return !value;
}

function serverIloFirmwareText(summaries: FirmwareSummary[]): string {
  const summary = summaries.find((candidate) => /ilo/i.test(candidate.label) || /management_firmware/i.test(candidate.component_type));
  if (!summary) return "Not detected";
  const version = firmwareVersionByLabel(summary, /ilo/i) || firmwareCurrentVersion(summary);
  return version === "Unknown" ? "Not detected" : `${summary.label}: ${version}`;
}

function deviceCurrentFirmwareText(summaries: FirmwareSummary[]): string {
  const values = summaries
    .map((summary) => {
      const version = firmwareCurrentVersion(summary);
      return version === "Unknown" ? "" : `${summary.label}: ${version}`;
    })
    .filter(Boolean);
  return values.length ? values.join("; ") : "Not detected";
}

function deviceTargetFirmwareText(summaries: FirmwareSummary[]): string {
  const values = summaries
    .map((summary) => firstApprovedVersion(summary) || summary.target_version || "")
    .filter(Boolean);
  return values.length ? Array.from(new Set(values)).join(", ") : "Not detected";
}

function deviceHardwareText(summaries: FirmwareSummary[], deviceKey: ProfileDeviceKey): string {
  const paths = firmwarePathsForDevice(collectFirmwarePaths(summaries), deviceKey);
  const pathLabel = paths.find((path) => path.component_label)?.component_label;
  if (pathLabel) return pathLabel;
  const summary = summaries[0];
  if (summary?.label) return summary.label;
  if (deviceKey === "storage") return "Not detected";
  return "Not detected";
}

function updateProfileFeature<K extends keyof LabProfileFeatures>(
  context: ControlCenterContext,
  field: K,
  value: LabProfileFeatures[K]
) {
  context.setProfileEditor((current) => ({
    ...current,
    features: {
      ...current.features,
      [field]: value
    }
  }));
}

function deviceDetailValue(editor: ProfileEditorState, deviceKey: ProfileDeviceKey, field: string): string {
  const details = recordValue(editor.devices[`${deviceKey}_details`]);
  const value = details[field];
  return typeof value === "string" ? value : "";
}

function validateProfileEditor(editor: ProfileEditorState): string[] {
  const errors: string[] = [];
  if (editor.name.trim().length < 2) errors.push("Lab name is required.");
  if (!editor.subnet.trim()) errors.push("Subnet CIDR is required.");
  if (editor.subnet.trim() && !parseIpv4Cidr(editor.subnet.trim())) errors.push("Subnet CIDR must be an IPv4 CIDR such as 192.168.1.0/24.");
  if (!Object.values(editor.deviceSelection).some(Boolean)) errors.push("Select at least one hardware device for the profile.");
  if (editor.mtu.trim() && (Number(editor.mtu) < 576 || Number(editor.mtu) > 9216)) errors.push("MTU must be between 576 and 9216.");
  return errors;
}

function profilePayloadFromEditor(editor: ProfileEditorState): LabProfileWrite {
  const dnsServers = splitCsv(editor.dnsText);
  const ntpServers = splitCsv(editor.ntpText);
  const mtu = editor.mtu.trim() ? Number(editor.mtu) : null;
  const addressPlan = {
    ...emptyAddressPlan,
    ...editor.addressPlan,
    subnet: editor.subnet.trim()
  };
  const enabledDevices = {
    ...editor.deviceSelection,
    ilo: editor.deviceSelection.server
  };
  const devices: LabProfileDevices = {
    ...editor.devices,
    cisco: editor.deviceSelection.cisco ? addressPlan.cisco_management : null,
    enabled: enabledDevices,
    esxi: editor.deviceSelection.esxi ? addressPlan.esxi_management : null,
    ilo: editor.deviceSelection.server ? addressPlan.ilo : null,
    internal_storage: editor.deviceSelection.storage ? storageDetailsForProfile(editor) : null,
    netapp: editor.deviceSelection.netapp
      ? {
          cluster_mgmt: addressPlan.netapp_cluster_mgmt,
          controller_a_sp: addressPlan.netapp_controller_a_sp,
          controller_b_sp: addressPlan.netapp_controller_b_sp,
          iscsi_lifs: addressPlan.netapp_iscsi_lifs,
          nfs_lifs: addressPlan.netapp_nfs_lifs,
          node_a_mgmt: addressPlan.netapp_node_a_mgmt,
          node_b_mgmt: addressPlan.netapp_node_b_mgmt,
          status: "in_scope",
          svm_mgmt: addressPlan.netapp_svm_mgmt
        }
      : null,
    switch_primary: editor.deviceSelection.cisco ? addressPlan.cisco_management : null,
    server: editor.deviceSelection.server ? addressPlan.server_embedded_nic : null,
    storage_details: editor.deviceSelection.storage ? storageDetailsForProfile(editor) : null,
    utility_vm: addressPlan.ansible_control_host,
    vcenter: editor.deviceSelection.vcenter ? deviceDetailValue(editor, "vcenter", "endpoint") : null
  };
  const features: LabProfileFeatures = {
    ...editor.features,
    netapp_disabled_reason: editor.deviceSelection.netapp ? null : "NetApp excluded by lab profile.",
    netapp_enabled: editor.deviceSelection.netapp,
    storage_protocol: editor.deviceSelection.netapp ? editor.features.storage_protocol || "nfs" : "none",
    vcenter_disabled_reason: editor.deviceSelection.vcenter ? null : "vCenter excluded by lab profile.",
    vcenter_enabled: editor.deviceSelection.vcenter
  };
  const globalSettings: LabGlobalSettings = {
    dns_servers: dnsServers,
    domain_name: stringOrNull(deviceDetailValue(editor, "esxi", "dns_domain")),
    gateway: stringOrNull(editor.gateway),
    mtu,
    netapp_disabled_reason: features.netapp_disabled_reason,
    netapp_enabled: features.netapp_enabled,
    ntp_servers: ntpServers,
    subnet_prefix: parseIpv4Cidr(editor.subnet)?.prefix ?? 24,
    timezone: null,
    vlan_id: stringOrNull(editor.vlanId),
    vcenter_enabled: features.vcenter_enabled
  };
  return {
    address_plan: addressPlan,
    description: stringOrNull(editor.description),
    devices,
    dns: dnsServers,
    features,
    gateway: stringOrNull(editor.gateway),
    global_settings: globalSettings,
    mtu,
    name: editor.name.trim(),
    ntp: ntpServers,
    profile_topology: editor.profileTopology,
    subnet_cidr: editor.subnet.trim(),
    vlan_id: stringOrNull(editor.vlanId)
  };
}

function includedDeviceLabels(selection: ProfileDeviceSelection): string {
  const labels = profileDeviceDefinitions
    .filter((definition) => selection[definition.key])
    .map((definition) => definition.label);
  return labels.length ? labels.join(", ") : "None selected";
}

function profileDeviceLabel(deviceKey: ProfileDeviceKey): string {
  return profileDeviceDefinitions.find((definition) => definition.key === deviceKey)?.label ?? statusLabel(deviceKey);
}

function profileDeviceAddress(deviceKey: ProfileDeviceKey, addressPlan: LabAddressPlan): string {
  if (deviceKey === "cisco") return addressPlan.cisco_management ?? "";
  if (deviceKey === "server") return addressPlan.ilo_initial ?? addressPlan.ilo ?? addressPlan.server_embedded_nic ?? "";
  if (deviceKey === "storage") return addressPlan.ilo_initial ?? addressPlan.ilo ?? "";
  if (deviceKey === "esxi") return addressPlan.esxi_management ?? "";
  if (deviceKey === "netapp") return addressPlan.netapp_cluster_mgmt ?? addressPlan.netapp_node_a_mgmt ?? "";
  return "";
}

function firmwareTargetForDevice(editor: ProfileEditorState, deviceKey: ProfileDeviceKey): string {
  if (deviceKey === "server" || deviceKey === "storage") {
    return (
      editor.addressPlan.ilo_initial ??
      editor.addressPlan.ilo ??
      editor.addressPlan.server_embedded_nic ??
      ""
    );
  }
  return profileDeviceAddress(deviceKey, editor.addressPlan);
}

function addressPlanFieldLabel(field: keyof LabAddressPlan): string {
  const labels: Record<keyof LabAddressPlan, string> = {
    ansible_control_host: "Automation/control host IP",
    cisco_management: "Cisco management IP",
    esxi_management: "ESXi management IP",
    ilo: "iLO management IP",
    ilo_initial: "Initial iLO IP",
    netapp_cluster_mgmt: "Cluster management IP",
    netapp_controller_a_sp: "Controller A SP IP",
    netapp_controller_b_sp: "Controller B SP IP",
    netapp_iscsi_lifs: "iSCSI LIF IPs",
    netapp_nfs_lifs: "NFS LIF IPs",
    netapp_node_a_mgmt: "Node A management IP",
    netapp_node_b_mgmt: "Node B management IP",
    netapp_svm_mgmt: "SVM management IP",
    server_embedded_nic: "Server embedded NIC IP",
    subnet: "Subnet"
  };
  return labels[field];
}

function splitCsv(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function stringOrNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed || null;
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function booleanRecordValue(record: Record<string, unknown>, key: string, fallback: boolean): boolean {
  const value = record[key];
  return typeof value === "boolean" ? value : fallback;
}

function stringRecordValue(record: Record<string, unknown>, key: string, fallback = ""): string {
  const value = record[key];
  if (typeof value === "string") return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return fallback;
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

function elapsedLabel(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
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
