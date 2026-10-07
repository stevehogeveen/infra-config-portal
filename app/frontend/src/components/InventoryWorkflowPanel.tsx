import { useEffect, useState } from "react";
import { Play, RefreshCw } from "lucide-react";
import { api } from "../api";
import type { InventoryRun } from "../types";

export function InventoryWorkflowPanel(props: { deviceId: string; currentHost: string | null }) {
  return <DeviceInventoryWorkflow key={JSON.stringify([props.deviceId, props.currentHost])} {...props} />;
}

function DeviceInventoryWorkflow({ deviceId }: { deviceId: string }) {
  const [run, setRun] = useState<InventoryRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const pending = run !== null && ["queued", "started", "deferred", "scheduled"].includes(run.status);

  useEffect(() => {
    let active = true;
    let inFlight = false;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      if (!active || inFlight || document.hidden) return;
      inFlight = true;
      try {
        const next = await api.latestInventoryJob(deviceId);
        if (!active) return;
        setRun(next);
        setError("");
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "Inventory status unavailable.");
      } finally {
        inFlight = false;
        if (active) {
          setLoading(false);
          if (!document.hidden) timer = setTimeout(() => void refresh(), 5000);
        }
      }
    }
    function visibilityChanged() {
      clearTimeout(timer);
      if (!document.hidden) void refresh();
    }
    document.addEventListener("visibilitychange", visibilityChanged);
    void refresh();
    return () => { active = false; clearTimeout(timer); document.removeEventListener("visibilitychange", visibilityChanged); };
  }, [deviceId]);

  async function start() {
    setSubmitting(true);
    setError("");
    try {
      setRun(await api.createInventoryJob(deviceId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Inventory could not be queued.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="inventory-workflow" aria-label="Inventory workflow">
      <header>
        <div><h3>System inventory</h3><p>Read-only &middot; {run?.status ?? "Not checked"}</p></div>
        <button className="rack-action" disabled={loading || submitting || pending} onClick={() => void start()} type="button">
          {pending ? <RefreshCw size={15} /> : <Play size={15} />}
          {submitting ? "Queuing..." : pending ? "Inventory pending" : "Read inventory"}
        </button>
      </header>
      {error ? <p role="alert">{error}</p> : null}
      {run?.result ? (
        <div aria-live="polite">
          <p>{run.result.summary}</p>
          <p>{run.result.source === "mock" ? "Mock result" : run.current ? "Current observation" : "Historical observation"} &middot; {new Date(run.result.checked_at).toLocaleString()}</p>
          {run.result.systems.map((system, index) => (
            <dl key={index}>
              <div><dt>Model</dt><dd>{system.model || "Unknown"}</dd></div>
              <div><dt>Manufacturer</dt><dd>{system.manufacturer || "Unknown"}</dd></div>
              <div><dt>Serial</dt><dd>{system.serial_number || "Unknown"}</dd></div>
              <div><dt>Power</dt><dd>{system.power_state || "Unknown"}</dd></div>
            </dl>
          ))}
        </div>
      ) : run?.status === "failed" ? <p>Worker execution failed. Check the automation service before retrying.</p>
        : run?.status === "expired" ? <p>The job expired. Check worker availability and request a fresh inventory.</p> : null}
    </section>
  );
}
