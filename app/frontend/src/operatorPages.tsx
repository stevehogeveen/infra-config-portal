import {
  Activity,
  AlertTriangle,
  Ban,
  CheckCircle2,
  ClipboardList,
  Gauge,
  HardDrive,
  Layers,
  Play,
  RefreshCw,
  Route,
  Save,
  Server,
  Settings,
  ShieldCheck,
  Wrench
} from "lucide-react";
import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "./api";
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

type ConfigValue = {
  label: string;
  source?: string;
  status?: string;
  value: string;
};

type AccessItem = {
  label: string;
  detail?: string;
  status?: string;
  value: string;
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
  disabledReason?: string;
  icon?: ReactNode;
  kind?: "read" | "write" | "apply" | "link" | "custom";
  label: string;
  onClick?: () => Promise<void> | void;
  primary?: boolean;
  to?: string;
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

export const LabConfigEditorContext = createContext<(() => void) | null>(null);

export function OperatorOverviewPage({
  health,
  labProfileError = "",
  labProfileLoading = false,
  labProfileState
}: OperatorPageProps) {
  const openConfigEditor = useContext(LabConfigEditorContext);
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

  const rows = useMemo(
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

  return (
    <OperatorPage title="Overview">
      <PageStatusHeader
        actions={
          <>
            <button disabled={loading} onClick={() => void load()} type="button">
              <RefreshCw size={16} />
              Refresh Access
            </button>
            <button className="primary" onClick={() => openConfigEditor?.()} type="button">
              <Settings size={16} />
              Edit Config
            </button>
          </>
        }
        description="This page shows what the app can currently access."
        helper="Change values here if your lab uses different IPs. Advanced proof is hidden unless you need it."
        icon={<Gauge size={26} />}
        title="Overview"
      />
      <Feedback loading={loading && !validation} error={error || labProfileError} />
      {labProfileLoading && <Feedback loading />}
      <section className="operator-section" aria-label="Active lab summary">
        <div className="operator-section-head">
          <div>
            <p className="operator-kicker">This is what I am working on</p>
            <h2>Active Lab Setup</h2>
            <p className="operator-muted">{activeProfile?.name ?? "No active setup"}</p>
            <p className="operator-muted">
              {labelize(activeProfile?.profile_topology ?? labProfileState?.active_context?.topology ?? "topology not set")}
              {" / "}
              {displayAddress(address.subnet)}
            </p>
          </div>
          <button onClick={() => openConfigEditor?.()} type="button">
            <Settings size={16} />
            Edit Config
          </button>
        </div>
      </section>
      <section className="operator-section" aria-label="Lab values">
        <div className="operator-section-head">
          <div>
            <p className="operator-kicker">These are the values</p>
            <h2>Lab Values</h2>
          </div>
        </div>
        <ConfigValueList values={labValues} />
      </section>
      <AccessTable rows={accessRows} />
      <AdvancedDrawer title="Advanced details" summary={noProofText}>
        <InventoryTable rows={rows} />
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

  return (
    <OperatorPage title="Network">
      <PageStatusHeader
        actions={<button disabled={loading} onClick={() => void load()} type="button"><RefreshCw size={16} />Refresh</button>}
        description="Use these buttons to test or change this part of the lab."
        helper="Cisco access, VLAN, subnet, gateway, switch access, DNS, NTP, SNMP, and MTU are grouped here."
        icon={<Route size={26} />}
        nextAction={humanize(asString(ciscoReadiness?.next_safe_action) || "Test Cisco access, then save switch config when ready.")}
        status={networkStatus}
        title="Network"
      />
      <Feedback loading={loading && !ciscoReadiness} error={error} />
      <AccessSummary
        items={[
          { label: "Cisco switch", value: displayAddress(address.cisco_management), status: networkStatus },
          { label: "Console", value: displayValue(asString(consoleState.selected_path) || asString(consoleState.effective_path)), detail: "First contact access" },
          { label: "SSH access", value: boolStateLabel(asBoolean(ciscoReadiness?.management_configured)), status: asBoolean(ciscoReadiness?.management_configured) ? "ready" : "not_checked" },
          { label: "Credentials", value: "Configured or missing only", detail: "Secret values are hidden" }
        ]}
      />
      <ConfigValueList
        values={[
          { label: "Subnet", value: displayAddress(address.subnet), source: "Saved setup" },
          { label: "Gateway", value: displayAddress(global?.gateway ?? activeProfile?.gateway), source: "Saved setup" },
          { label: "VLAN", value: displayValue(global?.vlan_id ?? activeProfile?.vlan_id), source: "Saved setup" },
          { label: "DNS", value: listLabel(global?.dns_servers ?? activeProfile?.dns), status: featureStatus(features, "enable_dns") },
          { label: "NTP", value: listLabel(global?.ntp_servers ?? activeProfile?.ntp), status: featureStatus(features, "enable_ntp") },
          { label: "SNMP", value: enabledLabel(features?.enable_snmp), status: featureStatus(features, "enable_snmp") },
          { label: "MTU", value: displayValue(global?.mtu ?? activeProfile?.mtu), source: "Saved setup" }
        ]}
      />
      <PageRunButtons
        actions={actions}
        buttons={[
          { actionIds: ["cisco.validate-ssh-scp", "cisco.privilege-check", "cisco.setup-readiness"], label: "Test Switch", primary: true },
          { actionIds: ["cisco.save-config"], kind: "write", label: "Save Config", icon: <Save size={16} /> },
          { actionIds: ["cisco.firmware-inventory"], label: "Scan Firmware" }
        ]}
        onReload={load}
      />
      <AdvancedDrawer title="Network proof" summary={noProofText}>
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

  return (
    <OperatorPage title="Server">
      <PageStatusHeader
        actions={<button disabled={loading} onClick={() => void load()} type="button"><RefreshCw size={16} />Refresh</button>}
        description="Use these buttons to test or change this part of the lab."
        helper="iLO, DL360 server, RAID layout, and ESXi access are grouped here."
        icon={<Server size={26} />}
        nextAction={humanize(asString(esxiReadiness?.next_safe_action) || "Test iLO and ESXi, then validate RAID when storage layout is ready.")}
        status={strongestStatus([iloStatus, esxiStatus, raidStatus])}
        title="Server"
      />
      <Feedback loading={loading && !providers.length} error={error} />
      <AccessSummary
        items={[
          { label: "iLO URL", value: address.ilo ? `https://${address.ilo}` : "Not set up yet", status: iloStatus },
          { label: "Server power", value: "Not checked", detail: "Power-changing actions stay guarded" },
          { label: "ESXi IP", value: displayAddress(address.esxi_management), status: esxiStatus },
          { label: "Credentials", value: "Configured or missing only", detail: "Secret values are hidden" }
        ]}
      />
      <ConfigValueList
        values={[
          { label: "Server", value: "HPE DL360", source: "Saved setup" },
          { label: "iLO IP", value: displayAddress(address.ilo), source: "Saved setup" },
          { label: "RAID layout", value: raidLayoutLabel(raidPlan), status: raidStatus },
          { label: "HPE Service Pack", value: servicePackSummary(firmwareSummaries), source: "Firmware files" },
          { label: "ESXi management", value: displayAddress(address.esxi_management), source: "Saved setup" },
          { label: "BIOS / iLO firmware", value: firmwareVersion(firmwareSummaries, "ilo") },
          { label: "ESXi version", value: firmwareVersion(firmwareSummaries, "esxi") }
        ]}
      />
      <PageRunButtons
        actions={actions}
        buttons={[
          { actionIds: ["ilo.reachability", "ilo.auth", "ilo.inventory"], label: "Test iLO", primary: true },
          { actionIds: ["esxi.management-validation", "esxi.ssh-api-check", "esxi.readiness"], label: "Test ESXi" },
          { actionIds: ["esxi.recover-management"], kind: "write", label: "Recover ESXi" },
          { actionIds: ["raid.validate", "raid.pending-check"], label: "Validate RAID" }
        ]}
        onReload={load}
      />
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

  return (
    <OperatorPage title="Storage">
      <PageStatusHeader
        actions={<button disabled={loading} onClick={() => void load()} type="button"><RefreshCw size={16} />Refresh</button>}
        description="Use these buttons to test or change this part of the lab."
        helper="NetApp access, ONTAP, NFS LIFs, volume, export policy, and datastore readiness are grouped here."
        icon={<HardDrive size={26} />}
        nextAction={humanize(asString(vcenterNetapp?.next_safe_action) || asString(nfsReadiness?.next_safe_action) || "Validate NFS, then mount the datastore when guarded apply is ready.")}
        status={storageStatus}
        title="Storage"
      />
      <Feedback loading={loading && !netappPlan} error={error} />
      <AccessSummary
        items={[
          { label: "Console access", value: displayValue(asString(objectValue(consoleReadiness?.runtime_state).console)), detail: "Advanced proof has details" },
          { label: "Cluster IP", value: displayAddress(address.netapp_cluster_mgmt), status: storageStatus },
          { label: "NFS LIF", value: listLabel(address.netapp_nfs_lifs), status: address.netapp_nfs_lifs.length ? "ready" : "not_configured_yet" },
          { label: "Credentials", value: "Configured or missing only", detail: "Secret values are hidden" }
        ]}
      />
      <ConfigValueList
        values={[
          { label: "ONTAP version", value: firmwareVersion(firmwareSummaries, "netapp") },
          { label: "Volume", value: displayValue(asString(plannedNfs.volume) || asString(plannedNfs.volume_name)) },
          { label: "Export policy", value: displayValue(asString(plannedNfs.export_policy)) },
          { label: "Datastore", value: datastoreName(vcenterNetapp), status: datastoreVisibleStatus(vcenterNetapp) },
          { label: "Cluster management", value: displayAddress(address.netapp_cluster_mgmt), source: "Saved setup" },
          { label: "SVM management", value: displayAddress(address.netapp_svm_mgmt), source: "Saved setup" }
        ]}
      />
      <PageRunButtons
        actions={actions}
        buttons={[
          { actionIds: ["netapp.live-state", "netapp.validate-setup", "netapp.setup-preview"], label: "Test NetApp", primary: true },
          { actionIds: ["netapp.nfs-setup-validate", "netapp.nfs-vcenter-readiness"], label: "Validate NFS" },
          { actionIds: ["esxi.netapp-datastore-apply", "netapp.nfs-setup-apply"], kind: "write", label: "Mount Datastore" }
        ]}
        onReload={load}
      />
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

  return (
    <OperatorPage title="Virtualization">
      <PageStatusHeader
        actions={<button disabled={loading} onClick={() => void load()} type="button"><RefreshCw size={16} />Refresh</button>}
        description="Use these buttons to test or change this part of the lab."
        helper="vCenter, ESXi attach, datastore visibility, VM inventory, and OVF deployment are grouped here."
        icon={<Layers size={26} />}
        nextAction={humanize(asString(vcenterNetapp?.next_safe_action) || "Test vCenter, then validate datastore and VM inventory visibility.")}
        status={virtualStatus}
        title="Virtualization"
      />
      <Feedback loading={loading && !vcenterNetapp} error={error} />
      <AccessSummary
        items={[
          { label: "vCenter target", value: target, status: virtualStatus },
          { label: "ESXi target", value: displayAddress(address.esxi_management), status: asString(objectValue(vcenterNetapp?.targets).esxi_management) ? "ready" : "not_checked" },
          { label: "Datastore", value: datastoreName(vcenterNetapp), status: datastoreVisibleStatus(vcenterNetapp || postAttach) },
          { label: "Credentials", value: credentialSummary(vcenterNetapp), detail: "Secret values are hidden" }
        ]}
      />
      <ConfigValueList
        values={[
          { label: "ESXi attach", value: attachStateLabel(vcenterNetapp, postAttach), status: virtualStatus },
          { label: "Datastore visibility", value: visibilityLabel(postChecks.netapp_datastore_visible ?? objectValue(vcenterNetapp?.checks).datastore_mounted), status: datastoreVisibleStatus(vcenterNetapp || postAttach) },
          { label: "VM inventory", value: visibilityLabel(postChecks.vm_inventory_visible), status: visibilityStatus(postChecks.vm_inventory_visible) },
          { label: "OVF deployment", value: "Ready after validation", status: "not_checked" },
          { label: "Access URL", value: target },
          { label: "Datastore name", value: datastoreName(vcenterNetapp) }
        ]}
      />
      <PageRunButtons
        actions={actions}
        buttons={[
          { actionIds: ["vcenter-netapp.readiness", "vcenter.install-readiness"], label: "Test vCenter", primary: true },
          { actionIds: ["esxi.vm-deploy-apply"], kind: "write", label: "Deploy VM" },
          { actionIds: ["esxi.vm-deploy-validate", "vcenter.post-attach-validation"], label: "Validate Inventory" }
        ]}
        onReload={load}
      />
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

export function OperatorFirmwareUpgradesPage() {
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
    const nextSelections = { ...selectedFiles, [componentId]: fileName };
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

  return (
    <OperatorPage title="Firmware Upgrades">
      <PageStatusHeader
        actions={<button disabled={loading} onClick={() => void load()} type="button"><RefreshCw size={16} />Refresh</button>}
        description="Firmware files are read from the local media folder."
        helper="Choose the file for each device. Upgrade stays gated until the path is validated."
        icon={<ShieldCheck size={26} />}
        status={firmwareStatus}
        title="Firmware Upgrades"
      />
      <Feedback loading={loading && !firmwareSummaries.length} error={error} />
      <FirmwareFilesPanel
        directory="/home/administrator/infra-config-portal/artifacts/Media"
        lastScanned={files.lastScanned}
        loading={loading}
        onRescan={() => void load()}
        packageCount={files.packageCount}
        selectionStatus={selectionStatusLabel(fileSelections, savingSelection)}
      />
      <Feedback loading={false} error={selectionError} />
      <FirmwarePathTable
        rows={rows}
        selectedFiles={selectedFiles}
        onSelect={(componentId, fileName) => void saveFileSelection(componentId, fileName)}
      />
      <PageRunButtons
        actions={actions}
        buttons={[
          { actionIds: ["firmware.inventory", "firmware.compliance-check"], label: "Scan Firmware", primary: true },
          { actionIds: ["firmware.upgrade-plan", "netapp.ontap-upgrade-plan"], label: "Validate Upgrade Path" },
          { actionIds: ["firmware.upgrade-apply-placeholder", "netapp.ontap-upgrade-apply"], kind: "apply", label: "Upgrade" }
        ]}
        onReload={load}
      />
      <AdvancedDrawer title="Firmware proof" summary={noProofText}>
        <ValidationProofList
          items={[]}
          proofLinks={firmwareSummaries.reduce((count, summary) => count + summary.evidence_artifacts.length, 0)}
        />
      </AdvancedDrawer>
    </OperatorPage>
  );
}

export function OperatorValidationPage() {
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

  return (
    <OperatorPage title="Validation">
      <PageStatusHeader
        actions={<button disabled={loading} onClick={() => void load()} type="button"><RefreshCw size={16} />Refresh</button>}
        description="Use these buttons to test or change this part of the lab."
        helper="Golden State means expected working lab state. Advanced proof is hidden unless you need it."
        icon={<CheckCircle2 size={26} />}
        nextAction={humanize(validation?.next_action || "Run validation, then generate the handoff.")}
        status={validation?.overall_status ?? "not_checked"}
        title="Validation"
      />
      <Feedback loading={loading && !validation} error={error} />
      <AccessSummary
        items={[
          { label: "Golden State", value: "Expected working lab state.", status: validation?.overall_status ?? "not_checked" },
          { label: "Different from expected", value: String(differentFromExpected), status: differentFromExpected ? "warning" : "ready" },
          { label: "Build Verification", value: displayStatus(buildVerification?.status ?? "not_checked"), status: buildVerification?.status ?? "not_checked" },
          { label: "Handoff", value: validation?.handoff_report ? "Ready to generate" : "Not generated", status: validation?.handoff_report ? "ready" : "not_checked" }
        ]}
      />
      <ConfigValueList
        values={[
          { label: "vCenter-NetApp readiness", value: displayStatus(vcenterNetapp?.status ?? "not_checked"), status: vcenterNetapp?.status ?? "not_checked" },
          { label: "Top blocker", value: validation?.top_blocker?.problem ?? "None", status: validation?.top_blocker ? "blocked" : "ready" },
          { label: "Checked", value: validation?.generated_at ? formatDateTime(validation.generated_at) : "Not checked" }
        ]}
      />
      <PageRunButtons
        actions={actions}
        buttons={[
          { actionIds: ["full-lab.validation", "build-verification.run-full"], label: "Run Validation", primary: true },
          { actionIds: ["full-lab.handoff-report"], label: "Generate Handoff", onClick: async () => { await api.labValidationHandoff(); } }
        ]}
        onReload={load}
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
  const [actions, setActions] = useState<WorkflowAction[]>([]);
  const [vcenterNetapp, setVcenterNetapp] = useState<ProviderProbeResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    setLoading(true);
    try {
      const [nextActions, nextVcenterNetapp] = await Promise.all([
        safeApi(api.workflowActions, [] as WorkflowAction[]),
        safeApi(api.vcenterNetappReadiness, null)
      ]);
      setActions(Array.isArray(nextActions) ? nextActions : []);
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

  return (
    <OperatorPage title="Settings">
      <PageStatusHeader
        actions={<button disabled={loading || labProfileLoading} onClick={() => void load()} type="button"><RefreshCw size={16} />Refresh</button>}
        description="Use these buttons to test or change this part of the lab."
        helper="Active lab setup values, IP layout, console mappings, credential status, and feature toggles are kept here."
        icon={<Settings size={26} />}
        nextAction={labProfileState?.next_safe_action ?? "Review the active lab setup before running validation."}
        status={activeProfile ? "ready" : "not_configured_yet"}
        title="Settings"
      />
      <Feedback loading={loading && !activeProfile} error={error || labProfileError} />
      <section className="operator-section" aria-label="Active lab setup values">
        <div className="operator-section-head">
          <div>
            <p className="operator-kicker">Active lab setup</p>
            <h2>{activeProfile?.name ?? "No active setup"}</h2>
          </div>
          <SimpleStatusPill status={runtimeStatus(health ?? null)} />
        </div>
        <ConfigValueList
          values={[
            { label: "Subnet", value: displayAddress(address.subnet), source: "Saved setup" },
            { label: "Beginning IPs / offsets", value: offsetSummary(address), source: "Saved setup" },
            { label: "iLO IP", value: displayAddress(address.ilo), source: "Saved setup" },
            { label: "Cisco IP", value: displayAddress(address.cisco_management), source: "Saved setup" },
            { label: "ESXi IP", value: displayAddress(address.esxi_management), source: "Saved setup" },
            { label: "NetApp IPs", value: netappAddressSummary(address), source: "Saved setup" },
            { label: "vCenter target", value: vcenterTarget(vcenterNetapp, activeProfile), source: "Saved or discovered" }
          ]}
        />
      </section>
      <section className="operator-section" aria-label="Credentials and feature toggles">
        <div className="operator-section-head">
          <div>
            <p className="operator-kicker">Credential status</p>
            <h2>Configured or missing only</h2>
          </div>
        </div>
        <ConfigValueList
          values={[
            { label: "Cisco", value: "Configured or missing", status: "not_checked" },
            { label: "iLO", value: "Configured or missing", status: "not_checked" },
            { label: "ESXi", value: "Configured or missing", status: "not_checked" },
            { label: "NetApp", value: netappCredentialStatus(vcenterNetapp), status: netappCredentialStatus(vcenterNetapp) === "Configured" ? "ready" : "not_checked" },
            { label: "vCenter", value: vcenterCredentialStatus(vcenterNetapp), status: vcenterCredentialStatus(vcenterNetapp) === "Configured" ? "ready" : "not_checked" },
            { label: "DNS / NTP / SNMP", value: featureToggleSummary(features), source: "Saved setup" },
            { label: "Gateway", value: displayAddress(global?.gateway ?? activeProfile?.gateway), source: "Saved setup" },
            { label: "Console mappings", value: "Refresh consoles to discover current ports", status: "not_checked" }
          ]}
        />
      </section>
      <PageRunButtons
        actions={actions}
        buttons={[
          { disabledReason: "No unsaved setup changes are open on this page.", icon: <Save size={16} />, kind: "custom", label: "Save Setup", primary: true },
          { actionIds: ["build-verification.run-full", "full-lab.validation"], label: "Test Credentials" },
          { actionIds: ["cisco.discover-console", "netapp.console-autodiscovery"], label: "Refresh Consoles" }
        ]}
        onReload={load}
      />
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
  actions,
  description,
  helper,
  icon,
  nextAction,
  status,
  title
}: {
  actions?: ReactNode;
  description: string;
  helper: string;
  icon: ReactNode;
  nextAction?: string;
  status?: string;
  title: string;
}) {
  return (
    <header className="operator-status-header">
      <div className="operator-status-icon">{icon}</div>
      <div className="operator-status-main">
        <p className="operator-kicker">Lab Builder</p>
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
        {actions && <div className="operator-header-actions">{actions}</div>}
      </div>
    </header>
  );
}

function AccessSummary({ items }: { items: AccessItem[] }) {
  return (
    <section className="operator-section" aria-label="Access information">
      <div className="operator-section-head">
        <div>
          <p className="operator-kicker">Access information</p>
          <h2>How this part of the lab is reached</h2>
        </div>
      </div>
      <div className="access-summary">
        {items.map((item) => (
          <article key={`${item.label}-${item.value}`}>
            <div>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
              {item.detail && <p>{item.detail}</p>}
            </div>
            {item.status && <SimpleStatusPill status={item.status} />}
          </article>
        ))}
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

function PageRunButtons({
  actions,
  buttons,
  onReload
}: {
  actions: WorkflowAction[];
  buttons: RunButtonDefinition[];
  onReload: () => Promise<void> | void;
}) {
  const [runState, setRunState] = useState<WorkflowRunState>(emptyRunState);
  const byId = useMemo(() => new Map(actions.map((action) => [action.action_id, action])), [actions]);

  async function runAction(action: WorkflowAction, request?: WorkflowActionRunRequest) {
    setRunState({ error: "", message: "", runningActionId: action.action_id });
    try {
      const result = await api.runWorkflowAction(action.action_id, request);
      setRunState({
        error: "",
        message: `${humanWorkflowActionLabel(action)}: ${humanize(result.summary || result.next_action || displayStatus(result.status))}`,
        runningActionId: ""
      });
      await onReload();
    } catch (err) {
      setRunState({ error: errorMessage(err), message: "", runningActionId: "" });
    }
  }

  return (
    <section className="operator-section" aria-label="Run buttons">
      <div className="operator-section-head">
        <div>
          <p className="operator-kicker">Run / Test / Apply</p>
          <h2>Actions for this page</h2>
        </div>
      </div>
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
    </section>
  );
}

function InventoryTable({ rows }: { rows: InventoryRow[] }) {
  return (
    <section className="operator-section" aria-label="Hardware and software inventory">
      <div className="operator-section-head">
        <div>
          <p className="operator-kicker">Inventory</p>
          <h2>Hardware and software</h2>
        </div>
        <span>{rows.length} items</span>
      </div>
      <div className="operator-table-wrap">
        <table className="operator-table inventory-table">
          <thead>
            <tr>
              <th>Item</th>
              <th>Role</th>
              <th>Access target</th>
              <th>Version</th>
              <th>Status</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.item}>
                <td><strong>{row.item}</strong></td>
                <td>{row.role}</td>
                <td>{row.accessTarget}</td>
                <td>{row.version}</td>
                <td><SimpleStatusPill status={row.status} /></td>
                <td>{row.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function AccessTable({ rows }: { rows: AccessRow[] }) {
  return (
    <section className="operator-section" aria-label="Currently Accessible">
      <div className="operator-section-head">
        <div>
          <p className="operator-kicker">This is what the app can see</p>
          <h2>Currently Accessible</h2>
        </div>
        <span>{rows.filter((row) => row.status === "accessible").length} accessible</span>
      </div>
      <div className="operator-table-wrap">
        <table className="operator-table access-table">
          <thead>
            <tr>
              <th>Item</th>
              <th>Target</th>
              <th>Status</th>
              <th>App can see</th>
              <th>Needs before it can see it</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.item}>
                <td><strong>{row.item}</strong></td>
                <td>{row.target}</td>
                <td><SimpleStatusPill status={row.status} /></td>
                <td>{row.appSees}</td>
                <td>{row.needs}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
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

function FirmwarePathTable({
  onSelect,
  rows,
  selectedFiles
}: {
  onSelect: (componentId: string, fileName: string) => void;
  rows: FirmwareTableRow[];
  selectedFiles: Record<string, string>;
}) {
  return (
    <section className="operator-section" aria-label="Firmware upgrade path">
      <div className="operator-section-head">
        <div>
          <p className="operator-kicker">Firmware Table</p>
          <h2>Equipment and selected files</h2>
        </div>
      </div>
      <div className="operator-table-wrap">
        <table className="operator-table firmware-path-table">
          <thead>
            <tr>
              <th>Equipment</th>
              <th>Component</th>
              <th>Current Version</th>
              <th>Target Version</th>
              <th>Selected File</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.componentId}>
                <td><strong>{row.equipment}</strong></td>
                <td>{row.component}</td>
                <td>{row.current}</td>
                <td>{row.target}</td>
                <td>
                  <div className="firmware-file-cell">
                    <select
                      aria-label={`${row.equipment} ${row.component} firmware file`}
                      onChange={(event) => onSelect(row.componentId, event.target.value)}
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
                    <span>{row.selectedFileName || "No file selected"}</span>
                    <small>{selectionSourceLabel(row.selectionSource)}</small>
                  </div>
                </td>
                <td><SimpleStatusPill status={row.pathStatus} /></td>
                <td>
                  <div className="firmware-row-actions">
                    <button type="button">Scan</button>
                    <button type="button">Validate Path</button>
                    <button disabled={row.pathStatus !== "ready_to_upgrade"} type="button">Upgrade</button>
                  </div>
                  <span className="operator-muted">{row.action}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

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
          <p className="operator-muted">Firmware files are read from this folder. Use the HPE Service Pack for server BIOS and Smart Array updates, and pick a different file if the app chose the wrong one.</p>
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
  return <span className={`simple-status-pill ${statusTone(status)}`}>{displayStatus(status)}</span>;
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

function disabledReasonFor(button: RunButtonDefinition, action: WorkflowAction | null): string {
  if (button.kind === "custom" && !button.onClick) {
    return button.disabledReason || "This action is not ready yet.";
  }
  if (!action) {
    return "Action is not registered yet.";
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

function isChangingAction(action: WorkflowAction): boolean {
  return ["write", "destructive", "upgrade"].includes(action.mode);
}

function humanWorkflowActionLabel(action: WorkflowAction): string {
  return humanize(action.label || action.action_id);
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
      target: displayValue(path.target_version)
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
    summary.upgrade_paths.filter((path) => ["hpe_bios_version", "hpe_smart_array_firmware"].includes(path.component_id))
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
  if (source === "live_probe" || source === "live_cached") return "Live";
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
