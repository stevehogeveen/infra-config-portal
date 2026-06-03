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
  CiscoSetupReadiness,
  CiscoSetupWizardPlan,
  ConsoleCandidate,
  IloUpgradeReadiness,
  MediaInventory,
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
  const [selectedQueueKey, setSelectedQueueKey] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

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

  useEffect(() => {
    load();
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
    </Page>
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
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyProvider, setBusyProvider] = useState("");
  const [busyPromptReadiness, setBusyPromptReadiness] = useState(false);
  const [probeResults, setProbeResults] = useState<Record<string, ProviderProbeResult>>({});
  const [promptReadinessResult, setPromptReadinessResult] = useState<ProviderProbeResult | null>(null);

  async function load() {
    setError("");
    setLoading(true);
    try {
      const [providerStatuses, ciscoReadiness, setupWizardPlan] = await Promise.all([
        api.providers(),
        api.ciscoSetupReadiness(),
        api.ciscoSetupWizardPlan()
      ]);
      setProviders(providerStatuses);
      setCiscoSetupReadiness(ciscoReadiness);
      setCiscoSetupWizardPlan(setupWizardPlan);
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

  const orderedProviders = [...providers].sort((left, right) => {
    return providerOrder(left.id) - providerOrder(right.id);
  });

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
      {ciscoSetupReadiness && (
        <CiscoSetupReadinessPanel
          readiness={ciscoSetupReadiness}
          setupWizardPlan={ciscoSetupWizardPlan}
        />
      )}
      <section className="provider-status-stack">
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
      </section>
    </Page>
  );
}

function CiscoSetupReadinessPanel({
  readiness,
  setupWizardPlan
}: {
  readiness: CiscoSetupReadiness;
  setupWizardPlan: CiscoSetupWizardPlan | null;
}) {
  const setupWizardDetected = Boolean(
    setupWizardPlan?.setup_wizard_detected || readiness.setup_wizard_plan?.detected
  );
  const displayedNextAction = setupWizardDetected
    ? "Review setup wizard plan preview."
    : readiness.next_safe_action;

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
        <ProviderFact label="Ansible Path" value={readiness.ansible.enabled ? "Enabled" : "Blocked"} />
      </div>
      <div className="provider-fact-grid compact">
        <ProviderFact label="Recommended Console" value={readiness.console.recommended_path ?? "-"} />
        <ProviderFact label="Effective Console" value={readiness.console.effective_path ?? "-"} />
        <ProviderFact
          label="Console Candidates"
          value={`${readiness.console.candidate_count} total, ${readiness.console.stable_candidate_count} stable, ${readiness.console.fallback_candidate_count} fallback`}
        />
        <ProviderFact label="Prompt Readiness" value={readiness.console.safe_next_action} />
      </div>
      <div className="setup-preview-grid">
        <SetupPreviewBlock
          title="Bootstrap Preview"
          tag="Plan only"
          lines={readiness.bootstrap_preview.summary}
        />
        <SetupPreviewBlock
          title="SSH/SCP Readiness"
          tag="Disabled"
          lines={[readiness.ssh_scp_readiness.summary]}
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
  return (
    <div className="setup-preview-block">
      <div>
        <h3>{title}</h3>
        <span className="action-tag disabled">{tag}</span>
      </div>
      {lines.map((line) => (
        <p key={line}>{line}</p>
      ))}
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
      {["cisco-ansible", "esxi-readonly"].includes(provider.id) && (
        <ManagementTargetDetails provider={provider} />
      )}
      {!["cisco-console", "ilo-redfish", "cisco-ansible", "esxi-readonly"].includes(provider.id) && (
        <GenericProviderDetails provider={provider} />
      )}
      <ProviderIssueRows blockers={provider.blockers} warnings={provider.warnings} />
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
  const promptReadinessEnabled = provider.mode === "local-readonly" && provider.status === "ready";

  return (
    <div className="provider-detail-section">
      <div className="provider-callout">
        <strong>{labelize(asString(discovery.selection_source) || asString(discovery.status) || "discovery")}</strong>
        <p>{asString(discovery.safe_next_action) || "Review local console discovery before probing."}</p>
      </div>
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
        <p className="muted">No serial console candidates were discovered.</p>
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
          </div>
          <p className="provider-redaction-note">
            {promptReadinessMessage(promptReadinessResult)}
          </p>
          <JsonDetails title="Raw redacted prompt readiness result" data={promptReadinessResult} />
        </div>
      )}
    </div>
  );
}

function IloRedfishDetails({ provider }: { provider: ProviderStatus }) {
  const [readiness, setReadiness] = useState<IloUpgradeReadiness | null>(null);
  const [error, setError] = useState("");
  const config = provider.configuration;
  const missingFields = stringArray(config.missing_fields);

  useEffect(() => {
    let cancelled = false;
    api
      .iloUpgradeReadiness()
      .then((payload) => {
        if (!cancelled) {
          setReadiness(payload);
          setError("");
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setReadiness(null);
          setError(err.message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [provider.last_probe_time, provider.status]);

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
      <IloUpgradeDecisionPanel error={error} readiness={readiness} />
    </div>
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

function providerOrder(id: string): number {
  const order = [
    "ilo-redfish",
    "cisco-console",
    "cisco-ansible",
    "esxi-readonly",
    "mock-vsphere",
    "mock-netapp",
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
  if (promptState === "exec") {
    return "Prompt is ready for future safe show-command checks.";
  }
  if (promptState === "setup-wizard") {
    return "Console is at an initial setup wizard prompt; no answers or commands were sent.";
  }
  return asString(result.message) || "Prompt readiness result is redacted.";
}

function objectValue(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
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
