import {
  Activity,
  CheckCircle2,
  ClipboardList,
  Gauge,
  HardDrive,
  History,
  Layers,
  Play,
  Plus,
  RefreshCw,
  Route,
  Server,
  ShieldCheck,
  Send,
  Workflow
} from "lucide-react";
import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import { Link, NavLink, Route as RouterRoute, Routes, useNavigate, useParams } from "react-router-dom";

import { api } from "./api";
import type {
  AuditEvent,
  Catalog,
  ProviderStatus,
  RequestRecord,
  RequestStatus,
  VMDeploymentCreate,
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
  "cancelled"
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
          <NavItem to="/requests/new" icon={<Plus size={18} />} label="New VM Request" />
          <NavItem to="/audit-events" icon={<History size={18} />} label="Audit Events" />
          <NavItem to="/providers" icon={<Activity size={18} />} label="Provider Status" />
        </nav>
      </aside>
      <main className="content">
        <Routes>
          <RouterRoute path="/" element={<Dashboard />} />
          <RouterRoute path="/requests/new" element={<NewRequest />} />
          <RouterRoute path="/requests/:id" element={<RequestDetail />} />
          <RouterRoute path="/workflow-runs/:id" element={<WorkflowRunDetail />} />
          <RouterRoute path="/audit-events" element={<AuditEvents />} />
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
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .requests()
      .then(setRequests)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const counts = useMemo(() => {
    return statusOrder.reduce<Record<string, number>>((acc, status) => {
      acc[status] = requests.filter((request) => request.status === status).length;
      return acc;
    }, {});
  }, [requests]);

  return (
    <Page title="Dashboard" actions={<ButtonLink to="/requests/new" icon={<Plus size={16} />} label="New VM" />}>
      <Feedback loading={loading} error={error} />
      <section className="metric-grid">
        <Metric label="Requests" value={requests.length} icon={<ClipboardList size={18} />} />
        <Metric label="Needs Approval" value={counts.needs_approval ?? 0} icon={<ShieldCheck size={18} />} />
        <Metric label="Planned" value={counts.planned ?? 0} icon={<Workflow size={18} />} />
        <Metric label="Completed" value={counts.completed ?? 0} icon={<CheckCircle2 size={18} />} />
      </section>
      <section className="panel">
        <PanelTitle icon={<Layers size={18} />} title="Recent Requests" />
        <RequestTable requests={requests.slice(0, 10)} />
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
  const [error, setError] = useState("");
  const [approval, setApproval] = useState({ approver: "change.manager", notes: "" });
  const [busy, setBusy] = useState("");
  const [lastRunId, setLastRunId] = useState("");

  async function load() {
    if (!id) return;
    setError("");
    try {
      setRequest(await api.request(id));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  useEffect(() => {
    load();
  }, [id]);

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
          setRequest(await api.request(request?.id ?? ""));
        }
      } else {
        setRequest(result);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy("");
    }
  }

  if (!request) {
    return (
      <Page title="Request Detail">
        <Feedback loading={!error} error={error} />
      </Page>
    );
  }

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
      <section className="detail-grid">
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
        <div className="action-row">
          <button disabled={request.status !== "draft" || Boolean(busy)} onClick={() => runAction("submit", () => api.submit(request.id))}>
            <Send size={16} />
            Submit
          </button>
          <button disabled={request.status !== "approved" || Boolean(busy)} onClick={() => runAction("plan", () => api.plan(request.id))}>
            <Workflow size={16} />
            Plan
          </button>
          <button disabled={request.status !== "planned" || Boolean(busy)} onClick={() => runAction("execute", () => api.execute(request.id))}>
            <Play size={16} />
            Execute
          </button>
          <button onClick={load} disabled={Boolean(busy)}>
            <RefreshCw size={16} />
            Refresh
          </button>
        </div>
      </section>
      <section className="panel">
        <PanelTitle icon={<ShieldCheck size={18} />} title="Approval" />
        <div className="approval-row">
          <input value={approval.approver} onChange={(event) => setApproval({ ...approval, approver: event.target.value })} />
          <input value={approval.notes} placeholder="Notes" onChange={(event) => setApproval({ ...approval, notes: event.target.value })} />
          <button
            className="primary"
            disabled={request.status !== "needs_approval" || Boolean(busy)}
            onClick={() => runAction("approve", () => api.approve(request.id, approval.approver, approval.notes))}
          >
            <CheckCircle2 size={16} />
            Approve
          </button>
        </div>
      </section>
    </Page>
  );
}

function WorkflowRunDetail() {
  const { id } = useParams();
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;
    api.workflowRun(id).then(setRun).catch((err: Error) => setError(err.message));
  }, [id]);

  return (
    <Page title="Workflow Run" actions={run ? <StatusBadge status={run.status} /> : null}>
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
          <JsonPanel title="Plan" data={run.plan_json} />
          {run.result_json && <JsonPanel title="Result" data={run.result_json} />}
        </>
      )}
    </Page>
  );
}

function AuditEvents() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api.auditEvents().then(setEvents).catch((err: Error) => setError(err.message));
  }, []);

  return (
    <Page title="Audit Events">
      <Feedback error={error} />
      <section className="panel">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Event</th>
              <th>Actor</th>
              <th>Status</th>
              <th>Message</th>
            </tr>
          </thead>
          <tbody>
            {events.map((event) => (
              <tr key={event.id}>
                <td>{formatDateTime(event.created_at)}</td>
                <td>{event.event_type}</td>
                <td>{event.actor}</td>
                <td>{`${event.from_status ?? "-"} -> ${event.to_status ?? "-"}`}</td>
                <td>{event.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </Page>
  );
}

function ProviderStatusPage() {
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api.providers().then(setProviders).catch((err: Error) => setError(err.message));
  }, []);

  return (
    <Page title="Provider Status">
      <Feedback error={error} />
      <section className="provider-grid">
        {providers.map((provider) => (
          <article className="provider-card" key={provider.name}>
            <div className="provider-head">
              <HardDrive size={18} />
              <div>
                <h2>{provider.name}</h2>
                <p>{provider.kind}</p>
              </div>
              <StatusBadge status={provider.status} />
            </div>
            <p>{provider.message}</p>
            <div className="tag-row">
              <span>{provider.mode}</span>
              {provider.capabilities.map((capability) => (
                <span key={capability}>{capability}</span>
              ))}
            </div>
          </article>
        ))}
      </section>
    </Page>
  );
}

function RequestTable({ requests }: { requests: RequestRecord[] }) {
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
            <td>{formatDateTime(request.updated_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
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

function labelize(value: string) {
  return value.replace(/_/g, " ");
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString();
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString();
}

export default App;
