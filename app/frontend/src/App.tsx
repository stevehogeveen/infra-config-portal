import {
  Activity,
  AlertTriangle,
  Ban,
  CheckCircle2,
  ClipboardList,
  Pencil,
  Gauge,
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
  Workflow,
  XCircle
} from "lucide-react";
import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import { Link, NavLink, Route as RouterRoute, Routes, useNavigate, useParams } from "react-router-dom";

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
  HpeRaidIntent,
  HpeRaidIntentWrite,
  HpeRaidPlanPreview,
  HpeRaidVolumeIntent,
  HpeStorageDiscovery,
  IloSetupIntent,
  IloSetupIntentWrite,
  IloSetupPlanPreview,
  IloUpgradeReadiness,
  MediaInventory,
  NetAppConsoleReadiness,
  NetAppObservationUpdate,
  NetAppProviderArtifact,
  NetAppPlanPreview,
  NetAppReadinessComparison,
  NetAppUpgradeReadiness,
  ProviderAction,
  ProviderProbeResult,
  ProviderStatus,
  ReadinessIssue,
  RequestReadiness,
  RequestRecord,
  RequestStatus,
  VMDeploymentCreate,
  VMDeploymentUpdate,
  WorkflowRun
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
    empty: "No planned requests are ready for mock execution."
  },
  {
    id: "executing",
    title: "Executing",
    empty: "No mock workflow is executing."
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

function App() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" to="/">
          <Server size={22} />
          <span>infra-config-portal</span>
        </Link>
        <nav>
          <NavItem to="/" icon={<Gauge size={18} />} label="Dashboard" />
          <NavItem to="/run-center" icon={<Workflow size={18} />} label="Run Center" />
          <NavItem to="/requests" icon={<ClipboardList size={18} />} label="VM Requests" />
          <NavItem to="/requests/new" icon={<Plus size={18} />} label="New VM Request" />
          <NavItem to="/audit-events" icon={<History size={18} />} label="Audit Events" />
          <NavItem to="/artifacts" icon={<HardDrive size={18} />} label="Reports / Artifacts" />
          <NavItem to="/media" icon={<HardDrive size={18} />} label="Media Inventory" />
          <NavItem to="/providers" icon={<Activity size={18} />} label="Provider Status" />
        </nav>
      </aside>
      <main className="content">
        <MockModeBanner />
        <Routes>
          <RouterRoute path="/" element={<Dashboard />} />
          <RouterRoute path="/run-center" element={<RunCenter />} />
          <RouterRoute path="/requests" element={<RequestListPage />} />
          <RouterRoute path="/requests/new" element={<NewRequest />} />
          <RouterRoute path="/requests/:id" element={<RequestDetail />} />
          <RouterRoute path="/workflow-runs/:id" element={<WorkflowRunDetail />} />
          <RouterRoute path="/audit-events" element={<AuditEvents />} />
          <RouterRoute path="/artifacts" element={<ProviderArtifactsPage />} />
          <RouterRoute path="/media" element={<MediaInventoryPage />} />
          <RouterRoute path="/providers" element={<ProviderStatusPage />} />
        </Routes>
      </main>
    </div>
  );
}

function NavItem({ to, icon, label }: { to: string; icon: ReactNode; label: string }) {
  return (
    <NavLink to={to} className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}>
      {icon}
      <span>{label}</span>
    </NavLink>
  );
}

function Dashboard() {
  const [requests, setRequests] = useState<RequestRecord[]>([]);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [readinessByRequest, setReadinessByRequest] = useState<ReadinessMap>({});
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

  return (
    <Page title="Dashboard" actions={<ButtonLink to="/requests/new" icon={<Plus size={16} />} label="New VM" />}>
      <Feedback loading={loading} error={error} />
      <section className="metric-grid">
        <Metric label="Ready To Approve" value={readyToApprove} icon={<ShieldCheck size={18} />} />
        <Metric label="Ready To Plan" value={readyToPlan} icon={<Workflow size={18} />} />
        <Metric label="Ready To Execute" value={readyToExecute} icon={<Play size={18} />} />
        <Metric label="Blocked / Failed" value={blockedItems.length} icon={<AlertTriangle size={18} />} />
      </section>
      <section className="dashboard-grid">
        <div className="panel">
          <PanelTitle icon={<Route size={18} />} title="Next Recommended Actions" />
          <QueueItemList
            empty="No operator action is waiting. Completed work is available in Run Center."
            items={nextActionItems}
          />
        </div>
        <div className="panel">
          <PanelTitle icon={<Workflow size={18} />} title="Run Center Handoff" />
          <div className="handoff-summary">
            <Info label="Total Requests" value={String(requests.length)} />
            <Info label="Planned" value={String(counts.planned ?? 0)} />
            <Info label="Executing" value={String(counts.executing ?? 0)} />
            <Info label="Completed" value={String(counts.completed ?? 0)} />
          </div>
          <p className="muted">
            Use Run Center to approve, plan, execute, monitor, and review mock workflow runs.
          </p>
          <Link className="button-link primary" to="/run-center">
            <Workflow size={16} />
            Open Run Center
          </Link>
        </div>
      </section>
      <section className="panel">
        <PanelTitle icon={<Layers size={18} />} title="Recent Requests" />
        <RequestTable readinessByRequest={readinessByRequest} requests={requests.slice(0, 10)} showNextAction />
        <Link className="button-link request-list-link" to="/requests">
          <ClipboardList size={16} />
          View All Requests
        </Link>
      </section>
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

function RunCenter() {
  const [requests, setRequests] = useState<RequestRecord[]>([]);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [readinessByRequest, setReadinessByRequest] = useState<ReadinessMap>({});
  const [netappPlanPreview, setNetappPlanPreview] = useState<NetAppPlanPreview | null>(null);
  const [netappArtifacts, setNetappArtifacts] = useState<NetAppProviderArtifact[]>([]);
  const [netappConsoleReadiness, setNetappConsoleReadiness] = useState<NetAppConsoleReadiness | null>(null);
  const [netappReadinessComparison, setNetappReadinessComparison] = useState<NetAppReadinessComparison | null>(null);
  const [netappUpgradeReadiness, setNetappUpgradeReadiness] = useState<NetAppUpgradeReadiness | null>(null);
  const [selectedQueueKey, setSelectedQueueKey] = useState("");
  const [error, setError] = useState("");
  const [netappError, setNetappError] = useState("");
  const [loading, setLoading] = useState(true);
  const [netappLoading, setNetappLoading] = useState(true);

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

  async function loadNetAppPlanPreview() {
    setNetappError("");
    setNetappLoading(true);
    try {
      const [
        nextPreview,
        nextConsoleReadiness,
        nextReadinessComparison,
        nextUpgradeReadiness,
        nextArtifacts
      ] = await Promise.all([
        api.netappPlanPreview(),
        api.netappConsoleReadiness(),
        api.netappReadinessComparison(),
        api.netappUpgradeReadiness(),
        api.netappArtifacts()
      ]);
      setNetappPlanPreview(nextPreview);
      setNetappConsoleReadiness(nextConsoleReadiness);
      setNetappReadinessComparison(nextReadinessComparison);
      setNetappUpgradeReadiness(nextUpgradeReadiness);
      setNetappArtifacts(nextArtifacts);
    } catch (err) {
      setNetappError((err as Error).message);
    } finally {
      setNetappLoading(false);
    }
  }

  useEffect(() => {
    load();
    loadNetAppPlanPreview();
  }, []);

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
  }, [firstActionableKey, queueItemKeySignature]);

  const selectedItem = queueItems.find((item) => item.key === selectedQueueKey) ?? queueItems[0] ?? null;
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

  return (
    <Page
      title="Run Center"
      actions={
        <>
          <button onClick={load} disabled={loading}>
            <RefreshCw size={16} />
            Refresh
          </button>
        </>
      }
    >
      <Feedback loading={loading} error={error} />
      <section className="operator-metric-grid">
        <Metric label="Needs Approval" value={needsApproval} icon={<ShieldCheck size={18} />} />
        <Metric label="Ready To Plan" value={readyToPlan} icon={<Workflow size={18} />} />
        <Metric label="Ready To Execute" value={readyToExecute} icon={<Play size={18} />} />
        <Metric label="Executing" value={executing} icon={<Activity size={18} />} />
        <Metric label="Blocked / Failed" value={blocked} icon={<AlertTriangle size={18} />} />
        <Metric label="Completed" value={completed} icon={<CheckCircle2 size={18} />} />
      </section>
      <section className="operator-queue-grid">
        {queueSections.map((section) => (
          <QueueSectionPanel
            key={section.id}
            onSelect={setSelectedQueueKey}
            section={section}
            selectedKey={selectedItem?.key ?? ""}
          />
        ))}
      </section>
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
      <NetAppRunCenterPreview
        artifacts={netappArtifacts}
        consoleReadiness={netappConsoleReadiness}
        error={netappError}
        loading={netappLoading}
        onRefresh={loadNetAppPlanPreview}
        preview={netappPlanPreview}
        readinessComparison={netappReadinessComparison}
        upgradeReadiness={netappUpgradeReadiness}
      />
    </Page>
  );
}

function NetAppRunCenterPreview({
  artifacts,
  consoleReadiness,
  error,
  loading,
  onRefresh,
  preview,
  readinessComparison,
  upgradeReadiness
}: {
  artifacts: NetAppProviderArtifact[];
  consoleReadiness: NetAppConsoleReadiness | null;
  error: string;
  loading: boolean;
  onRefresh: () => void;
  preview: NetAppPlanPreview | null;
  readinessComparison: NetAppReadinessComparison | null;
  upgradeReadiness: NetAppUpgradeReadiness | null;
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
        <PanelTitle icon={<HardDrive size={18} />} title="NetApp ONTAP Plan Preview" />
        <button onClick={onRefresh} disabled={loading}>
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>
      <div className="provider-callout netapp-apply-disabled">
        <strong>Preview only / Apply disabled</strong>
        <p>
          No ONTAP calls are made. This Run Center section has no confirmation, start,
          execute, apply, cluster creation, SVM/LIF/volume creation, upgrade, reboot, or wipe control.
        </p>
      </div>
      <Feedback loading={loading && !preview} error={error} />
      {preview ? (
        <>
          <div className="provider-fact-grid compact">
            <ProviderFact label="Provider" value={preview.provider_id} />
            <ProviderFact label="Mode" value={preview.mode} />
            <ProviderFact label="Apply Enabled" value={preview.apply_enabled ? "Enabled" : "Disabled"} />
            <ProviderFact label="NETAPP_CONFIGURED" value={preview.netapp_configured ? "true" : "false"} />
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
            <p>Setup: {labelize(asString(setupReadiness.status) || "blocked preview only")}. Upgrade: {labelize(asString(upgradeReadinessSummary.status) || "blocked until setup ready")}.</p>
          </div>
          <h3>Readiness Sections</h3>
          <NetAppReadinessGrid readiness={preview.readiness_buckets} />
          <h3>Blockers / Warnings</h3>
          <NetAppRunCenterIssues
            blockers={preview.blockers}
            removableWarnings={preview.removable_warnings}
            warnings={preview.warnings}
          />
          <h3>Planned vs Observed</h3>
          <NetAppReadinessComparisonPanel comparison={readinessComparison} />
          <h3>Console / Bootstrap Readiness</h3>
          <NetAppConsoleReadinessPanel onRefresh={onRefresh} readiness={consoleReadiness} />
          <h3>Cluster / SVM / LIF Intent</h3>
          <div className="provider-fact-grid compact">
            <ProviderFact label="Cluster Management IP" value={asString(cluster.management_ip) || "-"} />
            <ProviderFact label="SVM Management IP" value={asString(svm.management_ip) || "-"} />
          </div>
          <KeyValueTable rows={recordArray(cluster.nodes)} labelKey="name" valueKey="management_ip" empty="No node management intent is planned." />
          <KeyValueTable rows={recordArray(lifIntent.iscsi_lifs)} labelKey="name" valueKey="address" empty="No iSCSI LIF intent is planned." />
          <div className="run-center-preview-grid">
            <div>
              <h3>Storage / iSCSI Preview</h3>
              <PreviewNoteBlock payload={storagePreview} fallback="Storage/iSCSI preview placeholder only. No volumes, LUNs, igroups, or LIFs are created." />
            </div>
            <div>
              <h3>Upgrade Readiness Preview</h3>
              <NetAppUpgradeReadinessPanel readiness={upgradeReadiness} fallbackPreview={upgradePreview} />
            </div>
          </div>
          <h3>Artifact / Report Placeholders</h3>
          <div className="tag-row netapp-artifact-row">
            {preview.artifact_placeholders.map((artifact) => (
              <span key={artifact}>{artifact}</span>
            ))}
          </div>
          <h3>Persisted Mock Artifact Metadata</h3>
          <NetAppProviderArtifactList artifacts={artifacts} />
          <h3>Disabled Dangerous Actions</h3>
          <DisabledActionList actions={disabledActions} />
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
        <strong>Offline media preview only</strong>
        <p>No ONTAP calls are made. Upgrade and apply remain disabled.</p>
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
      setSaveMessage("Saved locally in the mock observation store. Nothing was sent to NetApp.");
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
        <ProviderFact label="NETAPP_CONFIGURED" value={readiness.netapp_configured ? "true" : "false"} />
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
        <strong>Local/mock-only status capture</strong>
        <p>No serial port is opened, no console command is sent, and these observations are not sent to NetApp.</p>
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Stored Locally" value={observations?.mock_only ? "Mock only" : "Mock only"} />
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
        <p className="muted">Do not paste passwords, tokens, or raw configs. Notes are local/mock-only and bounded to 1200 characters.</p>
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
            <ProviderFact label="Mock Only" value={artifact.mock_only ? "true" : "false"} />
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
        No provider artifact metadata matches the current filters. Provider artifacts are mock-only
        placeholders until a future approved reporting workflow is added.
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
        <ProviderFact label="Mock Only" value={artifact.mock_only ? "true" : "false"} />
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

  async function load() {
    setError("");
    setLoading(true);
    try {
      const [
        providerStatuses,
        ciscoReadiness,
        setupWizardPlan,
        bootstrapRequirements,
        consoleBootstrapPlan
      ] = await Promise.all([
        api.providers(),
        api.ciscoSetupReadiness(),
        api.ciscoSetupWizardPlan(),
        api.ciscoBootstrapRequirements(),
        api.ciscoConsoleBootstrapPlan()
      ]);
      setProviders(providerStatuses);
      setCiscoSetupReadiness(ciscoReadiness);
      setCiscoSetupWizardPlan(setupWizardPlan);
      setCiscoBootstrapRequirements(bootstrapRequirements);
      setCiscoConsoleBootstrapPlan(consoleBootstrapPlan);
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
  const providerSections = useMemo(
    () => buildProviderSections(orderedProviders),
    [orderedProviders]
  );
  const [activeSectionId, setActiveSectionId] = useState("ilo");
  const activeSection = providerSections.find((section) => section.id === activeSectionId) ?? providerSections[0];
  const activeProviders = activeSection
    ? orderedProviders.filter((provider) => activeSection.providerIds.includes(provider.id))
    : [];

  useEffect(() => {
    if (!providerSections.length) return;
    if (!providerSections.some((section) => section.id === activeSectionId)) {
      setActiveSectionId(providerSections[0].id);
    }
  }, [activeSectionId, providerSections]);

  return (
    <Page
      title="Provider Status"
      actions={
        <button onClick={load} disabled={loading || Boolean(busyProvider)}>
          <RefreshCw size={16} />
          Refresh
        </button>
      }
    >
      <Feedback loading={loading && !providers.length} error={error} />
      {providerSections.length > 0 && (
        <ProviderSectionTabs
          activeSectionId={activeSection?.id ?? ""}
          busy={Boolean(busyProvider) || busyPromptReadiness || busyBootstrapRequirements}
          onSelect={setActiveSectionId}
          sections={providerSections}
        />
      )}
      <section className="provider-status-stack">
        {activeSection?.id === "cisco" && ciscoSetupReadiness && (
          <CiscoSetupReadinessPanel
            bootstrapRequirements={ciscoBootstrapRequirements}
            busyBootstrapRequirements={busyBootstrapRequirements}
            consoleBootstrapPlan={ciscoConsoleBootstrapPlan}
            onSaveBootstrapRequirements={saveBootstrapRequirements}
            readiness={ciscoSetupReadiness}
            setupWizardPlan={ciscoSetupWizardPlan}
          />
        )}
        {activeProviders.map((provider) => (
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
        {!loading && activeSection && activeProviders.length === 0 && (
          <section className="provider-card provider-card-wide">
            <div className="provider-head">
              <HardDrive size={18} />
              <div>
                <h2>{activeSection.label}</h2>
                <p>No provider status is available for this section.</p>
              </div>
              <StatusBadge status="missing-config" />
            </div>
          </section>
        )}
      </section>
    </Page>
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
    ? "Review setup wizard plan preview."
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
          <strong>Preview only</strong>
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
            : "Setup wizard/default prompt planning preview"}
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
        <SetupPreviewBlock title="Why Blocked" tag="Preview only" lines={plan.why_blocked} />
        <SetupPreviewBlock
          title="Future Guarded Workflow"
          tag="Preview only"
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
  const lastResult = probeResult ?? provider.last_probe_result;

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
      <p>{provider.message}</p>
      <ProviderFactGrid provider={provider} />
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
      {provider.id !== "netapp-ontap" && (
        <ProviderIssueRows blockers={provider.blockers} warnings={provider.warnings} />
      )}
      <ProviderActionRows
        busy={busy}
        disabledActions={provider.disabled_actions}
        onProbe={onProbe}
        safeActions={provider.safe_actions}
      />
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
    </article>
  );
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
  const effectivePath = asString(discovery.effective_path);
  const recommendedPath = asString(discovery.recommended_path);
  const operatorMessage = asString(discovery.operator_message);
  const operatorChecklist = stringArray(discovery.operator_checklist);
  const permissionGuidance = asString(discovery.permission_guidance);
  const missingConsole = candidates.length === 0 || asString(discovery.status) === "missing-console";
  const stableCandidates = candidates.filter((candidate) => candidate.stable_path && candidate.exists);
  const fallbackCandidates = candidates.filter((candidate) => !candidate.stable_path && candidate.exists);
  const hasPermissionIssue = candidates.some(
    (candidate) => candidate.exists && (candidate.readable === false || candidate.writable === false)
  );
  const promptReadinessEnabled = provider.mode === "local-readonly" && provider.status === "ready";

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
          label="Env Override"
          value={asBoolean(envOverride.configured) ? asString(envOverride.path) || "Configured" : "Not configured"}
        />
        <ProviderFact label="Recommended Path" value={recommendedPath || "-"} />
        <ProviderFact label="Effective Path" value={effectivePath || "-"} />
        <ProviderFact label="Baud" value={asString(provider.configuration.baud) || "9600"} />
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Existing Candidates" value={`${asNumber(candidateCounts.existing, candidates.filter((candidate) => candidate.exists).length)}`} />
        <ProviderFact
          label="Stable / Fallback"
          value={`${asNumber(candidateCounts.stable_existing, candidates.filter((candidate) => candidate.stable_path && candidate.exists).length)} / ${asNumber(candidateCounts.fallback_existing, candidates.filter((candidate) => !candidate.stable_path && candidate.exists).length)}`}
        />
      </div>
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
              <span className="action-tag read-only">Newline only</span>
              <p>
                Sends newline only and reads the redacted prompt state. No show commands are run by this check.
              </p>
              {!promptReadinessEnabled && (
                <p>
                  Requires PROVIDER_MODE=local-readonly, lab read-only acknowledgements, and one ready console path.
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
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
      <IloSetupIntentPanel
        busy={setupBusy}
        error={setupError}
        intent={setupIntent}
        onSave={saveSetupIntent}
        plan={setupPlan}
        savedMessage={setupSavedMessage}
      />
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
      <EsxiInstallReadinessPanel
        busy={raidPostApplyBusy}
        onRefresh={refreshEsxiInstallReadiness}
        readiness={esxiInstallReadiness}
      />
      <IloUpgradeDecisionPanel error={error} readiness={readiness} />
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

  return (
    <div className="provider-detail-section netapp-setup">
      <div className="provider-callout netapp-apply-disabled">
        <strong>Apply disabled / preview only</strong>
        <p>
          Planned target display only. Cluster creation, IP changes, SVM/LIF creation, volume
          provisioning, ONTAP upgrades, controller reboots, disk wipes, and configuration apply are disabled.
        </p>
      </div>
      <div className="provider-callout">
        <strong>Plan-preview endpoint</strong>
        <p>
          {planError
            ? `Plan preview unavailable: ${planError}`
            : planPreview
              ? "Loaded from /api/v1/providers/netapp-ontap/plan-preview."
              : "Loading structured plan preview."}
        </p>
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="NETAPP_CONFIGURED" value={asBoolean(planPreview?.netapp_configured ?? provider.configuration.netapp_configured) ? "true" : "false"} />
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
      <h3>Planned Targets</h3>
      <KeyValueTable rows={targetAddressing} labelKey="label" valueKey="address" empty="No NetApp target addresses are planned." />
      <h3>Current / Discovered Targets</h3>
      <KeyValueTable rows={currentAddressing} labelKey="label" valueKey="address" empty="No NetApp current targets have been discovered." />
      <h3>Readiness Preview</h3>
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
      <h3>Storage / iSCSI Plan Preview</h3>
      <div className="provider-callout">
        <strong>{labelize(asString(storageIscsiPlan.status) || "placeholder")}</strong>
        {stringArray(storageIscsiPlan.notes).map((note) => (
          <p key={note}>{note}</p>
        ))}
        {!stringArray(storageIscsiPlan.notes).length && (
          <p>Placeholder only. No volumes, LIFs, LUNs, or igroups are created.</p>
        )}
      </div>
      <h3>Upgrade Readiness Preview</h3>
      <div className="provider-callout">
        <strong>{labelize(asString(planPreview?.upgrade_readiness_preview.status) || "preview only")}</strong>
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
        <div>
          <h3>Disabled Dangerous Actions</h3>
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
        </div>
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
  return `read ${readable} / write ${writable}`;
}

function MockModeBanner() {
  const [health, setHealth] = useState<{ provider_mode: string; status: string } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .health()
      .then((nextHealth) => {
        setHealth(nextHealth);
        setError("");
      })
      .catch((err: Error) => {
        setHealth(null);
        setError(err.message);
      });
  }, []);

  const providerMode = health?.provider_mode ?? (error ? "unverified" : "checking");
  const verifiedMock = health?.provider_mode === "mock";
  const bannerClass = verifiedMock || (!health && !error) ? "mock-mode-banner" : "mock-mode-banner non-mock";

  return (
    <section
      className={bannerClass}
      aria-label="Mock provider safety mode"
    >
      {verifiedMock ? <ShieldCheck size={18} /> : <AlertTriangle size={18} />}
      <div>
        <strong>Provider mode: {providerMode}</strong>
        <p>{mockModeBannerMessage(providerMode, verifiedMock, Boolean(error))}</p>
        {error && <p>Health check error: {error}</p>}
      </div>
    </section>
  );
}

function mockModeBannerMessage(providerMode: string, verifiedMock: boolean, hasError: boolean): string {
  if (verifiedMock) {
    return "Local UI only. No real infrastructure calls are made; real adapters require explicit future configuration.";
  }
  if (hasError) {
    return "Health check unavailable. This operator UI expects PROVIDER_MODE=mock; do not continue lifecycle work until backend health is verified.";
  }
  if (providerMode === "local-readonly") {
    return "Real lab read-only mode. Lifecycle execution remains mock-only; Provider Status probes require explicit actions and local safety acknowledgements.";
  }
  if (providerMode === "local-lab-readwrite") {
    return "Real lab read/write mode. Discovery, planning, and explicitly gated apply workflows are available only through local-lab controls and confirmation gates.";
  }
  return "Verifying backend provider mode; local workflow pages require mock mode.";
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
        <PanelTitle icon={<ShieldCheck size={18} />} title="Mock-Only Safety" />
        <p>
          This run uses provider <strong>{run.provider}</strong>. The plan and result are local mock data;
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
          <Info label="Mock Task" value={result.mockTaskId} />
          <Info label="Mock VM" value={result.mockVmId} />
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
        {artifact.mock_only && <span>Mock only</span>}
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
    metadataSummaryItem("Mock task", metadata.mock_task_id),
    metadataSummaryItem("Mock VM", metadata.mock_vm_id),
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

function Page({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Infrastructure Configuration</p>
          <h1>{title}</h1>
        </div>
        <div className="page-actions">{actions}</div>
      </header>
      {children}
    </>
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
  return <span className={`status status-${status}`}>{labelize(status)}</span>;
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
      reason: "Approval is recorded; the next safe step is mock planning."
    };
  }
  if (sectionId === "planned_ready_to_execute") {
    return {
      label: "Launch mock execution",
      reason: "A persisted dry-run plan is ready for explicit mock execution."
    };
  }
  if (sectionId === "executing") {
    return {
      label: "Monitor run",
      reason: "Mock execution is in progress; watch stages, logs, and audit events."
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
    return "Required intent fields are present; submit will run mock source-of-truth validation.";
  }
  if (action === "approve") {
    return "Validation passed; approving records the decision and unlocks dry-run planning.";
  }
  if (action === "plan") {
    return "Approval is recorded; planning will create a mock dry-run plan.";
  }
  if (action === "execute") {
    return "A valid persisted dry-run plan exists; execution remains mock-only.";
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
      message: "Mock execution completed; review the result summary, audit trail, and report placeholders."
    };
  }
  if (run.status === "executing") {
    return {
      status: "executing",
      message: "Mock execution is in progress; monitor stage events and audit records."
    };
  }
  if (run.status === "failed") {
    return {
      status: "failed",
      message: run.error_message ?? "Mock execution failed; review blockers and audit details."
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
      message: "Review the dry-run plan before launching mock execution."
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
